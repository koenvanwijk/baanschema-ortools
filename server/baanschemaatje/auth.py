"""Schrijfrechten per club + Google OAuth + deellinks (I1/I3/I5).

Besluit Oscar 26-10-2026 (bijgewerkt zelfde dag):
- Alleen platformbeheerder (PLATFORM_ADMIN_EMAILS) mag clubs aanmaken.
- Schrijven: altijd Google-login + rol zodra OAuth geconfigureerd is.
  Geen open-schrijven-loophole meer via ``auth_required=false``.
- Kijken (tv/dag/bingolijst + GET-API's): geheime deellink ``?s=TOKEN``
  of ingelogde rol — niet meer publiek op alleen club-id.
- Geen gedeeld clubwachtwoord. Rollen: club_admin / commissaris / platform_admin.
  Later optioneel e-mail+wachtwoord per user — alleen een haak; niet gebouwd.

Env (Cloud Run / lokaal):
  PLATFORM_ADMIN_EMAILS   komma-lijst, bv. oscarreynhout@gmail.com
  GOOGLE_OAUTH_CLIENT_ID
  GOOGLE_OAUTH_CLIENT_SECRET
  BS_SESSION_SECRET       willekeurige string (≥16 tekens) voor cookie-HMAC
  BS_PUBLIC_BASE_URL      https://…run.app (redirect URI-basis); leeg = request.base_url
  BS_AUTH_ENFORCE         legacy (schrijven is sowieso dicht bij OAuth)
  BS_ALLOW_OPEN_CREATE    1 = alleen voor tests: POST /clubs zonder login

Cookies (HTTP-only, Secure in productie, SameSite=Lax):
  bs_session   e-mail + verloop, HMAC-gesigneerd
  bs_oauth     kortstondige OAuth-state (CSRF)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from fastapi import HTTPException, Request, Response

COOKIE_SESSION = "bs_session"
COOKIE_OAUTH = "bs_oauth"
COOKIE_PIN = "bs_pin"          # commissaris-PIN-sessie (Q5), per club
PIN_SESSION_TTL_S = 60 * 60 * 12  # 12 uur
PIN_MIN_LEN = 6
PIN_MAX_LEN = 12
SESSION_TTL_S = 60 * 60 * 24 * 14  # 14 dagen
OAUTH_STATE_TTL_S = 600
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def platform_admin_emails() -> set[str]:
    raw = _env("PLATFORM_ADMIN_EMAILS", "oscarreynhout@gmail.com")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def oauth_client_id() -> str:
    return _env("GOOGLE_OAUTH_CLIENT_ID")


def oauth_client_secret() -> str:
    return _env("GOOGLE_OAUTH_CLIENT_SECRET")


def session_secret() -> bytes:
    s = _env("BS_SESSION_SECRET")
    if not s:
        return b""
    return s.encode("utf-8")


def auth_configured() -> bool:
    """Google OAuth + sessie-geheim aanwezig → login kan aan."""
    return bool(oauth_client_id() and oauth_client_secret() and session_secret())


def auth_enforce_global() -> bool:
    return _env("BS_AUTH_ENFORCE") in ("1", "true", "yes")


def allow_open_create() -> bool:
    """Alleen tests: BS_ALLOW_OPEN_CREATE=1."""
    return _env("BS_ALLOW_OPEN_CREATE") in ("1", "true", "yes")


def is_platform_admin(email: str | None) -> bool:
    return bool(email) and email.strip().lower() in platform_admin_emails()


def public_base_url(request: Request) -> str:
    configured = _env("BS_PUBLIC_BASE_URL").rstrip("/")
    if configured:
        return configured
    # Achter Cloud Run proxies: X-Forwarded-* of request.base_url
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def redirect_uri(request: Request) -> str:
    return f"{public_base_url(request)}/auth/callback"


# ---------------------------------------------------------------- cookies / sessie


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload: bytes) -> str:
    secret = session_secret()
    if not secret:
        raise RuntimeError("BS_SESSION_SECRET ontbreekt")
    sig = hmac.new(secret, payload, hashlib.sha256).digest()
    return f"{_b64url(payload)}.{_b64url(sig)}"


def _verify(token: str) -> dict[str, Any] | None:
    if not token or "." not in token or not session_secret():
        return None
    try:
        body_b64, sig_b64 = token.rsplit(".", 1)
        payload = _b64url_decode(body_b64)
        expect = hmac.new(session_secret(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expect, _b64url_decode(sig_b64)):
            return None
        data = json.loads(payload.decode("utf-8"))
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        email = (data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return None
        return {"email": email, "name": data.get("name") or ""}
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def _cookie_secure(request: Request) -> bool:
    return public_base_url(request).startswith("https://")


def set_session_cookie(response: Response, request: Request, email: str, name: str = "") -> None:
    now = int(time.time())
    payload = json.dumps(
        {"email": email.strip().lower(), "name": name or "", "iat": now, "exp": now + SESSION_TTL_S},
        separators=(",", ":"),
    ).encode("utf-8")
    response.set_cookie(
        COOKIE_SESSION,
        _sign(payload),
        max_age=SESSION_TTL_S,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_SESSION, path="/")
    response.delete_cookie(COOKIE_OAUTH, path="/")
    response.delete_cookie(COOKIE_PIN, path="/")


# ---------------------------------------------------------------- commissaris-PIN (Q5)
# Besluit Oscar 29-10-2026: clubbeheerder zet per club een commissaris-PIN (min. 6 cijfers).
# Opslag alleen als salted scrypt-hash in meta; PIN zelf nooit opgeslagen/gelogd.
# PIN-sessie = alleen commissarisrechten voor die ene club, 12 uur; nieuwe PIN → oude sessies ongeldig.

_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


def valid_pin_format(pin: str | None) -> bool:
    return bool(pin) and pin.isdigit() and pin.isascii() and PIN_MIN_LEN <= len(pin) <= PIN_MAX_LEN


def generate_pin() -> str:
    return f"{secrets.randbelow(10 ** PIN_MIN_LEN):0{PIN_MIN_LEN}d}"


def hash_pin(pin: str) -> dict[str, Any]:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pin.encode("utf-8"), salt=salt, n=_SCRYPT["n"], r=_SCRYPT["r"], p=_SCRYPT["p"],
                       dklen=_SCRYPT["dklen"])
    return {"alg": "scrypt", **{k: _SCRYPT[k] for k in ("n", "r", "p")},
            "salt": _b64url(salt), "hash": _b64url(h)}


def verify_pin(pin: str, rec: dict[str, Any] | None) -> bool:
    if not rec or rec.get("alg") != "scrypt" or not pin:
        return False
    try:
        salt = _b64url_decode(rec["salt"])
        expect = _b64url_decode(rec["hash"])
        h = hashlib.scrypt(pin.encode("utf-8"), salt=salt, n=int(rec["n"]), r=int(rec["r"]),
                           p=int(rec["p"]), dklen=len(expect))
    except (KeyError, ValueError, TypeError):
        return False
    return hmac.compare_digest(h, expect)


def pin_record(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    rec = (meta or {}).get("commissaris_pin")
    return rec if isinstance(rec, dict) and rec.get("hash") else None


def set_pin_cookie(response: Response, request: Request, club_id: str, gen: int) -> int:
    now = int(time.time())
    exp = now + PIN_SESSION_TTL_S
    payload = json.dumps({"kind": "pin", "club": club_id, "gen": int(gen), "iat": now, "exp": exp},
                         separators=(",", ":")).encode("utf-8")
    response.set_cookie(COOKIE_PIN, _sign(payload), max_age=PIN_SESSION_TTL_S, httponly=True,
                        secure=_cookie_secure(request), samesite="lax", path="/")
    return exp


def clear_pin_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_PIN, path="/")


def _verify_pin_cookie(token: str) -> dict[str, Any] | None:
    if not token or "." not in token or not session_secret():
        return None
    try:
        body_b64, sig_b64 = token.rsplit(".", 1)
        payload = _b64url_decode(body_b64)
        expect = hmac.new(session_secret(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expect, _b64url_decode(sig_b64)):
            return None
        data = json.loads(payload.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, TypeError):
        return None
    if data.get("kind") != "pin" or int(data.get("exp", 0)) < int(time.time()):
        return None
    return data


def pin_session(request: Request | None, club_id: str | None, meta: dict[str, Any] | None) -> dict[str, Any] | None:
    """Geldige PIN-sessie voor precies deze club (PIN nog gezet, zelfde generatie)?"""
    if request is None or not club_id or not auth_configured() or pin_record(meta) is None:
        return None
    data = _verify_pin_cookie(request.cookies.get(COOKIE_PIN) or "")
    if not data or data.get("club") != club_id:
        return None
    if int(data.get("gen", -1)) != int((meta or {}).get("pin_gen") or 0):
        return None
    return data


def current_user(request: Request | None) -> dict[str, Any] | None:
    if request is None:
        return None
    return _verify(request.cookies.get(COOKIE_SESSION) or "")


# ---------------------------------------------------------------- OAuth


def start_oauth_url(request: Request, *, next_url: str = "/", club_id: str = "") -> tuple[str, str]:
    """Geeft (Google-authorize-URL, state-cookie-waarde)."""
    if not auth_configured():
        raise HTTPException(503, "Google-login is nog niet geconfigureerd (OAuth client ontbreekt)")
    state = secrets.token_urlsafe(24)
    # state payload in cookie; Google krijgt alleen de random state
    cookie_payload = json.dumps(
        {"s": state, "next": next_url or "/", "club": club_id or "", "exp": int(time.time()) + OAUTH_STATE_TTL_S},
        separators=(",", ":"),
    ).encode("utf-8")
    state_token = _sign(cookie_payload)
    params = {
        "client_id": oauth_client_id(),
        "redirect_uri": redirect_uri(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}", state_token


def set_oauth_state_cookie(response: Response, request: Request, state_token: str) -> None:
    response.set_cookie(
        COOKIE_OAUTH,
        state_token,
        max_age=OAUTH_STATE_TTL_S,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path="/",
    )


def consume_oauth_state(request: Request, state: str) -> dict[str, Any]:
    raw = request.cookies.get(COOKIE_OAUTH) or ""
    # State-cookie is zelf gesigneerd JSON met veld s/next/club/exp (niet de sessie-vorm).
    try:
        if not raw or "." not in raw or not session_secret():
            raise ValueError("geen state")
        body_b64, sig_b64 = raw.rsplit(".", 1)
        payload = _b64url_decode(body_b64)
        expect = hmac.new(session_secret(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expect, _b64url_decode(sig_b64)):
            raise ValueError("handtekening")
        data = json.loads(payload.decode("utf-8"))
        if int(data.get("exp", 0)) < int(time.time()):
            raise ValueError("verlopen")
        if not secrets.compare_digest(str(data.get("s") or ""), str(state or "")):
            raise ValueError("state mismatch")
        return {"next": data.get("next") or "/", "club": data.get("club") or ""}
    except (ValueError, json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(400, "Ongeldige of verlopen login-poging; probeer opnieuw") from exc


def exchange_code_for_user(request: Request, code: str) -> dict[str, str]:
    """Code → {email, name}."""
    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": oauth_client_id(),
            "client_secret": oauth_client_secret(),
            "redirect_uri": redirect_uri(request),
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            tok = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise HTTPException(401, f"Google-token mislukt: {detail}") from exc
    except OSError as exc:
        raise HTTPException(502, f"Google niet bereikbaar: {exc}") from exc
    access = tok.get("access_token")
    if not access:
        raise HTTPException(401, "Google gaf geen access_token")
    ureq = urllib.request.Request(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access}"},
    )
    try:
        with urllib.request.urlopen(ureq, timeout=15) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError) as exc:
        raise HTTPException(502, f"Google userinfo mislukt: {exc}") from exc
    email = (info.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(401, "Google-account heeft geen e-mailadres")
    if info.get("email_verified") is False:
        raise HTTPException(401, "Google-e-mail is niet geverifieerd")
    return {"email": email, "name": (info.get("name") or info.get("given_name") or "").strip()}


# ---------------------------------------------------------------- autorisatie

ROLE_VIEWER = "viewer"
ROLE_COMMISSARIS = "commissaris"
ROLE_CLUB_ADMIN = "club_admin"
ROLE_PLATFORM_ADMIN = "platform_admin"

ROLE_RANK = {
    ROLE_VIEWER: 0,
    ROLE_COMMISSARIS: 1,
    ROLE_CLUB_ADMIN: 2,
    ROLE_PLATFORM_ADMIN: 3,
}

ROLE_LABELS_NL = {
    ROLE_VIEWER: "Alleen kijken",
    ROLE_COMMISSARIS: "Baancommissaris",
    ROLE_CLUB_ADMIN: "Clubbeheerder",
    ROLE_PLATFORM_ADMIN: "Platformbeheerder",
}

# Welke minimum-rol voor welke actiegroep (API).
# commissaris: speeldag tikken (bingo/dashboard/demo-reset/herplan-voorstel)
# club_admin: instellingen, import, toegang, verzetten, host-away, schema opslaan, berekenen
ASSIGNABLE_ROLES = (ROLE_CLUB_ADMIN, ROLE_COMMISSARIS)


def _legacy_writer_emails(meta: dict[str, Any] | None) -> set[str]:
    if not meta:
        return set()
    raw = meta.get("writers") or meta.get("writer_emails") or []
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.split(",")]
    return {str(e).strip().lower() for e in raw if str(e).strip() and "@" in str(e)}


def club_roles(meta: dict[str, Any] | None) -> dict[str, str]:
    """E-mail → rol (club_admin | commissaris). Legacy ``writers`` = club_admin."""
    out: dict[str, str] = {}
    if not meta:
        return out
    raw = meta.get("roles") or {}
    if isinstance(raw, dict):
        for email, role in raw.items():
            e = str(email).strip().lower()
            r = str(role).strip().lower()
            if e and "@" in e and r in ASSIGNABLE_ROLES:
                out[e] = r
    for e in _legacy_writer_emails(meta):
        out.setdefault(e, ROLE_CLUB_ADMIN)
    return out


def club_writers(meta: dict[str, Any] | None) -> set[str]:
    """Alle e-mails met een schrijfrol (club_admin of commissaris)."""
    return set(club_roles(meta).keys())


def club_auth_required(meta: dict[str, Any] | None) -> bool:
    """Legacy: schrijven is altijd dicht bij OAuth. True zodra OAuth aan staat."""
    if auth_configured() or auth_enforce_global():
        return True
    if not meta:
        return False
    return bool(meta.get("auth_required"))


def resolve_role(email: str | None, meta: dict[str, Any] | None) -> str:
    """Effectieve rol van deze gebruiker voor de club (platform_admin wint)."""
    if is_platform_admin(email):
        return ROLE_PLATFORM_ADMIN
    if not email:
        return ROLE_VIEWER
    return club_roles(meta).get(email.strip().lower(), ROLE_VIEWER)


def role_at_least(role: str, minimum: str) -> bool:
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(minimum, 0)


def can_write_club(email: str | None, club_id: str, meta: dict[str, Any] | None) -> bool:
    """Mag überhaupt iets schrijven (minstens commissaris), als auth aan staat."""
    return role_at_least(resolve_role(email, meta), ROLE_COMMISSARIS)


def can_manage_access(email: str | None, meta: dict[str, Any] | None) -> bool:
    return role_at_least(resolve_role(email, meta), ROLE_CLUB_ADMIN)


def new_share_token() -> str:
    """Onvoorspelbare deellink-token (url-safe)."""
    return secrets.token_urlsafe(24)


def share_token_of(meta: dict[str, Any] | None) -> str | None:
    if not meta:
        return None
    tok = (meta.get("share_token") or "").strip()
    return tok or None


def share_token_ok(meta: dict[str, Any] | None, candidate: str | None) -> bool:
    """Constant-time vergelijking van deellink-token."""
    expect = share_token_of(meta)
    if not expect or not candidate:
        return False
    return secrets.compare_digest(expect, candidate.strip())


def authorize_platform_admin(request: Request | None) -> str:
    """Voor POST /clubs. Geeft e-mail van de beheerder terug."""
    if allow_open_create():
        return "test@localhost"
    if not auth_configured():
        raise HTTPException(
            401,
            "Inloggen vereist. Google-login is nog niet geconfigureerd; "
            "nieuwe clubs aanmaken kan pas na OAuth-setup door de platformbeheerder.",
        )
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Inloggen vereist (Google) om een club aan te maken")
    if not is_platform_admin(user["email"]):
        raise HTTPException(403, "Alleen de platformbeheerder mag nieuwe clubs aanmaken")
    return user["email"]


def _role_forbidden_message(email: str, club_id: str, role: str, min_role: str) -> str:
    need = ROLE_LABELS_NL.get(min_role, min_role)
    have = ROLE_LABELS_NL.get(role, role)
    if role == ROLE_VIEWER:
        return (
            f"Geen schrijfrecht voor club '{club_id}' met {email}. "
            f"Vraag de clubbeheerder om je als {need.lower()} toe te voegen."
        )
    return (
        f"Rol '{have}' is onvoldoende voor club '{club_id}' (minimaal {need} nodig). "
        f"Ingelogd als {email}."
    )


def authorize_write(
    club_id: str,
    request: Request | None = None,
    *,
    meta: dict[str, Any] | None = None,
    min_role: str = ROLE_COMMISSARIS,
) -> None:
    """Gooi 401/403 als de aanvrager deze actie niet mag.

    Zonder geconfigureerde Google OAuth: open (alleen lokale tests zonder OAuth).
    Met OAuth: altijd sessie + rol ≥ min_role (geen open-schrijven meer).
    """
    if min_role not in ROLE_RANK:
        min_role = ROLE_COMMISSARIS
    if not auth_configured():
        return None
    user = current_user(request)
    pin_ok = role_at_least(ROLE_COMMISSARIS, min_role) and pin_session(request, club_id, meta) is not None
    if not user:
        if pin_ok:
            return None  # commissaris-PIN: alleen speeldag-acties (Q5)
        raise HTTPException(401, "Inloggen vereist (Google) om te wijzigen")
    role = resolve_role(user["email"], meta)
    if not role_at_least(role, min_role):
        if pin_ok:
            return None
        raise HTTPException(403, _role_forbidden_message(user["email"], club_id, role, min_role))
    return None


def authorize_view(
    club_id: str,
    request: Request | None = None,
    *,
    meta: dict[str, Any] | None = None,
    share_token: str | None = None,
) -> None:
    """Gooi 401/403 als kijken niet mag (tv/dag/bingo GET).

    Zonder OAuth: open (tests). Met OAuth: deellink-token óf ingelogde rol
    (commissaris/club_admin/platform). Alleen club-id weten is niet genoeg.
    """
    if not auth_configured():
        return None
    if share_token_ok(meta, share_token):
        return None
    if pin_session(request, club_id, meta) is not None:
        return None
    user = current_user(request)
    if user and role_at_least(resolve_role(user["email"], meta), ROLE_COMMISSARIS):
        return None
    if user:
        raise HTTPException(
            403,
            f"Geen kijkrecht voor club '{club_id}'. Gebruik de deellink of vraag om een rol.",
        )
    raise HTTPException(
        401,
        "Deellink of inloggen vereist om dit schema te zien",
    )


def auth_status(request: Request | None, *, club_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    user = current_user(request)
    email = user["email"] if user else None
    role = resolve_role(email, club_meta) if club_meta is not None else (
        ROLE_PLATFORM_ADMIN if is_platform_admin(email) else (ROLE_VIEWER if email else None)
    )
    pin = pin_session(request, (club_meta or {}).get("id"), club_meta) if club_meta is not None else None
    if pin and not role_at_least(role or ROLE_VIEWER, ROLE_COMMISSARIS):
        role = ROLE_COMMISSARIS
    open_writes = not auth_configured()
    has_share = bool(share_token_of(club_meta)) if club_meta is not None else None
    return {
        "configured": auth_configured(),
        "enforce": True if auth_configured() else auth_enforce_global(),
        "user": user,
        "is_platform_admin": is_platform_admin(email),
        "role": role,
        "role_label": ROLE_LABELS_NL.get(role or "", None),
        "can_create_club": bool(
            allow_open_create()
            or (auth_configured() and is_platform_admin(email))
        ),
        "create_blocked_reason": (
            None
            if allow_open_create() or (auth_configured() and is_platform_admin(email))
            else (
                "Inloggen vereist"
                if not auth_configured() or not email
                else "Alleen de platformbeheerder mag clubs aanmaken"
            )
        ),
        "club_auth_required": True if (club_meta is not None and auth_configured()) else (
            club_auth_required(club_meta) if club_meta is not None else None
        ),
        "has_share_token": has_share,
        "can_write_club": (
            open_writes or role_at_least(role or ROLE_VIEWER, ROLE_COMMISSARIS)
        )
        if club_meta is not None
        else None,
        "can_admin_club": (
            open_writes or role_at_least(role or ROLE_VIEWER, ROLE_CLUB_ADMIN)
        )
        if club_meta is not None
        else None,
        "can_manage_access": (
            bool(email) and can_manage_access(email, club_meta)
        )
        if club_meta is not None
        else None,
        # Rollen/e-mails alleen voor wie toegang beheert (geen lek naar anoniem/PIN/deellink).
        "roles": club_roles(club_meta) if (club_meta is not None and email and can_manage_access(email, club_meta)) else None,
        "role_labels": dict(ROLE_LABELS_NL),
        "password_login": False,
        "pin_enabled": (pin_record(club_meta) is not None) if club_meta is not None else None,
        "pin_session": bool(pin),
        "pin_session_exp": int(pin["exp"]) if pin else None,
    }
