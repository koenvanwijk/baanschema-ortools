"use strict";
// Officiële KNLTB-speeldata, met de inhaaldagen. Bron (gecontroleerd 09-10-2026):
// "Data KNLTB competitie najaar tennis 2026" (tennis.nl/media/z2kjtglt/speeldata-knltb-najaarscompetitie-tennis-2026.pdf)
// (lokale kopie: knltb-bronnen/pdf/speeldata-knltb-najaarscompetitie-tennis-2026.pdf).
// Komt er een nieuw seizoen bij, voeg dan hier een blok toe. Data als dd-mm-jjjj.
const KNLTB_KALENDER = [
  {
    seizoen: "Najaar 2026",
    bron: "KNLTB: Data KNLTB competitie najaar tennis 2026",
    url: "https://www.tennis.nl/media/z2kjtglt/speeldata-knltb-najaarscompetitie-tennis-2026.pdf",
    competities: [
      {
        id: "rog", naam: "Rood, Oranje en Groen", kort: "R/O/G",
        dagen: {
          zondag: { speeldagen: ["06-09-2026", "13-09-2026", "20-09-2026", "27-09-2026", "04-10-2026"],
            inhaaldagen: ["11-10-2026", "18-10-2026", "25-10-2026"] },
        },
      },
      {
        id: "junioren", naam: "Junioren 11–14 en 13–17", kort: "junioren",
        dagen: {
          vrijdag: { speeldagen: ["04-09-2026", "11-09-2026", "18-09-2026", "25-09-2026", "02-10-2026"],
            inhaaldagen: ["09-10-2026", "16-10-2026", "23-10-2026"] },
          zondag: { speeldagen: ["06-09-2026", "13-09-2026", "20-09-2026", "27-09-2026", "04-10-2026"],
            inhaaldagen: ["11-10-2026", "18-10-2026", "25-10-2026"] },
        },
      },
      {
        id: "regulier", naam: "Reguliere competitie", kort: "regulier",
        dagen: {
          maandag: { speeldagen: ["07-09-2026", "14-09-2026", "21-09-2026", "28-09-2026", "05-10-2026"], inhaaldagen: ["12-10-2026", "19-10-2026", "26-10-2026"] },
          dinsdag: { speeldagen: ["08-09-2026", "15-09-2026", "22-09-2026", "29-09-2026", "06-10-2026"], inhaaldagen: ["13-10-2026", "20-10-2026", "27-10-2026"] },
          woensdag: { speeldagen: ["09-09-2026", "16-09-2026", "23-09-2026", "30-09-2026", "07-10-2026"], inhaaldagen: ["14-10-2026", "21-10-2026", "28-10-2026"] },
          donderdag: { speeldagen: ["10-09-2026", "17-09-2026", "24-09-2026", "01-10-2026", "08-10-2026"], inhaaldagen: ["15-10-2026", "22-10-2026", "29-10-2026"] },
          vrijdag: { speeldagen: ["11-09-2026", "18-09-2026", "25-09-2026", "02-10-2026", "09-10-2026"], inhaaldagen: ["16-10-2026", "23-10-2026", "30-10-2026"] },
          zaterdag: { speeldagen: ["12-09-2026", "19-09-2026", "26-09-2026", "03-10-2026", "10-10-2026"], inhaaldagen: ["17-10-2026", "24-10-2026", "31-10-2026"] },
          zondag: { speeldagen: ["13-09-2026", "20-09-2026", "27-09-2026", "04-10-2026", "11-10-2026"], inhaaldagen: ["18-10-2026", "25-10-2026", "01-11-2026"] },
        },
      },
    ],
  },
];
