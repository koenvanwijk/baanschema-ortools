"""Antwoord op een regelvraag: zoeken in de regelbank + Gemini (Vertex AI).

Het model krijgt alleen de gevonden fragmenten; elke bewering moet naar een
fragment [n] verwijzen. Geen API-sleutel: de Cloud Run-serviceaccount
authenticeert via Application Default Credentials.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from .bronnen import RANG_NAAM
from .zoek import Index

MODEL = os.environ.get("BS_REGEL_MODEL", "gemini-2.5-flash")
PROJECT = os.environ.get("BS_GCP_PROJECT", "baanschema")
LOCATION = os.environ.get("BS_REGEL_LOCATION", "europe-west1")
TOP_K = int(os.environ.get("BS_REGEL_TOPK", "10"))
MAX_CHUNK_CHARS = 1600
MAX_OUTPUT_TOKENS = int(os.environ.get("BS_REGEL_MAX_TOKENS", "900"))
THINKING_BUDGET = int(os.environ.get("BS_REGEL_THINKING", "512"))
# Prijzen (USD per 1M tokens) voor de kostenschatting in de respons.
PRIJS_IN = float(os.environ.get("BS_REGEL_PRIJS_IN", "0.30"))
PRIJS_UIT = float(os.environ.get("BS_REGEL_PRIJS_UIT", "2.50"))

SYSTEEM = """Je bent de KNLTB-regelhulp van Baanschemaatje, voor competitieleiders en leden van tennisclubs.
Regels:
- Antwoord in het Nederlands, kort en zakelijk. Begin met een antwoord van 1-2 zinnen (vetgedrukt), daarna een korte onderbouwing in opsommingstekens.
- Gebruik UITSLUITEND de genummerde fragmenten hieronder. Verzin niets en gebruik geen eigen kennis van het reglement.
- Noem bij elke bewering het label uit het fragment én het nummer, bv. "volgens CR art. 49 lid 1 [1]". Eén nummer per haakje: [1] [3], niet [1, 3].
- Verwijs alleen naar fragmenten die de bewering echt dragen. Noem geen fragmenten die niet relevant zijn.
- Lees de vraag precies (wie speelt in welk team, welke richting) en trek geen conclusies die niet letterlijk volgen.
- Rangorde bij tegenspraak: Competitiereglement (CR) > Wedstrijdbulletin > Veelgestelde vragen > uitleg-pdf's. Zeg het als bronnen elkaar tegenspreken.
- Staat het antwoord niet (volledig) in de fragmenten, zeg dat dan duidelijk ("Dit staat niet in de KNLTB-regels die ik heb.") en verwijs naar de competitieleider of KNLTB. Gok niet en som dan geen fragmenten op.
- Clubafspraken (uit het clubprofiel) zijn GEEN KNLTB-regels: noem ze apart onder "Clubafspraak" en alleen als ze relevant zijn.
- Sluit af met een regel "Zelf nagaan:" als er iets onzeker is (bv. welke competitie, datum in MijnKNLTB).
- Dit is advies; bij twijfel beslist de competitieleider of de KNLTB.
- Maximaal ongeveer 250 woorden. Markdown is toegestaan (vet, lijsten), geen tabellen, geen koppen."""


def bouw_prompt(vraag: str, hits: list[dict[str, Any]], club: dict[str, Any] | None) -> str:
    parts = []
    for n, c in enumerate(hits, 1):
        txt = c["text"]
        if len(txt) > MAX_CHUNK_CHARS:
            txt = txt[:MAX_CHUNK_CHARS] + " […]"
        parts.append(f"[{n}] {c['label']} — {RANG_NAAM.get(c.get('rang', 4), '')}, {c['bron_titel']} ({c.get('versie') or 'versie onbekend'})\n{txt}")
    clubtxt = ""
    if club:
        clubtxt = "\n\nClubprofiel (clubafspraken, geen KNLTB-regels):\n" + json.dumps(club, ensure_ascii=False)[:1500]
    return f"Fragmenten:\n\n" + "\n\n".join(parts) + clubtxt + f"\n\nVraag: {vraag}"


def vertex_generate(prompt: str, systeem: str) -> dict[str, Any]:
    """Roep Gemini aan op Vertex AI (ADC). Geeft {text, tokens_in, tokens_uit}."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    host = "aiplatform.googleapis.com" if LOCATION == "global" else f"{LOCATION}-aiplatform.googleapis.com"
    url = f"https://{host}/v1/projects/{PROJECT}/locations/{LOCATION}/publishers/google/models/{MODEL}:generateContent"
    gen: dict[str, Any] = {"temperature": 0.1, "maxOutputTokens": MAX_OUTPUT_TOKENS + max(0, THINKING_BUDGET)}
    if THINKING_BUDGET >= 0:
        gen["thinkingConfig"] = {"thinkingBudget": THINKING_BUDGET}
    body = {
        "systemInstruction": {"parts": [{"text": systeem}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen,
    }
    r = AuthorizedSession(creds).post(url, json=body, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Vertex AI {r.status_code}: {r.text[:300]}")
    j = r.json()
    cand = (j.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
    um = j.get("usageMetadata", {})
    return {"text": text.strip(), "tokens_in": um.get("promptTokenCount", 0),
            "tokens_uit": um.get("candidatesTokenCount", 0) + um.get("thoughtsTokenCount", 0),
            "finish": cand.get("finishReason")}


def _quote(text: str, n: int = 280) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


def beantwoord(vraag: str, index: Index, club: dict[str, Any] | None = None,
               llm: Callable[[str, str], dict[str, Any]] = vertex_generate, k: int = TOP_K) -> dict[str, Any]:
    hits = [c for _, c in index.zoek(vraag, k=k)]
    if not hits:
        return {"antwoord": "**Dit staat niet in de KNLTB-regels die ik heb.** Vraag het na bij je competitieleider of de KNLTB.",
                "bronnen": [], "model": None, "kosten_usd": 0.0}
    res = llm(bouw_prompt(vraag, hits, club), SYSTEEM)
    text = res["text"] or "Er kwam geen antwoord. Probeer het opnieuw."
    nums = [n for grp in re.findall(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]", text) for n in re.split(r"\s*,\s*", grp)]
    cited = sorted({int(n) for n in nums if 1 <= int(n) <= len(hits)})
    # "[4, 5]" -> "[4] [5]" zodat de web-GUI elk nummer kan linken
    text = re.sub(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})+)\]", lambda m: " ".join(f"[{x}]" for x in re.split(r"\s*,\s*", m.group(1))), text)
    bronnen = []
    for n in cited:
        c = hits[n - 1]
        bronnen.append({"n": n, "label": c["label"], "url": c["url"], "quote": _quote(c["text"]),
                        "bron": c["bron_titel"], "versie": c.get("versie")})
    kosten = (res.get("tokens_in", 0) * PRIJS_IN + res.get("tokens_uit", 0) * PRIJS_UIT) / 1e6
    return {"antwoord": text, "bronnen": bronnen,
            "gezocht": [{"n": i + 1, "label": c["label"], "url": c["url"]} for i, c in enumerate(hits)],
            "model": MODEL, "tokens": {"in": res.get("tokens_in"), "uit": res.get("tokens_uit")},
            "kosten_usd": round(kosten, 5)}
