# Baanschema Optimizer (OR-Tools + Python)

Planningsproject voor Oscar om wedstrijden over banen en tijdsloten te plannen met:

- **Harde constraints** (moeten altijd gelden)
  - vast aantal banen
  - spelers kunnen niet op twee banen tegelijk spelen
  - vast aantal spelers per baan/wedstrijd
- **Zachte constraints** (liefst, maar niet verplicht)
  - geen twee wedstrijden direct achter elkaar voor dezelfde speler

## Stack

- Python 3.11+
- Google OR-Tools (CP-SAT)

## Snelle start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m baanschema.cli --example
```

## Model aanpak (v1)

We modelleren binaire variabelen:

- `x[match, slot, court] = 1` als wedstrijd `match` op `slot` en `court` staat.

Harde constraints:

1. Elke wedstrijd precies één keer ingepland.
2. Per baan+slot maximaal één wedstrijd.
3. Geen speler in twee wedstrijden in hetzelfde slot.

Zachte constraints (objective penalties):

- Back-to-back wedstrijden voor dezelfde speler.

## Input formaat (v1)

Zie `examples/simple_case.json`.

## Wedstrijddag herplanning

De live herplanning draait via de Cloud Run API:
- Frontend: `https://koenvanwijk.github.io/baanschema-ortools/replan.html`
- API: `https://baanschema-api-dndzrlckha-ew.a.run.app`

In de pagina kies je:
- datum
- huidige tijd (`now`)
- afgeronde partijen (checkboxen in de matrix)

De tool toont direct de restplanning voor die dag en haalt plandata op via `GET /result`.

Optioneel blijft de CLI versie beschikbaar:

```bash
python scripts/replan_day.py --status examples/replan_status.example.json
```

## Tweede planningstool (OR-Tools CP-SAT)

Er is nu ook een tweede planner toegevoegd met een OR-Tools optimalisatie-loop:

```bash
python scripts/ortools_planner.py --date 17-05-2026 --time-limit 30
```

Output komt standaard in:
- `docs/ortools_result.json`

Doel van deze tweede tool:
- vergelijken met de heuristische planner op kwaliteit/runtime
- betere bezetting op drukke dagen via CP-SAT objective

## Schema valideren

Elke uitvoer kan los van de solver getoetst worden tegen `data/season.tsv` en
`docs/planningsregels.md`:

```bash
python scripts/validate_schedule.py docs/ortools_06-04-2026.json
python scripts/validate_schedule.py docs/gold_result.json --all
```

Bevindingen zijn **HARD** (regel uit `planningsregels.md`) of **MODEL** (extra
constraint die alleen het CP-SAT model oplegt). Die tweede categorie laat zien
waar het model strenger is dan het handmatige schema. In CI staat per bron een
plafond via `--max-hard` / `--max-model`, zodat regressies opvallen.

## Planningsregels

Alle actuele planningsregels staan in:
- `docs/planningsregels.md`

Snelle handmatige versie (printbaar):
- `docs/planner-cheatsheet.md`

## Volgende stappen

Uitgewerkt plan met metingen: `docs/REFACTOR_PLAN.md`.

1. ~~Validator + CI-vangnet~~ (klaar)
2. Unieke teamsleutel en de S/D-bug
3. CP-SAT model naar intervals + integer-startvariabelen
4. Objective lexicografisch in plaats van gewogen som
5. Vergelijkingsrapport oud vs nieuw vs gold per speeldag
6. cuOpt- en Timefold-experimenten archiveren
