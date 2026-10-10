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


#: Bevindingen van de zondag-validator die op ma-vr (geen Bijlage 3) niet gelden;
#: daar toetsen we zelf aan het dagvenster van het clubprofiel.
_SUNDAY_ONLY = ("LAATSTE-START", "EERSTE-START", "EERSTE-START-GROEN", "EERSTE-START-VOORKEUR",
                "VENSTER-GEM", "VENSTER-JEUGD", "VENSTER-JEUGD-LAAT")


def _weekday_findings(plan: dict[str, Any], prof: ClubProfile) -> list[dict[str, Any]]:
    from baanschemaatje.profile import min_to_hhmm

    out = []
    date = plan.get("date")
    for r in plan.get("rows") or []:
        st, en = str(r.get("start") or ""), str(r.get("end") or "")
        if len(st) < 5 or not st[:2].isdigit() or r.get("kind") == "W":
            continue
        s = int(st[:2]) * 60 + int(st[3:5])
        subj = f"{r.get('label', '')} {r.get('home_team', '')}".strip()
        if s > prof.last_start:
            out.append({"rule": "LAATSTE-START", "severity": "HARD", "date": date, "subject": subj,
                        "message": f"{r.get('part')} start {st}, na de laatste start {min_to_hhmm(prof.last_start)} "
                                   f"van de {prof.weekday} (clubprofiel)"})
        if s < prof.day_start:
            out.append({"rule": "DAGVENSTER", "severity": "HARD", "date": date, "subject": subj,
                        "message": f"{r.get('part')} start {st}, vóór de dagstart {min_to_hhmm(prof.day_start)}"})
        if len(en) >= 5 and en[:2].isdigit() and int(en[:2]) * 60 + int(en[3:5]) > prof.day_end:
            out.append({"rule": "EINDTIJD", "severity": "HARD", "date": date, "subject": subj,
                        "message": f"{r.get('part')} eindigt {en}, na {min_to_hhmm(prof.day_end)}"})
    return out


def _unplayed_season(season: Path, td: str) -> Path:
    """Kopie van het seizoen zonder gespeelde wedstrijden (die worden niet gepland)."""
    import csv

    with Path(season).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    if not rows or "Status" not in rows[0] or not any(r.get("Status") == "gespeeld" for r in rows):
        return Path(season)
    out = Path(td) / "season-open.tsv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(r for r in rows if r.get("Status") != "gespeeld")
    return out


def validate_plan(plan: dict[str, Any], season: Path, profile: ClubProfile | None = None) -> dict[str, Any]:
    """``plan`` = {"status", "date", "rows"}; geeft {available, hard, model, findings}.

    Gespeelde wedstrijden tellen niet mee. Op ma-vr (geen Bijlage 3) gelden de
    zondagvensters niet maar het dagvenster van het profiel voor die weekdag."""
    if profile is not None and profile.weekday is None and plan.get("date"):
        from baanschemaatje.profile import WEEKDAYS
        from datetime import datetime as _dt

        dd = {str(r.get("dagdeel") or "") for r in plan.get("rows") or []}
        if not dd - {""}:
            dd = {("ochtend" if "ochtend" in str(r.get("team", "")).lower() else
                   "middag" if "middag" in str(r.get("team", "")).lower() else "dag") for r in plan.get("rows") or []}
        profile = profile.for_day(WEEKDAYS[_dt.strptime(plan["date"], "%d-%m-%Y").weekday()], dd)
    with tempfile.TemporaryDirectory() as td:
        season = _unplayed_season(season, td)
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
    if profile is not None and not profile.bijlage3:
        f = [x for x in f if x.get("rule") not in _SUNDAY_ONLY] + _weekday_findings(plan, profile)
    return {
        "available": True,
        "hard": sum(1 for x in f if x.get("severity") == "HARD"),
        "model": sum(1 for x in f if x.get("severity") == "MODEL"),
        "findings": f,
    }
