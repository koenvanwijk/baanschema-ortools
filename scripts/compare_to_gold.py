#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


def hhmm_to_min(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def union_len(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    iv = sorted(intervals)
    s, e = iv[0]
    total = 0
    for a, b in iv[1:]:
        if a <= e:
            e = max(e, b)
        else:
            total += e - s
            s, e = a, b
    total += e - s
    return total


def normalize_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        s = r.get("start")
        e = r.get("end")
        if not s or s == "NIET_GELUKT":
            continue
        out.append(
            {
                "team_short": (r.get("team_short") or r.get("team") or r.get("schema") or "").strip(),
                "part": r.get("part", ""),
                "kind": r.get("kind", ""),
                "start": s,
                "end": e,
                "court": r.get("court"),
            }
        )
    return out


def metrics(rows: list[dict]) -> dict:
    by_team: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for r in rows:
        t = r["team_short"]
        if not t or t in {"ROOD", "ORANJE"}:
            continue
        by_team[t].append((hhmm_to_min(r["start"]), hhmm_to_min(r["end"])))

    spans, gaps, blocks = [], [], []
    for t, arr in by_team.items():
        s = min(a for a, _ in arr)
        e = max(b for _, b in arr)
        active = union_len(arr)
        spans.append(e - s)
        gaps.append((e - s) - active)

        iv = sorted(arr)
        bcnt = 1
        cur_e = iv[0][1]
        for a, b in iv[1:]:
            if a > cur_e:
                bcnt += 1
                cur_e = b
            else:
                cur_e = max(cur_e, b)
        blocks.append(bcnt)

    if not spans:
        return {"teams": 0, "avg_span": 0.0, "avg_gap": 0.0, "avg_blocks": 0.0}

    return {
        "teams": len(by_team),
        "avg_span": round(mean(spans), 1),
        "avg_gap": round(mean(gaps), 1),
        "avg_blocks": round(mean(blocks), 2),
    }


def score(m: dict) -> float:
    # Lower is better.
    return m["avg_span"] + 3.0 * m["avg_gap"] + 20.0 * (m["avg_blocks"] - 1.0)


def load_by_date(path: Path) -> dict[str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data
    raise ValueError(f"Unsupported JSON format in {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare planner outputs to manual gold schedule")
    ap.add_argument("--gold", type=Path, required=True, help="gold_result.json from parse_gold_xlsx.py")
    ap.add_argument("--heur", type=Path, default=Path("docs/result.json"))
    ap.add_argument("--ortools-dir", type=Path, default=Path("docs"))
    ap.add_argument("--out", type=Path, default=Path("docs/gold_compare.json"))
    args = ap.parse_args()

    gold = load_by_date(args.gold)
    heur = load_by_date(args.heur)

    report = {"dates": {}, "summary": {}}

    heur_scores, or_scores = [], []

    for d, gold_rows in sorted(gold.items()):
        g_norm = normalize_rows(gold_rows)
        h_norm = normalize_rows(heur.get(d, []))

        ort_path = args.ortools_dir / f"ortools_{d}.json"
        o_rows = []
        if ort_path.exists():
            o_data = load_by_date(ort_path)
            o_rows = o_data.get("rows") or o_data.get(d, [])
        o_norm = normalize_rows(o_rows)

        g_m = metrics(g_norm)
        h_m = metrics(h_norm)
        o_m = metrics(o_norm)

        h_s = round(score(h_m), 2)
        o_s = round(score(o_m), 2)
        heur_scores.append(h_s)
        or_scores.append(o_s)

        report["dates"][d] = {
            "gold": g_m,
            "heuristic": {**h_m, "score": h_s, "delta_vs_gold": round(h_s - score(g_m), 2)},
            "ortools": {**o_m, "score": o_s, "delta_vs_gold": round(o_s - score(g_m), 2)},
            "winner": "heuristic" if h_s <= o_s else "ortools",
        }

    report["summary"] = {
        "heuristic_avg_score": round(mean(heur_scores), 2) if heur_scores else 0,
        "ortools_avg_score": round(mean(or_scores), 2) if or_scores else 0,
        "overall_winner": "heuristic" if (mean(heur_scores) if heur_scores else 1e9) <= (mean(or_scores) if or_scores else 1e9) else "ortools",
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {args.out}")
    print("Summary:", report["summary"])


if __name__ == "__main__":
    main()
