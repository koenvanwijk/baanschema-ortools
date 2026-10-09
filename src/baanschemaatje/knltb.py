"""Toets een plan aan de KNLTB-regels (Competitiereglement 11-11-2025, Bijlage 3).

Los van ``scripts/validate_schedule.py``: die toetst aan de operationele SPEC
van het eerste clubprofiel (inclusief clubafspraken). Deze toets kent alleen
het reglement, zodat je kunt zien of een voorstel KNLTB-conform is, ook als het
een clubafspraak versoepelt.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from baanschemaatje.categories import JUNIOR_CATEGORIES, MIN_RESERVATION, Category

UNSCHEDULED = "NIET_GELUKT"


def _m(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def knltb_findings(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []

    def add(rule: str, subject: str, msg: str) -> None:
        out.append({"rule": rule, "severity": "HARD", "subject": subject, "message": msg})

    teams: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("kind") == "W":
            continue
        teams[r["team_id"]].append(r)
    for tid, rs in teams.items():
        label = f"{rs[0].get('label', '')} {rs[0].get('home_team', '')}".strip()
        cat = Category(rs[0].get("category", "overig"))
        team = rs[0]["team"].lower()
        placed = [r for r in rs if r["start"] != UNSCHEDULED]
        ng = [r["part"] for r in rs if r["start"] == UNSCHEDULED]
        if ng:
            add("NIET-GEPLAND", label, f"{len(ng)} partij(en) niet ingepland: {', '.join(ng)}")
        if not placed:
            continue
        first = min(_m(r["start"]) for r in placed)
        if first % 30:
            add("B3-1.1-GRID", label, f"begintijd {_hhmm(first)} niet op heel/half uur")
        if not 8 * 60 + 30 <= first <= 16 * 60 + 30:
            add("B3-1.1-VENSTER", label, f"begintijd {_hhmm(first)} buiten 08:30-16:30")
        is_8p = len(rs) == 8
        mixed = "gemengd" in team
        if cat in JUNIOR_CATEGORIES:
            limit = 13 * 60 if (is_8p and mixed) else 15 * 60
            if first > limit:
                add("B3-1.1a-JUNIOREN", label, f"begintijd {_hhmm(first)} na {_hhmm(limit)}")
        elif is_8p and mixed and first > 14 * 60:
            add("B3-1.1b-GEMENGD8", label, f"begintijd {_hhmm(first)} na 14:00")
        for r in placed:
            if _m(r["start"]) > 19 * 60 + 30:
                add("B3-2.1c-1930", label, f"{r['part']} start {r['start']} na 19:30")
            mr = MIN_RESERVATION.get(cat)
            if mr and _m(r["end"]) - _m(r["start"]) < mr:
                add("B3-2.1a-RESERVERING", label, f"{r['part']} {_m(r['end']) - _m(r['start'])} min < {mr} min")
    return out


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"
