"""Catalogus van KNLTB-bronnen voor de regelbank (rangorde: lager = zwaarder)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

BASE = "https://www.tennis.nl"
FAQ_URL = BASE + "/alles-over-tennis/competitie/veelgestelde-vragen/"

# stem -> (titel, korte label-prefix, rang, soort)
# rang: 1 Competitiereglement, 2 Wedstrijdbulletin, 3 FAQ, 4 uitleg/overig.
PDF_BRONNEN: dict[str, tuple[str, str, int, str]] = {
    "knltb-competitiereglement-tennis": ("KNLTB Competitiereglement Tennis", "CR", 1, "cr"),
    "wedstrijdbulletin-2026-knltb-tennis": ("Wedstrijdbulletin 2026 KNLTB Competitie Tennis", "Wedstrijdbulletin 2026", 2, "bulletin"),
    "stroomschema-wat-te-doen-als-wij-niet-kunnen-spelen": ("Stroomschema 'Wat te doen als wij niet kunnen spelen?'", "Stroomschema niet kunnen spelen", 4, "pagina"),
    "uitleg-invallen-in-ander-team": ("Uitleg invallen in een ander team", "Uitleg invallen", 4, "pagina"),
    "competitie-spelen-in-twee-of-meer-teams": ("Competitie spelen in twee of meer teams", "Spelen in meerdere teams", 4, "pagina"),
    "regels-spelen-op-tijd": ("Regels spelen op tijd", "Regels spelen op tijd", 4, "pagina"),
    "begintijden-competitie": ("Begintijden competitie", "Begintijden competitie", 4, "pagina"),
    "telling-jeugd": ("Telling jeugd", "Telling jeugd", 4, "pagina"),
    "spelregels-junioren": ("Spelregels junioren", "Spelregels junioren", 4, "pagina"),
    "uitleg-promotie-degradatie-tenniscompetitie": ("Uitleg promotie/degradatie tenniscompetitie", "Uitleg promotie/degradatie", 4, "pagina"),
    "leeftijden-2026": ("Leeftijden 2026", "Leeftijden 2026", 4, "pagina"),
    "speeldata-knltb-najaarscompetitie-tennis-2026": ("Speeldata KNLTB najaarscompetitie 2026", "Speeldata najaar 2026", 4, "pagina"),
    "speeldata-knltb-alle-competities-senioren-tennis-2026": ("Speeldata alle competities senioren 2026", "Speeldata senioren 2026", 4, "pagina"),
    "speeldata-knltb-wintercompetitie-tennis-20262027": ("Speeldata wintercompetitie 2026-2027", "Speeldata winter 2026-2027", 4, "pagina"),
    "speeldata-knltb-voorjaarscompetitie-tenniskids-2026": ("Speeldata voorjaarscompetitie Tenniskids 2026", "Speeldata Tenniskids 2026", 4, "pagina"),
    "aanbod-knltb-najaarscompetitie-senioren-regionaal": ("Aanbod najaarscompetitie senioren regionaal", "Aanbod najaar senioren regionaal", 4, "pagina"),
    "aanbod-knltb-najaarscompetitie-senioren-landelijk": ("Aanbod najaarscompetitie senioren landelijk", "Aanbod najaar senioren landelijk", 4, "pagina"),
    "aanbod-knltb-voorjaar-najaarscompetitie-jeugd": ("Aanbod voorjaar/najaarscompetitie jeugd", "Aanbod jeugd", 4, "pagina"),
    "aanbod-wintercompetitie-jeugd-en-senioren": ("Aanbod wintercompetitie", "Aanbod winter", 4, "pagina"),
    "tips-8-9-tennis": ("Tips 8&9 tennis", "Tips 8&9 tennis", 4, "pagina"),
    "knltb-tennisspelregels": ("KNLTB Tennisspelregels", "Tennisspelregels", 4, "pagina"),
    "knltb-reglement-fair-play": ("KNLTB Reglement Fair Play", "Reglement Fair Play", 4, "pagina"),
    "reglement-begripsbepalingen-knltb": ("KNLTB Reglement Begripsbepalingen", "Begripsbepalingen", 4, "pagina"),
    "knltb-algemeen-reglement": ("KNLTB Algemeen Reglement", "Algemeen Reglement", 4, "pagina"),
}

RANG_NAAM = {1: "Competitiereglement", 2: "Wedstrijdbulletin", 3: "Veelgestelde vragen", 4: "Uitleg/overig"}


def ticks_naar_datum(ts: str | int | None) -> str | None:
    """.NET-ticks (``?ts=`` op tennis.nl) -> ISO-datum (UTC)."""
    try:
        t = int(ts)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    d = datetime(1, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=t // 10)
    return d.date().isoformat()
