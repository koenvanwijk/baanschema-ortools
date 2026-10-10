import csv

from baanschemaatje.knltb_import import derive_format, parse_export, to_tsv
from baanschemaatje.season import load_season_tsv


def _key(r):
    return (r["Datum"], " ".join(r["Schema"].split()), r["Team 1"], r["Team 2"], str(r["Wedstrijden"]), str(r["Wedstrijdduur"]))


def test_raw_knltb_xlsx_matches_curated_season(root):
    rows, rep = parse_export((root / "docs" / "wedstrijden_2026-2027.xlsx").read_bytes(), "w.xlsx", "MIERLO",
                             {"zondag"})
    assert rep["format"] == "ruwe KNLTB-export" and rep["imported"] == 52
    assert rep["skipped"]["uitwedstrijd"] == 116
    ref = list(csv.DictReader((root / "data" / "season_2026-2027.tsv").open(encoding="utf-8"), delimiter="\t"))
    got = {_key({k: str(v) for k, v in r.items()}) for r in rows if r["Weekdag"] == "zondag"}
    want = {_key(r) for r in ref}
    # Enige verschil: Rood/Oranje staan niet in de competitie-export.
    assert got <= want
    assert all(("rood" in k[1].lower() or "oranje" in k[1].lower()) for k in want - got)
    assert all("Aanvoerder" not in str(r) for r in rows)


def test_normalized_tsv_and_csv_roundtrip(root, tmp_path):
    data = (root / "data" / "season_2026-2027.tsv").read_bytes()
    rows, rep = parse_export(data, "s.tsv", "MIERLO")
    assert rep["format"] == "genormaliseerd" and rep["imported"] == 55
    out = tmp_path / "s.tsv"
    out.write_text(to_tsv(rows), encoding="utf-8")
    assert len(load_season_tsv(out, "MIERLO").fixtures) == 55
    csv_text = data.decode().replace("\t", ";")
    rows2, _ = parse_export(csv_text.encode(), "s.csv", "MIERLO")
    assert len(rows2) == 55


def test_weekday_filter_and_unknown_formats(root):
    rows, rep = parse_export((root / "docs" / "wedstrijden_2026-2027.xlsx").read_bytes(), "w.xlsx", "MIERLO",
                             {"zaterdag"})
    # Zaterdag: dubbelcompetities (4 partijen) en Gemengd 17+ (5 partijen) zijn nu bekend.
    assert len(rows) == 8 and rep["skipped"].get("onbekend formaat", 0) == 0
    assert all(r["Weekdag"] == "zaterdag" for r in rows)
    assert derive_format("Groen Zondag – Groen 1") == (6, 45, 4, 2, 0)
    assert derive_format("Gemengd Dubbel 35+ Zaterdag") == (4, 90, 0, 2, 2)
    assert derive_format("Dames Dubbel 17+ Vrijdag Avond – 4e klasse") == (4, 90, 0, 4, 0)
    assert derive_format("Gemengd 17+ Zaterdag  – 4e klasse") == (5, 90, 2, 2, 1)
    assert derive_format("Iets onbekends") is None


def test_oscar_export_all_weekdays_and_played(root):
    """Upload Oscar 10-10-2026: do/vr-avond, za en zo; gespeeld = uitslag."""
    from datetime import date
    data = (root / "tests" / "generiek" / "data" / "export_mierlo_20261010.xlsx").read_bytes()
    rows, rep = parse_export(data, "w.xlsx", "MIERLO", today=date(2026, 10, 10))
    assert rep["rows_in_file"] == 228 and rep["imported"] == 112
    assert rep["per_weekday"] == {"zondag": 51, "donderdag": 12, "vrijdag": 40, "zaterdag": 9}
    assert rep["skipped"] == {"uitwedstrijd": 116} and not rep["unknown_schemas"]
    assert rep["played"] == 95 and rep["open"] == 16 and len(rep["expired_no_result"]) == 1
    fri = [r for r in rows if r["Weekdag"] == "vrijdag"]
    assert all(r["Dagdeel"] == "avond" and r["Begintijd"] == "19:00" and r["Wedstrijden"] == 4 for r in fri)
    assert {r["Dagdeel"] for r in rows if r["Weekdag"] == "donderdag"} == {"avond", "ochtend"}
    # Gespeelde wedstrijd houdt zijn echte datum en uitslag.
    g = [r for r in rows if r["Status"] == "gespeeld"]
    assert all(r["Uitslag"] for r in g)
    # Round-trip via TSV behoudt status/uitslag/dagdeel.
    rows2, rep2 = parse_export(to_tsv(rows).encode(), "s.tsv", "MIERLO", today=date(2026, 10, 10))
    assert rep2["played"] == 95 and [r["Status"] for r in rows2] == [r["Status"] for r in rows]
