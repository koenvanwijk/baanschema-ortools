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


def player_demand(schema: str, label: str, kind: str) -> tuple[int, int, int]:
    """Return (male, female, total) player demand for one match part.

    For non-mixed teams we only enforce total<=4.
    For mixed teams we enforce male<=2, female<=2, total<=4.
    """
    s = (schema or "").lower()
    is_mixed = "gemengd zondag" in s

    # Generic fallback (non-mixed or unknown part): S=1, D/M=2
    if not is_mixed:
        if kind == "S":
            return (0, 0, 1)
        if kind in {"D", "M"}:
            return (0, 0, 2)
        return (0, 0, 0)

    # Mixed team specifics
    # GD always 1 man + 1 woman
    if label.startswith("GD") or kind == "M":
        return (1, 1, 2)

    # Singles mapping by known mixed schemas
    if label.startswith("S"):
        idx = int(label[1:]) if label[1:].isdigit() else 1
        if "2de-2he" in s:
            # convention: S1,S2=DE ; S3,S4=HE
            return (0, 1, 1) if idx <= 2 else (1, 0, 1)
        if "de-he" in s:
            # convention: S1=DE ; S2=HE
            return (0, 1, 1) if idx == 1 else (1, 0, 1)
        # Unknown mixed schema: keep total only
        return (0, 0, 1)

    # Doubles mapping by known mixed schemas
    if label.startswith("D") or kind == "D":
        idx = int(label[1:]) if label[1:].isdigit() else 1
        if "dd-hd" in s:
            # convention: D1=DD ; D2=HD
            return (0, 2, 2) if idx == 1 else (2, 0, 2)
        # Unknown mixed schema: keep total only
        return (0, 0, 2)

    return (0, 0, 0)


def mins_to_hhmm(m: int) -> str:
    return f"{m//60:02d}:{m%60:02d}"


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
    w_high_court_penalty: int = 80_000,
    random_seed: int = 42,
) -> dict:
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
    kinds_today = {r.kind for r in day_res}
    for r in day_res:
        if r.kind == "oranje":
            for c in [1, 2, 3]:
                reserved.append((c, 8 * 60 + 30, 10 * 60 + 30))
        elif r.kind == "rood":
            rood_court = 4 if "oranje" in kinds_today else 1
            reserved.append((rood_court, 8 * 60 + 30, 9 * 60 + 30))

    parts = []
    for t in day_teams:
        for label, kind in build_parts(t):
            tl = t.schema.lower()
            male_d, female_d, total_d = player_demand(t.schema, label, kind)
            parts.append(
                {
                    "team": t.schema,
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
        if p["is_mixed_team"]:
            starts = [m for m in starts if m >= 10 * 60]
        # Hard cap: jeugd/groen geen starts na 17:30
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

    # S and D cannot overlap within same team (M can overlap)
    by_team = defaultdict(list)
    for i, p in enumerate(parts):
        by_team[p["team"]].append(i)

    for team, idxs in by_team.items():
        s_parts = [i for i in idxs if parts[i]["kind"] == "S"]
        d_parts = [i for i in idxs if parts[i]["kind"] == "D"]
        m_parts = [i for i in idxs if parts[i]["kind"] == "M"]
        combo_parts = [i for i in idxs if parts[i].get("is_4p_combo")]
        non_s_parts = [i for i in idxs if parts[i]["kind"] != "S"]

        # Singles moeten altijd vóór andere wedstrijden voor hetzelfde team.
        for si in s_parts:
            dur_s = parts[si]["duration"]
            for ni in non_s_parts:
                for s_s in allowed_starts[si]:
                    for s_n in allowed_starts[ni]:
                        if s_n < s_s + dur_s:
                            model.add(start_used[(si, s_s)] + start_used[(ni, s_n)] <= 1)

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

            # Singles en dubbels mogen niet tegelijk.
            if s_parts and d_parts:
                z_sd = model.new_bool_var(f"team_{abs(hash(team))%10_000_000}_t{t}_sd_mode")
                model.add(s_sum <= 10 * z_sd)
                model.add(d_sum <= 10 * (1 - z_sd))

            # Gemengd dubbel (M/GD) en dubbel mogen niet tegelijk.
            if m_parts and d_parts:
                z_md = model.new_bool_var(f"team_{abs(hash(team))%10_000_000}_t{t}_md_mode")
                model.add(m_sum <= 10 * z_md)
                model.add(d_sum <= 10 * (1 - z_md))

            # Voor 2DE-2HE-DD-HD-2GD-teams: singles en GD ook niet tegelijk (4-spelers team).
            if combo_parts and s_parts and m_parts:
                z_sm = model.new_bool_var(f"team_{abs(hash(team))%10_000_000}_t{t}_sm_mode")
                model.add(s_sum <= 10 * z_sm)
                model.add(m_sum <= 10 * (1 - z_sm))

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

    # NOTE: first-match cutoff is treated as soft preference in OR mode.
    # Hard enforcement made several days infeasible; we keep it in the objective instead.

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
            # higher bonus for earlier starts
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

    # soft penalty: aantal activity-blocks per team minimaliseren (minder lange gaten)
    team_block_rises = []
    long_gap_team_penalty = []
    team_court_penalty = []
    high_court_penalty = []
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
        # Blokken = start van activiteit op dagstart + 0->1 overgangen.
        if team_rises:
            model.add(active_vars[0] + sum(team_rises) <= 2)

            # Extra soft indicator voor sterk gefragmenteerde teamdag (moet idealiter 0 blijven)
            long_gap = model.new_bool_var(f"team_long_gap_{abs(hash(team))%10_000_000}")
            model.add(sum(team_rises) >= 3).only_enforce_if(long_gap)
            model.add(sum(team_rises) <= 2).only_enforce_if(long_gap.Not())
            long_gap_team_penalty.append(long_gap)

        # Soft: houd teams zoveel mogelijk op dezelfde banen.
        use_courts = []
        for c in courts:
            use_c = model.new_bool_var(f"team_{abs(hash(team))%10_000_000}_use_c{c}")
            for i in idxs:
                for s in allowed_starts[i]:
                    model.add(x[(i, s, c)] <= use_c)
            use_courts.append(use_c)
        if use_courts:
            model.add(sum(use_courts) <= 2)
            team_court_penalty.append(sum(use_courts))

        # Soft: teams met 8 wedstrijden bij voorkeur op lage banen (1-4).
        if any(parts[i].get("team") == team and parts[i].get("duration") for i in idxs):
            team_matches = next((t.matches for t in day_teams if t.schema == team), None)
            if team_matches == 8:
                for i in idxs:
                    for s in allowed_starts[i]:
                        for c in courts:
                            if c > 4:
                                high_court_penalty.append(x[(i, s, c)])

    # comfort-pass penalties: late starts, extra streng voor jeugd/groen
    late_start_penalty = []
    youth_late_penalty = []
    for p_idx, p in enumerate(parts):
        team_l = p["team"].lower()
        is_youth = ("junioren" in team_l) or ("jongens 13 t/m 17" in team_l) or ("meisjes 13 t/m 17" in team_l) or ("groen zondag" in team_l)
        for s in allowed_starts[p_idx]:
            for c in courts:
                if s > 19 * 60 + 30:
                    late_start_penalty.append(x[(p_idx, s, c)])
                if is_youth and s > 17 * 60:
                    youth_late_penalty.append(x[(p_idx, s, c)])

    model.maximize(
        scheduled_score
        # Team compactness: minimize fragmentation and gaps
        # (removed explicit span penalty for now - active_var sum not reliable proxy)
        - w_block_rise * sum(team_block_rises)
        - w_long_gap * sum(long_gap_team_penalty)
        - w_team_court_penalty * sum(team_court_penalty)
        - w_high_court_penalty * sum(high_court_penalty)
        # Occupancy optimization:
        + w_morning_occ * sum(morning_occ_terms)
        + w_total_occ * sum(total_occ_terms)
        # Comfort preferences:
        + w_cutoff_bonus * sum(team_cutoff_bonus)
        + w_early_start * sum(early_start_bonus)
        - w_late_start * sum(late_start_penalty)
        - w_youth_late * sum(youth_late_penalty)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 1
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
                            "team_id": p["team"],  # Add team_id for proper grouping
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
                    "team_id": p["team"],  # Add team_id for proper grouping
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
    ap.add_argument("--random-seed", type=int, default=42)
    args = ap.parse_args()

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
        random_seed=args.random_seed,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Status: {result['status']}")
    print(f"Rows: {len(result['rows'])}")
    if "objective" in result:
        print(f"Objective: {result['objective']:.1f}")


if __name__ == "__main__":
    main()
