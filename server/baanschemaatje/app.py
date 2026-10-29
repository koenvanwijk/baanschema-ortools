"""Baanschemaatje live-backend (FastAPI).

Rekent baanschema's live met de generieke CP-SAT-planner uit het
``baanschemaatje``-package. Staat los van ``backend/`` (Koens bestaande
backend) en van de live Pages-site: deze service leest alleen clubprofielen
en de seizoensexport en schrijft niets terug.

Endpoints
  GET  /                             product-frontpage (home.html); clublijst na Google-login
  GET  /health                       status + versie
  GET  /clubs                        clubs (ingebouwd + opgeslagen) met samenvatting
  POST /clubs                        nieuwe club (profiel in store; login volgt I3)
  GET  /clubs/{id}                   profiel (ruw + samenvatting), seizoen-info
  PUT  /clubs/{id}/profile           profiel opslaan
  POST /clubs/{id}/season            KNLTB-export uploaden (alle weekdagen; ruwe upload wordt bewaard)
  POST /clubs/{id}/season/reprocess  laatst geüploade export opnieuw verwerken (nieuwe importregels)
  GET  /clubs/{id}/season            speeldagen + wedstrijden
  GET  /clubs/{id}/schedules         alle opgeslagen dagschema's (voor het seizoensoverzicht)
  GET/PUT/DELETE /clubs/{id}/schedule/{datum}   opgeslagen baanschema van één dag
  GET/PUT/DELETE /clubs/{id}/bingo/{date}  bingo-avond (live indelen); PUT met "gen" (optimistische gelijktijdigheid, 409 bij conflict)
  GET/PUT /clubs/{id}/cancellations  wedstrijden die niet gespeeld worden ("vervallen"; sleutel schema+thuis+uit+datum)
  GET/PUT /clubs/{id}/host-away      uitwedstrijden die toch thuis gespeeld worden (banen nodig)
  GET/PUT /clubs/{id}/moves          opgeslagen verzettingen (wedstrijd van dag X naar Y)
  GET  /dates?club=<id>              speeldagen met aantal wedstrijden
  POST /plan                         één speeldag plannen  → plan-JSON zoals web/baanschemaatje/data/<club>/<datum>.json
                                     optioneel "moves": [{schema, home, from, to}] = verzette wedstrijden (bv. naar een inhaaldag)
  POST /scenarios                    oplossingen voor een dag die niet past → zoals <datum>.solutions.json

Beveiliging (I1/I3/I5, Oscar 26-10-2026, herzien zelfde dag): schrijfacties via
``auth.authorize_write`` met rollen (I4). Met Google OAuth: schrijven altijd
achter login+rol (geen open-loophole meer). Kijken (tv/dag/bingolijst + GET
schema/bingo/dayrun) via geheime deellink ``?s=TOKEN`` of ingelogde rol.
Rollen: club_admin (beheer) / commissaris (speeldag); platform_admin via env.
``POST /clubs`` alleen voor platformbeheerder (nooit anoniem open).
Ingebouwde YAML-clubs alleen-lezen.

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
import contextvars
import re
import sys
import tempfile
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, PrivateAttr

import baanschemaatje
from baanschemaatje import miniyaml
from baanschemaatje.profile import ClubProfile, ProfileError, profile_from_dict
from baanschemaatje.season import Season, load_season_tsv
from baanschemaatje.knltb_import import WEEKDAYS_NL, ImportError_, parse_export, to_tsv
from baanschemaatje.validation import validate_plan
from baanschemaatje.webexport import profile_summary

sys.path.insert(0, str(Path(__file__).resolve().parent))
from auth import (  # noqa: E402
    ASSIGNABLE_ROLES,
    ROLE_CLUB_ADMIN,
    ROLE_COMMISSARIS,
    ROLE_LABELS_NL,
    ROLE_VIEWER,
    auth_configured,
    auth_status,
    authorize_platform_admin,
    authorize_view,
    authorize_write,
    can_manage_access,
    clear_pin_cookie,
    clear_session_cookie,
    generate_pin,
    hash_pin,
    pin_record,
    pin_session,
    set_pin_cookie,
    valid_pin_format,
    verify_pin,
    club_roles,
    club_writers,
    consume_oauth_state,
    current_user,
    exchange_code_for_user,
    is_platform_admin,
    new_share_token,
    public_base_url,
    resolve_role,
    set_oauth_state_cookie,
    set_session_cookie,
    share_token_of,
    start_oauth_url,
)
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
    allow_credentials=True,  # sessiecookie na Google-login (zelfde origin op Cloud Run)
    max_age=3600,
)

# CP-SAT gebruikt alle cores; één solve tegelijk per instance (Cloud Run
# concurrency staat ook op 1, dit is de vangrail voor lokaal/tests).
_SOLVE_LOCK = threading.Lock()
_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
_CACHE_MAX = 64
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")

# ---------------------------------------------------------------- democlubs alleen platformbeheerder (Q4)
# Besluit Oscar 29-10-2026: Demo TV en TV Voorbeeld (en elke club met meta.demo) zijn alleen
# zichtbaar/bruikbaar voor de platformbeheerder: niet in 'Mijn clubs' van anderen, kijken én
# schrijven vereisen login als platformbeheerder; deellinks geven geen toegang.
PLATFORM_ONLY_CLUBS = {c.strip() for c in os.environ.get(
    "BS_PLATFORM_ONLY_CLUBS", "demo-tv,voorbeeld-6-banen").split(",") if c.strip()}
_CUR_REQ: contextvars.ContextVar[Request | None] = contextvars.ContextVar("bs_cur_req", default=None)


@app.middleware("http")
async def _request_context(request: Request, call_next):
    """Onthoud het lopende request (voor de democlub-guard diep in de helpers) en sluit de
    statische, vooraf berekende data van platform-only clubs af (/app/data/<club>/...)."""
    tok = _CUR_REQ.set(request)
    try:
        path = request.url.path
        if path.startswith("/app/data/"):
            seg = path[len("/app/data/"):].split("/", 1)[0]
            if seg in PLATFORM_ONLY_CLUBS and auth_configured():
                user = current_user(request)
                if not user or not is_platform_admin(user["email"]):
                    return JSONResponse({"detail": "Democlub: alleen voor de platformbeheerder"},
                                        status_code=401 if not user else 403)
        return await call_next(request)
    finally:
        _CUR_REQ.reset(tok)


def _platform_only(club_id: str | None) -> bool:
    if not club_id:
        return False
    if club_id in PLATFORM_ONLY_CLUBS:
        return True
    m = _meta(club_id)
    return bool(m and (m.get("demo") or m.get("platform_only")))


def _platform_viewer_ok(request: Request | None = None) -> bool:
    if not auth_configured():
        return True  # lokale tests zonder OAuth
    req = request if request is not None else _CUR_REQ.get()
    user = current_user(req) if req is not None else None
    return bool(user and is_platform_admin(user["email"]))


def _guard_platform_only(club_id: str | None, request: Request | None = None) -> None:
    """401/403 voor democlubs als de aanvrager niet de ingelogde platformbeheerder is."""
    if not _platform_only(club_id) or _platform_viewer_ok(request):
        return
    req = request if request is not None else _CUR_REQ.get()
    if req is None or current_user(req) is None:
        raise HTTPException(401, "Democlub: log in met Google als platformbeheerder")
    raise HTTPException(403, "Democlub: alleen toegankelijk voor de platformbeheerder")



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
    _guard_platform_only(club_id)
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


def _writable(club_id: str, request: Request | None, *, min_role: str = ROLE_CLUB_ADMIN) -> dict[str, Any]:
    _guard_platform_only(club_id, request)
    meta = _meta(club_id)
    if meta is None:
        raise HTTPException(404 if club_id not in _builtin_files() else 403,
                            f"club '{club_id}' is niet bewerkbaar (alleen-lezen voorbeeldprofiel)")
    authorize_write(club_id, request, meta=meta, min_role=min_role)
    return meta


def _share_from_request(request: Request | None) -> str | None:
    if request is None:
        return None
    q = request.query_params.get("s") or request.query_params.get("share")
    if q:
        return q
    return request.headers.get("x-bs-share")


def _viewable(club_id: str, request: Request | None) -> dict[str, Any] | None:
    """Controleer kijkrecht (deellink of login+rol); geeft meta terug.
    Democlubs: deellink telt niet, alleen platformbeheerder (Q4)."""
    _guard_platform_only(club_id, request)
    meta = _meta(club_id)
    authorize_view(club_id, request, meta=meta, share_token=_share_from_request(request))
    return meta


def _ensure_share_token(meta: dict[str, Any]) -> str:
    tok = share_token_of(meta)
    if tok:
        return tok
    tok = new_share_token()
    meta["share_token"] = tok
    return tok


def _share_links(club_id: str, request: Request, token: str) -> dict[str, str]:
    base = public_base_url(request)
    return {
        "token": token,
        "tv_template": f"{base}/tv/{club_id}/{{datum}}?s={token}",
        "dag_template": f"{base}/dag/{club_id}/{{datum}}?s={token}",
        "bingolijst_template": f"{base}/bingolijst/{club_id}/{{datum}}?s={token}",
        "hint": "Vervang {datum} door bv. 23-10-2026. Regenereren maakt oude links ongeldig.",
    }


_DEMO_SHARE_OFF = {"disabled": True, "has_token": False,
                   "hint": "Democlub: alleen jij als platformbeheerder hebt toegang; deellinks zijn uitgeschakeld."}


def _put_meta(club_id: str, meta: dict[str, Any]) -> None:
    meta["updated_at"] = _now()
    STORE.put(f"clubs/{club_id}/meta.json", json.dumps(meta, ensure_ascii=False, indent=1).encode(), "application/json")


def _public_meta(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    if meta is None:
        return None
    out = {
        "id": meta.get("id"),
        "name": meta.get("name"),
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "season": meta.get("season"),
        "demo": bool(meta.get("demo")),
        "auth_required": True if auth_configured() else bool(meta.get("auth_required")),
        "has_share_token": bool(share_token_of(meta)),
        "writers": sorted(club_writers(meta)),
        "roles": club_roles(meta),
        # Geen wachtwoordhashes e.d. — later optioneel e-mail+wachtwoord: alleen flags, nooit secrets.
        "password_login": False,
    }
    return out


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
SOURCES = ("berekend", "handmatig aangepast", "herplan")  # herplan = aangepast op de speeldag (dashboard)


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
    _guard_platform_only(club_id)


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
def list_schedules(club_id: str, request: Request) -> dict[str, Any]:
    _known_club(club_id)
    _viewable(club_id, request)
    out: dict[str, Any] = {}
    for key in STORE.list(f"clubs/{club_id}/schedules/"):
        if key.endswith(".json"):
            j = _get_json(key)
            if j:
                out[j.get("date") or Path(key).stem] = j
    return {"club": club_id, "schedules": out}


@app.get("/clubs/{club_id}/schedule/{date}")
def get_schedule(club_id: str, date: str, request: Request) -> dict[str, Any]:
    _known_club(club_id)
    _viewable(club_id, request)
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


# ---------------------------------------------------------------- vervallen wedstrijden ("wordt niet gespeeld")

def _norm(x: Any) -> str:
    return " ".join(str(x or "").split()).upper()


def _ckey(schema: Any, home: Any, away: Any, date: Any) -> tuple[str, str, str, str]:
    a, b = sorted((_norm(home), _norm(away)))  # thuis kan in de export Team 1 of Team 2 zijn
    return (_norm(schema), a, b, str(date or "").strip())


def _cancellations(club_id: str | None) -> list[dict[str, Any]]:
    if not club_id:
        return []
    j = _get_json(f"clubs/{club_id}/cancellations.json")
    return list((j or {}).get("cancellations") or [])


def _cancel_map(cancels: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    return {_ckey(c.get("schema"), c.get("home"), c.get("away"), c.get("date")): c for c in cancels}


def _apply_cancellations(spath: Path, cancels: list[dict[str, Any]]) -> Path:
    """Kopie van het seizoensbestand zonder vervallen wedstrijden: planner en validator zien ze niet.
    Gespeelde wedstrijden (uitslag in de export) blijven altijd staan: de export wint."""
    if not cancels:
        return spath
    cm = _cancel_map(cancels)
    with spath.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh, delimiter="\t"))
    if not rows:
        return spath
    hdr = rows[0]
    try:
        i_d, i_s, i_1, i_2 = (hdr.index(k) for k in ("Datum", "Schema", "Team 1", "Team 2"))
    except ValueError:
        return spath
    i_st = hdr.index("Status") if "Status" in hdr else None
    keep = [hdr]
    for r in rows[1:]:
        if len(r) > max(i_d, i_s, i_1, i_2) and _ckey(r[i_s], r[i_1], r[i_2], r[i_d]) in cm \
                and not (i_st is not None and len(r) > i_st and r[i_st].strip() == "gespeeld"):
            continue
        keep.append(r)
    if len(keep) == len(rows):
        return spath
    buf = io.StringIO()
    csv.writer(buf, delimiter="\t", lineterminator="\n").writerows(keep)
    b = buf.getvalue().encode("utf-8")
    _SEASON_DIR.mkdir(parents=True, exist_ok=True)
    p = _SEASON_DIR / f"cancelled-{hashlib.sha256(b).hexdigest()[:16]}.tsv"
    if not p.exists():
        p.write_bytes(b)
    return p


# ---------------------------------------------------------------- uitwedstrijd → thuis gespeeld

def _away_path(club_id: str | None) -> Path | None:
    """Uitwedstrijden uit de laatste KNLTB-export (away.tsv), of afgeleid van upload/latest."""
    if not club_id or _meta(club_id) is None:
        return None
    b = STORE.get(f"clubs/{club_id}/away.tsv")
    if b is None:
        # Bestaande clubs: eenmalig afleiden uit de bewaarde ruwe upload (geen herimport nodig).
        data = STORE.get(f"clubs/{club_id}/upload/latest")
        if data is None:
            return None
        try:
            prof = _profile(_club_raw(club_id), club_id)
            meta = _meta(club_id) or {}
            fn = ((meta.get("season") or {}).get("filename") or "export.xlsx")
            _, away_rows, _ = parse_export(data, fn, prof.knltb_name)
            b = to_tsv(away_rows).encode()
            STORE.put(f"clubs/{club_id}/away.tsv", b, "text/tab-separated-values")
        except Exception:  # noqa: BLE001
            return None
    _SEASON_DIR.mkdir(parents=True, exist_ok=True)
    p = _SEASON_DIR / f"{club_id}-away-{hashlib.sha256(b).hexdigest()[:16]}.tsv"
    if not p.exists():
        p.write_bytes(b)
    return p


def _host_away_list(club_id: str | None) -> list[dict[str, Any]]:
    if not club_id:
        return []
    j = _get_json(f"clubs/{club_id}/host_away.json")
    return list((j or {}).get("hosted") or [])


def _host_away_map(items: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    return {_ckey(c.get("schema"), c.get("home"), c.get("away"), c.get("date")): c for c in items}


def _apply_host_away(spath: Path, club_id: str, home_name: str) -> Path:
    """Voeg gemarkeerde uitwedstrijden toe aan het seizoensbestand (als thuiswedstrijd).

    In away.tsv staat Team 1 = tegenstander (export-thuis), Team 2 = onze club.
    Voor de planner wisselen we: Team 1 = onze club, Team 2 = tegenstander.
    """
    hosted = _host_away_list(club_id)
    if not hosted:
        return spath
    ap = _away_path(club_id)
    if ap is None:
        return spath
    hm = _host_away_map(hosted)
    with ap.open("r", encoding="utf-8", newline="") as fh:
        away_rows = list(csv.reader(fh, delimiter="\t"))
    if len(away_rows) < 2:
        return spath
    ahdr = away_rows[0]
    try:
        ai_d, ai_s, ai_1, ai_2 = (ahdr.index(k) for k in ("Datum", "Schema", "Team 1", "Team 2"))
    except ValueError:
        return spath
    pick: list[list[str]] = []
    for r in away_rows[1:]:
        if len(r) <= max(ai_d, ai_s, ai_1, ai_2):
            continue
        # na swap is home=onze club (Team 2), away=tegenstander (Team 1)
        if _ckey(r[ai_s], r[ai_2], r[ai_1], r[ai_d]) in hm:
            rr = list(r)
            rr[ai_1], rr[ai_2] = r[ai_2], r[ai_1]
            pick.append(rr)
    if not pick:
        return spath
    with spath.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh, delimiter="\t"))
    if not rows:
        return spath
    hdr = rows[0]
    # Zorg dat kolommen overeenkomen; ontbrekende cellen opvullen.
    out_rows = [hdr] + rows[1:]
    for r in pick:
        aligned = [(r[ahdr.index(c)] if c in ahdr and ahdr.index(c) < len(r) else "") for c in hdr]
        out_rows.append(aligned)
    buf = io.StringIO()
    csv.writer(buf, delimiter="\t", lineterminator="\n").writerows(out_rows)
    b = buf.getvalue().encode("utf-8")
    _SEASON_DIR.mkdir(parents=True, exist_ok=True)
    p = _SEASON_DIR / f"hosted-{hashlib.sha256(b).hexdigest()[:16]}.tsv"
    if not p.exists():
        p.write_bytes(b)
    return p


def _away_fixtures(club_id: str | None, home_name: str) -> list:
    """Uitwedstrijden als Fixture-lijst (home_team = onze club na swap in load_season_tsv)."""
    ap = _away_path(club_id)
    if ap is None:
        return []
    return list(_season(home_name, ap).fixtures)


# ---------------------------------------------------------------- bingo-avond (baancommissaris, live)

MAX_BINGO_BYTES = int(os.environ.get("BS_MAX_BINGO_BYTES", str(512 * 1024)))


def _bingo_key(club_id: str, date: str) -> str:
    return f"clubs/{club_id}/bingo/{date}.json"


def _saved_moves(club_id: str) -> list[Move]:
    """Opgeslagen verzettingen die nog toepasbaar zijn (opgaven en verouderde verzettingen overgeslagen)."""
    spath = _season_path(club_id)
    cm = _cancel_map(_cancellations(club_id))
    gone = {(k[0], t, k[3]) for k in cm for t in (k[1], k[2])}
    out = []
    for m in ((_get_json(f"clubs/{club_id}/moves.json") or {}).get("moves") or []):
        try:
            mv = Move.model_validate(m)
            if (_norm(mv.schema_), _norm(mv.home), mv.from_) in gone:
                continue
            _apply_moves(spath, [mv])
            out.append(mv)
        except Exception:  # noqa: BLE001 - verouderde verzetting: negeren
            continue
    return out


def _bingo_part(f: Any, key: str, lab: str, kind: str) -> dict[str, Any]:
    """Partij met soort (HE/DE/HD/DD/GD) en spelersbehoefte, voor de teambezettingsregels in de bingo-wachtrij."""
    from baanschemaatje.teamrules import part_type, team_demand

    m, w, n = team_demand(f.schema, lab, kind)
    return {"id": f"{key}|{lab}", "label": lab, "kind": kind, "type": part_type(f.schema, lab, kind), "men": m, "women": w, "players": n}


def _bingo_matches(club_id: str, prof: ClubProfile, date: str) -> list[dict[str, Any]]:
    """Wedstrijden van de avond met hun partijen (S/D/GD volgens de KNLTB-categorie); zonder opgaven en gespeelde."""
    from baanschemaatje.planner import build_parts
    from baanschemaatje.teamrules import team_order_rules

    # Opgeslagen verzettingen tellen mee: een naar deze bingo-avond verzette wedstrijd verschijnt
    # bij de commissaris (en een weg-verzette verdwijnt). Ongeldige/verouderde verzettingen worden overgeslagen.
    spath = _apply_host_away(_season_path(club_id), club_id, prof.knltb_name)
    cm = _cancel_map(_cancellations(club_id))
    moves = _saved_moves(club_id)
    moved_in = {(_norm(m.schema_), _norm(m.home)): m.from_ for m in moves if m.to == date}
    spath, _ = _apply_moves(spath, moves)
    season = _season(prof.knltb_name, spath)
    hm = _host_away_map(_host_away_list(club_id))
    out = []
    for f in season.day(date):
        if f.played or _ckey(f.schema, f.home_team, f.away_team, f.date) in cm or f.is_block:
            continue
        key = f"{' '.join(f.schema.split())}|{f.home_team}"
        out.append({"key": key, "label": f.label, "schema": f.schema, "home": f.home_team, "away": f.away_team,
                    "category": f.category.value, "export_start": f.export_start,
                    "moved_from": moved_in.get((_norm(f.schema), _norm(f.home_team))),
                    "hosted_away": _ckey(f.schema, f.home_team, f.away_team, f.date) in hm,
                    "duration": prof.duration_for(f.category, f.export_duration),
                    "rules": team_order_rules(f, prof.rules["waterfall_8p"].hard),
                    "parts": [_bingo_part(f, key, lab, kind) for lab, kind in build_parts(f)]})
    return out


@app.get("/clubs/{club_id}/bingo/{date}")
def get_bingo(club_id: str, date: str, request: Request) -> dict[str, Any]:
    _known_club(club_id)
    _viewable(club_id, request)
    _check_date(date)
    prof = _profile(_club_raw(club_id), club_id)
    data, gen = STORE.get_gen(_bingo_key(club_id, date))
    # Inclusief gemarkeerde uitwedstrijden (D3): venster/mode klopt ook op een dag
    # die alleen hosted-away heeft, en op bingo-avonden (vrijdag e.d.).
    fx = _season(prof.knltb_name, _apply_host_away(_season_path(club_id), club_id, prof.knltb_name)).day(date)
    return {"club": club_id, "date": date, "name": prof.name, "gen": gen,
            "state": json.loads(data) if data else None,
            "mode": prof.day_mode(WEEKDAYS_NL[datetime.strptime(date, "%d-%m-%Y").weekday()]),
            "window": _day_window(prof, date, fx), "matches": _bingo_matches(club_id, prof, date),
            "demo": _is_demo(club_id)}


@app.put("/clubs/{club_id}/bingo/{date}")
async def put_bingo(club_id: str, date: str, request: Request) -> dict[str, Any]:
    # Speeldag: baancommissaris (I4). Schrijven altijd achter login bij OAuth.
    _writable(club_id, request, min_role=ROLE_COMMISSARIS)
    _check_date(date)
    body = await _json_body(request, MAX_BINGO_BYTES)
    if not isinstance(body, dict) or not isinstance(body.get("state"), dict) or not isinstance(body.get("gen"), int):
        raise HTTPException(422, 'verwacht {"state": {...}, "gen": <getal>}')
    state = body["state"]
    state["saved_at"] = _now()
    new = STORE.put_if(_bingo_key(club_id, date), json.dumps(state, ensure_ascii=False).encode(), body["gen"])
    if new is None:
        data, gen = STORE.get_gen(_bingo_key(club_id, date))
        raise HTTPException(409, {"message": "Iemand anders heeft de avond net gewijzigd; opnieuw geladen.",
                                  "gen": gen, "state": json.loads(data) if data else None})
    return {"ok": True, "gen": new, "saved_at": state["saved_at"]}


@app.delete("/clubs/{club_id}/bingo/{date}")
def delete_bingo(club_id: str, date: str, request: Request) -> dict[str, Any]:
    _writable(club_id, request, min_role=ROLE_COMMISSARIS)
    _check_date(date)
    return {"deleted": STORE.delete(_bingo_key(club_id, date))}


# ---------------------------------------------------------------- speeldag-dashboard (sectie H)
# Toestand van een gewone speeldag (verloop): per partij gestart/klaar, per team aanwezig/te laat/staakt/…,
# banen buiten gebruik, logboek en ongedaan maken. Zelfde opslag als bingo: per club/datum met generatie.

def _dayrun_key(club_id: str, date: str) -> str:
    return f"clubs/{club_id}/dayrun/{date}.json"


@app.get("/clubs/{club_id}/dayrun/{date}")
def get_dayrun(club_id: str, date: str, request: Request) -> dict[str, Any]:
    _known_club(club_id)
    _viewable(club_id, request)
    _check_date(date)
    prof = _profile(_club_raw(club_id), club_id)
    data, gen = STORE.get_gen(_dayrun_key(club_id, date))
    fx = _season(prof.knltb_name, _apply_host_away(_season_path(club_id), club_id, prof.knltb_name)).day(date)
    return {"club": club_id, "date": date, "name": prof.name, "gen": gen,
            "state": json.loads(data) if data else None,
            "mode": prof.day_mode(WEEKDAYS_NL[datetime.strptime(date, "%d-%m-%Y").weekday()]),
            "window": _day_window(prof, date, fx), "schedule": _get_json(_sched_key(club_id, date)),
            "profile": profile_summary(prof.for_date(date, fx), club_id), "demo": _is_demo(club_id)}


@app.put("/clubs/{club_id}/dayrun/{date}")
async def put_dayrun(club_id: str, date: str, request: Request) -> dict[str, Any]:
    # Speeldag: baancommissaris (I4). Schrijven altijd achter login bij OAuth.
    _writable(club_id, request, min_role=ROLE_COMMISSARIS)
    _check_date(date)
    body = await _json_body(request, MAX_BINGO_BYTES)
    if not isinstance(body, dict) or not isinstance(body.get("state"), dict) or not isinstance(body.get("gen"), int):
        raise HTTPException(422, 'verwacht {"state": {...}, "gen": <getal>}')
    state = body["state"]
    state["saved_at"] = _now()
    new = STORE.put_if(_dayrun_key(club_id, date), json.dumps(state, ensure_ascii=False).encode(), body["gen"])
    if new is None:
        data, gen = STORE.get_gen(_dayrun_key(club_id, date))
        raise HTTPException(409, {"message": "Het verloop is net op een ander apparaat gewijzigd; opnieuw geladen.",
                                  "gen": gen, "state": json.loads(data) if data else None})
    return {"ok": True, "gen": new, "saved_at": state["saved_at"]}


@app.delete("/clubs/{club_id}/dayrun/{date}")
def delete_dayrun(club_id: str, date: str, request: Request) -> dict[str, Any]:
    _writable(club_id, request, min_role=ROLE_COMMISSARIS)
    _check_date(date)
    return {"deleted": STORE.delete(_dayrun_key(club_id, date))}


def _is_demo(club_id: str) -> bool:
    meta = _meta(club_id)
    return bool(meta and meta.get("demo"))


@app.post("/clubs/{club_id}/demo-reset/{date}")
def demo_reset(club_id: str, date: str, request: Request) -> dict[str, Any]:
    """Alleen democlubs (meta.demo): wis het getikte verloop van die avond/dag (bingo + dashboard), zodat je opnieuw
    kunt oefenen. Schema, verzettingen en opgaven blijven staan. Echte clubs: 403."""
    _writable(club_id, request, min_role=ROLE_COMMISSARIS)
    _check_date(date)
    if not _is_demo(club_id):
        raise HTTPException(403, "reset kan alleen bij een democlub")
    return {"bingo": STORE.delete(_bingo_key(club_id, date)), "dayrun": STORE.delete(_dayrun_key(club_id, date))}


class ReplanRequest(BaseModel):
    now: str = Field(..., description="huidige tijd HH:MM (speeldag)")
    time_limit_s: float = Field(8.0, gt=0, le=20)


def _iso_to_min(iso: str) -> int | None:
    from zoneinfo import ZoneInfo
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Amsterdam"))
    except (ValueError, AttributeError):
        return None
    return d.hour * 60 + d.minute


@app.post("/clubs/{club_id}/replan/{date}")
def replan(club_id: str, date: str, req: ReplanRequest, request: Request) -> dict[str, Any]:
    """SD5 "Herplan rest van de dag": rekent alleen een voorstel uit (slaat niets op). Gespeelde/lopende partijen
    (uit het verloop) staan vast; banen buiten gebruik, gestaakte teams en "later starten" tellen mee.
    Speeldag-actie: baancommissaris mag dit (I4)."""
    _writable(club_id, request, min_role=ROLE_COMMISSARIS)
    from baanschemaatje.planner import replan_day

    _known_club(club_id)
    _check_date(date)
    if not re.match(r"^\d{2}:\d{2}$", req.now):
        raise HTTPException(422, "now moet HH:MM zijn")
    saved = _get_json(_sched_key(club_id, date))
    if not saved:
        raise HTTPException(404, f"geen definitief schema voor {date}")
    state = json.loads(STORE.get_gen(_dayrun_key(club_id, date))[0] or b"{}")
    _, prof, _, season, _ = _resolve(PlanRequest(club=club_id, date=date, moves=[m.model_dump(by_alias=True) for m in _saved_moves(club_id)]))
    rows = [r for r in saved["plan"].get("rows", []) if r.get("kind") != "W"]
    old = {(r["team_id"], r["part"]): (_hm_min(r["start"]), r["court"]) for r in rows if r.get("court") and ":" in str(r.get("start"))}
    pins: dict[tuple[str, str], tuple[int, int]] = {}
    for pid, p in (state.get("parts") or {}).items():
        tk, _, lab = pid.rpartition("|")
        if p.get("status") in ("bezig", "klaar") and (tk, lab) in old:
            m = _iso_to_min(p.get("start") or "")
            pins[(tk, lab)] = (m if m is not None else old[(tk, lab)][0], int(p.get("court") or old[(tk, lab)][1]))
    day_end = _hm_min(_day_window(prof, date, season.day(date))["end"])
    off = [(int(o["court"]), _hm_min(o["from"]), _hm_min(o["to"]) if o.get("to") else day_end)
           for o in (state.get("off") or []) if o.get("court") and o.get("from")]
    drop, later = set(), {}
    for tk, t in (state.get("teams") or {}).items():
        if t.get("status") == "staakt":
            drop |= {k for k in old if k[0] == tk and k not in pins}
        elif t.get("status") == "later" and t.get("time"):
            later[tk] = _hm_min(t["time"])
    day_start = _hm_min(saved["plan"].get("day_start") or "09:00")
    status, new_rows = replan_day(prof, season.fixtures, date, day_start, _hm_min(req.now), pins, old, off=off, drop=drop,
                                  team_earliest=later, time_limit_s=min(req.time_limit_s, MAX_TIME_LIMIT), workers=WORKERS)
    if not new_rows:
        raise HTTPException(409, f"geen haalbaar schema gevonden ({status}); probeer minder banen buiten gebruik of een team later te laten starten")
    unsched = [r for r in new_rows if not r.get("court") and r.get("kind") != "W"]
    return {"status": status, "rows": new_rows, "pinned": len(pins), "dropped": len(drop), "unscheduled": len(unsched)}


def _hm_min(hhmm: str) -> int:
    h, m = str(hhmm)[:5].split(":")
    return int(h) * 60 + int(m)


CANCEL_TYPES = ("eigen", "tegenstander")  # eigen opgave / tegenstander opgave


@app.get("/clubs/{club_id}/cancellations")
def get_cancellations(club_id: str) -> dict[str, Any]:
    _known_club(club_id)
    j = _get_json(f"clubs/{club_id}/cancellations.json")
    return j or {"club": club_id, "cancellations": [], "saved_at": None}


@app.put("/clubs/{club_id}/cancellations")
async def put_cancellations(club_id: str, request: Request) -> dict[str, Any]:
    _writable(club_id, request)
    body = await _json_body(request, MAX_SCHEDULE_BYTES)
    items = body.get("cancellations") if isinstance(body, dict) else None
    if not isinstance(items, list):
        raise HTTPException(422, "verwacht {\"cancellations\": [...]}")
    if len(items) > MAX_MOVES:
        raise HTTPException(413, f"te veel vervallen wedstrijden ({len(items)}, max {MAX_MOVES})")
    prof = _profile(_club_raw(club_id), club_id)
    season = _season(prof.knltb_name, _season_path(club_id))
    played = {_ckey(f.schema, f.home_team, f.away_team, f.date) for f in season.fixtures if f.played}
    old = _cancel_map(_cancellations(club_id))
    out = []
    for c in items:
        if not isinstance(c, dict) or not all(isinstance(c.get(k), str) and c.get(k).strip() for k in ("schema", "home", "away", "date")):
            raise HTTPException(422, "elke vervallen wedstrijd heeft schema, home, away en date")
        _check_date(c["date"])
        k = _ckey(c["schema"], c["home"], c["away"], c["date"])
        if k in played and k not in old:
            raise HTTPException(409, f"'{c['schema']}' {c['home']} – {c['away']} op {c['date']} is al gespeeld; kan niet vervallen")
        out.append({"schema": c["schema"], "home": c["home"], "away": c["away"], "date": c["date"],
                    "type": c.get("type") if c.get("type") in CANCEL_TYPES else "",
                    "reason": str(c.get("reason") or "")[:200], "at": (old.get(k) or {}).get("at") or _now()})
    doc = {"club": club_id, "saved_at": _now(), "cancellations": out}
    STORE.put(f"clubs/{club_id}/cancellations.json", json.dumps(doc, ensure_ascii=False).encode(), "application/json")
    return {"club": club_id, "saved_at": doc["saved_at"], "count": len(out), "dates": _season_view(season, prof, out, club_id=club_id)}


@app.get("/clubs/{club_id}/host-away")
def get_host_away(club_id: str) -> dict[str, Any]:
    _known_club(club_id)
    j = _get_json(f"clubs/{club_id}/host_away.json")
    return j or {"club": club_id, "hosted": [], "saved_at": None}


@app.put("/clubs/{club_id}/host-away")
async def put_host_away(club_id: str, request: Request) -> dict[str, Any]:
    """Markeer uitwedstrijden die toch thuis (op onze banen) gespeeld worden."""
    _writable(club_id, request)
    body = await _json_body(request, MAX_SCHEDULE_BYTES)
    items = body.get("hosted") if isinstance(body, dict) else None
    if not isinstance(items, list):
        raise HTTPException(422, 'verwacht {"hosted": [...]}')
    if len(items) > MAX_MOVES:
        raise HTTPException(413, f"te veel gemarkeerde uitwedstrijden ({len(items)}, max {MAX_MOVES})")
    prof = _profile(_club_raw(club_id), club_id)
    away = _away_fixtures(club_id, prof.knltb_name)
    known = {_ckey(f.schema, f.home_team, f.away_team, f.date): f for f in away}
    played = {k for k, f in known.items() if f.played}
    old = _host_away_map(_host_away_list(club_id))
    out = []
    for c in items:
        if not isinstance(c, dict) or not all(isinstance(c.get(k), str) and c.get(k).strip() for k in ("schema", "home", "away", "date")):
            raise HTTPException(422, "elke gemarkeerde uitwedstrijd heeft schema, home, away en date")
        _check_date(c["date"])
        k = _ckey(c["schema"], c["home"], c["away"], c["date"])
        if k not in known:
            raise HTTPException(404, f"geen uitwedstrijd '{c['schema']}' {c['home']} – {c['away']} op {c['date']}")
        if k in played:
            raise HTTPException(409, f"'{c['schema']}' {c['home']} – {c['away']} op {c['date']} is al gespeeld")
        out.append({"schema": c["schema"], "home": c["home"], "away": c["away"], "date": c["date"],
                    "reason": str(c.get("reason") or "")[:200], "at": (old.get(k) or {}).get("at") or _now()})
    doc = {"club": club_id, "saved_at": _now(), "hosted": out}
    STORE.put(f"clubs/{club_id}/host_away.json", json.dumps(doc, ensure_ascii=False).encode(), "application/json")
    season = _season(prof.knltb_name, _season_path(club_id))
    return {"club": club_id, "saved_at": doc["saved_at"], "count": len(out),
            "dates": _season_view(season, prof, _cancellations(club_id), club_id=club_id)}


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
    moves = req.moves or []
    if isinstance(req.club, str) and (cancels := _cancellations(req.club)):
        spath = _apply_cancellations(spath, cancels)
        cm = _cancel_map(cancels)
        gone = {(k[0], t, k[3]) for k in cm for t in (k[1], k[2])}
        moves = [m for m in moves if (_norm(m.schema_), _norm(m.home), m.from_) not in gone]
    if isinstance(req.club, str):
        spath = _apply_host_away(spath, req.club, prof.knltb_name)
    spath, req._moves_applied = _apply_moves(spath, moves)
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
            "end": min_to_hhmm(dp.day_end), "courts": dp.courts, "bijlage3": dp.bijlage3, "lighting": dp.lighting,
            "mode": prof.day_mode(dp.weekday)}


def _wdict(f, cx: dict, hosted: bool = False) -> dict[str, Any]:
    """Wedstrijdregel voor de seizoensweergave."""
    d: dict[str, Any] = {"label": f.label, "schema": f.schema, "category": f.category.value,
                         "matches": f.matches, "singles": f.singles, "doubles": f.doubles, "mix": f.mix,
                         "home": f.home_team, "away": f.away_team, "dagdeel": f.dagdeel,
                         "export_start": f.export_start, "result": f.result,
                         "status": "vervallen" if cx.get(id(f)) and not f.played else f.status}
    if cx.get(id(f)) and not f.played:
        d["cancel_reason"] = cx[id(f)].get("reason", "")
        d["cancel_type"] = cx[id(f)].get("type", "")
        d["cancelled_at"] = cx[id(f)].get("at")
    if cx.get(id(f)) and f.played:
        d["cancel_conflict"] = True
    if hosted:
        d["hosted_away"] = True
    return d


def _season_view(season: Season, prof: ClubProfile | None = None,
                 cancels: list[dict[str, Any]] | None = None,
                 club_id: str | None = None) -> list[dict[str, Any]]:
    cm = _cancel_map(cancels if cancels is not None else (_cancellations(club_id) if club_id else []))
    home_name = prof.knltb_name if prof else ""
    hosted_items = _host_away_list(club_id) if club_id else []
    hm = _host_away_map(hosted_items)
    away_fx = _away_fixtures(club_id, home_name) if club_id and home_name else []
    away_by: dict[str, list] = {}
    for f in away_fx:
        away_by.setdefault(f.date, []).append(f)
    dates = set(season.by_date()) | set(away_by)
    out = []
    for d in dates:
        fx_home = list(season.by_date().get(d, []))
        # Hosted away: toevoegen aan thuislijst (niet al aanwezig).
        hosted_fx = []
        for f in away_by.get(d, []):
            if _ckey(f.schema, f.home_team, f.away_team, f.date) in hm and not f.played:
                hosted_fx.append(f)
        # Dedup: als dezelfde sleutel al in seizoen staat, niet dubbel.
        have = {_ckey(f.schema, f.home_team, f.away_team, f.date) for f in fx_home}
        extra = [f for f in hosted_fx if _ckey(f.schema, f.home_team, f.away_team, f.date) not in have]
        fx = fx_home + extra
        cx = {id(f): cm.get(_ckey(f.schema, f.home_team, f.away_team, f.date)) for f in fx}
        gone = [f for f in fx if cx[id(f)] and not f.played]
        played = [f for f in fx if f.played]
        live = [f for f in fx if not f.played and not cx[id(f)]]
        hosted_keys = {_ckey(f.schema, f.home_team, f.away_team, f.date) for f in extra}
        uit = []
        for f in away_by.get(d, []):
            k = _ckey(f.schema, f.home_team, f.away_team, f.date)
            uit.append({"label": f.label, "schema": f.schema, "category": f.category.value,
                        "matches": f.matches, "singles": f.singles, "doubles": f.doubles, "mix": f.mix,
                        "home": f.home_team, "away": f.away_team, "dagdeel": f.dagdeel,
                        "export_start": f.export_start, "result": f.result, "status": f.status,
                        "hosted_away": k in hm and not f.played})
        out.append({"date": d, "weekday": WEEKDAYS_NL[datetime.strptime(d, "%d-%m-%Y").weekday()], "fixtures": len(fx),
                    "partijen": sum(f.matches for f in fx),
                    "open_fixtures": len(live),
                    "open_partijen": sum(f.matches for f in live),
                    "played": len(played),
                    "cancelled": len(gone),
                    # Dagdelen/competities/venster: thuis + gemarkeerd-thuis. Ongehoste uit
                    # telt alleen mee op dagen zonder thuiswedstrijden (anders vervuilt bv. een
                    # ochtend-uit de donderdagavond-filter).
                    "dagdelen": sorted({f.dagdeel for f in (fx or away_by.get(d, []))}),
                    "competitions": sorted({" ".join(f.schema.split("–")[0].split())
                                            for f in (fx or away_by.get(d, []))}),
                    "window": _day_window(prof, d, fx or away_by.get(d, [])),
                    "wedstrijden": [_wdict(f, cx, hosted=_ckey(f.schema, f.home_team, f.away_team, f.date) in hosted_keys)
                                   for f in fx],
                    "uitwedstrijden": uit})
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
        "auth_configured": auth_configured(),
    }


@app.get("/clubs")
def clubs(request: Request, mine: bool = Query(False, description="alleen clubs waar de ingelogde user rol heeft (frontpage)")) -> dict[str, Any]:
    """Clublijst. Zonder ``mine``: alle clubs (clubkiezer / diepe links).
    Met ``mine=1``: alleen clubs van de sessie-user (platformbeheerder = alles);
    anoniem → lege lijst. Frontpage gebruikt mine=1 zodat de productpagina
    geen clubdirectory publiek toont.
    """
    user = current_user(request)
    email = user["email"] if user else None
    out = []
    admin_ok = _platform_viewer_ok(request)
    for cid in _all_ids():
        if not admin_ok and _platform_only(cid):
            continue  # democlubs: alleen voor de platformbeheerder (Q4)
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
        s["auth_required"] = bool(meta and meta.get("auth_required"))
        role = resolve_role(email, meta) if email else ROLE_VIEWER
        if email and role != ROLE_VIEWER:
            s["my_role"] = role
            s["my_role_label"] = ROLE_LABELS_NL.get(role, role)
        elif email and is_platform_admin(email):
            s["my_role"] = "platform_admin"
            s["my_role_label"] = ROLE_LABELS_NL.get("platform_admin", "Platformbeheerder")
        else:
            s["my_role"] = None
            s["my_role_label"] = None
        if mine:
            if not email:
                continue
            if is_platform_admin(email):
                out.append(s)
                continue
            if role == ROLE_VIEWER:
                continue
        out.append(s)
    return {"season_file": SEASON_FILE.name, "clubs": out, "auth": auth_status(request), "mine": bool(mine)}


class CreateClub(BaseModel):
    id: str | None = None
    profile: dict[str, Any]


@app.post("/clubs", status_code=201)
def create_club(body: CreateClub, request: Request) -> dict[str, Any]:
    """Alleen platformbeheerder (I1). Anoniem nooit open — ook niet zonder OAuth."""
    admin_email = authorize_platform_admin(request)
    prof = _profile(body.profile, "nieuw")
    cid = body.id or _slug(prof.name)
    if not _ID_RE.match(cid):
        raise HTTPException(422, "club-id: 2-41 tekens, a-z, 0-9 en '-'")
    if cid in _builtin_files() or _meta(cid) is not None:
        raise HTTPException(409, f"club-id '{cid}' bestaat al")
    if len(STORE.list_clubs()) >= MAX_CLUBS:
        raise HTTPException(429, "maximum aantal clubs bereikt")
    now = _now()
    STORE.put(f"clubs/{cid}/profile.json", json.dumps(body.profile, ensure_ascii=False, indent=1).encode(), "application/json")
    # Platformbeheerder = club_admin; deellink meteen; schrijven altijd achter login.
    roles = {admin_email: ROLE_CLUB_ADMIN} if admin_email != "test@localhost" else {}
    meta = {
        "id": cid,
        "name": prof.name,
        "created_at": now,
        "season": None,
        "roles": roles,
        "writers": sorted(roles.keys()),
        "auth_required": True,
        "share_token": new_share_token(),
        "created_by": admin_email,
    }
    _put_meta(cid, meta)
    return {"id": cid}


@app.get("/clubs/{club_id}")
def get_club(club_id: str, request: Request) -> dict[str, Any]:
    raw = _club_raw(club_id)
    prof = _profile(raw, club_id)
    meta = _meta(club_id)
    return {"id": club_id, "profile": raw, "summary": profile_summary(prof, club_id),
            "stored": meta is not None, "builtin": club_id in _builtin_files(),
            "editable": meta is not None, "meta": _public_meta(meta),
            "auth": auth_status(request, club_meta=meta if meta else {"id": club_id})}


@app.put("/clubs/{club_id}/profile")
def put_profile(club_id: str, raw: dict[str, Any], request: Request) -> dict[str, Any]:
    meta = _writable(club_id, request)
    prof = _profile(raw, club_id)
    STORE.put(f"clubs/{club_id}/profile.json", json.dumps(raw, ensure_ascii=False, indent=1).encode(), "application/json")
    meta["name"] = prof.name
    _put_meta(club_id, meta)
    return {"ok": True, "summary": profile_summary(prof, club_id)}


class ClubAccessMember(BaseModel):
    email: str
    role: str = ROLE_CLUB_ADMIN


class ClubAccess(BaseModel):
    """Rollen per club (I4). Geen gedeeld wachtwoord; later evt. e-mail+wachtwoord per user."""
    members: list[ClubAccessMember] | None = None
    # Backward compat: platte writers-lijst → club_admin
    writers: list[str] | None = None
    # Legacy: genegeerd — schrijven is altijd achter login bij OAuth.
    auth_required: bool | None = None


@app.get("/clubs/{club_id}/access")
def get_access(club_id: str, request: Request) -> dict[str, Any]:
    _guard_platform_only(club_id, request)
    meta = _meta(club_id)
    if meta is None:
        raise HTTPException(404 if club_id not in _builtin_files() else 403, "club niet bewerkbaar")
    user = current_user(request)
    email = user["email"] if user else None
    if auth_configured():
        # Ledenlijst (e-mails) alleen voor Google-ingelogde leden met een rol; PIN-sessie telt niet.
        if not email:
            raise HTTPException(401, "Inloggen vereist (Google) om de toegang te zien")
        if resolve_role(email, meta) == ROLE_VIEWER:
            raise HTTPException(403, "Geen rol bij deze club")
    show_share = bool(email) and can_manage_access(email, meta)
    if _platform_only(club_id):
        share = dict(_DEMO_SHARE_OFF)
    elif show_share:
        had = share_token_of(meta)
        tok = _ensure_share_token(meta)
        if not had:
            _put_meta(club_id, meta)
        share = _share_links(club_id, request, tok)
    else:
        share = {"has_token": bool(share_token_of(meta))}
    roles = club_roles(meta)
    members = [{"email": e, "role": r, "label": ROLE_LABELS_NL.get(r, r)} for e, r in sorted(roles.items())]
    return {
        "id": club_id,
        "members": members,
        "roles": roles,
        "writers": sorted(roles.keys()),
        "auth_required": True if auth_configured() else bool(meta.get("auth_required")),
        "share": share,
        "assignable_roles": [
            {"id": r, "label": ROLE_LABELS_NL[r]} for r in ASSIGNABLE_ROLES
        ],
        "auth": auth_status(request, club_meta=meta),
    }


@app.put("/clubs/{club_id}/access")
def put_access(club_id: str, body: ClubAccess, request: Request) -> dict[str, Any]:
    """Alleen platformbeheerder of clubbeheerder mag rollen beheren."""
    _guard_platform_only(club_id, request)
    meta = _meta(club_id)
    if meta is None:
        raise HTTPException(404 if club_id not in _builtin_files() else 403, "club niet bewerkbaar")
    user = current_user(request)
    email = user["email"] if user else None
    if not auth_configured():
        raise HTTPException(503, "Google-login is nog niet geconfigureerd")
    if not email:
        raise HTTPException(401, "Inloggen vereist")
    if not can_manage_access(email, meta):
        raise HTTPException(403, "Geen recht om rollen van deze club te beheren (alleen clubbeheerder)")
    if body.members is not None or body.writers is not None:
        cleaned: dict[str, str] = {}
        if body.members is not None:
            for m in body.members:
                e = (m.email or "").strip().lower()
                r = (m.role or ROLE_CLUB_ADMIN).strip().lower()
                if not e or "@" not in e:
                    continue
                if r not in ASSIGNABLE_ROLES:
                    raise HTTPException(
                        422,
                        f"Onbekende rol '{m.role}'. Kies Clubbeheerder of Baancommissaris.",
                    )
                cleaned[e] = r
        elif body.writers is not None:
            for w in body.writers:
                e = (w or "").strip().lower()
                if e and "@" in e:
                    cleaned[e] = ROLE_CLUB_ADMIN
        if is_platform_admin(email) and email not in cleaned:
            cleaned[email] = ROLE_CLUB_ADMIN
        # Voorkom dat de laatste clubbeheerder zichzelf weghaalt.
        if not any(r == ROLE_CLUB_ADMIN for r in cleaned.values()) and not is_platform_admin(email):
            raise HTTPException(422, "Er moet minstens één clubbeheerder overblijven")
        meta["roles"] = cleaned
        meta["writers"] = sorted(cleaned.keys())
    if body.auth_required is not None:
        meta["auth_required"] = True if auth_configured() else bool(body.auth_required)
        if meta["auth_required"] and not club_roles(meta):
            meta["roles"] = {email: ROLE_CLUB_ADMIN}
            meta["writers"] = [email]
    _ensure_share_token(meta)
    _put_meta(club_id, meta)
    roles = club_roles(meta)
    members = [{"email": e, "role": r, "label": ROLE_LABELS_NL.get(r, r)} for e, r in sorted(roles.items())]
    return {
        "ok": True,
        "members": members,
        "roles": roles,
        "writers": sorted(roles.keys()),
        "auth_required": True if auth_configured() else bool(meta.get("auth_required")),
        "share": dict(_DEMO_SHARE_OFF) if _platform_only(club_id)
        else _share_links(club_id, request, share_token_of(meta)),
    }


@app.post("/clubs/{club_id}/share-token")
def regenerate_share_token(club_id: str, request: Request) -> dict[str, Any]:
    """Nieuwe deellink; oude links meteen ongeldig. Alleen clubbeheerder."""
    _guard_platform_only(club_id, request)
    if _platform_only(club_id):
        raise HTTPException(409, _DEMO_SHARE_OFF["hint"])
    meta = _meta(club_id)
    if meta is None:
        raise HTTPException(404 if club_id not in _builtin_files() else 403, "club niet bewerkbaar")
    user = current_user(request)
    email = user["email"] if user else None
    if not auth_configured():
        raise HTTPException(503, "Google-login is nog niet geconfigureerd")
    if not email:
        raise HTTPException(401, "Inloggen vereist")
    if not can_manage_access(email, meta):
        raise HTTPException(403, "Alleen clubbeheerder mag de deellink vernieuwen")
    meta["share_token"] = new_share_token()
    _put_meta(club_id, meta)
    return {"ok": True, "share": _share_links(club_id, request, meta["share_token"])}


# ---------------------------------------------------------------- commissaris-PIN (Q5, Oscar 29-10-2026)
PIN_WINDOW_S = 600          # 10 minuten
PIN_MAX_PER_IP = 5          # mislukte pogingen per IP per club per venster
PIN_MAX_PER_CLUB = 20       # mislukte pogingen per club (alle IP's) per venster


class PinBody(BaseModel):
    pin: str | None = Field(None, description="6–12 cijfers; leeg = server kiest 6 cijfers")


def _client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()


def _pin_attempts_key(club_id: str) -> str:
    return f"clubs/{club_id}/pin_attempts.json"


def _pin_attempts(club_id: str) -> dict[str, list[float]]:
    now = time.time()
    j = _get_json(_pin_attempts_key(club_id)) or {}
    out: dict[str, list[float]] = {}
    for ip, ts in (j.get("fails") or {}).items():
        keep = [t for t in ts if isinstance(t, (int, float)) and now - t < PIN_WINDOW_S]
        if keep:
            out[ip] = keep
    return out


def _pin_lock_msg(oldest: float) -> str:
    mins = max(1, int((PIN_WINDOW_S - (time.time() - oldest)) // 60) + 1)
    return f"Te veel onjuiste pogingen. Probeer het over {mins} minuten opnieuw of vraag de clubbeheerder."


@app.put("/clubs/{club_id}/commissaris-pin")
def set_commissaris_pin(club_id: str, request: Request, body: PinBody | None = None) -> dict[str, Any]:
    """Clubbeheerder zet/vernieuwt de commissaris-PIN. De PIN wordt éénmalig teruggegeven;
    opgeslagen wordt alleen een salted scrypt-hash. Oude PIN-sessies vervallen."""
    meta = _writable(club_id, request, min_role=ROLE_CLUB_ADMIN)
    if _platform_only(club_id):
        raise HTTPException(409, "Democlub: alleen de platformbeheerder; een commissaris-PIN is hier niet mogelijk.")
    pin = (body.pin if body else None) or ""
    pin = pin.strip()
    if pin and not valid_pin_format(pin):
        raise HTTPException(422, "PIN moet uit 6 tot 12 cijfers bestaan.")
    if not pin:
        pin = generate_pin()
    user = current_user(request)
    meta["commissaris_pin"] = {**hash_pin(pin), "set_at": _now(), "set_by": user["email"] if user else None}
    meta["pin_gen"] = int(meta.get("pin_gen") or 0) + 1
    _put_meta(club_id, meta)
    STORE.delete(_pin_attempts_key(club_id))
    return {"ok": True, "pin": pin, "set_at": meta["commissaris_pin"]["set_at"],
            "hint": "Noteer deze PIN nu: hij wordt niet opnieuw getoond. Een nieuwe PIN maakt oude PIN-sessies ongeldig."}


@app.delete("/clubs/{club_id}/commissaris-pin")
def delete_commissaris_pin(club_id: str, request: Request) -> dict[str, Any]:
    meta = _writable(club_id, request, min_role=ROLE_CLUB_ADMIN)
    had = meta.pop("commissaris_pin", None) is not None
    meta["pin_gen"] = int(meta.get("pin_gen") or 0) + 1
    _put_meta(club_id, meta)
    return {"ok": True, "deleted": had}


@app.get("/clubs/{club_id}/commissaris-pin")
def get_commissaris_pin(club_id: str, request: Request) -> dict[str, Any]:
    """Alleen of er een PIN is en wanneer gezet (nooit de PIN of hash)."""
    meta = _writable(club_id, request, min_role=ROLE_CLUB_ADMIN)
    rec = pin_record(meta)
    return {"enabled": rec is not None, "set_at": (rec or {}).get("set_at"), "set_by": (rec or {}).get("set_by")}


@app.post("/clubs/{club_id}/pin-login")
def pin_login(club_id: str, body: PinBody, request: Request, response: Response) -> dict[str, Any]:
    """Commissaris logt in met de club-PIN → 12 uur commissarisrechten voor deze club (HTTP-only cookie)."""
    _known_club(club_id)  # democlubs: alleen platformbeheerder (PIN opent ze niet)
    if not auth_configured():
        raise HTTPException(503, "Inloggen is nog niet geconfigureerd")
    meta = _meta(club_id)
    if _platform_only(club_id) or pin_record(meta) is None:
        raise HTTPException(400, "Deze club heeft geen commissaris-PIN. Vraag de clubbeheerder of log in met Google.")
    ip = _client_ip(request)
    fails = _pin_attempts(club_id)
    mine = fails.get(ip, [])
    total = [t for ts in fails.values() for t in ts]
    if len(mine) >= PIN_MAX_PER_IP:
        raise HTTPException(429, _pin_lock_msg(min(mine)))
    if len(total) >= PIN_MAX_PER_CLUB:
        raise HTTPException(429, _pin_lock_msg(min(total)))
    pin = (body.pin or "").strip()
    if not valid_pin_format(pin) or not verify_pin(pin, pin_record(meta)):
        mine = mine + [time.time()]
        fails[ip] = mine
        STORE.put(_pin_attempts_key(club_id), json.dumps({"fails": fails}).encode(), "application/json")
        left = PIN_MAX_PER_IP - len(mine)
        if left <= 0:
            raise HTTPException(429, _pin_lock_msg(min(mine)))
        raise HTTPException(401, f"Onjuiste PIN. Nog {left} {'poging' if left == 1 else 'pogingen'}.")
    if ip in fails:
        fails.pop(ip, None)
        STORE.put(_pin_attempts_key(club_id), json.dumps({"fails": fails}).encode(), "application/json")
    exp = set_pin_cookie(response, request, club_id, int(meta.get("pin_gen") or 0))
    return {"ok": True, "club": club_id, "role": ROLE_COMMISSARIS, "exp": exp}


@app.post("/auth/pin-logout")
def pin_logout(response: Response) -> dict[str, Any]:
    clear_pin_cookie(response)
    return {"ok": True}


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
        rows, away_rows, rep = parse_export(data, filename, prof.knltb_name, wd)
    except ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc
    if not rows:
        raise HTTPException(422, {"message": f"geen thuiswedstrijden van '{prof.knltb_name}' gevonden op {', '.join(sorted(wd))}",
                                  "report": rep})
    tsv = to_tsv(rows).encode()
    STORE.put(f"clubs/{club_id}/upload/latest", data, "application/octet-stream")
    STORE.put(f"clubs/{club_id}/season.tsv", tsv, "text/tab-separated-values")
    STORE.put(f"clubs/{club_id}/away.tsv", to_tsv(away_rows).encode(), "text/tab-separated-values")
    rep["days"] = [d for d in WEEKDAYS_NL if d in wd]
    meta["season"] = {"filename": filename[:120], "uploaded_at": uploaded_at, "processed_at": _now(), "report": rep}
    _put_meta(club_id, meta)
    season = _season(prof.knltb_name, _season_path(club_id))
    return {"ok": True, "report": rep, "dates": _season_view(season, prof, _cancellations(club_id),
                                                             club_id=club_id)}


@app.get("/clubs/{club_id}/season")
def get_season(club_id: str) -> dict[str, Any]:
    prof = _profile(_club_raw(club_id), club_id)
    spath = _season_path(club_id)
    meta = _meta(club_id)
    return {"club": club_id, "own_season": spath != SEASON_FILE,
            "season": (meta or {}).get("season") if spath != SEASON_FILE else {"filename": SEASON_FILE.name},
            "dates": _season_view(_season(prof.knltb_name, spath), prof, _cancellations(club_id), club_id=club_id)}


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
def plan(req: PlanRequest, request: Request) -> dict[str, Any]:
    from baanschemaatje.planner import plan_day

    club_id, prof, raw, season, spath = _resolve(req)
    # Berekenen is clubbeheer; commissaris niet (I4). Inline/builtin zonder meta blijft open.
    if isinstance(getattr(req, "club", None), str) and req.club:
        meta = _meta(req.club)
        if meta is not None:
            authorize_write(req.club, request, meta=meta, min_role=ROLE_CLUB_ADMIN)
    day_fx = season.day(req.date)
    wd = WEEKDAYS_NL[datetime.strptime(req.date, "%d-%m-%Y").weekday()]
    if prof.day_mode(wd) == "bingo":
        return {"status": "BINGO", "date": req.date, "rows": [], "day_start": None, "courts": prof.courts,
                "stats": {"scheduled": 0, "unscheduled": 0, "solve_time_s": 0}, "attempts": [],
                "summary": {"solved": False, "date": req.date, "status": "BINGO", "fixtures": len(day_fx),
                            "played": sum(1 for f in day_fx if f.played), "scheduled": 0, "unscheduled": 0},
                "message": "Bingo-avond (live indelen): er wordt geen baanschema berekend.",
                "profile": profile_summary(prof.for_date(req.date, day_fx), club_id),
                "moves_applied": req._moves_applied, "played": _played_view(day_fx), "cached": False}
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
def scenarios(req: PlanRequest, request: Request, combos: bool = Query(False, description="ook combinaties proberen (duurt langer)")) -> dict[str, Any]:
    from baanschemaatje.planner import plan_day
    from baanschemaatje.scenarios import candidate_scenarios, propose_solutions

    club_id, prof, raw, season, spath = _resolve(req)
    if isinstance(getattr(req, "club", None), str) and req.club:
        meta = _meta(req.club)
        if meta is not None:
            authorize_write(req.club, request, meta=meta, min_role=ROLE_CLUB_ADMIN)
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



# ---------------------------------------------------------------- auth (Google OAuth, I3)

from fastapi.responses import FileResponse, RedirectResponse  # noqa: E402


@app.get("/auth/status")
def get_auth_status(request: Request, club: str | None = None) -> dict[str, Any]:
    meta = _meta(club) if club and _ID_RE.match(club) else None
    if club and meta is not None and _platform_only(club) and not _platform_viewer_ok(request):
        meta = None  # democlub: geen rollen/e-mails lekken
    return auth_status(request, club_meta=meta)


@app.get("/auth/login")
def auth_login(request: Request, next: str = "/", club: str = "") -> RedirectResponse:
    """Start Google OAuth. ``next`` = pad of volledige URL op dezelfde host."""
    next_url = next or "/"
    # Alleen relatieve paden of zelfde-origin URLs (open redirect voorkomen).
    if next_url.startswith("http"):
        base = public_base_from_request(request)
        if not next_url.startswith(base):
            next_url = "/"
    elif not next_url.startswith("/"):
        next_url = "/"
    url, state_token = start_oauth_url(request, next_url=next_url, club_id=club or "")
    resp = RedirectResponse(url, status_code=302)
    set_oauth_state_cookie(resp, request, state_token)
    return resp


def public_base_from_request(request: Request) -> str:
    return public_base_url(request)


@app.get("/auth/callback")
def auth_callback(request: Request, response: Response, code: str | None = None,
                  state: str | None = None, error: str | None = None) -> RedirectResponse:
    if error:
        raise HTTPException(401, f"Google-login geannuleerd: {error}")
    if not code or not state:
        raise HTTPException(400, "OAuth-callback mist code of state")
    ctx = consume_oauth_state(request, state)
    user = exchange_code_for_user(request, code)
    next_url = ctx.get("next") or "/"
    resp = RedirectResponse(next_url, status_code=302)
    set_session_cookie(resp, request, user["email"], user.get("name") or "")
    resp.delete_cookie("bs_oauth", path="/")
    return resp


@app.post("/auth/logout")
def auth_logout(response: Response) -> dict[str, Any]:
    clear_session_cookie(response)
    return {"ok": True}


@app.get("/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    return auth_status(request)


# ---------------------------------------------------------------- vaste clublink (F2)
# De statische web-app (web/baanschemaatje) wordt door dezelfde Cloud Run-service geserveerd onder /app,
# met korte vaste links zonder githack-tussenpagina: /club/<id>, /dag/<id>/<datum>, /bingo/<id>/<datum>,
# /tv/<id>/<datum>. Zelfde origin als de API, dus de standaard-API-URL in common.js klopt. Geen extra kosten
# (zelfde service, min-instances 0). Alleen lezen van bestanden; geen nieuwe schrijfroutes.
from fastapi.staticfiles import StaticFiles  # noqa: E402

WEB_DIR = Path(os.environ.get("BS_WEB", ROOT / "web" / "baanschemaatje"))


def _go(page: str, *parts: str, share: str | None = None) -> RedirectResponse:
    frag = "/".join(parts)
    q = f"?s={share}" if share else ""
    return RedirectResponse(f"/app/{page}{q}{'#' + frag if frag else ''}", status_code=307)


def _link_id(club_id: str) -> str:
    if not _ID_RE.match(club_id):
        raise HTTPException(404, "onbekende club")
    return club_id


@app.get("/", include_in_schema=False)
def web_root():
    """Product-frontpage (alsof baanschemaatje.nl). Clublijst pas na Google-login."""
    home = WEB_DIR / "home.html"
    if home.is_file():
        return FileResponse(home, media_type="text/html; charset=utf-8")
    return _go("club.html")


@app.get("/club/{club_id}", include_in_schema=False)
def web_club(club_id: str) -> RedirectResponse:
    return _go("club.html", _link_id(club_id))


@app.get("/dashboard/{club_id}", include_in_schema=False)
def web_dashboard_today(club_id: str) -> RedirectResponse:
    return _go("dashboard.html", _link_id(club_id), _today_ams().strftime("%d-%m-%Y"))


@app.get("/{page}/{club_id}/{date}", include_in_schema=False)
def web_day(page: str, club_id: str, date: str, request: Request) -> RedirectResponse:
    pages = {"dashboard": "dashboard.html", "dag": "dag.html", "bingo": "bingo.html", "tv": "tv.html", "bingolijst": "bingo-print.html"}
    if page not in pages:
        raise HTTPException(404, "niet gevonden")
    return _go(pages[page], _link_id(club_id), _check_date(date), share=_share_from_request(request))


if WEB_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")
