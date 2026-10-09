# Clubprofiel: Mierlose T.V.

**Rol:** eerste referentie-implementatie van een Baanschemaatje-clubprofiel (`clubs/mierlo.yaml`) — **geen** speciaal productgeval.  
**Basis:** `SPEC-core.md` (geldt onverkort; dit bestand bevat alleen overrides en ops van deze vereniging).  
**Status:** skelet voor branch `product/generiek`  
**Bron:** eerdere planningsdocumentatie en operationele praktijk najaar 2026-2027.

Elke andere tennisvereniging krijgt hetzelfde soort document (of config): park-layout, seizoenpaden, UI/ops. De productkern blijft SPEC-core.

---

## Clubprofiel

| Parameter | Waarde (deze club) |
|---|---|
| Vereniging | Mierlose T.V. |
| Banen `N` | 10 |
| Norm-seizoen (actueel) | Najaar 2026-2027 — `data/season_2026-2027.tsv` |
| Historisch | Voorjaar — `data/season.tsv`, `docs/gold_result.json` (geen productnorm) |
| Dagstart voorkeur | 09:00 (terugval 08:30) |
| Avond-deadline | start tot en met 19:30 |
| Pages (operationeel) | `mierlo-2026-2027.html` (goedgekeurd schema als default) |
| Editor | `editor-najaar.html` + opslag (GCS bucket `baanschema-najaar-state`) |

---

## Baanreserveringen / park-layout (override op §3 core)

De **categorieën** Rood, Oranje, Groen en jeugd 11–14 en hun **standaard speelduur** (o.a. Groen en jeugd 11–14 = 45 min) staan in `SPEC-core.md` als KNLTB-standaard — **niet** in dit clubprofiel.

Alleen de *baantoewijzing* op dit park is club-override:

- **Rood:** altijd baan 1, vanaf dagstart (ongeacht of Oranje speelt).
- **Oranje:** banen 1–3 vanaf dagstart; speelt Rood ook, dan Oranje op 2–4.
- **Grote teams (8 partijen):** sterke voorkeur banen 1–4 (onderin het park).

Andere clubs laten deze reserveringen leeg of vullen hun eigen park-layout in op dezelfde manier.

---

## Clubafspraken bovenop het KNLTB-reglement

Rood/Oranje/Groen/jeugd 11–14 horen **niet** hier (zie SPEC-core). De KNLTB-regels uit Competitiereglement Bijlage 3 (11-11-2025) gelden onverkort via SPEC-core. Hieronder staan **clubafspraken** — strenger dan het reglement, géén KNLTB-regels:

| Afspraak (deze club) | KNLTB-grens (SPEC-core) | In `clubs/mierlo.yaml` |
|---|---|---|
| 8-partijenteams: begintijd tussen **10:00 en 11:00, HARD** (reistijd van ver) | gemengd 8p uiterlijk 14:00 **[CR B3 1.1.b]**; begintijd 08:30–16:30 **[CR B3 1.1]** | `rules.start_window_8p` |
| Gemengd 8p niet vóór 10:00, HARD | geen ondergrens behalve 08:30 (en 10:00 bij ≥ 80 km reisafstand **[CR B3 1.2]**) | `rules.mixed_8p_not_before` |
| Jeugd: laatste partij start uiterlijk 17:30 | laatste partij uiterlijk 19:30 **[CR B3 2.1.c]** | `rules.youth_last_start` |
| Team speelt op één vast baanpaar (1+2, 3+4, …) | twee banen per team **[CR B3 2.1.b]** | `court_assignment.pairs` |

- Baan-geheugen gewenst; de vaste baanparen zijn een tijdelijke benadering (productdoel blijft dynamisch geheugen in core).

---

## Operationele waarheid (deze club)

- Goedgekeurd schema (“gold”) + handmatige editor is de bron van waarheid voor gepubliceerde speeldagen/inhaaldagen van **deze** vereniging.
- OR-Tools levert drafts; na verplaatsing naar inhaaldagen moeten artifacts gesynchroniseerd worden (anders TEAM-ONTBREEKT in validator).
- Inhaaldagen (najaar): o.a. 11/18/25 okt, 1 nov (zie editor / recente commits).

Dit ops-patroon (draft → handmatig goedkeuren → publiceren) is herbruikbaar voor andere clubs; de concrete bestanden en data zijn van dit profiel.

---

## UI / copy (dit clubprofiel)

- Captains, kleuren, gap-/violation-weergave op `mierlo-2026-2027.html`.
- Heuristiek / OR / goedgekeurd-schema-toggles op voorjaars-`index.html` (historisch).

Product-UI moet uiteindelijk clubneutraal zijn met config uit het clubprofiel.

---

## Migratie vanaf oude monolithische SPEC.md

Bij de eerste commit op `product/generiek`:

1. Generieke regels → SPEC-core; cluboverrides → dit clubprofiel.
2. `docs/SPEC.md` blijft de operationele SPEC van de live stack (ongewijzigd); de wegwijzer staat in `docs/SPEC-INDEX.md`.
3. `docs/planningsregels.md` blijft historisch / deprecated.

---

## Revisie

| Datum | Wijziging |
|---|---|
| 2026-10-05 | Skelet aangemaakt als club-overrides |
| 2026-10-05 | KNLTB-categorieën uit dit bestand; alleen baanreserveringen |
| 2026-10-05 | Herschreven als eerste clubprofiel / referentie — niet als productcentrum |
| 2026-10-09 | Clubafspraken expliciet als strenger dan KNLTB CR Bijlage 3 (o.a. 8p 10:00–11:00 vs KNLTB max 14:00) |
