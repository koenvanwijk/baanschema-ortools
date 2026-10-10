"use strict";
// Seizoensoverzicht (startpagina per club): alle speeldagen + KNLTB-inhaaldagen,
// per dag status, partijen, controle en baanbezetting. Gedeeld door index.html en club.html.
// Rekent zelf nooit: "Nu berekenen" roept alleen de meegegeven callback aan.

const OV_BUSY = 85; // bezetting (%) vanaf hier: "extreem druk"
const OV_WEEKDAYS = ["zondag", "maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag"];
const ovEsc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ovMin = (hhmm) => parseInt(hhmm.slice(0, 2), 10) * 60 + parseInt(hhmm.slice(3, 5), 10);
const ovHHMM = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const ovDate = (dmy) => { const [d, m, y] = dmy.split("-").map(Number); return new Date(y, m - 1, d); };
const ovKey = (dmy) => dmy.split("-").reverse().join("");
const ovWeekday = (dmy) => OV_WEEKDAYS[ovDate(dmy).getDay()];

const OV_BEZETTING_TIP = "Baanbezetting = totale gereserveerde baantijd van alle ingeplande partijen (begin tot eind per partij, "
  + "inclusief vaste baanreserveringen voor Rood/Oranje) gedeeld door (aantal banen × dagvenster). "
  + "Dagvenster = dagstart tot 'alle partijen klaar om' uit het clubprofiel (bv. 09:00–20:00), "
  + `ruimer als het plan eerder begint of later eindigt. Vanaf ${OV_BUSY}% is een dag extreem druk.`;

// Alle dagen van het seizoen voor deze club: dagen met thuiswedstrijden + KNLTB-speel- en inhaaldagen
// op dezelfde weekdag(en). matchDates: [{date: "dd-mm-jjjj", ...}].
// KNLTB-competitie(s) per weekdag: op zondag alle (R/O/G, junioren, regulier); op andere dagen
// regulier, plus junioren/R/O/G alleen als die op die weekdag wedstrijden hebben.
function ovSeasonDays(matchDates) {
  const weekdays = new Set(matchDates.map((d) => ovWeekday(d.date)));
  if (!weekdays.size) weekdays.add("zondag");
  const comps = new Map([...weekdays].map((wd) => [wd, new Set(wd === "zondag" ? ["rog", "junioren", "regulier"] : ["regulier"])]));
  for (const d of matchDates) for (const w of d.wedstrijden || []) {
    const set = comps.get(ovWeekday(d.date));
    if (["groen", "rood", "oranje"].includes(w.category)) set.add("rog");
    if (["junioren_11_14", "jeugd_13_17"].includes(w.category)) set.add("junioren");
  }
  const days = new Map();
  const get = (date) => {
    if (!days.has(date)) days.set(date, { date, weekday: ovWeekday(date), match: null, speel: [], inhaal: [] });
    return days.get(date);
  };
  const keys = matchDates.map((d) => ovKey(d.date));
  for (const s of (typeof KNLTB_KALENDER !== "undefined" ? KNLTB_KALENDER : [])) {
    const all = s.competities.flatMap((c) => Object.values(c.dagen).flatMap((x) => [...x.speeldagen, ...x.inhaaldagen])).map(ovKey);
    const lo = all.reduce((a, b) => (a < b ? a : b)), hi = all.reduce((a, b) => (a > b ? a : b));
    if (keys.length && !keys.some((k) => k >= lo && k <= hi)) continue; // ander seizoen
    for (const c of s.competities) {
      for (const [wd, x] of Object.entries(c.dagen)) {
        if (!weekdays.has(wd) || !comps.get(wd).has(c.id)) continue;
        for (const dt of x.speeldagen) get(dt).speel.push(c.kort || c.naam);
        for (const dt of x.inhaaldagen) get(dt).inhaal.push(c.kort || c.naam);
      }
    }
  }
  for (const d of matchDates) get(d.date).match = d;
  return [...days.values()].sort((a, b) => ovKey(a.date).localeCompare(ovKey(b.date)));
}

// Kerngetallen van één plan. club: {courts, day: {start, fallback_start, end}}.
function ovPlanStats(plan, club) {
  const rows = plan.rows || [];
  const partijen = rows.filter((r) => r.kind !== "W");
  const placed = rows.filter((r) => r.start !== "NIET_GELUKT" && r.court);
  const placedP = placed.filter((r) => r.kind !== "W");
  const starts = placed.map((r) => ovMin(r.start)), ends = placed.map((r) => ovMin(r.end));
  const busy = placed.reduce((s, r) => s + ovMin(r.end) - ovMin(r.start), 0);
  const w0 = Math.min(ovMin(plan.day_start || club.day.start), ...starts);
  const w1 = Math.max(ovMin(club.day.end), ...ends);
  const courts = plan.courts || club.courts;
  const v = plan.validator || {};
  return {
    partijen: partijen.length, scheduled: placedP.length, unscheduled: partijen.length - placedP.length,
    hard: v.hard ?? null, model: v.model ?? null,
    first: starts.length ? ovHHMM(Math.min(...starts)) : null, last: ends.length ? ovHHMM(Math.max(...ends)) : null,
    busy, window: `${ovHHMM(w0)}–${ovHHMM(w1)}`, capacity: courts * (w1 - w0), courts,
    pct: courts && w1 > w0 ? Math.round((100 * busy) / (courts * (w1 - w0))) : 0,
  };
}

function ovStatus(day) {
  if (day.allPlayed) return { cls: "played", txt: "gespeeld (vast)" };
  if (day.changed && day.wedstrijden) return { cls: "changed", txt: "aangepast, nog niet berekend" };
  if (!day.wedstrijden) return { cls: "neutral", txt: day.kind === "inhaaldag" ? "inhaaldag, geen wedstrijden" : "geen thuiswedstrijden" };
  const s = day.stats;
  if (!s) return { cls: "grey", txt: "nog niet berekend" };
  if (s.unscheduled || s.hard) return { cls: "red", txt: [s.unscheduled ? `${s.unscheduled} niet ingepland` : "", s.hard ? `${s.hard} overtreding${s.hard > 1 ? "en" : ""}` : ""].filter(Boolean).join(", ") };
  if (s.model) return { cls: "orange", txt: `${s.model} voorkeur${s.model > 1 ? "en" : ""} niet gehaald` };
  return { cls: "green", txt: "in orde" };
}

// days: [{date, weekday, kind: "speeldag"|"inhaaldag", note, wedstrijden, partijen, stats|null, busyLabel}]
// opts: {onOpen(date), onCompute(date)|null, recompute: bool (ook knop bij al berekende dagen), computing: Set, queued: Set, busy: bool}
function ovRender(el, days, opts = {}) {
  const computing = opts.computing || new Set();
  const queued = opts.queued || new Set();
  const busy = !!opts.busy || computing.size > 0;
  const n = (x) => (x == null ? "–" : x);
  const st = days.map(ovStatus);
  const counts = { red: 0, orange: 0, green: 0, grey: 0, changed: 0, played: 0 };
  st.forEach((s) => { if (s.cls in counts) counts[s.cls]++; });
  const busiest = days.filter((d) => d.stats).sort((a, b) => b.stats.pct - a.stats.pct)[0];
  const nSpeel = days.filter((d) => d.kind === "speeldag").length, nInh = days.length - nSpeel;
  const head = `<div class="ov-sum">
    <span>${nSpeel} speeldagen · ${nInh} inhaaldagen</span>
    <span class="ov-pill red">${counts.red} met problemen</span>
    <span class="ov-pill orange">${counts.orange} alleen voorkeuren</span>
    <span class="ov-pill green">${counts.green} in orde</span>
    ${counts.grey ? `<span class="ov-pill grey">${counts.grey} nog niet berekend</span>` : ""}
    ${counts.played ? `<span class="ov-pill played">${counts.played} gespeeld</span>` : ""}
    ${counts.changed ? `<span class="ov-pill changed">${counts.changed} aangepast, nog niet berekend</span>` : ""}
    ${days.some((d) => d.saveCls === "saved") ? `<span class="ov-pill saved">${days.filter((d) => d.saveCls === "saved").length} opgeslagen</span>` : ""}
    ${days.some((d) => d.saveCls === "unsaved") ? `<span class="ov-pill unsaved">${days.filter((d) => d.saveCls === "unsaved").length} niet opgeslagen</span>` : ""}
    ${busiest ? `<span title="${ovEsc(OV_BEZETTING_TIP)}">Drukste dag: <b>${ovEsc(busiest.date)}</b> (${busiest.stats.pct}% bezet)</span>` : ""}
  </div>`;
  const rows = days.map((d, i) => {
    const s = d.stats, stt = st[i];
    const open = (d.wedstrijden || d.allPlayed) && (s || d.changed || opts.openAlways) && opts.onOpen;
    const extreme = s && s.pct >= OV_BUSY;
    const bar = s ? `<div class="ov-bar${extreme ? " extreme" : s.pct >= 70 ? " busy" : ""}" title="${ovEsc(`${s.pct}% · ${Math.round(s.busy / 60)} van ${Math.round(s.capacity / 60)} baanuren (${s.courts} banen × ${s.window})\n\n${OV_BEZETTING_TIP}`)}">
        <span style="width:${Math.min(100, s.pct)}%"></span><b>${s.pct}%</b></div>${extreme ? `<span class="ov-hot">extreem druk</span>` : ""}`
      : d.wedstrijden ? `<span class="hint">–</span>` : "";
    const mvBtn = d.wedstrijden && !d.allPlayed && opts.onMove ? ` <button class="btn2 ov-calc ov-move" data-date="${ovEsc(d.date)}" title="Wedstrijden van deze dag naar een andere dag verzetten">Verzetten…</button>` : "";
    const btn = d.wedstrijden && !d.allPlayed && opts.onCompute && (!s || d.changed || opts.recompute)
      ? `<button class="btn2 ov-calc" data-date="${ovEsc(d.date)}" title="Deze dag nu (opnieuw) berekenen op de server"${busy ? " disabled" : ""}>${computing.has(d.date) ? "Bezig…" : s ? "Opnieuw" : "Nu berekenen"}</button>` : "";
    const kind = d.kind === "inhaaldag" ? `<span class="ov-kind inh">inhaaldag</span>` : `<span class="ov-kind">speeldag</span>`;
    return `<tr class="ov-row ${stt.cls}${computing.has(d.date) ? " computing" : ""}${d.kind === "inhaaldag" ? " inh" : ""}${open ? " click" : ""}${extreme ? " extreme" : ""}" data-date="${ovEsc(d.date)}">
      <td class="ov-date"><span class="ov-dot ${stt.cls}"></span><b>${ovEsc(d.date)}</b> <span class="hint">${ovEsc(d.weekday)}</span></td>
      <td>${kind}${d.note ? `<div class="hint ov-note">${ovEsc(d.note)}</div>` : ""}${(d.movedOut || []).map((m) => `<div class="ov-note mv-tag">verzet: ${m.n} wedstrijd${m.n === 1 ? "" : "en"} naar ${ovEsc(m.to)}</div>`).join("")}${(d.movedIn || []).map((m) => `<div class="ov-note mv-tag in">+${m.n} verzet van ${ovEsc(m.from)}</div>`).join("")}</td>
      <td class="num">${d.wedstrijden || "–"}</td><td class="num">${n(d.partijen)}</td>
      <td class="num">${s ? s.scheduled : "–"}</td>
      <td class="num${s && s.unscheduled ? " bad" : ""}">${s ? s.unscheduled : "–"}</td>
      <td class="num${s && s.hard ? " bad" : ""}">${s ? n(s.hard) : "–"}</td>
      <td class="num${s && s.model ? " warn" : ""}">${s ? n(s.model) : "–"}</td>
      <td>${s && s.first ? `${s.first}–${s.last}` : "–"}</td>
      <td class="ov-bez">${bar}</td>
      <td class="ov-st ${computing.has(d.date) ? "computing" : queued.has(d.date) ? "queued" : stt.cls}">${computing.has(d.date) ? `<span class="spin"></span>berekenen…` : queued.has(d.date) ? "in wachtrij" : ovEsc(stt.txt)}${d.saveInfo ? `<div class="ov-save ${d.saveCls || ""}">${ovEsc(d.saveInfo)}</div>` : ""}</td>
      <td>${open ? `<a href="#" class="ov-open" data-date="${ovEsc(d.date)}">Open dag →</a> ` : ""}${btn}${mvBtn}</td></tr>`;
  }).join("");
  el.innerHTML = head + `<div class="tablewrap"><table class="ov">
    <tr><th>Datum</th><th>Soort</th><th title="Thuiswedstrijden">Wedstr.</th><th>Partijen</th><th>Ingepland</th><th>Niet ingepland</th>
    <th title="Regels die niet gebroken mogen worden. Moet 0 zijn.">Overtredingen</th><th title="Mag, maar kan mooier.">Niet-gehaalde voorkeuren</th>
    <th>Eerste start – laatste einde</th><th title="${ovEsc(OV_BEZETTING_TIP)}">Baanbezetting ⓘ</th><th>Status</th><th></th></tr>${rows}</table></div>
    <p class="hint">Inhaaldagen volgens de officiële <a href="${ovEsc(KNLTB_KALENDER[0].url)}" target="_blank" rel="noopener">KNLTB-speeldata ${ovEsc(KNLTB_KALENDER[0].seizoen)}</a>. Klik op een dag om het baanschema te openen. Er wordt alleen gerekend als je zelf op "Nu berekenen" drukt.</p>`;
  for (const tr of el.querySelectorAll("tr.ov-row.click")) {
    tr.onclick = (e) => { if (e.target.closest("button")) return; e.preventDefault(); opts.onOpen(tr.dataset.date); };
  }
  for (const b of el.querySelectorAll("button.ov-move")) b.onclick = (e) => { e.stopPropagation(); opts.onMove(b.dataset.date); };
  for (const b of el.querySelectorAll("button.ov-calc:not(.ov-move)")) b.onclick = (e) => { e.stopPropagation(); opts.onCompute(b.dataset.date); };
}

// Dag-object voor ovRender uit een ovSeasonDays-item.
function ovDay(x, { wedstrijden, partijen, stats, moves }) {
  const inhaalOnly = !x.speel.length && x.inhaal.length;
  const note = x.speel.length && x.inhaal.length ? `ook inhaaldag ${x.inhaal.join(" + ")}`
    : inhaalOnly && x.inhaal.length < 3 ? `alleen ${x.inhaal.join(" + ")}` : "";
  return { date: x.date, weekday: x.weekday, kind: inhaalOnly ? "inhaaldag" : "speeldag",
    note, wedstrijden: wedstrijden || 0, partijen, stats, ...ovMoveInfo(x.date, moves) };
}

// Verzettingen (MoveState uit verzetten.js) samengevat per dag.
function ovMoveInfo(date, moves) {
  if (!moves) return {};
  const grp = (list, k) => { const m = new Map(); for (const x of list) m.set(x[k], (m.get(x[k]) || 0) + 1); return [...m]; };
  return {
    movedOut: grp(moves.outOf(date).filter((x) => x.to !== date), "to").map(([to, n]) => ({ to, n })),
    movedIn: grp(moves.into(date), "from").map(([from, n]) => ({ from, n })),
  };
}
