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
import shutil
import subprocess
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
INPUT = ROOT / "data" / "season.tsv"


@dataclass
class TeamDay:
    date: str
    weekday: str
    schema: str
    team_id: str
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

            team_id = f"{date}::{schema}::{home_team}::{away_team}"
            teams.append(
                TeamDay(
                    date=date,
                    weekday=weekday,
                    schema=schema,
                    team_id=team_id,
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


def gap_penalty_with_existing(start: int, end: int, existing: list[tuple[int, int, str]]) -> int:
    if not existing:
        return 0
    intervals = sorted((s, e) for s, e, _k in existing)
    # als overlap/aanliggend met bestaande teamtijd -> geen extra gat
    for s, e in intervals:
        if not (end < s or start > e):
            return 0
        if end == s or start == e:
            return 0

    # anders: afstand tot dichtstbijzijnde bestaand interval als penalty
    distances = []
    for s, e in intervals:
        if end <= s:
            distances.append(s - end)
        elif start >= e:
            distances.append(start - e)
    return min(distances) if distances else 0


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
    sat = 92 if base_hue is None else 88
    light = 58 if base_hue is None else 56
    color = f"hsl({hue} {sat}% {light}%)"
    _COLOR_CACHE[name] = color
    return color


def short_team_name(schema: str, home_team: str = "") -> str:
    low = schema.lower()
    if "gemengd zondag" in low:
        prefix = "GEM"
    elif "heren zondag" in low:
        prefix = "HER"
    elif "groen zondag" in low:
        prefix = "GRO"
    elif "jongens 13 t/m 17" in low:
        prefix = "JO13-17"
    elif "meisjes 13 t/m 17" in low:
        prefix = "ME13-17"
    elif "junioren 11 t/m 14" in low:
        prefix = "JU11-14"
    else:
        prefix = schema.split("–", 1)[0].strip()[:20]

    parts = [p.strip() for p in schema.split("–")]
    klasse = ""
    if len(parts) >= 2:
        klasse = re.sub(r"\s*\([^)]*\)", "", parts[1])
        klasse = klasse.replace("klasse", "").strip()

    m = re.search(r"\bMIERLO\s*(\d+)\b", home_team or "", flags=re.I)
    home_short = f"M{m.group(1)}" if m else ""

    out = " ".join(x for x in [prefix, klasse, home_short] if x)
    return re.sub(r"\s+", " ", out).strip()


def match_player_demand(kind: str) -> int:
    if kind == "S":
        return 1
    if kind in {"D", "M"}:
        return 2
    return 0


def build_rounds(team: TeamDay) -> list[list[dict]]:
    # Singles moeten altijd vóór andere wedstrijden.
    # Singles mogen NIET tegelijk met dubbels, maar WEL met mix.
    singles = [{"label": f"S{i+1}", "kind": "S"} for i in range(team.singles)]
    doubles = [{"label": f"D{i+1}", "kind": "D"} for i in range(team.doubles)]
    mixes = [{"label": f"GD{i+1}", "kind": "M"} for i in range(team.mix)]

    rounds: list[list[dict]] = []

    for i in range(0, len(singles), 2):
        rounds.append(singles[i : i + 2])
    non_singles = doubles + mixes
    for i in range(0, len(non_singles), 2):
        rounds.append(non_singles[i : i + 2])

    # fallback voor inconsistente input
    planned = sum(len(r) for r in rounds)
    if planned < team.matches:
        for i in range(planned + 1, team.matches + 1):
            rounds.append([{"label": f"W{i}", "kind": "W"}])

    return rounds


def _schedule_day_with_start(
    items: list[TeamDay], reservations: list[Reservation], date: str, day_start_pref: int
) -> list[dict]:
    start_pref = day_start_pref
    fallback_start = 8 * 60 + 30
    latest_start = 19 * 60 + 30
    first_match_latest = 15 * 60  # eerste teamwedstrijd mag niet na 15:00 starten
    first_match_latest_by_date = {
        "06-04-2026": 16 * 60,
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
    team_courts: dict[str, set[int]] = defaultdict(set)

    out: list[dict] = []

    # Plan en toon Rood/Oranje als expliciete blokken op gereserveerde banen.
    # Regels:
    # - Rood altijd baan 1.
    # - Oranje bij voorkeur baan 1-3, tenzij Rood ook speelt: dan baan 2-4.
    kinds_today = {r.kind for r in reservations}
    for r in reservations:
        if r.kind == "oranje":
            reserve_courts = [2, 3, 4] if "rood" in kinds_today else [1, 2, 3]
            label = "ORANJE"
            res_start, res_end = day_start_pref, day_start_pref + 120
        elif r.kind == "rood":
            reserve_courts = [1]
            label = "ROOD"
            res_start, res_end = day_start_pref, day_start_pref + 60  # rood duurt 1 uur
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
        # Voorkeursvolgorde (zacht): jong -> oud
        # Rood/Oranje worden apart als reservatieblokken gepland.
        if "groen zondag" in s:
            p = 0
        elif "junioren 11 t/m 14" in s:
            p = 1
        elif "jongens 13 t/m 17" in s or "meisjes 13 t/m 17" in s:
            p = 2
        elif "gemengd zondag" in s:
            p = 3
        else:
            p = 4
        return (p, -t.matches)

    ordered = sorted(items, key=team_priority)

    def first_start_earliest(team: TeamDay) -> int:
        s = team.schema.lower()
        if "gemengd zondag" in s:
            return 10 * 60  # gemengd later laten starten
        if "jongens 13 t/m 17" in s or "meisjes 13 t/m 17" in s:
            return start_pref
        return start_pref

    for team in ordered:
        rounds = build_rounds(team)
        tname = team.team_id

        for idx, rnd in enumerate(rounds):
            remaining = list(rnd)

            while remaining:
                placed = False

                # liefst vanaf 09:00; eerste teampartij uiterlijk volgens datumregel
                first_latest = first_match_latest_by_date.get(date, first_match_latest)
                latest_for_round = first_latest if idx == 0 else latest_start
                earliest_for_round = first_start_earliest(team)
                candidate_starts = [
                    range(max(start_pref, earliest_for_round), latest_for_round + 1, step),
                ]

                for start_range in candidate_starts:
                    if placed:
                        break
                    starts = list(start_range)
                    starts.sort(
                        key=lambda s: (
                            -sum(1 for c in courts if any(overlaps((s, s + team.duration_min), itv) for itv in court_busy[c])),
                            -(s < 12 * 60) * sum(1 for c in courts if all(not overlaps((s, s + team.duration_min), itv) for itv in court_busy[c])),
                            gap_penalty_with_existing(s, s + team.duration_min, team_busy[tname]) // 15,
                            s,
                        )
                    )

                    for start in starts:
                        end = start + team.duration_min
                        team_overlaps = [b for b in team_busy[tname] if overlaps((start, end), (b[0], b[1]))]
                        kinds_now = {x[2] for x in team_overlaps}

                        free = [
                            c
                            for c in courts
                            if all(not overlaps((start, end), itv) for itv in court_busy[c])
                        ]
                        if not free:
                            continue

                        # Zo compact mogelijk: plan zoveel mogelijk uit de huidige ronde,
                        # maar laat ook 1 baan-start toe als dat eerder kan.
                        max_place = min(len(remaining), len(free))
                        chosen_parts = None
                        for take in range(max_place, 0, -1):
                            cand_parts = remaining[:take]
                            round_kinds = {p["kind"] for p in cand_parts}

                            # team constraints
                            if "S" in round_kinds and ("D" in kinds_now):
                                continue
                            if "D" in round_kinds and ("S" in kinds_now):
                                continue
                            if "M" in round_kinds and ("D" in kinds_now):
                                continue
                            if "D" in round_kinds and ("M" in kinds_now):
                                continue

                            schema_l = team.schema.lower()
                            if "2de-2he-dd-hd-2gd" in schema_l:
                                if "S" in round_kinds and ("M" in kinds_now):
                                    continue
                                if "M" in round_kinds and ("S" in kinds_now):
                                    continue

                            # Max 2 banen per team tegelijk.
                            if len(team_overlaps) + len(cand_parts) > 2:
                                continue

                            # Player-capacity constraint (4 spelers per team max tegelijk).
                            # Dit geldt voor alle teams behalve rood/oranje (die zitten in reservations).
                            players_now = sum(match_player_demand(k) for _s, _e, k in team_overlaps)
                            players_new = sum(match_player_demand(p["kind"]) for p in cand_parts)
                            if players_now + players_new > 4:
                                continue

                            chosen_parts = cand_parts
                            break

                        if not chosen_parts:
                            continue

                        def court_load(c: int) -> int:
                            return sum(b - a for a, b in court_busy[c])

                        def court_key(c: int) -> tuple:
                            same = c in team_courts[tname]
                            low = c <= 4
                            if int(team.matches or 0) == 8:
                                return (0 if same else 1, 0 if low else 1, -court_load(c), c)
                            return (0 if same else 1, -court_load(c), c)

                        free.sort(key=court_key)

                        if int(team.matches or 0) == 8:
                            low_free = [c for c in free if c <= 4]
                            if len(low_free) >= len(chosen_parts):
                                free = low_free + [c for c in free if c > 4]

                        best = free[: len(chosen_parts)]
                        for p, c in zip(chosen_parts, best):
                            court_busy[c].append((start, end))
                            team_busy[tname].append((start, end, p["kind"]))
                            team_courts[tname].add(c)
                            out.append(
                                {
                                    "schema": team.schema,
                                    "team_id": team.team_id,
                                    "team_short": short_team_name(team.schema, team.home_team),
                                    "home_team": team.home_team,
                                    "away_team": team.away_team,
                                    "part": p["label"],
                                    "kind": p["kind"],
                                    "matches": team.matches,
                                    "duration_min_cfg": team.duration_min,
                                    "start": mins_to_hhmm(start),
                                    "end": mins_to_hhmm(end),
                                    "court": c,
                                }
                            )

                        remaining = remaining[len(chosen_parts) :]
                        placed = True
                        break

                if not placed:
                    for p in remaining:
                        out.append(
                            {
                                "schema": team.schema,
                                "team_id": team.team_id,
                                "team_short": short_team_name(team.schema, team.home_team),
                                "home_team": team.home_team,
                                "away_team": team.away_team,
                                "part": p["label"],
                                "kind": p["kind"],
                                "matches": team.matches,
                                "duration_min_cfg": team.duration_min,
                                "start": "NIET_GELUKT",
                                "end": "",
                                "court": None,
                            }
                        )
                    break

    # Post-pass: compacteer planning door partijen waar mogelijk per 15 minuten naar voren te schuiven.
    min_start_compact = start_pref

    def can_move(row: dict, new_start: int, duration: int) -> bool:
        new_end = new_start + duration

        # startgrenzen
        if new_start < min_start_compact:
            return False
        if "gemengd zondag" in row["schema"].lower() and new_start < 10 * 60:
            return False

        for other in out:
            if other is row:
                continue
            if other.get("start") in (None, "", "NIET_GELUKT"):
                continue
            os = hhmm_to_mins(other["start"])
            oe = hhmm_to_mins(other["end"])

            # zelfde baan mag niet overlappen
            if other.get("court") == row.get("court") and overlaps((new_start, new_end), (os, oe)):
                return False

            # teamregels binnen zelfde team tijdens compaction
            if other.get("team_id") == row.get("team_id") and overlaps((new_start, new_end), (os, oe)):
                rk = row.get("kind")
                ok = other.get("kind")

                # S en D niet tegelijk
                if rk == "S" and ok == "D":
                    return False
                if rk == "D" and ok == "S":
                    return False

                # D en GD(M) niet tegelijk
                if rk == "D" and ok == "M":
                    return False
                if rk == "M" and ok == "D":
                    return False

                # Voor 2DE-2HE-DD-HD-2GD: ook S en GD niet tegelijk
                schema_l = (row.get("schema") or "").lower()
                if "2de-2he-dd-hd-2gd" in schema_l:
                    if rk == "S" and ok == "M":
                        return False
                    if rk == "M" and ok == "S":
                        return False

        return True

    movable = [r for r in out if r.get("part") != "COMP" and r.get("start") not in (None, "", "NIET_GELUKT")]
    improved = True
    while improved:
        improved = False
        for row in sorted(movable, key=lambda r: hhmm_to_mins(r["start"])):
            cur_start = hhmm_to_mins(row["start"])
            cur_end = hhmm_to_mins(row["end"])
            dur = cur_end - cur_start
            trial = cur_start - 15
            while trial >= min_start_compact:
                if can_move(row, trial, dur):
                    row["start"] = mins_to_hhmm(trial)
                    row["end"] = mins_to_hhmm(trial + dur)
                    cur_start = trial
                    trial -= 15
                    improved = True
                else:
                    break

    return sorted(out, key=lambda x: (x["start"], x["court"] or 99, x["schema"], x["part"]))


def schedule_day(items: list[TeamDay], reservations: list[Reservation], date: str) -> list[dict]:
    # Regel: start op 09:00, behalve als dat ertoe leidt dat partijen pas na 19:30 moeten starten
    # of onplanbaar worden. Dan fallback naar 08:30.
    rows_0900 = _schedule_day_with_start(items, reservations, date, day_start_pref=9 * 60)
    valid_0900 = [r for r in rows_0900 if r.get("start") not in (None, "", "NIET_GELUKT") and r.get("part") != "COMP"]
    failed_0900 = [r for r in rows_0900 if r.get("start") == "NIET_GELUKT" and r.get("part") != "COMP"]
    if valid_0900 and not failed_0900:
        last_start_0900 = max(hhmm_to_mins(r["start"]) for r in valid_0900)
        if last_start_0900 <= 19 * 60 + 30:
            return rows_0900

    return _schedule_day_with_start(items, reservations, date, day_start_pref=8 * 60 + 30)


def render_day_summary(rows: list[dict], include_reservations: bool = False) -> str:
    valid = [r for r in rows if r["start"] != "NIET_GELUKT"]
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in valid:
        if r.get("part") == "COMP" and not include_reservations:
            continue
        by_team[r.get("team_id") or r["schema"]].append(r)

    if not by_team:
        return ""

    items = []
    for _team_id, rr in sorted(by_team.items(), key=lambda kv: min(hhmm_to_mins(x["start"]) for x in kv[1])):
        rr_noncomp = [x for x in rr if x.get("part") != "COMP"]
        rr_for_times = rr_noncomp or rr
        rr_for_stats = rr_noncomp or rr
        schema_name = rr[0].get("schema", "")
        first_start = mins_to_hhmm(min(hhmm_to_mins(x["start"]) for x in rr_for_times))
        last_end = mins_to_hhmm(max(hhmm_to_mins(x["end"]) for x in rr_for_times))
        team_short = rr[0].get("team_short", short_team_name(schema_name))
        home = rr_for_stats[0].get("home_team", "")
        away = rr_for_stats[0].get("away_team", "")
        matchup = f"{home} vs {away}" if home or away else "-"
        planned = len(rr_for_stats)
        target = int(rr_for_stats[0].get("matches") or planned)
        color = color_for(rr[0].get("team_id") or schema_name)
        items.append(
            f"<li><span class='team-swatch' style='background:{color}'></span><strong>{html.escape(team_short)}</strong> <span class='small'>( {html.escape(schema_name)} )</span>: {html.escape(matchup)} — wedstrijden <strong>{planned}/{target}</strong> — eerste start <strong>{first_start}</strong>, laatste eind <strong>{last_end}</strong></li>"
        )

    return "<div class='summary'><h3>Teams vandaag</h3><ul>" + "".join(items) + "</ul></div>"


def compute_kpis(rows: list[dict]) -> dict:
    valid = [r for r in rows if r.get("start") not in (None, "", "NIET_GELUKT") and r.get("part") != "COMP"]
    if not valid:
        return {"morning": 0, "total": 0, "long_gaps": 0, "violations": 0}

    # court occupancy ratio
    court_slots_total = 0
    court_slots_used = 0
    for t in range(8 * 60 + 30, 20 * 60, 15):
        for c in range(1, 11):
            court_slots_total += 1
            if any(r.get("court") == c and hhmm_to_mins(r["start"]) <= t < hhmm_to_mins(r["end"]) for r in valid):
                court_slots_used += 1

    morning_total = 0
    morning_used = 0
    for t in range(8 * 60 + 30, 12 * 60, 15):
        for c in range(1, 11):
            morning_total += 1
            if any(r.get("court") == c and hhmm_to_mins(r["start"]) <= t < hhmm_to_mins(r["end"]) for r in valid):
                morning_used += 1

    # teams with long gaps > 60 min
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in valid:
        by_team[r.get("team_id") or r["schema"]].append(r)
    long_gaps = 0
    for _schema, rr in by_team.items():
        st = min(hhmm_to_mins(x["start"]) for x in rr)
        en = max(hhmm_to_mins(x["end"]) for x in rr)
        occupied = 0
        for t in range(st, en, 15):
            if any(hhmm_to_mins(x["start"]) <= t < hhmm_to_mins(x["end"]) for x in rr):
                occupied += 15
        idle = (en - st) - occupied
        if idle > 60:
            long_gaps += 1

    return {
        "morning": round(100 * morning_used / max(1, morning_total), 1),
        "total": round(100 * court_slots_used / max(1, court_slots_total), 1),
        "long_gaps": long_gaps,
        "violations": len(evaluate_day_rule_violations(rows)),
    }


def render_kpi_compare(heur_rows: list[dict], ort_rows: list[dict]) -> str:
    h = compute_kpis(heur_rows)
    o = compute_kpis(ort_rows) if ort_rows else None
    if not o:
        return "<div class='kpi'><strong>KPI</strong>: OR-Tools nog niet beschikbaar voor vergelijking.</div>"

    # simpele score voor dagwinnaar
    h_score = h['morning'] + h['total'] - 5 * h['long_gaps'] - 3 * h['violations']
    o_score = o['morning'] + o['total'] - 5 * o['long_gaps'] - 3 * o['violations']
    winner = "OR-Tools" if o_score > h_score else "Heuristiek"

    return (
        "<div class='kpi'><strong>KPI Heuristiek vs OR-Tools</strong>"
        f" <span class='small'>(dagwinnaar: <strong>{winner}</strong>)</span>"
        f"<ul><li>Ochtendbezetting: {h['morning']}% vs {o['morning']}%</li>"
        f"<li>Totale bezetting: {h['total']}% vs {o['total']}%</li>"
        f"<li>Teams met >60 min gat: {h['long_gaps']} vs {o['long_gaps']}</li>"
        f"<li>Aantal regelafwijkingen: {h['violations']} vs {o['violations']}</li></ul></div>"
    )


def render_grid(rows: list[dict]) -> str:
    valid = [r for r in rows if r["start"] != "NIET_GELUKT"]
    if not valid:
        return "<p>Geen planbare wedstrijden.</p>"

    start_min = min(hhmm_to_mins(r["start"]) for r in valid)
    end_min = max(hhmm_to_mins(r["end"]) for r in valid)
    times = list(range(start_min, end_min + 1, 15))

    cell: dict[tuple[int, int], dict[str, Any]] = {}
    for r in valid:
        s = hhmm_to_mins(r["start"])
        e = hhmm_to_mins(r["end"])
        label = f"{r['team_short']} · {r['part']}"
        away = r.get("away_team", "")
        if away:
            label = f"{r['team_short']} · {r['part']} vs {away}"
        detail = f"{r['schema']} | {r['part']} | {r['start']}-{r['end']} | Baan {r.get('court','?')}" + (f" | vs {away}" if away else "")
        color = color_for(r.get("team_id") or r["schema"])
        for t in range(s, e, 15):
            cell[(t, int(r["court"]))] = {
                "label": label,
                "detail": detail,
                "color": color,
                "is_start": t == s,
            }

    header = "".join(f"<th>Baan {c}</th>" for c in range(1, 11))
    body = []
    major_anchor = start_min
    for t in times[:-1]:
        row_cls = "major-row" if ((t - major_anchor) % 90 == 0) else ""
        tds = [f"<td class='time'>{mins_to_hhmm(t)}</td>"]
        for c in range(1, 11):
            v = cell.get((t, c))
            if v:
                txt = v["label"] if v["is_start"] else "·"
                clr = v["color"]
                detail = html.escape(v["detail"], quote=True)
                tds.append(
                    f"<td class='tap-cell' style='background:{clr}' data-detail='{detail}'><div class='cell'>{html.escape(txt)}</div></td>"
                )
            else:
                tds.append("<td class='empty'>—</td>")
        body.append(f"<tr class='{row_cls}'>" + "".join(tds) + "</tr>")

    return (
        "<div class='grid-wrap'><table class='grid'><thead><tr><th>Tijd</th>"
        + header
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )


def assert_no_double_mix_overlap(rows: list[dict], day_label: str) -> None:
    valid = [r for r in rows if r.get("start") not in (None, "", "NIET_GELUKT") and r.get("part") != "COMP"]
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in valid:
        by_team[r.get("team_id") or r["schema"]].append(r)

    for team_key, rr in by_team.items():
        for t in range(8 * 60 + 30, 20 * 60, 15):
            has_d = any(x.get("kind") == "D" and hhmm_to_mins(x["start"]) <= t < hhmm_to_mins(x["end"]) for x in rr)
            has_m = any(x.get("kind") == "M" and hhmm_to_mins(x["start"]) <= t < hhmm_to_mins(x["end"]) for x in rr)
            if has_d and has_m:
                raise RuntimeError(
                    f"Regelbreuk: D en GD tegelijk voor team '{rr[0].get('schema', team_key)}' op {day_label} rond {mins_to_hhmm(t)}"
                )


def evaluate_day_rule_violations(rows: list[dict]) -> list[str]:
    valid = [r for r in rows if r.get("start") not in (None, "", "NIET_GELUKT", "__ORT_SOLVED__") and r.get("part") != "COMP"]
    violations: list[str] = []

    failed = [r for r in rows if r.get("start") == "NIET_GELUKT" and r.get("part") != "COMP"]
    if failed:
        sample = ", ".join(f"{r.get('team_short','?')} {r.get('part','?')}" for r in failed[:6])
        violations.append(f"[ROOD] Niet planbaar: {len(failed)} partijen ({sample}).")

    if not valid:
        return violations

    # 1) Kwartierstarts zijn toegestaan (geen penalty).

    # 2) Eerste teamstart binnen 08:30-16:30 (volgens verduidelijking)
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in valid:
        by_team[r.get("team_id") or r["schema"]].append(r)

    first_start_out_of_window = 0
    late_junior = 0
    late_gem8 = 0
    too_late_last_start = 0

    for _team_key, rr in by_team.items():
        schema_name = rr[0].get("schema", "")
        first_start = min(hhmm_to_mins(x["start"]) for x in rr)
        last_start = max(hhmm_to_mins(x["start"]) for x in rr)
        if first_start < 8 * 60 + 30 or first_start > 16 * 60 + 30:
            first_start_out_of_window += 1
        if "junioren" in schema_name.lower() and first_start > 12 * 60:
            late_junior += 1
        if "gemengd zondag" in schema_name.lower() and int(rr[0].get("matches") or 0) == 8 and first_start > 14 * 60:
            late_gem8 += 1
        if last_start > 19 * 60 + 30:
            too_late_last_start += 1

    if first_start_out_of_window:
        violations.append(f"[HARD] Eerste teamstart buiten 08:30–16:30: {first_start_out_of_window} teams.")
    if late_junior:
        violations.append(f"[SOFT] Junioren eerste start na 12:00 (capaciteitsuitzondering nodig): {late_junior} teams.")
    if late_gem8:
        violations.append(f"[HARD] Gemengd 8-partijen eerste start na 14:00: {late_gem8} teams.")
    if too_late_last_start:
        violations.append(f"[HARD] Laatste partijstart na 19:30: {too_late_last_start} teams.")

    return violations


def render_rule_violations(violations: list[str]) -> str:
    if not violations:
        return ""
    items = "".join(f"<li>{html.escape(v)}</li>" for v in violations)
    return f"<div class='violations'><strong>Niet-gehaalde regels op deze dag</strong><ul>{items}</ul></div>"


def compute_ortools_results(dates: list[str], team_lookup: dict[str, TeamDay]) -> tuple[dict[str, list[dict]], dict]:
    status: dict = {"ortools_available": importlib.util.find_spec("ortools") is not None, "runs": {}}
    if not status["ortools_available"]:
        # Niet-blocking: pagina blijft bruikbaar met alleen heuristiek.
        return {d: [] for d in dates}, status

    out: dict[str, list[dict]] = {}
    for d in dates:
        out_path = DOCS / f"ortools_{d}.json"
        # If the output file already exists, skip re-running the planner.
        if out_path.exists():
            status["runs"][d] = {"returncode": 0, "stdout": "(cached)", "stderr": "", "out_exists": True}
        else:
            cmd = [
                sys.executable,
                str(ROOT / "scripts" / "ortools_planner.py"),
                "--date",
                d,
                "--time-limit",
                "180",
                "--out",
                str(out_path),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            status["runs"][d] = {
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-400:],
                "stderr": (proc.stderr or "")[-400:],
                "out_exists": out_path.exists(),
            }
        if status["runs"][d].get("returncode", 0) != 0 or not out_path.exists():
            out[d] = []
            continue

        raw = json.loads(out_path.read_text(encoding="utf-8"))
        rows = []
        for r in raw.get("rows", []):
            schema = r.get("team", "")
            team_id = f"{d}::{schema}"
            # Best effort lookup (may be empty when same schema occurs multiple times)
            t = next((tv for k, tv in team_lookup.items() if k.startswith(f"{d}::{schema}::")), None)
            rows.append(
                {
                    "schema": schema,
                    "team_id": team_id,
                    "team_short": short_team_name(schema, t.home_team if t else ""),
                    "home_team": t.home_team if t else "",
                    "away_team": t.away_team if t else "",
                    "part": r.get("part", ""),
                    "kind": r.get("kind", ""),
                    "matches": t.matches if t else 0,
                    "duration_min_cfg": t.duration_min if t else 0,
                    "start": r.get("start", "NIET_GELUKT"),
                    "end": r.get("end", ""),
                    "court": r.get("court"),
                }
            )
        out[d] = rows
    return out, status


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    teams, reserves = parse_input(INPUT)

    by_date: dict[str, list[TeamDay]] = defaultdict(list)
    reserve_by_date: dict[str, list[Reservation]] = defaultdict(list)

    for t in teams:
        by_date[t.date].append(t)
    for r in reserves:
        reserve_by_date[r.date].append(r)

    team_lookup: dict[str, TeamDay] = {}
    team_short_lookup: dict[str, TeamDay] = {}  # "date::team_short" → TeamDay
    for d, ts in by_date.items():
        for t in ts:
            team_lookup[f"{d}::{t.schema}::{t.home_team}::{t.away_team}"] = t
            short = short_team_name(t.schema, t.home_team)
            team_short_lookup[f"{d}::{short}"] = t

    ordered_dates = sorted(by_date.keys(), key=lambda s: datetime.strptime(s, "%d-%m-%Y"))

    results: dict[str, list[dict]] = {}
    for d in ordered_dates:
        day_rows = schedule_day(by_date[d], reserve_by_date[d], d)
        assert_no_double_mix_overlap(day_rows, d)
        results[d] = day_rows

    ortools_results, ortools_status = compute_ortools_results(ordered_dates, team_lookup)

    # Gold (handmatige referentie) inlezen indien aanwezig
    gold_results: dict[str, list[dict]] = {}
    gold_path = DOCS / "gold_result.json"
    if gold_path.exists():
        try:
            raw_gold = json.loads(gold_path.read_text(encoding="utf-8"))
            if isinstance(raw_gold, dict):
                for gd, rows in raw_gold.items():
                    norm = []
                    for r in rows or []:
                        if not isinstance(r, dict):
                            continue
                        start = r.get("start")
                        end = r.get("end")
                        if not start or not end:
                            continue
                        ts = r.get("team_short") or ""
                        schema_key = r.get("schema") or ts
                        # Enrich away_team from team_lookup if not already present in gold data
                        away_from_gold = r.get("away_team") or ""
                        if not away_from_gold:
                            t_lu = next((tv for k, tv in team_lookup.items() if k.startswith(f"{gd}::{schema_key}::")), None)
                            if not t_lu:
                                t_lu = team_short_lookup.get(f"{gd}::{ts}")
                            away_from_gold = t_lu.away_team if t_lu else ""
                        home_from_gold = r.get("home_team") or ""
                        if not home_from_gold:
                            t_lu2 = next((tv for k, tv in team_lookup.items() if k.startswith(f"{gd}::{schema_key}::")), None)
                            if not t_lu2:
                                t_lu2 = team_short_lookup.get(f"{gd}::{ts}")
                            home_from_gold = t_lu2.home_team if t_lu2 else ""
                        norm.append(
                            {
                                "schema": schema_key,
                                "team_id": r.get("team_id") or ts,
                                "team_short": ts,
                                "home_team": home_from_gold,
                                "away_team": away_from_gold,
                                "part": r.get("part") or "",
                                "kind": r.get("kind") or "W",
                                "matches": r.get("matches") or 0,
                                "duration_min_cfg": r.get("duration_min_cfg") or 0,
                                "start": start,
                                "end": end,
                                "court": int(r.get("court") or 0),
                            }
                        )
                    gold_results[gd] = norm
        except Exception:
            gold_results = {}

    # Niet-blocking: OR-Tools mag ontbreken/mislukken; heuristiekpagina blijft beschikbaar.

    (DOCS / "result.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    (DOCS / "ortools_result.json").write_text(json.dumps(ortools_results, indent=2, ensure_ascii=False), encoding="utf-8")
    (DOCS / "ortools_status.json").write_text(json.dumps(ortools_status, indent=2, ensure_ascii=False), encoding="utf-8")

    # opponents.json: { "schema::datum": "tegenstander" } — voor gebruik in editor en andere views
    opponents: dict[str, str] = {}
    for t in teams:
        if t.away_team:
            opponents[f"{t.schema}::{t.date}"] = t.away_team
    (DOCS / "opponents.json").write_text(json.dumps(opponents, indent=2, ensure_ascii=False), encoding="utf-8")

    def reservation_rows_for_date(d: str) -> list[dict]:
        out = []
        day_res = reserve_by_date.get(d, [])
        kinds = {r.kind for r in day_res}
        for r in day_res:
            if r.kind == "oranje":
                courts, start, end, label = ([2, 3, 4] if "rood" in kinds else [1, 2, 3]), "09:00", "11:00", "ORANJE"
            elif r.kind == "rood":
                courts, start, end, label = [1], "09:00", "10:00", "ROOD"
            else:
                courts, start, end, label = [], "09:00", "11:00", r.kind.upper()
            for c in courts:
                out.append(
                    {
                        "schema": r.schema,
                        "team_short": label,
                        "home_team": "",
                        "away_team": "",
                        "part": "COMP",
                        "kind": "R",
                        "matches": 0,
                        "duration_min_cfg": 0,
                        "start": start,
                        "end": end,
                        "court": c,
                    }
                )
        return out

    sections = []
    for d, rows in results.items():
        failed = [r for r in rows if r["start"] == "NIET_GELUKT"]
        failed_html = ""
        if failed:
            failed_html = "<p><strong>Niet gelukt:</strong> " + ", ".join(
                html.escape(f"{r['team_short']} {r['part']}") for r in failed
            ) + "</p>"
        # Compute heuristic violations, but suppress ROOD "Niet planbaar" for teams
        # that were successfully scheduled by OR-Tools (false positive prevention).
        ort_day_rows = ortools_results.get(d, [])
        ort_scheduled_keys = {(r.get("team_short"), r.get("part")) for r in ort_day_rows if r.get("start") not in (None, "", "NIET_GELUKT")}
        # For violations check: mask NIET_GELUKT rows that OR-Tools solved (so no false ROOD)
        rows_for_violations = [
            r if not (r.get("start") == "NIET_GELUKT" and (r.get("team_short"), r.get("part")) in ort_scheduled_keys)
            else {**r, "start": "__ORT_SOLVED__"}  # suppress from NIET_GELUKT count; excluded from valid processing
            for r in rows
        ]
        violations = evaluate_day_rule_violations(rows_for_violations)
        ort_rows = reservation_rows_for_date(d) + ort_day_rows
        if ort_rows:
            assert_no_double_mix_overlap(ort_rows, f"{d} (OR)")
        run_info = (ortools_status.get("runs") or {}).get(d, {})
        if ort_rows:
            ort_block = render_day_summary(ort_rows) + render_grid(ort_rows)
        else:
            why = "OR-Tools resultaat nog niet beschikbaar in deze run."
            if not ortools_status.get("ortools_available", False):
                why = "OR-Tools package niet beschikbaar in deze build-runtime."
            elif run_info:
                rc = run_info.get("returncode")
                err = (run_info.get("stderr") or "").strip()
                out = (run_info.get("stdout") or "").strip()
                tail = err or out
                why = f"OR-Tools run gaf geen resultaat (returncode={rc})."
                if tail:
                    why += f" Laatste melding: {tail[-180:]}"
            ort_block = f"<div class='ort-status-inline'>{html.escape(why)}</div>"
        gold_rows = reservation_rows_for_date(d) + gold_results.get(d, [])
        gold_block = (render_day_summary(gold_rows, include_reservations=True) + render_grid(gold_rows)) if gold_rows else "<div class='ort-status-inline'>Gold-referentie niet beschikbaar voor deze datum.</div>"
        sections.append(
            f"<h2>{html.escape(d)}</h2>{failed_html}{render_rule_violations(violations)}{render_kpi_compare(rows, ort_rows)}"
            f"<div class='plan-view heur-view'>{render_day_summary(rows)}{render_grid(rows)}</div>"
            f"<div class='plan-view ort-view hidden'>{ort_block}</div>"
            f"<div class='plan-view gold-view hidden' data-date='{html.escape(d)}'>{gold_block}</div>"
        )

    ort_ok_count = sum(1 for v in ortools_results.values() if v)
    ort_total = len(ordered_dates)
    ort_msg = (
        f"OR-Tools runs met resultaat: {ort_ok_count}/{ort_total}."
        if ortools_status.get("ortools_available", False)
        else "OR-Tools niet beschikbaar in deze runtime; OR-view kan leeg zijn."
    )

    page = f"""<!doctype html>
<html lang='nl'>
<head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<meta http-equiv='Cache-Control' content='no-cache, no-store, must-revalidate'>
<meta http-equiv='Pragma' content='no-cache'>
<meta http-equiv='Expires' content='0'>
<title>Baanschemaatje</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;max-width:1550px;margin:1.2rem auto;padding:0 1rem}}
.small{{color:#666}}
.summary{{background:#fafafa;border:1px solid #eee;border-radius:10px;padding:.7rem .9rem;margin:.5rem 0 1rem 0}}
.summary h3{{margin:.2rem 0 .5rem 0;font-size:1rem}}
.summary ul{{margin:.2rem 0 .1rem 1.1rem;padding:0}}
.summary li{{margin:.25rem 0}}
.team-swatch{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:.35rem;vertical-align:middle;border:1px solid rgba(0,0,0,.15)}}
.requirements{{background:#f7f9ff;border:1px solid #d9e2ff;border-radius:10px;padding:.75rem .95rem;margin:.8rem 0 1rem 0}}
.requirements h3{{margin:.2rem 0 .5rem 0;font-size:1rem}}
.requirements ul{{margin:.2rem 0 .1rem 1.1rem;padding:0}}
.violations{{background:#fff6bf;border:1px solid #e6cc55;border-radius:10px;padding:.65rem .85rem;margin:.4rem 0 .8rem 0}}
.violations ul{{margin:.35rem 0 .1rem 1.1rem;padding:0}}
.kpi{{background:#eefaf1;border:1px solid #b6e3c1;border-radius:10px;padding:.6rem .8rem;margin:.4rem 0 .8rem 0}}
.kpi ul{{margin:.35rem 0 .1rem 1.1rem;padding:0}}
.toggle{{display:flex;gap:.5rem;margin:.6rem 0 1rem 0}}
.toggle button{{border:1px solid #ccc;background:#fff;padding:.35rem .6rem;border-radius:8px;cursor:pointer}}
.toggle button.active{{background:#111;color:#fff;border-color:#111}}
.ort-status{{background:#f3f6ff;border:1px solid #c8d4ff;border-radius:10px;padding:.55rem .75rem;margin:.45rem 0 .8rem 0;font-size:12px;color:#223}}
.ort-status-inline{{background:#f7f7f7;border:1px solid #ddd;border-radius:10px;padding:.55rem .75rem;margin:.2rem 0 1rem 0;font-size:12px;color:#333}}
.hidden{{display:none}}
.grid-wrap{{overflow:auto;border:1px solid #eee;border-radius:10px;margin-bottom:2rem}}
.grid{{border-collapse:collapse;width:100%;table-layout:fixed}}
.grid th,.grid td{{border:1px solid #dcdfe6;padding:.2rem .25rem;vertical-align:middle;height:30px;min-height:30px;box-sizing:border-box}}
.grid tr.major-row td{{border-top:3px solid #8f97a8}}
.grid th{{position:sticky;top:0;background:#fafafa;z-index:2;font-size:12px}}
.time{{font-variant-numeric:tabular-nums;background:#f3f4f7;position:sticky;left:0;z-index:1;width:56px;min-width:56px;max-width:56px;font-size:11px;font-weight:600}}
.empty{{color:#aeb4c2;text-align:center}}
.cell{{font-size:10px;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#111;font-weight:600}}
.tap-cell{{cursor:pointer}}
.modal-backdrop{{position:fixed;inset:0;background:rgba(0,0,0,.45);display:none;align-items:center;justify-content:center;z-index:20}}
.modal{{background:#fff;border-radius:12px;max-width:92vw;padding:.9rem 1rem;box-shadow:0 10px 30px rgba(0,0,0,.25)}}
@media (max-width: 800px){{
  .grid th,.grid td{{padding:.12rem .14rem;height:24px;min-height:24px}}
  .cell{{font-size:9px}}
}}
</style>
</head>
<body>
<h1>Baanschemaatje (per kwartier)</h1>
<p class='small'>Kolommen = banen, rijen = kwartierblokken. Cellen tonen team + partij (S1/D2/GD1). Startvoorkeur is 08:30. Eerste teamwedstrijd is normaal uiterlijk 15:00, met verruiming op kneldatums. Volgorde is jong naar oud; gemengde teams starten later (vanaf 10:00) waar mogelijk.</p>
<div class='requirements'>
  <h3>Planningsregels (actueel)</h3>
  <ul>
    <li>10 banen totaal; Rood reserveert altijd baan 1 (08:30–09:30). Oranje reserveert bij voorkeur baan 1–3 (08:30–10:30), tenzij Rood ook speelt: dan baan 2–4.</li>
    <li>Teams spelen partijen met labels S / D / GD; singles niet tegelijk met dubbels, singles wel met GD.</li>
    <li>Als een team met 1–2 banen kan starten: begin met dubbels/GD; bij 3–4 banen: begin met singles.</li>
    <li>Startvenster: planner probeert 09:00 als dagstart en valt terug op 08:30 wanneer nodig; eerste teamwedstrijd normaal uiterlijk 15:00 (met datum-specifieke verruiming waar nodig).</li>
    <li>Gemengd Zondag start bij voorkeur later (vanaf 10:00), jeugd eerder.</li>
    <li>Doel: hoge baanbezetting + zo min mogelijk gaten binnen teamplanning.</li>
    <li>KNLTB-tekstregels worden hieronder per dag gecontroleerd; afwijkingen staan geel gemarkeerd.</li>
    <li>OR-Tools debugstatus: <code>ortools_status.json</code> (laat zien of de OR-Tools run echt is uitgevoerd).</li>
  </ul>
</div>
<div class='ort-status'>{html.escape(ort_msg)}</div>
<div class='toggle'>
  <button id='btn-heur' onclick='setPlan("heur")'>Heuristiek</button>
  <button id='btn-ort' onclick='setPlan("ort")'>OR-Tools</button>
  <button id='btn-gold' class='active' onclick='setPlan("gold")'>Gold</button>
  <a href='editor.html?plan=gold' id='link-bewerk-gold'><button style='background:#7c3aed;color:#fff;border:none;padding:.35rem .8rem;border-radius:4px;cursor:pointer;font-weight:600'>📝 Bewerk Gold</button></a>
  <a href='editor.html'><button style='background:#7c3aed;color:#fff;border:none;padding:.35rem .8rem;border-radius:4px;cursor:pointer;font-weight:600'>✏️ Editor</button></a>
  <a href='./replan.html' style='margin-left:.5rem;align-self:center'>Open wedstrijddag herplanning →</a>
</div>
{''.join(sections)}
<div id='cellModalBg' class='modal-backdrop' onclick='closeCellModal()'>
  <div class='modal' onclick='event.stopPropagation()'>
    <strong>Wedstrijddetail</strong>
    <div id='cellModalText' style='margin-top:.4rem;white-space:pre-wrap'></div>
    <div style='margin-top:.7rem'><button onclick='closeCellModal()'>Sluiten</button></div>
  </div>
</div>
<script>
function setPlan(mode){{
  const heur = document.querySelectorAll('.heur-view');
  const ort = document.querySelectorAll('.ort-view');
  const gold = document.querySelectorAll('.gold-view');
  const bh = document.getElementById('btn-heur');
  const bo = document.getElementById('btn-ort');
  const bg = document.getElementById('btn-gold');

  heur.forEach(e=>e.classList.add('hidden'));
  ort.forEach(e=>e.classList.add('hidden'));
  gold.forEach(e=>e.classList.add('hidden'));
  bh.classList.remove('active');
  bo.classList.remove('active');
  if(bg) bg.classList.remove('active');

  if(mode==='ort'){{
    ort.forEach(e=>e.classList.remove('hidden'));
    bo.classList.add('active');
  }} else if (mode==='heur') {{
    heur.forEach(e=>e.classList.remove('hidden'));
    bh.classList.add('active');
  }} else {{
    gold.forEach(e=>e.classList.remove('hidden'));
    if(bg) bg.classList.add('active');
    if(typeof applyLocalEdits === 'function') applyLocalEdits();
  }}
  bindCellPopups();
}}
function bindCellPopups(){{
  document.querySelectorAll('.tap-cell').forEach(el=>{{
    if(el.dataset.bound==='1') return;
    el.dataset.bound='1';
    el.addEventListener('click',()=>openCellModal(el.dataset.detail||''));
  }});
}}
function openCellModal(text){{
  const bg=document.getElementById('cellModalBg');
  const t=document.getElementById('cellModalText');
  if(t) t.textContent=text;
  if(bg) bg.style.display='flex';
}}
function closeCellModal(){{
  const bg=document.getElementById('cellModalBg');
  if(bg) bg.style.display='none';
}}
bindCellPopups();
setPlan('gold');
applyLocalEdits();
</script>
<script src="render-grid.js"></script>
<script>
function applyLocalEdits() {{
  const goldViews = document.querySelectorAll('.plan-view.gold-view');
  goldViews.forEach(view => {{
    const date = view.dataset.date;
    if (!date) return;
    const key = `schedule_saved_${{date}}_gold`;
    const saved = localStorage.getItem(key);
    if (!saved) return;
    let rows;
    try {{ rows = JSON.parse(saved); }} catch(e) {{ return; }}
    const gridWrap = view.querySelector('.grid-wrap');
    const summary  = view.querySelector('.summary');
    if (gridWrap) renderGoldGrid(rows, date, gridWrap);
    if (summary)  renderGoldSummary(rows, summary);
  }});
  bindCellPopups();
}}
</script>
</body></html>"""
    (DOCS / "index.html").write_text(page, encoding="utf-8")

    # kleurmapping voor replan in dezelfde stijl als planner
    replan_color_map = {}
    for day_rows in results.values():
        for r in day_rows:
            key = r.get("team_id") or r.get("schema")
            if key and key not in replan_color_map:
                replan_color_map[key] = color_for(key)
    replan_color_json = json.dumps(replan_color_map, ensure_ascii=False)

    replan_page = """<!doctype html>
<html lang='nl'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Baanschema Replan</title>
  <style>
    body{font-family:Inter,system-ui,sans-serif;max-width:1200px;margin:1.2rem auto;padding:0 1rem}
    input,button,select{padding:.4rem .55rem}
    .row{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center;margin:.6rem 0}
    table{border-collapse:collapse;width:100%}
    th,td{border:1px solid #e6e6e6;padding:.35rem .45rem;text-align:left;vertical-align:top}
    .small{color:#666}
    .card{border:1px solid #e6e6e6;border-radius:10px;padding:.7rem .85rem;margin:.7rem 0}
    #changeLog{margin:.5rem 0 0 1rem}
    #changeLog li{margin:.15rem 0}
    #matrixTbl{border-collapse:collapse;width:100%;table-layout:fixed}
    #matrixTbl th,#matrixTbl td{border:1px solid #dcdfe6;padding:.2rem .25rem;vertical-align:middle;height:30px;box-sizing:border-box}
    #matrixTbl tr.major-row td{border-top:3px solid #8f97a8}
    #matrixTbl tr.now-row td{border-top:4px solid #000 !important}
    #matrixTbl th{background:#fafafa;font-size:12px}
    #matrixTbl .time{background:#f3f4f7;font-weight:600;width:56px;min-width:56px;max-width:56px}
    #matrixTbl .cell{font-size:10px;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#111;font-weight:600}
    #matrixTbl input{transform:scale(.9);margin-right:.25rem}
    #matrixTbl td.earlydone{box-shadow: inset 0 0 0 2px #107a2f}
  </style>
</head>
<body>
  <h1>Wedstrijddag Herplanning (Cloud Run API)</h1>
  <p class='small'>Werk direct in de browser via de live Cloud Run API. Vink partijen af en bekijk wat klaar is, wat nu loopt en de restplanning.</p>

  <div class='row'>
    <label>Modus
      <select id='mode'>
        <option value='test'>Testmodus</option>
        <option value='live'>Live modus</option>
      </select>
    </label>
    <label>Datum
      <select id='date'></select>
    </label>
    <label>Huidige tijd
      <input id='now' value='12:15' placeholder='HH:MM'>
    </label>
    <button onclick='renderAll()'>Update status</button>
    <button onclick='runReplan()'>Herplan restdag</button>
    <button id='resetBtn' onclick='resetTestMode()'>Reset testmodus</button>
    <span id='status' class='small'></span>
  </div>

  <div class='card'>
    <strong>Wedstrijddag matrix (afvinken in de cel)</strong>
    <div id='summary' class='small'>Checkboxen worden lokaal onthouden per datum.</div>
    <ul id='changeLog' class='small'></ul>
    <div style='overflow:auto'>
      <table id='matrixTbl'>
        <thead><tr><th>Tijd</th><th>Baan 1</th><th>Baan 2</th><th>Baan 3</th><th>Baan 4</th><th>Baan 5</th><th>Baan 6</th><th>Baan 7</th><th>Baan 8</th><th>Baan 9</th><th>Baan 10</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

<script>
let DATA = {};
const COLOR_MAP = __COLOR_JSON__;
const API_BASE_DEFAULT = 'https://baanschema-api-dndzrlckha-ew.a.run.app';

function getApiBase(){
  const p = new URLSearchParams(location.search);
  return (p.get('api') || API_BASE_DEFAULT).replace(/\/$/, '');
}

function toMin(hhmm){ const [h,m]=hhmm.split(':').map(Number); return h*60+m; }
function keyFor(d,r){ return `${d}||${r.team_id||r.schema||''}||${r.part||''}`; }
function loadDone(d){ return new Set(JSON.parse(localStorage.getItem('replan_done_'+d) || '[]')); }
function saveDone(d,set){ localStorage.setItem('replan_done_'+d, JSON.stringify([...set])); }
function loadActualEnd(d){ return JSON.parse(localStorage.getItem('replan_actual_end_'+d) || '{}'); }
function saveActualEnd(d,obj){ localStorage.setItem('replan_actual_end_'+d, JSON.stringify(obj)); }
function roundUp15(m){ return Math.ceil(m/15)*15; }
function effectiveEndMin(d, r, nowMin, done, actualEnd){
  const k = keyFor(d,r);
  const planned = toMin(r.end||r.start||'00:00');
  if(actualEnd[k] && /^\d{2}:\d{2}$/.test(actualEnd[k])) return roundUp15(toMin(actualEnd[k]));
  if(done.has(k)) return planned;
  const s = toMin(r.start||'00:00');
  // Als partij gestart is en niet afgevinkt: bezet minstens tot de huidige tijd (afgerond op blok).
  if(s <= nowMin) return Math.max(planned, roundUp15(nowMin));
  return planned;
}
function hashString(s){ let h=2166136261>>>0; for(let i=0;i<s.length;i++){ h^=s.charCodeAt(i); h=Math.imul(h,16777619);} return h>>>0; }
function colorForKey(k){
  if(k && COLOR_MAP[k]) return COLOR_MAP[k];
  const l=(k||'').toLowerCase();
  if(l.includes('rood')) return 'hsl(0 88% 56%)';
  if(l.includes('oranje')) return 'hsl(30 92% 56%)';
  if(l.includes('groen')) return 'hsl(125 88% 46%)';
  const h = hashString(k)%360;
  return `hsl(${h} 92% 58%)`;
}

function fmtDate(d){
  const dd=String(d.getDate()).padStart(2,'0');
  const mm=String(d.getMonth()+1).padStart(2,'0');
  const yy=d.getFullYear();
  return `${dd}-${mm}-${yy}`;
}
function fmtTime(d){
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}
function applyMode(){
  const mode = document.getElementById('mode').value;
  const dateEl = document.getElementById('date');
  const nowEl = document.getElementById('now');
  const resetBtn = document.getElementById('resetBtn');
  if(mode==='live'){
    const n = new Date();
    const d = fmtDate(n);
    if([...dateEl.options].some(o=>o.value===d)) dateEl.value=d;
    nowEl.value = fmtTime(n);
    dateEl.disabled = true;
    nowEl.disabled = true;
    if(resetBtn) resetBtn.style.display='none';
  } else {
    dateEl.disabled = false;
    nowEl.disabled = false;
    if(resetBtn) resetBtn.style.display='inline-block';
  }
}

function resetTestMode(){
  const d = document.getElementById('date').value;
  if(!d) return;
  localStorage.removeItem('replan_done_'+d);
  localStorage.removeItem('replan_actual_end_'+d);
  CURRENT_ROWS = [];
  window.__LAST_CHANGES__ = [];
  document.getElementById('status').textContent = 'Testmodus gereset voor '+d;
  renderAll();
}

async function init(){
  const status = document.getElementById('status');
  const apiBase = getApiBase();
  try{
    let loadedFrom = '';
    try{
      const apiRes = await fetch(`${apiBase}/result?v=`+Date.now());
      if(!apiRes.ok) throw new Error('api result '+apiRes.status);
      DATA = await apiRes.json();
      loadedFrom = `API (${apiBase})`;
    } catch(_e){
      const localRes = await fetch('./result.json?v='+Date.now());
      if(!localRes.ok) throw new Error('local result '+localRes.status);
      DATA = await localRes.json();
      loadedFrom = 'lokale result.json fallback';
    }

    const sel = document.getElementById('date');
    const dates = Object.keys(DATA);
    if(!dates.length){ status.textContent='Geen data gevonden'; return; }
    dates.forEach(d=>{
      const o=document.createElement('option'); o.value=d; o.textContent=d; sel.appendChild(o);
    });
    if(dates.length) sel.value = dates[0];
    sel.addEventListener('change', ()=>{ CURRENT_ROWS=[]; renderAll(); });
    document.getElementById('now').addEventListener('change', ()=>{ renderAll(); });
    document.getElementById('mode').addEventListener('change', ()=>{ CURRENT_ROWS=[]; applyMode(); renderAll(); });
    applyMode();
    status.textContent='Data geladen via '+loadedFrom;
    renderAll();
  }catch(e){
    status.textContent='Kon geen plandata laden';
  }
}

let CURRENT_ROWS = [];
window.__LAST_CHANGES__ = [];

function renderMatrix(d, rows, done, nowMin){
  const tb = document.querySelector('#matrixTbl tbody');
  tb.innerHTML='';
  const actualEnd = loadActualEnd(d);
  const playable = rows.filter(r=>r.start && r.start!=='NIET_GELUKT' && r.part!=='COMP');
  if(!playable.length) return;

  const starts = playable.map(r=>toMin(r.start));
  const ends = playable.map(r=>effectiveEndMin(d, r, nowMin, done, actualEnd));
  const t0 = Math.min(...starts);
  const t1 = Math.max(...ends);

  const startCell = new Map();
  const occ = new Map();
  const effEndMap = new Map();
  let overlapConflicts = 0;
  function rowPriority(r, t){
    const k = keyFor(d,r);
    if(done.has(k)) return 1;
    const s = toMin(r.start), e = effectiveEndMin(d,r,nowMin,done,actualEnd);
    if(s <= t && t < e) return 3; // bezig/actief
    return 2; // gepland
  }
  playable.forEach(r=>{
    const endMin = effectiveEndMin(d, r, nowMin, done, actualEnd);
    const planEnd = toMin(r.end);
    const k = keyFor(d,r);
    effEndMap.set(k, {eff:endMin, planned:planEnd});
    for(let t=toMin(r.start); t<endMin; t+=15){
      const cellKey = `${t}-${r.court}`;
      const ex = occ.get(cellKey);
      if(!ex){
        occ.set(cellKey, r);
      } else {
        overlapConflicts++;
        const exPri = rowPriority(ex, t);
        const nwPri = rowPriority(r, t);
        if(nwPri > exPri){
          occ.set(cellKey, r);
        } else if(nwPri === exPri){
          const exEnd = effectiveEndMin(d, ex, nowMin, done, actualEnd);
          if(endMin > exEnd) occ.set(cellKey, r);
        }
      }
    }
    startCell.set(`${toMin(r.start)}-${r.court}`, r);
  });

  const nowMark = roundUp15(nowMin);
  for(let t=t0; t<t1; t+=15){
    const tr = document.createElement('tr');
    if(((t-t0)%90)===0) tr.classList.add('major-row');
    if(t===nowMark) tr.classList.add('now-row');
    const hh = String(Math.floor(t/60)).padStart(2,'0');
    const mm = String(t%60).padStart(2,'0');
    tr.innerHTML = `<td class='time'>${hh}:${mm}</td>`;
    for(let c=1;c<=10;c++){
      const key = `${t}-${c}`;
      const r = occ.get(key);
      const td = document.createElement('td');
      if(!r){ td.textContent='—'; tr.appendChild(td); continue; }

      const k = keyFor(d,r);
      const clr = colorForKey(r.team_id||r.schema||'');
      td.style.background = clr;
      td.style.cursor='pointer';
      const detailText = `${r.schema} | ${r.part} | ${r.start}-${r.end} | Baan ${r.court||'?'}${r.away_team ? ' | vs '+r.away_team : ''}`;
      td.addEventListener('click', ()=>openCellModal(detailText));
      const meta = effEndMap.get(k) || {eff: toMin(r.end||r.start||'00:00'), planned: toMin(r.end||r.start||'00:00')};

      if(startCell.has(key)){
        const checked = done.has(k) ? 'checked' : '';
        const effEnd = meta.eff;
        const plannedEnd = meta.planned;
        const overtime = (!done.has(k) && effEnd > plannedEnd) ? ` <span class='small'>(loopt door tot ${String(Math.floor(effEnd/60)).padStart(2,'0')}:${String(effEnd%60).padStart(2,'0')})</span>` : '';
        const early = (done.has(k) && effEnd < plannedEnd) ? ` <span class='small'>(eerder klaar ${String(Math.floor(effEnd/60)).padStart(2,'0')}:${String(effEnd%60).padStart(2,'0')})</span>` : '';
        if(done.has(k) && effEnd < plannedEnd) td.classList.add('earlydone');
        const ae = actualEnd[k] ? ` <span class='small'>(echt: ${actualEnd[k]})</span>` : '';
        const oppLabel = r.away_team ? ` vs ${r.away_team}` : '';
        td.innerHTML = `<label class='cell'><input type='checkbox' data-k="${k}" ${checked}>${r.team_short||r.schema} · ${r.part}${oppLabel}${ae}${overtime}${early}</label>`;
        const cb = td.querySelector('input');
        if(cb){ cb.addEventListener('change', (ev)=>{
          if(ev.target.checked){
            done.add(k);
            // Conservatief: als je later afvinkt dan geplande eindtijd, neem gepland einde.
            // (voorkomt kunstmatige uitloop als er achteraf wordt afgevinkt)
            const nowV = toMin(document.getElementById('now').value);
            const plannedV = toMin(r.end||r.start||'00:00');
            const endV = nowV <= plannedV ? nowV : plannedV;
            actualEnd[k] = String(Math.floor(endV/60)).padStart(2,'0')+':'+String(endV%60).padStart(2,'0');
          } else {
            done.delete(k);
            delete actualEnd[k];
          }
          saveDone(d,done);
          saveActualEnd(d,actualEnd);
          renderAll();
        }); }
      } else {
        td.innerHTML = `<div class='cell'>${r.team_short||r.schema} · ${r.part}${r.away_team ? ' vs '+r.away_team : ''}</div>`;
        td.style.opacity='0.6';
      }
      tr.appendChild(td);
    }
    tb.appendChild(tr);
  }
}

function runReplan(){
  applyMode();
  const d = document.getElementById('date').value;
  if(!d || !DATA[d]) return;
  const nowMin = toMin(document.getElementById('now').value);
  const done = loadDone(d);
  const actualEnd = loadActualEnd(d);

  const src = (DATA[d]||[]).map(r=>({...r}));
  const baseByKey = new Map(src.filter(r=>r.start && r.start!=='NIET_GELUKT' && r.part!=='COMP').map(r=>[keyFor(d,r), {start:r.start,end:r.end,court:r.court}]));
  const playable = src.filter(r=>r.start && r.start!=='NIET_GELUKT' && r.part!=='COMP');

  // lock completed + realistisch actieve partijen op basis van werkelijkheid
  // Belangrijk: per baan kan op 'nu' maar 1 partij echt bezig zijn.
  const lockedKeys = new Set();
  const delayedCourts = new Set();
  const scheduled = [];

  // 1) Afgeronde partijen vastzetten
  playable.forEach(r=>{
    const k = keyFor(d,r);
    if(!done.has(k)) return;
    const s=toMin(r.start), e=toMin(r.end);
    const realEnd = effectiveEndMin(d, r, nowMin, done, actualEnd);
    lockedKeys.add(k);
    if(realEnd !== e){
      r.end = String(Math.floor(realEnd/60)).padStart(2,'0')+':'+String(realEnd%60).padStart(2,'0');
    }
    scheduled.push({
      team: r.team_id||r.schema,
      schema: (r.schema||'').toLowerCase(),
      kind: r.kind,
      court: r.court,
      start: s,
      end: toMin(r.end)
    });
  });

  // 2) Lopende kandidaten bepalen (niet-afgerond, gestart en nog niet klaar op 'nu')
  const activeByCourt = new Map();
  playable.forEach(r=>{
    const k = keyFor(d,r);
    if(lockedKeys.has(k)) return;
    const s=toMin(r.start), e=toMin(r.end);
    const realEnd = effectiveEndMin(d, r, nowMin, done, actualEnd);
    if(!(s<=nowMin && nowMin<realEnd)) return;
    const c = r.court || 1;
    const prev = activeByCourt.get(c);
    // Kies op een baan de partij die het langst/het eerst bezig is.
    if(!prev || s < prev.s || (s===prev.s && realEnd>prev.realEnd)){
      activeByCourt.set(c, {r, s, e, realEnd});
    }
  });

  // 3) Winnaars per baan vastzetten als 'bezig'
  for(const [c,v] of activeByCourt.entries()){
    const {r,s,e,realEnd} = v;
    const k = keyFor(d,r);
    lockedKeys.add(k);
    if(realEnd !== e){
      r.end = String(Math.floor(realEnd/60)).padStart(2,'0')+':'+String(realEnd%60).padStart(2,'0');
      if(realEnd > e) delayedCourts.add(c);
    }
    scheduled.push({
      team: r.team_id||r.schema,
      schema: (r.schema||'').toLowerCase(),
      kind: r.kind,
      court: c,
      start: s,
      end: toMin(r.end)
    });
  }

  // 4) Gestarte maar niet-gekozen overlap-kandidaten terug naar pending (nog niet gestart in werkelijkheid)
  playable.forEach(r=>{
    const k = keyFor(d,r);
    if(lockedKeys.has(k)) return;
    const s=toMin(r.start), e=toMin(r.end);
    const realEnd = effectiveEndMin(d, r, nowMin, done, actualEnd);
    if(s<=nowMin && nowMin<realEnd){
      // kon in werkelijkheid niet gestart zijn door baanconflict; laat herplan opnieuw plaatsen
      r.start = String(Math.floor(nowMin/60)).padStart(2,'0')+':'+String(nowMin%60).padStart(2,'0');
      const ne = nowMin + (e-s);
      r.end = String(Math.floor(ne/60)).padStart(2,'0')+':'+String(ne%60).padStart(2,'0');
    }
  });

  function ov(aS,aE,bS,bE){ return !(aE<=bS || aS>=bE); }
  function violatesTeam(a, teamRows){
    const schemaL = (a.schema||'').toLowerCase();
    for(const b of teamRows){
      if(!ov(a.start,a.end,b.start,b.end)) continue;
      if((a.kind==='S' && b.kind==='D') || (a.kind==='D' && b.kind==='S')) return true;
      if((a.kind==='D' && b.kind==='M') || (a.kind==='M' && b.kind==='D')) return true;
      if(schemaL.includes('2de-2he-dd-hd-2gd')){
        if((a.kind==='S' && b.kind==='M') || (a.kind==='M' && b.kind==='S')) return true;
      }
    }
    return false;
  }

  // herplan remaining wedstrijden op dezelfde baan (duidelijk causaal op wedstrijddag)
  const pending = playable
    .filter(r=>!lockedKeys.has(keyFor(d,r)))
    .sort((a,b)=> (a.start||'').localeCompare(b.start||'') || ((a.court||99)-(b.court||99)));

  for(const r of pending){
    const origS=toMin(r.start), origE=toMin(r.end), dur=origE-origS;
    const team = r.team_id||r.schema;
    const schemaL = (r.schema||'').toLowerCase();
    const c = r.court || 1;
    let placed=false;

    for(let t=roundUp15(Math.max(nowMin, origS)); t<=23*60; t+=15){
      const end=t+dur;
      const courtBusy = scheduled.some(x=>x.court===c && ov(t,end,x.start,x.end));
      if(courtBusy) continue;
      const teamRows = scheduled.filter(x=>x.team===team);
      const cand = {team, schema:schemaL, kind:r.kind, court:c, start:t, end};
      if(violatesTeam(cand, teamRows)) continue;

      r.start = String(Math.floor(t/60)).padStart(2,'0')+':'+String(t%60).padStart(2,'0');
      r.end = String(Math.floor(end/60)).padStart(2,'0')+':'+String(end%60).padStart(2,'0');
      r.court = c;
      scheduled.push(cand);
      placed=true;
      break;
    }

    if(!placed){
      // fallback: laat staan zoals het was
      scheduled.push({team, schema:schemaL, kind:r.kind, court:c, start:origS, end:origE});
    }
  }

  let changed=0;
  const changes=[];
  src.forEach(r=>{
    if(!r.start || r.start==='NIET_GELUKT' || r.part==='COMP') return;
    const b = baseByKey.get(keyFor(d,r));
    if(!b) return;
    if(b.start!==r.start || b.end!==r.end || b.court!==r.court){
      changed++;
      changes.push(`${r.team_short||r.schema} · ${r.part}: ${b.start}-${b.end} (B${b.court}) → ${r.start}-${r.end} (B${r.court})`);
    }
  });

  CURRENT_ROWS = src;
  window.__LAST_CHANGES__ = changes;
  const dc = [...delayedCourts].sort((a,b)=>a-b);
  const delayedTxt = dc.length ? ` · uitloop op baan ${dc.join(', ')}` : '';
  document.getElementById('status').textContent = `Herplan klaar: ${changed} partijen aangepast${delayedTxt}`;
  renderAll();
}

function renderAll(){
  applyMode();
  const d = document.getElementById('date').value;
  if(!d || !DATA[d]) return;
  const now = document.getElementById('now').value;
  const nowMin = toMin(now);
  const rows = (CURRENT_ROWS.length ? CURRENT_ROWS : DATA[d]);
  const done = loadDone(d);
  const actualEnd = loadActualEnd(d);

  let doneCount=0, liveCount=0, remainCount=0;
  rows.forEach(r=>{
    if(r.start==='NIET_GELUKT' || r.part==='COMP') return;
    const k = keyFor(d,r);
    const s = toMin(r.start), eEff = effectiveEndMin(d, r, nowMin, done, actualEnd);
    if(done.has(k)) doneCount++;
    else if(s<=nowMin && nowMin<=eEff) liveCount++;
    else remainCount++;
  });

  document.getElementById('summary').textContent = `Nu: ${now} · Gereed: ${doneCount} · Bezig: ${liveCount} · Resterend: ${remainCount}`;
  const log = document.getElementById('changeLog');
  const ch = window.__LAST_CHANGES__ || [];
  if(ch.length){
    log.innerHTML = '<li><strong>Wijzigingen door herplan:</strong></li>' + ch.map(x=>`<li>${x}</li>`).join('');
  } else {
    log.innerHTML = '<li>Nog geen herplan-wijzigingen.</li>';
  }
  renderMatrix(d, rows, done, nowMin);
}

init();
</script>
</body></html>"""
    replan_page = replan_page.replace("__COLOR_JSON__", replan_color_json)
    (DOCS / "replan.html").write_text(replan_page, encoding="utf-8")

    # Backward-compat: older shared links used /docs/architecture/* while Pages serves DOCS root as '/'.
    # Mirror architecture assets under docs/docs/architecture so both URL shapes keep working.
    arch_src = DOCS / "architecture"
    arch_legacy = DOCS / "docs" / "architecture"
    if arch_src.exists():
        arch_legacy.parent.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(arch_legacy, ignore_errors=True)
        shutil.copytree(arch_src, arch_legacy)


if __name__ == "__main__":
    main()
