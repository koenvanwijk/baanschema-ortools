"""KNLTB-competitiecategorieën en generieke defaults (SPEC-core §1, §2, §4).

Deze defaults gelden voor élke vereniging. Een clubprofiel kan ze alleen met
een expliciete override aanpassen; ze horen nooit in een clubbestand thuis.
"""

from __future__ import annotations

from enum import Enum


class Category(str, Enum):
    ROOD = "rood"
    ORANJE = "oranje"
    GROEN = "groen"
    JUNIOREN_11_14 = "junioren_11_14"
    JEUGD_13_17 = "jeugd_13_17"
    GEMENGD = "gemengd"
    SENIOREN = "senioren"
    OVERIG = "overig"


#: Standaard speelduur (minuten) per categorie — KNLTB-competitiestandaard.
DEFAULT_DURATIONS: dict[Category, int] = {
    Category.ROOD: 60,
    Category.ORANJE: 120,
    Category.GROEN: 45,
    Category.JUNIOREN_11_14: 45,
    Category.JEUGD_13_17: 90,
    Category.GEMENGD: 90,
    Category.SENIOREN: 90,
    Category.OVERIG: 90,
}

#: Minimale baanreservering per partij volgens KNLTB Competitiereglement
#: (vastgesteld 11-11-2025), Bijlage 3, 2.1.a: "voor elke partij minimaal
#: anderhalf uur ... Voor de Junioren 11 t/m 14 jaar ... minimaal drie
#: kwartier". Groen heeft geen expliciete minimumreservering; daar geldt de
#: verwachte duur van 45 min. Dit is een ondergrens voor de *reservering*, niet de verwachte
#: speelduur (DEFAULT_DURATIONS). Tenniskids (Rood/Oranje/Groen) vallen hier
#: niet expliciet onder; daarvoor geldt de verwachte duur (te verifiëren).
MIN_RESERVATION: dict[Category, int | None] = {
    Category.ROOD: None,
    Category.ORANJE: None,
    Category.GROEN: None,
    Category.JUNIOREN_11_14: 45,
    Category.JEUGD_13_17: 90,
    Category.GEMENGD: 90,
    Category.SENIOREN: 90,
    Category.OVERIG: 90,
}

#: "Juniorencompetities" in de zin van CR Bijlage 3, 1.1.a (begintijd
#: 08:30-12:00): Groen en Junioren 11 t/m 14 (besluit Oscar, 2026-10-09).
#: Jongens/Meisjes 13 t/m 17 zijn géén junioren in deze zin.
JUNIOR_CATEGORIES = frozenset({Category.GROEN, Category.JUNIOREN_11_14})

#: Rood/Oranje spelen in blokken op vaste banen vanaf dagstart (geen losse partijen).
BLOCK_CATEGORIES = frozenset({Category.ROOD, Category.ORANJE})

#: Jeugdcategorieën (o.a. voor de "jeugd niet te laat"-regel).
YOUTH_CATEGORIES = frozenset(
    {Category.GROEN, Category.JUNIOREN_11_14, Category.JEUGD_13_17}
)

#: Default inplan-prioriteit (SPEC-core §4); lager = eerder/belangrijker.
DEFAULT_PRIORITY: dict[Category, int] = {
    Category.ROOD: 1,
    Category.ORANJE: 1,
    Category.GROEN: 3,
    Category.JUNIOREN_11_14: 4,
    Category.JEUGD_13_17: 5,
    Category.GEMENGD: 6,
    Category.SENIOREN: 7,
    Category.OVERIG: 7,
}


#: Korte labels voor UI/export. Jeugd 13-17 wordt gesplitst op geslacht.
SHORT_LABELS: dict[Category, str] = {
    Category.ROOD: "ROOD",
    Category.ORANJE: "ORA",
    Category.GROEN: "GRO",
    Category.JUNIOREN_11_14: "JU11-14",
    Category.JEUGD_13_17: "J/M13-17",
    Category.GEMENGD: "GEM",
    Category.SENIOREN: "SEN",
    Category.OVERIG: "OV",
}


def short_label(schema: str, category: Category | None = None) -> str:
    """Kort label voor een teamschema, bv. ``J13-17`` (jongens) of ``M13-17``
    (meisjes). Het geslacht staat in de KNLTB-export alleen in de
    schema-omschrijving ("Jongens 13 t/m 17 ..." / "Meisjes 13 t/m 17 ...")."""
    cat = category or classify(schema)
    s = (schema or "").lower()
    if cat == Category.JEUGD_13_17:
        if "jongens" in s:
            return "J13-17"
        if "meisjes" in s:
            return "M13-17"
    if cat == Category.SENIOREN:
        if "heren" in s:
            return "HEREN"
        if "dames" in s:
            return "DAMES"
    return SHORT_LABELS[cat]


def classify(schema: str) -> Category:
    """Bepaal de KNLTB-categorie uit de schema-omschrijving van de export."""
    s = (schema or "").lower()
    if "rood" in s:
        return Category.ROOD
    if "oranje" in s:
        return Category.ORANJE
    if "groen" in s:
        return Category.GROEN
    if "junioren" in s or "11 t/m 14" in s:
        return Category.JUNIOREN_11_14
    if "13 t/m 17" in s or "jongens" in s or "meisjes" in s:
        return Category.JEUGD_13_17
    if "gemengd" in s:
        return Category.GEMENGD
    if "heren" in s or "dames" in s or "senioren" in s:
        return Category.SENIOREN
    return Category.OVERIG
