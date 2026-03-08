# Planningsregels baanschema

Dit bestand bevat de actuele regels die door de planner/herplanner worden gebruikt.

## Capaciteit en basis
- 10 banen totaal.
- Planning in kwartierblokken (15 minuten).
- Elke wedstrijd precies één keer.
- Maximaal één wedstrijd per baan per tijdslot.
- Een speler/team mag niet in conflicterende partijen tegelijk staan.

## Rood/Oranje reserveringen
- **Rood**: altijd baan 1, start op de dagstart (09:00 of 08:30) en duurt 60 min.
- **Oranje**: bij voorkeur baan 1,2,3, start op de dagstart (09:00 of 08:30) en duurt 120 min.
- Als Rood en Oranje op dezelfde dag spelen, krijgt Oranje baan 2,3,4.

## Startregels dag
- Planner probeert de dag te starten om **09:00**.
- Alleen als 09:00 ertoe leidt dat partijen pas na 19:30 moeten starten of onplanbaar worden, valt planner terug naar **08:30**.

## Team- en partijregels
- Singles (S) en dubbels (D) niet tegelijk.
- Dubbels (D) en gemengd dubbel (GD/M) niet tegelijk.
- Voor schema `2DE-2HE-DD-HD-2GD`: singles (S) en GD/M ook niet tegelijk.
- Extra startregel: als een team in het eerste haalbare startvenster met 1 of 2 banen kan beginnen, start het team met dubbels/GD.
- Als er in dat startvenster 3 of 4+ banen beschikbaar zijn, begin met singles.

## Volgorde/voorkeuren
- Basisvolgorde teams: jong naar oud, gemengd later.
- Gemengd Zondag start bij voorkeur vanaf 10:00.
- Teams met 8 wedstrijden worden zoveel mogelijk op baan 1 t/m 4 gepland.
- Rood/Oranje-reserveringen hebben altijd prioriteit op hun vaste banen.
- Doel: hoge baanbezetting + zo min mogelijk gaten binnen teamplanning.

## Tijdvensters
- Eerste teamwedstrijd normaal uiterlijk 15:00, met datum-specifieke verruiming op kneldagen.
- Wedstrijden mogen starten tot en met **19:30**.

## Niet-blocking beleid
- Geen eis mag de build blokkeren.
- Als een eis niet gehaald wordt (bijv. niet-planbare partijen), blijft de pagina wel gegenereerd.
- Afwijkingen worden per dag zichtbaar gemaakt in de rode/geel gemarkeerde regels op de pagina.

## Herplanning op wedstrijddag
- Afgevinkte partijen worden vastgezet.
- Lopende partijen op `now` worden als bezet beschouwd.
- Overige partijen schuiven door in 15-min stappen met behoud van constraints.
- Als maar 1 baan vrij is, mag de planner alvast 1 partij uit een ronde starten (compactheid boven symmetrie).
- Bij voorkeur blijft een partij op dezelfde baan in de herplanning.
