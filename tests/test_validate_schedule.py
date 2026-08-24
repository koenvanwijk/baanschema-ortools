"""Tests voor de schemavalidator.

De validator is het vangnet onder elke modelwijziging, dus hij moet zelf
aantoonbaar overtredingen vinden én een correct schema goedkeuren.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def _load():
    spec = importlib.util.spec_from_file_location(
        "validate_schedule", str(ROOT / "scripts" / "validate_schedule.py")
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # dataclasses zoeken hun eigen module op in sys.modules, dus registreren
    # vóór exec_module.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


V = _load()

DATE = "06-04-2026"


def _rules(findings):
    return {f.rule for f in findings}


def _report_for(rows):
    rep = V.Report()
    V.validate_date(DATE, rows, rep)
    return rep


def _gold_rows():
    import json

    data = json.loads((ROOT / "docs" / "gold_result.json").read_text(encoding="utf-8"))
    return data[DATE]


# --------------------------------------------------------------------------- #
# hulpfuncties
# --------------------------------------------------------------------------- #

def test_hhmm_to_min_leest_tijden_en_niet_gelukt():
    assert V.hhmm_to_min("09:15") == 555
    assert V.hhmm_to_min("NIET_GELUKT") is None
    assert V.hhmm_to_min("") is None
    assert V.hhmm_to_min("kwart over negen") is None


def test_merge_slots_vouwt_aaneengesloten_slots_samen():
    assert V.merge_slots([540, 555, 570]) == "09:00-09:45"
    assert V.merge_slots([540, 570]) == "09:00-09:15, 09:30-09:45"
    assert V.merge_slots([]) == ""


# --------------------------------------------------------------------------- #
# het gold-schema is de referentie
# --------------------------------------------------------------------------- #

# Regels waar het handmatige schema van 06-04 aantoonbaar niet aan voldoet.
# Dit zijn allebei nieuwe eisen uit SPEC.md (24-08-2026); vóór die spec was het
# schema schoon. Zolang deze set niet leeg is, is de spec strenger dan de
# menselijke referentie — een besluit voor Oscar, niet iets om weg te poetsen.
GOLD_BREEKT = {"FASE", "EERSTE-START"}


def test_gold_schema_haalt_alle_harde_regels_op_twee_na():
    """Het handmatige schema van 06-04 moet de harde regels halen.

    Uitzondering: de twee regels in GOLD_BREEKT. Wijkt het schema op iets ánders
    af, dan klopt de validator of season.tsv niet — niet het schema.
    """
    rep = _report_for(_gold_rows())
    onverwacht = [f for f in rep.hard if f.rule not in GOLD_BREEKT]
    assert not onverwacht, "\n".join(f.line() for f in onverwacht)


def test_gold_schema_breekt_de_nieuwe_spec_regels():
    """Vastgelegd: de nieuwe spec is strenger dan het handmatige schema.

    Het 8-partijenteam start om 11:15 (spec sectie 2 wil 10:00-11:00) en zet zijn
    gemengd dubbel neer voordat de dubbels klaar zijn (spec sectie 5, strikte
    waterval). Zie de vragen in Discord #baanschema van 24-08-2026.
    """
    rep = _report_for(_gold_rows())
    gebroken = {f.rule for f in rep.hard}
    assert gebroken == GOLD_BREEKT, f"verwacht {GOLD_BREEKT}, kreeg {gebroken}"


def test_gold_schema_breekt_de_jeugdvensterregel_van_het_model():  # noqa: E302
    """Vastgelegd gedrag: de harde 11:00-grens voor jeugd 13-17 is strenger dan
    het handmatige schema. Zie docs/REFACTOR_PLAN.md, observatie 3."""
    rep = _report_for(_gold_rows())
    assert "VENSTER-JEUGD" in _rules(rep.by_severity("MODEL"))


# --------------------------------------------------------------------------- #
# vindt de validator wat hij moet vinden?
# --------------------------------------------------------------------------- #

def test_baanoverlap_wordt_gevonden():
    rows = _gold_rows()
    victim = next(r for r in rows if r["kind"] == "S")
    clash = {**victim, "part": "S9", "court": victim["court"]}
    rep = _report_for(rows + [clash])
    assert "BAAN-OVERLAP" in _rules(rep.by_severity("HARD"))


def test_start_na_halfacht_wordt_gevonden():
    rows = _gold_rows()
    late = {**rows[0], "start": "19:45", "end": "21:15", "court": 9}
    rep = _report_for([late] + rows[1:])
    assert "LAATSTE-START" in _rules(rep.by_severity("HARD"))


def test_niet_bestaande_baan_wordt_gevonden():
    rows = _gold_rows()
    bad = {**rows[0], "court": 11}
    rep = _report_for([bad] + rows[1:])
    assert "BAAN" in _rules(rep.by_severity("HARD"))


def test_tijd_buiten_kwartierraster_wordt_gevonden():
    rows = _gold_rows()
    off = {**rows[0], "start": "09:07", "end": "10:37"}
    rep = _report_for([off] + rows[1:])
    assert "RASTER" in _rules(rep.by_severity("HARD"))


def test_ontbrekende_partij_wordt_gevonden():
    rows = _gold_rows()
    rep = _report_for([r for r in rows if r.get("part") != "S1"])
    hard = rep.by_severity("HARD")
    assert "NIET-GEPLAND" in _rules(hard)


def test_niet_gelukt_telt_als_niet_gepland():
    rows = _gold_rows()
    victim = next(r for r in rows if r["kind"] == "S")
    patched = [
        {**r, "start": "NIET_GELUKT", "end": "NIET_GELUKT"}
        if r is victim else r
        for r in rows
    ]
    rep = _report_for(patched)
    findings = [f for f in rep.by_severity("HARD") if f.rule == "NIET-GEPLAND"]
    assert findings, "een NIET_GELUKT-rij moet als niet-gepland gemeld worden"


def test_dubbel_geplande_partij_wordt_gevonden():
    rows = _gold_rows()
    victim = next(r for r in rows if r["kind"] == "S")
    twin = {**victim, "court": 9, "start": "18:00", "end": "19:30"}
    rep = _report_for(rows + [twin])
    assert "DUBBEL-GEPLAND" in _rules(rep.by_severity("HARD"))


def test_verkeerde_wedstrijdduur_wordt_gevonden():
    rows = _gold_rows()
    victim = next(r for r in rows if r["kind"] == "S")
    short = {**victim, "end": V.to_hhmm(V.hhmm_to_min(victim["start"]) + 15)}
    rep = _report_for([short if r is victim else r for r in rows])
    assert "DUUR" in _rules(rep.by_severity("HARD"))


def test_onbekende_datum_wordt_gemeld():
    rep = V.Report()
    V.validate_date("01-01-1999", [], rep)
    assert "ONBEKENDE-DATUM" in _rules(rep.by_severity("HARD"))


# --------------------------------------------------------------------------- #
# bestandsformaten
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "name",
    ["gold_result.json", "result.json", f"ortools_{DATE}.json"],
)
def test_alle_drie_de_uitvoerformaten_zijn_leesbaar(name):
    path = ROOT / "docs" / name
    if not path.exists():
        pytest.skip(f"{name} niet aanwezig")
    per_date = V.load_rows(path)
    assert per_date, f"geen datums gevonden in {name}"
    for date, rows in per_date.items():
        assert isinstance(rows, list)
        if rows:
            assert V.row_team_key(rows[0]) != "?", f"team niet herkend in {name}"
