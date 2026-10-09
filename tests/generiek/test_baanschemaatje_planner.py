"""Planner-tests op echte speeldagen uit het seizoen 2026-2027.

Tijdslimieten zijn kort gehouden voor CI; de tests controleren harde
eigenschappen (capaciteit, banen, reserveringen), niet optimaliteit.
"""

from collections import defaultdict

import pytest

from baanschemaatje.categories import Category
from baanschemaatje.planner import UNSCHEDULED, plan_day
from baanschemaatje.profile import load_profile
from baanschemaatje.season import Fixture, load_season_tsv

TL = 8.0


def _m(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def _placed(rows):
    return [r for r in rows if r["start"] != UNSCHEDULED]


def _assert_no_court_overlap(rows):
    by_court = defaultdict(list)
    for r in _placed(rows):
        by_court[r["court"]].append((_m(r["start"]), _m(r["end"]), r["team"], r["part"]))
    for c, iv in by_court.items():
        iv.sort()
        for a, b in zip(iv, iv[1:]):
            assert a[1] <= b[0], f"overlap op baan {c}: {a} / {b}"


def _assert_team_concurrency(rows, limit=2):
    by_team = defaultdict(list)
    for r in _placed(rows):
        if r["kind"] != "W":
            by_team[r["team_id"]].append((_m(r["start"]), _m(r["end"])))
    for team, iv in by_team.items():
        for t in range(0, 24 * 60, 15):
            assert sum(1 for s, e in iv if s <= t < e) <= limit, team


@pytest.fixture(scope="module")
def profiles(root):
    return {
        "mierlo": load_profile(root / "clubs" / "mierlo.yaml"),
        "voorbeeld": load_profile(root / "clubs" / "voorbeeld-6-banen.yaml"),
    }


@pytest.fixture(scope="module")
def season(season_path):
    return load_season_tsv(season_path, "MIERLO")


@pytest.fixture(scope="module")
def plans(profiles, season):
    out = {}
    for club in ("mierlo", "voorbeeld"):
        for date in ("06-09-2026", "11-10-2026"):
            out[(club, date)] = plan_day(profiles[club], season.fixtures, date, time_limit_s=TL)
    return out


@pytest.mark.parametrize("club", ["mierlo", "voorbeeld"])
@pytest.mark.parametrize("date", ["06-09-2026", "11-10-2026"])
def test_both_clubs_produce_valid_plan(plans, profiles, club, date):
    res = plans[(club, date)]
    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert res.scheduled > 0
    prof = profiles[club]
    for r in _placed(res.rows):
        assert 1 <= r["court"] <= prof.courts
        assert _m(r["end"]) <= prof.day_end
        if r["kind"] != "W":
            assert _m(r["start"]) <= prof.last_start
    _assert_no_court_overlap(res.rows)
    _assert_team_concurrency(res.rows)


def test_small_day_fully_scheduled(plans):
    assert plans[("mierlo", "11-10-2026")].unscheduled == 0
    assert plans[("voorbeeld", "11-10-2026")].unscheduled == 0


def test_six_court_club_never_uses_court_7_plus(plans):
    for date in ("06-09-2026", "11-10-2026"):
        assert max(r["court"] for r in _placed(plans[("voorbeeld", date)].rows)) <= 6


def test_voorbeeld_oranje_gets_solver_chosen_courts(plans):
    rows = plans[("voorbeeld", "06-09-2026")].rows
    w = [r for r in rows if r["kind"] == "W"]
    assert len(w) == 3  # Oranje: 3 wedstrijden → 3 banen
    assert len({r["start"] for r in w}) == 1


def test_mierlo_oranje_reservation_on_courts_1_to_3(plans):
    res = plans[("mierlo", "06-09-2026")]
    w = [r for r in res.rows if r["kind"] == "W"]
    assert sorted(r["court"] for r in w) == [1, 2, 3]
    start, end = _m(w[0]["start"]), _m(w[0]["end"])
    assert end - start == 120
    assert w[0]["start"] == res.day_start
    for r in _placed(res.rows):
        if r["kind"] != "W" and r["court"] in (1, 2, 3):
            assert _m(r["end"]) <= start or _m(r["start"]) >= end


def test_mierlo_teams_stay_on_one_court_pair(plans, profiles):
    pairs = profiles["mierlo"].court_pairs
    for date in ("06-09-2026", "11-10-2026"):
        used = defaultdict(set)
        for r in _placed(plans[("mierlo", date)].rows):
            if r["kind"] != "W":
                used[r["team_id"]].add(r["court"])
        for team, cs in used.items():
            assert any(cs <= set(p) for p in pairs), (team, cs)


def test_mierlo_8p_team_respects_start_window(plans):
    rows = [r for r in _placed(plans[("mierlo", "11-10-2026")].rows) if "2DE-2HE-DD-HD-2GD" in r["team"]]
    assert rows, "8-partijenteam verwacht op 11-10-2026"
    first = min(_m(r["start"]) for r in rows)
    assert 10 * 60 <= first <= 11 * 60


def _fx(schema, cat, matches, dur, s=0, d=0, home="CLUB 1"):
    return Fixture("01-01-2030", schema, cat, matches, dur, s, d, 0, home, "GAST 1")


def test_mierlo_rood_and_oranje_same_day(profiles):
    fixtures = [
        _fx("Rood 1", Category.ROOD, 1, 60),
        _fx("Oranje 1", Category.ORANJE, 3, 120),
        _fx("Groen Zondag – Groen 1", Category.GROEN, 6, 45, s=4, d=2),
    ]
    res = plan_day(profiles["mierlo"], fixtures, "01-01-2030", time_limit_s=5)
    w = [r for r in res.rows if r["kind"] == "W"]
    assert sorted(r["court"] for r in w if r["team"] == "Rood 1") == [1]
    assert sorted(r["court"] for r in w if r["team"] == "Oranje 1") == [2, 3, 4]
    assert res.unscheduled == 0
    _assert_no_court_overlap(res.rows)


def test_profile_court_count_is_respected_for_tiny_club(profiles):
    from baanschemaatje.profile import profile_from_dict

    tiny = profile_from_dict({"club": {"name": "Mini"}, "courts": {"count": 2}})
    fixtures = [_fx("Groen Zondag – Groen 1", Category.GROEN, 6, 45, s=4, d=2)]
    res = plan_day(tiny, fixtures, "01-01-2030", time_limit_s=5)
    assert res.unscheduled == 0
    assert {r["court"] for r in res.rows} <= {1, 2}
