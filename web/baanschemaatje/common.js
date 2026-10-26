"use strict";
// Baanschemaatje: gedeelde helpers voor clubpagina en club-instellingen.
// Login: Google OAuth (I3); tv/dag blijven publiek (I5). Geen gedeeld clubwachtwoord.

const API_DEFAULT = "https://baanschemaatje-356953092000.europe-west1.run.app";
const API = (new URLSearchParams(location.search).get("api") || API_DEFAULT).replace(/\/+$/, "");

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const toMin = (hhmm) => parseInt(hhmm.slice(0, 2), 10) * 60 + parseInt(hhmm.slice(3, 5), 10);
// Tijd ná middernacht ("25:00") tonen als "01:00".
const clockHHMM = (hhmm) => { const m = toMin(hhmm); return m >= 1440 ? `${toHHMM(m - 1440)} (volgende dag)` : hhmm; };
// Compact (rooster, print, overzicht): 25:00 → "01:00+".
const clockShort = (hhmm) => { if (!hhmm || !/^\d{1,2}:\d{2}/.test(hhmm)) return hhmm; const m = toMin(hhmm); return m >= 1440 ? `${toHHMM(m - 1440)}+` : hhmm; };
const toHHMM = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

const RULE_NL = {
  match_start_grid: "Begintijd op hele/halve uren (min)",
  match_start_window: "Begintijd wedstrijd",
  junioren_start_window: "Junioren (Groen + 11–14): begintijd",
  junioren_latest_start: "Junioren: begintijd uiterlijk",
  junioren_mixed_8p_latest_start: "Gemengd 8p junioren: begintijd uiterlijk",
  mixed_8p_latest_start: "Gemengd 8p: begintijd uiterlijk",
  travel_not_before: "Reisafstand ≥ km: niet vóór",
  min_reservation: "Minimale reservering per partij (KNLTB)",
  start_window_8p: "8-partijenteams: begintijd",
  mixed_8p_not_before: "Gemengd 8p: niet vóór",
  youth_last_start: "Jeugd: laatste start uiterlijk",
  first_start_deadline: "Eerste partij elk team uiterlijk",
  max_wait_minutes: "Max wachttijd tussen partijen (min)",
  max_blocks_per_team: "Max speelblokken per team",
  waterfall_8p: "8p: strikte S → D → GD",
  evening_start_window: "Avondcompetitie: begintijd",
  morning_start_window: "Ochtendcompetitie: begintijd",
  afternoon_start_window: "Middagcompetitie: begintijd",
  export_start: "Begintijd uit de KNLTB-export aanhouden",
};

let CLUBS = [];
let CLUB = null;      // GET /clubs/{id}
let DATES = [];
let AUTH = null;      // /auth/status of clubs.auth

function status(msg, cls = "") { const el = $("status"); if (!el) return; el.className = `live-status ${cls}`; el.textContent = msg; }

async function api(path, opts = {}) {
  const o = { credentials: "include", ...opts };
  if (o.headers) o.headers = { ...o.headers };
  const res = await fetch(`${API}${path}`, o);
  let body = null;
  try { body = await res.json(); } catch (_) { /* geen JSON */ }
  if (!res.ok) {
    const d = body && body.detail;
    const msg = typeof d === "string" ? d : d && d.message ? d.message : `HTTP ${res.status}`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return body;
}
const jsonOpts = (method, data) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data), credentials: "include" });

// Hash: #<club>[&comp=<competitie>] (club.html) of #regelhulp?q=… (Regelmaatje).
function parseHash() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (!h || h.startsWith("regelhulp") || h.startsWith("regelmaatje")) return { club: null, comp: null };
  const [club, ...rest] = h.split("&");
  const kv = Object.fromEntries(rest.map((x) => x.split("=")));
  return { club, comp: kv.comp || null };
}
function setHash(club, comp) {
  history.replaceState(null, "", `#${encodeURIComponent(club)}${comp && comp !== "alle" ? `&comp=${encodeURIComponent(comp)}` : ""}`);
}

async function loadClubList(select) {
  const j = await api("/clubs");
  CLUBS = j.clubs;
  AUTH = j.auth || AUTH;
  $("club").innerHTML = CLUBS.map((c) =>
    `<option value="${esc(c.id)}">${esc(c.name)}${c.demo ? " — demo" : ""}${c.stored ? "" : " (alleen lezen)"}</option>`).join("");
  const dflt = (CLUBS.find((c) => c.id === "mierlo") || CLUBS[0]).id;
  const want = select || parseHash().club || dflt;
  $("club").value = CLUBS.some((c) => c.id === want) ? want : dflt;
  renderAuthBar();
}

async function refreshAuth(clubId) {
  try {
    AUTH = await api(`/auth/status${clubId ? `?club=${encodeURIComponent(clubId)}` : ""}`);
  } catch (_) { AUTH = AUTH || { configured: false, user: null }; }
  renderAuthBar();
  return AUTH;
}

function loginUrl(next, club) {
  const n = encodeURIComponent(next || (location.pathname + location.search + location.hash));
  const c = club ? `&club=${encodeURIComponent(club)}` : "";
  // Zelfde origin: /auth/login op de API-host. Als UI via /app draait is API same-origin.
  const base = API || "";
  return `${base}/auth/login?next=${n}${c}`;
}

async function logout() {
  try { await api("/auth/logout", { method: "POST" }); } catch (_) { /* ignore */ }
  AUTH = { ...(AUTH || {}), user: null, is_platform_admin: false, can_create_club: false };
  renderAuthBar();
}

function renderAuthBar() {
  const el = $("auth-bar");
  if (!el) return;
  const a = AUTH || {};
  if (!a.configured) {
    el.innerHTML = `<span class="hint">Login: Google nog niet geconfigureerd</span>`;
    return;
  }
  if (a.user) {
    el.innerHTML = `<span class="auth-user" title="${esc(a.user.email)}">${esc(a.user.name || a.user.email)}</span>`
      + (a.is_platform_admin ? ' <span class="badge">beheerder</span>' : "")
      + ` <button type="button" class="btn2" id="auth-logout">Uitloggen</button>`;
    const btn = $("auth-logout");
    if (btn) btn.onclick = async () => { await logout(); location.reload(); };
  } else {
    const club = ($("club") && $("club").value) || "";
    el.innerHTML = `<a class="live-btn" id="auth-login" href="${esc(loginUrl(null, club))}">Inloggen met Google</a>`;
  }
}
