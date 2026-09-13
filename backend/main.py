from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Baanschema Backend", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "season.tsv"
RESULT_JSON_CANDIDATES = [
    ROOT / "docs" / "result.json",  # repo root deploy
    Path(__file__).resolve().parent / "result.json",  # backend-only deploy
]


def load_rows() -> list[dict[str, str]]:
    if not INPUT.exists():
        return []
    with INPUT.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def load_result() -> dict[str, Any]:
    import json

    for p in RESULT_JSON_CANDIDATES:
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
    raise HTTPException(status_code=404, detail="result.json not found")


class ReplanRequest(BaseModel):
    date: str
    now: str
    completed: list[dict[str, str]] = []


# ── Najaar 2026-2027 editor: server-side opslag van herplande schema's ─────
#
# We bewaren de (door de gebruiker bewerkte) najaarsschema's in een GCS bucket
# in plaats van in localStorage, zodat iedereen die de editor opent dezelfde
# stand ziet. Bucketnaam via env var NAJAAR_STATE_BUCKET, default hieronder.
NAJAAR_STATE_BUCKET = os.environ.get("NAJAAR_STATE_BUCKET", "baanschema-najaar-state")
NAJAAR_STATE_BLOB = "najaar-2026-2027/schema.json"

_najaar_gcs_client = None


def _najaar_blob():
    global _najaar_gcs_client
    if _najaar_gcs_client is None:
        from google.cloud import storage  # type: ignore

        _najaar_gcs_client = storage.Client()
    bucket = _najaar_gcs_client.bucket(NAJAAR_STATE_BUCKET)
    return bucket.blob(NAJAAR_STATE_BLOB)


class NajaarSchemaPayload(BaseModel):
    # { "11-10-2026": [...rows...], "18-10-2026": [...], ... }
    schema: dict[str, list[dict[str, Any]]]
    updated_by: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"ok": "true"}


@app.get("/dates")
def dates() -> dict[str, Any]:
    rows = load_rows()
    ds = sorted({(r.get("Datum") or "").strip() for r in rows if (r.get("Datum") or "").strip()})
    return {"dates": ds}


@app.get("/result")
def result() -> dict[str, Any]:
    return load_result()


@app.get("/plan/{date}")
def plan(date: str) -> dict[str, Any]:
    rows = [r for r in load_rows() if (r.get("Datum") or "").strip() == date]
    if not rows:
        raise HTTPException(status_code=404, detail="date not found")
    return {"date": date, "items": rows}


@app.get("/najaar/schema")
def get_najaar_schema() -> dict[str, Any]:
    """Haal het huidige (server-opgeslagen) najaarsschema op.

    Geeft {"schema": {}, "updated_by": None, "updated_at": None} terug als er
    nog niets is opgeslagen, zodat de editor kan terugvallen op
    gold_result_najaar2026.json.
    """
    try:
        blob = _najaar_blob()
        if not blob.exists():
            return {"schema": {}, "updated_by": None, "updated_at": None}
        data = json.loads(blob.download_as_text())
        return data
    except Exception as exc:  # pragma: no cover - infra-afhankelijk
        raise HTTPException(status_code=503, detail=f"opslag niet beschikbaar: {exc}")


@app.post("/najaar/schema")
def save_najaar_schema(payload: NajaarSchemaPayload) -> dict[str, Any]:
    """Sla het najaarsschema server-side op (overschrijft de vorige versie)."""
    from datetime import datetime, timezone

    body = {
        "schema": payload.schema,
        "updated_by": payload.updated_by,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        blob = _najaar_blob()
        blob.upload_from_string(json.dumps(body, ensure_ascii=False, indent=2), content_type="application/json")
    except Exception as exc:  # pragma: no cover - infra-afhankelijk
        raise HTTPException(status_code=503, detail=f"opslag niet beschikbaar: {exc}")
    return {"ok": True, "updated_at": body["updated_at"]}


@app.post("/replan")
def replan(req: ReplanRequest) -> dict[str, Any]:
    rows = [r for r in load_rows() if (r.get("Datum") or "").strip() == req.date]
    if not rows:
        raise HTTPException(status_code=404, detail="date not found")
    # v1 backend stub: returns date slice + request context
    return {
        "date": req.date,
        "now": req.now,
        "completed_count": len(req.completed),
        "items": rows,
    }
