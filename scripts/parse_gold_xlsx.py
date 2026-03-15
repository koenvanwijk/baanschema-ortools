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


def parse_gold_xlsx(path: Path) -> dict[str, list[dict]]:
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
                    s = (str(raw).strip() if raw is not None else "")
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
