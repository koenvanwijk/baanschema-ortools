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
TOP_K = int(os.environ.get("BS_REGEL_TOPK", "14"))
MAX_CHUNK_CHARS = 1600
MAX_OUTPUT_TOKENS = int(os.environ.get("BS_REGEL_MAX_TOKENS", "900"))
THINKING_BUDGET = int(os.environ.get("BS_REGEL_THINKING", "512"))
# Prijzen (USD per 1M tokens) voor de kostenschatting in de respons.
PRIJS_IN = float(os.environ.get("BS_REGEL_PRIJS_IN", "0.30"))
PRIJS_UIT = float(os.environ.get("BS_REGEL_PRIJS_UIT", "2.50"))

SYSTEEM = """Je bent de KNLTB-regelhulp van Baanschemaatje, voor competitieleiders en leden van tennisclubs.
Regels:
- Antwoord in het Nederlands, kort en zakelijk. De eerste zin is een direct antwoord (vetgedrukt), bij een ja/nee-vraag beginnend met "Ja" of "Nee". Daarna een korte onderbouwing in opsommingstekens.
- Bevestigingsvraag ("..., toch?", "klopt het dat ...", "dus ..., right?"): begin met "Klopt," of "Klopt niet," en herhaal de conclusie in gewone woorden (bv. "Klopt, zij mag niet in een derde team invallen."). Gebruik dan geen los "Ja" of "Nee".
- Noem kort de voorwaarden of uitzonderingen uit dezelfde sectie die de uitkomst kunnen veranderen (bv. voor welke competitie of welke dagen iets geldt), met het advies dat bij de competitieleider na te gaan.
- Gebruik UITSLUITEND de fragmenten hieronder. Verzin niets en gebruik geen eigen kennis van het reglement.
- Alle fragmenten zijn officiële KNLTB-bronnen. Een specifieke KNLTB-uitleg (bv. "KNLTB-uitleg Twee of meer teams") of FAQ die de vraag direct beantwoordt, MOET je gebruiken, ook als het Competitiereglement er niets over zegt.
- De rangorde Competitiereglement (CR) > Wedstrijdbulletin > Veelgestelde vragen > KNLTB-uitleg geldt alleen als bronnen elkaar tegenspreken; meld dat dan.
- Verwijs naar bronnen met hun label, letterlijk zoals tussen «» bij het fragment staat, bv. (CR art. 49 lid 1) of (KNLTB-uitleg Twee of meer teams, voorwaarde 4). Gebruik geen [n]-nummers. Noem bij de belangrijkste bron de versie/releasedatum, bv. "(release 17-09-2026)".
- Verwijs alleen naar fragmenten die de bewering echt dragen.
- Lees de vraag precies (wie, welk team, welke richting) en trek geen conclusies die niet uit de tekst volgen.
- Zeg alleen "Dit staat niet in de KNLTB-regels die ik heb." als GEEN enkel fragment de vraag beantwoordt; som dan geen fragmenten op en verwijs naar de competitieleider of KNLTB.
- Clubafspraken (uit het clubprofiel) zijn GEEN KNLTB-regels: noem ze apart onder "Clubafspraak" en alleen als ze relevant zijn.
- Sluit zo nodig af met "Zelf nagaan:" voor wat onzeker is (bv. welke competitie, gegevens in MijnKNLTB).
- Maximaal ongeveer 250 woorden. Markdown is toegestaan (vet, lijsten), geen tabellen, geen koppen."""


def bouw_prompt(vraag: str, hits: list[dict[str, Any]], club: dict[str, Any] | None) -> str:
    parts = []
    for n, c in enumerate(hits, 1):
        txt = c["text"]
        if len(txt) > MAX_CHUNK_CHARS:
            txt = txt[:MAX_CHUNK_CHARS] + " […]"
        parts.append(f"Fragment {n}: «{c['label']}» — {RANG_NAAM.get(c.get('rang', 4), '')}, {c['bron_titel']}, "
                     f"versie/release {_datum(c.get('versie'))}\n{txt}")
    clubtxt = ""
    if club:
        clubtxt = "\n\nClubprofiel (clubafspraken, geen KNLTB-regels):\n" + json.dumps(club, ensure_ascii=False)[:1500]
    return f"Fragmenten:\n\n" + "\n\n".join(parts) + clubtxt + f"\n\nVraag: {vraag}"


def _datum(v: str | None) -> str:
    if not v:
        return "onbekend"
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", v)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else v


def _norm(s: str) -> str:
    return re.sub(r"[\s'‘’\"“”«»]+", " ", s.lower()).strip()


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
    hits = index.met_context([c for _, c in index.zoek(vraag, k=k)])
    if not hits:
        return {"antwoord": "**Dit staat niet in de KNLTB-regels die ik heb.** Vraag het na bij je competitieleider of de KNLTB.",
                "bronnen": [], "model": None, "kosten_usd": 0.0}
    res = llm(bouw_prompt(vraag, hits, club), SYSTEEM)
    text = res["text"] or "Er kwam geen antwoord. Probeer het opnieuw."
    # Bronnen = labels die letterlijk in het antwoord staan (langste eerst, zodat
    # "lid 1" niet ook "lid 10" matcht), plus eventuele [n]-verwijzingen.
    nt = _norm(text)
    found: dict[int, int] = {}
    for n, c in sorted(enumerate(hits, 1), key=lambda x: -len(x[1]["label"])):
        lab = _norm(c["label"])
        for m in re.finditer(re.escape(lab) + r"(?![0-9])", nt):
            if not any(m.start() >= s0 and m.end() <= e0 for s0, e0 in found.values()):
                found.setdefault(n, (m.start(), m.end()))
                break
    found_pos = {n: se[0] for n, se in found.items()}
    for grp in re.findall(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]", text):
        for x in re.split(r"\s*,\s*", grp):
            if 1 <= int(x) <= len(hits):
                found_pos.setdefault(int(x), 10**9)
    text = re.sub(r"\s*\[\d{1,2}(?:\s*,\s*\d{1,2})*\]", "", text)
    bronnen = []
    for n in sorted(found_pos, key=lambda n: found_pos[n]):
        c = hits[n - 1]
        bronnen.append({"n": len(bronnen) + 1, "label": c["label"], "url": c["url"], "quote": _quote(c["text"]),
                        "bron": c["bron_titel"], "versie": c.get("versie")})
    kosten = (res.get("tokens_in", 0) * PRIJS_IN + res.get("tokens_uit", 0) * PRIJS_UIT) / 1e6
    return {"antwoord": text, "bronnen": bronnen,
            "gezocht": [{"label": c["label"], "url": c["url"]} for c in hits],
            "model": MODEL, "tokens": {"in": res.get("tokens_in"), "uit": res.get("tokens_uit")},
            "kosten_usd": round(kosten, 5)}
