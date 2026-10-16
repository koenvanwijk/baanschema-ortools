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

test("voorstel volgende partij: laagste vrije baan, minst bezette team, KNLTB-volgorde, tijdsgrens", () => {
  const w = { start: "19:00", last_start: "23:30", end: "25:00", courts: 3 };
  let s = B.bgEmpty();
  assert.strictEqual(B.bgSuggest(s, M, w, at(19, 0)), null);
  s = B.bgSetPresent(s, M[0], true, at(19, 0));
  s = B.bgSetPresent(s, M[1], true, at(19, 0));
  let g = B.bgSuggest(s, M, w, at(19, 1));
  assert.deepStrictEqual([g.court, g.label, g.match.home], [1, "DD", "MIERLO 1"]);
  s = B.bgAssign(s, M, g.part, g.court, "", at(19, 1));
  g = B.bgSuggest(s, M, w, at(19, 2));
  assert.deepStrictEqual([g.court, g.label, g.match.home], [2, "D1", "MIERLO 2"]);
  assert.strictEqual(B.bgSuggest(s, M, w, at(23, 45)), null);
  assert.ok(B.bgSuggest(s, M, w, at(23, 30 - 60)));
});

test("voorstel: partij die na sluiting eindigt wordt niet voorgesteld", () => {
  const w = { start: "19:00", last_start: "23:30", end: "24:30", courts: 2 };
  const s = B.bgSetPresent(B.bgEmpty(), M[1], true, at(19, 0));
  assert.ok(B.bgSuggest(s, M, w, at(23, 0)));
  assert.strictEqual(B.bgSuggest(s, M, w, at(23, 15)), null);
});

test("verslag achteraf: gespeelde partijen op starttijd, niet-afgeronde apart", () => {
  const { bpReport } = require("../../web/baanschemaatje/bingo-print.js");
  let s = B.bgSetPresent(B.bgEmpty(), M[0], true, at(19, 0));
  s = B.bgAssign(s, M, "GEM|MIERLO 1|HD", 2, "A – B", at(19, 10));
  s = B.bgAssign(s, M, "GEM|MIERLO 1|DD", 1, "", at(19, 20));
  s = B.bgFinish(s, M, 2, at(20, 40));
  const r = bpReport(s, M);
  assert.deepStrictEqual(r.played.map((x) => [x.part.label, x.court, x.min, x.lineup]), [["HD", 2, 90, "A – B"]]);
  assert.deepStrictEqual(r.open.map((x) => [x.part.label, x.playing && x.playing[0]]), [["DD", "1"], ["D1", undefined]]);
});

test("bingo: speler niet tegelijk op twee banen voor hetzelfde team", () => {
  let s = B.bgSetPresent(B.bgEmpty(), M[0], true, at(19, 0));
  s = B.bgAssign(s, M, "GEM|MIERLO 1|DD", 1, "Ann + Bo", at(19, 1));
  assert.throws(() => B.bgAssign(s, M, "GEM|MIERLO 1|HD", 2, "Cor + bo", at(19, 2)), /bo speelt nog op baan 1/);
  assert.ok(B.bgAssign(s, M, "GEM|MIERLO 1|HD", 2, "Cor + Dirk", at(19, 2)).courts["2"]);
});
