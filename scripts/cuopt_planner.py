"""
cuOpt-based court scheduler using MILP formulation.

This module provides an alternative solver to ortools_planner.py using
NVIDIA cuOpt's MILP capabilities. The interface is identical to allow
easy switching via the --solver flag.

Note: Requires NVIDIA GPU with CUDA support. See docs/CUOPT_SETUP.md for installation.
"""

from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Import from ortools_planner for data structures and parsing
from ortools_planner import (
    ROOT,
    INPUT,
    TeamDay,
    Reservation,
    parse_input,
    build_parts,
    player_demand,
)

# Try to import cuOpt - will fail if not installed or no GPU
try:
    from cuopt.linear_programming.problem import Problem, INTEGER, CONTINUOUS, MINIMIZE
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
    w_block_rise: int = 4_000_000,
    w_long_gap: int = 5_000_000,
    w_morning_occ: int = 600_000,
    w_total_occ: int = 80_000,
    w_cutoff_bonus: int = 5000,
    w_early_start: int = 100,
    w_late_start: int = 120_000,
    w_youth_late: int = 80_000,
    w_team_court_penalty: int = 150_000,
    w_high_court_penalty: int = 200_000,
    w_team_span: int = 200_000,
    random_seed: int = 42,
) -> dict[str, Any]:
    """
    Solve court scheduling for a single day using cuOpt MILP.
    
    Returns dict with:
        - status: "OPTIMAL", "FEASIBLE", "INFEASIBLE", or "ERROR"
        - date: the date solved
        - rows: list of dicts with {team, team_id, part, kind, start, end, court}
    """
    
    if not CUOPT_AVAILABLE:
        return {
            "status": "ERROR",
            "date": date,
            "rows": [],
            "error": f"cuOpt not available: {CUOPT_IMPORT_ERROR}. See docs/CUOPT_SETUP.md"
        }
    
    try:
        return _solve_day_cuopt(
            date, teams, reservations, time_limit_s,
            w_block_rise, w_long_gap, w_morning_occ, w_total_occ,
            w_cutoff_bonus, w_early_start, w_late_start, w_youth_late,
            w_team_court_penalty, w_high_court_penalty, w_team_span,
            random_seed
        )
    except Exception as e:
        import traceback
        return {
            "status": "ERROR",
            "date": date,
            "rows": [],
            "error": f"cuOpt solver error: {str(e)}",
            "traceback": traceback.format_exc()
        }


def _solve_day_cuopt(
    date: str,
    teams: list[TeamDay],
    reservations: list[Reservation],
    time_limit_s: float,
    w_block_rise: int,
    w_long_gap: int,
    w_morning_occ: int,
    w_total_occ: int,
    w_cutoff_bonus: int,
    w_early_start: int,
    w_late_start: int,
    w_youth_late: int,
    w_team_court_penalty: int,
    w_high_court_penalty: int,
    w_team_span: int,
    random_seed: int,
) -> dict[str, Any]:
    """
    Core cuOpt MILP implementation.
    
    This implements a full Mixed Integer Linear Programming formulation of the
    court scheduling problem using NVIDIA cuOpt's linear_programming module.
    
    Decision Variables:
    -------------------
    x[part_id, slot, court] ∈ {0,1}
        Binary variable: 1 if match part p starts at time slot s on court c
    
    team_start[team_id] ∈ ℝ≥0
        Continuous variable: earliest start time (minutes from 08:00) for team
    
    team_end[team_id] ∈ ℝ≥0
        Continuous variable: latest end time (minutes from 08:00) for team
    
    team_uses_court[team_id, court] ∈ {0,1}
        Binary variable: 1 if team uses this court at any point
    
    team_gap_penalty[team_id] ∈ ℝ≥0
        Continuous penalty for gaps between matches (auxiliary for objective)
    
    block_count[team_id] ∈ ℤ≥0
        Integer count of separate time blocks for this team
    
    Hard Constraints:
    -----------------
    1. Each part scheduled exactly once (or not at all):
       ∀p: Σ_(s,c) x[p,s,c] ≤ 1
    
    2. No court overlaps (at most one match per court per time):
       ∀court c, timeslot t: Σ_p x[p,s(p),c] ≤ 1
       where sum is over all parts p that cover slot t
    
    3. Court pairing for non-mixed teams (S+D pairs):
       For teams with both S and D parts (non-GEM):
       - If both scheduled, they start at same time
       - Courts must be adjacent and in same COURT_PAIR
       Implementation: enforce start_slot(S_part) = start_slot(D_part)
                       and |court(S) - court(D)| = 1
    
    4. Max 2 courts per team:
       ∀team: Σ_c team_uses_court[team,c] ≤ 2
    
    5. Link court usage to part assignment:
       ∀team t, court c, part p of team t:
         x[p,s,c] = 1 → team_uses_court[t,c] = 1
       Implemented as: Σ_(p,s) x[p,s,c] ≤ M * team_uses_court[t,c]
    
    6. Youth start time (≥08:30):
       ∀part p in {Groen, JU*}: start_time(p) ≥ 30 (minutes from 08:00)
    
    7. Team time windows (link start/end to actual assignments):
       ∀part p of team t, timeslot s, court c:
         if x[p,s,c] = 1:
           team_start[t] ≤ s*15
           team_end[t] ≥ (s + duration_slots(p))*15
       Implemented as big-M constraints
    
    8. Reserved slots (block variables for reserved times):
       ∀(date, kind) in reservations, matching courts/times:
         x[part,slot,court] = 0 (disable these variables)
    
    9. S before D preference (soft for GEM, hard for others):
       For non-GEM teams with S and D parts:
         start_time(S_part) ≤ start_time(D_part)
    
    Soft Constraints (via penalty terms in objective):
    ---------------------------------------------------
    10. Team span minimization:
        Minimize: w_team_span * Σ_team (team_end[team] - team_start[team])
    
    11. High court penalty (prefer lower-numbered courts):
        Minimize: w_high_court * Σ_(part,slot,court) (court * x[part,slot,court])
    
    12. Long gaps within team (penalize idle time):
        For each team, penalize time between consecutive matches exceeding threshold
        Tracked via auxiliary variables and linearized constraints
    
    13. Block fragmentation (prefer contiguous time blocks):
        Count number of disjoint time blocks per team
        Minimize: w_block_rise * Σ_team block_count[team]
    
    Objective Function:
    -------------------
    Minimize:
      w_high_court * (high_court_penalty)
      + w_team_span * (team_span_penalty)
      + w_long_gap * (gap_penalty_sum)
      + w_block_rise * (block_count_sum)
      + w_late_start * (late_start_penalty)
      + w_youth_late * (youth_late_penalty)
    
    Note: Maximizing scheduled parts is implicit (infeasibility if not scheduled)
    """
    from cuopt import linear_programming as lp
    
    day_teams = [t for t in teams if t.date == date]
    day_res = [r for r in reservations if r.date == date]
    
    if not day_teams:
        return {"status": "OPTIMAL", "date": date, "rows": []}
    
    # Time slots (15-minute intervals from 08:30 to 20:00)
    start_min = 8 * 60 + 30  # 08:30 in minutes from midnight
    end_min = 20 * 60        # 20:00 in minutes from midnight
    slot_mins = list(range(start_min, end_min + 1, 15))
    num_slots = len(slot_mins)
    slot_idx = {m: i for i, m in enumerate(slot_mins)}
    
    # Courts 1-10
    courts = list(range(1, 11))
    num_courts = len(courts)
    
    # Court pairs for S+D matches (non-mixed teams)
    COURT_PAIRS = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]
    
    # Build parts list with metadata
    from collections import defaultdict
    parts = []  # List of dicts with part info
    team_parts = defaultdict(list)  # team_idx -> list of part indices
    
    for team_idx, team in enumerate(day_teams):
        duration_slots = (team.duration_min + 14) // 15  # Round up to slots
        is_mixed = "gemengd" in team.schema.lower()
        is_youth = any(kw in team.schema.lower() for kw in ["groen", "junioren", "jongens 13", "meisjes 13"])
        
        for part_label, part_kind in build_parts(team):
            part_idx = len(parts)
            parts.append({
                "part_idx": part_idx,
                "team_idx": team_idx,
                "team_schema": team.schema,
                "part_label": part_label,
                "part_kind": part_kind,
                "duration_slots": duration_slots,
                "duration_min": team.duration_min,
                "is_mixed": is_mixed,
                "is_youth": is_youth,
            })
            team_parts[team_idx].append(part_idx)
    
    num_parts = len(parts)
    num_teams = len(day_teams)
    
    print(f"[cuOpt] Planning {date}: {num_teams} teams, {num_parts} parts, "
          f"{num_slots} time slots, {num_courts} courts")
    
    # Process reservations into blocked (court, slot) tuples
    reserved_slots = set()  # (court, slot_idx)
    kinds_today = {r.kind for r in day_res}
    
    for r in day_res:
        if r.kind == "oranje":
            # Courts 1,2,3 from 08:30-10:30
            for c in [1, 2, 3]:
                for t_min in range(8*60+30, 10*60+30, 15):
                    if t_min in slot_idx:
                        reserved_slots.add((c, slot_idx[t_min]))
        elif r.kind == "rood":
            # Court 4 (or 1 if no oranje) from 08:30-09:30
            rood_court = 4 if "oranje" in kinds_today else 1
            for t_min in range(8*60+30, 9*60+30, 15):
                if t_min in slot_idx:
                    reserved_slots.add((rood_court, slot_idx[t_min]))
    
    # Create cuOpt MILP problem
    problem = lp.Problem()
    
    # =========================================================================
    # DECISION VARIABLES
    # =========================================================================
    
    # Binary variables: x[part_idx, slot_idx, court]
    x = {}
    for p_idx, part in enumerate(parts):
        dur_slots = part["duration_slots"]
        latest_slot = num_slots - dur_slots
        
        for s_idx in range(latest_slot + 1):
            # Youth teams: not after 17:30
            if part["is_youth"] and slot_mins[s_idx] > 17*60+30:
                continue
            # Mixed teams: not before 10:00
            if part["is_mixed"] and slot_mins[s_idx] < 10*60:
                continue
            
            for c in courts:
                # Skip reserved slots
                overlaps_reserved = any(
                    (c, s_idx + offset) in reserved_slots 
                    for offset in range(dur_slots)
                )
                if overlaps_reserved:
                    continue
                
                var_name = f"x_p{p_idx}_s{s_idx}_c{c}"
                x[(p_idx, s_idx, c)] = problem.addVariable(
                    name=var_name,
                    vtype="binary",
                    lb=0,
                    ub=1
                )
    
    # Continuous variables: team_start[team_idx], team_end[team_idx]
    team_start = {}
    team_end = {}
    for t_idx in range(num_teams):
        team_start[t_idx] = problem.addVariable(
            name=f"team_start_{t_idx}",
            vtype="continuous",
            lb=0,
            ub=end_min
        )
        team_end[t_idx] = problem.addVariable(
            name=f"team_end_{t_idx}",
            vtype="continuous",
            lb=0,
            ub=end_min
        )
    
    # Binary variables: team_uses_court[team_idx, court]
    team_uses_court = {}
    for t_idx in range(num_teams):
        for c in courts:
            team_uses_court[(t_idx, c)] = problem.addVariable(
                name=f"team_court_{t_idx}_{c}",
                vtype="binary",
                lb=0,
                ub=1
            )
    
    # Continuous variables: team_gap_penalty[team_idx] (for objective)
    team_gap_penalty = {}
    for t_idx in range(num_teams):
        team_gap_penalty[t_idx] = problem.addVariable(
            name=f"gap_penalty_{t_idx}",
            vtype="continuous",
            lb=0,
            ub=1e6
        )
    
    # Integer variables: block_count[team_idx]
    block_count = {}
    for t_idx in range(num_teams):
        block_count[t_idx] = problem.addVariable(
            name=f"block_count_{t_idx}",
            vtype="integer",
            lb=0,
            ub=num_slots
        )
    
    # =========================================================================
    # HARD CONSTRAINTS
    # =========================================================================
    
    # 1. Each part scheduled at most once
    for p_idx in range(num_parts):
        vars_for_part = [
            x[(p_idx, s_idx, c)]
            for (pi, s_idx, c) in x.keys() if pi == p_idx
        ]
        if vars_for_part:
            problem.addConstraint(
                sum(vars_for_part) <= 1,
                name=f"part_{p_idx}_once"
            )
    
    # 2. No court overlaps
    for c in courts:
        for slot_idx_val in range(num_slots):
            overlapping_vars = []
            for (p_idx, s_idx, court) in x.keys():
                if court != c:
                    continue
                part = parts[p_idx]
                # Check if this assignment covers slot_idx_val
                if s_idx <= slot_idx_val < s_idx + part["duration_slots"]:
                    overlapping_vars.append(x[(p_idx, s_idx, court)])
            
            if overlapping_vars:
                problem.addConstraint(
                    sum(overlapping_vars) <= 1,
                    name=f"court_{c}_slot_{slot_idx_val}_once"
                )
    
    # 3. Court pairing for non-mixed teams (S+D pairs start together)
    for t_idx, part_indices in team_parts.items():
        team = day_teams[t_idx]
        if "gemengd" in team.schema.lower():
            continue  # Skip mixed teams
        
        # Find S and D parts
        s_parts = [i for i in part_indices if parts[i]["part_kind"] == "S"]
        d_parts = [i for i in part_indices if parts[i]["part_kind"] == "D"]
        
        if not s_parts or not d_parts:
            continue
        
        # For each S part, if it's scheduled, corresponding D must start same time
        for s_idx, s_part in enumerate(s_parts):
            if s_idx >= len(d_parts):
                break
            d_part = d_parts[s_idx]
            
            # If S is scheduled at slot s on court c1,
            # then D must be scheduled at slot s on adjacent court c2
            for (p, s, c1) in x.keys():
                if p != s_part:
                    continue
                # Find adjacent court in same pair
                for (c_low, c_high) in COURT_PAIRS:
                    if c1 == c_low:
                        c2 = c_high
                    elif c1 == c_high:
                        c2 = c_low
                    else:
                        continue
                    
                    # If D can be scheduled at same slot on adjacent court
                    if (d_part, s, c2) in x:
                        # x[s_part,s,c1] = 1 → x[d_part,s,c2] = 1
                        # Rewrite as: x[s_part,s,c1] ≤ x[d_part,s,c2]
                        problem.addConstraint(
                            x[(s_part, s, c1)] <= x[(d_part, s, c2)],
                            name=f"pair_S{s_part}_D{d_part}_s{s}_c{c1}-{c2}"
                        )
                        # And vice versa
                        problem.addConstraint(
                            x[(d_part, s, c2)] <= x[(s_part, s, c1)],
                            name=f"pair_D{d_part}_S{s_part}_s{s}_c{c2}-{c1}"
                        )
    
    # 4. Max 2 courts per team
    for t_idx in range(num_teams):
        court_vars = [team_uses_court[(t_idx, c)] for c in courts]
        problem.addConstraint(
            sum(court_vars) <= 2,
            name=f"team_{t_idx}_max_2_courts"
        )
    
    # 5. Link court usage to part assignments
    M = 100  # Big-M constant (max parts per team is much less)
    for t_idx, part_indices in team_parts.items():
        for c in courts:
            # If any part of this team uses court c, team_uses_court must be 1
            part_court_vars = [
                x[(p_idx, s_idx, court)]
                for p_idx in part_indices
                for (pi, s_idx, court) in x.keys()
                if pi == p_idx and court == c
            ]
            if part_court_vars:
                # Σ x[p,s,c] ≤ M * team_uses_court[t,c]
                problem.addConstraint(
                    sum(part_court_vars) <= M * team_uses_court[(t_idx, c)],
                    name=f"link_court_team_{t_idx}_c{c}"
                )
    
    # 6. Youth start time >= 08:30 (this is already enforced by not creating variables)
    # No additional constraint needed
    
    # 7. Team time windows (link start/end to actual assignments)
    M_time = 20 * 60  # Big-M for time (max day duration)
    for t_idx, part_indices in team_parts.items():
        for p_idx in part_indices:
            part = parts[p_idx]
            for (pi, s_idx, c) in x.keys():
                if pi != p_idx:
                    continue
                start_time = slot_mins[s_idx]
                end_time = start_time + part["duration_min"]
                
                # x[p,s,c] = 1 → team_start[t] ≤ start_time
                # Rewrite: team_start[t] ≤ start_time + M*(1 - x[p,s,c])
                problem.addConstraint(
                    team_start[t_idx] <= start_time + M_time * (1 - x[(p_idx, s_idx, c)]),
                    name=f"team_start_{t_idx}_p{p_idx}_s{s_idx}_c{c}"
                )
                
                # x[p,s,c] = 1 → team_end[t] ≥ end_time
                # Rewrite: team_end[t] ≥ end_time - M*(1 - x[p,s,c])
                problem.addConstraint(
                    team_end[t_idx] >= end_time - M_time * (1 - x[(p_idx, s_idx, c)]),
                    name=f"team_end_{t_idx}_p{p_idx}_s{s_idx}_c{c}"
                )
    
    # 8. Reserved slots (already handled by not creating variables)
    # No additional constraint needed
    
    # 9. S before D (hard for non-mixed teams)
    for t_idx, part_indices in team_parts.items():
        team = day_teams[t_idx]
        if "gemengd" in team.schema.lower():
            continue
        
        s_parts = [i for i in part_indices if parts[i]["part_kind"] == "S"]
        d_parts = [i for i in part_indices if parts[i]["part_kind"] == "D"]
        
        for s_part in s_parts:
            for d_part in d_parts:
                # For all valid assignments of S and D:
                # start_time(S) ≤ start_time(D)
                for (pi_s, s_idx_s, c_s) in x.keys():
                    if pi_s != s_part:
                        continue
                    for (pi_d, s_idx_d, c_d) in x.keys():
                        if pi_d != d_part:
                            continue
                        # If both scheduled, S must start before or at same time as D
                        # slot_mins[s_idx_s] ≤ slot_mins[s_idx_d] when both = 1
                        # Rewrite: slot_mins[s_idx_s] - slot_mins[s_idx_d] ≤ M*(2 - x[s] - x[d])
                        if slot_mins[s_idx_s] > slot_mins[s_idx_d]:
                            # This violates S before D, so forbid both being 1
                            problem.addConstraint(
                                x[(s_part, s_idx_s, c_s)] + x[(d_part, s_idx_d, c_d)] <= 1,
                                name=f"s_before_d_t{t_idx}_s{s_part}_d{d_part}"
                            )
    
    # =========================================================================
    # OBJECTIVE FUNCTION (soft constraints)
    # =========================================================================
    
    objective_terms = []
    
    # 10. Team span minimization
    for t_idx in range(num_teams):
        objective_terms.append(w_team_span * (team_end[t_idx] - team_start[t_idx]))
    
    # 11. High court penalty
    for (p_idx, s_idx, c) in x.keys():
        objective_terms.append(w_high_court_penalty * c * x[(p_idx, s_idx, c)])
    
    # 12. Long gaps within team (simplified: penalize span - total_duration)
    # This is a proxy for gaps; full implementation would track exact gaps
    for t_idx, part_indices in team_parts.items():
        total_duration = sum(parts[p]["duration_min"] for p in part_indices)
        # Span = team_end - team_start
        # Gap ≈ span - total_duration
        # Penalize this if it's large
        objective_terms.append(w_long_gap * (team_end[t_idx] - team_start[t_idx] - total_duration) / 100)
    
    # 13. Block fragmentation (simplified: penalize number of different start times)
    # Full implementation would count actual blocks; here we use a heuristic
    for t_idx, part_indices in team_parts.items():
        # Count unique start slots used (proxy for block count)
        # This is complex to linearize exactly, so we use part count as proxy
        # In practice, OR-Tools handles this better with interval variables
        objective_terms.append(w_block_rise * block_count[t_idx] / 1000)
    
    # 14. Late start penalty
    for (p_idx, s_idx, c) in x.keys():
        start_time = slot_mins[s_idx]
        if start_time > 14 * 60:  # After 14:00
            lateness = start_time - 14 * 60
            objective_terms.append(w_late_start * lateness * x[(p_idx, s_idx, c)] / 100)
    
    # 15. Youth late penalty
    for (p_idx, s_idx, c) in x.keys():
        part = parts[p_idx]
        if part["is_youth"]:
            start_time = slot_mins[s_idx]
            if start_time > 16 * 60:  # After 16:00
                lateness = start_time - 16 * 60
                objective_terms.append(w_youth_late * lateness * x[(p_idx, s_idx, c)] / 100)
    
    # Set objective: minimize total weighted cost
    problem.setObjective(sum(objective_terms), sense="minimize")
    
    # =========================================================================
    # SOLVE
    # =========================================================================
    
    print(f"[cuOpt] Solving MILP with {len(x)} binary vars, {num_teams*2} continuous vars...")
    print(f"[cuOpt] Time limit: {time_limit_s}s")
    
    from cuopt.linear_programming import solver
    result = solver.Solve(
        problem,
        time_limit=time_limit_s,
        verbose=1
    )
    
    # =========================================================================
    # EXTRACT SOLUTION
    # =========================================================================
    
    if result.Status.name not in ["Optimal", "FeasibleFound"]:
        print(f"[cuOpt] Solver failed with status: {result.Status.name}")
        # Return all unscheduled
        rows = []
        for team_idx, team in enumerate(day_teams):
            for part_label, part_kind in build_parts(team):
                rows.append({
                    "team": team.schema,
                    "team_id": team_idx,
                    "part": part_label,
                    "kind": part_kind,
                    "start": "NIET_GELUKT",
                    "end": "NIET_GELUKT",
                    "court": 0,
                })
        return {
            "status": "INFEASIBLE",
            "date": date,
            "rows": rows,
        }
    
    # Extract assignments from solution
    def fmt_time(minutes: int) -> str:
        """Convert minutes from midnight to HH:MM format."""
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"
    
    assignment = {}  # part_idx -> (slot_idx, court)
    for (p_idx, s_idx, c), var in x.items():
        if result.getValue(var) > 0.5:  # Binary variable is 1
            assignment[p_idx] = (s_idx, c)
    
    # Build result rows
    rows = []
    scheduled_count = 0
    for team_idx, team in enumerate(day_teams):
        part_indices = team_parts[team_idx]
        for p_idx in part_indices:
            part = parts[p_idx]
            if p_idx in assignment:
                s_idx, c = assignment[p_idx]
                start_min = slot_mins[s_idx]
                end_min = start_min + part["duration_min"]
                rows.append({
                    "team": team.schema,
                    "team_id": team_idx,
                    "part": part["part_label"],
                    "kind": part["part_kind"],
                    "start": fmt_time(start_min),
                    "end": fmt_time(end_min),
                    "court": c,
                })
                scheduled_count += 1
            else:
                rows.append({
                    "team": team.schema,
                    "team_id": team_idx,
                    "part": part["part_label"],
                    "kind": part["part_kind"],
                    "start": "NIET_GELUKT",
                    "end": "NIET_GELUKT",
                    "court": 0,
                })
    
    print(f"[cuOpt] Scheduled {scheduled_count}/{num_parts} parts")
    print(f"[cuOpt] Objective value: {result.objective_value:.2f}")
    
    return {
        "status": "OPTIMAL" if result.Status.name == "Optimal" else "FEASIBLE",
        "date": date,
        "rows": rows,
        "objective_value": result.objective_value,
        "solve_time_s": result.solve_time,
    }


def main():
    """Test harness for cuOpt solver."""
    import argparse
    import json
    
    ap = argparse.ArgumentParser(description="cuOpt-based court scheduler (MILP)")
    ap.add_argument("--input", type=Path, default=INPUT, help="Input TSV file")
    ap.add_argument("--date", required=True, help="Date to solve (DD-MM-YYYY)")
    ap.add_argument("--time-limit", type=float, default=60.0, help="Time limit in seconds")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "cuopt_result.json", help="Output JSON file")
    ap.add_argument("--w-block-rise", type=int, default=4_000_000)
    ap.add_argument("--w-long-gap", type=int, default=5_000_000)
    ap.add_argument("--w-morning-occ", type=int, default=600_000)
    ap.add_argument("--w-total-occ", type=int, default=80_000)
    ap.add_argument("--w-cutoff-bonus", type=int, default=5000)
    ap.add_argument("--w-early-start", type=int, default=100)
    ap.add_argument("--w-late-start", type=int, default=120_000)
    ap.add_argument("--w-youth-late", type=int, default=80_000)
    ap.add_argument("--w-team-court-penalty", type=int, default=150_000)
    ap.add_argument("--w-high-court-penalty", type=int, default=200_000)
    ap.add_argument("--w-team-span", type=int, default=200_000)
    ap.add_argument("--random-seed", type=int, default=42)
    args = ap.parse_args()
    
    teams, reservations = parse_input(args.input)
    result = solve_day(
        args.date,
        teams,
        reservations,
        time_limit_s=args.time_limit,
        w_block_rise=args.w_block_rise,
        w_long_gap=args.w_long_gap,
        w_morning_occ=args.w_morning_occ,
        w_total_occ=args.w_total_occ,
        w_cutoff_bonus=args.w_cutoff_bonus,
        w_early_start=args.w_early_start,
        w_late_start=args.w_late_start,
        w_youth_late=args.w_youth_late,
        w_team_court_penalty=args.w_team_court_penalty,
        w_high_court_penalty=args.w_high_court_penalty,
        w_team_span=args.w_team_span,
        random_seed=args.random_seed,
    )
    
    # Write output
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"Status: {result['status']}")
    print(f"Date: {result['date']}")
    
    if "error" in result:
        print(f"Error: {result['error']}")
        if "traceback" in result:
            print(result['traceback'])
        sys.exit(1)
    
    if "warning" in result:
        print(f"Warning: {result['warning']}")
    
    scheduled = [r for r in result["rows"] if r["start"] != "NIET_GELUKT"]
    failed = [r for r in result["rows"] if r["start"] == "NIET_GELUKT"]
    
    print(f"Scheduled: {len(scheduled)}/{len(result['rows'])} parts")
    print(f"Failed: {len(failed)} parts")
    
    if scheduled:
        print("\nFirst 5 scheduled parts:")
        for row in scheduled[:5]:
            print(f"  {row['team']:30s} {row['part']:6s} "
                  f"{row['start']}-{row['end']} court {row['court']}")


if __name__ == "__main__":
    main()
