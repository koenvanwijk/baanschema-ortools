"""Teambezetting per partij: spelersbehoefte (heren/dames/totaal) en partijsoort (HE/DE/HD/DD/GD).

Bouwt voort op `baanschema.rules.player_demand` (die blijft ongewijzigd, ook voor de bestaande stack en de
validator) en vult de KNLTB-dubbelcompetities aan die daar ontbreken (besluit Oscar 17-10-2026):
- Gemengd Dubbel (avond) = DD-HD-2GD: D1 = damesdubbel, D2 = herendubbel, GD = 1 heer + 1 dame.
- Gemengd 17+/35+ zaterdag = DE-HE-GD-DD-HD: S1 = damesenkel, S2 = herenenkel.
Zo kunnen bv. een DD en een GD van hetzelfde gemengde team niet tegelijk (beide hebben de 2 dames nodig).
Gebruikt door de planner (hard), herplannen en de bingo-avond (wachtrij/blokkades).
"""

from __future__ import annotations

from typing import Any

from baanschema.rules import player_demand


def _num(label: str) -> int:
    d = "".join(ch for ch in label if ch.isdigit())
    return int(d) if d else 1


def team_demand(schema: str, label: str, kind: str) -> tuple[int, int, int]:
    """(heren, dames, totaal) voor één partij."""
    s = " ".join((schema or "").lower().split())
    if "gemengd" in s and "gemengd zondag" not in s:
        if label.startswith("GD") or kind == "M":
            return (1, 1, 2)
        if kind == "D":
            return (0, 2, 2) if _num(label) == 1 else (2, 0, 2)
        if kind == "S":
            return (0, 1, 1) if _num(label) == 1 else (1, 0, 1)
    return player_demand(schema, label, kind)


def part_type(schema: str, label: str, kind: str) -> str:
    """Partijsoort zoals op het wedstrijdformulier: HE/DE/HD/DD/GD (jeugd: JE/ME/JD/MD); anders Enkel/Dubbel."""
    if kind == "M" or label.startswith("GD"):
        return "GD"
    m, w, _ = team_demand(schema, label, kind)
    s = (schema or "").lower()
    if kind == "S":
        if w and not m:
            return "DE"
        if m and not w:
            return "HE"
    if kind == "D":
        if w and not m:
            return "DD"
        if m and not w:
            return "HD"
    pre = {"S": "E", "D": "D"}.get(kind)
    if not pre:
        return label
    for word, code in (("dames", "D"), ("heren", "H"), ("meisjes", "M"), ("jongens", "J")):
        if s.startswith(word):
            return code + pre
    return "Enkel" if kind == "S" else "Dubbel"


def team_order_rules(f: Any, waterfall_8p_hard: bool) -> dict[str, bool]:
    """Volgorderegels van de planner (hard): niet-gemengd (of 8p strikt) enkels vóór dubbels; 8p ook D vóór GD."""
    strict_8p = bool(f.is_8p and waterfall_8p_hard)
    return {"mixed": bool(f.is_mixed), "singles_first": (not f.is_mixed) or strict_8p, "doubles_before_mixed": strict_8p}
