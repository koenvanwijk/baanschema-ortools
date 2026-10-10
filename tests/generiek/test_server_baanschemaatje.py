"""Live-backend (server/baanschemaatje): API-contract met FastAPI TestClient.

Wordt overgeslagen als fastapi/httpx niet geïnstalleerd zijn (CI van main).
"""

import json
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
    r = client.post(f"/clubs/{cid}/season", content=data, params={"filename": "w.xlsx", "days": "zondag"})
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


# ---------------------------------------------------------------- opslaan (zonder solver)

def _stored_club(client, name):
    prof = {"club": {"name": name, "knltb_name": "MIERLO"}, "courts": {"count": 10}}
    r = client.post("/clubs", json={"profile": prof})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_schedule_save_load_delete(client, root, monkeypatch):
    from datetime import date as _date
    # Vóór de speeldag: overschrijven/verwijderen mag (na de dag blijft een opgeslagen schema staan).
    monkeypatch.setattr(sys.modules["bs_server_app"], "_today_ams", lambda: _date(2026, 9, 1))
    cid = _stored_club(client, "TV Opslaan")
    plan = json.loads((root / "web/baanschemaatje/data/mierlo/27-09-2026.json").read_text())
    assert client.get(f"/clubs/{cid}/schedule/27-09-2026").status_code == 404
    assert client.get(f"/clubs/{cid}/schedules").json()["schedules"] == {}
    body = {"plan": plan, "source": "handmatig aangepast", "check": {"hard": 0, "model": 3, "scheduled": 66}, "sig": "[]"}
    r = client.put(f"/clubs/{cid}/schedule/27-09-2026", json=body)
    assert r.status_code == 200, r.text
    meta = r.json()
    assert meta["source"] == "handmatig aangepast" and meta["saved_at"] and "plan" not in meta
    g = client.get(f"/clubs/{cid}/schedule/27-09-2026").json()
    assert g["plan"]["rows"] == plan["rows"] and g["check"]["model"] == 3 and g["date"] == "27-09-2026"
    all_ = client.get(f"/clubs/{cid}/schedules").json()["schedules"]
    assert list(all_) == ["27-09-2026"]
    assert client.delete(f"/clubs/{cid}/schedule/27-09-2026").json() == {"ok": True, "deleted": True}
    assert client.get(f"/clubs/{cid}/schedule/27-09-2026").status_code == 404
    assert client.delete(f"/clubs/{cid}/schedule/27-09-2026").json()["deleted"] is False


def test_schedule_validation_and_limits(client, monkeypatch):
    cid = _stored_club(client, "TV Grenzen")
    ok = {"plan": {"rows": []}, "source": "berekend"}
    assert client.put(f"/clubs/{cid}/schedule/2026-09-27", json=ok).status_code == 422
    assert client.put(f"/clubs/{cid}/schedule/31-02-2026", json=ok).status_code == 422
    assert client.put(f"/clubs/{cid}/schedule/27-09-2026", json={**ok, "source": "zomaar"}).status_code == 422
    assert client.put(f"/clubs/{cid}/schedule/27-09-2026", json={"plan": {"rows": "x"}}).status_code == 422
    assert client.put(f"/clubs/{cid}/schedule/27-09-2026", content=b"{kapot", headers={"Content-Type": "application/json"}).status_code == 422
    mod = sys.modules["bs_server_app"]
    monkeypatch.setattr(mod, "MAX_SCHEDULE_ROWS", 2)
    assert client.put(f"/clubs/{cid}/schedule/27-09-2026", json={"plan": {"rows": [{}, {}, {}]}}).status_code == 413
    monkeypatch.setattr(mod, "MAX_SCHEDULE_BYTES", 100)
    big = {"plan": {"rows": [{"team": "x" * 200}]}}
    assert client.put(f"/clubs/{cid}/schedule/27-09-2026", json=big).status_code == 413
    # ingebouwd voorbeeldprofiel: alleen-lezen; onbekende club: 404
    assert client.put("/clubs/voorbeeld-6-banen/schedule/27-09-2026", json=ok).status_code == 403
    assert client.get("/clubs/voorbeeld-6-banen/schedules").json()["schedules"] == {}
    assert client.get("/clubs/bestaat-niet/schedules").status_code == 404


def test_moves_save_load(client):
    cid = _stored_club(client, "TV Verzet")
    assert client.get(f"/clubs/{cid}/moves").json()["moves"] == []
    mv = {"schema": "Gemengd Zondag – 1e klasse – Afdeling 3", "home": "MIERLO 1", "from": "27-09-2026", "to": "18-10-2026",
          "key": "Gemengd · MIERLO 1", "label": "GEM 1e"}
    r = client.put(f"/clubs/{cid}/moves", json={"moves": [mv]})
    assert r.status_code == 200 and r.json()["count"] == 1
    g = client.get(f"/clubs/{cid}/moves").json()
    assert g["moves"] == [mv] and g["saved_at"]  # extra velden (voor de web-GUI) blijven bewaard
    assert client.put(f"/clubs/{cid}/moves", json={"moves": [{"schema": "x"}]}).status_code == 422
    assert client.put(f"/clubs/{cid}/moves", json={"moves": [{**mv, "to": "18/10/2026"}]}).status_code == 422
    assert client.put(f"/clubs/{cid}/moves", json=[mv]).status_code == 422
    assert client.put("/clubs/voorbeeld-6-banen/moves", json={"moves": []}).status_code == 403


def test_save_routes_use_auth_hook(client, monkeypatch):
    from fastapi import HTTPException

    cid = _stored_club(client, "TV Auth Opslaan")
    mod = sys.modules["bs_server_app"]

    def deny(club_id, request=None):
        raise HTTPException(401, "login vereist")

    monkeypatch.setattr(mod, "authorize_write", deny)
    assert client.put(f"/clubs/{cid}/schedule/27-09-2026", json={"plan": {"rows": []}}).status_code == 401
    assert client.delete(f"/clubs/{cid}/schedule/27-09-2026").status_code == 401
    assert client.put(f"/clubs/{cid}/moves", json={"moves": []}).status_code == 401
    assert client.get(f"/clubs/{cid}/moves").status_code == 200


def test_upload_all_weekdays_played_locked_and_reprocess(client, root, monkeypatch):
    """Upload Oscar 10-10-2026: do/vr/za/zo; gespeelde wedstrijden vast; reprocess; geen solver."""
    from datetime import date as _date

    mod = sys.modules["bs_server_app"]
    monkeypatch.setattr(mod, "_today_ams", lambda: _date(2026, 10, 10))
    prof = {"club": {"name": "TV Avond", "knltb_name": "MIERLO"}, "courts": {"count": 10},
            "weekdays": {"vrijdag": {"courts": 6}}}
    cid = client.post("/clubs", json={"profile": prof}).json()["id"]
    data = (root / "tests" / "generiek" / "data" / "export_mierlo_20261010.xlsx").read_bytes()
    j = client.post(f"/clubs/{cid}/season", content=data, params={"filename": "w.xlsx"}).json()
    rep = j["report"]
    assert rep["imported"] == 112 and rep["per_weekday"]["vrijdag"] == 40 and rep["per_weekday"]["donderdag"] == 12
    fri = [d for d in j["dates"] if d["weekday"] == "vrijdag"]
    assert fri and all(d["window"]["start"] == "19:00" and not d["window"]["bijlage3"] and d["window"]["courts"] == 6 for d in fri)
    thu = next(d for d in j["dates"] if d["weekday"] == "donderdag" and "ochtend" in d["dagdelen"])
    assert thu["window"]["start"] == "09:00"
    sun = next(d for d in j["dates"] if d["weekday"] == "zondag")
    assert sun["window"]["bijlage3"] and sun["window"]["start"] == "09:00"
    # Volledig gespeelde dag: /plan rekent niet, geeft GESPEELD + de vaste wedstrijden.
    p = client.post("/plan", json={"club": cid, "date": fri[0]["date"], "time_limit_s": 1}).json()
    assert p["status"] == "GESPEELD" and p["played"] and p["rows"] == []
    # Gespeelde wedstrijd verzetten mag niet.
    w = next(x for x in fri[0]["wedstrijden"] if x["status"] == "gespeeld")
    r = client.post("/plan", json={"club": cid, "date": "16-10-2026", "time_limit_s": 1,
                                   "moves": [{"schema": w["schema"], "home": w["home"], "from": fri[0]["date"], "to": "16-10-2026"}]})
    assert r.status_code == 409
    # Opgeslagen schema van een dag in het verleden blijft staan.
    ok = {"plan": {"rows": []}, "source": "berekend"}
    assert client.put(f"/clubs/{cid}/schedule/{fri[0]['date']}", json=ok).status_code == 200
    assert client.put(f"/clubs/{cid}/schedule/{fri[0]['date']}", json=ok).status_code == 409
    assert client.delete(f"/clubs/{cid}/schedule/{fri[0]['date']}").status_code == 409
    # Opnieuw verwerken met de bewaarde upload.
    r2 = client.post(f"/clubs/{cid}/season/reprocess").json()
    assert r2["report"]["imported"] == 112
    summ = client.get(f"/clubs/{cid}").json()["summary"]
    assert summ["weekdays"]["vrijdag"]["courts"] == 6 and "courts" not in summ["weekdays"]["vrijdag"]["defaults"]
    assert summ["weekdays"]["vrijdag"]["start"] == "19:00" and "start" in summ["weekdays"]["vrijdag"]["defaults"]
