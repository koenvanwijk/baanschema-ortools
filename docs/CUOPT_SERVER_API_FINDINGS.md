# cuOpt Server API Findings (2026-06-04)

> **CORRECTION (2026-08-19):** The central conclusion of this document — that
> cuOpt MILP is only available via a server/client architecture — is **wrong for
> cuOpt 25.12**. That release ships a full symbolic MILP modelling API as
> `cuopt.linear_programming.problem.Problem` (`addVariable` / `addConstraint` /
> `setObjective` / `solve`), which is exactly what `cuopt_planner.py` uses. The
> planner now runs directly against this in-process Python API inside the official
> `nvidia/cuopt` Docker image — no server needed. See
> [`CUOPT_TEST_RESULTS.md`](CUOPT_TEST_RESULTS.md). The notes below are retained
> for historical context only.

## Discovery: MILP is Server-Based

### What We Learned
During Docker testing on spark-480b (GB10), we discovered that cuOpt's MILP support is **not available as a direct Python module** via `pip install cuopt-cu12`. Instead, it requires:

1. **cuopt-server** (CUDA 12.x or 13.x)
2. **cuopt-sh-client** (Python client library)
3. Server/client architecture (HTTP-based API)

### Installation (Correct)
```bash
# For CUDA 12.x
pip install \
  --extra-index-url=https://pypi.nvidia.com \
  nvidia-cuda-runtime-cu12==12.9.* \
  cuopt-server-cu12==26.6.* cuopt-sh-client==26.6.*

# For CUDA 13.x
pip install \
  --extra-index-url=https://pypi.nvidia.com \
  cuopt-server-cu13==26.6.* cuopt-sh-client==26.6.*
```

### What We Tried (Incorrect)
```bash
# ❌ This does NOT include MILP support
pip install cuopt-cu12 cudf-cu12
```

**Error:**
```python
from cuopt import milp
# ImportError: cannot import name 'milp' from 'cuopt'
```

### Architecture

#### Direct Python API (Available)
- **Routing (VRP, TSP, PDP)** — `from cuopt.routing import ...`
- Uses direct Python bindings to C++ core

#### Server API (Required for MILP)
- **MILP, LP, QP, QCQP, SOCP** — HTTP-based
- Client sends JSON problem definition
- Server solves on GPU and returns JSON solution
- Requires `cuopt-server` daemon running

### Implementation Options for `cuopt_planner.py`

#### Option 1: Server API (Recommended)
**Pros:**
- Access to MILP (what we originally planned)
- Production-ready (designed for microservices)
- Can run server on spark GPU, client anywhere

**Cons:**
- More setup (server daemon + client)
- HTTP overhead (but negligible for 60s solves)
- Requires cuopt-server package (larger install)

**Implementation:**
```python
from cuopt_sh_client import Client

client = Client(server_url="http://localhost:8080")
problem = {
    "variables": [...],
    "constraints": [...],
    "objective": {...}
}
result = client.solve_milp(problem, time_limit=60)
```

#### Option 2: VRP Reformulation
**Pros:**
- Direct Python API (no server needed)
- Simpler install (`cuopt-cu12` package)
- Proven fast for routing problems

**Cons:**
- Scheduling ≠ routing (awkward mapping)
- Less natural constraint expression
- May not fit all our constraints (court pairs, time windows)

**Mapping:**
- Teams → Vehicles
- Tijdslots → Locations
- Baan-paren → ???
- Team span → Route duration

**Challenge:** Court pairing constraint is hard to express in VRP terms.

#### Option 3: Defer cuOpt, Keep OR-Tools
**Pros:**
- OR-Tools works well (proven results)
- No additional setup
- CPU-based (no GPU requirement)

**Cons:**
- Misses GPU acceleration benefits
- No exploration of cuOpt capabilities

### Test Results (2026-06-04)

#### Environment
- **Host:** spark-480b (192.168.86.32)
- **GPU:** NVIDIA GB10, CUDA 12.6.3
- **Container:** nvidia/cuda:12.6.3-devel-ubuntu24.04
- **Test date:** 06-04-2026 (49 parts, 17 teams)

#### Attempt 1: Direct Python MILP
```bash
pip install cuopt-cu12 cudf-cu12 ortools
python scripts/cuopt_planner.py --date 06-04-2026
```

**Result:**
```
Status: ERROR
Error: cuOpt not available: cannot import name 'milp' from 'cuopt'
```

#### Attempt 2: cudf/pandas Incompatibility (Unrelated)
- cudf 26.4.0 requires `pandas.api.types.is_interval` (removed in pandas 2.2+)
- This blocked earlier local testing
- Not relevant for server API approach

### Next Steps

**Recommended Path: Server API Implementation**

1. **Install cuopt-server on spark-480b:**
   ```bash
   pip install --extra-index-url=https://pypi.nvidia.com \
     nvidia-cuda-runtime-cu12==12.9.* \
     cuopt-server-cu12==26.6.* cuopt-sh-client==26.6.*
   ```

2. **Start cuopt-server daemon:**
   ```bash
   cuopt-server --port 8080 --gpu 0
   # or via systemd for production
   ```

3. **Rewrite `_solve_day_cuopt()` to use client API:**
   - Convert MILP formulation to cuopt-server JSON format
   - Send via `cuopt_sh_client.Client.solve_milp()`
   - Parse JSON response and extract solution

4. **Test on 06-04-2026:**
   ```bash
   python scripts/cuopt_planner.py --date 06-04-2026 --server-url http://192.168.86.32:8080
   ```

5. **Compare with OR-Tools:**
   - NIET_GELUKT count
   - Solve time
   - Constraint violations
   - Objective value

### Documentation Updates Needed

- `docs/CUOPT_SETUP.md`: Add server API installation steps
- `scripts/cuopt_planner.py`: Add `--server-url` CLI argument
- `scripts/cuopt_planner.py`: Rewrite solver to use client API
- `TEST_CUOPT.md`: Update test plan for server-based approach

### Resources

- [cuOpt GitHub](https://github.com/NVIDIA/cuopt)
- [cuOpt Documentation](https://docs.nvidia.com/cuopt/index.html)
- [Server API Guide](https://docs.nvidia.com/cuopt/user-guide/latest/cuopt-server/quick-start.html)
- [MILP Beta Docs](https://docs.nvidia.com/cuopt/user-guide/latest/cuopt-server/milp.html) (if available)

### Conclusion

The current `cuopt_planner.py` implementation assumes a direct Python MILP API (similar to OR-Tools CP-SAT). This API **does not exist** in cuOpt — MILP requires the server/client architecture.

**Two viable paths forward:**
1. ✅ **Server API** (recommended) — full MILP support, production-ready
2. ⚠️ **VRP reformulation** (fallback) — direct Python API, but awkward fit

**Action:** Update implementation to use cuopt-server + cuopt-sh-client for MILP solving.
