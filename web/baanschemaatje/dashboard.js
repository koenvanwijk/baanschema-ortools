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
  const r = await fetch(`${API}${withShare(path)}`, { credentials: "include", ...opts });
  let b = null; try { b = await r.json(); } catch (_) { /* leeg */ }
  return { ok: r.ok, status: r.status, body: b };
}
function nowMin() { return dsClock(new Date()); }

async function load(quiet = false) {
  const { club, date } = dsParse();
  const r = await dsFetch(`/clubs/${encodeURIComponent(club)}/dayrun/${encodeURIComponent(date)}`);
  if (!r.ok) { say(`Kon de speeldag niet laden: ${(r.body && r.body.detail) || r.status}`, "bad"); return; }
  const j = r.body;
  DS = { club, date, name: j.name, window: j.window, mode: j.mode, plan: j.schedule && j.schedule.plan, saved: j.schedule, profile: j.profile, demo: !!j.demo };
  $("ds-demo-reset").hidden = !DS.demo; $("ds-demo-reset").onclick = demoReset;
  if (j.gen !== GEN || !quiet) { ST = dsNorm(j.state); GEN = j.gen; }
  render();
}

async function demoReset() {
  if (!DS || !DS.demo || !confirm("Alles wat er deze dag getikt is wissen (demo)?")) return;
  const r = await dsFetch(`/clubs/${encodeURIComponent(DS.club)}/demo-reset/${encodeURIComponent(DS.date)}`, { method: "POST" });
  if (!r.ok) { say(`Reset mislukt: ${(r.body && r.body.detail) || r.status}`, "bad"); return; }
  GEN = null; await load(); say("Demo-dag gereset", "ok");
}

function chip(s, r) {
  if (s.status === "gepland" && r && dsHit(r, ST)) return '<span class="ds-chip late" title="Baan buiten gebruik in deze periode">geraakt · baan buiten gebruik</span>';
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
    return `<li data-pid="${esc(dsPid(r))}"><span class="pl-court">Baan ${s.court || r.court}</span> <b>${esc(r.label)} ${esc(r.home_team)}</b> ${esc(r.part)} ${chip(s, r)}${ch ? ` <span class="ds-chip gewijzigd" title="was ${esc(ch.start)} baan ${ch.court}">gewijzigd</span>` : ""}${rowButtons(r, s)}</li>`;
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
  const delay = dsExpectedDelay(dsRows(DS.plan), ST, c.court, new Date());
  const shift = delay > 0 && c.next ? `<div class="ds-over">Volgende partij ~${delay} min later</div><button class="btn2 ds-shift" data-court="${c.court}" data-delta="${Math.ceil(delay / 15) * 15}">Doorschuiven +${Math.ceil(delay / 15) * 15} min…</button>` : "";
  return `<div class="bg-court busy${over ? " long" : ""}"><div class="bg-cn">Baan ${c.court}</div>
    <div class="bg-what"><b>${esc(c.cur.part)}</b> ${esc(c.cur.label)} ${esc(c.cur.home_team)}</div>
    ${shift}<div class="bg-time">sinds ${new Date(p.start).toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })} · <b>${el} min</b>${over ? ` · <span class="ds-over">${over} min uitloop</span>` : ""}</div>${nx}${cardButtons(c)}</div>`;
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
  return ["aanwezig", "te_laat", "staakt", "doorgaan", "later"].map((k) => `<button class="btn2 ds-team-b${cur === k ? " on" : ""}" data-team="${esc(t.id)}" data-st="${k}">${DS_TEAM_NL[k]}</button>`).join("");
}
function renderTeams(rows) {
  $("ds-teams-sec").hidden = false;
  const now = nowMin();
  $("ds-teams").innerHTML = teamsOf(rows).map((t) => {
    const done = t.rows.filter((r) => dsStatus(r, ST, now).status === "klaar").length;
    const cur = ST.teams[t.id];
    return `<div class="ds-team"><b>${esc(t.label)}</b> – ${esc(t.away)}<br><span class="hint">aanvang ${esc(clockShort(t.first))} · ${done}/${t.rows.length} klaar${cur ? ` · ${esc(DS_TEAM_NL[cur.status])}${cur.time ? ` ${esc(cur.time)}` : ""}` : ""}</span>
      <div class="btns">${teamButtons(t)}</div></div>`;
  }).join("") + '<p class="hint" style="grid-column:1/-1">Regen? Beslis per team: staakt, gaat door of start later. Daarna "Herplan rest van de dag".</p>';
}
function bind() {
  $("ds-actions").innerHTML = `<button id="ds-undo" class="btn2 bg-big"${(ST.undo || []).length && !BUSY ? "" : " disabled"}>↶ Ongedaan maken</button>`;
  $("ds-undo").onclick = () => act((s) => dsUndo(s));
  if ((ST.prev || []).length) { $("ds-actions").insertAdjacentHTML("beforeend", ' <button id="ds-restore" class="btn2">Vorige schemaversie terugzetten</button>'); $("ds-restore").onclick = restorePrev; }
  for (const b of document.querySelectorAll(".ds-start")) b.onclick = () => openStart(rowOf(b.dataset.pid));
  for (const b of document.querySelectorAll(".ds-done")) b.onclick = () => act((s) => dsFinish(s, rowOf(b.dataset.pid)));
  for (const b of document.querySelectorAll(".ds-team-b")) b.onclick = () => {
    const t = teamsOf(ROWS()).find((x) => x.id === b.dataset.team);
    const cur = (ST.teams[t.id] || {}).status, k = b.dataset.st;
    if (cur === k) { act((s) => dsTeam(s, t.id, t.label, null)); return; }
    if (k === "later") {
      // SD8: later starten met nieuwe starttijd; herplannen (SD5) houdt die aan.
      const tm = prompt(`${t.label}: vanaf hoe laat kan het team (weer) spelen? (HH:MM)`, dsHM(Math.ceil((nowMin() + 60) / 15) * 15));
      if (!tm || !/^\d\d:\d\d$/.test(tm)) return;
      act((s) => dsTeam(s, t.id, t.label, "later", { time: tm }));
      return;
    }
    if (k === "staakt" && !confirm(`${t.label} staakt: de partijen die nog niet begonnen zijn vallen weg bij herplannen (geen opgave; terug te draaien). Doorgaan?`)) return;
    act((s) => dsTeam(s, t.id, t.label, k));
  };
  bindMore();
}
function bindMore() {
  $("ds-actions").insertAdjacentHTML("beforeend", ` <button id="ds-off" class="btn2 bg-big">Baan buiten gebruik…</button>`);
  $("ds-off").onclick = openOff;
  const offs = ST.off || [];
  $("ds-offs").innerHTML = offs.length ? `<div class="banner">Buiten gebruik: ${offs.map((o, i) => `baan ${o.court} vanaf ${esc(o.from)}${o.to ? ` tot ${esc(o.to)}` : ""}${o.why ? ` (${esc(o.why)})` : ""} <button class="btn2 ds-off-rm" data-i="${i}">opheffen</button>`).join(" · ")}</div>` : "";
  for (const b of document.querySelectorAll(".ds-off-rm")) b.onclick = () => act((s) => dsOffRemove(s, +b.dataset.i));
  bindMore2();
}
function bindMore2() {
  for (const b of document.querySelectorAll(".ds-shift")) b.onclick = () => {
    const c = +b.dataset.court, d = +b.dataset.delta;
    const rows = DS.plan.rows;
    const next = ROWS().find((r) => r.court === c && dsStatus(r, ST, nowMin()).status === "gepland");
    proposePlan(dsShiftCourt(rows, ST, c, dsMin(next.start), d, nowMin()), `Doorschuiven baan ${c}: +${d} min`);
  };
  bindMore3();
}
// SD5: "Herplan rest van de dag" — alleen op deze knop; voorstel met verschil, pas na bevestiging definitief.
function bindMore3() {
  $("ds-actions").insertAdjacentHTML("beforeend", ' <button id="ds-replan" class="btn bg-big">Herplan rest van de dag…</button>');
  $("ds-replan").onclick = replanRest;
  bindMore4();
}
function bindMore4() {}
async function replanRest() {
  const now = dsHM(nowMin());
  if (!confirm(`Rest van de dag herplannen vanaf ${now}?\n\nGespeelde en lopende partijen blijven staan. Banen buiten gebruik, gestaakte teams en "later starten" tellen mee. Partijen kunnen naar een andere baan en later beginnen (tot sluiting). Je ziet eerst het verschil; pas na Bevestigen wordt het definitief.`)) return;
  BUSY = true; say("Herplannen… (enkele seconden)", "warn");
  const r = await dsFetch(`/clubs/${encodeURIComponent(DS.club)}/replan/${encodeURIComponent(DS.date)}`, jsonOpts("POST", { now, time_limit_s: 8 }));
  BUSY = false;
  if (!r.ok) { say(`Herplannen lukte niet: ${(r.body && r.body.detail) || r.status}`, "bad"); return; }
  say("");
  const j = r.body;
  proposePlan(j.rows, `Herplan rest van de dag (vanaf ${now})`,
    `${j.pinned} partij(en) vast (gespeeld/bezig)${j.dropped ? ` · ${j.dropped} gestaakt` : ""}${j.unscheduled ? ` · <b class="ds-over">${j.unscheduled} past niet meer</b>` : " · alles past"}. Alleen schuiven, geen omwisselen tussen teams.`);
}

// Voorstel tonen (verschil oud ↔ nieuw) en pas na bevestiging opslaan als definitief schema (bron "herplan").
let PROPOSAL = null;
function proposePlan(newRows, title, info = "") {
  const diff = dsDiff(DS.plan.rows, newRows);
  PROPOSAL = { rows: newRows, diff, title };
  $("ds-diff-title").textContent = title;
  // Teambezetting (spelers/volgorde) en baanconflicten zijn hard (besluit Oscar 16-10-2026): alleen nieuwe
  // problemen tellen (t.o.v. het huidige schema), anders kan Bevestigen niet.
  const key = (x) => `${x.level}|${x.msg}`;
  const before = new Set(checkPlan(DS.plan.rows, DS.profile).issues.map(key));
  const all = checkPlan(newRows, DS.profile).issues.filter((x) => !before.has(key(x)));
  const hard = all.filter((x) => ["conflict", "Spelersconflict", "Volgorde"].includes(x.level));
  const soft = all.filter((x) => x.level === "KNLTB");
  $("ds-diff-info").innerHTML = info + (hard.length ? `<div class="ds-over">✖ Kan zo niet: ${esc(hard[0].msg)}${hard.length > 1 ? ` (+${hard.length - 1})` : ""}. Enkels en dubbels van een team mogen niet tegelijk dezelfde spelers vragen. Gebruik "Herplan rest van de dag".</div>` : "")
    + (soft.length ? `<div class="ds-over">⚠ ${soft.length} regelpunt(en), bv. ${esc(soft[0].msg)}</div>` : "");
  $("ds-diff").innerHTML = diff.length ? `<table class="ds-diff"><tr><th>Partij</th><th>Oud</th><th>Nieuw</th></tr>${diff.map((d) => `<tr><td>${esc(dsName(d.row))}</td><td>${d.old ? `${esc(d.old.start)} · baan ${d.old.court}` : "niet ingepland"}</td><td>${d.new ? `<b>${esc(d.new.start)} · baan ${d.new.court}</b>` : d.gone ? "<b>vervalt (team staakt)</b>" : '<b class="ds-over">past niet meer</b>'}</td></tr>`).join("")}</table>`
    : '<p class="hint">Geen wijzigingen.</p>';
  $("ds-diff-ok").disabled = !diff.length || hard.length > 0;
  $("ds-diff-dlg").showModal();
}
async function confirmProposal() {
  const P = PROPOSAL;
  $("ds-diff-dlg").close();
  if (!P || !P.diff.length) return;
  const old = DS.plan;
  const plan = { ...JSON.parse(JSON.stringify(old)), rows: P.rows, changed: dsChanged(old.changed, P.diff), changed_at: new Date().toISOString() };
  delete plan.sig;
  const check = checkSummary(P.rows, checkPlan(P.rows, DS.profile));
  BUSY = true;
  const r = await dsFetch(`/clubs/${encodeURIComponent(DS.club)}/schedule/${encodeURIComponent(DS.date)}`, jsonOpts("PUT", { plan, source: "herplan", check, sig: (DS.saved && DS.saved.sig) || "[]" }));
  BUSY = false;
  if (!r.ok) { say(`Niet opgeslagen: ${(r.body && r.body.detail) || r.status}`, "bad"); return; }
  DS.plan = plan; DS.saved = { ...DS.saved, ...r.body, plan };
  // Vorige versie bewaren in het verloop (terug te zetten), plus logregel.
  await act((s) => _dsDo(s, (x) => { x.prev = [...(x.prev || []), { at: new Date().toISOString(), title: P.title, rows: old.rows, changed: old.changed || null }].slice(-3); },
    `${P.title}: ${P.diff.length} partij(en) gewijzigd`, new Date()));
}
async function restorePrev() {
  const pv = (ST.prev || [])[ST.prev.length - 1];
  if (!pv || !confirm(`Vorige versie (vóór "${pv.title}") terugzetten?`)) return;
  const plan = { ...JSON.parse(JSON.stringify(DS.plan)), rows: pv.rows, changed: pv.changed || undefined };
  if (!pv.changed) delete plan.changed;
  const r = await dsFetch(`/clubs/${encodeURIComponent(DS.club)}/schedule/${encodeURIComponent(DS.date)}`, jsonOpts("PUT", { plan, source: "herplan", check: checkSummary(pv.rows, checkPlan(pv.rows, DS.profile)), sig: (DS.saved && DS.saved.sig) || "[]" }));
  if (!r.ok) { say(`Niet teruggezet: ${(r.body && r.body.detail) || r.status}`, "bad"); return; }
  DS.plan = plan;
  await act((s) => _dsDo(s, (x) => { x.prev = x.prev.slice(0, -1); }, `Vorige versie teruggezet (vóór "${pv.title}")`, new Date()));
}
function openOff() {
  const n = (DS.window || {}).courts || 0;
  $("ds-off-courts").innerHTML = [...Array(n).keys()].map((i) => `<label class="inline"><input type="checkbox" value="${i + 1}"> ${i + 1}</label>`).join(" ");
  $("ds-off-from").value = dsHM(Math.ceil(nowMin() / 15) * 15);
  $("ds-off-to").value = ""; $("ds-off-why").value = "";
  $("ds-off-dlg").showModal();
  $("ds-off-all").onclick = () => { for (const i of $("ds-off-courts").querySelectorAll("input")) i.checked = true; };
  $("ds-off-ok").onclick = (ev) => {
    ev.preventDefault();
    const cs = [...$("ds-off-courts").querySelectorAll("input:checked")].map((i) => +i.value);
    if (!cs.length || !/^\d\d:\d\d$/.test($("ds-off-from").value)) { alert("Kies minstens één baan en een begintijd."); return; }
    $("ds-off-dlg").close();
    act((s) => dsOffAdd(s, cs, $("ds-off-from").value, $("ds-off-to").value, $("ds-off-why").value.trim()));
  };
}
// Starten: op de geplande baan, of (als die bezet/buiten gebruik is) op een andere vrije baan.
function openStart(r) {
  const n = (DS.window || {}).courts || 0, now = nowMin();
  // Opstelling optioneel; als ingevuld controleren we dat niemand tegelijk in een andere lopende partij van het team staat.
  const lineup = (prompt(`Opstelling ${dsName(r)} (optioneel, bv. "Jan + Piet"):`, "") || "").trim();
  const busy = new Set(dsCourts(ROWS(), ST, now, n).filter((c) => c.cur || c.off).map((c) => c.court));
  if (!busy.has(r.court)) { act((s) => dsStart(s, r, r.court, new Date(), lineup, ROWS())); return; }
  const free = [...Array(n).keys()].map((i) => i + 1).filter((c) => !busy.has(c));
  const c = prompt(`Baan ${r.court} is bezet. Op welke baan start ${dsName(r)}? Vrij: ${free.join(", ") || "geen"}`, free[0] || "");
  if (c && free.includes(+c)) act((s) => dsStart(s, r, +c, new Date(), lineup, ROWS()));
}

function init() {
  $("ds-diff-ok").onclick = confirmProposal;
  window.addEventListener("hashchange", () => { GEN = -1; load(); });
  load();
  setInterval(() => { if (!BUSY && !document.querySelector("dialog[open]")) load(true).catch(() => {}); else render(); }, DS_POLL);
}
if (typeof document !== "undefined") init();
