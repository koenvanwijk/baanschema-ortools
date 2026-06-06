"""
cuOpt VRP tennis scheduler - minimal working version with correct pandas/cudf types.

Core mapping:
- Orders = Parts (match segments)
- Vehicles = Courts
- Time windows = slot availability
- Service times = match durations
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ortools_planner import parse_input, build_parts, INPUT

try:
    from cuopt import routing
    import cudf
    import numpy as np
    CUOPT_AVAILABLE = True
except ImportError as e:
    CUOPT_AVAILABLE = False
    CUOPT_IMPORT_ERROR = str(e)


def solve_day(date, teams, reservations, time_limit_s=60):
    """Minimal VRP solver with correct cudf/pandas types."""
    
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
    for t_idx, team in enumerate(day_teams):
        for part_label, part_kind in build_parts(team):
            duration_min = 90 if part_kind == "D" else 60
            parts.append({
                "team_idx": t_idx,
                "part_label": part_label,
                "part_kind": part_kind,
                "duration_min": duration_min,
                "team": team,
            })
    
    num_parts = len(parts)
    num_courts = 10
    
    # Time slots
    start_min = 8 * 60 + 30  # 08:30
    end_min = 20 * 60        # 20:00
    
    print(f"[cuOpt-VRP] {date}: {len(day_teams)} teams, {num_parts} parts, {num_courts} courts")
    
    # =========================================================================
    # DATAMODEL
    # =========================================================================
    # n_locations = depot (0) + orders (1..N)
    n_locations = 1 + num_parts
    
    data_model = routing.DataModel(n_locations=n_locations, n_fleet=num_courts)
    
    # =========================================================================
    # COST MATRIX (cudf DataFrame)
    # =========================================================================
    # Simple uniform cost: minimize total route length
    cost_matrix_np = np.ones((n_locations, n_locations), dtype=np.float32)
    
    # Depot has zero cost
    cost_matrix_np[0, :] = 0
    cost_matrix_np[:, 0] = 0
    
    # Self-loops are zero
    np.fill_diagonal(cost_matrix_np, 0)
    
    # Convert to cudf DataFrame
    cost_matrix_df = cudf.DataFrame(cost_matrix_np)
    data_model.add_cost_matrix(cost_matrix_df)
    
    # =========================================================================
    # ORDER TIME WINDOWS (cudf Series)
    # =========================================================================
    earliest_times = [start_min]  # Depot
    latest_times = [end_min]
    
    for part in parts:
        team = part["team"]
        is_youth = "groen" in team.schema.lower() or "ju" in team.schema.lower()
        
        earliest = start_min if not is_youth else max(start_min, 8*60 + 30)
        latest = end_min - part["duration_min"]
        
        earliest_times.append(earliest)
        latest_times.append(latest)
    
    earliest_series = cudf.Series(earliest_times, dtype=np.int32)
    latest_series = cudf.Series(latest_times, dtype=np.int32)
    
    data_model.set_order_time_windows(earliest_series, latest_series)
    
    # =========================================================================
    # SERVICE TIMES (cudf Series)
    # =========================================================================
    service_times = [0]  # Depot
    for part in parts:
        service_times.append(part["duration_min"])
    
    service_series = cudf.Series(service_times, dtype=np.int32)
    data_model.set_order_service_times(service_series)
    
    # =========================================================================
    # VEHICLE LOCATIONS (cudf Series)
    # =========================================================================
    # All vehicles start/end at depot (location 0)
    start_locs = cudf.Series(np.zeros(num_courts, dtype=np.int32))
    return_locs = cudf.Series(np.zeros(num_courts, dtype=np.int32))
    data_model.set_vehicle_locations(start_locs, return_locs)
    
    # =========================================================================
    # VEHICLE TIME WINDOWS (cudf Series)
    # =========================================================================
    vehicle_earliest = cudf.Series(np.full(num_courts, start_min, dtype=np.int32))
    vehicle_latest = cudf.Series(np.full(num_courts, end_min, dtype=np.int32))
    data_model.set_vehicle_time_windows(vehicle_earliest, vehicle_latest)
    
    # =========================================================================
    # SOLVER
    # =========================================================================
    solver_settings = routing.SolverSettings()
    solver_settings.set_time_limit(time_limit_s)
    
    print(f"[cuOpt-VRP] Solving with {time_limit_s}s time limit...")
    
    try:
        # Solve() directly returns Assignment object
        solution = routing.Solve(data_model, solver_settings)
    except Exception as e:
        print(f"[cuOpt-VRP] Solver exception: {e}")
        import traceback
        traceback.print_exc()
        
        # Return all as NIET_GELUKT
        rows = []
        for p_idx, part in enumerate(parts):
            team = part["team"]
            rows.append({
                "team": team.schema,
                "team_id": part["team_idx"],
                "part": part["part_label"],
                "kind": part["part_kind"],
                "start": "NIET_GELUKT",
                "end": "NIET_GELUKT",
                "court": 0,
            })
        return {"status": "ERROR", "date": date, "error": str(e), "rows": rows}
    
    # =========================================================================
    # EXTRACT SOLUTION
    # =========================================================================
    status = solution.get_status()
    print(f"[cuOpt-VRP] Status: {status}")
    
    if status != routing.SolutionStatus.SUCCESS:
        print(f"[cuOpt-VRP] No solution found")
        rows = []
        for p_idx, part in enumerate(parts):
            team = part["team"]
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
    
    try:
        cost = solution.get_total_objective()
    except Exception:
        cost = 0.0
    print(f"[cuOpt-VRP] Cost: {cost}")
    
    # Get routes per vehicle
    vehicle_count = solution.get_vehicle_count()
    routes = [solution.get_route(v) for v in range(vehicle_count)]
    
    def fmt_time(minutes):
        return f"{int(minutes)//60:02d}:{int(minutes)%60:02d}"
    
    # Build assignment
    assignment = {}
    for vehicle_idx in range(num_courts):
        route = routes[vehicle_idx]
        
        if not route or len(route) == 0:
            continue
        
        court = vehicle_idx + 1  # Courts 1-10
        
        # Route contains location IDs (depot=0, orders=1..N)
        # For now: assign sequential slots (TODO: extract arrival times from solution)
        current_time = start_min
        
        for loc_id in route:
            if loc_id == 0:  # Skip depot
                continue
            
            part_idx = loc_id - 1
            assignment[part_idx] = (court, current_time)
            current_time += parts[part_idx]["duration_min"]
    
    # Build rows
    rows = []
    scheduled_count = 0
    
    for p_idx, part in enumerate(parts):
        team = part["team"]
        if p_idx in assignment:
            court, start_time = assignment[p_idx]
            end_time = start_time + part["duration_min"]
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
    
    print(f"[cuOpt-VRP] Scheduled {scheduled_count}/{num_parts} parts")
    
    return {
        "status": "SUCCESS",
        "date": date,
        "rows": rows,
        "cost": float(cost),
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
        if "cost" in result:
            print(f"Cost: {result['cost']:.1f}")
        
        if scheduled < total:
            failed = [r for r in result["rows"] if r["start"] == "NIET_GELUKT"]
            print(f"\nFailed ({len(failed)}):")
            for r in failed[:10]:
                print(f"  - {r['team']} {r['part']}")
    print('='*60)


if __name__ == "__main__":
    main()
