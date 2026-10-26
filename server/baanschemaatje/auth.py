"""Schrijfrechten per club + Google OAuth (I1/I3/I5).

Besluit Oscar 26-10-2026:
- Alleen platformbeheerder (PLATFORM_ADMIN_EMAILS) mag clubs aanmaken.
- Schrijven: Google-login + e-mail in club.writers (of platformbeheerder),
  pas als auth geconfigureerd is én de club ``auth_required`` heeft
  (of globale BS_AUTH_ENFORCE=1). Tot die tijd blijft schrijven open
  (interim), behalve club-aanmaken: dat is nooit anoniem open.
- Geen gedeeld clubwachtwoord. Later optioneel e-mail+wachtwoord per user
  (I4) — hier alleen een haak; niet gebouwd.
- TV / dag / bingolijst (GET) blijven publiek (I5).

Env (Cloud Run / lokaal):
  PLATFORM_ADMIN_EMAILS   komma-lijst, bv. oscarreynhout@gmail.com
  GOOGLE_OAUTH_CLIENT_ID
  GOOGLE_OAUTH_CLIENT_SECRET
  BS_SESSION_SECRET       willekeurige string (≥16 tekens) voor cookie-HMAC
  BS_PUBLIC_BASE_URL      https://…run.app (redirect URI-basis); leeg = request.base_url
  BS_AUTH_ENFORCE         1 = alle clubs schrijven achter login (ook zonder meta.auth_required)
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


def club_writers(meta: dict[str, Any] | None) -> set[str]:
    if not meta:
        return set()
    raw = meta.get("writers") or meta.get("writer_emails") or []
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.split(",")]
    return {str(e).strip().lower() for e in raw if str(e).strip()}


def club_auth_required(meta: dict[str, Any] | None) -> bool:
    if auth_enforce_global():
        return True
    if not meta:
        return False
    return bool(meta.get("auth_required"))


def can_write_club(email: str | None, club_id: str, meta: dict[str, Any] | None) -> bool:
    if is_platform_admin(email):
        return True
    if not email:
        return False
    # Democlubs blijven open tot Q4 besloten is, tenzij auth_required expliciet aan staat.
    if meta and meta.get("demo") and not club_auth_required(meta):
        return True
    return email.strip().lower() in club_writers(meta)


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


def authorize_write(club_id: str, request: Request | None = None, *, meta: dict[str, Any] | None = None) -> None:
    """Gooi 401/403 als de aanvrager deze club niet mag wijzigen.

    Zonder geconfigureerde Google OAuth: open (interim), behalve dat create
    elders geblokkeerd is. Met OAuth + auth_required (of BS_AUTH_ENFORCE):
    sessie + allowlist (of platformbeheerder). Democlubs zonder auth_required
    blijven open (Q4).
    """
    # Create-pad gebruikt authorize_platform_admin; hier geen speciale create-logica.
    if not auth_configured():
        return None
    if meta is not None and not club_auth_required(meta):
        # Club nog niet achter login; democlubs/Mierlo blijven werken tijdens uitrol.
        return None
    if meta is None and not auth_enforce_global():
        # Aanroeper gaf geen meta (oude tests); zonder enforce blijft open.
        return None
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Inloggen vereist (Google) om te wijzigen")
    if not can_write_club(user["email"], club_id, meta):
        raise HTTPException(
            403,
            f"Geen schrijfrecht voor club '{club_id}' met {user['email']}. "
            "Vraag de clubbeheerder om je e-mail toe te voegen.",
        )
    return None


def auth_status(request: Request | None, *, club_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    user = current_user(request)
    email = user["email"] if user else None
    return {
        "configured": auth_configured(),
        "enforce": auth_enforce_global(),
        "user": user,
        "is_platform_admin": is_platform_admin(email),
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
        "club_auth_required": club_auth_required(club_meta) if club_meta is not None else None,
        "can_write_club": (
            (not auth_configured())
            or (club_meta is not None and not club_auth_required(club_meta))
            or can_write_club(email, (club_meta or {}).get("id") or "", club_meta)
        )
        if club_meta is not None
        else None,
        # Haak voor later (I4): e-mail + wachtwoord per user — niet gebouwd.
        "password_login": False,
    }
