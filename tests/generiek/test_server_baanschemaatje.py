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
def client(root):
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
