"use strict";
// Bingo-avond: printbare lijst (A4, lege vakjes baan/tijd) en verslag achteraf uit het logboek.
// URL: bingo-print.html#<club>/<dd-mm-jjjj>[/verslag]
let BP = null;
const bpNorm = typeof bgNorm !== "undefined" ? bgNorm : require("./bingo-core.js").bgNorm;
const bpHM = (iso) => (iso ? new Date(iso).toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" }) : "");

// Verslagregels (pure functie, ook in Node getest): per gespeelde partij baan/start/eind/duur/opstelling, op starttijd.
function bpReport(state, matches) {
  const s = bpNorm(state), out = [];
  for (const m of matches) for (const p of m.parts) {
    const d = s.done[p.id];
    if (d) out.push({ match: m, part: p, court: d.court, start: d.start, end: d.end, lineup: d.lineup || "", min: Math.round((new Date(d.end) - new Date(d.start)) / 60000) });
  }
  out.sort((a, b) => new Date(a.start) - new Date(b.start) || a.court - b.court);
  const open = [];
  for (const m of matches) for (const p of m.parts) if (!s.done[p.id]) open.push({ match: m, part: p, playing: Object.entries(s.courts).find(([, c]) => c.part === p.id) });
  return { played: out, open };
}

function bpRender() {
  const kind = document.querySelector('input[name="bp"]:checked').value;
  const j = BP, w = j.window || {};
  const head = `<h1>${esc(j.name)} · bingo-avond ${esc(j.date)}</h1>
    <p class="sub">${w.start ? `Avond ${esc(w.start)}–${esc(clockShort(w.end))} · laatste start ${esc(w.last_start)} · ${w.courts} banen` : ""}</p>`;
  if (kind === "lijst") {
    $("bp-body").innerHTML = `${head}<h2>Bingolijst</h2>
      <table class="bp"><thead><tr><th>Team</th><th>Partij</th><th class="w-lineup">Opstelling</th><th>Baan</th><th>Start</th><th>Klaar</th></tr></thead><tbody>
      ${j.matches.map((m) => m.parts.map((p, i) => `<tr class="${i === 0 ? "first" : ""}">${i === 0 ? `<td rowspan="${m.parts.length}" class="team"><b>${esc(m.label)} ${esc(m.home)}</b><br>– ${esc(m.away)}${m.moved_from ? `<br><small>verzet van ${esc(m.moved_from)}</small>` : ""}<br><span class="box"></span> aanwezig</td>` : ""}
        <td>${esc(p.label)}${p.type && p.type !== p.label ? ` ${esc(p.type)}` : ""}</td><td></td><td class="box-c"></td><td class="box-c"></td><td class="box-c"></td></tr>`).join("")).join("")
        || '<tr><td colspan="6">Geen wedstrijden op deze avond.</td></tr>'}</tbody></table>`;
  } else {
    const r = bpReport(j.state, j.matches);
    const log = (bgNorm(j.state).log || []);
    $("bp-body").innerHTML = `${head}<h2>Verslag</h2>
      <p>${r.played.length} partijen gespeeld${r.open.length ? `, ${r.open.length} niet (afgerond)` : ""}.</p>
      <table class="bp"><thead><tr><th>Start</th><th>Eind</th><th>Duur</th><th>Baan</th><th>Team</th><th>Partij</th><th>Opstelling</th></tr></thead><tbody>
      ${r.played.map((x) => `<tr><td>${bpHM(x.start)}</td><td>${bpHM(x.end)}</td><td>${x.min} min</td><td>${x.court}</td><td>${esc(x.match.label)} ${esc(x.match.home)} – ${esc(x.match.away)}</td><td>${esc(x.part.label)}${x.part.type && x.part.type !== x.part.label ? ` ${esc(x.part.type)}` : ""}</td><td>${esc(x.lineup)}</td></tr>`).join("")
        || '<tr><td colspan="7">Nog geen partijen afgerond.</td></tr>'}</tbody></table>
      ${r.open.length ? `<h3>Niet afgerond</h3><ul>${r.open.map((x) => `<li>${esc(x.part.label)} ${esc(x.match.label)} ${esc(x.match.home)}${x.playing ? ` (nog op baan ${x.playing[0]})` : ""}</li>`).join("")}</ul>` : ""}
      <h3>Logboek</h3><ol class="bp-log">${log.map((l) => `<li><b>${bpHM(l.t)}</b> ${esc(l.msg)}</li>`).join("") || "<li>Leeg</li>"}</ol>`;
  }
}

async function bpLoad() {
  const [club, date, kind] = decodeURIComponent(location.hash.slice(1)).split("/");
  document.querySelector(`input[value="${kind === "verslag" ? "verslag" : "lijst"}"]`).checked = true;
  $("bp-back").href = `bingo.html${location.search}#${encodeURIComponent(club)}/${encodeURIComponent(date)}`;
  const r = await fetch(`${API}${withShare(`/clubs/${encodeURIComponent(club)}/bingo/${encodeURIComponent(date)}`)}`, { credentials: "include" });
  if (!r.ok) { $("bp-body").textContent = `Kon de avond niet laden (${r.status}).`; return; }
  BP = await r.json();
  bpRender();
}

if (typeof document !== "undefined") {
  for (const i of document.querySelectorAll('input[name="bp"]')) i.onchange = () => BP && bpRender();
  window.addEventListener("hashchange", bpLoad);
  bpLoad();
}
if (typeof module !== "undefined") module.exports = { bpReport };
