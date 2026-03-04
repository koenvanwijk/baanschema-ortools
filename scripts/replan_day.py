from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_pages import parse_input, schedule_day, hhmm_to_mins  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "season.tsv"
OUT = ROOT / "docs" / "replan_result.json"


"""
Matchday replan tool (simple v1)

Input status JSON shape:
{
  "date": "12-04-2026",
  "now": "12:15",
  "completed": [
    {"schema": "...", "part": "S1"},
    ...
  ]
}

Behavior:
- Rebuilds day schedule with existing rules.
- Filters out completed parts.
- Keeps only future/non-completed parts from 'now'.
- Outputs a practical remainder schedule for operations.
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Replan remaining matches for a day")
    ap.add_argument("--status", type=Path, required=True, help="JSON with now/completed")
    ap.add_argument("--input", type=Path, default=INPUT)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    status = json.loads(args.status.read_text(encoding="utf-8"))
    date = status["date"]
    now = hhmm_to_mins(status.get("now", "08:30"))
    completed = {(x.get("schema"), x.get("part")) for x in status.get("completed", [])}

    teams, reservations = parse_input(args.input)
    day_teams = [t for t in teams if t.date == date]
    day_res = [r for r in reservations if r.date == date]

    # full planned day with current heuristics
    planned = schedule_day(day_teams, day_res, date)

    # keep only future + not completed
    remainder = []
    for r in planned:
        if r.get("part") == "COMP":
            if hhmm_to_mins(r["end"]) > now:
                remainder.append(r)
            continue

        key = (r.get("schema"), r.get("part"))
        if key in completed:
            continue

        if r.get("start") in (None, "", "NIET_GELUKT"):
            remainder.append(r)
            continue

        if hhmm_to_mins(r["end"]) <= now:
            continue

        remainder.append(r)

    result = {
        "date": date,
        "now": status.get("now", "08:30"),
        "count": len(remainder),
        "rows": remainder,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Replan rows: {len(remainder)}")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    main()
