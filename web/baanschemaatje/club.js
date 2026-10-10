"use strict";
// Baanschemaatje clubpagina: instellingen, KNLTB-export uploaden, seizoensoverzicht, plannen op verzoek.
// Praat met de live-backend (server/baanschemaatje). Geen login (nog): zie ROADMAP "Login per club".

const API_DEFAULT = "https://baanschemaatje-356953092000.europe-west1.run.app";
const API = (new URLSearchParams(location.search).get("api") || API_DEFAULT).replace(/\/+$/, "");

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const toMin = (hhmm) => parseInt(hhmm.slice(0, 2), 10) * 60 + parseInt(hhmm.slice(3, 5), 10);
const toHHMM = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

const RULE_NL = {
  match_start_grid: "Begintijd op hele/halve uren (min)",
  match_start_window: "Begintijd wedstrijd",
  junioren_start_window: "Junioren (Groen + 11–14): begintijd",
  junioren_latest_start: "Junioren: begintijd uiterlijk",
  junioren_mixed_8p_latest_start: "Gemengd 8p junioren: begintijd uiterlijk",
  mixed_8p_latest_start: "Gemengd 8p: begintijd uiterlijk",
  travel_not_before: "Reisafstand ≥ km: niet vóór",
  min_reservation: "Minimale reservering per partij (KNLTB)",
  start_window_8p: "8-partijenteams: begintijd",
  mixed_8p_not_before: "Gemengd 8p: niet vóór",
  youth_last_start: "Jeugd: laatste start uiterlijk",
  first_start_deadline: "Eerste partij elk team uiterlijk",
  max_wait_minutes: "Max wachttijd tussen partijen (min)",
  max_blocks_per_team: "Max speelblokken per team",
  waterfall_8p: "8p: strikte S → D → GD",
};

let CLUBS = [];
let CLUB = null;      // GET /clubs/{id}
let DATES = [];
const PLANS = new Map();

function status(msg, cls = "") { const el = $("status"); el.className = `live-status ${cls}`; el.textContent = msg; }

async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, opts);
  let body = null;
  try { body = await res.json(); } catch (_) { /* geen JSON */ }
  if (!res.ok) {
    const d = body && body.detail;
    throw new Error(typeof d === "string" ? d : d && d.message ? d.message : `HTTP ${res.status}`);
  }
  return body;
}
const jsonOpts = (method, data) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

// ---------------------------------------------------------------- clubs

async function loadClubs(select) {
  const j = await api("/clubs");
  CLUBS = j.clubs;
  $("club").innerHTML = CLUBS.map((c) =>
    `<option value="${esc(c.id)}">${esc(c.name)}${c.demo ? " — demo" : ""}${c.stored ? "" : " (alleen lezen)"}</option>`).join("");
  const want = select || decodeURIComponent(location.hash.slice(1)) || (CLUBS.find((c) => c.id === "mierlo") || CLUBS[0]).id;
  const dflt = (CLUBS.find((c) => c.id === "mierlo") || CLUBS[0]).id;
  $("club").value = CLUBS.some((c) => c.id === want) ? want : dflt;  // bv. #regelhulp?q=… is geen club
  await loadClub();
}

async function loadClub() {
  const id = $("club").value;
  if (CLUB && CLUB.id !== id && anyDirty() && !confirm("Er zijn niet-opgeslagen wijzigingen voor deze club. Toch van club wisselen?")) { $("club").value = CLUB.id; return; }
  history.replaceState(null, "", `#${encodeURIComponent(id)}`);
  status("Club laden…", "busy");
  CLUB = await api(`/clubs/${encodeURIComponent(id)}`);
  PLANS.clear();
  $("plan-sec").hidden = true;
  SHOWN_DATE = null;
  fillForm();
  await loadSaved();
  await loadSeason();
  status("");
}

function fillForm() {
  const p = CLUB.profile, s = CLUB.summary;
  const meta = CLUB.meta || {};
  $("club-title").innerHTML = `${esc(s.name)}${meta.demo ? '<span class="badge demo">DEMO</span>' : ""}${CLUB.editable ? "" : '<span class="badge ro">alleen lezen</span>'}`;
  $("club-kind").textContent = meta.demo
    ? "Democlub: fictieve vereniging om Baanschemaatje uit te proberen. Pas gerust aan; hij kan later worden teruggezet."
    : CLUB.editable ? `Club-id ${CLUB.id}. Laatst gewijzigd ${meta.updated_at ? new Date(meta.updated_at).toLocaleString("nl-NL") : "–"}.`
      : "Ingebouwd voorbeeldprofiel (clubs/*.yaml): alleen lezen. Maak een nieuwe club om zelf te experimenteren.";
  $("f-name").value = s.name; $("f-knltb").value = s.knltb_name; $("f-courts").value = s.courts;
  $("f-start").value = s.day.start; $("f-fallback").value = s.day.fallback_start || "";
  $("f-last").value = s.day.last_start; $("f-end").value = s.day.end;
  const r = s.reservations || {};
  $("f-rood").value = r.rood ? r.rood.courts.join(", ") : "";
  $("f-oranje").value = r.oranje ? r.oranje.courts.join(", ") : "";
  $("f-oranje-rood").value = r.oranje && r.oranje.courts_if_rood ? r.oranje.courts_if_rood.join(", ") : "";
  $("f-maxcourts").value = s.max_courts_per_team;
  $("f-pairs").value = s.court_pairs ? s.court_pairs.map((x) => x.join("-")).join(", ") : "";
  $("f-pref8p").value = (s.preferred_courts_8p || []).join(", ");
  $("f-adjacent").checked = s.adjacent_courts !== false;
  renderRules(s.rules);
  for (const el of document.querySelectorAll('[id^="f-"], #rules input, #days-pick input')) el.disabled = !CLUB.editable;
  $("save").disabled = !CLUB.editable;
  $("upload").disabled = !CLUB.editable;
  $("file").disabled = !CLUB.editable;
}

function paramInputs(r) {
  const p = r.params || {};
  const inp = (k, v, type) => `<input data-rule="${esc(r.name)}" data-k="${k}" type="${type}" ${type === "time" ? 'step="900"' : 'min="0"'} value="${esc(v)}">`;
  if (r.name === "min_reservation" || r.name === "waterfall_8p") return "–";
  const parts = [];
  if ("from" in p) parts.push(`${inp("from", p.from, "time")} – ${inp("to", p.to, "time")}`);
  if ("time" in p) parts.push(inp("time", p.time, "time"));
  if ("value" in p) parts.push(inp("value", p.value, "number"));
  return parts.join(" ");
}
function paramText(p) {
  if (!p || !Object.keys(p).length) return "aan";
  if ("from" in p) return `${p.from} – ${p.to}`;
  if ("time" in p && "value" in p) return `${p.value} km → ${p.time}`;
  if ("time" in p) return p.time;
  return String(p.value);
}

// Ruimer dan KNLTB? Alleen voor KNLTB-regels; productdefaults mag een club vrij kiezen.
function looser(r, params, hard) {
  if (r.source === "product") return false;
  if (r.core_hard && !hard) return true;
  const c = r.core_params || {};
  if ("from" in c && (toMin(params.from) < toMin(c.from) || toMin(params.to) > toMin(c.to))) return true;
  if ("time" in c && r.name !== "travel_not_before" && toMin(params.time) > toMin(c.time)) return true;
  if (r.name === "travel_not_before" && (toMin(params.time) < toMin(c.time) || params.value > c.value)) return true;
  if (r.name === "match_start_grid" && params.value < c.value) return true;
  return false;
}

function renderRules(rules) {
  $("rules").innerHTML = `<tr><th>Regel</th><th>Deze club</th><th>Hard</th><th>Soort</th><th>KNLTB/standaard</th><th>Bron</th></tr>` +
    rules.map((r) => {
      const tag = r.source === "product" ? '<span class="tag product">Baanschemaatje</span>' : '<span class="tag knltb">KNLTB</span>';
      return `<tr data-rule-row="${esc(r.name)}"><td>${esc(RULE_NL[r.name] || r.name)}${r.club_override ? ' <span class="tag club">clubafspraak</span>' : ""}</td>
        <td>${paramInputs(r)}</td>
        <td><input type="checkbox" data-rule="${esc(r.name)}" data-k="hard" ${r.hard ? "checked" : ""}></td>
        <td>${tag}</td><td>${esc(paramText(r.core_params))}${r.core_hard ? "" : " (zacht)"}</td>
        <td class="hint">${r.source === "product" ? "productstandaard" : sourceLink(r.source)}</td></tr>`;
    }).join("");
  for (const el of $("rules").querySelectorAll("input")) el.addEventListener("input", markLooser);
  markLooser();
}

function readRule(r) {
  const params = { ...(r.params || {}) };
  let hard = r.hard;
  for (const el of $("rules").querySelectorAll(`input[data-rule="${r.name}"]`)) {
    if (el.dataset.k === "hard") hard = el.checked;
    else params[el.dataset.k] = el.type === "number" ? parseInt(el.value || "0", 10) : el.value;
  }
  return { params, hard };
}

function markLooser() {
  for (const r of CLUB.summary.rules) {
    const { params, hard } = readRule(r);
    const tr = $("rules").querySelector(`tr[data-rule-row="${r.name}"]`);
    let bad = false;
    try { bad = looser(r, params, hard); } catch (_) { bad = false; }
    tr.classList.toggle("looser", bad);
    tr.title = bad ? "Ruimer dan het KNLTB-reglement" : "";
  }
}

const courtsList = (s) => s.split(/[,\s]+/).filter(Boolean).map((x) => parseInt(x, 10));

function buildProfile() {
  const raw = JSON.parse(JSON.stringify(CLUB.profile));
  raw.club = { ...(raw.club || {}), name: $("f-name").value.trim(), knltb_name: $("f-knltb").value.trim() };
  raw.courts = { ...(raw.courts || {}), count: parseInt($("f-courts").value, 10) };
  raw.day = { start: $("f-start").value, last_start: $("f-last").value, end: $("f-end").value };
  if ($("f-fallback").value) raw.day.fallback_start = $("f-fallback").value;
  const res = {};
  if ($("f-rood").value.trim()) res.rood = { courts: courtsList($("f-rood").value) };
  if ($("f-oranje").value.trim()) {
    res.oranje = { courts: courtsList($("f-oranje").value) };
    if ($("f-oranje-rood").value.trim()) res.oranje.courts_if_rood = courtsList($("f-oranje-rood").value);
  }
  if (Object.keys(res).length) raw.reservations = res; else delete raw.reservations;
  const ca = { max_courts_per_team: parseInt($("f-maxcourts").value, 10) };
  if ($("f-pairs").value.trim()) ca.pairs = $("f-pairs").value.split(",").map((p) => courtsList(p.replace("-", " ")));
  if ($("f-pref8p").value.trim()) ca.preferred_courts_8p = courtsList($("f-pref8p").value);
  ca.adjacent = $("f-adjacent").checked;
  raw.court_assignment = ca;
  const rules = {};
  for (const r of CLUB.summary.rules) {
    const { params, hard } = readRule(r);
    const same = hard === r.core_hard && JSON.stringify(params) === JSON.stringify(r.core_params);
    if (!same) rules[r.name] = { ...params, hard };
  }
  raw.rules = rules;
  return raw;
}

async function save() {
  $("save-status").textContent = "Opslaan…";
  try {
    await api(`/clubs/${encodeURIComponent(CLUB.id)}/profile`, jsonOpts("PUT", buildProfile()));
    $("save-status").textContent = "Opgeslagen.";
    const keep = CLUB.id;
    await loadClubs(keep);
    $("save-status").textContent = `Opgeslagen om ${new Date().toLocaleTimeString("nl-NL")}.`;
  } catch (e) {
    $("save-status").innerHTML = `<span style="color:#c53030;white-space:pre-wrap">Niet opgeslagen: ${esc(e.message)}</span>`;
  }
}

async function createClub() {
  const name = $("new-name").value.trim();
  if (!name) { status("Vul een clubnaam in.", "err"); return; }
  const profile = { club: { name, knltb_name: $("new-knltb").value.trim().toUpperCase() || name.toUpperCase() },
    courts: { count: parseInt($("new-courts").value, 10) || 6 },
    day: { start: "09:00", fallback_start: "08:30", last_start: "19:30", end: "20:00" } };
  try {
    const j = await api("/clubs", jsonOpts("POST", { profile }));
    $("new-sec").hidden = true;
    await loadClubs(j.id);
    status(`Club "${name}" aangemaakt. Upload nu de KNLTB-export.`, "ok");
  } catch (e) { status(`Aanmaken mislukt: ${e.message}`, "err"); }
}

// ---------------------------------------------------------------- seizoen

async function loadSeason() {
  const j = await api(`/clubs/${encodeURIComponent(CLUB.id)}/season`);
  DATES = j.dates;
  const s = j.season || {};
  const rep = s.report;
  $("season-info").innerHTML = j.own_season
    ? `<p><b>Eigen seizoen:</b> ${esc(s.filename)} (geüpload ${s.uploaded_at ? new Date(s.uploaded_at).toLocaleString("nl-NL") : "–"})${rep ? ` · ${esc(rep.format)} · ${rep.imported} thuiswedstrijden overgenomen van ${rep.rows_in_file} regels` : ""}</p>${rep ? reportHtml(rep) : ""}`
    : `<p class="hint">Nog geen eigen seizoen; het standaardseizoen (${esc(s.filename || "")}) wordt gebruikt.</p>`;
  renderDates();
}

function reportHtml(rep) {
  const sk = Object.entries(rep.skipped || {}).map(([k, v]) => `${esc(k)}: ${v}`).join(" · ");
  const un = Object.entries(rep.unknown_schemas || {}).map(([k, v]) => `${esc(k)} (${v}×)`).join(", ");
  return `<p class="hint">Overgeslagen: ${sk || "niets"}${un ? `<br><b>Onbekend formaat (niet ingepland):</b> ${un}` : ""}</p>`;
}

async function upload() {
  const f = $("file").files[0];
  if (!f) { status("Kies eerst een bestand.", "err"); return; }
  const days = [...document.querySelectorAll("#days-pick input:checked")].map((x) => x.value).join(",") || "zondag";
  status(`"${f.name}" uploaden en verwerken…`, "busy");
  try {
    const j = await api(`/clubs/${encodeURIComponent(CLUB.id)}/season?filename=${encodeURIComponent(f.name)}&days=${days}`,
      { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: await f.arrayBuffer() });
    PLANS.clear();
    await loadClub();
    status(`${j.report.imported} thuiswedstrijden op ${j.dates.length} speeldagen gevonden.`, "ok");
  } catch (e) { status(`Upload mislukt: ${e.message}`, "err"); }
}

// ---------------------------------------------------------------- plannen

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
  const d = DATES.find((x) => x.date === date);
  const s = CLUB.summary;
  const base = ok || { status: "", day_start: s.day.start, courts: s.courts, validator: {}, stats: {},
    rows: (d ? d.wedstrijden : []).flatMap((x) => mvRowsFor({ ...mvFromSeason(x), from: undefined })) };
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
    const stats = computed ? ovPlanStats(plan, CLUB.summary) : null;
    const day = ovDay(x, { wedstrijden: mvFromRows(plan.rows).length, partijen: plan.rows.filter((r) => r.kind !== "W").length || null,
      stats, moves: cmv() });
    day.changed = changed;
    if (saved) { day.saveInfo = `opgeslagen ${hhmm(saved.saved_at)}${saved.source === "handmatig aangepast" ? " · handmatig aangepast" : ""}`; day.saveCls = "saved"; }
    else if (unsaved) { day.saveInfo = "berekend, niet opgeslagen"; day.saveCls = "unsaved"; }
    else if (staleSaved) { day.saveInfo = "opgeslagen versie past niet meer bij de verzettingen"; day.saveCls = "unsaved"; }
    const p = PLANS.get(x.date);
    if (p && p.error) day.note = `Fout: ${p.error}`;
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
  const s = CLUB.summary;
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
  $("plan-state").innerHTML = changed ? `<div class="banner">Aangepast: ${[cmv().into(date).length ? `${cmv().into(date).length} wedstrijd(en) hierheen verzet` : "", cmv().outOf(date).length ? `${cmv().outOf(date).length} wedstrijd(en) naar een andere dag verzet` : ""].filter(Boolean).join(", ")}, nog niet berekend. Sleep de partijen zelf op het baanschema of <button class="btn2 ov-calc" id="calc-day">Nu berekenen</button></div>`
    : !computed ? `<div class="banner">Nog niet berekend: alle partijen staan bij "Niet ingepland". <button class="btn2 ov-calc" id="calc-day">Nu berekenen</button></div>` : "";
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
  bar: () => $("edit-bar"), club: () => CLUB.summary, render: renderPlanGrid,
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
  const s = CLUB.summary;
  const placed = plan.rows.filter((r) => r.start !== "NIET_GELUKT" && r.court);
  const startMin = Math.min(510, toMin(s.day.fallback_start || s.day.start), ...placed.map((r) => toMin(r.start)));
  const endMin = Math.max(toMin(s.day.end), ...placed.map((r) => toMin(r.end)));
  const n = (endMin - startMin) / 15;
  const g = $("grid");
  g.style.gridTemplateColumns = `56px repeat(${plan.courts}, minmax(100px, 1fr))`;
  g.style.gridTemplateRows = `auto repeat(${n}, var(--row))`;
  const html = [`<div class="hdr corner" style="grid-row:1;grid-column:1">tijd</div>`];
  for (let k = 1; k <= plan.courts; k++) html.push(`<div class="hdr" style="grid-row:1;grid-column:${k + 1}">Baan ${k}</div>`);
  for (let i = 0; i < n; i++) {
    const m = startMin + i * 15;
    html.push(`<div class="time${m % 60 === 0 ? " hour" : ""}" style="grid-row:${i + 2};grid-column:1">${m % 30 === 0 ? toHHMM(m) : ""}</div>`);
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
    html.push(`<div class="blk${isRes ? " res" : ""}" data-ri="${IDX.get(r)}" style="grid-row:${r0}/${r1};grid-column:${r.court + 1};${style}" title="${esc(r.team)}">
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
  $("save").onclick = save;
  $("upload").onclick = upload;
  $("plan-all").onclick = planAll;
  $("back-link").onclick = (e) => { e.preventDefault(); $("plan-sec").hidden = true; $("overview-sec").scrollIntoView({ behavior: "smooth" }); };
  $("new-btn").onclick = () => { $("new-sec").hidden = false; $("new-name").focus(); };
  $("new-cancel").onclick = () => { $("new-sec").hidden = true; };
  $("new-create").onclick = createClub;
  try { await loadClubs(); } catch (e) { status(`Server niet bereikbaar (${API}): ${e.message}`, "err"); }
}
init();
