"use strict";
// Centrale configuratie voor bronverwijzingen. Publiceert de KNLTB een nieuwe
// versie van het Competitiereglement, pas dan alleen deze waarden aan.
const KNLTB_CR = {
  title: "KNLTB Competitiereglement (vastgesteld 11-11-2025)",
  url: "https://www.tennis.nl/media/fiyffx0f/knltb-competitiereglement-tennis.pdf",
  // PDF-pagina per bijlage (voor #page=N); controleren bij een nieuwe versie.
  pages: { "Bijlage 3": 28 },
  overview: "https://www.tennis.nl/alles-over-tennis/regelgeving-fair-play/reglementen-competitie-en-toernooien/",
};

// "KNLTB CR Bijlage 3, 1.1" → klikbare link naar de juiste PDF-pagina; anders gewoon tekst.
function sourceLink(source) {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  if (!source || !/KNLTB|CR\b/.test(source)) return esc(source);
  const m = source.match(/Bijlage\s+\d+/i);
  const page = m && KNLTB_CR.pages[m[0].replace(/\s+/, " ")];
  const href = `${KNLTB_CR.url}${page ? `#page=${page}` : ""}`;
  return `<a href="${esc(href)}" target="_blank" rel="noopener" title="${esc(KNLTB_CR.title)}${page ? `, pagina ${page}` : ""}">${esc(source)}</a>`;
}
