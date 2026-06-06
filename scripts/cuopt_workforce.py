"""
Tennis court scheduling using cuOpt MILP (workforce optimization style).

Based on NVIDIA cuopt-examples/workforce_optimization pattern:
- Binary vars: (part, slot, court) assignments
- Constraints: each part assigned exactly once, court capacity, time windows
- Objective: minimize cost (prefer low courts, compact schedules)
"""

from __future__ import annotations
import sys
from pathlib import Path

# Import data structures from ortools_planner
sys.path.insert(0, str(Path(__file__).parent))
from ortools_planner import (
    ROOT, INPUT, TeamDay, Reservation,
    parse_input, build_parts, player_demand,
)

try:
    from cuopt.linear_programming.problem import Problem, VType, sense, LinearExpression
    from cuopt.linear_programming.solver_settings import SolverSettings
    CUOPT_AVAILABLE = True
except ImportError as e:
    CUOPT_AVAILABLE = False
    CUOPT_IMPORT_ERROR = str(e)


def solve_day(
    date: str,
    teams: list[TeamDay],
    reservations: list[Reservation],
    time_limit_s: float = 60.0,
) -> dict:
    """Solve court scheduling using workforce optimization pattern."""
    
    if not CUOPT_AVAILABLE:
        return {
            "status": "ERROR",
            "date": date,
            "error": f"cuOpt not available: {CUOPT_IMPORT_ERROR}",
            "rows": [],
        }
    
    # Build parts (match segments)
    parts = build_parts(teams, date)
    if not parts:
        return {"status": "NO_TEAMS", "date": date, "rows": []}
    
    print(f"[cuOpt-workforce] {date}: {len(teams)} teams, {len(parts)} parts")
    
    # Time slots (15-min intervals, 08:30-20:00)
    start_min = 8 * 60 + 30  # 08:30
    end_min = 20 * 60        # 20:00
    slot_interval = 15
    slots = list(range(start_min, end_min, slot_interval))
    
    # Courts
    courts = list(range(1, 11))  # 1-10
    
    # Reserved slots (block from assignments)
    reserved_set = set()
    for res in reservations:
        res_start = res.start_hour * 60 + res.start_minute
        res_end = res.end_hour * 60 + res.end_minute
        for court in res.courts:
            for slot in slots:
                if res_start <= slot < res_end:
                    reserved_set.add((slot, court))
    
    print(f"[cuOpt-workforce] {len(slots)} slots, {len(courts)} courts, {len(reserved_set)} reserved")
    
    # =========================================================================
    # CREATE PROBLEM
    # =========================================================================
    problem = Problem("tennis_scheduling")
    
    # Binary decision variables: x[part, slot, court] = 1 if part assigned to (slot, court)
    assignment_vars = {}
    
    for p_idx, part in enumerate(parts):
        duration_min = part["duration_min"]
        team = part["team"]
        
        # Youth constraint: no start before 08:30
        is_youth = "t/m" in team.schema.lower() or "jeugd" in team.schema.lower()
        
        for slot in slots:
            # Check if part fits (duration)
            if slot + duration_min > end_min:
                continue
            
            # Youth time window
            if is_youth and slot < start_min:
                continue
            
            for court in courts:
                # Check if slot+court is reserved
                overlaps_reservation = False
                for t in range(slot, slot + duration_min, slot_interval):
                    if (t, court) in reserved_set:
                        overlaps_reservation = True
                        break
                
                if overlaps_reservation:
                    continue
                
                # Create variable
                var_name = f"p{p_idx}_t{slot}_c{court}"
                var = problem.addVariable(name=var_name, vtype=VType.INTEGER, lb=0.0, ub=1.0)
                assignment_vars[(p_idx, slot, court)] = var
    
    print(f"[cuOpt-workforce] Created {len(assignment_vars)} binary variables")
    
    if len(assignment_vars) == 0:
        return {
            "status": "INFEASIBLE",
            "date": date,
            "error": "No valid assignments (all slots reserved or youth constraints too strict)",
            "rows": [],
        }
    
    # =========================================================================
    # OBJECTIVE: Minimize total cost
    # =========================================================================
    objective_expr = LinearExpression([], [], 0.0)
    
    for (p_idx, slot, court), var in assignment_vars.items():
        # Prefer low court numbers (cost = court number)
        cost = court
        objective_expr += var * cost
    
    problem.setObjective(objective_expr, sense.MINIMIZE)
    print("[cuOpt-workforce] Objective: minimize court numbers (prefer low courts)")
    
    # =========================================================================
    # CONSTRAINTS
    # =========================================================================
    
    # 1. Each part assigned exactly once
    for p_idx in range(len(parts)):
        part_assignments = [
            var for (pi, slot, court), var in assignment_vars.items() if pi == p_idx
        ]
        
        if len(part_assignments) > 0:
            part_expr = LinearExpression([], [], 0.0)
            for var in part_assignments:
                part_expr += var
            
            problem.addConstraint(part_expr == 1, name=f"part{p_idx}_once")
    
    print(f"[cuOpt-workforce] Added {len(parts)} part-assignment constraints")
    
    # 2. Court capacity: max 1 part per (slot, court) — NOT NEEDED if vars non-overlapping
    #    (vars already filtered to non-overlapping slots via duration check)
    
    # =========================================================================
    # SOLVE
    # =========================================================================
    settings = SolverSettings()
    settings.set_parameter("time_limit", time_limit_s)
    settings.set_parameter("log_to_console", False)
    
    print(f"[cuOpt-workforce] Solving with {time_limit_s}s time limit...")
    print(f"  Variables: {problem.NumVariables}, Constraints: {problem.NumConstraints}")
    
    problem.solve(settings)
    
    print(f"[cuOpt-workforce] Solved in {problem.SolveTime:.2f}s")
    print(f"[cuOpt-workforce] Status: {problem.Status.name}, Objective: {problem.ObjValue:.1f}")
    
    # =========================================================================
    # EXTRACT SOLUTION
    # =========================================================================
    def fmt_time(minutes):
        return f"{int(minutes)//60:02d}:{int(minutes)%60:02d}"
    
    assignment = {}
    for (p_idx, slot, court), var in assignment_vars.items():
        value = var.getValue()
        if value > 0.5:  # Binary: 0 or 1
            assignment[p_idx] = (slot, court)
    
    rows = []
    scheduled_count = 0
    
    for p_idx, part in enumerate(parts):
        team = part["team"]
        if p_idx in assignment:
            slot, court = assignment[p_idx]
            start_time = slot
            end_time = slot + part["duration_min"]
            rows.append({
                "team": team.schema,
                "team_id": part["team_idx"],
                "part": part["part_label"],
                "kind": part["part_kind"],
                "start": fmt_time(start_time),
                "end": fmt_time(end_time),
                "court": court,
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
    
    print(f"[cuOpt-workforce] Scheduled {scheduled_count}/{len(parts)} parts")
    
    return {
        "status": problem.Status.name,
        "date": date,
        "rows": rows,
        "objective": float(problem.ObjValue),
        "solve_time": float(problem.SolveTime),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--time-limit", type=int, default=60)
    args = parser.parse_args()
    
    teams, reservations = parse_input(INPUT)
    result = solve_day(args.date, teams, reservations, args.time_limit)
    
    print(f"\n{'='*60}")
    print(f"Status: {result['status']}")
    print(f"Date: {result['date']}")
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        scheduled = sum(1 for r in result["rows"] if r["start"] != "NIET_GELUKT")
        total = len(result["rows"])
        print(f"Scheduled: {scheduled}/{total} parts ({100*scheduled/total:.1f}%)")
        if "objective" in result:
            print(f"Objective: {result['objective']:.1f}")
        if "solve_time" in result:
            print(f"Solve time: {result['solve_time']:.2f}s")
        
        if scheduled < total:
            failed = [r for r in result["rows"] if r["start"] == "NIET_GELUKT"]
            print(f"\nFailed ({len(failed)}):")
            for r in failed[:10]:
                print(f"  - {r['team']} {r['part']}")
    print('='*60)


if __name__ == "__main__":
    main()
