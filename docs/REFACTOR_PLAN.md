# Refactorplan baanschema-planner

Status: voorstel, 2026-08-20. Gebaseerd op metingen aan `scripts/ortools_planner.py`
(commit `e1a65d9`).

## Uitgangspunt: waar staan we nu?

Alle 7 speeldagen, 30s tijdslimiet per dag, `.venv` met OR-Tools 9.15:

| datum | partijen | niet gepland | variabelen | constraints | status | gap |
|---|---|---|---|---|---|---|
| 06-04-2026 | 49 | 2 | 17.622 | 75.441 | FEASIBLE | 5,18% |
| 10-05-2026 | 75 | 6 | 28.665 | 127.486 | FEASIBLE | 12,03% |
| 12-04-2026 | 69 | 5 | 26.725 | 117.633 | FEASIBLE | 9,92% |
| 17-05-2026 | 73 | 9 | 28.144 | 110.226 | FEASIBLE | 16,91% |
| 19-04-2026 | 72 | 6 | 27.765 | 128.937 | FEASIBLE | 10,59% |
| 25-05-2026 | 62 | 12 | 23.467 | 129.093 | FEASIBLE | 0,10% |
| 31-05-2026 | 58 | 0 | 22.582 | 112.735 | FEASIBLE | 0,39% |
| **totaal** | **458** | **40 (8,7%)** | | | **0× OPTIMAL** | |

Twee dingen vallen op.

**Geen enkele dag wordt OPTIMAL.** Op vijf van de zeven dagen zit de solver na
30 seconden nog op 5-17% gap. Het probleem is klein — maximaal 75 partijen, 10
banen, 46 kwartierslots — dus dat is geen probleemcomplexiteit maar
modelomvang: 110.000 tot 129.000 constraints voor 75 taken.

**Op 25-05 is de gap 0,10% en blijven er tóch 12 partijen liggen.** Daar is de
oplossing dus bijna bewijsbaar optimaal en zijn die 12 partijen geen zoekprobleem
maar een gevolg van de harde constraints (zie observatie 3). Op 17-05 is het
omgekeerd: 16,91% gap, daar valt met een beter model nog winst te halen.

Dat onderscheid — "kan de solver het niet vinden" versus "mag het niet van de
regels" — is nu niet zichtbaar in de output. Dat maakt elke discussie over
niet-geplande partijen een gok.

## Observatie 1 — 93% van het model komt uit vier regels

Constraints geteld per bronregel (datum `06-04-2026`):

| regel | aantal | % | wat het doet |
|---|---|---|---|
| `ortools_planner.py:446` | 26.112 | 35% | singles vóór doubles, paarsgewijs over alle starttijdcombinaties |
| `ortools_planner.py:661` | 14.870 | 20% | koppeling `x` → `pair_active` (banenpaar per team) |
| `ortools_planner.py:670` | 14.870 | 20% | koppeling `x` → `use_c` (baan in gebruik) |
| `ortools_planner.py:456` | 14.526 | 19% | `pair_same_start`: S1+S2 gelijk starten, paarsgewijs |
| overige ~40 regels | 5.031 | 7% | |

De eerste en de vierde zijn kwadratisch in het aantal starttijden: voor elk paar
partijen wordt élke combinatie van starttijden verboden. Met ~40 toegestane
starts per partij is dat 40 × 40 = 1.600 constraints om één precedentie uit te
drukken.

Met een integer starttijdvariabele is dat precies één constraint:

```python
# nu (regel 440-446): 1.600 constraints per (S, niet-S) paar
for s_s in allowed_starts[si]:
    for s_n in allowed_starts[ni]:
        if s_n < s_s + dur_s:
            model.add(start_used[(si, s_s)] + start_used[(ni, s_n)] <= 1)

# straks: 1 constraint
model.add(start[ni] >= start[si] + dur_s)
```

Idem voor `pair_same_start` → `model.add(start[i0] == start[i1])`, en voor de
baankoppelingen → één `court[i]` integer-variabele met domein `{ca, cb}` in
plaats van 14.870 implicaties.

Het model heeft die integer-variabelen trouwens al: regel 713-724 bouwt
`start_i` en `end_i` als gewogen som van `x`. Ze worden alleen niet gebruikt om
constraints op te leggen, alleen voor de span-penalty. De refactor is dus vooral
*bestaande variabelen tot hoofdvariabelen promoveren*, niet iets nieuws bedenken.

## Observatie 2 — bug: S/D-niet-tegelijk geldt op één tijdslot — OPGELOST (`067d725`)

`ortools_planner.py:462-502` bouwt de "singles en dubbels mogen niet tegelijk"-
constraints, maar er staat geen `for t in slot_mins` boven. De variabele `t`
lekt uit de loop op regel 410 en is daar altijd `19:45` — het laatste slot.

Gevolg: die constraint wordt voor precies één tijdslot opgelegd en is verder
inactief. Het blok zit door de indentatie ook binnen `if not team_is_mixed:`,
wat waarschijnlijk niet de bedoeling was (de comment op 462 suggereert dat het
op teamniveau hoort).

Dat het schema er toch redelijk uitziet, komt doordat de
speler-resourceconstraints (regel 504-545, `team_occ_terms <= 2` en
`total_terms <= 4`) per slot wél kloppen en een deel van hetzelfde afdekken.
Maar de bedoelde regel wordt niet gehandhaafd.

## Observatie 3 — de harde 11:00-grens kost 2 partijen

Commit `e1a65d9` maakte "Jeugd 13-17 start ≥ 11:00" een harde constraint
(`ortools_planner.py:387`). Getest op `06-04-2026`:

| variant | niet-gepland |
|---|---|
| hard ≥ 11:00 (nu) | 2 (beide `Meisjes 13 t/m 17` D1) |
| ≥ 09:00 | 0 |
| alle zachte gewichten op 0, hard ≥ 11:00 | 2 |

De derde regel is het bewijs dat het geen gewichtenkwestie is: met alle soft
weights op nul blijven die twee partijen onplanbaar. De 100%-middagstart is dus
gekocht met twee partijen die niet gespeeld worden.

Dat is een beleidskeuze, niet per se een bug — maar het moet een expliciete keuze
zijn. Een zachte constraint met een gewicht boven de andere comfort-termen geeft
100% middagstart wanneer het kan, en wijkt af wanneer het alternatief is dat er
niet gespeeld wordt.

## Observatie 4 — de objective is niet echt lexicografisch

De objective (regel 801-822) is één gewogen som met stappen van 1e9 (gepland),
5e6, 4e6, 2e5 … De bedoeling is lexicografisch, maar dat is niet afgedwongen:

- `w_team_span * span` met span in *minuten* levert tot ~138M per team;
- de slack-term (`w_team_span * 4`) tot ~552M per team;
- bij 17 teams zit de totale span-penalty in dezelfde orde als de 1e9 per
  geplande partij.

De marge waarmee "plan alles" wint van "houd het compact" is dus ongeveer een
factor 1,3 — niet de factor 1000 die de gewichten suggereren. Bij een drukkere
dag of een extra team kan dat kantelen zonder dat iemand het merkt.

Daarnaast is `jeugd_middag_penalty` (regel 788-799, gewicht 5.000.000) dode
code: het vult alleen termen voor `s < 11*60`, maar `allowed_starts` filtert die
starts sinds `e1a65d9` al hard weg. De lijst is altijd leeg.

## Observatie 5 — het cuOpt-spoor

Tien scripts (`cuopt_planner.py`, `_v3`, `.backup-continuous`, `_binary`,
`_simple`, `_vrp`, `_vrp_v2`, `_workforce`, `_minimal`, plus twee
introspectie-helpers), samen ~3.500 regels, waarvan geen enkele ooit gedraaid
heeft: cudf 26.4.0 gebruikt `pandas.api.types.is_interval`, verwijderd in pandas
2.2.

Voor 49 taken en 10 banen is een GPU-MILP het verkeerde gereedschap. Het
GPU-voordeel van cuOpt zit bij LP-relaxaties met honderdduizenden rijen; hier
verlies je juist de expressiviteit (geen intervals, geen no-overlap, alles via
big-M met handmatig getunede M-constanten) die dit probleem makkelijk maakt.

## Observatie 6 — twee teams met hetzelfde schema worden één team — OPGELOST (`067d725`)

`ortools_planner.py` groepeert teams op de schemanaam:

```python
by_team = defaultdict(list)
for i, p in enumerate(parts):
    by_team[p["team"]].append(i)      # p["team"] is t.schema
```

Op twee speeldagen komt hetzelfde schema twee keer voor, met verschillende
thuisteams:

| datum | schema | aantal |
|---|---|---|
| 17-05-2026 | `Gemengd Zondag – 5e klasse (DE-HE-GD-DD-HD) – Afdeling 10` | 2 |
| 25-05-2026 | `Meisjes 13 t/m 17 jaar Zondag – 2e klasse – Afdeling 16` | 2 |

Die twee teams worden dan als één team behandeld voor élke teamregel: samen
maximaal 4 spelers, samen 2 banen, samen één baanpaar, samen 2 speelblokken, en
S-vóór-D over de teamgrens heen. Twee teams van vier spelers moeten dus samen
met vier spelers op twee banen twaalf partijen spelen. Dat kan niet.

Gemeten effect op 25-05-2026, alleen door beide teams een eigen sleutel te geven:

| variant | niet gepland |
|---|---|
| nu (samengevoegd) | 12 van 62 |
| unieke teamsleutel | 2 van 62 |

Alle twaalf niet-geplande partijen op die dag zijn precies de twee slates van
zes van die twee teams. Op 17-05 verandert het niets (9 blijft 9), omdat
gemengde teams veel minder teamregels krijgen — geen S-vóór-D, geen rondeparen —
en de samenvoeging daar dus minder pijn doet.

`build_pages.parse_input` bouwt al een unieke `team_id`
(`datum::schema::thuis::uit`); `ortools_planner.parse_input` niet. De uitvoer
zet ook `team_id = p["team"]`, dus de twee teams zijn in de JSON evenmin te
onderscheiden — de validator meldt dat als `AMBIGU-TEAM`.

Dit is de eerste fix die ik zou doen na de validator: hij is klein, en levert
op één dag tien partijen op.

## Observatie 7 — CI is rood sinds 8 juni — OPGELOST

`pytest -q` verzamelt ook `scripts/timefold_test.py`, dat `timefold` importeert.
Dat pakket staat niet in `pyproject.toml`, dus de collectie faalt en daarmee de
hele testrun. De laatste geslaagde `CI`-run op `main` is van vóór 8 juni; alleen
`Deploy GitHub Pages` is nog groen.

Gevolg: de bestaande tests in `tests/` hebben maanden niets meer bewaakt.

## Plan

### Stap 1 — validator eerst (vangnet) — UITGEVOERD

`scripts/validate_schedule.py` toetst een resultaat-JSON tegen `season.tsv` en
`docs/planningsregels.md`, los van welke solver hem gemaakt heeft. Hij leest de
drie bestandsvormen in de repo (OR-Tools per dag, gold en heuristiek per seizoen).

Bevindingen zijn gesplitst in twee soorten:

- **HARD** — een regel uit `docs/planningsregels.md`. Een overtreding is een fout.
- **MODEL** — een extra constraint die het CP-SAT model oplegt maar die niet in
  de planningsregels staat. Zichtbaar maken welke daarvan het handmatige
  gold-schema breekt, wijst precies de constraints aan die te streng zijn.

Stand bij invoeren:

| bron | partijen | HARD | MODEL |
|---|---|---|---|
| gold (handmatig) | 458/458 | 7 | 70 |
| heuristiek | 456/458 | 1 | 91 |
| OR-Tools (gecommitte artefacten) | 428/458 | 30 | 0 |

Wat dat oplevert:

**Het gold-schema haalt op 6 van de 7 dagen alle harde regels.** De 7
overtredingen zitten allemaal op 25-05: zes keer een Groen-partij van 45 minuten
waar `season.tsv` 90 zegt, en één keer singles en dubbels tegelijk bij JU11-14.
Dat zijn dus vragen over de brondata en over de regel zelf, niet over het schema.

**Gold breekt de jeugd-11:00-regel 68 keer.** De handmatige planner laat Jeugd
13-17 om 09:00 en 10:30 starten. De harde grens uit `e1a65d9` spreekt het
referentieschema dus rechtstreeks tegen. Samen met observatie 3 (die grens kost
partijen) is dat voldoende grond om hem zacht te maken.

**Gold breekt de baanregels niet.** Geen enkele `BAANPAAR`- of
`BANEN-PER-TEAM`-bevinding. Die MODEL-constraints mogen dus blijven. De
heuristiek breekt ze wel (25 + 9), dus daar wijkt de heuristiek af van het
handmatige schema, niet het model.

**De OR-Tools uitvoer overtreedt 14 keer een harde regel.** Allemaal
`SOORT-CONFLICT`: singles en dubbels tegelijk binnen één team. Dat is observatie
2 zichtbaar in de uitvoer in plaats van alleen in de code.

Verder toegevoegd:

- `--max-hard N` / `--max-model N`: een ratchet voor CI. Faalt bij meer
  overtredingen (regressie) én bij minder (dan hoort het plafond omlaag, zodat
  winst vastligt).
- `src/baanschema/rules.py`: `build_parts` en `player_demand` staan nu één keer,
  gedeeld door planner en validator. Anders zou de validator de regels nabouwen
  en met een fout in de planner mee kunnen groeien in plaats van hem te vinden.
  Nagerekend: identieke uitkomst voor alle 458 partijen.
- `tests/test_validate_schedule.py`: 16 tests. Naast de hulpfuncties toetsen ze
  dat het gold-schema van 06-04 schoon door de HARD-regels komt, en dat de
  validator een geïntroduceerde baanoverlap, te late start, niet-bestaande baan,
  tijd buiten het raster, ontbrekende partij, dubbele partij en verkeerde
  wedstrijdduur ook echt vindt.
- `testpaths = ["tests"]` in `pyproject.toml`, wat observatie 7 oplost.
- CI-job `validate-schedules` met de drie ratchets hierboven.

### Stap 2 — twee kleine bugfixes, los van de refactor — UITGEVOERD (`067d725`)

Beide met de validator ervoor en erna, zodat het effect meetbaar is.

**2a. Unieke teamsleutel (observatie 6).** Geef `ortools_planner.parse_input`
dezelfde `team_id` als `build_pages.parse_input` en groepeer `by_team` daarop in
plaats van op `t.schema`. Zet die `team_id` ook in de uitvoerrijen. Verwachting:
25-05 gaat van 12 naar 2 niet-geplande partijen, en `AMBIGU-TEAM` verdwijnt uit
het validatierapport.

**2b. De S/D-bug (observatie 2).** Zet de ontbrekende `for t in slot_mins`-loop
terug en bepaal of het blok binnen `if not team_is_mixed:` hoort. Verwachting:
de 14 `SOORT-CONFLICT`-bevindingen verdwijnen, en sommige dagen worden krapper
omdat een constraint gaat gelden die er nooit echt was. Doe deze ná 2a, zodat je
de twee effecten niet door elkaar meet.

### Stap 3 — herschrijf naar intervals + integer-variabelen (observatie 1)

Nieuw bestand `src/baanschema/model_cpsat.py`, zodat
`scripts/ortools_planner.py` intact blijft als referentie tot de nieuwe versie
bewijsbaar even goed is.

Per partij `i`:

```python
start[i]  = model.new_int_var_from_domain(Domain.from_values(allowed_starts[i]), ...)
court[i]  = model.new_int_var(1, 10, ...)
present[i] = model.new_bool_var(...)
iv[i] = model.new_optional_interval_var(start[i], dur[i], end[i], present[i], ...)
```

Dan:

- **baanbezetting**: per baan `c` een `AddNoOverlap` over de optionele intervals
  met `court[i] == c`, via een tweede laag optionele intervals per (partij, baan).
  Vervangt regel 409-422 én meteen de reserveringen (vaste intervals toevoegen).
- **S vóór D**: `model.add(start[d] >= start[s] + dur_s)` — vervangt 26.112 door
  ~30 constraints per team.
- **ronde-paren**: `model.add(start[i0] == start[i1])` — vervangt 14.526 door 1
  per paar.
- **banenpaar**: `pair[t]` als IntVar 0-4, `model.add_allowed_assignments` of
  `add_element` om `court[i]` aan het paar te binden — vervangt 29.740 door ~2
  per partij.
- **speler-resource per slot**: blijft grotendeels zoals nu (regel 504-545);
  eventueel later `add_cumulative` met capaciteit 4 per team.

Verwachting: van 75k-129k naar enkele duizenden constraints, en OPTIMAL binnen
seconden in plaats van 5-17% gap na 30s. Dat is de aanname die stap 5 moet
toetsen — als het model klein is en de gap blijft groot, zit het probleem elders
en is stap 4 belangrijker dan stap 3.

### Stap 4 — objective lexicografisch oplossen (observatie 4)

In plaats van één som met magische gewichten: los in fasen op, met de vorige
uitkomst als harde bovengrens.

```python
PRIORITEITEN = [
    ("gepland",        maximize, aantal_geplande_partijen),
    ("blokken",        minimize, som_speelblokken),
    ("jeugd_middag",   minimize, jeugd_starts_voor_11),   # was hard, nu prio 3
    ("span",           minimize, som_team_slack),
    ("banen",          minimize, hoge_banen + spreiding),
    ("comfort",        minimize, late_starts),
]
```

Per niveau: optimaliseer, lees de waarde, voeg `model.add(term == waarde)` toe
(of `<= waarde + tolerantie` voor speelruimte), ga naar het volgende niveau.
Voordelen:

- je weet per regel of je optimaal zit, in plaats van één objective van 4,6e10;
- geen gewichtenkalibratie meer, dus `tune_ortools_weights.py` en
  `tune_ortools_search.py` kunnen weg;
- de jeugd-11:00-regel wordt een prioriteit in plaats van een harde grens, dus
  100% middagstart wanneer het kan en 0 niet-geplande partijen wanneer het moet
  (observatie 3).

Dit vervangt ook de twee-fase-aanpak (`solve_day_two_phase`, regel 185-291), die
nu twee solves in threads doet en de beste kiest — een work-around voor precies
dit gewichtenprobleem. Kanttekening: die functie splitst teams op
schema-naam-substrings en een team dat in geen van beide filters valt verdwijnt
stil uit de planning. Nu zijn er 0 zulke teams van de 22 schema's, maar het is
een valkuil bij nieuwe schema's.

### Stap 5 — vergelijkingsrapport oud vs nieuw

`scripts/compare_models.py` dat over alle 7 datums beide modellen draait en een
tabel geeft: niet-gepland, blokken, gemiddelde span, jeugd-middagstarts,
banen>4, solve-tijd, status, gap. De baseline hierboven is de nulmeting:
**40 niet-geplande partijen van 458, 0× OPTIMAL**. Pas als de nieuwe versie op alle regels
gelijk of beter is, wordt hij de default in `build_pages.py`.

Neem `docs/gold_result.json` mee als derde kolom — dat is de handmatige planning
en de eigenlijke maatstaf.

### Stap 6 — warm starts

`model.add_hint()` vullen met de vorige oplossing voor die datum (uit
`docs/ortools_<datum>.json`) of met de heuristiek. In de praktijk vaak de
grootste snelheidswinst, maar pas nuttig als het model klein is — anders
optimaliseer je de verkeerde bottleneck. Daarom ná stap 3.

### Stap 7 — cuOpt-spoor afsluiten

- `scripts/cuopt_*.py` en `scripts/inspect_cuopt_*.py` → `experiments/cuopt/`,
  met een `README.md` die de conclusie vasthoudt: formulering compleet, nooit
  gedraaid door cudf/pandas, en niet de moeite waard bij deze probleemgrootte.
- `scripts/timefold_*.py` → `experiments/timefold/` met dezelfde behandeling.
- `COMPLETION_SUMMARY.md` en `TEST_CUOPT.md` daarheen verplaatsen.
- `scripts/cuopt_planner.py.backup-continuous` weg.
- Alleen als je het experiment met cijfers wilt afsluiten: één run in
  `nvidia/cuopt:25.12.0a-cuda12.9-py3.13` voor het rapport. Optioneel.

Dit haalt ~3.500 regels ongebruikte code uit `scripts/`, waar nu 24 bestanden
staan waarvan 4 in gebruik zijn.

## Volgorde en risico

| stap | risico | omkeerbaar |
|---|---|---|
| 1 validator | geen (voegt alleen toe) | ja |
| 2 S/D-bug | kan dagen krapper maken | ja, kleine commit |
| 3 intervals | grootste wijziging, nieuw bestand naast oud | ja |
| 4 lexicografisch | verandert uitkomsten zichtbaar | ja |
| 5 vergelijking | geen | ja |
| 6 hints | geen | ja |
| 7 opruimen | geen (git bewaart alles) | ja |

Stap 1 en 2 zijn los waardevol, ook als de refactor niet doorgaat. Stap 3 is de
kern. Stap 7 kan op elk moment.

## Open vragen

1. **Is "alle partijen gepland" absoluut hoger dan "jeugd in de middag"?** Stap 4
   gaat daarvan uit (observatie 3). Als Oscar liever 2 partijen laat vallen dan
   een jeugdteam om 09:00 laat starten, moeten die twee prioriteiten omgewisseld.
2. **Mag de S-vóór-D-regel per team verschillen?** Nu geldt hij strikt voor
   niet-gemengde teams en niet voor gemengde. Dat lijkt uit de Gold-analyse te
   komen, maar staat niet in `docs/planningsregels.md`.
3. **Is de 2-blokken-grens (regel 639) hard bedoeld?** Hij is nu hard én er is
   een soft penalty op hetzelfde (`long_gap`). Dat is dubbelop.
4. **Duren Groen-partijen 45 of 90 minuten?** `season.tsv` zegt 90 voor
   `GRO Groen 2 M3` op 25-05, het gold-schema plant ze op 45. Eén van de twee
   is fout; de planner rekent nu met 90.
5. **Mogen singles en dubbels echt nooit tegelijk?** `planningsregels.md` zegt
   het zonder uitzondering, maar het gold-schema doet het één keer (JU11-14 op
   25-05) en het CP-SAT model sluit gemengde teams er helemaal van uit. Drie
   bronnen, drie antwoorden.
