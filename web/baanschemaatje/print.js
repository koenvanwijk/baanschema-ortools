"use strict";
// Printbaar dagoverzicht op precies één A4 (staand): baangrid (banen × tijd),
// dezelfde teamkleuren als op het scherm (kleurenprint) + label in elk blok, compacte legenda
// en de niet-ingeplande partijen. Gedeeld door index.html en club.html.
// Vereist colors.js (teamColors).

function _pEsc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const _pMin = (h) => parseInt(h.slice(0, 2), 10) * 60 + parseInt(h.slice(3, 5), 10);
const _pHHMM = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

// A4 staand, marge 7 mm → 196 × 283 mm bruikbaar.
const PRINT_W = 196, PRINT_H = 283;

function buildPrintView(plan, opt) {
  const placed = plan.rows.filter((r) => r.start !== "NIET_GELUKT" && r.court);
  const un = plan.rows.filter((r) => r.start === "NIET_GELUKT");
  const t0 = Math.min(_pMin(opt.dayStart || "09:00"), ...placed.map((r) => _pMin(r.start)));
  const t1 = Math.max(_pMin(opt.dayEnd || "20:00"), ...placed.map((r) => _pMin(r.end)));
  const start = Math.floor(t0 / 30) * 30, end = Math.ceil(t1 / 30) * 30;
  const slots = (end - start) / 15;
  const courts = plan.courts;
  const COL = teamColors(plan.rows);
  const teams = new Map();
  for (const r of placed) if (r.kind !== "W" && !teams.has(r.team_id)) teams.set(r.team_id, r);

  // Hoogtebudget (mm): titel 9, legenda, niet-ingepland, marge 4.
  const legendLines = Math.ceil(teams.size / 4);
  const unLines = un.length ? Math.ceil(un.length / 3) + 1 : 0;
  const gridH = PRINT_H - 11 - legendLines * 4.2 - unLines * 3.6 - 6;
  const rowH = gridH / (slots + 1.2); // +header
  const timeW = 10;
  const colW = (PRINT_W - timeW) / courts;

  const h = [];
  h.push(`<div class="p-title"><div><b>${_pEsc(opt.clubName)}</b> — baanschema ${_pEsc(plan.date || opt.date)}</div>` +
    `<span>${placed.filter((r) => r.kind !== "W").length} partijen ingepland${un.length ? `, ${un.length} niet` : ""} · ${courts} banen · dagstart ${_pEsc(plan.day_start)}${opt.note ? " · " + _pEsc(opt.note) : ""}</span></div>`);
  h.push(`<div class="p-grid" style="height:${gridH.toFixed(1)}mm;grid-template-columns:${timeW}mm repeat(${courts}, ${colW.toFixed(2)}mm);grid-template-rows:${(rowH * 1.2).toFixed(2)}mm repeat(${slots}, ${rowH.toFixed(3)}mm)">`);
  h.push(`<div class="p-hdr" style="grid-row:1;grid-column:1"></div>`);
  for (let k = 1; k <= courts; k++) h.push(`<div class="p-hdr" style="grid-row:1;grid-column:${k + 1}">Baan ${k}</div>`);
  for (let i = 0; i < slots; i++) {
    const m = start + i * 15;
    if (m % 30 === 0) h.push(`<div class="p-time${m % 60 === 0 ? " hr" : ""}" style="grid-row:${i + 2}/${i + 4};grid-column:1">${_pHHMM(m)}</div>`);
    if (m % 30 === 0) h.push(`<div class="p-line${m % 60 === 0 ? " hr" : ""}" style="grid-row:${i + 2};grid-column:2/${courts + 2}"></div>`);
  }
  for (let k = 1; k <= courts; k++) h.push(`<div class="p-col" style="grid-row:2/${slots + 2};grid-column:${k + 1}"></div>`);
  for (const r of placed) {
    const a = (_pMin(r.start) - start) / 15 + 2, b = (_pMin(r.end) - start) / 15 + 2;
    const isRes = r.kind === "W";
    const c = isRes ? (COL.get(`__res_${r.category}`) || { bg: "#ccc", fg: "#111" }) : COL.get(r.team_id);
    const style = isRes
      ? `background:repeating-linear-gradient(45deg, ${c.bg}, ${c.bg} 1.2mm, #fff 1.2mm, #fff 2.4mm);color:#111`
      : `background:${c.bg};color:${c.fg}`;
    const who = isRes ? "baanreservering" : (r.home_team || "");
    h.push(`<div class="p-blk${isRes ? " p-res" : ""}" style="grid-row:${a}/${b};grid-column:${r.court + 1};${style}">` +
      `<div class="l1"><span class="p-lab">${_pEsc(r.label || r.category || "")}</span> <b>${_pEsc(r.part || (isRes ? r.category : ""))}</b></div>` +
      `<div class="l2">${_pEsc(who)}</div><div class="l2">${_pEsc(r.start)}–${_pEsc(r.end)}</div></div>`);
  }
  h.push(`</div>`);
  const leg = [...teams.values()].sort((x, y) => (x.category || "").localeCompare(y.category || "") || (x.home_team || "").localeCompare(y.home_team || ""));
  h.push(`<div class="p-legend">${leg.map((r) => { const c = COL.get(r.team_id); return `<span><i style="background:${c.bg}"></i><b>${_pEsc(r.label || "")}</b> ${_pEsc(r.home_team || "")} – ${_pEsc(r.away_team || "")}</span>`; }).join("")}</div>`);
  if (un.length) {
    h.push(`<div class="p-un"><b>Niet ingepland (${un.length}):</b><div>${un.map((r) => `<span>${_pEsc(r.label || "")} ${_pEsc(r.home_team || "")} – ${_pEsc(r.away_team || "")}: <b>${_pEsc(r.part)}</b></span>`).join("")}</div></div>`);
  }
  let el = document.getElementById("print-area");
  if (!el) { el = document.createElement("div"); el.id = "print-area"; document.body.appendChild(el); }
  el.innerHTML = h.join("");
  return el;
}

function printPlan(plan, opt) {
  buildPrintView(plan, opt);
  window.print();
}
