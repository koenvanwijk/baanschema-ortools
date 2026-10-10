"use strict";
// Baanschemaatje club-instellingen: profiel, dagvensters per weekdag, regels/clubafspraken, KNLTB-import.
// Helpers in common.js. Het seizoensoverzicht en de dagweergave staan op club.html.

let WD_IN_SEASON = new Set();
const WD_ALL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"];

async function loadClub() {
  const id = $("club").value;
  setHash(id);
  $("back-club").href = `club.html${location.search}#${encodeURIComponent(id)}`;
  status("Club laden…", "busy");
  CLUB = await api(`/clubs/${encodeURIComponent(id)}`);
  fillForm();
  await loadSeason();
  status("");
}
async function loadClubs(select) { await loadClubList(select); await loadClub(); }

// Dagvensters per weekdag: alleen weekdagen in het seizoen + do/vr (avond) worden getoond.
function renderWeekdays(wds) {
  const raw = (CLUB.profile && CLUB.profile.weekdays) || {};
  const show = WD_ALL.filter((wd) => WD_IN_SEASON.has(wd) || raw[wd] || wd === "donderdag" || wd === "vrijdag");
  const cell = (wd, k, type, v) => {
    const isD = (wds[wd] && (wds[wd].defaults || []).includes(k));
    const inp = type === "checkbox" ? `<input type="checkbox" data-wd="${wd}" data-k="${k}" ${v ? "checked" : ""}>`
      : `<input type="${type}" ${type === "time" ? 'step="900"' : `min="1" max="${CLUB.summary.courts}"`} data-wd="${wd}" data-k="${k}" value="${esc(type === "time" && v ? toHHMM(toMin(v) % 1440) : v ?? "")}">`;
    const next = type === "time" && v && toMin(v) >= 1440 ? ' <span class="hint">volgende dag</span>' : "";
    return `<td>${inp}${next}${isD ? ' <span class="dflt" title="Standaardwaarde, nog niet door de club bevestigd">standaard</span>' : ' <span class="hint" title="Door de club ingesteld">✓ bevestigd</span>'}</td>`;
  };
  $("weekdays").innerHTML = `<tr><th>Weekdag</th><th>Dagstart</th><th>Laatste start</th><th>Alles klaar om</th><th>Banen</th><th>Verlichting</th><th>Regels</th></tr>` +
    show.map((wd) => {
      const w = wds[wd] || {};
      const b3 = w.bijlage3;
      return `<tr><td><b>${wd}</b>${WD_IN_SEASON.has(wd) ? "" : ' <span class="hint">(geen wedstrijden)</span>'}</td>` +
        (b3 ? `<td colspan="3" class="hint">algemene dagstart/laatste start/einde (hierboven)</td>` :
          cell(wd, "start", "time", w.start) + cell(wd, "last_start", "time", w.last_start) + cell(wd, "end", "time", w.end)) +
        cell(wd, "courts", "number", w.courts) + cell(wd, "lighting", "checkbox", w.lighting) +
        `<td class="hint">${b3 ? "KNLTB Bijlage 3" : "avond: begintijd 19:00–20:00 (KNLTB)"}</td></tr>`;
    }).join("");
  for (const el of $("weekdays").querySelectorAll("input")) el.disabled = !CLUB.editable;
}

// Alleen waarden die de club heeft opgegeven of veranderd, worden opgeslagen (de rest blijft standaard).
function readWeekdays() {
  const raw = JSON.parse(JSON.stringify((CLUB.profile && CLUB.profile.weekdays) || {}));
  const eff = CLUB.summary.weekdays || {};
  for (const el of $("weekdays").querySelectorAll("input")) {
    const wd = el.dataset.wd, k = el.dataset.k;
    const v = el.type === "checkbox" ? el.checked : el.type === "number" ? (el.value ? parseInt(el.value, 10) : null) : el.value;
    let cur = (eff[wd] || {})[k];
    if (el.type === "time" && cur) cur = toHHMM(toMin(cur) % 1440);
    const wasSet = raw[wd] && k in raw[wd];
    if (wasSet || (v !== cur && v !== null && v !== "")) { raw[wd] = raw[wd] || {}; raw[wd][k] = v; }
  }
  return raw;
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
  renderWeekdays(s.weekdays || {});
  for (const el of document.querySelectorAll('[id^="f-"], #rules input, #weekdays input')) el.disabled = !CLUB.editable;
  $("save").disabled = !CLUB.editable;
  $("upload").disabled = !CLUB.editable;
  $("reprocess").disabled = !CLUB.editable;
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
  const wds = readWeekdays();
  if (Object.keys(wds).length) raw.weekdays = wds; else delete raw.weekdays;
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
  WD_IN_SEASON = new Set(DATES.map((d) => d.weekday));
  renderWeekdays(CLUB.summary.weekdays || {});
  const s = j.season || {};
  const rep = s.report;
  $("season-info").innerHTML = j.own_season
    ? `<p><b>Eigen seizoen:</b> ${esc(s.filename)} (geüpload ${s.uploaded_at ? new Date(s.uploaded_at).toLocaleString("nl-NL") : "–"})${rep ? ` · ${esc(rep.format)} · ${rep.imported} thuiswedstrijden overgenomen van ${rep.rows_in_file} regels` : ""}</p>${rep ? reportHtml(rep) : ""}`
    : `<p class="hint">Nog geen eigen seizoen; het standaardseizoen (${esc(s.filename || "")}) wordt gebruikt.</p>`;
}

function reportHtml(rep) {
  const sk = Object.entries(rep.skipped || {}).map(([k, v]) => `${esc(k)}: ${v}`).join(" · ");
  const un = Object.entries(rep.unknown_schemas || {}).map(([k, v]) => `${esc(k)} (${v}×)`).join(", ");
  const wd = Object.entries(rep.per_weekday || {}).map(([k, v]) => `${esc(k)} ${v}`).join(" · ");
  const comp = Object.entries(rep.per_competition || {}).map(([k, v]) => `<li>${esc(k)}: ${v}</li>`).join("");
  const part = (rep.played_partial || []).map((x) => `<li>${esc(x)}</li>`).join("");
  const exp = (rep.expired_no_result || []).map((x) => `<li>${esc(x)}</li>`).join("");
  return `<p class="hint">Per weekdag: ${wd || "–"}${rep.played != null ? ` · <b>${rep.played} gespeeld</b> (vast) · ${rep.open} nog te spelen` : ""}<br>Overgeslagen: ${sk || "niets"}${un ? `<br><b>Onbekend formaat (niet ingepland):</b> ${un}` : ""}</p>
    ${comp ? `<details><summary>Per competitie</summary><ul class="plain">${comp}</ul></details>` : ""}
    ${part ? `<details open><summary>Gespeeld maar onvolledig (minder partijen in de uitslag)</summary><ul class="plain">${part}</ul></details>` : ""}
    ${exp ? `<details open><summary>Datum voorbij, geen uitslag (wel planbaar)</summary><ul class="plain">${exp}</ul></details>` : ""}`;
}

async function upload() {
  const f = $("file").files[0];
  if (!f) { status("Kies eerst een bestand.", "err"); return; }
  status(`"${f.name}" uploaden en verwerken…`, "busy");
  try {
    const j = await api(`/clubs/${encodeURIComponent(CLUB.id)}/season?filename=${encodeURIComponent(f.name)}`,
      { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: await f.arrayBuffer() });
    await loadClub();
    status(`${j.report.imported} thuiswedstrijden op ${j.dates.length} dagen gevonden (${j.report.played || 0} gespeeld).`, "ok");
  } catch (e) { status(`Upload mislukt: ${e.message}`, "err"); }
}

async function reprocess() {
  status("Laatste upload opnieuw verwerken…", "busy");
  try {
    const j = await api(`/clubs/${encodeURIComponent(CLUB.id)}/season/reprocess`, { method: "POST" });
    await loadClub();
    status(`Opnieuw verwerkt: ${j.report.imported} thuiswedstrijden op ${j.dates.length} dagen (${j.report.played || 0} gespeeld).`, "ok");
  } catch (e) { status(`Opnieuw verwerken mislukt: ${e.message}`, "err"); }
}

// ---------------------------------------------------------------- plannen

async function init() {
  $("club").onchange = loadClub;
  $("save").onclick = save;
  $("upload").onclick = upload;
  $("reprocess").onclick = reprocess;
  $("new-btn").onclick = () => { $("new-sec").hidden = false; $("new-name").focus(); };
  $("new-cancel").onclick = () => { $("new-sec").hidden = true; };
  $("new-create").onclick = createClub;
  try { await loadClubs(); } catch (e) { status(`Server niet bereikbaar (${API}): ${e.message}`, "err"); }
}
init();
