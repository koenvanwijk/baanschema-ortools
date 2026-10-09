"use strict";
// Teamkleuren per speeldag: elk team een eigen, goed te onderscheiden kleur.
// Logische kleuren voor de KNLTB-categorieën: Groen = groen, Rood = rood,
// Oranje = oranje (tinten bij meerdere teams). Overige teams krijgen kleuren
// buiten die drie families, zo ver mogelijk uit elkaar. Gedeeld door
// index.html en club.html.
const FAMILY = {
  groen: ["#2e7d32", "#81c784", "#1b5e20", "#c8e6c9", "#4caf50"],
  rood: ["#c62828", "#ef9a9a", "#8e0000", "#e57373"],
  oranje: ["#ef6c00", "#ffcc80", "#b53d00", "#ffa726"],
};
// Geen groen/rood/oranje; volgorde = maximaal verschil tussen opeenvolgende teams.
const OTHER = [
  "#1e88e5", "#fdd835", "#8e24aa", "#00acc1", "#f06292", "#6d4c41", "#3949ab", "#9e9e9e",
  "#81d4fa", "#ce93d8", "#0d47a1", "#fff59d", "#455a64", "#f8bbd0", "#d7ccc8", "#5c6bc0",
  "#4a148c", "#b2ebf2", "#795548", "#e1bee7",
];

function _lum(hex) {
  const n = parseInt(hex.slice(1), 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function _fg(hex) { return _lum(hex) > 0.36 ? "#111" : "#fff"; }

function _extra(i) {
  // Reserve na het palet: gouden-hoek-tinten buiten groen (75-165), rood (<15, >345) en oranje (15-45).
  let h = (i * 137.508) % 360;
  for (let k = 0; k < 12 && (h < 45 || (h > 75 && h < 165) || h > 345); k++) h = (h + 47) % 360;
  return `hsl(${h.toFixed(0)}, 60%, ${i % 2 ? 40 : 70}%)`;
}

// rows: planregels van één dag. Geeft Map team_id → {bg, fg}.
function teamColors(rows) {
  const teams = new Map();
  for (const r of rows) if (r.kind !== "W" && !teams.has(r.team_id)) teams.set(r.team_id, r);
  const sorted = [...teams.values()].sort((a, b) =>
    (a.category || "").localeCompare(b.category || "") || (a.team || "").localeCompare(b.team || "") ||
    (a.home_team || "").localeCompare(b.home_team || ""));
  const used = { groen: 0, rood: 0, oranje: 0 };
  let other = 0;
  const out = new Map();
  for (const r of sorted) {
    let bg;
    const fam = FAMILY[r.category];
    if (fam) bg = fam[used[r.category]++ % fam.length];
    else bg = other < OTHER.length ? OTHER[other++] : _extra(other++);
    out.set(r.team_id, { bg, fg: bg.startsWith("#") ? _fg(bg) : (bg.endsWith("40%)") ? "#fff" : "#111") });
  }
  // Baanreserveringen (Rood/Oranje-blokken) in hun categoriekleur.
  for (const k of Object.keys(FAMILY)) out.set(`__res_${k}`, { bg: FAMILY[k][0], fg: "#fff" });
  return out;
}
