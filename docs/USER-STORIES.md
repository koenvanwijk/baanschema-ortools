# User stories & beslissingen — Baanschemaatje

Levend brondocument voor **alle** beslissingen en requirements van het project (branch `product/generiek`).
Laatst bijgewerkt: 14-10-2026 (avond).

## Werkprincipe

- **Elke beslissing en elke requirement** wordt in dit document vastgelegd als user story:
  *Als &lt;rol&gt; wil ik &lt;wens&gt;, zodat &lt;doel&gt;* + **acceptatiecriteria** + **status** + **datum** + **bron**.
- Wijzigt een beslissing of requirement, dan wordt dit document **in dezelfde commit** bijgewerkt.
- Status: `gepland` · `in uitvoering` · `gereed` · `uitgesteld` · `vervallen` · `open vraag`.
- Bron: wie/waar (bv. "Oscar, chat 14-10-2026", "SPEC-core.md", commit-hash).
- Detailregels (KNLTB, parameters) blijven in [`SPEC-core.md`](./SPEC-core.md) en [`SPEC-mierlo.md`](./SPEC-mierlo.md); dit document verwijst ernaar.
- Werkwijze: **kleine stappen**; `main` en de live Mierlo-pagina worden nooit gebroken.

Rollen: **TC** (technische commissie / planner van de club), **commissaris** (baancommissaris op de avond), **captain**, **lid/bar**, **beheerder** (ontwikkelaar).

---

## Beslissingenlog

| Datum | Beslissing | Bron |
|---|---|---|
| 2026-08-24 | Faseregels en deadline eerste partij toegevoegd aan SPEC (CI-plafonds daarop gebaseerd) | docs/SPEC.md, ci.yml |
| 2026-10-05 | Rood/Oranje/Groen/jeugd 11–14 zijn KNLTB-core; Groen + jeugd 11–14 = 45 min | SPEC-core.md |
| 2026-10-09 | Juniorencompetities (CR B3 1.1.a) = Groen + Junioren 11–14; J13-17/M13-17 zijn géén junioren | SPEC-core.md |
| 2026-10-09 | Geen login nu; clubpagina staat bewust open, democlub om te proberen; login per club later (issue 27) | Oscar, ROADMAP |
| 2026-10-10 | Import ondersteunt alle weekdagen (do/vr-avond, za, zo) | Oscar, commit 4ba6364 e.e. |
| 2026-10-10 | Gespeelde wedstrijden uit de import zijn de waarheid: vast, nooit herplannen/verzetten | Oscar |
| 2026-10-10 | Mierlo vrijdag: park dicht 01:00 (volgende dag); laatste start 20:30 (onbevestigd) | Oscar, commit 95c34fd |
| 2026-10-12 | CI-plafonds validate-schedules naar gemeten stand (HARD strenger) op product/generiek | commit d2f1efe |
| 2026-10-12 | "Wordt niet gespeeld" per wedstrijd, omkeerbaar; export met uitslag wint | Oscar, commit 81c9db9 |
| 2026-10-12 | Begintijd uit de export is verplicht (standaard hard, als clubregel instelbaar) | Oscar, commit 81c9db9 |
| 2026-10-14 | Opgave als type: Eigen opgave / Tegenstander opgave | Oscar, commit 2e197bc |
| 2026-10-14 | UX-review: 5 vervolgacties; (5) opruimen eerst | Oscar |
| 2026-10-14 | Bingo-schema (vrijdagavond live) als dagkeuze; volgorde: opruimen → bingo 1 → bingo 2 | Oscar |
| 2026-10-14 | Werkprincipe: alle beslissingen als user story in dit document | Oscar |
| 2026-10-14 | Mierlo-vrijdag = bingo (profiel server + clubs/mierlo.yaml) | Oscar |
| 2026-10-14 | Geen login voorlopig: iedereen met de commissaris-link mag tikken; login per club blijft backlog | Oscar |
| 2026-10-14 | Avond: laatste start = sluiting − 1:30 (generiek, per club instelbaar `day.evening_close_margin`); vrijdag 23:30 | Oscar |
| 2026-10-14 | Mierlo donderdag: eindtijd 00:00 (bevestigd) → laatste start 22:30 | Oscar |
| 2026-10-14 | JU11-14 MIERLO 2 – VALKENSWAARD 1 (11-10) "Tegenstander opgave" is echt; blijft staan | Oscar |
| 2026-10-14 | Testbestand geanonimiseerd: `export_mierlo_20261010.xlsx` → `tests/generiek/data/export_anoniem_20261010.xlsx` (THUISCLUB n / TEGENSTANDER X n, fictieve uitslagen, status/structuur gelijk). Geen history-rewrite: origineel blijft in git-geschiedenis (commit 39f5781) | Oscar |
| 2026-10-14 | Bingo stap 2 gebouwd: commissarisscherm (bingo.html), opslag per club/datum met generatie (409 bij conflict), polling 5 s | Oscar |
| 2026-10-12 | 25-10 niet in te plannen: exporttijd 11:15 (hard) botste met halve-uur-raster (CR B3 1.1, hard). Besluit: KNLTB-exporttijd wint; raster vervalt voor dat team (planner + editor-check). Test: export 11:15 → ingepland om 11:15. | Oscar |
| 2026-10-14 | Voorkeur lage baannummers (clubinstelling `court_assignment.prefer_low_courts`, default aan, vinkje in Instellingen): bij genoeg plek eerst de laagste banen. Zacht, alleen tie-break (gewicht onder alle andere voorkeuren); aangrenzend/overige regels blijven. Geen sleepcheck (zacht). Aanleiding: 25-10 MIERLO 3 op baan 9-10. | Oscar |
| 2026-10-14 | Bingo: opgeslagen verzettingen tellen mee op het commissarisscherm (naar de avond verzet = erbij, met "verzet van <datum>"; weg-verzet = eraf; verouderde verzetting genegeerd) | Oscar |
| 2026-10-14 | Bingo stap 3: voorstel "Volgende op baan X" = laagste vrije baan, aanwezig team met minste partijen op de baan, singles vóór dubbels, alleen als hij ≤ laatste start begint en vóór sluiting klaar is; één tik accepteren, commissaris kan anders kiezen | Oscar |
| 2026-10-14 | Bingo stap 4: tv/beamer-scherm tv.html#club/datum, alleen-lezen (zelfde GET als commissaris, geen knoppen), ververst elke 5 s; voorstelblok staat boven de banen | Oscar |
| 2026-10-14 | Deelbare dagpagina toont alleen het opgeslagen schema (wat de TC definitief maakte), niet een werkversie; geen schema = melding | Oscar |

---

## A. Product & werkwijze

**A1 — Generiek product, Mierlo eerste profiel.** Als beheerder wil ik dat elke vereniging hetzelfde pad volgt (clubprofiel + KNLTB-export → voorstel), zodat Mierlo geen uitzondering is.
- AC: clubspecifieke keuzes staan in het clubprofiel/SPEC-mierlo, niet in de kern.
- Status: gereed · Bron: ROADMAP "Houding".

**A2 — Kleine stappen, main nooit breken.** Als beheerder wil ik kleine, afzonderlijk gepushte stappen op `product/generiek`, zodat `main` en de live Mierlo-pagina altijd blijven werken.
- AC: geen wijzigingen aan `main`; CI-checks voor main's Mierlo-schema's niet afzwakken.
- Status: gereed (doorlopend) · Bron: Oscar.

**A3 — Plannen alleen expliciet.** Als TC wil ik dat er alleen gerekend wordt als ik op "Nu berekenen"/"Alle dagen" druk, zodat er niets ongemerkt verandert.
- AC: na upload/opslaan/herimport wordt niets vanzelf berekend.
- Status: gereed · Bron: ROADMAP fase 1.

**A4 — Geen login nu, democlub.** Als bezoeker wil ik zonder account kunnen proberen (democlub), zodat de drempel laag is.
- AC: schrijven staat open; ingebouwde voorbeeldprofielen zijn alleen-lezen. Login per club = later (issue 27).
- Status: gereed (login: gepland) · Bron: Oscar 09-10-2026.

## B. KNLTB-regels en planner (zie SPEC-core / SPEC-mierlo)

**B1 — Junioren = Groen + 11–14.** Als TC wil ik dat juniorenregels alleen voor Groen en Junioren 11–14 gelden, zodat J/M 13–17 de gewone regels volgen.
- AC: labels J13-17 / M13-17 / JU11-14 in rooster; juniorregels niet op 13–17. · Status: gereed · Bron: SPEC-core 09-10-2026.

**B2 — Mierlo junioren start ≤ 13:00.** Als TC van Mierlo wil ik junioren uiterlijk 13:00 laten beginnen (KNLTB: 15:00), zodat jeugd op tijd klaar is.
- AC: hard in profiel (`junioren_latest_start`). · Status: gereed · Bron: SPEC-mierlo.

**B3 — Max 3 banen per team, aangrenzend.** Als TC wil ik dat een team op max. 3 aangrenzende banen speelt, zodat captains overzicht houden.
- AC: planner + directe controle melden overschrijding (niet bij bingo, zie G). · Status: gereed · Bron: SPEC-mierlo.

**B4 — Eerste partij ≤ 15:00 (zacht).** Als TC wil ik dat elk team uiterlijk 15:00 begint (voorkeur), zodat dagen niet te laat eindigen.
- AC: zachte regel, telt als "kan mooier". · Status: gereed · Bron: SPEC-core.

**B5 — Inhaaldag nooit automatische oplossing.** Als TC wil ik dat de planner nooit zelf wedstrijden naar een inhaaldag schuift, zodat dat altijd een bewuste keuze is.
- AC: verzetten alleen via "Verzetten naar…". · Status: gereed · Bron: ROADMAP / Oscar.

**B6 — 80 km-regel uitgesteld.** Als TC wil ik later per tegenstander reisafstand invullen (niet vóór 10:00 bij ≥ 80 km).
- Status: uitgesteld (issue 26) · Bron: SPEC-core, ROADMAP.

**B7 — Begintijd uit de export verplicht.** Als TC wil ik dat de eerste partij op de exporttijd start, zodat het schema klopt met KNLTB.
- AC: standaard hard (clubregel `export_start`, uit te zetten); dagweergave "tijd uit export"; afwijking na slepen gemeld. · Status: gereed · Bron: Oscar 12-10-2026, commit 81c9db9.

**B8 — Avondcompetities (do/vr).** Als TC wil ik per weekdag een dagvenster (eerste aanvang, laatste start, park dicht, banen, verlichting), zodat avonden goed gepland worden.
- AC: Bijlage 3 alleen za/zo; avond 19:00–20:00 begintijd; laatste start = sluiting − 1:30 (per club instelbaar, eigen waarde per weekdag wint). Mierlo: vrijdag park dicht 01:00 → laatste start 23:30; donderdag eind 00:00 → 22:30 (bevestigd). · Status: gereed · Bron: Oscar 10/14-10-2026.

## C. Import & seizoen

**C1 — KNLTB-export uploaden (alle weekdagen).** Als TC wil ik de KNLTB-export uploaden, zodat alle thuiswedstrijden (do/vr/za/zo) in het seizoen staan.
- AC: rapport per weekdag/competitie, wat overgeslagen is en waarom; opnieuw verwerken mogelijk. · Status: gereed · Bron: Oscar 10-10-2026.

**C2 — Gespeeld = waarheid.** Als TC wil ik dat gespeelde wedstrijden (uitslag/status of datum voorbij) vast staan, zodat ze nooit herpland worden.
- AC: 🔒 in overzicht/dag; niet verzetbaar; opgeslagen schema's van het verleden blijven staan. · Status: gereed · Bron: Oscar 10-10-2026.

## D. Wijzigingen tijdens de competitie

**D1 — Team verzetten.** Als TC wil ik een wedstrijd/team naar een andere dag (bv. inhaaldag) verzetten, zodat ik na regen snel kan herplannen.
- AC: via teammenu; omkeerbaar; opslaan op server. · Status: gereed · Bron: Oscar.

**D2 — Opgave (wordt niet gespeeld).** (Echte opgave vastgelegd: JU11-14 MIERLO 2 – VALKENSWAARD 1, 11-10-2026, tegenstander opgave — blijft staan.) Als TC wil ik een wedstrijd markeren als *Eigen opgave* of *Tegenstander opgave* met optionele toelichting, zodat banen vrijkomen.
- AC: partijen weg uit rooster; validator negeert; "vervallen" doorgestreept; "Toch spelen" om terug te draaien; overleeft herimport; export met uitslag wint (gemarkeerd). · Status: gereed · Bron: Oscar 12/14-10-2026.

## E. Delen & weergave

**E1 — Kleuren uniek per dag.** Als captain wil ik dat elk team op een dag een eigen, goed onderscheidbare kleur heeft. · Status: gereed · Bron: commit 84d6a4b e.e.

**E2 — Print op 1 A4 in kleur.** Als TC wil ik het dagschema op één A4 in kleur printen, zodat het aan de muur kan. · Status: gereed · Bron: Oscar.

**E3 — Regelmaatje.** Als lid/captain wil ik vragen over KNLTB-regels stellen en een antwoord met bronnen krijgen, dat makkelijk te kopiëren/delen is. · Status: gereed · Bron: Oscar.

## F. UX-assessment 14-10-2026 — vervolgacties

**F1 — Deelbare alleen-lezen dagpagina.** Als captain/lid/bar wil ik een alleen-lezen link per dag (telefoonvriendelijk) en een "Kopieer link / WhatsApp"-knop, zodat ik het schema op de dag zelf kan delen.
- AC: geen bewerkknoppen; lijst per team (aanvang, banen); printbaar. Gebouwd: `dag.html#<club>/<datum>`, telefoon-eerst, toont alleen het opgeslagen (definitieve) schema (anders "nog geen definitief schema"); Kopieer link, WhatsApp, Printen; knop "Delen" in de dagweergave. · Status: klaar (14-10-2026).

**F2 — Vaste clublink.** Als TC wil ik een vaste link zonder githack-tussenpagina, zonder "voorbeeld" in de kop, en index = clubkeuze, zodat duidelijk is waar ik begin. · Status: nog niet gestart.

**F3 — Telefoon: dagschema als lijst.** Als captain wil ik op mijn telefoon een lijst per tijd (tijd · baan · team) i.p.v. een grid van 10 banen. · Status: nog niet gestart.

**F4 — Eén opslaggedrag.** Als TC wil ik dat alles op dezelfde manier wordt opgeslagen, met één statusregel en een badge "definitief schema", zodat ik weet wat geldt. · Status: nog niet gestart.

**F5 — Opruimen.** Als TC wil ik geen jargon (Solver/Rekentijd/Dagstart onder "Details"), tijden na middernacht als "01:00+" (niet 19:00–25:00), en een ⋯-menu per wedstrijd.
- AC: overzicht, dagweergave, instellingen en print consistent; ⋯ werkt op telefoon. · Status: klaar (commit 3a5ddcc) · Bron: Oscar 14-10-2026.

## G. Bingo-schema (vrijdagavond, live)

Concept: op een bingo-avond wordt **geen** baanschema berekend; een baancommissaris bepaalt live welke partij als volgende op welke baan gaat. Geen solver.

Antwoorden van Oscar (14-10-2026):
1. Aanmelden per team; de commissaris vult de opstelling per partij in.
2. Geen minimale rust berekenen — verantwoordelijkheid van het team.
3. Geen max 3 banen / aangrenzend bij bingo; de commissaris bepaalt.
4. Alle banen hebben licht; park dicht 01:00.
5. Alleen vrijdag.
6. Eén commissaris tegelijk.
7. Live scherm voor grote tv/beamer is belangrijk; captains/bar meekijken op telefoon = nice-to-have, later.
8. Geen uitslagen invoeren (gaat via KNLTB-app); wel registreren dat een partij klaar is.
9. Dekking (wifi/4G) ruim voldoende; offline niet nodig.

**G1 — Keuze gepland/bingo per speeldag.** Als TC wil ik per weekdag kiezen tussen *Gepland (berekend)* en *Bingo (live)*, zodat de vrijdagavond live kan.
- AC: standaard gepland; label "Bingo (live)" in overzicht/dag; geen "Nu berekenen" (ook niet bij Alle dagen, server weigert); knop "Avond openen" met placeholder + wedstrijdlijst. Mierlo-vrijdag staat op bingo (besluit 14-10-2026). · Status: gereed (commit 94a32a7).

**G2 — MVP commissarisscherm.** Als commissaris wil ik teams aanmelden, banen zien, een wachtrij van partijen, en per partij start/klaar tikken, op één apparaat.
- AC: `bingo.html#<club>/<datum>` via "Avond openen"; per team "aanwezig"; alle banen vrij/bezet met verstreken tijd; wachtrij met partijen (S/D/GD volgens KNLTB-categorie) van aanwezige teams; partij op vrije baan zetten met opstelling (vrije tekst); "Klaar" maakt baan vrij (geen uitslag); ongedaan maken; logboek met tijden; waarschuwing na laatste start (23:30) of einde na 01:00; geen rust-/max-banen-/aangrenzend-regel; opgaven en gespeelde wedstrijden tellen niet mee; geen login (iedereen met de link). Opslag per club/datum met generatie (409 bij gelijktijdige wijziging), polling elke 5 s.
- Status: gereed (deze commit) · Bron: Oscar 14-10-2026.

**G3 — Voorstel volgende partij + ongedaan maken.** Als commissaris wil ik een voorstel voor de volgende partij en een "ongedaan maken".
- AC: blok "Volgende op baan X" (laagste vrije baan) met partij van een aanwezig team, singles vóór dubbels (KNLTB-volgorde), voorrang aan het team met de minste partijen op de baan; alleen als hij nog mag starten (≤ laatste start) en vóór sluiting klaar is; één tik "Starten", of "Anders kiezen…"/wachtrij. Geen rust-/max-banen-regel. Ongedaan maken zat al in G2. · Status: klaar (14-10-2026).

**G4 — Tv/beamer-scherm (alleen-lezen).** Als lid/bar wil ik op een groot scherm zien wat waar speelt en wat volgt. Prioriteit boven meekijken op telefoon.
- AC: `tv.html#<club>/<datum>` (link "📺 Tv-scherm" op het commissarisscherm); groot, liggend, donker; per baan team/partij/tegenstander/opstelling en verstreken tijd (rood bij uitloop); rij "Straks" (eerste 8 uit de wachtrij); ververst elke 5 s; geen knoppen, schrijft niets. · Status: klaar (14-10-2026).

**G5 — Print/verslag van de avond.** Als TC wil ik na afloop een verslag/print van de avond. · Status: gepland.

## Beslisvolgorde (14-10-2026)

1. Opruimen (F5) → 2. Bingo stap 1 (G1) → 3. Bingo stap 2 (G2).

## Backlog

Alle openstaande items, van hoog naar laag. Label: [UX] · [Bingo] · [Planner] · [Beheer].

| # | Label | Item | Story | Status |
|---|---|---|---|---|
| 1 | [UX] | Opruimen: jargon naar "Details", 01:00+ i.p.v. 25:00, ⋯-menu per wedstrijd — **hoogste prioriteit** | F5 | klaar (commit 3a5ddcc, 14-10-2026) |
| 2 | [Bingo] | Stap 1: keuze gepland/bingo per speeldag, label, "Avond openen" | G1 | klaar (commit 94a32a7) |
| 3 | [Bingo] | Stap 2: MVP commissarisscherm (aanmelden, banen, wachtrij, start/klaar, één apparaat) | G2 | klaar |
| 4 | [UX] | Deelbare dagpagina (alleen-lezen + WhatsApp/kopieerlink) | F1 | klaar (14-10-2026) |
| 5 | [UX] | Vaste clublink (geen githack-tussenpagina, "voorbeeld" weg, index = clubkeuze) | F2 | nog niet gestart |
| 6 | [UX] | Dagschema als lijst op telefoon | F3 | nog niet gestart |
| 7 | [UX] | Overal hetzelfde opslaan (statusregel, badge "definitief schema") | F4 | nog niet gestart |
| 8 | [Bingo] | Stap 3: voorstel volgende partij + ongedaan maken | G3 | klaar (14-10-2026) |
| 9 | [Bingo] | Stap 4: tv/beamer-scherm (alleen-lezen), vóór meekijken op telefoon | G4 | klaar (14-10-2026) |
| 10 | [Bingo] | Stap 5: print/verslag van de avond | G5 | nog niet gestart |
| 11 | [Bingo] | Mierlo-vrijdag op bingo | G1 | klaar (besluit 14-10-2026) |
| 12 | [Bingo] | Zonder login: iedereen met de commissaris-link mag tikken (besloten); aparte alleen-kijken tv-link volgt bij stap 4 | G2/G4 | besloten |
| 13 | [Planner] | Laatste start avond = sluiting − 1:30; donderdag eind 00:00 | B8 | klaar (besluit 14-10-2026) |
| 14 | [Planner] | 27-09 herberekenen op verzoek | — | open |
| 15 | [Planner] | Reisafstand per tegenstander (80 km-regel) | B6 | uitgesteld |
| 16 | [Planner] | Dashboard / herplannen op de wedstrijddag (ROADMAP fase 3) | — | gepland |
| 17 | [Beheer] | Openbaar testbestand met teamnamen/uitslagen geanonimiseerd (`tests/generiek/data/export_anoniem_20261010.xlsx`); origineel nog in git-geschiedenis (39f5781) — history-rewrite alleen op verzoek | — | klaar (14-10-2026) |
| 18 | [Beheer] | CI op `main` rood (validate-schedules-plafonds) — bij Koen | — | open |
| 19 | [Beheer] | Login per club (issue 27) | A4 | gepland |
| 20 | [Bingo] | Naar een bingo-avond verzette wedstrijden verschijnen bij de commissaris | G2 | klaar (14-10-2026) |
