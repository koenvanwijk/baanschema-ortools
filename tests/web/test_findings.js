"use strict";
const test = require("node:test");
const assert = require("node:assert");
const F = require("../../web/baanschemaatje/findings.js");
const R = (label, home, cat, part, start, court, exp = "") => ({ team_id: `${label} · ${home}`, label, home_team: home, away_team: "X", category: cat, part, kind: "S", start, end: "", court, export_start: exp });
const rows = [R("GRO", "MIERLO 2", "groen", "S4", "09:00", 2, "09:00"), R("J13-17", "MIERLO 2", "jeugd_13_17", "S4", "09:00", 3, "09:00"), R("J13-17", "MIERLO 2", "jeugd_13_17", "S1", "10:30", 4, "09:00")];
const old = { rule: "VENSTER-JEUGD", severity: "MODEL", message: "S4 start 09:00, model dwingt jeugd 13-17 vanaf 11:00 af — die grens is met SPEC.md ingetrokken", subject: "JO13-17 1e M2" };

test("ingetrokken jeugd-11:00-check telt niet mee (18-10-2026: Kan mooier 4 → 0)", () => {
  const v = F.fdCleanValidator({ hard: 0, model: 4, findings: [old, old, old, old] }, "solver-validatie");
  assert.deepStrictEqual([v.model, v.findings.length], [0, 0]);
  assert.strictEqual(F.fdCleanValidator({ hard: 0, model: 1, findings: [old] }, "directe controle").model, 1);
});

test("bevinding → juiste partij, met uitleg en exporttijd-notitie", () => {
  const f = { rule: "VENSTER-JEUGD-LAAT", severity: "MODEL", message: "S4 start 09:00, jeugd niet na 17:30", subject: "JO13-17 1e M2" };
  assert.deepStrictEqual(F.fdRowsFor(f, rows), [1]);
  const it = F.fdItems({ rows, validator: { hard: 0, model: 1, findings: [f] } }, {}, []);
  assert.strictEqual(it[0].who, "J13-17 MIERLO 2 – X");
  assert.match(it[0].uitleg, /vast in de KNLTB-export/);
  const d = F.fdItems({ rows, validator: {} }, {}, [{ level: "clubafspraak", rule: "x", msg: "te laat", rows: [2] }]);
  assert.deepStrictEqual([d[0].kind, d[0].part, d[0].actual], ["model", "S1", "10:30 · baan 4"]);
});
