from baanschemaatje.categories import Category
from baanschemaatje.season import load_season_tsv


def test_season_tsv_adapter(season_path):
    s = load_season_tsv(season_path, "MIERLO")
    assert "06-09-2026" in s.dates()
    day = s.day("06-09-2026")
    cats = {f.category for f in day}
    assert Category.ORANJE in cats and Category.GROEN in cats
    oranje = next(f for f in day if f.category == Category.ORANJE)
    assert oranje.is_block and oranje.matches == 3
    groen = next(f for f in day if f.category == Category.GROEN)
    assert groen.export_duration == 45
    # Teamsleutels zijn per speeldag uniek.
    for d in s.dates():
        ks = [f.team_key for f in s.day(d)]
        assert len(ks) == len(set(ks))


def test_season_is_read_only(season_path):
    before = season_path.read_bytes()
    load_season_tsv(season_path, "MIERLO")
    assert season_path.read_bytes() == before
