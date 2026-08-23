"""Tests for the Mierlo 2026-2027 Sunday planning: xlsx parser + the two known
planner bugfixes (unique team keys, non-overlap over all timeslots)."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import parse_wedstrijden_xlsx as pw  # noqa: E402
from ortools_planner import TeamDay, solve_day  # noqa: E402
from validate_schedule import validate_day, hhmm_to_min  # noqa: E402

XLSX = ROOT / "docs" / "wedstrijden_2026-2027.xlsx"


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def test_derive_format_known_schemas():
    assert pw.derive_format("Gemengd Zondag – 1e klasse (2DE-2HE-DD-HD-2GD) – Afdeling 1") == (8, 90, 4, 2, 2)
    assert pw.derive_format("Gemengd Zondag – 5e klasse (DE-HE-GD-DD-HD) – Afdeling 7") == (5, 90, 2, 2, 1)
    assert pw.derive_format("Jongens 13 t/m 17 jaar Zondag – 1e klasse – Afdeling 12") == (6, 90, 4, 2, 0)
    assert pw.derive_format("Meisjes 13 t/m 17 jaar Zondag – Hoofdklasse – Afdeling 2") == (6, 90, 4, 2, 0)
    assert pw.derive_format("Junioren 11 t/m 14 jaar Zondag – 3e klasse – Afdeling 22") == (6, 45, 4, 2, 0)
    assert pw.derive_format("Groen Zondag – Groen 1 – Afdeling 36") == (6, 45, 4, 2, 0)
    assert pw.derive_format("Heren Zondag – 4e klasse – Afdeling 4") == (6, 90, 4, 2, 0)


def test_is_home_sunday_filter():
    # Sunday (weekday 6), Team 1 = MIERLO, Zondag schema -> home match.
    assert pw.is_home_sunday("Groen Zondag – Groen 1", "MIERLO 1", 6) is True
    # Away: Mierlo is Team 2.
    assert pw.is_home_sunday("Groen Zondag – Groen 1", "CAROLUS 1", 6) is False
    # Not a Sunday.
    assert pw.is_home_sunday("Groen Zondag – Groen 1", "MIERLO 1", 4) is False


def test_parse_only_home_sundays():
    if not XLSX.exists():
        return
    recs = pw.parse(XLSX)
    assert recs, "expected home-Sunday matches"
    for r in recs:
        assert r["Weekdag"] == "zondag"
        assert r["Team 1"].upper().startswith("MIERLO")
        assert "zondag" in r["Schema"].lower()
    counts = defaultdict(int)
    for r in recs:
        counts[r["Datum"]] += 1
    # The six home Sundays discovered in the export.
    assert counts["06-09-2026"] == 8
    assert counts["27-09-2026"] == 11
    assert len(counts) == 6


# --------------------------------------------------------------------------- #
# Bug #1: two teams with the SAME schema on one day must stay separate
# --------------------------------------------------------------------------- #
def _meisjes(home: str) -> TeamDay:
    schema = "Meisjes 13 t/m 17 jaar Zondag – 3e klasse – Afdeling 2"
    return TeamDay(
        date="01-01-2026", schema=schema, matches=6, duration_min=90,
        singles=4, doubles=2, mix=0,
        team_key=f"{schema} · {home}", home_team=home, away_team="OPP",
    )


def test_bug1_same_schema_different_home_not_merged():
    teams = [_meisjes("MIERLO 4"), _meisjes("MIERLO 5")]
    res = solve_day("01-01-2026", teams, [], time_limit_s=20.0)
    assert res["status"] in {"OPTIMAL", "FEASIBLE"}
    placed = [r for r in res["rows"] if r.get("start") != "NIET_GELUKT"]
    # Both teams must be present as DISTINCT identities, each with all 6 parts.
    by_id = defaultdict(list)
    for r in placed:
        by_id[r["team_id"]].append(r)
    assert len(by_id) == 2, f"expected 2 distinct teams, got {list(by_id)}"
    for tid, rr in by_id.items():
        assert len(rr) == 6, f"team {tid} scheduled {len(rr)} parts, expected 6"
    # And each team independently respects the max-2-concurrent-parts / 4-players rule.
    rep = validate_day("01-01-2026", teams, res["rows"])
    assert rep.hard == [], f"unexpected HARD violations: {rep.hard}"


# --------------------------------------------------------------------------- #
# Bug #2: S/D, D/GD, S/GD non-overlap must hold over ALL timeslots
# --------------------------------------------------------------------------- #
def _combo_mixed(home: str) -> TeamDay:
    # 2DE-2HE-DD-HD-2GD mixed team: S and GD may NOT overlap, D and GD may NOT overlap.
    schema = "Gemengd Zondag – 1e klasse (2DE-2HE-DD-HD-2GD) – Afdeling 1"
    return TeamDay(
        date="02-02-2026", schema=schema, matches=8, duration_min=90,
        singles=4, doubles=2, mix=2,
        team_key=f"{schema} · {home}", home_team=home, away_team="OPP",
    )


def test_bug2_no_overlap_across_all_timeslots_combo():
    teams = [_combo_mixed("MIERLO 1")]
    res = solve_day("02-02-2026", teams, [], time_limit_s=30.0)
    assert res["status"] in {"OPTIMAL", "FEASIBLE"}
    placed = [r for r in res["rows"] if r.get("start") != "NIET_GELUKT"]
    assert len(placed) == 8, f"expected 8 scheduled parts, got {len(placed)}"

    # Explicit all-timeslots check (independent of the validator).
    for t in range(8 * 60 + 30, 20 * 60, 15):
        kinds = {
            r["kind"]
            for r in placed
            if hhmm_to_min(r["start"]) <= t < hhmm_to_min(r["end"])
        }
        assert not ("S" in kinds and "D" in kinds), f"S+D overlap at {t}"
        assert not ("D" in kinds and "M" in kinds), f"D+GD overlap at {t}"
        assert not ("S" in kinds and "M" in kinds), f"S+GD overlap (combo) at {t}"

    rep = validate_day("02-02-2026", teams, res["rows"])
    assert rep.hard == [], f"unexpected HARD violations: {rep.hard}"


def test_bug2_doubles_mix_non_overlap_five_klasse():
    # DE-HE-GD-DD-HD: D and GD may not overlap; S and GD MAY overlap.
    schema = "Gemengd Zondag – 5e klasse (DE-HE-GD-DD-HD) – Afdeling 7"
    team = TeamDay(
        date="03-03-2026", schema=schema, matches=5, duration_min=90,
        singles=2, doubles=2, mix=1,
        team_key=f"{schema} · MIERLO 4", home_team="MIERLO 4", away_team="OPP",
    )
    res = solve_day("03-03-2026", [team], [], time_limit_s=20.0)
    assert res["status"] in {"OPTIMAL", "FEASIBLE"}
    placed = [r for r in res["rows"] if r.get("start") != "NIET_GELUKT"]
    assert len(placed) == 5
    for t in range(8 * 60 + 30, 20 * 60, 15):
        kinds = {r["kind"] for r in placed if hhmm_to_min(r["start"]) <= t < hhmm_to_min(r["end"])}
        assert not ("D" in kinds and "M" in kinds), f"D+GD overlap at {t}"
