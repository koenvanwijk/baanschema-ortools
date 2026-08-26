from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ortools.sat.python import cp_model

from baanschema.rules import build_parts, player_demand

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
    # Unique key per (day, schema, home team). Guards against merging two teams
    # that happen to share the same schema string on one day (bug #1).
    team_key: str = ""
    home_team: str = ""
    away_team: str = ""


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
            team1 = (row.get("Team 1") or "").strip()
            team2 = (row.get("Team 2") or "").strip()
            # KNLTB export: Team 1 is the home team. Fall back to team1 as home.
            home_team = team1
            away_team = team2
            if team1 and not team1.upper().startswith("MIERLO") and team2.upper().startswith("MIERLO"):
                # Defensive: if only Team 2 is Mierlo, treat that as home side.
                home_team, away_team = team2, team1
            # Unique key so two teams with the same schema on one day stay separate.
            team_key = f"{schema} · {home_team}" if home_team else schema
            teams.append(
                TeamDay(
                    date=date,
                    schema=schema,
                    matches=m,
                    duration_min=d,
                    singles=_to_int(row.get("Singles") or ""),
                    doubles=_to_int(row.get("Doubles") or ""),
                    mix=_to_int(row.get("Mix") or ""),
                    team_key=team_key,
                    home_team=home_team,
                    away_team=away_team,
                )
            )
    return teams, reservations


def mins_to_hhmm(m: int) -> str:
    return f"{m//60:02d}:{m%60:02d}"


def estimate_parallel_capacity(team: TeamDay) -> int:
    """Best-effort team-first capacity estimate.

    Small teams should ideally stay on one court.
    Larger match sets may use two courts in parallel.
    """
    if team.matches <= 4:
        return 1
    return 2


def solve_day(
    date: str,
    teams: list[TeamDay],
    reservations: list[Reservation],
    time_limit_s: float = 20.0,
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
    w_fasering_soft: int = 300_000,
    random_seed: int = 42,
    two_phase: bool = False,  # Default: single-phase (beter voor age-based spreiding)
) -> dict:
    """
    Main scheduler. If two_phase=True, runs a two-phase approach:
      Phase A: Groen + JU + lagere jeugd → plan eerst, reserveer banen tot ~13:30
      Phase B: GEM + HER + hogere klassen → plan daarna met fase-A als reserveringen

    Startregels dag: planner probeert eerst dagstart 09:00. Alleen als dat leidt
    tot partijen die pas na 19:30 moeten starten, of tot onplanbare (NIET_GELUKT)
    partijen, valt de planner terug op dagstart 08:30.

    First-match cutoff (eerste teamwedstrijd uiterlijk 15:00, met datum-specifieke
    verruiming op kneldagen) blijft een ZACHTE voorkeur (team_cutoff_bonus in de
    objective). Een experiment met harde handhaving + escalatieladder gaf meer
    NIET_GELUKT-partijen dan de zachte variant op meerdere dagen (regressie), dus
    is teruggedraaid conform het niet-blocking beleid: harde eisen mogen de build
    nooit verslechteren t.o.v. de zachte voorkeur.
    """
    def _run(day_start_pref: int) -> dict:
        if two_phase:
            return solve_day_two_phase(
                date, teams, reservations, time_limit_s,
                w_block_rise, w_long_gap, w_morning_occ, w_total_occ,
                w_cutoff_bonus, w_early_start, w_late_start, w_youth_late,
                w_team_court_penalty, w_high_court_penalty, w_team_span, w_fasering_soft, random_seed,
                day_start_pref=day_start_pref,
            )
        return _solve_single_phase(
            date, teams, reservations, time_limit_s,
            w_block_rise, w_long_gap, w_morning_occ, w_total_occ,
            w_cutoff_bonus, w_early_start, w_late_start, w_youth_late,
            w_team_court_penalty, w_high_court_penalty, w_team_span, w_fasering_soft, random_seed,
            day_start_pref=day_start_pref,
        )

    result_0900 = _run(9 * 60)
    rows_0900 = result_0900.get("rows", [])
    failed_0900 = [r for r in rows_0900 if r.get("start") == "NIET_GELUKT"]
    valid_starts_0900 = [
        int(r["start"][:2]) * 60 + int(r["start"][3:])
        for r in rows_0900
        if r.get("start") not in (None, "", "NIET_GELUKT")
    ]
    if (
        result_0900.get("status") in ("OPTIMAL", "FEASIBLE")
        and not failed_0900
        and valid_starts_0900
        and max(valid_starts_0900) <= 19 * 60 + 30
    ):
        return result_0900

    # Terugval naar 08:30 dagstart.
    result_0830 = _run(8 * 60 + 30)

    # Niet-blocking beleid: kies de poging met de minste NIET_GELUKT-partijen.
    ng_0900 = len(failed_0900)
    ng_0830 = sum(1 for r in result_0830.get("rows", []) if r.get("start") == "NIET_GELUKT")
    if result_0900.get("status") in ("OPTIMAL", "FEASIBLE") and ng_0900 <= ng_0830:
        return result_0900
    return result_0830


def solve_day_two_phase(
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
    w_fasering_soft: int,
    random_seed: int,
    day_start_pref: int = 8 * 60 + 30,
    enforce_cutoff_hard: bool = False,
) -> dict:
    """Two-phase scheduler: fase-A (morning) then fase-B (afternoon)."""
    
    def _is_phase_a(schema: str) -> bool:
        """Phase A: Junioren (11-14) only - these prefer early starts."""
        tl = schema.lower()
        # Only Junioren (11-14) and Groen go in Phase A
        if "groen zondag" in tl or "junioren" in tl:
            return True
        return False

    def _is_phase_b(schema: str) -> bool:
        """Phase B: All Jeugd 13-17 + Senioren - spread across day."""
        tl = schema.lower()
        # Gemengd, Heren, Dames always Phase B
        if ("gemengd" in tl) or ("heren" in tl) or ("dames" in tl):
            return True
        # ALL Jeugd 13-17 go to Phase B (they need middag preference)
        is_jeugd_1317 = ("jongens 13 t/m 17" in tl) or ("meisjes 13 t/m 17" in tl)
        return is_jeugd_1317

    day_teams = [t for t in teams if t.date == date]
    phase_a_teams = [t for t in day_teams if _is_phase_a(t.schema)]
    phase_b_teams = [t for t in day_teams if _is_phase_b(t.schema)]

    # Phase A: plan Groen + JU + lagere jeugd met half time-limit
    print(f"[Phase A] Planning {len(phase_a_teams)} morning teams...")
    result_a = _solve_single_phase(
        date, phase_a_teams, reservations, time_limit_s / 2,
        w_block_rise, w_long_gap, w_morning_occ, w_total_occ,
        w_cutoff_bonus, w_early_start, w_late_start, w_youth_late,
        w_team_court_penalty, w_high_court_penalty, w_team_span, w_fasering_soft, random_seed,
        day_start_pref=day_start_pref,
        enforce_cutoff_hard=enforce_cutoff_hard,
    )
    
    if result_a["status"] not in ["OPTIMAL", "FEASIBLE"]:
        print(f"[Phase A] Failed: {result_a['status']}")
        return result_a  # Kan niet verder zonder fase-A

    # Converteer fase-A rows naar reserveringen voor fase-B
    phase_a_reservations = []
    for row in result_a["rows"]:
        if row.get("start") == "NIET_GELUKT":
            continue
        s_hhmm = row["start"]
        e_hhmm = row["end"]
        c = row["court"]
        s_min = int(s_hhmm[:2]) * 60 + int(s_hhmm[3:])
        e_min = int(e_hhmm[:2]) * 60 + int(e_hhmm[3:])
        phase_a_reservations.append((c, s_min, e_min))

    # Phase B: plan GEM + HER + hogere klassen met fase-A slots als reserveringen
    print(f"[Phase B] Planning {len(phase_b_teams)} afternoon teams with {len(phase_a_reservations)} reserved slots...")

    import concurrent.futures

    def run_two_phase():
        rb = _solve_single_phase(
            date, phase_b_teams, reservations, time_limit_s * 0.4,
            w_block_rise, w_long_gap, w_morning_occ, w_total_occ,
            w_cutoff_bonus, w_early_start, w_late_start, w_youth_late,
            w_team_court_penalty, w_high_court_penalty, w_team_span, w_fasering_soft, random_seed,
            extra_reserved=phase_a_reservations,
            day_start_pref=day_start_pref,
            enforce_cutoff_hard=enforce_cutoff_hard,
        )
        return result_a["rows"] + rb["rows"]

    def run_single():
        rs = _solve_single_phase(
            date, day_teams, reservations, time_limit_s * 0.6,
            w_block_rise, w_long_gap, w_morning_occ, w_total_occ,
            w_cutoff_bonus, w_early_start, w_late_start, w_youth_late,
            w_team_court_penalty, w_high_court_penalty, w_team_span, w_fasering_soft, random_seed,
            day_start_pref=day_start_pref,
            enforce_cutoff_hard=enforce_cutoff_hard,
        )
        return rs.get("rows", [])

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_two = ex.submit(run_two_phase)
        f_single = ex.submit(run_single)
        two_rows = f_two.result()
        single_rows = f_single.result()

    two_ng = sum(1 for r in two_rows if r.get("start") == "NIET_GELUKT")
    single_ng = sum(1 for r in single_rows if r.get("start") == "NIET_GELUKT")
    print(f"[Compare] Two-phase NG={two_ng}  Single-phase NG={single_ng}")

    if single_ng < two_ng:
        print(f"[Fallback] Single-phase wint, gebruik single-phase resultaat.")
        return {"status": "FEASIBLE", "date": date, "rows": single_rows}

    print(f"[Two-phase] Wint of gelijk, gebruik twee-fase resultaat.")
    return {"status": "FEASIBLE", "date": date, "rows": two_rows}


def _solve_single_phase(
    date: str,
    teams: list[TeamDay],
    reservations: list[Reservation],
    time_limit_s: float = 20.0,
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
    w_fasering_soft: int = 300_000,
    random_seed: int = 42,
    extra_reserved: list = None,
    day_start_pref: int = 8 * 60 + 30,
    enforce_cutoff_hard: bool = False,
) -> dict:
    day_teams = [t for t in teams if t.date == date]
    day_res = [r for r in reservations if r.date == date]

    # quarter-hour grid
    start_min = day_start_pref
    end_min = 20 * 60
    slot_mins = list(range(start_min, end_min + 1, 15))
    slot_idx = {m: i for i, m in enumerate(slot_mins)}
    courts = list(range(1, 11))

    # Baan-paren: teams mogen alleen op aangrenzende paren spelen (1+2, 3+4, 5+6, 7+8, 9+10).
    COURT_PAIRS = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]

    first_cutoff = {
        "12-04-2026": 16 * 60,
        "19-04-2026": 17 * 60,
        "10-05-2026": 17 * 60,
        "17-05-2026": 18 * 60 + 30,
        "25-05-2026": 16 * 60,
        "06-04-2026": 16 * 60,
    }.get(date, 15 * 60)

    reserved = []  # (court, start, end)
    if extra_reserved:
        reserved.extend(extra_reserved)  # Fase-A reserveringen indien twee-fase mode
    
    kinds_today = {r.kind for r in day_res}
    # Reserveringsvensters gebruiken de dagstart als basis (besluit 2026-08-26,
    # SPEC.md sectie 2/3). Voorkeur: dagstart_pref (bv 09:00). Val alleen terug
    # op 08:30 als de dagstart later is dan 08:30 zou toestaan (d.w.z. nooit
    # vroeger reserveren dan de eigenlijke dagstart, en nooit later dan nodig).
    rood_oranje_base = day_start_pref if day_start_pref <= 8 * 60 + 30 else day_start_pref
    for r in day_res:
        if r.kind == "oranje":
            # Rood krijgt altijd baan 1 (SPEC.md sectie 3). Oranje schuift naar
            # 2, 3, 4 zodra Rood ook speelt; anders houdt Oranje 1, 2, 3.
            oranje_courts = [2, 3, 4] if "rood" in kinds_today else [1, 2, 3]
            for c in oranje_courts:
                reserved.append((c, rood_oranje_base, rood_oranje_base + 2 * 60))
        elif r.kind == "rood":
            reserved.append((1, rood_oranje_base, rood_oranje_base + 60))

    parts = []
    for t in day_teams:
        for label, kind in build_parts(t):
            tl = t.schema.lower()
            male_d, female_d, total_d = player_demand(t.schema, label, kind)
            parts.append(
                {
                    "team": t.schema,
                    "team_key": t.team_key or t.schema,
                    "home_team": t.home_team,
                    "away_team": t.away_team,
                    "label": label,
                    "kind": kind,
                    "duration": t.duration_min,
                    "is_mixed_team": "gemengd zondag" in tl,
                    "is_youth_team": ("junioren" in tl) or ("jongens 13 t/m 17" in tl) or ("meisjes 13 t/m 17" in tl) or ("groen zondag" in tl),
                    "is_4p_combo": "2de-2he-dd-hd-2gd" in tl,
                    "male_demand": male_d,
                    "female_demand": female_d,
                    "player_demand": total_d,
                }
            )

    model = cp_model.CpModel()
    x = {}  # part,start,court
    y = []
    start_used = {}

    allowed_starts = {}
    for p_idx, p in enumerate(parts):
        dur = p["duration"]
        latest = end_min - dur
        starts = [m for m in slot_mins if m <= latest]
        
        # Mixed teams: niet voor 10:00
        if p["is_mixed_team"]:
            starts = [m for m in starts if m >= 10 * 60]
        
        # Jeugd 13-17: HARD CONSTRAINT ≥11:00 (spreiding)
        team_l = p["team"].lower()
        is_jeugd_1317 = ("jongens 13 t/m 17" in team_l) or ("meisjes 13 t/m 17" in team_l)
        if is_jeugd_1317:
            starts = [m for m in starts if m >= 11 * 60]  # HARD: ≥11:00
        
        # Youth/Groen: niet na 17:30
        if p["is_youth_team"]:
            starts = [m for m in starts if m <= 17 * 60 + 30]
        
        allowed_starts[p_idx] = starts

        vars_p = []
        for s in starts:
            for c in courts:
                v = model.new_bool_var(f"x_p{p_idx}_s{s}_c{c}")
                x[(p_idx, s, c)] = v
                vars_p.append(v)
            su = model.new_bool_var(f"start_p{p_idx}_s{s}")
            start_used[(p_idx, s)] = su
            model.add(sum(x[(p_idx, s, c)] for c in courts) == su)
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

    # S and D cannot overlap within same team (M can overlap).
    # Group by the UNIQUE team key (schema + home team), so two teams that share
    # the same schema string on one day are never merged (bug #1).
    by_team = defaultdict(list)
    for i, p in enumerate(parts):
        by_team[p["team_key"]].append(i)

    # Meta lookup by unique key (used for court/span heuristics below).
    team_meta_by_key = {(t.team_key or t.schema): t for t in day_teams}

    def free_static_courts_at(t: int) -> int:
        reserved_courts_here = {rc for rc, rs, re in reserved if rs <= t < re}
        return len(courts) - len(reserved_courts_here)

    fasering_soft_penalty = []  # zachte fasering-penalty voor niet-8-partijenteams (SPEC.md sectie 5)

    for team, idxs in by_team.items():
        s_parts = [i for i in idxs if parts[i]["kind"] == "S"]
        d_parts = [i for i in idxs if parts[i]["kind"] == "D"]
        m_parts = [i for i in idxs if parts[i]["kind"] == "M"]
        combo_parts = [i for i in idxs if parts[i].get("is_4p_combo")]
        non_s_parts = [i for i in idxs if parts[i]["kind"] != "S"]

        # Besluit Oscar/Koen 2026-08-26 (SPEC.md sectie 5): de strikte
        # S->D->GD-waterval is alleen nog een HARDE eis voor 8-partijenteams
        # (landelijke competitie, hoog niveau, 4 spelers). Voor alle overige
        # teams (5-partijenteams, niet-gemengde teams, etc.) wordt de waterval
        # een ZACHTE voorkeur: een optimaler baanschema/bezetting weegt daar
        # zwaarder dan strikte fasering.
        team_meta = team_meta_by_key.get(team)
        is_8p_team = bool(team_meta and team_meta.matches == 8)

        # Extra startregel (planningsregels.md): kijk naar het eerste haalbare
        # startvenster van het team. Zijn daar nog maar 1-2 banen vrij (na
        # aftrek van Rood/Oranje-reserveringen), dan heeft het team een ZACHTE
        # voorkeur om te starten met dubbels/GD i.p.v. singles. Zijn er 3+ banen
        # vrij, dan blijft de oude standaardregel (singles eerst, hard) gelden.
        # Zachte voorkeur i.p.v. harde eis: een harde omkering bleek op sommige
        # dagen extra partijen onplanbaar te maken (regressie t.o.v. de oude
        # gedrag), wat in strijd is met het niet-blocking beleid.
        team_is_mixed = parts[idxs[0]].get("is_mixed_team", False) if idxs else False
        earliest_candidates = [min(allowed_starts[i]) for i in idxs if allowed_starts[i]]
        earliest_start = min(earliest_candidates) if earliest_candidates else start_min
        free_at_earliest = free_static_courts_at(earliest_start)
        prefer_doubles_first = (not team_is_mixed) and non_s_parts and free_at_earliest <= 2

        # Singles vóór doubles: harde eis voor niet-gemengde teams (ongewijzigd).
        # Gemengde teams (GEM): S en GD mogen overlappen (Gold doet dit ook).
        if not team_is_mixed:
            for si in s_parts:
                dur_s = parts[si]["duration"]
                for ni in non_s_parts:
                    for s_s in allowed_starts[si]:
                        for s_n in allowed_starts[ni]:
                            if s_n < s_s + dur_s:
                                model.add(start_used[(si, s_s)] + start_used[(ni, s_n)] <= 1)

        # Rondenstructuur (Gold-patroon): pairs van wedstrijden starten tegelijk.
        # S1+S2 tegelijk, S3+S4 tegelijk, D1+D2 tegelijk.
        # Alleen voor niet-gemengde teams.
        if not team_is_mixed:
            def pair_same_start(i0, i1):
                for s0 in allowed_starts[i0]:
                    for s1 in allowed_starts[i1]:
                        if s0 != s1:
                            model.add(start_used[(i0, s0)] + start_used[(i1, s1)] <= 1)

            for parts_list in [s_parts, d_parts, m_parts]:
                for idx in range(0, len(parts_list) - 1, 2):
                    pair_same_start(parts_list[idx], parts_list[idx + 1])

        # Per-slot occupancy: S/D, D/GD (en bij 4-spelersschema's ook S/GD) mogen
        # elkaar niet overlappen. Voor 8-partijenteams is dit een HARDE waterval
        # (fase N+1 mag pas starten als fase N helemaal klaar is, over de hele
        # teamdag). Voor overige teams blijft dit de bestaande "geen twee
        # soorten tegelijk actief in hetzelfde tijdslot"-vorm, als ZACHTE
        # voorkeur via een penalty in de objective (fasering_soft_penalty).
        team_hash = abs(hash(team)) % 10_000_000
        for t in slot_mins[:-1]:
            s_occ = []
            d_occ = []
            m_occ = []
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
            for i in m_parts:
                for s in allowed_starts[i]:
                    if s <= t < s + parts[i]["duration"]:
                        for c in courts:
                            m_occ.append(x[(i, s, c)])

            s_sum = sum(s_occ)
            d_sum = sum(d_occ)
            m_sum = sum(m_occ)

            if is_8p_team:
                # HARD: singles en dubbels mogen niet tegelijk.
                if s_parts and d_parts:
                    z_sd = model.new_bool_var(f"team_{team_hash}_t{t}_sd_mode")
                    model.add(s_sum <= 10 * z_sd)
                    model.add(d_sum <= 10 * (1 - z_sd))

                # HARD: gemengd dubbel (M/GD) en dubbel mogen niet tegelijk.
                if m_parts and d_parts:
                    z_md = model.new_bool_var(f"team_{team_hash}_t{t}_md_mode")
                    model.add(m_sum <= 10 * z_md)
                    model.add(d_sum <= 10 * (1 - z_md))

                # HARD (4-spelersteam): singles en GD ook niet tegelijk.
                if combo_parts and s_parts and m_parts:
                    z_sm = model.new_bool_var(f"team_{team_hash}_t{t}_sm_mode")
                    model.add(s_sum <= 10 * z_sm)
                    model.add(m_sum <= 10 * (1 - z_sm))
            else:
                # SOFT: dezelfde niet-overlap-conditie, maar als penalty i.p.v.
                # harde constraint. We gebruiken losse "is deze soort actief"
                # indicatoren (niet de ruwe occupancy-som, die bij 2 gelijktijdige
                # singles al >1 kan zijn zonder dat er sprake is van fase-overlap)
                # en tellen een overlap alleen als twee VERSCHILLENDE soorten
                # tegelijk actief zijn. Dat telt op in fasering_soft_penalty
                # hieronder (objective).
                if s_parts and d_parts:
                    s_active = model.new_bool_var(f"team_{team_hash}_t{t}_s_active")
                    d_active = model.new_bool_var(f"team_{team_hash}_t{t}_d_active")
                    model.add(s_sum >= 1).only_enforce_if(s_active)
                    model.add(s_sum == 0).only_enforce_if(s_active.Not())
                    model.add(d_sum >= 1).only_enforce_if(d_active)
                    model.add(d_sum == 0).only_enforce_if(d_active.Not())
                    overlap_sd = model.new_bool_var(f"team_{team_hash}_t{t}_sd_overlap")
                    model.add(overlap_sd >= s_active + d_active - 1)
                    fasering_soft_penalty.append(overlap_sd)

                if m_parts and d_parts:
                    m_active = model.new_bool_var(f"team_{team_hash}_t{t}_m_active")
                    d_active2 = model.new_bool_var(f"team_{team_hash}_t{t}_d_active2")
                    model.add(m_sum >= 1).only_enforce_if(m_active)
                    model.add(m_sum == 0).only_enforce_if(m_active.Not())
                    model.add(d_sum >= 1).only_enforce_if(d_active2)
                    model.add(d_sum == 0).only_enforce_if(d_active2.Not())
                    overlap_md = model.new_bool_var(f"team_{team_hash}_t{t}_md_overlap")
                    model.add(overlap_md >= m_active + d_active2 - 1)
                    fasering_soft_penalty.append(overlap_md)

                if combo_parts and s_parts and m_parts:
                    s_active2 = model.new_bool_var(f"team_{team_hash}_t{t}_s_active2")
                    m_active2 = model.new_bool_var(f"team_{team_hash}_t{t}_m_active2")
                    model.add(s_sum >= 1).only_enforce_if(s_active2)
                    model.add(s_sum == 0).only_enforce_if(s_active2.Not())
                    model.add(m_sum >= 1).only_enforce_if(m_active2)
                    model.add(m_sum == 0).only_enforce_if(m_active2.Not())
                    overlap_sm = model.new_bool_var(f"team_{team_hash}_t{t}_sm_overlap")
                    model.add(overlap_sm >= s_active2 + m_active2 - 1)
                    fasering_soft_penalty.append(overlap_sm)

    # Player-resource constraints per team per timeslot (except rood/oranje; those are reservations)
    for team, idxs in by_team.items():
        team_l = team.lower()
        is_mixed_team = "gemengd zondag" in team_l

        for t in slot_mins[:-1]:
            total_terms = []
            male_terms = []
            female_terms = []
            team_occ_terms = []

            for i in idxs:
                p = parts[i]
                if p["player_demand"] == 0 and p["male_demand"] == 0 and p["female_demand"] == 0:
                    continue
                occ_terms = []
                for s in allowed_starts[i]:
                    if s <= t < s + p["duration"]:
                        for c in courts:
                            occ_terms.append(x[(i, s, c)])
                if not occ_terms:
                    continue

                occ = sum(occ_terms)
                team_occ_terms.append(occ)
                if p["player_demand"]:
                    total_terms.append(p["player_demand"] * occ)
                if p["male_demand"]:
                    male_terms.append(p["male_demand"] * occ)
                if p["female_demand"]:
                    female_terms.append(p["female_demand"] * occ)

            if team_occ_terms:
                model.add(sum(team_occ_terms) <= 2)
            if total_terms:
                model.add(sum(total_terms) <= 4)
            if is_mixed_team:
                # Mixed teams: 2 men + 2 women max tegelijk
                if male_terms:
                    model.add(sum(male_terms) <= 2)
                if female_terms:
                    model.add(sum(female_terms) <= 2)

    # First-match cutoff: bij enforce_cutoff_hard=True wordt dit een harde eis
    # per team (eerste teamwedstrijd start uiterlijk op de cutoff-tijd). Bij
    # False (laatste redmiddel in de escalatieladder van solve_day) blijft het
    # een zachte voorkeur via de objective (team_cutoff_bonus hieronder).
    if enforce_cutoff_hard:
        for team, idxs in by_team.items():
            late_starts = []
            for i in idxs:
                for s in allowed_starts[i]:
                    if s > first_cutoff:
                        for c in courts:
                            late_starts.append(x[(i, s, c)])
            if not late_starts:
                continue
            # Team mag alleen na de cutoff starten als er al een eerdere partij
            # van datzelfde team vóór/op de cutoff is gestart (dus dit is geen
            # eerste-wedstrijd-schending).
            early_starts = []
            for i in idxs:
                for s in allowed_starts[i]:
                    if s <= first_cutoff:
                        for c in courts:
                            early_starts.append(x[(i, s, c)])
            if early_starts:
                has_early_hard = model.new_bool_var(f"cutoff_hard_early_{abs(hash(team))%10_000_000}")
                model.add(sum(early_starts) >= 1).only_enforce_if(has_early_hard)
                model.add(sum(early_starts) == 0).only_enforce_if(has_early_hard.Not())
                model.add(sum(late_starts) == 0).only_enforce_if(has_early_hard.Not())
            else:
                # Geen enkele toegestane start valt vóór de cutoff: team kan de
                # eis nooit halen (bv. jeugd 13-17 met harde ondergrens 11:00 op
                # een dag met cutoff 15:00 zou hier nog kunnen). Laat dit team
                # ongemoeid; de escalatieladder in solve_day vangt dit geval op.
                pass

    # NOTE: als enforce_cutoff_hard=False blijft de cutoff een soft preference
    # (zie team_cutoff_bonus in de objective hieronder).

    # Lexicographic-like objective (grote gewichtsstappen):
    # 1) maximaal planbaar
    # 2) ochtendbezetting
    # 3) totale bezetting
    # 4) vroege starts
    # 5) first-start cutoff per team
    scheduled_score = sum(y) * 1_000_000_000

    morning_occ_terms = []
    total_occ_terms = []
    for c in courts:
        for t in slot_mins[:-1]:
            terms_here = []
            for p_idx, p in enumerate(parts):
                for s in allowed_starts[p_idx]:
                    if s <= t < s + p["duration"]:
                        terms_here.append(x[(p_idx, s, c)])
            total_occ_terms.extend(terms_here)
            if t < 12 * 60:
                morning_occ_terms.extend(terms_here)

    early_start_bonus = []
    for p_idx, p in enumerate(parts):
        for s in allowed_starts[p_idx]:
            if p.get("is_youth_team"):
                # Jeugd: bonus voor starts 09:00-14:00; geen bonus voor 08:30 (te vroeg → gaten)
                if s < 9 * 60:
                    continue
                bonus = max(0, (14 * 60 - s))
            else:
                bonus = max(0, (18 * 60 - s))
            for c in courts:
                early_start_bonus.append(bonus * x[(p_idx, s, c)])

    # soft bonus: each team prefers at least one start before cutoff
    team_cutoff_bonus = []
    for team, idxs in by_team.items():
        has_early = model.new_bool_var(f"has_early_{abs(hash(team))%10_000_000}")
        early_terms = []
        for i in idxs:
            for s in allowed_starts[i]:
                if s <= first_cutoff:
                    for c in courts:
                        early_terms.append(x[(i, s, c)])
        if early_terms:
            model.add(sum(early_terms) >= 1).only_enforce_if(has_early)
            model.add(sum(early_terms) == 0).only_enforce_if(has_early.Not())
            team_cutoff_bonus.append(has_early)

    # soft bonus: teams met weinig vrije banen op hun eerste haalbare moment
    # krijgen een bonus als hun eerste gestarte partij dubbels/GD is i.p.v.
    # singles (planningsregels.md extra startregel, als zachte voorkeur).
    doubles_first_bonus = []
    for team, idxs in by_team.items():
        team_is_mixed_pref = parts[idxs[0]].get("is_mixed_team", False) if idxs else False
        non_s_parts_pref = [i for i in idxs if parts[i]["kind"] != "S"]
        s_parts_pref = [i for i in idxs if parts[i]["kind"] == "S"]
        if team_is_mixed_pref or not non_s_parts_pref or not s_parts_pref:
            continue
        earliest_candidates = [min(allowed_starts[i]) for i in idxs if allowed_starts[i]]
        earliest_start = min(earliest_candidates) if earliest_candidates else start_min
        free_at_earliest = free_static_courts_at(earliest_start)
        if free_at_earliest > 2:
            continue
        first_is_doubles = model.new_bool_var(f"first_doubles_{abs(hash(team))%10_000_000}")
        earliest_doubles_terms = []
        for i in non_s_parts_pref:
            for s in allowed_starts[i]:
                if s == earliest_start:
                    for c in courts:
                        earliest_doubles_terms.append(x[(i, s, c)])
        if earliest_doubles_terms:
            model.add(sum(earliest_doubles_terms) >= 1).only_enforce_if(first_is_doubles)
            model.add(sum(earliest_doubles_terms) == 0).only_enforce_if(first_is_doubles.Not())
            doubles_first_bonus.append(first_is_doubles)

    # team-first compactness: teams kiezen klein court-budget + zo klein mogelijke span/slack
    team_block_rises = []
    long_gap_team_penalty = []
    team_court_penalty = []
    team_court_spread_penalty = []  # adjacency: prefer courts close together per team
    high_court_penalty = []
    team_span_penalty = []
    team_span_slack_penalty = []
    horizon = slot_mins[:-1]
    for team, idxs in by_team.items():
        active_vars = []
        for t in horizon:
            occ_terms = []
            for i in idxs:
                for s in allowed_starts[i]:
                    if s <= t < s + parts[i]["duration"]:
                        for c in courts:
                            occ_terms.append(x[(i, s, c)])
            a = model.new_bool_var(f"team_active_{abs(hash(team))%10_000_000}_t{t}")
            if occ_terms:
                model.add(sum(occ_terms) >= 1).only_enforce_if(a)
                model.add(sum(occ_terms) == 0).only_enforce_if(a.Not())
            else:
                model.add(a == 0)
            active_vars.append(a)

        team_rises = []
        for k in range(1, len(active_vars)):
            prev_a = active_vars[k - 1]
            cur_a = active_vars[k]
            rise = model.new_bool_var(f"team_rise_{abs(hash(team))%10_000_000}_{k}")
            model.add(rise >= cur_a - prev_a)
            model.add(rise <= cur_a)
            model.add(rise <= 1 - prev_a)
            team_block_rises.append(rise)
            team_rises.append(rise)

        # Harde compactheidseis: maximaal 2 speelblokken per teamdag.
        # De team-first objective moet hem daarna richting 1 blok duwen.
        if team_rises:
            model.add(active_vars[0] + sum(team_rises) <= 2)

            # Soft indicator voor extra fragmentatie.
            long_gap = model.new_bool_var(f"team_long_gap_{abs(hash(team))%10_000_000}")
            model.add(sum(team_rises) >= 2).only_enforce_if(long_gap)
            model.add(sum(team_rises) <= 1).only_enforce_if(long_gap.Not())
            long_gap_team_penalty.append(long_gap)

        # Team-first: kies een klein court-budget per team én banen dicht bij elkaar.
        # Hard constraint: team mag alleen op één baan-paar spelen (1+2, 3+4, 5+6, 7+8, 9+10).
        team_meta = team_meta_by_key.get(team)
        preferred_courts = estimate_parallel_capacity(team_meta) if team_meta else 2

        # Kies welk paar dit team gebruikt (one-of-pairs).
        pair_vars = []
        for pi, (ca, cb) in enumerate(COURT_PAIRS):
            pair_active = model.new_bool_var(f"team_{abs(hash(team))%10_000_000}_pair{pi}")
            pair_vars.append((pair_active, ca, cb))
            # Als dit paar niet actief is: geen wedstrijden op deze banen.
            for i in idxs:
                for s in allowed_starts[i]:
                    for c in [ca, cb]:
                        model.add(x[(i, s, c)] <= pair_active)
        # Precies één paar actief (hard).
        model.add(sum(pv for pv, _, _ in pair_vars) == 1)
        # Penalty: liever geen extra banen buiten het paar (al afgedwongen door hard constraint).
        use_courts = []
        for c in courts:
            use_c = model.new_bool_var(f"team_{abs(hash(team))%10_000_000}_use_c{c}")
            for i in idxs:
                for s in allowed_starts[i]:
                    model.add(x[(i, s, c)] <= use_c)
            use_courts.append(use_c)
        if use_courts:
            used_courts = sum(use_courts)
            model.add(used_courts <= 2)
            excess_courts = model.new_int_var(0, 2, f"team_{abs(hash(team))%10_000_000}_excess_courts")
            model.add(excess_courts >= used_courts - preferred_courts)
            model.add(excess_courts >= 0)
            team_court_penalty.append(excess_courts)

            # Adjacency: penalize non-adjacent court pairs (spread = max_court - min_court).
            # Use sentinel values so unused courts don't constrain min/max.
            min_cand = []
            max_cand = []
            for c, use_c in zip(courts, use_courts):
                min_v = model.new_int_var(1, 11, f"team_{abs(hash(team))%10_000_000}_mincand_c{c}")
                max_v = model.new_int_var(0, 10, f"team_{abs(hash(team))%10_000_000}_maxcand_c{c}")
                model.add(min_v == c).only_enforce_if(use_c)
                model.add(min_v == 11).only_enforce_if(use_c.Not())
                model.add(max_v == c).only_enforce_if(use_c)
                model.add(max_v == 0).only_enforce_if(use_c.Not())
                min_cand.append(min_v)
                max_cand.append(max_v)

            min_used = model.new_int_var(1, 11, f"team_{abs(hash(team))%10_000_000}_min_used")
            max_used = model.new_int_var(0, 10, f"team_{abs(hash(team))%10_000_000}_max_used")
            model.add_min_equality(min_used, min_cand)
            model.add_max_equality(max_used, max_cand)

            spread_raw = model.new_int_var(-11, 9, f"team_{abs(hash(team))%10_000_000}_spread_raw")
            model.add(spread_raw == max_used - min_used)
            spread = model.new_int_var(0, 9, f"team_{abs(hash(team))%10_000_000}_spread")
            has_two = model.new_bool_var(f"team_{abs(hash(team))%10_000_000}_has_two_courts")
            model.add(used_courts >= 2).only_enforce_if(has_two)
            model.add(used_courts <= 1).only_enforce_if(has_two.Not())
            model.add(spread == spread_raw).only_enforce_if(has_two)
            model.add(spread == 0).only_enforce_if(has_two.Not())
            team_court_spread_penalty.append(spread)

        # Team-first: minimaliseer teamspan én vooral slack boven theoretisch minimum.
        team_starts = []
        team_ends = []
        for i in idxs:
            start_i = model.new_int_var(start_min, end_min, f"team_{abs(hash(team))%10_000_000}_start_{i}")
            end_i = model.new_int_var(start_min, end_min + 180, f"team_{abs(hash(team))%10_000_000}_end_{i}")
            model.add(
                start_i
                == sum(s * x[(i, s, c)] for s in allowed_starts[i] for c in courts)
                + end_min * (1 - y[i])
            )
            model.add(
                end_i
                == sum((s + parts[i]["duration"]) * x[(i, s, c)] for s in allowed_starts[i] for c in courts)
                + start_min * (1 - y[i])
            )
            team_starts.append(start_i)
            team_ends.append(end_i)
        if team_starts and team_ends:
            team_has_any = model.new_bool_var(f"team_{abs(hash(team))%10_000_000}_has_any")
            model.add(sum(y[i] for i in idxs) >= 1).only_enforce_if(team_has_any)
            model.add(sum(y[i] for i in idxs) == 0).only_enforce_if(team_has_any.Not())

            team_start = model.new_int_var(start_min, end_min, f"team_{abs(hash(team))%10_000_000}_start")
            team_end = model.new_int_var(start_min, end_min + 180, f"team_{abs(hash(team))%10_000_000}_end")
            model.add_min_equality(team_start, team_starts)
            model.add_max_equality(team_end, team_ends)
            span = model.new_int_var(0, end_min - start_min + 180, f"team_{abs(hash(team))%10_000_000}_span")
            model.add(span == team_end - team_start).only_enforce_if(team_has_any)
            model.add(span == 0).only_enforce_if(team_has_any.Not())
            team_span_penalty.append(span)

            total_duration = sum(parts[i]["duration"] for i in idxs)
            min_span_lb = max(
                max(parts[i]["duration"] for i in idxs),
                ((total_duration + 15 * preferred_courts - 1) // (15 * preferred_courts)) * 15,
            )
            slack = model.new_int_var(0, end_min - start_min + 180, f"team_{abs(hash(team))%10_000_000}_slack")
            model.add(slack == span - min_span_lb).only_enforce_if(team_has_any)
            model.add(slack == 0).only_enforce_if(team_has_any.Not())
            team_span_slack_penalty.append(slack)

        # Soft: alle teams bij voorkeur op lage banen (1-4); 8-wedstrijden-teams extra zwaar.
        if any(parts[i].get("duration") for i in idxs):
            team_matches = team_meta_by_key[team].matches if team in team_meta_by_key else None
            weight_mult = 2 if team_matches == 8 else 1
            for i in idxs:
                for s in allowed_starts[i]:
                    for c in courts:
                        if c > 4:
                            for _ in range(weight_mult):
                                high_court_penalty.append(x[(i, s, c)])

    # comfort-pass penalties: late starts, extra streng voor jeugd/groen
    late_start_penalty = []
    youth_late_penalty = []
    junioren_early_bonus = []  # Junioren (11-14) prefer early (08:30-11:00)
    jeugd_middag_penalty = []  # Jeugd (13-17) avoid too early (<11:00)
    
    for p_idx, p in enumerate(parts):
        team_l = p["team"].lower()
        is_junioren = "junioren" in team_l  # 11-14 jaar
        is_jeugd_1317 = ("jongens 13 t/m 17" in team_l) or ("meisjes 13 t/m 17" in team_l)
        is_youth = is_junioren or is_jeugd_1317 or ("groen zondag" in team_l)
        
        for s in allowed_starts[p_idx]:
            for c in courts:
                # Late start penalties (everyone)
                if s > 19 * 60 + 30:
                    late_start_penalty.append(x[(p_idx, s, c)])
                if is_youth and s > 17 * 60:
                    youth_late_penalty.append(x[(p_idx, s, c)])
                
                # Age-based start time preferences
                if is_junioren:
                    # Junioren (11-14): bonus voor vroeg (08:30-11:00)
                    if s <= 11 * 60:
                        junioren_early_bonus.append(x[(p_idx, s, c)])
                
                if is_jeugd_1317:
                    # Jeugd (13-17): penalty voor té vroeg (<11:00)
                    # Prefer middag (11:00-15:00)
                    if s < 11 * 60:
                        # Linear penalty: hoe vroeger, hoe erger
                        # 08:30 = 510 min → penalty × 5
                        # 09:00 = 540 min → penalty × 4
                        # 10:30 = 630 min → penalty × 1
                        early_minutes = 11 * 60 - s
                        penalty_mult = (early_minutes + 29) // 30  # Per 30 min vroeger
                        for _ in range(penalty_mult):
                            jeugd_middag_penalty.append(x[(p_idx, s, c)])

    model.maximize(
        scheduled_score
        # Team-first compactness first: contiguous day, tiny slack, tiny span, few courts.
        - w_block_rise * sum(team_block_rises)
        - w_long_gap * sum(long_gap_team_penalty)
        - (w_team_span * 4) * sum(team_span_slack_penalty)
        - w_team_span * sum(team_span_penalty)
        - w_team_court_penalty * sum(team_court_penalty)
        - (w_team_court_penalty // 3) * sum(team_court_spread_penalty)
        - w_high_court_penalty * sum(high_court_penalty)
        # Occupancy optimization:
        + w_morning_occ * sum(morning_occ_terms)
        + w_total_occ * sum(total_occ_terms)
        # Comfort preferences:
        + w_cutoff_bonus * sum(team_cutoff_bonus)
        + 40_000 * sum(doubles_first_bonus)  # Extra startregel: 1-2 banen vrij -> D/GD eerst (soft)
        + w_early_start * sum(early_start_bonus)
        - w_late_start * sum(late_start_penalty)
        - w_youth_late * sum(youth_late_penalty)
        # Age-based start time preferences:
        + 300_000 * sum(junioren_early_bonus)  # Junioren vroeg = goed (3x verhoogd)
        - 5_000_000 * sum(jeugd_middag_penalty)  # Jeugd (13-17) vroeg = ZEER ZEER SLECHT (10x original!)
        # Fasering (SPEC.md sectie 5, besluit 2026-08-26): voor niet-8-partijenteams
        # is de S->D->GD-waterval een zachte voorkeur i.p.v. een harde eis.
        - w_fasering_soft * sum(fasering_soft_penalty)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = random_seed

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
                            "team_id": p["team_key"],  # unique per (day, schema, home)
                            "home_team": p.get("home_team", ""),
                            "away_team": p.get("away_team", ""),
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
                    "team_id": p["team_key"],  # unique per (day, schema, home)
                    "home_team": p.get("home_team", ""),
                    "away_team": p.get("away_team", ""),
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
    ap.add_argument("--out", type=Path, default=None, help="Output JSON path (default: docs/ortools_<date>.json)")
    ap.add_argument("--w-block-rise", type=int, default=4_000_000)
    ap.add_argument("--w-long-gap", type=int, default=5_000_000)
    ap.add_argument("--w-morning-occ", type=int, default=600_000)
    ap.add_argument("--w-total-occ", type=int, default=80_000)
    ap.add_argument("--w-cutoff-bonus", type=int, default=5000)
    ap.add_argument("--w-early-start", type=int, default=100)
    ap.add_argument("--w-late-start", type=int, default=120_000)
    ap.add_argument("--w-youth-late", type=int, default=80_000)
    ap.add_argument("--w-team-court-penalty", type=int, default=150_000)
    ap.add_argument("--w-high-court-penalty", type=int, default=80_000)
    ap.add_argument("--w-team-span", type=int, default=200_000)
    ap.add_argument("--w-fasering-soft", type=int, default=300_000)
    ap.add_argument("--random-seed", type=int, default=42)
    args = ap.parse_args()

    # Default output path: docs/ortools_<date>.json
    if args.out is None:
        args.out = ROOT / "docs" / f"ortools_{args.date}.json"

    teams, res = parse_input(args.input)
    result = solve_day(
        args.date,
        teams,
        res,
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
        w_fasering_soft=args.w_fasering_soft,
        random_seed=args.random_seed,
        two_phase=False,  # Default: single-phase (better age-based spreading)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Status: {result['status']}")
    print(f"Rows: {len(result['rows'])}")
    if "objective" in result:
        print(f"Objective: {result['objective']:.1f}")


if __name__ == "__main__":
    main()
