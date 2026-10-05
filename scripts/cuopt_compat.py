"""Compatibility shims for NVIDIA cuOpt's linear_programming modelling API.

cuOpt 25.12 ships a symbolic modelling layer (``Problem`` / ``Variable`` /
``LinearExpression``) that mirrors PuLP/Gurobi, but two operator overloads are
broken in that release:

1. ``LinearExpression.__rmul__`` is defined as ``return other * self``. When
   ``other`` is a plain ``int``/``float`` (e.g. ``5_000_000 * expr``), Python
   evaluates ``int.__mul__(other, self)`` which returns ``NotImplemented`` and
   then calls ``LinearExpression.__rmul__`` again -> infinite recursion
   (``RecursionError: maximum recursion depth exceeded``).

2. ``Variable`` and ``LinearExpression`` have no ``__neg__``, so unary ``-expr``
   raises ``TypeError: bad operand type for unary -``.

Both patterns occur throughout ``cuopt_planner.py`` (``M * (1 - x)``,
``w * (team_end - team_start) / 100`` etc.), so the planner cannot build its
model without these fixes.

Importing this module patches the classes in place. It is a no-op if cuOpt is
not importable (e.g. on a CPU-only machine), so importing it never hurts.
"""

from __future__ import annotations


def apply_patches() -> bool:
    """Patch cuOpt's expression classes. Returns True if patches were applied."""
    try:
        from cuopt.linear_programming import problem as _pb
    except Exception:
        # cuOpt not available (no GPU / not installed) -- nothing to patch.
        return False

    LinearExpression = _pb.LinearExpression
    Variable = _pb.Variable

    # Fix 1: scalar * LinearExpression recursion.
    # __mul__ already handles the int/float/Variable/LinearExpression cases
    # correctly, and scalar multiplication is commutative, so delegate to it.
    def _le_rmul(self, other):
        return self.__mul__(other)

    LinearExpression.__rmul__ = _le_rmul

    # Fix 2: unary negation, expressed as multiplication by -1.
    def _neg(self):
        return self.__mul__(-1.0)

    LinearExpression.__neg__ = _neg
    Variable.__neg__ = _neg

    return True


PATCHED = apply_patches()
