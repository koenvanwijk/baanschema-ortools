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
    # Patch cuOpt 25.12 expression operator bugs (see cuopt_compat.py) BEFORE
    # building any model. Import order matters: this imports cuopt itself.
    import cuopt_compat  # noqa: F401  (side-effecting: patches cuOpt classes)
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
        1 if match part p starts at time slot s on court c. Variables are only
        created for feasible (slot, court) combinations (respecting youth/mixed
        start windows and reserved slots), which keeps the model compact.

    unscheduled[part_id] ∈ {0,1}
        Slack: 1 if the part could not be scheduled. Heavily penalised so the
        solver schedules as many parts as possible first.

    team_start[team_id], team_end[team_id] ∈ ℝ≥0
        Earliest start / latest end (minutes from midnight) for the team.

    team_gap_penalty[team_id] ∈ ℝ≥0
        Non-negative auxiliary variable clamping the team's idle-gap penalty at 0.

    team_pair[team_id, pair_idx] ∈ {0,1}
        1 if the team plays on court pair `pair_idx` (one of (1,2),(3,4),...).

    Per-part linear time expressions (not variables, built from x):
        part_start_expr[p] = Σ_(s,c) slot_mins[s]           * x[p,s,c]
        part_end_expr[p]   = Σ_(s,c) (slot_mins[s]+duration) * x[p,s,c]
    These make the time-window and pairing constraints compact (a few rows per
    part instead of one big-M row per (part, slot, court) assignment).

    Hard Constraints:
    -----------------
    1. Each part is scheduled exactly once, or flagged unscheduled:
       ∀p: Σ_(s,c) x[p,s,c] + unscheduled[p] = 1

    2. No court overlaps (at most one match per court per timeslot):
       ∀court c, timeslot t: Σ_{p covering t} x[p,s,c] ≤ 1

    3. Round structure (non-mixed teams): same-kind pairs start together
       (S1+S2, S3+S4, D1+D2, ...), enforced via
       part_start_expr[p0] == part_start_expr[p1] (big-M relaxed if unscheduled).

    4/5. Court-pair confinement: each team plays on exactly one adjacent court
       pair, and every part of the team must be on that pair's two courts:
       Σ_pi team_pair[t,pi] = 1  and  x[p,s,c] ≤ team_pair[t, pair_of(c)].

    6. Youth start window: enforced by not creating variables outside the window.

    7. Team time windows (compact, one row per part):
       team_start[t] ≤ part_start_expr[p] + M·unscheduled[p]
       team_end[t]   ≥ part_end_expr[p]   − M·unscheduled[p]

    8. Reserved slots: enforced by not creating the corresponding variables.

    9. (removed) No global S-before-D ordering exists in the reference model.

    Span/gap linking:
       team_end[t] ≥ team_start[t]                              (span ≥ 0)
       team_gap_penalty[t] ≥ team_end − team_start − total_dur  (gap ≥ 0)

    Objective (minimise):
    ---------------------
      UNSCHEDULED_PENALTY · Σ_p unscheduled[p]         (dominant: schedule first)
      + SOFT_SCALE · [ w_team_span   · Σ_t (end − start)
                     + w_high_court  · Σ (court · x)
                     + w_long_gap    · Σ_t gap_penalty / 100
                     + w_late_start  · late-start penalty
                     + w_youth_late  · youth-late penalty ]

    The soft weights are scaled (SOFT_SCALE) so the entire soft budget stays well
    below the unscheduled penalty and the coefficient range stays numerically
    healthy on the GPU.
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
                    vtype=INTEGER,
                    lb=0,
                    ub=1
                )
    
    # Continuous variables: team_start[team_idx], team_end[team_idx]
    team_start = {}
    team_end = {}
    for t_idx in range(num_teams):
        team_start[t_idx] = problem.addVariable(
            name=f"team_start_{t_idx}",
            vtype=CONTINUOUS,
            lb=0,
            ub=end_min
        )
        team_end[t_idx] = problem.addVariable(
            name=f"team_end_{t_idx}",
            vtype=CONTINUOUS,
            lb=0,
            ub=end_min
        )
    
    # Continuous variables: team_gap_penalty[team_idx] (for objective).
    # Court-pair selection variables (team_pair) are created later, next to the
    # court-pair confinement constraint that uses them.
    team_gap_penalty = {}
    for t_idx in range(num_teams):
        team_gap_penalty[t_idx] = problem.addVariable(
            name=f"gap_penalty_{t_idx}",
            vtype=CONTINUOUS,
            lb=0,
            ub=1e6
        )

    # =========================================================================
    # SLACK VARIABLES FOR SOFT SCHEDULING
    # =========================================================================
    
    # Add slack variable per part: 1 if unscheduled, 0 if scheduled
    unscheduled = {}
    for p_idx in range(num_parts):
        unscheduled[p_idx] = problem.addVariable(
            name=f"unscheduled_{p_idx}",
            vtype=INTEGER,
            lb=0,
            ub=1
        )
    
    # =========================================================================
    # PER-PART LINEAR TIME EXPRESSIONS (used to keep the model compact)
    # =========================================================================
    # For every part, build a single linear expression equal to its start time
    # (in minutes) when scheduled, and 0 when unscheduled:
    #     part_start_expr[p] = Σ_(s,c) slot_mins[s] * x[p,s,c]
    #     part_end_expr[p]   = Σ_(s,c) (slot_mins[s] + duration) * x[p,s,c]
    # These let us express the time-window and S-before-D constraints with a
    # handful of constraints per part instead of one big-M constraint per
    # (part, slot, court) assignment, which otherwise blows the model up to
    # millions of rows and exhausts GPU memory.
    x_by_part = defaultdict(list)
    for (p_idx, s_idx, c) in x.keys():
        x_by_part[p_idx].append((s_idx, c))

    part_start_expr = {}
    part_end_expr = {}
    for p_idx in range(num_parts):
        assigns = x_by_part.get(p_idx, [])
        if not assigns:
            part_start_expr[p_idx] = None
            part_end_expr[p_idx] = None
            continue
        dur = parts[p_idx]["duration_min"]
        part_start_expr[p_idx] = sum(
            slot_mins[s_idx] * x[(p_idx, s_idx, c)] for (s_idx, c) in assigns
        )
        part_end_expr[p_idx] = sum(
            (slot_mins[s_idx] + dur) * x[(p_idx, s_idx, c)] for (s_idx, c) in assigns
        )

    # =========================================================================
    # HARD CONSTRAINTS
    # =========================================================================

    # 1. Each part must be scheduled exactly once OR marked unscheduled
    for p_idx in range(num_parts):
        vars_for_part = [
            x[(p_idx, s_idx, c)]
            for (pi, s_idx, c) in x.keys() if pi == p_idx
        ]
        if vars_for_part:
            problem.addConstraint(
                sum(vars_for_part) + unscheduled[p_idx] == 1,
                name=f"part_{p_idx}_once"
            )
        else:
            # No valid slots for this part — must be unscheduled
            problem.addConstraint(
                unscheduled[p_idx] == 1,
                name=f"part_{p_idx}_forced_unscheduled"
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
    
    # 3. Round structure: same-kind pairs start at the same time (matches the
    # OR-Tools "Gold" pattern): S1+S2 together, S3+S4 together, D1+D2 together,
    # etc. This applies only to non-mixed teams. Expressed with the per-part
    # start expressions: start(p0) == start(p1) when both are scheduled, relaxed
    # by big-M whenever either part is unscheduled.
    for t_idx, part_indices in team_parts.items():
        team = day_teams[t_idx]
        if "gemengd" in team.schema.lower():
            continue  # Skip mixed teams

        for kind in ("S", "D", "M"):
            kind_parts = [i for i in part_indices if parts[i]["part_kind"] == kind]
            for j in range(0, len(kind_parts) - 1, 2):
                p0, p1 = kind_parts[j], kind_parts[j + 1]
                if part_start_expr[p0] is None or part_start_expr[p1] is None:
                    continue
                relax = end_min * (unscheduled[p0] + unscheduled[p1])
                problem.addConstraint(
                    part_start_expr[p0] <= part_start_expr[p1] + relax,
                    name=f"pair_start_{t_idx}_{kind}_{p0}_{p1}_a",
                )
                problem.addConstraint(
                    part_start_expr[p1] <= part_start_expr[p0] + relax,
                    name=f"pair_start_{t_idx}_{kind}_{p0}_{p1}_b",
                )

    # 4/5. Court-pair confinement: every team uses exactly one adjacent court
    # pair (1+2, 3+4, ...), and all of its parts must be played on that pair's
    # two courts. This replaces the looser "max 2 courts" + big-M court-linking
    # constraints with the correct rule and automatically bounds a team to two
    # adjacent courts.
    pair_of_court = {}
    for pi, (ca, cb) in enumerate(COURT_PAIRS):
        pair_of_court[ca] = pi
        pair_of_court[cb] = pi

    team_pair = {}
    for t_idx in range(num_teams):
        pvars = []
        for pi in range(len(COURT_PAIRS)):
            v = problem.addVariable(
                name=f"team_pair_{t_idx}_{pi}", vtype=INTEGER, lb=0, ub=1
            )
            team_pair[(t_idx, pi)] = v
            pvars.append(v)
        problem.addConstraint(sum(pvars) == 1, name=f"team_{t_idx}_one_pair")

    # A part on court c requires its team's selected pair to be the one containing c.
    for (p_idx, s_idx, c) in x.keys():
        t_idx = parts[p_idx]["team_idx"]
        problem.addConstraint(
            x[(p_idx, s_idx, c)] <= team_pair[(t_idx, pair_of_court[c])],
            name=f"court_pair_link_p{p_idx}_s{s_idx}_c{c}",
        )

    # 6. Youth start time >= 08:30 (this is already enforced by not creating variables)
    # No additional constraint needed
    
    # 7. Team time windows (link start/end to actual assignments)
    # Compact form using the per-part linear time expressions: one constraint
    # per part instead of one per (part, slot, court) assignment.
    #   scheduled part -> team_start[t] <= part_start, team_end[t] >= part_end
    # When a part is unscheduled its expression is 0, so the big-M term (scaled
    # by the part's `unscheduled` indicator) relaxes the constraint.
    M_time = 20 * 60  # Big-M for time (max day duration)
    for t_idx, part_indices in team_parts.items():
        for p_idx in part_indices:
            if part_start_expr[p_idx] is None:
                continue
            # team_start[t] <= part_start + M*unscheduled[p]
            problem.addConstraint(
                team_start[t_idx] <= part_start_expr[p_idx] + M_time * unscheduled[p_idx],
                name=f"team_start_{t_idx}_p{p_idx}"
            )
            # team_end[t] >= part_end - M*unscheduled[p]
            problem.addConstraint(
                team_end[t_idx] >= part_end_expr[p_idx] - M_time * unscheduled[p_idx],
                name=f"team_end_{t_idx}_p{p_idx}"
            )
    
    # 8. Reserved slots (already handled by not creating variables)
    # No additional constraint needed

    # 9. (removed) There is no global "S before D" ordering rule. The OR-Tools
    # reference model only requires same-kind pairs to start together (see
    # constraint 3 above); it never forces singles to precede doubles. The
    # previous S-before-D constraint was both incorrect and over-restrictive,
    # so it has been dropped.

    # =========================================================================
    # SPAN / GAP LINKING CONSTRAINTS
    # =========================================================================
    # Without these the soft span/gap terms could be driven negative (rewarding
    # empty or inverted schedules), which made the solver leave every part
    # unscheduled. team_total_duration is the sum of the durations of a team's
    # parts; because a team may play two parts in parallel on two courts, the
    # span (end - start) can legitimately be *smaller* than the total duration,
    # so the gap must be clamped at 0 via a dedicated non-negative variable.
    team_total_duration = {
        t_idx: sum(parts[p]["duration_min"] for p in part_indices)
        for t_idx, part_indices in team_parts.items()
    }
    for t_idx in range(num_teams):
        # Span is non-negative.
        problem.addConstraint(
            team_end[t_idx] >= team_start[t_idx],
            name=f"team_span_nonneg_{t_idx}",
        )
        # Gap penalty variable: gap >= span - total_duration, and gap >= 0 (lb).
        # It only ever adds cost, never subtracts it.
        problem.addConstraint(
            team_gap_penalty[t_idx]
            >= team_end[t_idx] - team_start[t_idx] - team_total_duration[t_idx],
            name=f"team_gap_link_{t_idx}",
        )

    # =========================================================================
    # OBJECTIVE FUNCTION (soft constraints)
    # =========================================================================
    #
    # Scheduling as many parts as possible is the top priority, so the penalty
    # for an unscheduled part must exceed the largest soft cost the solver could
    # ever save by leaving parts out. The soft tuning weights below are large
    # (hundreds of thousands to millions) and multiply minute-scale quantities,
    # so they are scaled down by SOFT_SCALE to keep the whole soft budget well
    # under the unscheduled penalty and within a numerically healthy range.
    objective_terms = []

    SOFT_SCALE = 1.0 / 10_000.0

    # 0. CRITICAL: dominant penalty for unscheduled parts -> schedule first.
    UNSCHEDULED_PENALTY = 100_000_000
    for p_idx in range(num_parts):
        objective_terms.append(UNSCHEDULED_PENALTY * unscheduled[p_idx])

    # 10. Team span minimization (compactness).
    for t_idx in range(num_teams):
        objective_terms.append(
            SOFT_SCALE * w_team_span * (team_end[t_idx] - team_start[t_idx])
        )

    # 11. High court penalty (prefer low-numbered courts).
    for (p_idx, s_idx, c) in x.keys():
        objective_terms.append(SOFT_SCALE * w_high_court_penalty * c * x[(p_idx, s_idx, c)])

    # 12. Long gaps within a team (clamped at 0 via team_gap_penalty).
    for t_idx in range(num_teams):
        objective_terms.append(SOFT_SCALE * w_long_gap * team_gap_penalty[t_idx] / 100)

    # 14. Late start penalty (after 14:00).
    for (p_idx, s_idx, c) in x.keys():
        start_time = slot_mins[s_idx]
        if start_time > 14 * 60:
            lateness = start_time - 14 * 60
            objective_terms.append(
                SOFT_SCALE * w_late_start * lateness * x[(p_idx, s_idx, c)] / 100
            )

    # 15. Youth late penalty (youth after 16:00).
    for (p_idx, s_idx, c) in x.keys():
        part = parts[p_idx]
        if part["is_youth"]:
            start_time = slot_mins[s_idx]
            if start_time > 16 * 60:
                lateness = start_time - 16 * 60
                objective_terms.append(
                    SOFT_SCALE * w_youth_late * lateness * x[(p_idx, s_idx, c)] / 100
                )

    # Set objective: minimize total weighted cost
    problem.setObjective(sum(objective_terms), sense=MINIMIZE)
    
    # =========================================================================
    # SOLVE
    # =========================================================================
    
    print(f"[cuOpt] Solving MILP with {len(x)} binary vars, {num_teams*2} continuous vars...")
    print(f"[cuOpt] Time limit: {time_limit_s}s")
    
    settings = SolverSettings()
    settings.set_parameter("time_limit", time_limit_s)
    settings.set_parameter("log_to_console", 1)
    settings.set_parameter("mip_relative_gap", 0.01)  # 1% optimality gap
    
    problem.solve(settings)
    
    # =========================================================================
    # EXTRACT SOLUTION
    # =========================================================================
    
    if problem.Status.name not in ["Optimal", "FeasibleFound"]:
        print(f"[cuOpt] Solver failed with status: {problem.Status.name}")
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
    
    print(f"[cuOpt] Solution status: {problem.Status.name}, objective: {problem.ObjValue:.2f}")
    
    # Extract assignments from solution
    def fmt_time(minutes: int) -> str:
        """Convert minutes from midnight to HH:MM format."""
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"
    
    assignment = {}  # part_idx -> (slot_idx, court)
    for (p_idx, s_idx, c), var in x.items():
        if var.getValue() > 0.5:  # Binary variable is 1
            assignment[p_idx] = (s_idx, c)
    
    # Check which parts are unscheduled
    unscheduled_parts = []
    for p_idx in range(num_parts):
        if unscheduled[p_idx].getValue() > 0.5:
            unscheduled_parts.append(p_idx)
    
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
    if unscheduled_parts:
        print(f"[cuOpt] WARNING: {len(unscheduled_parts)} parts could not be scheduled:")
        for p_idx in unscheduled_parts:
            part = parts[p_idx]
            print(f"  - Part {p_idx}: {part['part_label']} ({part['part_kind']}, {part['duration_min']}min)")
    print(f"[cuOpt] Objective value: {problem.ObjValue:.2f}")
    
    return {
        "status": "OPTIMAL" if problem.Status.name == "Optimal" else "FEASIBLE",
        "date": date,
        "rows": rows,
        "objective_value": problem.ObjValue,
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
