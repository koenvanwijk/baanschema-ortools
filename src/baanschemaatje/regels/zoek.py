"""Lexicaal zoeken (BM25) in de regelbank, met Nederlandse normalisatie en synoniemen."""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Any

STOP = set("""de het een en of van in op te is dat die dit er zijn wordt worden aan voor met als bij om
door naar ook niet wel nog maar dan kan kunnen moet moeten mag mogen we wij ze zij ik je jij u hun
ons onze mijn zijn haar wat wie waar hoe wanneer welke welk deze geen al als tot uit over na
heeft hebben had is was waren wordt zal zullen zou zouden dus nu zo omdat want daar hier""".split())

# Groepen begrippen die als hetzelfde woord tellen (na normalisatie/stemming).
SYNONIEMEN = [
    {"inval", "invaller", "invallers", "invallen", "valt", "vervanger", "vervangen", "reserve"},
    {"afgebroken", "afbreken", "gestaakt", "staken", "onderbroken", "stilgelegd", "uitspelen", "uitgespeeld", "afspelen"},
    {"inhaaldag", "inhaaldagen", "inhalen", "ingehaald", "inhaalwedstrijd"},
    {"verzetten", "verzet", "verplaatsen", "verplaatst", "uitstel", "uitstellen", "uitgesteld", "verschuiven"},
    {"walkover", "walk-over", "wo", "claimen", "reglementair", "afwezig", "afwezigheid", "opdagen", "verhinderd", "niet kunnen", "niet beschikbaar", "niet spelen"},
    {"onvoltallig", "incompleet", "niet compleet", "te weinig"},
    {"regen", "weer", "weersomstandigheden", "verregend", "regenen"},
    {"kampioen", "kampioenschap", "kampioenswedstrijd", "beslissingswedstrijd", "promotie"},
    {"competitieleider", "cl"},
    {"aanvoerder", "captain"},
    {"opstelling", "teamopstelling", "opstellen"},
    {"speelgerechtigd", "speelgerechtigdheid", "spelen", "mag spelen"},
    {"boete", "boetes", "straf", "straffen", "sanctie"},
    {"begintijd", "begintijden", "aanvang", "starttijd"},
    {"te laat", "laat", "opkomen", "wachttijd"},
    {"vaak", "maal", "keer", "hoeveel"},
    {"sterker", "hoger", "zwakker", "lager", "eerste team", "tweede team", "ander team"},
]


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _stem(w: str) -> str:
    """Zeer lichte Nederlandse stemmer (meervoud/verkleinwoord)."""
    for suf in ("heden", "ingen", "tjes", "jes", "tje", "je", "en", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            w = w[: -len(suf)]
            break
    if len(w) > 4 and w[-1] == w[-2] and w[-1] not in "aeiou":  # ballen -> ball -> bal
        w = w[:-1]
    return w


_SYN: dict[str, str] = {}
for g in SYNONIEMEN:
    canon = "§" + sorted(g)[0]
    for w in g:
        if " " not in w:
            _SYN[_stem(_fold(w))] = canon
_PHRASES = [(_fold(w), "§" + sorted(g)[0]) for g in SYNONIEMEN for w in g if " " in w]


def tokens(text: str) -> list[str]:
    t = _fold(text)
    t = t.replace("walk-over", "walkover")
    extra = [c for p, c in _PHRASES if p in t]
    out = []
    for w in re.findall(r"[a-z0-9]+", t):
        if w in STOP or len(w) < 2:
            continue
        s = _stem(w)
        out.append(s)
        if s in _SYN:
            out.append(_SYN[s])
    return out + extra


class Index:
    def __init__(self, chunks: list[dict[str, Any]], k1: float = 1.4, b: float = 0.7):
        self.chunks = chunks
        self.k1, self.b = k1, b
        # titel/sectie telt dubbel: artikeltitels zijn sterke signalen
        self.docs = [Counter(tokens(" ".join([c.get("label", ""), c.get("sectie", ""), c.get("sectie", ""), c["text"]])))
                     for c in chunks]
        self.len = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.len) / max(1, len(self.len))
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, q: list[str], i: int) -> float:
        d, L = self.docs[i], self.len[i]
        s = 0.0
        for t, qf in Counter(q).items():
            f = d.get(t)
            if not f:
                continue
            w = 1.0  # synoniem-token iets lichter
            s += w * self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * L / self.avg))
        return s

    def zoek(self, vraag: str, k: int = 8, rang_bonus: float = 0.08) -> list[tuple[float, dict[str, Any]]]:
        q = tokens(vraag)
        # expliciet artikelnummer in de vraag ("art 49", "artikel 35")
        arts = {int(m) for m in re.findall(r"\bart(?:ikel)?\.?\s*(\d{1,2})\b", _fold(vraag))}
        res = []
        for i, c in enumerate(self.chunks):
            s = self.score(q, i)
            if s <= 0 and not arts:
                continue
            s *= 1 + rang_bonus * (4 - c.get("rang", 4))  # hiërarchie: CR > bulletin > FAQ > uitleg
            if arts and c["id"].split("-")[0] == "cr" and c["id"].split("-")[1].isdigit() and int(c["id"].split("-")[1]) in arts:
                s += 5
            if s > 0:
                res.append((s, c))
        res.sort(key=lambda x: -x[0])
        # Hiërarchie: reserveer plekken voor de beste CR- (3) en bulletin-treffers (2),
        # vul daarna aan op score; max een paar chunks per bron voor variatie.
        gekozen: list[tuple[float, dict[str, Any]]] = []
        for rang, n in ((1, 3), (2, 2)):
            gekozen += [x for x in res if x[1].get("rang") == rang][:n]
        per = Counter(c["bron"] for _, c in gekozen)
        ids = {c["id"] for _, c in gekozen}
        for s, c in res:
            if len(gekozen) >= k:
                break
            if c["id"] in ids or per[c["bron"]] >= max(3, k // 2):
                continue
            per[c["bron"]] += 1
            ids.add(c["id"])
            gekozen.append((s, c))
        gekozen = gekozen[:k]
        gekozen.sort(key=lambda x: -x[0])
        return gekozen
