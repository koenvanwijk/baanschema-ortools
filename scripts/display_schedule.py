#!/usr/bin/env python3
"""Display cuOpt workforce schedule in readable format."""

import sys
sys.path.insert(0, 'scripts')

from cuopt_workforce import solve_day
from ortools_planner import parse_input, INPUT
from collections import defaultdict

teams, reservations = parse_input(INPUT)
result = solve_day('06-04-2026', teams, reservations, 60)

print('\n=== cuOpt Workforce Schedule: 06-04-2026 ===\n')
print(f'Status: {result["status"]}')
scheduled = sum(1 for r in result["rows"] if r["start"] != "NIET_GELUKT")
print(f'Scheduled: {scheduled}/{len(result["rows"])} parts ({100*scheduled/len(result["rows"]):.0f}%)')
if "objective" in result:
    print(f'Objective: {result["objective"]:.1f}')
if "solve_time" in result:
    print(f'Solve time: {result["solve_time"]:.3f}s\n')

# Group by court
by_court = defaultdict(list)
for row in result['rows']:
    if row['start'] != 'NIET_GELUKT':
        by_court[row['court']].append(row)

# Sort and display
for court in sorted(by_court.keys()):
    print(f'\nBaan {court}:')
    for row in sorted(by_court[court], key=lambda r: r['start']):
        print(f'  {row["start"]}-{row["end"]}  {row["team"]:60s}  {row["part"]:4s} ({row["kind"]})')

# Failed parts
failed = [r for r in result["rows"] if r["start"] == "NIET_GELUKT"]
if failed:
    print(f'\n=== NIET GELUKT ({len(failed)}) ===')
    for r in failed:
        print(f'  {r["team"]:60s}  {r["part"]:4s} ({r["kind"]})')
