from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "season.tsv"


@dataclass
class TeamDay:
    date: str
    schema: str
    matches: int
    duration_min: int
    singles: int
    doubles: int
    mix: int


@dataclass
class Reservation:
    date: str
    kind: str


def _to_int(v: str) -> int:
    v = (v or "").strip()
    return int(v) if v else 0


def parse_input(path: Path) -> tuple[list[TeamDay], list[Reservation]]:
    teams: list[TeamDay] = []
    reservations: list[Reservation] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            date = (row.get("Datum") or "").strip()
            schema = (row.get("Schema") or "").strip()
            if not date or not schema:
                continue
            low = schema.lower()
            if "rood" in low:
                reservations.append(Reservation(date=date, kind="rood"))
                continue
            if "oranje" in low:
                reservations.append(Reservation(date=date, kind="oranje"))
                continue

            m = _to_int(row.get("Wedstrijden") or "")
            d = _to_int(row.get("Wedstrijdduur") or "")
            if not m or not d:
                continue
            teams.append(
                TeamDay(
                    date=date,
                    schema=schema,
                    matches=m,
                    duration_min=d,
                    singles=_to_int(row.get("Singles") or ""),
                    doubles=_to_int(row.get("Doubles") or ""),
                    mix=_to_int(row.get("Mix") or ""),
                )
            )
    return teams, reservations


def build_parts(team: TeamDay) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    parts += [(f"S{i+1}", "S") for i in range(team.singles)]
    parts += [(f"D{i+1}", "D") for i in range(team.doubles)]
    parts += [(f"GD{i+1}", "M") for i in range(team.mix)]
    while len(parts) < team.matches:
        parts.append((f"W{len(parts)+1}", "W"))
    return parts[: team.matches]


def mins_to_hhmm(m: int) -> str:
    return f"{m//60:02d}:{m%60:02d}"


def solve_day(date: str, teams: list[TeamDay], reservations: list[Reservation], time_limit_s: float = 20.0) -> dict:
    day_teams = [t for t in teams if t.date == date]
    day_res = [r for r in reservations if r.date == date]

    # quarter-hour grid
    start_min = 8 * 60 + 30
    end_min = 20 * 60
    slot_mins = list(range(start_min, end_min + 1, 15))
    slot_idx = {m: i for i, m in enumerate(slot_mins)}
    courts = list(range(1, 11))

    first_cutoff = {
        "12-04-2026": 16 * 60,
        "19-04-2026": 17 * 60,
        "10-05-2026": 17 * 60,
        "17-05-2026": 18 * 60 + 30,
        "25-05-2026": 16 * 60,
        "06-04-2026": 16 * 60,
    }.get(date, 15 * 60)

    reserved = []  # (court, start, end)
    for r in day_res:
        if r.kind == "oranje":
            for c in [1, 2, 3]:
                reserved.append((c, 8 * 60 + 30, 10 * 60 + 30))
        elif r.kind == "rood":
            reserved.append((1, 8 * 60 + 30, 9 * 60 + 30))

    parts = []
    for t in day_teams:
        for label, kind in build_parts(t):
            parts.append(
                {
                    "team": t.schema,
                    "label": label,
                    "kind": kind,
                    "duration": t.duration_min,
                    "is_mixed_team": "gemengd zondag" in t.schema.lower(),
                }
            )

    model = cp_model.CpModel()
    x = {}  # part,start,court
    y = []

    allowed_starts = {}
    for p_idx, p in enumerate(parts):
        dur = p["duration"]
        latest = end_min - dur
        starts = [m for m in slot_mins if m <= latest]
        if p["is_mixed_team"]:
            starts = [m for m in starts if m >= 10 * 60]
        allowed_starts[p_idx] = starts

        vars_p = []
        for s in starts:
            for c in courts:
                v = model.new_bool_var(f"x_p{p_idx}_s{s}_c{c}")
                x[(p_idx, s, c)] = v
                vars_p.append(v)
        yp = model.new_bool_var(f"y_p{p_idx}")
        y.append(yp)
        model.add(sum(vars_p) == yp)

    # court occupancy including reservations
    for c in courts:
        for t in slot_mins[:-1]:
            occ = []
            for p_idx, p in enumerate(parts):
                dur = p["duration"]
                for s in allowed_starts[p_idx]:
                    if s <= t < s + dur:
                        occ.append(x[(p_idx, s, c)])

            is_reserved = any(rc == c and rs <= t < re for rc, rs, re in reserved)
            if is_reserved:
                model.add(sum(occ) == 0)
            else:
                model.add(sum(occ) <= 1)

    # S and D cannot overlap within same team (M can overlap)
    by_team = defaultdict(list)
    for i, p in enumerate(parts):
        by_team[p["team"]].append(i)

    for team, idxs in by_team.items():
        s_parts = [i for i in idxs if parts[i]["kind"] == "S"]
        d_parts = [i for i in idxs if parts[i]["kind"] == "D"]
        if not s_parts or not d_parts:
            continue
        for t in slot_mins[:-1]:
            s_occ = []
            d_occ = []
            for i in s_parts:
                for s in allowed_starts[i]:
                    if s <= t < s + parts[i]["duration"]:
                        for c in courts:
                            s_occ.append(x[(i, s, c)])
            for i in d_parts:
                for s in allowed_starts[i]:
                    if s <= t < s + parts[i]["duration"]:
                        for c in courts:
                            d_occ.append(x[(i, s, c)])
            model.add(sum(s_occ) + sum(d_occ) <= 1)

    # first match start <= cutoff (at least one part start <= cutoff per team)
    for team, idxs in by_team.items():
        early = []
        for i in idxs:
            for s in allowed_starts[i]:
                if s <= first_cutoff:
                    for c in courts:
                        early.append(x[(i, s, c)])
        model.add(sum(early) >= 1)

    # objective phase 1+2 in one shot:
    # maximize scheduled parts, then maximize morning occupancy, then earlier starts
    scheduled_score = sum(y) * 1_000_000

    morning_occ_terms = []
    for c in courts:
        for t in slot_mins[:-1]:
            if t >= 12 * 60:
                continue
            for p_idx, p in enumerate(parts):
                for s in allowed_starts[p_idx]:
                    if s <= t < s + p["duration"]:
                        morning_occ_terms.append(x[(p_idx, s, c)])

    early_start_bonus = []
    for p_idx, p in enumerate(parts):
        for s in allowed_starts[p_idx]:
            # higher bonus for earlier starts
            bonus = max(0, (18 * 60 - s))
            for c in courts:
                early_start_bonus.append(bonus * x[(p_idx, s, c)])

    model.maximize(scheduled_score + 100 * sum(morning_occ_terms) + sum(early_start_bonus))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8

    st = solver.solve(model)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": solver.status_name(st), "date": date, "rows": []}

    rows = []
    for p_idx, p in enumerate(parts):
        placed = False
        for s in allowed_starts[p_idx]:
            for c in courts:
                if solver.value(x[(p_idx, s, c)]) == 1:
                    rows.append(
                        {
                            "team": p["team"],
                            "part": p["label"],
                            "kind": p["kind"],
                            "start": mins_to_hhmm(s),
                            "end": mins_to_hhmm(s + p["duration"]),
                            "court": c,
                        }
                    )
                    placed = True
        if not placed:
            rows.append(
                {
                    "team": p["team"],
                    "part": p["label"],
                    "kind": p["kind"],
                    "start": "NIET_GELUKT",
                    "end": "",
                    "court": None,
                }
            )

    return {
        "status": solver.status_name(st),
        "date": date,
        "rows": sorted(rows, key=lambda r: (r["start"], r["court"] or 99, r["team"], r["part"])),
        "objective": solver.objective_value,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Second planner using OR-Tools CP-SAT optimization loop")
    ap.add_argument("--input", type=Path, default=INPUT)
    ap.add_argument("--date", required=True, help="dd-mm-YYYY")
    ap.add_argument("--time-limit", type=float, default=20.0)
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "ortools_result.json")
    args = ap.parse_args()

    teams, res = parse_input(args.input)
    result = solve_day(args.date, teams, res, time_limit_s=args.time_limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Status: {result['status']}")
    print(f"Rows: {len(result['rows'])}")
    if "objective" in result:
        print(f"Objective: {result['objective']:.1f}")


if __name__ == "__main__":
    main()
