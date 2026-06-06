#!/usr/bin/env python3
"""Introspect cuOpt routing API."""

from cuopt import routing
import inspect

print("=== DataModel constructor ===")
sig = inspect.signature(routing.DataModel.__init__)
print(f"DataModel.__init__{sig}")
print()

print("=== DataModel methods ===")
for name in sorted(dir(routing.DataModel)):
    if name.startswith("_"):
        continue
    attr = getattr(routing.DataModel, name)
    if callable(attr):
        try:
            sig = inspect.signature(attr)
            print(f"{name}{sig}")
        except Exception as e:
            print(f"{name}: (no signature - {e})")
print()

print("=== routing module exports ===")
exports = [x for x in dir(routing) if not x.startswith("_")]
print(exports)
print()

print("=== SolverConfig constructor ===")
try:
    sig = inspect.signature(routing.SolverConfig.__init__)
    print(f"SolverConfig.__init__{sig}")
except Exception as e:
    print(f"SolverConfig: {e}")
print()

print("=== solve function ===")
try:
    sig = inspect.signature(routing.solve)
    print(f"routing.solve{sig}")
except Exception as e:
    print(f"solve: {e}")
