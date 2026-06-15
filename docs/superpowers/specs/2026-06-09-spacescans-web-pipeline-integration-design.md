# spacescans-web ↔ spacescans-pipeline Integration — Design Spec

## Goal

Replace the placeholder `mock_cli/` in `spacescans-web/backend/` with a real
integration that runs the `spacescans-pipeline` CLI on user-uploaded CSV
cohorts. The v1 deliverable is a complete walk-through of **one** README
experiment — *#4: BG NDI + EPA Walkability Index* — covering upload →
variable selection → 3-step C3/C4 pipeline run → merged result download.

Existing infrastructure (FastAPI single-process, SQLite auth, file-based
task contract) is preserved; pipeline invocation slots in as a new
experiment handler beside the retained mock.

## Scope

### In scope (v1)

- Single experiment: **BG NDI + Walkability** (`configs/c3/bg_us_demo.yaml` +
  `configs/c4/bg_ndi_demo.yaml` + `configs/c4/bg_wi_demo.yaml`).
- Single-machine local deployment: web app, conda env `spacescans`, and the
  ~220 GB `data_full/` tree all on the same host.
- Synchronous, blocking subprocess invocation of the `spacescans` CLI from
  the FastAPI process; one concurrent task at a time enforced via file
  lock.
- CSV → parquet conversion with explicit FIPS string dtype preservation
  and date parsing (no column rename — the pipeline's existing
  `demo_conus` adapter handles renames at runtime).
- Per-step status surfacing through the existing `status.json` / `logs.jsonl`
  contract, extended with `current_step` and `total_steps`.
- Result merge into a single `output/result.csv` with one row per uploaded
  patient episode.

### Out of scope (deferred to v2+)

- Other 7 README experiments (TIGER proximity, NHD, VNL, TEMIS, FARA, Noise,
  County/ZCTA5/CBP). Each becomes its own experiment handler.
- Ontology-driven generic variable mapping. Existing
  `frontend/public/ontology/` files stay in place but the wizard's variables
  step bypasses them for v1.
- Multi-tenant concurrent execution. Global single-task lock is sufficient
  for the local-dev v1 deployment.
- Cross-task C3 weights caching. Each task recomputes C3 weights, even when
  the boundary × buffer × cohort would be reusable.
- Auto-retry on failure. Failed tasks can be deleted and recreated; no
  retry endpoint.
- Remote / cluster pipeline execution (cloud, HPC, GCP Batch).
- Rectangular / hexagonal buffer shapes (pipeline only supports circular).

## Architecture

```text
┌────────────────────────────────────────────────────────────────┐
│                        same dev machine                        │
│                                                                │
│  ┌──────────────┐   HTTP    ┌──────────────────────────────┐   │
│  │  Next.js     │ ───────→  │   FastAPI                    │   │
│  │  :3000       │           │   :8000                      │   │
│  │              │           │                              │   │
│  │  4-step      │           │  routers/tasks.py            │   │
│  │  wizard      │           │  task_manager.py             │   │
│  │              │           │  experiments/bg_ndi_wi.py ★  │   │
│  └──────────────┘           └─────────┬────────────────────┘   │
│                                       │ subprocess.Popen       │
│                                       │ (3 sequential calls    │
│                                       │  + dispatch by         │
│                                       │  config.experiment)    │
│                                       ▼                        │
│                            ┌─────────────────────────┐         │
│                            │  spacescans run         │         │
│                            │  (conda env spacescans) │         │
│                            └────┬────────────┬───────┘         │
│                                 │ reads      │ writes          │
│                                 ▼            ▼                 │
│                         /Users/.../          backend/data/     │
│                         data_full/           tasks/task-xxx/   │
│                         (220 GB rw mount)    output/           │
└────────────────────────────────────────────────────────────────┘
```

### Architectural choices and rationale

- **Single FastAPI process, blocking subprocess.** Avoids the operational
  cost of Celery / Redis / RQ. A `spacescans run` invocation is a 1–5 min
  CPU-bound task, not a long job needing distributed queueing. UI polls
  `status.json` for progress.
- **One task at a time via flock.** `backend/data/.run_lock` provides
  mutual exclusion. Concurrent `start` returns HTTP 409. Trivial to lift
  later when usage justifies it.
- **Subprocess, not import.** Web backend never imports `spacescans-pipeline`.
  Pipeline runs inside its own conda env via subprocess. Decouples env
  failures and dependency conflicts between the two repos.
- **Mock_cli retained as fallback.** `config.json:experiment` field
  dispatches between `bg_ndi_wi` and `mock` handlers. Mock stays useful for
  automated tests and dev iteration without `data_full/`.
- **Path configuration via env vars.** `SPACESCANS_DATA_DIR`,
  `SPACESCANS_PIPELINE_CLI`, `SPACESCANS_CONFIG_TEMPLATES_DIR` settings in
  `app/config.py`. Validated on FastAPI startup; missing paths fail-fast.

## Data Flow and File Contract

### Task directory layout

```text
backend/data/tasks/task-<uuid>/
├── meta.json                     backend writes — user_id, task_name, experiment, data_summary
├── input.csv                     uploaded — pid, startDate, endDate, longitude, latitude [, GEOIDs]
├── input.parquet                 ★ runner writes — dtype-corrected upload (no rename; demo_conus adapter handles it at runtime)
├── config.json                   backend writes — experiment, variables, buffer
├── pipeline_configs/             ★ runner writes — task-local YAMLs derived from templates
│   ├── c3_bg.yaml
│   ├── c4_ndi.yaml               (only if NDI selected)
│   └── c4_wi.yaml                (only if Walkability selected)
├── status.json                   runner writes — status/progress/message/pid/current_step/total_steps
├── logs.jsonl                    runner writes — append-only, with {ts, level, msg, source}
└── output/
    ├── c3_weights.parquet        spacescans writes — patient-buffer × BG-GEOID weight table
    ├── ndi.parquet               spacescans writes — patient-episode × NDI long table
    ├── walkability.parquet       spacescans writes — patient-episode × Walkability long table
    └── result.csv                ★ runner writes — outer-joined wide table for download
```

### Extended status.json

```json
{
  "status": "running" | "finished" | "error" | "cancelled",
  "progress": 0.42,
  "message": "Computing BG weights (2/3)",
  "started_at": "2026-06-09T16:00:00Z",
  "pid": 12345,
  "current_step": "c3_bg",
  "total_steps": 3
}
```

Global `progress` is computed as
`(completed_steps + current_step_progress) / total_steps`. Per-step
progress is parsed from spacescans stdout (`[overlap_fast] tile X/Y`
lines for C3; C4 steps are fast enough to count as binary 0/1).

### logs.jsonl source field

Each line includes `source` for filtering / colouring in the UI:

- `"runner"` — `bg_ndi_wi.py` orchestration lines
- `"c3_bg"`, `"c4_ndi"`, `"c4_wi"` — spacescans subprocess stdout, with INFO
  noise filtered out, retaining `[overlap_fast]` / `[overlap]` progress
  lines and errors

### Web → pipeline field mapping

| Web config.json | Pipeline YAML | Where injected |
|---|---|---|
| `buffer.size` | `buffer.buffer_m` | c3 + c4 |
| `buffer.raster_res_m` | `buffer.raster_res_m` | c3 only |
| `buffer.shape` (locked `"circle"`) | (n/a — pipeline only circle) | validation only |
| `variables: ["ndi", "walkability"]` | which c4 YAMLs generated | step planning |
| (implicit) `input.parquet` path | `buffer.patient_file` | all YAMLs |
| (implicit) `task_dir/output/...` | `output.path` | each YAML |

## Backend Modules

### New files

**`backend/app/experiments/__init__.py`** — empty package marker.

**`backend/app/experiments/bg_ndi_wi.py`** (~250 LOC) — single experiment
orchestrator. Five small functions:

| Function | Responsibility |
|---|---|
| `run(task_dir, config) -> int` | Main entry. Validate, convert, render, run, merge. Returns process exit code. |
| `plan(config) -> list[PipelineStep]` | Compute step list from selected variables. C3 always first, one C4 per variable. |
| `csv_to_parquet(src, dst)` | Read CSV with explicit FIPS=string dtype. Parse dates. Write parquet (no column rename — `demo_conus` adapter handles renaming at runtime). |
| `render_yaml(step, task_dir, config) -> Path` | Read template YAML, inject 5 keys, write to `pipeline_configs/<step>.yaml`. |
| `run_pipeline_step(yaml_path, task_dir, step_name) -> int` | `subprocess.Popen` with new process session; capture stdout line-by-line; parse progress; tee to logs.jsonl. |
| `merge_results(task_dir, variables) -> Path` | pandas outer-join of per-variable parquets on `(PATID, startDate, endDate)`. Write `output/result.csv`. |

### Modified files

**`backend/app/config.py`** — four new settings:

```python
SPACESCANS_DATA_DIR: Path                  # e.g. /Users/.../data_full
SPACESCANS_PIPELINE_PYTHON: Path           # conda env python
SPACESCANS_PIPELINE_CLI: Path              # conda env spacescans entrypoint
SPACESCANS_CONFIG_TEMPLATES_DIR: Path      # /Users/.../configs
```

Read from `.env`. App startup validates existence; missing paths raise
`RuntimeError` before serving requests.

**`backend/app/task_manager.py`** — two changes:

1. `save_config(task_id, cfg)` accepts new `experiment` field (default
   `"bg_ndi_wi"`), persists into config.json.
2. `start_task(task_id)` dispatches subprocess based on `config.experiment`:
   ```python
   if cfg.get("experiment") == "bg_ndi_wi":
       cmd = [PIPELINE_PYTHON, "-m", "app.experiments.bg_ndi_wi", "run", str(task_dir)]
   else:
       cmd = [sys.executable, "-m", "mock_cli.cli", "run", str(task_dir)]
   ```
   Acquires `.run_lock` via `fcntl.flock(LOCK_EX | LOCK_NB)` first.

**`backend/app/routers/tasks.py`** — `/{task_id}/results` keeps returning
`output/result.csv`; no API surface change.

**`backend/requirements.txt`** — add:

```text
pyyaml>=6.0
pyarrow>=15
pandas>=2.0
```

(pyarrow and pandas may already be present transitively; listed explicitly.)

### Unmodified

`auth.py`, `database.py`, `routers/auth.py`, `mock_cli/` — pipeline
integration does not touch authentication, DB, or the mock path.

## Frontend Changes

### Wizard step diff

```text
Existing (4 steps):           v1 changes:
1. Upload Data                1. Upload Data            (unchanged — CSV schema doc landed earlier)
2. Buffer Settings            2. Buffer Settings        ★ lock shape=circle, add raster_res_m input
3. Variables (ontology)       3. Variables             ★ replace ontology browse with 2 checkboxes
4. Review & Run               4. Review & Run          ★ progress panel shows per-step status
```

### Files modified

**`src/components/wizard/buffer-step.tsx`**
- shape selector: three options shown (circle, square, hexagon) but only
  circle clickable. Tooltips on disabled options: "Not supported by
  spacescans-pipeline yet."
- Add `raster_res_m` number input, default 25, range 5–100.
- Header note: "v1 supports circular buffers only. Other shapes will be
  added when the pipeline supports them."

**`src/components/wizard/variables-step.tsx`** — v1 simplification
- Ontology browse tree hidden behind
  `process.env.NEXT_PUBLIC_USE_ONTOLOGY === "true"` flag.
- Replaced with a Card titled "Experiment: BG NDI + Walkability (v1)"
  containing two checkboxes:
  - Neighborhood Deprivation Index (NDI) — Singh's BG composite, 2012–2022.
  - EPA Walkability Index — BG-level, 2016–2021.
- At least one must be checked to advance.

**`src/components/wizard/wizard-layout.tsx`** — STEPS description
copy-edit only:

```diff
- { label: "Variables", description: "Ontology selection" },
+ { label: "Variables", description: "BG NDI / Walkability" },
```

**`src/components/wizard/review-step.tsx`** — multi-step progress display
- Overall progress bar (existing) retained.
- Add step list below:
  ```
  Step 1/3   ✅ C3: Compute BG weights for buffers          [2:14]
  Step 2/3   ⏳ C4: NDI exposure (45%)                       [running]
  Step 3/3   ⏸ C4: EPA Walkability                           [pending]
  ```
- Data from `status.json.current_step` + `total_steps`, with per-step state
  derived from logs.jsonl by `source` field.
- Results section: primary download is `result.csv`. An expandable
  "Advanced: pipeline intermediates" panel lists `c3_weights.parquet`,
  `ndi.parquet`, `walkability.parquet`.

**`src/lib/api.ts`** — `saveConfig` body adds `experiment: "bg_ndi_wi"`.

### Unmodified

- Login / signup / dashboard task list — pipeline integration is transparent.
- `frontend/public/ontology/` — preserved as-is for v2 generic mapping.

## YAML Template Rendering

### Template → target mapping

| Step | Template | Target | Condition |
|---|---|---|---|
| `c3_bg` | `configs/c3/bg_us_demo.yaml` | `task_dir/pipeline_configs/c3_bg.yaml` | always |
| `c4_ndi` | `configs/c4/bg_ndi_demo.yaml` | `task_dir/pipeline_configs/c4_ndi.yaml` | `"ndi" in variables` |
| `c4_wi` | `configs/c4/bg_wi_demo.yaml` | `task_dir/pipeline_configs/c4_wi.yaml` | `"walkability" in variables` |

### Injection points

Each template has exactly five keys overwritten; everything else (source.file,
exposure.file, time.years, engine.backend, …) is preserved verbatim:

| YAML key | Template value (typical) | Injected value |
|---|---|---|
| `name` | `bg_us_demo` | `<original>_task_<task_id_short>` |
| `buffer.patient_file` | `data_full/demo_patients_conus_fast_100000.parquet` | `<task_dir>/input.parquet` |
| `buffer.patient_adapter` | `demo_conus` | `demo_conus` (preserved — see schema note below) |
| `buffer.buffer_m` | `270` | user-selected size |
| `buffer.raster_res_m` (c3 only) | `25` | user-selected raster res |
| `output.path` | `output/python_v2/270m/BG_US/C3/.../...parquet` | `<task_dir>/output/<step_name>.parquet` |

### Pipeline patient-schema alignment

The web app's upload schema (`pid, startDate, endDate, longitude, latitude,
[state_fips, county_fips, tract_geoid, bg_geoid]`) was deliberately chosen
to match what the pipeline's `demo_conus` patient adapter expects as input.
Setting `patient_adapter: demo_conus` in the rendered YAML therefore lets
the pipeline reuse its existing rename + synthetic-geoid logic verbatim
(`src/spacescans/linkage/helpers.py:_adapt_demo_conus`).

Notes on the adapter's behaviour:

- Renames `pid→PATID, startDate→start, endDate→end, longitude→long,
  latitude→lat` at runtime.
- Synthesizes `geoid = range(len(df))` rather than using `bg_geoid`. This
  is required because the pipeline's `grid_weights` validation enforces
  a 1:1 patient↔geoid mapping; reusing `bg_geoid` would collide multiple
  patients onto the same block group.
- Optional FIPS columns (`state_fips`, `county_fips`, etc.) are passed
  through but ignored by the boundary_overlap_fast linkage path used
  by this experiment.

`csv_to_parquet` therefore does **not** rename columns. Its job is
narrower: enforce FIPS string dtypes (preserve leading zeros), parse
date columns, and write the parquet so subsequent pipeline reads do
zero coercion.

### Rendering algorithm (pseudocode)

```python
def render_yaml(step, task_dir, user_config):
    template_path = SPACESCANS_CONFIG_TEMPLATES_DIR / step.template_relpath
    cfg = yaml.safe_load(template_path.read_text())

    cfg["name"] = f"{cfg['name']}_task_{task_dir.name[-8:]}"
    cfg["buffer"]["patient_file"] = str(task_dir / "input.parquet")
    # patient_adapter "demo_conus" is preserved — our upload schema mirrors
    # the demo cohort's, so the adapter's rename + synthetic-geoid logic
    # applies as-is.
    cfg["buffer"]["buffer_m"] = user_config["buffer"]["size"]
    if step.is_c3:
        cfg["buffer"]["raster_res_m"] = user_config["buffer"]["raster_res_m"]
    cfg["output"]["path"] = str(task_dir / "output" / f"{step.name}.parquet")

    out = task_dir / "pipeline_configs" / f"{step.name}.yaml"
    out.parent.mkdir(exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out
```

## Error Handling

### Failure matrix

| # | Failure | Detection | UX |
|---|---|---|---|
| 1 | CSV missing required columns / bad FIPS dtype / non-ISO dates | `save_upload` validation | 400 with column list (already implemented) |
| 2 | env config invalid (`SPACESCANS_DATA_DIR` missing, CLI not found) | startup validation | App fails to start; 503 on `/api/health` |
| 3 | Another task running | `flock(LOCK_NB)` fails | 409 with running task ID |
| 4 | `csv_to_parquet` failure (encoding / unparseable date / dtype) | runner top-level try | `status="error"`, traceback in logs |
| 5 | YAML render failure (missing template key, parse error) | runner | same as #4 |
| 6 | spacescans subprocess exit code != 0 | `Popen.wait()` returncode | `status="error"`, message names the step, last 50 stdout lines in logs |
| 7 | Subprocess hangs | watchdog with configurable per-step timeout (default 30 min) | SIGTERM → wait 5s → SIGKILL, `status="error: timeout"` |
| 8 | User clicks Stop | router calls `kill_task` → SIGTERM the process group | `status="cancelled"`, partial outputs preserved |
| 9 | Output parquet missing after pipeline reports success | pre-merge assert | `status="error: missing output"` |
| 10 | Merge produces many null rows (low match rate) | post-merge null-rate check | logs.jsonl warning, not error |
| 11 | Disk full | `OSError` catch | `status="error: disk full"` |
| 12 | task_dir deleted mid-run | runner self-check via mtime | early error |

### Critical decisions

**Process group management.** `subprocess.Popen(..., start_new_session=True)`
puts each pipeline step in its own session/group. Stop and timeout use
`os.killpg(pgid, SIGTERM)` so worker threads / forks (DuckDB,
exactextract) are also reaped.

**Partial-failure semantics.** If C3 succeeds but C4 NDI fails (or
Walkability fails after NDI succeeded), the task is marked `"error"` but
partial outputs are preserved (`c3_weights.parquet`, `ndi.parquet`, etc.).
The merged `result.csv` is **not** written, to avoid presenting incomplete
data as complete. logs.jsonl explicitly records which steps completed.

**No auto-retry in v1.** Pipeline failures are usually OOM / disk /
data-source issues; blind retry won't help. Users delete the task and
recreate it. A retry endpoint is deferred to v2.

### Fail-fast order in `start_task`

```
1. config.json fields present (experiment, variables, buffer)
2. variables ⊆ {"ndi", "walkability"}                            (v1 whitelist)
3. buffer.shape == "circle", buffer.size ∈ [50, 5000] meters
4. SPACESCANS_DATA_DIR exists AND key sources present
   (BG_FL/C3/tiger2010_bg10_states/, BG_NDI/C4/*.Rda, BG_WI/C4/*.Rda)
5. .run_lock acquired                                            (mutex)
6. Spawn runner subprocess
```

Steps 1–4 are synchronous; failure returns HTTP 400 from the `/start`
endpoint. Step 5 returns 409. Step 6 onward is the async lifecycle.

## Testing

### Pyramid

```
                       ┌─────────────────────┐
                       │  E2E (smoke)        │   1 — manual, not in CI
                       │  full wizard run    │
                       └─────────────────────┘
                  ┌─────────────────────────────┐
                  │  Integration               │   2–3
                  │  TestClient + real         │
                  │  experiment subprocess     │
                  └─────────────────────────────┘
            ┌───────────────────────────────────────┐
            │  Unit                                │   ~10
            │  csv_to_parquet, render_yaml, plan,  │
            │  merge_results, stdout parser, lock  │
            └───────────────────────────────────────┘
```

### Unit tests (`backend/tests/test_bg_ndi_wi.py`)

| Test | Asserts |
|---|---|
| `test_plan_with_both_variables` | Both variables → 3 steps in order c3_bg → c4_ndi → c4_wi |
| `test_plan_with_ndi_only` | NDI only → 2 steps, c4_wi skipped |
| `test_csv_to_parquet_preserves_fips` | Leading-zero `"06"` stays as string |
| `test_csv_to_parquet_parses_dates` | `startDate` / `endDate` columns become `datetime64`, malformed dates fail explicitly |
| `test_render_yaml_injects_patient_file` | Rendered `buffer.patient_file` equals `task_dir/input.parquet` |
| `test_render_yaml_preserves_source_file` | Template `source.file` unchanged after render |
| `test_render_yaml_c4_no_raster_res_m` | C4 templates without `raster_res_m` key render without error |
| `test_merge_results_outer_join` | 50 NDI rows + 80 Walkability rows → 100-row result.csv |
| `test_merge_results_warns_on_high_null` | Low match rate produces a warning log entry |
| `test_parse_overlap_fast_progress` | `[overlap_fast] tile 7460/14938 ( 49.9%)` → progress 0.499 |

### Integration tests (`backend/tests/test_bg_ndi_wi_integration.py`, marked `@pytest.mark.integration`)

Skipped automatically if `SPACESCANS_DATA_DIR` is unset or `spacescans` CLI
is absent — keeps CI green on machines without the 220 GB tree.

| Test | Asserts |
|---|---|
| `test_e2e_small_cohort` | 5-row CSV → full pipeline → result.csv has 5 rows × 2 variable columns, no all-null. Wall-clock < 60 s. |
| `test_lock_prevents_concurrent_start` | Second start while first runs returns 409 |
| `test_stop_kills_pipeline_subprocess` | Stop while C3 running → status `"cancelled"`, no `spacescans` processes in ps |

### Smoke test (manual, documented)

`backend/tests/manual_e2e.md` describes the full UI walk-through:

1. Start backend and frontend.
2. Sign up + log in.
3. Upload first 100 rows of `data_full/demo_patients_conus_fast_100000.csv`.
4. Buffer 270 m / 25 m; select both variables.
5. Run; verify `result.csv` has 100 rows × 2 variable columns.

Expected wall-clock: ≈ 1–2 min for 100 patients on BG, dominated by tile
selection overhead.

### Test data

- Unit tests use mock + tmpdir; no `data_full/` access.
- Integration tests use `tests/fixtures/patients_5.csv` (5 rows in Leon FL,
  guaranteed BG-shapefile coverage).
- Smoke uses the bundled demo CSV.

### CI behaviour

- `pytest -q` runs unit + existing auth/health/upload tests (the 17 already
  passing).
- `pytest -m integration` is a separate, opt-in command for machines with
  `data_full/`.
- `spacescans-pipeline` is not a Python import dependency — the
  integration is purely via subprocess.

## Implementation Estimate

| Type | Files | Approx LOC |
|---|---|---|
| New | `experiments/__init__.py`, `experiments/bg_ndi_wi.py` | ~260 |
| Modified backend | `config.py`, `task_manager.py`, `requirements.txt` | ~50 |
| Modified frontend | 5 wizard components + `api.ts` | ~120 |
| New tests | `test_bg_ndi_wi.py` (unit) + `test_bg_ndi_wi_integration.py` (integration) + `manual_e2e.md` | ~150 |

Targeting 1–2 weeks of focused work.

## Open Questions for Future Versions

- Should ontology nodes get a `linkage` metadata field linking them to
  pipeline YAML templates (the v2 generic mapping path)?
- For multi-experiment v2, do C3 weights get cached across tasks by
  `hash(boundary, buffer_m, raster_res_m, cohort)`?
- Does the FastAPI single-process model still hold at multi-user scale,
  or does v2 need a job runner?

These are explicitly deferred and not blocking v1.
