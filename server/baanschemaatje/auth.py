"""Schrijfrechten per club.

Alle schrijfacties (profiel, seizoen, schema, bingo, dashboard, …) lopen via
``authorize_write``. Nu staat die alles toe (interim-besluit Oscar 09/14-10-2026:
open testen / iedereen met de link).

Productrichting (Oscar 26-10-2026): login per club + access management —
zie ``docs/USER-STORIES.md`` sectie I (I3 fase 2, I4 fase 3). Routes hoeven
niet te veranderen: hier later sessie/token controleren en 401/403 geven.
Democlubs en publieke alleen-lezen links (tv/dag): zie I5 / open vragen.
"""

from __future__ import annotations

from fastapi import Request


def authorize_write(club_id: str, request: Request | None = None) -> None:
    """Gooi HTTPException(401/403) als de aanvrager deze club niet mag wijzigen.

    TODO(I3 Login per club): echte controle. Tot dan: iedereen mag schrijven.
    """
    return None
