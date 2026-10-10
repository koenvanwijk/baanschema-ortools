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
heeft hebben had is was waren wordt zal zullen zou zouden dus nu zo omdat want daar hier
zoeken zoek zoekt weer overweeg overweeg overwegen vragen vraag betekent betekenen toch label iemand
graag eigenlijk precies even klopt dame heer meneer mevrouw speelster speler spelers""".split())

# Groepen begrippen die als hetzelfde woord tellen (na normalisatie/stemming).
SYNONIEMEN = [
    {"inval", "invaller", "invallers", "invallen", "valt", "vervanger", "vervangen", "reserve", "vallen", "ander team", "derde team",
     "andere team", "in te vallen"},
    {"dispensatie", "2x spelen", "2x", "twee keer spelen", "dubbel spelen", "in twee teams", "twee teams", "2 teams",
     "meerdere teams", "twee of meer teams", "beide teams"},
    {"afgebroken", "afbreken", "gestaakt", "staken", "onderbroken", "stilgelegd", "uitspelen", "uitgespeeld", "afspelen"},
    {"inhaaldag", "inhaaldagen", "inhalen", "ingehaald", "inhaalwedstrijd"},
    {"verzetten", "verzet", "verplaatsen", "verplaatst", "uitstel", "uitstellen", "uitgesteld", "verschuiven"},
    {"walkover", "walk-over", "wo", "claimen", "reglementair", "afwezig", "afwezigheid", "opdagen", "verhinderd", "niet kunnen", "niet beschikbaar", "niet spelen"},
    {"onvoltallig", "incompleet", "niet compleet", "te weinig"},
    {"regen", "weersomstandigheden", "verregend", "regenen", "slecht weer"},
    {"kampioen", "kampioenschap", "kampioenswedstrijd", "beslissingswedstrijd", "promotie"},
    {"competitieleider", "cl"},
    {"aanvoerder", "captain"},
    {"opstelling", "teamopstelling", "opstellen"},
    {"speelgerechtigd", "speelgerechtigdheid", "mag spelen", "mogen spelen"},
    {"boete", "boetes", "straf", "straffen", "sanctie"},
    {"begintijd", "begintijden", "aanvang", "starttijd"},
    {"te laat", "laat", "opkomen", "wachttijd"},
    {"vaak", "maal", "keer", "hoeveel"},
    {"sterker", "hoger", "zwakker", "lager", "eerste team", "tweede team"},
]


# Verwante begrippen: een vraag over het eerste begrip raakt vaak ook het tweede
# (bv. inhalen <-> uitstel/verzetten). Alleen als extra zoekterm, licht gewogen.
VERWANT = [("inhaaldag", "uitstel"), ("afgebroken", "inhaaldag"), ("dispensatie", "invallen"), ("afwezig", "boete")]


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


_NAAM = re.compile(r"(?<![.!?:]\s)(?<!^)\b[A-Z][a-z\u00e0-\u00ff]+(?:\s+(?:van|de|der|den|ter|ten|het)){0,3}\s+[A-Z][a-z\u00e0-\u00ff]+\b")


def strip_namen(vraag: str) -> str:
    """Haal persoonsnamen (twee+ woorden met hoofdletter midden in een zin) weg."""
    return _NAAM.sub("[naam]", vraag)


def tokens(text: str) -> list[str]:
    t = _fold(text)
    t = t.replace("walk-over", "walkover")
    flat = " " + " ".join(re.findall(r"[a-z0-9]+", t)) + " "
    extra = [c for p, c in _PHRASES if f" {p} " in flat]
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
        self.bigr = [_bigrams(c.get("sectie", "") + " " + c["text"]) for c in chunks]
        self.groepen: dict[str, list[int]] = {}
        for i, c in enumerate(chunks):
            if c.get("groep"):
                self.groepen.setdefault(c["groep"], []).append(i)
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

    def _rank(self, vraag: str, verwant: bool = False) -> list[tuple[float, int]]:
        q = tokens(vraag)
        if verwant:
            have = set(q)
            for a, b in VERWANT:
                ca, cb = _SYN.get(_stem(_fold(a))), _SYN.get(_stem(_fold(b)))
                if ca in have and cb and cb not in have:
                    q.append(cb)
        qb = _bigrams(vraag)
        arts = {int(m) for m in re.findall(r"\bart(?:ikel)?\.?\s*(\d{1,2})\b", _fold(vraag))}
        qset = {t for t in set(q) if t in self.idf}
        qidf = sum(self.idf[t] for t in qset) or 1.0
        res = []
        for i, c in enumerate(self.chunks):
            s = self.score(q, i)
            if s <= 0 and not arts:
                continue
            # dekking: welk deel van de (idf-gewogen) vraagbegrippen staat in het fragment
            s *= 0.4 + sum(self.idf[t] for t in qset if t in self.docs[i]) / qidf
            # woordparen uit de vraag die letterlijk in het fragment staan
            s *= 1 + 0.15 * min(6, len(qb & self.bigr[i]))
            parts = c["id"].split("-")
            if arts and parts[0] == "cr" and parts[1].isdigit() and int(parts[1]) in arts:
                s += 5
            if s > 0:
                res.append((s, i))
        res.sort(key=lambda x: -x[0])
        return res

    def zoek(self, vraag: str, k: int = 14, rang_bonus: float = 0.02) -> list[tuple[float, dict[str, Any]]]:
        vraag = strip_namen(vraag)
        # Deelvragen: een vraag met meerdere onderdelen ("..., en kunnen zij ...?")
        # wordt ook per onderdeel gezocht; rangen worden samengevoegd (RRF).
        delen = [d for d in re.split(r"[;?!]|\.\s|,\s*(?:en|maar|of)\s", vraag) if len(tokens(d)) >= 2]
        queries = [vraag] + (delen if len(delen) > 1 else [])
        fused: dict[int, float] = {}
        deel_top: list[int] = []
        for qn, qq in enumerate(queries):
            w = 1.0 if qn == 0 else 0.7
            rk = self._rank(qq, verwant=True)[:60]
            if qn:
                deel_top += [i for _, i in rk[:3]]  # elk onderdeel krijgt zijn beste 3
            for r, (_, i) in enumerate(rk):
                fused[i] = fused.get(i, 0.0) + w / (8 + r)
        res = []
        for i, f in fused.items():
            c = self.chunks[i]
            res.append((f * (1 + rang_bonus * (4 - c.get("rang", 4))), i, c))
        res.sort(key=lambda x: -x[0])
        # Plekken per brontype, zodat specifieke KNLTB-uitleg naast het CR kan staan:
        # CR 2, bulletin 2, FAQ 1, uitleg 2 (mits >= 30% van de topscore); rest op score.
        gekozen: list[tuple[float, int, dict[str, Any]]] = []
        drempel = 0.3 * res[0][0] if res else 0
        for rang, n in ((1, 2), (2, 2), (3, 1), (4, 2)):
            kand = [x for x in res if x[2].get("rang") == rang and x[0] >= drempel]
            if rang == 4:  # uitleg: eerst de beste per document, dan de rest
                eerst, seen = [], set()
                for x in kand:
                    if x[2]["bron"] not in seen:
                        seen.add(x[2]["bron"])
                        eerst.append(x)
                kand = eerst + [x for x in kand if x not in eerst]
            gekozen += kand[:n]
        def sleutel(c: dict[str, Any]) -> str:  # CR: per artikel, anders per document
            return "-".join(c["id"].split("-")[:2]) if c.get("rang") == 1 else c["bron"]

        ids = {i for _, i, _ in gekozen}
        byi = {i: (sc, i, c) for sc, i, c in res}
        for i in deel_top:
            if i not in ids and i in byi:
                gekozen.append(byi[i])
                ids.add(i)
        per = Counter(sleutel(c) for _, _, c in gekozen)
        for s, i, c in res:
            if len(gekozen) >= k:
                break
            if i in ids or per[sleutel(c)] >= (3 if c.get("rang") == 1 else 4):
                continue
            per[sleutel(c)] += 1
            ids.add(i)
            gekozen.append((s, i, c))
        gekozen.sort(key=lambda x: -x[0])
        return [(s, c) for s, _, c in gekozen[:k]]

    def met_context(self, hits: list[dict[str, Any]], max_extra: int = 6) -> list[dict[str, Any]]:
        """Voeg bij een sterk passend uitlegpunt de andere punten van dezelfde kop toe
        (korte lijsten zoals 'voorwaarden'), zodat het model het geheel ziet."""
        out = list(hits)
        have = {c["id"] for c in out}
        extra = 0
        for c in hits[:8]:
            for j in self.groepen.get(c.get("groep") or "", []):
                cj = self.chunks[j]
                if cj["id"] not in have and extra < max_extra:
                    out.append(cj)
                    have.add(cj["id"])
                    extra += 1
        return out


def _bigrams(text: str) -> set[tuple[str, str]]:
    t = [w for w in re.findall(r"[a-z0-9]+", _fold(text)) if w not in STOP and len(w) > 1]
    t = [_stem(w) for w in t]
    return set(zip(t, t[1:]))
