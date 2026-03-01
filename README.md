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

## Volgende stappen

1. Inputschema fixeren met Oscar
2. Extra zachte constraints toevoegen (eerlijkheid, rustverdeling)
3. Export naar overzichtelijk schema (CSV / markdown)
4. Github repo aanmaken + CI + tests uitbreiden
