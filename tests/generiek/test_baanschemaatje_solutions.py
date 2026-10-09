from baanschemaatje.categories import Category
from baanschemaatje.knltb import knltb_findings
from baanschemaatje.planner import plan_day
from baanschemaatje.profile import profile_from_dict
from baanschemaatje.scenarios import propose_solutions
from baanschemaatje.season import Fixture


def _fx(schema, cat, matches, dur, s, d, home, date="01-01-2030"):
    return Fixture(date, schema, cat, matches, dur, s, d, 0, home, "GAST 1")


def _row(team, part, start, end, cat="senioren", label="HEREN"):
    return {"team": team, "team_id": team, "home_team": "X", "category": cat, "label": label,
            "part": part, "kind": "S", "start": start, "end": end, "court": 1}


def test_knltb_checker_flags_bijlage_3():
    rows = [_row("Heren Zondag", "S1", "09:15", "10:45"), _row("Heren Zondag", "S2", "19:45", "21:15")]
    rules = {f["rule"] for f in knltb_findings(rows)}
    assert "B3-1.1-GRID" in rules and "B3-2.1c-1930" in rules
    jr = [_row("Junioren 11 t/m 14", "S1", "15:30", "16:15", cat="junioren_11_14", label="JU11-14")]
    assert {f["rule"] for f in knltb_findings(jr)} == {"B3-1.1a-JUNIOREN"}


def test_rows_carry_gender_label():
    prof = profile_from_dict({"club": {"name": "Mini"}, "courts": {"count": 2}})
    fx = [_fx("Meisjes 13 t/m 17 jaar Zondag – 1e klasse", Category.JEUGD_13_17, 2, 90, 2, 0, "CLUB 1")]
    res = plan_day(prof, fx, "01-01-2030", time_limit_s=3)
    assert {r["label"] for r in res.rows} == {"M13-17"}


def test_propose_solutions_ranks_a_fitting_option_first():
    # 2 banen, één ronde van 90 min: drie teams met elk één single passen niet.
    prof = profile_from_dict({
        "club": {"name": "Krap"}, "courts": {"count": 2},
        "day": {"start": "09:00", "last_start": "09:30", "end": "10:30"},
    })
    fx = [
        _fx("Heren Zondag – 1e klasse", Category.SENIOREN, 1, 90, 1, 0, "CLUB 1"),
        _fx("Dames Zondag – 1e klasse", Category.SENIOREN, 1, 90, 1, 0, "CLUB 2"),
        _fx("Heren Zondag – 2e klasse", Category.SENIOREN, 1, 90, 1, 0, "CLUB 3"),
    ]
    base = plan_day(prof, fx, "01-01-2030", time_limit_s=3)
    assert base.unscheduled > 0
    sols = propose_solutions(prof, fx, "01-01-2030", base.rows, time_limit_s=3, combos=False)
    assert sols[0]["fits"] and sols[0]["knltb_ok"]
    assert sols[0]["kind"] == "inhaaldag"
    ref = [s for s in sols if s["kind"] == "niet-knltb"]
    assert ref and not ref[0]["knltb_ok"]
