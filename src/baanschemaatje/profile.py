"""Clubprofiel: alles wat per vereniging verschilt, en niets meer.

Een clubprofiel is configuratie. Elke vereniging (de eerste referentie is
Mierlose T.V.) gebruikt hetzelfde schema; KNLTB-defaults staan in
``categories.py`` en de generieke regel-defaults in ``CORE_RULE_DEFAULTS``.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from baanschemaatje import miniyaml
from baanschemaatje.categories import BLOCK_CATEGORIES, DEFAULT_DURATIONS, MIN_RESERVATION, Category


class ProfileError(ValueError):
    """Ongeldig clubprofiel; de melding noemt alle gevonden problemen."""


def hhmm_to_min(v: Any, where: str = "") -> int:
    if isinstance(v, int):  # YAML 1.1 leest 09:00 soms als sexagesimaal getal
        return v
    s = str(v).strip()
    try:
        h, m = s.split(":")
        hi, mi = int(h), int(m)
    except ValueError as exc:
        raise ProfileError(f"{where}: verwacht tijd als 'HH:MM', kreeg {v!r}") from exc
    if not (0 <= hi < 24 and 0 <= mi < 60):
        raise ProfileError(f"{where}: ongeldige tijd {v!r}")
    return hi * 60 + mi


def min_to_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


#: Generieke regel-defaults. Bron per regel staat erbij:
#:   [CR B3] = KNLTB Competitiereglement (vastgesteld 11-11-2025), Bijlage 3
#:             "Variabele begintijden bij wedstrijden en baanplanning";
#:   [product] = Baanschemaatje-default (geen KNLTB-regel), club mag aanpassen.
#: Een clubprofiel mag strenger zijn dan het reglement (bv. 8p-venster 10-11).
#: "Begintijd" = start van de eerste partij van een team (de wedstrijd).
CORE_RULE_DEFAULTS: dict[str, dict[str, Any]] = {
    # [CR B3 1.1] Begintijd alleen op hele of halve uren ...
    "match_start_grid": {"value": 30, "hard": True},
    # [CR B3 1.1] ... niet vroeger dan 08:30 en niet later dan 16:30.
    "match_start_window": {"from": "08:30", "to": "16:30", "hard": True},
    # [CR B3 1.1.a] Juniorencompetities (Groen + Junioren 11-14): begintijd 08:30-12:00 ...
    "junioren_start_window": {"from": "08:30", "to": "12:00", "hard": False},
    # [CR B3 1.1.a] ... bij baancapaciteitsproblemen uiterlijk 15:00 ...
    "junioren_latest_start": {"time": "15:00", "hard": True},
    # [CR B3 1.1.a] ... en uiterlijk 13:00 bij 8 partijen gemengd junioren.
    "junioren_mixed_8p_latest_start": {"time": "13:00", "hard": True},
    # [CR B3 1.1.b] Reguliere gemengde 8 partijen: begintijd uiterlijk 14:00.
    "mixed_8p_latest_start": {"time": "14:00", "hard": True},
    # [CR B3 1.2] Reisafstand uitspelend team >= 80 km: niet vóór 10:00.
    # Geldt alleen als de seizoensinput een reisafstand bevat.
    "travel_not_before": {"value": 80, "time": "10:00", "hard": True},
    # [CR B3 2.1.a] Minimale baanreservering per partij (zie MIN_RESERVATION).
    "min_reservation": {"hard": True},
    # [product] 8p-teams: begintijd-venster. Default = KNLTB-grenzen; een club
    # mag strenger zijn (Mierlo: 10:00-11:00).
    "start_window_8p": {"from": "08:30", "to": "16:30", "hard": True},
    # [product] Gemengd 8p niet vóór ... (default 08:30 = geen extra eis).
    "mixed_8p_not_before": {"time": "08:30", "hard": True},
    # [product] Jeugd: laatste partij start uiterlijk ... (default 19:30 =
    # gelijk aan CR B3 2.1.c; club mag strenger, bv. 17:30).
    "youth_last_start": {"time": "19:30", "hard": True},
    # [product] Eerste partij van elk team bij voorkeur uiterlijk 15:00.
    "first_start_deadline": {"time": "15:00", "hard": False},
    # [product] Max aaneengesloten wachttijd tussen partijen van één team.
    "max_wait_minutes": {"value": 60, "hard": True},
    # [product] Max aantal speelblokken per team per dag.
    "max_blocks_per_team": {"value": 2, "hard": True},
    # [product] Strikte S → D → GD-waterval + rondes voor 8p-teams.
    "waterfall_8p": {"hard": True},
}


#: Bron per regel (voor UI/rapportage). "product" = geen KNLTB-regel.
RULE_SOURCES: dict[str, str] = {
    "match_start_grid": "KNLTB CR Bijlage 3, 1.1",
    "match_start_window": "KNLTB CR Bijlage 3, 1.1",
    "junioren_start_window": "KNLTB CR Bijlage 3, 1.1.a",
    "junioren_latest_start": "KNLTB CR Bijlage 3, 1.1.a",
    "junioren_mixed_8p_latest_start": "KNLTB CR Bijlage 3, 1.1.a",
    "mixed_8p_latest_start": "KNLTB CR Bijlage 3, 1.1.b",
    "travel_not_before": "KNLTB CR Bijlage 3, 1.2",
    "min_reservation": "KNLTB CR Bijlage 3, 2.1.a",
}


@dataclass(frozen=True)
class Rule:
    name: str
    hard: bool
    params: dict[str, Any]


@dataclass(frozen=True)
class Reservation:
    """Vaste baanreservering voor een blokcategorie (Rood/Oranje)."""

    category: Category
    courts: tuple[int, ...]
    courts_if_rood: tuple[int, ...] | None = None


@dataclass(frozen=True)
class ClubProfile:
    name: str
    knltb_name: str
    courts: int
    day_start: int
    fallback_start: int | None
    last_start: int
    day_end: int
    reservations: dict[Category, Reservation] = field(default_factory=dict)
    max_courts_per_team: int = 2
    court_pairs: tuple[tuple[int, int], ...] | None = None
    preferred_courts_8p: tuple[int, ...] = ()
    rules: dict[str, Rule] = field(default_factory=dict)
    durations: dict[Category, int] = field(default_factory=dict)
    source: str = ""

    @property
    def court_list(self) -> list[int]:
        return list(range(1, self.courts + 1))

    def expected_duration(self, category: Category, export_minutes: int = 0) -> int:
        """Verwachte speelduur: clubprofiel-override > KNLTB-export > core-default."""
        if category in self.durations:
            return self.durations[category]
        if export_minutes:
            return export_minutes
        return DEFAULT_DURATIONS[category]

    def duration_for(self, category: Category, export_minutes: int = 0) -> int:
        """Gereserveerde tijd per partij: verwachte duur, maar nooit korter dan
        de KNLTB-minimumreservering (CR Bijlage 3, 2.1.a) als die regel hard is."""
        d = self.expected_duration(category, export_minutes)
        r = self.rules.get("min_reservation")
        m = MIN_RESERVATION.get(category)
        if r is not None and r.hard and m:
            d = max(d, m)
        return d

    def rule(self, name: str) -> Rule:
        return self.rules[name]


def _as_courts(v: Any, where: str, n: int, errors: list[str]) -> tuple[int, ...]:
    if not isinstance(v, list) or not v or not all(isinstance(c, int) for c in v):
        errors.append(f"{where}: verwacht een lijst baannummers, kreeg {v!r}")
        return ()
    bad = [c for c in v if not 1 <= c <= n]
    if bad:
        errors.append(f"{where}: baan {bad} bestaat niet (club heeft {n} banen)")
    if len(set(v)) != len(v):
        errors.append(f"{where}: dubbele baannummers in {v}")
    return tuple(v)


def profile_from_dict(data: dict[str, Any], source: str = "") -> ClubProfile:
    errors: list[str] = []
    if not isinstance(data, dict):
        raise ProfileError(f"{source}: clubprofiel moet een mapping zijn")

    known = {"club", "courts", "day", "reservations", "court_assignment", "rules", "durations"}
    for k in data:
        if k not in known:
            errors.append(f"onbekende sectie '{k}' (toegestaan: {sorted(known)})")

    club = data.get("club") or {}
    name = str(club.get("name") or "").strip()
    if not name:
        errors.append("club.name ontbreekt")
    knltb_name = str(club.get("knltb_name") or "").strip()

    courts_cfg = data.get("courts") or {}
    n = courts_cfg.get("count")
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        errors.append(f"courts.count moet een positief geheel getal zijn, kreeg {n!r}")
        n = 1

    day = data.get("day") or {}

    def _t(key: str, default: str | None) -> int | None:
        v = day.get(key, default)
        if v is None:
            return None
        try:
            return hhmm_to_min(v, f"day.{key}")
        except ProfileError as exc:
            errors.append(str(exc))
            return None

    day_start = _t("start", "09:00")
    fallback = _t("fallback_start", None)
    last_start = _t("last_start", "19:30")
    day_end = _t("end", "20:00")
    for key, v in (("start", day_start), ("fallback_start", fallback), ("last_start", last_start), ("end", day_end)):
        if v is not None and v % 15:
            errors.append(f"day.{key} moet op het kwartiergrid liggen ({min_to_hhmm(v)})")
    if None not in (day_start, last_start, day_end):
        if not day_start < last_start <= day_end:
            errors.append("day: verwacht start < last_start <= end")
    if fallback is not None and day_start is not None and fallback > day_start:
        errors.append("day.fallback_start moet vóór of gelijk aan day.start liggen")

    reservations: dict[Category, Reservation] = {}
    for key, cfg in (data.get("reservations") or {}).items():
        try:
            cat = Category(key)
        except ValueError:
            errors.append(f"reservations.{key}: onbekende categorie")
            continue
        if cat not in BLOCK_CATEGORIES:
            errors.append(f"reservations.{key}: alleen {sorted(c.value for c in BLOCK_CATEGORIES)} kunnen een vaste reservering hebben")
            continue
        if not isinstance(cfg, dict):
            errors.append(f"reservations.{key}: verwacht mapping met 'courts'")
            continue
        cs = _as_courts(cfg.get("courts"), f"reservations.{key}.courts", n, errors)
        cir = None
        if cfg.get("courts_if_rood") is not None:
            cir = _as_courts(cfg["courts_if_rood"], f"reservations.{key}.courts_if_rood", n, errors)
        reservations[cat] = Reservation(cat, cs, cir)
    if Category.ROOD in reservations and Category.ORANJE in reservations:
        rood = set(reservations[Category.ROOD].courts)
        oranje_r = reservations[Category.ORANJE]
        o = set(oranje_r.courts_if_rood or oranje_r.courts)
        if rood & o:
            errors.append(
                "reservations: Rood en Oranje overlappen als ze op dezelfde dag spelen "
                f"(baan {sorted(rood & o)}); zet oranje.courts_if_rood"
            )

    ca = data.get("court_assignment") or {}
    mcpt = ca.get("max_courts_per_team", 2)
    if not isinstance(mcpt, int) or mcpt < 1:
        errors.append("court_assignment.max_courts_per_team moet >= 1 zijn")
        mcpt = 2
    pairs = None
    if ca.get("pairs") is not None:
        raw = ca["pairs"]
        if not isinstance(raw, list) or not all(isinstance(p, list) and len(p) == 2 for p in raw):
            errors.append("court_assignment.pairs: verwacht lijst van paren, bv. [[1, 2], [3, 4]]")
        else:
            flat = _as_courts([c for p in raw for c in p], "court_assignment.pairs", n, errors)
            if flat:
                pairs = tuple((p[0], p[1]) for p in raw)
                if mcpt > 2:
                    errors.append("court_assignment.pairs vereist max_courts_per_team <= 2")
    pref = ()
    if ca.get("preferred_courts_8p") is not None:
        pref = _as_courts(ca["preferred_courts_8p"], "court_assignment.preferred_courts_8p", n, errors)

    rules: dict[str, Rule] = {}
    user_rules = data.get("rules") or {}
    for key in user_rules:
        if key not in CORE_RULE_DEFAULTS:
            errors.append(f"rules.{key}: onbekende regel (bekend: {sorted(CORE_RULE_DEFAULTS)})")
    for key, default in CORE_RULE_DEFAULTS.items():
        merged = copy.deepcopy(default)
        override = user_rules.get(key)
        if override is not None:
            if not isinstance(override, dict):
                errors.append(f"rules.{key}: verwacht mapping")
            else:
                for k2 in override:
                    if k2 not in default:
                        errors.append(f"rules.{key}.{k2}: onbekende parameter")
                merged.update(override)
        if not isinstance(merged.get("hard"), bool):
            errors.append(f"rules.{key}.hard moet true/false zijn")
        params = {k: v for k, v in merged.items() if k != "hard"}
        for pk in ("time", "from", "to"):
            if pk in params:
                try:
                    params[pk] = hhmm_to_min(params[pk], f"rules.{key}.{pk}")
                except ProfileError as exc:
                    errors.append(str(exc))
        if "value" in params and (not isinstance(params["value"], int) or params["value"] < 0):
            errors.append(f"rules.{key}.value moet een niet-negatief geheel getal zijn")
        rules[key] = Rule(key, bool(merged.get("hard")), params)

    rg = rules.get("match_start_grid")
    if rg and rg.hard and isinstance(rg.params.get("value"), int) and rg.params["value"] > 0:
        for key, v in (("start", day_start), ("fallback_start", fallback)):
            if v is not None and v % rg.params["value"]:
                errors.append(
                    f"day.{key} ({min_to_hhmm(v)}) ligt niet op een heel/half uur; "
                    "Rood/Oranje beginnen op de dagstart (CR Bijlage 3, 1.1)"
                )

    durations: dict[Category, int] = {}
    for key, v in (data.get("durations") or {}).items():
        try:
            cat = Category(key)
        except ValueError:
            errors.append(f"durations.{key}: onbekende categorie")
            continue
        if not isinstance(v, int) or v <= 0 or v % 15:
            errors.append(f"durations.{key}: verwacht positief veelvoud van 15 minuten")
            continue
        m = MIN_RESERVATION.get(cat)
        if m and rules.get("min_reservation") and rules["min_reservation"].hard and v < m:
            errors.append(
                f"durations.{key}: {v} min is korter dan de KNLTB-minimumreservering "
                f"van {m} min (CR Bijlage 3, 2.1.a)"
            )
            continue
        durations[cat] = v

    if errors:
        raise ProfileError(f"Ongeldig clubprofiel {source}:\n  - " + "\n  - ".join(errors))

    return ClubProfile(
        name=name,
        knltb_name=knltb_name,
        courts=n,
        day_start=day_start,
        fallback_start=fallback,
        last_start=last_start,
        day_end=day_end,
        reservations=reservations,
        max_courts_per_team=mcpt,
        court_pairs=pairs,
        preferred_courts_8p=pref,
        rules=rules,
        durations=durations,
        source=source,
    )


def load_profile(path: str | Path) -> ClubProfile:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    data = json.loads(text) if p.suffix.lower() == ".json" else miniyaml.loads(text)
    return profile_from_dict(data or {}, source=str(p))
