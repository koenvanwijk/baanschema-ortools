# ROADMAP — Baanschemaatje

**Productnaam:** **Baanschemaatje** — het generieke baanschema-product voor elke tennisvereniging (code: package `baanschemaatje`, CLI `python -m baanschemaatje`). De bestaande Baanschema-stack op `main` blijft ongewijzigd draaien.

**Branch:** `product/generiek` (vanaf `main`)  
**Status:** productrichting vastgelegd — 2026-10-05  
**Solver:** OR-Tools CP-SAT (enige productpad)

## Houding (belangrijk)

Baanschemaatje is een **generiek product** voor elke tennisvereniging. Er is geen “hoofdclub”.

- **Mierlose T.V.** is het **eerste clubprofiel** en de eerste referentie-implementatie — niet een uitzondering op de regels.
- Elke andere vereniging kan hetzelfde pad volgen: clubprofiel + KNLTB-data → automatisch voorstel.
- Club-specifieke keuzes (park-layout, seizoenbestanden, UI-copy) horen in een **clubprofiel-document** (nu: `SPEC-mierlo.md` als voorbeeld). De productkern staat in `SPEC-core.md`.

## Doel

1. Input: KNLTB-data (platte export; later bij voorkeur een koppeling).
2. De vereniging configureert haar clubprofiel (aantal banen, openingsuren, optionele reserveringen).
3. Baanschemaatje maakt automatisch een **eerste baanschema-voorstel**.
4. Dat voorstel kan later handmatig worden aangepast.
5. Later stadium: herplannen op een wedstrijddag (uitloop / uitvallers) en een clubdashboard.

**KNLTB-standaard in de core:** Rood, Oranje, Groen en jeugd 11 t/m 14 zijn generieke competitiecategorieën (SPEC-core), inclusief standaard speelduur **45 min** voor Groen en jeugd 11–14. Een clubprofiel mag duur of *baan*reserveringen alleen met expliciete reden overschrijven; de categorieën zelf blijven core.

## Out of scope (nu)

- cuOpt / Timefold als productpad (experimenten archiveren of expliciet als experiment houden).
- KNLTB live-API als blocker voor fase 1 (eerst export; koppeling als parallel spoor).
- Multi-tenant SaaS-billing, accountsysteem voor meerdere verenigingen tegelijk.

## Fases

### Fase 0 — Baken

**Succescriteria**

- Documentatie splitst productkern (`SPEC-core`) en clubprofiel-voorbeeld (`SPEC-mierlo` = eerste referentie, niet “de” SPEC).
- README “volgende stappen” wijst naar deze ROADMAP.
- Open P0-issues zijn aangemaakt (titels zie onder).

**Deliverables**

- `ROADMAP.md` (dit bestand)
- `docs/SPEC-core.md`
- `docs/SPEC-mierlo.md` (eerste clubprofiel)
- Index `docs/SPEC-INDEX.md` (wegwijzer); de operationele `docs/SPEC.md` blijft ongewijzigd zoals op `main`

### Fase 1 — Automatisch eerste voorstel (MVP)

**Succescriteria**

- Voor **elk** clubprofiel (N banen, openingsuren, optionele reserveringen) + genormaliseerd seizoen uit KNLTB-**export** levert de pipeline één geldig dag-/seizoensvoorstel.
- Geen hardcodes van één club (vaste N, vaste court-pairs, vaste seizoenpaden) in de planner-kern.
- Validator + CI toetsen tegen SPEC-core.
- Het eerste clubprofiel (Mierlo) valideert het pad; het mag geen aannames in de kern hinterlaten.

**Deliverables**

- Club-configmodel (generiek)
- Import: export → genormaliseerd seizoenmodel
- CP-SAT met configureerbaar aantal banen
- Minimale UI: voorstel bekijken + exporteren

### Fase 2 — Handmatig bijsturen

**Succescriteria**

- Editor werkt tegen een generieke API (club/seizoen-storage).
- Schrijven vereist auth (issue 27 "Login per club"; tot dan staat de testomgeving open).
- Geen vaste club-URL’s of open write naar object storage in de productcode.

**Deliverables**

- Beveiligde schema-API
- Generieke editor (speeldagen + verplaatsen)
- Sync OR-draft ↔ handmatig goedgekeurd schema (geen valse TEAM-ONTBREEKT na verplaatsing)

### Fase 3 — Wedstrijddag + dashboard

**Succescriteria**

- Herplan van resterende partijen bij uitloop/uitval via **echte** solver (geen stub).
- Herplan volgt KNLTB Competitiereglement (11-11-2025) **Bijlage 3, 2.2**: verplicht zodra partijen ≥ 1 uur later worden gespeeld dan gepland; voorrang voor (a) afgebroken partijen, dan (b) teams met > 80 km reisafstand, dan (c) het volledig afspelen van hele wedstrijden boven delen van andere wedstrijden; art. 41 blijft gelden (2.3). Zie SPEC-core §7.
- Read-only clubdashboard (TV/tablet) op het actuele schema — bruikbaar voor elke club.

**Deliverables**

- `POST /replan` met CP-SAT
- Dashboard-pagina
- Optioneel offline/cache

## Parallel spoor (niet blocker)

**Spike KNLTB-koppeling:** mogelijkheden, auth, datamodel. Pas daarna “liefst koppeling” i.p.v. alleen export.

### Spoor Regelmaatje (KNLTB-regelhulp, AI) — parallel, niet blocker voor fase 1

Een AI-assistent in Baanschemaatje die de KNLTB-competitiereglementen kent en actueel houdt (de regels wijzigen vaak), en vragen beantwoordt over o.a. invallers, uitval, verplaatsen en opgave.

**Ontwerpprincipes**

- **Gegrond in officiële bronnen:** elk antwoord is gebaseerd op de officiële KNLTB-reglementdocumenten en citeert **artikel + versie/datum** van het reglement. Geen bron gevonden → dat expliciet zeggen, niet gissen.
- **Actueel houden:** geplande check op nieuwe reglementversies; wijzigingen landen in een **changelog** (wat is er veranderd, sinds welke versie/datum).
- **Officieel vs clubafspraak gescheiden:** KNLTB-regels (regelbank) staan los van clubafspraken (clubprofiel). Een antwoord maakt altijd duidelijk wat officieel reglement is en wat een afspraak van de eigen vereniging.
- **Adviseert, handelt niet:** de assistent wijzigt nooit zelf een schema; hij geeft advies, de mens (of de planner via een expliciete actie) beslist.

**Succescriteria**

- Antwoorden op een testset vragen (invallers, uitval, verplaatsen) bevatten correcte artikelcitaten met versie/datum.
- Een nieuwe reglementversie wordt automatisch gedetecteerd en in de changelog gezet.

## Acceptatie per fase

- CI groen op SPEC-core-tests.
- Geen HARD-violations op het referentieseizoen van het actieve clubprofiel, **of** expliciet getagd volgens §6-beleid in SPEC-core.
- Clubprofielen (te beginnen met Mierlo) zijn *configuratie + overrides*, geen parallel product.

## Issue-titels (aanmaken op de branch / in GitHub)

### Fase 0

1. Docs: ROADMAP.md toevoegen (fases 0–3, out-of-scope, succescriteria)
2. Docs: SPEC splitsen in SPEC-core.md en clubprofiel SPEC-mierlo.md (KNLTB Rood/Oranje/Groen/jeugd 11–14 + 45 min in core)
3. Docs: README “volgende stappen” laten wijzen naar ROADMAP; verouderde bullets opschonen
4. Chore: cuOpt/Timefold markeren als experiments/ (of PR #1 formeel als experiment)

### Fase 1

5. Feature: club-profielconfig (banen, uren, reserveringen, soft/hard toggles)
6. Feature: KNLTB-export → genormaliseerd seizoenmodel (geen club-hardcodes in de kern)
7. Refactor: ortools_planner los van vaste N-banen / vaste court-pairs uit één clubprofiel
8. Fix: begintijden volgens KNLTB CR Bijlage 3 in de planner-kern (core: gemengd 8p ≤ 14:00); 8p 10:00–11:00 als clubafspraak in het profiel
9. Decision: SPEC §6 — alles inplannen + tags vs NIET_GELUKT (één beleid in SPEC-core)
10. Feature: eerste-start-deadlines volgens CR Bijlage 3 (junioren 08:30–12:00, uiterlijk 13:00/15:00) + productdeadline overige teams
11. Test: CI-ratchet op SPEC-core; clubprofiel-fixtures (eerste: Mierlo) als voorbeelddata

### Fase 2

12. Security: auth op schema write-API
13. Chore: configureerbare API-basis-URL in frontend + docs (geen vaste club-URL in code)
14. Feature: generieke editor (speeldagen + verplaatsen) op club/seizoen-storage
15. Feature: OR-draft syncen met handmatig verplaatste partijen (geen valse TEAM-ONTBREEKT)
27. Security: **Login per club** — schrijven (clubinstellingen, seizoen-upload, later schema's) alleen na inloggen voor die club. Nu staat de clubpagina bewust open (besluit Oscar 09-10-2026); alle schrijfroutes van de live-backend lopen al via één hook (`server/baanschemaatje/auth.py`, `authorize_write`), zodat login daar zonder routewijziging in kan.

### Fase 3

16. Feature: POST /replan met echte CP-SAT op resterende partijen (voorrangsregels CR Bijlage 3, 2.2)
17. Feature: clubdashboard (read-only actueel schema, TV-vriendelijk)

### Spoor KNLTB

18. Spike: KNLTB-koppeling — mogelijkheden, auth, datamodel (geen implementatie)
26. Feature: reisafstand per tegenstander invullen (80 km-regel)

### Spoor Regelmaatje (KNLTB-regelhulp, AI) — parallel, niet blocker

22. Spike: bronnen KNLTB-reglementen + updatefrequentie
23. Feature: regelbank met versies en bronverwijzingen
24. Feature: Regelmaatje: AI-regelhulp met citaten (invallers, uitval, verplaatsen)
25. Feature: automatische check op nieuwe reglementversies

### P2 engineering (na MVP of parallel)

19. Refactor: model_cpsat.py (intervals) + lexico-fase-oplossen
20. Feature: compare_models.py (heuristiek / OR / goedgekeurd schema) als CI-rapport
21. Chore: .venv-local uit git; toy-package vs productie-scripts scheiden

## Branch-conventie

- Basis: `main` (huidige codebase; bevat o.a. het eerste clubprofiel in data/UI)
- Productlijn: `product/generiek`
- Features: `feat/<korte-slug>` vanaf `product/generiek` (één issue per branch waar mogelijk)
