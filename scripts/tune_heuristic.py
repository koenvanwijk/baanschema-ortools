#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Heuristic tuning scaffold against gold score")
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--gold", type=Path, default=Path("docs/gold_result.json"))
    ap.add_argument("--out", type=Path, default=Path("docs/gold_compare.json"))
    args = ap.parse_args()

    repo = args.repo.resolve()

    # 1) rebuild heuristic output
    run(["python", "scripts/build_pages.py"], repo)

    # 2) compare to gold
    run(
        [
            "python",
            "scripts/compare_to_gold.py",
            "--gold",
            str(args.gold),
            "--heur",
            "docs/result.json",
            "--ortools-dir",
            "docs",
            "--out",
            str(args.out),
        ],
        repo,
    )

    report = json.loads((repo / args.out).read_text(encoding="utf-8"))
    print("heuristic_avg_score:", report["summary"].get("heuristic_avg_score"))
    print("ortools_avg_score:", report["summary"].get("ortools_avg_score"))
    print("overall_winner:", report["summary"].get("overall_winner"))
    print("\nNOTE: this is the tuning scaffold baseline run. Next step: parameter grid search.")


if __name__ == "__main__":
    main()
