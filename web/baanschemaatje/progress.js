"use strict";
// Voortgang van "Nu berekenen" / "Zoek oplossingen" (alleen in de browser).
// De server meldt geen tussenstand; de balk is een schatting op basis van verstreken tijd
// t.o.v. de verwachte duur (rekentijd per poging × mogelijke pogingen).

let PG_FIRST_CALL = true; // eerste aanroep in deze sessie: Cloud Run moet mogelijk opstarten

// Fases voor één dag plannen: meestal 1 poging; past niet alles, dan nog 2 (zoeken + passend maken);
// lukt dat niet, dan dezelfde reeks met de terugval-dagstart (bv. 08:30).
function pgStages(kind, tl, n = 1) {
  const o = 5; // opstart/controle
  if (kind === "scenarios") return [{ end: n * tl + 2 * tl + o, label: "Oplossingen doorrekenen…" }];
  return [
    { end: tl + o, label: "Rekenen…" },
    { end: 3 * tl + o, label: "Rekenen… extra poging (niet alles paste meteen)" },
    { end: 6 * tl + o, label: "Rekenen… met terugval-dagstart" },
  ];
}

// Toestand op tijdstip `el` (s): {pct, label, stage, over}. cold = eerste aanroep (server opstarten).
function pgState(stages, el, cold) {
  if (el < (cold ? 8 : 1.5)) return { pct: Math.min(4, el), label: cold ? "Server opstarten…" : "Verbinden…", stage: -1, over: false };
  const last = stages[stages.length - 1];
  if (el >= last.end) return { pct: 97, label: "Bijna klaar…", stage: stages.length, over: true };
  const k = stages.findIndex((s) => el < s.end);
  const lo = k ? stages[k - 1].end : 0;
  const pct = Math.min(95, (100 * el) / stages[k].end);
  return { pct: Math.max(pct, (100 * lo) / stages[k].end), label: stages[k].label, stage: k, over: false, max: stages[k].end };
}

class Progress {
  constructor(el) { this.el = el; this.timer = null; }

  // opts: {title, kind: "plan"|"scenarios", tl, n, onCancel}
  start(opts) {
    this.stop();
    this.opts = opts;
    this.t0 = performance.now();
    this.cold = PG_FIRST_CALL;
    PG_FIRST_CALL = false;
    this.stages = pgStages(opts.kind || "plan", opts.tl, opts.n);
    this.el.hidden = false;
    this.el.classList.remove("ok", "warn", "err"); this.el.classList.add("pg", "running");
    this.el.innerHTML = `<div class="pg-head"><b class="pg-title"></b> <span class="pg-label"></span>
        <span class="pg-time"></span>${opts.onCancel ? ` <button class="btn2 pg-cancel">Annuleren</button>` : ""}</div>
      <div class="pg-bar"><span></span></div>`;
    const c = this.el.querySelector(".pg-cancel");
    if (c) c.onclick = () => { c.disabled = true; opts.onCancel(); };
    this.tick();
    this.timer = setInterval(() => this.tick(), 250);
  }

  setTitle(t) { if (this.opts) { this.opts.title = t; this.tick(); } }

  tick() {
    const el = (performance.now() - this.t0) / 1000;
    const st = pgState(this.stages, el, this.cold);
    this.el.querySelector(".pg-title").textContent = this.opts.title || "";
    this.el.querySelector(".pg-label").textContent = st.label;
    this.el.querySelector(".pg-time").textContent = `${Math.floor(el)}s${st.max ? ` (verwacht tot ~${Math.round(st.max)}s)` : ""}`;
    this.el.querySelector(".pg-bar span").style.width = `${st.pct}%`;
  }

  stop() { if (this.timer) clearInterval(this.timer); this.timer = null; }

  // cls: ok | warn | err
  finish(msg, cls = "ok") {
    this.stop();
    if (!this.opts) return;
    const el = Math.round((performance.now() - this.t0) / 1000);
    this.el.classList.remove("running", "ok", "warn", "err"); if (cls) this.el.classList.add(cls);
    this.el.querySelector(".pg-bar span").style.width = cls === "err" ? this.el.querySelector(".pg-bar span").style.width : "100%";
    this.el.querySelector(".pg-label").textContent = msg;
    this.el.querySelector(".pg-time").textContent = `${el}s`;
    const c = this.el.querySelector(".pg-cancel");
    if (c) c.remove();
  }
}

// "Klaar: 25 ingepland, 0 niet, 0 overtredingen"
function pgDoneText(summary, hard) {
  const h = hard ?? summary.hard;
  return `Klaar: ${summary.scheduled} ingepland, ${summary.unscheduled} niet${h != null ? `, ${h} overtreding${h === 1 ? "" : "en"}` : ""}`;
}

if (typeof module !== "undefined") module.exports = { pgStages, pgState, pgDoneText };
