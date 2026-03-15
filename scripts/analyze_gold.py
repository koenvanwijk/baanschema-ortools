#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


def hhmm_to_min(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def union_len(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    iv = sorted(intervals)
    s, e = iv[0]
    total = 0
    for a, b in iv[1:]:
        if a <= e:
            e = max(e, b)
        else:
            total += e - s
            s, e = a, b
    total += e - s
    return total


def normalize_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        s = r.get("start")
        e = r.get("end")
        if not s or s == "NIET_GELUKT":
            continue
        team_short = (r.get("team_short") or r.get("team") or r.get("schema") or "").strip()
        if team_short in {"ROOD", "ORANJE"}:
            continue
        out.append(
            {
                "team_short": team_short,
                "part": r.get("part", ""),
                "kind": r.get("kind", ""),
                "start": s,
                "end": e,
                "court": r.get("court"),
            }
        )
    return out


def blocks(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    iv = sorted(intervals)
    cnt = 1
    cur_e = iv[0][1]
    for a, b in iv[1:]:
        if a > cur_e:
            cnt += 1
            cur_e = b
        else:
            cur_e = max(cur_e, b)
    return cnt


def analyze_day(rows: list[dict]) -> dict:
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_team[r["team_short"]].append(r)

    courts_used, blocks_used, gaps, spans = [], [], [], []
    single_violations = 0
    team_count = len(by_team)
    court_concentration = []

    for team, rr in by_team.items():
        intervals = [(hhmm_to_min(r["start"]), hhmm_to_min(r["end"])) for r in rr]
        span = max(b for _, b in intervals) - min(a for a, _ in intervals)
        active = union_len(intervals)
        gap = span - active
        spans.append(span)
        gaps.append(gap)
        blocks_used.append(blocks(intervals))

        courts = [r.get("court") for r in rr if r.get("court")]
        cset = set(courts)
        courts_used.append(len(cset))
        if courts:
            top = max(courts.count(c) for c in cset)
            court_concentration.append(round(top / len(courts), 3))

        singles = [r for r in rr if (r.get("kind") == "S" or str(r.get("part", "")).startswith("S"))]
        non_s = [r for r in rr if r not in singles]
        if singles and non_s:
            first_s = min(hhmm_to_min(r["start"]) for r in singles)
            first_non = min(hhmm_to_min(r["start"]) for r in non_s)
            if first_non < first_s:
                single_violations += 1

    return {
        "teams": team_count,
        "avg_span": round(mean(spans), 1) if spans else 0,
        "avg_gap": round(mean(gaps), 1) if gaps else 0,
        "avg_blocks": round(mean(blocks_used), 2) if blocks_used else 0,
        "avg_courts_used": round(mean(courts_used), 2) if courts_used else 0,
        "pct_teams_1_court": round(sum(1 for x in courts_used if x <= 1) / team_count * 100, 1) if team_count else 0,
        "pct_teams_2_courts": round(sum(1 for x in courts_used if x == 2) / team_count * 100, 1) if team_count else 0,
        "pct_teams_gt2_courts": round(sum(1 for x in courts_used if x > 2) / team_count * 100, 1) if team_count else 0,
        "avg_court_concentration": round(mean(court_concentration), 3) if court_concentration else 0,
        "singles_before_non_singles_violations": single_violations,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze Gold schedule patterns")
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("docs/gold_analysis.json"))
    args = ap.parse_args()

    data = json.loads(args.gold.read_text(encoding="utf-8"))
    report = {"dates": {}, "summary": {}}

    metrics_list = []
    for d, rows in sorted(data.items()):
        norm = normalize_rows(rows)
        m = analyze_day(norm)
        report["dates"][d] = m
        metrics_list.append(m)

    if metrics_list:
        keys = metrics_list[0].keys()
        report["summary"] = {
            k: round(mean([m[k] for m in metrics_list]), 2) if isinstance(metrics_list[0][k], (int, float)) else metrics_list[0][k]
            for k in keys
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
