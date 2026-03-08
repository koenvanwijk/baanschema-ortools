from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Baanschema Backend", version="0.2.0")
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
