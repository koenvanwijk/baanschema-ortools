import pytest

from baanschemaatje import miniyaml
from baanschemaatje.categories import DEFAULT_DURATIONS, Category, classify
from baanschemaatje.profile import ProfileError, load_profile, profile_from_dict


def test_knltb_defaults_live_in_core():
    assert DEFAULT_DURATIONS[Category.ROOD] == 60
    assert DEFAULT_DURATIONS[Category.ORANJE] == 120
    assert DEFAULT_DURATIONS[Category.GROEN] == 45
    assert DEFAULT_DURATIONS[Category.JUNIOREN_11_14] == 45
    assert DEFAULT_DURATIONS[Category.JEUGD_13_17] == 90
    assert DEFAULT_DURATIONS[Category.GEMENGD] == 90
    assert DEFAULT_DURATIONS[Category.SENIOREN] == 90


def test_club_files_do_not_redefine_knltb_durations(root):
    for f in (root / "clubs").glob("*.yaml"):
        assert "durations" not in f.read_text(encoding="utf-8"), f


@pytest.mark.parametrize(
    "schema,cat",
    [
        ("Rood 2 -Afdeling 19", Category.ROOD),
        ("Oranje 1 - Afdeling 37", Category.ORANJE),
        ("Groen Zondag – Groen 1  – Afdeling 36", Category.GROEN),
        ("Junioren 11 t/m 14 jaar Zondag – 3e klasse", Category.JUNIOREN_11_14),
        ("Meisjes 13 t/m 17 jaar Zondag – 1e klasse", Category.JEUGD_13_17),
        ("Gemengd Zondag – 1e klasse (2DE-2HE-DD-HD-2GD)", Category.GEMENGD),
        ("Heren Zondag – 4e klasse – Afdeling 4", Category.SENIOREN),
    ],
)
def test_classify(schema, cat):
    assert classify(schema) == cat


def test_load_mierlo(root):
    p = load_profile(root / "clubs" / "mierlo.yaml")
    assert p.courts == 10
    assert p.reservations[Category.ROOD].courts == (1,)
    assert p.reservations[Category.ORANJE].courts == (1, 2, 3)
    assert p.reservations[Category.ORANJE].courts_if_rood == (2, 3, 4)
    assert p.preferred_courts_8p == (1, 2, 3, 4)
    assert p.day_start == 9 * 60 and p.fallback_start == 8 * 60 + 30
    # Regels zonder override komen uit de core-defaults.
    # Clubafspraak, strenger dan KNLTB (gemengd 8p tot 14:00).
    sw = p.rule("start_window_8p")
    assert sw.hard is True and sw.params == {"from": 600, "to": 660}
    assert p.duration_for(Category.GROEN) == 45


def test_load_voorbeeld(root):
    p = load_profile(root / "clubs" / "voorbeeld-6-banen.yaml")
    assert p.courts == 6
    assert p.reservations == {}
    assert p.court_pairs is None


def test_duration_precedence():
    p = profile_from_dict({"club": {"name": "X"}, "courts": {"count": 4}, "durations": {"groen": 60}})
    assert p.expected_duration(Category.GROEN, export_minutes=45) == 60  # club-override
    assert p.expected_duration(Category.GEMENGD, export_minutes=75) == 75  # export
    assert p.expected_duration(Category.GEMENGD) == 90  # core-default


@pytest.mark.parametrize(
    "data,msg",
    [
        ({"courts": {"count": 4}}, "club.name"),
        ({"club": {"name": "X"}, "courts": {"count": 0}}, "courts.count"),
        ({"club": {"name": "X"}, "courts": {"count": 4}, "reservations": {"rood": {"courts": [5]}}}, "bestaat niet"),
        ({"club": {"name": "X"}, "courts": {"count": 4}, "reservations": {"groen": {"courts": [1]}}}, "alleen"),
        (
            {"club": {"name": "X"}, "courts": {"count": 4},
             "reservations": {"rood": {"courts": [1]}, "oranje": {"courts": [1, 2, 3]}}},
            "overlappen",
        ),
        ({"club": {"name": "X"}, "courts": {"count": 4}, "rules": {"bestaat_niet": {"hard": True}}}, "onbekende regel"),
        ({"club": {"name": "X"}, "courts": {"count": 4}, "day": {"start": "09:10"}}, "kwartiergrid"),
        ({"club": {"name": "X"}, "courts": {"count": 4}, "extra": 1}, "onbekende sectie"),
    ],
)
def test_invalid_profiles(data, msg):
    with pytest.raises(ProfileError, match=msg):
        profile_from_dict(data)


def test_miniyaml_fallback_parser():
    text = """
# commentaar
club:
  name: "TV Test"   # inline commentaar
courts:
  count: 6
court_assignment:
  pairs: [[1, 2], [3, 4]]
  lijst:
    - 1
    - 2
rules:
  max_wait_minutes:
    value: 45
    hard: false
"""
    d = miniyaml._parse(text)
    assert d["club"]["name"] == "TV Test"
    assert d["courts"]["count"] == 6
    assert d["court_assignment"]["pairs"] == [[1, 2], [3, 4]]
    assert d["court_assignment"]["lijst"] == [1, 2]
    assert d["rules"]["max_wait_minutes"] == {"value": 45, "hard": False}


def test_core_rules_follow_knltb_bijlage_3():
    p = profile_from_dict({"club": {"name": "X"}, "courts": {"count": 4}})
    assert p.rule("match_start_grid").params["value"] == 30 and p.rule("match_start_grid").hard
    assert p.rule("match_start_window").params == {"from": 8 * 60 + 30, "to": 16 * 60 + 30}
    assert p.rule("junioren_start_window").params == {"from": 8 * 60 + 30, "to": 12 * 60}
    assert p.rule("junioren_latest_start").params["time"] == 15 * 60
    assert p.rule("junioren_mixed_8p_latest_start").params["time"] == 13 * 60
    assert p.rule("mixed_8p_latest_start").params["time"] == 14 * 60
    assert p.rule("travel_not_before").params == {"value": 80, "time": 10 * 60}
    assert p.last_start == 19 * 60 + 30
    assert p.max_courts_per_team == 2
    # Generiek default: geen extra 8p-venster bovenop KNLTB.
    assert p.rule("start_window_8p").params == {"from": 8 * 60 + 30, "to": 16 * 60 + 30}


def test_min_reservation_vs_expected_duration():
    from baanschemaatje.categories import MIN_RESERVATION

    assert MIN_RESERVATION[Category.SENIOREN] == 90
    assert MIN_RESERVATION[Category.JUNIOREN_11_14] == 45
    p = profile_from_dict({"club": {"name": "X"}, "courts": {"count": 4}})
    # Export zegt 60 min voor senioren: verwacht 60, maar reservering minimaal 90.
    assert p.expected_duration(Category.SENIOREN, 60) == 60
    assert p.duration_for(Category.SENIOREN, 60) == 90
    assert p.duration_for(Category.JUNIOREN_11_14, 45) == 45
    with pytest.raises(ProfileError, match="minimumreservering"):
        profile_from_dict({"club": {"name": "X"}, "courts": {"count": 4}, "durations": {"senioren": 60}})


def test_day_start_must_be_on_half_hour():
    with pytest.raises(ProfileError, match="heel/half uur"):
        profile_from_dict({"club": {"name": "X"}, "courts": {"count": 4}, "day": {"start": "09:15"}})
