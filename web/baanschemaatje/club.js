"use strict";
// Baanschemaatje clubpagina: instellingen, KNLTB-export uploaden, live plannen.
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
  if (CLUBS.some((c) => c.id === want)) $("club").value = want;
  await loadClub();
}

async function loadClub() {
  const id = $("club").value;
  history.replaceState(null, "", `#${encodeURIComponent(id)}`);
  status("Club laden…", "busy");
  CLUB = await api(`/clubs/${encodeURIComponent(id)}`);
  PLANS.clear();
  $("plan-sec").hidden = true;
  fillForm();
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
        <td class="hint">${esc(r.source === "product" ? "productstandaard" : r.source)}</td></tr>`;
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

function renderDates() {
  $("dates").innerHTML = `<tr><th>Speeldag</th><th>Dag</th><th>Wedstrijden</th><th>Partijen</th><th>Wedstrijden (thuis – uit)</th><th>Resultaat</th><th></th></tr>` +
    DATES.map((d, i) => {
      const p = PLANS.get(d.date);
      const resTxt = !p ? "" : p.error ? `<td class="res-bad">${esc(p.error)}</td>`
        : `<td class="${p.summary.unscheduled ? "res-bad" : "res-ok"}">${p.summary.solved ? `${p.summary.scheduled} ingepland, ${p.summary.unscheduled} niet` : "geen oplossing binnen rekentijd"}${p.summary.hard != null ? ` · validator HARD ${p.summary.hard}` : ""}</td>`;
      return `<tr><td>${esc(d.date)}</td><td>${esc(d.weekday)}</td><td class="num">${d.fixtures}</td><td class="num">${d.partijen}</td>
        <td class="wed">${d.wedstrijden.map((w) => `<b>${esc(w.label)}</b> ${esc(w.home)} – ${esc(w.away)}`).join("<br>")}</td>
        ${resTxt || "<td></td>"}
        <td><button class="btn2" data-plan="${i}">Plan live</button>${p && !p.error ? ` <button class="btn2" data-show="${i}">Bekijk</button>` : ""}</td></tr>`;
    }).join("");
  for (const b of $("dates").querySelectorAll("button[data-plan]")) b.onclick = () => planDay(DATES[+b.dataset.plan].date, true);
  for (const b of $("dates").querySelectorAll("button[data-show]")) b.onclick = () => showPlan(DATES[+b.dataset.show].date);
}

async function planDay(date, show) {
  status(`${date} live plannen…`, "busy");
  try {
    const p = await api("/plan", jsonOpts("POST", { club: CLUB.id, date, time_limit_s: +$("tl").value }));
    PLANS.set(date, p);
    status(`${date}: ${p.summary.scheduled} ingepland, ${p.summary.unscheduled} niet (${p.live.wall_time_s}s).`, p.summary.unscheduled ? "warn" : "ok");
    if (show) showPlan(date);
  } catch (e) {
    PLANS.set(date, { error: e.message });
    status(`${date}: ${e.message}`, "err");
  }
  renderDates();
}

async function planAll() {
  $("plan-all").disabled = true;
  for (const d of DATES) await planDay(d.date, false);
  $("plan-all").disabled = false;
  status(`Alle ${DATES.length} speeldagen gepland.`, "ok");
}

function showPlan(date) {
  const plan = PLANS.get(date);
  const s = CLUB.summary;
  $("plan-sec").hidden = false;
  $("plan-title").textContent = `Baanschema ${s.name} — ${date}`;
  const v = plan.validator || {};
  const card = (k, val, cls = "") => `<div class="card"><div class="k">${k}</div><div class="v ${cls}">${esc(val)}</div></div>`;
  $("summary").innerHTML = [card("Ingepland", plan.summary.scheduled, "good"),
    card("Niet ingepland", plan.summary.unscheduled, plan.summary.unscheduled ? "bad" : "good"),
    card("Validator HARD", v.hard ?? "–", v.hard ? "bad" : "good"), card("Dagstart", plan.day_start),
    card("Rekentijd", `${plan.stats.solve_time_s}s`), card("Solver", plan.status)].join("");
  const placed = plan.rows.filter((r) => r.start !== "NIET_GELUKT" && r.court);
  const startMin = Math.min(toMin(s.day.fallback_start || s.day.start), ...placed.map((r) => toMin(r.start)));
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
    for (let k = 1; k <= plan.courts; k++) html.push(`<div class="cell${m % 60 === 45 ? " hour" : ""}" style="grid-row:${i + 2};grid-column:${k + 1}"></div>`);
  }
  const COL = teamColors(plan.rows);
  const teams = new Map();
  for (const r of placed) {
    const r0 = (toMin(r.start) - startMin) / 15 + 2, r1 = (toMin(r.end) - startMin) / 15 + 2;
    const isRes = r.kind === "W";
    const c = COL.get(r.team_id) || { bg: "#ddd", fg: "#111" };
    if (!isRes) teams.set(r.team_id, r);
    const rc = COL.get(`__res_${r.category}`);
    const style = isRes ? (rc ? `background:repeating-linear-gradient(45deg, ${rc.bg}, ${rc.bg} 6px, #fff 6px, #fff 12px)` : "")
      : `background:${c.bg};color:${c.fg}`;
    html.push(`<div class="blk${isRes ? " res" : ""}" style="grid-row:${r0}/${r1};grid-column:${r.court + 1};${style}" title="${esc(r.team)}">
      <span class="cat">${esc(r.label || r.category)}</span><b>${esc(r.part || "reservering")}</b><div>${esc(isRes ? "baanreservering" : r.home_team || "")}</div><div class="t">${esc(r.start)}–${esc(r.end)}</div></div>`);
  }
  g.innerHTML = html.join("");
  $("legend").innerHTML = [...teams.values()].sort((a, b) => (a.category || "").localeCompare(b.category || ""))
    .map((r) => `<span style="background:${COL.get(r.team_id).bg};color:${COL.get(r.team_id).fg}" title="${esc(r.team)}">${esc(r.label || "")} ${esc(r.home_team || "")}</span>`).join("");
  const un = plan.rows.filter((r) => r.start === "NIET_GELUKT");
  $("unscheduled").innerHTML = un.length ? `<h3>Niet ingepland</h3><ul class="plain">${un.map((r) => `<li><b>${esc(r.part)}</b> · ${esc(r.label || "")} ${esc(r.home_team || "")} – ${esc(r.away_team || "")}</li>`).join("")}</ul>` : "";
  $("print-btn").onclick = () => printPlan(plan, { clubName: s.name, date, dayStart: s.day.fallback_start || s.day.start, dayEnd: s.day.end, note: "live berekend" });
  $("plan-sec").scrollIntoView({ behavior: "smooth" });
}

// ---------------------------------------------------------------- init

async function init() {
  $("club").onchange = loadClub;
  $("save").onclick = save;
  $("upload").onclick = upload;
  $("plan-all").onclick = planAll;
  $("new-btn").onclick = () => { $("new-sec").hidden = false; $("new-name").focus(); };
  $("new-cancel").onclick = () => { $("new-sec").hidden = true; };
  $("new-create").onclick = createClub;
  try { await loadClubs(); } catch (e) { status(`Server niet bereikbaar (${API}): ${e.message}`, "err"); }
}
init();
