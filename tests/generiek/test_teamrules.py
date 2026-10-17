"""Teambezetting per partij (besluit Oscar 17-10-2026): DD/HD/GD bij gemengde dubbelcompetities."""
from baanschemaatje.teamrules import part_type, team_demand


def test_gemengd_dubbel_dd_hd_gd():
    s = "Gemengd Dubbel 17+ Vrijdag Avond – 4e klasse"
    assert [part_type(s, l, k) for l, k in (("D1", "D"), ("D2", "D"), ("GD1", "M"))] == ["DD", "HD", "GD"]
    assert team_demand(s, "D1", "D") == (0, 2, 2) and team_demand(s, "GD2", "M") == (1, 1, 2)


def test_overige_soorten_en_bestaande_regels_ongewijzigd():
    assert part_type("Heren 17+ Vrijdag Avond", "S1", "S") == "HE"
    assert part_type("Dames Dubbel 35+ Vrijdag Avond", "D3", "D") == "DD"
    z = "Gemengd zondag 2DE-2HE-DD-HD-2GD"
    assert [part_type(z, l, k) for l, k in (("S1", "S"), ("S3", "S"), ("D2", "D"))] == ["DE", "HE", "HD"]
    assert team_demand("Junioren 11 t/m 14 jaar", "S1", "S") == (0, 0, 1)
