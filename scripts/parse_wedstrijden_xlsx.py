#!/usr/bin/env python3
"""Parse the KNLTB competition export (docs/wedstrijden_2026-2027.xlsx) into a
season TSV that the OR-Tools planner understands.

We only keep Mierlo *home* matches on *Sundays*:
  - the match is played on a Sunday (Datum weekday == Sunday), and
  - Team 1 starts with "MIERLO" (Team 1 = home team in the KNLTB export), and
  - the Schema is a "Zondag" competition.

Match count / duration / singles / doubles / mix are derived from the Schema
text, using the same conventions as the existing data/season.tsv.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]

WEEKDAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]

# Output columns match data/season.tsv so the planner/build_pages can read it.
COLUMNS = [
    "Datum",
    "Weekdag",
    "Schema",
    "Wedstrijden",
    "Wedstrijdduur",
    "Singles",
    "Doubles",
    "Mix",
    "Team 1",
    "Team 2",
]


def derive_format(schema: str) -> tuple[int, int, int, int, int]:
    """Return (matches, duration_min, singles, doubles, mix) for a schema string.

    Conventions are taken from the 2025-2026 season.tsv:
      - Gemengd (2DE-2HE-DD-HD-2GD): 8 matches, 90 min, S=4 D=2 M=2
      - Gemengd (DE-HE-GD-DD-HD):    5 matches, 90 min, S=2 D=2 M=1
      - Jongens/Meisjes 13 t/m 17:   6 matches, 90 min, S=4 D=2
      - Junioren 11 t/m 14:          6 matches, 45 min, S=4 D=2
      - Groen:                       6 matches, 45 min, S=4 D=2
      - Heren/Dames Zondag:          6 matches, 90 min, S=4 D=2
    """
    s = schema.lower()
    if "2de-2he-dd-hd-2gd" in s:
        return (8, 90, 4, 2, 2)
    if "de-he-gd-dd-hd" in s:
        return (5, 90, 2, 2, 1)
    if "junioren 11 t/m 14" in s:
        return (6, 45, 4, 2, 0)
    if "groen zondag" in s:
        return (6, 45, 4, 2, 0)
    if ("jongens 13 t/m 17" in s) or ("meisjes 13 t/m 17" in s):
        return (6, 90, 4, 2, 0)
    if ("heren zondag" in s) or ("dames zondag" in s):
        return (6, 90, 4, 2, 0)
    # Unknown schema: best-effort single doubles match so it is still visible.
    return (1, 90, 0, 1, 0)


def is_home_sunday(schema: str, team1: str, weekday: int) -> bool:
    return (
        weekday == 6
        and str(team1).upper().startswith("MIERLO")
        and "zondag" in str(schema).lower()
    )


def parse(xlsx: Path) -> list[dict]:
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    out: list[dict] = []
    for r in rows[1:]:
        d, schema, team1, team2 = r[0], r[1], r[2], r[3]
        if d is None or schema is None:
            continue
        if not is_home_sunday(schema, team1, d.weekday()):
            continue
        m, dur, si, do, mi = derive_format(str(schema))
        out.append(
            {
                "Datum": d.strftime("%d-%m-%Y"),
                "Weekdag": WEEKDAYS_NL[d.weekday()],
                "Schema": str(schema).strip(),
                "Wedstrijden": m,
                "Wedstrijdduur": dur,
                "Singles": si,
                "Doubles": do,
                "Mix": mi,
                "Team 1": str(team1).strip(),
                "Team 2": ("" if team2 is None else str(team2).strip()),
                "_sortkey": (d, str(schema)),
            }
        )
    out.sort(key=lambda x: x["_sortkey"])
    for x in out:
        del x["_sortkey"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xlsx", type=Path, default=ROOT / "docs" / "wedstrijden_2026-2027.xlsx")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "season_2026-2027.tsv")
    args = ap.parse_args()

    records = parse(args.xlsx)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter="\t")
        w.writeheader()
        for rec in records:
            w.writerow(rec)

    by_date: dict[str, int] = defaultdict(int)
    for rec in records:
        by_date[rec["Datum"]] += 1
    print(f"Wrote {args.out} ({len(records)} home-Sunday matches)")
    for date, n in sorted(by_date.items(), key=lambda kv: kv[0][::-1]):
        print(f"  {date}: {n} matches")


if __name__ == "__main__":
    main()
