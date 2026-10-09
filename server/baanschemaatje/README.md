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
  --set-env-vars BS_WORKERS=8,BS_MAX_TIME_LIMIT=30
```

8 vCPU is bewust: met 2 vCPU vond CP-SAT voor Mierlo 13-09 binnen de
tijdslimiet maar 22 van 62 partijen; met 8 vCPU alle 62 (0 HARD).
`min-instances 0` = geen kosten als niemand rekent.

Omgevingsvariabelen: `BS_SEASON`, `BS_CLUBS_DIR`, `BS_MAX_TIME_LIMIT` (30),
`BS_DEFAULT_TIME_LIMIT` (15), `BS_SCENARIO_BUDGET` (240), `BS_WORKERS` (4),
`BS_CORS_ORIGINS` (raw.githack.com, koenvanwijk.github.io, localhost).
