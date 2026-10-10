"""Bouw de regelbank (JSON) uit lokaal gedownloade KNLTB-bronnen.

    python -m baanschemaatje.regels.bouw --bronnen /workspace/knltb-bronnen --out regelbank.json

Verwacht ``<bronnen>/pdf/<stem>.pdf`` + ``<stem>.txt`` (``pdftotext -layout``),
``<bronnen>/veelgestelde-vragen.html`` en html-pagina's met de PDF-links
(voor de URL + ``?ts=``-versie).
"""
from __future__ import annotations

import argparse
import hashlib
import html as htmllib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bronnen import BASE, FAQ_URL, PDF_BRONNEN, ticks_naar_datum

MAX_CHUNK = 1800


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _clean(lines: list[str]) -> str:
    out = []
    for ln in lines:
        ln = re.sub(r"[ \t]+", " ", ln.replace("\f", "")).strip()
        if re.fullmatch(r"\d{1,3}", ln):  # paginanummer
            continue
        out.append(ln)
    txt = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def _pages(txt: str) -> list[int]:
    """Paginanummer (1-based) per regel."""
    res, p = [], 1
    for ln in txt.split("\n"):
        res.append(p)
        p += ln.count("\f")
    return res


def pdf_links(bronnen: Path) -> dict[str, dict[str, str | None]]:
    """stem -> {url, ts} uit html-pagina's en pdfurls.txt."""
    seen: dict[str, dict[str, str | None]] = {}
    texts = [p.read_text(errors="ignore") for p in bronnen.glob("*.html")]
    if (bronnen / "pdfurls.txt").is_file():
        texts.append((bronnen / "pdfurls.txt").read_text())
    for t in texts:
        for m in re.finditer(r"(/media/[a-z0-9]+/([a-z0-9-]+)\.pdf)(?:\?ts=(\d+))?", t):
            path, stem, ts = m.groups()
            cur = seen.get(stem)
            if cur is None or (ts and not cur.get("ts")):
                seen[stem] = {"url": BASE + path, "ts": ts}
    return seen


def _split_long(text: str, limit: int = MAX_CHUNK) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if cur and len(cur) + len(para) > limit:
            parts.append(cur.strip())
            cur = ""
        cur += para + "\n\n"
    if cur.strip():
        parts.append(cur.strip())
    # nog te lang (geen lege regels): hard knippen op regels
    final = []
    for p in parts:
        while len(p) > limit * 1.5:
            cut = p.rfind("\n", 0, limit)
            cut = cut if cut > limit // 2 else limit
            final.append(p[:cut].strip())
            p = p[cut:].strip()
        final.append(p)
    return [p for p in final if p]


def chunk_cr(txt: str, url: str, meta: dict[str, Any]) -> list[dict[str, Any]]:
    lines = txt.split("\n")
    pages = _pages(txt)
    art_re = re.compile(r"^(?:[A-Z+]{1,5})?\s*(\d{2})\s+([A-Z][^\n]{2,90}?)\s*$")
    lid_re = re.compile(r"^\s{2,14}(\d{1,2})\.\s+\S")
    bij_re = re.compile(r"^BIJLAGE\s+(\d)\s+(.+?)\s*$")
    # Inhoudsopgave overslaan: begin bij eerste '01 Competitiereglement' ná regel 100.
    start = next(i for i, ln in enumerate(lines) if i > 100 and art_re.match(ln) and art_re.match(ln).group(1) == "01")
    chunks: list[dict[str, Any]] = []
    expect = 1
    art = None  # (nr, titel, startregel)
    body: list[tuple[int, str]] = []

    def flush():
        if not art:
            return
        nr, titel, s = art
        # splits in leden
        leden: list[tuple[str, int, list[str]]] = []
        cur_lid, cur_start, cur_lines = None, s, []
        for i, ln in body:
            m = lid_re.match(ln)
            if m and (cur_lid is None and m.group(1) == "1" or cur_lid is not None and int(m.group(1)) == int(cur_lid) + 1):
                if cur_lines:
                    leden.append((cur_lid, cur_start, cur_lines))
                cur_lid, cur_start, cur_lines = m.group(1), i, []
            cur_lines.append(ln)
        if cur_lines:
            leden.append((cur_lid, cur_start, cur_lines))
        for lid, ls, ll in leden:
            text = _clean(ll)
            if not text:
                continue
            label = f"CR art. {int(nr)}" + (f" lid {lid}" if lid else "")
            for k, part in enumerate(_split_long(text)):
                cid = f"cr-{int(nr)}" + (f"-{lid}" if lid else "") + (f"-{k + 1}" if k else "")
                chunks.append(_mk(cid, label, f"Artikel {int(nr)} {titel}", f"{int(nr):02d} {titel}\n{part}", url, pages[ls], meta))

    i = start
    while i < len(lines):
        ln = lines[i]
        if bij_re.match(ln.strip()) and i > start:
            break
        m = art_re.match(ln)
        if m and int(m.group(1)) == expect:
            flush()
            art = (m.group(1), re.sub(r"\s+", " ", m.group(2)).strip(), i)
            body = []
            expect += 1
        else:
            body.append((i, ln))
        i += 1
    flush()
    # Bijlagen
    bij_idx = [(j, bij_re.match(lines[j].strip())) for j in range(i, len(lines)) if bij_re.match(lines[j].strip())]
    for n, (j, m) in enumerate(bij_idx):
        end = bij_idx[n + 1][0] if n + 1 < len(bij_idx) else len(lines)
        text = _clean(lines[j + 1:end])
        for k, part in enumerate(_split_long(text)):
            # pagina van het deel: zoek eerste regel
            first = part.split("\n", 1)[0]
            pg = next((pages[x] for x in range(j, end) if first and first in re.sub(r"[ \t]+", " ", lines[x]).strip()), pages[j])
            chunks.append(_mk(f"cr-bijlage{m.group(1)}-{k + 1}", f"CR bijlage {m.group(1)}", f"Bijlage {m.group(1)} {m.group(2)}",
                              part, url, pg, meta))
    return chunks


def chunk_bulletin(txt: str, url: str, meta: dict[str, Any], label_prefix: str) -> list[dict[str, Any]]:
    lines = txt.split("\n")
    pages = _pages(txt)
    heads = []
    for ln in lines[:80]:
        m = re.match(r"^\s*(\S.*?\S)\s*\.{5,}\s*\d+\s*$", ln)
        if m:
            heads.append(m.group(1).strip())
    toc_end = max(i for i, ln in enumerate(lines[:80]) if re.search(r"\.{5,}", ln))
    idx = []
    for i in range(toc_end + 1, len(lines)):
        s = lines[i].replace("\f", "").strip()
        if s in heads:
            idx.append((i, s))
    chunks = []
    for n, (i, h) in enumerate(idx):
        end = idx[n + 1][0] if n + 1 < len(idx) else len(lines)
        text = _clean(lines[i + 1:end])
        for k, part in enumerate(_split_long(text)):
            cid = "wb-" + re.sub(r"[^a-z0-9]+", "-", h.lower()).strip("-") + (f"-{k + 1}" if k else "")
            chunks.append(_mk(cid, f"{label_prefix}, '{h}'" + (f" (deel {k + 1})" if k else ""), h, f"{h}\n{part}", url, pages[i], meta))
    return chunks


def chunk_pages(txt: str, url: str, meta: dict[str, Any], stem: str, label_prefix: str) -> list[dict[str, Any]]:
    chunks = []
    for p, page in enumerate(txt.split("\f"), start=1):
        text = _clean(page.split("\n"))
        if len(text) < 40:
            continue
        for k, part in enumerate(_split_long(text)):
            chunks.append(_mk(f"{stem}-p{p}" + (f"-{k + 1}" if k else ""), f"{label_prefix}, p. {p}", f"pagina {p}", part, url, p, meta))
    return chunks


def _is_heading(raw: str, prev_blank: bool) -> bool:
    s = raw.replace("\f", "").rstrip()
    t = s.strip()
    if not prev_blank or not t or s[:1] in (" ", "\t") or len(t) > 60:
        return False
    if re.match(r"^(\d{1,2}\.|[•o*-])\s", t) or t[-1] in ".,;:" or not t[0].isupper():
        return False
    return True


def chunk_uitleg(txt: str, url: str, meta: dict[str, Any], stem: str, naam: str) -> list[dict[str, Any]]:
    """Uitleg-pdf per kop en per genummerd/opsommingspunt; kopcontext ervoor."""
    lines = txt.split("\n")
    pages = _pages(txt)
    secties: list[dict[str, Any]] = []  # {kop, page, intro:[...], items:[(nr, page, [...])]}
    cur = {"kop": "", "page": 1, "intro": [], "items": []}
    prev_blank = True
    item = None
    for i, raw in enumerate(lines):
        t = re.sub(r"\s+", " ", raw.replace("\f", "")).strip()
        if not t:
            prev_blank, item = True, None
            continue
        if re.fullmatch(r"\d{1,3}", t):
            continue
        if i > 0 and _is_heading(raw, prev_blank):
            secties.append(cur)
            cur = {"kop": t, "page": pages[i], "intro": [], "items": []}
            item, prev_blank = None, False
            continue
        m = re.match(r"^(\d{1,2})\.\s+(.*)$", t) or re.match(r"^[•]\s+(.*)$", t)
        if m:
            nr = m.group(1) if m.lastindex == 2 else str(len(cur["items"]) + 1)
            item = [nr, pages[i], [m.group(m.lastindex)]]
            cur["items"].append(item)
        elif item is not None and raw[:1] in (" ", "\t"):
            item[2].append(t)
        else:
            item = None
            cur["intro"].append(t)
        prev_blank = False
    secties.append(cur)
    titel = secties[0]["intro"][0] if secties and secties[0]["intro"] else meta["titel"]
    chunks: list[dict[str, Any]] = []
    for n, sec in enumerate(secties):
        kop = sec["kop"]
        ctx = f"{meta['titel']}" + (f" — {kop}" if kop else "")
        base = f"KNLTB-uitleg {naam}"
        soort = "voorwaarde" if "voorwaarde" in kop.lower() else "punt"
        if sec["intro"]:
            text = "\n".join(sec["intro"])
            for k, part in enumerate(_split_long(text)):
                lab = base + (f", '{kop}'" if kop else ", inleiding") + (f" (deel {k + 1})" if k else "")
                chunks.append(_mk(f"{stem}-s{n}" + (f"-{k + 1}" if k else ""), lab, ctx, f"{ctx}\n{part}", url, sec["page"], meta,
                                  groep=f"{stem}-s{n}"))
        for nr, pg, ll in sec["items"]:
            lab = base + (f", '{kop}'" if kop and soort == "punt" else "") + f", {soort} {nr}"
            chunks.append(_mk(f"{stem}-s{n}-{soort[0]}{nr}", lab, ctx, f"{ctx}\n{nr}. " + " ".join(ll), url, pg, meta,
                              groep=f"{stem}-s{n}"))
    return chunks


def chunk_faq(html: str, meta: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = []
    cat = ""
    pos = 0
    tok = re.compile(r"<h2[^>]*toggle__trigger[^>]*>(.*?)</h2>|<button[^>]*c-list-stack__button--toggle[^>]*>(.*?)</button>\s*<div[^>]*c-list-stack__summary[^>]*>(.*?)</div>\s*</li>", re.S)
    n = 0
    for m in tok.finditer(html, pos):
        if m.group(1) is not None:
            cat = _strip_html(m.group(1))
            continue
        q, a = _strip_html(m.group(2)), _strip_html(m.group(3))
        if not q or not a:
            continue
        n += 1
        short = q if len(q) <= 70 else q[:67].rsplit(" ", 1)[0] + "…"
        chunks.append(_mk(f"faq-{n}", f"FAQ: '{short}'", f"{cat}: {q}", f"Vraag ({cat}): {q}\nAntwoord: {a}", FAQ_URL, None, meta))
    return chunks


def _strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = htmllib.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    return re.sub(r"\s*\n\s*", "\n", s).strip()


def _mk(cid, label, titel_sectie, text, url, page, meta, groep=None) -> dict[str, Any]:
    d = {
        "id": cid,
        "label": label,
        "sectie": titel_sectie,
        "text": text,
        "bron": meta["bron"],
        "bron_titel": meta["titel"],
        "rang": meta["rang"],
        "url": f"{url}#page={page}" if page else url,
        "versie": meta.get("versie"),
        "sha256": _sha(text),
    }
    if groep:
        d["groep"] = groep
    return d


def bouw(bronnen: Path) -> dict[str, Any]:
    links = pdf_links(bronnen)
    pdfdir = bronnen / "pdf"
    chunks: list[dict[str, Any]] = []
    docs: list[dict[str, Any]] = []
    for stem, (titel, prefix, rang, soort) in PDF_BRONNEN.items():
        txtp = pdfdir / f"{stem}.txt"
        if not txtp.is_file():
            print(f"ontbreekt: {txtp}", file=sys.stderr)
            continue
        txt = txtp.read_text(errors="ignore")
        link = links.get(stem, {})
        url = link.get("url") or f"{BASE}/media/onbekend/{stem}.pdf"
        versie = ticks_naar_datum(link.get("ts"))
        if soort == "cr":
            m = re.search(r"vastgesteld door het Bestuur d\.d\. (\d{2}-\d{2}-\d{4})", txt)
            if m:
                versie = f"vastgesteld {m.group(1)}"
        pdfp = pdfdir / f"{stem}.pdf"
        meta = {"bron": stem, "titel": titel, "rang": rang, "versie": versie}
        if soort == "cr":
            cs = chunk_cr(txt, url, meta)
        elif soort == "uitleg":
            cs = chunk_uitleg(txt, url, meta, stem, prefix)
        elif soort == "bulletin":
            cs = chunk_bulletin(txt, url, meta, prefix)
        else:
            cs = chunk_pages(txt, url, meta, stem, prefix)
        chunks += cs
        docs.append({"bron": stem, "titel": titel, "rang": rang, "url": url, "ts": link.get("ts"), "versie": versie,
                     "sha256": hashlib.sha256(pdfp.read_bytes()).hexdigest() if pdfp.is_file() else None,
                     "chunks": len(cs)})
    faqp = bronnen / "veelgestelde-vragen.html"
    if faqp.is_file():
        h = faqp.read_text(errors="ignore")
        lm = _sitemap_lastmod(bronnen, FAQ_URL)
        meta = {"bron": "faq", "titel": "KNLTB Veelgestelde vragen competitie", "rang": 3, "versie": lm}
        cs = chunk_faq(h, meta)
        chunks += cs
        docs.append({"bron": "faq", "titel": meta["titel"], "rang": 3, "url": FAQ_URL, "versie": lm, "lastmod": lm,
                     "sha256": _sha(" ".join(c["text"] for c in cs)), "chunks": len(cs)})
    seen_l: dict[str, int] = {}
    for c in chunks:
        n = seen_l.get(c["label"], 0) + 1
        seen_l[c["label"]] = n
        if n > 1:
            c["label"] += f" ({n})"
    ids = [c["id"] for c in chunks]
    dup = {i for i in ids if ids.count(i) > 1}
    for c in chunks:  # ids uniek maken
        if c["id"] in dup:
            c["id"] = c["id"] + "-" + c["sha256"][:6]
    return {"gebouwd": datetime.now(timezone.utc).isoformat(timespec="seconds"), "documenten": docs, "chunks": chunks}


def _sitemap_lastmod(bronnen: Path, url: str) -> str | None:
    sm = bronnen / "sitemap.xml"
    if not sm.is_file():
        return None
    m = re.search(re.escape(f"<loc>{url}</loc>") + r"\s*<lastmod>([^<]+)</lastmod>", sm.read_text(errors="ignore"))
    return m.group(1)[:10] if m else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bronnen", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    rb = bouw(a.bronnen)
    a.out.write_text(json.dumps(rb, ensure_ascii=False, indent=0))
    print(f"{len(rb['chunks'])} chunks uit {len(rb['documenten'])} documenten -> {a.out}")
    for d in rb["documenten"]:
        print(f"  {d['chunks']:4d}  {d['bron']}  ({d['versie']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
