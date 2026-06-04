# cuOpt Setup and Usage Guide

## Overview

NVIDIA cuOpt is a GPU-accelerated optimization library that we're using as an **optional** alternative solver for our court scheduling problem. While cuOpt is primarily designed for Vehicle Routing Problems (VRP), we can map our scheduling constraints to a MILP formulation.

**Note**: cuOpt is **completely optional**. The default OR-Tools solver works fine without a GPU and is the recommended choice for most users. cuOpt is provided for experimentation and as an alternative for users with NVIDIA GPUs who want to explore GPU-accelerated solving.

## Dependencies

cuOpt is **not** listed in `pyproject.toml` or `requirements.txt` because:
1. It requires an NVIDIA GPU and CUDA drivers
2. It's optional - OR-Tools is the default and works on any CPU
3. Installation varies by system (pip, conda, or Docker)
4. Not all users have compatible hardware

To use cuOpt, you must install it manually following the instructions below.

## System Requirements

- NVIDIA GPU with CUDA support (compute capability 7.0+)
- CUDA Toolkit 12.x or 13.x
- Python 3.10+
- Linux operating system (recommended)

## Installation

### ⚠️ Known Issues (2026-06-04)

**cudf pandas compatibility**: cuOpt 26.4.0 requires cudf, which has a known incompatibility with pandas ≥2.2. 
The error: `AttributeError: module 'pandas.api.types' has no attribute 'is_interval'`

**Workaround**: Install pandas 2.1.x before cuOpt:
```bash
pip install 'pandas>=2.0,<2.2' 'numpy<2.0'
pip install cuopt-cu12 cudf-cu12
```

**Status**: Installation succeeded on laptop (RTX A2000), but runtime import fails due to pandas API changes in cudf.

### Option 1: pip (Recommended for Development)

```bash
# Install pandas 2.1.x first (required for cudf compatibility)
pip install 'pandas>=2.0,<2.2' 'numpy<2.0'

# Then install cuOpt
pip install cuopt-cu12  # For CUDA 12.x
# or
pip install cuopt-cu13  # For CUDA 13.x
```

Also requires:
```bash
pip install cudf-cu12  # cuDF for DataFrame operations
```

### Option 2: Docker (Recommended for Production)

```bash
# Pull the cuOpt container
docker pull nvidia/cuopt:25.12.0a-cuda12.9-py3.13

# Run with GPU support
docker run -it --rm --gpus all \
  -v $(pwd):/workspace \
  -w /workspace \
  nvidia/cuopt:25.12.0a-cuda12.9-py3.13 \
  /bin/bash
```

### Option 3: Conda

```bash
conda install -c nvidia cuopt
```

## Verification

After installation, verify that cuOpt is working:

```bash
python -c "from cuopt import routing; print('cuOpt is installed correctly')"
```

If you get a CUDA error, check:
1. NVIDIA drivers are installed: `nvidia-smi`
2. GPU is visible to the container: `docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi`
3. CUDA version matches cuOpt version

## Problem Mapping: Court Scheduling → MILP

### Decision Variables

The cuOpt MILP implementation uses the following variables:

**Binary Variables:**
- `x[part_id, slot, court] ∈ {0,1}`: 1 if match part `p` starts at time slot `s` on court `c`
- `team_uses_court[team_id, court] ∈ {0,1}`: 1 if team uses this court at any point

**Continuous Variables:**
- `team_start[team_id] ∈ ℝ≥0`: Earliest start time (minutes from 08:00) for team
- `team_end[team_id] ∈ ℝ≥0`: Latest end time (minutes from 08:00) for team
- `team_gap_penalty[team_id] ∈ ℝ≥0`: Penalty for gaps between matches

**Integer Variables:**
- `block_count[team_id] ∈ ℤ≥0`: Number of separate time blocks for this team

### Hard Constraints

1. **Each part scheduled at most once:**
   ```
   ∀p: Σ_(s,c) x[p,s,c] ≤ 1
   ```

2. **No court overlaps:**
   ```
   ∀court c, timeslot t: Σ_p x[p,s(p),c] ≤ 1
   ```
   where sum is over all parts p that cover slot t

3. **Court pairing for non-mixed teams (S+D pairs):**
   - If both S and D scheduled, they start at same time
   - Courts must be adjacent and in same COURT_PAIR: (1,2), (3,4), (5,6), (7,8), (9,10)

4. **Max 2 courts per team:**
   ```
   ∀team: Σ_c team_uses_court[team,c] ≤ 2
   ```

5. **Link court usage:**
   ```
   ∀team t, court c: Σ_(p,s) x[p,s,c] ≤ M * team_uses_court[t,c]
   ```

6. **Youth start time ≥08:30:**
   - Enforced by not creating variables for earlier slots

7. **Team time windows:**
   ```
   x[p,s,c] = 1 → team_start[t] ≤ s*15
   x[p,s,c] = 1 → team_end[t] ≥ (s + duration)*15
   ```

8. **Reserved slots:**
   - Variables not created for reserved (court, slot) combinations

9. **S before D (hard for non-mixed teams):**
   ```
   start_time(S_part) ≤ start_time(D_part)
   ```

### Soft Constraints (Objective Function)

Minimize weighted sum:
```
w_high_court * Σ_(p,s,c) (court * x[p,s,c])
+ w_team_span * Σ_t (team_end[t] - team_start[t])
+ w_long_gap * (gap penalties)
+ w_block_rise * Σ_t block_count[t]
+ w_late_start * (late start penalties)
+ w_youth_late * (youth late penalties)
```

### Implementation Status (2026-06-04)

✅ **Complete MILP formulation** in `scripts/cuopt_planner.py`
- All decision variables defined
- All hard constraints implemented
- Objective function with all penalty terms
- Solution extraction logic

❌ **Cannot test** due to cudf/pandas compatibility issues
- cuOpt linear_programming API is correct
- Needs cuOpt 26.4+ with fixed cudf

### Next Steps for Testing

1. Wait for cudf fix or use Docker container
2. Test on date 06-04-2026 (49 parts in gold):
   ```bash
   python scripts/cuopt_planner.py --date 06-04-2026 --time-limit 60
   ```
3. Compare with OR-Tools baseline:
   ```bash
   python scripts/ortools_planner.py --date 06-04-2026
   ```
4. Metrics to track:
   - Number of NIET_GELUKT (unscheduled parts)
   - Constraint violations (should be 0)
   - Objective value
   - Solve time
   - GPU memory usage

## Problem Mapping: Court Scheduling → VRP (Legacy)

Our court scheduling problem can be mapped to a VRP as follows:

### VRP Concepts → Scheduling Concepts

- **Vehicles** → **Teams** (each team is a "vehicle" that visits time slots)
- **Locations** → **Time slots × Courts** (each combination is a "location")
- **Tasks/Deliveries** → **Match parts** (S1, D1, etc. that need to be scheduled)
- **Depots** → **Start/end of day** (teams start and return to "depot")
- **Travel time** → **Time between slots**
- **Capacity constraints** → **Court pair constraints, max 2 courts per team**
- **Time windows** → **Earliest/latest start times for matches**
- **Order constraints** → **S before D for coupled matches**

### Key Differences from Pure VRP

1. **Multiple vehicles per task**: A match part occupies a court at a time, but doesn't "belong" to a vehicle
2. **Court pairing**: Matches must be on adjacent courts (1+2, 3+4, etc.)
3. **No actual routing**: Teams don't physically move between courts in sequence
4. **Objective**: Minimize team span + maximize compactness (not typical distance minimization)

## Constraints Implementation

### Hard Constraints
1. **Court pairs**: Use `order_locations` or custom constraints
2. **No overlap**: Implicit in VRP formulation (one task per time-court location)
3. **Max 2 courts per team**: Vehicle capacity constraint
4. **Youth start time ≥08:30**: Time window constraints
5. **Coupled S/D start together**: Order/precedence constraints

### Soft Constraints (via penalties in objective)
1. **S before D**: Penalty for reversed order
2. **Compact blocks**: Penalty for gaps in team schedule
3. **Low court preference**: Add cost to higher-numbered courts
4. **Short team spans**: Minimize route duration

## Usage in build_pages.py

```bash
# Use OR-Tools (default)
python scripts/build_pages.py

# Use cuOpt
python scripts/build_pages.py --solver cuopt

# Compare both solvers
python scripts/build_pages.py --solver both
```

## Output Files

- OR-Tools results: `docs/ortools_YYYY-MM-DD.json`
- cuOpt results: `docs/cuopt_YYYY-MM-DD.json`
- HTML visualization: `docs/index.html` (can switch between solvers)

## Performance Notes

- **cuOpt** is designed for GPU acceleration and may be faster for large problem instances
- **OR-Tools** uses constraint programming and may find better solutions for highly constrained problems
- **First run** of cuOpt may be slower due to GPU initialization
- **GPU memory**: cuOpt requires ~2-4GB GPU memory for typical problem sizes

## Troubleshooting

### "No GPU available" Error
```bash
# Check GPU visibility
nvidia-smi

# If in Docker, ensure --gpus all flag is set
docker run --gpus all ...
```

### Import Error: "No module named 'cuopt'"
- Verify installation: `pip list | grep cuopt`
- Check Python version compatibility (3.10+)
- Ensure CUDA version matches

### Poor Solution Quality
- Increase time limit: `--time-limit 120` (default: 60s)
- Try different solver settings in `cuopt_planner.py`
- Compare with OR-Tools results to identify specific constraint violations

### Memory Errors
- Reduce problem size (fewer teams per day)
- Use smaller cost matrix precision
- Close other GPU applications

## References

- [cuOpt Documentation](https://docs.nvidia.com/cuopt/user-guide/latest/)
- [cuOpt Examples](https://github.com/NVIDIA/cuopt-examples)
- [cuOpt API Reference](https://docs.nvidia.com/cuopt/user-guide/latest/api.html)
- [VRP on Wikipedia](https://en.wikipedia.org/wiki/Vehicle_routing_problem)

## Known Limitations

1. **GPU requirement**: Unlike OR-Tools, cuOpt requires a CUDA-capable GPU
2. **Learning curve**: VRP formulation is less intuitive than CP-SAT for scheduling
3. **Constraint expressiveness**: Some custom constraints may be harder to express in VRP form
4. **Debugging**: GPU errors can be harder to debug than CPU-based OR-Tools

## Development Notes

The cuOpt implementation is experimental and aims to:
1. Provide an alternative solver for comparison
2. Leverage GPU acceleration for larger problem instances
3. Validate that VRP formulation can handle our constraints
4. Enable future scaling if we add more teams/courts

For most use cases, OR-Tools remains the recommended solver unless:
- You have a CUDA GPU available
- Problem size exceeds OR-Tools performance limits
- You want to experiment with alternative formulations
