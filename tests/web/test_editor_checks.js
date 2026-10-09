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

// ---------------------------------------------------------------- spelers en volgorde (spiegelt planner.py)

const { playerDemand } = require("../../web/baanschemaatje/editor.js");
const levels = (res) => res.issues.map((i) => i.level);
const loadPlan = (club_, date) => JSON.parse(fs.readFileSync(path.join(DATA, club_, `${date}.json`)));

test("alle vooraf berekende plannen: geen Spelersconflict/Volgorde/wachttijd/blokken", () => {
  const idx = JSON.parse(fs.readFileSync(path.join(DATA, "index.json")));
  for (const c of idx.clubs) for (const d of c.dates) {
    const plan = JSON.parse(fs.readFileSync(path.join(DATA, d.file)));
    assert.deepStrictEqual(checkPlan(plan.rows, c).issues, [], d.file);
  }
});

test("Oscar: M13-17 1e MIERLO 3 S3 over D1/D2 heen slepen (27-09) → Spelersconflict + Volgorde", () => {
  const plan = loadPlan("mierlo", "27-09-2026");
  const team = (r) => r.home_team === "MIERLO 3" && r.label === "M13-17";
  const s3 = plan.rows.findIndex((r) => team(r) && r.part === "S3");
  const d1 = plan.rows.findIndex((r) => team(r) && r.part === "D1");
  const d2 = plan.rows.findIndex((r) => team(r) && r.part === "D2");
  assert.ok(s3 >= 0 && d1 >= 0 && d2 >= 0);
  assert.deepStrictEqual(checkPlan(plan.rows, club).issues, []);
  const rows = JSON.parse(JSON.stringify(plan.rows));
  Object.assign(rows[s3], { start: rows[d1].start, end: "14:00", court: rows[d1].court === 9 ? 3 : 9 });
  // S3 naar een vrije baan om 12:30, dus geen baanconflict, wel dezelfde spelers tegelijk bezet.
  rows[s3].court = [1, 2, 5, 6, 7, 8, 9, 10].find((c) => !rows.some((r, i) => i !== s3 && r.court === c && r.start !== "NIET_GELUKT"
    && r.start < rows[s3].end && rows[s3].start < r.end)) || rows[s3].court;
  const res = checkPlan(rows, club);
  const lv = levels(res);
  assert.ok(lv.includes("Spelersconflict"), JSON.stringify(res.issues));
  assert.ok(lv.includes("Volgorde"), JSON.stringify(res.issues));
  for (const i of [s3, d1, d2]) assert.ok(res.byRow.get(i), `rij ${rows[i].part} gemarkeerd`);
  assert.ok(res.issues.some((x) => x.level === "Spelersconflict" && /5 spelers/.test(x.msg)));
});

const team4 = (part, start, end, court, extra = {}) => row("A", part, start, end, court, { team: "Heren Zondag – 4e klasse", ...extra });

test("spelers: S + D tegelijk met >4 spelers is Spelersconflict; 2 enkels tegelijk niet", () => {
  // S1 (1) + D1 (2) + D2 (2) = 5 spelers tegelijk; S1 + S2 + D1 = 4 mag (zoals in de planner).
  const bad = [team4("S1", "10:00", "11:30", 1), team4("D1", "10:00", "11:30", 2), team4("D2", "10:00", "11:30", 3)];
  assert.ok(levels(checkPlan(bad, club)).includes("Spelersconflict"));
  const ok = [team4("S1", "10:00", "11:30", 1), team4("S2", "10:00", "11:30", 2)];
  assert.ok(!levels(checkPlan(ok, club)).includes("Spelersconflict"));
});

test("volgorde: dubbel vóór enkel klaar is (niet-gemengd)", () => {
  const rs = [team4("S1", "10:00", "11:30", 1), team4("S2", "10:00", "11:30", 2), team4("D1", "11:00", "12:30", 3)];
  const res = checkPlan(rs, club);
  assert.ok(res.issues.some((x) => x.level === "Volgorde" && x.rule === "waterval"));
});

test("volgorde: paar S1/S2 begint niet tegelijk", () => {
  const rs = [team4("S1", "10:00", "11:30", 1), team4("S2", "10:30", "12:00", 2)];
  assert.ok(checkPlan(rs, club).issues.some((x) => x.level === "Volgorde" && x.rule === "paar-samen"));
});

test("gemengd 8p: strikt S → D → GD; gemengd max 2 heren + 2 dames", () => {
  const T = "Gemengd Zondag – 1e klasse (2DE-2HE-DD-HD-2GD) – Afdeling 1";
  const g = (part, s, e, c) => row("G", part, s, e, c, { team: T, category: "gemengd", kind: part.startsWith("GD") ? "M" : part[0] });
  const parts = [g("S1", "10:00", "11:30", 1), g("S2", "10:00", "11:30", 2), g("S3", "11:30", "13:00", 1), g("S4", "11:30", "13:00", 2),
    g("D1", "13:00", "14:30", 1), g("D2", "13:00", "14:30", 2), g("GD1", "14:00", "15:30", 3), g("GD2", "14:00", "15:30", 4)];
  const res = checkPlan(parts, club);
  assert.ok(res.issues.some((x) => x.level === "Volgorde" && /GD1|GD2/.test(x.msg)), JSON.stringify(res.issues));
  // HD (2 heren) tegelijk met 2 herenenkels (S3, S4) → 4 heren.
  assert.deepStrictEqual(playerDemand(T, "D2", "D"), [2, 0, 2]);
  const men = checkPlan([g("S3", "10:00", "11:30", 1), g("D2", "10:00", "11:30", 2)], club);
  assert.ok(men.issues.some((x) => x.level === "Spelersconflict" && /3 heren/.test(x.msg)), JSON.stringify(men.issues));
});

test("wachttijd > 60 min en te veel speelblokken (hard productstandaard)", () => {
  const rs = [team4("S1", "09:00", "10:30", 1), team4("S2", "09:00", "10:30", 2), team4("D1", "12:00", "13:30", 1)];
  assert.ok(checkPlan(rs, club).issues.some((x) => x.rule === "max_wait_minutes"));
  const three = [team4("S1", "09:00", "10:30", 1), team4("S2", "09:00", "10:30", 2), team4("D1", "11:00", "12:30", 1), team4("D2", "13:00", "14:30", 1)];
  assert.ok(checkPlan(three, club).issues.some((x) => x.rule === "max_blocks_per_team"));
});

test("banen per team over de dag: meer dan max verschillende banen", () => {
  const rs = [team4("S1", "10:00", "11:30", 1), team4("S2", "10:00", "11:30", 2), team4("D1", "11:30", "13:00", 5), team4("D2", "11:30", "13:00", 6)];
  assert.ok(checkPlan(rs, club).issues.some((x) => x.rule === "max-banen-dag"));
});
