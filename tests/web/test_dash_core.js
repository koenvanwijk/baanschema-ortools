"use strict";
const test = require("node:test");
const assert = require("node:assert");
const D = require("../../web/baanschemaatje/dash-core.js");
const R = (home, part, start, end, court) => ({ team_id: `T · ${home}`, label: "HD", home_team: home, away_team: "X", part, kind: "S", start, end, court });
const PLAN = { rows: [R("M 1", "S1", "09:00", "10:30", 1), R("M 1", "S2", "09:00", "10:30", 2), R("M 1", "D1", "10:30", "12:00", 1), { kind: "W", court: 5, start: "09:00" }, R("M 2", "S1", "11:00", "12:30", 3)] };
const at = (h, m) => new Date(2026, 9, 18, h, m);

test("dagoverzicht: status, banen nu, uitloop", () => {
  const rows = D.dsRows(PLAN);
  assert.strictEqual(rows.length, 4);
  let s = D.dsEmpty();
  assert.deepStrictEqual(D.dsStatus(rows[0], s, 9 * 60 + 2), { status: "gepland", late: false });
  assert.strictEqual(D.dsStatus(rows[0], s, 9 * 60 + 10).late, true);
  s.parts[D.dsPid(rows[0])] = { status: "bezig", start: at(9, 5).toISOString(), court: 1 };
  s.teams["T · M 2"] = { status: "staakt" };
  const cs = D.dsCourts(rows, s, 9 * 60 + 30, 3);
  assert.strictEqual(cs[0].cur.part, "S1");
  assert.strictEqual(cs[0].next.part, "D1");
  assert.strictEqual(cs[2].next, null);
  assert.strictEqual(D.dsStatus(rows[3], s, 600).status, "gestaakt");
  assert.strictEqual(D.dsOverrun(rows[0], s, at(10, 50)), 15);
  assert.strictEqual(D.dsOverrun(rows[0], s, at(10, 0)), 0);
});

test("verloop: start/klaar/team/ongedaan", () => {
  const rows = D.dsRows(PLAN);
  let s = D.dsStart(D.dsEmpty(), rows[0], 4, at(9, 3));
  assert.deepStrictEqual([s.parts[D.dsPid(rows[0])].court, D.dsStatus(rows[0], s, 600).status], [4, "bezig"]);
  assert.match(s.log[0].msg, /gepland op baan 1/);
  assert.throws(() => D.dsFinish(s, rows[1], at(9, 4)), /niet bezig/);
  s = D.dsFinish(s, rows[0], at(10, 40));
  assert.strictEqual(D.dsStatus(rows[0], s, 640).status, "klaar");
  s = D.dsTeam(s, "T · M 2", "HD M 2", "te_laat", {}, at(10, 41));
  assert.strictEqual(s.teams["T · M 2"].status, "te_laat");
  s = D.dsUndo(s, at(10, 42));
  assert.ok(!s.teams["T · M 2"] && s.parts[D.dsPid(rows[0])].status === "klaar");
});

test("baan buiten gebruik: geraakte partijen, opheffen", () => {
  const rows = D.dsRows(PLAN);
  let s = D.dsOffAdd(D.dsEmpty(), [1], "10:00", "", "onderhoud", at(9, 50));
  assert.deepStrictEqual(rows.map((r) => D.dsHit(r, s)), [true, false, true, false]);
  assert.ok(D.dsCourts(rows, s, 600, 3)[0].off);
  assert.ok(!D.dsCourts(rows, s, 590, 3)[0].off);
  s = D.dsOffRemove(s, 0, at(10, 5));
  assert.deepStrictEqual(s.off, []);
});

test("uitloop: verwachte vertraging, doorschuiven op één baan, verschil en gewijzigd-markering", () => {
  const rows = D.dsRows(PLAN);
  let s = D.dsStart(D.dsEmpty(), rows[0], 1, at(9, 10));
  assert.strictEqual(D.dsExpectedDelay(rows, s, 1, at(10, 50)), 20); // nu 10:50 (na verwacht eind 10:40) − volgende 10:30
  assert.strictEqual(D.dsExpectedDelay(rows, s, 1, at(9, 30)), 10);
  const nw = D.dsShiftCourt(PLAN.rows, s, 1, 10 * 60 + 30, 30, 10 * 60 + 50);
  const diff = D.dsDiff(PLAN.rows, nw);
  assert.deepStrictEqual(diff.map((d) => [d.row.part, d.old.start, d.new.start]), [["D1", "10:30", "11:00"]]);
  const ch = D.dsChanged({}, diff);
  assert.deepStrictEqual(ch[D.dsPid(rows[2])], { start: "10:30", court: 1 });
  assert.deepStrictEqual(D.dsChanged(ch, [{ pid: D.dsPid(rows[2]), old: { start: "11:00", court: 1 } }])[D.dsPid(rows[2])].start, "10:30");
});

test("per team staken / later starten (SD8)", () => {
  const rows = D.dsRows(PLAN);
  let s = D.dsTeam(D.dsEmpty(), "T · M 1", "HD M 1", "later", { time: "13:00" }, at(10, 0));
  assert.deepStrictEqual([s.teams["T · M 1"].status, s.teams["T · M 1"].time], ["later", "13:00"]);
  assert.match(s.log[0].msg, /start later \(13:00\)/);
  s = D.dsTeam(s, "T · M 1", "HD M 1", "staakt", {}, at(10, 1));
  assert.strictEqual(D.dsStatus(rows[0], s, 600).status, "gestaakt");
  s = D.dsStart(D.dsEmpty(), rows[0], 1, at(9, 0));
  s = D.dsTeam(s, "T · M 1", "HD M 1", "staakt", {}, at(10, 1));
  assert.strictEqual(D.dsStatus(rows[0], s, 600).status, "bezig"); // al begonnen blijft lopen
});

test("verschil toont weggevallen (gestaakte) partijen", () => {
  const nw = PLAN.rows.filter((r) => r.home_team !== "M 2");
  const d = D.dsDiff(PLAN.rows, nw);
  assert.deepStrictEqual(d.map((x) => [x.row.home_team, x.gone]), [["M 2", true]]);
  assert.strictEqual(D.dsChanged({}, d)[d[0].pid].gone, true);
});
