# Master planningsregels baanschema — seizoen 2026+

Dit is de gezaghebbende spec. Bij twijfel tussen dit document, de code en
`data/season.tsv` wint dit document.

Vastgesteld: 2026-08-24, aangevuld met besluiten van 2026-08-26. Vervangt
`docs/planningsregels.md`.

**Uitgangspunt is het laatst aangeleverde wedstrijdprogramma**
(`data/season_2026-2027.tsv`, zes zondagen september/oktober 2026). Het
voorjaarsseizoen in `data/season.tsv` en het handmatige schema in
`docs/gold_result.json` zijn historisch materiaal, geen norm. (Oscar, 26-08-2026)

Secties 1 t/m 6 zijn de regels zoals aangeleverd. Secties 7 en 8 zijn
overgenomen uit de vorige versie omdat de nieuwe regels ze niet behandelen en ze
nog steeds gelden. De **Notities bij invoering** aan het eind zijn van de
implementatie, niet van de regels zelf.

---

## 1. Basis en capaciteit

- **Park:** 10 beschikbare banen.
- **Tijdsloten:** planning verloopt in blokken van 15 minuten.
- **Bezetting:** maximaal 1 partij per baan per tijdslot. Geen dubbele boekingen
  voor spelers.
- **Speelduur per soort:**

  | soort | duur |
  |---|---|
  | Rood | 60 min |
  | Oranje | 120 min |
  | Groen | 45 min |
  | Junioren (11 t/m 14) | 45 min |
  | Jongens/Meisjes (13 t/m 17) | 90 min |
  | Gemengd | 90 min |
  | Senioren (Heren/Dames) | 90 min |

## 2. Starttijden en harde tijdslimieten

- **Standaard dagstart:** 09:00. Dit is de **voorkeur/default** voor alle
  dag-gebaseerde logica, inclusief de reserveringsvensters van Rood/Oranje in
  sectie 3 (besluit Oscar/Koen 2026-08-26).
- **Vroege dagstart:** alleen terugvallen op 08:30 indien noodzakelijk om te
  voorkomen dat partijen de avond-deadline overschrijden, of om te veel
  onplanbare (`NIET_GELUKT`) partijen te voorkomen omdat er te veel wedstrijden
  zijn om op tijd te starten met 09:00 als beginpunt. Op zeer rustige dagen mag
  het schema vanzelf opschuiven naar een start om 10:00.
- **Avond-deadline:** wedstrijden mogen starten tot en met 19:30.
- **Deadline eerste partij per team:**

  | team | eerste partij start uiterlijk |
  |---|---|
  | Junioren (11 t/m 14) | 13:00 |
  | Grote teams (8 partijen) | tussen 10:00 en 11:00 — **HARD**, niet aanpasbaar (reistijd van ver) |
  | overige reguliere teams | 15:00 |

  Het startvenster van 10:00-11:00 voor 8-partijenteams (landelijke
  competitie) blijft een harde eis: deze teams reizen van ver en kunnen niet
  eerder of later starten (besluit Oscar/Koen 2026-08-26, bevestigt bestaand
  gedrag — geen wijziging nodig).

## 3. Baan-toewijzing en baan-geheugen

- **Rood:** speelt altijd op baan 1, vanaf de dagstart. Naast die baan is extra
  ruimte die meegebruikt wordt, dus baan 1 is geen willekeurige keuze.
  (Oscar, 26-08-2026) Rood krijgt baan 1
  ongeacht of Oranje die dag ook speelt (besluit Oscar/Koen 2026-08-26,
  bevestigt de bestaande regel — de bug zat in de code, niet in de spec).
- **Oranje:** speelt altijd vanaf de dagstart op baan 1, 2 en 3. Speelt Rood ook
  die dag, dan schuift Oranje op naar baan 2, 3 en 4 (Rood houdt baan 1).
- **Grote teams (8 partijen):** sterke voorkeur voor baan 1 t/m 4, onderin het park.
- **Baan-geheugen (vaste uitvalsbasis):** zodra een team zijn eerste partij(en)
  speelt en daarvoor banen pakt, worden die baannummers vastgelegd als de
  thuisbasis van dat team. Bij alle volgende partijen plant de planner exclusief
  op — of strak naast — die specifieke banen, om baanhoppen te voorkomen.

## 4. Team-prioriteit (inplan-volgorde)

De banen worden in deze dwingende volgorde uitgedeeld:

1. Rood en Oranje
2. Grote teams (8 partijen) — om hun slot van 10:00 te garanderen
3. Groen
4. Junioren (11 t/m 14)
5. Jongens en Meisjes (13 t/m 17)
6. Gemengd — start überhaupt pas vanaf 10:00
7. Heren / Senioren

## 5. Fasering en gelijktijdigheid (de "breedte"-regels)

Teams spelen in fases (singles → dubbels → gemengd), maar dynamisch, om
wachttijden te minimaliseren.

- **Niet wachten op symmetrie:** is een team aan de beurt en is er maar 1 baan
  vrij, start daar direct de eerste single. Niet wachten tot er 2 vrij zijn.
- **Volle breedte benutten:** moeten er 4 singles gepland worden en zijn er 4
  aaneengesloten banen vrij, start ze alle 4 tegelijk. Vooral in de middag geeft
  dit grote tijdwinst.
- **Uitzondering 5-wedstrijdteams (S en GD tegelijk):** deze teams hebben genoeg
  spelers, dus hun singles én hun gemengd dubbel mogen samen in fase 1 starten.
  Ze kunnen dus op 3 banen tegelijk openen. Daarna volgt fase 2, de dubbels.
- **Uitzondering 8-wedstrijdteams (strikte waterval, HARD):** deze teams bestaan
  uit slechts 4 spelers en moeten strikt in 3 fases spelen zonder overlap:
  fase 1 singles → fase 2 dubbels → fase 3 gemengd dubbels. HD/DD en GD mogen
  nooit tegelijk starten, en geen enkele partij van fase N+1 mag starten voordat
  alle partijen van fase N klaar zijn. Dit is een **harde eis**: een landelijk
  8-partijenteam speelt op hoog niveau met te weinig spelers om fases door
  elkaar te laten lopen.
- **Overige teams (SOFT, besluit Oscar/Koen 2026-08-26):** voor 5-partijenteams,
  niet-gemengde teams en alle overige teamsoorten is de waterval-volgorde een
  **voorkeur**, geen harde eis. Een schending telt als zachte penalty in de
  objective/metrics, niet als harde overtreding. Reden: bij deze teams weegt een
  optimaler baanschema en een betere baanbezetting zwaarder dan strikte
  fasering — in de praktijk (zie gold-schema) wordt de waterval bij deze teams
  toch al regelmatig doorbroken zonder dat dit een probleem is.

## 6. Foutafhandeling (niet-blocking)

- De planner mag nooit vastlopen als het niet past.
- Overschrijdt een partij noodgedwongen een tijdslimiet, dan wordt hij **alsnog
  ingepland**, met een opvallende waarschuwingstag en een rode achtergrond ter
  controle. Tags: `[>19:30]`, `[>15:00]`, `[>13:00]`, `[>11:00]`.

## 7. Herplanning op wedstrijddag

Overgenomen uit de vorige versie; de nieuwe regels behandelen dit niet.

- Afgevinkte partijen worden vastgezet.
- Lopende partijen op `now` worden als bezet beschouwd.
- Overige partijen schuiven door in stappen van 15 minuten, met behoud van
  constraints.
- Is er maar 1 baan vrij, dan mag de planner alvast 1 partij uit een ronde
  starten: compactheid boven symmetrie. Dit is dezelfde regel als "niet wachten
  op symmetrie" in sectie 5.
- Bij voorkeur blijft een partij op dezelfde baan als in de oorspronkelijke
  planning. Dit is het baan-geheugen uit sectie 3.

## 8. Zachte voorkeuren

Optimalisatiedoelen, geen harde eisen. Overgenomen uit de vorige versie, waar ze
uit het handmatige referentieschema (`docs/gold_result.json`) waren afgeleid.
Sectie 3 en 5 dekken een deel hiervan nu hard af.

- **Aaneengesloten teamverloop:** plan een team bij voorkeur in één doorlopend
  speelblok; minimaliseer het aantal blokken en de wachttijd binnen een team.
- **Rondegewijze afwikkeling:** plan bij voorkeur complete rondes in plaats van
  losse verspreide starts. Ondergeschikt aan "niet wachten op symmetrie".
- **Compactheid boven kunstmatig vroeg starten:** vermijd vroege starts die
  later extra gaten veroorzaken.
- **Teamdoorlooptijd boven pure baanvulling:** een hogere bezettingsgraad is
  wenselijk, maar niet ten koste van een sterk verlengde teamdoorlooptijd.
- Basisvolgorde jong naar oud, gemengd later. Formeel vastgelegd in sectie 4.

---

## Welke teams zijn "5-wedstrijd" en "8-wedstrijd"?

Uit `data/season.tsv`, seizoen 2026:

| type | schema's | partijen | samenstelling |
|---|---|---|---|
| 8-wedstrijdteam | `Gemengd Zondag (2DE-2HE-DD-HD-2GD)` | 8 | 4 singles, 2 dubbels, 2 gemengd |
| 5-wedstrijdteam | `Gemengd Zondag (DE-HE-GD-DD-HD)` | 5 | 2 singles, 2 dubbels, 1 gemengd |

Alle overige teams spelen 6 partijen (4 singles, 2 dubbels). Beide
uitzonderingen in sectie 5 gaan dus over Gemengd-teams; het onderscheid zit in
het schema tussen haakjes, niet in de klasse.

## Notities bij invoering

Van de implementatie, niet van de regels. Getoetst tegen commit `1ba4d55` op
2026-08-24.

### Wat al klopt

- **Dagstart 09:00 met terugval naar 08:30** — geïmplementeerd in commit
  `143bed0` (`ortools_planner.py:161-178`). Vier van de zes zondagen in
  `data/season_2026-2027.tsv` draaien op 09:00, twee vallen terug.
- **Speelduren** — `data/season_2026-2027.tsv` is volledig consistent met
  sectie 1: Groen en Junioren 45, alle 13-17 / Gemengd / Heren 90, Rood 60,
  Oranje 120 (3 banen).
- **Gemengd niet voor 10:00** en **8-partijenteams bij voorkeur op baan 1 t/m 4**
  zitten al in het model.

### Twee conflicten tussen sectie 3 en de code — OPGELOST 2026-08-26

**Rood en Oranje stonden omgewisseld.** Sectie 3 zegt: Rood speelt *altijd* op
baan 1, en Oranje schuift op naar 2, 3, 4 als Rood ook speelt.
`ortools_planner.py:354-359` deed het omgekeerd — Oranje hield 1, 2, 3 en Rood
verhuisde naar baan 4. Gefixt op 2026-08-26: Rood krijgt nu consequent baan 1,
Oranje schuift naar 2, 3, 4 zodra Rood ook speelt.

**Reserveringen negeerden de dagstart.** De vensters stonden hard op
`8 * 60 + 30`, terwijl `start_min = day_start_pref` is. Op een dag die om 09:00
begint werd Rood dus van 08:30 tot 09:30 gereserveerd — een half uur vóór de
dagstart. Gefixt op 2026-08-26: de reserveringsvensters gebruiken nu
`day_start_pref` (dus 09:00 als dat de dagstart is), met terugval naar 08:30
alleen als 09:00 niet haalbaar is (dezelfde escalatieladder als de rest van de
dagstart-logica in sectie 2).

## Besluiten Oscar/Koen (2026-08-26)

Op basis van de open punten hieronder en Discord `#baanschema` van 24-08-2026
zijn de volgende vier besluiten genomen:

1. **8-partijenteams startvenster 10:00-11:00 blijft HARD.** Niet aanpasbaar:
   deze teams reizen van ver. Bevestigt bestaand gedrag, geen codewijziging
   nodig — alleen expliciet gedocumenteerd in sectie 2.
2. **Fasering S→D→GD (waterval):**
   - **8-partijenteams: HARD.** Landelijke competitie, hoog niveau, slechts 4
     spelers — strikte waterval blijft een harde eis.
   - **Overige teams (5-partijenteams, niet-gemengde teams, etc.): SOFT.** Een
     optimaler baanschema/bezetting weegt hier zwaarder dan strikte fasering.
     Schendingen tellen als zachte penalty in de objective, niet als harde
     overtreding. Zie sectie 5.
3. **Rood/Oranje baanvolgorde:** Rood krijgt altijd baan 1, Oranje schuift naar
   2-3-4 als Rood ook speelt. De bug in `ortools_planner.py:354-359` (Oranje op
   1-2-3, Rood op 4) is gefixt.
4. **Reserveringsvensters Rood/Oranje:** gebruiken nu de dagstart-tijd
   (`day_start_pref`, standaard 09:00) als basis. 08:30 blijft de fallback
   wanneer 09:00 niet haalbaar is.

### Wat de nieuwe regels intrekken

De harde grens "Jeugd 13-17 start pas vanaf 11:00" (`ortools_planner.py`, commit
`e1a65d9`) komt in deze spec in geen enkele vorm voor. Die grens kost partijen en
spreekt het handmatige schema 68 keer tegen. Hij vervalt hiermee.

### Wat sectie 6 verandert aan het model

De planner laat nu partijen vallen als ze niet passen, gemarkeerd als
`NIET_GELUKT`. Sectie 6 zegt dat dat niet mag: alles wordt ingepland, en een
overschrijding krijgt een tag. Daarmee wordt "alles gepland" een harde eis en
worden de deadlines uit sectie 2 zacht, met een tag als uitkomst. Dat is een
andere opzet dan de huidige objective en raakt ook `build_pages.py`, dat de tags
en de rode achtergrond moet weergeven.

### Nog niet geïmplementeerd

Het baan-geheugen uit sectie 3 (de code kent alleen een vast baanpaar per team),
de inplan-volgorde uit sectie 4, de drie deadlines uit sectie 2 (de first-match
cutoff is een zachte voorkeur; een harde variant is in `38357ce` teruggedraaid
omdat hij meer `NIET_GELUKT` gaf), en de faseregels uit sectie 5. Zie
`docs/REFACTOR_PLAN.md`.

### Verhouding tot het spec-experiment

`docs/experiments/oscar-2026-08-24-spec.md` bevat de eerdere, als systeemprompt
geformuleerde versie van deze regels, met een werkend experiment in
`scripts/experiments/oscar_spec_planner.py` dat alle zes zondagen oplost zonder
overschrijdingen. Dit document is de leesbare masterversie en gaat verder op vier
punten die daar niet in staan: de speelduren per soort, de terugval-logica voor
de dagstart, het baan-geheugen als expliciete regel, en de breedte-regels uit
sectie 5.

Waar de twee elkaar tegenspreken, wint dit document. Eén verschil om in de gaten
te houden: het experiment zet Rood en Oranje op index 2 (09:00) of 0 (08:30) met
Oranje op baan 0, 1, 2 — dat is de code-conventie, niet die van sectie 3.

## Wat de spec betekent voor de bestaande schema's

`scripts/validate_schedule.py` toetst sinds 2026-08-24 ook sectie 2 (deadline
eerste partij), sectie 4 (gemengd vanaf 10:00) en sectie 5 (fases). Stand:

| bron | HARD | waarvan `FASE` | waarvan `EERSTE-START` |
|---|---|---|---|
| gold (handmatig) | 26 | 10 | 9 |
| heuristiek | 26 | 10 | 15 |
| OR-Tools | 60 | 22 | 8 |

Twee dingen vallen op.

**Elk 8-partijenteam in het gold-schema start te laat.** Sectie 2 wil ze tussen
10:00 en 11:00; het handmatige schema zet ze op 11:15, 12:00 en 13:30 — negen
gevallen, geen enkele uitzondering. Sectie 4 geeft die teams juist prioriteit 2
"om hun slot van 10:00 te garanderen". De menselijke planner doet dus
systematisch het omgekeerde. Er is geen enkele overtreding van de deadlines van
13:00 (Junioren) en 15:00 (overige teams); die twee zijn niet in geding.

**De faseregels worden door alle drie de bronnen gebroken.** Bij de
5-partijenteams start het dubbel voordat de fase S+GD klaar is; bij de
8-partijenteams start het gemengd dubbel voordat de dubbels klaar zijn; en bij
twee niet-gemengde teams start het dubbel voordat de laatste single is
afgelopen. Het model bewaakt nu alleen dat soorten niet *tegelijk* spelen, wat
zwakker is dan een waterval: S1+S2, dan D1+D2, dan S3+S4 overlapt nergens maar
breekt de fasering wel.

Beide punten zijn een keuze, geen bug: of de spec is te streng, of de bestaande
schema's waren dat niet streng genoeg. Zie de open punten hieronder en de vragen
in Discord `#baanschema` van 24-08-2026.

## Open punten in de spec

1. ~~**Sectie 5 motiveert de strikte waterval met "slechts 4 spelers", maar het
   5-partijenteam heeft er ook 4.**~~ **Beantwoord 2026-08-26:** het onderscheid
   zit niet (meer) in de teamgrootte, maar in het niveau/de competitie. Alleen
   8-partijenteams (landelijke competitie) krijgen de harde waterval; overige
   teams, inclusief 5-partijenteams, krijgen 'm als zachte voorkeur omdat een
   optimaler baanschema daar zwaarder weegt. Zie "Besluiten Oscar/Koen
   (2026-08-26)" hierboven.
2. **Sectie 6 noemt een tag `[>11:00]`.** De andere drie horen bij de deadlines
   uit sectie 2 (19:30, 15:00, 13:00). Bij welke regel hoort 11:00 — de
   bovengrens van het startvenster van de 8-partijenteams?
3. **Sectie 3 en sectie 5 kunnen botsen.** Het baan-geheugen wil een team op
   vaste banen houden; "volle breedte benutten" wil 4 aaneengesloten banen pakken
   voor 4 singles. Welke gaat voor als de thuisbasis 2 banen is?
4. **Geldt de deadline van 15:00 ook voor Groen?** Sectie 2 zegt "overige
   reguliere teams". Rood en Oranje zijn reserveringen met een vaste starttijd,
   maar Groen is een gewoon team en heeft geen eigen deadline in sectie 2.
5. **Sectie 2 zegt dat het schema op rustige dagen "vanzelf mag opschuiven naar
   10:00".** Is dat een toegestaan gevolg van de optimalisatie, of een expliciete
   voorkeur die het model moet nastreven? Dat verschil bepaalt of het een
   constraint of een objective-term wordt.
