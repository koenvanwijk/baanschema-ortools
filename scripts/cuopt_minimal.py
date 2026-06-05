"""
Minimal cuOpt MILP solver: absolute minimum constraints, pair-based court assignment.

Key simplifications:
- Use court PAIRS instead of individual courts (reduces vars and constraints 2x)
- Minimal linking constraints (only pair-level, not per-court)
- Simple objective: unscheduled penalty + pair-number penalty
- Target: <10K constraints for maximum stability
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ortools_planner import (
    ROOT, INPUT, TeamDay, Reservation,
    parse_input, build_parts, player_demand
)

try:
    from cuopt.linear_programming.problem import Problem, INTEGER, MINIMIZE
    from cuopt.linear_programming.solver_settings import SolverSettings
    CUOPT_AVAILABLE = True
except ImportError as e:
    CUOPT_AVAILABLE = False
    CUOPT_IMPORT_ERROR = str(e)


def solve_day(date, teams, reservations, time_limit_s=60):
    """Minimal cuOpt solver with pair-based court assignment."""
    
    if not CUOPT_AVAILABLE:
        return {
            "status": "ERROR",
            "date": date,
            "error": f"cuOpt not available: {CUOPT_IMPORT_ERROR}",
            "rows": []
        }
    
    day_teams = [t for t in teams if t.date == date]
    if not day_teams:
        return {"status": "ERROR", "date": date, "error": "No teams", "rows": []}
    
    # Build parts
    parts = []
    team_parts = {}
    for t_idx, team in enumerate(day_teams):
        team_parts[t_idx] = []
        for part_label, part_kind in build_parts(team):
            duration_min = 90 if part_kind == "D" else 60
            parts.append({
                "team_idx": t_idx,
                "part_label": part_label,
                "part_kind": part_kind,
                "duration_min": duration_min,
                "duration_slots": (duration_min + 14) // 15,
            })
            team_parts[t_idx].append(len(parts) - 1)
    
    num_parts = len(parts)
    num_teams = len(day_teams)
    
    # Time slots
    start_min = 8 * 60 + 30
    end_min = 20 * 60
    num_slots = (end_min - start_min) // 15
    slot_mins = [start_min + i * 15 for i in range(num_slots)]
    
    # Court PAIRS (not individual courts)
    COURT_PAIRS = [(1,2), (3,4), (5,6), (7,8), (9,10)]
    
    # Reserved slots
    reserved_kinds = {r.kind for r in reservations if r.date == date}
    
    print(f"[cuOpt-minimal] Planning {date}: {num_teams} teams, {num_parts} parts, {num_slots} slots, {len(COURT_PAIRS)} pairs")
    
    # =========================================================================
    # DECISION VARIABLES
    # =========================================================================
    
    problem = Problem(f"scheduler_{date}")
    
    # x[part_idx, slot_idx, pair_idx, court_in_pair]: 
    #   binary, 1 if part starts at slot on (pair, court_in_pair)
    #   court_in_pair = 0 or 1 (left/right court in pair)
    x = {}
    for p_idx, part in enumerate(parts):
        team = day_teams[part["team_idx"]]
        is_youth = "groen" in team.schema.lower() or "ju" in team.schema.lower()
        
        for s_idx in range(num_slots):
            start_time = slot_mins[s_idx]
            
            if is_youth and start_time < 8*60 + 30:
                continue
            if s_idx + part["duration_slots"] > num_slots:
                continue
            if date in reserved_kinds:
                continue
            
            for pair_idx, (c1, c2) in enumerate(COURT_PAIRS):
                for court_in_pair, actual_court in enumerate([c1, c2]):
                    x[(p_idx, s_idx, pair_idx, court_in_pair)] = problem.addVariable(
                        name=f"x_p{p_idx}_s{s_idx}_pr{pair_idx}_c{court_in_pair}",
                        vtype=INTEGER,
                        lb=0,
                        ub=1
                    )
    
    # unscheduled[part_idx]
    unscheduled = {}
    for p_idx in range(num_parts):
        unscheduled[p_idx] = problem.addVariable(
            name=f"unsch_{p_idx}",
            vtype=INTEGER,
            lb=0,
            ub=1
        )
    
    # team_uses_pair[team_idx, pair_idx]
    team_uses_pair = {}
    for t_idx in range(num_teams):
        for pair_idx in range(len(COURT_PAIRS)):
            team_uses_pair[(t_idx, pair_idx)] = problem.addVariable(
                name=f"tp_{t_idx}_{pair_idx}",
                vtype=INTEGER,
                lb=0,
                ub=1
            )
    
    print(f"[cuOpt-minimal] Created {len(x)} schedule vars + {num_parts} unscheduled + {num_teams*len(COURT_PAIRS)} team_pair vars")
    
    # =========================================================================
    # HARD CONSTRAINTS
    # =========================================================================
    
    constraint_count = 0
    
    # 1. Each part scheduled exactly once OR unscheduled
    for p_idx in range(num_parts):
        vars_for_part = [x[k] for k in x.keys() if k[0] == p_idx]
        if vars_for_part:
            problem.addConstraint(
                sum(vars_for_part) + unscheduled[p_idx] == 1,
                name=f"part_{p_idx}_once"
            )
            constraint_count += 1
        else:
            problem.addConstraint(unscheduled[p_idx] == 1, name=f"part_{p_idx}_must_unsch")
            constraint_count += 1
    
    # 2. No overlaps on each physical court
    for pair_idx, (c1, c2) in enumerate(COURT_PAIRS):
        for court_in_pair in [0, 1]:  # 0=left (c1), 1=right (c2)
            for s_idx in range(num_slots):
                overlapping = []
                for (p, s, pr, cip), var in x.items():
                    if pr != pair_idx or cip != court_in_pair:
                        continue
                    part = parts[p]
                    if s <= s_idx < s + part["duration_slots"]:
                        overlapping.append(var)
                
                if overlapping:
                    problem.addConstraint(
                        sum(overlapping) <= 1,
                        name=f"pair{pair_idx}_c{court_in_pair}_s{s_idx}"
                    )
                    constraint_count += 1
    
    # 3. Link x to team_uses_pair (simplified: 1 constraint per team-pair combo)
    for t_idx in range(num_teams):
        part_indices = team_parts[t_idx]
        for pair_idx in range(len(COURT_PAIRS)):
            # If team uses this pair, team_uses_pair = 1
            parts_on_pair = [x[k] for k in x.keys() 
                            if k[0] in part_indices and k[2] == pair_idx]
            if parts_on_pair:
                # sum(x on pair) <= M * team_uses_pair[t, pair]
                # Simplified: team_uses_pair >= x for any x
                problem.addConstraint(
                    team_uses_pair[(t_idx, pair_idx)] >= sum(parts_on_pair) / len(parts_on_pair),
                    name=f"link_t{t_idx}_pr{pair_idx}"
                )
                constraint_count += 1
    
    # 4. Max 1 pair per team (court pairing constraint)
    for t_idx in range(num_teams):
        problem.addConstraint(
            sum(team_uses_pair[(t_idx, pair_idx)] for pair_idx in range(len(COURT_PAIRS))) <= 1,
            name=f"team_{t_idx}_max1pair"
        )
        constraint_count += 1
    
    print(f"[cuOpt-minimal] Added {constraint_count} constraints")
    
    # =========================================================================
    # OBJECTIVE
    # =========================================================================
    
    objective_terms = []
    
    # Heavy penalty for unscheduled
    UNSCHEDULED_PENALTY = 10_000_000
    for p_idx in range(num_parts):
        objective_terms.append(UNSCHEDULED_PENALTY * unscheduled[p_idx])
    
    # Pair number penalty (prefer lower pairs = lower courts)
    PAIR_PENALTY = 100_000
    for (p, s, pr, cip), var in x.items():
        objective_terms.append(PAIR_PENALTY * pr * var)
    
    # Court-in-pair penalty (prefer left court in each pair)
    COURT_IN_PAIR_PENALTY = 10_000
    for (p, s, pr, cip), var in x.items():
        objective_terms.append(COURT_IN_PAIR_PENALTY * cip * var)
    
    # Late start penalty
    LATE_PENALTY = 50_000
    for (p, s, pr, cip), var in x.items():
        if slot_mins[s] > 16 * 60:
            lateness = (slot_mins[s] - 16*60) / 100
            objective_terms.append(LATE_PENALTY * lateness * var)
    
    problem.setObjective(sum(objective_terms), sense=MINIMIZE)
    
    # =========================================================================
    # SOLVE
    # =========================================================================
    
    print(f"[cuOpt-minimal] Solving with {len(x) + num_parts + num_teams*len(COURT_PAIRS)} vars, {constraint_count} constraints")
    print(f"[cuOpt-minimal] Time limit: {time_limit_s}s")
    
    settings = SolverSettings()
    settings.set_parameter("time_limit", time_limit_s)
    settings.set_parameter("log_to_console", 1)
    settings.set_parameter("mip_relative_gap", 0.01)
    
    problem.solve(settings)
    
    # =========================================================================
    # EXTRACT SOLUTION
    # =========================================================================
    
    if problem.Status.name not in ["Optimal", "FeasibleFound"]:
        print(f"[cuOpt-minimal] Solver failed: {problem.Status.name}")
        rows = []
        for p_idx, part in enumerate(parts):
            team = day_teams[part["team_idx"]]
            rows.append({
                "team": team.schema,
                "team_id": part["team_idx"],
                "part": part["part_label"],
                "kind": part["part_kind"],
                "start": "NIET_GELUKT",
                "end": "NIET_GELUKT",
                "court": 0,
            })
        return {"status": "INFEASIBLE", "date": date, "rows": rows}
    
    print(f"[cuOpt-minimal] Solution: {problem.Status.name}, objective: {problem.ObjValue:.2f}")
    
    # Extract assignments
    assignment = {}
    for (p, s, pr, cip), var in x.items():
        if var.getValue() > 0.5:
            c1, c2 = COURT_PAIRS[pr]
            actual_court = c1 if cip == 0 else c2
            assignment[p] = (s, actual_court)
    
    # Check unscheduled
    unscheduled_parts = [p for p in range(num_parts) if unscheduled[p].getValue() > 0.5]
    
    # Build rows
    def fmt_time(minutes):
        return f"{minutes//60:02d}:{minutes%60:02d}"
    
    rows = []
    scheduled_count = 0
    for p_idx, part in enumerate(parts):
        team = day_teams[part["team_idx"]]
        if p_idx in assignment:
            s_idx, c = assignment[p_idx]
            start_time = slot_mins[s_idx]
            end_time = start_time + part["duration_min"]
            rows.append({
                "team": team.schema,
                "team_id": part["team_idx"],
                "part": part["part_label"],
                "kind": part["part_kind"],
                "start": fmt_time(start_time),
                "end": fmt_time(end_time),
                "court": c,
            })
            scheduled_count += 1
        else:
            rows.append({
                "team": team.schema,
                "team_id": part["team_idx"],
                "part": part["part_label"],
                "kind": part["part_kind"],
                "start": "NIET_GELUKT",
                "end": "NIET_GELUKT",
                "court": 0,
            })
    
    print(f"[cuOpt-minimal] Scheduled {scheduled_count}/{num_parts} parts")
    if unscheduled_parts:
        print(f"[cuOpt-minimal] Unscheduled: {[parts[p]['part_label'] for p in unscheduled_parts]}")
    
    return {
        "status": "OPTIMAL" if problem.Status.name == "Optimal" else "FEASIBLE",
        "date": date,
        "rows": rows,
        "objective_value": problem.ObjValue,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--time-limit", type=int, default=60)
    args = parser.parse_args()
    
    teams, reservations = parse_input(INPUT)
    result = solve_day(args.date, teams, reservations, args.time_limit)
    
    print(f"\nStatus: {result['status']}")
    print(f"Date: {result['date']}")
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        scheduled = sum(1 for r in result["rows"] if r["start"] != "NIET_GELUKT")
        print(f"Scheduled: {scheduled}/{len(result['rows'])} parts")
        if scheduled < len(result["rows"]):
            failed = [r for r in result["rows"] if r["start"] == "NIET_GELUKT"]
            print(f"Failed: {len(failed)} parts")
            for r in failed[:5]:
                print(f"  - {r['team']} {r['part']}")


if __name__ == "__main__":
    main()
