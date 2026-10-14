"use strict";
// Tv/beamer-scherm (alleen-lezen) voor een bingo-avond: tv.html#<club>/<dd-mm-jjjj>. Ververst elke 5 s; geen knoppen.
const TV_MS = 5000;
let TV = null;

function tvParse() { const [club, date] = decodeURIComponent(location.hash.slice(1)).split("/"); return { club: club || "mierlo", date: date || "" }; }
const tvMins = (iso) => Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
const tvDur = (m) => (m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}` : `${m} min`);

async function tvLoad() {
  const { club, date } = tvParse();
  try {
    const r = await fetch(`${API}/clubs/${encodeURIComponent(club)}/bingo/${encodeURIComponent(date)}`);
    if (!r.ok) throw new Error(String(r.status));
    TV = await r.json();
    $("tv-msg").textContent = "";
  } catch (e) { $("tv-msg").textContent = `Verbinding… (${e.message})`; }
  tvRender();
}

function tvRender() {
  $("tv-clock").textContent = new Date().toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
  if (!TV) return;
  const st = bgNorm(TV.state), w = TV.window || {}, n = w.courts || 0;
  $("tv-title").textContent = `${TV.name} · bingo-avond ${TV.date}`;
  $("tv-sub").textContent = w.last_start ? `Laatste start ${w.last_start} · park dicht ${clockHHMM(w.end)}` : "";
  const find = (pid) => { for (const m of TV.matches) for (const p of m.parts) if (p.id === pid) return { m, p }; return null; };
  $("tv-courts").innerHTML = Array.from({ length: n }, (_, i) => {
    const c = st.courts[String(i + 1)];
    if (!c) return `<div class="tv-court free"><div class="tv-cn">${i + 1}</div><div class="tv-free">vrij</div></div>`;
    const f = find(c.part), el = tvMins(c.start);
    return `<div class="tv-court busy${f && el > f.m.duration ? " long" : ""}"><div class="tv-cn">${i + 1}</div>
      <div class="tv-team">${esc(f ? `${f.m.label} ${f.m.home}` : "?")}</div>
      <div class="tv-part">${esc(f ? f.p.label : "")}${f ? ` <span class="tv-away">– ${esc(f.m.away)}</span>` : ""}</div>
      ${c.lineup ? `<div class="tv-lineup">${esc(c.lineup)}</div>` : ""}
      <div class="tv-el">${tvDur(el)}</div></div>`;
  }).join("");
  const q = bgQueue(st, TV.matches).slice(0, 8);
  $("tv-queue").innerHTML = q.map((p) => `<li><b>${esc(p.label)}</b> ${esc(p.match.label)} ${esc(p.match.home)}</li>`).join("")
    || `<li class="tv-none">${Object.keys(st.present).length ? "Niets meer in de wachtrij" : "Nog geen teams aangemeld"}</li>`;
}

if (typeof document !== "undefined") {
  window.addEventListener("hashchange", tvLoad);
  tvLoad();
  setInterval(tvLoad, TV_MS);
  setInterval(tvRender, 30000);
}
