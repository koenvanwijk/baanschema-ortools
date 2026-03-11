from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARSE = ROOT / "scripts" / "parse_gold_xlsx.py"
COMPARE = ROOT / "scripts" / "compare_to_gold.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_gold_xlsx_smoke_on_real_file():
    mod = _load(PARSE, "parse_gold")
    xlsx = Path("/home/kwijk/.openclaw/media/inbound/a8eabae3-2359-44dd-9985-4e9beec59078.xlsx")
    if not xlsx.exists():
        # CI/sandbox may not have inbound attachment.
        return

    gold = mod.parse_gold_xlsx(xlsx)
    assert "06-04-2026" in gold
    assert gold["06-04-2026"], "Gold parser should extract matches for 06-04-2026"
    sample = gold["06-04-2026"][0]
    assert "team_short" in sample and "start" in sample and "end" in sample


def test_compare_metrics_prefers_lower_span_gap_blocks():
    mod = _load(COMPARE, "compare_gold")

    # Gold: compact single block
    gold_rows = [
        {"team_short": "T1", "start": "10:00", "end": "11:30", "court": 1, "kind": "D", "part": "D1"},
        {"team_short": "T1", "start": "11:30", "end": "13:00", "court": 2, "kind": "S", "part": "S1"},
    ]
    # Worse: two blocks + bigger span
    bad_rows = [
        {"team_short": "T1", "start": "10:00", "end": "11:30", "court": 1, "kind": "D", "part": "D1"},
        {"team_short": "T1", "start": "14:00", "end": "15:30", "court": 2, "kind": "S", "part": "S1"},
    ]

    g = mod.metrics(mod.normalize_rows(gold_rows))
    b = mod.metrics(mod.normalize_rows(bad_rows))

    assert mod.score(g) < mod.score(b)


def test_compare_script_output_json(tmp_path: Path):
    mod = _load(COMPARE, "compare_gold2")

    gold = {
        "06-04-2026": [
            {"team_short": "T1", "start": "10:00", "end": "11:30", "court": 1, "kind": "D", "part": "D1"}
        ]
    }
    heur = {
        "06-04-2026": [
            {"team_short": "T1", "start": "10:00", "end": "11:30", "court": 1, "kind": "D", "part": "D1"}
        ]
    }
    ort = {
        "06-04-2026": [
            {"team_short": "T1", "start": "12:00", "end": "13:30", "court": 1, "kind": "D", "part": "D1"}
        ]
    }

    gold_p = tmp_path / "gold.json"
    heur_p = tmp_path / "heur.json"
    ort_p = tmp_path / "ortools_06-04-2026.json"
    out_p = tmp_path / "report.json"

    gold_p.write_text(json.dumps(gold), encoding="utf-8")
    heur_p.write_text(json.dumps(heur), encoding="utf-8")
    ort_p.write_text(json.dumps(ort), encoding="utf-8")

    # direct function-level test by emulating script internals
    gold_d = mod.load_by_date(gold_p)
    heur_d = mod.load_by_date(heur_p)
    ort_d = mod.load_by_date(ort_p)

    assert "06-04-2026" in gold_d and "06-04-2026" in heur_d and "06-04-2026" in ort_d
