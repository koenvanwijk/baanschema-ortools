"use strict";
// Bingo-avond: pure toestandslogica (geen DOM), ook in Node getest (tests/web/test_bingo_core.js).
// Toestand: {present:{matchKey: ISO-tijd aanmelden (oud: true)}, courts:{"1":{part, lineup, start}}, done:{partId:{court,start,end,lineup}}, log:[{t,msg}], undo:[...]}
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
  for (const m of matches) for (const p of m.parts) if (p.id === partId) return `${p.label}${p.type && p.type !== p.label ? ` ${p.type}` : ""} · ${m.label} ${m.home} – ${m.away}`;
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

// ---------- Teambezetting (hard, dezelfde regels als planner/herplannen; besluit Oscar 16/17-10-2026) ----------
// Per partij levert de server type (HE/DE/HD/DD/GD), men/women/players (src/baanschemaatje/teamrules.py);
// per wedstrijd rules {mixed, singles_first, doubles_before_mixed}. Regels:
//  - max 4 spelers van een team tegelijk; gemengd max 2 heren + 2 dames (dus DD en GD van één team niet tegelijk);
//  - niet-gemengd (en 8p strikt): enkels klaar vóór een dubbel start; 8p ook dubbels vóór gemengd dubbel.
// Geen max-banen/aangrenzend-regel en geen rustregel (besluit Oscar 14-10-2026).
const bgType = (p) => p.type || p.label;
const _bgDem = (p) => ({ men: p.men || 0, women: p.women || 0, players: p.players != null ? p.players : (p.kind === "S" ? 1 : p.kind === "D" || p.kind === "M" ? 2 : 0) });

function bgMatchOf(matches, partId) { return matches.find((m) => m.parts.some((p) => p.id === partId)) || null; }

// Lopende partijen van een team: [{court, part}]
function bgRunningOf(state, match) {
  const out = [];
  for (const [c, cur] of Object.entries(state.courts)) {
    const p = match.parts.find((x) => x.id === cur.part);
    if (p) out.push({ court: +c, part: p });
  }
  return out;
}

// Reden waarom deze partij nu niet kan (teamregels), of null. running: [{court, part}] van hetzelfde team.
function bgTeamBlock(state, match, part, running) {
  running = running || bgRunningOf(state, match);
  const r = match.rules || {};
  const open = (k) => match.parts.filter((p) => p.kind === k && !state.done[p.id] && p.id !== part.id);
  if (r.singles_first && part.kind !== "S") {
    const s = open("S");
    if (s.length) return `eerst de enkels klaar (${s.map(bgType).join(", ")})`;
  }
  if (r.doubles_before_mixed && part.kind === "M") {
    const d = open("D");
    if (d.length) return `eerst de dubbels klaar (${d.map(bgType).join(", ")})`;
  }
  const me = _bgDem(part);
  const where = (xs) => xs.map((x) => `${bgType(x.part)} op baan ${x.court}`).join(", ");
  const tot = running.reduce((a, x) => a + _bgDem(x.part).players, 0) + me.players;
  if (r.mixed) {
    const w = running.filter((x) => _bgDem(x.part).women), m = running.filter((x) => _bgDem(x.part).men);
    if (me.women && w.reduce((a, x) => a + _bgDem(x.part).women, 0) + me.women > 2) return `de dames spelen nog (${where(w)})`;
    if (me.men && m.reduce((a, x) => a + _bgDem(x.part).men, 0) + me.men > 2) return `de heren spelen nog (${where(m)})`;
  }
  if (running.length && tot > 4) return `spelers nog bezig (${where(running)}; team heeft 4 spelers)`;
  return null;
}

// Reden waarom er nu niets meer mag starten (tijd), of null.
function bgTimeBlock(window, duration, now) {
  if (!window) return null;
  const t = bgEveningMin(now);
  if (window.last_start && t > bgMin(window.last_start)) return `na de laatste start (${window.last_start})`;
  if (window.end && duration && t + duration > bgMin(window.end)) return `eindigt na sluiting (${bgHM(bgMin(window.end))})`;
  return null;
}

// Voortgang per team: {total, done, running, left}
function bgProgress(state, match) {
  const total = match.parts.length;
  const done = match.parts.filter((p) => state.done[p.id]).length;
  const running = bgRunningOf(state, match).length;
  return { total, done, running, left: total - done - running };
}

// Wacht sinds: laatste "klaar" van het team, anders het aanmelden (ISO), anders null.
function bgWaitingSince(state, match) {
  let t = typeof state.present[match.key] === "string" ? state.present[match.key] : null;
  for (const p of match.parts) { const d = state.done[p.id]; if (d && d.end && (!t || d.end > t)) t = d.end; }
  return t;
}

// Wachtrij met volgorde en redenen. Elke regel: {...part, match, ok, blocked, why}.
// Volgorde (besluit Oscar 17-10-2026, uitlegbaar):
//  1. eerst wat nu kan (team aanwezig, geen spelersconflict/volgorderegel, nog op tijd);
//  2. team met de minste partijen op de baan (wie nu staat te wachten);
//  3. team met de meeste partijen nog te gaan (wie het verst achterligt, bepaalt hoe laat de avond eindigt);
//  4. wie het langst wacht (sinds aanmelden of laatste partij klaar);
//  5. vroegste exporttijd, daarna KNLTB-volgorde binnen het team (enkels, dubbels, gemengd).
// De lijst is "als je ze van boven af start": na elke keuze telt die partij als bezig, zodat bv. DD + HD van een
// gemengd team samen bovenaan komen en de GD's daarna (die botsen met de DD/HD erboven).
function bgRanked(state, matches, window, now = new Date()) {
  const items = bgQueue(state, matches);
  const virt = new Map(), picked = new Map();
  for (const m of matches) if (state.present[m.key]) { virt.set(m.key, bgRunningOf(state, m)); picked.set(m.key, 0); }
  const order = new Map(); matches.forEach((m, i) => m.parts.forEach((p, j) => order.set(p.id, i * 100 + j)));
  const keyOf = (it) => {
    const pr = bgProgress(state, it.match), run = virt.get(it.match.key).length, left = pr.left - picked.get(it.match.key);
    const ws = bgWaitingSince(state, it.match);
    return { run, left, ws: ws ? Date.parse(ws) : 0, exp: it.match.export_start || "99:99", ord: order.get(it.id) };
  };
  const cmp = (a, b) => a.k.run - b.k.run || b.k.left - a.k.left || a.k.ws - b.k.ws || (a.k.exp < b.k.exp ? -1 : a.k.exp > b.k.exp ? 1 : 0) || a.k.ord - b.k.ord;
  const hm = (ms) => { const d = new Date(ms); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const whyOf = (k) => [k.run ? `team heeft ${k.run} op de baan` : "team staat nog niet op de baan", `nog ${k.left} te gaan`, k.ws ? `wacht sinds ${hm(k.ws)}` : ""].filter(Boolean).join(" · ");
  const out = [];
  let rest = items.slice();
  for (;;) {
    const cand = rest.filter((it) => !bgTimeBlock(window, it.match.duration, now) && !bgTeamBlock(state, it.match, it, virt.get(it.match.key)))
      .map((it) => ({ it, k: keyOf(it) })).sort(cmp);
    if (!cand.length) break;
    const { it, k } = cand[0];
    out.push({ ...it, ok: true, blocked: null, why: whyOf(k) });
    virt.get(it.match.key).push({ court: 0, part: it });
    picked.set(it.match.key, picked.get(it.match.key) + 1);
    rest = rest.filter((x) => x.id !== it.id);
  }
  // Wat overblijft: kan ook nu (botst alleen met een partij hierboven) of is echt geblokkeerd (met reden).
  const later = [], blocked = [];
  for (const it of rest) {
    const real = bgTimeBlock(window, it.match.duration, now) || bgTeamBlock(state, it.match, it);
    const k = keyOf(it);
    if (real) blocked.push({ it: { ...it, ok: false, blocked: real, why: "" }, k });
    else {
      const above = out.filter((x) => x.match.key === it.match.key).map(bgType);
      later.push({ it: { ...it, ok: true, blocked: null, why: `kan ook nu, maar zelfde spelers als ${above.join(" / ") || "hierboven"} hierboven` }, k });
    }
  }
  return [...out, ...later.sort(cmp).map((x) => x.it), ...blocked.sort(cmp).map((x) => x.it)];
}

// Voorstel "Volgende op baan X": laagste vrije baan + bovenste partij die nu kan (zie bgRanked). {court, part, match, label, type, why} of null.
function bgSuggest(state, matches, window, now = new Date()) {
  const n = (window && window.courts) || 0;
  const court = bgFreeCourts(state, n)[0];
  if (!court) return null;
  const top = bgRanked(state, matches, window, now)[0];
  if (!top || !top.ok) return null;
  return { court, part: top.id, match: top.match, label: top.label, type: bgType(top), why: top.why };
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
  return _bgDo(state, (s) => { if (on) s.present[match.key] = now.toISOString(); else delete s.present[match.key]; },
    `${match.label} ${match.home} ${on ? "aanwezig" : "niet meer aanwezig"}`, now);
}

// Opstelling bekend: een speler kan niet tegelijk in twee partijen van hetzelfde team (besluit Oscar 16-10-2026).
const bgNames = (l) => String(l || "").split(/[,+–\-\/&]| en /i).map((x) => x.trim().toLowerCase()).filter((x) => x.length > 1);
function bgAssign(state, matches, partId, court, lineup, now = new Date(), force = false) {
  if (state.courts[String(court)]) throw new Error(`Baan ${court} is bezet.`);
  const m = matches.find((x) => x.parts.some((p) => p.id === partId));
  const rule = m ? bgTeamBlock(state, m, m.parts.find((p) => p.id === partId)) : null;
  if (rule && !force) { const e = new Error(`Kan nog niet: ${rule}.`); e.rule = rule; throw e; }
  const mine = new Set(bgNames(lineup));
  if (m && mine.size) {
    for (const [c, cur] of Object.entries(state.courts)) {
      if (!m.parts.some((p) => p.id === cur.part)) continue;
      const hit = bgNames(cur.lineup).filter((n) => mine.has(n));
      if (hit.length) throw new Error(`${hit.join(", ")} speelt nog op baan ${c}.`);
    }
  }
  return _bgDo(state, (s) => { s.courts[String(court)] = { part: partId, lineup: lineup || "", start: now.toISOString() }; },
    `Baan ${court}: ${bgPartName(matches, partId)} gestart${lineup ? ` (${lineup})` : ""}${rule ? ` — toch gestart, regel: ${rule}` : ""}`, now);
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

if (typeof module !== "undefined") module.exports = { bgEmpty, bgNorm, bgQueue, bgFreeCourts, bgWarnings, bgSetPresent, bgAssign, bgFinish, bgUndo, bgSuggest, bgEveningMin, bgHM,
  bgRanked, bgTeamBlock, bgTimeBlock, bgProgress, bgRunningOf, bgWaitingSince, bgMatchOf, bgType };
