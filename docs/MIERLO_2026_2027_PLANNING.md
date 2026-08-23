# Mierlo baanschema 2026-2027 — thuiszondagen

Deze notitie beschrijft de aanpak en resultaten voor het plannen van de
**thuiswedstrijden van Mierlose T.V. op zondagen** in het seizoen 2026-2027.

## Bron en selectie

- Bron: `docs/wedstrijden_2026-2027.xlsx` (229 rijen, KNLTB-competitie-export;
  kolommen `Datum, Schema, Team 1, Team 2, Uitslag, Wedstrijdstatus,
  Aanvoerder Team 1, Aanvoerder Team 2`).
- We plannen **alleen** wedstrijden die:
  1. op een **zondag** worden gespeeld (`Datum` valt op zondag),
  2. een **thuiswedstrijd** van Mierlo zijn — in de KNLTB-export is **Team 1 de
     thuisploeg**, dus `Team 1` begint met `MIERLO`, en
  3. tot een **Zondag-competitie** horen (`Schema` bevat "Zondag").
- Selectie en afleiding gebeurt met `scripts/parse_wedstrijden_xlsx.py`, dat een
  seizoens-TSV `data/season_2026-2027.tsv` schrijft in hetzelfde formaat als de
  bestaande `data/season.tsv`. Wedstrijden/duur/singles/dubbels/mix worden uit de
  schema-tekst afgeleid met dezelfde conventies als het seizoen 2025-2026:

  | Schema bevat | Wedstrijden | Duur | S | D | GD |
  |---|---|---|---|---|---|
  | `2DE-2HE-DD-HD-2GD` (Gemengd) | 8 | 90 | 4 | 2 | 2 |
  | `DE-HE-GD-DD-HD` (Gemengd) | 5 | 90 | 2 | 2 | 1 |
  | Jongens / Meisjes 13 t/m 17 | 6 | 90 | 4 | 2 | 0 |
  | Junioren 11 t/m 14 | 6 | 45 | 4 | 2 | 0 |
  | Groen | 6 | 45 | 4 | 2 | 0 |
  | Heren / Dames Zondag | 6 | 90 | 4 | 2 | 0 |

Resultaat: **52 thuiswedstrijden over 6 zondagen** (6-9, 13-9, 20-9, 27-9,
4-10, 11-10 2026). De KNLTB-export bevat geen Rood/Oranje-reserveringen voor deze
zondagen, dus die spelen hier geen rol.

## Planning

Per zondag worden alle thuiswedstrijden samen gepland met de bestaande OR-Tools
CP-SAT planner (`scripts/ortools_planner.py`), met de regels uit
`docs/planningsregels.md` als bindende basis (10 banen, kwartierblokken,
S/D/GD-volgorderegels, start-tijdvensters, compactheid, baan-paren, enz.).

Aanroep per dag:

```bash
python scripts/ortools_planner.py \
  --input data/season_2026-2027.tsv \
  --date 06-09-2026 --time-limit 90 \
  --out docs/ortools_2026-2027_06-09-2026.json
```

De outputs staan in `docs/ortools_2026-2027_<datum>.json` en worden getoond op de
losse pagina `docs/mierlo-2026-2027.html` (gegenereerd door
`scripts/build_mierlo_page.py`), naast de bestaande 2025-2026 pagina
`docs/index.html`.

## Twee bekende bugs — gefixt

Twee eerder gevonden bugs in de planner zijn in deze branch verholpen:

1. **Unieke team-sleutels (bug #1).** Als op één dag hetzelfde schema/dezelfde
   klasse 2× voorkomt met verschillende thuisteams, werden de teams samengevoegd
   omdat er op `schema` werd gegroepeerd. De planner gebruikt nu een unieke
   sleutel `schema · <thuisteam>` (`TeamDay.team_key`), zodat teams gescheiden
   blijven. Voor 2026-2027 verschillen alle schema-strings per dag toevallig al
   (via het afdelingsnummer), maar de fix maakt de planner robuust en is met een
   synthetische testcase afgedekt.

2. **Non-overlap over álle tijdsloten (bug #2).** De regels "singles en dubbels
   niet tegelijk" en "dubbels en GD niet tegelijk" (en voor
   `2DE-2HE-DD-HD-2GD` ook "singles en GD niet tegelijk") werden opgelegd op
   slechts één tijdslot (de laatste waarde van een eerdere lus-variabele `t`).
   Ze staan nu in een expliciete lus over **alle** kwartierblokken en gelden voor
   alle teams. Dit raakte vooral gemengde teams, waar de "singles vóór dubbels"-
   constraint niet geldt.

Beide fixes zijn afgedekt door tests in `tests/test_mierlo_2026_2027.py`.

## Validatie

`scripts/validate_schedule.py` controleert elk dagresultaat tegen de regels en
rapporteert per dag het aantal thuiswedstrijden, geplande/totale partijen en het
aantal HARD- en MODEL-afwijkingen:

```bash
python scripts/validate_schedule.py \
  --input data/season_2026-2027.tsv \
  --schedule docs/ortools_2026-2027_*.json
```

HARD = mag nooit voorkomen (baan dubbelgeboekt, S/D of D/GD tegelijk, te veel
spelers/banen tegelijk, start buiten venster, niet-planbare partij). MODEL =
zachte voorkeuren (compact ≤2 speelblokken, één baan-paar per team, jeugd-late
starts). Conform het niet-blocking-beleid worden afwijkingen gerapporteerd, niet
geblokkeerd.

## Resultaten per speeldag

| Datum | Thuisteams | Partijen gepland | HARD | MODEL | Status |
|---|---|---|---|---|---|
| 06-09-2026 | 8  | 48/48 | 0 | 0 | OPTIMAL/FEASIBLE, geen afwijkingen |
| 13-09-2026 | 10 | 58/62 | 1 (4 partijen NIET_GELUKT) | 0 | FEASIBLE binnen tijdslimiet; 4 partijen niet inpasbaar (zie hieronder) |
| 20-09-2026 | 9  | 51/51 | 0 | 0 | OPTIMAL/FEASIBLE, geen afwijkingen |
| 27-09-2026 | 11 | 58/66 | 1 (8 partijen NIET_GELUKT) | 0 | FEASIBLE binnen tijdslimiet; 8 partijen niet inpasbaar (zie hieronder) |
| 04-10-2026 | 11 | 64/64 | 0 | 0 | FEASIBLE binnen tijdslimiet, geen afwijkingen |
| 11-10-2026 | 3  | 19/19 | 0 | 0 | OPTIMAL/FEASIBLE, geen afwijkingen |

**Totaal:** 52 thuisteams / 6 zondagen, 298/310 partijen gepland, 2 dagen met HARD-afwijkingen (12 partijen totaal), 0 MODEL-afwijkingen.

Niet-geplande partijen (conform het niet-blocking-beleid gerapporteerd, niet
geblokkeerd):
- **13-09-2026** (4 partijen): Jongens 13-17 2e klasse Afd. 10 S3; Meisjes
  13-17 1e klasse Afd. 2 S2; Meisjes 13-17 3e klasse Afd. 3 D1 en S2.
- **27-09-2026** (8 partijen): Gemengd 4e klasse Afd. 2 S2; Gemengd 5e klasse
  Afd. 7 S1; Jongens 13-17 2e klasse Afd. 10 S1 en S4; Meisjes 13-17 3e klasse
  Afd. 2 S3 en S4 (plus 2 vergelijkbare partijen).

Dit zijn de twee dagen met de meeste thuisteams (10 resp. 11), waardoor de
baan-/tijdcapaciteit binnen het venster (uiterlijk 19:30) krap wordt. Een
langere solver-tijdslimiet of handmatige tweak van het tijdvenster op die twee
dagen kan dit mogelijk verder oplossen; voor nu wordt dit gerapporteerd zoals
de bestaande gold-standaard planning ook af en toe onplanbare partijen had.

Alle 13 tests in de bestaande testsuite slagen (`pytest -q`,
`scripts/timefold_test.py` faalt los hiervan al op `main` door een
niet-geïnstalleerde `timefold`-dependency).

## Bekende beperkingen

- De afleiding van wedstrijden/duur/singles/dubbels/mix uit de schema-tekst volgt
  de 2025-2026-conventies; onbekende schema's vallen terug op één dubbel-partij.
- Rood/Oranje-reserveringen zitten niet in de zondag-export en zijn dus niet
  meegepland.
- De solver draait met een tijdslimiet per dag; grote dagen (11 teams) kunnen
  `FEASIBLE` i.p.v. `OPTIMAL` opleveren binnen de limiet — dit is geen regelbreuk,
  alleen geen bewezen optimum.
