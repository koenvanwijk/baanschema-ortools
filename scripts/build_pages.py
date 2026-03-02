from __future__ import annotations

import csv
import html
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
INPUT = ROOT / "data" / "season.tsv"


@dataclass
class TeamDay:
    date: str
    weekday: str
    schema: str
    matches: int
    duration_min: int


@dataclass
class Reservation:
    date: str
    kind: str  # rood/oranje


def parse_input(path: Path) -> tuple[list[TeamDay], list[Reservation]]:
    teams: list[TeamDay] = []
    reservations: list[Reservation] = []

    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            schema = (row.get("Schema") or "").strip()
            date = (row.get("Datum") or "").strip()
            weekday = (row.get("Weekdag") or "").strip()
            matches_raw = (row.get("Wedstrijden") or "").strip()
            duration_raw = (row.get("Wedstrijdduur") or "").strip()

            if not date or not schema:
                continue

            if "rood" in schema.lower():
                reservations.append(Reservation(date=date, kind="rood"))
                continue
            if "oranje" in schema.lower():
                reservations.append(Reservation(date=date, kind="oranje"))
                continue

            if not matches_raw or not duration_raw:
                continue

            teams.append(
                TeamDay(
                    date=date,
                    weekday=weekday,
                    schema=schema,
                    matches=int(matches_raw),
                    duration_min=int(duration_raw),
                )
            )

    return teams, reservations


def mins_to_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def try_place(occupied: dict[int, list[tuple[int, int]]], courts: list[int], start: int, end: int) -> bool:
    for c in courts:
        for a, b in occupied[c]:
            if not (end <= a or start >= b):
                return False
    for c in courts:
        occupied[c].append((start, end))
    return True


def schedule_day(items: list[TeamDay], reservations: list[Reservation]) -> list[dict]:
    # simple baseline: each team uses 2 courts, block duration = ceil(matches/2) * match_duration
    open_time = 8 * 60 + 30
    latest_start = 16 * 60 + 30
    step = 30
    courts = list(range(1, 11))
    occupied: dict[int, list[tuple[int, int]]] = {c: [] for c in courts}

    # reservations 09:00-11:00
    reserve_courts = set()
    kinds = {r.kind for r in reservations}
    if "oranje" in kinds:
        reserve_courts.update({1, 2, 3})
    elif "rood" in kinds:
        reserve_courts.update({1})
    for c in reserve_courts:
        occupied[c].append((9 * 60, 11 * 60))

    # longest blocks first
    ordered = sorted(items, key=lambda t: ((t.matches + 1) // 2 * t.duration_min), reverse=True)
    output = []

    for t in ordered:
        rounds = (t.matches + 1) // 2
        total = rounds * t.duration_min
        placed = False

        for start in range(open_time, latest_start + 1, step):
            end = start + total
            # prefer nearby courts
            for c1 in range(1, 10):
                c2 = c1 + 1
                if try_place(occupied, [c1, c2], start, end):
                    output.append(
                        {
                            "schema": t.schema,
                            "start": mins_to_hhmm(start),
                            "end": mins_to_hhmm(end),
                            "courts": [c1, c2],
                            "duration_min": total,
                            "rounds": rounds,
                        }
                    )
                    placed = True
                    break
            if placed:
                break

        if not placed:
            output.append(
                {
                    "schema": t.schema,
                    "start": "NIET_GELUKT",
                    "end": "",
                    "courts": [],
                    "duration_min": total,
                    "rounds": rounds,
                }
            )

    return sorted(output, key=lambda x: (x["start"], x["schema"]))


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    teams, reserves = parse_input(INPUT)

    by_date: dict[str, list[TeamDay]] = defaultdict(list)
    reserve_by_date: dict[str, list[Reservation]] = defaultdict(list)

    for t in teams:
        by_date[t.date].append(t)
    for r in reserves:
        reserve_by_date[r.date].append(r)

    results = {}
    for d in sorted(by_date.keys(), key=lambda s: datetime.strptime(s, "%d-%m-%Y")):
        results[d] = schedule_day(by_date[d], reserve_by_date[d])

    (DOCS / "result.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    sections = []
    for d, rows in results.items():
        trs = "\n".join(
            f"<tr><td>{html.escape(r['start'])}</td><td>{html.escape(r['end'])}</td><td>{html.escape(', '.join(map(str, r['courts'])) if r['courts'] else '-')}</td><td>{html.escape(r['schema'])}</td></tr>"
            for r in rows
        )
        sections.append(
            f"<h2>{html.escape(d)}</h2><table><thead><tr><th>Start</th><th>Eind</th><th>Banen</th><th>Team/Wedstrijd</th></tr></thead><tbody>{trs}</tbody></table>"
        )

    page = f"""<!doctype html>
<html lang='nl'>
<head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Baanschema Planner</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}}
table{{border-collapse:collapse;width:100%;margin-bottom:1.5rem}}th,td{{border-bottom:1px solid #eee;padding:.5rem;text-align:left}}th{{background:#fafafa}}
.small{{color:#666}}
</style>
</head>
<body>
<h1>Baanschema Planner (baseline)</h1>
<p class='small'>Automatisch gegenereerd uit <code>data/season.tsv</code>. Dit is een eerste heuristische planning (nog geen volledige CP-SAT constraint set).</p>
{''.join(sections)}
</body></html>"""
    (DOCS / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
