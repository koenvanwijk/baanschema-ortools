"use strict";
// Bingo-avond: pure toestandslogica (geen DOM), ook in Node getest (tests/web/test_bingo_core.js).
// Toestand: {present:{matchKey:true}, courts:{"1":{part, lineup, start}}, done:{partId:{court,start,end,lineup}}, log:[{t,msg}], undo:[...]}
// Geen rustregel en geen max-banen/aangrenzend-regel (besluit Oscar 14-10-2026): de commissaris beslist.

const BG_UNDO_MAX = 25;

function bgEmpty() { return { present: {}, courts: {}, done: {}, log: [], undo: [] }; }

function bgNorm(s) {
  const e = bgEmpty();
  s = s && typeof s === "object" ? s : {};
  return { present: s.present || e.present, courts: s.courts || e.courts, done: s.done || e.done, log: s.log || e.log, undo: s.undo || e.undo };
}

// Minuten sinds 00:00 van de avond; tijden vóór 12:00 tellen als na middernacht (+24 h).
function bgEveningMin(date) { const m = date.getHours() * 60 + date.getMinutes(); return m < 12 * 60 ? m + 1440 : m; }
const bgHM = (m) => `${String(Math.floor((m % 1440) / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const bgMin = (hhmm) => parseInt(hhmm.slice(0, 2), 10) * 60 + parseInt(hhmm.slice(3, 5), 10);

// Wachtrij: partijen van aanwezige teams die nog niet speelden en niet op een baan staan.
function bgQueue(state, matches) {
  const busy = new Set(Object.values(state.courts).map((c) => c.part));
  const out = [];
  for (const m of matches) {
    if (!state.present[m.key]) continue;
    for (const p of m.parts) if (!state.done[p.id] && !busy.has(p.id)) out.push({ ...p, match: m });
  }
  return out;
}

function bgFreeCourts(state, n) {
  const out = [];
  for (let c = 1; c <= n; c++) if (!state.courts[String(c)]) out.push(c);
  return out;
}

function bgPartName(matches, partId) {
  for (const m of matches) for (const p of m.parts) if (p.id === partId) return `${p.label} · ${m.label} ${m.home} – ${m.away}`;
  return partId;
}

// Waarschuwingen bij starten: na laatste start / eindigt na sluiting.
function bgWarnings(window, duration, now) {
  if (!window) return [];
  const t = bgEveningMin(now), w = [];
  const last = bgMin(window.last_start), end = bgMin(window.end);
  if (t > last) w.push(`Na de laatste start (${bgHM(last)}).`);
  if (duration && t + duration > end) w.push(`Eindigt rond ${bgHM(t + duration)}, na sluiting (${bgHM(end)}).`);
  return w;
}

// Voorstel "Volgende op baan X" (besluit Oscar 14-10-2026, simpel): laagste vrije baan; partij van een aanwezig team,
// per team in KNLTB-volgorde (singles vóór dubbels, zoals de export: S, D, GD); voorrang aan het team met de minste
// partijen nu op de baan, daarna wie het eerst in de lijst staat. Alleen als de partij nog mag starten (≤ laatste start)
// en vóór sluiting klaar is. Geen rust-/max-banen-regel. Geeft {court, part, match} of null.
function bgSuggest(state, matches, window, now = new Date()) {
  const n = (window && window.courts) || 0;
  const court = bgFreeCourts(state, n)[0];
  if (!court) return null;
  if (window && window.last_start && bgEveningMin(now) > bgMin(window.last_start)) return null;
  const playing = {};
  for (const c of Object.values(state.courts)) for (const m of matches) if (m.parts.some((p) => p.id === c.part)) playing[m.key] = (playing[m.key] || 0) + 1;
  const q = bgQueue(state, matches).filter((p) => !(window && window.end && p.match.duration && bgEveningMin(now) + p.match.duration > bgMin(window.end)));
  if (!q.length) return null;
  const firstOf = new Map();
  for (const p of q) if (!firstOf.has(p.match.key)) firstOf.set(p.match.key, p);
  const pick = [...firstOf.values()].sort((a, b) => (playing[a.match.key] || 0) - (playing[b.match.key] || 0))[0];
  return { court, part: pick.id, match: pick.match, label: pick.label };
}

function _bgSnap(state) { const { undo, ...rest } = state; return JSON.parse(JSON.stringify(rest)); }
function _bgDo(state, fn, msg, now) {
  const s = JSON.parse(JSON.stringify(state));
  s.undo = [...(state.undo || []), _bgSnap(state)].slice(-BG_UNDO_MAX);
  fn(s);
  s.log = [...s.log, { t: now.toISOString(), msg }];
  return s;
}

function bgSetPresent(state, match, on, now = new Date()) {
  return _bgDo(state, (s) => { if (on) s.present[match.key] = true; else delete s.present[match.key]; },
    `${match.label} ${match.home} ${on ? "aanwezig" : "niet meer aanwezig"}`, now);
}

function bgAssign(state, matches, partId, court, lineup, now = new Date()) {
  if (state.courts[String(court)]) throw new Error(`Baan ${court} is bezet.`);
  return _bgDo(state, (s) => { s.courts[String(court)] = { part: partId, lineup: lineup || "", start: now.toISOString() }; },
    `Baan ${court}: ${bgPartName(matches, partId)} gestart${lineup ? ` (${lineup})` : ""}`, now);
}

function bgFinish(state, matches, court, now = new Date()) {
  const c = state.courts[String(court)];
  if (!c) throw new Error(`Baan ${court} is vrij.`);
  return _bgDo(state, (s) => { s.done[c.part] = { court, start: c.start, end: now.toISOString(), lineup: c.lineup }; delete s.courts[String(court)]; },
    `Baan ${court}: ${bgPartName(matches, c.part)} klaar`, now);
}

function bgUndo(state, now = new Date()) {
  const u = state.undo || [];
  if (!u.length) return state;
  const prev = u[u.length - 1];
  const lastMsg = (state.log[state.log.length - 1] || {}).msg || "";
  return { ...prev, undo: u.slice(0, -1), log: [...prev.log, { t: now.toISOString(), msg: `Ongedaan: ${lastMsg}` }] };
}

if (typeof module !== "undefined") module.exports = { bgEmpty, bgNorm, bgQueue, bgFreeCourts, bgWarnings, bgSetPresent, bgAssign, bgFinish, bgUndo, bgSuggest, bgEveningMin, bgHM };
