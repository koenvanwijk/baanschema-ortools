from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baanschema.cli import load_problem
from baanschema.model import solve_schedule
EXAMPLE = ROOT / "examples" / "simple_case.json"
DOCS = ROOT / "docs"


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)

    problem = load_problem(EXAMPLE)
    result = solve_schedule(problem)

    rows = "\n".join(
        f"<tr><td>{html.escape(slot)}</td><td>{html.escape(court)}</td><td>{html.escape(match_id)}</td></tr>"
        for match_id, slot, court in result.assignments
    )

    payload = {
        "status": result.status,
        "objective": result.objective,
        "assignments": [
            {"match_id": m, "slot": s, "court": c} for m, s, c in result.assignments
        ],
    }
    (DOCS / "result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    page = f"""<!doctype html>
<html lang=\"nl\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Baanschema Optimizer</title>
  <style>
    body {{ font-family: Inter, system-ui, sans-serif; margin: 2rem auto; max-width: 900px; padding: 0 1rem; }}
    .card {{ border: 1px solid #ddd; border-radius: 12px; padding: 1rem; margin-bottom: 1rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #eee; text-align: left; padding: 0.55rem; }}
    th {{ background: #fafafa; }}
    code {{ background: #f2f2f2; padding: 0.15rem 0.35rem; border-radius: 6px; }}
  </style>
</head>
<body>
  <h1>Baanschema Optimizer</h1>
  <p>Automatisch gegenereerd met OR-Tools op basis van <code>examples/simple_case.json</code>.</p>

  <div class=\"card\">
    <strong>Status:</strong> {html.escape(result.status)}<br />
    <strong>Objective (back-to-back penalties):</strong> {result.objective}
  </div>

  <h2>Ingepland schema</h2>
  <table>
    <thead><tr><th>Slot</th><th>Baan</th><th>Wedstrijd</th></tr></thead>
    <tbody>
      {rows}
    </tbody>
  </table>

  <p style=\"margin-top:1.5rem;color:#666\">Deze pagina wordt automatisch bijgewerkt via GitHub Actions.</p>
</body>
</html>
"""
    (DOCS / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
