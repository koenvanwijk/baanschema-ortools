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
    _assert_team_concurrency(res.rows, limit=prof.max_courts_per_team)


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


def test_mierlo_teams_use_at_most_three_courts(plans, profiles):
    # Besluit Oscar 09-10-2026: max 3 banen per team, geen vaste baanparen.
    assert profiles["mierlo"].court_pairs is None
    assert profiles["mierlo"].max_courts_per_team == 3
    for date in ("06-09-2026", "11-10-2026"):
        used = defaultdict(set)
        for r in _placed(plans[("mierlo", date)].rows):
            if r["kind"] != "W":
                used[r["team_id"]].add(r["court"])
        for team, cs in used.items():
            assert len(cs) <= 3, (team, cs)


def test_mierlo_8p_team_respects_start_window(plans):
    rows = [r for r in _placed(plans[("mierlo", "11-10-2026")].rows) if "2DE-2HE-DD-HD-2GD" in r["team"]]
    assert rows, "8-partijenteam verwacht op 11-10-2026"
    first = min(_m(r["start"]) for r in rows)
    assert 10 * 60 <= first <= 11 * 60


def _fx(schema, cat, matches, dur, s=0, d=0, home="CLUB 1"):
    return Fixture("06-01-2030", schema, cat, matches, dur, s, d, 0, home, "GAST 1")


def test_mierlo_rood_and_oranje_same_day(profiles):
    fixtures = [
        _fx("Rood 1", Category.ROOD, 1, 60),
        _fx("Oranje 1", Category.ORANJE, 3, 120),
        _fx("Groen Zondag – Groen 1", Category.GROEN, 6, 45, s=4, d=2),
    ]
    res = plan_day(profiles["mierlo"], fixtures, "06-01-2030", time_limit_s=5)
    w = [r for r in res.rows if r["kind"] == "W"]
    assert sorted(r["court"] for r in w if r["team"] == "Rood 1") == [1]
    assert sorted(r["court"] for r in w if r["team"] == "Oranje 1") == [2, 3, 4]
    assert res.unscheduled == 0
    _assert_no_court_overlap(res.rows)


def test_profile_court_count_is_respected_for_tiny_club(profiles):
    from baanschemaatje.profile import profile_from_dict

    tiny = profile_from_dict({"club": {"name": "Mini"}, "courts": {"count": 2}})
    fixtures = [_fx("Groen Zondag – Groen 1", Category.GROEN, 6, 45, s=4, d=2)]
    res = plan_day(tiny, fixtures, "06-01-2030", time_limit_s=5)
    assert res.unscheduled == 0
    assert {r["court"] for r in res.rows} <= {1, 2}


def _first_starts(rows):
    first = {}
    for r in _placed(rows):
        if r["kind"] != "W":
            first[r["team_id"]] = min(first.get(r["team_id"], 99 * 60), _m(r["start"]))
    return first


@pytest.mark.parametrize("club", ["mierlo", "voorbeeld"])
@pytest.mark.parametrize("date", ["06-09-2026", "11-10-2026"])
def test_knltb_bijlage_3_begintijden(plans, club, date):
    """CR Bijlage 3, 1.1: begintijd op heel/half uur, 08:30-16:30;
    juniorencompetities uiterlijk 15:00; laatste partij start <= 19:30."""
    res = plans[(club, date)]
    for team, s in _first_starts(res.rows).items():
        assert s % 30 == 0, (team, s)
        assert 8 * 60 + 30 <= s <= 16 * 60 + 30, (team, s)
        low = team.lower()
        if "junioren" in low or "groen" in low:
            # KNLTB: uiterlijk 15:00; Mierlo-clubafspraak: uiterlijk 13:00.
            assert s <= (13 * 60 if club == "mierlo" else 15 * 60), (team, s)
        if "gemengd" in low and "2de-2he-dd-hd-2gd" in low:
            assert s <= 14 * 60, (team, s)
    for r in _placed(res.rows):
        assert _m(r["start"]) <= 19 * 60 + 30


def test_travel_80km_not_before_10(profiles):
    import dataclasses

    fx = _fx("Heren Zondag – 4e klasse", Category.SENIOREN, 4, 90, s=2, d=2)
    far = dataclasses.replace(fx, travel_km=95)
    res = plan_day(profiles["voorbeeld"], [far], "06-01-2030", time_limit_s=5)
    assert res.unscheduled == 0
    assert min(_first_starts(res.rows).values()) >= 10 * 60


def _assert_adjacent_courts(rows):
    by_team = defaultdict(set)
    for r in _placed(rows):
        if r["kind"] != "W":
            by_team[r["team_id"]].add(r["court"])
    for team, cs in by_team.items():
        assert max(cs) - min(cs) + 1 == len(cs), f"{team}: banen {sorted(cs)} niet aangrenzend"


@pytest.mark.parametrize("club,date", [("mierlo", "11-10-2026"), ("voorbeeld", "11-10-2026")])
def test_adjacent_courts_hard(profiles, season, club, date):
    prof = profiles[club]
    assert prof.adjacent_courts
    res = plan_day(prof, season.fixtures, date, time_limit_s=TL)
    assert res.status in ("OPTIMAL", "FEASIBLE")
    _assert_adjacent_courts(res.rows)
    _assert_no_court_overlap(res.rows)


def test_friday_evening_doubles_fit_in_two_rounds(profiles):
    """Vrijdagavond 4 dubbels (DD-HD-2GD): 19:00-22:00, geen Bijlage 3, gespeelde wedstrijd wordt niet gepland."""
    def ev(schema, home, status="open"):
        return Fixture("16-10-2026", schema, Category.GEMENGD if "Gemengd" in schema else Category.SENIOREN,
                       4, 90, 0, 2 if "Gemengd" in schema else 4, 2 if "Gemengd" in schema else 0, home, "GAST 1",
                       dagdeel="avond", status=status, result="3 - 1" if status == "gespeeld" else "")
    fx = [ev("Gemengd Dubbel 17+ Vrijdag Avond – 1e klasse", "CLUB 1"),
          ev("Dames Dubbel 35+ Vrijdag Avond – 3e klasse", "CLUB 2"),
          ev("Heren Dubbel 17+ Vrijdag Avond – 3e klasse", "CLUB 3", status="gespeeld")]
    res = plan_day(profiles["mierlo"], fx, "16-10-2026", time_limit_s=5)
    assert res.unscheduled == 0
    rows = _placed(res.rows)
    assert {r["home_team"] for r in rows} == {"CLUB 1", "CLUB 2"}
    assert all(19 * 60 <= _m(r["start"]) <= 20 * 60 + 30 for r in rows)
    for team in ("CLUB 1", "CLUB 2"):
        assert min(_m(r["start"]) for r in rows if r["home_team"] == team) <= 20 * 60
    _assert_no_court_overlap(res.rows)


def test_weekday_profile_defaults_and_overrides():
    from baanschemaatje.profile import ProfileError, profile_from_dict
    import pytest

    p = profile_from_dict({"club": {"name": "X"}, "courts": {"count": 8},
                           "weekdays": {"vrijdag": {"courts": 6, "end": "22:30"}}})
    f = p.for_day("vrijdag", {"avond"})
    assert (f.day_start, f.last_start, f.day_end, f.courts, f.bijlage3) == (19 * 60, 20 * 60 + 30, 22 * 60 + 30, 6, False)
    assert not f.rules["first_start_deadline"].hard
    t = p.for_day("donderdag", {"avond", "ochtend"})
    assert t.day_start == 9 * 60 and t.courts == 8
    z = p.for_day("zondag")
    assert z.bijlage3 and z.day_start == p.day_start
    with pytest.raises(ProfileError):
        profile_from_dict({"club": {"name": "X"}, "courts": {"count": 8}, "weekdays": {"vrydag": {}}})
    with pytest.raises(ProfileError):
        profile_from_dict({"club": {"name": "X"}, "courts": {"count": 8}, "weekdays": {"vrijdag": {"courts": 9}}})


def test_friday_end_after_midnight():
    from baanschemaatje.profile import profile_from_dict
    from baanschemaatje.webexport import profile_summary

    p = profile_from_dict({"club": {"name": "X"}, "courts": {"count": 8}, "weekdays": {"vrijdag": {"end": "01:00"}}})
    f = p.for_day("vrijdag", {"avond"})
    assert (f.day_end, f.last_start) == (25 * 60, 20 * 60 + 30)
    w = profile_summary(p, "x")["weekdays"]["vrijdag"]
    assert w["end"] == "25:00" and w["end_display"] == "01:00 (volgende dag)" and "end" not in w["defaults"]
    assert "last_start" in w["defaults"]
    fx = [Fixture("16-10-2026", "Dames Dubbel 35+ Vrijdag Avond", Category.SENIOREN, 4, 90, 0, 4, 0, "CLUB 1", "G",
                  dagdeel="avond")]
    res = plan_day(p, fx, "16-10-2026", time_limit_s=5)
    assert res.unscheduled == 0
