"use strict";
// Baanschemaatje web-GUI: leest vooraf berekende plannen uit ./data/.
// Geen build-stap, geen externe bibliotheken; alle paden zijn relatief.
// Optioneel: "Live berekenen" rekent de speeldag opnieuw via de live-backend
// (server/baanschemaatje, Cloud Run). Is die onbereikbaar, dan blijven de
// vooraf berekende plannen gewoon staan.

// Live-backend. Overschrijfbaar met ?api=<url> (bv. ?api=http://localhost:8080).
const LIVE_API_DEFAULT = "https://baanschemaatje-356953092000.europe-west1.run.app";
const LIVE_API = (new URLSearchParams(location.search).get("api") || LIVE_API_DEFAULT).replace(/\/+$/, "");

const CAT = {
  rood: { label: "Rood", short: "ROOD" },
  oranje: { label: "Oranje", short: "ORA" },
  groen: { label: "Groen", short: "GRO" },
  junioren_11_14: { label: "Junioren 11–14", short: "JU11-14" },
  jeugd_13_17: { label: "Jeugd 13–17", short: "13-17" },
  gemengd: { label: "Gemengd", short: "GEM" },
  senioren: { label: "Senioren", short: "SEN" },
  overig: { label: "Overig", short: "OV" },
};
const RULE_NL = {
  match_start_grid: "Begintijd op hele/halve uren",
  match_start_window: "Begintijd wedstrijd",
  junioren_start_window: "Junioren (Groen + 11–14): begintijd",
  junioren_latest_start: "Junioren: begintijd uiterlijk",
  junioren_mixed_8p_latest_start: "Gemengd 8p junioren: begintijd uiterlijk",
  mixed_8p_latest_start: "Gemengd 8p: begintijd uiterlijk",
  travel_not_before: "Reisafstand ≥ X km: niet vóór",
  min_reservation: "Minimale reservering per partij",
  start_window_8p: "8-partijenteams: begintijd",
  mixed_8p_not_before: "Gemengd 8p: niet vóór",
  youth_last_start: "Jeugd: laatste start uiterlijk",
  first_start_deadline: "Eerste partij elk team uiterlijk",
  max_wait_minutes: "Max wachttijd tussen partijen",
  max_blocks_per_team: "Max speelblokken per team",
  waterfall_8p: "8p: strikte S → D → GD",
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const toMin = (hhmm) => parseInt(hhmm.slice(0, 2), 10) * 60 + parseInt(hhmm.slice(3, 5), 10);
const toHHMM = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

let INDEX = null;
const cache = new Map();

function hue(str) {
  let h = 0;
  for (const ch of str) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % 360;
}
function teamColor(id) { return `hsl(${hue(id)}, 65%, 80%)`; }

// Label per rij: uit de export (J13-17 / M13-17 / ...), anders uit de categorie.
function rowLabel(r) { return r.label || (CAT[r.category] || CAT.overig).short; }

function shortTeam(row) {
  const s = row.team || "";
  const m = s.match(/(\d+e klasse|Hoofdklasse|Groen \d+|Rood \d+|Oranje \d+)/i);
  const cls = m ? m[1].replace(" klasse", "") : "";
  const home = (row.home_team || "").trim();
  return [cls, home].filter(Boolean).join(" · ") || s;
}

function params(r) {
  const p = r.params || {};
  if (r.name === "min_reservation") return "90 min (Junioren 11–14: 45 min)";
  if (r.name === "match_start_grid") return `elke ${p.value} min`;
  if (r.name === "travel_not_before") return `${p.value} km → ${p.time}`;
  if ("from" in p) return `${p.from} – ${p.to}`;
  if ("time" in p) return p.time;
  if ("value" in p) return r.name === "max_wait_minutes" ? `${p.value} min` : String(p.value);
  return "aan";
}

async function getJSON(path) {
  if (cache.has(path)) return cache.get(path);
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  const data = await res.json();
  cache.set(path, data);
  return data;
}

function club() { return INDEX.clubs.find((c) => c.id === $("club").value); }

function fillDates(keep) {
  const c = club();
  $("date").innerHTML = c.dates.map((d) =>
    `<option value="${esc(d.date)}">${esc(d.date)} — ${d.scheduled} ingepland${d.unscheduled ? `, ${d.unscheduled} niet` : ""}</option>`).join("");
  if (keep && c.dates.some((d) => d.date === keep)) $("date").value = keep;
}

function updateHash() {
  history.replaceState(null, "", `#${encodeURIComponent($("club").value)}/${encodeURIComponent($("date").value)}`);
}

async function render() {
  const c = club();
  const d = c.dates.find((x) => x.date === $("date").value);
  updateHash();
  renderDays(c);
  renderProfile(c);
  $("note").textContent = `${c.name} · ${c.courts} banen · seizoen ${INDEX.season_file} · berekend ${new Date(INDEX.generated_at).toLocaleString("nl-NL")} (tijdslimiet ${INDEX.time_limit_s}s per poging)`;
  let plan;
  try {
    plan = await getJSON(`data/${d.file}`);
  } catch (e) {
    $("grid").innerHTML = `<p class="note">Kon plan niet laden: ${esc(e.message)}</p>`;
    return;
  }
  CURRENT = { c, d, plan };
  setLive("");
  showPlan(plan, null);
  renderSolutions(c, d);
}

let CURRENT = null;

// Toon een plan (het voorstel of een oplossingsscenario) in kaarten, grid en lijsten.
function showPlan(plan, scenario) {
  const { c, d } = CURRENT;
  const v = plan.validator || {};
  const dd = scenario
    ? { ...d, scheduled: scenario.scheduled, unscheduled: scenario.unscheduled, solve_time_s: scenario.solve_time_s,
        fixtures: d.fixtures - (scenario.moved_wedstrijden || 0) }
    : d;
  renderSummary(c, dd, plan);
  renderGrid(c, plan);
  renderUnscheduled(plan);
  renderFindings(plan);
  const vw = $("viewing");
  if (scenario && scenario.live) {
    vw.hidden = false;
    vw.innerHTML = `Je bekijkt een <b>live berekend</b> plan (${esc(scenario.title)}) — geen gepubliceerd schema.<button id="back">Terug naar vooraf berekend</button>`;
    $("back").onclick = () => { showPlan(CURRENT.plan, null); renderSolutions(CURRENT.c, CURRENT.d); };
  } else if (scenario) {
    vw.hidden = false;
    vw.innerHTML = `Je bekijkt oplossing <b>#${scenario.rank}: ${esc(scenario.title)}</b> — geen gepubliceerd schema.<button id="back">Terug naar voorstel</button>`;
    $("back").onclick = () => showPlan(CURRENT.plan, null);
  } else {
    vw.hidden = true;
  }
}

async function renderSolutions(c, d) {
  const sec = $("solutions-sec");
  if (!d.solutions_file) { sec.hidden = true; return; }
  sec.hidden = false;
  $("solutions").innerHTML = `<p class="note">Oplossingen laden…</p>`;
  let data;
  try { data = await getJSON(`data/${d.solutions_file}`); } catch (e) {
    $("solutions").innerHTML = `<p class="note">Kon oplossingen niet laden: ${esc(e.message)}</p>`; return;
  }
  renderSolutionList(data.solutions);
}

function renderSolutionList(sols, live = false) {
  const best = sols.find((s) => s.fits && s.knltb_ok);
  const kindNL = { rekentijd: "rekentijd", clubafspraak: "clubafspraak", productdefault: "productdefault",
    dagindeling: "dagindeling", inhaaldag: "inhaaldag", combinatie: "combinatie", "niet-knltb": "mag niet (KNLTB)" };
  const reco = best
    ? `<div class="reco">Aanbevolen: <b>${esc(best.title)}</b> — alle ${best.scheduled} partijen passen, KNLTB-conform${best.moved_wedstrijden ? `, ${best.moved_wedstrijden} wedstrijd verplaatst` : ""}.</div>`
    : `<div class="reco" style="background:#fdecea;border-color:#f3c2bd">Geen enkele doorgerekende KNLTB-conforme versoepeling laat alles passen binnen de rekentijd. Overweeg een wedstrijd naar een inhaaldag of meer banen.</div>`;
  const rows = sols.map((s, i) => `<tr class="sol${s === best ? " best" : ""}${s.kind === "niet-knltb" ? " ref" : ""}">
      <td class="num">${s.rank}</td><td style="white-space:normal;min-width:220px">${esc(s.title)}</td>
      <td><span class="tag ${s.kind === "clubafspraak" ? "club" : s.kind === "niet-knltb" ? "" : "product"}">${esc(kindNL[s.kind] || s.kind)}</span></td>
      <td>${s.fits ? '<span class="yes">ja</span>' : '<span class="no">nee</span>'}</td>
      <td class="num">${s.scheduled}</td><td class="num">${s.unscheduled}</td>
      <td>${s.knltb_ok ? '<span class="yes">ja</span>' : '<span class="no">nee</span>'}</td>
      <td class="num">${s.validator_hard ?? "–"}</td>
      <td><button data-i="${i}">Bekijk</button></td></tr>`).join("");
  $("solutions").innerHTML = (live ? `<p class="note">Live doorgerekend op de server.</p>` : "") + reco + `<div class="tablewrap"><table>
    <tr><th>#</th><th>Versoepeling</th><th>Soort</th><th>Past alles</th><th>Ingepland</th><th>Niet</th><th>KNLTB-conform</th><th>HARD (ops-validator)</th><th></th></tr>${rows}</table></div>
    <p class="hint">"HARD (ops-validator)" toetst aan de operationele SPEC.md inclusief de huidige clubafspraken; een versoepelde clubafspraak telt daar dus als HARD, ook als het KNLTB-conform is.</p>`;
  for (const b of $("solutions").querySelectorAll("button[data-i]")) {
    b.onclick = () => { const s = sols[+b.dataset.i]; showPlan(s.plan, s); $("viewing").scrollIntoView({ behavior: "smooth" }); };
  }
}

function renderSummary(c, d, plan) {
  const v = plan.validator || {};
  const card = (k, val, cls = "") => `<div class="card"><div class="k">${k}</div><div class="v ${cls}">${esc(val)}</div></div>`;
  $("summary").innerHTML = [
    card("Ingepland", d.scheduled, "good"),
    card("Niet ingepland", d.unscheduled, d.unscheduled ? "bad" : "good"),
    card("Validator HARD", v.hard ?? "–", v.hard ? "bad" : "good"),
    card("Validator MODEL", v.model ?? "–", v.model ? "warn" : ""),
    card("Dagstart", plan.day_start),
    card("Wedstrijden", d.fixtures),
    card("Rekentijd", `${d.solve_time_s}s`),
    card("Solver", plan.status),
  ].join("");
}

function renderGrid(c, plan) {
  const placed = plan.rows.filter((r) => r.start !== "NIET_GELUKT" && r.court);
  const startMin = Math.min(toMin(c.day.fallback_start || c.day.start), ...placed.map((r) => toMin(r.start)));
  const endMin = Math.max(toMin(c.day.end), ...placed.map((r) => toMin(r.end)));
  const nSlots = (endMin - startMin) / 15;
  const g = $("grid");
  g.style.gridTemplateColumns = `56px repeat(${c.courts}, minmax(112px, 1fr))`;
  g.style.gridTemplateRows = `auto repeat(${nSlots}, var(--row))`;
  const html = [`<div class="hdr corner" style="grid-row:1;grid-column:1">tijd</div>`];
  for (let k = 1; k <= c.courts; k++) html.push(`<div class="hdr" style="grid-row:1;grid-column:${k + 1}">Baan ${k}</div>`);
  for (let i = 0; i < nSlots; i++) {
    const m = startMin + i * 15;
    const hour = m % 60 === 45;
    const lbl = m % 30 === 0 ? toHHMM(m) : "";
    html.push(`<div class="time${m % 60 === 0 ? " hour" : ""}" style="grid-row:${i + 2};grid-column:1">${lbl}</div>`);
    for (let k = 1; k <= c.courts; k++) html.push(`<div class="cell${hour ? " hour" : ""}" style="grid-row:${i + 2};grid-column:${k + 1}"></div>`);
  }
  const teams = new Map();
  for (const r of placed) {
    const r0 = (toMin(r.start) - startMin) / 15 + 2;
    const r1 = (toMin(r.end) - startMin) / 15 + 2;
    const cat = CAT[r.category] || CAT.overig;
    const isRes = r.kind === "W";
    const tip = `${r.team}\n${r.home_team || ""}${r.away_team ? " – " + r.away_team : ""}\n${r.part || "reservering"} · ${r.start}–${r.end} · baan ${r.court}`;
    const bg = isRes ? "" : `background:${teamColor(r.team_id)}`;
    if (!isRes) teams.set(r.team_id, r);
    html.push(`<div class="blk${isRes ? " res" : ""}" title="${esc(tip)}" style="grid-row:${r0}/${r1};grid-column:${r.court + 1};${bg}">
      <span class="cat">${esc(rowLabel(r))}</span><b>${esc(r.part || (isRes ? cat.label : ""))}</b>
      <div>${esc(isRes ? "baanreservering" : shortTeam(r))}</div>
      <div class="t">${esc(r.start)}–${esc(r.end)}</div></div>`);
  }
  g.innerHTML = html.join("");
  $("legend").innerHTML = [...teams.values()]
    .sort((a, b) => a.team.localeCompare(b.team))
    .map((r) => `<span style="background:${teamColor(r.team_id)}" title="${esc(r.team)}">${esc(rowLabel(r))} ${esc(shortTeam(r))}</span>`)
    .join("");
}

function renderUnscheduled(plan) {
  const un = plan.rows.filter((r) => r.start === "NIET_GELUKT");
  $("unscheduled").innerHTML = un.length
    ? `<ul class="plain">${un.map((r) => `<li><b>${esc(r.part)}</b> · ${esc(rowLabel(r))} ${esc(shortTeam(r))}<br><span class="hint">${esc(r.team)}</span></li>`).join("")}</ul>`
    : `<p class="empty">Alle partijen zijn ingepland.</p>`;
}

function renderFindings(plan) {
  const v = plan.validator || {};
  if (!v.available) { $("findings").innerHTML = `<p class="note">Geen validatorrapport.</p>`; return; }
  const f = v.findings || [];
  if (!f.length) { $("findings").innerHTML = `<p class="empty">Geen bevindingen.</p>`; return; }
  const item = (x) => `<li><span class="sev ${esc(x.severity)}">${esc(x.severity)}</span><b>${esc(x.rule)}</b> · ${esc(x.subject || "")}<br>${esc(x.message)}</li>`;
  const hard = f.filter((x) => x.severity === "HARD");
  const model = f.filter((x) => x.severity !== "HARD");
  $("findings").innerHTML =
    (hard.length ? `<ul class="plain">${hard.map(item).join("")}</ul>` : `<p class="empty">Geen HARD-overtredingen.</p>`) +
    (model.length ? `<details><summary>${model.length} MODEL-bevinding(en) tonen</summary><ul class="plain">${model.map(item).join("")}</ul></details>` : "");
}

function renderDays(c) {
  const sel = $("date").value;
  $("days").innerHTML =
    `<tr><th>Speeldag</th><th>Wedstrijden</th><th>Ingepland</th><th>Niet</th><th>Dagstart</th><th>HARD</th><th>MODEL</th><th>Rekentijd</th><th>Oplossing</th></tr>` +
    c.dates.map((d) => `<tr class="click${d.date === sel ? " sel" : ""}" data-date="${esc(d.date)}">
      <td>${esc(d.date)}</td><td class="num">${d.fixtures}</td><td class="num">${d.scheduled}</td>
      <td class="num" style="${d.unscheduled ? "color:var(--hard);font-weight:600" : ""}">${d.unscheduled}</td>
      <td>${esc(d.day_start)}</td>
      <td class="num" style="${d.hard ? "color:var(--hard);font-weight:600" : ""}">${d.hard ?? "–"}</td>
      <td class="num">${d.model ?? "–"}</td><td class="num">${d.solve_time_s}s</td>
      <td style="white-space:normal">${d.unscheduled ? esc(d.best_solution || (d.solutions_file ? "geen passende gevonden" : "–")) : ""}</td></tr>`).join("");
  for (const tr of $("days").querySelectorAll("tr.click")) {
    tr.onclick = () => { $("date").value = tr.dataset.date; render(); window.scrollTo({ top: 0, behavior: "smooth" }); };
  }
}

function renderProfile(c) {
  const res = Object.entries(c.reservations || {});
  const resTxt = res.length
    ? res.map(([k, v]) => `${esc(CAT[k]?.label || k)}: baan ${v.courts.join(", ")}${v.courts_if_rood ? ` (als Rood ook speelt: ${v.courts_if_rood.join(", ")})` : ""}`).join("<br>")
    : "geen vaste reserveringen (solver kiest banen)";
  const durs = Object.entries(c.durations).filter(([k]) => k !== "overig")
    .map(([k, v]) => `${esc(CAT[k]?.label || k)} ${v}`).join(" · ");
  const rows = c.rules.map((r) => {
    const tag = r.club_override ? `<span class="tag club">clubafspraak</span>`
      : r.source === "product" ? `<span class="tag product">productdefault</span>` : `<span class="tag knltb">KNLTB</span>`;
    const core = r.club_override ? `${esc(params({ ...r, params: r.core_params }))}${r.core_hard ? "" : " (zacht)"}` : "";
    return `<tr><td>${esc(RULE_NL[r.name] || r.name)}</td><td><b>${esc(params(r))}</b></td><td>${r.hard ? "hard" : "zacht"}</td>
      <td>${tag}</td><td>${core}</td><td class="hint">${esc(r.source === "product" ? "Baanschemaatje" : r.source)}</td></tr>`;
  }).join("");
  $("profile").innerHTML = `
    <div class="cards">
      <div class="card"><div class="k">Club</div><div class="v">${esc(c.name)}</div></div>
      <div class="card"><div class="k">Banen</div><div class="v">${c.courts}</div></div>
      <div class="card"><div class="k">Dagstart</div><div class="v">${esc(c.day.start)}${c.day.fallback_start ? ` <small>(terugval ${esc(c.day.fallback_start)})</small>` : ""}</div></div>
      <div class="card"><div class="k">Laatste start / einde</div><div class="v">${esc(c.day.last_start)} / ${esc(c.day.end)}</div></div>
    </div>
    <p><b>Baanreserveringen:</b> ${resTxt}<br>
    <b>Baantoewijzing:</b> max ${c.max_courts_per_team} banen per team${c.court_pairs ? `; vaste baanparen ${c.court_pairs.map((p) => p.join("+")).join(", ")}` : ""}${c.preferred_courts_8p.length ? `; 8p-teams bij voorkeur op baan ${c.preferred_courts_8p.join(", ")}` : ""}<br>
    <b>Verwachte speelduur (min, KNLTB-default):</b> ${durs}</p>
    <div class="tablewrap"><table>
      <tr><th>Regel</th><th>Waarde</th><th>Hard/zacht</th><th>Soort</th><th>KNLTB/core-default</th><th>Bron</th></tr>${rows}
    </table></div>
    <p class="hint">Clubafspraken mogen strenger zijn dan het KNLTB-reglement, niet ruimer. KNLTB = Competitiereglement (vastgesteld 11-11-2025), Bijlage 3.</p>`;
}

// ---------------------------------------------------------------- live

function setLive(msg, cls = "") {
  const el = $("live-status");
  el.className = `live-status ${cls}`;
  el.textContent = msg;
}

async function livePost(path, body) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 590000);
  try {
    const res = await fetch(`${LIVE_API}${path}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: ctl.signal,
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { detail += `: ${(await res.json()).detail}`; } catch (_) { /* geen JSON */ }
      throw new Error(detail);
    }
    return await res.json();
  } finally { clearTimeout(t); }
}

async function livePlan() {
  if (!CURRENT) return;
  const { c, d } = CURRENT;
  const tl = +$("live-tl").value;
  const btn = $("live-btn");
  btn.disabled = true;
  setLive(`Bezig met live rekenen (${c.name}, ${d.date}, max ${tl}s per poging; eerste aanroep kan ~10s extra kosten)…`, "busy");
  const t0 = performance.now();
  try {
    const plan = await livePost("/plan", { club: c.id, date: d.date, time_limit_s: tl });
    if (CURRENT.d.date !== d.date || CURRENT.c.id !== c.id) return; // gebruiker is doorgeklikt
    const s = plan.summary;
    if (!s.solved) {
      setLive(`Live: geen oplossing gevonden binnen ${tl}s per poging (solver: ${plan.status}). Probeer een langere rekentijd. Het vooraf berekende plan blijft getoond.`, "warn");
      return;
    }
    showPlan(plan, { live: true, title: `${s.scheduled} ingepland, ${s.unscheduled} niet, ${plan.stats.solve_time_s}s rekentijd`,
      scheduled: s.scheduled, unscheduled: s.unscheduled, solve_time_s: s.solve_time_s, moved_wedstrijden: 0 });
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    setLive(`Live berekend in ${secs}s${plan.cached ? " (uit cache)" : ""}: ${s.scheduled} ingepland, ${s.unscheduled} niet ingepland.`, s.unscheduled ? "warn" : "ok");
    const sec = $("solutions-sec");
    if (s.unscheduled) {
      sec.hidden = false;
      $("solutions").innerHTML = `<p class="note">Live plan past niet volledig. <button id="live-sol">Oplossingen live zoeken</button> (kan 3–5 minuten duren; korte rekentijd per scenario, dus indicatief)</p>`;
      $("live-sol").onclick = () => liveScenarios(c, d, tl);
    }
  } catch (e) {
    setLive(`Live server niet bereikbaar of fout (${e.name === "AbortError" ? "time-out" : e.message}). Het vooraf berekende plan blijft getoond.`, "err");
  } finally { btn.disabled = false; }
}

async function liveScenarios(c, d, tl) {
  $("solutions").innerHTML = `<p class="note">Oplossingen worden live doorgerekend…</p>`;
  try {
    const data = await livePost("/scenarios", { club: c.id, date: d.date, time_limit_s: tl });
    if (CURRENT.d.date !== d.date || CURRENT.c.id !== c.id) return;
    if (!data.solutions.length && data.base_solved) { $("solutions").innerHTML = `<p class="empty">Deze dag past al volledig.</p>`; return; }
    renderSolutionList(data.solutions, true);
  } catch (e) {
    $("solutions").innerHTML = `<p class="note">Live oplossingen mislukt (${esc(e.message)}).</p>`;
  }
}

async function init() {
  try {
    INDEX = await getJSON("data/index.json");
  } catch (e) {
    $("note").textContent = `Kon data/index.json niet laden (${e.message}). Draai: python -m baanschemaatje build-web`;
    return;
  }
  $("club").innerHTML = INDEX.clubs.map((c) => `<option value="${esc(c.id)}">${esc(c.name)} (${c.courts} banen)</option>`).join("");
  const [hc, hd] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (hc && INDEX.clubs.some((c) => c.id === hc)) $("club").value = hc;
  fillDates(hd);
  $("club").onchange = () => { fillDates($("date").value); render(); };
  $("date").onchange = render;
  $("live-btn").onclick = livePlan;
  $("live-btn").title = `Rekent deze speeldag opnieuw op ${LIVE_API}`;
  render();
}
init();
