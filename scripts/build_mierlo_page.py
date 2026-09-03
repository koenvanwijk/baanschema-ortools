#!/usr/bin/env python3
"""Build a standalone GitHub Pages view for the Mierlo 2026-2027 Sunday schedule.

Reads the per-day OR-Tools outputs (docs/ortools_2026-2027_<date>.json) plus the
season TSV, and renders one self-contained HTML page (docs/mierlo-2026-2027.html)
with a court grid per Sunday, a team summary, and a per-day rule-violation block.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ortools_planner import parse_input  # type: ignore
from validate_schedule import validate_day  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

DATES = ["06-09-2026", "13-09-2026", "20-09-2026", "27-09-2026", "04-10-2026", "11-10-2026"]


def hhmm_to_min(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def min_to_hhmm(m: int) -> str:
    return f"{m//60:02d}:{m%60:02d}"


# Consequente kleurfamilies per categorie (Koen, 2026-08-29): Rood/Oranje/Groen
# waren al duidelijk; de overige categorieen krijgen nu ook een vaste hue-band
# in plaats van een volledig willekeurige hash-kleur per team. Binnen een
# categorie krijgt elk team nog een unieke tint (net als bij Rood/Oranje/Groen).
_CATEGORY_HUES: list[tuple[str, int]] = [
    ("rood", 0),
    ("oranje", 30),
    ("dames zondag", 60),
    ("groen zondag", 125),
    ("heren zondag", 170),
    ("jongens 13 t/m 17", 210),
    ("junioren 11 t/m 14", 250),
    ("gemengd zondag", 290),
    ("meisjes 13 t/m 17", 330),
]

_COLOR_CACHE: dict[str, str] = {}
_USED_HUES: list[int] = []


def _is_hue_far_enough(h: int, min_gap: int = 24) -> bool:
    return all(min((h - u) % 360, (u - h) % 360) >= min_gap for u in _USED_HUES)


def _base_hue_for(lname: str) -> int | None:
    for needle, hue in _CATEGORY_HUES:
        if needle in lname:
            return hue
    return None


def color_for(name: str) -> str:
    if name in _COLOR_CACHE:
        return _COLOR_CACHE[name]

    lname = name.lower()
    base_hue = _base_hue_for(lname)
    seed = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16)
    if base_hue is None:
        seed_hue = seed % 360
    else:
        seed_hue = (base_hue + (seed % 21) - 10) % 360

    hue = None
    for step in range(360):
        cand = (seed_hue + step * 37) % 360
        if _is_hue_far_enough(cand):
            hue = cand
            break
    if hue is None:
        hue = seed_hue

    _USED_HUES.append(hue)
    sat = 92 if base_hue is None else 88
    light = 58 if base_hue is None else 56
    color = f"hsl({hue} {sat}% {light}%)"
    _COLOR_CACHE[name] = color
    return color


def short_team_name(schema: str, home_team: str = "") -> str:
    low = schema.lower()
    if "gemengd zondag" in low:
        prefix = "GEM"
    elif "heren zondag" in low:
        prefix = "HER"
    elif "dames zondag" in low:
        prefix = "DAM"
    elif "groen zondag" in low:
        prefix = "GRO"
    elif "jongens 13 t/m 17" in low:
        prefix = "JO13-17"
    elif "meisjes 13 t/m 17" in low:
        prefix = "ME13-17"
    elif "junioren 11 t/m 14" in low:
        prefix = "JU11-14"
    else:
        prefix = schema.split("–", 1)[0].strip()[:20]

    parts = [p.strip() for p in schema.split("–")]
    klasse = ""
    if len(parts) >= 2:
        klasse = re.sub(r"\s*\([^)]*\)", "", parts[1]).replace("klasse", "").strip()

    m = re.search(r"\bMIERLO\s*(\d+)\b", home_team or "", flags=re.I)
    home_short = f"M{m.group(1)}" if m else ""
    return re.sub(r"\s+", " ", " ".join(x for x in [prefix, klasse, home_short] if x)).strip()


def explain_row(row: dict, day_rows: list[dict]) -> str:
    """Menselijke uitleg waarom deze partij op dit moment/deze baan gepland is.

    Werkt puur op de output-rijen (geen solver-interne data nodig) door bekende
    planningsregels (SPEC.md) te herkennen aan patronen in de uitkomst:
    baan-bezetting vlak ervoor, eigen fasevolgorde (S voor D voor GD), starten
    in ronde met een teamgenoot, en leeftijds-/schema-voorkeuren.
    """
    team = row.get("team", "")
    team_l = team.lower()
    kind = row.get("kind")
    start = row.get("start")
    court = row.get("court")
    if not start or start == "NIET_GELUKT":
        return ""
    start_min = hhmm_to_min(start)
    team_id = row.get("team_id") or team

    is_mixed = "gemengd zondag" in team_l
    is_jeugd_1317 = ("jongens 13 t/m 17" in team_l) or ("meisjes 13 t/m 17" in team_l)
    is_junioren = "junioren" in team_l

    same_team = [r for r in day_rows if (r.get("team_id") or r.get("team")) == team_id and r is not row and r.get("start") not in (None, "", "NIET_GELUKT")]

    reasons: list[str] = []

    # 1. Fasevolgorde binnen het team: D/GD start pas als de voorgaande fase
    #    (singles, dan dubbels) klaar is — hard voor 8-partijenteams, en in de
    #    praktijk ook zo gepland bij de meeste andere teams.
    if kind in ("D", "M"):
        earlier_s = [r for r in same_team if r.get("kind") == "S"]
        if earlier_s:
            last_s_end = max(hhmm_to_min(r["end"]) for r in earlier_s)
            if start_min >= last_s_end:
                reasons.append(
                    f"Start pas na de singles van dit team (laatste eindigt om {min_to_hhmm(last_s_end)}) "
                    "— singles gaan voor dubbels/gemengd (S→D→GD-volgorde)."
                )
    if kind == "M":
        earlier_d = [r for r in same_team if r.get("kind") == "D"]
        if earlier_d:
            last_d_end = max(hhmm_to_min(r["end"]) for r in earlier_d)
            if start_min >= last_d_end:
                reasons.append(
                    f"Start pas na de dubbels van dit team (laatste eindigt om {min_to_hhmm(last_d_end)})."
                )

    # 2. Rondegewijze afwikkeling: gelijktijdig met een teamgenoot van dezelfde soort.
    siblings = [r for r in same_team if r.get("kind") == kind and r.get("start") == start and r.get("part") != row.get("part")]
    if siblings:
        names = ", ".join(sorted(r["part"] for r in siblings))
        reasons.append(f"Start gelijktijdig met {names} van hetzelfde team (rondegewijze afwikkeling i.p.v. losse starts).")

    # 3. Baanbezetting: wat zat er vlak voor deze partij op dezelfde baan?
    prior_on_court = [
        r for r in day_rows
        if r.get("court") == court and r is not row
        and r.get("start") not in (None, "", "NIET_GELUKT")
        and hhmm_to_min(r["end"]) <= start_min
    ]
    if prior_on_court:
        last = max(prior_on_court, key=lambda r: hhmm_to_min(r["end"]))
        gap = start_min - hhmm_to_min(last["end"])
        if gap == 0:
            other = short_team_name(last.get("team", ""), last.get("home_team", ""))
            reasons.append(f"Baan {court} was tot {last['end']} bezet door {other} ({last['part']}) — start meteen daarna.")
        elif gap > 0 and not reasons:
            other = short_team_name(last.get("team", ""), last.get("home_team", ""))
            reasons.append(
                f"Baan {court} was vrij vanaf {last['end']} ({other} {last['part']} klaar), "
                f"maar dit team kon pas om {start} beginnen (zie hieronder)."
            )

    # 4. Schema-/leeftijdsregels: alleen noemen als ze de start ook echt
    #    verklaren. Voorheen citeerden we deze voorkeuren ook als er allang een
    #    onverklaard gat zat (bijv. banen al vanaf 09:00 vrij, team startte toch
    #    pas om 11:00) — dat wekte de indruk dat een regel de vertraging
    #    afdwong, terwijl het gewoon een niet-optimale oplossing van de solver
    #    was. Check daarom eerst of er een eerder moment was waarop dit team op
    #    zijn eigen banen had kunnen beginnen.
    own_courts = {r["court"] for r in same_team + [row]}
    earliest_free_for_team = None
    for cand_t in range(9 * 60, start_min, 15):
        blocked = any(
            r.get("court") in own_courts
            and hhmm_to_min(r["start"]) <= cand_t < hhmm_to_min(r["end"])
            for r in day_rows
            if r.get("start") not in (None, "", "NIET_GELUKT") and (r.get("team_id") or r.get("team")) != team_id
        )
        if not blocked:
            earliest_free_for_team = cand_t
            break
    could_start_earlier = earliest_free_for_team is not None and not reasons

    if is_mixed and start_min == 10 * 60:
        reasons.append("Gemengd-teams starten volgens de parkregel nooit voor 10:00 (harde eis).")
    elif is_jeugd_1317 and start_min >= 11 * 60 and not could_start_earlier:
        reasons.append("Jeugd 13-17 heeft een voorkeur voor een middagstart (vanaf ca. 11:00) i.p.v. vroeg in de ochtend — dit is een zachte optimalisatie-voorkeur, geen harde eis.")
    elif is_junioren and start_min <= 11 * 60 and not could_start_earlier:
        reasons.append("Junioren (11-14) hebben juist een voorkeur voor een vroege start.")
    elif could_start_earlier:
        reasons.append(
            f"Dit kon in principe al vanaf {min_to_hhmm(earliest_free_for_team)} — er was geen regel of "
            "bezette baan die een latere start afdwong. Dit is vermoedelijk een niet-volledig "
            "uitgeoptimaliseerde plek in het schema (de solver stopt na een tijdslimiet met de "
            "beste oplossing tot dan toe, niet per se de allerbeste); meld dit gerust, dan draaien "
            "we die dag met meer rekentijd opnieuw."
        )

    if not reasons:
        reasons.append(
            "Startmoment volgt uit de baan-optimalisatie (compactheid, minimale wachttijd, "
            "weinig baanwissels) — er is geen aparte regel die een latere start afdwingt."
        )

    return " ".join(reasons)


def render_gaps(rows: list[dict]) -> str:
    """Lijst alle gaten van >=30 min op elke baan tussen twee partijen op die dag.

    Voor elk gat wordt vermeld: baan, tijdvak, wat ervoor/erna gepland stond, en
    of er een duidelijke reden is (bv. baan gereserveerd voor latere leeftijds-
    groep, of team dat nog niet klaar was met een vorige fase elders) dan wel
    dat het een onbenutte plek is die de solver had kunnen opvullen.
    """
    valid = [r for r in rows if r.get("start") not in (None, "", "NIET_GELUKT") and r.get("court")]
    if not valid:
        return ""
    courts = sorted({int(r["court"]) for r in valid})
    gaps_html = []
    total_gap_min = 0
    n_gaps = 0
    for c in courts:
        on_court = sorted((r for r in valid if int(r["court"]) == c), key=lambda r: hhmm_to_min(r["start"]))
        for prev, nxt in zip(on_court, on_court[1:]):
            gap = hhmm_to_min(nxt["start"]) - hhmm_to_min(prev["end"])
            if gap < 30:
                continue
            n_gaps += 1
            total_gap_min += gap
            prev_short = short_team_name(prev.get("team", ""), prev.get("home_team", ""))
            next_short = short_team_name(nxt.get("team", ""), nxt.get("home_team", ""))
            why = explain_row(nxt, valid)
            explained = bool(why) and "kon in principe al vanaf" not in why and "geen aparte regel" not in why
            verdict = (
                "<span class='gap-explained'>verklaard</span>" if explained
                else "<span class='gap-unexplained'>mogelijk te vullen</span>"
            )
            gaps_html.append(
                f"<li>Baan {c}: <strong>{prev['end']}–{nxt['start']}</strong> "
                f"({gap} min) leeg — na {html.escape(prev_short)} ({prev['part']}), "
                f"voor {html.escape(next_short)} ({nxt['part']}) {verdict}"
                f"<div class='gap-why'>{html.escape(why)}</div></li>"
            )
    if not gaps_html:
        return "<div class='ok'>✓ Geen gaten ≥30 min op enige baan deze dag.</div>"
    return (
        f"<div class='gaps'><strong>Gaten-analyse ({n_gaps} gaten, totaal {total_gap_min} baan-minuten leeg)</strong>"
        "<ul>" + "".join(gaps_html) + "</ul></div>"
    )


def render_grid(rows: list[dict]) -> str:
    valid = [r for r in rows if r.get("start") not in (None, "", "NIET_GELUKT") and r.get("court")]
    if not valid:
        return "<p>Geen planbare wedstrijden.</p>"
    start_min = min(hhmm_to_min(r["start"]) for r in valid)
    end_min = max(hhmm_to_min(r["end"]) for r in valid)
    times = list(range(start_min, end_min + 1, 15))

    cell: dict[tuple[int, int], dict] = {}
    for r in valid:
        s, e = hhmm_to_min(r["start"]), hhmm_to_min(r["end"])
        short = short_team_name(r.get("team", ""), r.get("home_team", ""))
        away = r.get("away_team", "")
        label = f"{short} · {r['part']}" + (f" vs {away}" if away else "")
        why = explain_row(r, valid)
        detail = (
            f"{r.get('team','')} | {r['part']} | {r['start']}-{r['end']} | Baan {r.get('court')}"
            + (f" | vs {away}" if away else "")
            + (f"\n\nWaarom dit moment/deze baan?\n{why}" if why else "")
        )
        color = color_for(r.get("team_id") or r.get("team", ""))
        for t in range(s, e, 15):
            cell[(t, int(r["court"]))] = {"label": label, "detail": detail, "why": why, "color": color, "is_start": t == s}

    header = "".join(f"<th>Baan {c}</th>" for c in range(1, 11))
    body = []
    for t in times[:-1]:
        row_cls = "major-row" if ((t - start_min) % 90 == 0) else ""
        tds = [f"<td class='time'>{min_to_hhmm(t)}</td>"]
        for c in range(1, 11):
            v = cell.get((t, c))
            if v:
                txt = v["label"] if v["is_start"] else "·"
                title_attr = f" title='{html.escape(v['why'], quote=True)}'" if v.get("why") else ""
                tds.append(
                    f"<td class='tap-cell' style='background:{v['color']}' data-detail='{html.escape(v['detail'], quote=True)}'{title_attr}>"
                    f"<div class='cell'>{html.escape(txt)}</div></td>"
                )
            else:
                tds.append("<td class='empty'>—</td>")
        body.append(f"<tr class='{row_cls}'>" + "".join(tds) + "</tr>")
    return (
        "<div class='grid-wrap'><table class='grid'><thead><tr><th>Tijd</th>"
        + header + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
    )


def render_summary(rows: list[dict], captains: dict[str, str] | None = None) -> str:
    valid = [r for r in rows if r.get("start") not in (None, "", "NIET_GELUKT")]
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in valid:
        by_team[r.get("team_id") or r.get("team") or r.get("team_short")].append(r)
    if not by_team:
        return ""
    items = []
    for key, rr in sorted(by_team.items(), key=lambda kv: min(hhmm_to_min(x["start"]) for x in kv[1])):
        schema = rr[0].get("team", "") or rr[0].get("team_short", "")
        short = rr[0].get("team_short") or short_team_name(schema, rr[0].get("home_team", ""))
        home, away = rr[0].get("home_team", ""), rr[0].get("away_team", "")
        matchup = f"{home} vs {away}" if (home or away) else "-"
        first = min_to_hhmm(min(hhmm_to_min(x["start"]) for x in rr))
        last = min_to_hhmm(max(hhmm_to_min(x["end"]) for x in rr))
        color = color_for(key)
        captain = (captains or {}).get(short, "") or next((x.get("captain") for x in rr if x.get("captain")), "")
        captain_html = f" — aanvoerder <strong>{html.escape(captain)}</strong>" if captain else ""
        items.append(
            f"<li><span class='sw' style='background:{color}'></span><strong>{html.escape(short)}</strong> "
            f"<span class='small'>({html.escape(schema)})</span>: {html.escape(matchup)} — "
            f"partijen <strong>{len(rr)}</strong> — {first}–{last}{captain_html}</li>"
        )
    return "<div class='summary'><h3>Teams deze zondag</h3><ul>" + "".join(items) + "</ul></div>"


_GOLD_MATCH_RE = re.compile(r"^(?P<label>\S+)\s+vs\s+(?P<opp>.+)$")


def render_summary_gold(rows: list[dict], captains: dict[str, str] | None = None) -> str:
    """Team-summary voor het Gold-schema (docs/gold_result_najaar2026.json).

    Rijen hebben een ander schema dan de OR-Tools output: 'team_short' i.p.v.
    'team'/'team_id', en reservering-/opwarmblokken (kind == 'W', part == '')
    die niet als eigen 'team' in de samenvatting horen (die zijn geen partij,
    maar een baanreservering). Die reservering-rijen blijven wel gewoon op het
    rooster staan (render_grid_gold), ze worden alleen uit deze samenvatting
    gefilterd.
    """
    matches = [r for r in rows if r.get("kind") != "W" and (r.get("part") or "").strip()]
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in matches:
        by_team[r.get("team_short") or "?"].append(r)
    if not by_team:
        return ""
    items = []
    for short, rr in sorted(by_team.items(), key=lambda kv: min(hhmm_to_min(x["start"]) for x in kv[1])):
        first = min_to_hhmm(min(hhmm_to_min(x["start"]) for x in rr))
        last = min_to_hhmm(max(hhmm_to_min(x["end"]) for x in rr))
        color = color_for(short)
        captain = (captains or {}).get(short, "") or next((x.get("captain") for x in rr if x.get("captain")), "")
        captain_html = f" — aanvoerder <strong>{html.escape(captain)}</strong>" if captain else ""
        opp = ""
        for r in rr:
            m = _GOLD_MATCH_RE.match((r.get("part") or "").strip())
            if m:
                opp = m.group("opp").strip()
                break
        matchup = f" vs {html.escape(opp)}" if opp else ""
        items.append(
            f"<li><span class='sw' style='background:{color}'></span><strong>{html.escape(short)}</strong>{matchup} — "
            f"partijen <strong>{len(rr)}</strong> — {first}–{last}{captain_html}</li>"
        )
    return "<div class='summary'><h3>Teams deze zondag (Gold)</h3><ul>" + "".join(items) + "</ul></div>"


def render_grid_gold(rows: list[dict]) -> str:
    """Roosterweergave voor Gold-rijen; toont ook reservering-/opwarmblokken (kind=='W')."""
    valid = [r for r in rows if r.get("start") not in (None, "", "NIET_GELUKT") and r.get("court")]
    if not valid:
        return "<p>Geen Gold-planning beschikbaar.</p>"
    start_min = min(hhmm_to_min(r["start"]) for r in valid)
    end_min = max(hhmm_to_min(r["end"]) for r in valid)
    times = list(range(start_min, end_min + 1, 15))

    cell: dict[tuple[int, int], dict] = {}
    for r in valid:
        s, e = hhmm_to_min(r["start"]), hhmm_to_min(r["end"])
        short = r.get("team_short", "")
        part = (r.get("part") or "").strip()
        label = f"{short} · {part}" if part else short
        captain = r.get("captain", "")
        detail = (
            f"{short} | {part or '(reservering)'} | {r['start']}-{r['end']} | Baan {r.get('court')}"
            + (f" | aanvoerder {captain}" if captain else "")
        )
        color = color_for(short)
        for t in range(s, e, 15):
            cell[(t, int(r["court"]))] = {"label": label, "detail": detail, "color": color, "is_start": t == s}

    header = "".join(f"<th>Baan {c}</th>" for c in range(1, 11))
    body = []
    for t in times[:-1]:
        row_cls = "major-row" if ((t - start_min) % 90 == 0) else ""
        tds = [f"<td class='time'>{min_to_hhmm(t)}</td>"]
        for c in range(1, 11):
            v = cell.get((t, c))
            if v:
                txt = v["label"] if v["is_start"] else "·"
                tds.append(
                    f"<td class='tap-cell' style='background:{v['color']}' data-detail='{html.escape(v['detail'], quote=True)}'>"
                    f"<div class='cell'>{html.escape(txt)}</div></td>"
                )
            else:
                tds.append("<td class='empty'>—</td>")
        body.append(f"<tr class='{row_cls}'>" + "".join(tds) + "</tr>")
    return (
        "<div class='grid-wrap'><table class='grid'><thead><tr><th>Tijd</th>"
        + header + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
    )


def render_violations(rep) -> str:
    if not rep.hard and not rep.model:
        return "<div class='ok'>✓ Geen HARD- of MODEL-afwijkingen.</div>"
    out = ["<div class='violations'>"]
    if rep.hard:
        out.append("<strong>HARD-afwijkingen (mogen niet voorkomen)</strong><ul>")
        out += [f"<li>{html.escape(v.line().strip())}</li>" for v in rep.hard]
        out.append("</ul>")
    if rep.model:
        out.append("<strong>MODEL/soft-afwijkingen (niet-blokkerend)</strong><ul>")
        out += [f"<li>{html.escape(v.line().strip())}</li>" for v in rep.model]
        out.append("</ul>")
    out.append("</div>")
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=ROOT / "data" / "season_2026-2027.tsv")
    ap.add_argument("--out", type=Path, default=DOCS / "mierlo-2026-2027.html")
    ap.add_argument("--captains", type=Path, default=DOCS / "gold_captains_najaar2026.json")
    ap.add_argument("--gold", type=Path, default=DOCS / "gold_result_najaar2026.json")
    args = ap.parse_args()

    teams, _res = parse_input(args.input)

    captains_by_date: dict[str, dict[str, str]] = {}
    if args.captains.exists():
        try:
            captains_by_date = json.loads(args.captains.read_text(encoding="utf-8"))
        except Exception:
            captains_by_date = {}

    gold_by_date: dict[str, list[dict]] = {}
    if args.gold.exists():
        try:
            gold_by_date = json.loads(args.gold.read_text(encoding="utf-8"))
        except Exception:
            gold_by_date = {}

    sections = []
    for d in DATES:
        path = DOCS / f"ortools_2026-2027_{d}.json"
        day_captains = captains_by_date.get(d, {})
        gold_rows = gold_by_date.get(d, [])
        gold_block = (
            (render_summary_gold(gold_rows, day_captains) + render_grid_gold(gold_rows))
            if gold_rows else "<div class='ort-status-inline'>Gold-referentie niet beschikbaar voor deze datum.</div>"
        )
        if not path.exists():
            sections.append(
                f"<h2>{d}</h2><div class='ort-status-inline'>Nog geen OR-Tools planning beschikbaar.</div>"
                f"<div class='plan-view ort-view'>{''}</div>"
                f"<div class='plan-view gold-view hidden'>{gold_block}</div>"
            )
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("rows", [])
        rep = validate_day(d, teams, rows)
        st = rep.stats.get(d, {})
        pretty = datetime.strptime(d, "%d-%m-%Y").strftime("%A %d %B %Y")
        head = (
            f"<h2>{html.escape(d)} <span class='small'>({html.escape(pretty)}) — "
            f"{st.get('teams_verwacht', '?')} thuiswedstrijden, "
            f"{st.get('partijen_gepland', '?')}/{st.get('partijen_verwacht', '?')} partijen gepland, "
            f"status {html.escape(data.get('status','?'))}</span></h2>"
        )
        ort_block = render_violations(rep) + render_summary(rows, day_captains) + render_gaps(rows) + render_grid(rows)
        sections.append(
            head
            + f"<div class='plan-view ort-view'>{ort_block}</div>"
            + f"<div class='plan-view gold-view hidden'>{gold_block}</div>"
        )

    page = f"""<!doctype html>
<html lang='nl'>
<head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<meta http-equiv='Cache-Control' content='no-cache, no-store, must-revalidate'>
<title>Mierlo baanschema 2026-2027 (zondagen)</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;max-width:1550px;margin:1.2rem auto;padding:0 1rem}}
.small{{color:#666;font-weight:400}}
.summary{{background:#fafafa;border:1px solid #eee;border-radius:10px;padding:.7rem .9rem;margin:.5rem 0 1rem 0}}
.summary h3{{margin:.2rem 0 .5rem 0;font-size:1rem}}
.summary ul{{margin:.2rem 0 .1rem 1.1rem;padding:0}}
.summary li{{margin:.25rem 0}}
.sw{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:.35rem;vertical-align:middle;border:1px solid rgba(0,0,0,.15)}}
.violations{{background:#fff6bf;border:1px solid #e6cc55;border-radius:10px;padding:.65rem .85rem;margin:.4rem 0 .8rem 0}}
.violations ul{{margin:.35rem 0 .5rem 1.1rem;padding:0}}
.ok{{background:#eefaf1;border:1px solid #b6e3c1;border-radius:10px;padding:.55rem .8rem;margin:.4rem 0 .8rem 0;font-size:13px;color:#175}}
.gaps{{background:#eef3ff;border:1px solid #b7c8f2;border-radius:10px;padding:.6rem .85rem;margin:.4rem 0 .8rem 0;font-size:13px}}
.gaps ul{{margin:.35rem 0 .3rem 1.1rem;padding:0}}
.gaps li{{margin:.35rem 0}}
.gap-explained{{color:#175;font-weight:600;font-size:11px}}
.gap-unexplained{{color:#a15c00;font-weight:600;font-size:11px}}
.gap-why{{color:#555;font-size:11.5px;margin:.1rem 0 0 0}}
.ort-status-inline{{background:#f7f7f7;border:1px solid #ddd;border-radius:10px;padding:.55rem .75rem;margin:.2rem 0 1rem 0;font-size:12px;color:#333}}
.grid-wrap{{overflow:auto;border:1px solid #eee;border-radius:10px;margin-bottom:2rem}}
.grid{{border-collapse:collapse;width:100%;table-layout:fixed}}
.grid th,.grid td{{border:1px solid #dcdfe6;padding:.2rem .25rem;vertical-align:middle;height:30px;box-sizing:border-box}}
.grid tr.major-row td{{border-top:3px solid #8f97a8}}
.grid th{{position:sticky;top:0;background:#fafafa;z-index:2;font-size:12px}}
.time{{font-variant-numeric:tabular-nums;background:#f3f4f7;position:sticky;left:0;z-index:1;width:56px;font-size:11px;font-weight:600}}
.empty{{color:#aeb4c2;text-align:center}}
.cell{{font-size:10px;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#111;font-weight:600}}
.tap-cell{{cursor:pointer}}
.toggle{{display:flex;gap:.5rem;margin:.6rem 0 1rem 0}}
.toggle button{{border:1px solid #ccc;background:#fff;padding:.35rem .6rem;border-radius:8px;cursor:pointer}}
.toggle button.active{{background:#111;color:#fff;border-color:#111}}
.hidden{{display:none}}
</style>
</head>
<body>
<div style='display:flex;gap:.5rem;align-items:center;margin:.4rem 0 .6rem 0'>
  <label for='seasonSelect' style='font-weight:600;font-size:13px'>Seizoen:</label>
  <select id='seasonSelect' onchange="if(this.value==='voorjaar'){{location.href='./index.html?season=voorjaar';}}">
    <option value='najaar' selected>2026-Najaar</option>
    <option value='voorjaar'>2026-Voorjaar</option>
  </select>
</div>
<h1>Mierlose T.V. — baanschema zondagen 2026-2027</h1>
<p class='small'>Alleen de thuiswedstrijden van Mierlo op zondagen, gepland per zondag met de OR-Tools CP-SAT solver.
Kolommen = banen (1–10), rijen = kwartierblokken. Tik op een cel voor detail.
Zie ook de <a href='./index.html'>2025-2026 pagina</a> en
<a href='./MIERLO_2026_2027_PLANNING.md'>de toelichting</a>.</p>
<div class='toggle'>
  <button id='btn-ort' class='active' onclick="setPlan('ort')">OR-Tools</button>
  <button id='btn-gold' onclick="setPlan('gold')">Gold</button>
</div>
{''.join(sections)}
<div id='bg' style='position:fixed;inset:0;background:rgba(0,0,0,.45);display:none;align-items:center;justify-content:center;z-index:20' onclick='this.style.display="none"'>
  <div style='background:#fff;border-radius:12px;max-width:92vw;padding:.9rem 1rem' onclick='event.stopPropagation()'>
    <strong>Wedstrijddetail</strong><div id='mt' style='margin-top:.4rem;white-space:pre-wrap'></div>
    <div style='margin-top:.7rem'><button onclick="document.getElementById('bg').style.display='none'">Sluiten</button></div>
  </div>
</div>
<script>
function bindCellPopups(){{
  document.querySelectorAll('.tap-cell').forEach(function(el){{
    if(el.dataset.bound==='1') return;
    el.dataset.bound='1';
    el.addEventListener('click', function(){{
      document.getElementById('mt').textContent = el.getAttribute('data-detail');
      document.getElementById('bg').style.display = 'flex';
    }});
  }});
}}
function setPlan(mode){{
  const ort = document.querySelectorAll('.ort-view');
  const gold = document.querySelectorAll('.gold-view');
  const bo = document.getElementById('btn-ort');
  const bg = document.getElementById('btn-gold');
  ort.forEach(e=>e.classList.add('hidden'));
  gold.forEach(e=>e.classList.add('hidden'));
  bo.classList.remove('active');
  bg.classList.remove('active');
  if(mode==='gold'){{
    gold.forEach(e=>e.classList.remove('hidden'));
    bg.classList.add('active');
  }} else {{
    ort.forEach(e=>e.classList.remove('hidden'));
    bo.classList.add('active');
  }}
  bindCellPopups();
}}
bindCellPopups();
</script>
</body>
</html>
"""
    args.out.write_text(page, encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
