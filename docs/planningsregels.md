# Planningsregels baanschema — vervangen

De gezaghebbende regels staan sinds 2026-08-24 in **[SPEC.md](SPEC.md)**.

Dit bestand blijft bestaan omdat de code en de documentatie ernaar verwijzen.
Alles wat hier stond is overgenomen in `SPEC.md`: de nieuwe regels in sectie 1
t/m 6, de herplanningsregels in sectie 7 en de zachte voorkeuren uit de
gold-analyse in sectie 8.

Let op bij het lezen van oudere commits en scripts: de vorige versie van dit
bestand zei op drie punten iets anders dan `SPEC.md`.

| onderwerp | vorige versie | SPEC.md |
|---|---|---|
| speelduur Groen / Junioren | niet vermeld | 45 min |
| Oranje bij Rood op dezelfde dag | Oranje naar baan 2, 3, 4 | idem, maar de code doet het omgekeerd |
| niet-planbare partijen | mochten wegvallen | worden altijd ingepland, met waarschuwingstag |

De regel "Jeugd 13-17 start pas vanaf 11:00" stond niet in dit bestand maar wel
hard in `scripts/ortools_planner.py`. Die is met `SPEC.md` ingetrokken.
