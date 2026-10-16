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
