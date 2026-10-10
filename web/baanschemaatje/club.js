"use strict";
// Baanschemaatje clubpagina: seizoensoverzicht + dagweergave, plannen op verzoek, Regelmaatje.
// Instellingen en KNLTB-import staan op club-instellingen.html (instellingen.js). Helpers: common.js.

const PLANS = new Map();

// ---------------------------------------------------------------- clubs

async function loadClubs(select) {
  await loadClubList(select);
  COMP = parseHash().comp || COMP || "alle";
  await loadClub();
}

async function loadClub() {
  const id = $("club").value;
  if (CLUB && CLUB.id !== id && anyDirty() && !confirm("Er zijn niet-opgeslagen wijzigingen voor deze club. Toch van club wisselen?")) { $("club").value = CLUB.id; return; }
  if (!/^#regel/.test(location.hash) || CLUB) setHash(id, COMP);
  status("Club laden…", "busy");
  CLUB = await api(`/clubs/${encodeURIComponent(id)}`);
  PLANS.clear();
  $("plan-sec").hidden = true;
  SHOWN_DATE = null;
  $("settings-link").href = `club-instellingen.html${location.search}#${encodeURIComponent(id)}`;
  $("club-title").innerHTML = `${esc(CLUB.summary.name)}${(CLUB.meta || {}).demo ? '<span class="badge demo">DEMO</span>' : ""}${CLUB.editable ? "" : '<span class="badge ro">alleen lezen</span>'}`;
  await loadSaved();
  await loadSeason();
  status("");
}

// ---------------------------------------------------------------- seizoen + competitiefilter

let ALL_DATES = [];   // seizoen van de server (alle competities)
let COMP = "alle";    // gekozen competitie (sleutel weekdag[-dagdeel]); in de URL-hash als &comp=

async function loadSeason() {
  const j = await api(`/clubs/${encodeURIComponent(CLUB.id)}/season`);
  ALL_DATES = j.dates;
  const s = j.season || {};
  const rep = s.report;
  $("season-line").innerHTML = j.own_season
    ? `Seizoen: ${esc(s.filename)} (geüpload ${s.uploaded_at ? new Date(s.uploaded_at).toLocaleString("nl-NL") : "–"})${rep ? ` · ${rep.imported} thuiswedstrijden${rep.played ? `, waarvan ${rep.played} gespeeld` : ""}` : ""} · <a href="${esc($("settings-link").href)}">import en instellingen</a>`
    : `Nog geen eigen seizoen; het standaardseizoen wordt gebruikt. Upload de KNLTB-export via <a href="${esc($("settings-link").href)}">Instellingen</a>.`;
  renderCompPicker();
  applyComp();
}

// Competitie van één wedstrijd: weekdag + dagdeel (bv. "vrijdag-avond"); za/zo zonder dagdeel.
const compKey = (weekday, dagdeel) => (dagdeel && dagdeel !== "dag" ? `${weekday}-${dagdeel}` : weekday);
const COMP_ORDER = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"];
function compLabel(k) {
  if (k === "alle") return "Alle competities";
  const [wd, dd] = k.split("-");
  const W = wd[0].toUpperCase() + wd.slice(1);
  return dd ? `${W}${dd}` : `${W} (najaar)`;
}
function compCounts() {
  const m = new Map();
  for (const d of ALL_DATES) for (const w of d.wedstrijden) { const k = compKey(d.weekday, w.dagdeel); m.set(k, (m.get(k) || 0) + 1); }
  return [...m].sort((a, b) => COMP_ORDER.indexOf(a[0].split("-")[0]) - COMP_ORDER.indexOf(b[0].split("-")[0]) || a[0].localeCompare(b[0]));
}
function renderCompPicker() {
  const cc = compCounts();
  if (COMP !== "alle" && !cc.some(([k]) => k === COMP)) COMP = "alle";
  const total = cc.reduce((s, [, n]) => s + n, 0);
  $("comp").innerHTML = `<option value="alle">Alle competities (${total})</option>` +
    cc.map(([k, n]) => `<option value="${esc(k)}">${esc(compLabel(k))} (${n})</option>`).join("");
  $("comp").value = COMP;
}
const inComp = (weekday, w) => COMP === "alle" || compKey(weekday, w.dagdeel) === COMP;
// DATES = seizoen gefilterd op de gekozen competitie (dagen zonder wedstrijden in die competitie vallen weg).
function applyComp() {
  DATES = ALL_DATES.map((d) => {
    const ws = d.wedstrijden.filter((w) => inComp(d.weekday, w));
    return { ...d, wedstrijden: ws, fixtures: ws.length, partijen: ws.reduce((s, w) => s + w.matches, 0),
      played: ws.filter((w) => w.status === "gespeeld").length };
  }).filter((d) => d.wedstrijden.length);
  $("comp-note").textContent = COMP === "alle" ? "" : `Alleen ${compLabel(COMP)}. In de dagweergave zie je de hele dag (alle banen); partijen van andere competities zijn lichter.`;
  renderDates();
  if (SHOWN_DATE && !$("plan-sec").hidden) showPlan(SHOWN_DATE, false, true);
}

// Clubsamenvatting voor één dag: dagvenster/banen/regels van die weekdag (do/vr-avond ≠ zondag).
function dayClub(date) {
  const s = CLUB.summary;
  const wd = ovWeekday(date);
  const d = ALL_DATES.find((x) => x.date === date);
  const ws = (s.weekdays || {})[wd];
  const win = (d && d.window) || (ws ? { start: ws.start, last_start: ws.last_start, end: ws.end, courts: ws.courts, bijlage3: ws.bijlage3, lighting: ws.lighting } : null);
  if (!win) return s;
  if (d && !win.bijlage3 && d.dagdelen && d.dagdelen.includes("ochtend") && toMin(win.start) > 540) win.start = "09:00";
  const day = { ...s.day, start: win.start, last_start: win.last_start, end: win.end, fallback_start: win.bijlage3 ? s.day.fallback_start : null };
  let rules = s.rules;
  if (!win.bijlage3) {
    rules = s.rules.map((r) => r.name === "match_start_window" ? { ...r, params: { from: day.start, to: day.last_start }, core_params: { from: day.start, to: day.last_start } }
      : r.name === "first_start_deadline" ? { ...r, hard: false, params: { time: day.last_start } }
      : r.name === "youth_last_start" ? { ...r, params: { time: day.last_start } } : r);
  }
  return { ...s, day, courts: win.courts || s.courts, bijlage3: win.bijlage3 !== false, lighting: win.lighting !== false, weekday: wd, rules };
}

const COMPUTING = new Set();

// Verzettingen per club (verzetten.js), alleen in dit tabblad: opslag voor wijzigingen bestaat nog niet.
const CMOVES = new Map();
function cmv() { if (!CMOVES.has(CLUB.id)) CMOVES.set(CLUB.id, new MoveState()); return CMOVES.get(CLUB.id); }

// ---------------------------------------------------------------- opslaan (server: /clubs/{id}/schedule(s), /moves)

const SAVED = new Map(); // datum → {date, saved_at, source, check, sig, plan}
let SAVED_MOVES = { json: "[]", at: null };
let SAVING = false;
const movesJson = () => JSON.stringify(cmv().forServer());
const movesDirty = () => !!CLUB && CLUB.editable && movesJson() !== SAVED_MOVES.json;
const hhmm = (iso) => { const d = new Date(iso); return isNaN(d) ? "" : `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
// Opgeslagen plan met de status uit de opgeslagen controle.
const savedPlan = (sv) => ({ ...sv.plan, validator: { ...(sv.plan.validator || {}), hard: sv.check.hard ?? null, model: sv.check.model ?? null } });

async function loadSaved() {
  SAVED.clear();
  SAVED_MOVES = { json: "[]", at: null };
  CMOVES.delete(CLUB.id);
  try {
    const [sch, mvs] = await Promise.all([api(`/clubs/${encodeURIComponent(CLUB.id)}/schedules`), api(`/clubs/${encodeURIComponent(CLUB.id)}/moves`)]);
    for (const [d, x] of Object.entries(sch.schedules || {})) if (x && x.plan && Array.isArray(x.plan.rows)) SAVED.set(d, x);
    const st = cmv();
    st.list = (mvs.moves || []).filter((m) => m && m.schema && m.from && m.to).map((m) => ({ ...m, key: m.key || mvKey(m.schema, m.home) }));
    SAVED_MOVES = { json: movesJson(), at: mvs.saved_at };
  } catch (e) {
    status(`Opgeslagen schema's konden niet geladen worden (${e.message}); je ziet de niet-opgeslagen stand.`, "warn");
  }
}

// Niet-opgeslagen werk: berekende dagen (nog niet opgeslagen), versleepte partijen, verzettingen.
function anyDirty() {
  if (!CLUB || !CLUB.editable) return false;
  return movesDirty() || (SHOWN_DATE && !$("plan-sec").hidden && EDITOR.plan && EDITOR.dirty) || [...PLANS.values()].some((p) => p && !p.error && p.rows);
}

async function saveMoves() {
  const r = await api(`/clubs/${encodeURIComponent(CLUB.id)}/moves`, jsonOpts("PUT", { moves: cmv().list.map(({ rows, ...m }) => m) }));
  SAVED_MOVES = { json: movesJson(), at: r.saved_at };
}

async function saveDay(res) {
  const date = SHOWN_DATE;
  if (!date || SAVING) return;
  SAVING = true; EDITOR.refresh();
  try {
    if (movesDirty()) await saveMoves();
    const rows = EDITOR.plan.rows;
    const check = checkSummary(rows, res);
    const src = EDITOR.edited || SHOWN_SRC === "handmatig aangepast" ? "handmatig aangepast" : "berekend";
    const plan = JSON.parse(JSON.stringify(EDITOR.plan));
    delete plan.sig;
    // Onveranderd berekend: status volgens de solver-validatie (zoals vóór opslaan); anders volgens de directe controle.
    const v = plan.validator || {};
    if (src === "berekend" && typeof v.hard === "number") Object.assign(check, { direct: { hard: check.hard, model: check.model }, hard: v.hard, model: v.model ?? 0, by: "solver-validatie" });
    const r = await api(`/clubs/${encodeURIComponent(CLUB.id)}/schedule/${date}`, jsonOpts("PUT", { plan, source: src, check, sig: cmv().sig(date) }));
    SAVED.set(date, { ...r, plan });
    PLANS.delete(date);
    EDITOR.markSaved();
    status(`Baanschema ${date} opgeslagen om ${hhmm(r.saved_at)}.`, "ok");
  } catch (e) {
    status(`Opslaan mislukt: ${e.message}`, "err");
  }
  SAVING = false;
  renderDates();
  showPlan(date, false, true);
}

async function deleteSaved() {
  const date = SHOWN_DATE;
  if (!date || !SAVED.has(date)) return;
  if (!confirm(`Het opgeslagen baanschema van ${date} verwijderen? Je ziet daarna weer de berekende of nog niet berekende stand.`)) return;
  try {
    await api(`/clubs/${encodeURIComponent(CLUB.id)}/schedule/${date}`, { method: "DELETE" });
    SAVED.delete(date);
    status(`Opgeslagen versie van ${date} verwijderd.`, "ok");
  } catch (e) {
    status(`Verwijderen mislukt: ${e.message}`, "err");
  }
  renderDates();
  showPlan(date, false, true);
}

async function saveMovesOnly() {
  if (SAVING) return;
  SAVING = true; renderMoveBars();
  try { await saveMoves(); status("Verzettingen opgeslagen.", "ok"); } catch (e) { status(`Opslaan mislukt: ${e.message}`, "err"); }
  SAVING = false;
  renderDates();
  if (SHOWN_DATE && !$("plan-sec").hidden) EDITOR.refresh();
}

window.addEventListener("beforeunload", (e) => { if (anyDirty()) { e.preventDefault(); e.returnValue = ""; } });

// Plan van een dag zoals het nu is. Nog niet berekend → alle partijen "niet ingepland" (uit de seizoensweergave).
// Volgorde: nu berekend (nog niet opgeslagen) → opgeslagen → vooraf/niet berekend.
function clubDayPlan(date) {
  const p = PLANS.get(date);
  const sv = SAVED.get(date);
  const sig = cmv().sig(date);
  if (p && !p.error && p.rows && p.sig === sig) return { plan: p, computed: true, changed: false, saved: null, unsaved: true };
  if (sv && sv.sig === sig) return { plan: savedPlan(sv), computed: true, changed: false, saved: sv, unsaved: false };
  const ok = p && !p.error && p.rows ? p : sv ? savedPlan(sv) : null;
  const d = ALL_DATES.find((x) => x.date === date);
  const s = dayClub(date);
  // Gespeelde wedstrijden staan vast en worden nooit als "niet ingepland" getoond.
  const base = ok || { status: "", day_start: s.day.start, courts: s.courts, validator: {}, stats: {},
    rows: (d ? d.wedstrijden : []).filter((x) => x.status !== "gespeeld").flatMap((x) => mvRowsFor({ ...mvFromSeason(x), from: undefined })) };
  const changed = cmv().into(date).length > 0 || (!!ok && cmv().touches(date));
  return { plan: mvApplyPlan(base, date, cmv()), computed: !!ok, changed, saved: null, unsaved: false, staleSaved: !!sv };
}

function renderMoveBars() {
  for (const id of ["mv-bar-ov", "mv-bar-day"]) {
    const el = $(id);
    el.innerHTML = CLUB.editable
      ? mvBarHtml(cmv(), "Verzettingen gelden voor het hele seizoen. Opslaan bewaart ze op de server (ook met Opslaan bij een dag).", { dirty: movesDirty(), savedAt: SAVED_MOVES.at, busy: SAVING })
      : mvBarHtml(cmv(), "Dit voorbeeldprofiel is alleen-lezen: verzettingen gelden alleen in dit tabblad.");
    const u = el.querySelector(".mv-undo"), r = el.querySelector(".mv-reset"), sb = el.querySelector(".mv-save-btn");
    if (sb) sb.onclick = saveMovesOnly;
    if (u) u.onclick = () => { cmv().undo(); afterMove(); };
    if (r) r.onclick = () => { cmv().reset(); afterMove(); };
  }
}

function afterMove() {
  renderDates();
  if (SHOWN_DATE && !$("plan-sec").hidden) showPlan(SHOWN_DATE, false);
}

function renderDates() {
  renderMoveBars();
  const days = ovSeasonDays(DATES).map((x) => {
    const { plan, computed, changed, saved, unsaved, staleSaved } = clubDayPlan(x.date);
    const stats = computed ? ovPlanStats(plan, dayClub(x.date)) : null;
    const day = ovDay(x, { wedstrijden: mvFromRows(plan.rows).length, partijen: plan.rows.filter((r) => r.kind !== "W").length || null,
      stats, moves: cmv() });
    day.changed = changed;
    if (saved) { day.saveInfo = `opgeslagen ${hhmm(saved.saved_at)}${saved.source === "handmatig aangepast" ? " · handmatig aangepast" : ""}`; day.saveCls = "saved"; }
    else if (unsaved) { day.saveInfo = "berekend, niet opgeslagen"; day.saveCls = "unsaved"; }
    else if (staleSaved) { day.saveInfo = "opgeslagen versie past niet meer bij de verzettingen"; day.saveCls = "unsaved"; }
    const p = PLANS.get(x.date);
    if (p && p.error) day.note = `Fout: ${p.error}`;
    const m = x.match;
    if (m && m.played) {
      day.played = m.played;
      day.allPlayed = m.played === m.wedstrijden.length && !cmv().into(x.date).length;
      day.wedstrijden = (day.wedstrijden || 0) + m.played;
      day.partijen = (day.partijen || 0) + m.wedstrijden.filter((w) => w.status === "gespeeld").reduce((t, w) => t + w.matches, 0);
      day.note = [day.note, day.allPlayed ? `gespeeld (${m.played})` : `${m.played} gespeeld, vast`].filter(Boolean).join(" · ");
    }
    if (m && m.window && !m.window.bijlage3) day.note = [day.note, `${m.dagdelen.filter((x) => x !== "dag").join("/") || "avond"} ${m.window.start}–${m.window.end}`].filter(Boolean).join(" · ");
    return day;
  });
  ovRender($("overview"), days, { onOpen: (date) => showPlan(date), onCompute: (date) => planDay(date, true), recompute: true,
    computing: COMPUTING, queued: QUEUED, busy: !!RUN, openAlways: true, onMove: (date) => showPlan(date) });
}

const QUEUED = new Set();
let RUN = null; // {ctl, cancelled} van de lopende berekening
const PROG = () => (window._pg ||= new Progress($("progress")));

function setBusy(b) {
  $("plan-all").disabled = b;
  if ($("calc-day")) $("calc-day").disabled = b;
}

// Eén dag berekenen. prefix = "Dag 2 van 6 · " bij "Alle dagen". Geeft true als gelukt.
async function planDay(date, show, prefix = "") {
  if (RUN && !prefix) return false;
  const own = !prefix;
  if (own) RUN = { ctl: null, cancelled: false };
  RUN.ctl = new AbortController();
  const tl = +$("tl").value;
  status("");
  COMPUTING.add(date); QUEUED.delete(date); setBusy(true); renderDates();
  PROG().start({ title: `${prefix}${date}`, kind: "plan", tl, onCancel: () => { RUN.cancelled = true; RUN.ctl.abort(); } });
  let ok = false;
  try {
    const sig = cmv().sig(date);
    const body = { club: CLUB.id, date, time_limit_s: tl };
    if (cmv().count) body.moves = cmv().forServer();
    const p = await api("/plan", { ...jsonOpts("POST", body), signal: RUN.ctl.signal });
    if (body.moves && !p.moves_applied && cmv().touches(date)) {
      throw new Error("de server kent verzetten nog niet (nieuwe serverversie moet nog worden uitgerold); sleep de verzette partijen zelf op het baanschema");
    }
    p.sig = sig;
    PLANS.set(date, p);
    const sm = p.summary;
    PROG().finish(`${prefix}${date} · ${p.summary.solved ? pgDoneText(sm) : "geen oplossing binnen de rekentijd"}`,
      !sm.solved || sm.unscheduled || sm.hard ? "warn" : "ok");
    ok = true;
    if (show) showPlan(date);
  } catch (e) {
    if (e.name === "AbortError") {
      PROG().finish(`${prefix}${date} · Geannuleerd. De server rekent de lopende poging nog af (dat kost nog even rekentijd), het resultaat wordt niet getoond.`, "warn");
    } else {
      if (cmv().into(date).length && /niet in seizoen/.test(e.message)) e.message = "de server kent verzetten nog niet (nieuwe serverversie moet nog worden uitgerold)";
      PLANS.set(date, { error: e.message });
      PROG().finish(`${prefix}${date} · Fout: ${e.message}`, "err");
    }
  }
  COMPUTING.delete(date);
  if (own) { RUN = null; setBusy(false); }
  renderDates();
  return ok;
}

async function planAll() {
  if (RUN) return;
  // Alle dagen met wedstrijden, ook inhaaldagen waar wedstrijden naartoe zijn verzet.
  const todo = ovSeasonDays(DATES).map((x) => x.date).filter((d) => clubDayPlan(d).plan.rows.length);
  RUN = { ctl: null, cancelled: false };
  setBusy(true);
  todo.forEach((d) => QUEUED.add(d));
  let n = 0, okN = 0;
  for (const d of todo) {
    if (RUN.cancelled) break;
    n++;
    if (await planDay(d, false, `Dag ${n} van ${todo.length} · `)) okN++;
  }
  const cancelled = RUN.cancelled;
  QUEUED.clear();
  RUN = null;
  setBusy(false);
  renderDates();
  const probs = todo.filter((d) => { const p = PLANS.get(d); return p && (p.error || p.summary.unscheduled || p.summary.hard); }).length;
  PROG().finish(cancelled ? `Geannuleerd na ${n - 1} van ${todo.length} dagen.` : `Klaar: ${okN} van ${todo.length} dagen berekend${probs ? `, ${probs} met problemen (zie overzicht)` : ", alle in orde of alleen voorkeuren"}.`,
    cancelled || probs ? "warn" : "ok");
}

let SHOWN_SRC = null; // "berekend" | "handmatig aangepast" | null (nog niet berekend)
function showPlan(date, scroll = true, force = false) {
  if (!force && SHOWN_DATE && SHOWN_DATE !== date && !$("plan-sec").hidden && EDITOR.plan && EDITOR.edited
      && !confirm(`Je hebt partijen op ${SHOWN_DATE} versleept zonder op te slaan. Die wijzigingen gaan verloren. Doorgaan?`)) return;
  const { plan, computed, changed, saved, unsaved, staleSaved } = clubDayPlan(date);
  SHOWN_SRC = saved ? saved.source : unsaved || computed ? "berekend" : null;
  SHOWN_STATE = { saved, unsaved, stale: !!staleSaved };
  const s = dayClub(date);
  if (SHOWN_DATE !== date) HL = null;
  $("plan-sec").hidden = false;
  $("plan-title").textContent = `Baanschema ${s.name} — ${ovWeekday(date)} ${date}`;
  const v = plan.validator || {};
  const st = ovPlanStats(plan, s);
  const card = (k, val, cls = "", tip = "") => `<div class="card"${tip ? ` title="${esc(tip)}"` : ""}><div class="k">${k}</div><div class="v ${cls}">${esc(val)}</div></div>`;
  $("summary").innerHTML = [card("Ingepland", st.scheduled, "good"),
    card("Niet ingepland", st.unscheduled, st.unscheduled ? "bad" : "good"),
    card("Overtredingen", v.hard ?? "–", v.hard ? "bad" : "good", "Overtredingen: regels die niet gebroken mogen worden. Moet 0 zijn."),
    card("Niet-gehaalde voorkeuren", v.model ?? "–", v.model ? "warn" : "", "Niet-gehaalde voorkeuren: mag, maar kan mooier."), card("Dagstart", plan.day_start),
    card("Rekentijd", plan.stats && typeof plan.stats.solve_time_s === "number" ? `${plan.stats.solve_time_s}s` : "–"), card("Solver", plan.status || "–")].join("");
  const dd = ALL_DATES.find((x) => x.date === date);
  const played = dd ? dd.wedstrijden.filter((w) => w.status === "gespeeld") : [];
  const playedHtml = played.length ? `<div class="played"><h3>Gespeeld (vast)</h3><p class="hint">Uitslag uit de KNLTB-export. Deze wedstrijden worden niet opnieuw gepland of verzet.</p><ul class="plain">${played.map((w) =>
    `<li class="played-item${inComp(ovWeekday(date), w) ? "" : " dim"}">🔒 <b>${esc(w.label)} ${esc(w.home)}</b> – ${esc(w.away)} · ${esc(w.export_start || "")} · uitslag <b>${esc(w.result)}</b></li>`).join("")}</ul></div>` : "";
  const allPlayed = dd && played.length === dd.wedstrijden.length && !cmv().into(date).length;
  const winNote = s.bijlage3 ? "" : `<p class="hint">Dagvenster ${esc(s.weekday)}: ${esc(s.day.start)}–${esc(clockHHMM(s.day.end))}, laatste start ${esc(s.day.last_start)}, ${s.courts} banen${s.lighting ? " (met verlichting)" : ", <b>geen verlichting ingesteld</b>"}. KNLTB Bijlage 3 (variabele begintijden) geldt alleen op za/zo.</p>`;
  $("plan-state").innerHTML = winNote + playedHtml + (allPlayed ? "" : changed ? `<div class="banner">Aangepast: ${[cmv().into(date).length ? `${cmv().into(date).length} wedstrijd(en) hierheen verzet` : "", cmv().outOf(date).length ? `${cmv().outOf(date).length} wedstrijd(en) naar een andere dag verzet` : ""].filter(Boolean).join(", ")}, nog niet berekend. Sleep de partijen zelf op het baanschema of <button class="btn2 ov-calc" id="calc-day">Nu berekenen</button></div>`
    : !computed ? `<div class="banner">Nog niet berekend: alle partijen staan bij "Niet ingepland". <button class="btn2 ov-calc" id="calc-day">Nu berekenen</button></div>` : "");
  if ($("calc-day")) $("calc-day").onclick = () => planDay(date, true);
  SHOWN_DATE = date;
  EDITOR.load(plan); // werkkopie: slepen + directe controle; Opslaan bewaart hem op de server
  $("print-btn").onclick = () => printPlan(EDITOR.plan, { clubName: s.name, date, dayStart: s.day.fallback_start || s.day.start, dayEnd: s.day.end,
    note: [SHOWN_SRC === "handmatig aangepast" || EDITOR.edited ? "handmatig aangepast" : SHOWN_SRC ? "berekend" : "nog niet berekend",
      EDITOR.dirty ? "niet opgeslagen" : SHOWN_STATE.saved ? `opgeslagen ${hhmm(SHOWN_STATE.saved.saved_at)}` : ""].filter(Boolean).join(", ") });
  if (scroll) $("plan-sec").scrollIntoView({ behavior: "smooth" });
}

let HL = null;
function bindLegend(plan) {
  const date = SHOWN_DATE;
  const ws = new Map(mvFromRows(plan.rows).map((w) => [w.key, w]));
  const sd = ovSeasonDays(DATES);
  for (const chip of document.querySelectorAll("#legend .chip")) {
    chip.onclick = (ev) => {
      ev.stopPropagation();
      const w = ws.get(chip.dataset.team), team = chip.dataset.team;
      mvOpenMenu(chip, w, date, sd, { highlighted: HL === team,
        onHighlight: () => { HL = HL === team ? null : team; mvHighlight($("grid"), $("legend"), EDITOR.plan.rows, HL); },
        onMove: (to) => {
          if (HL === team) HL = null;
          cmv().move([{ w, at: date, to }]);
          status(`${w.label} ${w.home} verzet naar ${to}. Niet opgeslagen; ${to} is nog niet berekend.`, "ok");
          afterMove();
        } });
    };
  }
  if (HL) mvHighlight($("grid"), $("legend"), EDITOR.plan.rows, HL);
}

let SHOWN_DATE = null;
let SHOWN_STATE = { saved: null, unsaved: false };
const EDITOR = new PlanEditor({
  bar: () => $("edit-bar"), club: () => (SHOWN_DATE ? dayClub(SHOWN_DATE) : CLUB.summary), render: renderPlanGrid,
  save: {
    state: () => {
      if (!CLUB || !CLUB.editable) return null;
      const sv = SHOWN_STATE.saved;
      const unsavedWhy = SHOWN_STATE.unsaved ? "berekend, nog niet opgeslagen" : SHOWN_STATE.stale ? "wijkt af van de opgeslagen versie door verzettingen" : movesDirty() ? "verzettingen nog niet opgeslagen" : "";
      return { unsaved: !!unsavedWhy, unsavedWhy, savedAt: sv && sv.saved_at, source: sv && sv.source, canDelete: SAVED.has(SHOWN_DATE), busy: SAVING };
    },
    onSave: (res) => saveDay(res),
    onDelete: () => deleteSaved(),
  },
});

function renderPlanGrid(plan) {
  const s = SHOWN_DATE ? dayClub(SHOWN_DATE) : CLUB.summary;
  const wdShown = SHOWN_DATE ? ovWeekday(SHOWN_DATE) : "zondag";
  const placed = plan.rows.filter((r) => r.start !== "NIET_GELUKT" && r.court);
  // Za/zo: bereik ruim genoeg om naar 08:30 (KNLTB-vroegste) te slepen; doordeweeks het dagvenster.
  const startMin = Math.min(s.bijlage3 ? 510 : toMin(s.day.start), toMin(s.day.fallback_start || s.day.start), ...placed.map((r) => toMin(r.start)));
  const endMin = Math.max(toMin(s.day.end), ...placed.map((r) => toMin(r.end)));
  const n = (endMin - startMin) / 15;
  const g = $("grid");
  g.style.gridTemplateColumns = `56px repeat(${plan.courts}, minmax(100px, 1fr))`;
  g.style.gridTemplateRows = `auto repeat(${n}, var(--row))`;
  const html = [`<div class="hdr corner" style="grid-row:1;grid-column:1">tijd</div>`];
  for (let k = 1; k <= plan.courts; k++) html.push(`<div class="hdr" style="grid-row:1;grid-column:${k + 1}">Baan ${k}</div>`);
  for (let i = 0; i < n; i++) {
    const m = startMin + i * 15;
    html.push(`<div class="time${m % 60 === 0 ? " hour" : ""}" style="grid-row:${i + 2};grid-column:1">${m % 30 === 0 ? toHHMM(m % 1440) : ""}</div>`);
    for (let k = 1; k <= plan.courts; k++) html.push(`<div class="cell${m % 60 === 45 ? " hour" : ""}" data-court="${k}" data-min="${m}" style="grid-row:${i + 2};grid-column:${k + 1}"></div>`);
  }
  const COL = teamColors(plan.rows);
  const teams = new Map();
  const IDX = new Map(plan.rows.map((r, i) => [r, i]));
  for (const r of placed) {
    const r0 = (toMin(r.start) - startMin) / 15 + 2, r1 = (toMin(r.end) - startMin) / 15 + 2;
    const isRes = r.kind === "W";
    const c = COL.get(r.team_id) || { bg: "#ddd", fg: "#111" };
    if (!isRes) teams.set(r.team_id, r);
    const rc = COL.get(`__res_${r.category}`);
    const style = isRes ? (rc ? `background:repeating-linear-gradient(45deg, ${rc.bg}, ${rc.bg} 6px, #fff 6px, #fff 12px)` : "")
      : `background:${c.bg};color:${c.fg}`;
    const dim = !isRes && COMP !== "alle" && compKey(wdShown, r.dagdeel || (/avond/i.test(r.team) ? "avond" : /ochtend/i.test(r.team) ? "ochtend" : "dag")) !== COMP;
    html.push(`<div class="blk${isRes ? " res" : ""}${dim ? " dim" : ""}" data-ri="${IDX.get(r)}" style="grid-row:${r0}/${r1};grid-column:${r.court + 1};${style}" title="${esc(r.team)}">
      <span class="cat">${esc(r.label || r.category)}</span><b>${esc(r.part || "reservering")}</b><div>${esc(isRes ? "baanreservering" : r.home_team || "")}</div><div class="t">${esc(r.start)}–${esc(r.end)}</div></div>`);
  }
  g.innerHTML = html.join("");
  for (const r of plan.rows) if (r.kind !== "W" && !teams.has(r.team_id)) teams.set(r.team_id, r); // ook niet-ingeplande teams
  $("legend").innerHTML = [...teams.values()].sort((a, b) => (a.category || "").localeCompare(b.category || ""))
    .map((r) => { const col = COL.get(r.team_id) || { bg: "#ddd", fg: "#111" };
      return `<span class="chip" data-team="${esc(r.team_id)}" style="background:${col.bg};color:${col.fg}" title="${esc(r.team)} — klik voor markeren / verzetten">${esc(r.label || "")} ${esc(r.home_team || "")}${r.moved_from ? " ↪" : ""}</span>`; }).join("");
  const un = plan.rows.map((r, i) => [r, i]).filter(([r]) => r.start === "NIET_GELUKT");
  $("unscheduled").innerHTML = un.length ? `<h3>Niet ingepland</h3><p class="hint">Sleep een partij op het baanschema om hem in te plannen.</p><ul class="plain">${un.map(([r, i]) => `<li class="drag${r.moved_from ? " moved" : ""}" data-ri="${i}"><b>${esc(r.part || "reservering")}</b> · ${esc(r.label || "")} ${esc(r.home_team || "")} – ${esc(r.away_team || "")}${r.moved_from ? ` <span class="mv-tag">niet ingepland (verzet van ${esc(r.moved_from)})</span>` : ""}</li>`).join("")}</ul>` : "";
  bindLegend(plan);
}

// ---------------------------------------------------------------- init

async function init() {
  $("club").onchange = loadClub;
  $("plan-all").onclick = planAll;
  $("comp").onchange = () => { COMP = $("comp").value; setHash(CLUB.id, COMP); applyComp(); };
  $("back-link").onclick = (e) => { e.preventDefault(); $("plan-sec").hidden = true; $("overview-sec").scrollIntoView({ behavior: "smooth" }); };
  try { await loadClubs(); } catch (e) { status(`Server niet bereikbaar (${API}): ${e.message}`, "err"); }
}
init();
