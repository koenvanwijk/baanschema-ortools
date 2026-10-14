"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { dgTeams } = require("../../web/baanschemaatje/dag.js");

test("dagpagina: groepering per team, aanvang, banen gesorteerd", () => {
  const R = (team, home, part, start, court) => ({ team, team_id: `${team} · ${home}`, label: team, home_team: home, away_team: "X", part, start, end: "", court });
  const t = dgTeams([R("HD", "M 2", "D1", "11:00", 4), R("HD", "M 2", "D2", "10:15", 3), R("GEM", "M 1", "S1", "09:00", 1), { team: "GEM", start: "", court: null }]);
  assert.deepStrictEqual(t.map((x) => [x.home, x.aanvang, x.courts]), [["M 1", "09:00", [1]], ["M 2", "10:15", [3, 4]]]);
  assert.deepStrictEqual(t[1].parts.map((p) => p.part), ["D2", "D1"]);
});
