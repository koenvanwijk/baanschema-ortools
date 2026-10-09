"""Schrijfrechten per club — bewust nog OPEN (besluit Oscar 09-10-2026).

Alle schrijfacties (profiel opslaan, seizoen uploaden) lopen via
``authorize_write``. Nu staat die alles toe; "Login per club" (ROADMAP) komt
hier later in: sessie/token controleren en 401/403 geven. De routes hoeven
daarvoor niet te veranderen.
"""

from __future__ import annotations

from fastapi import Request


def authorize_write(club_id: str, request: Request | None = None) -> None:
    """Gooi HTTPException(401/403) als de aanvrager deze club niet mag wijzigen.

    TODO(Login per club): echte controle. Tot dan: iedereen mag schrijven.
    """
    return None
