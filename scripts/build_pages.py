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
            schema = (row.get("Schema") or "").strip()
            date = (row.get("Datum") or "").strip()
            weekday = (row.get("Weekdag") or "").strip()
            if not date or not schema:
                continue

            low = schema.lower()
            if "rood" in low:
                reservations.append(Reservation(date=date, kind="rood"))
                continue
            if "oranje" in low:
                reservations.append(Reservation(date=date, kind="oranje"))
                continue

            matches = _to_int(row.get("Wedstrijden") or "")
            duration = _to_int(row.get("Wedstrijdduur") or "")
            if not matches or not duration:
                continue

            teams.append(
                TeamDay(
                    date=date,
                    weekday=weekday,
                    schema=schema,
                    matches=matches,
                    duration_min=duration,
                    singles=_to_int(row.get("Singles") or ""),
                    doubles=_to_int(row.get("Doubles") or ""),
                    mix=_to_int(row.get("Mix") or ""),
                )
            )
    return teams, reservations


def mins_to_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def hhmm_to_mins(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return not (a[1] <= b[0] or a[0] >= b[1])


def color_for(name: str) -> str:
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:6], 16)
    hue = h % 360
    return f"hsl({hue} 70% 88%)"


def short_team_name(schema: str) -> str:
    return schema.split("–", 1)[0].strip()[:18]


def build_rounds(team: TeamDay) -> list[list[dict]]:
    # Doubles/mix nooit tegelijk met singles: plan in aparte blokken
    singles = [{"label": f"S{i+1}", "kind": "S"} for i in range(team.singles)]
    doubles = [{"label": f"D{i+1}", "kind": "D"} for i in range(team.doubles)]
    mixes = [{"label": f"M{i+1}", "kind": "M"} for i in range(team.mix)]

    rounds: list[list[dict]] = []
    for i in range(0, len(singles), 2):
        rounds.append(singles[i : i + 2])
    dm = doubles + mixes
    for i in range(0, len(dm), 2):
        rounds.append(dm[i : i + 2])

    # fallback voor inconsistente input
    planned = sum(len(r) for r in rounds)
    if planned < team.matches:
        for i in range(planned + 1, team.matches + 1):
            rounds.append([{"label": f"W{i}", "kind": "W"}])

    return rounds


def schedule_day(items: list[TeamDay], reservations: list[Reservation]) -> list[dict]:
    start_pref = 9 * 60  # liefst 09:00
    latest_start = 19 * 60 + 30
    step = 15
    courts = list(range(1, 11))

    court_busy: dict[int, list[tuple[int, int]]] = {c: [] for c in courts}
    team_busy: dict[str, list[tuple[int, int, str]]] = defaultdict(list)  # (s,e,kind)

    reserve_courts = set()
    kinds = {r.kind for r in reservations}
    if "oranje" in kinds:
        reserve_courts.update({1, 2, 3})
    elif "rood" in kinds:
        reserve_courts.update({1})
    for c in reserve_courts:
        court_busy[c].append((9 * 60, 11 * 60))

    out: list[dict] = []
    # meeste partijen eerst voor betere bezetting
    ordered = sorted(items, key=lambda t: t.matches, reverse=True)

    for team in ordered:
        rounds = build_rounds(team)
        tname = team.schema

        for rnd in rounds:
            needed = len(rnd)
            placed = False
            for start in range(start_pref, latest_start + 1, step):
                end = start + team.duration_min

                # team constraint: max 2 tegelijk
                team_overlaps = [b for b in team_busy[tname] if overlaps((start, end), (b[0], b[1]))]
                if len(team_overlaps) + needed > 2:
                    continue

                # team constraint: geen singles tegelijk met doubles/mix
                kinds_now = {x[2] for x in team_overlaps}
                round_kinds = {p["kind"] for p in rnd}
                if "S" in round_kinds and ({"D", "M"} & kinds_now):
                    continue
                if ({"D", "M"} & round_kinds) and ("S" in kinds_now):
                    continue

                free = []
                for c in courts:
                    if all(not overlaps((start, end), itv) for itv in court_busy[c]):
                        free.append(c)
                if len(free) < needed:
                    continue

                # Prioriteit: capaciteit benutten > naast elkaar spelen.
                # Kies beschikbare banen met meeste bestaande bezetting (compacter vullen).
                free.sort(key=lambda c: sum(b - a for a, b in court_busy[c]), reverse=True)
                best = free[:needed]
                for p, c in zip(rnd, best):
                    court_busy[c].append((start, end))
                    team_busy[tname].append((start, end, p["kind"]))
                    out.append(
                        {
                            "schema": tname,
                            "team_short": short_team_name(tname),
                            "part": p["label"],
                            "kind": p["kind"],
                            "start": mins_to_hhmm(start),
                            "end": mins_to_hhmm(end),
                            "court": c,
                        }
                    )
                placed = True
                break

            if not placed:
                for p in rnd:
                    out.append(
                        {
                            "schema": tname,
                            "team_short": short_team_name(tname),
                            "part": p["label"],
                            "kind": p["kind"],
                            "start": "NIET_GELUKT",
                            "end": "",
                            "court": None,
                        }
                    )

    return sorted(out, key=lambda x: (x["start"], x["court"] or 99, x["schema"], x["part"]))


def render_grid(rows: list[dict]) -> str:
    valid = [r for r in rows if r["start"] != "NIET_GELUKT"]
    if not valid:
        return "<p>Geen planbare wedstrijden.</p>"

    start_min = min(hhmm_to_mins(r["start"]) for r in valid)
    end_min = max(hhmm_to_mins(r["end"]) for r in valid)
    times = list(range(start_min, end_min + 1, 15))

    cell: dict[tuple[int, int], tuple[str, str]] = {}
    for r in valid:
        s = hhmm_to_mins(r["start"])
        e = hhmm_to_mins(r["end"])
        label = f"{r['team_short']} · {r['part']}"
        color = color_for(r["schema"])
        for t in range(s, e, 15):
            cell[(t, int(r["court"]))] = (label, color)

    header = "".join(f"<th>Baan {c}</th>" for c in range(1, 11))
    body = []
    for t in times[:-1]:
        tds = [f"<td class='time'>{mins_to_hhmm(t)}</td>"]
        for c in range(1, 11):
            v = cell.get((t, c))
            if v:
                txt, clr = v
                tds.append(f"<td style='background:{clr}'><div class='cell'>{html.escape(txt)}</div></td>")
            else:
                tds.append("<td class='empty'>—</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")

    return (
        "<div class='grid-wrap'><table class='grid'><thead><tr><th>Tijd</th>"
        + header
        + "</tr></thead><tbody>"
        + "".join(body)
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

    results: dict[str, list[dict]] = {}
    for d in sorted(by_date.keys(), key=lambda s: datetime.strptime(s, "%d-%m-%Y")):
        results[d] = schedule_day(by_date[d], reserve_by_date[d])

    (DOCS / "result.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    sections = []
    for d, rows in results.items():
        failed = [r for r in rows if r["start"] == "NIET_GELUKT"]
        failed_html = ""
        if failed:
            failed_html = "<p><strong>Niet gelukt:</strong> " + ", ".join(
                html.escape(f"{r['team_short']} {r['part']}") for r in failed
            ) + "</p>"
        sections.append(f"<h2>{html.escape(d)}</h2>{failed_html}{render_grid(rows)}")

    page = f"""<!doctype html>
<html lang='nl'>
<head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Baanschema Planner</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;max-width:1550px;margin:1.2rem auto;padding:0 1rem}}
.small{{color:#666}}
.grid-wrap{{overflow:auto;border:1px solid #eee;border-radius:10px;margin-bottom:2rem}}
.grid{{border-collapse:collapse;width:max-content;min-width:100%}}
.grid th,.grid td{{border:1px solid #ececec;padding:.35rem .45rem;vertical-align:top}}
.grid th{{position:sticky;top:0;background:#fafafa;z-index:2}}
.time{{font-variant-numeric:tabular-nums;background:#fcfcfc;position:sticky;left:0;z-index:1;min-width:58px}}
.empty{{color:#bbb;text-align:center;min-width:150px}}
.cell{{font-size:12px;line-height:1.2;max-width:230px}}
</style>
</head>
<body>
<h1>Baanschema Planner (per kwartier)</h1>
<p class='small'>Kolommen = banen, rijen = kwartierblokken. Cellen tonen team + partij (S1/D2/M1). Planner start zo vroeg mogelijk vanaf 09:00 en optimaliseert primair op maximale baanbezetting (naast-elkaar spelen is ondergeschikt).</p>
{''.join(sections)}
</body></html>"""
    (DOCS / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
