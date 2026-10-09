"""Seizoensinput → genormaliseerd model.

Adapter voor de bestaande KNLTB-export als TSV (kolommen ``Datum``, ``Schema``,
``Wedstrijden``, ``Wedstrijdduur``, ``Singles``, ``Doubles``, ``Mix``,
``Team 1``, ``Team 2``). Het bestand wordt alleen gelezen.

Het genormaliseerde model is clubneutraal: welke club "thuis" is, komt uit het
clubprofiel (``club.knltb_name``), niet uit de code.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from baanschemaatje.categories import BLOCK_CATEGORIES, Category, classify


@dataclass(frozen=True)
class Fixture:
    """Eén thuiswedstrijd (teamdag) van de club op een speeldag."""

    date: str  # dd-mm-YYYY, zoals in de KNLTB-export
    schema: str
    category: Category
    matches: int
    export_duration: int
    singles: int
    doubles: int
    mix: int
    home_team: str
    away_team: str
    #: Reisafstand van het uitspelende team in km (CR Bijlage 3, 1.2); None = onbekend.
    travel_km: int | None = None

    @property
    def team_key(self) -> str:
        """Unieke sleutel per (dag, schema, thuisteam)."""
        return f"{self.schema} · {self.home_team}" if self.home_team else self.schema

    @property
    def is_block(self) -> bool:
        """Rood/Oranje: blokreservering i.p.v. losse partijen."""
        return self.category in BLOCK_CATEGORIES

    @property
    def label(self) -> str:
        """Kort label, bv. J13-17 / M13-17 / JU11-14 / GEM."""
        from baanschemaatje.categories import short_label

        return short_label(self.schema, self.category)

    @property
    def is_mixed(self) -> bool:
        return "gemengd" in self.schema.lower()

    @property
    def is_8p(self) -> bool:
        return self.matches == 8


@dataclass
class Season:
    fixtures: list[Fixture]
    source: str = ""

    def dates(self) -> list[str]:
        ds = {f.date for f in self.fixtures}
        return sorted(ds, key=lambda d: datetime.strptime(d, "%d-%m-%Y"))

    def day(self, date: str) -> list[Fixture]:
        return [f for f in self.fixtures if f.date == date]

    def by_date(self) -> dict[str, list[Fixture]]:
        out: dict[str, list[Fixture]] = defaultdict(list)
        for f in self.fixtures:
            out[f.date].append(f)
        return dict(out)


def _int(v: str | None) -> int:
    v = (v or "").strip()
    return int(v) if v else 0


def load_season_tsv(path: str | Path, home_name: str = "") -> Season:
    """Lees een KNLTB-export (TSV) read-only in.

    ``home_name`` is ``club.knltb_name`` uit het clubprofiel. Staat alleen
    Team 2 op naam van de club, dan wordt die als thuisteam behandeld.
    """
    p = Path(path)
    fixtures: list[Fixture] = []
    home_up = home_name.upper().strip()
    with p.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            date = (row.get("Datum") or "").strip()
            schema = (row.get("Schema") or "").strip()
            if not date or not schema:
                continue
            cat = classify(schema)
            matches = _int(row.get("Wedstrijden"))
            if not matches:
                continue
            t1 = (row.get("Team 1") or "").strip()
            t2 = (row.get("Team 2") or "").strip()
            home, away = t1, t2
            if home_up and not t1.upper().startswith(home_up) and t2.upper().startswith(home_up):
                home, away = t2, t1
            fixtures.append(
                Fixture(
                    date=date,
                    schema=schema,
                    category=cat,
                    matches=matches,
                    export_duration=_int(row.get("Wedstrijdduur")),
                    singles=_int(row.get("Singles")),
                    doubles=_int(row.get("Doubles")),
                    mix=_int(row.get("Mix")),
                    home_team=home,
                    away_team=away,
                    # Optionele kolom; de huidige export heeft hem niet.
                    travel_km=_int(row.get("Reisafstand")) if (row.get("Reisafstand") or "").strip() else None,
                )
            )
    return Season(fixtures=fixtures, source=str(p))
