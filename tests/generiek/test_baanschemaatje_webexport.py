import json

from baanschemaatje.webexport import build_web


def test_build_web_writes_index_and_plans(root, season_path, tmp_path):
    idx = build_web(
        [root / "clubs" / "voorbeeld-6-banen.yaml"], season_path, tmp_path,
        time_limit_s=5, dates=["11-10-2026"], log=lambda *_: None,
    )
    data = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert data == json.loads(json.dumps(idx))
    club = data["clubs"][0]
    assert club["id"] == "voorbeeld-6-banen" and club["courts"] == 6
    assert {r["name"] for r in club["rules"]} >= {"match_start_grid", "start_window_8p"}
    d = club["dates"][0]
    plan = json.loads((tmp_path / d["file"]).read_text(encoding="utf-8"))
    assert plan["rows"] and d["scheduled"] == plan["stats"]["scheduled"]
    assert plan["validator"]["available"] is True
    assert d["hard"] == plan["validator"]["hard"]


def test_mierlo_profile_summary_marks_club_agreements(root):
    from baanschemaatje.profile import load_profile
    from baanschemaatje.webexport import profile_summary

    s = profile_summary(load_profile(root / "clubs" / "mierlo.yaml"), "mierlo")
    rules = {r["name"]: r for r in s["rules"]}
    assert rules["start_window_8p"]["club_override"] is True
    assert rules["start_window_8p"]["params"] == {"from": "10:00", "to": "11:00"}
    assert rules["junioren_latest_start"]["club_override"] is True
    assert rules["junioren_latest_start"]["source"].startswith("KNLTB")
    assert rules["match_start_grid"]["club_override"] is False
