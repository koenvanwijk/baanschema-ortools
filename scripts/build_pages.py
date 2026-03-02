from __future__ import annotations

import csv
import hashlib
import html
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

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
    home_team: str
    away_team: str


@dataclass
class Reservation:
    date: str
    kind: str
    schema: str


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
                reservations.append(Reservation(date=date, kind="rood", schema=schema))
                continue
            if "oranje" in low:
                reservations.append(Reservation(date=date, kind="oranje", schema=schema))
                continue

            matches = _to_int(row.get("Wedstrijden") or "")
            duration = _to_int(row.get("Wedstrijdduur") or "")
            if not matches or not duration:
                continue

            team1 = (row.get("Team 1") or "").strip()
            team2 = (row.get("Team 2") or "").strip()
            team3 = (row.get("Team 3") or "").strip().upper()
            home_team = team1
            away_team = team2
            if team3 == "THUIS":
                if team1.upper().startswith("MIERLO"):
                    home_team, away_team = team1, team2
                elif team2.upper().startswith("MIERLO"):
                    home_team, away_team = team2, team1

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
                    home_team=home_team,
                    away_team=away_team,
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


_COLOR_CACHE: dict[str, str] = {}
_USED_HUES: list[int] = []


def _is_hue_far_enough(h: int, min_gap: int = 24) -> bool:
    return all(min((h - u) % 360, (u - h) % 360) >= min_gap for u in _USED_HUES)


def color_for(name: str) -> str:
    if name in _COLOR_CACHE:
        return _COLOR_CACHE[name]

    lname = name.lower()
    base_hue = None
    # Zelfde kleurfamilie voor Rood/Oranje/Groen, maar per team unieke tint
    if "rood" in lname:
        base_hue = 0
    elif "oranje" in lname:
        base_hue = 30
    elif "groen" in lname:
        base_hue = 125

    seed = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16)
    if base_hue is None:
        seed_hue = seed % 360
    else:
        seed_hue = (base_hue + (seed % 21) - 10) % 360

    hue = None
    for step in range(360):
        cand = (seed_hue + step * 37) % 360
        if _is_hue_far_enough(cand):
            hue = cand
            break
    if hue is None:
        hue = seed_hue

    _USED_HUES.append(hue)
    sat = 88 if base_hue is None else 82
    light = 70 if base_hue is None else 68
    color = f"hsl({hue} {sat}% {light}%)"
    _COLOR_CACHE[name] = color
    return color


def short_team_name(schema: str) -> str:
    s = schema
    s = s.replace("Jongens 13 t/m 17 jaar Zondag", "JO13-17")
    s = s.replace("Meisjes 13 t/m 17 jaar Zondag", "ME13-17")
    s = s.replace("Junioren 11 t/m 14 jaar Zondag", "JU11-14")
    s = s.replace("Gemengd Zondag", "GEM")
    s = s.replace("Heren Zondag", "HER")
    s = s.replace("Groen Zondag", "GRO")

    parts = [p.strip() for p in s.split("–")]
    if len(parts) >= 3:
        base = re.sub(r"\s*\([^)]*\)", "", parts[0]).strip()
        if base.startswith("GRO Groen"):
            base = base.replace("GRO Groen", "GRO", 1)
        klasse = re.sub(r"\s*\([^)]*\)", "", parts[1]).replace("klasse", "").strip()
        afdeling = parts[2].replace("Afdeling", "Afd").strip().replace("  ", " ")
        afdeling = afdeling.replace("Afd ", "Afd")
        return f"{base} {klasse} {afdeling}".strip()
    return parts[0][:20]


def build_rounds(team: TeamDay) -> list[list[dict]]:
    # Singles mogen NIET tegelijk met dubbels, maar WEL met mix.
    singles = [{"label": f"S{i+1}", "kind": "S"} for i in range(team.singles)]
    doubles = [{"label": f"D{i+1}", "kind": "D"} for i in range(team.doubles)]
    mixes = [{"label": f"M{i+1}", "kind": "M"} for i in range(team.mix)]

    rounds: list[list[dict]] = []

    # Fase 1: plan singles + mix samen (toegestaan)
    sm = singles + mixes
    for i in range(0, len(sm), 2):
        rounds.append(sm[i : i + 2])

    # Fase 2: plan dubbels apart (niet tegelijk met singles)
    for i in range(0, len(doubles), 2):
        rounds.append(doubles[i : i + 2])

    # fallback voor inconsistente input
    planned = sum(len(r) for r in rounds)
    if planned < team.matches:
        for i in range(planned + 1, team.matches + 1):
            rounds.append([{"label": f"W{i}", "kind": "W"}])

    return rounds


def schedule_day(items: list[TeamDay], reservations: list[Reservation], date: str) -> list[dict]:
    start_pref = 8 * 60 + 30  # optie 1: starten vanaf 08:30
    fallback_start = 8 * 60 + 30
    latest_start = 19 * 60 + 30
    first_match_latest = 15 * 60  # eerste teamwedstrijd mag niet na 15:00 starten
    first_match_latest_by_date = {
        "12-04-2026": 16 * 60,
        "19-04-2026": 17 * 60,
        "10-05-2026": 17 * 60,
        "17-05-2026": 18 * 60 + 30,
        "25-05-2026": 16 * 60,
    }
    step = 15  # starts op kwartieren
    courts = list(range(1, 11))

    court_busy: dict[int, list[tuple[int, int]]] = {c: [] for c in courts}
    team_busy: dict[str, list[tuple[int, int, str]]] = defaultdict(list)  # (s,e,kind)

    out: list[dict] = []

    # Plan en toon Rood/Oranje als expliciete blokken op de gereserveerde banen (09:00-11:00)
    for r in reservations:
        if r.kind == "oranje":
            reserve_courts = [1, 2, 3]
            label = "ORANJE"
            res_start, res_end = 9 * 60, 11 * 60
        elif r.kind == "rood":
            reserve_courts = [1]
            label = "ROOD"
            res_start, res_end = 9 * 60, 10 * 60  # rood duurt 1 uur
        else:
            reserve_courts = []
            label = r.kind.upper()
            res_start, res_end = 9 * 60, 11 * 60

        for c in reserve_courts:
            court_busy[c].append((res_start, res_end))
            out.append(
                {
                    "schema": r.schema,
                    "team_short": label,
                    "part": "COMP",
                    "kind": "R",
                    "start": mins_to_hhmm(res_start),
                    "end": mins_to_hhmm(res_end),
                    "court": c,
                }
            )
    # Basisvolgorde: jong -> oud (rood/oranje via reservaties), gemengd later
    def team_priority(t: TeamDay) -> tuple[int, int]:
        s = t.schema.lower()
        if "groen zondag" in s:
            p = 0
        elif "junioren 11 t/m 14" in s:
            p = 1
        elif "jongens 13 t/m 17" in s or "meisjes 13 t/m 17" in s:
            p = 2
        elif "gemengd zondag" in s:
            p = 3  # na JO/ME
        else:
            p = 4
        return (p, -t.matches)

    ordered = sorted(items, key=team_priority)

    def first_start_earliest(team: TeamDay) -> int:
        s = team.schema.lower()
        if "gemengd zondag" in s:
            return 10 * 60  # gemengd later laten starten
        if "jongens 13 t/m 17" in s or "meisjes 13 t/m 17" in s:
            return 9 * 60 + 15  # JO/ME actief vroeg proberen
        return fallback_start

    for team in ordered:
        rounds = build_rounds(team)
        tname = team.schema

        for idx, rnd in enumerate(rounds):
            needed = len(rnd)
            placed = False

            # liefst vanaf 09:00, alleen indien nodig terugvallen naar 08:30
            # eerste teampartij moet uiterlijk om 15:00 starten
            first_latest = first_match_latest_by_date.get(date, first_match_latest)
            latest_for_round = first_latest if idx == 0 else latest_start
            earliest_for_round = first_start_earliest(team) if "gemengd zondag" in team.schema.lower() else (first_start_earliest(team) if idx == 0 else fallback_start)
            candidate_starts = [
                range(max(start_pref, earliest_for_round), latest_for_round + 1, step),
                range(max(fallback_start, earliest_for_round), latest_for_round + 1, step),
            ]

            for start_range in candidate_starts:
                if placed:
                    break
                starts = list(start_range)
                starts.sort(
                    key=lambda s: (
                        -sum(1 for c in courts if any(overlaps((s, s + team.duration_min), itv) for itv in court_busy[c])),
                        s,
                    )
                )
                for start in starts:
                    end = start + team.duration_min

                    team_overlaps = [b for b in team_busy[tname] if overlaps((start, end), (b[0], b[1]))]

                    # team constraint: singles niet tegelijk met dubbels; mix mag wel met singles
                    kinds_now = {x[2] for x in team_overlaps}
                    round_kinds = {p["kind"] for p in rnd}
                    if "S" in round_kinds and ("D" in kinds_now):
                        continue
                    if "D" in round_kinds and ("S" in kinds_now):
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
                                "home_team": team.home_team,
                                "away_team": team.away_team,
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
                            "home_team": team.home_team,
                            "away_team": team.away_team,
                            "part": p["label"],
                            "kind": p["kind"],
                            "start": "NIET_GELUKT",
                            "end": "",
                            "court": None,
                        }
                    )

    return sorted(out, key=lambda x: (x["start"], x["court"] or 99, x["schema"], x["part"]))


def render_day_summary(rows: list[dict]) -> str:
    valid = [r for r in rows if r["start"] != "NIET_GELUKT"]
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in valid:
        if r.get("part") == "COMP":
            continue
        by_team[r["schema"]].append(r)

    if not by_team:
        return ""

    items = []
    for schema, rr in sorted(by_team.items(), key=lambda kv: min(hhmm_to_mins(x["start"]) for x in kv[1])):
        first_start = mins_to_hhmm(min(hhmm_to_mins(x["start"]) for x in rr))
        last_end = mins_to_hhmm(max(hhmm_to_mins(x["end"]) for x in rr))
        team_short = rr[0].get("team_short", short_team_name(schema))
        home = rr[0].get("home_team", "")
        away = rr[0].get("away_team", "")
        matchup = f"{home} vs {away}" if home or away else "-"
        items.append(
            f"<li><strong>{html.escape(team_short)}</strong> <span class='small'>( {html.escape(schema)} )</span>: {html.escape(matchup)} — eerste start <strong>{first_start}</strong>, laatste eind <strong>{last_end}</strong></li>"
        )

    return "<div class='summary'><h3>Teams vandaag</h3><ul>" + "".join(items) + "</ul></div>"


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
    blockers: list[str] = []
    for d in sorted(by_date.keys(), key=lambda s: datetime.strptime(s, "%d-%m-%Y")):
        day_rows = schedule_day(by_date[d], reserve_by_date[d], d)
        results[d] = day_rows
        failed = [r for r in day_rows if r["start"] == "NIET_GELUKT"]
        if failed:
            sample = ", ".join(f"{r['team_short']} {r['part']}" for r in failed[:5])
            blockers.append(f"{d}: {len(failed)} niet planbaar ({sample})")

    if blockers:
        raise RuntimeError(
            "Planning niet haalbaar; geen pagina gegenereerd. Bespreek keuze met planner:\n- "
            + "\n- ".join(blockers)
        )

    (DOCS / "result.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    sections = []
    for d, rows in results.items():
        failed = [r for r in rows if r["start"] == "NIET_GELUKT"]
        failed_html = ""
        if failed:
            failed_html = "<p><strong>Niet gelukt:</strong> " + ", ".join(
                html.escape(f"{r['team_short']} {r['part']}") for r in failed
            ) + "</p>"
        sections.append(f"<h2>{html.escape(d)}</h2>{failed_html}{render_day_summary(rows)}{render_grid(rows)}")

    page = f"""<!doctype html>
<html lang='nl'>
<head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Baanschema Planner</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;max-width:1550px;margin:1.2rem auto;padding:0 1rem}}
.small{{color:#666}}
.summary{{background:#fafafa;border:1px solid #eee;border-radius:10px;padding:.7rem .9rem;margin:.5rem 0 1rem 0}}
.summary h3{{margin:.2rem 0 .5rem 0;font-size:1rem}}
.summary ul{{margin:.2rem 0 .1rem 1.1rem;padding:0}}
.summary li{{margin:.25rem 0}}
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
<p class='small'>Kolommen = banen, rijen = kwartierblokken. Cellen tonen team + partij (S1/D2/M1). Startvoorkeur is 08:30. Eerste teamwedstrijd is normaal uiterlijk 15:00, met verruiming op kneldatums. Volgorde is jong naar oud; gemengde teams starten later (vanaf 10:00) waar mogelijk.</p>
{''.join(sections)}
</body></html>"""
    (DOCS / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
