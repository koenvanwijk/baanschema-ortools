"""Quick constraint count check without solving."""
import sys
sys.path.insert(0, 'scripts')

# Mock cuOpt to avoid import errors
class MockVar:
    def __init__(self, name): self.name = name
    def getVariableName(self): return self.name

class MockProblem:
    def __init__(self, name):
        self.name = name
        self.vars = []
        self.constraints = []
        self.NumVariables = 0
        self.NumConstraints = 0
    
    def addVariable(self, name, vtype, lb, ub):
        var = MockVar(name)
        self.vars.append(var)
        self.NumVariables += 1
        return var
    
    def addConstraint(self, expr, name):
        self.constraints.append(name)
        self.NumConstraints += 1
    
    def setObjective(self, expr, sense):
        pass

class MockLinearExpression:
    def __init__(self, *args): pass
    def __add__(self, other): return self
    def __radd__(self, other): return self
    def __mul__(self, other): return self
    def __rmul__(self, other): return self
    def __le__(self, other): return self
    def __eq__(self, other): return self

class MockVType:
    INTEGER = 0

class MockSense:
    MINIMIZE = 0

sys.modules['cuopt'] = type(sys)('cuopt')
sys.modules['cuopt.linear_programming'] = type(sys)('cuopt.linear_programming')
sys.modules['cuopt.linear_programming.problem'] = type(sys)('cuopt.linear_programming.problem')
sys.modules['cuopt.linear_programming.solver_settings'] = type(sys)('cuopt.linear_programming.solver_settings')

import cuopt.linear_programming.problem as prob_mod
prob_mod.Problem = MockProblem
prob_mod.LinearExpression = MockLinearExpression
prob_mod.VType = MockVType()
prob_mod.sense = MockSense()

# Now import and run constraint building
from cuopt_workforce import solve_day
from ortools_planner import parse_input, INPUT

teams, reservations = parse_input(INPUT)
print("Building constraints (no solve)...")

# Patch solve to skip
original_solve_day = solve_day

def mock_solve_day(date, teams, reservations, time_limit_s):
    # Run everything except solve
    import cuopt_workforce
    result = original_solve_day.__wrapped__(date, teams, reservations, time_limit_s)
    return result

# Monkey-patch to capture problem before solve
captured_problem = None

def capture_problem(self, settings):
    global captured_problem
    captured_problem = self
    print(f"\n[CAPTURED] Problem: {self.NumVariables} vars, {self.NumConstraints} constraints")
    print(f"[CAPTURED] Constraint names sample: {self.constraints[:10]}")
    raise RuntimeError("Stopping before solve")

MockProblem.solve = capture_problem

try:
    result = solve_day('06-04-2026', teams, reservations, 10)
except RuntimeError as e:
    if "Stopping before solve" in str(e):
        print("\n✅ Constraint building complete")
        if captured_problem:
            print(f"Total variables: {captured_problem.NumVariables}")
            print(f"Total constraints: {captured_problem.NumConstraints}")
            
            # Count constraint types
            from collections import Counter
            constraint_types = Counter()
            for c in captured_problem.constraints:
                if c.startswith('part'):
                    constraint_types['part_assignment'] += 1
                elif c.startswith('overlap'):
                    constraint_types['non_overlap'] += 1
            
            print(f"\nConstraint breakdown:")
            for ctype, count in constraint_types.items():
                print(f"  {ctype}: {count}")
    else:
        raise
