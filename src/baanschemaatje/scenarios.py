"""Oplossingen voorstellen als een speeldag niet past.

Draait what-if-scenario's met de generieke planner: steeds één versoepeling
(een clubafspraak, een productdefault, een andere dagstart, ...) en rangschikt de uitkomsten. Een voorstel dat het KNLTB-
reglement zou overtreden, wordt alleen als referentiepunt getoond.

Scenario's worden generiek afgeleid uit clubprofiel + speeldag; er staan geen
clubnamen of vaste waarden in deze module.
"""

from __future__ import annotations

import dataclasses
import itertools
from dataclasses import dataclass
from typing import Any, Callable

from baanschemaatje.categories import JUNIOR_CATEGORIES, YOUTH_CATEGORIES, Category
from baanschemaatje.knltb import knltb_findings
from baanschemaatje.planner import plan_day
from baanschemaatje.profile import ClubProfile, Rule, min_to_hhmm
from baanschemaatje.season import Fixture

Transform = Callable[[ClubProfile, list[Fixture]], tuple[ClubProfile, list[Fixture]]]

# KNLTB-grenzen (CR Bijlage 3) die een club maximaal mag benutten.
KNLTB_MAX_START = 16 * 60 + 30
KNLTB_MIXED_8P_MAX = 14 * 60
KNLTB_JUNIOR_MAX = 15 * 60
KNLTB_LAST_START = 19 * 60 + 30
KNLTB_EARLIEST = 8 * 60 + 30


@dataclass
class Scenario:
    id: str
    title: str
    kind: str  # rekentijd | clubafspraak | productdefault | dagindeling | niet-knltb
    knltb_ok: bool
    cost: int
    transform: Transform
    time_factor: float = 1.0
    parts: tuple[str, ...] = ()


def _with_rule(p: ClubProfile, name: str, **params: Any) -> ClubProfile:
    rules = dict(p.rules)
    old = rules[name]
    hard = params.pop("hard", old.hard)
    rules[name] = Rule(name, hard, {**old.params, **params})
    return dataclasses.replace(p, rules=rules)


def candidate_scenarios(profile: ClubProfile, day: list[Fixture], base_rows: list[dict]) -> list[Scenario]:
    sc: list[Scenario] = []
    has_8p = any(f.is_8p for f in day)
    has_mixed_8p = any(f.is_8p and f.is_mixed and f.category not in JUNIOR_CATEGORIES for f in day)
    has_junior = any(f.category in JUNIOR_CATEGORIES for f in day)
    has_youth = any(f.category in YOUTH_CATEGORIES for f in day)
    R = profile.rules

    sc.append(Scenario("rekentijd", "Langer rekenen (3× tijdslimiet)", "rekentijd", True, 0,
                       lambda p, f: (p, f), time_factor=3.0))

    sw = R["start_window_8p"]
    if has_8p and sw.hard:
        cap = KNLTB_MIXED_8P_MAX if has_mixed_8p else KNLTB_MAX_START
        steps = list(range(sw.params["to"] + 30, cap + 1, 30))
        for to in steps:
            if to > sw.params["to"]:
                sc.append(Scenario(
                    f"8p_tot_{min_to_hhmm(to).replace(':', '')}",
                    f"8-partijenteams mogen beginnen tot {min_to_hhmm(to)} (clubafspraak {min_to_hhmm(sw.params['from'])}–{min_to_hhmm(sw.params['to'])})",
                    "clubafspraak", True, 2 + (to - sw.params["to"]) // 30,
                    (lambda t: lambda p, f: (_with_rule(p, "start_window_8p", to=t), f))(to)))

    mn = R["mixed_8p_not_before"]
    if has_mixed_8p and mn.hard and mn.params["time"] > KNLTB_EARLIEST:
        sc.append(Scenario("gem8p_vroeger", f"Gemengd 8p mag vóór {min_to_hhmm(mn.params['time'])} beginnen",
                           "clubafspraak", True, 3,
                           lambda p, f: (_with_rule(p, "mixed_8p_not_before", time=KNLTB_EARLIEST), f)))

    if profile.day_start > KNLTB_EARLIEST:
        sc.append(Scenario("dagstart_0830", f"Dagstart 08:30 i.p.v. {min_to_hhmm(profile.day_start)}", "dagindeling", True, 1,
                           lambda p, f: (dataclasses.replace(p, day_start=KNLTB_EARLIEST, fallback_start=None), f)))

    if profile.court_pairs:
        sc.append(Scenario("geen_baanparen", "Geen vaste baanparen (wel max 2 banen per team)", "clubafspraak", True, 2,
                           lambda p, f: (dataclasses.replace(p, court_pairs=None), f)))
    sc.append(Scenario("drie_banen", "Teams mogen 3 banen tegelijk gebruiken (geen vaste paren)", "clubafspraak", True, 3,
                       lambda p, f: (dataclasses.replace(p, court_pairs=None, max_courts_per_team=3), f)))

    jl = R["junioren_latest_start"]
    if has_junior and jl.hard and jl.params["time"] < KNLTB_JUNIOR_MAX:
        sc.append(Scenario("junioren_1500", f"Junioren beginnen uiterlijk 15:00 (KNLTB) i.p.v. {min_to_hhmm(jl.params['time'])}",
                           "clubafspraak", True, 2,
                           lambda p, f: (_with_rule(p, "junioren_latest_start", time=KNLTB_JUNIOR_MAX), f)))

    yl = R["youth_last_start"]
    if has_youth and yl.hard and yl.params["time"] < KNLTB_LAST_START:
        sc.append(Scenario("jeugd_1930", f"Jeugd mag tot 19:30 starten i.p.v. {min_to_hhmm(yl.params['time'])}",
                           "clubafspraak", True, 2,
                           lambda p, f: (_with_rule(p, "youth_last_start", time=KNLTB_LAST_START), f)))

    mw = R["max_wait_minutes"]
    if mw.hard:
        sc.append(Scenario("wachttijd_90", f"Max wachttijd {mw.params['value'] + 30} min i.p.v. {mw.params['value']}",
                           "productdefault", True, 1,
                           lambda p, f: (_with_rule(p, "max_wait_minutes", value=mw.params["value"] + 30), f)))
    mb = R["max_blocks_per_team"]
    if mb.hard:
        sc.append(Scenario("blokken_3", f"Max {mb.params['value'] + 1} speelblokken per team", "productdefault", True, 1,
                           lambda p, f: (_with_rule(p, "max_blocks_per_team", value=mb.params["value"] + 1), f)))

    # Een wedstrijd naar een inhaaldag verplaatsen is bewust GEEN automatische
    # oplossing (besluit Oscar 09-10-2026): dat is nooit acceptabel als voorstel.

    if profile.last_start <= KNLTB_LAST_START:
        sc.append(Scenario("laat_2030", "Laatste start 20:30 (mag NIET volgens KNLTB, alleen ter referentie)",
                           "niet-knltb", False, 9,
                           lambda p, f: (dataclasses.replace(p, last_start=20 * 60 + 30, day_end=22 * 60), f)))
    return sc


def _run(s: Scenario, profile: ClubProfile, day: list[Fixture], date: str, tl: float, seed: int) -> dict[str, Any]:
    p, fx = s.transform(dataclasses.replace(profile, fallback_start=None), list(day))
    res = plan_day(p, fx, date, time_limit_s=tl * s.time_factor, random_seed=seed, fit_check=True)
    kf = [x for x in knltb_findings(res.rows) if x["rule"] != "NIET-GEPLAND"]
    removed = len({f.team_key for f in day} - {f.team_key for f in fx})
    return {
        "id": s.id,
        "title": s.title,
        "kind": s.kind,
        "knltb_ok": s.knltb_ok and not kf,
        "cost": s.cost,
        "scheduled": res.scheduled,
        "unscheduled": res.unscheduled,
        "moved_wedstrijden": removed,
        "knltb_hard": len(kf),
        "knltb_findings": kf,
        "day_start": res.day_start,
        "status": res.status,
        "solve_time_s": round(res.solve_time_s, 1),
        "fits": res.unscheduled == 0 and res.status in ("OPTIMAL", "FEASIBLE"),
        "plan": res.to_dict(),
    }


def _rank_key(r: dict[str, Any]):
    return (not r["fits"], not r["knltb_ok"], r["cost"], r["unscheduled"])


def propose_solutions(
    profile: ClubProfile,
    fixtures: list[Fixture],
    date: str,
    base_rows: list[dict],
    time_limit_s: float = 20.0,
    seed: int = 42,
    combos: bool = True,
    log: Callable[[str], None] = lambda _: None,
) -> list[dict[str, Any]]:
    """Rangschik versoepelingen voor een speeldag met niet-ingeplande partijen."""
    day = [f for f in fixtures if f.date == date]
    scen = candidate_scenarios(profile, day, base_rows)
    results = []
    for s in scen:
        r = _run(s, profile, day, date, time_limit_s, seed)
        log(f"  {s.id}: {r['scheduled']} ingepland, {r['unscheduled']} niet, KNLTB-HARD {r['knltb_hard']}")
        results.append(r)

    # Geen enkele KNLTB-conforme losse versoepeling past? Probeer combinaties
    # van de beste clubafspraak-/productversoepelingen.
    if combos and not any(r["fits"] and r["knltb_ok"] for r in results):
        pool = [s for s in scen if s.kind in ("clubafspraak", "productdefault", "dagindeling")]
        best = sorted(pool, key=lambda s: next(r["unscheduled"] for r in results if r["id"] == s.id))[:3]
        for a, b in itertools.combinations(best, 2):
            combo = Scenario(f"{a.id}+{b.id}", f"{a.title} + {b.title}", "combinatie", True, a.cost + b.cost,
                             (lambda ta, tb: lambda p, f: tb(*ta(p, f)))(a.transform, b.transform))
            r = _run(combo, profile, day, date, time_limit_s, seed)
            log(f"  {combo.id}: {r['scheduled']} ingepland, {r['unscheduled']} niet, KNLTB-HARD {r['knltb_hard']}")
            results.append(r)

    results.sort(key=_rank_key)
    for i, r in enumerate(results, 1):
        r["rank"] = i
    return results
