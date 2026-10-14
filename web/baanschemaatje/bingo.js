"use strict";
// Bingo-avond: baancommissaris-scherm (één apparaat tegelijk; een tweede/ververst apparaat blijft gelijk via polling).
// URL: bingo.html#<club>/<dd-mm-jjjj>. Opslaan op de server met generatie (409 = iemand anders was eerder).

let BG = null;      // {club, date, name, window, matches}
let ST = bgEmpty(); // toestand
let GEN = 0;
let BUSY = false;
const POLL_MS = 5000;

function bgParse() {
  const [club, date] = decodeURIComponent(location.hash.slice(1)).split("/");
  return { club: club || "mierlo", date: date || "" };
}

function say(msg, cls = "") { const el = $("bg-status"); el.textContent = msg; el.className = `bg-status ${cls}`; }

async function bgFetch(path, opts) {
  const r = await fetch(`${API}${path}`, opts);
  let b = null; try { b = await r.json(); } catch (_) { /* leeg */ }
  return { ok: r.ok, status: r.status, body: b };
}

async function load(quiet = false) {
  const { club, date } = bgParse();
  const r = await bgFetch(`/clubs/${encodeURIComponent(club)}/bingo/${encodeURIComponent(date)}`);
  if (!r.ok) { say(`Kon de avond niet laden: ${(r.body && r.body.detail) || r.status}`, "bad"); return; }
  const j = r.body;
  BG = { club, date, name: j.name, window: j.window, matches: j.matches, mode: j.mode };
  if (j.gen !== GEN || !quiet) { ST = bgNorm(j.state); GEN = j.gen; }
  render();
}

async function act(fn) {
  if (BUSY) return;
  let next;
  try { next = fn(ST); } catch (e) { say(e.message, "bad"); return; }
  BUSY = true;
  const prev = ST;
  ST = next; render();
  const r = await bgFetch(`/clubs/${encodeURIComponent(BG.club)}/bingo/${encodeURIComponent(BG.date)}`, jsonOpts("PUT", { state: next, gen: GEN }));
  BUSY = false;
  if (r.ok) { GEN = r.body.gen; say(`Opgeslagen ${new Date().toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })}`, "ok"); render(); return; }
  if (r.status === 409 && r.body && r.body.detail) {
    ST = bgNorm(r.body.detail.state); GEN = r.body.detail.gen;
    say(r.body.detail.message || "Iemand anders wijzigde de avond; opnieuw geladen. Doe je actie zo nodig opnieuw.", "warn");
  } else { ST = prev; say(`Niet opgeslagen: ${(r.body && (r.body.detail || {}).message) || (r.body && r.body.detail) || r.status}`, "bad"); }
  render();
}

const hm = (iso) => new Date(iso).toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
const mins = (iso) => Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
const dur = (m) => (m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")} u` : `${m} min`);
const matchOf = (partId) => BG.matches.find((m) => m.parts.some((p) => p.id === partId));

function render() {
  if (!BG) return;
  const w = BG.window || {};
  const n = w.courts || 0;
  $("bg-title").textContent = `Bingo-avond ${BG.date}`;
  $("bg-sub").textContent = `${BG.name} · baancommissaris`;
  $("bg-back").href = `club.html${location.search}#${encodeURIComponent(BG.club)}`;
  $("bg-window").textContent = w.start ? `Avond ${w.start}–${clockHHMM(w.end)} · laatste start ${w.last_start} · ${n} banen (alle met licht)` : "";
  $("bg-clock").textContent = new Date().toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
  $("bg-undo").disabled = !(ST.undo || []).length || BUSY;
  if (BG.mode !== "bingo" && !$("bg-status").textContent) say("Let op: deze dag staat in de instellingen niet op 'Bingo (live)'.", "warn");

  // Banen
  $("bg-courts").innerHTML = Array.from({ length: n }, (_, i) => {
    const c = ST.courts[String(i + 1)];
    if (!c) return `<div class="bg-court free"><div class="bg-cn">Baan ${i + 1}</div><div class="bg-free-lbl">vrij</div></div>`;
    const m = matchOf(c.part), p = m && m.parts.find((x) => x.id === c.part);
    const el = mins(c.start), long = m && el > m.duration;
    return `<div class="bg-court busy${long ? " long" : ""}"><div class="bg-cn">Baan ${i + 1}</div>
      <div class="bg-what"><b>${esc(p ? p.label : "?")}</b> ${esc(m ? `${m.label} ${m.home}` : c.part)}</div>
      ${c.lineup ? `<div class="bg-lineup">${esc(c.lineup)}</div>` : ""}
      <div class="bg-time">sinds ${hm(c.start)} · <b>${dur(el)}</b>${m ? ` / ${m.duration} min` : ""}</div>
      <button class="btn bg-big bg-done" data-court="${i + 1}">Klaar</button></div>`;
  }).join("") || '<p class="hint">Geen banen ingesteld.</p>';

  // Voorstel
  const sg = bgSuggest(ST, BG.matches, BG.window, new Date());
  $("bg-suggest").hidden = !sg;
  if (sg) {
    $("bg-sg-text").innerHTML = `Volgende op <b>baan ${sg.court}</b>: <b>${esc(sg.label)}</b> ${esc(sg.match.label)} ${esc(sg.match.home)} <span class="hint">– ${esc(sg.match.away)}</span>`;
    $("bg-sg-ok").onclick = () => act((s) => bgAssign(s, BG.matches, sg.part, sg.court, ""));
    $("bg-sg-other").onclick = () => openAssign(sg.part);
  }

  // Wachtrij
  const q = bgQueue(ST, BG.matches);
  $("bg-qn").textContent = `(${q.length})`;
  $("bg-queue").innerHTML = q.map((p) => `<button class="bg-q" data-part="${esc(p.id)}"><b>${esc(p.label)}</b> ${esc(p.match.label)} ${esc(p.match.home)} <span class="hint">– ${esc(p.match.away)}</span></button>`).join("")
    || `<p class="hint">${Object.keys(ST.present).length ? "Geen partijen meer in de wachtrij." : "Nog geen teams aanwezig gemeld."}</p>`;

  // Teams
  $("bg-teams").innerHTML = BG.matches.map((m) => {
    const left = m.parts.filter((p) => !ST.done[p.id]).length;
    return `<label class="bg-team${ST.present[m.key] ? " on" : ""}"><input type="checkbox" data-key="${esc(m.key)}"${ST.present[m.key] ? " checked" : ""}>
      <span><b>${esc(m.label)} ${esc(m.home)}</b> – ${esc(m.away)}<br><span class="hint">${m.moved_from ? `verzet van ${esc(m.moved_from)} · ` : ""}${m.export_start ? `${esc(m.export_start)} · ` : ""}${m.parts.length} partijen${left < m.parts.length ? ` · nog ${left}` : ""}</span></span></label>`;
  }).join("") || '<p class="hint">Geen (niet-gespeelde) wedstrijden op deze avond. Opgaven tellen niet mee.</p>';

  $("bg-log").innerHTML = [...ST.log].reverse().map((l) => `<li><span class="hint">${hm(l.t)}</span> ${esc(l.msg)}</li>`).join("");

  for (const b of document.querySelectorAll(".bg-done")) b.onclick = () => act((s) => bgFinish(s, BG.matches, +b.dataset.court));
  for (const b of document.querySelectorAll(".bg-q")) b.onclick = () => openAssign(b.dataset.part);
  for (const i of document.querySelectorAll("#bg-teams input")) i.onchange = () => act((s) => bgSetPresent(s, BG.matches.find((m) => m.key === i.dataset.key), i.checked));
}

function openAssign(partId) {
  const m = matchOf(partId), p = m.parts.find((x) => x.id === partId);
  const free = bgFreeCourts(ST, (BG.window || {}).courts || 0);
  $("bg-dlg-title").textContent = `${p.label} · ${m.label} ${m.home} – ${m.away}`;
  $("bg-lineup").value = "";
  const warn = bgWarnings(BG.window, m.duration, new Date());
  $("bg-warn").innerHTML = warn.map((x) => `<div>⚠ ${esc(x)}</div>`).join("");
  $("bg-free").innerHTML = free.map((c) => `<button type="button" class="btn bg-big" data-court="${c}">Baan ${c}</button>`).join("") || '<p class="hint">Geen vrije baan.</p>';
  for (const b of $("bg-free").querySelectorAll("button")) b.onclick = () => {
    const lineup = $("bg-lineup").value.trim();
    $("bg-dlg").close();
    act((s) => bgAssign(s, BG.matches, partId, +b.dataset.court, lineup));
  };
  $("bg-dlg").showModal();
}

function init() {
  $("bg-undo").onclick = () => act((s) => bgUndo(s));
  window.addEventListener("hashchange", () => load());
  load();
  setInterval(() => { if (!BUSY && !$("bg-dlg").open) load(true).catch(() => {}); else render(); }, POLL_MS);
}
if (typeof document !== "undefined") init();
