"""Baanschemaatje live-backend (FastAPI).

Rekent baanschema's live met de generieke CP-SAT-planner uit het
``baanschemaatje``-package. Staat los van ``backend/`` (Koens bestaande
backend) en van de live Pages-site: deze service leest alleen clubprofielen
en de seizoensexport en schrijft niets terug.

Endpoints
  GET  /health                       status + versie
  GET  /clubs                        clubs (ingebouwd + opgeslagen) met samenvatting
  POST /clubs                        nieuwe club → eenmalig de bewerk-sleutel
  GET  /clubs/{id}                   profiel (ruw + samenvatting), seizoen-info
  PUT  /clubs/{id}/profile           profiel opslaan
  POST /clubs/{id}/season            KNLTB-export uploaden (alle weekdagen; ruwe upload wordt bewaard)
  POST /clubs/{id}/season/reprocess  laatst geüploade export opnieuw verwerken (nieuwe importregels)
  GET  /clubs/{id}/season            speeldagen + wedstrijden
  GET  /clubs/{id}/schedules         alle opgeslagen dagschema's (voor het seizoensoverzicht)
  GET/PUT/DELETE /clubs/{id}/schedule/{datum}   opgeslagen baanschema van één dag
  GET/PUT /clubs/{id}/moves          opgeslagen verzettingen (wedstrijd van dag X naar Y)
  GET  /dates?club=<id>              speeldagen met aantal wedstrijden
  POST /plan                         één speeldag plannen  → plan-JSON zoals web/baanschemaatje/data/<club>/<datum>.json
                                     optioneel "moves": [{schema, home, from, to}] = verzette wedstrijden (bv. naar een inhaaldag)
  POST /scenarios                    oplossingen voor een dag die niet past → zoals <datum>.solutions.json

Beveiliging: alles is voorlopig open, ook schrijven (besluit Oscar
09-10-2026). Alle schrijfacties lopen via ``auth.authorize_write``; daar komt
later "Login per club" (ROADMAP). Ingebouwde clubs (clubs/*.yaml) zijn niet
te overschrijven via POST /clubs; een opgeslagen club met dezelfde id (geseed)
gaat voor.

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
import csv
import io
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
import re
import sys
import tempfile
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, PrivateAttr

import baanschemaatje
from baanschemaatje import miniyaml
from baanschemaatje.profile import ClubProfile, ProfileError, profile_from_dict
from baanschemaatje.season import Season, load_season_tsv
from baanschemaatje.knltb_import import WEEKDAYS_NL, ImportError_, parse_export, to_tsv
from baanschemaatje.validation import validate_plan
from baanschemaatje.webexport import profile_summary

sys.path.insert(0, str(Path(__file__).resolve().parent))
from auth import authorize_write  # noqa: E402
from store import make_store  # noqa: E402

ROOT = Path(os.environ.get("BS_ROOT", Path(__file__).resolve().parents[2]))
CLUBS_DIR = Path(os.environ.get("BS_CLUBS_DIR", ROOT / "clubs"))
SEASON_FILE = Path(os.environ.get("BS_SEASON", ROOT / "data" / "season_2026-2027.tsv"))
MAX_TIME_LIMIT = float(os.environ.get("BS_MAX_TIME_LIMIT", "30"))
DEFAULT_TIME_LIMIT = float(os.environ.get("BS_DEFAULT_TIME_LIMIT", "15"))
# Totale rekentijd voor /scenarios (alle scenario's samen, ruwweg).
SCENARIO_BUDGET = float(os.environ.get("BS_SCENARIO_BUDGET", "240"))
WORKERS = int(os.environ.get("BS_WORKERS", "4"))
MAX_CLUBS = int(os.environ.get("BS_MAX_CLUBS", "100"))
MAX_SCHEDULE_BYTES = int(os.environ.get("BS_MAX_SCHEDULE_BYTES", str(1024 * 1024)))
MAX_SCHEDULE_ROWS = int(os.environ.get("BS_MAX_SCHEDULE_ROWS", "1500"))
MAX_MOVES = int(os.environ.get("BS_MAX_MOVES", "500"))
MAX_UPLOAD = int(os.environ.get("BS_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
STORE = make_store()

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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=3600,
)

# CP-SAT gebruikt alle cores; één solve tegelijk per instance (Cloud Run
# concurrency staat ook op 1, dit is de vangrail voor lokaal/tests).
_SOLVE_LOCK = threading.Lock()
_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
_CACHE_MAX = 64
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "club"


# ---------------------------------------------------------------- data


def _builtin_files() -> dict[str, Path]:
    return {p.stem: p for p in sorted(CLUBS_DIR.glob("*.yaml"))}


def _club_files() -> dict[str, Path]:  # compat
    return _builtin_files()


def _get_json(key: str) -> Any:
    b = STORE.get(key)
    return json.loads(b) if b is not None else None


def _meta(club_id: str) -> dict[str, Any] | None:
    return _get_json(f"clubs/{club_id}/meta.json") if _ID_RE.match(club_id) else None


def _all_ids() -> list[str]:
    return sorted(set(_builtin_files()) | set(STORE.list_clubs()))


def _club_raw(club_id: str) -> dict[str, Any]:
    """Opgeslagen profiel gaat voor het ingebouwde (clubs/*.yaml)."""
    if _meta(club_id) is not None:
        raw = _get_json(f"clubs/{club_id}/profile.json")
        if raw is not None:
            return raw
    files = _builtin_files()
    if club_id not in files:
        raise HTTPException(404, f"onbekende club '{club_id}'")
    return miniyaml.loads(files[club_id].read_text(encoding="utf-8")) or {}


_SEASON_DIR = Path(tempfile.gettempdir()) / "baanschemaatje-seasons"


def _season_path(club_id: str | None) -> Path:
    """Seizoensbestand van de club (opgeslagen upload) of het standaardseizoen."""
    if club_id and _meta(club_id) is not None:
        b = STORE.get(f"clubs/{club_id}/season.tsv")
        if b is not None:
            _SEASON_DIR.mkdir(parents=True, exist_ok=True)
            p = _SEASON_DIR / f"{club_id}-{hashlib.sha256(b).hexdigest()[:16]}.tsv"
            if not p.exists():
                p.write_bytes(b)
            return p
    return SEASON_FILE


@lru_cache(maxsize=64)
def _season_at(path: str, home_name: str) -> Season:
    return load_season_tsv(path, home_name)


def _season(home_name: str, path: Path | None = None) -> Season:
    return _season_at(str(path or SEASON_FILE), home_name)


def _profile(raw: dict, source: str) -> ClubProfile:
    try:
        return profile_from_dict(copy.deepcopy(raw), source=source)
    except ProfileError as exc:
        raise HTTPException(422, f"ongeldig clubprofiel: {exc}") from exc


def _writable(club_id: str, request: Request | None) -> dict[str, Any]:
    meta = _meta(club_id)
    if meta is None:
        raise HTTPException(404 if club_id not in _builtin_files() else 403,
                            f"club '{club_id}' is niet bewerkbaar (alleen-lezen voorbeeldprofiel)")
    authorize_write(club_id, request)
    return meta


def _put_meta(club_id: str, meta: dict[str, Any]) -> None:
    meta["updated_at"] = _now()
    STORE.put(f"clubs/{club_id}/meta.json", json.dumps(meta, ensure_ascii=False, indent=1).encode(), "application/json")


def _public_meta(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    if meta is None:
        return None
    return dict(meta)


def _deep_merge(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = _deep_merge(base.get(k), v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


class Move(BaseModel):
    """Eén verzette thuiswedstrijd: (schema, thuisteam) van speeldag ``from`` naar ``to``."""
    schema_: str = Field(..., alias="schema", description="Schema zoals in de export/het plan (rij 'team')")
    home: str = Field(..., description="thuisteam, bv. MIERLO 3")
    from_: str = Field(..., alias="from", description="oorspronkelijke speeldag dd-mm-YYYY")
    to: str = Field(..., description="nieuwe dag dd-mm-YYYY, bv. een KNLTB-inhaaldag")

    model_config = {"populate_by_name": True}


def _apply_moves(spath: Path, moves: list[Move]) -> tuple[Path, list[dict[str, Any]]]:
    """Schrijf een kopie van het seizoensbestand met verzette wedstrijden (alleen de kolom Datum wijzigt).

    Zo plannen planner én validator met hetzelfde seizoen. Geeft (pad, toegepaste verzettingen)."""
    if not moves:
        return spath, []
    for m in moves:
        for d in (m.from_, m.to):
            try:
                datetime.strptime(d, "%d-%m-%Y")
            except ValueError as exc:
                raise HTTPException(422, f"ongeldige datum '{d}' in verzetting (verwacht dd-mm-jjjj)") from exc
    with spath.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh, delimiter="\t"))
    if not rows:
        return spath, []
    hdr = rows[0]
    try:
        i_d, i_s, i_1, i_2 = (hdr.index(k) for k in ("Datum", "Schema", "Team 1", "Team 2"))
    except ValueError as exc:
        raise HTTPException(422, f"seizoensbestand mist kolom: {exc}") from exc
    i_st = hdr.index("Status") if "Status" in hdr else None
    applied = []
    for m in moves:
        hit = 0
        for r in rows[1:]:
            if len(r) <= max(i_d, i_s, i_1, i_2):
                continue
            if (r[i_d].strip() == m.from_ and " ".join(r[i_s].split()) == " ".join(m.schema_.split())
                    and m.home.strip().upper() in (r[i_1].strip().upper(), r[i_2].strip().upper())):
                if i_st is not None and len(r) > i_st and r[i_st].strip() == "gespeeld":
                    raise HTTPException(409, f"verzetting: '{m.schema_}' van {m.home} op {m.from_} is al gespeeld")
                r[i_d] = m.to
                hit += 1
        if not hit:
            raise HTTPException(404, f"verzetting: geen wedstrijd '{m.schema_}' van {m.home} op {m.from_}")
        applied.append({"schema": m.schema_, "home": m.home, "from": m.from_, "to": m.to})
    buf = io.StringIO()
    csv.writer(buf, delimiter="\t", lineterminator="\n").writerows(rows)
    b = buf.getvalue().encode("utf-8")
    _SEASON_DIR.mkdir(parents=True, exist_ok=True)
    p = _SEASON_DIR / f"moved-{hashlib.sha256(b).hexdigest()[:16]}.tsv"
    if not p.exists():
        p.write_bytes(b)
    return p, applied


# ---------------------------------------------------------------- opgeslagen schema's + verzettingen

_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
SOURCES = ("berekend", "handmatig aangepast")


def _check_date(date: str) -> str:
    if not _DATE_RE.match(date):
        raise HTTPException(422, "datum moet dd-mm-jjjj zijn")
    try:
        datetime.strptime(date, "%d-%m-%Y")
    except ValueError as exc:
        raise HTTPException(422, f"ongeldige datum {date}") from exc
    return date


async def _json_body(request: Request, limit: int) -> Any:
    raw = await request.body()
    if len(raw) > limit:
        raise HTTPException(413, f"te groot ({len(raw)} bytes, max {limit})")
    try:
        return json.loads(raw or b"null")
    except ValueError as exc:
        raise HTTPException(422, "geen geldige JSON") from exc


def _sched_key(club_id: str, date: str) -> str:
    return f"clubs/{club_id}/schedules/{date}.json"


def _known_club(club_id: str) -> None:
    if club_id not in _builtin_files() and _meta(club_id) is None:
        raise HTTPException(404, f"onbekende club '{club_id}'")


class SaveSchedule(BaseModel):
    """Baanschema van één dag zoals de gebruiker het heeft (berekend en/of handmatig versleept)."""
    plan: dict[str, Any] = Field(..., description="plan-JSON; minstens 'rows' (lijst planregels)")
    source: str = Field("berekend", description="'berekend' of 'handmatig aangepast'")
    check: dict[str, Any] = Field(default_factory=dict, description="samenvatting directe controle (aantallen per soort)")
    sig: str | None = Field(None, description="verzettingen die deze dag raken op het moment van opslaan (client)")


def _validate_schedule(body: Any) -> SaveSchedule:
    try:
        sch = SaveSchedule.model_validate(body)
    except Exception as exc:  # pydantic ValidationError
        raise HTTPException(422, f"ongeldig schema: {exc}") from exc
    rows = sch.plan.get("rows")
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise HTTPException(422, "plan.rows moet een lijst planregels zijn")
    if len(rows) > MAX_SCHEDULE_ROWS:
        raise HTTPException(413, f"te veel planregels ({len(rows)}, max {MAX_SCHEDULE_ROWS})")
    if sch.source not in SOURCES:
        raise HTTPException(422, f"source moet een van {SOURCES} zijn")
    return sch


def _today_ams():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Europe/Amsterdam")).date()


def _guard_past(club_id: str, date: str, request: Request) -> None:
    """Opgeslagen schema van een dag in het verleden blijft staan (gespeeld = waarheid).
    Alleen als er nog niets is opgeslagen mag het, of met ?force=1."""
    if datetime.strptime(date, "%d-%m-%Y").date() >= _today_ams():
        return
    if request.query_params.get("force") in ("1", "true"):
        return
    if STORE.get(_sched_key(club_id, date)) is not None:
        raise HTTPException(409, f"{date} ligt in het verleden; het opgeslagen schema blijft staan (gespeeld)")


@app.get("/clubs/{club_id}/schedules")
def list_schedules(club_id: str) -> dict[str, Any]:
    _known_club(club_id)
    out: dict[str, Any] = {}
    for key in STORE.list(f"clubs/{club_id}/schedules/"):
        if key.endswith(".json"):
            j = _get_json(key)
            if j:
                out[j.get("date") or Path(key).stem] = j
    return {"club": club_id, "schedules": out}


@app.get("/clubs/{club_id}/schedule/{date}")
def get_schedule(club_id: str, date: str) -> dict[str, Any]:
    _known_club(club_id)
    j = _get_json(_sched_key(club_id, _check_date(date)))
    if j is None:
        raise HTTPException(404, f"geen opgeslagen baanschema voor {date}")
    return j


@app.put("/clubs/{club_id}/schedule/{date}")
async def put_schedule(club_id: str, date: str, request: Request) -> dict[str, Any]:
    _check_date(date)
    _writable(club_id, request)
    sch = _validate_schedule(await _json_body(request, MAX_SCHEDULE_BYTES))
    _guard_past(club_id, date, request)
    doc = {"club": club_id, "date": date, "saved_at": _now(), "source": sch.source,
           "check": sch.check, "sig": sch.sig, "plan": sch.plan}
    STORE.put(_sched_key(club_id, date), json.dumps(doc, ensure_ascii=False).encode(), "application/json")
    return {k: v for k, v in doc.items() if k != "plan"}


@app.delete("/clubs/{club_id}/schedule/{date}")
def delete_schedule(club_id: str, date: str, request: Request) -> dict[str, Any]:
    _check_date(date)
    _writable(club_id, request)
    _guard_past(club_id, date, request)
    return {"ok": True, "deleted": STORE.delete(_sched_key(club_id, date))}


@app.get("/clubs/{club_id}/moves")
def get_moves(club_id: str) -> dict[str, Any]:
    _known_club(club_id)
    j = _get_json(f"clubs/{club_id}/moves.json")
    return j or {"club": club_id, "moves": [], "saved_at": None}


@app.put("/clubs/{club_id}/moves")
async def put_moves(club_id: str, request: Request) -> dict[str, Any]:
    _writable(club_id, request)
    body = await _json_body(request, MAX_SCHEDULE_BYTES)
    moves = body.get("moves") if isinstance(body, dict) else None
    if not isinstance(moves, list):
        raise HTTPException(422, "verwacht {\"moves\": [...]}")
    if len(moves) > MAX_MOVES:
        raise HTTPException(413, f"te veel verzettingen ({len(moves)}, max {MAX_MOVES})")
    for m in moves:
        try:
            mv = Move.model_validate(m)
        except Exception as exc:
            raise HTTPException(422, f"ongeldige verzetting: {exc}") from exc
        _check_date(mv.from_)
        _check_date(mv.to)
    doc = {"club": club_id, "saved_at": _now(), "moves": moves}
    STORE.put(f"clubs/{club_id}/moves.json", json.dumps(doc, ensure_ascii=False).encode(), "application/json")
    return {"club": club_id, "saved_at": doc["saved_at"], "count": len(moves)}


class PlanRequest(BaseModel):
    club: str | dict[str, Any] = Field(..., description="club-id (opgeslagen of clubs/*.yaml) of een inline clubprofiel")
    date: str = Field(..., description="speeldag als dd-mm-YYYY")
    overrides: dict[str, Any] | None = Field(None, description="diep samengevoegd met het clubprofiel")
    time_limit_s: float | None = Field(None, gt=0, description=f"per solverpoging, max {MAX_TIME_LIMIT}s")
    seed: int = 42
    validate_plan: bool = Field(True, alias="validate")
    moves: list[Move] | None = Field(None, description="verzette wedstrijden (bv. naar een inhaaldag); alleen voor deze berekening")

    model_config = {"populate_by_name": True}
    _moves_applied: list[dict[str, Any]] = PrivateAttr(default_factory=list)


def _resolve(req: PlanRequest) -> tuple[str, ClubProfile, dict[str, Any], Season, Path]:
    if isinstance(req.club, str):
        club_id, raw = req.club, _club_raw(req.club)
        spath = _season_path(req.club)
    else:
        raw = req.club
        club_id = str((raw.get("club") or {}).get("id") or "inline")
        spath = SEASON_FILE
    if req.overrides:
        raw = _deep_merge(raw, req.overrides)
        club_id = f"{club_id}+overrides"
    prof = _profile(raw, club_id)
    spath, req._moves_applied = _apply_moves(spath, req.moves or [])
    season = _season(prof.knltb_name, spath)
    if req.date not in season.dates():
        raise HTTPException(404, f"datum {req.date} niet in seizoen; beschikbaar: {', '.join(season.dates())}")
    return club_id, prof, raw, season, spath


def _time_limit(req: PlanRequest) -> float:
    tl = req.time_limit_s if req.time_limit_s is not None else DEFAULT_TIME_LIMIT
    return max(1.0, min(float(tl), MAX_TIME_LIMIT))


def _key(kind: str, raw: dict, req: PlanRequest, tl: float, spath: Path) -> str:
    blob = json.dumps([kind, raw, req.date, tl, req.seed, req.validate_plan, spath.name], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _cached(key: str) -> dict[str, Any] | None:
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return copy.deepcopy(_CACHE[key])
    return None


def _store_cache(key: str, val: dict[str, Any]) -> None:
    _CACHE[key] = copy.deepcopy(val)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


def _day_window(prof: ClubProfile | None, date: str, fx: list) -> dict[str, Any] | None:
    if prof is None:
        return None
    dp = prof.for_date(date, fx)
    from baanschemaatje.profile import min_to_hhmm
    return {"start": min_to_hhmm(dp.day_start), "last_start": min_to_hhmm(dp.last_start),
            "end": min_to_hhmm(dp.day_end), "courts": dp.courts, "bijlage3": dp.bijlage3, "lighting": dp.lighting}


def _season_view(season: Season, prof: ClubProfile | None = None) -> list[dict[str, Any]]:
    out = []
    for d, fx in season.by_date().items():
        played = [f for f in fx if f.played]
        out.append({"date": d, "weekday": WEEKDAYS_NL[datetime.strptime(d, "%d-%m-%Y").weekday()], "fixtures": len(fx),
                    "partijen": sum(f.matches for f in fx),
                    "open_fixtures": len(fx) - len(played),
                    "open_partijen": sum(f.matches for f in fx if not f.played),
                    "played": len(played),
                    "dagdelen": sorted({f.dagdeel for f in fx}),
                    "competitions": sorted({" ".join(f.schema.split("–")[0].split()) for f in fx}),
                    "window": _day_window(prof, d, fx),
                    "wedstrijden": [{"label": f.label, "schema": f.schema, "category": f.category.value,
                                     "matches": f.matches, "singles": f.singles, "doubles": f.doubles, "mix": f.mix,
                                     "home": f.home_team, "away": f.away_team, "dagdeel": f.dagdeel,
                                     "export_start": f.export_start, "result": f.result, "status": f.status}
                                    for f in fx]})
    out.sort(key=lambda x: datetime.strptime(x["date"], "%d-%m-%Y"))
    return out


# ---------------------------------------------------------------- routes


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "baanschemaatje",
        "version": baanschemaatje.__version__,
        "season_file": SEASON_FILE.name,
        "season_present": SEASON_FILE.exists(),
        "clubs": _all_ids(),
        "store": STORE.describe().split(":")[0],
        "regelhulp": True,
        "max_time_limit_s": MAX_TIME_LIMIT,
    }


@app.get("/clubs")
def clubs() -> dict[str, Any]:
    out = []
    for cid in _all_ids():
        meta = _meta(cid)
        try:
            prof = _profile(_club_raw(cid), cid)
        except HTTPException:
            continue
        s = profile_summary(prof, cid)
        s["stored"] = meta is not None
        s["builtin"] = cid in _builtin_files()
        s["has_season"] = bool(meta and meta.get("season"))
        s["demo"] = bool(meta and meta.get("demo"))
        out.append(s)
    return {"season_file": SEASON_FILE.name, "clubs": out}


class CreateClub(BaseModel):
    id: str | None = None
    profile: dict[str, Any]


@app.post("/clubs", status_code=201)
def create_club(body: CreateClub, request: Request) -> dict[str, Any]:
    prof = _profile(body.profile, "nieuw")
    cid = body.id or _slug(prof.name)
    if not _ID_RE.match(cid):
        raise HTTPException(422, "club-id: 2-41 tekens, a-z, 0-9 en '-'")
    if cid in _builtin_files() or _meta(cid) is not None:
        raise HTTPException(409, f"club-id '{cid}' bestaat al")
    if len(STORE.list_clubs()) >= MAX_CLUBS:
        raise HTTPException(429, "maximum aantal clubs bereikt")
    authorize_write(cid, request)
    now = _now()
    STORE.put(f"clubs/{cid}/profile.json", json.dumps(body.profile, ensure_ascii=False, indent=1).encode(), "application/json")
    meta = {"id": cid, "name": prof.name, "created_at": now, "season": None}
    _put_meta(cid, meta)
    return {"id": cid}


@app.get("/clubs/{club_id}")
def get_club(club_id: str) -> dict[str, Any]:
    raw = _club_raw(club_id)
    prof = _profile(raw, club_id)
    meta = _meta(club_id)
    return {"id": club_id, "profile": raw, "summary": profile_summary(prof, club_id),
            "stored": meta is not None, "builtin": club_id in _builtin_files(),
            "editable": meta is not None, "meta": _public_meta(meta)}


@app.put("/clubs/{club_id}/profile")
def put_profile(club_id: str, raw: dict[str, Any], request: Request) -> dict[str, Any]:
    meta = _writable(club_id, request)
    prof = _profile(raw, club_id)
    STORE.put(f"clubs/{club_id}/profile.json", json.dumps(raw, ensure_ascii=False, indent=1).encode(), "application/json")
    meta["name"] = prof.name
    _put_meta(club_id, meta)
    return {"ok": True, "summary": profile_summary(prof, club_id)}


@app.post("/clubs/{club_id}/season")
async def upload_season(club_id: str, request: Request, filename: str = Query("export.xlsx"),
                        days: str = Query("", description="speeldagen, komma-gescheiden (leeg = alle weekdagen)")) -> dict[str, Any]:
    meta = _writable(club_id, request)
    data = await request.body()
    if not data:
        raise HTTPException(400, "leeg bestand")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"bestand te groot (max {MAX_UPLOAD // 1024 // 1024} MB)")
    return _import_season(club_id, meta, data, filename, days, _now())


@app.post("/clubs/{club_id}/season/reprocess")
def reprocess_season(club_id: str, request: Request,
                     days: str = Query("", description="leeg = alle weekdagen")) -> dict[str, Any]:
    """Verwerk de laatst geüploade (ruwe) export opnieuw, bv. na nieuwe importregels."""
    meta = _writable(club_id, request)
    data = STORE.get(f"clubs/{club_id}/upload/latest")
    if data is None:
        raise HTTPException(404, "geen bewaarde upload; upload de KNLTB-export opnieuw")
    s = meta.get("season") or {}
    return _import_season(club_id, meta, data, s.get("filename") or "export.xlsx", days, s.get("uploaded_at") or _now())


def _import_season(club_id: str, meta: dict[str, Any], data: bytes, filename: str, days: str,
                   uploaded_at: str) -> dict[str, Any]:
    prof = _profile(_club_raw(club_id), club_id)
    wd = {d.strip().lower() for d in days.split(",") if d.strip()} or set(WEEKDAYS_NL)
    try:
        rows, rep = parse_export(data, filename, prof.knltb_name, wd)
    except ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc
    if not rows:
        raise HTTPException(422, {"message": f"geen thuiswedstrijden van '{prof.knltb_name}' gevonden op {', '.join(sorted(wd))}",
                                  "report": rep})
    tsv = to_tsv(rows).encode()
    STORE.put(f"clubs/{club_id}/upload/latest", data, "application/octet-stream")
    STORE.put(f"clubs/{club_id}/season.tsv", tsv, "text/tab-separated-values")
    rep["days"] = [d for d in WEEKDAYS_NL if d in wd]
    meta["season"] = {"filename": filename[:120], "uploaded_at": uploaded_at, "processed_at": _now(), "report": rep}
    _put_meta(club_id, meta)
    season = _season(prof.knltb_name, _season_path(club_id))
    return {"ok": True, "report": rep, "dates": _season_view(season, prof)}


@app.get("/clubs/{club_id}/season")
def get_season(club_id: str) -> dict[str, Any]:
    prof = _profile(_club_raw(club_id), club_id)
    spath = _season_path(club_id)
    meta = _meta(club_id)
    return {"club": club_id, "own_season": spath != SEASON_FILE,
            "season": (meta or {}).get("season") if spath != SEASON_FILE else {"filename": SEASON_FILE.name},
            "dates": _season_view(_season(prof.knltb_name, spath), prof)}


@app.get("/dates")
def dates(club: str = Query("", description="club-id; bepaalt thuisteam en seizoen")) -> dict[str, Any]:
    home, spath = "", SEASON_FILE
    if club:
        home = _profile(_club_raw(club), club).knltb_name
        spath = _season_path(club)
    s = _season(home, spath)
    return {"club": club or None, "season_file": spath.name,
            "dates": [{"date": d, "fixtures": len(fx)} for d, fx in s.by_date().items()]}


@app.post("/plan")
def plan(req: PlanRequest) -> dict[str, Any]:
    from baanschemaatje.planner import plan_day

    club_id, prof, raw, season, spath = _resolve(req)
    day_fx = season.day(req.date)
    if day_fx and all(f.played for f in day_fx):
        return {"status": "GESPEELD", "date": req.date, "rows": [], "day_start": None, "courts": prof.courts,
                "stats": {"scheduled": 0, "unscheduled": 0, "solve_time_s": 0}, "attempts": [],
                "summary": {"solved": False, "date": req.date, "status": "GESPEELD", "fixtures": len(day_fx),
                            "played": len(day_fx), "scheduled": 0, "unscheduled": 0},
                "message": "Alle wedstrijden van deze dag zijn gespeeld; er wordt niets gepland.",
                "profile": profile_summary(prof.for_date(req.date, day_fx), club_id),
                "moves_applied": req._moves_applied, "played": _played_view(day_fx), "cached": False}
    tl = _time_limit(req)
    key = _key("plan", raw, req, tl, spath)
    if (hit := _cached(key)) is not None:
        hit["cached"] = True
        return hit
    t0 = time.perf_counter()
    with _SOLVE_LOCK:
        res = plan_day(prof, season.fixtures, req.date, time_limit_s=tl, random_seed=req.seed, workers=WORKERS)
    out = res.to_dict()
    if req.validate_plan:
        out["validator"] = validate_plan({"status": out["status"], "date": req.date, "rows": out["rows"]}, spath, prof)
    v = out.get("validator") or {}
    solved = out["status"] in ("OPTIMAL", "FEASIBLE") and bool(out["rows"])
    # Zelfde velden als een datumregel in index.json van de web-GUI.
    out["summary"] = {
        "solved": solved,
        "date": req.date,
        "status": out["status"],
        "day_start": out["day_start"],
        "fixtures": len(season.day(req.date)),
        "played": sum(1 for f in season.day(req.date) if f.played),
        "scheduled": res.scheduled,
        "unscheduled": res.unscheduled,
        "solve_time_s": out["stats"]["solve_time_s"],
        "hard": v.get("hard"),
        "model": v.get("model"),
        "solutions_file": None,
        "best_solution": None,
    }
    out["profile"] = profile_summary(prof.for_date(req.date, season.day(req.date)), club_id)
    out["live"] = {"time_limit_s": tl, "wall_time_s": round(time.perf_counter() - t0, 2), "workers": WORKERS,
                   "season_file": spath.name}
    out["moves_applied"] = req._moves_applied
    out["played"] = _played_view(season.day(req.date))
    out["cached"] = False
    _store_cache(key, out)
    return out


def _played_view(fx: list) -> list[dict[str, Any]]:
    """Gespeelde wedstrijden van een dag (vast, alleen-lezen)."""
    return [{"label": f.label, "schema": f.schema, "home": f.home_team, "away": f.away_team,
             "export_start": f.export_start, "result": f.result, "matches": f.matches, "status": f.status}
            for f in fx if f.played]


@app.post("/scenarios")
def scenarios(req: PlanRequest, combos: bool = Query(False, description="ook combinaties proberen (duurt langer)")) -> dict[str, Any]:
    from baanschemaatje.planner import plan_day
    from baanschemaatje.scenarios import candidate_scenarios, propose_solutions

    club_id, prof, raw, season, spath = _resolve(req)
    tl = _time_limit(req)
    key = _key(f"scenarios:{combos}", raw, req, tl, spath)
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
            sol["plan"]["validator"] = validate_plan(
                {"status": sol["plan"]["status"], "date": req.date, "rows": sol["plan"]["rows"]}, spath, prof)
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
    _store_cache(key, out)
    return out


# --------------------------------------------------------------------------
# KNLTB-regelhulp: POST /regelhulp {vraag, club?} -> {antwoord, bronnen}
# De regelbank (volledige teksten) staat privé in de opslag
# (regelbank/regelbank.json) of lokaal via BS_REGELBANK; nooit in web/.
# --------------------------------------------------------------------------
from baanschemaatje.regels.antwoord import beantwoord  # noqa: E402
from baanschemaatje.regels.zoek import Index  # noqa: E402

REGELBANK_PATH = os.environ.get("BS_REGELBANK")
REGEL_MAX_VRAAG = int(os.environ.get("BS_REGEL_MAX_VRAAG", "600"))
REGEL_PER_IP_UUR = int(os.environ.get("BS_REGEL_PER_IP_UUR", "20"))
REGEL_PER_DAG = int(os.environ.get("BS_REGEL_PER_DAG", "300"))
_REGEL: dict[str, Any] = {}
_REGEL_LOCK = threading.Lock()
_REGEL_HITS: dict[str, list[float]] = {}
_REGEL_DAG: dict[str, int] = {}
_REGEL_LLM = None  # tests kunnen hier een nep-LLM zetten


class RegelVraag(BaseModel):
    vraag: str = Field(min_length=3)
    club: str | None = None


def _regelindex() -> Index:
    with _REGEL_LOCK:
        if "index" not in _REGEL:
            raw = Path(REGELBANK_PATH).read_bytes() if REGELBANK_PATH else STORE.get("regelbank/regelbank.json")
            if not raw:
                raise HTTPException(503, "regelbank niet beschikbaar")
            rb = json.loads(raw)
            _REGEL["index"] = Index(rb["chunks"])
            _REGEL["gebouwd"] = rb.get("gebouwd")
        return _REGEL["index"]


def _regel_rate(ip: str) -> None:
    """Eenvoudige limiet per instance: per IP per uur en totaal per dag."""
    now = time.time()
    dag = datetime.now(timezone.utc).date().isoformat()
    with _REGEL_LOCK:
        if _REGEL_DAG.get(dag, 0) >= REGEL_PER_DAG:
            raise HTTPException(429, "daglimiet regelhulp bereikt, probeer het morgen opnieuw")
        hits = [t for t in _REGEL_HITS.get(ip, []) if now - t < 3600]
        if len(hits) >= REGEL_PER_IP_UUR:
            raise HTTPException(429, "te veel vragen; probeer het over een uur opnieuw")
        _REGEL_HITS[ip] = hits + [now]
        n = _REGEL_DAG.get(dag, 0) + 1
        _REGEL_DAG.clear()
        _REGEL_DAG[dag] = n


def _club_context(club_id: str | None) -> dict[str, Any] | None:
    if not club_id:
        return None
    try:
        raw = _club_raw(club_id)
        summ = profile_summary(_profile(raw, club_id), club_id)
    except Exception:  # noqa: BLE001 - club is optioneel
        return None
    return {
        "naam": summ.get("name"),
        "banen": summ.get("courts"),
        "dag": summ.get("day"),
        "clubafspraken": [{"regel": r["name"], "params": r["params"], "hard": r["hard"]}
                          for r in summ.get("rules", []) if r.get("club_override")],
    }


@app.post("/regelhulp")
def regelhulp(req: RegelVraag, request: Request) -> dict[str, Any]:
    vraag = req.vraag.strip()
    if len(vraag) > REGEL_MAX_VRAAG:
        raise HTTPException(413, f"vraag te lang (max {REGEL_MAX_VRAAG} tekens)")
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    index = _regelindex()
    _regel_rate(ip)
    kw = {"llm": _REGEL_LLM} if _REGEL_LLM else {}
    try:
        out = beantwoord(vraag, index, _club_context(req.club), **kw)
    except RuntimeError as e:
        raise HTTPException(502, f"taalmodel niet bereikbaar: {e}") from e
    out["regelbank"] = _REGEL.get("gebouwd")
    out["disclaimer"] = "Advies op basis van de KNLTB-regels; bij twijfel beslist de competitieleider of de KNLTB."
    return out
