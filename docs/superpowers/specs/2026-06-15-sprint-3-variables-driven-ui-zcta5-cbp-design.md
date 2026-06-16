# Sprint 3: Variables-Driven UI + ZCTA5×CBP Experiment — Design Spec

## Background

The Sprint 1 variable catalog (`backend/data/variable_metadata.json`)
ships with exactly two entries — `ndi` and `walkability` — and is read
in exactly one place (`task_manager.compute_coverage`) to derive
per-variable time/region masks. The wizard's Variables step
(`frontend/src/components/wizard/variables-step.tsx:23-36`) hardcodes
the same two entries as a `V1_VARIABLES as const` array with no
connection to the backend file. The Review step
(`frontend/src/components/wizard/review-step.tsx` around lines 67-81,
the fetch + label-resolution block) pulls labels
from a third source — `/ontology/metadata.json` — fetched via raw
`fetch()`. Three independent definitions of "what variables exist"
coexist today, and the dispatch layer
(`backend/app/task_manager.py:285-291`) is a hard `if experiment ==
"bg_ndi_wi"` branch with a mock fallback.

This works for the v1 demo. It does not work for the next 7 variables.

## Goal

Stand up a single source of truth for variable definitions and prove
the dispatch architecture against a second, structurally different
experiment.

1. Promote `variable_metadata.json` to source-controlled
   `backend/app/data/variable_metadata.json` with `schema_version: 1`
   and a JSON Schema that locks the contract.
2. Introduce `variable_registry.py` as the single Python module that
   loads, validates, and queries the catalog.
3. Expose the registry as `GET /api/variables` so the wizard can
   render dynamically.
4. Refactor `VariablesStep` to consume `/api/variables`, group by
   boundary type, and render label/description/unit/coverage chips
   from metadata.
5. Add a second experiment — `zcta5_cbp` (community-organization
   density on ZCTA5 boundaries via the `yearly_areal` linkage pattern
   with a `.Rda` exposure file) — that lives alongside `bg_ndi_wi` and
   shares zero hardcoded coupling.
6. Generalize `task_manager.start_task` to dispatch by the
   `experiment` field on each selected variable's metadata, spawning
   one runner per experiment, sequentially.
7. Extract the (pid, episode_id) join from
   `bg_ndi_wi.merge_results` into a reusable `experiments/_merge.py`
   so `task_manager` can fan-in partial CSVs from every runner into a
   single `result.csv`.

The change is structurally larger than Sprint 2 (~1620 LOC including
tests; see the Implementation Estimate table) because it touches the
wizard, the dispatcher, and adds a new experiment runner end-to-end.
But every change is contained behind the registry boundary: future
sprints add a JSON entry + a runner file and inherit dispatch, UI
rendering, and coverage for free.

## Scope

### In scope (Sprint 3)

Each bullet annotates the brainstorm item it implements (B1-B13).
B14 and B15 (status.json multi-runner extension and C3 cache key
boundary extension) are forced dependencies of B6 and B4 respectively
— promote them to first-class brainstorm items in the brainstorm
follow-up, or read them as sub-bullets here.

- [B1] Move `backend/data/variable_metadata.json` →
  `backend/app/data/variable_metadata.json`, add `schema_version: 1`
  top-level field, add `backend/app/data/variable_metadata.schema.json`
  (JSON Schema draft-2020-12), wire `jsonschema` validation into the
  registry loader.
- [B2] Add `cbp_zcta5` entry to the metadata (10 value cols: r_religious,
  r_civic, r_business, r_political, r_professional, r_labor, r_bowling,
  r_recreational, r_golf, r_sports).
- [B3] New module `backend/app/variable_registry.py` exposing
  `load_variables()`, `get_variable(key)`, `variables_by_experiment()`,
  `list_experiments()`. Module-level mtime-keyed cache same as today's
  loader.
- [B4] New experiment runner `backend/app/experiments/zcta5_cbp.py` (~280
  LOC, cloned-and-trimmed from `bg_ndi_wi.py`).
- [B5] New shared module `backend/app/experiments/_merge.py` (~80 LOC) —
  extract the (pid, episode_id) join from
  `bg_ndi_wi.merge_results`. Both runners emit
  `result_<experiment_key>.csv`; the join into a single `result.csv`
  is performed by `task_manager` after all runners complete.
- [B6] `task_manager.start_task` dispatches by metadata `experiment` field:
  groups selected variables by experiment, spawns runners sequentially
  (host-level `.run_lock` and shared DuckDB/R workspace make parallel
  spawn unsafe).
- [B7] `task_manager.compute_coverage` becomes registry-driven (reads
  `m["coverage_years"]`, `m["coverage_region"]`, `m["boundary"]`,
  `m["display_unit"]` via `get_variable(key)`).
- [B14, sub-bullet of B6] `status.json` schema extension: top-level
  `"experiments": {<key>: {status, steps, current, progress}}` map;
  legacy flat `steps[]` remains for backwards compat (concatenation
  of all experiments' steps in dispatch order). Forced by
  multi-runner dispatch — sequential dispatch needs a per-runner
  progress channel.
- [B15, sub-bullet of B4] C3 cache key extended to include boundary
  type: existing key `<sha8>__BG__b<buffer>m__r<raster>m` becomes
  `<sha8>__<boundary>__b<buffer>m__r<raster>m` so `BG` and `ZCTA5`
  caches are independent. Forced by adding a second boundary —
  without it the BG cache would silently shadow ZCTA5 weights.
- [B8] New endpoint `GET /api/variables` returning `{schema_version,
  variables: {...}}` from `variable_registry.load_variables()`.
- [B9] Coverage endpoint response gains `boundary` and `display_unit`
  fields per variable (sourced from registry, not recomputed).
- [B10] Frontend refactor:
  `frontend/src/components/wizard/variables-step.tsx` fetches
  `/api/variables` on mount, displays grouped-by-boundary cards
  (Block Group / ZCTA5 sections), shows label + description + unit
  chip + coverage_years chip, mounts `VariableCoveragePanel` inline
  when checked.
- [B11] `frontend/src/components/wizard/review-step.tsx` groups selected
  variables by experiment in the summary section; resolves labels via
  the same registry payload (no second fetch to
  `/ontology/metadata.json`).
- [B10 cont.] `frontend/src/lib/api.ts` adds `api.listVariables()`; extends
  `VarCoverage` with `boundary` and `display_unit`.
- [B10 cont.] New `frontend/src/components/wizard/variable-card.tsx` (lifted out
  of `variables-step.tsx` to keep the wizard step file under ~150
  lines once dynamic loading + grouping land).
- [B12] Unit + integration tests: 5 new test files on the backend (~10 new
  unit tests), 1 new integration test for ZCTA5×CBP single-experiment
  run, 1 new integration test for multi-experiment dispatch
  (BG+ZCTA5).
- [B13] `backend/tests/manual_e2e.md` gains a Sprint 3 section covering
  registry-driven UI, schema-bump fallback, and the multi-experiment
  task.

### Out of scope (deferred)

- The remaining 6 experiments (`tiger_proximity`, `nhd_bluespace`,
  `vnl`, `temis`, `fara_tract`, `noise`). Sprint 4+.
- A `precomputed_areal` / `precomputed_static` / `cbp_fallback`
  episode-dispatch audit (Sprint 2 only covered `yearly_areal`,
  `yearly_areal_bg_vintage`, `static_areal`). Required when those
  linkage patterns appear in the wild; not needed for `zcta5_cbp`
  (uses `yearly_areal`).
- Per-variable shapefile coverage. Coverage stays
  bbox-based with the same hardcoded CONUS envelope; the
  `coverage_region` field stays a string enum
  (`"CONUS" | "US" | "AK_HI"`) where only `"CONUS"` is implemented
  this sprint. Sprint 4+ may upgrade `coverage_region` to a
  shapefile path.
- Renaming the synthetic `geoid` column to `episode_id` throughout
  the pipeline (Sprint 2 open question). Out of scope here to avoid
  churn. **Pre-condition for Sprint 3 correctness:** the `zcta5_cbp`
  linkage pattern is `yearly_areal`, which Sprint 2 patched to honour
  `output_grouping=episode` (the C4 step emits one row per
  (PATID, episode_id) tuple with a `geoid` column). The rename to
  `pid`/`episode_id` happens inside `_merge.write_partial` (see the
  source-to-extract subsection); the upstream pipeline is unmodified.
  Test coverage: the `geoid` smoke assertion added to
  `test_zcta5_cbp.py` (see Testing section) catches any drift from
  this assumption.
- A metadata editor UI. Edits are JSON-file-only this sprint.
- LRU cap on the C3 cache directory. The cache grows linearly with
  unique (cohort × boundary × buffer × raster) tuples; capacity
  management is Sprint 4+.
- Frontend test framework (jest / vitest). Visual regression covered
  by the manual_e2e smoke this sprint.
- Multi-experiment parallel spawn. Sequential only. The orchestrator
  holds `.run_lock` for its entire lifetime
  (`bg_ndi_wi.py:376-392`), so two runners in flight would deadlock
  on the lock; even without the lock, DuckDB engine and R sessions
  contend on a shared workspace. Defer parallelism until lock scope
  shrinks to per-step.
- Legacy `backend/data/variable_metadata.json` fallback. Sprint 3
  reads only the new path. The old file is removed from
  `backend/.gitignore` line 6 and deleted from working trees; Sprint
  4 follow-up cleanup verifies no dev-only copy survives.

## Architecture

```text
                          ┌──────────────────────────────┐
                          │  backend/app/data/           │
                          │    variable_metadata.json    │ ← schema_version:1
                          │    variable_metadata.schema  │   3 entries
                          └────────────┬─────────────────┘
                                       │ load + jsonschema.validate
                                       ▼
                          ┌──────────────────────────────┐
                          │  variable_registry.py        │
                          │    load_variables()          │
                          │    get_variable(key)         │
                          │    variables_by_experiment() │
                          └─────┬────────────────┬───────┘
                                │                │
            ┌───────────────────┘                └──────────┐
            ▼                                               ▼
   GET /api/variables                          task_manager.start_task
            │                                               │
            ▼                                               ▼
   variables-step.tsx                       group by metadata.experiment
   ┌──────────────────┐                                     │
   │ Block Group      │                              for each exp_key:
   │   [x] NDI        │                                 spawn runner
   │   [ ] Walkability│                                 (sequential)
   │ ZCTA5            │                                     │
   │   [x] CBP        │                            result_<key>.csv
   └──────────────────┘                                     │
                                                            ▼
                                              _merge.py: fan-in on
                                                (pid, episode_id)
                                                            │
                                                            ▼
                                                       result.csv
```

The dispatch architecture is a fan-out / fan-in:

1. The wizard selects a flat list of variable keys
   (`["ndi", "walkability", "cbp_zcta5"]`).
2. `task_manager.start_task` calls
   `variable_registry.variables_by_experiment(selected_keys)` →
   `{"bg_ndi_wi": ["ndi", "walkability"], "zcta5_cbp": ["cbp_zcta5"]}`.
3. For each experiment key (sorted by insertion order in the
   metadata file for determinism), spawn the runner subprocess with
   the experiment's filtered config; wait for completion before
   spawning the next.
4. Each runner emits `result_<experiment_key>.csv` (renamed from
   today's monolithic `result.csv` to allow fan-in).
5. After all runners complete, `task_manager` calls
   `experiments._merge.fan_in(task_dir, experiment_keys)` to join all
   partial CSVs on `(pid, episode_id)` into the final `result.csv`.

### Architectural choices and rationale

- **JSON Schema, not Pydantic.** The metadata file is the contract;
  multiple readers may grow over time (CLI inspector, deployment
  validator). A standalone schema file is consumable from any
  language and validates the source-of-truth file independent of
  Python. Loader still uses `jsonschema.validate(...)` for runtime
  enforcement on every read.
- **Schema version + mtime cache.** The Sprint 1
  `_VARIABLE_METADATA_CACHE` is preserved (mtime-keyed reload). The
  new `schema_version` field gates the loader: if a future bump
  breaks compat, the loader raises a clear
  `MetadataSchemaError(expected=1, actual=N)` instead of silently
  returning an unexpected shape.
- **`experiment` field becomes load-bearing.** Today it's
  documentation. Sprint 3 makes it the dispatch key. A whitelist
  guards against trivial code injection: only experiment values that
  match a Python module name in `backend/app/experiments/` (excluding
  `_merge`, `__init__`) are accepted at registry load time. Unknown
  experiment in metadata → fail-fast at server startup.
- **Sequential dispatch.** Two structural reasons: (a) host-level
  `.run_lock` is acquired for the whole orchestrator lifetime
  (`bg_ndi_wi.py:376-392`); (b) the spacescans DuckDB engine and R
  exposure-reader sessions are not designed for concurrent access
  within the same data dir. Sprint 3 does not change either invariant
  — it just plays nicely with both by spawning runners one at a
  time. The web layer's user-facing latency cost is additive (~30s
  for ZCTA5×CBP on top of ~90s for BG NDI+WI on the demo cohort);
  acceptable.
- **Dispatch order is a deliberate contract = JSON file order of
  first experiment appearance.** `variables_by_experiment()` uses
  `OrderedDict` and iterates the metadata `variables` map in file
  order, so experiment dispatch order tracks the JSON file. Sprint 3
  enshrines this: `test_e2e_multi_experiment` asserts `bg_ndi_wi`
  runs before `zcta5_cbp` _because_ `ndi` appears before `cbp_zcta5`
  in `variable_metadata.json`. A second unit test
  (`test_variables_by_experiment_respects_file_order`) reorders the
  JSON file and asserts the dispatch order inverts, locking the
  contract. Future schemas may introduce an explicit `priority: int`
  field if file-order proves too implicit; out of scope here.
- **C3 cache key includes boundary.** Today's key is
  `<sha8>__BG__b<buffer>m__r<raster>m`. The `BG` is a literal. Once
  ZCTA5 enters the picture the same input.parquet legitimately
  produces a different weight table per boundary, so the boundary
  must be part of the key. Sprint 3 lifts the literal into a per-runner
  constant.
- **Fan-out / fan-in instead of one big runner.** Each experiment has
  its own R/Python entry point in the upstream `spacescans` repo;
  forcing them into one process means a single sys.path, a single
  YAML render loop, and tight coupling between every future runner
  and the dispatcher. Per-runner subprocess + final-merge keeps each
  experiment self-contained and testable.
- **`result_<key>.csv` per runner, single `result.csv` after merge.**
  Frontend downloads are unchanged (still
  `${API_BASE}/api/tasks/${id}/results`). The fan-in step is the only
  consumer of the per-key files; they live under
  `task_dir/output/` alongside today's intermediate parquets and are
  not exposed as separate download URLs.
- **No legacy metadata fallback.** Sprint 1's gitignored
  `backend/data/variable_metadata.json` is removed. Any dev with a
  local-only copy gets a clear `FileNotFoundError(...)` on first
  registry load pointing at the new path; the migration message is
  one line in the Sprint 3 release notes.

## Data Flow

### Server startup

```text
1. FastAPI imports backend/app/variable_registry.
2. registry.load_variables() reads backend/app/data/variable_metadata.json
   + backend/app/data/variable_metadata.schema.json.
3. jsonschema.validate(...) raises on any constraint violation
   (missing required field, wrong enum, unknown experiment).
4. For each entry, registry asserts experiment in
   {f.stem for f in (backend/app/experiments/).glob("*.py")
    if f.stem not in {"__init__", "_merge"}}.
5. Validated dict is cached at module level, keyed by mtime.
6. Server starts; any failure above aborts startup with a stack trace.
```

### User selects variables → starts task

```text
1. Wizard fetches GET /api/variables on Variables-step mount.
2. User checks `ndi` (experiment=bg_ndi_wi), `walkability`
   (experiment=bg_ndi_wi), `cbp_zcta5` (experiment=zcta5_cbp).
3. Review step posts saveConfig({variables: [...3 keys]}).
   The `experiment` field on the request body is no longer used
   for dispatch (kept as an audit-log breadcrumb only — defaults
   to "auto"). See "API request compatibility" below.
4. POST /api/tasks/{id}/start → task_manager.start_task.
5. start_task:
   a. Acquire-then-release .run_lock (TOCTOU pre-check, unchanged).
   b. Read config.json["variables"].
   c. by_exp = registry.variables_by_experiment(selected_keys)
   d. for exp_key in by_exp:                  # sorted by metadata order
        spawn runner subprocess
        wait for terminal status (finished | error | cancelled)
        if status == "error":
            mark remaining experiments as skipped_due_to_prior_failure
            break (skip remaining experiments)
   e. if completed_keys is non-empty:
        _merge.fan_in(task_dir, completed_keys)   # produces partial result.csv
        on full success: status="finished", progress=1.0
        on partial:      status="partial",  progress=<aggregated>
        on zero success: status="error",    progress=0.0 (no fan_in)
6. Each runner subprocess:
   - acquires .run_lock for its lifetime (unchanged)
   - reads config.json, filters config["variables"] to its own keys
     (using registry.variables_by_experiment(...) again from inside
     the runner)
   - runs C3 + per-variable C4 steps as today
   - emits task_dir/output/result_<exp_key>.csv via _merge.write_partial(
     task_dir, exp_key, variables, parquet_map=...)
7. _merge.fan_in:
   - df = pd.read_csv(input.csv, dtype=str)
   - df["episode_id"] = range(len(df))         # same recomputation
   - for exp_key in completed_keys:
       partial = pd.read_csv(output/result_<key>.csv, dtype={...})
       df = df.merge(partial, on=["pid", "episode_id"], how="left")
   - df.to_csv(output/result.csv)
8. status.json final write — top-level experiments map shows each
   runner's terminal status; flat status="finished" iff every
   experiment finished.
```

### API request compatibility

The `experiment` field on the `POST /api/tasks/{id}/config` request
body (today: `experiment: str | None`, hardcoded to `"bg_ndi_wi"` by
`frontend/src/lib/api.ts:161`) becomes dispatch-irrelevant in Sprint
3 but is retained for one release as an audit-log breadcrumb.

Call sites that currently send `experiment`:

| Caller | Current behaviour | Sprint 3 behaviour |
|---|---|---|
| `frontend/src/lib/api.ts::saveConfig` | hardcodes `experiment: "bg_ndi_wi"` | changes to `experiment: "auto"`; backend ignores the value |
| Sprint 2 integration tests (`test_e2e_*`) | pass `experiment="bg_ndi_wi"` in the POST body | unchanged; backend accepts and logs but does not dispatch on it |
| Manual `curl` invocations | unspecified | accepted regardless of value |

Backend behaviour:

- The request schema keeps `experiment: str | None` for one release
  (Sprint 3) for backwards compat. Sprint 4 removes the field
  entirely.
- Whatever value is received is recorded in `logs.jsonl` as
  `{event: "config_saved", experiment_field_received: "<value>",
   dispatch_plan: {<by_exp>}}`. `"auto"` is the value emitted by the
  Sprint 3 frontend; older clients still see their value preserved in
  logs.
- No 410 deprecation header is added this sprint (avoids noise in
  the in-flight Sprint 2 integration tests); a Sprint 4 follow-up
  removes the field along with its schema entry.

## Variable Metadata Schema v1.0

### File: `backend/app/data/variable_metadata.json`

```json
{
  "schema_version": 1,
  "variables": {
    "ndi": {
      "label": "Neighborhood Deprivation Index (NDI)",
      "description": "Composite measure of neighborhood-level socioeconomic deprivation from US Census ACS variables.",
      "boundary": "BG",
      "coverage_years": [2012, 2022],
      "coverage_region": "CONUS",
      "experiment": "bg_ndi_wi",
      "variable_type": "continuous",
      "display_unit": "z-score",
      "value_cols": ["ndi"]
    },
    "walkability": {
      "label": "EPA Walkability Index",
      "description": "EPA National Walkability Index ranking neighborhoods on walkability characteristics (intersection density, transit proximity, employment mix).",
      "boundary": "BG",
      "coverage_years": [2016, 2021],
      "coverage_region": "CONUS",
      "experiment": "bg_ndi_wi",
      "variable_type": "continuous",
      "display_unit": "1-20 index",
      "value_cols": ["NatWalkInd"]
    },
    "cbp_zcta5": {
      "label": "Community Organization Density (ZBP)",
      "description": "Per-capita density of 10 community organization categories (religious, civic, business, political, professional, labor, bowling, recreational, golf, sports) at the ZIP Code Tabulation Area level from Census Zip Business Patterns.",
      "boundary": "ZCTA5",
      "coverage_years": [2013, 2019],
      "coverage_region": "CONUS",
      "experiment": "zcta5_cbp",
      "variable_type": "continuous",
      "display_unit": "establishments / 1k residents",
      "value_cols": [
        "r_religious", "r_civic", "r_business", "r_political",
        "r_professional", "r_labor", "r_bowling", "r_recreational",
        "r_golf", "r_sports"
      ]
    }
  }
}
```

### File: `backend/app/data/variable_metadata.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "spacescans.org/variable_metadata.schema.json",
  "title": "spacescans-web variable metadata",
  "type": "object",
  "required": ["schema_version", "variables"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"type": "integer", "const": 1},
    "variables": {
      "type": "object",
      "minProperties": 1,
      "patternProperties": {
        "^[a-z][a-z0-9_]*$": {
          "type": "object",
          "required": [
            "label", "description", "boundary",
            "coverage_years", "coverage_region",
            "experiment", "variable_type",
            "display_unit", "value_cols"
          ],
          "additionalProperties": false,
          "properties": {
            "label": {"type": "string", "minLength": 1, "maxLength": 80},
            "description": {"type": "string", "minLength": 1, "maxLength": 400},
            "boundary": {
              "type": "string",
              "enum": ["BG", "ZCTA5", "Tract", "County"]
            },
            "coverage_years": {
              "type": "array",
              "items": {"type": "integer", "minimum": 1900, "maximum": 2100},
              "minItems": 2, "maxItems": 2
            },
            "coverage_region": {
              "type": "string",
              "enum": ["CONUS", "US", "AK_HI"]
            },
            "experiment": {
              "type": "string",
              "pattern": "^[a-z][a-z0-9_]*$"
            },
            "variable_type": {
              "type": "string",
              "enum": ["categorical", "continuous"]
            },
            "display_unit": {
              "type": "string",
              "pattern": "^[\\x20-\\x7E]+$",
              "maxLength": 50
            },
            "value_cols": {
              "type": "array",
              "items": {"type": "string", "minLength": 1},
              "minItems": 1
            }
          }
        }
      },
      "additionalProperties": false
    }
  }
}
```

Schema notes:

- `schema_version: const 1` — any change to required fields, enums, or
  semantics bumps this number, and the loader rejects unknown
  versions explicitly.
- Key pattern `^[a-z][a-z0-9_]*$` constrains keys to safe identifiers
  (used as URL params, frontend keys, R column suffixes).
- `display_unit` ASCII-only — avoids font/encoding issues in pill
  chips on the wizard and any future PDF export.
- `value_cols` is the list of columns in the per-variable result
  parquet that should be joined into `result.csv`. For `ndi` it's
  `["ndi"]`; for `cbp_zcta5` it's all 10 ratio columns. The fan-in
  step uses this to know what to expect.

## Backend Modules

### `backend/app/variable_registry.py` (NEW, ~120 LOC)

```python
"""Single source of truth for variable definitions.

Loads backend/app/data/variable_metadata.json, validates against
variable_metadata.schema.json on every reload, and exposes typed
query helpers.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

import jsonschema

import app.config

_DATA_DIR = Path(__file__).parent / "data"
_METADATA_PATH = _DATA_DIR / "variable_metadata.json"
_SCHEMA_PATH = _DATA_DIR / "variable_metadata.schema.json"
_SUPPORTED_SCHEMA_VERSIONS = {1}

_CACHE: dict[str, Any] = {"mtime": None, "payload": None}


class MetadataSchemaError(RuntimeError):
    pass


def _discover_experiments() -> set[str]:
    exp_dir = Path(__file__).parent / "experiments"
    return {
        p.stem for p in exp_dir.glob("*.py")
        if p.stem not in {"__init__", "_merge"}
    }


def load_variables(*, force: bool = False) -> dict[str, Any]:
    mtime = _METADATA_PATH.stat().st_mtime
    if not force and _CACHE["mtime"] == mtime and _CACHE["payload"]:
        return _CACHE["payload"]

    with _METADATA_PATH.open() as f:
        payload = json.load(f, object_pairs_hook=OrderedDict)
    with _SCHEMA_PATH.open() as f:
        schema = json.load(f)

    jsonschema.validate(payload, schema)

    if payload["schema_version"] not in _SUPPORTED_SCHEMA_VERSIONS:
        raise MetadataSchemaError(
            f"unsupported schema_version: {payload['schema_version']} "
            f"(supported: {sorted(_SUPPORTED_SCHEMA_VERSIONS)})"
        )

    known_experiments = _discover_experiments()
    for key, m in payload["variables"].items():
        if m["experiment"] not in known_experiments:
            raise MetadataSchemaError(
                f"variable {key!r} references unknown experiment "
                f"{m['experiment']!r} (known: {sorted(known_experiments)})"
            )

    _CACHE["mtime"] = mtime
    _CACHE["payload"] = payload
    return payload


def get_variable(key: str) -> dict[str, Any]:
    payload = load_variables()
    try:
        return payload["variables"][key]
    except KeyError:
        raise KeyError(key)


def variables_by_experiment(keys: list[str]) -> "OrderedDict[str, list[str]]":
    """Group variable keys by their experiment, preserving metadata insertion order."""
    payload = load_variables()
    out: OrderedDict[str, list[str]] = OrderedDict()
    for var_key, m in payload["variables"].items():
        if var_key not in keys:
            continue
        out.setdefault(m["experiment"], []).append(var_key)
    return out


def list_experiments() -> list[str]:
    payload = load_variables()
    seen: list[str] = []
    for m in payload["variables"].values():
        if m["experiment"] not in seen:
            seen.append(m["experiment"])
    return seen
```

### `backend/app/task_manager.py` — start_task dispatch (MODIFIED)

The `if experiment == "bg_ndi_wi": ... else: mock_cli` branch at
lines 285-291 is replaced by a dispatch loop.

**Dispatch shape (non-blocking request thread):** today's
`start_task` `Popen`s the runner subprocess, detaches, and returns
immediately so the FastAPI request handler does not block for the
~90s lifetime of the orchestrator. Sprint 3 MUST preserve that
semantics. The sequential multi-runner dispatch loop below runs
inside a **supervisor subprocess** that is itself Popen'd by
`start_task` — the request thread returns as soon as the supervisor
is spawned.

Two-process shape:

1. `start_task` (called from request handler) Popens
   `python -m app.dispatcher run <task_id>` with `start_new_session=True`,
   stores the supervisor pid in `status.json["pid"]`, and returns
   `{"pid": <supervisor_pid>, "task_id": task_id}` to the caller.
2. The supervisor (`backend/app/dispatcher.py`, ~60 LOC NEW) runs
   the sequential loop below: for each experiment, Popen the runner,
   `proc.wait()` (inside the supervisor, NOT the request thread),
   update `status.json`, repeat. After all runners finish (or one
   errors), call `_merge.fan_in` and write the terminal top-level
   status.
3. `stop_task` SIGTERMs the supervisor pid (the supervisor's signal
   handler then SIGTERMs whichever runner is currently `running` per
   `status.json["experiments"]`).

The code below is the supervisor's body (NOT the request handler's):

```python
# backend/app/dispatcher.py — runs in the supervisor subprocess
from app import variable_registry

def dispatch(task_id: str) -> dict:
    # ... existing ownership + pre-flight .run_lock acquisition ...

    config = json.loads((task_dir / "config.json").read_text())
    selected = config.get("variables", [])
    by_exp = variable_registry.variables_by_experiment(selected)

    if not by_exp:
        raise ValueError("no variables selected")

    # Persist dispatch plan into status.json so the frontend can
    # render progress per experiment from the first poll.
    _write_status(task_dir, status="running", progress=0.0,
                  message="Dispatching experiments",
                  experiments={
                      exp_key: {"status": "pending", "variables": vars_}
                      for exp_key, vars_ in by_exp.items()
                  },
                  started_at=datetime.now(timezone.utc).isoformat())

    completed: list[str] = []
    for exp_key, exp_vars in by_exp.items():
        cmd = [
            str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
            "-m", f"app.experiments.{exp_key}",
            "run", str(task_dir),
            "--variables", ",".join(exp_vars),
        ]
        proc = subprocess.Popen(
            cmd, cwd=str(app.config.settings.BASE_DIR),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        rc = proc.wait()                     # blocking — sequential dispatch
        if rc != 0:
            # Per-runner status was already written by the runner's
            # signal handler / error path. Mark remaining as skipped.
            for skipped in [k for k in by_exp if k not in completed
                            and k != exp_key]:
                _mark_experiment(task_dir, skipped, "skipped_due_to_prior_failure")
            break                            # exit dispatch loop, fall through
        completed.append(exp_key)

    # Fan-in on whatever completed — produces a partial result.csv with
    # NaN columns for skipped experiments (R5 in the risk table).
    from app.experiments._merge import fan_in
    failed = [k for k in by_exp if k not in completed]
    if completed:
        fan_in(task_dir, completed)

    if not completed:
        # No runner succeeded; no result.csv produced.
        _write_status(task_dir, status="error", progress=0.0,
                      message=f"All experiments failed (first failure: {failed[0]})")
        return {"pid": None, "task_id": task_id, "failed": failed}
    if failed:
        _write_status(task_dir, status="partial",
                      progress=round(len(completed) / len(by_exp), 2),
                      message=f"{len(completed)}/{len(by_exp)} experiments "
                              f"completed; partial result.csv available")
        return {"pid": None, "task_id": task_id,
                "completed": completed, "failed": failed}
    _write_status(task_dir, status="finished", progress=1.0,
                  message=f"Completed {len(completed)} experiments")
    return {"pid": None, "task_id": task_id, "completed": completed}
```

The `pid` returned by `start_task` was historically the orchestrator
pid for `stop_task`. Sequential multi-runner dispatch means the
caller-facing pid is the dispatcher's own (FastAPI worker) for the
duration of the call. `stop_task` is amended to walk
`status.json["experiments"]` and SIGTERM any runner whose
sub-status is `"running"`.

### `backend/app/experiments/zcta5_cbp.py` (NEW, ~280 LOC)

Structural clone of `bg_ndi_wi.py`, trimmed to the ZCTA5×CBP shape:

```python
# Steps for this experiment:
_C3_STEP = _Step(
    name="c3_zcta5",
    yaml_template="c3/zcta5_us_demo.yaml",
    is_c3=True,
)
_VARIABLE_TO_STEP = {
    "cbp_zcta5": _Step(
        name="c4_zcta5_cbp",
        yaml_template="c4/zcta5_cbp_demo.yaml",
        is_c3=False,
    ),
}

# Plan(): always _C3_STEP first, then one C4 step per requested
# variable. With only cbp_zcta5 in scope, plan is always
# [c3_zcta5, c4_zcta5_cbp].

# csv_to_parquet, render_yaml, run_pipeline_step, _on_step_progress,
# _install_cancel_handler, cache lookup — all copied wholesale from
# bg_ndi_wi.py with two differences:
#
#   1. _cache_key boundary literal is "ZCTA5" instead of "BG".
#   2. render_yaml does NOT set buffer.raster_res_m for C3
#      (the zcta5_us_demo.yaml template ships with raster_res_m=25
#       hardcoded and we honour the upstream default).
#
# merge_results is replaced by a call into experiments/_merge.py:
#
#   from app.experiments._merge import write_partial
#   write_partial(task_dir, experiment_key="zcta5_cbp",
#                 variables=requested_vars,
#                 parquet_map={
#                     "cbp_zcta5": "c4_zcta5_cbp.parquet",
#                 })
```

#### Parquet → column unpacking contract

Unlike `bg_ndi_wi.py` (where each variable maps 1:1 to its own
parquet and its own single value column), `cbp_zcta5` is a
**one-parquet-many-columns** experiment: the single
`c4_zcta5_cbp.parquet` produced by the upstream pipeline contains all
10 `r_*` columns for the only catalogued variable key
(`cbp_zcta5`).

`parquet_map` is therefore `{variable_key: parquet_filename}`, NOT
`{variable_key: column_name}`. The column set actually emitted into
`result_zcta5_cbp.csv` is sourced from each variable's metadata
`value_cols` list via `variable_registry.get_variable(key)["value_cols"]`,
which `write_partial` reads to select columns from the parquet (plus
the join keys `PATID`/`geoid` which are renamed to `pid`/`episode_id`).

For `cbp_zcta5` this yields the 10 columns
`r_religious, r_civic, r_business, r_political, r_professional,
r_labor, r_bowling, r_recreational, r_golf, r_sports` selected from
the single parquet. For `bg_ndi_wi` it remains one parquet per
variable, with `value_cols=["ndi"]` and `value_cols=["NatWalkInd"]`
respectively — `write_partial` handles both shapes uniformly because
the column selection comes from metadata, not from the per-runner
constant.

#### Upstream YAML template pre-flight

The C4 template path `c4/zcta5_cbp_demo.yaml` is resolved relative to
`spacescans-pipeline/configs/`. Pre-flight Task 0 confirms the file
exists at
`/Users/xai/Desktop/spacescans-project/spacescans-pipeline/configs/c4/zcta5_cbp_demo.yaml`
before Sprint 3 dispatch lands. If absent, the runner's
`render_yaml` call raises `FileNotFoundError` at first invocation;
registry load-time does NOT probe this path (template is a runtime
artifact of the upstream repo, not a metadata contract).

The CLI entrypoint accepts a `--variables` flag (comma-separated) so
the dispatcher can pass the filtered set; falls back to reading
`config.json["variables"]` when omitted (for direct CLI invocations
that mirror today's `bg_ndi_wi run <task_dir>` form).

### `backend/app/experiments/_merge.py` (NEW, ~80 LOC)

Extracted from `bg_ndi_wi.merge_results` (current
`bg_ndi_wi.py:228-270`). Two public functions:

```python
def write_partial(
    task_dir: Path,
    experiment_key: str,
    variables: list[str],
    parquet_map: dict[str, str],
) -> Path:
    """Read each variable's per-step parquet, select metadata-declared
    value_cols, rename {PATID -> pid, geoid -> episode_id}, coerce
    episode_id to int, outer-join across variables on (pid, episode_id),
    write task_dir/output/result_<experiment_key>.csv. Emits a
    match_pct warning into logs.jsonl if any join matches < 90%.

    Replaces the per-runner merge step previously inlined at
    bg_ndi_wi.py:228-270. Returns the partial CSV path.
    """
    import pandas as pd
    from app import variable_registry

    out_dir = task_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"result_{experiment_key}.csv"

    # Read input.csv once to know the denominator for match_pct.
    input_df = pd.read_csv(task_dir / "input.csv", dtype=str)
    input_df["episode_id"] = range(len(input_df))
    input_df["episode_id"] = input_df["episode_id"].astype(int)
    input_keys = input_df[["pid", "episode_id"]] if "pid" in input_df.columns \
        else input_df.rename(columns={"PATID": "pid"})[["pid", "episode_id"]]

    merged: pd.DataFrame | None = None
    for var_key in variables:
        parquet_name = parquet_map[var_key]
        parquet_path = out_dir / parquet_name
        df = pd.read_parquet(parquet_path)

        # Rename join columns to the (pid, episode_id) contract.
        df = df.rename(columns={"PATID": "pid", "geoid": "episode_id"})
        df["episode_id"] = df["episode_id"].astype(int)

        # Select metadata-declared value_cols (plus join keys). For
        # one-parquet-many-columns experiments like cbp_zcta5, the
        # same parquet contributes multiple value_cols and the variable
        # loop may reference it more than once — deduplicate columns
        # already present in `merged`.
        meta = variable_registry.get_variable(var_key)
        value_cols = [c for c in meta["value_cols"] if c in df.columns]
        keep = ["pid", "episode_id"] + value_cols
        df = df[keep]

        if merged is None:
            merged = df
        else:
            # Drop duplicate value columns we already merged in (idempotent
            # for the cbp_zcta5 one-parquet-many-vars case).
            new_cols = [c for c in df.columns
                        if c in ("pid", "episode_id") or c not in merged.columns]
            df = df[new_cols]
            merged = merged.merge(df, on=["pid", "episode_id"], how="outer")

    # match_pct: fraction of input cohort (pid, episode_id) rows that
    # appear in merged with at least one non-NaN value column.
    joined = input_keys.merge(merged, on=["pid", "episode_id"], how="left")
    value_only = joined.drop(columns=["pid", "episode_id"])
    matched = value_only.notna().any(axis=1).sum()
    match_pct = round(100.0 * matched / max(len(input_keys), 1), 2)
    if match_pct < 90.0:
        _emit_log_warning(
            task_dir,
            experiment_key=experiment_key,
            event="merge_partial_low_match_pct",
            match_pct=match_pct,
            cohort_n=len(input_keys),
            matched_n=int(matched),
        )

    merged.to_csv(out_path, index=False)
    return out_path


def fan_in(task_dir: Path, experiment_keys: list[str]) -> Path:
    """Read input.csv, recompute episode_id, left-join each
    result_<key>.csv on (pid, episode_id), write final result.csv.
    """
    df = pd.read_csv(task_dir / "input.csv", dtype=str)
    df["episode_id"] = range(len(df))
    for exp_key in experiment_keys:
        partial = pd.read_csv(
            task_dir / "output" / f"result_{exp_key}.csv",
            dtype=str,                       # preserve FIPS leading zeros
        )
        # Coerce join columns: episode_id is int in both sides
        partial["episode_id"] = partial["episode_id"].astype(int)
        df["episode_id"] = df["episode_id"].astype(int)
        df = df.merge(partial, on=["pid", "episode_id"], how="left",
                      suffixes=("", f"_{exp_key}_dup"))
    out_path = task_dir / "output" / "result.csv"
    df.to_csv(out_path, index=False)
    return out_path
```

`bg_ndi_wi.merge_results` is replaced by a 3-line call into
`write_partial(task_dir, "bg_ndi_wi", variables, parquet_map=...)`.
The Sprint 2 episode-dispatch tests (the (pid, episode_id) join
must still match) keep passing because the join logic itself moves
unchanged — only its enclosing module name changes.

#### Source to extract (Sprint 2 reference)

For PR-time review the extraction MUST preserve every behaviour from
the current `bg_ndi_wi.merge_results` body at lines 228-270 of
`backend/app/experiments/bg_ndi_wi.py`. The Sprint 2 git blame on
that block is the source of truth; the extracted `write_partial` body
above is a refactor, not a rewrite. Reviewer's PR-time checklist:

1. Open `backend/app/experiments/bg_ndi_wi.py:228-270` on `main` and
   diff against `experiments/_merge.py::write_partial` in the Sprint 3
   branch.
2. Confirm the rename map (`{PATID -> pid, geoid -> episode_id}`),
   the int coercion on `episode_id`, and the `logs.jsonl` warning
   emission path all survive byte-for-byte.
3. Run `test_e2e_multi_episode_cohort` (Sprint 2's regression test)
   against both branches and assert `result.csv` is byte-identical.
4. New behaviour delta to expect: column selection now comes from
   `variable_registry.get_variable(key)["value_cols"]` instead of
   passing all parquet columns minus join keys; for `bg_ndi_wi` this
   is a no-op (`value_cols=["ndi"]` and `value_cols=["NatWalkInd"]`
   already match the parquet contents); for `cbp_zcta5` this is the
   only mechanism that selects the 10 `r_*` columns.

### `backend/app/routers/tasks.py` — `/api/variables` endpoint (NEW)

```python
from fastapi import APIRouter, Depends, HTTPException
from app import variable_registry
from app.routers.tasks import require_user  # same auth dep as /api/tasks/*

router = APIRouter(prefix="/api/variables", tags=["variables"])


class VariableMetadataModel(BaseModel):
    label: str
    description: str
    boundary: Literal["BG", "ZCTA5", "Tract", "County"]
    coverage_years: tuple[int, int]
    coverage_region: Literal["CONUS", "US", "AK_HI"]
    experiment: str
    variable_type: Literal["categorical", "continuous"]
    display_unit: str
    value_cols: list[str]


class VariableCatalogResponse(BaseModel):
    schema_version: int
    variables: dict[str, VariableMetadataModel]


@router.get(
    "",
    response_model=VariableCatalogResponse,
    include_in_schema=True,         # surfaces in OpenAPI; the catalog
                                    # is a stable contract.
)
def list_variables(_user=Depends(require_user)) -> VariableCatalogResponse:
    try:
        payload = variable_registry.load_variables()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "metadata_unavailable", "message": str(e)},
        )
    except variable_registry.MetadataSchemaError as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "metadata_schema_invalid", "message": str(e)},
        )
    return payload
```

Mount point: a small new router file
`backend/app/routers/variables.py` with prefix `/api/variables` so the
existing `/api/tasks` router stays focused. `main.py` includes both.

Contract notes:

- **Response model:** `VariableCatalogResponse` (Pydantic). The
  per-variable shape mirrors `variable_metadata.schema.json` v1; both
  the JSON Schema file and the Pydantic model are versioned together.
- **Error semantics:**
  - `FileNotFoundError` → `503 metadata_unavailable` (the JSON file
    moved or was deleted at runtime; mtime invalidation triggered a
    reload that failed). Stable error body
    `{detail: {error, message}}`.
  - `MetadataSchemaError` → `500 metadata_schema_invalid` (file
    present but fails `jsonschema.validate` or contains an unknown
    `experiment`).
- **Auth:** `Depends(require_user)` — the same dependency used by
  `/api/tasks/coverage` and the rest of the task-scoped routes. The
  catalog is not public; an unauthenticated request gets `401`.
- **OpenAPI visibility:** `include_in_schema=True` so the catalog
  appears in `/openapi.json` alongside task endpoints, matching the
  spec's stated stance that the catalog is a stable contract.

### `backend/app/task_manager.py` — `compute_coverage` (MODIFIED)

The function body at lines 39-145 keeps its behaviour but reads
metadata via the registry instead of the inline cache. The response
gains two fields per variable:

```python
out_vars[var] = {
    "coverage_years": [y0, y1],
    "patients_in_time_window": int(in_time.sum()),
    "patients_in_region": int(in_region.sum()),
    "patients_covered": int(covered.sum()),
    "coverage_pct": round(100 * covered.sum() / n_total, 2),
    "warnings": warnings,
    "boundary": m["boundary"],          # NEW
    "display_unit": m["display_unit"],  # NEW
}
```

The hardcoded CONUS bbox (`-125..-66`, `24..50`) is unchanged; only
`coverage_region == "CONUS"` triggers the filter, anything else
short-circuits to `pd.Series(True, ...)` per current behaviour.

## Frontend Modules

### `frontend/src/lib/api.ts` (MODIFIED)

Add a new fetcher and extend `VarCoverage`:

```typescript
export interface VariableMetadata {
  label: string;
  description: string;
  boundary: 'BG' | 'ZCTA5' | 'Tract' | 'County';
  coverage_years: [number, number];
  coverage_region: 'CONUS' | 'US' | 'AK_HI';
  experiment: string;
  variable_type: 'categorical' | 'continuous';
  display_unit: string;
  value_cols: string[];
}

export interface VariableCatalog {
  schema_version: number;
  variables: Record<string, VariableMetadata>;
}

export interface VarCoverage {
  coverage_years: [number, number];
  patients_in_time_window: number;
  patients_in_region: number;
  patients_covered: number;
  coverage_pct: number;
  warnings: string[];
  boundary: 'BG' | 'ZCTA5' | 'Tract' | 'County';     // NEW
  display_unit: string;                              // NEW
}

export const api = {
  // ... existing ...
  listVariables: () => request<VariableCatalog>('/api/variables'),
};
```

`schema_version` is exposed to the frontend so the wizard can render
a "version mismatch — please refresh" banner if the backend bumps to
2 while a tab is open. The frontend's expected version is a constant
`EXPECTED_VARIABLE_SCHEMA_VERSION = 1` in `variables-step.tsx`.

#### saveConfig `experiment` field disposition

`frontend/src/lib/api.ts:161` currently hardcodes
`experiment: "bg_ndi_wi"` in the saveConfig body. **Sprint 3
replaces** that literal with `experiment: "auto"`. The field stays in
the request body for one release for backwards compat (Sprint 4
removes it entirely; see the API request compatibility subsection
above).

Rationale for retention vs. removal: Sprint 2's integration tests
(`test_e2e_multi_episode_cohort` and `test_e2e_bg_ndi_wi_cohort`)
construct the POST body with `experiment="bg_ndi_wi"`; removing the
field this sprint would force those test fixtures to change.
Retaining the field (backend accepts but ignores) keeps the test
diff small and isolates the cleanup to Sprint 4.

### `frontend/src/components/wizard/variables-step.tsx` (REWRITTEN)

```tsx
const EXPECTED_VARIABLE_SCHEMA_VERSION = 1;

export function VariablesStep({taskId, onComplete, onBack, initialSelection}) {
  const [catalog, setCatalog] = useState<VariableCatalog | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>(initialSelection ?? []);

  useEffect(() => {
    let cancelled = false;
    api.listVariables()
      .then(c => {
        if (cancelled) return;
        setCatalog(c);
        // Reconcile stale selection against new catalog.
        const known = new Set(Object.keys(c.variables));
        setSelected(prev => prev.filter(k => known.has(k)));
      })
      .catch(e => !cancelled && setLoadError(String(e)));
    return () => { cancelled = true; };
  }, []);

  if (loadError) return <ErrorCard message={loadError} />;
  if (!catalog) return <LoadingCard message="Loading variable catalog..." />;
  if (catalog.schema_version !== EXPECTED_VARIABLE_SCHEMA_VERSION) {
    return <SchemaMismatchBanner expected={EXPECTED_VARIABLE_SCHEMA_VERSION}
                                 actual={catalog.schema_version} />;
  }

  // Group by boundary, preserving JSON-file insertion order within each group.
  const grouped = useMemo(() => groupByBoundary(catalog.variables), [catalog]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Select Variables</CardTitle>
        <CardDescription>
          Choose one or more exposures to compute for your cohort. Variables
          are grouped by spatial boundary.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {Object.entries(grouped).map(([boundary, entries]) => (
          <section key={boundary}>
            <h3 className="text-sm font-medium">{BOUNDARY_LABEL[boundary]}</h3>
            {entries.map(([key, meta]) => (
              <VariableCard
                key={key}
                varKey={key}
                meta={meta}
                checked={selected.includes(key)}
                onToggle={() => toggleSelection(key)}
                taskId={taskId}
              />
            ))}
          </section>
        ))}
        <Button onClick={() => onComplete(selected)}
                disabled={selected.length < 1}>
          Next
        </Button>
      </CardContent>
    </Card>
  );
}
```

The hardcoded `V1_VARIABLES as const` array is deleted. The hardcoded
"Experiment: BG NDI + Walkability (v1)" title is deleted.

#### Frontend helpers

New helpers introduced by the Variables/Review refactors, with file
locations:

- `frontend/src/lib/variable-grouping.ts` (NEW, ~40 LOC):
  - `groupByBoundary(variables: Record<string, VariableMetadata>): Record<BoundaryKey, [string, VariableMetadata][]>`
    — preserves JSON-file insertion order within each boundary group.
  - `groupByExperiment(selectedKeys: string[], catalog: VariableCatalog): Record<string, string[]>`
    — preserves dispatch order (first-appearance of each experiment
    in the catalog).
  - `BOUNDARY_LABEL` literal mapping (also pins section render order):

    ```ts
    export const BOUNDARY_ORDER = ['BG', 'ZCTA5', 'Tract', 'County'] as const;
    export const BOUNDARY_LABEL: Record<typeof BOUNDARY_ORDER[number], string> = {
      BG: 'Block Group',
      ZCTA5: 'ZIP Code Tabulation Area',
      Tract: 'Census Tract',
      County: 'County',
    };
    ```

    Sprint 3 only renders `BG` and `ZCTA5` (the only boundaries with
    metadata entries this sprint); `Tract` and `County` are reserved
    for Sprint 4+. `groupByBoundary` iterates `BOUNDARY_ORDER` to
    guarantee deterministic section ordering regardless of metadata
    ordering.

- `toggleSelection(key: string)`: local handler defined inside
  `VariablesStep` — calls `setSelected(prev => prev.includes(key) ?
  prev.filter(k => k !== key) : [...prev, key])`. Not exported.

Component-library status (existing shadcn primitives vs. new):

- `<Card>`, `<CardHeader>`, `<CardTitle>`, `<CardDescription>`,
  `<CardContent>`, `<Checkbox>`, `<Button>` — existing shadcn
  components at `frontend/src/components/ui/`.
- `<Chip>` — NEW shadcn-style wrapper at
  `frontend/src/components/ui/chip.tsx` (~25 LOC); thin div with
  `variant: 'default' | 'outline'` prop, rounded-full badge styling.
- `<Pill>` — NEW alias of `<Chip>` at the same file; visually
  identical, used in Review step's per-experiment summary to match
  existing Review-step vocabulary.
- `<ErrorCard>` — NEW at
  `frontend/src/components/wizard/error-card.tsx` (~20 LOC); renders
  destructive-toned `<Card>` with a `message` prop.
- `<LoadingCard>` — NEW at
  `frontend/src/components/wizard/loading-card.tsx` (~15 LOC);
  `<Card>` with a spinner and `message` prop.
- `<SchemaMismatchBanner>` — NEW at
  `frontend/src/components/wizard/schema-mismatch-banner.tsx` (~25
  LOC); takes `expected` + `actual` numeric props, renders a
  destructive `<Card>` with a "please refresh" CTA.

### `frontend/src/components/wizard/variable-card.tsx` (NEW)

Lifted from the inline `<label>` block at
`variables-step.tsx:66-86`. Renders:

```tsx
<label className="...">
  <Checkbox checked={checked} onCheckedChange={onToggle} />
  <div>
    <div className="font-medium">{meta.label}</div>
    <div className="text-sm text-muted-foreground">{meta.description}</div>
    <div className="flex gap-1 mt-1">
      <Chip>{meta.display_unit}</Chip>
      <Chip>{meta.coverage_years[0]}–{meta.coverage_years[1]}</Chip>
      <Chip variant="outline">{meta.boundary}</Chip>
    </div>
  </div>
  {checked && <VariableCoveragePanel taskId={taskId} variableKey={varKey} />}
</label>
```

### `frontend/src/components/wizard/variable-coverage-panel.tsx` (MINOR)

Consumes the new `boundary` and `display_unit` fields:

- Body string changes from
  `within {coverage_years[0]}-{coverage_years[1]} + coverage region`
  to
  `within {coverage_years[0]}-{coverage_years[1]} + {boundary} on CONUS`.
- No other behavioural change. Tone thresholds (95/60) stay
  hardcoded; deferred to Sprint 4+ alignment with the backend's 5%
  threshold.

### `frontend/src/components/wizard/review-step.tsx` (MODIFIED)

The `/ontology/metadata.json` fetch around lines 67-81 (fetch +
label-resolution block) is deleted. The
component receives the catalog via a shared hook (see below) so
`getLabel(id)` becomes `catalog.variables[id]?.label ?? id`.

**Catalog sharing strategy (resolved):** use a module-level cached
hook `useVariableCatalog()` at
`frontend/src/lib/use-variable-catalog.ts` (NEW, ~30 LOC). Both
`VariablesStep` and `ReviewStep` call the hook; it returns the same
fetched object from a module-level cache (keyed on a `mtime` field
the backend could optionally surface — for Sprint 3 it caches for
the lifetime of the page). No prop-drilling through the wizard
container; no second network fetch (rules out option (b) from the
critic's note; honours the no-second-fetch goal at line 106).

This is added to the scope bullet list under "Frontend refactor": a
new `use-variable-catalog.ts` hook file alongside the catalog
helpers.

The "Selected Variables" SummarySection is grouped by experiment:

```tsx
{Object.entries(groupByExperiment(selectedVariables, catalog)).map(
  ([expKey, varKeys]) => (
    <div key={expKey}>
      <div className="text-xs uppercase">{expKey}</div>
      {varKeys.map(k => <Pill key={k}>{catalog.variables[k].label}</Pill>)}
    </div>
  )
)}
```

`estimateRuntime()` heuristic stays as-is for now (operates on row
count + buffer + variable count); a per-experiment refinement is
Sprint 4+.

## C3 Cache Extension

The Sprint 1 cache key is
`<sha8>__BG__b<buffer>m__r<raster>m` constructed at
`bg_ndi_wi.py:294-298`. The `BG` literal is replaced by a per-runner
constant:

```python
# bg_ndi_wi.py
_BOUNDARY = "BG"

# zcta5_cbp.py
_BOUNDARY = "ZCTA5"

# in both:
def _cache_key(input_parquet_path, buffer_m, raster_res_m):
    h = hashlib.sha256(open(input_parquet_path, "rb").read()).hexdigest()[:8]
    return f"{h}__{_BOUNDARY}__b{buffer_m}m__r{raster_res_m}m"
```

Existing BG cache entries continue to hit (key bytes unchanged).
ZCTA5 entries land in a separate namespace under the same
`C3_CACHE_DIR`. No migration script needed.

## status.json Schema Extension

Today's status.json (per `bg_ndi_wi.py:399-412`) is a flat dict:

```json
{
  "status": "running",
  "progress": 0.55,
  "message": "Running c4_walkability (3/3) — 12%",
  "current_step": "c4_walkability",
  "total_steps": 3,
  "steps": ["c3_bg", "c4_ndi", "c4_walkability"],
  "started_at": "2026-06-15T10:00:00Z",
  "pid": 12345
}
```

Sprint 3 adds a top-level `experiments` map while keeping every
existing field for backwards compat. Two writer paths produce it:

1. `task_manager.start_task` writes the initial map on dispatch
   (status="pending" for every experiment).
2. Each runner amends its own slot via the existing
   `_write_status(task_dir, ...)` helper, which now does a JSON
   merge instead of overwrite on the `experiments` sub-key. See
   "Status merge atomicity" below for the lock + atomic-rename
   contract that keeps the orchestrator and runner writers from
   racing.

**Aggregation formula.** Top-level `progress` is the step-weighted
average across all experiments: `progress = sum(completed sub-steps)
/ total_steps`, where `total_steps = sum(len(exp.steps))`. In the
example below, BG has completed 3 of 3 sub-steps and ZCTA5 has
completed 1 of 2 sub-steps, so `progress = 4 / 5 = 0.80`.

New shape:

```json
{
  "status": "running",
  "progress": 0.80,
  "message": "Running zcta5_cbp (2/2)",
  "current_step": "c4_zcta5_cbp",
  "total_steps": 5,
  "steps": ["c3_bg", "c4_ndi", "c4_walkability", "c3_zcta5", "c4_zcta5_cbp"],
  "started_at": "2026-06-15T10:00:00Z",
  "pid": 12345,
  "experiments": {
    "bg_ndi_wi": {
      "status": "finished", "progress": 1.0,
      "variables": ["ndi", "walkability"],
      "steps": ["c3_bg", "c4_ndi", "c4_walkability"],
      "current_step": null
    },
    "zcta5_cbp": {
      "status": "running", "progress": 0.50,
      "variables": ["cbp_zcta5"],
      "steps": ["c3_zcta5", "c4_zcta5_cbp"],
      "current_step": "c4_zcta5_cbp"
    }
  }
}
```

The flat `steps[]` is the concatenation of every
`experiments[*].steps` in dispatch order; flat `current_step` mirrors
the actively-running runner's `current_step`. Frontend's existing
`TaskStatus.steps` consumer keeps working; new code can opt into
`experiments` for per-runner UI.

### Status merge atomicity

`_write_status(task_dir, ...)` is upgraded to a read-modify-write
under a per-task lock with POSIX atomic rename:

1. Acquire `task_dir/.status_lock` (Python `fcntl.flock`, blocking
   with a 5s timeout — short because writes are sub-second).
2. Read current `status.json` if present.
3. Deep-merge the kwargs into the in-memory dict (the `experiments`
   sub-key is merged per-experiment-key, not overwritten; everything
   else is overwrite).
4. Write to `task_dir/status.json.tmp` and `os.replace(...)` into
   `task_dir/status.json` (atomic on the same filesystem).
5. Release the lock.

This handles the (rare-but-real) race where the orchestrator
supervisor writes top-level `status`/`progress` while a runner
amends its own `experiments[<key>]` slot. Sequential dispatch
guarantees at most one runner is active, but the supervisor +
runner pair is still two concurrent writers.

Alternative considered and rejected: per-experiment substatus files
(`status_<exp>.json`) polled by the supervisor. Rejected because
frontend consumers expect a single `status.json` polling endpoint
and aggregation would have to happen on every poll.

### Status enum and transition rules

Per-experiment `experiments[<key>].status` legal values:

| Value | Meaning |
|---|---|
| `pending` | Written by `start_task` on dispatch; runner not yet spawned. |
| `running` | Runner subprocess is active. |
| `finished` | Runner exited 0 and emitted `result_<key>.csv`. |
| `error` | Runner exited non-zero or its signal handler wrote an error status. |
| `cancelled` | `stop_task` SIGTERMed the runner (writes this on cleanup). |
| `skipped_due_to_prior_failure` | An earlier runner in the sequential dispatch errored; this runner was never spawned. |

Top-level `status` legal values after Sprint 3:

| Value | When written |
|---|---|
| `running` | Any runner in `running` AND at least one not yet terminal. |
| `finished` | Every runner in `finished`. |
| `partial` | At least one `finished` AND at least one `error`/`skipped_due_to_prior_failure`. |
| `error` | Every runner in `error` (zero completed; no fan_in run; no `result.csv`). |
| `cancelled` | `stop_task` was invoked; any runner in `running` is SIGTERMed. |

Transition rules:

- `start_task` writes top-level `running` and per-experiment `pending`
  on dispatch.
- Each runner transitions its own slot `pending → running → {finished, error, cancelled}`.
- `start_task`'s post-dispatch write computes top-level status from
  the per-experiment map: `finished` iff all completed; `partial` iff
  ≥1 completed AND ≥1 errored/skipped; `error` iff zero completed.
- `stop_task` walks `experiments` and SIGTERMs any runner whose
  sub-status is `running`, then writes top-level `cancelled`.

## Testing

### Pyramid

```text
              ┌───────────────────────────┐
              │  Manual smoke             │   1 — Sprint 3 walk-through
              └───────────────────────────┘     (variables UI + multi-exp)
            ┌───────────────────────────────┐
            │  Integration                  │   2 new
            │  - e2e_zcta5_cbp_cohort       │
            │  - e2e_multi_experiment       │
            └───────────────────────────────┘
      ┌──────────────────────────────────────────┐
      │  Unit                                    │   ~10 across 5 new files
      │  - variable_registry                     │
      │  - task_manager_dispatch                 │
      │  - zcta5_cbp                             │
      │  - merge_partial                         │
      │  - coverage_metadata                     │
      └──────────────────────────────────────────┘
```

### New test files (backend)

`backend/tests/test_variable_registry.py` — schema validation, mtime
reload, unknown experiment rejection, schema_version mismatch
rejection, `variables_by_experiment` ordering.

`backend/tests/test_task_manager_dispatch.py` — sequential dispatch
order matches metadata order; partial-failure path marks remaining as
skipped; status.json `experiments` map written on dispatch start.

`backend/tests/test_zcta5_cbp.py` — clone of `test_bg_ndi_wi.py`
shape: csv_to_parquet adds episode_id; render_yaml injects
`output_grouping: episode` and writes the ZCTA5 boundary; cache key
contains literal `ZCTA5`; `write_partial` emits
`result_zcta5_cbp.csv`. Plus a `geoid` smoke assertion: after the C4
step the produced parquet contains a `geoid` column whose values
fall inside the input `episode_id` range (catches the silent failure
mode where ZCTA5's linkage pattern would emit per-patient rows
instead of per-episode rows under `output_grouping=episode`).

`backend/tests/test_merge_partial.py` — extracted-and-shared
behaviour: `write_partial` produces the same join shape that
`bg_ndi_wi.merge_results` did pre-extraction (regression test for
Sprint 2 episode dispatch); `fan_in` left-joins two partials on (pid,
episode_id) without row duplication; suffix handling on column-name
collision.

`backend/tests/test_coverage_metadata.py` — `compute_coverage`
response includes `boundary` and `display_unit`; behaviour unchanged
for `coverage_region="CONUS"`; unknown variable raises with the
preserved error shape.

### New integration tests

`backend/tests/test_e2e_zcta5_cbp_cohort.py::test_e2e_zcta5_cbp_cohort`
— upload the existing demo cohort, run with `variables=["cbp_zcta5"]`,
assert `result.csv` has the same row count as input + all 10 r_*
columns present.

`backend/tests/test_e2e_multi_experiment.py::test_e2e_multi_experiment_cohort`
— same cohort, `variables=["ndi", "walkability", "cbp_zcta5"]`,
assert two runners spawned in order (bg_ndi_wi first, zcta5_cbp
second, by metadata insertion), final `result.csv` carries
NatWalkInd + ndi + 10 r_* columns, status.json's `experiments` map
shows both as `finished`.

Both integration tests are `@pytest.mark.integration` and skipped by
default. Local wall-clock budget: ~90s (BG) + ~30s (ZCTA5) on the
demo cohort.

### Manual smoke (`backend/tests/manual_e2e.md`)

```markdown
## Sprint 3 — Variables-driven UI + ZCTA5×CBP

Pre-flight:
- backend/app/data/variable_metadata.json exists with schema_version 1
  and 3 entries.
- backend/app/data/variable_metadata.schema.json exists.
- pyreadr installed in the spacescans-pipeline env (see Sprint 3
  Risk R1).

1. Variables-step renders 3 cards grouped by boundary:
   - "Block Group" section: NDI, EPA Walkability Index
   - "ZCTA5" section: Community Organization Density (ZBP)
   Each card shows label, description, unit chip, year-range chip,
   boundary chip.
2. Tick a card → coverage panel mounts inline, calls
   /api/tasks/<id>/coverage?variables=<key>, displays the same shape
   as Sprint 1 plus the new boundary chip.
3. Bump schema_version to 2 in the JSON file, refresh the wizard.
   Expected: "Variable catalog version mismatch" banner. Revert.
4. Tick all 3 variables → Review step → Run. Watch the task page:
   - status.json's `experiments` map shows bg_ndi_wi running first,
     zcta5_cbp pending; then bg_ndi_wi finished, zcta5_cbp running.
   - logs.jsonl carries entries from both runners.
   - result.csv on completion carries ndi + NatWalkInd + all 10 r_*
     columns.
```

## Migration / Backwards Compat

- **File location change.** Sprint 1's
  `backend/data/variable_metadata.json` is moved (git mv) to
  `backend/app/data/variable_metadata.json`. The `.gitignore` entry
  at `backend/.gitignore:6` is removed in the same commit. Devs with
  the old file in their working tree see an untracked duplicate;
  cleanup is `rm backend/data/variable_metadata.json` after pulling
  Sprint 3.
- **No code-level fallback to the old path.** Sprint 4 follow-up
  verifies that no dev or prod environment retains a copy at the old
  location. The deliberate non-fallback prevents drift between
  source-controlled metadata and a stale local override.
- **Sprint 1 result.csv files unaffected.** The fan-in step writes
  `result.csv` at the same path that Sprint 1's `merge_results` wrote
  to. Old tasks' result files are not migrated.
- **Sprint 2 episode dispatch preserved.** `_merge.write_partial` is
  a structural extraction, not a behaviour change; the (pid,
  episode_id) join Sprint 2 introduced moves wholesale into the new
  module. Test
  `test_merge_results_joins_on_pid_and_episode_id` from Sprint 2 is
  ported to `test_merge_partial.py` to lock the regression.
- **C3 cache entries from Sprint 1/2 keep hitting.** The key format
  `<sha8>__BG__...` is unchanged for the BG runner; ZCTA5 entries
  occupy a fresh namespace. No cache wipe required at deploy time.
- **`schema_version` bump path.** Future schema changes:
  1. Add the new shape to `variable_metadata.schema.json` with
     conditional `if/then` on `schema_version`.
  2. Bump the JSON file's `schema_version`.
  3. Update `_SUPPORTED_SCHEMA_VERSIONS` in `variable_registry.py`.
  4. Bump `EXPECTED_VARIABLE_SCHEMA_VERSION` in
     `variables-step.tsx`.
  Loader raises `MetadataSchemaError` if any of those four steps is
  skipped — failure is loud and at server start.

## Risks and Mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | `pyreadr` not installed in the `spacescans-pipeline` env. The ZCTA5×CBP exposure file is a `.Rda` read via `readers._read_r_table` (gated on `spacescans._extras.require('rda', 'pyreadr')`). Without it the runner fails at the C4 step with an ExtraNotInstalled error. | Pre-Sprint 3 Task 0: `pip install pyreadr` in the spacescans-pipeline env. The dependency is declared under `pyproject.toml [rda]` already; one-line install. Document in `manual_e2e.md` pre-flight. |
| R2 | The C3 ZCTA5 weight parquet `buffer270mZCTA525m_demo100k.parquet` exists today (~1.3M, May 26 16:40) but is regenerated by `configs/c3/zcta5_us_demo.yaml` on cache miss. If the file is deleted, the first ZCTA5 task incurs a multi-minute C3 build. | Pre-Sprint 3 check: confirm the file exists at `/Users/xai/Desktop/spacescans-project/output/python_v2/270m/ZCTA5_US/C3/`. If missing, regenerate per the spacescans-pipeline README before the smoke test. |
| R3 | Dynamic experiment dispatch via `f"app.experiments.{exp_key}"` is a code-injection sink if `exp_key` reaches it unsanitised. | Two layers: (a) the JSON Schema `experiment` pattern `^[a-z][a-z0-9_]*$` rejects shell-meta and path traversal at load time; (b) `_discover_experiments()` whitelists exp_keys against actual files in `backend/app/experiments/` at registry load. An attacker controlling the metadata file already has full code execution; the schema constraint blocks accidental drift in normal use. |
| R4 | A user with a wizard open during a `schema_version` bump or variable deletion holds a stale selection. | Frontend `useEffect` on `listVariables()` reconciles the in-memory selection against the new catalog (`selected.filter(k => known.has(k))`) and surfaces a toast `"Variable X is no longer available; removed from selection"`. The `schema_version` banner is the harder stop. |
| R5 | A runner fails mid-dispatch (e.g., zcta5_cbp errors after bg_ndi_wi succeeded). The user is left with a partial `result_bg_ndi_wi.csv` and no `result.csv`. | `start_task` marks remaining experiments as `skipped_due_to_prior_failure` in `status.json`. `_merge.fan_in` is called only on the `completed` list, so a partial `result.csv` is still produced with NaN columns for the failed experiment's variables. The frontend renders a banner "1 of 2 experiments failed; partial result available". |
| R6 | The `_merge.py` extraction touches the join logic that Sprint 2 specifically validated for (pid, episode_id) preservation. A subtle copy-paste error breaks multi-episode joins silently (left-join still succeeds, but NaN rate spikes). | The Sprint 2 integration test `test_e2e_multi_episode_cohort` is run before and after the extraction and must produce byte-identical `result.csv`. `test_merge_partial.py` adds a unit assertion: for a synthetic 10-row input × 10-row variable parquet, `match_pct == 100.0`. |
| R7 | `display_unit` strings appear in the wizard chip and may break layout if too long or use unsupported glyphs (`μg/m³`, `°C`). | JSON Schema constrains to ASCII printable + max 50 chars. Sprint 3's three entries use safe strings (`"z-score"`, `"1-20 index"`, `"establishments / 1k residents"`). Sprint 4+ can revisit Unicode support after a font audit. |
| R8 | Editable-install drift: a dev's `spacescans-pipeline` checkout is on an older branch missing Sprint 2's `time.output_grouping=episode` patch. The `zcta5_cbp` runner would silently produce per-patient (not per-episode) results, breaking fan-in joins on `episode_id`. | Registry startup probe: in `variable_registry.load_variables()`, when any catalogued runner is `zcta5_cbp` (or any future episode-dispatch runner), `import spacescans.pipeline.time` and assert `hasattr(TimeConfig, 'output_grouping')`. Missing attribute raises `MetadataSchemaError(pipeline_too_old=True)` at server boot. |
| R9 | `status.json` shape migration: in-flight tasks from before Sprint 3 deploy have no `experiments` key; new consumers reading the shape need a fallback. | Frontend reads `status.experiments ?? {}` defensively. Backend `_write_status` initialises the key on first write. The flat `steps[]` field is preserved unconditionally so the legacy progress-bar consumer keeps working until every in-flight task drains. |
| R10 | Legacy `experiment` field in the request body POST shape. If the wizard container still hardcodes `experiment: "bg_ndi_wi"` after Sprint 3, the audit log is a silent lie (every multi-experiment dispatch records `bg_ndi_wi` as the requested experiment). | Frontend `api.ts` saveConfig sends `experiment: "auto"` (settled in the saveConfig disposition subsection above). Audit log emits `experiment_field_received` verbatim so the lie surfaces in logs.jsonl if any caller still sends the old literal. |

## Out of Scope / Open Questions for Sprint 4+

- **Per-variable shapefile coverage.** Sprint 3 keeps the CONUS bbox.
  Variables that legitimately exceed the contiguous US (NDI extends
  to AK+HI; some marine variables to coastal buffer zones) need
  per-variable polygon coverage. The `coverage_region` field is
  intentionally an enum today; Sprint 4 may widen it to
  `{type: "bbox" | "shapefile", value: ...}`.
- **Episode dispatch on `precomputed_areal`, `precomputed_static`,
  `cbp_fallback` linkage patterns.** Sprint 2 covered the three
  patterns in active use. New experiments may pull from precomputed
  yearly tables (no temporal aggregation); the
  `time.output_grouping` injection in `render_yaml` is a no-op for
  those patterns. Each new runner should be audited.
- **`geoid` → `episode_id` rename in the pipeline.** Sprint 2 open
  question. Touches every linkage pattern and every result schema
  consumer downstream. Out of scope until the cohort/task decoupling
  sprint.
- **Metadata UI editor.** Today: edit JSON, restart server (or wait
  for mtime cache invalidation). A `/admin/variables` page with
  edit + validate + save against `variable_metadata.schema.json`
  would let non-engineers add variables. Defer until the catalog
  exceeds ~20 entries.
- **C3 cache LRU cap.** Cache grows linearly with unique (cohort ×
  boundary × buffer × raster) tuples. Sprint 4+ adds an LRU eviction
  policy and a `du`-based startup warning.
- **Frontend test framework.** No jest/vitest config exists today.
  The Variables-step refactor is large enough to motivate adding
  one; deferred for Sprint 3 to keep scope contained.
- **Multi-experiment parallel spawn.** Requires (a) shrinking
  `.run_lock` scope from orchestrator-lifetime to per-step, (b)
  proving DuckDB engine + R session can coexist with separate data
  dirs per runner. Out of scope here.
- **Legacy gitignored metadata cleanup.** Sprint 4 follow-up:
  `find . -name variable_metadata.json -not -path "*/app/data/*"` on
  every dev machine to confirm no stale copies survive.

## Implementation Estimate

| Component | New / Modified LOC |
|---|---:|
| `variable_metadata.json` move + schema_version + new entry | +50 |
| `variable_metadata.schema.json` | +80 |
| `variable_registry.py` | +120 |
| `task_manager.start_task` dispatch loop | ~80 |
| `task_manager.compute_coverage` registry rewire | ~20 |
| `experiments/zcta5_cbp.py` | ~280 |
| `experiments/_merge.py` + `bg_ndi_wi` reshim | ~80 |
| `routers/variables.py` + main.py wiring | ~25 |
| Backend tests (5 files) | ~350 |
| Backend integration tests (2 files) | ~200 |
| `frontend/src/lib/api.ts` | ~30 |
| `variables-step.tsx` rewrite | ~150 |
| `variable-card.tsx` extraction | ~60 |
| `variable-coverage-panel.tsx` minor | ~15 |
| `review-step.tsx` refactor | ~40 |
| `manual_e2e.md` Sprint 3 section | ~40 |
| **Total** | **~1620** |

Wall-clock estimate: **4 focused work days — the upper bound of the
3-4 day brainstorm range; expect to slip to 5 if Risk R1 (pyreadr)
or status.json file-locking surprises land**. Split as 1d
registry+schema+endpoint, 1d zcta5_cbp runner + `_merge` extraction +
dispatch loop (incl. supervisor subprocess), 1d frontend rewrite, 1d
tests + smoke + cleanup.

## Phase Sequencing

Sprint 3 spans **spacescans-web + spacescans-pipeline env config**
(re-classified from "single-repo" — the `pyreadr` install step is a
cross-env dependency edit equivalent to Sprint 2's Phase A). No code
changes land in `spacescans-pipeline` itself: Sprint 2's
`time.output_grouping=episode` patch is the only pipeline-level
contract this sprint relies on, and that already shipped.

### Phase A: spacescans-pipeline env config

1. Verify `pyreadr` is declared in
   `spacescans-pipeline/pyproject.toml` under `[project.optional-dependencies]
   rda` with a pinned version (currently asserted; confirm at PR
   time).
2. Add `pyreadr` to the spacescans-pipeline CI extras matrix so
   the upstream test suite covers the `.Rda` reader path.
3. `pip install -e '.[rda]'` in the spacescans-pipeline env on every
   dev machine and the deploy host; document in
   `spacescans-pipeline/README.md` and the spacescans-web bootstrap
   doc.
4. Defence-in-depth (in spacescans-web): `variable_registry.load_variables()`
   probes `spacescans._extras.require('rda', 'pyreadr')` at server
   boot whenever any catalogued experiment maps to a runner that
   reads `.Rda` files (`zcta5_cbp` qualifies). Failure raises
   `MetadataSchemaError` at startup rather than mid-run.

### Phase B: spacescans-web

1. Pre-flight check: confirm `buffer270mZCTA525m_demo100k.parquet`
   exists at the path called out in R2; confirm
   `spacescans-pipeline/configs/c4/zcta5_cbp_demo.yaml` exists (per
   the parquet → column unpacking pre-flight in the runner section).
2. Create branch `feat/sprint-3-variables-driven-ui-zcta5-cbp` (or
   worktree).
3. Land registry + schema + endpoint first; verify
   `/api/variables` returns the 3-entry catalog with `curl`.
4. Land `_merge.py` extraction + Sprint 2 integration test still
   green (the regression checkpoint).
5. Land `zcta5_cbp.py` runner + its unit tests.
6. Land `task_manager.start_task` dispatch loop + its dispatch unit
   tests + the two new integration tests.
7. Land frontend refactor; manual_e2e Sprint 3 walk-through.
8. Sprint 3 wrap-up.
