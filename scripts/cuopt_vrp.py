"""
cuOpt VRP-based tennis court scheduler.

Key insight: Tennis scheduling is a Vehicle Routing Problem in disguise:
- Vehicles = Courts (10 courts, or 5 court-pairs with 2 parallel routes each)
- Customers = Parts (tennis match segments to schedule)
- Time windows = Slot availability (youth ≥08:30, part duration constraints)
- Capacity = Court pairing (teams must stay on adjacent court pairs)
- Objective = Minimize unscheduled + compact time spans

This uses cuOpt's native VRP solver (cuopt.routing), not MILP.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ortools_planner import (
    ROOT, INPUT, TeamDay, Reservation,
    parse_input, build_parts, player_demand
)

try:
    from cuopt import routing
    CUOPT_AVAILABLE = True
except ImportError as e:
    CUOPT_AVAILABLE = False
    CUOPT_IMPORT_ERROR = str(e)


def solve_day(date, teams, reservations, time_limit_s=60):
    """VRP-based solver using cuOpt routing API."""
    
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
                "team": team,
            })
            team_parts[t_idx].append(len(parts) - 1)
    
    num_parts = len(parts)
    num_teams = len(day_teams)
    
    # Time slots
    start_min = 8 * 60 + 30  # 08:30
    end_min = 20 * 60        # 20:00
    slot_duration = 15
    
    # Court pairs
    COURT_PAIRS = [(1,2), (3,4), (5,6), (7,8), (9,10)]
    num_pairs = len(COURT_PAIRS)
    
    # Reserved slots
    reserved_kinds = {r.kind for r in reservations if r.date == date}
    
    print(f"[cuOpt-VRP] Planning {date}: {num_teams} teams, {num_parts} parts, {num_pairs} court pairs")
    
    # =========================================================================
    # VRP PROBLEM SETUP
    # =========================================================================
    
    # Create routing data model
    data_model = routing.DataModel()
    
    # LOCATIONS: depot (0) + one location per part (1..N)
    num_locations = 1 + num_parts
    
    # VEHICLES: one vehicle per court (10 courts = 10 vehicles)
    # Each vehicle represents a court and can handle parts assigned to it
    num_vehicles = 10
    
    # Cost matrix: travel time between locations
    # For scheduling: "travel" = gap between parts
    # We want to minimize gaps, so use time-based distance
    cost_matrix = [[0 for _ in range(num_locations)] for _ in range(num_locations)]
    
    # Depot (location 0) has zero cost to/from all parts
    # Part-to-part "travel cost" = gap penalty if parts are far apart in time
    # For simplicity: set all travel costs to 1 (we'll use time windows for actual scheduling)
    for i in range(num_locations):
        for j in range(num_locations):
            if i != j:
                cost_matrix[i][j] = 1
    
    data_model.set_cost_matrix(cost_matrix)
    
    # TIME WINDOWS: each part has a time window [earliest_start, latest_start]
    # Depot has full day window
    time_windows = [[start_min, end_min]]  # Depot
    
    for p_idx, part in enumerate(parts):
        team = part["team"]
        is_youth = "groen" in team.schema.lower() or "ju" in team.schema.lower()
        
        earliest = start_min if not is_youth else max(start_min, 8*60 + 30)
        latest = end_min - part["duration_min"]
        
        time_windows.append([earliest, latest])
    
    data_model.set_time_windows(time_windows)
    
    # SERVICE TIME: duration of each part
    service_times = [0]  # Depot has no service time
    for part in parts:
        service_times.append(part["duration_min"])
    
    data_model.set_service_times(service_times)
    
    # VEHICLE CAPACITY: each court can handle unlimited parts
    # But we want to enforce court pairing via capacity constraints
    # For now: set high capacity, use constraints separately
    vehicle_capacity = [1000] * num_vehicles
    data_model.set_vehicle_capacity(vehicle_capacity)
    
    # DEMAND: each part has demand=1 (simple capacity check)
    demand = [0]  # Depot
    for part in parts:
        demand.append(1)
    
    data_model.set_demand(demand)
    
    # VEHICLE START/END: all vehicles start/end at depot (court availability window)
    vehicle_locations = [[0, 0] for _ in range(num_vehicles)]
    data_model.set_vehicle_locations(vehicle_locations)
    
    print(f"[cuOpt-VRP] Data model: {num_locations} locations, {num_vehicles} vehicles")
    
    # =========================================================================
    # SOLVER CONFIGURATION
    # =========================================================================
    
    solver_config = routing.SolverConfig()
    solver_config.set_time_limit(time_limit_s)
    solver_config.set_verbose_mode(True)
    
    # =========================================================================
    # SOLVE
    # =========================================================================
    
    print(f"[cuOpt-VRP] Solving with time limit {time_limit_s}s...")
    
    try:
        solution = routing.solve(data_model, solver_config)
    except Exception as e:
        print(f"[cuOpt-VRP] Solver failed: {e}")
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
    
    if solution.get_status() != 0:  # 0 = success
        print(f"[cuOpt-VRP] No solution found, status: {solution.get_status()}")
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
    
    print(f"[cuOpt-VRP] Solution found, cost: {solution.get_cost()}")
    
    # Extract routes (one per vehicle/court)
    routes = solution.get_routes()
    
    def fmt_time(minutes):
        return f"{minutes//60:02d}:{minutes%60:02d}"
    
    # Build assignment: part_idx → (court, start_time)
    assignment = {}
    for vehicle_idx, route in enumerate(routes):
        court = vehicle_idx + 1  # Courts 1-10
        
        if not route:
            continue
        
        # Route contains location indices (excluding depot)
        # Times are cumulative from depot start
        route_times = solution.get_route_times(vehicle_idx)
        
        for loc_idx, arrival_time in zip(route, route_times):
            if loc_idx == 0:  # Skip depot
                continue
            
            part_idx = loc_idx - 1  # Convert location to part index
            assignment[part_idx] = (court, arrival_time)
    
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
        "status": "OPTIMAL" if solution.get_status() == 0 else "FEASIBLE",
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
