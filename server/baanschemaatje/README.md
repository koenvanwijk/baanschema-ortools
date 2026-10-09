# Baanschemaatje — live-backend

Kleine FastAPI-service die baanschema's **live** berekent met de generieke
CP-SAT-planner (`src/baanschemaatje`). Staat los van `backend/` en van de
live Pages-site; leest alleen `clubs/*.yaml` en de seizoensexport.

Live: <https://baanschemaatje-356953092000.europe-west1.run.app>
(Google Cloud-project `baanschema`, Cloud Run-service `baanschemaatje`, europe-west1).

## Endpoints

| Methode | Pad | Wat |
|---|---|---|
| GET | `/health` | status, seizoensbestand, clubs |
| GET | `/clubs` | clubprofielen (zelfde samenvatting als de web-GUI) |
| GET | `/dates?club=mierlo` | speeldagen met aantal wedstrijden |
| POST | `/plan` | één speeldag plannen → plan-JSON zoals `web/baanschemaatje/data/<club>/<datum>.json`, plus `summary` en `profile` |
| POST | `/scenarios?combos=false` | oplossingen voor een dag die niet past (zoals `<datum>.solutions.json`) |

```json
POST /plan
{"club": "mierlo", "date": "13-09-2026", "time_limit_s": 20,
 "overrides": {"rules": {"start_window_8p": {"to": "12:00"}}},
 "validate": true}
```

`club` mag ook een inline clubprofiel zijn (zelfde schema als `clubs/*.yaml`).
`time_limit_s` geldt per solverpoging en is begrensd op 30 s; een dag kan tot
zes pogingen doen (2 dagstarts × optimize/feasibility/fit).
`/scenarios` heeft een totaalbudget van ~240 s; per scenario is de rekentijd
dus kort en het resultaat indicatief. De vooraf berekende oplossingen
(`build-web`) rekenen langer.

## Clubs en opslag

Clubs staan in de bucket `gs://baanschemaatje-clubs` (project `baanschema`):
`clubs/<id>/meta.json`, `profile.json` (clubprofiel, zelfde schema als
`clubs/*.yaml`) en `season.tsv` (genormaliseerd seizoen uit de geüploade
KNLTB-export). Een opgeslagen club gaat voor een ingebouwd profiel met
dezelfde id. Ingebouwde profielen (`clubs/*.yaml`) zonder opgeslagen kopie
zijn alleen-lezen.

| Methode | Pad | Wat |
|---|---|---|
| POST | `/clubs` | `{"profile": {...}, "id"?}` → nieuwe club |
| GET | `/clubs/{id}` | profiel (ruw + samenvatting), metadata |
| PUT | `/clubs/{id}/profile` | profiel opslaan (wordt gevalideerd) |
| POST | `/clubs/{id}/season?filename=…&days=zondag` | body = bestand (xlsx/csv/tsv) |
| GET | `/clubs/{id}/season` | speeldagen + wedstrijden |

**Schrijven staat voorlopig open** (besluit Oscar 09-10-2026): iedereen met de
link kan een club aanmaken of wijzigen. Alle schrijfroutes roepen
`auth.authorize_write(club_id, request)` aan; daar komt "Login per club"
(ROADMAP issue 27). Vangrails: max 100 clubs, upload max 5 MB, profielen
worden gevalideerd, aanvoerdersnamen uit de export worden niet opgeslagen.

Seeden (Mierlo + Demo TV):

```bash
python seed_club.py --id mierlo --profile ../../clubs/mierlo.yaml --season ../../data/season_2026-2027.tsv --store /tmp/seed
python seed_club.py --id demo-tv --demo --profile seed/demo-tv.yaml --season seed/demo-season.tsv --store /tmp/seed
gcloud storage cp -r /tmp/seed/clubs gs://baanschemaatje-clubs/
```

### KNLTB-export (bevindingen)

De ruwe export (`docs/wedstrijden_2026-2027.xlsx`, blad "Wedstrijden") heeft
de kolommen `Datum, Schema, Team 1, Team 2, Uitslag, Wedstrijdstatus,
Aanvoerder Team 1, Aanvoerder Team 2`. Er staan alle wedstrijden van alle
afdelingen van de club in (thuis én uit, ook donderdag-/vrijdagavond en
zaterdag); `Datum` bevat ook een tijd. Aantal partijen en speelduur staan er
niet in maar volgen uit het schema (`knltb_import.derive_format`). Rood en
Oranje staan niet in deze competitie-export. Zie `src/baanschemaatje/knltb_import.py`.

## Lokaal

```bash
pip install -e . && pip install -r server/baanschemaatje/requirements.txt
cd server/baanschemaatje && uvicorn app:app --port 8080
# web-GUI tegen lokale server: web/baanschemaatje/index.html?api=http://localhost:8080
pytest tests/generiek/test_server_baanschemaatje.py
```

## Deploy

```bash
gcloud builds submit --project baanschema --region europe-west1 \
  --config server/baanschemaatje/cloudbuild.yaml .
gcloud run deploy baanschemaatje --project baanschema --region europe-west1 \
  --image europe-west1-docker.pkg.dev/baanschema/baanschemaatje/server:latest \
  --allow-unauthenticated --min-instances 0 --max-instances 2 \
  --cpu 8 --memory 4Gi --concurrency 1 --timeout 600 \
  --service-account baanschemaatje-run@baanschema.iam.gserviceaccount.com \
  --set-env-vars BS_WORKERS=8,BS_MAX_TIME_LIMIT=30,BS_STORE=gs://baanschemaatje-clubs
```

8 vCPU is bewust: met 2 vCPU vond CP-SAT voor Mierlo 13-09 binnen de
tijdslimiet maar 22 van 62 partijen; met 8 vCPU alle 62 (0 HARD).
`min-instances 0` = geen kosten als niemand rekent.

Omgevingsvariabelen: `BS_STORE` (gs://bucket of lokale map), `BS_MAX_CLUBS` (100), `BS_MAX_UPLOAD_BYTES` (5 MB), `BS_SEASON`, `BS_CLUBS_DIR`, `BS_MAX_TIME_LIMIT` (30),
`BS_DEFAULT_TIME_LIMIT` (15), `BS_SCENARIO_BUDGET` (240), `BS_WORKERS` (4),
`BS_CORS_ORIGINS` (raw.githack.com, koenvanwijk.github.io, localhost).
