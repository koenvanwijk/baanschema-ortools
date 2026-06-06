from cuopt import routing

print('SolutionStatus attrs:', [x for x in dir(routing.SolutionStatus) if not x.startswith('_')])
for name in ['EMPTY','FAIL','SUCCESS','TIMEOUT']:
    print(name, getattr(routing.SolutionStatus, name, None))

print('\nAssignment methods:')
for n in dir(routing.Assignment):
    if not n.startswith('_'):
        print(n)
