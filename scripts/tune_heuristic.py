#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DATES = [
    "06-04-2026",
    "12-04-2026",
    "19-04-2026",
    "10-05-2026",
    "17-05-2026",
    "25-05-2026",
    "31-05-2026",
]


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def run_one_combo(repo: Path, time_limit: float, seed: int, params: dict[str, int]) -> float:
    docs = repo / "docs"
    for d in DATES:
        out_file = docs / f"ortools_{d}.json"
        run(
            [
                sys.executable,
                "scripts/ortools_planner.py",
                "--date",
                d,
                "--time-limit",
                str(time_limit),
                "--random-seed",
                str(seed),
                "--w-block-rise",
                str(params["w_block_rise"]),
                "--w-long-gap",
                str(params["w_long_gap"]),
                "--w-morning-occ",
                str(params["w_morning_occ"]),
                "--w-total-occ",
                str(params["w_total_occ"]),
                "--w-cutoff-bonus",
                str(params["w_cutoff_bonus"]),
                "--w-early-start",
                str(params["w_early_start"]),
                "--w-late-start",
                str(params["w_late_start"]),
                "--w-youth-late",
                str(params["w_youth_late"]),
                "--out",
                str(out_file),
            ],
            repo,
        )

        raw = json.loads(out_file.read_text(encoding="utf-8"))
        if raw.get("status") not in {"OPTIMAL", "FEASIBLE"}:
            return 1_000_000_000.0

    out_file = docs / "gold_compare_tuning_tmp.json"
    run(
        [
            sys.executable,
            "scripts/compare_to_gold.py",
            "--gold",
            "docs/gold_result.json",
            "--heur",
            "docs/result.json",
            "--ortools-dir",
            "docs",
            "--out",
            str(out_file),
        ],
        repo,
    )

    report = json.loads(out_file.read_text(encoding="utf-8"))
    return float(report["summary"]["ortools_avg_score"])


def main() -> None:
    ap = argparse.ArgumentParser(description="Run reproducible OR-Tools weight tuning against gold score")
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--time-limit", type=float, default=20.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path("docs/tuning_report.json"))
    args = ap.parse_args()

    repo = args.repo.resolve()

    # Reuse existing heuristic baseline (docs/result.json) to keep tuning runtime short/reproducible.
    if not (repo / "docs" / "result.json").exists():
        raise FileNotFoundError("docs/result.json not found; run scripts/build_pages.py once first")

    default_params = {
        "w_block_rise": 2_000_000,
        "w_long_gap": 10_000_000,
        "w_morning_occ": 600_000,
        "w_total_occ": 80_000,
        "w_cutoff_bonus": 5000,
        "w_early_start": 100,
        "w_late_start": 120_000,
        "w_youth_late": 80_000,
    }

    # Small, safe first-pass candidate list (kept intentionally short for runtime)
    combos = [
        dict(default_params),
        {**default_params, "w_block_rise": 5_000_000, "w_long_gap": 20_000_000},
        {**default_params, "w_morning_occ": 200_000, "w_early_start": 0},
    ]

    results = []
    baseline_score = run_one_combo(repo, args.time_limit, args.seed, default_params)
    results.append({"name": "baseline", "params": default_params, "ortools_avg_score": baseline_score})

    for i, params in enumerate(combos[1:], start=1):
        score = run_one_combo(repo, args.time_limit, args.seed, params)
        results.append({"name": f"combo_{i}", "params": params, "ortools_avg_score": score})
        print(f"[{i}/{len(combos)-1}] score={score} params={params}")

    best = min(results, key=lambda r: r["ortools_avg_score"])
    report = {
        "seed": args.seed,
        "time_limit": args.time_limit,
        "baseline_score": baseline_score,
        "best": best,
        "all_results": sorted(results, key=lambda r: r["ortools_avg_score"]),
    }

    out_path = repo / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("baseline_score:", baseline_score)
    print("best_score:", best["ortools_avg_score"])
    print("best_params:", best["params"])
    print("report:", out_path)


if __name__ == "__main__":
    main()
