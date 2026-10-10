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
    # Uren 24-47 = na middernacht (bv. "25:00" = 01:00 de volgende dag).
    if not (0 <= hi < 48 and 0 <= mi < 60):
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
    # [KNLTB begintijden] Avondcompetities beginnen om 19:00 (8&9-tennis do/vr
    # 19:00-20:00). Venster voor de begintijd van een avondwedstrijd.
    "evening_start_window": {"from": "19:00", "to": "20:00", "hard": True},
    # [KNLTB begintijden] Ochtendcompetities: begintijd 09:00-10:00.
    "morning_start_window": {"from": "09:00", "to": "10:00", "hard": True},
    # [KNLTB begintijden] Middagcompetities: 13:00.
    "afternoon_start_window": {"from": "13:00", "to": "13:00", "hard": True},
}

#: Weekdagen waarop Bijlage 3 (variabele begintijden) geldt: alleen za/zo.
BIJLAGE3_DAYS = frozenset({"zaterdag", "zondag"})
WEEKDAYS = ("maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag")

#: Standaard dagvenster op ma-vr (avondcompetities). [product]-defaults,
#: gebaseerd op de KNLTB-begintijd 19:00; 4 dubbels op 2 banen = 2 rondes van
#: 90 min (19:00 en 20:30), klaar ~22:00. Club mag per weekdag afwijken
#: (sectie ``weekdays``). ``courts`` = aantal banen (1..N) met verlichting die
#: die avond beschikbaar zijn (None = alle banen).
EVENING_DEFAULT: dict[str, Any] = {"start": "19:00", "last_start": "20:30", "end": "23:00",
                                   "courts": None, "lighting": True}
#: Ochtendcompetitie op een doordeweekse dag: dagstart wordt dan 09:00.
MORNING_START = "09:00"


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
    "evening_start_window": "KNLTB Standaard begintijden competitie (avond 19:00)",
    "morning_start_window": "KNLTB Standaard begintijden competitie (ochtend 9:00-10:00)",
    "afternoon_start_window": "KNLTB Standaard begintijden competitie (middag 13:00)",
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
    #: Clubafspraak "aangrenzende banen": alle banen die een team op een dag gebruikt
    #: vormen één aaneengesloten blok (bv. 1-2, 1-2-3, 6-7-8). Default aan.
    adjacent_courts: bool = True
    preferred_courts_8p: tuple[int, ...] = ()
    rules: dict[str, Rule] = field(default_factory=dict)
    durations: dict[Category, int] = field(default_factory=dict)
    source: str = ""
    #: Per-weekdag instellingen (minuten), alleen wat de club zelf opgaf:
    #: {weekdag: {start, last_start, end, fallback_start, courts, lighting}}.
    weekday_cfg: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Voor welke weekdag dit profiel is afgeleid (None = basis/zondag).
    weekday: str | None = None
    lighting: bool = True

    @property
    def bijlage3(self) -> bool:
        """Geldt CR Bijlage 3 (variabele begintijden za/zo, laatste start 19:30)?"""
        return self.weekday is None or self.weekday in BIJLAGE3_DAYS

    def weekday_settings(self, weekday: str) -> dict[str, Any]:
        """Effectieve dagvensterinstellingen (minuten) voor een weekdag."""
        cfg = self.weekday_cfg.get(weekday, {})
        if weekday in BIJLAGE3_DAYS:
            base = {"start": self.day_start, "fallback_start": self.fallback_start,
                    "last_start": self.last_start, "end": self.day_end, "courts": None, "lighting": True}
        else:
            base = {k: (hhmm_to_min(v) if k in ("start", "last_start", "end") else v)
                    for k, v in EVENING_DEFAULT.items()}
            base["fallback_start"] = None
        out = dict(base)
        out.update(cfg)
        # Einde ná middernacht: "01:00" bij start 19:00 betekent 01:00 de volgende dag (25:00).
        if out["end"] <= out["start"]:
            out["end"] += 24 * 60
        out["defaults"] = sorted(k for k in ("start", "last_start", "end", "courts", "lighting") if k not in cfg)
        return out

    def for_day(self, weekday: str, dagdelen: set[str] | frozenset[str] = frozenset()) -> "ClubProfile":
        """Profiel voor één speeldag: dagvenster, banen en regels van die weekdag.

        Za/zo: het basisprofiel (Bijlage 3), eventueel met club-overrides.
        Ma-vr: avondvenster (default 19:00, laatste start 20:30, einde 23:00);
        Bijlage 3 geldt niet, dus het 08:30-16:30-venster wordt het dagvenster
        en de 15:00-voorkeur vervalt. Speelt er die dag ook een
        ochtendcompetitie, dan begint de dag om 09:00."""
        import dataclasses

        ws = self.weekday_settings(weekday)
        start, last, end, fb = ws["start"], ws["last_start"], ws["end"], ws.get("fallback_start")
        rules = dict(self.rules)
        if weekday not in BIJLAGE3_DAYS:
            if "ochtend" in dagdelen:
                start = min(start, hhmm_to_min(MORNING_START))
            if "middag" in dagdelen:
                start = min(start, rules["afternoon_start_window"].params["from"])
            rules["match_start_window"] = Rule("match_start_window", True, {"from": start, "to": last})
            rules["first_start_deadline"] = Rule("first_start_deadline", False, {"time": last})
            rules["youth_last_start"] = Rule("youth_last_start", rules["youth_last_start"].hard, {"time": last})
        n = ws.get("courts") or self.courts
        n = min(n, self.courts)
        res = {}
        for k, r in self.reservations.items():
            if all(c <= n for c in r.courts):
                cir = r.courts_if_rood if r.courts_if_rood and all(c <= n for c in r.courts_if_rood) else None
                res[k] = Reservation(r.category, r.courts, cir)
        pairs = self.court_pairs
        if pairs:
            pairs = tuple(p for p in pairs if max(p) <= n) or None
        return dataclasses.replace(
            self, day_start=start, fallback_start=fb if (fb is not None and fb < start) else None,
            last_start=last, day_end=end, courts=n, reservations=res, court_pairs=pairs,
            preferred_courts_8p=tuple(c for c in self.preferred_courts_8p if c <= n),
            rules=rules, weekday=weekday, lighting=bool(ws.get("lighting", True)),
        )

    def for_date(self, date: str, fixtures: list[Any] | None = None) -> "ClubProfile":
        from datetime import datetime as _dt

        wd = WEEKDAYS[_dt.strptime(date, "%d-%m-%Y").weekday()]
        dd = {getattr(f, "dagdeel", "dag") for f in (fixtures or []) if f.date == date}
        return self.for_day(wd, dd)

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

    known = {"club", "courts", "day", "reservations", "court_assignment", "rules", "durations", "weekdays"}
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
    adjacent = ca.get("adjacent", True)
    if not isinstance(adjacent, bool):
        errors.append("court_assignment.adjacent moet true of false zijn")
        adjacent = True
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

    weekday_cfg: dict[str, dict[str, Any]] = {}
    wraw = data.get("weekdays") or {}
    if not isinstance(wraw, dict):
        errors.append("weekdays: verwacht mapping per weekdag, bv. {vrijdag: {start: '19:00'}}")
        wraw = {}
    for wd, cfg in wraw.items():
        if wd not in WEEKDAYS:
            errors.append(f"weekdays.{wd}: onbekende weekdag (gebruik {', '.join(WEEKDAYS)})")
            continue
        if not isinstance(cfg, dict):
            errors.append(f"weekdays.{wd}: verwacht mapping")
            continue
        c: dict[str, Any] = {}
        for k, v in cfg.items():
            if k in ("start", "last_start", "end", "fallback_start"):
                try:
                    c[k] = hhmm_to_min(v, f"weekdays.{wd}.{k}")
                except ProfileError as exc:
                    errors.append(str(exc))
                    continue
                if c[k] % 15:
                    errors.append(f"weekdays.{wd}.{k} moet op het kwartiergrid liggen")
            elif k == "courts":
                if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= n):
                    errors.append(f"weekdays.{wd}.courts moet 1..{n} zijn (banen 1 t/m N beschikbaar)")
                else:
                    c[k] = v
            elif k == "lighting":
                if not isinstance(v, bool):
                    errors.append(f"weekdays.{wd}.lighting moet true of false zijn")
                else:
                    c[k] = v
            elif k == "note":
                c[k] = str(v)[:200]
            else:
                errors.append(f"weekdays.{wd}.{k}: onbekende instelling (start, last_start, end, fallback_start, courts, lighting, note)")
        weekday_cfg[wd] = c
    for wd, c in weekday_cfg.items():
        st = c.get("start", hhmm_to_min(EVENING_DEFAULT["start"]) if wd not in BIJLAGE3_DAYS else (day_start or 0))
        ls = c.get("last_start", hhmm_to_min(EVENING_DEFAULT["last_start"]) if wd not in BIJLAGE3_DAYS else (last_start or 0))
        en = c.get("end", hhmm_to_min(EVENING_DEFAULT["end"]) if wd not in BIJLAGE3_DAYS else (day_end or 0))
        if en <= st:
            en += 24 * 60
        if not st < ls <= en:
            errors.append(f"weekdays.{wd}: verwacht start < last_start <= end (einde mag na middernacht, bv. 01:00)")

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
        adjacent_courts=adjacent,
        preferred_courts_8p=pref,
        rules=rules,
        durations=durations,
        source=source,
        weekday_cfg=weekday_cfg,
    )


def load_profile(path: str | Path) -> ClubProfile:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    data = json.loads(text) if p.suffix.lower() == ".json" else miniyaml.loads(text)
    return profile_from_dict(data or {}, source=str(p))
