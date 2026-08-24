# Oscar's spec-experiment — resultaten

Zie `oscar-2026-08-24-spec.md` voor de volledige spec en het verschil met de
huidige productieregels (`docs/planningsregels.md`).

Script: `scripts/experiments/oscar_spec_planner.py`
Brondata: `data/experiments/oscar-2026-08-24-export_processed_NJ2026.xlsx`

## Resultaten (alle 6 zondagen uit de aangeleverde Excel)

| Datum | Status | Objective | Overschrijdingen (`[>19:30]` / start-limiet) |
|---|---|---|---|
| 2026-09-06 | FEASIBLE | 17840.0 | geen |
| 2026-09-13 | FEASIBLE | 34790.0 | geen |
| 2026-09-20 | FEASIBLE | 20810.0 | geen |
| 2026-09-27 | FEASIBLE | 40180.0 | geen |
| 2026-10-04 | FEASIBLE | 28590.0 | geen |
| 2026-10-11 | OPTIMAL  | 8850.0  | geen |

Alle 6 dagen zijn oplosbaar binnen Oscar's spec-regels, zonder enige
soft-constraint overschrijding (geen avond-overschrijdingen, geen
start-limiet-overschrijdingen). Volledige tijdslot × baan grids staan in
`oscar-spec-result-<datum>.txt` per dag.

**Let op:** dit is dus een ander model dan de bestaande productieplanner en
geeft daardoor ook een ander (eenvoudiger) rooster — geen baan-paren, geen
rondestructuur, geen player-demand voor gemengde teams. Puur bedoeld als
vergelijkingsmateriaal voor de regeldiscussie tussen Koen en Oscar.
