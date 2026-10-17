"use strict";
// "Regels gebroken" / "Kan mooier" klikbaar maken (Oscar 17-10-2026: "Ik wil dat kunnen zien").
// Pure functies (ook in Node getest): bevindingen van de validator of de directe controle → leesbare lijst
// met de bijbehorende partij(en), zodat de dagweergave ze kan aanwijzen.

// Korte uitleg per validatorregel (gewone taal). Onbekende regels tonen de validatormelding zelf.
const FD_UITLEG = {
  "VENSTER-JEUGD": { wens: "jeugd 13-17 vanaf 11:00", uitleg: "Oude modelgrens uit de validator; die regel is ingetrokken (SPEC.md). Niets aan te doen — mag je negeren." },
  "VENSTER-JEUGD-LAAT": { wens: "jeugd niet na 17:30", uitleg: "Jeugd liever niet laat op de dag laten beginnen." },
  "VENSTER-GEM": { wens: "gemengd vanaf 10:00", uitleg: "Gemengde teams liever niet vóór 10:00." },
  "EERSTE-START-VOORKEUR": { wens: "wedstrijd eerder laten beginnen", uitleg: "De wedstrijd begint later dan de clubvoorkeur." },
  "EERSTE-START": { wens: "eerste partij op tijd", uitleg: "De eerste partij begint te laat volgens het reglement." },
  "EERSTE-START-GROEN": { wens: "groen op tijd beginnen", uitleg: "Groen moet vroeg op de dag beginnen." },
  "LAATSTE-START": { wens: "uiterlijk de laatste begintijd", uitleg: "Partij begint na de laatste toegestane begintijd." },
  "DAGVENSTER": { wens: "binnen het dagvenster", uitleg: "Partij valt buiten de openingstijden van die dag." },
  "BANEN-PER-TEAM": { wens: "minder banen per team", uitleg: "Het team gebruikt meer banen dan afgesproken." },
  "BAANPAAR": { wens: "vaste baanparen", uitleg: "Het team staat niet op een afgesproken baanpaar." },
};
const FD_CAT = { JO: "jeugd_13_17", MO: "jeugd_13_17", "J13-17": "jeugd_13_17", GRO: "groen", JU: "junioren_11_14", GEM: "gemengd", HE: "senioren", DA: "senioren" };

// Rijen bij een validatorbevinding: partij + starttijd uit de melding ("S4 start 09:00"), verfijnd met het
// teamnummer (M2 → … 2) en de categorie uit het onderwerp ("JO13-17 1e M2").
function fdRowsFor(f, rows) {
  const m = /^(\w+) start (\d\d:\d\d)/.exec(f.message || "");
  let c = rows.map((r, i) => [r, i]).filter(([r]) => r.kind !== "W" && r.court);
  if (m) c = c.filter(([r]) => r.part === m[1] && r.start === m[2]);
  const subj = String(f.subject || "");
  const nr = /M(\d+)\b/.exec(subj);
  if (nr && c.length > 1) { const k = c.filter(([r]) => new RegExp(`\\b${nr[1]}$`).test(r.home_team || "")); if (k.length) c = k; }
  const cat = Object.keys(FD_CAT).find((k) => subj.toUpperCase().startsWith(k));
  if (cat && c.length > 1) { const k = c.filter(([r]) => r.category === FD_CAT[cat]); if (k.length) c = k; }
  if (!m) c = c.filter(([r]) => subj && (r.label && subj.includes(r.label)));
  return c.map(([, i]) => i);
}

// Lijst voor de tegels. bron: validatorbevindingen als die bij de getoonde tellingen horen, anders directe controle.
function fdItems(plan, club, directIssues) {
  const rows = plan.rows || [];
  const v = plan.validator || {};
  const fs = Array.isArray(v.findings) ? v.findings : null;
  const fromValidator = fs && (v.hard ?? 0) + (v.model ?? 0) === fs.length;
  const out = [];
  if (fromValidator) {
    for (const f of fs) {
      const idx = fdRowsFor(f, rows);
      const r = rows[idx[0]];
      const u = FD_UITLEG[f.rule] || {};
      const m = /^(\w+) start (\d\d:\d\d)/.exec(f.message || "");
      let note = "";
      if (r && r.export_start && m) {
        const first = rows.filter((x) => x.team_id === r.team_id && x.court).map((x) => x.start).sort()[0];
        if (first === r.export_start) note = `Begintijd ${r.export_start} ligt vast in de KNLTB-export.`;
      }
      out.push({ kind: f.severity === "HARD" ? "hard" : "model", rule: f.rule,
        who: r ? `${r.label} ${r.home_team} – ${r.away_team}` : f.subject || "", part: r ? r.part : (m && m[1]) || "",
        actual: r ? `${r.start} · baan ${r.court}` : (m ? m[2] : ""), wish: u.wens || "", uitleg: [u.uitleg || f.message, note].filter(Boolean).join(" "),
        detail: f.message, rows: idx });
    }
  } else {
    const hardLv = ["conflict", "Spelersconflict", "Volgorde", "KNLTB"];
    for (const x of directIssues || []) {
      const r = rows[(x.rows || [])[0]];
      out.push({ kind: hardLv.includes(x.level) ? "hard" : "model", rule: x.rule || x.level,
        who: r ? `${r.label} ${r.home_team} – ${r.away_team}` : "", part: r ? r.part : "", actual: r && r.start ? `${r.start} · baan ${r.court}` : "",
        wish: "", uitleg: x.msg, detail: x.msg, rows: x.rows || [] });
    }
  }
  return out;
}

// Al opgeslagen schema's: dezelfde ingetrokken bevinding wegfilteren en de telling bijwerken (zonder opnieuw opslaan).
const fdObsolete = (f) => f && f.rule === "VENSTER-JEUGD" && /ingetrokken/.test(f.message || "");
function fdCleanValidator(v, by) {
  if (!v || !Array.isArray(v.findings)) return v;
  const drop = v.findings.filter(fdObsolete);
  if (!drop.length) return v;
  const out = { ...v, findings: v.findings.filter((f) => !fdObsolete(f)) };
  if (typeof v.model === "number" && (!by || by === "solver-validatie")) out.model = Math.max(0, v.model - drop.filter((f) => f.severity !== "HARD").length);
  return out;
}

if (typeof module !== "undefined") module.exports = { fdItems, fdRowsFor, FD_UITLEG, fdCleanValidator, fdObsolete };
