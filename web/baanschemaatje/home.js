"use strict";
// Product-frontpage: login → mijn clubs. Geen publieke clublijst.

const LAST_CLUB_KEY = "bs_last_club";

function clubHref(id) {
  return `/club/${encodeURIComponent(id)}`;
}

function rememberClub(id) {
  try { localStorage.setItem(LAST_CLUB_KEY, id); } catch (_) { /* private mode */ }
}

function lastClub() {
  try { return localStorage.getItem(LAST_CLUB_KEY) || ""; } catch (_) { return ""; }
}

function renderLoggedOut() {
  $("hero").hidden = false;
  $("clubs-panel").hidden = true;
  $("new-panel").hidden = true;
  const login = $("cta-login");
  if (login) login.href = loginUrl("/", "");
  renderAuthBar();
  const barLogin = $("auth-login");
  if (barLogin) barLogin.href = loginUrl("/", "");
}

function roleLabel(c) {
  if (c.my_role_label) return c.my_role_label;
  if ((AUTH || {}).is_platform_admin) return "Platformbeheerder";
  return "";
}

function renderClubs(clubs) {
  $("hero").hidden = true;
  $("clubs-panel").hidden = false;
  const recent = lastClub();
  const list = $("club-list");
  const empty = $("clubs-empty");
  if (!clubs.length) {
    list.innerHTML = "";
    empty.hidden = false;
  } else {
    empty.hidden = true;
    const sorted = [...clubs].sort((a, b) => {
      if (a.id === recent) return -1;
      if (b.id === recent) return 1;
      return String(a.name || a.id).localeCompare(String(b.name || b.id), "nl");
    });
    list.innerHTML = sorted.map((c) => {
      const role = roleLabel(c);
      const bits = [];
      if (c.demo) bits.push("demo");
      if (c.courts) bits.push(`${c.courts} banen`);
      if (c.has_season) bits.push("seizoen geladen");
      const meta = bits.join(" · ") || c.id;
      return `<a class="club-card${c.id === recent ? " recent" : ""}" href="${esc(clubHref(c.id))}" data-club="${esc(c.id)}">
        <p class="name">${esc(c.name || c.id)}${c.demo ? ' <span class="badge demo">demo</span>' : ""}</p>
        <p class="meta">${esc(meta)}</p>
        ${role ? `<span class="badge role">${esc(role)}</span>` : ""}
        ${c.id === recent ? '<span class="badge" style="background:#ece4fb;color:#5b2fa0">Laatst gebruikt</span>' : ""}
      </a>`;
    }).join("");
    list.querySelectorAll("a.club-card").forEach((a) => {
      a.addEventListener("click", () => rememberClub(a.dataset.club));
    });
  }
  const newBtn = $("new-club-btn");
  if (newBtn) {
    newBtn.hidden = !(AUTH && AUTH.can_create_club);
    newBtn.onclick = () => {
      $("new-panel").hidden = false;
      $("new-name").focus();
    };
  }
  renderAuthBar();
  const barLogin = $("auth-login");
  if (barLogin) barLogin.href = loginUrl("/", "");
}

async function createClubFromHome() {
  const st = $("new-status");
  const name = ($("new-name").value || "").trim();
  if (!name) { st.className = "live-status err"; st.textContent = "Vul een clubnaam in."; return; }
  const id = ($("new-id").value || "").trim().toLowerCase() || undefined;
  const knltb = ($("new-knltb").value || "").trim().toUpperCase() || name.toUpperCase();
  const courts = Math.max(1, Math.min(40, parseInt($("new-courts").value, 10) || 6));
  const profile = {
    club: { name, knltb_name: knltb },
    courts: { count: courts },
    day: { start: "09:00", fallback_start: "08:30", last_start: "19:30", end: "20:00", evening_close_margin: "01:30" },
    weekdays: { zaterdag: { mode: "gepland" }, zondag: { mode: "gepland" } },
  };
  const body = { profile };
  if (id) body.id = id;
  st.className = "live-status busy"; st.textContent = "Aanmaken…";
  try {
    const r = await api("/clubs", jsonOpts("POST", body));
    rememberClub(r.id);
    st.className = "live-status ok";
    st.textContent = `Club ${r.id} aangemaakt.`;
    location.href = clubHref(r.id);
  } catch (e) {
    st.className = "live-status err";
    st.textContent = e.message || String(e);
  }
}

async function boot() {
  try {
    AUTH = await api("/auth/status");
  } catch (_) {
    AUTH = { configured: false, user: null };
  }

  if (!(AUTH && AUTH.user)) {
    renderLoggedOut();
    return;
  }

  let clubs = [];
  try {
    const j = await api("/clubs?mine=1");
    clubs = j.clubs || [];
    AUTH = j.auth || AUTH;
  } catch (e) {
    $("clubs-hint").textContent = `Kon clubs niet laden: ${e.message || e}`;
  }

  const params = new URLSearchParams(location.search);
  if (clubs.length === 1 && !(AUTH && AUTH.is_platform_admin) && params.get("stay") !== "1") {
    rememberClub(clubs[0].id);
    location.replace(clubHref(clubs[0].id));
    return;
  }

  renderClubs(clubs);

  $("new-cancel").onclick = () => { $("new-panel").hidden = true; };
  $("new-create").onclick = createClubFromHome;
}

boot();
