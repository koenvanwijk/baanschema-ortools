"""Pure planningsregels: partijopbouw en spelersbehoefte per schema.

Staat los van elke solver, zodat zowel de planners als de validator
(`scripts/validate_schedule.py`) dezelfde definitie gebruiken. Zonder deze
module zou de validator de regels moeten nabouwen en kan hij meegroeien met een
fout in de planner in plaats van hem te vinden.

Verwacht van een team-object alleen de attributen `schema`, `matches`,
`singles`, `doubles` en `mix`.
"""

from __future__ import annotations

from typing import Protocol


class TeamLike(Protocol):
    schema: str
    matches: int
    singles: int
    doubles: int
    mix: int


def build_parts(team: TeamLike) -> list[tuple[str, str]]:
    """Partijen van een teamdag als (label, soort).

    Soorten: S = single, D = dubbel, M = gemengd dubbel, W = onbekend
    (vulling wanneer season.tsv meer wedstrijden noemt dan S/D/GD samen).
    """
    parts: list[tuple[str, str]] = []
    parts += [(f"S{i+1}", "S") for i in range(team.singles)]
    parts += [(f"D{i+1}", "D") for i in range(team.doubles)]
    parts += [(f"GD{i+1}", "M") for i in range(team.mix)]
    while len(parts) < team.matches:
        parts.append((f"W{len(parts)+1}", "W"))
    return parts[: team.matches]


def player_demand(schema: str, label: str, kind: str) -> tuple[int, int, int]:
    """Spelersbehoefte van één partij als (heren, dames, totaal).

    Voor niet-gemengde teams tellen we alleen het totaal; de samenstelling doet
    er niet toe. Voor gemengde teams houden we heren en dames apart bij, omdat
    zo'n team uit 2 heren en 2 dames bestaat.
    """
    s = (schema or "").lower()
    is_mixed = "gemengd zondag" in s

    if not is_mixed:
        if kind == "S":
            return (0, 0, 1)
        if kind in {"D", "M"}:
            return (0, 0, 2)
        return (0, 0, 0)

    # Gemengd dubbel is altijd 1 heer + 1 dame.
    if label.startswith("GD") or kind == "M":
        return (1, 1, 2)

    if label.startswith("S"):
        idx = int(label[1:]) if label[1:].isdigit() else 1
        if "2de-2he" in s:
            # afspraak: S1,S2 = dames enkel; S3,S4 = heren enkel
            return (0, 1, 1) if idx <= 2 else (1, 0, 1)
        if "de-he" in s:
            # afspraak: S1 = dames enkel; S2 = heren enkel
            return (0, 1, 1) if idx == 1 else (1, 0, 1)
        return (0, 0, 1)

    if label.startswith("D") or kind == "D":
        idx = int(label[1:]) if label[1:].isdigit() else 1
        if "dd-hd" in s:
            # afspraak: D1 = damesdubbel, D2 = herendubbel
            return (0, 2, 2) if idx == 1 else (2, 0, 2)
        return (0, 0, 2)

    return (0, 0, 0)
