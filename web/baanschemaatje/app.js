"use strict";
// Baanschemaatje web-GUI: leest vooraf berekende plannen uit ./data/.
// Geen build-stap, geen externe bibliotheken; alle paden zijn relatief.
// Optioneel: "Nu berekenen" rekent de speeldag opnieuw via de live-backend
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

// Teamkleuren: zie colors.js (teamColors).

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

let CUR_DATE = null; // null = seizoensoverzicht

// Verzettingen per club (verzetten.js) en "Nu berekend"-plannen per club/dag (met de verzettingen van dat moment).
const MOVES = new Map();
const LIVE = new Map();
function mv() { const id = club().id; if (!MOVES.has(id)) MOVES.set(id, new MoveState()); return MOVES.get(id); }

// Plan van een dag zoals het nu is: nu berekend (als de verzettingen nog kloppen), anders vooraf berekend
// met de verzettingen erop. changed = er zijn wedstrijden naartoe verzet en nog niet berekend.
async function dayPlan(c, date) {
  const live = LIVE.get(`${c.id}/${date}`);
  if (live && live.sig === mv().sig(date)) return { plan: live.plan, changed: false, live: true };
  const d = c.dates.find((x) => x.date === date);
  let base = null;
  if (d) base = await getJSON(`data/${d.file}`).catch(() => null);
  const known = !!base;
  base = base || { status: "", day_start: c.day.start, courts: c.courts, rows: [], validator: {}, stats: { solve_time_s: "–" } };
  const plan = mv().touches(date) ? mvApplyPlan(base, date, mv()) : base;
  return { plan, changed: mv().into(date).length > 0, known };
}

function renderMoveBars() {
  for (const id of ["mv-bar-ov", "mv-bar-day"]) {
    const el = $(id);
    if (!el) continue;
    el.innerHTML = mvBarHtml(mv(), "Deze voorbeeldpagina bewaart niets: verzettingen gelden alleen in dit tabblad. Opslaan doe je op de clubpagina.");
    const u = el.querySelector(".mv-undo"), r = el.querySelector(".mv-reset");
    if (u) u.onclick = () => { mv().undo(); rerender(); };
    if (r) r.onclick = () => { mv().reset(); rerender(); };
  }
}
function rerender() { return CUR_DATE ? render() : renderOverview(); }
function doMove(items) {
  mv().move(items);
  setLive(`${items.length} wedstrijd${items.length === 1 ? "" : "en"} verzet: ${items.map((x) => `${x.w.label} ${x.w.home} → ${x.to}`).join(", ")}. Niet opgeslagen; de doeldag is nog niet berekend.`, "ok");
  const msg = $("live-status").textContent;
  return Promise.resolve(rerender()).then(() => { if (!$("live-status").textContent) setLive(msg, "ok"); });
}

function updateHash() {
  const h = `#${encodeURIComponent($("club").value)}${CUR_DATE ? `/${encodeURIComponent(CUR_DATE)}` : ""}`;
  if (location.hash !== h) history.pushState(null, "", h);
}

function setView(day) {
  $("overview-view").hidden = day;
  $("day-view").hidden = !day;
  for (const el of document.querySelectorAll(".day-only")) el.hidden = !day;
}

// Hash → overzicht (#club) of dagweergave (#club/dd-mm-jjjj).
function route() {
  const [hc, hd] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (hc && INDEX.clubs.some((c) => c.id === hc)) $("club").value = hc;
  const c = club();
  CUR_DATE = hd && (c.dates.some((d) => d.date === hd) || mv().into(hd).length) ? hd : null;
  return CUR_DATE ? render() : renderOverview();
}

function openDay(date) { CUR_DATE = date; render(); window.scrollTo({ top: 0 }); }

async function renderOverview() {
  const c = club();
  CUR_DATE = null;
  updateHash();
  setView(false);
  setLive("");
  renderProfile(c);
  $("note").textContent = `${c.name} · ${c.courts} banen · seizoen ${INDEX.season_file} · berekend ${new Date(INDEX.generated_at).toLocaleString("nl-NL")} (tijdslimiet ${INDEX.time_limit_s}s per poging)`;
  renderMoveBars();
  const sd = ovSeasonDays(c.dates);
  const res = await Promise.all(sd.map((x) => dayPlan(c, x.date)));
  if (club().id !== c.id || CUR_DATE) return; // intussen doorgeklikt
  const days = sd.map((x, i) => {
    const { plan, changed, known, live } = res[i];
    const stats = (known || live) && plan.rows.length ? ovPlanStats(plan, c) : null;
    const wed = mvFromRows(plan.rows).length;
    return ovDay(x, { wedstrijden: wed, partijen: stats ? stats.partijen : plan.rows.filter((r) => r.kind !== "W").length || null,
      stats, moves: mv() });
  }).map((d, i) => ({ ...d, changed: res[i].changed }));
  ovRender($("overview"), days, {
    busy: !!RUNNING,
    onOpen: openDay,
    onCompute: async (date) => { CUR_DATE = date; await render(); livePlan(); },
    onMove: async (date) => { CUR_DATE = date; await render(); $("legend").scrollIntoView({ block: "center" }); },
  });
}

async function render() {
  const c = club();
  const date = CUR_DATE;
  if (!CURRENT || CURRENT.d.date !== date || CURRENT.c.id !== c.id) { HL = null; }
  const d0 = c.dates.find((x) => x.date === date);
  if (!d0 && !mv().into(date || "").length) return renderOverview();
  updateHash();
  setView(true);
  renderProfile(c);
  renderMoveBars();
  $("day-title").textContent = `${c.name} — ${ovWeekday(date)} ${date}`;
  $("note").textContent = `${c.name} · ${c.courts} banen · seizoen ${INDEX.season_file} · berekend ${new Date(INDEX.generated_at).toLocaleString("nl-NL")} (tijdslimiet ${INDEX.time_limit_s}s per poging)`;
  const { plan, changed } = await dayPlan(c, date);
  if (CUR_DATE !== date) return;
  const st = ovPlanStats(plan, c);
  const d = { ...(d0 || { date, file: null, solutions_file: null, solve_time_s: "–" }),
    fixtures: mvFromRows(plan.rows).length, scheduled: st.scheduled, unscheduled: st.unscheduled };
  CURRENT = { c, d, plan, changed };
  setLive(changed ? `Aangepast: ${mv().into(date).length} wedstrijd(en) hierheen verzet, nog niet berekend. Sleep de partijen zelf op het baanschema of druk op "Nu berekenen".` : "", changed ? "warn" : "");
  showPlan(plan, null);
  if (changed || mv().touches(date)) $("solutions-sec").hidden = true; else renderSolutions(c, d);
}

// ---------------------------------------------------------------- teamchips: markeren + verzetten

let HL = null;            // team_id dat gemarkeerd is
function highlight(team) { HL = team; mvHighlight($("grid"), $("legend"), EDITOR.plan.rows, team); }

function bindLegend(plan) {
  if (!CURRENT) return;
  const { c, d } = CURRENT;
  const date = d.date;
  const ws = new Map(mvFromRows(plan.rows).map((w) => [w.key, w]));
  const sd = ovSeasonDays(c.dates);
  let tools = $("legend-tools");
  if (!tools) { tools = document.createElement("div"); tools.id = "legend-tools"; $("legend").before(tools); }
  tools.innerHTML = `<span class="hint">Klik op een team om het te markeren in het rooster of te verzetten naar een andere dag (bv. een inhaaldag).</span>
    ${HL ? `<button class="btn2 ov-calc" id="hl-off">Markering uit</button>` : ""}`;
  if ($("hl-off")) $("hl-off").onclick = () => { highlight(null); bindLegend(EDITOR.plan); };
  for (const chip of document.querySelectorAll("#legend .chip")) {
    chip.onclick = (ev) => {
      ev.stopPropagation();
      const w = ws.get(chip.dataset.team);
      mvOpenMenu(chip, w, date, sd, { highlighted: HL === chip.dataset.team,
        onHighlight: () => { highlight(HL === chip.dataset.team ? null : chip.dataset.team); bindLegend(EDITOR.plan); },
        onMove: (to) => { if (HL === w.key) HL = null; doMove([{ w, at: date, to }]); } });
    };
  }
  if (HL) highlight(HL);
}



let CURRENT = null;
let SHOWN = null; // plan dat nu in beeld is (voorstel, scenario of live) — voor Printen

// Slepen + directe controle (editor.js). Niets wordt opgeslagen.
const EDITOR = new PlanEditor({
  bar: () => $("edit-bar"),
  saveHint: "Deze voorbeeldpagina bewaart niets; opslaan doe je op de clubpagina.",
  club: () => CURRENT.c,
  render: (plan) => { renderGrid(CURRENT.c, plan); renderUnscheduled(plan); if (SHOWN) SHOWN.plan = plan; bindLegend(plan); },
});

function printDay() {
  if (!CURRENT || !SHOWN) return;
  const { c, d } = CURRENT;
  const sc = SHOWN.scenario;
  const note = sc ? (sc.live ? "nu berekend" : `oplossing: ${sc.title}`) : "";
  printPlan(SHOWN.plan, { clubName: c.name, date: d.date, dayStart: c.day.fallback_start || c.day.start, dayEnd: c.day.end, note });
}

// Toon een plan (het voorstel of een oplossingsscenario) in kaarten, grid en lijsten.
function showPlan(plan, scenario) {
  const { c, d } = CURRENT;
  const v = plan.validator || {};
  const dd = scenario
    ? { ...d, scheduled: scenario.scheduled, unscheduled: scenario.unscheduled, solve_time_s: scenario.solve_time_s,
        fixtures: d.fixtures - (scenario.moved_wedstrijden || 0) }
    : d;
  SHOWN = { plan, scenario };
  renderSummary(c, dd, plan);
  EDITOR.load(plan); // werkkopie: grid + niet-ingepland + directe controle
  SHOWN.plan = EDITOR.plan; // Printen = bewerkte stand
  renderFindings(plan);
  const vw = $("viewing");
  if (scenario && scenario.live) {
    vw.hidden = false;
    vw.innerHTML = `Je bekijkt een <b>nu berekend</b> plan (${esc(scenario.title)}) — geen gepubliceerd schema.<button id="back">Terug naar vooraf berekend</button>`;
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
    <tr><th>#</th><th>Versoepeling</th><th>Soort</th><th>Past alles</th><th>Ingepland</th><th>Niet</th><th>KNLTB-conform</th><th title="Overtredingen: regels die niet gebroken mogen worden. Moet 0 zijn.">Overtredingen</th><th></th></tr>${rows}</table></div>
    <p class="hint">"Overtredingen" = regels die niet gebroken mogen worden (moet 0 zijn), getoetst aan de huidige clubafspraken; een versoepelde clubafspraak telt daar dus als overtreding, ook als het KNLTB-conform is.</p>`;
  for (const b of $("solutions").querySelectorAll("button[data-i]")) {
    b.onclick = () => { const s = sols[+b.dataset.i]; showPlan(s.plan, s); $("viewing").scrollIntoView({ behavior: "smooth" }); };
  }
}

function renderSummary(c, d, plan) {
  const v = plan.validator || {};
  const card = (k, val, cls = "", tip = "") => `<div class="card"${tip ? ` title="${esc(tip)}"` : ""}><div class="k">${k}</div><div class="v ${cls}">${esc(val)}</div></div>`;
  $("summary").innerHTML = [
    card("Ingepland", d.scheduled, "good"),
    card("Niet ingepland", d.unscheduled, d.unscheduled ? "bad" : "good"),
    card("Overtredingen", v.hard ?? "–", v.hard ? "bad" : "good", "Overtredingen: regels die niet gebroken mogen worden. Moet 0 zijn."),
    card("Niet-gehaalde voorkeuren", v.model ?? "–", v.model ? "warn" : "", "Niet-gehaalde voorkeuren: mag, maar kan mooier."),
    card("Dagstart", plan.day_start),
    card("Wedstrijden", d.fixtures),
    card("Rekentijd", typeof d.solve_time_s === "number" ? `${d.solve_time_s}s` : "–"),
    card("Solver", plan.status),
  ].join("");
}

function renderGrid(c, plan) {
  const placed = plan.rows.filter((r) => r.start !== "NIET_GELUKT" && r.court);
  // Bereik ruim genoeg om naar 08:30 (KNLTB-vroegste) te kunnen slepen.
  const startMin = Math.min(510, toMin(c.day.fallback_start || c.day.start), ...placed.map((r) => toMin(r.start)));
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
    for (let k = 1; k <= c.courts; k++) html.push(`<div class="cell${hour ? " hour" : ""}" data-court="${k}" data-min="${m}" style="grid-row:${i + 2};grid-column:${k + 1}"></div>`);
  }
  const teams = new Map();
  const COL = teamColors(plan.rows);
  const IDX = new Map(plan.rows.map((r, i) => [r, i]));
  for (const r of placed) {
    const r0 = (toMin(r.start) - startMin) / 15 + 2;
    const r1 = (toMin(r.end) - startMin) / 15 + 2;
    const cat = CAT[r.category] || CAT.overig;
    const isRes = r.kind === "W";
    const tip = `${r.team}\n${r.home_team || ""}${r.away_team ? " – " + r.away_team : ""}\n${r.part || "reservering"} · ${r.start}–${r.end} · baan ${r.court}`;
    const col = COL.get(r.team_id) || { bg: "#ddd", fg: "#111" };
    const rc = COL.get(`__res_${r.category}`);
    const bg = isRes
      ? (rc ? `background:repeating-linear-gradient(45deg, ${rc.bg}, ${rc.bg} 6px, #fff 6px, #fff 12px)` : "")
      : `background:${col.bg};color:${col.fg}`;
    if (!isRes) teams.set(r.team_id, r);
    html.push(`<div class="blk${isRes ? " res" : ""}" data-ri="${IDX.get(r)}" title="${esc(tip)}" style="grid-row:${r0}/${r1};grid-column:${r.court + 1};${bg}">
      <span class="cat">${esc(rowLabel(r))}</span><b>${esc(r.part || (isRes ? cat.label : ""))}</b>
      <div>${esc(isRes ? "baanreservering" : shortTeam(r))}</div>
      <div class="t">${esc(r.start)}–${esc(r.end)}</div></div>`);
  }
  g.innerHTML = html.join("");
  for (const r of plan.rows) if (r.kind !== "W" && !teams.has(r.team_id)) teams.set(r.team_id, r); // ook niet-ingeplande teams
  $("legend").innerHTML = [...teams.values()]
    .sort((a, b) => a.team.localeCompare(b.team))
    .sort((a, b) => (a.category || "").localeCompare(b.category || ""))
    .map((r) => { const col = COL.get(r.team_id) || { bg: "#ddd", fg: "#111" };
      return `<span class="chip${HL === r.team_id ? " on" : ""}" data-team="${esc(r.team_id)}" style="background:${col.bg};color:${col.fg}" title="${esc(r.team)} — klik voor markeren / verzetten">${esc(rowLabel(r))} ${esc(shortTeam(r))}${r.moved_from ? " ↪" : ""}</span>`; })
    .join("");
}

function renderUnscheduled(plan) {
  const un = plan.rows.map((r, i) => [r, i]).filter(([r]) => r.start === "NIET_GELUKT");
  $("unscheduled").innerHTML = un.length
    ? `<p class="hint">Sleep een partij op het baanschema om hem in te plannen.</p><ul class="plain">${un.map(([r, i]) => `<li class="drag${r.moved_from ? " moved" : ""}" data-ri="${i}"><b>${esc(r.part || "reservering")}</b> · ${esc(rowLabel(r))} ${esc(shortTeam(r))}${r.moved_from ? ` <span class="mv-tag">niet ingepland (verzet van ${esc(r.moved_from)})</span>` : ""}<br><span class="hint">${esc(r.team)}</span></li>`).join("")}</ul>`
    : `<p class="empty">Alle partijen zijn ingepland.</p>`;
}

function renderFindings(plan) {
  const v = plan.validator || {};
  if (!v.available) { $("findings").innerHTML = `<p class="note">Geen validatorrapport.</p>`; return; }
  const f = v.findings || [];
  if (!f.length) { $("findings").innerHTML = `<p class="empty">Geen bevindingen.</p>`; return; }
  const item = (x) => `<li><span class="sev ${esc(x.severity)}">${x.severity === "HARD" ? "overtreding" : "voorkeur"}</span><b>${esc(x.rule)}</b> · ${esc(x.subject || "")}<br>${esc(x.message)}</li>`;
  const hard = f.filter((x) => x.severity === "HARD");
  const model = f.filter((x) => x.severity !== "HARD");
  $("findings").innerHTML =
    (hard.length ? `<ul class="plain">${hard.map(item).join("")}</ul>` : `<p class="empty">Geen overtredingen.</p>`) +
    (model.length ? `<details><summary>${model.length} niet-gehaalde voorkeur(en) tonen</summary><ul class="plain">${model.map(item).join("")}</ul></details>` : "");
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
      <td>${tag}</td><td>${core}</td><td class="hint">${r.source === "product" ? "Baanschemaatje" : sourceLink(r.source)}</td></tr>`;
  }).join("");
  $("profile").innerHTML = `
    <div class="cards">
      <div class="card"><div class="k">Club</div><div class="v">${esc(c.name)}</div></div>
      <div class="card"><div class="k">Banen</div><div class="v">${c.courts}</div></div>
      <div class="card"><div class="k">Dagstart</div><div class="v">${esc(c.day.start)}${c.day.fallback_start ? ` <small>(terugval ${esc(c.day.fallback_start)})</small>` : ""}</div></div>
      <div class="card"><div class="k">Laatste start / einde</div><div class="v">${esc(c.day.last_start)} / ${esc(c.day.end)}</div></div>
    </div>
    <p><b>Baanreserveringen:</b> ${resTxt}<br>
    <b>Baantoewijzing:</b> max ${c.max_courts_per_team} banen per team${c.adjacent_courts !== false && !c.court_pairs ? ", aangrenzend" : ""}${c.court_pairs ? `; vaste baanparen ${c.court_pairs.map((p) => p.join("+")).join(", ")}` : ""}${c.preferred_courts_8p.length ? `; 8p-teams bij voorkeur op baan ${c.preferred_courts_8p.join(", ")}` : ""}<br>
    <b>Verwachte speelduur (min, KNLTB-default):</b> ${durs}</p>
    <div class="tablewrap"><table>
      <tr><th>Regel</th><th>Waarde</th><th>Hard/zacht</th><th>Soort</th><th>KNLTB/core-default</th><th>Bron</th></tr>${rows}
    </table></div>
    <p class="hint">Clubafspraken mogen strenger zijn dan het KNLTB-reglement, niet ruimer. KNLTB = <a href="${KNLTB_CR.url}#page=${KNLTB_CR.pages["Bijlage 3"]}" target="_blank" rel="noopener">Competitiereglement (vastgesteld 11-11-2025), Bijlage 3</a>.</p>`;
}

// ---------------------------------------------------------------- live

function setLive(msg, cls = "") {
  const el = $("live-status");
  el.className = `live-status ${cls}`;
  el.textContent = msg;
}

async function livePost(path, body, ctl = new AbortController()) {
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

let RUNNING = null; // AbortController van de lopende berekening (één tegelijk)
const PROG = () => (window._pg ||= new Progress($("progress")));
const SCENARIO_BUDGET_S = 240; // server: BS_SCENARIO_BUDGET

function setRunning(ctl) {
  RUNNING = ctl;
  $("live-btn").disabled = !!ctl;
  const ls = $("live-sol");
  if (ls) ls.disabled = !!ctl;
}

async function livePlan() {
  if (!CURRENT || RUNNING) return;
  const { c, d } = CURRENT;
  const tl = +$("live-tl").value;
  const ctl = new AbortController();
  setRunning(ctl);
  setLive("");
  PROG().start({ title: `${c.name} · ${d.date}`, kind: "plan", tl, onCancel: () => ctl.abort() });
  try {
    const sig = mv().sig(d.date);
    const body = { club: c.id, date: d.date, time_limit_s: tl };
    if (mv().count) body.moves = mv().forServer();
    const plan = await livePost("/plan", body, ctl);
    if (body.moves && !plan.moves_applied && mv().touches(d.date)) {
      PROG().finish("De server kent verzetten nog niet. Er is niets veranderd; je kunt de verzette partijen wel zelf op het baanschema slepen.", "warn");
      return;
    }
    const s = plan.summary;
    if (!s.solved) {
      PROG().finish(`Geen oplossing gevonden binnen ${tl}s per poging (solver: ${plan.status}). Probeer een langere rekentijd; het getoonde plan blijft staan.`, "warn");
      return;
    }
    LIVE.set(`${c.id}/${d.date}`, { plan, sig });
    PROG().finish(`${pgDoneText(s)}${plan.cached ? " (uit cache)" : ""}`, s.unscheduled || s.hard ? "warn" : "ok");
    if (CURRENT.d.date !== d.date || CURRENT.c.id !== c.id) return; // gebruiker is doorgeklikt; resultaat staat in het overzicht
    showPlan(plan, { live: true, title: `${s.scheduled} ingepland, ${s.unscheduled} niet, ${plan.stats.solve_time_s}s rekentijd`,
      scheduled: s.scheduled, unscheduled: s.unscheduled, solve_time_s: s.solve_time_s, moved_wedstrijden: 0 });
    const sec = $("solutions-sec");
    if (s.unscheduled) {
      sec.hidden = false;
      $("solutions").innerHTML = `<p class="note">Nu berekend plan past niet volledig. <button id="live-sol">Zoek oplossingen</button> (kan 3–5 minuten duren; korte rekentijd per scenario, dus indicatief)</p>`;
      $("live-sol").onclick = () => liveScenarios(c, d, tl);
    }
  } catch (e) {
    if (e.name === "AbortError") {
      PROG().finish("Geannuleerd. De server rekent de lopende poging nog af (dat kost nog even rekentijd); het resultaat wordt niet getoond.", "warn");
    } else {
      const hint = mv().into(d.date).length && /HTTP 404/.test(e.message) ? " De server kent verzetten waarschijnlijk nog niet." : "";
      PROG().finish(`Server niet bereikbaar of fout (${e.message}).${hint} Het getoonde plan blijft staan.`, "err");
    }
  } finally { setRunning(null); }
}

async function liveScenarios(c, d, tl) {
  if (RUNNING) return;
  const ctl = new AbortController();
  setRunning(ctl);
  PROG().start({ title: `Zoek oplossingen · ${d.date}`, kind: "scenarios", tl, n: Math.ceil(SCENARIO_BUDGET_S / tl), onCancel: () => ctl.abort() });
  $("solutions").innerHTML = `<p class="note">Oplossingen worden doorgerekend…</p>`;
  try {
    const data = await livePost("/scenarios", { club: c.id, date: d.date, time_limit_s: tl }, ctl);
    const fits = data.solutions.filter((x) => x.fits && x.knltb_ok).length;
    PROG().finish(`Klaar: ${data.solutions.length} oplossing${data.solutions.length === 1 ? "" : "en"} doorgerekend, ${fits} past volledig (KNLTB-conform)`, fits ? "ok" : "warn");
    if (CURRENT.d.date !== d.date || CURRENT.c.id !== c.id) return;
    if (!data.solutions.length && data.base_solved) { $("solutions").innerHTML = `<p class="empty">Deze dag past al volledig.</p>`; return; }
    renderSolutionList(data.solutions, true);
  } catch (e) {
    const ab = e.name === "AbortError";
    PROG().finish(ab ? "Geannuleerd. De server rekent nog even door; het resultaat wordt niet getoond." : `Oplossingen zoeken mislukt (${e.message}).`, ab ? "warn" : "err");
    $("solutions").innerHTML = `<p class="note">${ab ? "Geannuleerd." : `Oplossingen zoeken mislukt (${esc(e.message)}).`}</p>`;
  } finally { setRunning(null); }
}

async function init() {
  try {
    INDEX = await getJSON("data/index.json");
  } catch (e) {
    $("note").textContent = `Kon data/index.json niet laden (${e.message}). Draai: python -m baanschemaatje build-web`;
    return;
  }
  $("club").innerHTML = INDEX.clubs.map((c) => `<option value="${esc(c.id)}">${esc(c.name)} (${c.courts} banen)</option>`).join("");
  $("club").onchange = () => { CUR_DATE = null; renderOverview(); };
  $("back-link").onclick = (e) => { e.preventDefault(); renderOverview(); window.scrollTo({ top: 0 }); };
  window.addEventListener("popstate", route);
  $("live-btn").onclick = livePlan;
  $("print-btn").onclick = printDay;
  $("live-btn").title = `Rekent deze speeldag nu opnieuw op ${LIVE_API} (alleen als je hierop drukt)`;
  route();
}
init();
