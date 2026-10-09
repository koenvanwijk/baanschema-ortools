"""Ops-validator voor Baanschemaatje.

Roept de bestaande ``scripts/validate_schedule.py`` ongewijzigd aan (die toetst
aan de operationele SPEC.md van het eerste clubprofiel) en legt daar de
Baanschemaatje-besluiten overheen, zodat de ernst klopt met het clubprofiel:

* "Eerste partij uiterlijk 15:00" (reguliere teams) is een zachte voorkeur
  (``first_start_deadline``, hard: false) → MODEL i.p.v. HARD
  (besluit Oscar 09-10-2026). Strengere clubafspraken die wél hard zijn (8p
  10:00-11:00, junioren 13:00) blijven HARD.
* BANEN-PER-TEAM / BAANPAAR gaan uit van max 2 banen op vaste paren. Staat het
  clubprofiel meer banen toe of heeft het geen vaste paren, dan vervallen die
  bevindingen voor zover ze binnen het profiel vallen.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from baanschemaatje.profile import ClubProfile

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate_schedule.py"  # alleen aangeroepen, nooit gewijzigd

_SOFT_FIRST_START = "reguliere teams: uiterlijk"
_COURTS_USED = re.compile(r"gebruikt (\d+) banen")


def adjust_findings(findings: list[dict[str, Any]], profile: ClubProfile | None = None) -> list[dict[str, Any]]:
    out = []
    soft_first = profile is None or not profile.rule("first_start_deadline").hard
    for f in findings:
        f = dict(f)
        if f.get("rule") == "EERSTE-START" and _SOFT_FIRST_START in f.get("message", "") and soft_first:
            f["severity"] = "MODEL"
            f["rule"] = "EERSTE-START-VOORKEUR"
            f["message"] += " (zachte voorkeur in het clubprofiel)"
        if profile is not None:
            if f.get("rule") == "BAANPAAR" and not profile.court_pairs:
                continue
            m = _COURTS_USED.search(f.get("message", ""))
            if f.get("rule") == "BANEN-PER-TEAM" and m and int(m.group(1)) <= profile.max_courts_per_team:
                continue
        out.append(f)
    return out


def validate_plan(plan: dict[str, Any], season: Path, profile: ClubProfile | None = None) -> dict[str, Any]:
    """``plan`` = {"status", "date", "rows"}; geeft {available, hard, model, findings}."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "plan.json"
        rep = Path(td) / "rapport.json"
        src.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        subprocess.run(
            [sys.executable, str(VALIDATOR), str(src), "--season", str(season), "--quiet", "--json", str(rep)],
            cwd=ROOT, capture_output=True, text=True,
        )
        if not rep.exists():
            return {"available": False, "hard": None, "model": None, "findings": []}
        data = json.loads(rep.read_text(encoding="utf-8"))
    f = adjust_findings(data.get("findings", []), profile)
    return {
        "available": True,
        "hard": sum(1 for x in f if x.get("severity") == "HARD"),
        "model": sum(1 for x in f if x.get("severity") == "MODEL"),
        "findings": f,
    }
