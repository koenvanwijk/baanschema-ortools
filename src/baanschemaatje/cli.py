"""CLI: ``python -m baanschemaatje <commando>``.

Commando's:
  check  --club FILE                       clubprofiel valideren
  dates  --season FILE [--club FILE]       speeldagen in het seizoen tonen
  plan   --club FILE --season FILE --date dd-mm-YYYY [--out FILE]

Output gaat standaard naar ``out/baanschemaatje/`` (gitignored), nooit naar
``docs/`` — de live site blijft onaangeroerd.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from baanschemaatje.profile import ProfileError, load_profile
from baanschemaatje.season import load_season_tsv

DEFAULT_OUT = Path("out") / "baanschemaatje"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "club"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="baanschemaatje", description="Baanschemaatje — generieke baanschema-planner")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="clubprofiel valideren")
    c.add_argument("--club", required=True, type=Path)

    d = sub.add_parser("dates", help="speeldagen in het seizoen")
    d.add_argument("--season", required=True, type=Path)
    d.add_argument("--club", type=Path)

    p = sub.add_parser("plan", help="eerste baanschema-voorstel voor één speeldag")
    p.add_argument("--club", required=True, type=Path)
    p.add_argument("--season", required=True, type=Path)
    p.add_argument("--date", required=True, help="dd-mm-YYYY")
    p.add_argument("--time-limit", type=float, default=20.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=Path, help=f"JSON-uitvoer (default: {DEFAULT_OUT}/<club>_<datum>.json)")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "check":
            prof = load_profile(a.club)
            print(f"OK: {prof.name} — {prof.courts} banen, reserveringen: "
                  f"{ {k.value: list(v.courts) for k, v in prof.reservations.items()} or 'geen'}")
            return 0
        if a.cmd == "dates":
            home = load_profile(a.club).knltb_name if a.club else ""
            season = load_season_tsv(a.season, home)
            for date, fx in season.by_date().items():
                print(f"{date}  {len(fx)} wedstrijden")
            return 0
        prof = load_profile(a.club)
        season = load_season_tsv(a.season, prof.knltb_name)
        if a.date not in season.dates():
            print(f"Datum {a.date} niet in seizoen; beschikbaar: {', '.join(season.dates())}", file=sys.stderr)
            return 2
        from baanschemaatje.planner import plan_day  # ortools pas laden als nodig

        res = plan_day(prof, season.fixtures, a.date, time_limit_s=a.time_limit, random_seed=a.seed)
        out = a.out or DEFAULT_OUT / f"{_slug(prof.name)}_{a.date}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{prof.name} {a.date}: status {res.status}, dagstart {res.day_start}, "
              f"ingepland {res.scheduled}, niet gelukt {res.unscheduled}, "
              f"{res.solve_time_s:.1f}s → {out}")
        return 0 if res.status in ("OPTIMAL", "FEASIBLE") else 1
    except ProfileError as exc:
        print(str(exc), file=sys.stderr)
        return 2
