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
    import cudf
    from cuopt import milp
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
    
    Variables:
        x[p,t,c] ∈ {0,1}: match part p starts at time slot t on court c
        team_start[i] ∈ [0, num_slots]: earliest start slot for team i
        team_end[i] ∈ [0, num_slots]: latest end slot for team i
        
    Constraints:
        1. Each part scheduled exactly once (or not at all for NIET_GELUKT)
        2. No court overlap (at most one part per court per time)
        3. Court pairing (S and D for same match start at same time on adjacent courts)
        4. Max 2 courts per team
        5. Youth teams start >= 08:30
        6. Reserved slots blocked
        
    Objective:
        Minimize weighted sum of:
        - Team span (team_end - team_start)
        - Gaps in team schedule
        - High court usage
        - Late starts
        - Block compactness violations
    """
    
    day_teams = [t for t in teams if t.date == date]
    day_res = [r for r in reservations if r.date == date]
    
    if not day_teams:
        return {"status": "OPTIMAL", "date": date, "rows": []}
    
    # Time slots (15-minute intervals from 08:30 to 20:00)
    start_min = 8 * 60 + 30
    end_min = 20 * 60
    slot_mins = list(range(start_min, end_min + 1, 15))
    num_slots = len(slot_mins)
    slot_idx = {m: i for i, m in enumerate(slot_mins)}
    
    # Courts 1-10
    courts = list(range(1, 11))
    num_courts = len(courts)
    
    # Court pairs for S+D matches
    COURT_PAIRS = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]
    
    # Build parts
    parts_data = []  # (team_idx, team_schema, part_label, part_kind, duration_slots)
    for team_idx, team in enumerate(day_teams):
        duration_slots = (team.duration_min + 14) // 15  # Round up to slots
        for part_label, part_kind in build_parts(team):
            parts_data.append((team_idx, team.schema, part_label, part_kind, duration_slots))
    
    num_parts = len(parts_data)
    
    print(f"[cuOpt] Planning {date}: {len(day_teams)} teams, {num_parts} parts, "
          f"{num_slots} time slots, {num_courts} courts")
    
    # TODO: Actually implement the MILP formulation using cuOpt
    # For now, return a placeholder that indicates parts couldn't be scheduled
    
    # This is where the actual cuOpt MILP solver would go:
    # 1. Create cuopt.milp.Model
    # 2. Add variables x[p,t,c], team_start[i], team_end[i]
    # 3. Add constraints
    # 4. Set objective
    # 5. Solve
    # 6. Extract solution
    
    warnings.warn(
        "cuOpt MILP implementation is not yet complete. "
        "Returning all parts as NIET_GELUKT. "
        "This is a placeholder - full implementation coming soon."
    )
    
    # Placeholder: mark all parts as unscheduled
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
        "status": "FEASIBLE",  # Technically feasible (empty schedule)
        "date": date,
        "rows": rows,
        "warning": "cuOpt implementation incomplete - placeholder result"
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
