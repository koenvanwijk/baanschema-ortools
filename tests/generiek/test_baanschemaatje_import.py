import csv

from baanschemaatje.knltb_import import derive_format, parse_export, to_tsv
from baanschemaatje.season import load_season_tsv


def _key(r):
    return (r["Datum"], " ".join(r["Schema"].split()), r["Team 1"], r["Team 2"], str(r["Wedstrijden"]), str(r["Wedstrijdduur"]))


def test_raw_knltb_xlsx_matches_curated_season(root):
    rows, rep = parse_export((root / "docs" / "wedstrijden_2026-2027.xlsx").read_bytes(), "w.xlsx", "MIERLO")
    assert rep["format"] == "ruwe KNLTB-export" and rep["imported"] == 52
    assert rep["skipped"]["uitwedstrijd"] == 116
    ref = list(csv.DictReader((root / "data" / "season_2026-2027.tsv").open(encoding="utf-8"), delimiter="\t"))
    got = {_key({k: str(v) for k, v in r.items()}) for r in rows}
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
    # Zaterdag-thuiswedstrijden zijn dubbelcompetities zonder bekend formaat.
    assert rows == [] and rep["skipped"].get("onbekend formaat", 0) == 8
    assert derive_format("Groen Zondag – Groen 1") == (6, 45, 4, 2, 0)
    assert derive_format("Gemengd Dubbel 35+ Zaterdag") is None
