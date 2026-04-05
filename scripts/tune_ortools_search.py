#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from statistics import mean

import ortools_planner
from compare_to_gold import normalize_rows, metrics, score


def load_gold(path: Path) -> dict[str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data
    raise ValueError("gold_result.json must be dict")


def evaluate_weights(dates, gold, teams, res, weights, time_limit):
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


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def main() -> None:
    ap = argparse.ArgumentParser(description="Iterative OR-Tools weight search vs Gold")
    ap.add_argument("--gold", type=Path, default=Path("docs/gold_result.json"))
    ap.add_argument("--time-limit", type=float, default=4.0)
    ap.add_argument("--seconds", type=int, default=3600)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path("docs/ortools_tuning_search.json"))
    args = ap.parse_args()

    random.seed(args.seed)
    gold = load_gold(args.gold)
    dates = sorted(gold.keys())
    teams, res = ortools_planner.parse_input(ortools_planner.INPUT)

    base = {
        "w_block_rise": 4_000_000,
        "w_long_gap": 5_000_000,
        "w_morning_occ": 600_000,
        "w_total_occ": 80_000,
        "w_cutoff_bonus": 5_000,
        "w_early_start": 100,
        "w_late_start": 120_000,
        "w_youth_late": 80_000,
        "w_team_court_penalty": 150_000,
        "w_high_court_penalty": 80_000,
        "w_team_span": 200_000,
    }

    bounds = {
        "w_block_rise": (500_000, 8_000_000),
        "w_long_gap": (1_000_000, 25_000_000),
        "w_team_court_penalty": (50_000, 500_000),
        "w_high_court_penalty": (10_000, 200_000),
        "w_team_span": (50_000, 800_000),
    }

    best = None
    history = []

    start = time.time()
    iter_no = 0
    phase = 0
    progress_path = args.out.with_suffix(".progress.json")
    last_flush = 0
    while time.time() - start < args.seconds:
        iter_no += 1
        # Alternate phases: wide random search, then local perturbations around best
        if best is None or phase % 2 == 0:
            cand = base.copy()
            for k, (lo, hi) in bounds.items():
                # wide random in log-space-ish
                r = random.random()
                val = lo + r * (hi - lo)
                cand[k] = int(val)
        else:
            cand = best["weights"].copy()
            for k, (lo, hi) in bounds.items():
                # small gaussian perturbation
                sigma = 0.15
                factor = random.gauss(1.0, sigma)
                cand[k] = int(clamp(cand[k] * factor, lo, hi))
        stats = evaluate_weights(dates, gold, teams, res, cand, args.time_limit)
        entry = {"iter": iter_no, "weights": cand, **stats}
        history.append(entry)
        if best is None or stats["avg_delta"] < best["avg_delta"]:
            best = entry
        if iter_no % 10 == 0:
            phase += 1
        # flush progress every ~60s or when best improves
        now = time.time()
        if now - last_flush > 60 or (best and entry is best):
            progress = {
                "iter": iter_no,
                "elapsed_s": round(now - start, 1),
                "best": best,
            }
            progress_path.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")
            last_flush = now

    report = {
        "started": start,
        "seconds": args.seconds,
        "time_limit_s": args.time_limit,
        "best": best,
        "history": history[-200:],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.out}")
    if best:
        print("Best avg_delta:", best["avg_delta"], "weights:", best["weights"])


if __name__ == "__main__":
    main()
