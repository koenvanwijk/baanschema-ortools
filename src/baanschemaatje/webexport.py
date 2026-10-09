"""Statische web-export: plannen voor alle speeldagen + clubprofielen als JSON.

``python -m baanschemaatje build-web`` schrijft naar ``web/baanschemaatje/data/``.
De web-GUI (``web/baanschemaatje/index.html``) leest alleen die bestanden;
er is geen backend nodig. Plannen zijn dus vooraf berekend.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from baanschemaatje.categories import DEFAULT_DURATIONS, MIN_RESERVATION
from baanschemaatje.profile import CORE_RULE_DEFAULTS, RULE_SOURCES, ClubProfile, load_profile, min_to_hhmm, profile_from_dict
from baanschemaatje.season import load_season_tsv

ROOT = Path(__file__).resolve().parents[2]


def _fmt_params(params: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in params.items():
        out[k] = min_to_hhmm(v) if k in ("time", "from", "to") and isinstance(v, int) else v
    return out


def profile_summary(prof: ClubProfile, club_id: str) -> dict[str, Any]:
    core = profile_from_dict({"club": {"name": "core"}, "courts": {"count": prof.courts}})
    rules = []
    for name in CORE_RULE_DEFAULTS:
        r, c = prof.rule(name), core.rule(name)
        rules.append({
            "name": name,
            "source": RULE_SOURCES.get(name, "product"),
            "hard": r.hard,
            "params": _fmt_params(r.params),
            "core_params": _fmt_params(c.params),
            "core_hard": c.hard,
            "club_override": (r.params != c.params) or (r.hard != c.hard),
        })
    return {
        "id": club_id,
        "name": prof.name,
        "knltb_name": prof.knltb_name,
        "courts": prof.courts,
        "day": {
            "start": min_to_hhmm(prof.day_start),
            "fallback_start": min_to_hhmm(prof.fallback_start) if prof.fallback_start is not None else None,
            "last_start": min_to_hhmm(prof.last_start),
            "end": min_to_hhmm(prof.day_end),
        },
        "reservations": {
            k.value: {"courts": list(v.courts), "courts_if_rood": list(v.courts_if_rood) if v.courts_if_rood else None}
            for k, v in prof.reservations.items()
        },
        "court_pairs": [list(p) for p in prof.court_pairs] if prof.court_pairs else None,
        "max_courts_per_team": prof.max_courts_per_team,
        "adjacent_courts": prof.adjacent_courts,
        "preferred_courts_8p": list(prof.preferred_courts_8p),
        "durations": {k.value: prof.expected_duration(k) for k in DEFAULT_DURATIONS},
        "min_reservation": {k.value: v for k, v in MIN_RESERVATION.items()},
        "rules": rules,
    }


def _validate(plan: dict[str, Any], season: Path, profile: ClubProfile | None = None) -> dict[str, Any]:
    from baanschemaatje.validation import validate_plan

    return validate_plan(plan, season, profile)


def build_web(
    clubs: list[Path],
    season: Path,
    out_dir: Path,
    time_limit_s: float = 20.0,
    dates: list[str] | None = None,
    log=print,
    solutions: bool = True,
) -> dict[str, Any]:
    from baanschemaatje.planner import plan_day

    out_dir.mkdir(parents=True, exist_ok=True)
    index: dict[str, Any] = {
        "generator": "baanschemaatje",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season_file": season.name,
        "time_limit_s": time_limit_s,
        "clubs": [],
    }
    for club_path in clubs:
        club_id = club_path.stem
        prof = load_profile(club_path)
        s = load_season_tsv(season, prof.knltb_name)
        club_dir = out_dir / club_id
        club_dir.mkdir(parents=True, exist_ok=True)
        summary = profile_summary(prof, club_id)
        summary["dates"] = []
        for date in dates or s.dates():
            res = plan_day(prof, s.fixtures, date, time_limit_s=time_limit_s)
            plan = res.to_dict()
            plan["validator"] = _validate({"status": plan["status"], "date": date, "rows": plan["rows"]}, season, prof)
            (club_dir / f"{date}.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
            sol_file, best = None, None
            if solutions and res.unscheduled:
                from baanschemaatje.scenarios import propose_solutions

                log(f"{prof.name} {date}: {res.unscheduled} niet ingepland → oplossingen zoeken")
                sols = propose_solutions(prof, s.fixtures, date, plan["rows"], time_limit_s=time_limit_s, log=log)
                for sol in sols:
                    sol["plan"]["validator"] = _validate(
                        {"status": sol["plan"]["status"], "date": date, "rows": sol["plan"]["rows"]}, season, prof)
                    sol["validator_hard"] = sol["plan"]["validator"]["hard"]
                sol_file = f"{club_id}/{date}.solutions.json"
                (out_dir / sol_file).write_text(json.dumps({"date": date, "club": club_id, "solutions": sols},
                                                           indent=1, ensure_ascii=False), encoding="utf-8")
                ok = [x for x in sols if x["fits"] and x["knltb_ok"]]
                best = ok[0]["title"] if ok else None
            summary["dates"].append({
                "solutions_file": sol_file,
                "best_solution": best,
                "date": date,
                "file": f"{club_id}/{date}.json",
                "status": plan["status"],
                "day_start": plan["day_start"],
                "fixtures": len(s.day(date)),
                "scheduled": res.scheduled,
                "unscheduled": res.unscheduled,
                "solve_time_s": plan["stats"]["solve_time_s"],
                "hard": plan["validator"]["hard"],
                "model": plan["validator"]["model"],
            })
            log(f"{prof.name} {date}: {res.scheduled} ingepland, {res.unscheduled} niet gelukt, "
                f"HARD={plan['validator']['hard']} MODEL={plan['validator']['model']}, {res.solve_time_s:.1f}s")
        index["clubs"].append(summary)
    (out_dir / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    return index


def rebuild_index(clubs: list[Path], season: Path, out_dir: Path, log=print) -> dict[str, Any]:
    """index.json opnieuw opbouwen uit bestaande plan-/oplossingsbestanden, ZONDER te plannen.

    Valideert de bestaande plannen opnieuw (goedkoop) met de huidige
    validator-wrapper en het huidige clubprofiel, en verwijdert voorstellen die
    niet meer zijn toegestaan (wedstrijd naar een inhaaldag). Dagen zonder
    planbestand worden overgeslagen; plannen gebeurt alleen expliciet.
    """
    index: dict[str, Any] = {
        "generator": "baanschemaatje",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season_file": season.name,
        "time_limit_s": None,
        "clubs": [],
    }
    old = {}
    if (out_dir / "index.json").exists():
        old = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
        index["time_limit_s"] = old.get("time_limit_s")
    for club_path in clubs:
        club_id = club_path.stem
        prof = load_profile(club_path)
        s = load_season_tsv(season, prof.knltb_name)
        summary = profile_summary(prof, club_id)
        summary["dates"] = []
        for date in s.dates():
            f = out_dir / club_id / f"{date}.json"
            if not f.exists():
                log(f"{club_id} {date}: geen planbestand, overgeslagen")
                continue
            plan = json.loads(f.read_text(encoding="utf-8"))
            plan["validator"] = _validate({"status": plan["status"], "date": date, "rows": plan["rows"]}, season, prof)
            f.write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
            st = plan["stats"]
            sol_rel, best = None, None
            sf = out_dir / club_id / f"{date}.solutions.json"
            if st["unscheduled"] and sf.exists():
                data = json.loads(sf.read_text(encoding="utf-8"))
                sols = [x for x in data["solutions"] if x.get("kind") != "inhaaldag" and "inhaaldag" not in x.get("id", "")]
                for i, x in enumerate(sols, 1):
                    x["rank"] = i
                    x["plan"]["validator"] = _validate(
                        {"status": x["plan"]["status"], "date": date, "rows": x["plan"]["rows"]}, season, prof)
                    x["validator_hard"] = x["plan"]["validator"]["hard"]
                data["solutions"] = sols
                sf.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
                sol_rel = f"{club_id}/{date}.solutions.json"
                ok = [x for x in sols if x["fits"] and x["knltb_ok"]]
                best = ok[0]["title"] if ok else None
            elif sf.exists():
                sf.unlink()  # dag past nu; oud oplossingsbestand is achterhaald
            summary["dates"].append({
                "solutions_file": sol_rel, "best_solution": best, "date": date, "file": f"{club_id}/{date}.json",
                "status": plan["status"], "day_start": plan["day_start"], "fixtures": len(s.day(date)),
                "scheduled": st["scheduled"], "unscheduled": st["unscheduled"], "solve_time_s": st["solve_time_s"],
                "hard": plan["validator"]["hard"], "model": plan["validator"]["model"],
            })
            log(f"{club_id} {date}: {st['scheduled']} ingepland, {st['unscheduled']} niet, HARD={plan['validator']['hard']}")
        index["clubs"].append(summary)
    (out_dir / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    return index
