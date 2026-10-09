"""Generieke CP-SAT-planner voor één speeldag.

Gebaseerd op de ideeën van ``scripts/ortools_planner.py`` (dat bestand blijft
ongewijzigd en blijft de live stack voeden). Verschillen:

- aantal banen, dagtijden, reserveringen, court-pairs en regels komen uit het
  clubprofiel — geen clubnamen of vaste banen in de code;
- Rood/Oranje zonder vaste reservering krijgen solver-gekozen banen;
- harde/zachte regels zijn per club te schakelen.

Zie ``README.md`` voor wat (nog) niet geport is.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model

from baanschema.rules import build_parts, player_demand  # pure regels, gedeeld met de bestaande stack
from baanschemaatje.categories import DEFAULT_PRIORITY, JUNIOR_CATEGORIES, YOUTH_CATEGORIES, Category
from baanschemaatje.profile import ClubProfile, min_to_hhmm
from baanschemaatje.season import Fixture

GRID = 15
UNSCHEDULED = "NIET_GELUKT"


@dataclass
class PlanResult:
    club: str
    date: str
    courts: int
    status: str
    day_start: str
    rows: list[dict[str, Any]]
    solve_time_s: float
    attempts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def scheduled(self) -> int:
        return sum(1 for r in self.rows if r["kind"] != "W" and r["start"] != UNSCHEDULED)

    @property
    def unscheduled(self) -> int:
        return sum(1 for r in self.rows if r["start"] == UNSCHEDULED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generator": "baanschemaatje",
            "club": self.club,
            "date": self.date,
            "courts": self.courts,
            "status": self.status,
            "day_start": self.day_start,
            "stats": {
                "scheduled": self.scheduled,
                "unscheduled": self.unscheduled,
                "solve_time_s": round(self.solve_time_s, 2),
            },
            "attempts": self.attempts,
            "rows": self.rows,
        }


def plan_day(
    profile: ClubProfile,
    fixtures: list[Fixture],
    date: str,
    time_limit_s: float = 20.0,
    random_seed: int = 42,
    workers: int = 8,
    fit_check: bool = True,
) -> PlanResult:
    """Plan één speeldag. Probeert ``day.start``; valt terug op
    ``day.fallback_start`` als er partijen onplanbaar blijven (SPEC-core §2).

    ``fit_check``: blijven er partijen over, dan zoekt een tweede ronde puur
    naar een oplossing waarin álles past (feasibility) en verfijnt die daarna
    met de zachte doelen. Het gewogen model vindt zo'n oplossing op krappe
    dagen niet altijd binnen de tijdslimiet."""
    day = [f for f in fixtures if f.date == date]
    t0 = time.perf_counter()
    attempts = []
    best: tuple[str, list[dict], int] | None = None
    starts = [profile.day_start]
    if profile.fallback_start is not None and profile.fallback_start < profile.day_start:
        starts.append(profile.fallback_start)
    for ds in starts:
        status, rows = _solve(profile, day, date, ds, time_limit_s, random_seed, workers)
        ng = sum(1 for r in rows if r["start"] == UNSCHEDULED)
        attempts.append({"day_start": min_to_hhmm(ds), "mode": "optimize", "status": status, "unscheduled": ng})
        if fit_check and ng and status in ("OPTIMAL", "FEASIBLE"):
            fst, frows = _solve(profile, day, date, ds, time_limit_s, random_seed, workers, mode="feasibility")
            attempts.append({"day_start": min_to_hhmm(ds), "mode": "feasibility", "status": fst,
                             "unscheduled": 0 if frows else None})
            if frows:
                hint = {(r["team_id"], r["part"]): (_hm(r["start"]), r["court"]) for r in frows if r["kind"] != "W"}
                ost, orows = _solve(profile, day, date, ds, time_limit_s, random_seed, workers, mode="fit", hint=hint)
                attempts.append({"day_start": min_to_hhmm(ds), "mode": "fit", "status": ost, "unscheduled": 0 if orows else None})
                status, rows, ng = (ost, orows, 0) if orows else (fst, frows, 0)
        ok = status in ("OPTIMAL", "FEASIBLE")
        if ok and (best is None or ng < sum(1 for r in best[1] if r["start"] == UNSCHEDULED)):
            best = (status, rows, ds)
        if ok and ng == 0:
            break
    elapsed = time.perf_counter() - t0
    if best is None:
        return PlanResult(profile.name, date, profile.courts, attempts[-1]["status"], min_to_hhmm(starts[-1]), [], elapsed, attempts)
    status, rows, ds = best
    return PlanResult(profile.name, date, profile.courts, status, min_to_hhmm(ds), rows, elapsed, attempts)


def _hm(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def _block_courts(profile: ClubProfile, f: Fixture, cats_today: set[Category]) -> tuple[int, ...] | None:
    res = profile.reservations.get(f.category)
    if res is None:
        return None
    if f.category == Category.ORANJE and Category.ROOD in cats_today and res.courts_if_rood:
        return res.courts_if_rood
    return res.courts


def _lb(r) -> int:
    return r.params.get("from", r.params.get("time"))


def _lower_bound_rules(R, f: Fixture) -> list:
    """Regels 'niet vóór X' — gelden voor élke partij van het team."""
    out = [R["match_start_window"]]  # CR B3 1.1: niet vroeger dan 08:30
    if f.is_8p:
        out.append(R["start_window_8p"])
    if f.is_8p and f.is_mixed:
        out.append(R["mixed_8p_not_before"])
    if f.category in JUNIOR_CATEGORIES:
        out.append(R["junioren_start_window"])  # CR B3 1.1.a
    rt = R["travel_not_before"]
    if f.travel_km is not None and f.travel_km >= rt.params["value"]:
        out.append(rt)  # CR B3 1.2
    return out


def _upper_bound_rules(R, f: Fixture) -> list:
    """Regels 'begintijd uiterlijk X' — gelden voor de eerste partij."""
    out = [(R["match_start_window"], R["match_start_window"].params["to"])]  # CR B3 1.1
    out.append((R["first_start_deadline"], R["first_start_deadline"].params["time"]))
    junior = f.category in JUNIOR_CATEGORIES
    if f.is_8p:
        out.append((R["start_window_8p"], R["start_window_8p"].params["to"]))
    if f.is_8p and f.is_mixed and not junior:
        out.append((R["mixed_8p_latest_start"], R["mixed_8p_latest_start"].params["time"]))  # CR B3 1.1.b
    if junior:
        out.append((R["junioren_start_window"], R["junioren_start_window"].params["to"]))  # CR B3 1.1.a
        out.append((R["junioren_latest_start"], R["junioren_latest_start"].params["time"]))
        if f.is_8p and f.is_mixed:
            out.append((R["junioren_mixed_8p_latest_start"], R["junioren_mixed_8p_latest_start"].params["time"]))
    return out


def _solve(
    profile: ClubProfile,
    day: list[Fixture],
    date: str,
    day_start: int,
    time_limit_s: float,
    random_seed: int,
    workers: int,
    mode: str = "optimize",
    hint: dict[tuple[str, str], tuple[int, int]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """mode: "optimize" (max ingepland + zachte doelen), "feasibility" (alles
    verplicht, geen doel) of "fit" (alles verplicht + zachte doelen).
    hint: (team_key, partlabel) -> (start, baan) als startoplossing."""
    R = profile.rules
    end = profile.day_end
    slots = list(range(day_start, end, GRID))  # begintijden van kwartierslots
    courts = profile.court_list
    model = cp_model.CpModel()

    # ---------- Rood/Oranje: blokken vanaf dagstart ----------
    cats_today = {f.category for f in day}
    block_occ: dict[tuple[int, int], list] = defaultdict(list)  # (court, slot) -> vars/consts
    blocks = []  # (fixture, start, end, {court: var|None})
    block_court_cost = []
    for f in (f for f in day if f.is_block):
        dur = profile.duration_for(f.category, f.export_duration)
        fixed = _block_courts(profile, f, cats_today)
        assign: dict[int, Any] = {}
        if fixed:
            for c in fixed:
                assign[c] = 1
        else:
            k = min(max(f.matches, 1), len(courts))
            bv = {c: model.new_bool_var(f"blk_{len(blocks)}_c{c}") for c in courts}
            model.add(sum(bv.values()) == k)
            assign = bv
            block_court_cost += [c * v for c, v in bv.items()]
        for c, v in assign.items():
            for t in slots:
                if day_start <= t < day_start + dur:
                    block_occ[(c, t)].append(v)
        blocks.append((f, day_start, day_start + dur, assign))

    # ---------- Partijen ----------
    teams = [f for f in day if not f.is_block]
    parts: list[dict[str, Any]] = []
    for f in teams:
        dur = profile.duration_for(f.category, f.export_duration)
        for label, kind in build_parts(f):
            m, w, tot = player_demand(f.schema, label, kind)
            parts.append(dict(f=f, label=label, kind=kind, dur=dur, male=m, female=w, total=tot))

    x: dict[tuple[int, int, int], cp_model.IntVar] = {}
    start_used: dict[tuple[int, int], Any] = {}
    y: list[Any] = []
    allowed: dict[int, list[int]] = {}
    for i, p in enumerate(parts):
        f: Fixture = p["f"]
        # CR Bijlage 3, 2.1.c: laatste partij start uiterlijk 19:30 (day.last_start).
        st = [s for s in slots if s + p["dur"] <= end and s <= profile.last_start]
        for r in _lower_bound_rules(R, f):
            if r.hard:
                st = [s for s in st if s >= _lb(r)]
        r = R["youth_last_start"]
        if r.hard and f.category in YOUTH_CATEGORIES:
            st = [s for s in st if s <= r.params["time"]]
        allowed[i] = st
        vs = []
        for s in st:
            row = []
            for c in courts:
                v = model.new_bool_var(f"x{i}_{s}_{c}")
                x[(i, s, c)] = v
                row.append(v)
            su = model.new_bool_var(f"su{i}_{s}")
            model.add(sum(row) == su)
            start_used[(i, s)] = su
            vs.extend(row)
        yi = model.new_bool_var(f"y{i}")
        model.add(sum(vs) == yi)
        y.append(yi)

    def occ_at(i: int, t: int, c: int | None = None) -> list:
        out = []
        for s in allowed[i]:
            if s <= t < s + parts[i]["dur"]:
                if c is None:
                    out.append(start_used[(i, s)])
                else:
                    out.append(x[(i, s, c)])
        return out

    # ---------- Baancapaciteit (hard) ----------
    for c in courts:
        for t in slots:
            terms = [v for i in range(len(parts)) for v in occ_at(i, t, c)]
            terms += block_occ.get((c, t), [])
            if terms:
                model.add(sum(terms) <= 1)

    # ---------- Per team ----------
    by_team: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(parts):
        by_team[p["f"].team_key].append(i)

    obj_pen: list[Any] = []  # (gewicht * expr)
    obj_bonus: list[Any] = []
    pairs = profile.court_pairs

    for ti, (tk, idxs) in enumerate(by_team.items()):
        f: Fixture = parts[idxs[0]]["f"]
        h = f"t{ti}"
        s_p = [i for i in idxs if parts[i]["kind"] == "S"]
        d_p = [i for i in idxs if parts[i]["kind"] == "D"]
        m_p = [i for i in idxs if parts[i]["kind"] == "M"]
        non_s = [i for i in idxs if parts[i]["kind"] != "S"]
        is_mixed = f.is_mixed

        def before(a_list: list[int], b_list: list[int]) -> None:
            for a in a_list:
                da = parts[a]["dur"]
                for b in b_list:
                    for sa in allowed[a]:
                        for sb in allowed[b]:
                            if sb < sa + da:
                                model.add(start_used[(a, sa)] + start_used[(b, sb)] <= 1)

        def same_start(a: int, b: int) -> None:
            for sa in allowed[a]:
                for sb in allowed[b]:
                    if sa != sb:
                        model.add(start_used[(a, sa)] + start_used[(b, sb)] <= 1)

        # Waterval: singles eerst (hard voor niet-gemengde teams, zoals de
        # bestaande planner) en voor 8p-teams strikt S → D → GD met rondes.
        strict_8p = f.is_8p and R["waterfall_8p"].hard
        if (not is_mixed) or strict_8p:
            before(s_p, non_s)
            for lst in (s_p, d_p, m_p):
                for k in range(0, len(lst) - 1, 2):
                    same_start(lst[k], lst[k + 1])
        if strict_8p:
            before(d_p, m_p)

        # Spelers: max gelijktijdige partijen, max 4 spelers, gemengd 2H+2D.
        for t in slots:
            occ_parts, tot, men, women = [], [], [], []
            for i in idxs:
                o = occ_at(i, t)
                if not o:
                    continue
                so = sum(o)
                occ_parts.append(so)
                p = parts[i]
                if p["total"]:
                    tot.append(p["total"] * so)
                if p["male"]:
                    men.append(p["male"] * so)
                if p["female"]:
                    women.append(p["female"] * so)
            if occ_parts:
                model.add(sum(occ_parts) <= profile.max_courts_per_team)
            if tot:
                model.add(sum(tot) <= 4)
            if is_mixed:
                if men:
                    model.add(sum(men) <= 2)
                if women:
                    model.add(sum(women) <= 2)

        # Banen per team: max N, optioneel vaste paren, anders zo dicht mogelijk bij elkaar.
        use = {}
        for c in courts:
            u = model.new_bool_var(f"use_{h}_{c}")
            for i in idxs:
                for s in allowed[i]:
                    model.add(x[(i, s, c)] <= u)
            use[c] = u
        model.add(sum(use.values()) <= profile.max_courts_per_team)
        if pairs:
            pv = []
            in_pair = set()
            for k, (a, b) in enumerate(pairs):
                v = model.new_bool_var(f"pair_{h}_{k}")
                model.add(use[a] <= v)
                model.add(use[b] <= v)
                pv.append(v)
                in_pair |= {a, b}
            model.add(sum(pv) <= 1)
            for c in courts:
                if c not in in_pair:
                    model.add(use[c] == 0)
        else:
            mn = model.new_int_var(1, len(courts) + 1, f"mn_{h}")
            mx = model.new_int_var(0, len(courts), f"mx_{h}")
            for c in courts:
                model.add(mn <= c).only_enforce_if(use[c])
                model.add(mx >= c).only_enforce_if(use[c])
            spread = model.new_int_var(0, len(courts), f"spr_{h}")
            model.add(spread >= mx - mn)
            obj_pen.append(100_000 * spread)
        obj_pen.append(150_000 * sum(use.values()))

        # 8p-teams bij voorkeur op de voorkeursbanen.
        if f.is_8p and profile.preferred_courts_8p:
            outside = [c for c in courts if c not in profile.preferred_courts_8p]
            obj_pen.append(400_000 * sum(use[c] for c in outside))

        # Activiteit per slot → blokken en wachttijd.
        act = []
        for t in slots:
            o = [v for i in idxs for v in occ_at(i, t)]
            a = model.new_bool_var(f"act_{h}_{t}")
            if o:
                model.add(sum(o) >= 1).only_enforce_if(a)
                model.add(sum(o) == 0).only_enforce_if(a.Not())
            else:
                model.add(a == 0)
            act.append(a)
        rises = []
        for k in range(len(act)):
            r_ = model.new_bool_var(f"rise_{h}_{k}")
            prev = act[k - 1] if k else 0
            model.add(r_ >= act[k] - prev)
            model.add(r_ <= act[k])
            if k:
                model.add(r_ <= 1 - prev)
            rises.append(r_)
        rb = R["max_blocks_per_team"]
        if rb.hard:
            model.add(sum(rises) <= rb.params["value"])
        else:
            extra = model.new_int_var(0, len(rises), f"xb_{h}")
            model.add(extra >= sum(rises) - rb.params["value"])
            obj_pen.append(2_000_000 * extra)
        obj_pen.append(4_000_000 * sum(rises))

        rw = R["max_wait_minutes"]
        win = rw.params["value"] // GRID + 1  # lege slots die verboden zijn
        n = len(act)
        if n > win + 1:
            pre = [act[0]]
            for k in range(1, n):
                v = model.new_bool_var(f"pre_{h}_{k}")
                model.add_max_equality(v, [pre[-1], act[k]])
                pre.append(v)
            suf = [None] * n
            suf[-1] = act[-1]
            for k in range(n - 2, -1, -1):
                v = model.new_bool_var(f"suf_{h}_{k}")
                model.add_max_equality(v, [suf[k + 1], act[k]])
                suf[k] = v
            for t0 in range(1, n - win):
                clause = act[t0 : t0 + win] + [pre[t0 - 1].Not(), suf[t0 + win].Not()]
                if not rw.hard:
                    viol = model.new_bool_var(f"wait_{h}_{t0}")
                    clause.append(viol)
                    obj_pen.append(1_000_000 * viol)
                model.add_bool_or(clause)

        # Teamspan (compactheid).
        any_y = model.new_bool_var(f"any_{h}")
        model.add_max_equality(any_y, [y[i] for i in idxs])
        obj_pen.append(200_000 * sum(act))  # actieve slots ≈ span bij 1 blok

        # Begintijd van de wedstrijd (= eerste partij van het team).
        def early_terms(limit: int) -> list:
            return [start_used[(i, s)] for i in idxs for s in allowed[i] if s <= limit]

        for k, (r, limit) in enumerate(_upper_bound_rules(R, f)):
            et = early_terms(limit)
            if r.hard:
                if et:
                    model.add(sum(et) >= 1).only_enforce_if(any_y)
                else:
                    model.add(any_y == 0)
            elif et:
                ok = model.new_bool_var(f"ub_{h}_{k}")
                model.add(sum(et) >= 1).only_enforce_if(ok)
                obj_bonus.append(3_000_000 * ok)

        # CR Bijlage 3, 1.1: begintijd alleen op hele of halve uren. Een partij
        # mag op een ander kwartier starten zolang er al een eerdere partij van
        # hetzelfde team is gestart (dan is het niet de begintijd).
        rg = R["match_start_grid"]
        g = rg.params["value"]
        if g > GRID:
            for i in idxs:
                for s in allowed[i]:
                    if s % g == 0:
                        continue
                    earlier = [start_used[(j, s2)] for j in idxs for s2 in allowed[j] if s2 < s]
                    clause = [start_used[(i, s)].Not()] + earlier
                    if not rg.hard:
                        viol = model.new_bool_var(f"grid_{h}_{i}_{s}")
                        clause.append(viol)
                        obj_pen.append(1_000_000 * viol)
                    model.add_bool_or(clause)

        # Zachte varianten van ondergrenzen + inplanvolgorde (SPEC-core §4).
        prio = DEFAULT_PRIORITY[f.category]
        soft_lb = [_lb(r) for r in _lower_bound_rules(R, f) if not r.hard]
        ry = R["youth_last_start"]
        for i in idxs:
            for s in allowed[i]:
                su = start_used[(i, s)]
                # Inplanvolgorde: lagere prioriteit-rang krijgt de vroege slots.
                obj_pen.append(prio * ((s - day_start) // GRID) * 2_000 * su)
                if any(s < lb for lb in soft_lb):
                    obj_pen.append(500_000 * su)
                if (not ry.hard) and f.category in YOUTH_CATEGORIES and s > ry.params["time"]:
                    obj_pen.append(500_000 * su)

    # Gewogen "bijna-lexicografisch" doel: ingeplande partijen wegen 1e9,
    # zachte voorkeuren zijn kleiner. (Een echte twee-fasen-lexico is
    # geprobeerd: fase 1 met alléén het aantal partijen zocht trager, omdat de
    # zachte termen de zoektocht juist sturen. Zie README, "Nog niet geport".)
    if hint:
        for i, p in enumerate(parts):
            h_ = hint.get((p["f"].team_key, p["label"]))
            for s in allowed[i]:
                for c in courts:
                    model.add_hint(x[(i, s, c)], 1 if h_ == (s, c) else 0)
    if mode == "fit":
        model.add(sum(y) == len(y))
    if mode == "feasibility":
        # Past alles? Alle partijen verplicht, geen zachte doelen: CP-SAT zoekt
        # puur een haalbare oplossing of bewijst dat die niet bestaat.
        model.add(sum(y) == len(y))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_s
        solver.parameters.num_search_workers = workers
        solver.parameters.random_seed = random_seed
        st = solver.solve(model)
        status = solver.status_name(st)
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return status, []
        return status, _rows(solver, blocks, parts, allowed, courts, x)
    model.maximize(
        1_000_000_000 * sum(y)
        + sum(obj_bonus)
        - sum(obj_pen)
        - 1_000 * sum(block_court_cost)
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = random_seed
    st = solver.solve(model)
    status = solver.status_name(st)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return status, []

    return status, _rows(solver, blocks, parts, allowed, courts, x)


def _rows(solver, blocks, parts, allowed, courts, x) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for f, bs, be, assign in blocks:
        for c, v in sorted(assign.items()):
            if (v == 1) if isinstance(v, int) else solver.value(v):
                rows.append(_row(f, "", "W", min_to_hhmm(bs), min_to_hhmm(be), c))
    for i, p in enumerate(parts):
        placed = False
        for s in allowed[i]:
            for c in courts:
                if solver.value(x[(i, s, c)]):
                    rows.append(_row(p["f"], p["label"], p["kind"], min_to_hhmm(s), min_to_hhmm(s + p["dur"]), c))
                    placed = True
        if not placed:
            rows.append(_row(p["f"], p["label"], p["kind"], UNSCHEDULED, "", None))
    rows.sort(key=lambda r: (r["start"], r["court"] or 99, r["team"], r["part"]))
    return rows


def _row(f: Fixture, part: str, kind: str, start: str, end: str, court: int | None) -> dict[str, Any]:
    # Zelfde rij-formaat als scripts/ortools_planner.py, zodat de bestaande
    # validator (scripts/validate_schedule.py) de output kan lezen.
    return {
        "team": f.schema,
        "team_id": f.team_key,
        "home_team": f.home_team,
        "away_team": f.away_team,
        "category": f.category.value,
        "label": f.label,
        "part": part,
        "kind": kind,
        "start": start,
        "end": end,
        "court": court,
    }
