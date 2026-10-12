"use strict";
// Elke thuiswedstrijd uit de export staat op zijn exportdatum in het overzicht, ook op inhaaldagen
// en op datums die niet in knltb-kalender.js staan.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const W = path.join(__dirname, "../../web/baanschemaatje");
const ctx = {};
vm.createContext(ctx);
for (const f of ["knltb-kalender.js", "overzicht.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8").replace(/^const /gm, "var "), ctx);

const d = (date, weekday, cat = "senioren", dagdeel = "avond") => ({ date, weekday, wedstrijden: [{ category: cat, dagdeel, status: "open" }] });

test("exportdatums op inhaaldagen en buiten de kalender verschijnen", () => {
  const dates = [d("11-09-2026", "vrijdag"), d("16-10-2026", "vrijdag"), d("18-10-2026", "zondag", "groen", "dag"),
    d("01-11-2026", "zondag", "senioren", "dag"), d("05-11-2026", "donderdag"), d("14-10-2026", "woensdag")];
  const days = ctx.ovSeasonDays(dates);
  for (const x of dates) {
    const day = days.find((y) => y.date === x.date);
    assert.ok(day && day.match === x, x.date);
  }
});
