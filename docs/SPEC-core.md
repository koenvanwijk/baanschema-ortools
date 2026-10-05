# SPEC-core — generieke planningsregels Baanschema

**Status:** productkern voor branch `product/generiek`  
**Doel:** regels en parameters die voor **elke** tennisvereniging gelden.  
**Clubprofielen:** overrides per vereniging in een apart document (voorbeeld: `SPEC-mierlo.md` = eerste referentie-implementatie).  
**Autoriteit:** bij conflict tussen code en deze core wint SPEC-core; club-afwijkingen staan alleen in het clubprofiel.

Vastgesteld als productrichting: 2026-10-05 (Oscar). Inhoudelijke regels hieronder zijn gedistilleerd uit KNLTB-competitiestandaard en eerdere planningsdocumentatie; fase 0–1 scherpt configureerbare club-parameters verder aan.

**Houding:** Baanschema is generiek. Geen club is een speciaal geval. Een clubprofiel is configuratie (banen, park-layout, seizoen, UI) — geen parallelle productdefinitie.

**KNLTB-standaard (generiek):** de competitiecategorieën **Rood**, **Oranje**, **Groen** en **jeugd 11 t/m 14 (Junioren)** horen in SPEC-core. **Groen** en **jeugd 11 t/m 14** spelen standaard wedstrijden van **45 minuten (drie kwartier)**. Clubprofielen mogen duur of baanreserveringen alleen overschrijven met expliciete reden; de categorieën zelf verdwijnen niet naar een clubdocument.

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

**Speelduur per soort** — KNLTB-competitiedefaults (club mag alleen met expliciete reden afwijken):

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

## 2. Starttijden en limieten

| Regel | Default | Hard/soft |
|---|---|---|
| Standaard dagstart | 09:00 | voorkeur |
| Vroege dagstart | 08:30 alleen indien nodig (avond-deadline / te veel onplanbaar) | soft terugval |
| Avond-deadline (laatste start) | 19:30 | hard (of getagd — zie §6) |
| Eerste partij Junioren | ≤ 13:00 | TBD: hard of getagd soft |
| Eerste partij grote teams (8 partijen) | start tussen 10:00 en 11:00 | **HARD** (tenzij club in profiel uitzet) |
| Eerste partij overige reguliere teams | ≤ 15:00 | TBD: hard of getagd soft |
| Gemengd 8p | niet vóór 10:00 | hard voor 8p; zachte voorkeur voor kleinere teams |

> **Open besluit (issue):** 8p-venster en eerste-start-deadlines moeten in de planner worden afgedwongen of bewust als club-toggle / SPEC-bijstelling worden vastgelegd.

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
- 8-partijenteams: harde S→D→(G) waterfall + ronde-logica zoals in de bestaande planner, tenzij clubprofiel anders bepaalt.

---

## 6. Onplanbaar / waarschuwingen (beleid — TBD)

Twee mogelijke productregels (één kiezen in fase 1):

**A.** Altijd inplannen en problemen taggen (bijv. `[>19:30]`, overschrijding eerste-start).  
**B.** Onplanbare partijen als `NIET_GELUKT` laten staan en in UI rood tonen.

Huidige code volgt vooral **B**. Eerdere clubdocumentatie neigt naar **A**.  
**Besluit nodig** voordat CI HARD-ratchets productbreed worden.

---

## 7. Wedstrijddag-herplan (fase 3)

- Input: actueel schema + wat al gespeeld / uitgevallen / uitgelopen is.
- Output: herplan van **resterende** partijen op beschikbare banen/tijd.
- Mag handmatige locks respecteren (vaste banen/tijden die de club vasthoudt).

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
