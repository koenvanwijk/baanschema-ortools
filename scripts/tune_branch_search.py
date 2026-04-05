#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import time
from pathlib import Path
from statistics import mean

import ortools_planner
from compare_to_gold import normalize_rows, metrics, score

ROOT = Path(__file__).resolve().parents[1]
PLANNER = ROOT / "scripts" / "ortools_planner.py"

WEIGHT_KEYS = [
    "w_block_rise",
    "w_long_gap",
    "w_morning_occ",
    "w_total_occ",
    "w_cutoff_bonus",
    "w_early_start",
    "w_late_start",
    "w_youth_late",
    "w_team_court_penalty",
    "w_high_court_penalty",
    "w_team_span",
]


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


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def update_defaults(weights: dict):
    text = PLANNER.read_text(encoding="utf-8")
    for k, v in weights.items():
        # update function defaults
        text = re.sub(rf"(\b{k}: int = )\d+[\d_]*", rf"\g<1>{v}", text)
        # update argparse defaults
        text = re.sub(rf"(--{k.replace('_','-')}\", type=int, default=)\d+[\d_]*", rf"\g<1>{v}", text)
    PLANNER.write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Branch-based OR-Tools weight search")
    ap.add_argument("--gold", type=Path, default=Path("docs/gold_result.json"))
    ap.add_argument("--seconds", type=int, default=3600)
    ap.add_argument("--time-limit", type=float, default=4.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rounds", type=int, default=6)
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

    start = time.time()
    seeds = [base]
    round_idx = 0
    log_path = ROOT / "docs" / "ortools_branch_tuning.log.json"
    log = []

    while time.time() - start < args.seconds and round_idx < args.rounds:
        round_idx += 1
        candidates = []
        for seed in seeds:
            for _ in range(10):
                cand = seed.copy()
                for k, (lo, hi) in bounds.items():
                    factor = random.gauss(1.0, 0.2)
                    cand[k] = int(clamp(cand[k] * factor, lo, hi))
                stats = evaluate_weights(dates, gold, teams, res, cand, args.time_limit)
                candidates.append({"weights": cand, **stats})
        # sort best (lower avg_delta)
        candidates.sort(key=lambda x: x["avg_delta"])
        top3 = candidates[:3]
        log.append({"round": round_idx, "top3": top3})
        log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")

        # create branches for top3
        for i, entry in enumerate(top3, 1):
            branch = f"tune/round-{round_idx}-rank-{i}"
            # reset working tree
            git("checkout", "main")
            git("reset", "--hard")
            git("checkout", "-B", branch)
            update_defaults(entry["weights"])
            git("add", str(PLANNER))
            git("commit", "-m", f"Tune weights r{round_idx} #{i} avg_delta {entry['avg_delta']}")

        seeds = [e["weights"] for e in top3]

    print("Done. Top branches created.")


if __name__ == "__main__":
    main()
