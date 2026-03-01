from baanschema.model import Match, ProblemData, solve_schedule


def test_solver_returns_feasible_schedule():
    data = ProblemData(
        courts=["c1", "c2"],
        slots=["s1", "s2", "s3"],
        matches=[
            Match("m1", ("A", "B", "C", "D")),
            Match("m2", ("E", "F", "G", "H")),
            Match("m3", ("A", "E", "I", "J")),
        ],
    )

    result = solve_schedule(data)

    assert result.status in {"OPTIMAL", "FEASIBLE"}
    assert len(result.assignments) == 3
