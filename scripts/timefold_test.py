#!/usr/bin/env python3
"""
Timefold tennis scheduling — initial test based on school timetabling pattern.
"""
import os
os.environ['JAVA_HOME'] = os.path.expanduser('~/.sdkman/candidates/java/current')

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

# Problem facts (unchanging)
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
    
    def __str__(self):
        return f"Baan {self.number}"

# Planning entity
@planning_entity
@dataclass
class Part:
    id: Annotated[int, PlanningId]
    team: str
    label: str  # S1, D1, etc.
    duration_min: int
    timeslot: Annotated[Timeslot | None, PlanningVariable] = field(default=None)
    court: Annotated[Court | None, PlanningVariable] = field(default=None)
    
    def __str__(self):
        return f"{self.team} {self.label}"

# Planning solution
@planning_solution
@dataclass
class Schedule:
    timeslots: Annotated[list[Timeslot], ProblemFactCollectionProperty, ValueRangeProvider]
    courts: Annotated[list[Court], ProblemFactCollectionProperty, ValueRangeProvider]
    parts: Annotated[list[Part], PlanningEntityCollectionProperty]
    score: Annotated[HardSoftScore | None, PlanningScore] = field(default=None)

# Constraints
@constraint_provider
def define_constraints(constraint_factory: ConstraintFactory) -> list[Constraint]:
    return [
        # Hard constraints
        court_conflict(constraint_factory),
        # Soft constraints
        prefer_low_courts(constraint_factory),
    ]

def court_conflict(constraint_factory: ConstraintFactory) -> Constraint:
    """A court can accommodate at most one part at the same time (considering duration)."""
    def overlaps(part1: Part, part2: Part) -> bool:
        if part1.timeslot is None or part2.timeslot is None:
            return False
        start1 = part1.timeslot.start_min
        end1 = start1 + part1.duration_min
        start2 = part2.timeslot.start_min
        end2 = start2 + part2.duration_min
        return start1 < end2 and start2 < end1
    
    return (
        constraint_factory
        .for_each_unique_pair(Part,
            Joiners.equal(lambda part: part.court))
        .filter(lambda part1, part2: overlaps(part1, part2))
        .penalize(HardSoftScore.ONE_HARD)
        .as_constraint("Court conflict")
    )

def prefer_low_courts(constraint_factory: ConstraintFactory) -> Constraint:
    """Prefer lower court numbers (e.g., prefer baan 1 over baan 10)."""
    return (
        constraint_factory
        .for_each(Part)
        .filter(lambda part: part.court is not None)
        .penalize(HardSoftScore.ONE_SOFT, lambda part: part.court.number)
        .as_constraint("Prefer low courts")
    )

# Generate test problem (simplified 06-04-2026)
def generate_problem() -> Schedule:
    # 6 timeslots (08:30, 09:00, 09:30, 10:00, 10:30, 11:00)
    timeslots = [
        Timeslot(id=i, start_min=30 + i*30)
        for i in range(6)
    ]
    
    # 3 courts
    courts = [Court(id=i+1, number=i+1) for i in range(3)]
    
    # 5 parts (simplified)
    parts = [
        Part(id=1, team="HC19D1", label="S1", duration_min=60),
        Part(id=2, team="HC19D1", label="D1", duration_min=90),
        Part(id=3, team="HC19D2", label="S1", duration_min=60),
        Part(id=4, team="HC19D2", label="D1", duration_min=90),
        Part(id=5, team="HD19D1", label="S1", duration_min=60),
    ]
    
    return Schedule(timeslots=timeslots, courts=courts, parts=parts, score=None)

def main():
    print("[Timefold] Tennis scheduling test")
    print("=" * 60)
    
    problem = generate_problem()
    print(f"Problem: {len(problem.parts)} parts, {len(problem.timeslots)} slots, {len(problem.courts)} courts")
    print()
    
    solver_config = SolverConfig(
        solution_class=Schedule,
        entity_class_list=[Part],
        score_director_factory_config=ScoreDirectorFactoryConfig(
            constraint_provider_function=define_constraints
        ),
        termination_config=TerminationConfig(
            spent_limit=Duration(seconds=10)
        )
    )
    
    solver = SolverFactory.create(solver_config).build_solver()
    
    print("[Timefold] Solving...")
    solution = solver.solve(problem)
    
    print(f"[Timefold] Score: {solution.score}")
    print()
    
    # Print schedule
    print("Schedule:")
    print("-" * 60)
    for part in solution.parts:
        if part.timeslot and part.court:
            print(f"{part} → {part.timeslot} {part.court} ({part.duration_min} min)")
        else:
            print(f"{part} → NIET GELUKT")
    
    # Count unassigned
    unassigned = sum(1 for p in solution.parts if p.timeslot is None or p.court is None)
    print()
    print(f"Scheduled: {len(solution.parts) - unassigned}/{len(solution.parts)}")
    print(f"NIET_GELUKT: {unassigned}")

if __name__ == "__main__":
    main()
