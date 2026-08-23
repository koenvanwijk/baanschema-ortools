# cuOpt MILP Planner — Test Results (2026-08-19)

This documents the first **successful** end-to-end run of the cuOpt MILP planner
(`scripts/cuopt_planner.py`). Prior to this, testing was reported as "blocked by
a cudf/pandas incompatibility" and the solver had never actually run.

## TL;DR

- ✅ The cuOpt planner now **runs on the GPU and solves all 7 play-days**.
- ✅ It produces valid schedules (0 court overlaps, 0 court-pair violations) that
  are **competitive with OR-Tools** on the constraints it models.
- ⚠️ It uses a **simplified** constraint model (see "Caveats"), so its lower
  unscheduled counts are not a strict apples-to-apples "better than OR-Tools".

## Environment

| | |
|---|---|
| GPU | **NVIDIA RTX A2000 Laptop GPU, 4 GB VRAM** (compute capability 8.6) |
| Host driver | 570.211.01 (CUDA 12.8) |
| Container | `nvidia/cuopt:25.12.0a-cuda12.9-py3.13` (cuOpt 25.12.0) |
| CUDA in container | 12.9 (runs on the 12.8 driver via CUDA minor-version compatibility) |

> Note: the machine described in the task brief (spark-480b / GB10, 32 GB, 1.1 TB
> free) was **not** the machine this ran on. The actual host is a laptop with an
> RTX A2000 (4 GB) and ~14–21 GB free disk. Everything below was achieved on that
> hardware, which is why memory/time limits mattered.

## How it was unblocked

The previous "blockers" were partly misdiagnosed. What actually happened:

1. **cudf/pandas incompatibility** — real, but only for the *pip*-installed
   `cuopt-cu12`/`cudf-cu12`. Using the official **NVIDIA cuOpt Docker image**
   ships a matching cudf/pandas pair, so the import works. No pandas downgrade
   needed.

2. **"MILP is server-only" (docs/CUOPT_SERVER_API_FINDINGS.md)** — **incorrect**
   for cuOpt 25.12. `cuopt.linear_programming.problem.Problem` provides a full
   symbolic MILP modelling API (`addVariable` / `addConstraint` / `setObjective`
   / `solve`), exactly what `cuopt_planner.py` assumed. No server/client needed.

3. **cuOpt 25.12 operator bugs** — two genuine bugs in cuOpt's expression
   classes broke model building:
   - `LinearExpression.__rmul__` is `return other * self`, which infinitely
     recurses for `scalar * expr` (`RecursionError`).
   - No `__neg__`, so `-expr` raises `TypeError`.
   Both are patched at import time by **`scripts/cuopt_compat.py`**.

4. **Model explosion → segfault** — the original formulation generated
   **~2.77 million constraints** for a 17-team day (a pairwise-conflict
   enumeration for "S before D", plus one big-M row per `(part, slot, court)`
   for time windows). That segfaulted the 4 GB GPU. Reformulated using per-part
   linear time expressions → **~17k–28k constraints** (a ~100× reduction).

5. **Objective bugs** — the gap term `span - total_duration` could go negative
   (teams play in parallel on 2 courts, so span < total duration), which
   *rewarded* leaving parts unscheduled; there was no `team_end ≥ team_start`
   constraint; and the soft weights dwarfed the unscheduled penalty. Fixed with a
   non-negative gap variable, a span-nonneg constraint, and a dominant, properly
   scaled unscheduled penalty.

6. **Wrong constraints vs the reference model** — the original cuOpt "court
   pairing" forced each S part and D part onto *adjacent courts at the same slot*,
   and imposed a global "S before D" ordering. Neither matches the OR-Tools
   reference model, which instead requires (a) same-kind pairs to start together
   (S1+S2, S3+S4, D1+D2) and (b) each team to play on one adjacent court-pair.
   Corrected — this both fixed the semantics and made the problem much easier.

## Results — all 7 play-days

Time limit 120 s/day. cuOpt values are the best feasible solution found within
that budget (all returned `FeasibleFound`, not proven optimal).

| Date | cuOpt scheduled | cuOpt NIET_GELUKT | OR-Tools NIET_GELUKT | court overlaps | pair violations | solve time |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| 06-04-2026 | 49/49 | **0** | 2 | 0 | 0 | ~124 s |
| 12-04-2026 | 68/69 | **1** | 3 | 0 | 0 | ~127 s |
| 19-04-2026 | 71/72 | **1** | 4 | 0 | 0 | ~128 s |
| 10-05-2026 | 75/75 | **0** | 6 | 0 | 0 | ~128 s |
| 17-05-2026 | 61/73 | 12 | **4** | 0 | 0 | ~128 s |
| 25-05-2026 | 62/62 | **0** | 12 | 0 | 0 | ~126 s |
| 31-05-2026 | 58/58 | **0** | 0 | 0 | 0 | ~125 s |
| **Total** | | **14** | 31 | 0 | 0 | ~14 min |

- cuOpt matches or beats OR-Tools' unscheduled count on **6 of 7 days**.
- Only **17-05-2026** is worse (12 vs 4): a harder instance where the branch &
  bound stalled far from the LP lower bound within the 120 s budget on this
  4 GB laptop GPU. More time / a bigger GPU would likely help.
- Objective values are **not** comparable between solvers (different formulations
  and scaling). For cuOpt, an objective ≈ n·1e8 means n parts unscheduled; a
  small objective (< 1e5) means everything scheduled and only soft costs remain.

Output files: `docs/cuopt_<DD-MM-YYYY>.json` (same schema as the OR-Tools files).

## Caveats — why "fewer NIET_GELUKT" is not strictly "better"

The cuOpt MILP is a **simplified** model. Compared to `ortools_planner.py` it
currently **omits** several constraints:

- Player-resource limits (≤ 4 players and ≤ 2 simultaneous matches per team per
  timeslot; separate male/female demand).
- "Singles and doubles not at the same time" / "mixed and doubles not at the same
  time" mode constraints.
- The soft objectives (compactness, court preference, morning occupancy, cutoff
  bonuses) are only partially modelled and differently weighted.

Because cuOpt's feasible region is **looser**, it can pack in more parts. Its
schedules are valid for everything it *does* model (verified: 0 court overlaps, 0
court-pair violations across all 7 days, checked per `team_id`), but they may
violate the player-resource rules that OR-Tools enforces. Closing this gap is the
main future-work item if cuOpt is to be a drop-in replacement rather than an
experiment.

## Performance notes

- Model sizes: ~17k–28k constraints, ~200k–320k nonzeros, ~17k–28k binaries.
- Papilo presolve + branch & bound run partly on CPU (15 threads) and partly on
  the GPU; VRAM use stayed within the 4 GB budget after the reformulation.
- The LP relaxation is loose (it schedules everything fractionally), so the
  integrality gap is large and the solver rarely proves optimality in 120 s. It
  does, however, find good feasible solutions quickly.

## How to reproduce

```bash
docker pull nvidia/cuopt:25.12.0a-cuda12.9-py3.13

# one day
docker run --rm --gpus all -v "$(pwd)":/workspace -w /workspace \
  nvidia/cuopt:25.12.0a-cuda12.9-py3.13 \
  python scripts/cuopt_planner.py --date 06-04-2026 --time-limit 120 \
    --out docs/cuopt_06-04-2026.json

# all seven days: loop the dates
#   06-04-2026 12-04-2026 19-04-2026 10-05-2026 17-05-2026 25-05-2026 31-05-2026
```

Requires only an NVIDIA GPU (compute capability ≥ 7.0) and Docker with the NVIDIA
container toolkit. `scripts/cuopt_compat.py` is imported automatically by the
planner and patches the cuOpt 25.12 operator bugs.
