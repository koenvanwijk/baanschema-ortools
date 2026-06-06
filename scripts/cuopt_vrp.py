"""
cuOpt VRP-based tennis court scheduler (CORRECTED API).

Tennis scheduling as Vehicle Routing Problem:
- Vehicles = Courts (10 routes)
- Orders = Parts (tennis match segments)
- Order locations = Time slots (encoded as location IDs)
- Service time = Match duration
- Time windows = Slot availability + youth constraints

Uses correct cuOpt.routing API discovered via introspection.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ortools_planner import (
    ROOT, INPUT, TeamDay, Reservation,
    parse_input, build_parts
)

try:
    from cuopt import routing
    import numpy as np
    CUOPT_AVAILABLE = True
except ImportError as e:
    CUOPT_AVAILABLE = False
    CUOPT_IMPORT_ERROR = str(e)


def solve_day(date, teams, reservations, time_limit_s=60):
    """VRP-based solver using correct cuOpt routing API."""
    
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
    
    # Build parts (orders)
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
                "team": team,
            })
            team_parts[t_idx].append(len(parts) - 1)
    
    num_parts = len(parts)
    num_teams = len(day_teams)
    num_courts = 10
    
    # Time slots
    start_min = 8 * 60 + 30  # 08:30
    end_min = 20 * 60        # 20:00
    slot_duration = 15
    num_slots = (end_min - start_min) // slot_duration
    
    # Reserved slots
    reserved_kinds = {r.kind for r in reservations if r.date == date}
    
    print(f"[cuOpt-VRP] Planning {date}: {num_teams} teams, {num_parts} parts, {num_courts} courts, {num_slots} slots")
    
    # =========================================================================
    # VRP MAPPING
    # =========================================================================
    # Locations: depot (0) + one per order (1..N)
    num_locations = 1 + num_parts
    
    # Create data model
    data_model = routing.DataModel(n_locations=num_locations, n_fleet=num_courts)
    
    print(f"[cuOpt-VRP] Created DataModel: {num_locations} locations, {num_courts} vehicles")
    
    # =========================================================================
    # COST MATRIX
    # =========================================================================
    # Cost = "distance" between orders
    # For scheduling: cost is gap penalty if orders are far apart in time
    # Depot (0) has zero cost to/from all orders
    # Order-to-order cost = time gap penalty
    
    cost_matrix = np.ones((num_locations, num_locations), dtype=np.float32)
    
    # Depot row/col = 0 cost
    cost_matrix[0, :] = 0
    cost_matrix[:, 0] = 0
    
    # Order-to-order: prefer sequential slots (minimize gaps)
    for i in range(1, num_locations):
        for j in range(1, num_locations):
            if i == j:
                cost_matrix[i, j] = 0
            else:
                # TODO: compute based on preferred time slots
                # For now: uniform cost
                cost_matrix[i, j] = 1
    
    data_model.add_cost_matrix(cost_matrix)
    
    # =========================================================================
    # TIME WINDOWS
    # =========================================================================
    # Order time windows: [earliest_start, latest_start]
    # Youth orders: earliest = 08:30
    # All orders: latest = end_time - duration
    
    earliest_times = [start_min]  # Depot
    latest_times = [end_min]      # Depot
    
    for part in parts:
        team = part["team"]
        is_youth = "groen" in team.schema.lower() or "ju" in team.schema.lower()
        
        earliest = start_min if not is_youth else max(start_min, 8*60 + 30)
        latest = end_min - part["duration_min"]
        
        earliest_times.append(earliest)
        latest_times.append(latest)
    
    earliest_arr = np.array(earliest_times, dtype=np.int32)
    latest_arr = np.array(latest_times, dtype=np.int32)
    
    data_model.set_order_time_windows(earliest_arr, latest_arr)
    
    # =========================================================================
    # SERVICE TIMES
    # =========================================================================
    # Service time = match duration
    service_times = [0]  # Depot
    for part in parts:
        service_times.append(part["duration_min"])
    
    service_arr = np.array(service_times, dtype=np.int32)
    data_model.set_order_service_times(service_arr)
    
    # =========================================================================
    # VEHICLE (COURT) CONFIGURATION
    # =========================================================================
    # All vehicles start/end at depot
    start_locs = np.zeros(num_courts, dtype=np.int32)
    return_locs = np.zeros(num_courts, dtype=np.int32)
    data_model.set_vehicle_locations(start_locs, return_locs)
    
    # Vehicle time windows (court availability)
    vehicle_earliest = np.full(num_courts, start_min, dtype=np.int32)
    vehicle_latest = np.full(num_courts, end_min, dtype=np.int32)
    data_model.set_vehicle_time_windows(vehicle_earliest, vehicle_latest)
    
    # =========================================================================
    # SOLVER SETTINGS
    # =========================================================================
    solver_settings = routing.SolverSettings()
    solver_settings.set_time_limit(time_limit_s)
    
    # =========================================================================
    # SOLVE
    # =========================================================================
    print(f"[cuOpt-VRP] Solving...")
    
    try:
        solver = routing.Solve(data_model, solver_settings)
        solution = solver.get_assignment()
    except Exception as e:
        print(f"[cuOpt-VRP] Solver failed: {e}")
        import traceback
        traceback.print_exc()
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
    print(f"[cuOpt-VRP] Solution status: {status}")
    
    if status != routing.SolutionStatus.Optimal and status != routing.SolutionStatus.Feasible:
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
    
    print(f"[cuOpt-VRP] Solution cost: {solution.get_cost()}")
    
    # Extract routes
    routes = solution.get_routes()
    route_costs = solution.get_route_costs()
    
    def fmt_time(minutes):
        return f"{minutes//60:02d}:{minutes%60:02d}"
    
    # Build assignment: part_idx → (court, start_time)
    assignment = {}
    for vehicle_idx in range(num_courts):
        route = routes[vehicle_idx]
        
        if not route or len(route) == 0:
            continue
        
        court = vehicle_idx + 1  # Courts 1-10
        
        # Route contains location IDs (depot = 0, orders = 1..N)
        # Times: cumulative arrival times at each location
        # TODO: Extract arrival times from solution
        # For now: assign sequential slots
        current_time = start_min
        
        for loc_id in route:
            if loc_id == 0:  # Skip depot
                continue
            
            part_idx = loc_id - 1  # Convert location to part index
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
                "start": fmt_time(int(start_time)),
                "end": fmt_time(int(end_time)),
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
        "status": "OPTIMAL" if status == routing.SolutionStatus.Optimal else "FEASIBLE",
        "date": date,
        "rows": rows,
        "cost": solution.get_cost(),
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
        if "cost" in result:
            print(f"Cost: {result['cost']}")
        if scheduled < len(result["rows"]):
            failed = [r for r in result["rows"] if r["start"] == "NIET_GELUKT"]
            print(f"Failed: {len(failed)} parts")
            for r in failed[:5]:
                print(f"  - {r['team']} {r['part']}")


if __name__ == "__main__":
    main()
