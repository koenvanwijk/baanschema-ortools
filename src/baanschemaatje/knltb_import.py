"""KNLTB-export (ruw) → genormaliseerd seizoen (TSV, zelfde kolommen als data/season_*.tsv).

Ondersteunde invoer (automatisch herkend aan de kopregel):

* **Ruwe KNLTB-export** (xlsx/csv/tsv) met kolommen ``Datum, Schema, Team 1,
  Team 2, Uitslag, Wedstrijdstatus, Aanvoerder Team 1, Aanvoerder Team 2``.
  ``Datum`` bevat ook een tijd (00:00 of de begintijd van de tegenstander).
  Alle wedstrijden van de afdeling staan erin (thuis én uit, alle dagdelen).
* **Bewerkte export / seizoensbestand** met ``Wedstrijden, Wedstrijdduur,
  Singles, Doubles, Mix`` (zoals data/season_2026-2027.tsv of de "processed"
  xlsx). Die kolommen worden overgenomen.

Regels bij de ruwe export:

* alleen **thuiswedstrijden**: Team 1 begint met ``club.knltb_name``;
* alle weekdagen (default; optioneel te beperken); per wedstrijd worden de
  weekdag, het dagdeel (``dag``/``avond``/``ochtend``/``middag``, uit het
  schema) en de begintijd uit ``Datum`` meegenomen;
* formaat (partijen, duur, S/D/GD) uit het schema afgeleid (KNLTB-aanbod
  najaar 2026: zondag-, zaterdag- en dubbelcompetities op donderdag/vrijdag
  4DD/4HD/DD-HD-2GD); een onbekend schema wordt gemeld en NIET geïmporteerd;
* **gespeelde wedstrijden** (er staat een uitslag, of de status zegt
  gespeeld/afgerond) krijgen ``Status = gespeeld`` en houden hun echte datum en
  uitslag; die worden nooit (her)gepland. Een wedstrijd in het verleden zonder
  uitslag krijgt ``Status = verlopen`` (wel planbaar, wordt gemeld);
* aanvoerdersnamen (persoonsgegevens) worden nooit overgenomen.

Rood en Oranje staan niet in de ruwe competitie-export; die kunnen als
genormaliseerde regels (zie data/season_2026-2027.tsv) worden toegevoegd.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import date, datetime
from typing import Any

WEEKDAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
COLUMNS = ["Datum", "Weekdag", "Dagdeel", "Begintijd", "Schema", "Wedstrijden", "Wedstrijdduur", "Singles", "Doubles",
           "Mix", "Team 1", "Team 2", "Uitslag", "Status"]
ALL_WEEKDAYS = frozenset(WEEKDAYS_NL)
PLAYED_STATUS_WORDS = ("gespeeld", "afgerond", "uitslag", "definitief", "walk-over", "walkover", "w.o.")
NORMALIZED_KEYS = {"Wedstrijden", "Wedstrijdduur"}
MAX_ROWS = 20000


class ImportError_(ValueError):
    """Bestand niet te lezen als KNLTB-export."""


def derive_format(schema: str) -> tuple[int, int, int, int, int] | None:
    """(partijen, duur_min, singles, dubbels, gemengd dubbel) of None als onbekend.

    Zelfde conventies als scripts/parse_wedstrijden_xlsx.py, plus Rood/Oranje.
    """
    s = " ".join(schema.lower().split())
    if "2de-2he-dd-hd-2gd" in s:
        return (8, 90, 4, 2, 2)
    if "de-he-gd-dd-hd" in s:
        return (5, 90, 2, 2, 1)
    if "junioren 11 t/m 14" in s:
        return (6, 45, 4, 2, 0)
    if s.startswith("groen"):
        return (6, 45, 4, 2, 0)
    if "jongens 13 t/m 17" in s or "meisjes 13 t/m 17" in s:
        return (6, 90, 4, 2, 0)
    if s.startswith("heren zondag") or s.startswith("dames zondag") \
            or s.startswith("heren zaterdag") or s.startswith("dames zaterdag"):
        return (6, 90, 4, 2, 0)
    # Dubbelcompetities (KNLTB-aanbod najaar 2026, senioren landelijk/regionaal):
    # Gemengd Dubbel = DD-HD-2GD, Dames/Heren Dubbel = 4DD/4HD; 4 partijen.
    if s.startswith("gemengd dubbel"):
        return (4, 90, 0, 2, 2)
    if s.startswith("dames dubbel") or s.startswith("heren dubbel"):
        return (4, 90, 0, 4, 0)
    # Gemengd 17+ zaterdag = DE-HE-GD-DD-HD (aanbod najaar landelijk).
    if s.startswith("gemengd 17+ zaterdag") or s.startswith("gemengd 35+ zaterdag"):
        return (5, 90, 2, 2, 1)
    if s.startswith("rood"):
        return (1, 60, 0, 1, 0)
    if s.startswith("oranje"):
        return (3, 120, 0, 1, 0)
    return None


def dagdeel(schema: str) -> str:
    """'avond' / 'ochtend' / 'middag' (uit de schemanaam) of 'dag'."""
    s = (schema or "").lower()
    for k in ("avond", "ochtend", "middag"):
        if k in s:
            return k
    return "dag"


def _parse_time(v: Any) -> str:
    """Begintijd uit de Datum-kolom ('' als 00:00 of onbekend)."""
    if isinstance(v, datetime):
        t = v.strftime("%H:%M")
    else:
        parts = str(v or "").replace("T", " ").split()
        t = parts[1][:5] if len(parts) > 1 else ""
    return "" if t in ("", "00:00") else t


def is_played(uitslag: str, status: str) -> bool:
    """Gespeeld = er staat een uitslag, of de status zegt dat er gespeeld is.
    'Resource group not found' en lege statussen tellen niet."""
    if (uitslag or "").strip():
        return True
    st = (status or "").lower()
    return any(w in st for w in PLAYED_STATUS_WORDS)


def _parse_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip().split(" ")[0].split("T")[0]
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _read_table(data: bytes, filename: str) -> list[list[Any]]:
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")) or data[:2] == b"PK":
        try:
            import openpyxl
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise ImportError_("xlsx-ondersteuning (openpyxl) ontbreekt op de server") from exc
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        except Exception as exc:  # noqa: BLE001
            raise ImportError_(f"kon xlsx niet openen: {exc}") from exc
        ws = wb.worksheets[0]
        rows = [list(r) for _, r in zip(range(MAX_ROWS + 1), ws.iter_rows(values_only=True))]
        wb.close()
        return rows
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252")
    first = text.splitlines()[0] if text else ""
    delim = "\t" if "\t" in first else (";" if first.count(";") > first.count(",") else ",")
    return [r for _, r in zip(range(MAX_ROWS + 1), csv.reader(io.StringIO(text), delimiter=delim))]


def _int(v: Any) -> int:
    try:
        return int(float(str(v).strip())) if v not in (None, "") else 0
    except ValueError:
        return 0


def parse_export(
    data: bytes,
    filename: str,
    home_name: str,
    weekdays: set[str] | None = None,
    today: date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Geeft (genormaliseerde rijen, rapport). ``today`` (Europe/Amsterdam)
    bepaalt wat 'in het verleden' is; default vandaag."""
    weekdays = {w.lower() for w in (weekdays or ALL_WEEKDAYS)}
    if today is None:
        today = _today_ams()
    rows = _read_table(data, filename)
    if not rows:
        raise ImportError_("leeg bestand")
    if len(rows) > MAX_ROWS:
        raise ImportError_(f"te veel regels (max {MAX_ROWS})")
    header = [str(h or "").strip() for h in rows[0]]
    idx = {h: i for i, h in enumerate(header) if h}
    missing = [c for c in ("Datum", "Schema", "Team 1") if c not in idx]
    if missing:
        raise ImportError_(f"kolom(men) {', '.join(missing)} ontbreken; gevonden: {', '.join(header)}")
    normalized = NORMALIZED_KEYS <= set(idx)
    home_up = (home_name or "").upper().strip()

    def g(r: list[Any], col: str) -> Any:
        i = idx.get(col)
        return r[i] if i is not None and i < len(r) else None

    out: list[dict[str, Any]] = []
    rep: dict[str, Any] = {
        "format": "genormaliseerd" if normalized else "ruwe KNLTB-export",
        "rows_in_file": len(rows) - 1,
        "imported": 0,
        "skipped": Counter(),
        "unknown_schemas": Counter(),
        "weekdays_in_file": Counter(),
        "home_weekdays": Counter(),
        "statuses": Counter(),
        "invalid_dates": 0,
        "per_weekday": Counter(),
        "per_competition": Counter(),
        "played": 0,
        "played_partial": [],
        "expired_no_result": [],
        "open": 0,
    }
    for r in rows[1:]:
        if not any(c not in (None, "") for c in r):
            continue
        d = _parse_date(g(r, "Datum"))
        schema = " ".join(str(g(r, "Schema") or "").split())
        if d is None or not schema:
            rep["invalid_dates"] += 1
            continue
        wd = WEEKDAYS_NL[d.weekday()]
        team1 = str(g(r, "Team 1") or "").strip()
        team2 = str(g(r, "Team 2") or "").strip()
        rep["weekdays_in_file"][wd] += 1
        status = str(g(r, "Wedstrijdstatus") or "").strip()
        if status:
            rep["statuses"][status] += 1
        if not normalized:
            if home_up and not team1.upper().startswith(home_up):
                rep["skipped"]["uitwedstrijd"] += 1
                continue
        rep["home_weekdays"][wd] += 1
        if wd not in weekdays:
            rep["skipped"][f"{wd} (niet gekozen)"] += 1
            continue
        if normalized:
            fmt = (_int(g(r, "Wedstrijden")), _int(g(r, "Wedstrijdduur")), _int(g(r, "Singles")),
                   _int(g(r, "Doubles")), _int(g(r, "Mix")))
            if not fmt[0]:
                fmt = derive_format(schema)
        else:
            fmt = derive_format(schema)
        if not fmt:
            rep["unknown_schemas"][schema.split("–")[0].strip()] += 1
            rep["skipped"]["onbekend formaat"] += 1
            continue
        m, dur, si, do, mi = fmt
        dd = str(g(r, "Dagdeel") or "").strip() or dagdeel(schema)
        tijd = str(g(r, "Begintijd") or "").strip() if normalized else _parse_time(g(r, "Datum"))
        uitslag = str(g(r, "Uitslag") or "").strip()
        st_in = str(g(r, "Status") or "").strip().lower() if normalized else ""
        if st_in in ("gespeeld", "open", "verlopen"):
            played = st_in == "gespeeld"
        else:
            played = is_played(uitslag, status)
        if played:
            st = "gespeeld"
            rep["played"] += 1
            try:
                a, b = (int(x) for x in uitslag.replace(" ", "").split("-"))
                if a + b < m:
                    rep["played_partial"].append(f"{d.strftime('%d-%m-%Y')} {team1} – {team2} ({uitslag}, {m} partijen)")
            except ValueError:
                pass
        elif d < today:
            st = "verlopen"
            rep["expired_no_result"].append(f"{d.strftime('%d-%m-%Y')} {team1} – {team2}")
        else:
            st = "open"
            rep["open"] += 1
        comp = _competition(schema)
        rep["per_weekday"][wd] += 1
        rep["per_competition"][f"{wd} · {comp}"] += 1
        out.append({
            "Datum": d.strftime("%d-%m-%Y"), "Weekdag": wd, "Dagdeel": dd, "Begintijd": tijd, "Schema": schema,
            "Wedstrijden": m, "Wedstrijdduur": dur, "Singles": si, "Doubles": do, "Mix": mi,
            "Team 1": team1, "Team 2": team2, "Uitslag": uitslag, "Status": st, "_k": (d, schema, team1),
        })
    out.sort(key=lambda x: x["_k"])
    for x in out:
        del x["_k"]
    rep["imported"] = len(out)
    for k in ("skipped", "unknown_schemas", "weekdays_in_file", "home_weekdays", "statuses", "per_weekday",
              "per_competition"):
        rep[k] = dict(rep[k])
    return out, rep


def _competition(schema: str) -> str:
    """Competitienaam zonder klasse/afdeling, bv. 'Gemengd Dubbel 17+ Vrijdag Avond'."""
    return " ".join(schema.split("–")[0].split())


def _today_ams() -> date:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    except Exception:  # noqa: BLE001
        return date.today()


def to_tsv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in COLUMNS})
    return buf.getvalue()
