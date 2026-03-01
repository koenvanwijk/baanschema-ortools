from __future__ import annotations

import argparse
import json
from pathlib import Path

from .model import Match, ProblemData, solve_schedule


def load_problem(path: Path) -> ProblemData:
    raw = json.loads(path.read_text())
    return ProblemData(
        courts=raw["courts"],
        slots=raw["slots"],
        matches=[Match(id=m["id"], players=tuple(m["players"])) for m in raw["matches"]],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Baanschema optimizer")
    parser.add_argument("--input", type=Path, help="Pad naar input JSON")
    parser.add_argument(
        "--example",
        action="store_true",
        help="Gebruik examples/simple_case.json als input",
    )
    parser.add_argument("--time-limit", type=float, default=10.0)
    args = parser.parse_args()

    if args.example:
        path = Path(__file__).resolve().parents[2] / "examples" / "simple_case.json"
    elif args.input:
        path = args.input
    else:
        raise SystemExit("Gebruik --input <file.json> of --example")

    problem = load_problem(path)
    result = solve_schedule(problem, time_limit_s=args.time_limit)

    print(f"Status: {result.status}")
    if result.objective is not None:
        print(f"Objective (back-to-back penalties): {result.objective}")

    for match_id, slot, court in result.assignments:
        print(f"- {slot} | {court} | {match_id}")


if __name__ == "__main__":
    main()
