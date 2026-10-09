# SPEC-core — generieke planningsregels Baanschemaatje

**Status:** productkern voor branch `product/generiek`  
**Doel:** regels en parameters die voor **elke** tennisvereniging gelden.  
**Clubprofielen:** overrides per vereniging in een apart document (voorbeeld: `SPEC-mierlo.md` = eerste referentie-implementatie).  
**Autoriteit:** bij conflict tussen code en deze core wint SPEC-core; club-afwijkingen staan alleen in het clubprofiel.

Vastgesteld als productrichting: 2026-10-05 (Oscar). Inhoudelijke regels hieronder zijn gedistilleerd uit KNLTB-competitiestandaard en eerdere planningsdocumentatie; fase 0–1 scherpt configureerbare club-parameters verder aan.

**Product:** Baanschemaatje (package `baanschemaatje`, naast de bestaande stack).  
**Houding:** Baanschemaatje is generiek. Geen club is een speciaal geval. Een clubprofiel is configuratie (banen, park-layout, seizoen, UI) — geen parallelle productdefinitie.

**KNLTB-standaard (generiek):** de competitiecategorieën **Rood**, **Oranje**, **Groen** en **jeugd 11 t/m 14 (Junioren)** horen in SPEC-core. **Groen** en **jeugd 11 t/m 14** spelen standaard wedstrijden van **45 minuten (drie kwartier)**. Clubprofielen mogen duur of baanreserveringen alleen overschrijven met expliciete reden; de categorieën zelf verdwijnen niet naar een clubdocument.

---

## Bron: KNLTB-reglement

Regels gemarkeerd met **[CR B3 x.y]** komen uit het KNLTB Competitiereglement Tennis (vastgesteld door het Bestuur d.d. 11-11-2025), Bijlage 3 “Variabele begintijden bij wedstrijden en baanplanning” (op zaterdag en zondag geldt de hele dag variabele begintijden). Zie ook art. 22 en 34 (planning in ten hoogste het door de CM vastgestelde aantal speelronden) en art. 41 (starten, spelen en afspelen van partijen; volgorde van partijen).

- **KNLTB-regels zijn de core-defaults.** Een clubprofiel mag **strenger** zijn (bv. een smaller startvenster), maar nooit ruimer dan het reglement.
- Regels zonder CR-markering zijn **productdefaults** van Baanschemaatje (geen KNLTB-regel); een club mag die aanpassen.
- **Begintijd** = de aanvangstijd van de wedstrijd = start van de eerste partij van het team.
- Let op: art. 22.1/22.2 verwijzen naar “bijlage C” voor speelronden; in deze versie heet de bijlage met speelronden “Bijlage 3”. Bij een nieuwe reglementversie opnieuw controleren.

---

## 0. Productuitgangspunt

- **Input:** KNLTB-wedstrijdprogramma (platte export in fase 1; koppeling later).
- **Config:** clubprofiel — minstens: aantal beschikbare banen, dagstart-voorkeur, avond-deadline, optionele vaste reserveringen.
- **Output:** automatisch **eerste voorstel** per speeldag / seizoen. Handmatige bijsturing is toegestaan; het eerste voorstel moet zonder handwerk ontstaan.
- **Solver:** OR-Tools CP-SAT.
- **Schaal:** hetzelfde pad geldt voor de eerste referentieclub én voor elke volgende vereniging.

---

## 1. Basis en capaciteit (configureerbaar)

| Parameter | Default (referentie) | Club mag overschrijven |
|---|---|---|
| Aantal banen `N` | 10 | ja |
| Tijdgrid | 15 minuten | ja (alleen met expliciete reden) |
| Max 1 partij per baan per slot | hard | nee |
| Geen dubbele boeking dezelfde speler | hard | nee |
| Twee banen per team | elk team kan steeds over twee banen beschikken **[CR B3 2.1.b]** | nee (alleen strenger) |
| Lukt twee banen niet | wedstrijden van 8, 6, 5 resp. 4 partijen in ten hoogste 5, 4, 3 resp. 3 speelronden **[CR B3 2.1.b]** | nee — *nog niet in de planner* |

**Minimale baanreservering per partij** **[CR B3 2.1.a]** — dit is een ondergrens voor de *gereserveerde* tijd, niet de *verwachte* speelduur:

| soort | minimale reservering |
|---|---|
| Elke partij (senioren, gemengd, jeugd 13–17, …) | **1,5 uur** (“minimaal anderhalf uur”) |
| Junioren 11 t/m 14 jaar | **45 min** (“minimaal drie kwartier”) |
| Tenniskids (Rood/Oranje/Groen) | niet expliciet in Bijlage 3 — verwachte duur gebruiken; *te verifiëren* |

De planner reserveert per partij `max(verwachte duur, minimale reservering)`. Een clubprofiel mag de verwachte duur niet onder de minimale reservering zetten.

**Verwachte speelduur per soort** — KNLTB-competitiedefaults (club mag alleen met expliciete reden afwijken):

| soort | duur | Bron |
|---|---|---|
| Rood | 60 min | KNLTB-standaard |
| Oranje | 120 min | KNLTB-standaard |
| Groen | **45 min** (drie kwartier) | KNLTB-standaard |
| Junioren / jeugd (11 t/m 14) | **45 min** (drie kwartier) | KNLTB-standaard |
| Jongens/Meisjes (13 t/m 17) | 90 min | KNLTB-standaard |
| Gemengd | 90 min | KNLTB-standaard |
| Senioren (Heren/Dames) | 90 min | KNLTB-standaard |

---

## 2. Begintijden en limieten

| Regel | Core-default | Hard/soft | Bron |
|---|---|---|---|
| Begintijd alleen op hele of halve uren | :00 / :30 | hard | **[CR B3 1.1]** |
| Begintijd niet vroeger dan / niet later dan | 08:30 – 16:30 | hard | **[CR B3 1.1]** |
| Juniorencompetities: begintijd | 08:30 – 12:00 | voorkeur (zacht) | **[CR B3 1.1.a]** |
| Junioren, bij baancapaciteitsproblemen | uiterlijk **13:00** bij 8 partijen gemengd junioren, uiterlijk **15:00** bij de overige competities | hard | **[CR B3 1.1.a]** |
| Reguliere gemengde 8 partijen-competitie | begintijd uiterlijk **14:00** | hard | **[CR B3 1.1.b]** |
| Reisafstand uitspelend team ≥ 80 km | niet vóór 10:00 | hard (zodra reisafstand in de input staat) | **[CR B3 1.2]** |
| Laatste partij van een wedstrijd | begint uiterlijk **19:30** | hard | **[CR B3 2.1.c]** |
| Standaard dagstart | 09:00, terugval 08:30 | voorkeur | product |
| Eerste partij overige teams | ≤ 15:00 | zacht | product |
| 8-partijenteams: smaller startvenster | geen (= KNLTB-grenzen) | — | club mag strenger (bv. 10:00–11:00) |

Interpretatie (te verifiëren): “juniorencompetities” = Junioren 11–14 en Jeugd 13–17; Tenniskids (Rood/Oranje/Groen) vallen daar niet onder.

---

## 3. Baan-toewijzing (generiek)

- **Vaste reserveringen:** optioneel in clubprofiel (bijv. “soort X altijd op baan Y vanaf dagstart”). Zonder reserveringen: vrije toewijzing binnen capaciteit.
- **Baan-geheugen:** zodra een team zijn eerste partij(en) speelt, worden die banen de thuisbasis; volgende partijen bij voorkeur op of strak naast die banen (voorkomt baanhoppen).
- **Max breedte:** begrens aantal gelijktijdige banen per team (default ≤ 2, tenzij 8p-fasering anders vereist).

> **Open punt:** vaste court-pairs vs dynamisch geheugen — productdefault = dynamisch geheugen; vaste pairs alleen als club-optie of tijdelijke benadering.

---

## 4. Team-prioriteit (inplan-volgorde)

Dwingende default-volgorde op KNLTB-categorieën (club mag herordenen in profiel; de categorieën zelf blijven core):

1. Rood en Oranje (KNLTB; eventuele *baan*reservering is clubprofiel)
2. Grote teams (8 partijen) — om startvenster te garanderen
3. Groen (KNLTB, standaard 45 min)
4. Junioren / jeugd 11 t/m 14 (KNLTB, standaard 45 min)
5. Jongens/Meisjes (13 t/m 17)
6. Gemengd
7. Heren / Senioren / overig

---

## 5. Fasering en gelijktijdigheid

- Teams spelen bij voorkeur in fases (singles → dubbels → gemengd), dynamisch om wachttijd te beperken.
- Niet wachten op symmetrie: 1 vrije baan → start direct.
- Volle breedte benutten wanneer meerdere banen vrij zijn.
- **Max opeenvolgende wachttijd** tussen activiteiten van hetzelfde team: default 60 minuten (hard of sterk soft — TBD).
- 8-partijenteams: harde S→D→(G) waterfall + ronde-logica zoals in de bestaande planner, tenzij clubprofiel anders bepaalt (productdefault; de volgorde van partijen zelf volgt art. 41).

---

## 6. Onplanbaar / waarschuwingen (beleid — TBD)

Twee mogelijke productregels (één kiezen in fase 1):

**A.** Altijd inplannen en problemen taggen (bijv. `[>19:30]`, overschrijding eerste-start).  
**B.** Onplanbare partijen als `NIET_GELUKT` laten staan en in UI rood tonen.

Huidige code volgt vooral **B**. Eerdere clubdocumentatie neigt naar **A**.  
**Besluit nodig** voordat CI HARD-ratchets productbreed worden.

---

## 7. Wedstrijddag-herplan (fase 3)

- Input: actueel schema + wat al gespeeld / afgebroken / uitgevallen / uitgelopen is.
- Output: herplan van **resterende** partijen op beschikbare banen/tijd.
- Mag handmatige locks respecteren (vaste banen/tijden die de club vasthoudt).
- **Wanneer verplicht [CR B3 2.2]:** de CL maakt een nieuwe planning als door (weers)omstandigheden de partijen ten minste **één uur** later worden gespeeld dan gepland.
- **Voorrangsregels bij de nieuwe planning [CR B3 2.2], in deze volgorde:**
  1. **afgebroken partijen** gaan voor partijen die nog moeten beginnen (a);
  2. partijen van teams met een reisafstand van **meer dan 80 km** gaan voor andere partijen (b);
  3. **alle (resterende) partijen van één wedstrijd** laten (af)spelen gaat voor het (af)spelen van slechts een deel van de partijen in andere wedstrijden (c).
- Daarbij gelden ook bij herplannen art. 41 en de grenzen uit §1–§2 (o.a. laatste partij ≤ 19:30) **[CR B3 2.3]**.
- Let op het verschil in formulering: bij begintijden “80 km of meer” (1.2), bij herplannen “meer dan 80 km” (2.2.b).

---

## 8. Niet-doelen van SPEC-core

- Clubkleuren, captainsteksten, club-specifieke HTML-pagina’s (horen in clubprofiel / UI-config).
- Eén club’s goedgekeurde (“gold”) schema als productnorm — dat is ops voor die club, geen generieke eis.
- Keuze voor andere solvers dan OR-Tools.

---

## Revisie

| Datum | Wijziging |
|---|---|
| 2026-10-05 | Skelet aangemaakt voor productbranch |
| 2026-10-05 | KNLTB: Rood/Oranje/Groen/jeugd 11–14 in core; Groen + jeugd 11–14 = 45 min |
| 2026-10-05 | Houding: product volledig generiek; eerste clubprofiel is referentie, geen uitzondering |
| 2026-10-09 | Productnaam Baanschemaatje; implementatie start in `src/baanschemaatje/` |
| 2026-10-09 | KNLTB CR Bijlage 3 (11-11-2025) als core-defaults met bronvermelding: begintijden, minimale reservering vs verwachte duur, twee banen/speelronden, 19:30, herplan-voorrang |
