"use strict";
// Baanschemaatje: slepen en direct controleren in het baangrid (alleen in de browser).
// - checkPlan(rows, club): pure functie (ook bruikbaar in node-tests)
// - PlanEditor: werkkopie + undo + "terug naar origineel" + drag & drop (pointer events)
// Er wordt niets opgeslagen of naar de server gestuurd.

const ED_YOUTH = new Set(["groen", "junioren_11_14", "jeugd_13_17"]);
const ED_JUNIOR = new Set(["groen", "junioren_11_14"]);
const ED_KNLTB_LAST_START = 19 * 60 + 30;
const _m = (h) => parseInt(h.slice(0, 2), 10) * 60 + parseInt(h.slice(3, 5), 10);
const _hm = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const _placed = (r) => r.start && r.start !== "NIET_GELUKT" && r.court;
const _num = (part) => { const m = String(part || "").match(/(\d+)$/); return m ? +m[1] : 1; };

// Spelersbehoefte van één partij als [heren, dames, totaal]; spiegelt
// baanschema.rules.player_demand (gebruikt door src/baanschemaatje/planner.py).
function playerDemand(schema, part, kind) {
  const s = String(schema || "").toLowerCase();
  if (!s.includes("gemengd zondag")) return kind === "S" ? [0, 0, 1] : kind === "D" || kind === "M" ? [0, 0, 2] : [0, 0, 0];
  const label = String(part || "");
  if (label.startsWith("GD") || kind === "M") return [1, 1, 2];
  if (label.startsWith("S")) {
    const i = _num(label);
    if (s.includes("2de-2he")) return i <= 2 ? [0, 1, 1] : [1, 0, 1];
    if (s.includes("de-he")) return i === 1 ? [0, 1, 1] : [1, 0, 1];
    return [0, 0, 1];
  }
  if (label.startsWith("D") || kind === "D") {
    if (s.includes("dd-hd")) return _num(label) === 1 ? [0, 2, 2] : [2, 0, 2];
    return [0, 0, 2];
  }
  return [0, 0, 0];
}

// rows: planregels; club: profielsamenvatting (courts, day, max_courts_per_team, rules[]).
// Geeft { issues: [{level, rule, msg, rows:[idx]}], byRow: Map idx → [issue] }.
function checkPlan(rows, club) {
  const issues = [];
  const add = (level, rule, msg, idx) => issues.push({ level, rule, msg, rows: idx });
  const rules = Object.fromEntries((club.rules || []).map((r) => [r.name, r]));
  const name = (r) => `${r.label || ""} ${r.home_team || ""}`.trim();

  // 1. Baanconflict (ook met baanreserveringen).
  const byCourt = new Map();
  rows.forEach((r, i) => { if (_placed(r)) (byCourt.get(r.court) || byCourt.set(r.court, []).get(r.court)).push(i); });
  for (const [court, idx] of byCourt) {
    idx.sort((a, b) => _m(rows[a].start) - _m(rows[b].start));
    for (let k = 0; k < idx.length; k++) for (let l = k + 1; l < idx.length; l++) {
      const a = rows[idx[k]], b = rows[idx[l]];
      if (_m(b.start) >= _m(a.end)) break;
      add("conflict", "baan-overlap", `Baan ${court}: ${name(a)} ${a.part || "reservering"} en ${name(b)} ${b.part || "reservering"} overlappen (${b.start}–${a.end})`, [idx[k], idx[l]]);
    }
  }
  if (club.courts) rows.forEach((r, i) => { if (_placed(r) && (r.court < 1 || r.court > club.courts)) add("conflict", "baan", `Baan ${r.court} bestaat niet`, [i]); });

  // Per team.
  const teams = new Map();
  rows.forEach((r, i) => { if (r.kind !== "W") (teams.get(r.team_id) || teams.set(r.team_id, []).get(r.team_id)).push(i); });

  // Regel toetsen: eerst tegen de KNLTB-/core-waarde, dan tegen de clubwaarde.
  const rule = (rname, test, msg, idx) => {
    const r = rules[rname];
    if (!r || !r.hard) return;
    if (r.source !== "product" && !test(r.core_params || r.params)) add("KNLTB", rname, msg(r.core_params || r.params, true), idx);
    else if (!test(r.params)) add(r.club_override ? "clubafspraak" : "Baanschemaatje", rname, msg(r.params, false), idx);
  };

  for (const [, idx] of teams) {
    const all = idx.map((i) => rows[i]);
    const pl = idx.filter((i) => _placed(rows[i]));
    if (!pl.length) continue;
    const t0 = rows[pl[0]];
    const nm = name(t0);
    const first = Math.min(...pl.map((i) => _m(rows[i].start)));
    const firstIdx = pl.filter((i) => _m(rows[i].start) === first);
    const cat = t0.category;
    const is8p = all.length === 8;

    // Max banen tegelijk.
    const maxC = club.max_courts_per_team || 2;
    for (let t = first; t < 24 * 60; t += 15) {
      const busy = pl.filter((i) => _m(rows[i].start) <= t && t < _m(rows[i].end));
      if (busy.length > maxC) {
        add("clubafspraak", "max-banen", `${nm}: ${busy.length} banen tegelijk om ${_hm(t)} (max ${maxC})`, busy);
        break;
      }
    }
    // Banen per team over de hele dag (planner: hard, max N verschillende banen).
    const usedCourts = [...new Set(pl.map((i) => rows[i].court))];
    if (usedCourts.length > maxC) {
      add("clubafspraak", "max-banen-dag", `${nm}: speelt op ${usedCourts.length} verschillende banen (${usedCourts.sort((a, b) => a - b).join(", ")}), max ${maxC} per team`, pl);
    }

    // Spelers: max 4 spelers tegelijk bezet (zelfde spelers spelen S en D), gemengd max 2 heren + 2 dames.
    const mixed = /gemengd/i.test(t0.team || "");
    const pts = [...new Set(pl.flatMap((i) => [_m(rows[i].start), _m(rows[i].end)]))].sort((a, b) => a - b);
    for (const t of pts) {
      const busy = pl.filter((i) => _m(rows[i].start) <= t && t < _m(rows[i].end));
      if (busy.length < 2) continue;
      const dem = busy.map((i) => playerDemand(rows[i].team, rows[i].part, rows[i].kind));
      const sum = (k) => dem.reduce((a, d) => a + d[k], 0);
      const [men, women, tot] = [sum(0), sum(1), sum(2)];
      const what = busy.map((i) => rows[i].part).join(" + ");
      if (tot > 4) {
        add("Spelersconflict", "spelers", `${nm}: ${what} overlappen om ${_hm(t)}: ${tot} spelers nodig, het team heeft er 4 (dezelfde spelers spelen enkel en dubbel)`, busy);
        break;
      }
      if (mixed && (men > 2 || women > 2)) {
        add("Spelersconflict", "spelers", `${nm}: ${what} overlappen om ${_hm(t)}: ${men} heren en ${women} dames nodig, gemengd team heeft 2 + 2`, busy);
        break;
      }
    }

    // Volgorde (waterval): singles vóór dubbels (niet-gemengd), 8p strikt S → D → GD; paren beginnen samen.
    const ofKind = (k) => idx.filter((i) => rows[i].kind === k).sort((a, b) => _num(rows[a].part) - _num(rows[b].part));
    const S = ofKind("S"), D = ofKind("D"), M = ofKind("M");
    const nonS = idx.filter((i) => rows[i].kind !== "S");
    const strict8p = is8p && rules.waterfall_8p && rules.waterfall_8p.hard;
    const before = (A, B, txt) => {
      for (const a of A) for (const b of B) {
        if (!_placed(rows[a]) || !_placed(rows[b])) continue;
        if (_m(rows[b].start) < _m(rows[a].end)) {
          add("Volgorde", "waterval", `${nm}: ${rows[b].part} begint ${rows[b].start}, vóór ${rows[a].part} klaar is (${rows[a].end}); ${txt}`, [a, b]);
          return;
        }
      }
    };
    if (!mixed || strict8p) {
      before(S, nonS, strict8p ? "8 partijen: strikt enkels → dubbels → gemengd" : "eerst alle enkels, dan de dubbels");
      for (const lst of [S, D, M]) for (let k = 0; k + 1 < lst.length; k += 2) {
        const a = rows[lst[k]], b = rows[lst[k + 1]];
        if (_placed(a) && _placed(b) && a.start !== b.start) {
          add("Volgorde", "paar-samen", `${nm}: ${a.part} (${a.start}) en ${b.part} (${b.start}) horen tegelijk te beginnen`, [lst[k], lst[k + 1]]);
        }
      }
    }
    if (strict8p) before(D, M, "8 partijen: strikt enkels → dubbels → gemengd");

    // Speelblokken en wachttijd (op kwartierbasis, zoals de planner).
    const act = new Set();
    for (const i of pl) for (let t = _m(rows[i].start); t < _m(rows[i].end); t += 15) act.add(t);
    const slots = [...act].sort((a, b) => a - b);
    let blocks = slots.length ? 1 : 0, maxGap = 0, gapAt = null;
    for (let k = 1; k < slots.length; k++) {
      const gap = slots[k] - slots[k - 1] - 15;
      if (gap > 0) { blocks++; if (gap > maxGap) { maxGap = gap; gapAt = slots[k - 1] + 15; } }
    }
    rule("max_wait_minutes", (p) => maxGap <= p.value,
      (p) => `${nm}: ${maxGap} min wachten tussen partijen vanaf ${_hm(gapAt)} (max ${p.value})`, pl);
    rule("max_blocks_per_team", (p) => blocks <= p.value,
      (p) => `${nm}: ${blocks} losse speelblokken (max ${p.value})`, pl);

    rule("match_start_grid", (p) => first % (p.value || 30) === 0,
      (p) => `${nm}: begintijd ${_hm(first)} niet op heel/half uur`, firstIdx);
    rule("match_start_window", (p) => first >= _m(p.from) && first <= _m(p.to),
      (p) => `${nm}: begintijd ${_hm(first)} buiten ${p.from}–${p.to}`, firstIdx);
    if (is8p) {
      rule("start_window_8p", (p) => first >= _m(p.from) && first <= _m(p.to),
        (p) => `${nm} (8 partijen): begintijd ${_hm(first)} buiten ${p.from}–${p.to}`, firstIdx);
      if (cat === "gemengd") {
        rule("mixed_8p_latest_start", (p) => first <= _m(p.time), (p) => `${nm}: gemengd 8p begint ${_hm(first)}, uiterlijk ${p.time}`, firstIdx);
        rule("mixed_8p_not_before", (p) => first >= _m(p.time), (p) => `${nm}: gemengd 8p begint ${_hm(first)}, niet vóór ${p.time}`, firstIdx);
      }
    }
    if (ED_JUNIOR.has(cat)) {
      rule("junioren_latest_start", (p) => first <= _m(p.time), (p) => `${nm}: junioren beginnen ${_hm(first)}, uiterlijk ${p.time}`, firstIdx);
    }
    if (ED_YOUTH.has(cat)) {
      const late = pl.filter((i) => _m(rows[i].start) > _m((rules.youth_last_start || { params: { time: "19:30" } }).params.time));
      if (late.length) rule("youth_last_start", (p) => pl.every((i) => _m(rows[i].start) <= _m(p.time)),
        (p) => `${nm}: jeugdpartij start na ${p.time}`, late);
    }
  }

  // Laatste start / eindtijd van de dag.
  const lastClub = club.day && club.day.last_start ? _m(club.day.last_start) : ED_KNLTB_LAST_START;
  const end = club.day && club.day.end ? _m(club.day.end) : null;
  rows.forEach((r, i) => {
    if (!_placed(r) || r.kind === "W") return;
    if (_m(r.start) > ED_KNLTB_LAST_START) add("KNLTB", "laatste-start", `${name(r)} ${r.part}: start ${r.start}, KNLTB uiterlijk 19:30`, [i]);
    else if (_m(r.start) > lastClub) add("clubafspraak", "laatste-start", `${name(r)} ${r.part}: start ${r.start}, club uiterlijk ${club.day.last_start}`, [i]);
    if (end !== null && _m(r.end) > end) add("clubafspraak", "eindtijd", `${name(r)} ${r.part}: eindigt ${r.end}, na ${club.day.end}`, [i]);
  });

  const byRow = new Map();
  for (const it of issues) for (const i of it.rows) (byRow.get(i) || byRow.set(i, []).get(i)).push(it);
  return { issues, byRow };
}

// ---------------------------------------------------------------- editor

class PlanEditor {
  // opts: { bar: element voor knoppen/meldingen, render(plan) → hertekent grid + lijst, club: () => profielsamenvatting }
  constructor(opts) { this.opts = opts; this.orig = null; this.plan = null; this.history = []; }

  load(plan) {
    this.orig = JSON.parse(JSON.stringify(plan));
    this.plan = JSON.parse(JSON.stringify(plan));
    this.history = [];
    this.refresh();
  }

  get edited() { return this.history.length > 0 || JSON.stringify(this.plan.rows) !== JSON.stringify(this.orig.rows); }

  _snap() { this.history.push(JSON.stringify(this.plan.rows)); }

  move(ri, court, startMin) {
    const r = this.plan.rows[ri];
    if (!r || r.kind === "W") return;
    let dur = _placed(r) ? _m(r.end) - _m(r.start) : null;
    if (!dur) dur = ((this.opts.club().durations || {})[r.category]) || 90;
    const end = startMin + dur;
    if (_placed(r) && r.court === court && _m(r.start) === startMin) return;
    this._snap();
    r.court = court; r.start = _hm(startMin); r.end = _hm(end);
    this.refresh();
  }

  undo() { if (this.history.length) { this.plan.rows = JSON.parse(this.history.pop()); this.refresh(); } }
  reset() { this.plan = JSON.parse(JSON.stringify(this.orig)); this.history = []; this.refresh(); }

  refresh() {
    this.opts.render(this.plan);
    const res = checkPlan(this.plan.rows, this.opts.club());
    this.decorate(res);
    this.renderBar(res);
  }

  decorate(res) {
    for (const el of document.querySelectorAll("[data-ri]")) {
      const iss = res.byRow.get(+el.dataset.ri);
      el.classList.toggle("viol", !!iss);
      if (iss) el.title = iss.map((x) => `[${x.level}] ${x.msg}`).join("\n");
    }
    this.enableDrag();
  }

  renderBar(res) {
    const bar = this.opts.bar();
    if (!bar) return;
    const e = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const groups = ["conflict", "Spelersconflict", "Volgorde", "KNLTB", "clubafspraak", "Baanschemaatje"].map((lv) => [lv, res.issues.filter((x) => x.level === lv)]).filter(([, l]) => l.length);
    const label = { conflict: "Baanconflict", Spelersconflict: "Spelersconflict", Volgorde: "Volgorde", KNLTB: "KNLTB-reglement", clubafspraak: "Clubafspraak", Baanschemaatje: "Baanschemaatje-standaard" };
    bar.innerHTML = `<div class="ed-tools">
        <span class="hint">Sleep een partij naar een andere baan of tijd (per kwartier). Niet-ingeplande partijen kun je op het grid slepen.</span>
        <button class="btn2" id="ed-undo" ${this.history.length ? "" : "disabled"}>Ongedaan maken</button>
        <button class="btn2" id="ed-reset" ${this.edited ? "" : "disabled"}>Terug naar origineel</button></div>
      ${this.edited ? `<div class="ed-banner">Aangepast, niet opgeslagen (${this.history.length} wijziging${this.history.length === 1 ? "" : "en"}). De directe controle hieronder geldt voor deze aangepaste stand.</div>` : ""}
      ${groups.length ? groups.map(([lv, l]) => `<div class="ed-issues ${lv}"><b>${label[lv]} (${l.length})</b><ul>${l.slice(0, 12).map((x) => `<li>${e(x.msg)}</li>`).join("")}${l.length > 12 ? `<li>… en ${l.length - 12} meer</li>` : ""}</ul></div>`).join("")
        : (this.edited ? `<div class="ed-ok">Geen overtredingen gevonden door de directe controle.</div>` : "")}`;
    bar.querySelector("#ed-undo").onclick = () => this.undo();
    bar.querySelector("#ed-reset").onclick = () => this.reset();
  }

  // Doelcel onder een schermpunt: .cell[data-court][data-min]
  _cellAt(x, y) {
    for (const el of document.elementsFromPoint(x, y)) if (el.dataset && el.dataset.court && el.dataset.min) return el;
    return null;
  }

  enableDrag() {
    const items = document.querySelectorAll("[data-ri]:not(.res)");
    for (const el of items) {
      el.style.touchAction = "none";
      el.onpointerdown = (ev) => {
        if (ev.button !== 0) return;
        ev.preventDefault();
        const ri = +el.dataset.ri;
        const rect = el.getBoundingClientRect();
        const fromGrid = el.classList.contains("blk");
        const offY = fromGrid ? ev.clientY - rect.top : 4;
        const ghost = el.cloneNode(true);
        Object.assign(ghost.style, { position: "fixed", left: `${rect.left}px`, top: `${rect.top}px`, width: `${Math.max(rect.width, 90)}px`,
          height: fromGrid ? `${rect.height}px` : "auto", opacity: ".8", pointerEvents: "none", zIndex: 1000, margin: 0 });
        ghost.classList.add("ghost");
        document.body.appendChild(ghost);
        const mv = (e) => { ghost.style.left = `${e.clientX - (fromGrid ? ev.clientX - rect.left : 10)}px`; ghost.style.top = `${e.clientY - offY}px`; };
        const up = (e) => {
          document.removeEventListener("pointermove", mv);
          document.removeEventListener("pointerup", up);
          ghost.remove();
          const cell = this._cellAt(e.clientX, e.clientY - offY + 3);
          if (cell) this.move(ri, +cell.dataset.court, +cell.dataset.min);
        };
        document.addEventListener("pointermove", mv);
        document.addEventListener("pointerup", up);
      };
    }
  }
}

if (typeof module !== "undefined") module.exports = { checkPlan, playerDemand, PlanEditor };
