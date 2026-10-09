"use strict";
// Node-unittests voor de voortgangsschatting (web/baanschemaatje/progress.js).
const test = require("node:test");
const assert = require("node:assert");
const { pgStages, pgState, pgDoneText } = require("../../web/baanschemaatje/progress.js");

test("fases: 1 poging, extra pogingen, terugval-dagstart; daarna 'Bijna klaar…'", () => {
  const st = pgStages("plan", 30);
  assert.deepStrictEqual(st.map((s) => s.end), [35, 95, 185]);
  assert.strictEqual(pgState(st, 3, true).label, "Server opstarten…");
  assert.strictEqual(pgState(st, 1, false).label, "Verbinden…");
  assert.strictEqual(pgState(st, 20, false).label, "Rekenen…");
  assert.ok(/extra poging/.test(pgState(st, 50, false).label));
  assert.ok(/terugval/.test(pgState(st, 120, false).label));
  const over = pgState(st, 200, false);
  assert.strictEqual(over.label, "Bijna klaar…");
  assert.ok(over.over && over.pct < 100);
});

test("balk loopt monotoon op en blijft onder 100% tot het antwoord er is", () => {
  const st = pgStages("plan", 20);
  let prev = -1;
  for (let t = 0; t < 200; t += 0.5) {
    const p = pgState(st, t, true).pct;
    assert.ok(p >= prev - 1e-9 || pgState(st, t - 0.5, true).stage !== pgState(st, t, true).stage, `t=${t}`);
    assert.ok(p < 100);
    prev = p;
  }
});

test("oplossingen: verwachte duur = aantal × rekentijd + basis", () => {
  const st = pgStages("scenarios", 30, 8);
  assert.strictEqual(st[0].end, 8 * 30 + 60 + 5);
});

test("klaartekst", () => {
  assert.strictEqual(pgDoneText({ scheduled: 25, unscheduled: 0, hard: 0 }), "Klaar: 25 ingepland, 0 niet, 0 overtredingen");
  assert.strictEqual(pgDoneText({ scheduled: 60, unscheduled: 6, hard: 1 }), "Klaar: 60 ingepland, 6 niet, 1 overtreding");
});
