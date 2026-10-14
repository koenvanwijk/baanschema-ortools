"use strict";
// Alleen-lezen dagpagina om te delen: dag.html#<club>/<dd-mm-jjjj>. Toont het opgeslagen (definitieve) schema
// per team: aanvang, banen, partijen. Geen bewerkknoppen.
function dgParse() { const [club, date] = decodeURIComponent(location.hash.slice(1)).split("/"); return { club: club || "mierlo", date: date || "" }; }

// Groepeer planregels per team (pure functie, ook in Node getest).
function dgTeams(rows) {
  const by = new Map();
  for (const r of rows || []) {
    if (!r.start || !r.court) continue;
    const k = r.team_id || `${r.team} · ${r.home_team}`;
    if (!by.has(k)) by.set(k, { label: r.label, home: r.home_team, away: r.away_team, starts: [], courts: new Set(), parts: [] });
    const t = by.get(k);
    t.starts.push(r.start); t.courts.add(r.court); t.parts.push({ part: r.part, start: r.start, end: r.end, court: r.court });
  }
  const toM = (s) => parseInt(s.slice(0, 2), 10) * 60 + parseInt(s.slice(3, 5), 10);
  return [...by.values()].map((t) => {
    t.parts.sort((a, b) => toM(a.start) - toM(b.start) || a.court - b.court);
    return { ...t, aanvang: t.parts[0].start, courts: [...t.courts].sort((a, b) => a - b) };
  }).sort((a, b) => toM(a.aanvang) - toM(b.aanvang) || a.courts[0] - b.courts[0]);
}

async function dgLoad() {
  const { club, date } = dgParse();
  const link = location.href;
  $("dg-wa").href = `https://wa.me/?text=${encodeURIComponent(`Baanschema ${date}: ${link}`)}`;
  $("dg-copy").onclick = async () => {
    try { await navigator.clipboard.writeText(link); $("dg-copied").textContent = "Gekopieerd ✓"; }
    catch (_) { prompt("Kopieer deze link:", link); }
  };
  let name = club;
  try { const c = await (await fetch(`${API}/clubs/${encodeURIComponent(club)}`)).json(); name = (c.summary && c.summary.name) || (c.profile && c.profile.club && c.profile.club.name) || club; } catch (_) { /* naam optioneel */ }
  $("dg-title").textContent = `Baanschema ${date}`;
  $("dg-sub").textContent = name;
  document.title = `Baanschema ${date} · ${name}`;
  const r = await fetch(`${API}/clubs/${encodeURIComponent(club)}/schedule/${encodeURIComponent(date)}`);
  if (r.status === 404) { $("dg-body").innerHTML = '<p class="banner">Voor deze dag is nog geen definitief schema opgeslagen. Kijk later nog eens.</p>'; return; }
  if (!r.ok) { $("dg-body").innerHTML = `<p class="banner warn">Kon het schema niet laden (${r.status}).</p>`; return; }
  const j = await r.json();
  const teams = dgTeams(j.plan && j.plan.rows);
  $("dg-body").innerHTML = `<p class="hint">Definitief schema · opgeslagen ${esc(new Date(j.saved_at).toLocaleString("nl-NL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }))}</p>
    <ul class="dg-teams">${teams.map((t) => `<li class="dg-team"><div class="dg-head"><span class="dg-time">${esc(clockShort(t.aanvang))}</span>
      <span><b>${esc(t.label)} ${esc(t.home)}</b> – ${esc(t.away)}</span></div>
      <div class="dg-courts">Baan ${t.courts.join(", ")}</div>
      <div class="dg-parts hint">${t.parts.map((p) => `${esc(p.part)} ${esc(clockShort(p.start))} b${p.court}`).join(" · ")}</div></li>`).join("")}</ul>`;
}

if (typeof document !== "undefined") { window.addEventListener("hashchange", dgLoad); dgLoad(); }
if (typeof module !== "undefined") module.exports = { dgTeams };
