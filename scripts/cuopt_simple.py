"""
Ultra-simple cuOpt MILP solver: minimal constraints, pure binary, stable.

Philosophy:
- Schedule all parts with hard constraints (overlap, court pairs, max 2 courts)
- Soft constraints via simple linear penalties (court number, late start, unscheduled)
- NO tracking of spans/gaps/blocks (post-processing only)
- Target: <100K constraints for numerical stability
"""

import sys
from pathlib import Path

# Import from ortools_planner for data structures
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
    """Ultra-simple cuOpt solver: only essential constraints."""
    
    if not CUOPT_AVAILABLE:
        return {
            "status": "ERROR",
            "date": date,
            "error": f"cuOpt not available: {CUOPT_IMPORT_ERROR}",
            "rows": []
        }
    
    # Filter teams for this date
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
    
    # Time slots (15-min intervals from 08:30 to 20:00)
    start_min = 8 * 60 + 30
    end_min = 20 * 60
    num_slots = (end_min - start_min) // 15
    slot_mins = [start_min + i * 15 for i in range(num_slots)]
    
    courts = list(range(1, 11))
    COURT_PAIRS = [(1,2), (3,4), (5,6), (7,8), (9,10)]
    
    # Reserved slots
    reserved_set = {(r.court, r.kind) for r in reservations if r.date == date}
    
    print(f"[cuOpt-simple] Planning {date}: {num_teams} teams, {num_parts} parts, {num_slots} slots, {len(courts)} courts")
    
    # =========================================================================
    # DECISION VARIABLES
    # =========================================================================
    
    problem = Problem(f"scheduler_{date}")
    
    # x[part_idx, slot_idx, court]: binary, 1 if part starts at slot on court
    x = {}
    for p_idx, part in enumerate(parts):
        team = day_teams[part["team_idx"]]
        is_youth = "groen" in team.schema.lower() or "ju" in team.schema.lower()
        
        for s_idx in range(num_slots):
            start_time = slot_mins[s_idx]
            
            # Youth constraint: no start before 08:30
            if is_youth and start_time < 8*60 + 30:
                continue
            
            # Check slot doesn't overflow
            if s_idx + part["duration_slots"] > num_slots:
                continue
            
            for c in courts:
                # Check reserved slots
                overlaps_reserved = any(
                    (c, date) in reserved_set
                    for offset in range(part["duration_slots"])
                )
                if overlaps_reserved:
                    continue
                
                x[(p_idx, s_idx, c)] = problem.addVariable(
                    name=f"x_p{p_idx}_s{s_idx}_c{c}",
                    vtype=INTEGER,
                    lb=0,
                    ub=1
                )
    
    # unscheduled[part_idx]: binary, 1 if not scheduled
    unscheduled = {}
    for p_idx in range(num_parts):
        unscheduled[p_idx] = problem.addVariable(
            name=f"unsch_{p_idx}",
            vtype=INTEGER,
            lb=0,
            ub=1
        )
    
    # team_uses_court[team_idx, court]: binary, 1 if team uses this court
    team_uses_court = {}
    for t_idx in range(num_teams):
        for c in courts:
            team_uses_court[(t_idx, c)] = problem.addVariable(
                name=f"tc_{t_idx}_{c}",
                vtype=INTEGER,
                lb=0,
                ub=1
            )
    
    print(f"[cuOpt-simple] Created {len(x)} schedule vars + {num_parts} unscheduled + {num_teams*10} team_court vars")
    
    # =========================================================================
    # HARD CONSTRAINTS
    # =========================================================================
    
    constraint_count = 0
    
    # 1. Each part scheduled exactly once OR unscheduled
    for p_idx in range(num_parts):
        vars_for_part = [x[(p, s, c)] for (p, s, c) in x.keys() if p == p_idx]
        if vars_for_part:
            problem.addConstraint(
                sum(vars_for_part) + unscheduled[p_idx] == 1,
                name=f"part_{p_idx}_once"
            )
            constraint_count += 1
        else:
            problem.addConstraint(unscheduled[p_idx] == 1, name=f"part_{p_idx}_must_unsch")
            constraint_count += 1
    
    # 2. No court overlaps (at most 1 part active per court per slot)
    for c in courts:
        for s_idx in range(num_slots):
            overlapping = []
            for (p, s, court) in x.keys():
                if court != c:
                    continue
                part = parts[p]
                if s <= s_idx < s + part["duration_slots"]:
                    overlapping.append(x[(p, s, court)])
            
            if overlapping:
                problem.addConstraint(
                    sum(overlapping) <= 1,
                    name=f"court_{c}_slot_{s_idx}"
                )
                constraint_count += 1
    
    # 3. Link x to team_uses_court
    for t_idx in range(num_teams):
        part_indices = team_parts[t_idx]
        for c in courts:
            # If any part of team t is on court c, then team_uses_court[t,c] = 1
            parts_on_c = [x[(p, s, court)] for (p, s, court) in x.keys() 
                          if p in part_indices and court == c]
            if parts_on_c:
                # team_uses_court[t,c] >= any x
                for var in parts_on_c:
                    problem.addConstraint(
                        team_uses_court[(t_idx, c)] >= var,
                        name=f"link_t{t_idx}_c{c}_{parts_on_c.index(var)}"
                    )
                    constraint_count += 1
    
    # 4. Max 2 courts per team
    for t_idx in range(num_teams):
        problem.addConstraint(
            sum(team_uses_court[(t_idx, c)] for c in courts) <= 2,
            name=f"team_{t_idx}_max2courts"
        )
        constraint_count += 1
    
    # 5. Court pairing: teams must use adjacent courts only
    for t_idx in range(num_teams):
        team = day_teams[t_idx]
        # For each pair, if team uses any court in pair, it can only use that pair
        for pair_idx, (c1, c2) in enumerate(COURT_PAIRS):
            # If team uses c1 or c2, it cannot use courts outside this pair
            uses_pair = team_uses_court[(t_idx, c1)] + team_uses_court[(t_idx, c2)]
            for other_c in courts:
                if other_c not in [c1, c2]:
                    # uses_pair > 0 => team_uses_court[t, other_c] = 0
                    # Linearize: team_uses_court[t, other_c] <= 2 - uses_pair
                    problem.addConstraint(
                        team_uses_court[(t_idx, other_c)] <= 2 - uses_pair,
                        name=f"pair_t{t_idx}_p{pair_idx}_excl{other_c}"
                    )
                    constraint_count += 1
    
    print(f"[cuOpt-simple] Added {constraint_count} constraints")
    
    # =========================================================================
    # OBJECTIVE
    # =========================================================================
    
    objective_terms = []
    
    # Heavy penalty for unscheduled (10M per part)
    UNSCHEDULED_PENALTY = 10_000_000
    for p_idx in range(num_parts):
        objective_terms.append(UNSCHEDULED_PENALTY * unscheduled[p_idx])
    
    # Court number penalty (prefer low courts)
    COURT_PENALTY = 100_000
    for (p, s, c) in x.keys():
        objective_terms.append(COURT_PENALTY * c * x[(p, s, c)])
    
    # Late start penalty (prefer earlier slots)
    LATE_PENALTY = 50_000
    for (p, s, c) in x.keys():
        if slot_mins[s] > 16 * 60:
            lateness = (slot_mins[s] - 16*60) / 100
            objective_terms.append(LATE_PENALTY * lateness * x[(p, s, c)])
    
    problem.setObjective(sum(objective_terms), sense=MINIMIZE)
    
    # =========================================================================
    # SOLVE
    # =========================================================================
    
    print(f"[cuOpt-simple] Solving with {len(x) + num_parts + num_teams*10} vars, {constraint_count} constraints")
    print(f"[cuOpt-simple] Time limit: {time_limit_s}s")
    
    settings = SolverSettings()
    settings.set_parameter("time_limit", time_limit_s)
    settings.set_parameter("log_to_console", 1)
    settings.set_parameter("mip_relative_gap", 0.01)
    
    problem.solve(settings)
    
    # =========================================================================
    # EXTRACT SOLUTION
    # =========================================================================
    
    if problem.Status.name not in ["Optimal", "FeasibleFound"]:
        print(f"[cuOpt-simple] Solver failed: {problem.Status.name}")
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
    
    print(f"[cuOpt-simple] Solution: {problem.Status.name}, objective: {problem.ObjValue:.2f}")
    
    # Extract assignments
    assignment = {}
    for (p, s, c), var in x.items():
        if var.getValue() > 0.5:
            assignment[p] = (s, c)
    
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
    
    print(f"[cuOpt-simple] Scheduled {scheduled_count}/{num_parts} parts")
    if unscheduled_parts:
        print(f"[cuOpt-simple] Unscheduled: {[parts[p]['part_label'] for p in unscheduled_parts]}")
    
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
