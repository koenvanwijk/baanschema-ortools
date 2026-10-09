"use strict";
// Node-unittests voor de directe controle in web/baanschemaatje/editor.js.
// Draaien: node --test tests/web/test_editor_checks.js   (geen dependencies, geen server, geen solver)
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { checkPlan } = require("../../web/baanschemaatje/editor.js");

const DATA = path.join(__dirname, "../../web/baanschemaatje/data");
const club = JSON.parse(fs.readFileSync(path.join(DATA, "index.json"))).clubs.find((c) => c.id === "mierlo");

const row = (team, part, start, end, court, extra = {}) => ({
  team_id: team, home_team: team, label: "T", part, kind: part[0], category: "senioren", start, end, court, ...extra,
});
const rules = (res) => res.issues.map((i) => `${i.level}:${i.rule}`);

test("bestaand mierlo-plan: geen baanconflicten of KNLTB-overtredingen", () => {
  for (const f of fs.readdirSync(path.join(DATA, "mierlo")).filter((f) => f.endsWith(".json"))) {
    const plan = JSON.parse(fs.readFileSync(path.join(DATA, "mierlo", f)));
    const bad = checkPlan(plan.rows, club).issues.filter((i) => i.level === "conflict" || i.level === "KNLTB");
    assert.deepStrictEqual(bad, [], f);
  }
});

test("baanoverlap", () => {
  const res = checkPlan([row("A", "S1", "10:00", "11:30", 1), row("B", "S1", "11:00", "12:30", 1)], club);
  assert.ok(rules(res).includes("conflict:baan-overlap"));
  assert.deepStrictEqual(res.byRow.get(0).length, 1);
});

test("aansluitend op dezelfde baan is geen overlap", () => {
  const res = checkPlan([row("A", "S1", "10:00", "11:30", 1), row("B", "S1", "11:30", "13:00", 1)], club);
  assert.ok(!rules(res).includes("conflict:baan-overlap"));
});

test("baan buiten bereik", () => {
  assert.ok(rules(checkPlan([row("A", "S1", "10:00", "11:30", 11)], club)).includes("conflict:baan"));
});

test("KNLTB: begintijd niet op heel/half uur", () => {
  assert.ok(rules(checkPlan([row("A", "S1", "10:15", "11:45", 1)], club)).includes("KNLTB:match_start_grid"));
});

test("KNLTB: eerste start na 16:30", () => {
  assert.ok(rules(checkPlan([row("A", "S1", "17:00", "18:30", 1)], club)).includes("KNLTB:match_start_window"));
});

test("KNLTB: laatste start na 19:30", () => {
  const rs = [row("A", "S1", "10:00", "11:30", 1), row("A", "D1", "19:45", "21:15", 2)];
  assert.ok(rules(checkPlan(rs, club)).includes("KNLTB:laatste-start"));
});

test("clubafspraak: meer dan max banen tegelijk", () => {
  const rs = [1, 2, 3, 4].map((c) => row("A", `S${c}`, "10:00", "11:30", c));
  assert.ok(rules(checkPlan(rs, club)).includes("clubafspraak:max-banen"));
  const ok = [1, 2, 3].map((c) => row("A", `S${c}`, "10:00", "11:30", c));
  assert.ok(!rules(checkPlan(ok, club)).includes("clubafspraak:max-banen"));
});

test("clubafspraak: 8 partijen buiten 10:00–11:00 (KNLTB staat het toe)", () => {
  const rs = Array.from({ length: 8 }, (_, k) => row("A", `P${k}`, k < 3 ? "09:00" : "12:00", k < 3 ? "10:30" : "13:30", (k % 3) + 1));
  const r = rules(checkPlan(rs, club));
  assert.ok(r.includes("clubafspraak:start_window_8p"));
  assert.ok(!r.includes("KNLTB:start_window_8p"));
});

test("junioren: 14:00 is clubafspraak (club 13:00), 15:30 is KNLTB (uiterlijk 15:00)", () => {
  const j = (s, e) => [row("J", "S1", s, e, 1, { category: "junioren_11_14" })];
  assert.ok(rules(checkPlan(j("14:00", "15:30"), club)).includes("clubafspraak:junioren_latest_start"));
  assert.ok(rules(checkPlan(j("15:30", "17:00"), club)).includes("KNLTB:junioren_latest_start"));
});
