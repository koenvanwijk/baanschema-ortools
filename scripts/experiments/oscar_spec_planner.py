"""
Alternatief baanschema CP-SAT model — spec zoals aangeleverd door Oscar (superozz)
in Discord #baanschema, 24-08-2026 (2x geplakt, incl. Excel-brondata NJ2026).

Dit is een LOS EXPERIMENT naast de bestaande productieplanner
(`scripts/ortools_planner.py`) — niet de vervanger. De regels in deze spec
wijken op een aantal punten af van `docs/planningsregels.md`:

  - Rood/Oranje: hier vaste index (2=09:00) + vaste baan-toewijzing i.p.v. de
    bestaande dynamische dagstart-regel (09:00 proberen, terugval 08:30).
  - Start-limieten (Junioren 13:00, overig 15:00) zijn hier vaste soft-caps,
    i.p.v. de datum-specifieke cutoffs in ortools_planner.py.
  - Interne fasering S->D->GD hier simpel end<=start per fase, i.p.v. de
    rondestructuur (S1+S2 gelijk, S3+S4 gelijk) + player-demand (mannen/vrouwen)
    die de bestaande planner gebruikt voor gemengde teams.
  - Geen baan-paren (1+2, 3+4, ...) constraint; hier vrije baankeuze met alleen
    een "spread"-penalty in de objective.
  - Geen 2-blokken-compactheidseis; hier alleen een softe span-penalty.

Zie ook:
  - docs/planningsregels.md  (huidige, in productie gebruikte regels)
  - docs/oscar-2026-08-24-spec.md  (letterlijke spec van Oscar)
  - data/oscar-2026-08-24-export_processed_NJ2026.xlsx  (aangeleverde Excel)

Gebruik: python3 scripts/experiments/oscar_spec_planner.py <xlsx> [YYYY-MM-DD]
Zonder datum wordt de eerste datum in het bestand gebruikt.
"""

import sys
from datetime import datetime
from pathlib import Path

import openpyxl
from ortools.sat.python import cp_model

NUM_COURTS = 10
MAX_HORIZON = 60
BLOCK_MIN = 15
START_CLOCK = (8, 30)


def idx_to_time(i):
    total_min = START_CLOCK[0] * 60 + START_CLOCK[1] + i * BLOCK_MIN
    h, m = divmod(total_min, 60)
    return f"{h:02d}:{m:02d}"


PRIORITY_ORDER = [
    "Rood", "Oranje", "8-partijen-team", "Groen", "Junioren",
    "Jongens/Meisjes", "Gemengd", "Heren",
]
PRIORITY_WEIGHT = {cat: (len(PRIORITY_ORDER) - i) * 10 for i, cat in enumerate(PRIORITY_ORDER)}


def categorize(schema_text, wedstrijden):
    t = schema_text.lower()
    if "gemengd" in t and wedstrijden == 8:
        return "8-partijen-team"
    if "gemengd" in t:
        return "Gemengd"
    if "junioren 11" in t:
        return "Junioren"
    if "groen" in t:
        return "Groen"
    if "jongens 13" in t or "meisjes 13" in t:
        return "Jongens/Meisjes"
    if "heren" in t:
        return "Heren"
    if "dames" in t:
        return "Heren"
    if "oranje" in t:
        return "Oranje"
    if "rood" in t:
        return "Rood"
    return "Heren"


def load_day(xlsx_path, target_date=None):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    dates = sorted({r[0].date() for r in rows if r[0] is not None})
    chosen = dates[0] if target_date is None else datetime.strptime(target_date, "%Y-%m-%d").date()
    day_rows = [r for r in rows if r[0] is not None and r[0].date() == chosen]
    return chosen, day_rows, dates


def build_matches(day_rows):
    matches = []
    for r in day_rows:
        (_datum, _weekdag, _middag, schema, wedstrijden, wedstrijdduur,
         singles, doubles, mix, _totale_duur, team1, _team2, _thuisuit) = r
        cat = categorize(schema, wedstrijden)
        blocks = round(wedstrijdduur / BLOCK_MIN)
        team_key = f"{team1} | {schema}"

        counts = [("S", singles or 0, 0), ("D", doubles or 0, 1), ("M", mix or 0, 2)]
        idx = 1
        produced = 0
        for label, cnt, fase in counts:
            for _ in range(cnt):
                mid = f"{team_key}#{label}{idx}"
                matches.append({"id": mid, "team": team_key, "cat": cat, "fase": fase, "duur": blocks})
                idx += 1
                produced += 1
        if produced == 0 and wedstrijden:
            for k in range(wedstrijden):
                mid = f"{team_key}#R{k+1}"
                matches.append({"id": mid, "team": team_key, "cat": cat, "fase": 0, "duur": blocks})
    return matches


def solve_and_print(matches, chosen_date):
    model = cp_model.CpModel()
    start, end, presence, baan_var = {}, {}, {}, {}

    for m in matches:
        i = m["id"]
        d = m["duur"]
        start[i] = model.NewIntVar(0, MAX_HORIZON, f"start_{i}")
        end[i] = model.NewIntVar(0, MAX_HORIZON, f"end_{i}")
        model.Add(end[i] == start[i] + d)
        presence[i] = {b: model.NewBoolVar(f"pres_{i}_{b}") for b in range(NUM_COURTS)}
        model.AddExactlyOne(presence[i][b] for b in range(NUM_COURTS))

    for b in range(NUM_COURTS):
        opt_ivs = []
        for m in matches:
            i = m["id"]
            opt_ivs.append(model.NewOptionalIntervalVar(
                start[i], m["duur"], end[i], presence[i][b], f"optiv_{i}_{b}"))
        model.AddNoOverlap(opt_ivs)

    rood_matches = [m for m in matches if m["cat"] == "Rood"]
    oranje_matches = [m for m in matches if m["cat"] == "Oranje"]
    rood_start_idx = 2  # 09:00
    for m in rood_matches:
        i = m["id"]
        model.Add(start[i] == rood_start_idx)
        model.Add(presence[i][0] == 1)
    oranje_banen = [1, 2, 3] if rood_matches else [0, 1, 2]
    for m in oranje_matches:
        i = m["id"]
        model.Add(start[i] == rood_start_idx)
        model.AddAllowedAssignments(
            [presence[i][b] for b in range(NUM_COURTS)],
            [[1 if b == ob else 0 for b in range(NUM_COURTS)] for ob in oranje_banen])

    soft_penalties = []
    teams_by_name = {}
    for m in matches:
        teams_by_name.setdefault(m["team"], []).append(m)

    for team_naam, team_matches in teams_by_name.items():
        cat = team_matches[0]["cat"]
        ids = [m["id"] for m in team_matches]
        min_start_var = model.NewIntVar(0, MAX_HORIZON, f"minstart_{team_naam}")
        model.AddMinEquality(min_start_var, [start[i] for i in ids])

        limit = None
        if cat == "Junioren":
            limit = 18
        elif cat == "8-partijen-team":
            model.Add(min_start_var >= 6)
            model.Add(min_start_var <= 10)
        elif cat not in ("Rood", "Oranje"):
            limit = 26

        if limit is not None:
            over = model.NewBoolVar(f"over_start_{team_naam}")
            model.Add(min_start_var <= limit).OnlyEnforceIf(over.Not())
            model.Add(min_start_var > limit).OnlyEnforceIf(over)
            soft_penalties.append((over, 5000, f"start-limiet overschreden: {team_naam}"))

        if cat == "Gemengd":
            for i in ids:
                model.Add(start[i] >= 6)

    for m in matches:
        i = m["id"]
        over_evening = model.NewBoolVar(f"over_evening_{i}")
        model.Add(start[i] <= 44).OnlyEnforceIf(over_evening.Not())
        model.Add(start[i] > 44).OnlyEnforceIf(over_evening)
        soft_penalties.append((over_evening, 10000, f"avond-deadline overschreden: {i}"))

    for team_naam, team_matches in teams_by_name.items():
        fase0 = [m["id"] for m in team_matches if m["fase"] == 0]
        fase1 = [m["id"] for m in team_matches if m["fase"] == 1]
        fase2 = [m["id"] for m in team_matches if m["fase"] == 2]
        if fase1:
            for i0 in fase0:
                for i1 in fase1:
                    model.Add(end[i0] <= start[i1])
        if fase2:
            base = fase1 if fase1 else fase0
            for ib in base:
                for i2 in fase2:
                    model.Add(end[ib] <= start[i2])

    objective_terms = []
    for m in matches:
        i = m["id"]
        w = PRIORITY_WEIGHT.get(m["cat"], 5)
        objective_terms.append(start[i] * w)

    for team_naam, team_matches in teams_by_name.items():
        ids = [m["id"] for m in team_matches]
        if len(ids) < 2:
            continue
        max_end = model.NewIntVar(0, MAX_HORIZON, f"maxend_{team_naam}")
        min_start_v = model.NewIntVar(0, MAX_HORIZON, f"minstart2_{team_naam}")
        model.AddMaxEquality(max_end, [end[i] for i in ids])
        model.AddMinEquality(min_start_v, [start[i] for i in ids])
        span = model.NewIntVar(0, MAX_HORIZON, f"span_{team_naam}")
        model.Add(span == max_end - min_start_v)
        objective_terms.append(span * 50)

    for m in matches:
        i = m["id"]
        bv = model.NewIntVar(0, NUM_COURTS - 1, f"baanidx_{i}")
        model.Add(bv == sum(b * presence[i][b] for b in range(NUM_COURTS)))
        baan_var[i] = bv

    for team_naam, team_matches in teams_by_name.items():
        ids = [m["id"] for m in team_matches]
        if len(ids) < 2:
            continue
        max_b = model.NewIntVar(0, NUM_COURTS - 1, f"maxbaan_{team_naam}")
        min_b = model.NewIntVar(0, NUM_COURTS - 1, f"minbaan_{team_naam}")
        model.AddMaxEquality(max_b, [baan_var[i] for i in ids])
        model.AddMinEquality(min_b, [baan_var[i] for i in ids])
        spread = model.NewIntVar(0, NUM_COURTS - 1, f"spread_{team_naam}")
        model.Add(spread == max_b - min_b)
        objective_terms.append(spread * 30)

    for m in matches:
        if m["cat"] == "8-partijen-team":
            i = m["id"]
            penalty_high_court = sum(presence[i][b] for b in range(4, NUM_COURTS))
            objective_terms.append(penalty_high_court * 20)

    for var, weight, _label in soft_penalties:
        objective_terms.append(var * weight)

    model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    status_name = solver.StatusName(status)

    print(f"=== Oscar-spec baanschema {chosen_date.isoformat()} — CP-SAT status: {status_name} "
          f"(objective={solver.ObjectiveValue() if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else 'n/a'}) ===\n")

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("Geen oplossing gevonden binnen tijdslimiet.")
        return

    unique_teams = []
    for m in matches:
        if m["team"] not in unique_teams:
            unique_teams.append(m["team"])
    team_code = {t: f"T{idx+1}" for idx, t in enumerate(unique_teams)}

    schedule = []
    for m in matches:
        i = m["id"]
        s = solver.Value(start[i])
        e = solver.Value(end[i])
        b = solver.Value(baan_var[i])
        tag = " [>19:30]" if s > 44 else ""
        label = f"{team_code[m['team']]}-{i.split('#')[-1]}"
        schedule.append({"id": i, "team": m["team"], "cat": m["cat"],
                          "start": s, "end": e, "baan": b, "tag": tag, "label": label})
    schedule.sort(key=lambda x: (x["start"], x["baan"]))

    slots = sorted(set(x["start"] for x in schedule))
    print(f"{'Tijd':7s} | " + " | ".join(f"Baan{c+1:>2}" for c in range(NUM_COURTS)))
    print("-" * (9 + NUM_COURTS * 9))
    for s in slots:
        row = [""] * NUM_COURTS
        for x in schedule:
            if x["start"] == s:
                row[x["baan"]] = x["label"] + x["tag"]
        print(f"{idx_to_time(s):7s} | " + " | ".join(f"{cell:>8s}" for cell in row))

    print("\n=== Legenda teams ===")
    for t in unique_teams:
        cat = next(m["cat"] for m in matches if m["team"] == t)
        print(f"  {team_code[t]}: {t}  (cat={cat})")

    print("\n=== Soft-constraint overschrijdingen ===")
    any_over = False
    for var, weight, label in soft_penalties:
        if solver.Value(var):
            any_over = True
            print(f"  - {label} (penalty gewicht {weight})")
    if not any_over:
        print("  Geen overschrijdingen — alle harde/soft deadlines gehaald.")


if __name__ == "__main__":
    xlsx_path = sys.argv[1]
    target_date = sys.argv[2] if len(sys.argv) > 2 else None
    chosen, day_rows, all_dates = load_day(xlsx_path, target_date)
    if not day_rows:
        print(f"Geen data voor {target_date}. Beschikbare datums: {all_dates}")
        sys.exit(1)
    matches = build_matches(day_rows)
    solve_and_print(matches, chosen)
