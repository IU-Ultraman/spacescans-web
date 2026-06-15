# Sprint 1: Pre-flight Coverage Check + C3 Weights Cross-Task Cache — Design Spec

## Goal

Two independent, low-risk improvements to the spacescans-web v1
single-experiment integration. Both are foundational for the larger
Sprint 3 rewrite that will introduce 7 additional pipeline experiments
under a Variables-driven UI.

- **#2 Pre-flight coverage check.** Surface, in the wizard's Variables
  step, what fraction of the uploaded cohort is actually covered by each
  selected variable's time window and geographic region — before the
  user spends 4-7 minutes running a task only to discover most rows are
  null.
- **#5 C3 weights cross-task cache.** Avoid recomputing identical C3
  boundary-overlap weight tables across multiple tasks that share the
  same cohort + buffer parameters. The current per-task recompute wastes
  ~95% of wall-clock when the only difference between two tasks is the
  selected variable.

The two features are unrelated in code and can be implemented
independently.

## Scope

### In scope (Sprint 1)

- Backend endpoint `GET /api/tasks/{task_id}/coverage?variables=<csv>`
  returning per-variable coverage statistics over the uploaded cohort.
- Variable metadata JSON file (`backend/data/variable_metadata.json`)
  encoding each known variable's coverage time window, geographic
  region, and source experiment.
- Frontend `VariableCoveragePanel` component rendering coverage stats
  inline below each selected variable in the Variables step.
- Backend C3 weights cache at `backend/data/c3_cache/` keyed on
  `(sha256(input.parquet), boundary, buffer_m, raster_res_m)`. Hit →
  copy cached parquet to `task_dir/output/<step>.parquet` and skip the
  spacescans subprocess. Miss → run normally, then write the result
  back to the cache. Sidecar `.meta.json` files record wall-clock,
  size, and timestamps for ops.
- Unit + integration tests covering coverage computation, cache hit /
  miss / corruption / write-failure paths, and an end-to-end cache hit
  on the existing 5-patient Leon FL fixture.

### Out of scope (deferred)

- LRU or size-bound cache eviction. v1 expects manual cleanup when the
  disk fills up. Sprint 3 will revisit if the cache footprint becomes
  noticeable.
- Hit-rate metrics or cache observability beyond the per-entry
  `.meta.json` sidecar.
- C4 caching. The combinatorial input space (cohort × variable × year
  range) makes the hit-rate too low to justify the complexity.
- Remote / shared cache (S3, etc.). Pure local-dev v1 stays single
  machine.
- Boundary-precise region check via shapefile lookup. v1 uses a CONUS
  bounding box (longitude ∈ [-125, -66], latitude ∈ [24, 50]). Sprint 3
  may upgrade to per-variable shapefile-aware coverage.
- Schema versioning of `variable_metadata.json`. v1 freezes the shape;
  Sprint 3 introduces a version field when adding 7 new entries.
- Multi-tenancy considerations. The cache is server-wide and shared
  across users. Acceptable per v1 single-user-machine model.

## Architecture

```text
┌───────────────────────── Sprint 1 ──────────────────────────────┐
│                                                                 │
│  #2 PRE-FLIGHT                                                  │
│  ─────────────                                                  │
│   Variables step UI ─── debounced (300 ms) ───┐                 │
│                                               │                 │
│                                               ▼                 │
│       GET /api/tasks/{id}/coverage?variables=ndi,walkability    │
│                          │                                      │
│                          ├─ load input.csv                      │
│                          ├─ load variable_metadata.json         │
│                          └─ for each selected var: compute      │
│                              { in_time, in_region, covered }    │
│                                                                 │
│       Response → render <VariableCoveragePanel>                 │
│                  per variable, colored by coverage_pct          │
│                                                                 │
│  #5 C3 CACHE                                                    │
│  ───────────                                                    │
│   bg_ndi_wi.run() — for each PipelineStep:                      │
│     if step.is_c3:                                              │
│       key = (sha256(input.parquet)[:8],                         │
│              boundary, buffer_m, raster_res_m)                  │
│       cached = c3_cache/<key>.parquet                           │
│       if cached.exists() and valid:                             │
│           copy → task_dir/output/<step>.parquet                 │
│           skip subprocess; log "cache hit"                      │
│       else:                                                     │
│           run subprocess; if ok, copy → cache; write .meta.json │
└─────────────────────────────────────────────────────────────────┘
```

### Architectural choices and rationale

- **Independent `/coverage` endpoint, not folded into `/tasks/{id}`.**
  Sprint 3 will reuse coverage data for multi-variable selection across
  7 experiments. Keeping it on its own endpoint avoids enlarging the
  task detail payload.
- **`variable_metadata.json` as the single source of truth.** Lives in
  `backend/data/` (kept under git via `.gitignore` audit; if the file
  needs to be git-tracked, it can be moved to `backend/app/`). Sprint 3
  expands it from 2 to 9+ entries without code changes.
- **Cache key includes only the four semantically-load-bearing
  parameters.** Pipeline output is deterministic in `(input cohort,
  boundary file, buffer_m, raster_res_m)`. No need to hash the rendered
  YAML or pipeline version — those are derivative of those four.
- **SHA256 of `input.parquet`, not `input.csv`.** Hashing happens after
  `csv_to_parquet`, so we hash the exact bytes the pipeline reads. Avoids
  a class of edge cases where CSV whitespace / line endings differ but
  the parquet equivalent is identical.
- **`shutil.copy` not symlink.** Cache misses fall back to fresh pipeline
  runs; symlinks would couple cache lifetime to task lifetime. The cost
  is 6 MB / cache entry duplicated; in practice the cache is small.
- **No LRU yet.** This is local-dev v1. The C3 outputs are bounded:
  six-figure-MB territory, not gigabytes. Manual `rm -rf c3_cache/`
  during development is acceptable. Sprint 3 reassesses when the cache
  serves a multi-day workflow.

## Data Flow

### #2 Pre-flight coverage

```text
1. User uploads input.csv → save_upload writes input.csv to task_dir
2. User picks Variables in wizard step 3
3. Frontend (variables-step.tsx) debounces toggle events (300 ms)
4. On change, calls GET /api/tasks/{id}/coverage?variables=ndi,walkability
5. Backend:
   - _verify_ownership(task_id, user)
   - Parse variables CSV → list[str]
   - Load input.csv as pandas DataFrame (cached in proc memory 30s)
   - Load variable_metadata.json
   - For each variable:
     - in_time = (df.startDate ≤ end) & (df.endDate ≥ start)
     - in_region = lon/lat in CONUS box (for CONUS variables)
     - covered = in_time & in_region
     - emit { coverage_years, patients_in_time_window,
              patients_in_region, patients_covered, coverage_pct, warnings }
6. Frontend renders one VariableCoveragePanel per variable:
   - ≥95% covered → green, "X% of your cohort covered"
   - 60–95%       → yellow, includes warning lines
   - <60%         → red, includes specific recommendation
7. Run button is NOT disabled — informational only.
```

### #5 C3 cache

```text
1. bg_ndi_wi.run() spawns; writes status="running"
2. csv_to_parquet(input.csv → input.parquet)
3. Loop over PipelineSteps from plan(config):
   a. render_yaml(step) → task_dir/pipeline_configs/<step>.yaml
   b. if step.is_c3:
      key = _cache_key(input.parquet, step, config)
      cached_path = DATA_DIR/c3_cache/<key>.parquet
      if cached_path.exists():
        validate(cached_path)  # > 100 bytes; parquet read header
        if valid:
          shutil.copy(cached_path, task_dir/output/<step>.parquet)
          _append_log("cache hit ...")
          _write_status(progress=(idx+1)/total, message=f"Reused cached {step.name}")
          continue  # skip subprocess entirely
   c. run_pipeline_step(yaml_path, task_dir, step.name, on_progress=...)
   d. if rc == 0 and step.is_c3:
      shutil.copy(out_parquet, cached_path)
      write_sidecar(cached_path.with_suffix(".meta.json"))
   e. on_progress maps frac → status.progress = (idx + frac) / total
4. merge_results → output/result.csv
5. _write_status(status="finished")
```

## Backend Modules

### New files

| Path | Role |
|---|---|
| `backend/data/variable_metadata.json` | Source-of-truth catalog mapping variable key → coverage time, region, source experiment. v1 contains `ndi`, `walkability`. |
| `backend/data/c3_cache/` | Cache directory created on first cache miss. Holds `<key>.parquet` + `<key>.meta.json` pairs. Gitignored. |

### Modified files

**`backend/app/routers/tasks.py`** — add `GET /{task_id}/coverage`:

```python
@router.get("/{task_id}/coverage")
def get_coverage(
    task_id: str,
    variables: str = Query(..., description="Comma-separated variable keys"),
    user: dict = Depends(get_current_user),
):
    _verify_ownership(task_id, user)
    var_keys = [v.strip() for v in variables.split(",") if v.strip()]
    if not var_keys:
        raise HTTPException(400, "variables query is required")
    try:
        return task_manager.compute_coverage(task_id, var_keys)
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))
    except KeyError as e:
        raise HTTPException(400, f"unknown variable(s): {e.args[0]}")
```

**`backend/app/task_manager.py`** — add `compute_coverage` and friends:

```python
def compute_coverage(task_id: str, variable_keys: list[str]) -> dict:
    """Compute per-variable cohort coverage statistics."""
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    input_csv = task_dir / "input.csv"
    if not input_csv.exists():
        raise FileNotFoundError("No input uploaded")

    metadata = _load_variable_metadata()
    unknown = [v for v in variable_keys if v not in metadata]
    if unknown:
        raise KeyError(", ".join(unknown))

    df = pd.read_csv(input_csv,
                     parse_dates=["startDate", "endDate"],
                     dtype={"state_fips": "string"})
    n_total = len(df)

    out_vars = {}
    for var in variable_keys:
        m = metadata[var]
        y0, y1 = m["coverage_years"]
        cov_start = pd.Timestamp(f"{y0}-01-01")
        cov_end = pd.Timestamp(f"{y1}-12-31")
        in_time = (df["startDate"] <= cov_end) & (df["endDate"] >= cov_start)
        if m.get("coverage_region") == "CONUS":
            in_region = (
                df["longitude"].between(-125, -66) &
                df["latitude"].between(24, 50)
            )
        else:
            in_region = pd.Series(True, index=df.index)
        covered = in_time & in_region
        warnings = []
        if covered.sum() < n_total * 0.95:
            outside = ((~in_time).sum() / n_total) * 100
            if outside > 5:
                warnings.append(
                    f"{outside:.0f}% of patients have episodes entirely outside "
                    f"{y0}-{y1}"
                )
        out_vars[var] = {
            "coverage_years": [y0, y1],
            "patients_in_time_window": int(in_time.sum()),
            "patients_in_region": int(in_region.sum()),
            "patients_covered": int(covered.sum()),
            "coverage_pct": round(100 * covered.sum() / n_total, 2),
            "warnings": warnings,
        }
    return {"row_count": n_total, "variables": out_vars}


_VARIABLE_METADATA_CACHE: dict | None = None
_VARIABLE_METADATA_MTIME: float | None = None

def _load_variable_metadata() -> dict:
    """Cached metadata load with mtime-based invalidation."""
    global _VARIABLE_METADATA_CACHE, _VARIABLE_METADATA_MTIME
    path = app.config.settings.DATA_DIR / "variable_metadata.json"
    mtime = path.stat().st_mtime
    if _VARIABLE_METADATA_CACHE is None or mtime != _VARIABLE_METADATA_MTIME:
        _VARIABLE_METADATA_CACHE = json.loads(path.read_text())
        _VARIABLE_METADATA_MTIME = mtime
    return _VARIABLE_METADATA_CACHE
```

**`backend/app/experiments/bg_ndi_wi.py`** — extend `run()` with cache logic:

```python
def _hash_input_parquet(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_key(input_parquet: Path, step: PipelineStep, user_config: dict) -> str:
    sha = _hash_input_parquet(input_parquet)
    boundary = "BG"
    buf = user_config["buffer"]["size"]
    raster = user_config["buffer"]["raster_res_m"]
    return f"{sha[:8]}__{boundary}__b{buf}m__r{raster}m"


def _is_valid_cached_parquet(path: Path) -> bool:
    """Quick sanity check before trusting a cached file."""
    if not path.exists():
        return False
    if path.stat().st_size < 100:
        return False
    try:
        pd.read_parquet(path, columns=[]).shape  # cheap header read
        return True
    except Exception:
        return False


# In the steps loop in run():
#     if step.is_c3:
#         cache_key = _cache_key(...)
#         cache_path = DATA_DIR / "c3_cache" / f"{cache_key}.parquet"
#         if _is_valid_cached_parquet(cache_path):
#             shutil.copy(cache_path, out_parquet)
#             _append_log("info", "runner", f"cache hit: {cache_key}")
#             continue
#     ... (existing run_pipeline_step)
#     if step.is_c3 and rc == 0:
#         cache_path.parent.mkdir(parents=True, exist_ok=True)
#         try:
#             shutil.copy(out_parquet, cache_path)
#             _write_cache_meta(cache_path.with_suffix(".meta.json"), ...)
#         except OSError as exc:
#             _append_log("warning", "runner", f"cache write failed: {exc}")
```

### Configuration changes

`backend/app/config.py` — add one new setting:

```python
C3_CACHE_DIR: Path = DATA_DIR / "c3_cache"
```

Validate it's writable in `validate_pipeline_settings` (silently create if absent).

`backend/.gitignore` — add:

```
data/c3_cache/
```

## Frontend Changes

### New file

**`frontend/src/components/wizard/variable-coverage-panel.tsx`** (~70 LOC):

```tsx
"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CheckCircle2, AlertTriangle, AlertCircle } from "lucide-react";

interface VarCoverage {
  coverage_years: [number, number];
  patients_in_time_window: number;
  patients_in_region: number;
  patients_covered: number;
  coverage_pct: number;
  warnings: string[];
}

interface VariableCoveragePanelProps {
  taskId: string;
  variableKey: string;
  rowCount: number;
}

export function VariableCoveragePanel({
  taskId, variableKey, rowCount
}: VariableCoveragePanelProps) {
  const [data, setData] = useState<VarCoverage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getCoverage(taskId, [variableKey])
      .then((resp) => {
        if (!cancelled) setData(resp.variables[variableKey]);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => { cancelled = true; };
  }, [taskId, variableKey]);

  if (error) return null;  // fail silently — no panel
  if (!data) return <div className="text-xs text-muted-foreground">Checking coverage...</div>;

  const tone =
    data.coverage_pct >= 95 ? "ok" :
    data.coverage_pct >= 60 ? "warn" : "bad";
  const Icon = tone === "ok" ? CheckCircle2 : tone === "warn" ? AlertTriangle : AlertCircle;

  return (
    <div className={cn(
      "rounded-md border p-2 text-xs mt-2",
      tone === "ok"   && "border-emerald-500/30 bg-emerald-500/5 text-emerald-700",
      tone === "warn" && "border-amber-500/30 bg-amber-500/5 text-amber-700",
      tone === "bad"  && "border-red-500/30 bg-red-500/5 text-red-700",
    )}>
      <div className="flex items-center gap-1.5 font-medium">
        <Icon className="size-3.5" />
        {data.coverage_pct}% of your cohort covered
      </div>
      <div className="text-muted-foreground mt-0.5">
        {data.patients_covered.toLocaleString()} / {rowCount.toLocaleString()}{" "}
        within {data.coverage_years[0]}-{data.coverage_years[1]} +
        coverage region
      </div>
      {data.warnings.map((w, i) => (
        <div key={i} className="mt-1">{w}</div>
      ))}
    </div>
  );
}
```

### Modified files

**`frontend/src/lib/api.ts`** — add `getCoverage`:

```ts
getCoverage: (taskId: string, variables: string[]) =>
  fetchJson<{ row_count: number; variables: Record<string, VarCoverage> }>(
    `${API_BASE}/api/tasks/${taskId}/coverage?variables=${variables.join(",")}`,
    { headers: { ...authHeader() } },
  ),
```

**`frontend/src/components/wizard/variables-step.tsx`** — render
`VariableCoveragePanel` below each checked variable. Pass `taskId`
(already known from the parent page) and `rowCount` (from `dataSummary`).

Debouncing: variable checkbox toggles fire `onChange` immediately
(reflects in UI), but `VariableCoveragePanel`'s `useEffect` runs on
component mount/unmount, so the panel only fetches when newly checked.
A separate fetch is issued per panel (small, parallel; backend caches
input.csv read for 30s so cost is minimal).

## Error Handling

### Pre-flight failure matrix

| # | Failure | Detection | UX |
|---|---|---|---|
| 1 | input.csv missing (task uploaded then deleted) | FileNotFoundError in `compute_coverage` | 400 `"No input uploaded"`; panel hidden |
| 2 | input.csv missing required columns | pandas KeyError on startDate etc. | 500 traceback; panel shows `"Coverage check unavailable"`; Run unblocked |
| 3 | `variable_metadata.json` missing or malformed | json.JSONDecodeError on startup load | 500 if endpoint called; **task_manager startup logs a warning but does not crash** |
| 4 | Unknown variable key | KeyError caught in router | 400 `"unknown variable(s): pm25"` |
| 5 | User spam-toggles | Frontend debounces 300 ms; in-proc cache 30 s for (task,vars) | Single fetch per real change |
| 6 | Very large input.csv | pandas read 1-2 s for 100k rows | Acceptable; Sprint 3 may add streaming for 1M+ rows |

### C3 cache failure matrix

| # | Failure | Detection | Behaviour |
|---|---|---|---|
| 1 | Cache dir absent | `mkdir(parents=True, exist_ok=True)` | Auto-created on first miss |
| 2 | Cached parquet < 100 bytes (partial write) | `_is_valid_cached_parquet` size check | Treated as miss; fresh run + rewrite |
| 3 | Cached parquet header unreadable | `pd.read_parquet(columns=[])` raises | Same as #2 |
| 4 | Disk full on cache write | `shutil.copy` raises OSError | Caught; warning log; task completes normally without caching |
| 5 | User deletes `c3_cache/` mid-task | task's `output/<step>.parquet` already copied before delete | Running task unaffected; next task misses → rebuild |
| 6 | Hash computation fails (input.parquet missing) | FileNotFoundError | Caught; warning log; task falls back to no-cache mode |
| 7 | Two concurrent tasks miss the same key | shutil.copy under index-lock; both write byte-identical content (deterministic pipeline) | No conflict; last writer wins; idempotent |
| 8 | SHA256 of 11 MB takes ~200 ms | Pre-computed once in csv_to_parquet, cached on Path object | Future optimization; v1 just hashes per cache check |

### Security

- `/coverage` reuses existing `_verify_ownership(task_id, user)` —
  no new auth surface.
- `variables` query string parsed safely: split on `,`, trim, drop
  empties. Variable keys are matched against the `metadata.json` keys
  — no SQL or filesystem injection.
- C3 cache is server-wide and shared across users (acceptable for
  single-tenant v1). The cache file names expose the first 8 hex chars
  of the SHA256, which is a low-grade information leak (an attacker who
  already has cohort A's data could try to discover whether A has been
  uploaded). Threat model declares this acceptable in v1.

## Testing

### Unit tests (`backend/tests/test_coverage.py` — new file)

| Test | Asserts |
|---|---|
| `test_coverage_endpoint_basic` | Upload + GET /coverage?variables=ndi returns row_count + variables.ndi.coverage_pct ≥ 0 |
| `test_coverage_endpoint_unknown_variable` | `?variables=pm25` → 400 with "unknown variable" |
| `test_coverage_endpoint_no_input` | task without upload → 400 |
| `test_coverage_endpoint_multi_variables` | `?variables=ndi,walkability` → both keys in response |
| `test_coverage_time_window_filter` | 10 patients: 5 in 2010 + 5 in 2017; NDI (2012-2022) → patients_in_time_window == 5 |
| `test_coverage_region_filter_conus` | 1 patient at lon=-149 (AK) + 9 CONUS; patients_in_region == 9 |
| `test_coverage_ownership_403` | User B querying A's task → 403 |

### Unit tests (`backend/tests/test_bg_ndi_wi.py` — append)

| Test | Asserts |
|---|---|
| `test_cache_key_stable` | Same input + config → same key |
| `test_cache_key_input_byte_change` | Modify input.parquet 1 byte → different key |
| `test_cache_key_buffer_change` | buffer_m 270 → 500 → different key |
| `test_cache_miss_creates_artifact` | After run, c3_cache/ contains `<key>.parquet` + `.meta.json` |
| `test_cache_hit_skips_subprocess` | Second run: subprocess.Popen called 0 times for C3 step (monkeypatch counter) |
| `test_cache_corrupted_falls_through` | Pre-write 10-byte fake → detected → fresh run + overwrite |
| `test_cache_write_failure_does_not_break_task` | Mock shutil.copy → OSError → status="finished" |

### Integration tests (`backend/tests/test_bg_ndi_wi_integration.py` — append)

| Test | Asserts |
|---|---|
| `test_e2e_cache_second_run_faster` | Two sequential runs on the same fixture: second `wall_clock < 0.1 × first` |

### Manual smoke (extend `backend/tests/manual_e2e.md`)

- After picking NDI, see green panel: "NDI: 99.x% of your cohort covered"
- After picking Walkability (2016-2021), expect yellow if cohort straddles
  that window
- Run task twice in a row with same settings; second task should finish
  in < 30 s (mostly merge_results + C4)

## Implementation Estimate

| Component | New LOC | Modified LOC |
|---|---:|---:|
| `variable_metadata.json` (2 entries) | ~30 | — |
| `compute_coverage` + helpers | ~80 | — |
| `/coverage` router | — | ~20 |
| `_hash_input_parquet` + `_cache_key` + `_is_valid_cached_parquet` | ~50 | — |
| Cache check/write blocks in `run()` | — | ~40 |
| `VariableCoveragePanel` component | ~70 | — |
| `variables-step.tsx` wiring | — | ~30 |
| `api.ts` `getCoverage` | ~20 | — |
| Backend unit tests | ~250 | — |
| Integration test | ~40 | — |
| **Total** | **~540** | **~90** |

Wall-clock estimate: **2-3 focused work days** for one developer.

## Open Questions for Sprint 2 / 3

- The CONUS bounding box is a coarse approximation. NDI / Walkability
  source rasters are sparse outside CONUS but include AK + HI partially.
  Sprint 3 may upgrade to per-variable shapefile coverage.
- Sprint 3 introduces 7 new variables; `variable_metadata.json` will
  grow. Consider a schema version field at that point.
- C3 cache size is unbounded in Sprint 1. If a developer accumulates
  hundreds of cohort variants, the directory may need pruning. Sprint 3
  reassesses whether to ship LRU.
- The 30-second in-process cache of `input.csv` reads is naive. Sprint
  3 may switch to a per-task LRU on disk to handle multiple workers.

These are noted but not blocking Sprint 1.
