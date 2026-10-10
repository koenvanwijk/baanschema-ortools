"""KNLTB-regelhulp: chunken, zoeken, antwoorden (nep-LLM), updatecheck, endpoint.

Geen echte LLM-aanroepen; teksten hieronder zijn synthetisch (geen KNLTB-corpus).
"""
import importlib.util
import json
import sys

import pytest

from baanschemaatje.regels import bouw, updatecheck
from baanschemaatje.regels.antwoord import beantwoord, bouw_prompt
from baanschemaatje.regels.bronnen import ticks_naar_datum
from baanschemaatje.regels.zoek import Index, tokens

META = {"bron": "cr", "titel": "CR", "rang": 1, "versie": "vastgesteld 11-11-2025"}

CR_TXT = "INHOUD\n" + "\n" * 101 + """        01 Reglement
       1.     Eerste lid tekst.
       2.     Tweede lid tekst.
\f
A+P    02 Inhalen
       1.     Een afgebroken teamwedstrijd wordt uiterlijk op de eerstvolgende inhaaldag uitgespeeld.
       2.     Gefingeerde uitslagen zijn verboden.
                                    7
        03 Zonder leden
Dit artikel heeft geen leden.
BIJLAGE 1   Straffen
Boete bij afwezigheid team.
"""


def _chunks():
    return [
        {"id": "cr-49-1", "label": "CR art. 49 lid 1", "sectie": "Artikel 49 Inhalen", "rang": 1, "bron": "cr", "bron_titel": "CR",
         "text": "Een afgebroken teamwedstrijd wordt uiterlijk op de eerstvolgende inhaaldag uitgespeeld.", "url": "https://x/cr.pdf#page=20"},
        {"id": "cr-35-3", "label": "CR art. 35 lid 3", "sectie": "Artikel 35 Onvoltallig of afwezig", "rang": 1, "bron": "cr", "bron_titel": "CR",
         "text": "Een afwezig team verliest de teamwedstrijd; partijen gaan als walk-over naar de tegenstander.", "url": "https://x/cr.pdf#page=16"},
        {"id": "inv-1", "label": "Uitleg invallen, p. 1", "sectie": "pagina 1", "rang": 4, "bron": "inv", "bron_titel": "Uitleg invallen",
         "text": "Een speler mag invallen in een team van gelijke of hogere sterkte.", "url": "https://x/inv.pdf#page=1"},
        {"id": "wb-1", "label": "Wedstrijdbulletin 2026, 'Ballen'", "sectie": "Ballen", "rang": 2, "bron": "wb", "bron_titel": "WB",
         "text": "Per teamwedstrijd zijn nieuwe ballen nodig.", "url": "https://x/wb.pdf#page=6"},
    ]


def test_chunk_cr_artikel_lid_bijlage():
    cs = bouw.chunk_cr(CR_TXT, "https://x/cr.pdf", META)
    labels = [c["label"] for c in cs]
    assert labels[:5] == ["CR art. 1 lid 1", "CR art. 1 lid 2", "CR art. 2 lid 1", "CR art. 2 lid 2", "CR art. 3"]
    c = next(c for c in cs if c["id"] == "cr-2-1")
    assert c["url"].endswith("#page=2") and "inhaaldag" in c["text"]
    assert len(c["sha256"]) == 64 and c["versie"].startswith("vastgesteld")
    assert any(c["label"] == "CR bijlage 1" for c in cs)
    assert all("        7" not in c["text"] for c in cs)


def test_faq_en_ticks():
    html = ('<h2 class="x toggle__trigger y">Algemeen</h2><li><button class="a c-list-stack__button--toggle">Mag ik verzetten?</button>'
            '<div class="js-dropdown-menu c-list-stack__summary collapsed"><p>Alleen in &eacute;&eacute;n overleg.</p></div></li>')
    cs = bouw.chunk_faq(html, {"bron": "faq", "titel": "FAQ", "rang": 3, "versie": None})
    assert cs[0]["label"].startswith("FAQ: 'Mag ik verzetten?") and "één" in cs[0]["text"]
    assert ticks_naar_datum("639077872333770000") == "2026-02-27"


def test_tokens_synoniemen():
    assert set(tokens("gestaakt")) & set(tokens("afgebroken")) - {""}
    assert set(tokens("invaller")) & set(tokens("invallen"))
    assert set(tokens("verzetten")) & set(tokens("uitstel"))


def test_zoek_rangorde_en_relevantie():
    ix = Index(_chunks())
    r = ix.zoek("Gestaakte partijen: moeten we inhalen op de inhaaldag?", k=3)
    assert r[0][1]["id"] == "cr-49-1"
    r = ix.zoek("Mag een invaller uit een ander team spelen?", k=2)
    assert r[0][1]["id"] == "inv-1"
    r = ix.zoek("Wat zegt artikel 35?", k=2)
    assert r[0][1]["id"] == "cr-35-3"
    assert ix.zoek("xyzzy quux", k=3) == []


def test_beantwoord_met_nep_llm():
    seen = {}

    def nep(prompt, systeem):
        seen["prompt"], seen["sys"] = prompt, systeem
        return {"text": "**Ja, uiterlijk op de inhaaldag** (CR art. 49 lid 1). Zie ook [9].", "tokens_in": 3000, "tokens_uit": 400}

    out = beantwoord("afgebroken inhaaldag", Index(_chunks()), club={"naam": "TV X"}, llm=nep)
    assert [b["label"] for b in out["bronnen"]] == ["CR art. 49 lid 1"]  # [9] bestaat niet -> genegeerd
    assert out["bronnen"][0]["url"].endswith("#page=20")
    assert "Clubprofiel" in seen["prompt"] and "UITSLUITEND" in seen["sys"] and "«CR art. 49 lid 1»" in seen["prompt"]
    assert "[9]" not in out["antwoord"]
    assert 0 < out["kosten_usd"] < 0.01


def test_beantwoord_niets_gevonden_geen_llm():
    def boom(*a):
        raise AssertionError("LLM mag niet worden aangeroepen")

    out = beantwoord("xyzzy quux", Index(_chunks()), llm=boom)
    assert "niet in de KNLTB-regels" in out["antwoord"] and out["bronnen"] == []


def test_prompt_kapt_lange_chunks():
    c = dict(_chunks()[0], text="a " * 5000)
    assert "[…]" in bouw_prompt("v", [c], None)


def test_updatecheck_vergelijk():
    rb = {"documenten": [{"bron": "cr", "ts": "1", "sha256": "aa", "url": "u"},
                         {"bron": "faq", "lastmod": "2025-04-09"},
                         {"bron": "weg", "ts": "1", "url": "w"}]}
    links = {"cr": {"url": "u", "ts": "2"}}
    ch = updatecheck.vergelijk(rb, links, {updatecheck.FAQ_URL: "2026-01-01T00:00Z"}, {"cr": "bb"})
    wat = {(c["bron"], c["wat"]) for c in ch}
    assert wat == {("cr", "ts"), ("cr", "sha256"), ("faq", "lastmod"), ("weg", "link verdwenen")}
    assert updatecheck.vergelijk({"documenten": [{"bron": "cr", "ts": "2", "sha256": "bb"}]}, links, {}, {"cr": "bb"}) == []


@pytest.fixture(scope="module")
def client(root, tmp_path_factory):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    import os

    from fastapi.testclient import TestClient

    d = tmp_path_factory.mktemp("rb")
    (d / "rb.json").write_text(json.dumps({"gebouwd": "test", "chunks": _chunks()}))
    os.environ["BS_STORE"] = str(d / "store")
    os.environ["BS_REGELBANK"] = str(d / "rb.json")
    spec = importlib.util.spec_from_file_location("bs_server_app_regels", root / "server" / "baanschemaatje" / "app.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bs_server_app_regels"] = mod
    spec.loader.exec_module(mod)
    calls = []
    mod._REGEL_LLM = lambda p, s: calls.append(p) or {"text": "**Ja** [1]", "tokens_in": 10, "tokens_uit": 5}
    mod.REGEL_PER_IP_UUR = 3
    os.environ.pop("BS_REGELBANK")
    c = TestClient(mod.app)
    c.calls = calls
    return c


def test_endpoint_regelhulp(client):
    r = client.post("/regelhulp", json={"vraag": "afgebroken partij inhaaldag?", "club": "mierlo"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["bronnen"][0]["label"] == "CR art. 49 lid 1" and "competitieleider" in j["disclaimer"]
    assert "Mierlose" in client.calls[-1]
    assert client.post("/regelhulp", json={"vraag": "x" * 700}).status_code == 413
    assert client.post("/regelhulp", json={"vraag": ""}).status_code == 422
    codes = [client.post("/regelhulp", json={"vraag": "inhaaldag?"}).status_code for _ in range(3)]
    assert codes[-1] == 429


def test_beantwoord_groepsverwijzing():
    nep = lambda p, s: {"text": "Ja [1, 2].", "tokens_in": 1, "tokens_uit": 1}
    out = beantwoord("afgebroken inhaaldag afwezig walk-over", Index(_chunks()), llm=nep)
    assert len(out["bronnen"]) == 2 and "[" not in out["antwoord"]


def test_zoek_reserveert_cr_en_bulletin():
    extra = [dict(_chunks()[2], id=f"inv-{i}", bron=f"inv{i}") for i in range(10)]
    r = Index(_chunks() + extra).zoek("invallen nieuwe ballen afgebroken inhaaldag", k=4)
    rangen = {c["rang"] for _, c in r}
    assert 1 in rangen and 2 in rangen


UITLEG_TXT = """Competitie spelen in twee of meer teams
Inleidende tekst over meerdere teams.

Welke voorwaarden gelden er voor spelers met dispensatie?
1. Dispensatie geldt uitsluitend voor de competitie waarvoor deze wordt aangevraagd.
2. Dispensatie geldt alleen voor twee competitiesoorten op verschillende
   dag(del)en.
4. Spelers met dispensatie mogen niet invallen in een andere (derde) team/competitiesoort.

Invallen?
Het kan voorkomen dat een speler eenmalig in een ander team uitkomt.
"""


def test_chunk_uitleg_per_kop_en_voorwaarde():
    meta = {"bron": "tw", "titel": "Competitie spelen in twee of meer teams", "rang": 4, "versie": "2026-09-17"}
    cs = bouw.chunk_uitleg(UITLEG_TXT, "https://x/tw.pdf", meta, "tw", "Twee of meer teams")
    labels = [c["label"] for c in cs]
    assert "KNLTB-uitleg Twee of meer teams, voorwaarde 4" in labels
    assert "KNLTB-uitleg Twee of meer teams, 'Invallen?'" in labels
    v2 = next(c for c in cs if c["label"].endswith("voorwaarde 2"))
    assert "dag(del)en" in v2["text"] and "Welke voorwaarden" in v2["text"]  # kopcontext + vervolgregel
    v4 = next(c for c in cs if c["label"].endswith("voorwaarde 4"))
    assert v4["groep"] == v2["groep"]


def test_namen_en_synoniemen():
    from baanschemaatje.regels.zoek import strip_namen

    q = strip_namen("Ik overweeg om Janneke Brouwers te vragen. Mag Piet van der Berg invallen?")
    assert "Janneke" not in q and "Berg" not in q
    assert set(tokens("label 2x spelen")) & set(tokens("dispensatie"))
    assert set(tokens("in een derde team")) & set(tokens("invallen"))
    assert "§regen" not in tokens("wij zoeken weer een dame")


def test_met_context_voegt_groep_toe():
    meta = {"bron": "tw", "titel": "Twee teams", "rang": 4, "versie": None}
    cs = bouw.chunk_uitleg(UITLEG_TXT, "u", meta, "tw", "Twee of meer teams")
    ix = Index(cs)
    hit = [c for _, c in ix.zoek("mag een speler met dispensatie invallen in een derde team", k=1)]
    assert hit[0]["label"].endswith("voorwaarde 4")
    assert {c["label"][-12:] for c in ix.met_context(hit)} >= {"voorwaarde 1", "voorwaarde 2", "voorwaarde 4"}


# --- Regressieset op de echte regelbank (geen LLM). De regelbank staat niet in de
# repo (auteursrecht); zet BS_REGELBANK_TEST=pad/regelbank.json om dit te draaien.
import os  # noqa: E402

_RB = os.environ.get("BS_REGELBANK_TEST", "/workspace/regelbank.json")
REGRESSIE = [
    ("wij zoeken weer een dame om in te vallen. Ik overweeg om Janneke Brouwers te vragen, maar zij heeft al dispensatie "
     "om in 2 teams te spelen (met label \u201c2x spelen\u201d). Dat betekent dat zij niet meer in een ander team mag spelen, toch?",
     ["KNLTB-uitleg Twee of meer teams, voorwaarde 4"]),
    ("Afgebroken partijen in kampioenswedstrijd; moeten we op eerstvolgende inhaaldag inhalen, en kunnen zij claimen als we niet kunnen?",
     ["CR art. 49 lid 1", "CR art. 35", "Wedstrijdbulletin 2026, 'Uitstel van teamwedstrijden'"]),
    ("Mag een speler uit ons eerste team invallen in ons tweede team, en hoe vaak mag dat?", ["CR art. 29"]),
    ("Mag een speler uit een sterker team invallen in een zwakker team?", ["CR art. 29"]),
    ("Wat gebeurt er als een team niet komt opdagen?", ["CR art. 35", "Wedstrijdbulletin 2026, 'Team afwezig'"]),
]


@pytest.mark.skipif(not os.path.isfile(_RB), reason="echte regelbank niet aanwezig")
@pytest.mark.parametrize("vraag,verwacht", REGRESSIE)
def test_regressie_retrieval(vraag, verwacht):
    ix = Index(json.load(open(_RB))["chunks"])
    labels = [c["label"] for c in ix.met_context([c for _, c in ix.zoek(vraag)])]
    for v in verwacht:
        assert any(lab == v or lab.startswith(v + " ") for lab in labels), (v, labels)


def test_zie_ook_vangnet():
    meta = {"bron": "tw", "titel": "Twee teams", "rang": 4, "versie": None}
    ix = Index(bouw.chunk_uitleg(UITLEG_TXT, "u", meta, "tw", "Twee of meer teams"))
    nep = lambda p, s: {"text": "**Klopt.** (KNLTB-uitleg Twee of meer teams, voorwaarde 4)", "tokens_in": 1, "tokens_uit": 1}
    out = beantwoord("mag een speler met dispensatie invallen in een derde team", ix, llm=nep)
    assert "Zie ook" in out["antwoord"] and "voorwaarde 1: “1. Dispensatie geldt uitsluitend" in out["antwoord"] and "competitieleider" in out["antwoord"]
    assert len(out["bronnen"]) >= 2
    nep2 = lambda p, s: {"text": "**Klopt.** (KNLTB-uitleg Twee of meer teams, voorwaarde 4)\nLet op:\n- x", "tokens_in": 1, "tokens_uit": 1}
    assert "Zie ook" not in beantwoord("mag een speler met dispensatie invallen in een derde team", ix, llm=nep2)["antwoord"]
