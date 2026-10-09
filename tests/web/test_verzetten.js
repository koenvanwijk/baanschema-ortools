"use strict";
// Node-unittests voor wedstrijden verzetten (web/baanschemaatje/verzetten.js). Geen server, geen solver.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const mv = require("../../web/baanschemaatje/verzetten.js");

const WEB = path.join(__dirname, "../../web/baanschemaatje");
const KAL = vm.runInNewContext(`${fs.readFileSync(path.join(WEB, "knltb-kalender.js"), "utf8")}; KNLTB_KALENDER`);
const plan27 = JSON.parse(fs.readFileSync(path.join(WEB, "data/mierlo/27-09-2026.json")));
const MATCH_DAYS = ["06-09-2026", "13-09-2026", "20-09-2026", "27-09-2026", "04-10-2026", "11-10-2026"].map((date) => ({ date, match: {} }));
const team = (pred) => mv.mvFromRows(plan27.rows).find(pred);
const ju = () => team((w) => w.label === "JU11-14" && w.home === "MIERLO 3");
const heren = () => team((w) => w.label === "HEREN");

test("wedstrijden uit planregels: 1 per team, met partijen", () => {
  const ws = mv.mvFromRows(plan27.rows);
  assert.strictEqual(ws.length, 11);
  const w = ju();
  assert.strictEqual(w.matches, 6);
  assert.strictEqual(w.singles + w.doubles, 6);
});

test("doeldagen: junioren → inhaaldagen 11/18/25 okt; regulier → 18/25 okt + 1 nov; 1 nov niet voor junioren", () => {
  const tj = mv.mvTargets(ju(), "27-09-2026", MATCH_DAYS, KAL);
  const inh = (t) => t.filter((x) => x.kind === "inhaaldag" && x.valid).map((x) => x.date);
  assert.deepStrictEqual(inh(tj), ["11-10-2026", "18-10-2026", "25-10-2026"]);
  assert.ok(tj.some((x) => x.date === "01-11-2026" && !x.valid));
  assert.ok(!tj.some((x) => x.date === "27-09-2026"));
  const th = mv.mvTargets(heren(), "27-09-2026", MATCH_DAYS, KAL);
  assert.deepStrictEqual(inh(th), ["18-10-2026", "25-10-2026", "01-11-2026"]);
  // 11-10 is voor de reguliere competitie een gewone speeldag
  assert.ok(th.some((x) => x.date === "11-10-2026" && x.kind === "speeldag" && x.valid));
  assert.strictEqual(mv.mvComp("groen"), "rog");
  assert.strictEqual(mv.mvComp("jeugd_13_17"), "junioren");
  assert.strictEqual(mv.mvComp("gemengd"), "regulier");
});

test("verzetten: bron verliest het team, doel krijgt het als niet ingepland (verzet van)", () => {
  const st = new mv.MoveState();
  st.move([{ w: ju(), at: "27-09-2026", to: "18-10-2026" }]);
  const src = mv.mvApplyPlan(plan27, "27-09-2026", st);
  assert.ok(!src.rows.some((r) => r.team_id === ju().key));
  assert.strictEqual(src.rows.length, plan27.rows.length - 6);
  const dst = mv.mvApplyPlan({ rows: [] }, "18-10-2026", st);
  assert.strictEqual(dst.rows.length, 6);
  assert.ok(dst.rows.every((r) => r.start === "NIET_GELUKT" && r.court === null && r.moved_from === "27-09-2026"));
  assert.deepStrictEqual(dst.rows.map((r) => r.part).sort(), ju().rows.map((r) => r.part).sort());
});

test("regen: meerdere teams elk naar een eigen dag; undo en reset", () => {
  const st = new mv.MoveState();
  st.move([{ w: ju(), at: "27-09-2026", to: "18-10-2026" }]);
  st.move([{ w: heren(), at: "27-09-2026", to: "01-11-2026" }]);
  assert.strictEqual(st.count, 2);
  assert.strictEqual(st.into("18-10-2026").length, 1);
  assert.strictEqual(st.into("01-11-2026").length, 1);
  assert.strictEqual(st.outOf("27-09-2026").length, 2);
  assert.deepStrictEqual(st.forServer().map((x) => x.to).sort(), ["01-11-2026", "18-10-2026"]);
  st.undo();
  assert.strictEqual(st.count, 1);
  st.reset();
  assert.strictEqual(st.count, 0);
  st.undo();
  assert.strictEqual(st.count, 1);
});

test("nogmaals verzetten houdt de oorspronkelijke dag; terug naar de oorspronkelijke dag heft op", () => {
  const st = new mv.MoveState();
  st.move([{ w: ju(), at: "27-09-2026", to: "18-10-2026" }]);
  const moved = { ...ju(), moved_from: "27-09-2026" };
  st.move([{ w: moved, at: "18-10-2026", to: "25-10-2026" }]);
  assert.strictEqual(st.count, 1);
  assert.deepStrictEqual([st.list[0].from, st.list[0].to], ["27-09-2026", "25-10-2026"]);
  assert.strictEqual(st.current(ju().key, "27-09-2026"), "25-10-2026");
  st.move([{ w: moved, at: "25-10-2026", to: "27-09-2026" }]);
  assert.strictEqual(st.count, 0);
});

test("handtekening per dag verandert alleen voor geraakte dagen", () => {
  const st = new mv.MoveState();
  const a = st.sig("04-10-2026"), b = st.sig("18-10-2026");
  st.move([{ w: ju(), at: "27-09-2026", to: "18-10-2026" }]);
  assert.strictEqual(st.sig("04-10-2026"), a);
  assert.notStrictEqual(st.sig("18-10-2026"), b);
  assert.ok(st.touches("27-09-2026") && !st.touches("04-10-2026"));
});

test("partijen zonder planregels: gemengd uit schema, anders 2/3 enkels; Rood/Oranje als 1 reservering", () => {
  assert.deepStrictEqual(mv.mvParts({ schema: "Gemengd Zondag – 1e klasse (2DE-2HE-DD-HD-2GD) – Afdeling 1", matches: 8 }).map((p) => p[0]),
    ["S1", "S2", "S3", "S4", "D1", "D2", "GD1", "GD2"]);
  assert.deepStrictEqual(mv.mvParts({ schema: "Jongens 13 t/m 17 jaar Zondag – 1e klasse", matches: 6 }).map((p) => p[1]).join(""), "SSSSDD");
  assert.deepStrictEqual(mv.mvParts({ schema: "x", matches: 6, singles: 4, doubles: 2, mix: 0 }).length, 6);
  const rood = mv.mvRowsFor({ key: "R · M", schema: "Rood 2", home: "M", category: "rood", matches: 1, from: "27-09-2026" });
  assert.strictEqual(rood.length, 1);
  assert.strictEqual(rood[0].kind, "W");
});
