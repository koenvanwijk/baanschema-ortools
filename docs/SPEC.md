# Master planningsregels baanschema — seizoen 2026+

Dit is de gezaghebbende spec. Bij twijfel tussen dit document, de code en
`data/season.tsv` wint dit document.

Vastgesteld: 2026-08-24. Vervangt `docs/planningsregels.md`.

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

- **Standaard dagstart:** 09:00.
- **Vroege dagstart:** alleen terugvallen op 08:30 indien noodzakelijk om te
  voorkomen dat partijen de avond-deadline overschrijden. Op zeer rustige dagen
  mag het schema vanzelf opschuiven naar een start om 10:00.
- **Avond-deadline:** wedstrijden mogen starten tot en met 19:30.
- **Deadline eerste partij per team:**

  | team | eerste partij start uiterlijk |
  |---|---|
  | Junioren (11 t/m 14) | 13:00 |
  | Grote teams (8 partijen) | tussen 10:00 en 11:00 |
  | overige reguliere teams | 15:00 |

## 3. Baan-toewijzing en baan-geheugen

- **Rood:** speelt altijd op baan 1, vanaf de dagstart.
- **Oranje:** speelt altijd vanaf de dagstart op baan 1, 2 en 3. Speelt Rood ook
  die dag, dan schuift Oranje op naar baan 2, 3 en 4.
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
- **Uitzondering 8-wedstrijdteams (strikte waterval):** deze teams bestaan uit
  slechts 4 spelers en moeten strikt in 3 fases spelen zonder overlap:
  fase 1 singles → fase 2 dubbels → fase 3 gemengd dubbels. HD/DD en GD mogen
  nooit tegelijk starten.

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

### Twee conflicten tussen sectie 3 en de code

**Rood en Oranje staan omgewisseld.** Sectie 3 zegt: Rood speelt *altijd* op baan
1, en Oranje schuift op naar 2, 3, 4 als Rood ook speelt.
`ortools_planner.py:354-359` doet het omgekeerd — Oranje houdt 1, 2, 3 en Rood
verhuist naar baan 4:

```python
if r.kind == "oranje":
    for c in [1, 2, 3]:
        reserved.append((c, 8 * 60 + 30, 10 * 60 + 30))
elif r.kind == "rood":
    rood_court = 4 if "oranje" in kinds_today else 1
```

Ook de vorige regelversie zei al "Oranje naar 2, 3, 4", dus dit staat los van de
nieuwe spec: de code week op dit punt altijd al af.

**Reserveringen negeren de dagstart.** De vensters hierboven staan hard op
`8 * 60 + 30`, terwijl `start_min = day_start_pref` is. Op een dag die om 09:00
begint wordt Rood dus van 08:30 tot 09:30 gereserveerd — een half uur vóór de
dagstart. Sectie 3 zegt "vanaf de dagstart".

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

## Open punten in de spec

1. **Sectie 5 motiveert de strikte waterval met "slechts 4 spelers", maar het
   5-partijenteam heeft er ook 4.** Bij `DE-HE-GD-DD-HD` kosten 2 singles plus
   1 gemengd dubbel samen 2 dames en 2 heren — precies vier spelers. Het
   onderscheid tussen de twee uitzonderingen zit dus niet in de teamgrootte. Wat
   is de eigenlijke reden: rust tussen partijen, of iets anders?
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
