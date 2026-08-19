# cuOpt MILP Implementation Test Plan

> **UPDATE 2026-08-19 — the solver now runs.** The "blocked by cudf/pandas"
> status below is out of date. The planner was successfully run on all 7
> play-days using the official cuOpt Docker image. See
> [`docs/CUOPT_TEST_RESULTS.md`](docs/CUOPT_TEST_RESULTS.md) for the full results,
> the bugs that were fixed, and the important caveats. The historical plan below
> is kept for reference.

## Date: 2026-06-04

## Current Status

### ✅ Completed

1. **Full MILP formulation implemented** in `scripts/cuopt_planner.py`
   - 400+ lines of complete constraint implementation
   - All decision variables (binary, continuous, integer)
   - All hard constraints (9 constraint types)
   - Complete objective function with weighted penalties
   - Solution extraction logic

2. **GPU availability confirmed**
   - Local: NVIDIA RTX A2000 (4GB)
   - spark-480b: NVIDIA GB10 (larger)
   - spark-36d1: GB200 (largest)

3. **cuOpt packages installed**
   - cuopt-cu12==26.4.0
   - cudf-cu12==26.4.0
   - Via `uv pip install` in project venv

### ❌ Blocked

**cudf pandas incompatibility:**
```python
AttributeError: module 'pandas.api.types' has no attribute 'is_interval'
```

**Root cause:** cudf 26.4.0 expects pandas API that was removed in pandas 2.2+

**Attempted fixes:**
- Downgrade to pandas 2.1.4 → still fails (cudf references removed API)
- Downgrade to pandas 2.0.x → not compatible with cudf requirements
- Install via uv, pip3, python3 -m pip → all same error

**Workaround needed:**
- Use cuOpt Docker container (26.4.0 has compatible pandas pre-installed)
- Or wait for cudf 26.4.1+ with pandas 2.3+ compatibility

## Implementation Details

### Variables Created

```python
# Binary: x[part, slot, court] → 49 parts × ~40 slots × 10 courts ≈ 19,600 vars
# (after filtering for time windows and reserved slots)

# Continuous: team_start[team], team_end[team] → 2 vars per team
# Binary: team_uses_court[team, court] → teams × 10 courts
# Continuous: team_gap_penalty[team] → 1 per team
# Integer: block_count[team] → 1 per team
```

For date 06-04-2026:
- 17 teams → 49 parts
- ~15,000-18,000 binary x variables (after filtering)
- ~34 continuous team variables
- ~170 binary court usage variables
- ~17 gap penalty variables
- ~17 block count variables

### Constraints Implemented

1. **Part uniqueness:** 49 constraints (one per part)
2. **Court occupancy:** ~4,800 constraints (10 courts × 48 slots)
3. **Court pairing:** ~200 constraints (S+D pairing for non-mixed teams)
4. **Max 2 courts:** 17 constraints (one per team)
5. **Court linkage:** ~170 constraints (teams × courts)
6. **Team start bounds:** ~800 constraints (big-M for each x variable)
7. **Team end bounds:** ~800 constraints (big-M for each x variable)
8. **S before D:** ~100 constraints (prevent reversed ordering)

**Total:** ~7,000-8,000 linear constraints

### Objective Terms

Weighted sum of:
1. High court penalty (prefer lower courts): `w=200k`
2. Team span (minimize time spread): `w=200k`
3. Long gap penalty (avoid idle time): `w=5M`
4. Block fragmentation (prefer contiguous): `w=4M`
5. Late start penalty (prefer early): `w=120k`
6. Youth late penalty (youth early): `w=80k`

## Testing Plan (When cudf Works)

### Step 1: Baseline Test

```bash
cd /home/kwijk/.openclaw/workspace/projects/baanschema-ortools

# Test cuOpt solver standalone
uv run python scripts/cuopt_planner.py \
  --date 06-04-2026 \
  --time-limit 60 \
  --out docs/cuopt_result.json
```

**Expected output:**
- Status: OPTIMAL or FEASIBLE
- Scheduled: 49/49 parts (or close)
- Objective value: < 50M (if competitive with OR-Tools)
- Solve time: < 60s

### Step 2: Compare with OR-Tools

```bash
# Run OR-Tools for baseline
python scripts/ortools_planner.py --date 06-04-2026

# Compare results
python scripts/compare_to_gold.py \
  --ortools docs/ortools_06-04-2026.json \
  --cuopt docs/cuopt_result.json
```

**Metrics to compare:**
- NIET_GELUKT count (lower is better)
- Constraint violations (should be 0 for both)
- Objective value (cuOpt may differ due to formulation)
- Solve time (cuOpt should be faster if GPU is utilized)

### Step 3: Integration Test

```bash
# Test via build_pages with cuopt solver
python scripts/build_pages.py \
  --solver cuopt \
  --dates 06-04-2026
```

**Expected output:**
- HTML page generated in `docs/06-04-2026.html`
- Valid schedule (no overlaps, all constraints satisfied)
- Comparable quality to OR-Tools version

### Step 4: GPU Machine Test

If local GPU is insufficient, test on spark-480b:

```bash
# SSH to spark-480b
ssh kwijk@192.168.86.32

# Clone repo or copy files
cd ~/baanschema-ortools

# Run cuOpt test
python scripts/cuopt_planner.py --date 06-04-2026 --time-limit 60

# Monitor GPU usage
nvidia-smi -l 1
```

**Expected GPU usage:**
- Memory: 1-2GB (out of 32GB+ available)
- Utilization: 50-100% during solve
- Solve time: potentially faster than local RTX A2000

## Docker Alternative (Recommended)

Since cudf has compatibility issues, use Docker:

```bash
cd /home/kwijk/.openclaw/workspace/projects/baanschema-ortools

# Pull cuOpt Docker image (has compatible pandas)
docker pull nvidia/cuopt:25.12.0a-cuda12.9-py3.13

# Run cuOpt solver in container
docker run -it --rm --gpus all \
  -v $(pwd):/workspace \
  -w /workspace \
  nvidia/cuopt:25.12.0a-cuda12.9-py3.13 \
  python scripts/cuopt_planner.py --date 06-04-2026 --time-limit 60 --out /workspace/docs/cuopt_result.json
```

This avoids the pandas/cudf version conflict by using NVIDIA's pre-configured environment.

## Validation Checklist

When testing succeeds, verify:

- [ ] All 49 parts scheduled (or >= 45 if same as OR-Tools)
- [ ] No court overlaps (check visually in HTML)
- [ ] S+D pairs on adjacent courts (for non-mixed teams)
- [ ] No team uses > 2 courts
- [ ] Youth teams start >= 08:30
- [ ] All teams finish by 20:00
- [ ] S before D respected (non-mixed teams)
- [ ] Reserved slots (rood/oranje) respected
- [ ] Objective value reasonable (< 100M)
- [ ] Solve completes within time limit

## Performance Benchmarks

Target metrics (06-04-2026):
- **OR-Tools**: ~30-50s solve time, 2-5 NIET_GELUKT
- **cuOpt (expected)**: 10-30s solve time, similar quality

If cuOpt is significantly slower or worse quality, debug:
1. Check GPU utilization (should be > 50%)
2. Verify constraint formulation matches OR-Tools logic
3. Tune solver parameters (time limit, tolerances)
4. Consider constraint simplification for GPU

## Known Limitations

1. **Block count constraint**: Currently simplified (doesn't count exact blocks)
2. **Gap penalty**: Uses span - total_duration as proxy (not exact gap tracking)
3. **Big-M constants**: May need tuning (currently M=100, M_time=1200)
4. **Court pair linking**: Assumes specific slot matching (may be too strict)

These can be refined after initial testing confirms basic functionality.

## Next Actions

1. ✅ Implement full MILP formulation → **DONE**
2. ⏳ Wait for cudf fix or use Docker → **IN PROGRESS**
3. ⏳ Test on 06-04-2026 → **BLOCKED BY CUDF**
4. ⏳ Compare with OR-Tools → **BLOCKED**
5. ⏳ Update CUOPT_SETUP.md with results → **BLOCKED**
6. ⏳ Commit and push → **BLOCKED**

## Commit Message (When Ready)

```
Implement full MILP formulation in cuOpt solver

- Add 400+ lines of MILP constraints to scripts/cuopt_planner.py
- Implement all 9 hard constraint types:
  * Part uniqueness (each scheduled once)
  * Court occupancy (no overlaps)
  * Court pairing (S+D on adjacent courts)
  * Max 2 courts per team
  * Court usage linking
  * Youth start time >= 08:30
  * Team time windows
  * Reserved slots
  * S before D ordering
- Add objective function with 6 penalty terms:
  * High court penalty (prefer low courts)
  * Team span minimization
  * Long gap penalty
  * Block fragmentation penalty
  * Late start penalty
  * Youth late penalty
- Include solution extraction and formatting
- Update CUOPT_SETUP.md with MILP formulation details

Testing blocked by cudf/pandas incompatibility in cuOpt 26.4.0.
Recommend testing via Docker container:
  docker pull nvidia/cuopt:25.12.0a-cuda12.9-py3.13

Target test: date 06-04-2026 (49 parts, 17 teams)
Expected performance: <60s solve time, <5 unscheduled parts

Ref: Task from main agent, implemented full MILP per spec
```
