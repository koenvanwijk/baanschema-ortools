"use strict";
// Wedstrijden verzetten (bv. na regen naar een KNLTB-inhaaldag). Alleen in de browser:
// niets wordt opgeslagen. Gedeeld door index.html en club.html; pure functies zijn node-testbaar.
// Een verzetting: {key, schema, home, away, label, category, matches, singles, doubles, mix, rows?, from, to}
//   key  = "<schema> · <thuisteam>" (= team_id in planregels)
//   from = oorspronkelijke speeldag (blijft gelijk bij nogmaals verzetten), to = nieuwe dag.

const MV_ROG = new Set(["rood", "oranje", "groen"]);
const MV_JUN = new Set(["junioren_11_14", "jeugd_13_17"]);
const mvComp = (cat) => (MV_ROG.has(cat) ? "rog" : MV_JUN.has(cat) ? "junioren" : "regulier");
const mvKey = (schema, home) => (home ? `${schema} · ${home}` : schema);
const mvSortKey = (dmy) => dmy.split("-").reverse().join("");
const mvWeekday = (dmy) => { const [d, m, y] = dmy.split("-").map(Number);
  return ["zondag", "maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag"][new Date(y, m - 1, d).getDay()]; };

class MoveState {
  constructor() { this.list = []; this.hist = []; }
  get count() { return this.list.length; }
  _snap() { this.hist.push(JSON.stringify(this.list)); }
  // Waar staat wedstrijd `key` nu? (oorspronkelijke dag `orig` als hij niet verzet is)
  current(key, orig) { const m = this.list.find((x) => x.key === key && x.from === orig); return m ? m.to : orig; }
  // items: [{w (wedstrijd), at (huidige dag), to}] — één stap voor undo.
  move(items) {
    const todo = items.filter((it) => it.to && it.to !== it.at);
    if (!todo.length) return 0;
    this._snap();
    for (const { w, at, to } of todo) {
      const ex = this.list.find((x) => x.key === w.key && x.to === at);
      if (ex) {
        if (to === ex.from) this.list = this.list.filter((x) => x !== ex); else ex.to = to;
      } else {
        this.list.push({ ...w, from: at, to });
      }
    }
    return todo.length;
  }
  undo() { if (this.hist.length) this.list = JSON.parse(this.hist.pop()); }
  reset() { if (this.list.length) this._snap(); this.list = []; }
  outOf(date) { return this.list.filter((x) => x.from === date); }
  into(date) { return this.list.filter((x) => x.to === date); }
  touches(date) { return this.list.some((x) => x.from === date || x.to === date); }
  // Verzettingen voor de server (/plan "moves"): alle, want ze kunnen elkaar raken.
  forServer() { return this.list.map((x) => ({ schema: x.schema, home: x.home, from: x.from, to: x.to })); }
  // Handtekening van wat dag `date` raakt (om te zien of een berekening nog klopt).
  sig(date) { return JSON.stringify(this.list.filter((x) => x.from === date || x.to === date).map((x) => [x.key, x.from, x.to]).sort()); }
}

// Wedstrijden (unieke teams) uit planregels.
function mvFromRows(rows) {
  const by = new Map();
  for (const r of rows || []) {
    const key = r.team_id || mvKey(r.team, r.home_team);
    if (!by.has(key)) {
      by.set(key, { key, schema: r.team, home: r.home_team, away: r.away_team || "", label: r.label || "", category: r.category,
        matches: 0, singles: 0, doubles: 0, mix: 0, rows: [] });
    }
    const w = by.get(key);
    if (r.moved_from) w.moved_from = r.moved_from;
    if (r.kind !== "W") w.matches++;
    if (r.kind === "S") w.singles++; else if (r.kind === "D") w.doubles++; else if (r.kind === "M") w.mix++;
    w.rows.push(r);
  }
  return [...by.values()];
}

// Wedstrijd uit de seizoensweergave van de server ({schema, home, away, label, category, matches, singles?, ...}).
function mvFromSeason(x) {
  return { key: mvKey(x.schema, x.home), schema: x.schema, home: x.home, away: x.away || "", label: x.label || "",
    category: x.category, matches: x.matches, singles: x.singles, doubles: x.doubles, mix: x.mix };
}

// Partijen (S/D/GD) als de serverweergave geen aantallen heeft: gemengd uit "(2DE-2HE-DD-HD-2GD)", anders 2/3 enkels.
function mvParts(w) {
  let s = w.singles, d = w.doubles, m = w.mix;
  if (s == null || d == null) {
    const p = String(w.schema || "").match(/\(([A-Z0-9-]+)\)/);
    s = 0; d = 0; m = 0;
    if (p) for (const tok of p[1].split("-")) {
      const n = /^\d/.test(tok) ? parseInt(tok, 10) : 1, t = tok.replace(/^\d+/, "");
      if (t === "DE" || t === "HE") s += n; else if (t === "DD" || t === "HD") d += n; else if (t === "GD") m += n;
    }
    if (s + d + m !== w.matches) { s = Math.round((w.matches * 2) / 3); d = w.matches - s; m = 0; }
  }
  const out = [];
  for (let i = 1; i <= s; i++) out.push([`S${i}`, "S"]);
  for (let i = 1; i <= d; i++) out.push([`D${i}`, "D"]);
  for (let i = 1; i <= m; i++) out.push([`GD${i}`, "M"]);
  return out;
}

// Planregels voor een naar `date` verzette wedstrijd: niet ingepland, gemarkeerd als verzet.
function mvRowsFor(mv) {
  const base = { team: mv.schema, team_id: mv.key, home_team: mv.home, away_team: mv.away, category: mv.category, label: mv.label,
    start: "NIET_GELUKT", end: "", court: null, moved_from: mv.from };
  if (mv.rows && mv.rows.length) return mv.rows.map((r) => ({ ...r, ...base, part: r.part, kind: r.kind }));
  if (MV_ROG.has(mv.category) && mv.category !== "groen") return [{ ...base, part: "", kind: "W" }];
  return mvParts(mv).map(([part, kind]) => ({ ...base, part, kind }));
}

// Plan van dag `date` met de verzettingen erop: uitgaande wedstrijden eruit, inkomende erbij (niet ingepland).
function mvApplyPlan(plan, date, state) {
  const out = new Set(state.outOf(date).filter((x) => x.to !== date).map((x) => x.key));
  const rows = (plan.rows || []).filter((r) => !out.has(r.team_id || mvKey(r.team, r.home_team)) || r.moved_from);
  const have = new Set(rows.map((r) => r.team_id || mvKey(r.team, r.home_team)));
  for (const mv of state.into(date)) if (!have.has(mv.key)) rows.push(...mvRowsFor(mv));
  return { ...plan, rows };
}

// Toegestane doeldagen voor wedstrijd w die nu op `at` staat. seasonDays = ovSeasonDays(...) of [{date, match}].
// Geeft [{date, kind: "inhaaldag"|"speeldag", valid, note}] chronologisch.
function mvTargets(w, at, seasonDays, kalender) {
  const wd = mvWeekday(at), comp = mvComp(w.category);
  const out = new Map();
  const put = (date, kind, valid, note) => {
    if (date === at) return;
    const ex = out.get(date);
    if (ex && (ex.valid || !valid)) return;
    out.set(date, { date, kind, valid, note });
  };
  for (const s of kalender || []) for (const c of s.competities) {
    const dd = c.dagen[wd];
    if (!dd) continue;
    const mine = c.id === comp;
    for (const d of dd.inhaaldagen) put(d, "inhaaldag", mine, mine ? `inhaaldag ${c.kort || c.naam}` : `alleen inhaaldag ${c.kort || c.naam}`);
    if (mine) for (const d of dd.speeldagen) put(d, "speeldag", true, "speeldag");
  }
  for (const d of seasonDays || []) if (d.match) put(d.date, "speeldag", true, "speeldag (club speelt thuis)");
  return [...out.values()].sort((a, b) => mvSortKey(a.date).localeCompare(mvSortKey(b.date)));
}

function mvCompName(cat) { return { rog: "Rood/Oranje/Groen", junioren: "junioren 11–14 / 13–17", regulier: "reguliere competitie" }[mvComp(cat)]; }

// Balk met "Aangepast, niet opgeslagen" + undo/reset.
// saved (optioneel, clubpagina): {dirty, savedAt, busy} → knop "Verzettingen opslaan" / "opgeslagen om HH:MM".
function mvBarHtml(state, saveNote, saved) {
  if (!state.count && !(saved && saved.dirty) && (saved || !state.hist.length)) return "";
  const groups = new Map();
  for (const x of state.list) { const k = `${x.from} → ${x.to}`; groups.set(k, (groups.get(k) || 0) + 1); }
  const hhmm = (iso) => { const d = new Date(iso); return isNaN(d) ? "" : `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const head = saved && !saved.dirty ? `Verzet: ${state.count} wedstrijd${state.count === 1 ? "" : "en"}${saved.savedAt ? ` · opgeslagen om ${hhmm(saved.savedAt)}` : ""}`
    : `Verzet, niet opgeslagen: ${state.count} wedstrijd${state.count === 1 ? "" : "en"}`;
  return `<div class="ed-banner mv-bar${saved && !saved.dirty ? " saved" : ""}">${head}
    ${[...groups].map(([k, n]) => `<span class="mv-tag">${n}× ${k}</span>`).join(" ")}
    ${saved ? `<button class="btn mv-save-btn" ${saved.dirty && !saved.busy ? "" : "disabled"}>${saved.busy ? "Opslaan…" : "Verzettingen opslaan"}</button>` : ""}
    <button class="btn2 mv-undo" ${state.hist.length ? "" : "disabled"}>Ongedaan maken</button>
    <button class="btn2 mv-reset" ${state.count ? "" : "disabled"}>Alle verzettingen terugdraaien</button>
    ${saveNote !== "" ? `<div class="hint">${saveNote || "Opslaan komt later; verzettingen gelden alleen in dit tabblad."}</div>` : ""}</div>`;
}

// ---------------------------------------------------------------- DOM: teamchip-menu (markeren / verzetten)

function mvHighlight(grid, legend, rows, team) {
  grid.classList.toggle("hl-mode", !!team);
  for (const el of grid.querySelectorAll(".blk")) {
    const r = rows[+el.dataset.ri];
    el.classList.toggle("hl", !!team && !!r && r.team_id === team);
  }
  for (const el of legend.querySelectorAll(".chip")) el.classList.toggle("on", el.dataset.team === team);
}

function mvCloseMenu() { const m = document.getElementById("chip-menu"); if (m) m.remove(); }

// opts: {highlighted, onHighlight(), onMove(toDate)}
function mvOpenMenu(chip, w, date, seasonDays, opts) {
  mvCloseMenu();
  if (!w) return;
  const e = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const t = mvTargets(w, date, seasonDays, typeof KNLTB_KALENDER !== "undefined" ? KNLTB_KALENDER : []);
  const opt = (x) => `<option value="${e(x.date)}"${x.valid ? "" : " disabled"}>${e(x.date)} · ${e(x.note)}</option>`;
  const m = document.createElement("div");
  m.id = "chip-menu";
  m.className = "chip-menu";
  m.innerHTML = `<div class="cm-title"><b>${e(w.label)} ${e(w.home)}</b> – ${e(w.away)}<div class="hint">${e(mvCompName(w.category))}${w.moved_from ? ` · verzet van ${e(w.moved_from)}` : ""}</div></div>
    <button class="btn2" id="cm-hl">${opts.highlighted ? "Markering uit" : "Markeer in rooster"}</button>
    <div class="cm-move"><label>Verzetten naar…<select id="cm-to"><option value="">— kies een dag —</option>
      <optgroup label="Inhaaldagen ${e(mvCompName(w.category))}">${t.filter((x) => x.kind === "inhaaldag" && x.valid).map(opt).join("")}</optgroup>
      <optgroup label="Andere speeldagen">${t.filter((x) => x.kind === "speeldag").map(opt).join("")}</optgroup>
      <optgroup label="Niet geldig voor deze competitie">${t.filter((x) => !x.valid).map(opt).join("")}</optgroup></select></label>
      <button class="live-btn" id="cm-go">Verzetten</button></div>`;
  document.body.appendChild(m);
  const r = chip.getBoundingClientRect();
  Object.assign(m.style, { left: `${Math.max(4, Math.min(r.left + scrollX, innerWidth - 340))}px`, top: `${r.bottom + scrollY + 4}px` });
  m.onclick = (ev) => ev.stopPropagation();
  m.querySelector("#cm-hl").onclick = () => { mvCloseMenu(); opts.onHighlight(); };
  m.querySelector("#cm-go").onclick = () => { const to = m.querySelector("#cm-to").value; if (!to) return; mvCloseMenu(); opts.onMove(to); };
}
if (typeof document !== "undefined") document.addEventListener("click", mvCloseMenu);

if (typeof module !== "undefined") {
  module.exports = { MoveState, mvComp, mvKey, mvFromRows, mvFromSeason, mvParts, mvRowsFor, mvApplyPlan, mvTargets, mvWeekday };
}
