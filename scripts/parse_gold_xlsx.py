#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _col_idx(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha())
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def _excel_day_fraction_to_hhmm(v: str | None) -> str | None:
    if v is None:
        return None
    try:
        mins = int(round(float(v) * 24 * 60))
    except Exception:
        return None
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _norm_team_key(team_short: str) -> str:
    return re.sub(r"\s+", " ", (team_short or "").strip())


def _col_idx_to_letter(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _extract_captains(row_cells_by_ref: list[dict[str, str | None]], short_team_name) -> dict[str, str]:
    """Extract captain per team_short from the 'Thuis/Team/.../Captain' side-table columns.

    The side table repeats a 'Thuis' (schema/afdeling text), 'Team' (home team, e.g. MIERLO 2)
    and 'Captain' column, sometimes twice per sheet (two side-by-side blocks). Column layout
    varies slightly between sheets, so we locate columns by header text rather than fixed letters.
    """
    if not row_cells_by_ref:
        return {}
    header = row_cells_by_ref[0]
    thuis_cols = [c for c, v in header.items() if v == "Thuis"]
    captain_cols = [c for c, v in header.items() if v == "Captain"]
    if not thuis_cols or not captain_cols:
        return {}

    def col_to_idx(col: str) -> int:
        n = 0
        for ch in col:
            n = n * 26 + (ord(ch) - 64)
        return n

    lookup: dict[str, str] = {}
    for tc, cc in zip(thuis_cols, captain_cols):
        home_col = _col_idx_to_letter(col_to_idx(tc) + 1)
        for cells in row_cells_by_ref[1:]:
            schema = cells.get(tc)
            home = cells.get(home_col)
            cap = cells.get(cc)
            if schema and home and cap:
                try:
                    ts = short_team_name(schema, home)
                except Exception:
                    continue
                if ts:
                    lookup[ts] = cap
    return lookup


def _default_short_team_name(schema: str, home_team: str = "") -> str:
    """Fallback team-short-name builder mirroring scripts/build_pages.py::short_team_name.

    Kept local (duplicated) so this parser has no hard import dependency on build_pages.py.
    """
    low = (schema or "").lower()
    if "gemengd zondag" in low:
        prefix = "GEM"
    elif "heren zondag" in low:
        prefix = "HER"
    elif "groen zondag" in low:
        prefix = "GRO"
    elif "jongens 13 t/m 17" in low:
        prefix = "JO13-17"
    elif "meisjes 13 t/m 17" in low:
        prefix = "ME13-17"
    elif "junioren 11 t/m 14" in low:
        prefix = "JU11-14"
    else:
        prefix = (schema or "").split("–", 1)[0].strip()[:20]

    parts = [p.strip() for p in (schema or "").split("–")]
    klasse = ""
    if len(parts) >= 2:
        klasse = re.sub(r"\s*\([^)]*\)", "", parts[1])
        klasse = klasse.replace("klasse", "").strip()

    m = re.search(r"\bMIERLO\s*(\d+)\b", home_team or "", flags=re.I)
    home_short = f"M{m.group(1)}" if m else ""

    out = " ".join(x for x in [prefix, klasse, home_short] if x)
    return re.sub(r"\s+", " ", out).strip()


def parse_gold_xlsx(path: Path, short_team_name=None) -> dict[str, list[dict]]:
    if short_team_name is None:
        short_team_name = _default_short_team_name
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", NS):
                txt = "".join(t.text or "" for t in si.findall(".//a:t", NS))
                shared.append(txt)

        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rid_to_target = {
            r.attrib["Id"]: r.attrib["Target"]
            for r in rels.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
        }

        out: dict[str, list[dict]] = {}
        captains_by_date: dict[str, dict[str, str]] = {}

        for sh in wb.findall("a:sheets/a:sheet", NS):
            sheet_name = sh.attrib["name"]
            rid = sh.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = "xl/" + rid_to_target[rid]

            root = ET.fromstring(z.read(target))
            grid: dict[tuple[int, int], str | None] = {}
            max_row = 0
            for row in root.findall(".//a:sheetData/a:row", NS):
                rnum = int(row.attrib.get("r", "0"))
                max_row = max(max_row, rnum)
                for c in row.findall("a:c", NS):
                    ref = c.attrib.get("r", "")
                    ci = _col_idx(ref)
                    t = c.attrib.get("t")
                    v = c.find("a:v", NS)
                    val: str | None = None
                    if v is not None:
                        val = v.text
                        if t == "s" and val is not None:
                            val = shared[int(val)]
                    isel = c.find("a:is", NS)
                    if isel is not None:
                        val = "".join(t.text or "" for t in isel.findall(".//a:t", NS))
                    grid[(rnum, ci)] = val

            # Build per-row column-letter dicts once, for the side "Thuis/Team/.../Captain"
            # table columns (used to extract captains per team_short).
            row_cells_by_ref: list[dict[str, str | None]] = []
            for rnum in range(1, max_row + 1):
                row_dict: dict[str, str | None] = {}
                for (r, ci), val in grid.items():
                    if r != rnum:
                        continue
                    row_dict[_col_idx_to_letter(ci)] = val
                row_cells_by_ref.append(row_dict)

            row_to_time: dict[int, str] = {}
            for r in range(2, max_row + 1):
                hhmm = _excel_day_fraction_to_hhmm(grid.get((r, 1)))
                if hhmm:
                    row_to_time[r] = hhmm

            matches: list[dict] = []
            for court in range(1, 11):
                col = 1 + court
                cur = ""
                start_row = None

                rows = sorted(row_to_time)
                for r in rows + [rows[-1] + 1 if rows else 2]:
                    raw = grid.get((r, col)) if r in row_to_time else None
                    if raw is None:
                        # Merged-cell continuation: the source xlsx merges cells for
                        # multi-slot blocks (e.g. Rood/Oranje reservations), so only
                        # the first row of the merge has a value and the following
                        # rows are physically empty (None) rather than the '·'
                        # marker used for regular (unmerged) match rows. Treat an
                        # empty cell as a continuation, not as an end-of-block.
                        s = cur
                    else:
                        s = str(raw).strip()
                        if s == "·":
                            s = cur  # continuation marker
                        elif s in {"", "—", "None"}:
                            s = ""

                    if s != cur:
                        if cur and start_row is not None:
                            start = row_to_time[start_row]
                            end = row_to_time.get(r)
                            if end is None:
                                # last interval fallback (+15m)
                                hh, mm = map(int, row_to_time[rows[-1]].split(":"))
                                end = f"{(hh*60+mm+15)//60:02d}:{(hh*60+mm+15)%60:02d}"

                            if " · " in cur:
                                team_short, part = cur.split(" · ", 1)
                            else:
                                team_short, part = cur, ""

                            team_short = _norm_team_key(team_short)
                            if team_short and team_short not in {"ROOD", "ORANJE"}:
                                matches.append(
                                    {
                                        "team_short": team_short,
                                        "part": part.strip(),
                                        "kind": "M" if part.strip().startswith("GD") else ("D" if part.strip().startswith("D") else ("S" if part.strip().startswith("S") else "W")),
                                        "start": start,
                                        "end": end,
                                        "court": court,
                                    }
                                )
                        cur = s
                        start_row = r

            # map 6-4 -> 06-04-2026 (assume 2026 season)
            m = re.match(r"^(\d{1,2})-(\d{1,2})$", sheet_name.strip())
            if not m:
                # skip non-date sheets (e.g. instructions)
                continue
            day, mon = int(m.group(1)), int(m.group(2))
            date_key = f"{day:02d}-{mon:02d}-2026"

            captains = _extract_captains(row_cells_by_ref, short_team_name)
            for match in matches:
                cap = captains.get(match["team_short"])
                if cap:
                    match["captain"] = cap
            captains_by_date[date_key] = captains
            out[date_key] = matches

        return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse manual gold baanschema xlsx to JSON")
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--out", type=Path, default=Path("docs/gold_result.json"))
    args = ap.parse_args()

    gold = parse_gold_xlsx(args.xlsx)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(gold, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.out} ({len(gold)} dates)")


if __name__ == "__main__":
    main()
