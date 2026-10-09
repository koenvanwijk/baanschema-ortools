"""Live-backend (server/baanschemaatje): API-contract met FastAPI TestClient.

Wordt overgeslagen als fastapi/httpx niet geïnstalleerd zijn (CI van main).
"""

import importlib.util
import sys

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client(root, tmp_path_factory):
    import os

    os.environ["BS_STORE"] = str(tmp_path_factory.mktemp("store"))
    spec = importlib.util.spec_from_file_location("bs_server_app", root / "server" / "baanschemaatje" / "app.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bs_server_app"] = mod
    spec.loader.exec_module(mod)
    return TestClient(mod.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok" and j["season_present"] and "mierlo" in j["clubs"]


def test_clubs_and_dates(client):
    j = client.get("/clubs").json()
    ids = {c["id"] for c in j["clubs"]}
    assert {"mierlo", "voorbeeld-6-banen"} <= ids
    d = client.get("/dates", params={"club": "mierlo"}).json()["dates"]
    assert any(x["date"] == "11-10-2026" for x in d)


def test_unknown_club_and_date(client):
    assert client.post("/plan", json={"club": "bestaat-niet", "date": "11-10-2026"}).status_code == 404
    assert client.post("/plan", json={"club": "mierlo", "date": "01-01-2000"}).status_code == 404


def test_invalid_inline_profile(client):
    r = client.post("/plan", json={"club": {"club": {"name": "X"}, "courts": {"count": 0}}, "date": "11-10-2026"})
    assert r.status_code == 422


def test_plan_shape_and_cap(client):
    body = {"club": "mierlo", "date": "11-10-2026", "time_limit_s": 999, "validate": False}
    r = client.post("/plan", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("status", "day_start", "rows", "stats", "courts", "summary", "profile"):
        assert k in j
    assert j["live"]["time_limit_s"] <= 30
    assert j["status"] in ("OPTIMAL", "FEASIBLE") and j["summary"]["solved"]
    assert j["summary"]["scheduled"] + j["summary"]["unscheduled"] > 0
    # tweede keer uit de cache
    assert client.post("/plan", json=body).json()["cached"] is True


def test_plan_overrides_and_inline(client):
    j = client.post("/plan", json={"club": "voorbeeld-6-banen", "date": "11-10-2026", "time_limit_s": 5,
                                   "overrides": {"courts": {"count": 8}}, "validate": False}).json()
    assert j["courts"] == 8 and j["profile"]["courts"] == 8
    inline = {"club": {"name": "TV Inline", "knltb_name": "MIERLO"}, "courts": {"count": 6},
              "day": {"start": "09:00", "last_start": "19:30", "end": "20:00"}}
    j = client.post("/plan", json={"club": inline, "date": "11-10-2026", "time_limit_s": 5, "validate": False}).json()
    assert j["club"] == "TV Inline" and j["courts"] == 6


def test_scenarios_day_that_fits(client):
    j = client.post("/scenarios", json={"club": "mierlo", "date": "11-10-2026", "time_limit_s": 5,
                                        "validate": False}).json()
    assert j["base_solved"] and j["base_unscheduled"] == 0 and j["solutions"] == []


def test_builtin_club_not_editable(client):
    # Ingebouwde voorbeeldprofielen (clubs/*.yaml zonder opgeslagen kopie) zijn alleen-lezen.
    assert client.put("/clubs/voorbeeld-6-banen/profile", json={}).status_code == 403
    nep = {"club": {"name": "Nep"}, "courts": {"count": 4}}
    assert client.post("/clubs", json={"id": "mierlo", "profile": nep}).status_code == 409


def test_auth_hook_is_used_for_writes(client, monkeypatch):
    """Login per club komt later; alle schrijfroutes lopen via auth.authorize_write."""
    from fastapi import HTTPException

    import auth

    calls = []

    def deny(club_id, request=None):
        calls.append(club_id)
        raise HTTPException(401, "login vereist")

    mod = sys.modules["bs_server_app"]
    monkeypatch.setattr(mod, "authorize_write", deny)
    prof = {"club": {"name": "TV Geweigerd"}, "courts": {"count": 4}}
    assert client.post("/clubs", json={"profile": prof}).status_code == 401
    assert calls == ["tv-geweigerd"]
    assert auth.authorize_write("x") is None  # nu nog open


def test_club_lifecycle(client, root):
    prof = {"club": {"name": "TV Testclub", "knltb_name": "MIERLO"}, "courts": {"count": 8},
            "day": {"start": "09:00", "last_start": "19:30", "end": "20:00"}}
    r = client.post("/clubs", json={"profile": prof})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert cid == "tv-testclub"
    assert client.post("/clubs", json={"profile": prof}).status_code == 409
    assert any(c["id"] == cid and c["stored"] for c in client.get("/clubs").json()["clubs"])
    # profiel wijzigen (ongeldig → 422, geldig → opgeslagen)
    assert client.put(f"/clubs/{cid}/profile", json={**prof, "courts": {"count": 0}}).status_code == 422
    assert client.put(f"/clubs/{cid}/profile", json={**prof, "courts": {"count": 7}}).status_code == 200
    assert client.get(f"/clubs/{cid}").json()["summary"]["courts"] == 7
    # ruwe KNLTB-export uploaden
    data = (root / "docs" / "wedstrijden_2026-2027.xlsx").read_bytes()
    r = client.post(f"/clubs/{cid}/season", content=data, params={"filename": "w.xlsx"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["report"]["imported"] == 52 and j["report"]["format"] == "ruwe KNLTB-export"
    assert [d["date"] for d in j["dates"]][:2] == ["06-09-2026", "13-09-2026"]
    assert "Aanvoerder" not in r.text
    s = client.get(f"/clubs/{cid}/season").json()
    assert s["own_season"] and len(s["dates"]) == 6
    # onleesbaar bestand → 422
    assert client.post(f"/clubs/{cid}/season", content=b"onzin", params={"filename": "x.csv"}).status_code == 422
    # live plannen met het eigen seizoen
    p = client.post("/plan", json={"club": cid, "date": "11-10-2026", "time_limit_s": 5}).json()
    assert p["courts"] == 7 and p["summary"]["solved"] and p["live"]["season_file"].startswith(cid)


# ---------------------------------------------------------------- verzetten (zonder solver)

def _mierlo_fixture(client, date="27-09-2026"):
    day = next(d for d in client.get("/clubs/mierlo/season").json()["dates"] if d["date"] == date)
    return next(w for w in day["wedstrijden"] if w["category"] not in ("rood", "oranje"))


def test_season_view_has_part_counts(client):
    w = _mierlo_fixture(client)
    assert w["singles"] + w["doubles"] + w["mix"] == w["matches"]


def test_apply_moves_to_inhaaldag(client):
    mod = sys.modules["bs_server_app"]
    w = _mierlo_fixture(client)
    req = mod.PlanRequest(club="mierlo", date="18-10-2026",
                          moves=[{"schema": w["schema"], "home": w["home"], "from": "27-09-2026", "to": "18-10-2026"}])
    _, prof, _, season, spath = mod._resolve(req)
    assert spath != mod.SEASON_FILE and spath.name.startswith("moved-")
    moved = season.day("18-10-2026")
    assert [(f.schema, f.home_team) for f in moved] == [(w["schema"], w["home"])]
    assert all(not (f.schema == w["schema"] and f.home_team == w["home"]) for f in season.day("27-09-2026"))
    assert req._moves_applied[0]["to"] == "18-10-2026"
    # Zonder verzetting bestaat 18-10 niet als speeldag.
    with pytest.raises(mod.HTTPException) as e:
        mod._resolve(mod.PlanRequest(club="mierlo", date="18-10-2026"))
    assert e.value.status_code == 404


def test_apply_moves_unknown_wedstrijd(client):
    r = client.post("/plan", json={"club": "mierlo", "date": "18-10-2026",
                                   "moves": [{"schema": "Bestaat niet", "home": "MIERLO 9", "from": "27-09-2026", "to": "18-10-2026"}]})
    assert r.status_code == 404 and "verzetting" in r.json()["detail"]
    r = client.post("/plan", json={"club": "mierlo", "date": "18-10-2026",
                                   "moves": [{"schema": "x", "home": "y", "from": "2026-09-27", "to": "18-10-2026"}]})
    assert r.status_code == 422


def test_apply_moves_ignores_whitespace_differences(client):
    mod = sys.modules["bs_server_app"]
    w = _mierlo_fixture(client)
    sloppy = w["schema"].replace(" – ", "  –  ")
    _, _, _, season, _ = mod._resolve(mod.PlanRequest(club="mierlo", date="25-10-2026",
                                                      moves=[{"schema": sloppy, "home": w["home"], "from": "27-09-2026", "to": "25-10-2026"}]))
    assert len(season.day("25-10-2026")) == 1
