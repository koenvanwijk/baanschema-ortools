# Baanschemaatje

Generieke baanschema-planner voor **elke** tennisvereniging. Input: de
KNLTB-wedstrijdexport + een clubprofiel (aantal banen, dagtijden, optionele
reserveringen). Output: automatisch een **eerste baanschema-voorstel** per
speeldag, dat de club daarna handmatig kan bijsturen.

Baanschemaatje staat **naast** de bestaande Baanschema-stack. Het wijzigt niets
aan `scripts/`, `data/`, `docs/*.html|json`, `backend/` of de workflows; de live
pagina (`mierlo-2026-2027.html`) blijft draaien zoals hij draait. Mierlose T.V.
is hier gewoon het eerste clubprofiel — geen speciaal geval.

Specificatie: [`docs/SPEC-core.md`](../../docs/SPEC-core.md) · roadmap:
[`ROADMAP.md`](../../ROADMAP.md).

## Gebruik

```bash
pip install -e .            # vanuit de repo-root (ortools zit al in de deps)

python -m baanschemaatje check --club clubs/voorbeeld-6-banen.yaml
python -m baanschemaatje dates --season data/season_2026-2027.tsv
python -m baanschemaatje plan  --club clubs/voorbeeld-6-banen.yaml \
    --season data/season_2026-2027.tsv --date 06-09-2026
```

Uitvoer: `out/baanschemaatje/<club>_<datum>.json` (gitignored; nooit `docs/`).
Het rij-formaat is gelijk aan dat van `scripts/ortools_planner.py`, dus de
bestaande validator werkt erop:

```bash
python scripts/validate_schedule.py out/baanschemaatje/mierlose-t-v_06-09-2026.json \
    --season data/season_2026-2027.tsv
```

## Opbouw

| Module | Rol |
|---|---|
| `categories.py` | KNLTB-categorieën (Rood, Oranje, Groen, Junioren 11–14, Jeugd 13–17, Gemengd, Senioren) + **core-defaults** voor speelduur en inplan-prioriteit |
| `profile.py` | Clubprofiel laden (YAML/JSON) + valideren; generieke regel-defaults (`CORE_RULE_DEFAULTS`) |
| `miniyaml.py` | YAML-lezer: PyYAML als die er is, anders een kleine ingebouwde parser (geen extra dependency) |
| `season.py` | KNLTB-export (TSV) → genormaliseerd `Season`/`Fixture`-model (read-only) |
| `planner.py` | CP-SAT-planner voor één speeldag met configureerbaar aantal banen |
| `cli.py` | `python -m baanschemaatje` |

## Clubprofiel

Zie `clubs/mierlo.yaml` (10 banen, vaste Rood/Oranje-banen, baanparen) en
`clubs/voorbeeld-6-banen.yaml` (fictief, 6 banen, geen reserveringen).

```yaml
club:
  name: "TV Voorbeeld"
  knltb_name: "VOORBEELD"     # teamnaam in de KNLTB-export
courts:
  count: 6
day:
  start: "09:00"
  fallback_start: "08:30"     # optioneel; alleen als start onplanbaar is
  last_start: "19:30"
  end: "20:00"
reservations:                 # optioneel, alleen voor rood/oranje
  rood:
    courts: [1]
  oranje:
    courts: [1, 2, 3]
    courts_if_rood: [2, 3, 4]   # als Rood dezelfde dag speelt
court_assignment:             # optioneel
  max_courts_per_team: 2
  pairs: [[1, 2], [3, 4]]     # optioneel: team speelt op één vast paar
  preferred_courts_8p: [1, 2, 3, 4]
rules:                        # optioneel: overrides op de core-defaults
  first_start_deadline:
    time: "15:00"
    hard: false
durations: {}                 # optioneel, alleen met expliciete reden
```

Speelduur: clubprofiel-override → duur uit de KNLTB-export → core-default
(Rood 60, Oranje 120, Groen 45, Junioren 11–14 45, Jeugd 13–17 90, Gemengd 90,
Senioren 90).

### Regels (core-defaults, per club hard/zacht te zetten)

| Regel | Default |
|---|---|
| `mixed_8p_not_before` | Gemengd 8p niet vóór 10:00 — hard |
| `start_window_8p` | eerste partij 8p-team tussen 10:00 en 11:00 — hard |
| `youth_last_start` | jeugd start uiterlijk 17:30 — hard |
| `first_start_deadline_junioren` | eerste partij Junioren ≤ 13:00 — zacht |
| `first_start_deadline` | eerste partij elk team ≤ 15:00 — zacht |
| `max_wait_minutes` | max 60 min wachten tussen partijen — hard |
| `max_blocks_per_team` | max 2 speelblokken per team — hard |
| `waterfall_8p` | strikte S → D → GD + rondes voor 8p-teams — hard |

Altijd hard (niet configureerbaar): 15-min-grid, max 1 partij per baan,
`max_courts_per_team` gelijktijdig, max 4 spelers tegelijk per team (gemengd:
2 heren + 2 dames), singles vóór de rest bij niet-gemengde teams, Rood/Oranje
als blok vanaf dagstart.

## Wat is geport uit `scripts/ortools_planner.py`

Geport (generiek gemaakt): kwartiergrid; baancapaciteit; Rood/Oranje-blokken
(nu uit het profiel, of solver-gekozen banen zonder reservering); singles-eerst
en rondes (paren tegelijk); 8p-waterval S → D → GD; spelerscapaciteit incl.
gemengd 2H+2D; max banen per team; optionele vaste baanparen; max 2 blokken;
max 60 min wachten; Gemengd-8p ≥ 10:00; jeugd ≤ 17:30; zachte
eerste-start-deadline; dagstart 09:00 met terugval 08:30; NIET_GELUKT-rijen.

Nieuw t.o.v. het origineel: aantal banen/dagtijden/regels uit het profiel;
8p-startvenster 10:00–11:00 ook aan de bovenkant afgedwongen (SPEC-core §2);
Junioren-deadline 13:00 als zachte regel; inplanvolgorde (SPEC-core §4) als
zachte voorkeur op vroege slots.

**Nog niet geport / bewust weggelaten:**

- Zachte fasering voor niet-8p-teams (S/D/GD-overlap-penalty) en de
  "dubbels eerst bij 1–2 vrije banen"-startregel.
- Ochtend-/totaalbezetting-bonussen en de afzonderlijke span-slack-term;
  compactheid loopt nu via blokken + actieve slots + baanspreiding.
- Specifieke leeftijdsvoorkeuren (Jeugd 13–17 liever na 11:00, Junioren-bonus
  vóór 11:00) — vervangen door de generieke prioriteitsvolgorde.
- Datum-specifieke cutoff-uitzonderingen (hardcoded datums in het origineel).
- Twee-fasen-modus (fase A/B) en de gewichten-CLI.
- Echte lexicografische oplossing: geprobeerd (fase 1 = alleen aantal
  partijen), maar zocht trager; nu net als het origineel een gewogen doel.
- Baan-geheugen (SPEC-core §3), waarschuwingstags (§6), seizoensbrede runs,
  herplan op de wedstrijddag, UI.

## Tests

```bash
pytest -q tests/generiek
```
