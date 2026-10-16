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
// SD2: werkelijk verloop.
function dsStart(state, r, court, now = new Date(), lineup = "", rows = null) {
  const clash = rows ? dsNameClash(state, rows, r, lineup) : [];
  if (clash.length) throw new Error(`Kan ${dsName(r)} niet starten: ${clash.join("; ")}.`);
  return _dsDo(state, (s) => { s.parts[dsPid(r)] = { status: "bezig", start: now.toISOString(), court: court || r.court, ...(lineup ? { lineup } : {}) }; },
    `Baan ${court || r.court}: ${dsName(r)} gestart${court && court !== r.court ? ` (gepland op baan ${r.court})` : ""}`, now);
}
function dsFinish(state, r, now = new Date()) {
  const p = state.parts[dsPid(r)];
  if (!p || p.status !== "bezig") throw new Error(`${dsName(r)} is niet bezig.`);
  return _dsDo(state, (s) => { s.parts[dsPid(r)] = { ...p, status: "klaar", end: now.toISOString() }; }, `Baan ${p.court}: ${dsName(r)} klaar`, now);
}
const DS_TEAM_NL = { aanwezig: "aanwezig", te_laat: "te laat", staakt: "staakt", doorgaan: "gaat door", later: "start later" };
function dsTeam(state, teamId, label, status, extra = {}, now = new Date()) {
  return _dsDo(state, (s) => { if (status) s.teams[teamId] = { ...extra, status, at: now.toISOString() }; else delete s.teams[teamId]; },
    `${label}: ${status ? DS_TEAM_NL[status] + (extra.time ? ` (${extra.time})` : "") : "status gewist"}`, now);
}
// Opstelling (namen) bekend? Dan mag een speler niet tegelijk in twee lopende partijen staan (besluit Oscar 16-10-2026).
function dsNames(lineup) { return String(lineup || "").split(/[,+–\-\/&]| en /i).map((x) => x.trim().toLowerCase()).filter((x) => x.length > 1); }
function dsNameClash(state, rows, r, lineup) {
  const mine = new Set(dsNames(lineup));
  if (!mine.size) return [];
  const out = [];
  for (const o of rows) {
    if (o.team_id !== r.team_id || dsPid(o) === dsPid(r)) continue;
    const p = state.parts[dsPid(o)];
    if (!p || p.status !== "bezig") continue;
    for (const n of dsNames(p.lineup)) if (mine.has(n)) out.push(`${n} speelt nog ${o.part}`);
  }
  return out;
}
// SD3: baan buiten gebruik vanaf tijd X (optioneel tot Y). Niets schuift vanzelf (dat doet herplannen, SD5).
function dsOffAdd(state, courts, from, to, why, now = new Date()) {
  return _dsDo(state, (s) => { for (const c of courts) s.off.push({ court: c, from, to: to || "", why: why || "" }); },
    `Baan ${courts.join(", ")} buiten gebruik vanaf ${from}${to ? ` tot ${to}` : ""}${why ? ` (${why})` : ""}`, now);
}
function dsOffRemove(state, idx, now = new Date()) {
  const o = state.off[idx];
  return _dsDo(state, (s) => { s.off.splice(idx, 1); }, `Baan ${o.court} weer in gebruik`, now);
}
// Geraakt: geplande (nog niet begonnen) partij overlapt een buiten-gebruik-periode op zijn baan.
function dsHit(r, state) {
  const a = dsMin(r.start), b = dsMin(r.end);
  return (state.off || []).some((o) => o.court === r.court && a < (o.to ? dsMin(o.to) : 24 * 60) && b > dsMin(o.from));
}
// SD4: doorschuiven op één baan. Geplande (niet begonnen) partijen op `court` die op/na `fromMin` beginnen,
// schuiven `delta` minuten op (volgorde blijft). Geeft nieuwe rijen; het origineel blijft onaangeroerd.
function dsShiftCourt(rows, state, court, fromMin, delta, now) {
  return rows.map((r) => {
    if (r.court !== court || dsMin(r.start) < fromMin || dsStatus(r, state, now).status !== "gepland" || !r.start) return r;
    return { ...r, start: dsHM(dsMin(r.start) + delta), end: dsHM(dsMin(r.end) + delta) };
  });
}
// Verwachte vertraging per volgende partij op die baan door uitloop van de lopende partij.
function dsExpectedDelay(rows, state, court, nowDate) {
  const now = dsClock(nowDate);
  const cur = rows.find((r) => { const s = dsStatus(r, state, now); return s.status === "bezig" && s.court === court; });
  const next = rows.find((r) => r.court === court && dsStatus(r, state, now).status === "gepland");
  if (!cur || !next) return 0;
  const p = state.parts[dsPid(cur)];
  const expEnd = Math.max(dsClock(new Date(p.start)) + (dsMin(cur.end) - dsMin(cur.start)), now);
  return Math.max(0, expEnd - dsMin(next.start));
}
// Verschil oud ↔ nieuw (per partij): verplaatst, nieuw onplanbaar.
function dsDiff(oldRows, newRows) {
  const o = new Map(oldRows.filter((r) => r.kind !== "W").map((r) => [dsPid(r), r]));
  const out = [];
  for (const n of newRows) {
    if (n.kind === "W") continue;
    const a = o.get(dsPid(n));
    const placed = n.court && n.start && n.start !== "NIET_GELUKT";
    const was = a && a.court && a.start !== "NIET_GELUKT";
    if (!a) continue;
    if (!placed && was) out.push({ pid: dsPid(n), row: n, old: { start: a.start, court: a.court }, new: null });
    else if (placed && (!was || a.start !== n.start || a.court !== n.court)) out.push({ pid: dsPid(n), row: n, old: was ? { start: a.start, court: a.court } : null, new: { start: n.start, court: n.court } });
  }
  // Weggevallen partijen (team staakt): staan niet meer in het nieuwe schema.
  const seen = new Set(newRows.map(dsPid));
  for (const [pid, a] of o) if (!seen.has(pid) && a.court && a.start !== "NIET_GELUKT") out.push({ pid, row: a, old: { start: a.start, court: a.court }, new: null, gone: true });
  return out.sort((x, y) => dsMin((x.new || x.old).start) - dsMin((y.new || y.old).start));
}
// "gewijzigd"-markering: oorspronkelijke tijd/baan per partij blijft bewaard over meerdere wijzigingen.
function dsChanged(prevChanged, diff) {
  const ch = { ...(prevChanged || {}) };
  for (const d of diff) {
    if (!ch[d.pid] && d.old) ch[d.pid] = { start: d.old.start, court: d.old.court, name: `${d.row.label} ${d.row.home_team} ${d.row.part}`, team: `${d.row.label} ${d.row.home_team}` };
    if (ch[d.pid] && d.gone) ch[d.pid].gone = true;
  }
  return ch;
}
const dsName = (r) => `${r.label} ${r.home_team} ${r.part}`;

if (typeof module !== "undefined") module.exports = { dsPid, dsMin, dsHM, dsClock, dsEmpty, dsNorm, dsRows, dsStatus, dsCourts, dsOverrun, dsUndo, _dsDo, dsName, dsStart, dsFinish, dsTeam, dsOffAdd, dsOffRemove, dsHit, dsNames, dsNameClash, dsShiftCourt, dsExpectedDelay, dsDiff, dsChanged };
