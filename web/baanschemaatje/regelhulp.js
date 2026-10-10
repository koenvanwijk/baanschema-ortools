"use strict";
// KNLTB-regelhulp: vraag -> POST /regelhulp -> antwoord met klikbare bronnen.
// Alleen op verzenden; niets automatisch.
(function () {
  const API_RH = (new URLSearchParams(location.search).get("api") || "https://baanschemaatje-356953092000.europe-west1.run.app").replace(/\/+$/, "");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // Bronlabel (zoals "CR art. 49 lid 1" of "Wedstrijdbulletin 2026, 'Opstelling'") -> regex
  // die aanhalingstekens en witruimte vergeeft.
  function labelRe(label) {
    const parts = String(label).replace(/['‘’"“”«»]/g, "").trim().split(/\s+/)
      .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    return parts.join("\\s+['‘’\"“”«»]?") ;
  }

  // Mini-markdown: **vet**, lijsten, alinea's; bronlabels en [n] worden links.
  function renderMd(md, bronnen) {
    const list0 = (bronnen || []).slice().sort((a, b) => b.label.length - a.label.length);
    const byN = Object.fromEntries((bronnen || []).map((b) => [b.n, b]));
    const re = list0.length ? new RegExp(`['‘’"“”«»]?(?:${list0.map((b) => labelRe(b.label)).join("|")})['‘’"“”«»]?(?![0-9])`, "gi") : null;
    const findB = (m) => {
      const k = m.replace(/['‘’"“”«»\s]+/g, " ").trim().toLowerCase();
      return list0.find((b) => b.label.replace(/['‘’"“”«»\s]+/g, " ").trim().toLowerCase() === k);
    };
    const link = (b, txt) => `<a class="rh-ref" href="${esc(b.url)}" target="_blank" rel="noopener" title="${esc(b.bron || b.label)}">${txt}</a>`;
    const inline = (s) => {
      let out = "", last = 0;
      if (re) {
        for (const m of s.matchAll(re)) {
          const b = findB(m[0]);
          out += esc(s.slice(last, m.index)) + (b ? link(b, esc(m[0])) : esc(m[0]));
          last = m.index + m[0].length;
        }
      }
      out += esc(s.slice(last));
      return out
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/(^|[^*])\*(?!\s)(.+?)\*/g, "$1<em>$2</em>")
        .replace(/\[(\d{1,2})\]/g, (m, n) => byN[n] ? link(byN[n], `[${n}]`) : "");
    };
    const out = [];
    let list = null;
    for (const raw of String(md || "").split("\n")) {
      const line = raw.trim();
      const li = line.match(/^(?:[-*•]|\d+\.)\s+(.*)$/);
      if (li) {
        if (!list) { list = /^\d/.test(line) ? "ol" : "ul"; out.push(`<${list}>`); }
        out.push(`<li>${inline(li[1])}</li>`);
        continue;
      }
      if (list) { out.push(`</${list}>`); list = null; }
      if (line) out.push(`<p>${inline(line.replace(/^#+\s*/, ""))}</p>`);
    }
    if (list) out.push(`</${list}>`);
    return out.join("");
  }

  function renderBronnen(bronnen) {
    if (!bronnen || !bronnen.length) return "";
    return `<h3>Bronnen</h3><ol class="rh-bronnen">${bronnen.map((b) => `<li value="${b.n}">
      <a href="${esc(b.url)}" target="_blank" rel="noopener"><strong>${esc(b.label)}</strong></a>
      <span class="hint">${esc(b.bron)}${b.versie ? ` · ${/^\d{4}-\d{2}-\d{2}$/.test(b.versie) ? "release " + b.versie.split("-").reverse().join("-") : esc(b.versie)}` : ""}</span>
      <blockquote>${esc(b.quote)}</blockquote></li>`).join("")}</ol>`;
  }

  async function ask(form) {
    const q = form.querySelector("textarea").value.trim();
    const out = document.getElementById("rh-out");
    const btn = form.querySelector("button");
    if (q.length < 3) return;
    const clubSel = document.getElementById("club");
    const club = form.querySelector("#rh-club")?.checked && clubSel ? clubSel.value : null;
    btn.disabled = true;
    out.innerHTML = `<p class="hint">Bezig met zoeken in de KNLTB-regels…</p>`;
    try {
      const r = await fetch(`${API_RH}/regelhulp`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vraag: q, club }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
      out.innerHTML = `<div class="rh-answer">${renderMd(j.antwoord, j.bronnen)}</div>${renderBronnen(j.bronnen)}
        <p class="hint rh-disc">${esc(j.disclaimer || "")}${j.regelbank ? ` Regelbank van ${esc(String(j.regelbank).slice(0, 10))}.` : ""}</p>`;
    } catch (e) {
      out.innerHTML = `<p class="err">Geen antwoord: ${esc(e.message)}</p>`;
    } finally {
      btn.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("rh-form");
    if (!form) return;
    form.addEventListener("submit", (ev) => { ev.preventDefault(); ask(form); });
    form.querySelector("textarea").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); ask(form); }
    });
  });
  if (typeof module !== "undefined") module.exports = { renderMd };
})();
