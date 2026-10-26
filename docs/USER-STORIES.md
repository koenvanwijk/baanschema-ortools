# User stories & beslissingen — Baanschemaatje

Levend brondocument voor **alle** beslissingen en requirements van het project (branch `product/generiek`).
Laatst bijgewerkt: 26-10-2026 (I1/I3 Google-login + club-aanmaakpoort).

## Werkprincipe

- **Elke beslissing en elke requirement** wordt in dit document vastgelegd als user story:
  *Als &lt;rol&gt; wil ik &lt;wens&gt;, zodat &lt;doel&gt;* + **acceptatiecriteria** + **status** + **datum** + **bron**.
- Wijzigt een beslissing of requirement, dan wordt dit document **in dezelfde commit** bijgewerkt.
- Status: `gepland` · `in uitvoering` · `gereed` · `uitgesteld` · `vervallen` · `open vraag`.
- Bron: wie/waar (bv. "Oscar, chat 14-10-2026", "SPEC-core.md", commit-hash).
- Detailregels (KNLTB, parameters) blijven in [`SPEC-core.md`](./SPEC-core.md) en [`SPEC-mierlo.md`](./SPEC-mierlo.md); dit document verwijst ernaar.
- Werkwijze: **kleine stappen**; `main` en de live Mierlo-pagina worden nooit gebroken.

Rollen: **TC** (technische commissie / planner van de club), **commissaris** (baancommissaris op de avond), **captain**, **lid/bar**, **clubbeheerder** (toegang/rollen per club, zie I4), **beheerder** (platform/ontwikkelaar).

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
| 2026-10-14 | Telefoon: dagschema standaard als lijst per tijd (≤ 700 px), schakelaar naar rooster; keuze per apparaat onthouden; slepen alleen in rooster | Oscar |
| 2026-10-14 | Eén opslaggedrag: alles meteen opgeslagen (verzettingen, slepen, berekende dagen); undo blijft; verouderd opgeslagen schema (door verzettingen) wordt niet automatisch overschreven; na een fout pas opnieuw via knop Opnieuw (geen herhaallus) | Oscar |
| 2026-10-14 | Bingo stap 5: printbare bingolijst (A4, lege vakjes) en verslag achteraf uit de opgeslagen toestand/logboek; geen uitslagen (KNLTB-app) | Oscar |
| 2026-10-14 | Vaste clublink via dezelfde Cloud Run-service (statische web-app onder /app, korte links /club/<id> e.d.), niet via GitHub Pages (Koens repo) | Oscar |
| 2026-10-16 | Oscar vraagt het speeldag-dashboard met herplannen uit te werken: stories SD1–SD7 + open vragen V1–V7 (sectie H); herplannen alleen expliciet, gespeelde/lopende partijen vast | Oscar |
| 2026-10-16 | Antwoorden dashboard (V1–V7): één baancommissaris op één apparaat; start/klaar per partij; herplannen mag naar andere baan, geen harde grens later beginnen (alleen sluiting/regels); omwisselen tussen teams OPEN (tot besluit alleen schuiven); regen per team (staken/doorgaan/later starten, nieuwe story SD8), niet hele dag stilleggen; tv-scherm ook voor geplande dagen (SD9); captains niet automatisch inlichten, gedeelde link volstaat (SD7 vervalt) | Oscar |
| 2026-10-16 | SD1 dashboard: bron = definitief (opgeslagen) schema; verloop apart per club/datum opgeslagen (zelfde mechaniek als bingo); vaste link /dashboard/<club> opent vandaag | Oscar |
| 2026-10-16 | SD2 verloop: per partij start en klaar tikken, ook op een andere baan dan gepland (gelogd); opslag zoals bingo (generatie, 409, polling 5 s) | Oscar |
| 2026-10-16 | SD4/SD5 opslaan: wijzigingen op de speeldag pas na bevestiging definitief (bron herplan), oorspronkelijke tijd/baan per partij bewaard voor gewijzigd-markering, laatste 3 versies terug te zetten | Oscar |
| 2026-10-16 | SD5 herplannen: alleen schuiven (V4 open), andere baan mag; bij herplannen worden max-banen/aangrenzend en gelijk-starten losgelaten en tijdregels die door vertraging onhaalbaar werden zacht; voorstel wordt pas na bevestiging opgeslagen | Oscar |
| 2026-10-16 | SD8 regen per team: staakt/gaat door/start later; staken laat niet-begonnen partijen vervallen bij herplannen (geen opgave, terug te draaien) | Oscar |
| 2026-10-16 | SD9 tv-scherm ook op geplande dagen; zonder getikte partijen toont het de partij volgens schema (gemarkeerd "volgens schema") | Oscar |
| 2026-10-16 | Teambezetting hard bij herplannen en doorschuiven (Oscar: enkel en dubbel goed controleren): spelers-/volgorderegels blijven hard; opstelling met namen (dashboard bij Start, bingo) → zelfde speler niet tegelijk in twee lopende partijen van het team; max banen/aangrenzend/gelijk starten mogen los | Oscar |
| 2026-10-16 | Oscar bevestigt: bij herplannen worden tijdregels die door vertraging onhaalbaar zijn geworden (bv. uiterste begintijd) voorkeuren i.p.v. harde regels. Omwisselen tussen teams blijft open (V4) | Oscar |
| 2026-10-17 | "Kan mooier"/"Regels gebroken" klikbaar (Oscar: "Ik wil dat kunnen zien"): lijst per bevinding (team · partij, nu vs wens, uitleg), tik wijst de partij aan in lijst en rooster (F6) | Oscar |
| 2026-10-17 | Ingetrokken modelgrens "jeugd 13-17 vanaf 11:00" (VENSTER-JEUGD, "ingetrokken") telt in Baanschemaatje niet meer als "Kan mooier" — ook in al opgeslagen schema's (18-10 Mierlo: 4 → 0). Gedeeld validatorscript (`scripts/validate_schedule.py`, CI main) ongewijzigd | Oscar |
| 2026-10-17 | Bingo oefenen op democlub Demo TV (Oscar): vrijdag = bingo (sluiting 01:00, laatste start 23:30); fictieve thuiswedstrijden op vr 23-10 (7) en vr 30-10 (6) 2026, mix GD 17+/35+, DD 17+/35+, HD 35+, Heren 17+ (S+D). Bingo/commissaris/tv/dashboard zijn bij Demo TV gewoon beschrijfbaar (testdata mag daar); knop "Reset demo-avond/-dag" (`POST /clubs/{club}/demo-reset/{datum}`) wist bingo- en dashboardverloop van die datum, alleen bij democlubs (meta.demo; echte clubs 403) | Oscar |
| 2026-10-26 | Uitwedstrijd → thuis gespeeld (D3): knop in dagweergave; away.tsv + host_away.json; zelfde plannerregels | Oscar |
| 2026-10-26 | Productrichting: zelf nieuwe clubs toevoegen + per club logins/access management (I1–I5). Eerdere "geen login voorlopig" blijft gelden tot fase 2 live is; implementatie gefaseerd. | Oscar |
| 2026-10-26 | Toegang besloten (I1/I3/I5): (1) alleen Oscar/platformbeheerder mag nieuwe clubs toevoegen (env-allowlist of vergelijkbare gate); (2) login = Google OAuth per club (goedgekeurde e-mails), **geen** gedeeld clubwachtwoord; (3) tv- en dagpagina (en bingolijst alleen-kijken) blijven publiek zonder login | Oscar |
| 2026-10-26 | Auth later optioneel: e-mailadres + wachtwoord **per gebruiker** (individuele accounts), niet één clubwachtwoord (Oscar: "evt later e-mailadres en wachtwoord per user") | Oscar |
| 2026-10-26 | Implementatie I1/I3 gestart: `POST /clubs` nooit anoniem open (401 zonder Google of `BS_ALLOW_OPEN_CREATE` alleen voor tests); Google OAuth-routes `/auth/*`; per club `writers` + `auth_required` in meta; tv/dag GET publiek (I5). Feature uit tot OAuth-client credentials op Cloud Run staan. | Oscar "begin" |
| 2026-10-26 | Wachtwoordveiligheid (antwoord Oscar "kun je wachtwoorden wel echt veilig houden?"): ja — als er wachtwoorden komen (later per user), alleen salted Argon2id (of bcrypt) hashes, nooit plaintext in GCS/logs/chat; HTTPS; rate-limit loginpogingen. Fase 2 is Google (geen wachtwoordopslag bij ons) | Oscar |
| 2026-10-26 | D3 geldt op **iedere** competitiedag (Oscar: "ja, dit zou in principe op iedere dag kunnen"): gepland én bingo (vrijdag e.d.), donderdagavond enz. Gemarkeerde uitwedstrijd verschijnt in bingo-wachtrij/TV/commissaris net als een thuiswedstrijd | Oscar |
| 2026-10-17 | Bingo 2 "meer intelligentie" (Oscar): zelfde teambezettingsregels als planner/herplannen, hard in wachtrij/voorstel (geblokkeerd met reden, "toch starten" alleen bewust met bevestiging + logregel); partijsoort HE/DE/HD/DD/GD overal zichtbaar; voortgang per team (x/y klaar, z bezig, balk) bij commissaris en tv; wachtrij gesorteerd zodat bovenaan het meest logische staat (volgorde: zie G6). Gemengd Dubbel = DD-HD-2GD (D1 = DD, D2 = HD) en Gemengd 17+/35+ zaterdag (S1 = DE, S2 = HE) krijgen heren/dames-behoefte, ook in planner en sleepcheck (was alleen "gemengd zondag") | Oscar |

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
- AC: schrijven staat open tot login-fase live is; ingebouwde voorbeeldprofielen zijn alleen-lezen; democlubs (meta.demo) blijven om te oefenen; tv/dag blijven publiek (I5).
- Status: gereed voor democlub/open testen · **productrichting login/access: zie I3–I5** (eerdere "geen login voorlopig" / backlog #12/#19 / ROADMAP issue 27 blijft interim tot fase 2 Google) · Bron: Oscar 09/14-10-2026; richting bijgesteld Oscar 26-10-2026 (Google; later evt e-mail+wachtwoord per user; tv/dag publiek).

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

**D3 — Uitwedstrijd wordt thuis gespeeld.** [Planner] [Beheer] Als TC wil ik een uitwedstrijd (die niet bij de tegenstander kan) markeren als *Wordt thuis gespeeld*, zodat die banen krijgt in ons baanschema (zelfde regels als een thuiswedstrijd).
- AC:
  - Bij de KNLTB-import worden uitwedstrijden bewaard (`away.tsv`); ze verdwijnen niet meer stil.
  - Per dag (elke weekdag/dagdeel uit de export): sectie "Uitwedstrijden" met knop/menu **Wordt thuis gespeeld** (optionele toelichting) — ook op vrijdag-bingo, donderdagavond, zaterdag, enz.
  - Gemarkeerde wedstrijd verschijnt bij de thuiswedstrijden met label "thuis (was uit)"; telt mee bij "Nu berekenen" op geplande dagen én in bingo (commissaris, TV, wachtrij/teamregels) en dashboard.
  - Op een bingo-avond: zelfde teambezettingsregels en wachtrij-logica als andere thuiswedstrijden; badge "thuis (was uit)" bij het team.
  - Omkeerbaar via **Toch uit spelen**.
  - Geen nieuw venue-systeem; hergebruikt het patroon van opgave/verzetten (`host_away.json`).
  - Gespeelde uitwedstrijden niet markeerbaar.
- Status: gereed (26-10-2026) · Bron: Oscar chat 26-10-2026 (zondag uitwedstrijd verplaatst naar Mierlo); 26-10-2026 "iedere dag, ook bingo".
- Besluitlog: kleinste knop i.p.v. volledig speellocatie-model; labels blijven MIERLO – TEGENSTANDER (onze club als "home" voor de planner). Geldt op iedere competitiedag (Oscar 26-10-2026).

## E. Delen & weergave

**E1 — Kleuren uniek per dag.** Als captain wil ik dat elk team op een dag een eigen, goed onderscheidbare kleur heeft. · Status: gereed · Bron: commit 84d6a4b e.e.

**E2 — Print op 1 A4 in kleur.** Als TC wil ik het dagschema op één A4 in kleur printen, zodat het aan de muur kan. · Status: gereed · Bron: Oscar.

**E3 — Regelmaatje.** Als lid/captain wil ik vragen over KNLTB-regels stellen en een antwoord met bronnen krijgen, dat makkelijk te kopiëren/delen is. · Status: gereed · Bron: Oscar.

## F. UX-assessment 14-10-2026 — vervolgacties

**F1 — Deelbare alleen-lezen dagpagina.** Als captain/lid/bar wil ik een alleen-lezen link per dag (telefoonvriendelijk) en een "Kopieer link / WhatsApp"-knop, zodat ik het schema op de dag zelf kan delen.
- AC: geen bewerkknoppen; lijst per team (aanvang, banen); printbaar. Gebouwd: `dag.html#<club>/<datum>`, telefoon-eerst, toont alleen het opgeslagen (definitieve) schema (anders "nog geen definitief schema"); Kopieer link, WhatsApp, Printen; knop "Delen" in de dagweergave. · Status: klaar (14-10-2026).

**F2 — Vaste clublink.** Als TC wil ik een vaste link zonder githack-tussenpagina, zonder "voorbeeld" in de kop, en index = clubkeuze, zodat duidelijk is waar ik begin.
- Gebouwd: de bestaande Cloud Run-service serveert ook de web-app (`/app/...`) met vaste links `/club/<id>`, `/dag/<id>/<datum>`, `/bingo/<id>/<datum>`, `/tv/<id>/<datum>`, `/bingolijst/<id>/<datum>`; `/` = clubpagina met clubkeuze. Geen tussenpagina, zelfde origin als de API, geen extra kosten (zelfde service, min 0). GitHub Pages op Koens repo blijft ongemoeid. Web-wijzigingen gaan live bij een deploy (net als de server). Open: link "voorbeeld (vooraf berekend)" in de kop. Later eventueel eigen domein (Cloud Run domain mapping of Firebase Hosting). · Status: klaar (14-10-2026).

**F3 — Telefoon: dagschema als lijst.** Als captain wil ik op mijn telefoon een lijst per tijd (tijd · baan · team) i.p.v. een grid van 10 banen.
- AC: schakelaar Lijst/Rooster boven het dagschema; standaard Lijst op schermen ≤ 700 px, Rooster op groter; keuze onthouden op het apparaat; slepen kan alleen in het rooster (hint). · Status: klaar (14-10-2026).

**F4 — Eén opslaggedrag.** Als TC wil ik dat alles op dezelfde manier wordt opgeslagen, met één statusregel en een badge "definitief schema", zodat ik weet wat geldt.
- AC: verzettingen, versleepte partijen en net berekende dagen (ook via Alle dagen) worden meteen opgeslagen (geen Opslaan-knoppen meer); één statusregel "Alles opgeslagen ✓ hh:mm" / "Opslaan…" / "Niet opgeslagen: … [Opnieuw]"; badge "Definitief schema" bij het opgeslagen schema van een dag, "definitief" in het overzicht; Ongedaan maken blijft werken na opslaan (en slaat ook meteen op). Een opgeslagen schema dat niet meer past bij verzettingen wordt níet automatisch overschreven (melding: opnieuw berekenen of slepen). · Status: klaar (14-10-2026).

**F6 — Bevindingen zien.** Als TC wil ik op "Kan mooier" en "Regels gebroken" kunnen tikken en per punt zien welke partij het is, wat de wens/regel is en hoe het nu staat, zodat ik weet wat ik kan verbeteren.
- AC: tegels zijn knoppen; lijst onder de tegels met team · partij, "nu: tijd · baan", "wens", uitleg in gewone taal (incl. "begintijd ligt vast in de KNLTB-export" waar dat zo is); tik op een punt markeert de partij in lijst én rooster en scrolt erheen; werkt op telefoon; bij 0: "Niets — alle wensen/regels gehaald". Ingetrokken check "jeugd 13-17 vanaf 11:00" telt niet mee. · Status: klaar (17-10-2026) · Bron: Oscar 17-10-2026.

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

**G5 — Print/verslag van de avond.** Als TC wil ik na afloop een verslag/print van de avond.
- AC: `bingo-print.html#<club>/<datum>[/verslag]` (link "🖨 Lijst/verslag" op het commissarisscherm). Bingolijst A4: per team aanwezig-vakje, per partij lege vakjes opstelling/baan/start/klaar (papieren reserve). Verslag: gespeelde partijen op starttijd met eind, duur, baan, opstelling; niet-afgeronde partijen; logboek. · Status: klaar (14-10-2026).

**G6 — [Bingo] Slimmere wachtrij: teambezetting, partijsoort, voortgang, logische volgorde.** Als commissaris wil ik dat de wachtrij dezelfde regels toepast als de planner, DD/HD/GD laat zien, de voortgang per team toont en zo gesorteerd is dat de bovenste partij de meest logische is, zodat ik niet zelf hoef te puzzelen wie er nu kan en niemand twee partijen tegelijk moet spelen.
- AC regels (hard, gedeeld met planner/herplannen via `src/baanschemaatje/teamrules.py` + `baanschema.rules`): max 4 spelers van een team tegelijk; gemengd max 2 heren + 2 dames (dus DD en GD, of HD en GD, van één team niet tegelijk; DD + HD en GD + GD wel); niet-gemengd (en 8p strikt) eerst alle enkels klaar vóór een dubbel; 8p ook dubbels vóór gemengd dubbel. Geen max-banen/aangrenzend/rust (blijft besluit 14-10-2026). Na laatste start of eindigt na sluiting = niet meer voorgesteld.
- AC weergave: elke partij met label + soort (bv. "D1 DD", "GD2 GD", "S1 HE") in voorstel, wachtrij, banen, tv, bingolijst/verslag. Geblokkeerde partijen staan onderaan, grijs, met reden ("de dames spelen nog (DD op baan 1)", "eerst de enkels klaar (HE, HE)"). Tikken op een geblokkeerde partij kan, maar de knop heet "Toch op baan X", vraagt bevestiging en het logboek vermeldt "toch gestart, regel: …".
- AC voortgang: per team balk + "x/y klaar · z bezig · nog n" in "Teams: aanwezig en voortgang"; ook in elke wachtrijregel; tv toont rechts per team een balk (afwezige teams gedimd).
- AC volgorde (uitlegbaar, bovenste regel toont "▲ Bovenaan: …", voorstel toont "Waarom: …"):
  1. eerst wat nu kan (team aanwezig, geen spelers-/volgordeconflict, nog op tijd);
  2. team met de minste partijen op de baan (spelers die staan te wachten);
  3. team met de meeste partijen nog te gaan (wie het verst achterligt bepaalt hoe laat de avond klaar is);
  4. wie het langst wacht (sinds aanmelden of sinds de laatste partij van het team klaar was);
  5. vroegste exporttijd, daarna KNLTB-volgorde binnen het team (enkels, dubbels, gemengd).
  De lijst is "van boven af starten": na elke keuze telt die partij als bezig, zodat bv. DD + HD van een gemengd team samen bovenaan komen en de GD's later ("kan ook nu, maar zelfde spelers als DD / HD hierboven").
- AC opslag: "aanwezig" bewaart nu de tijd van aanmelden (oude toestand met `true` blijft werken).
- Status: gereed (17-10-2026, deze commit) · Bron: Oscar, chat 17-10-2026 ("Bij de bingo moet meer intelligentie…").
- Open (aan Oscar): volgorde 2 vs 3 omdraaien (eerst wie het verst achterligt)? Mag "toch starten" blijven (team met meer dan 4 spelers) of moet het helemaal dicht? Gemengd Dubbel D1 = DD en D2 = HD aangenomen (KNLTB-volgorde DD-HD-2GD).

## H. [Dashboard] Speeldag-dashboard met herplannen (epic)

Doel: op de speeldag zelf zien wat waar speelt, afwijkingen vastleggen en — alleen als de TC daarom vraagt — de rest van de dag herplannen. Hergebruikt wat er is: dagpagina (F1), tv-scherm (G4), verzetten (D1), opgave (D2), bingo-commissarisscherm met logboek/ongedaan maken/generatie-opslag (G2). Nummering SD1–SD7 (D1/D2 zijn al in gebruik). Open vragen en antwoorden: zie *Open vragen dashboard* (V1–V7) hieronder; alleen V4 is nog open.

**SD1 — Dagoverzicht vandaag.** Prioriteit 1. Als baancommissaris wil ik op de speeldag één scherm met alle banen en tijden van vandaag, met per partij de status *gepland / bezig / klaar / vervallen*, zodat ik in één oogopslag zie hoe de dag loopt.
- AC: opent standaard op vandaag (vaste link, bv. `/dashboard/<club>`); bron = opgeslagen (definitief) schema; rooster per baan/tijd en lijstweergave op telefoon (F3); "nu"-lijn op de huidige tijd; opgaven tonen als vervallen (D2), verzette wedstrijden zichtbaar (D1); zonder definitief schema een duidelijke melding.; één baancommissaris op één apparaat (V1). · Status: klaar (16-10-2026): `dashboard.html#<club>/<datum>`, vaste link `/dashboard/<club>` (vandaag) of `/dashboard/<club>/<datum>`; knop "Dashboard" in de dagweergave. Banen nu (lopend + volgende), schema vandaag per tijd met status gepland/bezig/klaar/gestaakt (+ "nog niet gestart" na aanvang), ververst elke 5 s.

**SD2 — Werkelijk verloop registreren.** Prioriteit 1. Als baancommissaris wil ik per partij *gestart* / *klaar* tikken en per team *aanwezig* / *te laat* registreren, zodat het dashboard de echte stand toont en herplannen daarop kan rekenen.
- AC: dezelfde mechaniek als bingo (G2): één tik, logboek met tijden, ongedaan maken, opslag per club/datum met generatie (409 bij gelijktijdige wijziging), polling 5 s; geen uitslagen (KNLTB-app); werkt op telefoon. Start en klaar worden per partij bijgehouden (V2); één baancommissaris, één apparaat (V1). · Status: klaar (16-10-2026): per partij Start/Klaar (start op andere vrije baan als de geplande bezet is), per team aanwezig/te laat, ongedaan maken, logboek, opslag per club/datum met generatie (409), polling 5 s; één baancommissaris op één apparaat.

**SD3 — Baan buiten gebruik vanaf tijd X.** Prioriteit 2. Als baancommissaris wil ik een baan (of alle banen) vanaf een tijd buiten gebruik zetten (regen, onderhoud, kapotte verlichting), zodat ik zie welke partijen geraakt worden.
- AC: baan + van-tijd (+ optioneel tot-tijd); geraakte partijen gemarkeerd als "geraakt"; omkeerbaar; in logboek; voor onderhoud/verlichting; regen wordt per team afgehandeld (SD8, V5), niet door de hele dag stil te leggen; niets wordt vanzelf verschoven (dat doet SD5). · Status: klaar (16-10-2026): knop "Baan buiten gebruik…" (banen of alle, vanaf, optioneel tot, reden); baankaart grijs; geraakte geplande partijen gemarkeerd; opheffen en ongedaan maken; niets schuift vanzelf.

**SD4 — Uitloop / vertraging.** Prioriteit 2. Als baancommissaris wil ik zien welke partij uitloopt en de gevolgen voor volgende partijen op die baan, zodat ik op tijd kan bijsturen.
- AC: partij die langer bezig is dan de normtijd kleurt (zoals op het tv-scherm); verwachte vertraging per volgende partij op die baan en van hetzelfde team getoond; optioneel "doorschuiven op deze baan" (alleen latere partijen op dezelfde baan, met voorvertoning en bevestiging); geen harde grens voor later beginnen, alleen sluitingstijd en regels (V3). · Status: klaar (16-10-2026): lopende partij kleurt bij uitloop met minuten uitloop; verwachte vertraging van de volgende partij op die baan; "Doorschuiven +N min…" (alleen latere geplande partijen op die baan, per kwartier) met verschil oud ↔ nieuw en bevestiging; nieuwe baanconflicten of spelers-/volgordeconflicten (teambezetting) blokkeren Bevestigen (dan Herplan gebruiken), overige regelpunten zijn waarschuwingen; opgeslagen als definitief schema (bron "herplan") met gewijzigd-markering; vorige versie terug te zetten.

**SD5 — "Herplan rest van de dag".** Prioriteit 2. Als TC wil ik met één knop de rest van de dag laten herplannen vanaf nu, zodat ik na regen, uitloop of een buiten-gebruik-baan een haalbaar schema heb.
- AC: alleen expliciet via de knop (nooit automatisch); gespeelde en lopende partijen staan vast (vergrendeld); niet-beschikbare banen (SD3) en de huidige tijd als ondergrens; KNLTB-regels, clubafspraken en exporttijd blijven gelden; toont verschil oud ↔ nieuw (per partij baan/tijd, aantal verschoven, nieuwe eindtijd, onplanbare partijen) en vraagt bevestiging; pas na bevestiging wordt het nieuwe schema definitief (F4), het oude blijft terug te halen; korte rekentijd. Partijen mogen naar een andere baan; geen harde grens voor later beginnen, alleen sluitingstijd en regels (V3). Gestaakte/later-startende teams uit SD8 tellen mee. Omwisselen tussen teams: **open (V4)**; tot besluit alleen schuiven. · Status: klaar (16-10-2026): knop "Herplan rest van de dag…" (alleen expliciet) → server rekent een voorstel (POST /clubs/<id>/replan/<datum>, slaat niets op): gespeelde/lopende partijen vast op werkelijke start/baan, rest niet vóór nu (kwartier), banen buiten gebruik gemeden, gestaakte teams vallen weg, later-starten telt; KNLTB-regels/clubafspraken blijven, exporttijd alleen als nog haalbaar en team nog niet begonnen; mag naar andere baan, geen harde grens later (alleen sluiting); alleen schuiven, geen omwisselen (V4 open); zo min mogelijk verandering; verschil oud ↔ nieuw + regelwaarschuwingen, pas na Bevestigen definitief (bron herplan), vorige versie terug te zetten. Bij herplannen vervallen alleen: max banen per team/aangrenzend en gelijk starten van rondes; uiterste begintijden, max blokken en wachttijd worden zacht. Teambezetting blijft HARD (Oscar 16-10-2026): enkels vóór dubbels (niet-gemengd), max partijen en max 4 spelers tegelijk, gemengd 2H+2D; lopende partijen tellen mee (test: vertraagde enkels → dubbels pas daarna) · Vragen: V4.

**SD6 — Doorzetten naar dagpagina en tv-scherm.** Prioriteit 3. Als captain/lid wil ik op de gedeelde dagpagina (F1) en het tv-scherm (G4) direct de actuele stand zien, met een markering "gewijzigd", zodat ik weet dat het schema is aangepast.
- AC: dagpagina en tv-scherm lezen het actuele definitieve schema + verloop; gewijzigde partijen gemarkeerd met oude → nieuwe tijd/baan; tijdstip "laatst gewijzigd"; tv-scherm voor geplande dagen: zie SD9; alleen-lezen. · Status: klaar (16-10-2026) voor dagpagina en dashboard: melding "Gewijzigd op de speeldag (laatst om hh:mm)", gewijzigde teams omrand met chip "gewijzigd", per partij nieuwe tijd/baan vet met oude doorgestreept, vervallen partijen (team staakt) apart doorgestreept; oorspronkelijke tijd/baan blijft bewaard over meerdere wijzigingen. Tv-scherm: zie SD9.

**SD7 — Captains informeren.** ~~Automatisch bericht bij wijziging~~. · Status: **vervallen/gesloten** (V7, Oscar 16-10-2026): niet automatisch; de gedeelde dagpagina (F1/SD6) volstaat.

**SD8 — Per team staken / hervatten.** Prioriteit 2. Als baancommissaris wil ik bij regen per team kunnen vastleggen of het *staakt*, *doorgaat* of *later start* (met nieuwe starttijd), zodat ik niet de hele dag hoef stil te leggen en elk team apart kan afhandelen.
- AC: per team op het dashboard een keuze staken / doorgaan / later starten (tijd); gestaakte partijen gemarkeerd (gespeelde/lopende blijven zoals ze zijn), staken is omkeerbaar; geen automatische opgave (D2 blijft apart); in logboek; "later starten" en gestaakte teams worden meegenomen door SD5 (herplan rest van de dag); KNLTB-regels voor staken/hervatten als toelichting (Regelmaatje). Voorbeeld uit de praktijk: ochtendregen, de 13:00-teams speelden alsnog, verre teams hadden al gestaakt. · Status: klaar (16-10-2026): per team knoppen aanwezig / te laat / staakt / gaat door / start later (met tijd); staken met bevestiging, omkeerbaar, geen opgave; gestaakte niet-begonnen partijen vervallen bij herplannen (in het verschil als "vervalt (team staakt)"), al begonnen partijen lopen door; "start later" is de ondergrens voor dat team bij herplannen · Bron: Oscar 16-10-2026 (V5).

**SD9 — Tv-scherm voor geplande dagen.** Prioriteit 3. Als lid/bar wil ik het tv-scherm (G4) ook op gewone (geplande) speeldagen gebruiken, zodat iedereen op het park ziet wat waar speelt en wat straks komt.
- AC: `tv.html#<club>/<datum>` (vaste link `/tv/<club>/<datum>`) werkt ook voor geplande dagen: per baan de lopende partij (uit SD2 of anders volgens schema) met verstreken tijd, rij "Straks" uit het definitieve schema, vervallen/gewijzigd gemarkeerd (SD6); alleen-lezen, ververst elke 5 s. · Status: klaar (16-10-2026): `tv.html#<club>/<datum>` / `/tv/<club>/<datum>` werkt ook op geplande dagen (bingo-avonden blijven zoals G4): per baan de lopende partij (getikt op het dashboard; zonder tikken "volgens schema") met verstreken tijd en rood bij uitloop, volgende partij op vrije banen, buiten gebruik grijs, rij "Straks" uit het definitieve schema, chip "gewijzigd" en "schema gewijzigd" in de kop (SD6); alleen-lezen, ververst elke 5 s · Bron: Oscar 16-10-2026 (V6).

### Open vragen dashboard

Antwoorden Oscar 16-10-2026.

| # | Vraag | Raakt | Antwoord |
|---|---|---|---|
| V1 | Wie bedient het dashboard op een speeldag, en op één apparaat tegelijk? | SD1, SD2 | Eén baancommissaris, op één apparaat. |
| V2 | Start/klaar per partij bijhouden, of alleen afwijkingen? | SD2 | Per partij start en klaar bijhouden. |
| V3 | Mogen partijen bij herplannen naar andere banen, en hoeveel later mag iets beginnen? | SD4, SD5 | Andere baan mag; geen harde grens voor later beginnen, alleen sluitingstijd en regels. |
| V4 | Mag herplannen partijen over teams heen omwisselen, of alleen schuiven? | SD5 | **Open**: Oscar weet het nog niet. Tot besluit: alleen schuiven. |
| V5 | Regen: hele dag stilleggen en later hervatten? KNLTB staken/hervatten? | SD3, SD5, SD8 | Niet de hele dag stilleggen; per team beslissen (staken / doorgaan / later starten). Voorbeeld: ochtendregen, de 13:00-teams speelden alsnog, verre teams hadden al gestaakt. → SD8. |
| V6 | Tv-scherm ook voor geplande dagen? | SD6, SD9 | Ja. → SD9. |
| V7 | Captains automatisch informeren of alleen via gedeelde link? | SD7 | Niet automatisch; de gedeelde link volstaat. SD7 vervalt. |

## I. [Beheer] Clubs toevoegen & toegang (epic)

Doel (Oscar 26-10-2026): **zelf nieuwe clubs toevoegen** en **per club logins + access management**. Past op de bestaande stack (Cloud Run + GCS `gs://baanschemaatje-clubs`); geen aparte user-database nodig in fase 1–2. Neon alleen overwegen als fase 3 echte multi-user accounts met rollenlijst vraagt.

### Wat er al is (overlap)

| Onderdeel | Stand | Story/ref |
|---|---|---|
| Clubprofiel als YAML/JSON, Mierlo eerste profiel | gereed | A1, `clubs/*.yaml` |
| Opslag per club in bucket (profile, season, schedules, bingo, dayrun) | gereed | server `store.py` |
| `POST /clubs` + UI "+ Nieuwe club" (naam, KNLTB-naam, #banen) zonder code-deploy | gedeeltelijk | I1 |
| Instellingen-UI: weekdagen, sluiting, bingo vs gepland, reserveringen, clubafspraken, import | gereed na aanmaken | I2, G1 |
| Ingebouwde YAML-clubs alleen-lezen; opgeslagen club bewerkbaar | gereed | A4 |
| Schrijfhook `auth.authorize_write` (nu: alles open) | gereed als haak | I3, ROADMAP #27 |
| "Geen login; iedereen met commissaris-link mag tikken" | interim-besluit | A4, backlog #12 → I3/I5 |
| Login per club | alleen backlog | backlog #19 → I3 |

### Gefaseerd plan (besloten 26-10-2026)

1. **Fase 1 — Club aanmaken afronden.** Wizard/aanmaak + volledige profielvelden. **Alleen Oscar/platformbeheerder** mag `POST /clubs` (env-allowlist of vergelijkbare gate; niet open self-service). Stack: Cloud Run + GCS. *Geen* Neon. TV/dag blijven publiek (I5).
2. **Fase 2 — Google OAuth per club.** Schrijven (instellingen, import, berekenen, bingo/dashboard-tikken) via `authorize_write` na Google-login; alleen goedgekeurde e-mails per club. **Geen gedeeld clubwachtwoord.** Feature-flag / per-club `auth_required` zodat Mierlo niet breekt tijdens uitrol.
3. **Fase 3 — Rollen & access management.** Rollen: clubbeheerder / baancommissaris (+ platformbeheerder); alleen-kijken via publieke links. Uitnodigen/intrekken via Instellingen → Toegang. TV/dag/bingolijst blijven publiek (I5). **MVP gereed 26-10-2026** (GCS meta.roles + sessie; geen Neon).
4. **Later optioneel — e-mail + wachtwoord per gebruiker.** Individuele accounts (niet één clubwachtwoord). Als wachtwoorden: alleen salted **Argon2id** (of bcrypt) hash; nooit plaintext/reversibel in GCS, logs, chat of UI; HTTPS; rate-limit mislukte logins.

**I1 — [Beheer] Nieuwe club zonder code-deploy.** Als platformbeheerder wil ik een nieuwe club aanmaken (profiel in de bucket) zonder een deploy of YAML in git, zodat we zelf clubs kunnen toevoegen.
- AC: unieke club-id (slug); profiel + meta in store; club verschijnt in clubkeuze en onder `/club/<id>`; geen schrijven naar live Mierlo-testdata; max-clubs-vangrail blijft; ingebouwde YAML blijft alleen-lezen; **alleen Oscar/platformbeheerder** mag aanmaken (env-allowlist of vergelijkbare gate; `POST /clubs` 403 voor anderen; knop "+ Nieuwe club" alleen zichtbaar/bruikbaar voor beheerder).
- Stand nu: Oscar-only gate via `PLATFORM_ADMIN_EMAILS` + Google-sessie (`authorize_platform_admin`); zonder OAuth-config is aanmaken geblokkeerd ("Inloggen vereist"). Wizard: naam, slug, KNLTB-naam, #banen, competitiedagen, avond bingo/gepland, park dicht, marge. Verdere velden via Instellingen (I2).
- Status: **fase 1 gereed** (Google OAuth live op Cloud Run; Oscar kan inloggen en clubs aanmaken) · Datum: 2026-10-26 · Bron: Oscar ("begin").
- Besluitlog: eerdere edit-key per club is destijds bewust geschrapt (open testen); vervangen door I3 i.p.v. opnieuw een losse sleutel zonder login. **Besluit 26-10-2026:** geen self-service club-aanmaken — alleen Oscar/platformbeheerder. **26-10-2026 (later):** Google OAuth-client aangemaakt in project baanschema; credentials gezet op Cloud Run (`GOOGLE_OAUTH_CLIENT_ID` + secret); `/health` → `auth_configured: true`. Redirect URI: `{BS_PUBLIC_BASE_URL}/auth/callback`. Geen secrets in docs.

**I2 — [Beheer] [UX] Clubprofiel volledig via UI.** Als TC wil ik na aanmaken banen, speeldagen, bingo vs gepland, sluitingstijden, avondmarge, reserveringen en clubafspraken instellen en opslaan, zodat de club zonder codewijziging kan draaien.
- AC: zelfde velden als clubprofiel/YAML; opslaan via bestaande `PUT /clubs/{id}/profile`; geen herberekening zonder expliciete knop (A3); democlubs mogen reset.
- Status: **grotendeels gereed** (Instellingen-tabs + rijkere aanmaak-wizard) · Datum: 2026-10-26 · Bron: Oscar.

**I3 — [Beheer] Login per club (schrijven beveiligen).** Als clubbeheerder wil ik dat wijzigen van onze club alleen na inloggen kan, zodat vreemden ons schema/bingo niet kunnen aanpassen.
- AC: alle schrijfroutes via `authorize_write`; 401/403 zonder geldige club-sessie; lezen van publieke schermen volgens I5; democlubs: beleid open vraag (vrij houden of ook locken); Mierlo niet breken tijdens uitrol (feature-flag of per-club `auth_required`).
- AC login-vorm: **Google OAuth** begrensd tot goedgekeurde e-mails per club; **geen gedeeld clubwachtwoord**.
- AC als later e-mail+wachtwoord per user (optioneel, zie I4): wachtwoord alleen als salted **Argon2id** (of bcrypt) hash; **nooit** plaintext of reversibel in GCS, logs, chat of UI-responses; HTTPS; rate-limit op mislukte loginpogingen; geen wachtwoord (noch hash) in access-/error-logs.
- Status: **OAuth live / feature-flag** — Google OAuth + sessiecookie + `writers`/`auth_required` + `/clubs/{id}/access` live op Cloud Run (`auth_configured: true`). Per club `auth_required` (default uit) zodat Mierlo open blijft tot Oscar hem aanzet. Commissaris-schrijven vereist dan login (vervangt interim "iedereen met de link"). · Datum: 2026-10-26 · Bron: Oscar ("begin").
- Besluitlog: interim open schrijven blijft tot `auth_required` (of `BS_AUTH_ENFORCE`) voor die club. **Besluit 26-10-2026:** Google OAuth; geen clubwachtwoord. Env: `GOOGLE_OAUTH_CLIENT_ID/SECRET`, `BS_SESSION_SECRET`, `PLATFORM_ADMIN_EMAILS`, `BS_PUBLIC_BASE_URL`. **26-10-2026 (later):** OAuth-client in Console aangemaakt en op Cloud Run gezet (secret niet in docs/git); knop "Inloggen met Google" in de auth-balk op club-/instellingenpagina's; login-URL `/auth/login`.

**I4 — [Beheer] Rollen & access management.** Als clubbeheerder wil ik rollen toekennen (clubbeheerder, baancommissaris) en toegang intrekken, zodat niet iedereen hetzelfde mag.
- AC: Google-e-mail → rol per club in `meta.roles` (legacy `writers` = club_admin). Rollen:
  - **platform_admin** (`PLATFORM_ADMIN_EMAILS`, Oscar): clubs aanmaken; overal als clubbeheerder.
  - **club_admin** (Clubbeheerder): instellingen, import, toegang/rollen, verzetten, host-away, opgave, schema opslaan, **Nu berekenen**, plus alles van commissaris.
  - **commissaris** (Baancommissaris): speeldag-schrijven — bingo (aanwezig/start/klaar/reset demo), dashboard dayrun, herplan-voorstel; **niet** instellingen/import/rollen/upload/berekenen.
  - **viewer**: zonder login of zonder rol — alleen `/tv`, `/dag`, bingolijst, schema lezen.
- AC: Instellingen → Toegang: e-mail + rol-dropdown (Clubbeheerder | Baancommissaris); platformbeheerder altijd impliciet.
- AC: API 403 met duidelijke NL-tekst bij onvoldoende rol; zonder `auth_required` blijven schrijfacties open (Mierlo/demo-uitrol); met `auth_required` is rol verplicht.
- AC later optioneel: e-mailadres + wachtwoord **per gebruiker** (individuele accounts naast of i.p.v. alleen Google); wachtwoordopslag volgens I3-veiligheids-AC (Argon2id/bcrypt hash-only, rate-limit, geen plaintext in GCS/logs).
- Status: **gereed (MVP)** · Datum: 2026-10-26 · Bron: Oscar ("ik wil verschillende rollen").
- Besluitlog: **Besluit 26-10-2026:** geen gedeeld clubwachtwoord; per-user e-mail+wachtwoord later optioneel. **26-10-2026 (rollen):** TC samengevoegd met clubbeheerder (geen aparte TC-rol in UI); alleen-lezen = publieke links zonder login; commissaris mag **niet** "Nu berekenen" (alleen clubbeheerder); commissaris mag wel speeldag-herplan-voorstel.

**I5 — [Beheer] [UX] Publieke deel-links naast login.** Als TC wil ik tv-scherm, dagpagina en bingolijst (alleen-lezen) kunnen delen zonder dat die personen inloggen, zodat bar/captains meekijken terwijl schrijven wél beveiligd is.
- AC: alleen-lezen routes blijven bereikbaar via bestaande `/tv`, `/dag`, `/bingolijst` (of via apart deel-token als we URLs willen roteren); schrijven vereist I3; commissaris-schrijflink is níet publiek hetzelfde als tv.
- Status: **besloten: houden** (publiek zonder login) · Datum: 2026-10-26 · Bron: Oscar 26-10-2026 (tv- en daglinks blijven publiek).
- Besluitlog: **Besluit 26-10-2026:** tv- en daglinks (en bingolijst alleen-kijken) blijven publiek; geen login voor meekijken.

### Open / besloten vragen (Oscar)

| # | Vraag | Raakt | Stand |
|---|---|---|---|
| Q1 | Wie mag nieuwe clubs toevoegen: alleen Oscar/beheerder, of elke club zelf (self-service)? | I1 fase 1 | **Besloten 26-10-2026:** alleen Oscar/platformbeheerder (env-allowlist). |
| Q2 | Login-vorm: gedeeld clubwachtwoord, Google, of per-persoon accounts? | I3 / I4 | **Besloten 26-10-2026:** fase 2 = Google OAuth per club (geen gedeeld clubwachtwoord). Later optioneel: e-mail + wachtwoord **per gebruiker**. |
| Q3 | Blijven tv / dagpagina / bingolijst publiek deelbaar zonder login? | I5 | **Besloten 26-10-2026:** ja, publiek houden. |
| Q4 | Democlubs (Demo TV, TV Voorbeeld): open laten zonder login, of ook beveiligen? TV Voorbeeld uit clubkeuze verbergen? | I3, A4 | **Open** |
| Q5 | Mag commissaris-tikken (bingo/dashboard) op een kortere code/PIN i.p.v. volledige club-login? | I3/I4 | **Open** |

## Beslisvolgorde (14-10-2026)

1. Opruimen (F5) → 2. Bingo stap 1 (G1) → 3. Bingo stap 2 (G2).

## Backlog

Alle openstaande items, van hoog naar laag. Label: [UX] · [Bingo] · [Planner] · [Dashboard] · [Beheer].

| # | Label | Item | Story | Status |
|---|---|---|---|---|
| 1 | [UX] | Opruimen: jargon naar "Details", 01:00+ i.p.v. 25:00, ⋯-menu per wedstrijd — **hoogste prioriteit** | F5 | klaar (commit 3a5ddcc, 14-10-2026) |
| 2 | [Bingo] | Stap 1: keuze gepland/bingo per speeldag, label, "Avond openen" | G1 | klaar (commit 94a32a7) |
| 3 | [Bingo] | Stap 2: MVP commissarisscherm (aanmelden, banen, wachtrij, start/klaar, één apparaat) | G2 | klaar |
| 4 | [UX] | Deelbare dagpagina (alleen-lezen + WhatsApp/kopieerlink) | F1 | klaar (14-10-2026) |
| 5 | [UX] | Vaste clublink (geen githack-tussenpagina, "voorbeeld" weg, index = clubkeuze) | F2 | klaar: /club/<id> op de Cloud Run-service (14-10-2026); "voorbeeld"-link in kop nog open |
| 6 | [UX] | Dagschema als lijst op telefoon | F3 | klaar (14-10-2026) |
| 7 | [UX] | Overal hetzelfde opslaan (statusregel, badge "definitief schema") | F4 | klaar (14-10-2026) |
| 8 | [Bingo] | Stap 3: voorstel volgende partij + ongedaan maken | G3 | klaar (14-10-2026) |
| 9 | [Bingo] | Stap 4: tv/beamer-scherm (alleen-lezen), vóór meekijken op telefoon | G4 | klaar (14-10-2026) |
| 10 | [Bingo] | Stap 5: print/verslag van de avond | G5 | klaar (14-10-2026) |
| 11 | [Bingo] | Mierlo-vrijdag op bingo | G1 | klaar (besluit 14-10-2026) |
| 12 | [Bingo] | Zonder login: iedereen met de commissaris-link mag tikken — **interim** tot I3 fase 2; tv alleen-kijken = G4 (klaar). Productrichting login: I3–I5 | G2/G4 / I3 | interim / besloten tot fase 2 |
| 13 | [Planner] | Laatste start avond = sluiting − 1:30; donderdag eind 00:00 | B8 | klaar (besluit 14-10-2026) |
| 14 | [Planner] | 27-09 herberekenen op verzoek | — | open |
| 15 | [Planner] | Reisafstand per tegenstander (80 km-regel) | B6 | uitgesteld |
| 16 | [Dashboard] | Speeldag-dashboard met herplannen (ROADMAP fase 3): SD1–SD9 (SD7 vervallen), vragen V1–V7 beantwoord behalve V4 (omwisselen tussen teams) | H | klaar (16-10-2026); V4 open |
| 17 | [Beheer] | Openbaar testbestand met teamnamen/uitslagen geanonimiseerd (`tests/generiek/data/export_anoniem_20261010.xlsx`); origineel nog in git-geschiedenis (39f5781) — history-rewrite alleen op verzoek | — | klaar (14-10-2026) |
| 18 | [Beheer] | CI op `main` rood (validate-schedules-plafonds) — bij Koen | — | open |
| 19 | [Beheer] | Login per club (ROADMAP #27) — Google OAuth live op Cloud Run; aanzetten per club via `auth_required` | I3 / A4 | OAuth live / flag |
| 20 | [Bingo] | Naar een bingo-avond verzette wedstrijden verschijnen bij de commissaris | G2 | klaar (14-10-2026) |
| 21 | [Bingo] | Democlub Demo TV: bingo-vrijdagen 23-10/30-10 om te oefenen + "Reset demo-avond" | G | klaar (17-10-2026) |
| 22 | [Beheer] | Nieuwe club zonder deploy afronden (wizard + Oscar-only gate) | I1 | grotendeels klaar (code); live aanmaken wacht op Google OAuth |
| 23 | [Beheer] [UX] Clubprofiel-wizard bij aanmaken (speeldagen/bingo/sluiting) | I2 | klaar (wizard uitgebreid 26-10-2026) |
| 24 | [Beheer] | Rollen & access management (clubbeheerder / baancommissaris); later optioneel e-mail+wachtwoord per user | I4 | gereed (MVP 26-10-2026) |
| 25 | [Beheer] [UX] Publieke deel-links tv/dag naast login | I5 | besloten: houden (publiek); GET ongewijzigd |
