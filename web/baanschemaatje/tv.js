"use strict";
// Tv/beamer-scherm (alleen-lezen) voor een bingo-avond: tv.html#<club>/<dd-mm-jjjj>. Ververst elke 5 s; geen knoppen.
const TV_MS = 5000;
let TV = null;

function tvParse() { const [club, date] = decodeURIComponent(location.hash.slice(1)).split("/"); return { club: club || "mierlo", date: date || "" }; }
const tvMins = (iso) => Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
const tvDur = (m) => (m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}` : `${m} min`);

// SD9: ook voor gewone (geplande) speeldagen: schema + verloop van het dashboard.
let TVP = null;
async function tvLoad() {
  const { club, date } = tvParse();
  try {
    const d = await fetch(`${API}/clubs/${encodeURIComponent(club)}/dayrun/${encodeURIComponent(date)}`);
    if (d.ok) {
      const j = await d.json();
      if (j.mode !== "bingo") { TVP = j; TV = null; $("tv-msg").textContent = ""; tvRenderPlanned(); return; }
    }
    TVP = null;
    const r = await fetch(`${API}/clubs/${encodeURIComponent(club)}/bingo/${encodeURIComponent(date)}`);
    if (!r.ok) throw new Error(String(r.status));
    TV = await r.json();
    $("tv-msg").textContent = "";
  } catch (e) { $("tv-msg").textContent = `Verbinding… (${e.message})`; }
  tvRender();
}

function tvRenderPlanned() {
  const j = TVP, w = j.window || {}, n = w.courts || 0, plan = j.schedule && j.schedule.plan;
  $("tv-clock").textContent = new Date().toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
  $("tv-title").textContent = `${j.name} · speeldag ${j.date}`;
  const ch = (plan && plan.changed) || {};
  $("tv-sub").textContent = plan ? `Laatste start ${w.last_start} · einde ${clockShort(w.end)}${Object.keys(ch).length ? " · schema gewijzigd" : ""}` : "Nog geen definitief schema";
  if (!plan) { $("tv-courts").innerHTML = ""; $("tv-queue").innerHTML = '<li class="tv-none">Nog geen definitief schema</li>'; return; }
  const st = dsNorm(j.state), rows = dsRows(plan), now = dsClock(new Date());
  const tapped = Object.keys(st.parts).length > 0;
  const chip = (r) => (ch[dsPid(r)] ? ' <span class="tv-chg">gewijzigd</span>' : "");
  $("tv-courts").innerHTML = dsCourts(rows, st, now, n).map((c) => {
    if (c.off) return `<div class="tv-court free"><div class="tv-cn">${c.court}</div><div class="tv-free">buiten gebruik</div></div>`;
    // Lopend: getikt op het dashboard; zonder tikken volgens schema.
    let cur = c.cur, el = null, est = false;
    if (cur) el = tvMins(st.parts[dsPid(cur)].start);
    else if (!tapped) { cur = rows.find((r) => r.court === c.court && dsMin(r.start) <= now && now < dsMin(r.end)) || null; if (cur) { el = now - dsMin(cur.start); est = true; } }
    if (!cur) return `<div class="tv-court free"><div class="tv-cn">${c.court}</div><div class="tv-free">vrij</div>${c.next ? `<div class="tv-nx">${esc(clockShort(c.next.start))} ${esc(c.next.label)} ${esc(c.next.home_team)}</div>` : ""}</div>`;
    const dur = dsMin(cur.end) - dsMin(cur.start);
    return `<div class="tv-court busy${el > dur ? " long" : ""}"><div class="tv-cn">${c.court}</div>
      <div class="tv-team">${esc(cur.label)} ${esc(cur.home_team)}${chip(cur)}</div>
      <div class="tv-part">${esc(cur.part)} <span class="tv-away">– ${esc(cur.away_team)}</span></div>
      <div class="tv-el">${est ? "volgens schema · " : ""}${tvDur(el)}</div></div>`;
  }).join("");
  const q = rows.filter((r) => dsStatus(r, st, now).status === "gepland" && dsMin(r.end) > now).filter((r) => tapped || dsMin(r.start) > now).slice(0, 10);
  $("tv-queue").innerHTML = q.map((r) => `<li><b>${esc(clockShort(r.start))}</b> baan ${r.court} · ${esc(r.label)} ${esc(r.home_team)} ${esc(r.part)}${chip(r)}</li>`).join("")
    || '<li class="tv-none">Niets meer gepland</li>';
}

function tvRender() {
  $("tv-clock").textContent = new Date().toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
  if (TVP) { tvRenderPlanned(); return; }
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
