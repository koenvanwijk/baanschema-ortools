from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from ortools.sat.python import cp_model


@dataclass
class Match:
    id: str
    players: Tuple[str, ...]


@dataclass
class ProblemData:
    courts: List[str]
    slots: List[str]
    matches: List[Match]


@dataclass
class ScheduleResult:
    status: str
    assignments: List[Tuple[str, str, str]]  # (match_id, slot_id, court_id)
    objective: int | None = None


def solve_schedule(data: ProblemData, time_limit_s: float = 10.0) -> ScheduleResult:
    model = cp_model.CpModel()

    # x[(m, s, c)] = 1 <=> match m staat op slot s op court c
    x: Dict[Tuple[int, int, int], cp_model.IntVar] = {}
    for m_idx, _match in enumerate(data.matches):
        for s_idx, _slot in enumerate(data.slots):
            for c_idx, _court in enumerate(data.courts):
                x[(m_idx, s_idx, c_idx)] = model.new_bool_var(
                    f"x_m{m_idx}_s{s_idx}_c{c_idx}"
                )

    # Hard 1: elke wedstrijd precies 1x inplannen
    for m_idx, _match in enumerate(data.matches):
        model.add(
            sum(
                x[(m_idx, s_idx, c_idx)]
                for s_idx in range(len(data.slots))
                for c_idx in range(len(data.courts))
            )
            == 1
        )

    # Hard 2: per court+slot max 1 wedstrijd
    for s_idx, _slot in enumerate(data.slots):
        for c_idx, _court in enumerate(data.courts):
            model.add(sum(x[(m_idx, s_idx, c_idx)] for m_idx in range(len(data.matches))) <= 1)

    # Hard 3: speler niet in 2 wedstrijden op hetzelfde slot
    all_players = sorted({p for m in data.matches for p in m.players})
    player_to_matches: Dict[str, List[int]] = {p: [] for p in all_players}
    for m_idx, match in enumerate(data.matches):
        for p in match.players:
            player_to_matches[p].append(m_idx)

    for p in all_players:
        for s_idx, _slot in enumerate(data.slots):
            model.add(
                sum(
                    x[(m_idx, s_idx, c_idx)]
                    for m_idx in player_to_matches[p]
                    for c_idx in range(len(data.courts))
                )
                <= 1
            )

    # Soft: back-to-back wedstrijden minimaliseren
    penalties = []
    for p in all_players:
        for s_idx in range(len(data.slots) - 1):
            plays_slot = model.new_bool_var(f"plays_{p}_s{s_idx}")
            plays_next = model.new_bool_var(f"plays_{p}_s{s_idx+1}")

            model.add(
                sum(
                    x[(m_idx, s_idx, c_idx)]
                    for m_idx in player_to_matches[p]
                    for c_idx in range(len(data.courts))
                )
                >= 1
            ).only_enforce_if(plays_slot)
            model.add(
                sum(
                    x[(m_idx, s_idx, c_idx)]
                    for m_idx in player_to_matches[p]
                    for c_idx in range(len(data.courts))
                )
                == 0
            ).only_enforce_if(plays_slot.Not())

            model.add(
                sum(
                    x[(m_idx, s_idx + 1, c_idx)]
                    for m_idx in player_to_matches[p]
                    for c_idx in range(len(data.courts))
                )
                >= 1
            ).only_enforce_if(plays_next)
            model.add(
                sum(
                    x[(m_idx, s_idx + 1, c_idx)]
                    for m_idx in player_to_matches[p]
                    for c_idx in range(len(data.courts))
                )
                == 0
            ).only_enforce_if(plays_next.Not())

            back_to_back = model.new_bool_var(f"b2b_{p}_s{s_idx}")
            model.add_bool_and([plays_slot, plays_next]).only_enforce_if(back_to_back)
            model.add_bool_or([plays_slot.Not(), plays_next.Not(), back_to_back])
            penalties.append(back_to_back)

    model.minimize(sum(penalties))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s

    status = solver.solve(model)

    status_name = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return ScheduleResult(status=status_name, assignments=[])

    assignments: List[Tuple[str, str, str]] = []
    for m_idx, match in enumerate(data.matches):
        for s_idx, slot in enumerate(data.slots):
            for c_idx, court in enumerate(data.courts):
                if solver.value(x[(m_idx, s_idx, c_idx)]) == 1:
                    assignments.append((match.id, slot, court))

    return ScheduleResult(
        status=status_name,
        assignments=sorted(assignments, key=lambda t: (t[1], t[2], t[0])),
        objective=int(solver.objective_value),
    )
