#!/usr/bin/env python3
"""Validate an OR-Tools day schedule against the planning rules.

Reads the season TSV (for the expected teams/parts per day) and one or more
schedule JSON files produced by ortools_planner.py. Reports, per day:
  - number of home matches (teams) and scheduled parts vs total parts,
  - HARD constraint violations (must never happen),
  - MODEL/soft preference violations (reported, non-blocking).

Exit code is always 0: reporting is non-blocking, matching the "niet-blocking
beleid" in docs/planningsregels.md.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ortools_planner import parse_input, build_parts  # type: ignore

ROOT = Path(__file__).resolve().parents[1]

DAY_START = 8 * 60 + 30
DAY_END = 20 * 60
LAST_START = 19 * 60 + 30


def hhmm_to_min(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


@dataclass
class DayReport:
    date: str
    teams: int = 0
    total_parts: int = 0
    scheduled_parts: int = 0
    hard: list[str] = field(default_factory=list)
    model: list[str] = field(default_factory=list)


def _is_mixed(schema: str) -> bool:
    return "gemengd zondag" in schema.lower()


def _is_jeugd_1317(schema: str) -> bool:
    s = schema.lower()
    return ("jongens 13 t/m 17" in s) or ("meisjes 13 t/m 17" in s)


def _is_youth(schema: str) -> bool:
    s = schema.lower()
    return _is_jeugd_1317(schema) or ("junioren" in s) or ("groen zondag" in s)


def _is_combo(schema: str) -> bool:
    return "2de-2he-dd-hd-2gd" in schema.lower()


def validate_day(date: str, teams, rows: list[dict]) -> DayReport:
    day_teams = [t for t in teams if t.date == date]
    rep = DayReport(date=date, teams=len(day_teams))

    # Expected parts per team (unique key).
    expected: dict[str, int] = {}
    schema_by_key: dict[str, str] = {}
    for t in day_teams:
        key = t.team_key or t.schema
        expected[key] = len(build_parts(t))
        schema_by_key[key] = t.schema
    rep.total_parts = sum(expected.values())

    placed = [r for r in rows if r.get("start") not in (None, "", "NIET_GELUKT")]
    failed = [r for r in rows if r.get("start") == "NIET_GELUKT"]
    rep.scheduled_parts = len(placed)

    if failed:
        sample = ", ".join(f"{r.get('team','?')} {r.get('part','?')}" for r in failed[:6])
        rep.hard.append(f"{len(failed)} parts NIET_GELUKT ({sample})")

    # Intervals per placed row.
    for r in placed:
        s = hhmm_to_min(r["start"])
        e = hhmm_to_min(r["end"])
        if s < DAY_START or s > LAST_START:
            rep.hard.append(f"start {r['start']} outside 08:30-19:30 ({r.get('team')} {r.get('part')})")
        if e > DAY_END:
            rep.hard.append(f"end {r['end']} after 20:00 ({r.get('team')} {r.get('part')})")
        if s % 15 != 0:
            rep.hard.append(f"start {r['start']} not on quarter-hour ({r.get('team')} {r.get('part')})")

    # HARD: one match per court per timeslot.
    court_slot: dict[tuple[int, int], int] = defaultdict(int)
    for r in placed:
        s, e, c = hhmm_to_min(r["start"]), hhmm_to_min(r["end"]), r.get("court")
        if c is None:
            continue
        for t in range(s, e, 15):
            court_slot[(c, t)] += 1
    clashes = {k for k, v in court_slot.items() if v > 1}
    if clashes:
        rep.hard.append(f"court double-booked in {len(clashes)} court-slots")

    # Per-team checks.
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in placed:
        by_team[r.get("team_id") or r.get("team")].append(r)

    for key, rr in by_team.items():
        schema = schema_by_key.get(key, rr[0].get("team", ""))
        # kinds active per timeslot
        for t in range(DAY_START, DAY_END, 15):
            active = [x for x in rr if hhmm_to_min(x["start"]) <= t < hhmm_to_min(x["end"])]
            kinds = {x.get("kind") for x in active}
            # HARD: S and D not simultaneous.
            if "S" in kinds and "D" in kinds:
                rep.hard.append(f"S+D simultaneous @ {_m(t)} ({schema})")
                break
        for t in range(DAY_START, DAY_END, 15):
            active = [x for x in rr if hhmm_to_min(x["start"]) <= t < hhmm_to_min(x["end"])]
            kinds = {x.get("kind") for x in active}
            # HARD: D and GD(M) not simultaneous.
            if "D" in kinds and "M" in kinds:
                rep.hard.append(f"D+GD simultaneous @ {_m(t)} ({schema})")
                break
        if _is_combo(schema):
            for t in range(DAY_START, DAY_END, 15):
                active = [x for x in rr if hhmm_to_min(x["start"]) <= t < hhmm_to_min(x["end"])]
                kinds = {x.get("kind") for x in active}
                if "S" in kinds and "M" in kinds:
                    rep.hard.append(f"S+GD simultaneous (combo) @ {_m(t)} ({schema})")
                    break
        # HARD: max 2 concurrent parts + max 4 players concurrently.
        for t in range(DAY_START, DAY_END, 15):
            active = [x for x in rr if hhmm_to_min(x["start"]) <= t < hhmm_to_min(x["end"])]
            if len(active) > 2:
                rep.hard.append(f">2 concurrent parts @ {_m(t)} ({schema})")
                break
            players = sum(1 if x.get("kind") == "S" else 2 for x in active)
            if players > 4:
                rep.hard.append(f">4 concurrent players @ {_m(t)} ({schema})")
                break

        # HARD: start-time windows.
        first_start = min(hhmm_to_min(x["start"]) for x in rr)
        for x in rr:
            st = hhmm_to_min(x["start"])
            if _is_mixed(schema) and st < 10 * 60:
                rep.hard.append(f"mixed team starts {x['start']} (<10:00) ({schema})")
                break
        if _is_jeugd_1317(schema):
            for x in rr:
                if hhmm_to_min(x["start"]) < 11 * 60:
                    rep.hard.append(f"jeugd 13-17 starts {x['start']} (<11:00) ({schema})")
                    break
        if _is_youth(schema):
            for x in rr:
                if hhmm_to_min(x["start"]) > 17 * 60 + 30:
                    rep.model.append(f"youth starts {x['start']} (>17:30) ({schema})")
                    break

        # MODEL: at most 2 play blocks per team (compactness).
        occ = sorted((hhmm_to_min(x["start"]), hhmm_to_min(x["end"])) for x in rr)
        blocks = 1
        cur_end = occ[0][1]
        for s, e in occ[1:]:
            if s > cur_end:
                blocks += 1
            cur_end = max(cur_end, e)
        if blocks > 2:
            rep.model.append(f"{blocks} play blocks (>2) ({schema})")

        # MODEL: single court-pair (1+2,3+4,...) per team.
        pairs = {(c - 1) // 2 for c in (x.get("court") for x in rr) if c}
        if len(pairs) > 1:
            rep.model.append(f"uses {len(pairs)} court-pairs ({schema})")

    return rep


def _m(t: int) -> str:
    return f"{t//60:02d}:{t%60:02d}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=ROOT / "data" / "season_2026-2027.tsv")
    ap.add_argument("--schedule", type=Path, nargs="+", required=True, help="ortools_*.json file(s)")
    args = ap.parse_args()

    teams, _res = parse_input(args.input)

    reports: list[DayReport] = []
    for path in args.schedule:
        data = json.loads(path.read_text(encoding="utf-8"))
        date = data.get("date", path.stem)
        rep = validate_day(date, teams, data.get("rows", []))
        reports.append(rep)

    total_hard = 0
    total_model = 0
    print("=" * 72)
    for rep in reports:
        total_hard += len(rep.hard)
        total_model += len(rep.model)
        flag = "OK" if not rep.hard else "HARD-VIOLATIONS"
        print(
            f"{rep.date}: teams={rep.teams}  parts={rep.scheduled_parts}/{rep.total_parts}  "
            f"HARD={len(rep.hard)}  MODEL={len(rep.model)}  [{flag}]"
        )
        for v in rep.hard:
            print(f"    HARD  : {v}")
        for v in rep.model:
            print(f"    MODEL : {v}")
    print("=" * 72)
    print(f"TOTAL: HARD={total_hard}  MODEL={total_model} over {len(reports)} day(s)")


if __name__ == "__main__":
    main()
