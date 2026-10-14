"use strict";
// Bingo-avond: pure toestandslogica. Draaien: node --test tests/web/test_bingo_core.js
const test = require("node:test");
const assert = require("node:assert");
const B = require("../../web/baanschemaatje/bingo-core.js");

const M = [{ key: "GEM|MIERLO 1", label: "GEM", home: "MIERLO 1", away: "X 1", duration: 90,
  parts: [{ id: "GEM|MIERLO 1|DD", label: "DD", kind: "D" }, { id: "GEM|MIERLO 1|HD", label: "HD", kind: "D" }] },
{ key: "HD|MIERLO 2", label: "HEREN", home: "MIERLO 2", away: "Y 1", duration: 90, parts: [{ id: "HD|MIERLO 2|D1", label: "D1", kind: "D" }] }];
const at = (h, m) => new Date(2026, 9, 16, h, m);

test("aanmelden, toewijzen, klaar, ongedaan maken", () => {
  let s = B.bgEmpty();
  assert.strictEqual(B.bgQueue(s, M).length, 0);
  s = B.bgSetPresent(s, M[0], true, at(19, 0));
  assert.deepStrictEqual(B.bgQueue(s, M).map((p) => p.label), ["DD", "HD"]);
  s = B.bgAssign(s, M, "GEM|MIERLO 1|DD", 3, "Ann + Bo – Cor + Dirk", at(19, 5));
  assert.deepStrictEqual(B.bgFreeCourts(s, 4), [1, 2, 4]);
  assert.deepStrictEqual(B.bgQueue(s, M).map((p) => p.label), ["HD"]);
  assert.throws(() => B.bgAssign(s, M, "GEM|MIERLO 1|HD", 3, "", at(19, 6)), /bezet/);
  s = B.bgFinish(s, M, 3, at(20, 30));
  assert.ok(s.done["GEM|MIERLO 1|DD"] && !s.courts["3"]);
  assert.deepStrictEqual(B.bgQueue(s, M).map((p) => p.label), ["HD"]);
  s = B.bgUndo(s, at(20, 31));
  assert.ok(s.courts["3"] && !s.done["GEM|MIERLO 1|DD"]);
  assert.match(s.log[s.log.length - 1].msg, /^Ongedaan: Baan 3/);
  assert.strictEqual(s.log.filter((l) => /gestart/.test(l.msg)).length, 1);
});

test("waarschuwing na laatste start en na sluiting (na middernacht)", () => {
  const w = { start: "19:00", last_start: "23:30", end: "25:00" };
  assert.deepStrictEqual(B.bgWarnings(w, 90, at(22, 0)), []);
  assert.strictEqual(B.bgWarnings(w, 90, at(23, 45)).length, 2);
  assert.match(B.bgWarnings(w, 120, at(23, 15))[0], /na sluiting \(01:00\)/);
  assert.strictEqual(B.bgEveningMin(at(0, 30)), 24 * 60 + 30);
});
