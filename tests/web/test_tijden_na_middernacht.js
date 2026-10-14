"use strict";
// Tijden na middernacht (intern ≥ 24:00) tonen als "01:00+" / "01:00 (volgende dag)", nooit "25:00".
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const W = path.join(__dirname, "../../web/baanschemaatje");
const ctx = { location: { search: "", hash: "" }, URLSearchParams, window: {} };
vm.createContext(ctx);
for (const f of ["common.js", "overzicht.js", "print.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8").replace(/^const /gm, "var "), ctx);

test("compact en voluit", () => {
  assert.strictEqual(ctx.clockShort("25:00"), "01:00+");
  assert.strictEqual(ctx.clockShort("19:30"), "19:30");
  assert.strictEqual(ctx.clockHHMM("25:00"), "01:00 (volgende dag)");
  assert.strictEqual(ctx.ovHHMM(25 * 60 + 15), "01:15+");
  assert.strictEqual(ctx.ovHHMM(20 * 60), "20:00");
  assert.strictEqual(ctx._pClock("24:30"), "00:30+");
});
