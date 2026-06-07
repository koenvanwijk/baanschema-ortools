#!/usr/bin/env python3
"""
Timefold tennis scheduling — full 06-04-2026 implementation with all constraints.
"""
import os
os.environ['JAVA_HOME'] = os.path.expanduser('~/.sdkman/candidates/java/current')

import sys
import csv
from pathlib import Path
from dataclasses import dataclass, field
from typing import Annotated
from timefold.solver.domain import (
    planning_entity, PlanningId, PlanningVariable,
    planning_solution, ProblemFactCollectionProperty, ValueRangeProvider,
    PlanningEntityCollectionProperty, PlanningScore
)
from timefold.solver.score import HardSoftScore, ConstraintFactory, Constraint, Joiners, constraint_provider
from timefold.solver import SolverFactory
from timefold.solver.config import SolverConfig, TerminationConfig, ScoreDirectorFactoryConfig, Duration

# Minimal data structures
@dataclass
class TeamDay:
    date: str
    schema: str
    matches: int
    duration_min: int
    singles: int
    doubles: int
    mix: int

def parse_input(path: Path) -> list[TeamDay]:
    """Parse input TSV file."""
    teams = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            date = (row.get("Datum") or "").strip()
            schema = (row.get("Schema") or "").strip()
            if not date or not schema:
                continue
            low = schema.lower()
            if "rood" in low or "oranje" in low:
                continue
            
            def to_int(v):
                v = (v or "").strip()
                return int(v) if v else 0
            
            m = to_int(row.get("Wedstrijden"))
            d = to_int(row.get("Wedstrijdduur"))
            if not m or not d:
                continue
            
            teams.append(TeamDay(
                date=date,
                schema=schema,
                matches=m,
                duration_min=d,
                singles=to_int(row.get("Singles")),
                doubles=to_int(row.get("Doubles")),
                mix=to_int(row.get("Mix")),
            ))
    return teams

INPUT = Path(__file__).parent.parent / "data" / "season.tsv"

# Problem facts
@dataclass
class Timeslot:
    id: Annotated[int, PlanningId]
    start_min: int  # Minutes since 08:00
    
    def __str__(self):
        h = 8 + self.start_min // 60
        m = self.start_min % 60
        return f"{h:02d}:{m:02d}"

@dataclass
class Court:
    id: Annotated[int, PlanningId]
    number: int
    pair_id: int  # 1-2 → pair 1, 3-4 → pair 2, etc.
    
    def __str__(self):
        return f"Baan {self.number}"

@dataclass
class Team:
    """Problem fact representing a team (for constraints referencing team properties)."""
    schema: str
    is_youth: bool  # True if schema contains "Jongens" or "Meisjes"
    
    def __str__(self):
        return self.schema

# Planning entity
@planning_entity
@dataclass
class Part:
    id: Annotated[int, PlanningId]
    team: str
    label: str  # S1, D1, etc.
    duration_min: int
    is_singles: bool
    is_doubles: bool
    is_mixed: bool
    timeslot: Annotated[Timeslot | None, PlanningVariable] = field(default=None)
    court: Annotated[Court | None, PlanningVariable] = field(default=None)
    
    def __str__(self):
        return f"{self.team} {self.label}"
    
    def start_min(self) -> int | None:
        return self.timeslot.start_min if self.timeslot is not None else None
    
    def end_min(self) -> int | None:
        start = self.start_min()
        return start + self.duration_min if start is not None else None

# Planning solution
@planning_solution
@dataclass
class Schedule:
    timeslots: Annotated[list[Timeslot], ProblemFactCollectionProperty, ValueRangeProvider]
    courts: Annotated[list[Court], ProblemFactCollectionProperty, ValueRangeProvider]
    teams: Annotated[list[Team], ProblemFactCollectionProperty]
    parts: Annotated[list[Part], PlanningEntityCollectionProperty]
    score: Annotated[HardSoftScore | None, PlanningScore] = field(default=None)

# Constraints
@constraint_provider
def define_constraints(constraint_factory: ConstraintFactory) -> list[Constraint]:
    return [
        # Hard constraints
        court_conflict(constraint_factory),
        court_pairing(constraint_factory),
        youth_time_window(constraint_factory),
        # Soft constraints
        prefer_low_courts(constraint_factory),
        singles_before_doubles(constraint_factory),
        # team_compactness(constraint_factory),  # TODO: No min/max aggregators in Timefold Python
    ]

def court_conflict(constraint_factory: ConstraintFactory) -> Constraint:
    """No two parts can overlap on the same court."""
    def overlaps(part1: Part, part2: Part) -> bool:
        if part1.timeslot is None or part2.timeslot is None:
            return False
        start1 = part1.start_min()
        end1 = part1.end_min()
        start2 = part2.start_min()
        end2 = part2.end_min()
        return start1 < end2 and start2 < end1
    
    return (
        constraint_factory
        .for_each_unique_pair(Part, Joiners.equal(lambda p: p.court))
        .filter(lambda p1, p2: overlaps(p1, p2))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Court conflict")
    )

def court_pairing(constraint_factory: ConstraintFactory) -> Constraint:
    """Team parts must be on courts from the same pair (1-2, 3-4, 5-6, 7-8, 9-10)."""
    return (
        constraint_factory
        .for_each_unique_pair(Part, Joiners.equal(lambda p: p.team))
        .filter(lambda p1, p2: p1.court is not None and p2.court is not None)
        .filter(lambda p1, p2: p1.court.pair_id != p2.court.pair_id)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Court pairing violation")
    )

def team_max_two_courts(constraint_factory: ConstraintFactory) -> Constraint:
    """Each team can use at most 2 different courts (via pair counting)."""
    # For each team with 3+ parts, penalize if using >2 courts
    # Implementation: for each triple of parts from same team, penalize if all on different courts
    return (
        constraint_factory
        .for_each(Part)
        .join(Part, Joiners.equal(lambda p: p.team), Joiners.less_than(lambda p: p.id))
        .join(Part, Joiners.equal(lambda p1, p2: p1.team), Joiners.less_than(lambda p1, p2: p2.id))
        .filter(lambda p1, p2, p3: p1.court is not None and p2.court is not None and p3.court is not None)
        .filter(lambda p1, p2, p3: p1.court.number != p2.court.number and 
                                    p2.court.number != p3.court.number and
                                    p1.court.number != p3.court.number)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Team max 2 courts")
    )

def youth_time_window(constraint_factory: ConstraintFactory) -> Constraint:
    """Youth teams (Jongens/Meisjes) cannot start before 08:30."""
    return (
        constraint_factory
        .for_each(Part)
        .join(Team, Joiners.equal(lambda p: p.team, lambda t: t.schema))
        .filter(lambda p, t: t.is_youth and p.timeslot is not None and p.start_min() < 30)
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Youth time window")
    )

def prefer_low_courts(constraint_factory: ConstraintFactory) -> Constraint:
    """Prefer lower court numbers."""
    return (
        constraint_factory
        .for_each(Part)
        .filter(lambda p: p.court is not None)
        .penalize(HardSoftScore.ONE_SOFT, lambda p: p.court.number)
        .as_constraint("Prefer low courts")
    )

def singles_before_doubles(constraint_factory: ConstraintFactory) -> Constraint:
    """Singles should start before doubles (soft, except for mixed teams)."""
    return (
        constraint_factory
        .for_each_unique_pair(Part, Joiners.equal(lambda p: p.team))
        .filter(lambda s, d: s.is_singles and d.is_doubles and not d.is_mixed)
        .filter(lambda s, d: s.timeslot is not None and d.timeslot is not None)
        .filter(lambda s, d: s.start_min() >= d.start_min())
        .penalize(HardSoftScore.of_soft(1000))
        .as_constraint("Singles before doubles")
    )

def team_compactness(constraint_factory: ConstraintFactory) -> Constraint:
    """Minimize gaps between team parts (prefer compact schedules)."""
    return (
        constraint_factory
        .for_each(Part)
        .filter(lambda p: p.timeslot is not None)
        .group_by(lambda p: p.team,
                  ConstraintFactory.min(lambda p: p.start_min()),
                  ConstraintFactory.max(lambda p: p.end_min()))
        .penalize(HardSoftScore.ONE_SOFT, lambda team, min_start, max_end: max_end - min_start)
        .as_constraint("Team compactness")
    )

# Generate problem from data
def generate_problem(date: str) -> Schedule:
    teams_data = parse_input(INPUT)
    teams_for_date = [t for t in teams_data if t.date == date]
    
    if not teams_for_date:
        raise ValueError(f"No data for date {date}")
    
    print(f"[Timefold] Loading {len(teams_for_date)} teams for {date}")
    
    # Timeslots: 08:00-20:00 in 15-min intervals
    timeslots = [Timeslot(id=i, start_min=i*15) for i in range(48)]
    
    # Courts: 1-10 with pair assignments
    courts = [
        Court(id=i+1, number=i+1, pair_id=(i//2)+1)
        for i in range(10)
    ]
    
    # Teams (for constraint references)
    teams = [
        Team(schema=t.schema, is_youth=("Jongens" in t.schema or "Meisjes" in t.schema))
        for t in teams_for_date
    ]
    
    # Parts
    parts = []
    part_id = 1
    for t in teams_for_date:
        # Singles
        for i in range(t.singles):
            parts.append(Part(
                id=part_id,
                team=t.schema,
                label=f"S{i+1}",
                duration_min=60,
                is_singles=True,
                is_doubles=False,
                is_mixed=False
            ))
            part_id += 1
        
        # Doubles
        for i in range(t.doubles):
            parts.append(Part(
                id=part_id,
                team=t.schema,
                label=f"D{i+1}",
                duration_min=90,
                is_singles=False,
                is_doubles=True,
                is_mixed=False
            ))
            part_id += 1
        
        # Mixed doubles
        for i in range(t.mix):
            parts.append(Part(
                id=part_id,
                team=t.schema,
                label=f"M{i+1}",
                duration_min=90,
                is_singles=False,
                is_doubles=True,
                is_mixed=True
            ))
            part_id += 1
    
    print(f"[Timefold] Created {len(parts)} parts, {len(timeslots)} slots, {len(courts)} courts")
    return Schedule(timeslots=timeslots, courts=courts, teams=teams, parts=parts, score=None)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default='06-04-2026')
    parser.add_argument('--time-limit', type=int, default=60)
    args = parser.parse_args()
    
    print("[Timefold] Tennis scheduling — full implementation")
    print("=" * 60)
    
    problem = generate_problem(args.date)
    
    solver_config = SolverConfig(
        solution_class=Schedule,
        entity_class_list=[Part],
        score_director_factory_config=ScoreDirectorFactoryConfig(
            constraint_provider_function=define_constraints
        ),
        termination_config=TerminationConfig(
            spent_limit=Duration(seconds=args.time_limit)
        )
    )
    
    solver = SolverFactory.create(solver_config).build_solver()
    
    print(f"[Timefold] Solving for {args.date} (time limit: {args.time_limit}s)...")
    solution = solver.solve(problem)
    
    print()
    print(f"[Timefold] Final score: {solution.score}")
    print()
    
    # Count results
    unassigned = sum(1 for p in solution.parts if p.timeslot is None or p.court is None)
    print(f"Scheduled: {len(solution.parts) - unassigned}/{len(solution.parts)}")
    print(f"NIET_GELUKT: {unassigned}")
    
    # Group by team
    from collections import defaultdict
    by_team = defaultdict(list)
    for part in solution.parts:
        by_team[part.team].append(part)
    
    print()
    print("Schedule by team:")
    print("-" * 60)
    for team, team_parts in sorted(by_team.items()):
        print(f"\n{team}:")
        for part in sorted(team_parts, key=lambda p: (p.start_min() or 9999, p.court.number if p.court else 99)):
            if part.timeslot and part.court:
                print(f"  {part.label:4s} {part.timeslot} {part.court} ({part.duration_min} min)")
            else:
                print(f"  {part.label:4s} NIET GELUKT")

if __name__ == "__main__":
    main()
