"use strict";
// Speeldag-dashboard: pure logica (geen DOM), ook in Node getest (tests/web/test_dash_core.js).
// Toestand (zelfde opzet als bingo): {parts:{pid:{status:"bezig"|"klaar", start, end, court}},
//   teams:{team_id:{status:"aanwezig"|"te_laat"|"staakt"|"doorgaan"|"later", at}}, off:[{court, from, to}], log:[], undo:[]}
const DS_UNDO_MAX = 25;
const dsPid = (r) => `${r.team_id}|${r.part}`;
const dsMin = (hhmm) => parseInt(hhmm.slice(0, 2), 10) * 60 + parseInt(hhmm.slice(3, 5), 10);
const dsHM = (m) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(((m % 60) + 60) % 60).padStart(2, "0")}`;
const dsClock = (d) => d.getHours() * 60 + d.getMinutes();

function dsEmpty() { return { parts: {}, teams: {}, off: [], log: [], undo: [] }; }
function dsNorm(s) {
  s = s && typeof s === "object" ? s : {};
  const e = dsEmpty();
  return { ...s, parts: s.parts || e.parts, teams: s.teams || e.teams, off: s.off || e.off, log: s.log || e.log, undo: s.undo || e.undo };
}

// Ingeplande partijen (geen blokken zonder partij), op tijd en baan.
function dsRows(plan) {
  return ((plan && plan.rows) || []).filter((r) => r.court && r.start && r.start !== "NIET_GELUKT" && r.kind !== "W")
    .sort((a, b) => dsMin(a.start) - dsMin(b.start) || a.court - b.court);
}

// Status van een partij: klaar / bezig (getikt) / gestaakt (team staakt, nog niet begonnen) / gepland.
// `late`: had volgens schema al moeten beginnen (5 min speling).
function dsStatus(r, state, now) {
  const p = state.parts[dsPid(r)];
  if (p && p.status === "klaar") return { status: "klaar" };
  if (p && p.status === "bezig") return { status: "bezig", court: p.court || r.court, since: p.start };
  const t = state.teams[r.team_id];
  if (t && t.status === "staakt") return { status: "gestaakt" };
  return { status: "gepland", late: now > dsMin(r.start) + 5 };
}

// Per baan: wat speelt er nu (getikt) en wat is de volgende geplande partij.
function dsCourts(rows, state, now, n) {
  const out = [];
  for (let c = 1; c <= n; c++) {
    const cur = rows.find((r) => { const s = dsStatus(r, state, now); return s.status === "bezig" && s.court === c; }) || null;
    const next = rows.find((r) => r.court === c && dsStatus(r, state, now).status === "gepland") || null;
    const off = (state.off || []).find((o) => o.court === c && now >= dsMin(o.from) && (!o.to || now < dsMin(o.to))) || null;
    out.push({ court: c, cur, next, off });
  }
  return out;
}

// Uitloop van een lopende partij: minuten over de normduur (0 = op schema).
function dsOverrun(r, state, nowDate) {
  const p = state.parts[dsPid(r)];
  if (!p || p.status !== "bezig" || !p.start) return 0;
  const dur = dsMin(r.end) - dsMin(r.start);
  const el = Math.floor((nowDate - new Date(p.start)) / 60000);
  return Math.max(0, el - dur);
}

function _dsSnap(s) { const { undo, ...rest } = s; return JSON.parse(JSON.stringify(rest)); }
function _dsDo(state, fn, msg, now) {
  const s = JSON.parse(JSON.stringify(state));
  s.undo = [...(state.undo || []), _dsSnap(state)].slice(-DS_UNDO_MAX);
  fn(s);
  s.log = [...s.log, { t: now.toISOString(), msg }];
  return s;
}
function dsUndo(state, now = new Date()) {
  const u = state.undo || [];
  if (!u.length) return state;
  const prev = u[u.length - 1];
  const last = (state.log[state.log.length - 1] || {}).msg || "";
  return { ...prev, undo: u.slice(0, -1), log: [...prev.log, { t: now.toISOString(), msg: `Ongedaan: ${last}` }] };
}
const dsName = (r) => `${r.label} ${r.home_team} ${r.part}`;

if (typeof module !== "undefined") module.exports = { dsPid, dsMin, dsHM, dsClock, dsEmpty, dsNorm, dsRows, dsStatus, dsCourts, dsOverrun, dsUndo, _dsDo, dsName };
