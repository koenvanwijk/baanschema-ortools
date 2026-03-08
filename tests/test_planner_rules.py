from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_PAGES = ROOT / "scripts" / "build_pages.py"
INPUT = ROOT / "data" / "season.tsv"



def _load_build_pages_module():
    spec = importlib.util.spec_from_file_location("build_pages_rules", str(BUILD_PAGES))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_pages_rules"] = mod
    spec.loader.exec_module(mod)
    return mod


def _by_date(mod):
    teams, reservations = mod.parse_input(INPUT)
    by_date = {}
    reserve_by_date = {}
    for t in teams:
        by_date.setdefault(t.date, []).append(t)
    for r in reservations:
        reserve_by_date.setdefault(r.date, []).append(r)
    return by_date, reserve_by_date


def test_cheatsheet_day_start_rule_0900_unless_needed():
    mod = _load_build_pages_module()
    by_date, reserve_by_date = _by_date(mod)

    for d, items in by_date.items():
        rows = mod.schedule_day(items, reserve_by_date.get(d, []), d)
        play = [r for r in rows if r.get("part") != "COMP" and r.get("start") not in (None, "", "NIET_GELUKT")]
        assert play, f"Geen speelbare partijen op {d}"

        first_start = min(mod.hhmm_to_mins(r["start"]) for r in play)
        if first_start >= 9 * 60:
            continue

        # Als dag toch 08:30 start, moet 09:00-variant aantoonbaar niet voldoen
        rows_0900 = mod._schedule_day_with_start(items, reserve_by_date.get(d, []), d, 9 * 60)
        play_0900 = [
            r
            for r in rows_0900
            if r.get("part") != "COMP" and r.get("start") not in (None, "", "NIET_GELUKT")
        ]
        failed_0900 = [r for r in rows_0900 if r.get("part") != "COMP" and r.get("start") == "NIET_GELUKT"]

        assert play_0900, f"09:00-variant heeft geen speelbare partijen op {d}"
        last_start_0900 = max(mod.hhmm_to_mins(r["start"]) for r in play_0900)

        assert failed_0900 or last_start_0900 > 19 * 60 + 30, (
            f"{d} start op 08:30 terwijl 09:00 ook kon (geen failures, laatste start {last_start_0900})."
        )


def test_cheatsheet_no_starts_after_1930():
    mod = _load_build_pages_module()
    by_date, reserve_by_date = _by_date(mod)

    for d, items in by_date.items():
        rows = mod.schedule_day(items, reserve_by_date.get(d, []), d)
        offenders = [
            r for r in rows if r.get("part") != "COMP" and r.get("start") not in (None, "", "NIET_GELUKT") and mod.hhmm_to_mins(r["start"]) > 19 * 60 + 30
        ]
        assert not offenders, f"Start na 19:30 op {d}: {[(r['team_short'], r['part'], r['start']) for r in offenders[:5]]}"


def test_cheatsheet_reservations_follow_daystart_and_priority():
    mod = _load_build_pages_module()
    by_date, reserve_by_date = _by_date(mod)

    for d, items in by_date.items():
        rows = mod.schedule_day(items, reserve_by_date.get(d, []), d)
        comp = [r for r in rows if r.get("part") == "COMP"]
        if not comp:
            continue

        non_comp = [r for r in rows if r.get("part") != "COMP" and r.get("start") not in (None, "", "NIET_GELUKT")]
        assert non_comp, f"Geen normale partijen op {d}"
        day_start = min(mod.hhmm_to_mins(r["start"]) for r in non_comp)

        has_rood = any((getattr(r, "kind", "") or "").lower() == "rood" for r in reserve_by_date.get(d, []))
        has_oranje = any((getattr(r, "kind", "") or "").lower() == "oranje" for r in reserve_by_date.get(d, []))

        if has_rood:
            rood = [r for r in comp if r.get("team_short") == "ROOD"]
            assert rood, f"Rood verwacht op {d}"
            assert all(r.get("court") == 1 for r in rood), f"Rood niet op baan 1 op {d}"
            assert all(mod.hhmm_to_mins(r["start"]) == day_start for r in rood), f"Rood start niet op dagstart op {d}"

        if has_oranje:
            oranje = [r for r in comp if r.get("team_short") == "ORANJE"]
            assert oranje, f"Oranje verwacht op {d}"
            courts = sorted(r.get("court") for r in oranje)
            expected = [2, 3, 4] if has_rood else [1, 2, 3]
            assert courts == expected, f"Oranje-banen fout op {d}: {courts} != {expected}"
            assert all(mod.hhmm_to_mins(r["start"]) == day_start for r in oranje), f"Oranje start niet op dagstart op {d}"
