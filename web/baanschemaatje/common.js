"use strict";
// Baanschemaatje: gedeelde helpers voor clubpagina (club.html) en club-instellingen (club-instellingen.html).
// Praat met de live-backend (server/baanschemaatje). Geen login (nog): zie ROADMAP "Login per club".

const API_DEFAULT = "https://baanschemaatje-356953092000.europe-west1.run.app";
const API = (new URLSearchParams(location.search).get("api") || API_DEFAULT).replace(/\/+$/, "");

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const toMin = (hhmm) => parseInt(hhmm.slice(0, 2), 10) * 60 + parseInt(hhmm.slice(3, 5), 10);
// Tijd ná middernacht ("25:00") tonen als "01:00".
const clockHHMM = (hhmm) => { const m = toMin(hhmm); return m >= 1440 ? `${toHHMM(m - 1440)} (volgende dag)` : hhmm; };
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
};

let CLUBS = [];
let CLUB = null;      // GET /clubs/{id}
let DATES = [];

function status(msg, cls = "") { const el = $("status"); el.className = `live-status ${cls}`; el.textContent = msg; }

async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, opts);
  let body = null;
  try { body = await res.json(); } catch (_) { /* geen JSON */ }
  if (!res.ok) {
    const d = body && body.detail;
    throw new Error(typeof d === "string" ? d : d && d.message ? d.message : `HTTP ${res.status}`);
  }
  return body;
}
const jsonOpts = (method, data) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

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
  $("club").innerHTML = CLUBS.map((c) =>
    `<option value="${esc(c.id)}">${esc(c.name)}${c.demo ? " — demo" : ""}${c.stored ? "" : " (alleen lezen)"}</option>`).join("");
  const dflt = (CLUBS.find((c) => c.id === "mierlo") || CLUBS[0]).id;
  const want = select || parseHash().club || dflt;
  $("club").value = CLUBS.some((c) => c.id === want) ? want : dflt;
}

