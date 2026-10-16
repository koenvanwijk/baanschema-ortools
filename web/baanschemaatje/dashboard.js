"use strict";
// Speeldag-dashboard: dashboard.html#<club>/<dd-mm-jjjj>. Leest het definitieve schema + verloop; ververst elke 5 s.
let DS = null;           // {club, date, name, window, plan, mode}
let ST = dsEmpty();
let GEN = 0;
let BUSY = false;
const DS_POLL = 5000;

function dsParse() {
  const [club, date] = decodeURIComponent(location.hash.slice(1)).split("/");
  const t = new Date();
  const today = `${String(t.getDate()).padStart(2, "0")}-${String(t.getMonth() + 1).padStart(2, "0")}-${t.getFullYear()}`;
  return { club: club || "mierlo", date: date || today };
}
function say(msg, cls = "") { const el = $("ds-status"); el.textContent = msg; el.className = `bg-status ${cls}`; }
async function dsFetch(path, opts) {
  const r = await fetch(`${API}${path}`, opts);
  let b = null; try { b = await r.json(); } catch (_) { /* leeg */ }
  return { ok: r.ok, status: r.status, body: b };
}
function nowMin() { return dsClock(new Date()); }

async function load(quiet = false) {
  const { club, date } = dsParse();
  const r = await dsFetch(`/clubs/${encodeURIComponent(club)}/dayrun/${encodeURIComponent(date)}`);
  if (!r.ok) { say(`Kon de speeldag niet laden: ${(r.body && r.body.detail) || r.status}`, "bad"); return; }
  const j = r.body;
  DS = { club, date, name: j.name, window: j.window, mode: j.mode, plan: j.schedule && j.schedule.plan, saved: j.schedule };
  if (j.gen !== GEN || !quiet) { ST = dsNorm(j.state); GEN = j.gen; }
  render();
}

function chip(s) {
  if (s.status === "gepland" && s.late) return '<span class="ds-chip late">gepland · nog niet gestart</span>';
  return `<span class="ds-chip ${s.status}">${s.status}</span>`;
}

function render() {
  if (!DS) return;
  const w = DS.window || {}, n = w.courts || 0, now = nowMin();
  const q = location.search, h = `${encodeURIComponent(DS.club)}/${encodeURIComponent(DS.date)}`;
  $("ds-title").textContent = `Speeldag ${DS.date}`;
  $("ds-sub").textContent = `${DS.name} · dashboard`;
  $("ds-back").href = `club.html${q}#${encodeURIComponent(DS.club)}`;
  $("ds-tv").href = `tv.html${q}#${h}`;
  $("ds-dag").href = `dag.html${q}#${h}`;
  $("ds-clock").textContent = new Date().toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
  $("ds-window").textContent = w.start ? `Dag ${w.start}–${clockShort(w.end)} · laatste start ${w.last_start} · ${n} banen` : "";
  if (DS.mode === "bingo") { $("ds-list").innerHTML = `<p class="banner">Dit is een bingo-avond: gebruik het <a href="bingo.html${q}#${h}">commissarisscherm</a>.</p>`; $("ds-courts").innerHTML = ""; return; }
  if (!DS.plan) { $("ds-list").innerHTML = '<p class="banner">Voor deze dag is nog geen definitief schema opgeslagen. Bereken en sla het op via de clubpagina.</p>'; $("ds-courts").innerHTML = ""; return; }
  const rows = dsRows(DS.plan);
  const changed = DS.plan.changed || {};
  $("ds-courts").innerHTML = dsCourts(rows, ST, now, n).map((c) => courtCard(c, rows)).join("");
  const by = new Map();
  for (const r of rows) { if (!by.has(r.start)) by.set(r.start, []); by.get(r.start).push(r); }
  $("ds-list").innerHTML = [...by].map(([t, rs]) => `<div class="pl-slot${dsMin(t) <= now && now < dsMin(t) + 15 ? " now" : ""}"><div class="pl-time">${esc(clockShort(t))}</div><ul>${rs.map((r) => {
    const s = dsStatus(r, ST, now), ch = changed[dsPid(r)];
    return `<li data-pid="${esc(dsPid(r))}"><span class="pl-court">Baan ${s.court || r.court}</span> <b>${esc(r.label)} ${esc(r.home_team)}</b> ${esc(r.part)} ${chip(s)}${ch ? ` <span class="ds-chip gewijzigd" title="was ${esc(ch.start)} baan ${ch.court}">gewijzigd</span>` : ""}${rowButtons(r, s)}</li>`;
  }).join("")}</ul></div>`).join("");
  renderTeams(rows);
  $("ds-log").innerHTML = [...ST.log].reverse().map((l) => `<li><span class="hint">${new Date(l.t).toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })}</span> ${esc(l.msg)}</li>`).join("");
  bind(rows);
}

function courtCard(c) {
  if (c.off) return `<div class="bg-court off"><div class="bg-cn">Baan ${c.court}</div><div>buiten gebruik${c.off.to ? ` tot ${esc(c.off.to)}` : ""}${c.off.why ? ` · ${esc(c.off.why)}` : ""}</div></div>`;
  const nx = c.next ? `<div class="ds-next hint">Volgende: ${esc(clockShort(c.next.start))} ${esc(c.next.label)} ${esc(c.next.home_team)} ${esc(c.next.part)}</div>` : "";
  if (!c.cur) return `<div class="bg-court free"><div class="bg-cn">Baan ${c.court}</div><div class="bg-free-lbl">vrij</div>${nx}</div>`;
  const p = ST.parts[dsPid(c.cur)], over = dsOverrun(c.cur, ST, new Date());
  const el = Math.max(0, Math.floor((Date.now() - new Date(p.start)) / 60000));
  return `<div class="bg-court busy${over ? " long" : ""}"><div class="bg-cn">Baan ${c.court}</div>
    <div class="bg-what"><b>${esc(c.cur.part)}</b> ${esc(c.cur.label)} ${esc(c.cur.home_team)}</div>
    <div class="bg-time">sinds ${new Date(p.start).toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })} · <b>${el} min</b>${over ? ` · <span class="ds-over">${over} min uitloop</span>` : ""}</div>${nx}${cardButtons(c)}</div>`;
}

// SD2: tikken (start/klaar, team aanwezig/te laat), ongedaan maken, opslaan met generatie.
async function act(fn) {
  if (BUSY) return;
  let next;
  try { next = fn(ST); } catch (e) { say(e.message, "bad"); return; }
  BUSY = true;
  const prev = ST;
  ST = next; render();
  const r = await dsFetch(`/clubs/${encodeURIComponent(DS.club)}/dayrun/${encodeURIComponent(DS.date)}`, jsonOpts("PUT", { state: next, gen: GEN }));
  BUSY = false;
  if (r.ok) { GEN = r.body.gen; say(`Alles opgeslagen ✓ ${new Date().toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })}`, "ok"); render(); return; }
  if (r.status === 409 && r.body && r.body.detail) { ST = dsNorm(r.body.detail.state); GEN = r.body.detail.gen; say(r.body.detail.message, "warn"); }
  else { ST = prev; say(`Niet opgeslagen: ${(r.body && ((r.body.detail || {}).message || r.body.detail)) || r.status}`, "bad"); }
  render();
}
const ROWS = () => dsRows(DS.plan);
const rowOf = (pid) => ROWS().find((r) => dsPid(r) === pid);
function rowButtons(r, s) {
  if (s.status === "gepland") return ` <button class="btn2 ds-start" data-pid="${esc(dsPid(r))}">Start</button>`;
  if (s.status === "bezig") return ` <button class="btn2 ds-done" data-pid="${esc(dsPid(r))}">Klaar</button>`;
  return "";
}
function cardButtons(c) {
  return c.cur ? `<button class="btn bg-big ds-done" data-pid="${esc(dsPid(c.cur))}">Klaar</button>` : "";
}
function teamsOf(rows) {
  const m = new Map();
  for (const r of rows) if (!m.has(r.team_id)) m.set(r.team_id, { id: r.team_id, label: `${r.label} ${r.home_team}`, away: r.away_team, first: r.start, rows: [] });
  for (const r of rows) m.get(r.team_id).rows.push(r);
  return [...m.values()];
}
function teamButtons(t) {
  const cur = (ST.teams[t.id] || {}).status;
  return ["aanwezig", "te_laat"].map((k) => `<button class="btn2 ds-team-b${cur === k ? " on" : ""}" data-team="${esc(t.id)}" data-st="${k}">${DS_TEAM_NL[k]}</button>`).join("");
}
function renderTeams(rows) {
  $("ds-teams-sec").hidden = false;
  const now = nowMin();
  $("ds-teams").innerHTML = teamsOf(rows).map((t) => {
    const done = t.rows.filter((r) => dsStatus(r, ST, now).status === "klaar").length;
    const cur = ST.teams[t.id];
    return `<div class="ds-team"><b>${esc(t.label)}</b> – ${esc(t.away)}<br><span class="hint">aanvang ${esc(clockShort(t.first))} · ${done}/${t.rows.length} klaar${cur ? ` · ${esc(DS_TEAM_NL[cur.status])}${cur.time ? ` ${esc(cur.time)}` : ""}` : ""}</span>
      <div class="btns">${teamButtons(t)}</div></div>`;
  }).join("");
}
function bind() {
  $("ds-actions").innerHTML = `<button id="ds-undo" class="btn2 bg-big"${(ST.undo || []).length && !BUSY ? "" : " disabled"}>↶ Ongedaan maken</button>`;
  $("ds-undo").onclick = () => act((s) => dsUndo(s));
  for (const b of document.querySelectorAll(".ds-start")) b.onclick = () => openStart(rowOf(b.dataset.pid));
  for (const b of document.querySelectorAll(".ds-done")) b.onclick = () => act((s) => dsFinish(s, rowOf(b.dataset.pid)));
  for (const b of document.querySelectorAll(".ds-team-b")) b.onclick = () => {
    const t = teamsOf(ROWS()).find((x) => x.id === b.dataset.team);
    const cur = (ST.teams[t.id] || {}).status;
    act((s) => dsTeam(s, t.id, t.label, cur === b.dataset.st ? null : b.dataset.st));
  };
  bindMore();
}
function bindMore() {}
// Starten: op de geplande baan, of (als die bezet/buiten gebruik is) op een andere vrije baan.
function openStart(r) {
  const n = (DS.window || {}).courts || 0, now = nowMin();
  const busy = new Set(dsCourts(ROWS(), ST, now, n).filter((c) => c.cur || c.off).map((c) => c.court));
  if (!busy.has(r.court)) { act((s) => dsStart(s, r, r.court)); return; }
  const free = [...Array(n).keys()].map((i) => i + 1).filter((c) => !busy.has(c));
  const c = prompt(`Baan ${r.court} is bezet. Op welke baan start ${dsName(r)}? Vrij: ${free.join(", ") || "geen"}`, free[0] || "");
  if (c && free.includes(+c)) act((s) => dsStart(s, r, +c));
}

function init() {
  window.addEventListener("hashchange", () => { GEN = -1; load(); });
  load();
  setInterval(() => { if (!BUSY && !document.querySelector("dialog[open]")) load(true).catch(() => {}); else render(); }, DS_POLL);
}
if (typeof document !== "undefined") init();
