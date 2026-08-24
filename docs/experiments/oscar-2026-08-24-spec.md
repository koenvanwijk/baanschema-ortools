# Oscar's baanschema-spec (24-08-2026)

> **Sinds 24-08-2026 vervangen door [`docs/SPEC.md`](../SPEC.md).** Dat is de
> leesbare masterversie van dezelfde regels en is gezaghebbend. Dit bestand
> blijft staan als archief van de aangeleverde systeemprompt en als
> verantwoording bij het experiment. De vergelijkingstabel onderaan zet Oscar's
> spec naast `planningsregels.md`, dat nu ook door `SPEC.md` is vervangen.

Bron: Discord `#baanschema`, gepost door superozz op 24-08-2026 (2x, met bijbehorende
Excel-export `export_processed_NJ2026...xlsx`). Letterlijk overgenomen als referentie
voor het experiment in `scripts/experiments/oscar_spec_planner.py`.

Zie ook: `data/experiments/oscar-2026-08-24-export_processed_NJ2026.xlsx` (aangeleverde
brondata, 6 zondagen sep/okt 2026).

> **Let op:** deze regels wijken op meerdere punten af van de bestaande,
> geteste productieregels in `docs/planningsregels.md` (zie vergelijking onderaan).
> Dit document is puur een archief van de aangeleverde tekst, geen vervanging.

---

## Systeemprompt (letterlijk)

Je bent een expert in constraint programming met Python en Google OR-Tools (CP-SAT).
Jouw taak is om een optimaal en efficiënt baanschema te genereren voor een
tennisvereniging op basis van de onderstaande vereisten. Genereer werkende Python
code die een dagplanning oplost en print/exporteert.

### 1. Data Model & Variabelen

- Park: 10 banen (index 0 t/m 9).
- Tijdlijn: 15-minuten blokken. Index 0 = 08:30, index 2 = 09:00, index 44 = 19:30.
  Maximale horizon is index 60 (23:30).
- Partij Data (Input): een lijst met dictionaries per partij, bevattende:
  `team_naam`, `match_type` (bijv. 'S1', 'D1', 'GD1', 'Mix1'), `duur_in_blokken`
  (Senioren/13-17=6, Junioren 11-14/Groen=3, Rood=4, Oranje=8), `team_categorie`
  (Rood, Oranje, 8-partijen-team, Groen, Junioren, Jongens/Meisjes, Gemengd, Heren).
- CP-SAT variabelen per partij `i`:
  - `start[i]` (IntVar: 0 tot max_horizon)
  - `end[i]` (IntVar: 0 tot max_horizon)
  - `interval[i]` (IntervalVar)
  - `baan_presences[i][b]` (BoolVar voor baan `b` van 0 t/m 9). Gebruik
    `OptionalIntervalVar` gekoppeld aan deze presence voor het NoOverlap constraint.

### 2. Harde Constraints (moeten voldaan worden)

- **Overlap:** `model.AddNoOverlap()` per baan `b` over alle optionele intervallen
  op die baan. Geen dubbele boekingen.
- **Exact 1 baan:** `model.AddExactlyOne(baan_presences[i])` per partij.
- **Rood & Oranje reserveringen:**
  - Als `team_categorie == 'Rood'`: start vast op index 2 (09:00) of index 0
    (08:30) op Baan 0 (Baan 1 in UI).
  - Als `team_categorie == 'Oranje'`: start vast op dezelfde index als Rood.
    Banen zijn Baan 0, 1, 2. (Als Rood ook speelt, verschuift Oranje naar
    Baan 1, 2, 3.)
- **Starttijd limieten** (eerste partij van het team, `min_start` over alle
  partijen van dat team):
  - Junioren (11-14): `min_start_team <= index 18` (13:00).
  - Overige (reguliere) teams: `min_start_team <= index 26` (15:00).
  - Gemengd teams: `start[i] >= index 6` (10:00) voor alle partijen.
  - 8-partijen teams (groot): `min_start_team >= index 6` (10:00) én
    `min_start_team <= index 10` (11:00).
- **Avond-deadline:** `start[i] <= index 44` (19:30) voor álle partijen. Indien
  model infeasible is, maak deze grens een soft-constraint met een gigantische
  penalty.
- **Interne Team Fasering** (Singles -> Dubbels -> Gemengd Dubbel):
  - Standaard: binnen één team moet `end[S] <= start[D]` voor alle S en D, en
    `end[D] <= start[GD]` voor alle D en GD.
  - Uitzondering 5-partijen team (bijv. 2S, 2D, 1GD): fase 1 = S én GD, fase 2 =
    D. Dus: `end[S] <= start[D]` en `end[GD] <= start[D]`. S en GD mogen
    tegelijkertijd.
  - Uitzondering 8-partijen team (bijv. 4S, 2D, 2GD): strikte waterval.
    `max(end[S]) <= min(start[D])` én `max(end[D]) <= min(start[GD])`.

### 3. Zachte Constraints / Objectives (minimaliseer penalty sum)

Gebruik een gewogen doelfunctie (`model.Minimize()`).

- **Prioriteit inplannen (gewicht 100):** geef teams met hogere prioriteit een
  lagere starttijd. Rood/Oranje > 8-partijen > Groen > Junioren >
  Jongens/Meisjes > Gemengd > Heren.
- **Compactheid team / teamflow (gewicht 50):** minimaliseer de span van een
  team. `span = max(end) - min(start)` van alle partijen binnen dat team. Hoe
  dichter dit bij de pure netto speelduur ligt, hoe beter. Extra penalty als
  een team lang op de club is.
- **Baan-cluster / memory (gewicht 30):** een team moet zoveel mogelijk op een
  vaste set (aangrenzende) banen blijven. Bereken per team `max_baan_index` en
  `min_baan_index`. Minimaliseer `spread = max_baan_index - min_baan_index`.
  Extra strafpunten als banen niet aaneengesloten zijn.
- **Voorkeursbanen 8-partijen teams (gewicht 20):** als
  `team_categorie == '8-partijen-team'`, penalty als `baan_presences[i][b] ==
  True` voor `b > 3`. (Probeer ze op baan 0, 1, 2, 3 te houden.)
- **Middag-breedte aanmoedigen (negatief gewicht / bonus):** als `start[i] >
  index 18` (13:00), beloon het model (verminder de penalty) als meerdere
  partijen van hetzelfde team exact dezelfde starttijd hebben. Dit moedigt aan
  om in de middag op 3 of 4 banen tegelijk te openen in plaats van te faseren
  over 2 banen.

### 4. Output / Foutafhandeling

- Als het model de harde tijdslimieten (19:30, 15:00, 13:00) niet haalt, crash
  de build dan niet, maar markeer de betreffende output regel met een
  tekst-tag zoals `[>19:30]`.
- Zorg dat het Python script de output groepeert per Tijdslot en Kolommen
  (Baan 1 t/m 10) uitprint.

---

## Verschillen t.o.v. `docs/planningsregels.md` (huidige productieregels)

| Onderwerp | Oscar's spec | Huidige productieregels (`ortools_planner.py`) |
|---|---|---|
| Rood/Oranje starttijd | Vaste index 2 (09:00) | Dynamisch: probeert 09:00, valt terug op 08:30 als dat leidt tot NIET_GELUKT of avond-overschrijding |
| Rood baan | Vast Baan 0 (Baan 1 UI) | Baan 1, of Baan 4 als Oranje ook speelt |
| Oranje banen | 0,1,2 (of 1,2,3 als Rood speelt) | 1,2,3 (vast, ongeacht Rood) |
| Start-limiet Junioren | Hard/soft cap 13:00 | Geen aparte Junioren-cap; wel Jeugd 13-17 hard `>=11:00` (ondergrens, niet bovengrens) |
| Start-limiet overig | Soft cap 15:00 | Datum-specifieke cutoffs (`first_cutoff`), zachte voorkeur via bonus, geen harde cap |
| Fasering S->D->GD | Simpel `end<=start` per fase | Rondestructuur (S1+S2 gelijk, S3+S4 gelijk), S/D/GD non-overlap per tijdslot, player-demand (man/vrouw) voor gemengde teams |
| Baan-toewijzing | Vrije keuze + spread-penalty | Harde baan-paren (1+2, 3+4, 5+6, 7+8, 9+10); team mag maar op 1 paar spelen |
| Teamcompactheid | Soft span-penalty | Harde eis: max 2 speelblokken per teamdag + soft slack-penalty |
| Middag-breedte bonus | Expliciete bonus voor gelijktijdige middagstarts | Niet aanwezig; wel age-based voorkeuren (Junioren vroeg, Jeugd 13-17 middag) |
| Validatie | Geen aparte validator in de spec | `scripts/validate_schedule.py` toetst output tegen `planningsregels.md`, met HARD/MODEL categorieën en CI-plafonds |

**Conclusie (Koen, 24-08-2026):** noch de bestaande heuristische planner, noch de
handmatige gouden standaard voldeden aan de "oude regels" zoals Oscar ze nu
verwoordt — de regels zijn dus sowieso aan discussie/herziening toe. Dit
experiment dient om te laten zien hoe Oscar's specifieke spec zich gedraagt op
de aangeleverde data, als input voor die discussie. Nog geen besluit genomen
welke regelset definitief wordt.
