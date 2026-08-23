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


def color_for(name: str) -> str:
    seed = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16)
    hue = (seed * 137 + 60) % 360
    return f"hsl({hue} 82% 58%)"


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
        detail = f"{r.get('team','')} | {r['part']} | {r['start']}-{r['end']} | Baan {r.get('court')}" + (f" | vs {away}" if away else "")
        color = color_for(r.get("team_id") or r.get("team", ""))
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


def render_summary(rows: list[dict]) -> str:
    valid = [r for r in rows if r.get("start") not in (None, "", "NIET_GELUKT")]
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in valid:
        by_team[r.get("team_id") or r.get("team")].append(r)
    if not by_team:
        return ""
    items = []
    for key, rr in sorted(by_team.items(), key=lambda kv: min(hhmm_to_min(x["start"]) for x in kv[1])):
        schema = rr[0].get("team", "")
        short = short_team_name(schema, rr[0].get("home_team", ""))
        home, away = rr[0].get("home_team", ""), rr[0].get("away_team", "")
        matchup = f"{home} vs {away}" if (home or away) else "-"
        first = min_to_hhmm(min(hhmm_to_min(x["start"]) for x in rr))
        last = min_to_hhmm(max(hhmm_to_min(x["end"]) for x in rr))
        color = color_for(key)
        items.append(
            f"<li><span class='sw' style='background:{color}'></span><strong>{html.escape(short)}</strong> "
            f"<span class='small'>({html.escape(schema)})</span>: {html.escape(matchup)} — "
            f"partijen <strong>{len(rr)}</strong> — {first}–{last}</li>"
        )
    return "<div class='summary'><h3>Teams deze zondag</h3><ul>" + "".join(items) + "</ul></div>"


def render_violations(rep) -> str:
    if not rep.hard and not rep.model:
        return "<div class='ok'>✓ Geen HARD- of MODEL-afwijkingen.</div>"
    out = ["<div class='violations'>"]
    if rep.hard:
        out.append("<strong>HARD-afwijkingen (mogen niet voorkomen)</strong><ul>")
        out += [f"<li>{html.escape(v)}</li>" for v in rep.hard]
        out.append("</ul>")
    if rep.model:
        out.append("<strong>MODEL/soft-afwijkingen (niet-blokkerend)</strong><ul>")
        out += [f"<li>{html.escape(v)}</li>" for v in rep.model]
        out.append("</ul>")
    out.append("</div>")
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=ROOT / "data" / "season_2026-2027.tsv")
    ap.add_argument("--out", type=Path, default=DOCS / "mierlo-2026-2027.html")
    args = ap.parse_args()

    teams, _res = parse_input(args.input)

    sections = []
    for d in DATES:
        path = DOCS / f"ortools_2026-2027_{d}.json"
        if not path.exists():
            sections.append(f"<h2>{d}</h2><div class='ort-status-inline'>Nog geen planning beschikbaar.</div>")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("rows", [])
        rep = validate_day(d, teams, rows)
        pretty = datetime.strptime(d, "%d-%m-%Y").strftime("%A %d %B %Y")
        head = (
            f"<h2>{html.escape(d)} <span class='small'>({html.escape(pretty)}) — "
            f"{rep.teams} thuiswedstrijden, {rep.scheduled_parts}/{rep.total_parts} partijen gepland, "
            f"status {html.escape(data.get('status','?'))}</span></h2>"
        )
        sections.append(head + render_violations(rep) + render_summary(rows) + render_grid(rows))

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
</style>
</head>
<body>
<h1>Mierlose T.V. — baanschema zondagen 2026-2027</h1>
<p class='small'>Alleen de thuiswedstrijden van Mierlo op zondagen, gepland per zondag met de OR-Tools CP-SAT solver.
Kolommen = banen (1–10), rijen = kwartierblokken. Tik op een cel voor detail.
Zie ook de <a href='./index.html'>2025-2026 pagina</a> en
<a href='./MIERLO_2026_2027_PLANNING.md'>de toelichting</a>.</p>
{''.join(sections)}
<div id='bg' style='position:fixed;inset:0;background:rgba(0,0,0,.45);display:none;align-items:center;justify-content:center;z-index:20' onclick='this.style.display="none"'>
  <div style='background:#fff;border-radius:12px;max-width:92vw;padding:.9rem 1rem' onclick='event.stopPropagation()'>
    <strong>Wedstrijddetail</strong><div id='mt' style='margin-top:.4rem;white-space:pre-wrap'></div>
    <div style='margin-top:.7rem'><button onclick="document.getElementById('bg').style.display='none'">Sluiten</button></div>
  </div>
</div>
<script>
document.querySelectorAll('.tap-cell').forEach(function(el){{
  el.addEventListener('click', function(){{
    document.getElementById('mt').textContent = el.getAttribute('data-detail');
    document.getElementById('bg').style.display = 'flex';
  }});
}});
</script>
</body>
</html>
"""
    args.out.write_text(page, encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
