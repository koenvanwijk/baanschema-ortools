#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from statistics import mean

import ortools_planner
from compare_to_gold import normalize_rows, metrics, score


def load_gold(path: Path) -> dict[str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data
    raise ValueError("gold_result.json must be dict")


def evaluate_weights(dates: list[str], gold: dict[str, list[dict]], teams, res, weights: dict, time_limit: float) -> dict:
    deltas = []
    for d in dates:
        g_norm = normalize_rows(gold.get(d, []))
        g_score = score(metrics(g_norm))
        result = ortools_planner.solve_day(
            d,
            teams,
            res,
            time_limit_s=time_limit,
            **weights,
        )
        o_norm = normalize_rows(result.get("rows", []))
        o_score = score(metrics(o_norm))
        deltas.append(o_score - g_score)
    return {
        "avg_delta": round(mean(deltas), 2) if deltas else 0,
        "max_delta": round(max(deltas), 2) if deltas else 0,
        "min_delta": round(min(deltas), 2) if deltas else 0,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Tune OR-Tools weights against gold schedule")
    ap.add_argument("--gold", type=Path, default=Path("docs/gold_result.json"))
    ap.add_argument("--trials", type=int, default=12)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--time-limit", type=float, default=5.0)
    ap.add_argument("--out", type=Path, default=Path("docs/ortools_tuning.json"))
    args = ap.parse_args()

    gold = load_gold(args.gold)
    dates = sorted(gold.keys())

    teams, res = ortools_planner.parse_input(ortools_planner.INPUT)

    random.seed(args.seed)

    base = {
        "w_block_rise": 2_000_000,
        "w_long_gap": 10_000_000,
        "w_morning_occ": 600_000,
        "w_total_occ": 80_000,
        "w_cutoff_bonus": 5_000,
        "w_early_start": 100,
        "w_late_start": 120_000,
        "w_youth_late": 80_000,
        "w_team_court_penalty": 200_000,
        "w_high_court_penalty": 40_000,
    }

    ranges = {
        "w_block_rise": [1_000_000, 2_000_000, 4_000_000],
        "w_long_gap": [5_000_000, 10_000_000, 20_000_000],
        "w_team_court_penalty": [150_000, 200_000, 300_000],
        "w_high_court_penalty": [20_000, 40_000, 80_000],
    }

    trials = []
    for _ in range(args.trials):
        w = base.copy()
        for k, opts in ranges.items():
            w[k] = random.choice(opts)
        trials.append(w)

    best = None
    results = []
    for w in trials:
        stats = evaluate_weights(dates, gold, teams, res, w, args.time_limit)
        entry = {"weights": w, **stats}
        results.append(entry)
        if best is None or stats["avg_delta"] < best["avg_delta"]:
            best = entry

    report = {
        "trials": results,
        "best": best,
        "dates": dates,
        "time_limit_s": args.time_limit,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.out}")
    if best:
        print("Best avg_delta:", best["avg_delta"], "weights:", best["weights"])


if __name__ == "__main__":
    main()
