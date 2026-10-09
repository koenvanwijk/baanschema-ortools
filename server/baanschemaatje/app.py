"""Baanschemaatje live-backend (FastAPI).

Rekent baanschema's live met de generieke CP-SAT-planner uit het
``baanschemaatje``-package. Staat los van ``backend/`` (Koens bestaande
backend) en van de live Pages-site: deze service leest alleen clubprofielen
en de seizoensexport en schrijft niets terug.

Endpoints
  GET  /health                       status + versie
  GET  /clubs                        clubprofielen (zelfde samenvatting als de web-GUI)
  GET  /dates?club=<id>              speeldagen met aantal wedstrijden
  POST /plan                         één speeldag plannen  → plan-JSON zoals web/baanschemaatje/data/<club>/<datum>.json
  POST /scenarios                    oplossingen voor een dag die niet past → zoals <datum>.solutions.json

Request-body voor /plan en /scenarios::

  {"club": "mierlo" | {<inline clubprofiel>},
   "date": "13-09-2026",
   "overrides": {"rules": {"start_window_8p": {"to": "12:00"}}, "day": {"start": "08:30"}},
   "time_limit_s": 15,
   "validate": true}

``overrides`` wordt diep samengevoegd met het clubprofiel (zelfde schema als
``clubs/*.yaml``). ``time_limit_s`` is begrensd door ``BS_MAX_TIME_LIMIT``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import baanschemaatje
from baanschemaatje import miniyaml
from baanschemaatje.profile import ClubProfile, ProfileError, profile_from_dict
from baanschemaatje.season import Season, load_season_tsv
from baanschemaatje.webexport import _validate, profile_summary

ROOT = Path(os.environ.get("BS_ROOT", Path(__file__).resolve().parents[2]))
CLUBS_DIR = Path(os.environ.get("BS_CLUBS_DIR", ROOT / "clubs"))
SEASON_FILE = Path(os.environ.get("BS_SEASON", ROOT / "data" / "season_2026-2027.tsv"))
MAX_TIME_LIMIT = float(os.environ.get("BS_MAX_TIME_LIMIT", "30"))
DEFAULT_TIME_LIMIT = float(os.environ.get("BS_DEFAULT_TIME_LIMIT", "15"))
# Totale rekentijd voor /scenarios (alle scenario's samen, ruwweg).
SCENARIO_BUDGET = float(os.environ.get("BS_SCENARIO_BUDGET", "240"))
WORKERS = int(os.environ.get("BS_WORKERS", "4"))

DEFAULT_ORIGINS = [
    "https://raw.githack.com",
    "https://rawcdn.githack.com",
    "https://koenvanwijk.github.io",
    "http://localhost",
    "http://127.0.0.1",
]
ORIGINS = [o for o in os.environ.get("BS_CORS_ORIGINS", ",".join(DEFAULT_ORIGINS)).split(",") if o]

app = FastAPI(title="Baanschemaatje", version=baanschemaatje.__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    # localhost / 127.0.0.1 op elke poort (lokaal testen van de web-GUI).
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    max_age=3600,
)

# CP-SAT gebruikt alle cores; één solve tegelijk per instance (Cloud Run
# concurrency staat ook op 1, dit is de vangrail voor lokaal/tests).
_SOLVE_LOCK = threading.Lock()
_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
_CACHE_MAX = 64


# ---------------------------------------------------------------- data


def _club_files() -> dict[str, Path]:
    return {p.stem: p for p in sorted(CLUBS_DIR.glob("*.yaml"))}


@lru_cache(maxsize=None)
def _club_raw(club_id: str) -> dict[str, Any]:
    files = _club_files()
    if club_id not in files:
        raise HTTPException(404, f"onbekende club '{club_id}' (beschikbaar: {', '.join(files)})")
    return miniyaml.loads(files[club_id].read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=16)
def _season(home_name: str) -> Season:
    return load_season_tsv(SEASON_FILE, home_name)


def _deep_merge(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = _deep_merge(base.get(k), v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


class PlanRequest(BaseModel):
    club: str | dict[str, Any] = Field(..., description="club-id (bestand in clubs/) of een inline clubprofiel")
    date: str = Field(..., description="speeldag als dd-mm-YYYY")
    overrides: dict[str, Any] | None = Field(None, description="diep samengevoegd met het clubprofiel")
    time_limit_s: float | None = Field(None, gt=0, description=f"per solverpoging, max {MAX_TIME_LIMIT}s")
    seed: int = 42
    validate_plan: bool = Field(True, alias="validate")

    model_config = {"populate_by_name": True}


def _resolve(req: PlanRequest) -> tuple[str, ClubProfile, dict[str, Any], Season]:
    if isinstance(req.club, str):
        club_id, raw = req.club, _club_raw(req.club)
    else:
        raw = req.club
        club_id = str((raw.get("club") or {}).get("id") or "inline")
    if req.overrides:
        raw = _deep_merge(raw, req.overrides)
        club_id = f"{club_id}+overrides"
    try:
        prof = profile_from_dict(copy.deepcopy(raw), source=club_id)
    except ProfileError as exc:
        raise HTTPException(422, f"ongeldig clubprofiel: {exc}") from exc
    season = _season(prof.knltb_name)
    if req.date not in season.dates():
        raise HTTPException(404, f"datum {req.date} niet in seizoen; beschikbaar: {', '.join(season.dates())}")
    return club_id, prof, raw, season


def _time_limit(req: PlanRequest) -> float:
    tl = req.time_limit_s if req.time_limit_s is not None else DEFAULT_TIME_LIMIT
    return max(1.0, min(float(tl), MAX_TIME_LIMIT))


def _key(kind: str, raw: dict, req: PlanRequest, tl: float) -> str:
    blob = json.dumps([kind, raw, req.date, tl, req.seed, req.validate_plan], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _cached(key: str) -> dict[str, Any] | None:
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return copy.deepcopy(_CACHE[key])
    return None


def _store(key: str, val: dict[str, Any]) -> None:
    _CACHE[key] = copy.deepcopy(val)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


# ---------------------------------------------------------------- routes


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "baanschemaatje",
        "version": baanschemaatje.__version__,
        "season_file": SEASON_FILE.name,
        "season_present": SEASON_FILE.exists(),
        "clubs": list(_club_files()),
        "max_time_limit_s": MAX_TIME_LIMIT,
    }


@app.get("/clubs")
def clubs() -> dict[str, Any]:
    out = []
    for cid in _club_files():
        prof = profile_from_dict(copy.deepcopy(_club_raw(cid)), source=cid)
        out.append(profile_summary(prof, cid))
    return {"season_file": SEASON_FILE.name, "clubs": out}


@app.get("/dates")
def dates(club: str = Query("", description="club-id; bepaalt welk team als thuisteam telt")) -> dict[str, Any]:
    home = ""
    if club:
        home = profile_from_dict(copy.deepcopy(_club_raw(club)), source=club).knltb_name
    s = _season(home)
    return {"club": club or None, "season_file": SEASON_FILE.name,
            "dates": [{"date": d, "fixtures": len(fx)} for d, fx in s.by_date().items()]}


@app.post("/plan")
def plan(req: PlanRequest) -> dict[str, Any]:
    from baanschemaatje.planner import plan_day

    club_id, prof, raw, season = _resolve(req)
    tl = _time_limit(req)
    key = _key("plan", raw, req, tl)
    if (hit := _cached(key)) is not None:
        hit["cached"] = True
        return hit
    t0 = time.perf_counter()
    with _SOLVE_LOCK:
        res = plan_day(prof, season.fixtures, req.date, time_limit_s=tl, random_seed=req.seed, workers=WORKERS)
    out = res.to_dict()
    if req.validate_plan:
        out["validator"] = _validate({"status": out["status"], "date": req.date, "rows": out["rows"]}, SEASON_FILE)
    v = out.get("validator") or {}
    # Zelfde velden als een datumregel in index.json van de web-GUI.
    solved = out["status"] in ("OPTIMAL", "FEASIBLE") and bool(out["rows"])
    out["summary"] = {
        "solved": solved,
        "date": req.date,
        "status": out["status"],
        "day_start": out["day_start"],
        "fixtures": len(season.day(req.date)),
        "scheduled": res.scheduled,
        "unscheduled": res.unscheduled,
        "solve_time_s": out["stats"]["solve_time_s"],
        "hard": v.get("hard"),
        "model": v.get("model"),
        "solutions_file": None,
        "best_solution": None,
    }
    out["profile"] = profile_summary(prof, club_id)
    out["live"] = {"time_limit_s": tl, "wall_time_s": round(time.perf_counter() - t0, 2), "workers": WORKERS}
    out["cached"] = False
    _store(key, out)
    return out


@app.post("/scenarios")
def scenarios(req: PlanRequest, combos: bool = Query(False, description="ook combinaties proberen (duurt langer)")) -> dict[str, Any]:
    from baanschemaatje.planner import plan_day
    from baanschemaatje.scenarios import candidate_scenarios, propose_solutions

    club_id, prof, raw, season = _resolve(req)
    tl = _time_limit(req)
    key = _key(f"scenarios:{combos}", raw, req, tl)
    if (hit := _cached(key)) is not None:
        hit["cached"] = True
        return hit
    t0 = time.perf_counter()
    with _SOLVE_LOCK:
        base = plan_day(prof, season.fixtures, req.date, time_limit_s=tl, random_seed=req.seed, workers=WORKERS)
        base_rows = base.to_dict()["rows"]
        base_ok = base.status in ("OPTIMAL", "FEASIBLE")
        if base_ok and base.unscheduled == 0:
            sols: list[dict[str, Any]] = []
            per = 0.0
        else:
            day = season.day(req.date)
            n = len(candidate_scenarios(prof, day, base_rows)) + (3 if combos else 0)
            # Elk scenario kan tot ~3 solves doen (optimize/feasibility/fit).
            # Rekentijd-scenario telt 3x; ruwweg 3 solves per scenario.
            per = max(2.0, min(tl, SCENARIO_BUDGET / max(1, n + 2) / 3))
            sols = propose_solutions(prof, season.fixtures, req.date, base_rows, time_limit_s=per,
                                     seed=req.seed, combos=combos)
    for sol in sols:
        sol["solved"] = sol["status"] in ("OPTIMAL", "FEASIBLE") and bool(sol["plan"]["rows"])
        if not sol["solved"]:
            sol["title"] += f" — geen oplossing binnen {per:.0f}s rekentijd"
    if req.validate_plan:
        for sol in sols:
            sol["plan"]["validator"] = _validate(
                {"status": sol["plan"]["status"], "date": req.date, "rows": sol["plan"]["rows"]}, SEASON_FILE)
            sol["validator_hard"] = sol["plan"]["validator"]["hard"]
    ok = [x for x in sols if x["fits"] and x["knltb_ok"]]
    out = {
        "date": req.date,
        "club": club_id,
        "base_status": base.status,
        "base_solved": base_ok,
        "base_unscheduled": base.unscheduled if base_ok else None,
        "best_solution": ok[0]["title"] if ok else None,
        "solutions": sols,
        "live": {"time_limit_s_per_scenario": round(per, 1), "wall_time_s": round(time.perf_counter() - t0, 2)},
        "cached": False,
    }
    _store(key, out)
    return out
