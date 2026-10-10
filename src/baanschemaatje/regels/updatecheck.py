"""Controleer of KNLTB-bronnen van de regelbank zijn gewijzigd.

    python -m baanschemaatje.regels.updatecheck --regelbank regelbank.json [--sha]

Kijkt naar (1) ``lastmod`` in https://www.tennis.nl/sitemap.xml voor de
pagina's met reglementen/downloads/FAQ, (2) het ``?ts=``-versienummer in de
PDF-links op die pagina's, en (3) met ``--sha`` de sha256 van de PDF zelf.
Exitcode 0 = niets gewijzigd, 1 = wijzigingen (dan regelbank opnieuw bouwen).

Voorstel planning (nog niet ingericht): Cloud Scheduler -> Cloud Run Job,
wekelijks (ma 07:00); in nov-mrt (nieuw reglement/bulletin) dagelijks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

from .bouw import pdf_links
from .bronnen import BASE, FAQ_URL

PAGINAS = [
    BASE + "/alles-over-tennis/competitie/downloads/",
    BASE + "/alles-over-tennis/competitie/reglementen/",
    FAQ_URL,
]
UA = {"User-Agent": "Baanschemaatje-regelhulp/1 (updatecheck)"}


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def sitemap_lastmods(xml: str) -> dict[str, str]:
    return dict(re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", xml))


def vergelijk(regelbank: dict[str, Any], links: dict[str, dict[str, Any]], lastmods: dict[str, str],
              shas: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Pure vergelijking (testbaar). Geeft een lijst wijzigingen."""
    out = []
    for d in regelbank.get("documenten", []):
        if d["bron"] == "faq":
            lm = (lastmods.get(FAQ_URL) or "")[:10]
            if lm and lm != (d.get("lastmod") or ""):
                out.append({"bron": "faq", "wat": "lastmod", "oud": d.get("lastmod"), "nieuw": lm})
            continue
        link = links.get(d["bron"])
        if not link:
            out.append({"bron": d["bron"], "wat": "link verdwenen", "oud": d.get("url"), "nieuw": None})
            continue
        if link.get("ts") and d.get("ts") and link["ts"] != d["ts"]:
            out.append({"bron": d["bron"], "wat": "ts", "oud": d["ts"], "nieuw": link["ts"], "url": link["url"]})
        if shas and d["bron"] in shas and d.get("sha256") and shas[d["bron"]] != d["sha256"]:
            out.append({"bron": d["bron"], "wat": "sha256", "oud": d["sha256"][:12], "nieuw": shas[d["bron"]][:12]})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regelbank", required=True, type=Path)
    ap.add_argument("--sha", action="store_true", help="download de PDF's en vergelijk sha256")
    a = ap.parse_args(argv)
    rb = json.loads(a.regelbank.read_text())
    lastmods = sitemap_lastmods(_get(BASE + "/sitemap.xml").decode("utf-8", "ignore"))
    tmp = Path("/tmp/regelcheck")
    tmp.mkdir(exist_ok=True)
    for i, p in enumerate(PAGINAS):
        try:
            (tmp / f"p{i}.html").write_bytes(_get(p))
        except Exception as e:  # noqa: BLE001
            print(f"waarschuwing: {p}: {e}", file=sys.stderr)
    links = pdf_links(tmp)
    shas = None
    if a.sha:
        shas = {}
        for d in rb["documenten"]:
            l = links.get(d["bron"])
            if l:
                u = l["url"] + (f"?ts={l['ts']}" if l.get("ts") else "")
                shas[d["bron"]] = hashlib.sha256(_get(u, 60)).hexdigest()
    ch = vergelijk(rb, links, lastmods, shas)
    for p in PAGINAS:
        print(f"lastmod {lastmods.get(p, '?')[:10]}  {p}")
    print(json.dumps({"wijzigingen": ch}, ensure_ascii=False, indent=1))
    return 1 if ch else 0


if __name__ == "__main__":
    raise SystemExit(main())
