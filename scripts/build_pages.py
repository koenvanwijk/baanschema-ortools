from __future__ import annotations

import csv
import hashlib
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


def hhmm_to_mins(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def try_place(occupied: dict[int, list[tuple[int, int]]], courts: list[int], start: int, end: int) -> bool:
    for c in courts:
        for a, b in occupied[c]:
            if not (end <= a or start >= b):
                return False
    for c in courts:
        occupied[c].append((start, end))
    return True


def schedule_day(items: list[TeamDay], reservations: list[Reservation]) -> list[dict]:
    open_time = 8 * 60 + 30
    latest_start = 16 * 60 + 30
    step = 30
    courts = list(range(1, 11))
    occupied: dict[int, list[tuple[int, int]]] = {c: [] for c in courts}

    reserve_courts = set()
    kinds = {r.kind for r in reservations}
    if "oranje" in kinds:
        reserve_courts.update({1, 2, 3})
    elif "rood" in kinds:
        reserve_courts.update({1})
    for c in reserve_courts:
        occupied[c].append((9 * 60, 11 * 60))

    ordered = sorted(items, key=lambda t: ((t.matches + 1) // 2 * t.duration_min), reverse=True)
    output: list[dict] = []

    for t in ordered:
        rounds = (t.matches + 1) // 2
        total = rounds * t.duration_min
        placed = False

        for start in range(open_time, latest_start + 1, step):
            end = start + total
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


def color_for(name: str) -> str:
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:6], 16)
    hue = h % 360
    return f"hsl({hue} 70% 88%)"


def render_grid(rows: list[dict]) -> str:
    valid = [r for r in rows if r["start"] != "NIET_GELUKT"]
    if not valid:
        return "<p>Geen planbare wedstrijden.</p>"

    start_min = min(hhmm_to_mins(r["start"]) for r in valid)
    end_min = max(hhmm_to_mins(r["end"]) for r in valid)

    times = list(range(start_min, end_min + 1, 15))
    table: dict[tuple[int, int], tuple[str, str]] = {}

    for r in valid:
        s = hhmm_to_mins(r["start"])
        e = hhmm_to_mins(r["end"])
        label = r["schema"]
        color = color_for(label)
        for t in range(s, e, 15):
            for c in r["courts"]:
                table[(t, c)] = (label, color)

    header = "".join(f"<th>Baan {c}</th>" for c in range(1, 11))
    body_rows = []
    for t in times[:-1]:
        cells = [f"<td class='time'>{mins_to_hhmm(t)}</td>"]
        for c in range(1, 11):
            v = table.get((t, c))
            if v:
                label, color = v
                cells.append(
                    f"<td style='background:{color}' title='{html.escape(label)}'><div class='cell'>{html.escape(label)}</div></td>"
                )
            else:
                cells.append("<td class='empty'>—</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    return (
        "<div class='grid-wrap'><table class='grid'><thead><tr><th>Tijd</th>"
        + header
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table></div>"
    )


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
        failed = [r for r in rows if r["start"] == "NIET_GELUKT"]
        failed_html = ""
        if failed:
            failed_html = "<p><strong>Niet gelukt:</strong> " + ", ".join(html.escape(r["schema"]) for r in failed) + "</p>"
        sections.append(f"<h2>{html.escape(d)}</h2>{failed_html}{render_grid(rows)}")

    page = f"""<!doctype html>
<html lang='nl'>
<head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Baanschema Planner</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;max-width:1500px;margin:1.2rem auto;padding:0 1rem}}
.small{{color:#666}}
.grid-wrap{{overflow:auto;border:1px solid #eee;border-radius:10px;margin-bottom:2rem}}
.grid{{border-collapse:collapse;width:max-content;min-width:100%}}
.grid th,.grid td{{border:1px solid #ececec;padding:.35rem .45rem;vertical-align:top}}
.grid th{{position:sticky;top:0;background:#fafafa;z-index:2}}
.time{{font-variant-numeric:tabular-nums;background:#fcfcfc;position:sticky;left:0;z-index:1;min-width:58px}}
.empty{{color:#bbb;text-align:center;min-width:120px}}
.cell{{font-size:12px;line-height:1.2;max-width:210px}}
</style>
</head>
<body>
<h1>Baanschema Planner (per kwartier)</h1>
<p class='small'>Kolommen = banen, rijen = kwartierblokken. Kleuren onderscheiden teams/schema's. Bron: <code>data/season.tsv</code>.</p>
{''.join(sections)}
</body></html>"""
    (DOCS / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
