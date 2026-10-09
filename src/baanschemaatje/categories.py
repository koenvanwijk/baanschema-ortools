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
