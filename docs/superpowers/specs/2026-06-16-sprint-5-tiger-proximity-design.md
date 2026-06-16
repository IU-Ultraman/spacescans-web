# Sprint 5: TIGER Road Proximity (`precomputed_areal` Episode Dispatch) — Design Spec

## Background

Sprint 3 landed the variables-driven UI plus `zcta5_cbp`, validating
that adding a new variable now collapses to (a) a JSON entry under
`backend/app/data/variable_metadata.json`, (b) a runner file at
`backend/app/experiments/<exp_key>.py`, and (c) zero edits to the
dispatcher, registry, or wizard. Sprint 4 audited the remaining
linkage patterns and shipped follow-up cleanups but left
`precomputed_areal` untouched: no catalogued variable used it yet.

The `tiger_roads` experiment changes that. Its C4 step is the first
`precomputed_areal` consumer to enter the web UI:

- C3 (`linkage_pattern: tiger_proximity`) is point-based — one row
  per (patient-episode point, year) carrying distances to the
  nearest TIGER/Line primary, secondary, and primary+secondary
  road lines.
- C4 (`linkage_pattern: precomputed_areal`) consumes that parquet
  and produces a duration-weighted average distance per cohort row.

Sprint 2's Phase A added `time.output_grouping` dispatch to
`yearly_areal_linkage.py`. `precomputed_areal_linkage.py` was
deliberately skipped (no catalogued variable read it). TIGER changes
that — without the same patch the runner silently regresses to
patient-level aggregation and breaks the (pid, episode_id) join in
`_merge.write_partial`.

Sprint 5 is therefore a Sprint 2-style two-phase change scoped to
exactly one linkage pattern and exactly one new variable:

- **Phase A (`spacescans-pipeline`)** — extend
  `precomputed_areal_linkage.py` with the same `output_grouping`
  dispatch yearly_areal got in Sprint 2.
- **Phase B (`spacescans-web`)** — add the `tiger_proximity` runner
  and metadata entry; no dispatcher, registry, or wizard changes.

The payoff matches Sprint 3: future `precomputed_areal` variables
(Sprint 6+ for `nhd_bluespace`, `noise`, `temis`, `vnl`) inherit
episode dispatch for free.

## Goal

Land the third end-to-end experiment runner — TIGER road proximity
on BG-tagged cohort points — by extending `precomputed_areal` with
`output_grouping` dispatch (Phase A) and registering a single new
`tiger_proximity` variable (Phase B). Prove that the dispatcher +
registry + merge chain stays unchanged when a third runner type
arrives.

## Scope

### In scope (Sprint 5)

- [B1] Phase A: extend
  `src/spacescans/linkage/precomputed_areal_linkage.py:114-121` with
  an `output_grouping` branch. `'patient'` → today's behaviour
  (`SELECT PATID, … GROUP BY PATID`). `'episode'` →
  `SELECT PATID, geoid, … GROUP BY PATID, geoid`. Any other value
  raises `ValueError(f"unsupported output_grouping: …")` mirroring
  `yearly_areal_linkage.py:47-58`.
- [B2] Phase A: add unit tests under
  `tests/test_precomputed_areal_linkage.py` covering both branches
  plus the ValueError path.
- [B3] Phase A: update `configs/c4/tiger_roads_demo.yaml:20-23` time
  block to declare `output_grouping: episode` so the CLI smoke run
  continues to match the web runner's contract.
- [B4] Phase B: new variable entry `tiger_proximity` in
  `backend/app/data/variable_metadata.json` (boundary `BG`,
  `value_cols: [dist_pri, dist_sec, dist_prisec]`, `display_unit:
  meters`, `coverage_years: [2013, 2019]`).
- [B5] Phase B: new runner
  `backend/app/experiments/tiger_proximity.py` (~290 LOC, cloned
  from `bg_ndi_wi.py`). Two-step plan (C3 + C4) — both per-task,
  because the shipped `annual_proximity_demo100k.parquet` is bound
  to the demo cohort and CAN NOT be reused for arbitrary uploads.
- [B6] Phase B: lift `_BOUNDARY = "BG"` cache namespace into a
  step-specific tag — the new runner uses `_BOUNDARY = "BG_TIGER"`
  to avoid colliding with the BG NDI/Walkability cache key for the
  same input parquet + buffer.
- [B7] Phase B: in `tiger_proximity.render_yaml`, also rewrite
  `cfg["exposure"]["file"]` on the C4 template so it points at the
  per-task C3 output (the `precomputed_areal` linkage_pattern is the
  only one that reads a per-task C3 parquet at C4 time).
- [B8] Phase B: shared merge integration — runner's `merge_results`
  is a 3-line wrapper into `_merge.write_partial(...,
  experiment_key="tiger_proximity", parquet_map={…})`.
- [B9] Phase B: unit + integration tests
  (`backend/tests/test_tiger_proximity.py`,
  `backend/tests/test_e2e_tiger_proximity_cohort.py`,
  `backend/tests/test_e2e_multi_experiment_with_tiger.py`).
- [B10] Phase B: `backend/tests/manual_e2e.md` gains a Sprint 5
  section covering the new variable on the demo cohort and the
  three-experiment dispatch path.

### Out of scope (deferred)

- **G1.** The remaining 5 experiments
  (`nhd_bluespace`, `vnl`, `temis`, `noise`, `fara_tract`,
  `county_cbp`). Sprint 6+.
- **G2.** Frontend code changes. The
  `tiger_proximity` variable renders in the existing "Block Group"
  section with no edits to `variables-step.tsx`,
  `variable-card.tsx`, `variable-coverage-panel.tsx`, or
  `variable-grouping.ts`. Sprint 5 verifies (not modifies) this
  invariant per the frontend research.
- **G3.** Per-`value_col` `display_unit`. The wizard renders a single
  unit chip; "meters" covers all three TIGER distance columns
  unambiguously. A future variable with mixed units would need
  schema+UI changes at `api.ts:115` and `variable-card.tsx:26`;
  Sprint 5 documents the coupling and defers the change.
- **G4.** Per-column tooltip / result preview surfaces. No frontend
  consumer reads `VariableMetadata.value_cols` today; building one
  is Sprint 6+.
- **G5.** Cohort-coverage gating for the `tiger_proximity` variable
  on the wizard. The cohort-coverage panel still uses the same
  bbox-based CONUS check Sprints 1-4 use; per-county TIGER zip
  availability is a runtime concern surfaced via the runner's log
  output, not the coverage UI.
- **G6.** `precomputed_static` / `precomputed_areal_yearly_extrapolation` /
  `cbp_fallback` `output_grouping` dispatch. Sprint 2 covered
  `yearly_areal` + `yearly_areal_bg_vintage` + `static_areal`;
  Sprint 5 covers `precomputed_areal` (this sprint's variable);
  remaining patterns are Sprint 6+.
- **G7.** Disposition of the legacy
  `annual_proximity_demo100k.parquet` fixture. The file is
  cohort-bound (geoid 0..99999 maps to one specific demo cohort) and
  ships at a path that overlaps the web runner's per-task output
  namespace. Sprint 5 leaves it in place (CLI smoke tests depend on
  it — confirmed via `tests/test_pipeline_smoke.py`) and adds a
  README warning rather than reorganising fixtures.
- **G8.** Renaming the synthetic `geoid` column to `episode_id` in
  the pipeline. Sprint 2/3 open question; still out of scope. The
  `_merge.write_partial` rename map handles the column at the
  spacescans-web boundary.
- **G9.** TIGER `coverage_years` upgrade past `[2013, 2019]`. Matches
  the CLI YAML literally; broader TIGER/Line vintages exist but are
  not exercised by any shipped config and would risk YAML drift
  without a corresponding test.
- **G10.** Multi-experiment parallel spawn. Sprint 3 deferral still
  applies; Sprint 5 adds a third runner under the same sequential
  dispatcher with the same orchestrator-lifetime `.run_lock`.

## Architecture

```text
   spacescans-pipeline (Phase A)
   precomputed_areal_linkage.py
     if output_grouping == 'patient':   SELECT PATID,        … GROUP BY PATID
     elif      == 'episode':            SELECT PATID, geoid, … GROUP BY PATID, geoid
     else: raise ValueError(...)
                       │
                       ▼  C4 emits per-episode rows
   spacescans-web (Phase B)
   experiments/tiger_proximity.py
     plan() → [c3_tiger_roads, c4_tiger_roads]
     render_yaml: rewrite exposure.file for c4 step
     _BOUNDARY = "BG_TIGER"  (cache namespace)
     merge_results → _merge.write_partial(
       experiment_key="tiger_proximity",
       parquet_map={"tiger_proximity": "c4_tiger_roads.parquet"})
                       │
                       ▼
   variable_metadata.json adds 1 entry → GET /api/variables returns 4 entries
   Variables-step renders 4 BG cards (NDI, Walkability, TIGER Roads) + 1 ZCTA5
```

The fan-out / fan-in chain (Sprint 3 architecture) is unchanged.
`tiger_proximity` is the third experiment key; the dispatcher
discovers it via `variable_registry._discover_experiments()`
globbing `backend/app/experiments/*.py` — no dispatcher edits.

### Architectural choices and rationale

- **Phase A first, Phase B depends on it.** The web runner emits
  `time.output_grouping: episode` in its rendered YAML. Without
  Phase A live in the runner's pipeline env, the C4 step silently
  aggregates to PATID-level and `_merge.write_partial`'s
  episode-id join either collapses rows or matches nothing. Phase
  A's smoke (and the runner-side sanity probe, R3) catches this.
- **Episode dispatch via SQL branch, not via TemporalAggSpec.**
  yearly_areal threads `group_by_keys` into a `TemporalAggSpec`
  object; `precomputed_areal_linkage.py:68-123` does NOT route
  through any `*Spec` object — it runs raw SQLite SQL strings.
  Sprint 5 mirrors yearly_areal's *conditional* but implements it
  as a `SELECT … GROUP BY` clause edit at the terminal SQL, not a
  `group_by=[...]` list.
- **Hard-require an explicit `output_grouping` value when routing
  through `precomputed_areal` in any cataloged YAML.** Sprint 2's
  precedent at `yearly_areal_linkage.py:47-58` rejects unknown
  string values with `ValueError`, but `TimeConfig.output_grouping`
  at `src/spacescans/models/config.py:100` is declared
  `output_grouping: str = "patient"` — so a *missing* YAML key
  inherits the dataclass default and silently routes to the
  `'patient'` branch (the same is true in the new
  `precomputed_areal` dispatch). The ValueError fires only on an
  *explicitly invalid* string. Cost: every shipped config that
  routes through `precomputed_areal` needs `output_grouping`
  declared so reviewers see the choice. Audit: `grep -rn
  "linkage_pattern: precomputed_areal" configs/` returns exactly one
  hit (`configs/c4/tiger_roads_demo.yaml`) which gets the same
  one-line edit in Phase A. Optionally consider tightening the
  default to `Optional[str] = None` in a follow-up sprint so that
  a missing key raises rather than defaulting — this is a breaking
  change to `TimeConfig` that ripples across all linkage patterns
  (yearly_areal, yearly_areal_bg_vintage, static_areal,
  precomputed_areal), so call that out explicitly if pursued.
- **Boundary cache namespace `BG_TIGER`, not `BG` — defence in
  depth against future drift.** `bg_ndi_wi` and `tiger_proximity`
  both have `boundary: BG` in metadata, but emit incompatible C3
  parquet schemas: bg_ndi_wi writes `(PATID, bg_geoid, weight)`
  raster-sampling weights; tiger_proximity writes `(geoid, year,
  dist_pri, dist_sec, dist_prisec)` point-grain distances. The two
  cache-key shapes already diverge today (bg_ndi_wi carries
  `__r{raster}m`; tiger_proximity does not), so a same-`_BOUNDARY`
  value would NOT collide given the present-day shapes. The
  collision only materialises if a future maintainer drops the
  raster suffix from bg_ndi_wi or adds a raster suffix to
  tiger_proximity; the distinct `BG_TIGER` tag insulates against
  that drift. The new runner uses `_BOUNDARY = "BG_TIGER"`;
  bg_ndi_wi's `"BG"` constant stays put and its existing cache
  hits keep firing.
- **C3 step is mandatory, not optional.** The shipped
  `annual_proximity_demo100k.parquet` (10.4M, 700k rows, geoid
  0..99999) is bound to the 100k demo cohort: its `geoid` column
  is the per-patient episode id baked at C3 time
  (`tiger_proximity_linkage.py:174` emits `"geoid":
  patients[config.buffer.geoid_col].values`). A user-uploaded
  cohort with a different episode_id 0..N range would either match
  nothing or silently match row 0 to demo patient #0's road
  distances. The runner re-runs C3 per task; the cohort-independent
  `cache/C3/tiger_roads_filtered/` sub-cache (per-(state, county,
  year) filtered shapefiles) keeps subsequent same-county runs
  fast.
- **`render_yaml` rewrites `exposure.file` for c4_tiger_roads.**
  The C4 template's `exposure.file` literal points at the shipped
  demo parquet. The runner MUST rewrite that field to the per-task
  C3 output. This is a new render_yaml behaviour not exercised by
  bg_ndi_wi or zcta5_cbp (both leave `exposure.file` alone — it
  points at raster files or pre-built tables that all cohorts
  share). Sprint 5 codifies the rewrite inside
  `tiger_proximity.render_yaml`; the other two runners are
  untouched.
- **One variable, three columns.** The wizard UI is fully
  `value_cols`-agnostic outside the type declaration at
  `api.ts:116`. A single `tiger_proximity` variable emitting
  `[dist_pri, dist_sec, dist_prisec]` renders as one card with one
  unit chip ("meters"); the merge step picks up all three columns
  from `value_cols`. Splitting into three variables would triple
  cache pressure for zero UI gain.
- **`coverage_years: [2013, 2019]` matches YAML literally.**
  `configs/c3/tiger_roads_demo.yaml:15` and
  `configs/c4/tiger_roads_demo.yaml:21` both list 2013-2019. The
  metadata range follows verbatim; Sprint 5 does not widen it
  without a corresponding YAML update.

## Phase A: `precomputed_areal_linkage.py` output_grouping dispatch

### Today's code

`src/spacescans/linkage/precomputed_areal_linkage.py:114-121`:

```python
result = pd.read_sql(
    f"""
    SELECT PATID, {', '.join(twa_selects)}
    FROM patient_year
    GROUP BY PATID
    """,
    con,
)
```

The terminal aggregation is hard-coded to `GROUP BY PATID`. The
`patient_year` CTE (lines 80-104) already carries a `v.geoid`
column from the per-patient overlap join, so a `(PATID, geoid)`
group key is available at zero schema cost — the SQL change is the
only edit needed at this site.

There is no reference to `config.time.output_grouping` anywhere in
the file. The only attribute read off `config.time` is `years` at
line 42 (`year_range = list(config.time.years)`). `TimeConfig` is
the same dataclass used by `yearly_areal_linkage.py:50`, so the
`output_grouping` field is already defined on `config.time` — only
the linkage code needs to consume it.

`DurationWeightedSpec` at `src/spacescans/models/specs.py:51-58`
has a `group_by_episode: bool = False` flag, but
`precomputed_areal_linkage.py` does not import `specs` and does not
route through any `*Spec` object. The Phase A change is therefore
SQL-string-level only; no `*Spec` field is added or wired.

### Target code

Mirror Sprint 2's dispatch shape (the same conditional pattern from
`yearly_areal_linkage.py:47-58`), applied as an SQL clause edit:

```python
# precomputed_areal_linkage.py — replace lines 114-121

if config.time.output_grouping == "patient":
    select_keys = "PATID"
    group_keys = "PATID"
elif config.time.output_grouping == "episode":
    select_keys = "PATID, geoid"
    group_keys = "PATID, geoid"
else:
    raise ValueError(
        f"unsupported output_grouping: {config.time.output_grouping!r} "
        f"(expected 'patient' or 'episode')"
    )

result = pd.read_sql(
    f"""
    SELECT {select_keys}, {', '.join(twa_selects)}
    FROM patient_year
    GROUP BY {group_keys}
    """,
    con,
)
```

Notes:

- The `patient_year` table already carries a `geoid` column (line 80
  inner SELECT: `v.geoid`). The episode branch's `geoid` IS the
  patient-episode's geoid that the overlap join was keyed on; there
  is no separate "exposure-table geoid" to choose between — they are
  the same column after the join.
- The two-branch literal SQL is more auditable than an f-string
  interpolation that splices `output_grouping` into the column list;
  the SQL footprint is tiny and reviewers can read the GROUP BY
  intent at a glance.
- The ValueError message string matches `yearly_areal_linkage.py:55-58`
  byte-for-byte (modulo the file name in any traceback context),
  so downstream test assertions that grep for "unsupported
  output_grouping" across the spacescans tests catch both linkage
  patterns uniformly.
- `tiger_roads` reader plugin needs zero modification: the C3
  parquet's `geoid` column is already int64 and the precomputed_areal
  cast at lines 52-53 already coerces both sides to int64.

### Pipeline unit test plan

`tests/test_precomputed_areal_linkage.py` (NEW, ~80 LOC, three
tests):

1. `test_precomputed_areal_groups_by_patid_when_output_grouping_patient`
   — regression lock for today's behaviour; columns
   `[PATID, dist_pri, dist_sec, dist_prisec]`; `df["PATID"].is_unique`.
2. `test_precomputed_areal_groups_by_patid_geoid_when_episode` —
   Sprint 5 new branch; columns `[PATID, geoid, dist_pri, dist_sec,
   dist_prisec]`; `df.groupby(["PATID", "geoid"]).size().max() == 1`.
3. `test_precomputed_areal_rejects_unknown_output_grouping` —
   typo-catch test: constructs a config with
   `output_grouping="foo"` (an explicitly *unknown* value, not an
   omitted key — `TimeConfig.output_grouping` defaults to
   `"patient"` so a missing key never reaches the `else` branch);
   asserts `pytest.raises(ValueError,
   match="unsupported output_grouping")`.

A `make_demo_config` fixture builds the minimal TimeConfig +
BufferConfig + ExposureConfig + OutputConfig pointing at
`tests/fixtures/precomputed_areal_mini.parquet` (~10 rows, two
multi-episode patients; ~2K bytes committed).

Smoke run: `pytest -k "precomputed_areal or tiger_roads"`.

**Smoke fixture caveat.** The shipped 100k demo cohort has
`geoid = episode_id = range(100_000)` — every patient maps to a
single geoid — so a naive switch from
`SELECT PATID GROUP BY PATID` to
`SELECT PATID, geoid GROUP BY PATID, geoid` produces the same
100,000 rows under both branches. An assertion that only counts
distinct `(PATID, geoid)` pairs would silently pass even if the
episode branch were buggy. Sprint 5 resolves this in one of two
ways (choose at implementation time; document the choice in the
PR description so reviewers see why the row-count delta is
non-zero):

  (a) Leave `configs/c4/tiger_roads_demo.yaml` at
      `output_grouping: patient` for the CLI-only smoke (the web
      runner overrides via `render_yaml` anyway, per Phase B's
      `cfg["time"]["output_grouping"] = "episode"` line) and add a
      separate explicit-episode CLI smoke variant whose fixture
      has at least one patient with multiple episodes. The CLI
      smoke then asserts `len(out) == 100_000` (patient branch)
      and the new variant asserts
      `count(distinct (PATID, geoid)) > count(distinct PATID)`.
  (b) Extend the demo cohort fixture so a handful of PATIDs map
      to multiple geoid values, switch the demo YAML to
      `output_grouping: episode`, and assert
      `count(distinct (PATID, geoid)) > count(distinct PATID)`.

The unit-test fixture (`tests/fixtures/precomputed_areal_mini.parquet`)
ALREADY satisfies this — its two multi-episode patients give the
episode branch a strictly higher row count than the patient
branch — so the three unit tests above are unaffected by the
choice; only the end-to-end demo smoke is.

## Phase B: web experiment runner `tiger_proximity.py`

### Module shape

```python
# backend/app/experiments/tiger_proximity.py

from app.experiments import _merge
from app.experiments.bg_ndi_wi import (
    PipelineStep, _append_log, parse_step_progress, run_pipeline_step,
)

_VARIABLE_TO_STEP = {
    "tiger_proximity": PipelineStep(
        name="c4_tiger_roads",
        template_relpath="c4/tiger_roads_demo.yaml",
        is_c3=False,
    ),
}
_C3_STEP = PipelineStep(
    name="c3_tiger_roads",
    template_relpath="c3/tiger_roads_demo.yaml",
    is_c3=True,
)
_BOUNDARY = "BG_TIGER"     # cache-key namespace; distinct from bg_ndi_wi's "BG"
_EXPERIMENT_KEY = "tiger_proximity"
_PARQUET_MAP = {"tiger_proximity": "c4_tiger_roads.parquet"}
```

### `plan(config)` — two-step plan, always

```python
def plan(config: dict) -> list[PipelineStep]:
    """Always emits [c3_tiger_roads, c4_tiger_roads].

    tiger_proximity has a single variable with three value_cols emitted by a
    single C4 parquet — so the plan is deterministic.
    """
    variables = config.get("variables", [])
    if not variables:
        raise ValueError("at least one variable must be selected")
    unknown = [v for v in variables if v not in _VARIABLE_TO_STEP]
    if unknown:
        raise ValueError(f"unknown variable(s): {', '.join(unknown)}")
    return [_C3_STEP, _VARIABLE_TO_STEP["tiger_proximity"]]
```

### `render_yaml` — C4 exposure rewrite

Two structural differences from `bg_ndi_wi.render_yaml` /
`zcta5_cbp.render_yaml`:

1. **No `raster_res_m` injection** — TIGER templates have no
   `raster_res_m` under `buffer:` (matches `zcta5_cbp`); `_cache_key`
   omits raster too.
2. **C4 step rewrites `cfg["exposure"]["file"]`** to point at the
   per-task C3 output — the template's literal exposure path is the
   shipped demo parquet, which per-task runs MUST replace.

```python
def render_yaml(step: PipelineStep, task_dir: Path, user_config: dict) -> Path:
    template_path = (
        app.config.settings.SPACESCANS_CONFIG_TEMPLATES_DIR / step.template_relpath
    )
    cfg = yaml.safe_load(template_path.read_text())

    task_id_short = task_dir.name[-8:]
    cfg["name"] = f"{cfg['name']}_task_{task_id_short}"
    cfg["buffer"]["patient_file"] = str(task_dir / "input.parquet")
    cfg["buffer"]["buffer_m"] = user_config["buffer"]["size"]
    # NOTE: no raster_res_m write (template has no such key).

    if step.is_c3:
        # C3: nothing extra to wire; pipeline's road_cache_dir is
        # already cohort-independent in the template.
        pass
    else:
        # C4: rewrite exposure.file to point at the per-task C3 output,
        # so this C4 reads the parquet produced by this task's C3 step.
        cfg["exposure"]["file"] = str(
            task_dir / "output" / f"{_C3_STEP.name}.parquet"
        )

    if "time" in cfg:
        cfg["time"]["output_grouping"] = "episode"   # Sprint 5 Phase A contract
    cfg["output"]["path"] = str(task_dir / "output" / f"{step.name}.parquet")

    out = task_dir / "pipeline_configs" / f"{step.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out
```

### `_cache_key` — no raster, boundary-namespaced

```python
def _cache_key(input_parquet: Path, step: PipelineStep, user_config: dict) -> str:
    """Format: ``<sha8>__BG_TIGER__b<buffer>m``.

    Omits raster_res_m (template has no raster field). Boundary tag
    BG_TIGER avoids collision with bg_ndi_wi's BG cache for the same
    input parquet + buffer.
    """
    sha = _hash_input_parquet(input_parquet)
    buf = user_config["buffer"]["size"]
    return f"{sha[:8]}__{_BOUNDARY}__b{buf}m"
```

(`_hash_input_parquet` is copied verbatim from `zcta5_cbp.py`.)

### `merge_results` — delegates to `_merge.write_partial`

```python
def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Delegate to the shared _merge.write_partial.

    The _PARQUET_MAP carries a single entry (tiger_proximity → one parquet);
    the merge picks up all three value_cols (dist_pri, dist_sec, dist_prisec)
    from the variable_metadata.json entry via variable_registry.get_variable.
    """
    parquet_map = {v: _PARQUET_MAP[v] for v in variables}
    return _merge.write_partial(
        task_dir=task_dir,
        experiment_key="tiger_proximity",
        variables=variables,
        parquet_map=parquet_map,
    )
```

The `_merge.write_partial` body itself is unchanged from Sprint 3 —
it reads `value_cols` from `variable_registry.get_variable(key)`,
selects those plus the rename keys, joins on `(pid, episode_id)`,
and writes `result_tiger_proximity.csv`.

### `run(task_dir, variables=None)` and `_cli_main`

Structurally identical to `zcta5_cbp.run` / `zcta5_cbp._cli_main`
modulo the four module-level constants. Runner: SIGTERM handler →
acquire `.run_lock` → read config + apply dispatcher override →
`plan()` → per-step `render_yaml` + `run_pipeline_step` + slot
progress update → `merge_results` → terminal slot status → release
lock. The CLI argv shape
`python -m app.experiments.tiger_proximity run <task_dir>
--variables tiger_proximity` matches `bg_ndi_wi.py:621-635` and
`zcta5_cbp.py:434-448` byte-for-byte except for the parser `prog=`
field.

### Differences from `bg_ndi_wi.py` and `zcta5_cbp.py`

| Aspect | `bg_ndi_wi` | `zcta5_cbp` | `tiger_proximity` (new) |
|---|---|---|---|
| Linkage pattern (C4) | `yearly_areal` | `yearly_areal` | `precomputed_areal` |
| C3 step | `c3_bg` (boundary_overlap_fast) | `c3_zcta5` (boundary_overlap_fast) | `c3_tiger_roads` (tiger_proximity) |
| C4 reads exposure file via | raster | `.Rda` (pyreadr) | per-task C3 parquet |
| `render_yaml` rewrites `exposure.file`? | no | no | **yes** (C4 only) |
| `render_yaml` injects `raster_res_m`? | yes (C3) | no | no |
| `_BOUNDARY` cache tag | `"BG"` | `"ZCTA5"` | `"BG_TIGER"` |
| `_cache_key` shape | `<sha8>__BG__b{buf}m__r{raster}m` | `<sha8>__ZCTA5__b{buf}m__r{raster}m` | `<sha8>__BG_TIGER__b{buf}m` (no raster) |
| Variables per runner | 2 (NDI, Walkability) | 1 (cbp_zcta5) | 1 (tiger_proximity, 3 value_cols) |
| C4 parquets per run | one per variable | one (10 columns) | one (3 columns) |

The two structural deltas requiring genuinely new logic are the
exposure.file rewrite (cell 5) and the no-raster cache key
(cell 8). Everything else is parameterised over module-level
constants.

## Phase B: `variable_metadata.json` entry

```json
"tiger_proximity": {
  "label": "TIGER Road Proximity",
  "description": "Per-block-group annual distance (meters) to the nearest TIGER/Line primary road (S1100), secondary road (S1200), and primary+secondary combined, from US Census TIGER/Line shapefiles.",
  "boundary": "BG",
  "coverage_years": [2013, 2019],
  "coverage_region": "CONUS",
  "experiment": "tiger_proximity",
  "variable_type": "continuous",
  "display_unit": "meters",
  "value_cols": ["dist_pri", "dist_sec", "dist_prisec"]
}
```

Schema validation passes against
`backend/app/data/variable_metadata.schema.json` v1:

- `^[a-z][a-z0-9_]*$` matches the key `tiger_proximity`.
- `boundary: BG` is in the enum (the variable's spatial dispatch is
  at point grain at C3 time, then duration-weighted-averaged in C4;
  the Block Group framing reflects how the wizard groups the card,
  not the C3 implementation).
- `coverage_years: [2013, 2019]` — minItems 2, maxItems 2, integers
  in [1900, 2100].
- `display_unit: "meters"` — ASCII printable, ≤ 50 chars.
- `value_cols: ["dist_pri", "dist_sec", "dist_prisec"]` — minItems 1.
- `experiment: "tiger_proximity"` — `^[a-z][a-z0-9_]*$` pattern AND
  matches a discoverable Python module name at
  `backend/app/experiments/tiger_proximity.py` (registry load-time
  whitelist check).

The entry is appended to the existing `variables` map at the end of
the file. Dispatch order is JSON-file order of first experiment
appearance (Sprint 3 invariant); for a `[ndi, walkability,
cbp_zcta5, tiger_proximity]` selection the dispatcher would spawn
`bg_ndi_wi` first, then `zcta5_cbp`, then `tiger_proximity`.

## Phase B: frontend changes

**None.** Per the research:

- `VariablesStep` groups by `meta.boundary` via `groupByBoundary`
  (`variable-grouping.ts:17-19`); `BG` is first in `BOUNDARY_ORDER`
  with label "Block Group" — `tiger_proximity` joins NDI and
  Walkability with zero `variables-step.tsx` edits.
- `VariableCard` (`variable-card.tsx:25-29`) renders the three
  chips (display_unit "meters", coverage range "2013–2019",
  boundary "BG") directly from `VariableMetadata` — no template
  change.
- `VariableCoveragePanel` (`variable-coverage-panel.tsx:74-75`)
  consumes only `boundary` and `coverage_years`; backend's
  registry-driven `compute_coverage` already returns both.
- `value_cols` is declared on the type (`api.ts:116`) but read
  nowhere under `spacescans-web/` — one-card-three-columns works
  out of the box.

Sprint 5 manual smoke includes a no-op verification step: visually
confirm the BG section renders three cards after the metadata
entry lands.

## Implementation order

Phase A lands on the `pkg/pypi-only` branch of the `spacescans-project`
repo (where Sprint 4's pipeline-side work currently lives). Phase B
lands on a fresh `feat/sprint-5-tiger-proximity` branch (or
worktree) of `spacescans-web`. The phase boundary is the only
pipeline-vs-web split; within each phase the order matches the
brainstorm structure.

### Phase A (spacescans-pipeline, branch `pkg/pypi-only`)

1. Pre-flight: confirm `cache/C3/tiger_roads_filtered/` exists at
   the repo root; if absent, run
   `spacescans run configs/c3/tiger_roads_demo.yaml` once to seed.
2. Edit `src/spacescans/linkage/precomputed_areal_linkage.py:114-121`
   to add the `output_grouping` dispatch (~14 new / ~8 deleted).
3. Edit `configs/c4/tiger_roads_demo.yaml` to add
   `output_grouping: episode` under the time block.
4. Add `tests/test_precomputed_areal_linkage.py` (~80 LOC, three
   tests above) and `tests/fixtures/precomputed_areal_mini.parquet`.
5. Add a new pipeline smoke test that executes
   `configs/c4/tiger_roads_demo.yaml` end-to-end and asserts the
   row count equals the count of distinct `(PATID, geoid)` pairs
   from the demo cohort. (Audit: `grep -rn
   'test_tiger_roads_demo\|tiger_roads_demo'
   /Users/xai/Desktop/spacescans-project/tests/` returns zero hits
   today — `tests/test_pipeline_smoke.py` only contains
   registry-init smoke tests, so there is no existing assertion to
   bump.) See the "Smoke fixture caveat" note under the unit-test
   plan for why this requires extending the demo cohort fixture so
   that some patients map to multiple geoid values; otherwise the
   distinct-pair count equals the patient count and the smoke
   loses its protective value.
6. Run `pytest -k "precomputed_areal or tiger_roads"` — must pass.
   Full suite — no regressions in `yearly_areal`,
   `yearly_areal_bg_vintage`, `static_areal`.
7. **Editable install dependency:** Phase B's integration tests
   require Phase A live in the runner's pipeline env. The web's
   `SPACESCANS_PIPELINE_PYTHON` points at a Python env where
   `pip install -e ../spacescans-project` reflects the pipeline
   source. If Phase A lands as a release-pin instead, bump the pin
   in `spacescans-web/backend/pyproject.toml` and re-install
   before Phase B smoke. (See Risk R3.)
8. PR title: `feat(linkage): precomputed_areal output_grouping
   dispatch (Sprint 5 Phase A)`.

### Phase B (spacescans-web, branch `feat/sprint-5-tiger-proximity`)

1. Pre-flight: verify Phase A is live in the web's pipeline env via
   `python -c "from spacescans.linkage import
   precomputed_areal_linkage; import inspect; print('episode' in
   inspect.getsource(precomputed_areal_linkage))"` — expect `True`.
2. Add the `tiger_proximity` entry to
   `backend/app/data/variable_metadata.json` (server boot will fail
   the discovery whitelist until step 3 — expected and gating).
3. Add `backend/app/experiments/tiger_proximity.py` (~290 LOC).
   Server starts; `/api/variables` returns 4 keys.
4. Add `backend/tests/test_tiger_proximity.py` (~140 LOC). Pass
   locally.
5. Add `backend/tests/test_e2e_tiger_proximity_cohort.py`
   (`@pytest.mark.integration`, ~60s).
6. Add `backend/tests/test_e2e_multi_experiment_with_tiger.py`
   (4-variable, 3-experiment dispatch on the demo cohort;
   `@pytest.mark.integration`, ~210s).
7. Update `backend/tests/manual_e2e.md` with the Sprint 5 section.
8. Manual smoke: variables-step renders 4 cards (3 BG, 1 ZCTA5);
   4-variable task produces a `result.csv` with NDI + NatWalkInd +
   10 `r_*` + 3 `dist_*` columns.
9. PR title: `feat(experiments): tiger_proximity runner +
   precomputed_areal episode dispatch (Sprint 5)`.

## Test impact

### Backend test count delta

| Test file | Status | Tests | Notes |
|---|---|---:|---|
| `backend/tests/test_tiger_proximity.py` | NEW | +8 | plan/render_yaml/cache_key/merge_results/run smoke |
| `backend/tests/test_e2e_tiger_proximity_cohort.py` | NEW | +1 | single-experiment integration (demo cohort) |
| `backend/tests/test_e2e_multi_experiment_with_tiger.py` | NEW | +1 | 4-variable, 3-experiment dispatch |
| `backend/tests/test_variable_registry.py` | MODIFIED | +1 | "registry accepts tiger_proximity entry" |
| `backend/tests/test_task_manager_dispatch.py` | MODIFIED | +1 | "three-experiment dispatch preserves metadata order" |
| `backend/tests/test_merge_partial.py` | MODIFIED | +1 | "value_cols selection picks 3 TIGER columns from one parquet" |

Backend net: +13 tests across 3 new + 3 modified files. Two
integration tests are `@pytest.mark.integration` and skipped by
default; the other 11 run in the default suite (~3s additional
wall-clock).

### Pipeline test count delta

| Test file | Status | Tests | Notes |
|---|---|---:|---|
| `tests/test_precomputed_areal_linkage.py` | NEW | +3 | patient/episode/ValueError branches |
| `tests/test_pipeline_smoke.py` (new `tiger_roads_demo` end-to-end smoke) | NEW | +1 | asserts row count = distinct (PATID, geoid) pairs; no prior assertion existed |
| `tests/test_yearly_areal_linkage.py` | UNCHANGED | 0 | confirms Sprint 2 dispatch still passes |

Pipeline net: +4 tests.

## Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Future C3 cache key collision between `bg_ndi_wi` and `tiger_proximity`.** The two key shapes already diverge today (bg_ndi_wi: `<sha8>__BG__b{buf}m__r{raster}m`; tiger_proximity: `<sha8>__BG_TIGER__b{buf}m` — no raster suffix), so no collision exists at landing time. However, a future shape change (raster dropped from bg_ndi_wi, or raster added here) under a shared `_BOUNDARY = "BG"` would re-introduce the collision; the second runner would then read the first's parquet with the wrong schema and exit 0 (silent corruption). | New runner uses `_BOUNDARY = "BG_TIGER"` as defence in depth. `test_tiger_proximity.py::test_cache_key_differs_from_bg_ndi_wi_in_shape_and_boundary` asserts the two `_cache_key` outputs differ in both the boundary tag *and* the overall shape for the same `(input_parquet, buffer)`. |
| R2 | **TIGER C3 data versioning.** Per-county TIGER zips at `data_full/TIGER/C4/tiger{year}_roads/tl_{year}_{cnty}_roads.zip` are required for any per-task C3 run; missing files fail late after lock acquisition. | Server-boot pre-flight in `variable_registry.load_variables()`: if `tiger_proximity` is catalogued, assert `Path(SPACESCANS_DATA_DIR / "TIGER" / "C4").is_dir()` and that at least one `tiger{year}_roads/` subdir exists for each year in `coverage_years`. Missing → `raise MetadataSchemaError(f"tiger_proximity catalogued but TIGER data missing at {path}")` at startup, not runtime (string-only constructor matches the existing call pattern at `variable_registry.py:51, 57, 86, 94`). |
| R3 | **Pipeline editable-install drift between Phase A and Phase B.** The web runner subprocess uses `SPACESCANS_PIPELINE_PYTHON`; a stale wheel ignores the new `output_grouping: episode` field, silently emits patient-level rows, and `_merge.write_partial` collapses one-to-many on episode_id. | Three layers: (a) Phase A pyproject bump publishes a new wheel; web's pin moves forward in the same PR. (b) `tiger_proximity._sanity_check_pipeline_supports_precomputed_areal_episode()` imports `precomputed_areal_linkage` at runner start and greps its source for `'episode'`; raises `RuntimeError` if absent. (c) `_merge.write_partial`'s existing `merge_partial_low_match_pct` log signals catches silent regressions if (a) and (b) both fail. |
| R4 | **render_yaml's `exposure.file` rewrite breaks if a future C4 template uses a non-dict `exposure` shape.** | Guard with `isinstance(cfg.get("exposure"), dict)`; otherwise raise `RuntimeError("tiger_proximity.render_yaml: unexpected exposure: shape")`. |
| R5 | **`annual_proximity_demo100k.parquet` foot-gun.** Fixture's `geoid` column is per-patient episode_id 0..99999, bound to the demo cohort. A future cache keying on `(boundary, year, geoid)` could serve it to a non-demo cohort. | Leave in place (CLI smoke tests depend on it); add a one-line README warning under `output/python_v2/270m/TIGER/C3/README.md`. Sprint 6+ may relocate to `fixtures/`. |
| R6 | **Phase A's ValueError changes the failure mode of any other call site that explicitly passes an unknown `output_grouping` string through `precomputed_areal`.** A *missing* key still inherits the `TimeConfig.output_grouping = "patient"` default (`src/spacescans/models/config.py:100`) and silently routes to the patient branch; the ValueError fires only on an explicitly invalid value. | Audit: `grep -rn "linkage_pattern: precomputed_areal" configs/` returns exactly one hit (`configs/c4/tiger_roads_demo.yaml`), patched in Phase A step 3 to declare `episode` explicitly. No other in-tree call sites. Notebook users supplying a typo'd value get a clear ValueError with both legal values named. (A future sprint may tighten the dataclass default to `None` so absent keys also raise; out of scope here.) |
| R7 | **Three-experiment integration test wall-clock ~210s.** | `@pytest.mark.integration`; runs only on `make test-integration` or nightly CI. Default suite adds ~3s for the 11 unit tests. |
| R8 | **`tiger_proximity` is BG-tagged in metadata but runs at point grain in C3.** Users may expect BG-centroid aggregation. | Description string says "Per-block-group annual distance (meters) to the nearest TIGER/Line primary road…" verbatim. Sprint 6+ may add a `granularity: point \| polygon` field. |
| R9 | **C3 per-task wall-clock on small uploads is dominated by per-county shapefile filtering, not cohort size.** First 10-row cohort takes ~50s on a cold `cache/C3/tiger_roads_filtered/`; second over the same counties takes ~3s. | Cohort-independent cache survives across tasks; document on the variable card if first-task latency becomes a support burden. |
| R10 | **`exposure.file` rewrite is a structural divergence from the other two runners.** Future maintainer might generalise it incorrectly. | Rewrite is gated `if step.is_c3` inside `tiger_proximity.render_yaml`; bg_ndi_wi / zcta5_cbp render_yaml bodies untouched. Docstring on `_C3_STEP` notes the C4 step reads its parquet output. |

## Out of scope / open questions for Sprint 6+

- **G1.** Onboarding the next `precomputed_areal` variable. Once
  Phase A lands, candidates `nhd_bluespace`, `vnl`, `noise`,
  `temis` each collapse to a runner clone + metadata entry —
  Phase A is done.
- **G6.** `precomputed_static` and `cbp_fallback`
  `output_grouping` dispatch; neither is read by a catalogued
  variable today.
- **G3.** Per-`value_col` `display_unit` — requires
  `api.ts:115` + `variable-card.tsx:26` changes.
- **G4.** Per-column tooltip / result preview surfaces — would read
  `VariableMetadata.value_cols`; no consumer today.
- **TIGER vintage widening** past `[2013, 2019]` — requires upstream
  YAML widening + per-county zip availability audit.
- **Per-county shapefile coverage gating** — would replace
  bbox-CONUS check with "your cohort includes N counties whose
  TIGER {year} zip is missing".
- **Multi-experiment parallel spawn** — still blocked by
  `.run_lock` orchestrator-lifetime scope and DuckDB + workspace
  contention.

## Implementation estimate

| Component | New / Modified LOC |
|---|---:|
| **Phase A** | |
| `src/spacescans/linkage/precomputed_areal_linkage.py` (output_grouping dispatch) | ~20 |
| `configs/c4/tiger_roads_demo.yaml` (add `output_grouping: episode`) | +1 |
| `tests/test_precomputed_areal_linkage.py` (3 tests) | ~80 |
| `tests/fixtures/precomputed_areal_mini.parquet` (committed fixture, ~2K bytes) | 0 LOC |
| `tests/test_pipeline_smoke.py` (row-count assertion update) | ~3 |
| **Phase A total** | **~104** |
| **Phase B** | |
| `backend/app/data/variable_metadata.json` (tiger_proximity entry) | +11 |
| `backend/app/experiments/tiger_proximity.py` | ~290 |
| `backend/tests/test_tiger_proximity.py` (8 tests) | ~140 |
| `backend/tests/test_e2e_tiger_proximity_cohort.py` | ~90 |
| `backend/tests/test_e2e_multi_experiment_with_tiger.py` | ~110 |
| `backend/tests/test_variable_registry.py` (+1 test) | ~10 |
| `backend/tests/test_task_manager_dispatch.py` (+1 test) | ~15 |
| `backend/tests/test_merge_partial.py` (+1 test) | ~12 |
| `backend/tests/manual_e2e.md` (Sprint 5 section) | ~30 |
| **Phase B total** | **~708** |
| **Grand total** | **~812** |

Wall-clock estimate: **2-3 focused work days.** Phase A is 0.5d
(scoped pipeline patch + three unit tests). Phase B is 1.5-2d
(cloned-and-trimmed runner + tests + smoke). The 3-experiment
integration test is the longest single task — budget 2 hours.

## Manual smoke (`backend/tests/manual_e2e.md` Sprint 5 section)

```markdown
## Sprint 5 — TIGER Road Proximity + precomputed_areal episode dispatch

Pre-flight:
- spacescans-pipeline editable install reflects Phase A
  (`output_grouping` dispatch in `precomputed_areal_linkage.py`).
  Verify with `python -c "from spacescans.linkage import
  precomputed_areal_linkage; import inspect; print('episode' in
  inspect.getsource(precomputed_areal_linkage))"` — expect True.
- `data_full/TIGER/C4/tiger{2013,…,2019}_roads/` exists with per-county
  zip files for at least one county.
- `cache/C3/tiger_roads_filtered/` exists (first run on a fresh cache
  takes longer).
- `backend/app/data/variable_metadata.json` has 4 entries including
  `tiger_proximity`.

1. Variables-step renders 4 cards grouped by boundary:
   - "Block Group" section: NDI, EPA Walkability Index, TIGER Road
     Proximity
   - "ZCTA5" section: Community Organization Density (ZBP)
   Each card shows label, description, unit chip, year-range chip,
   boundary chip. The TIGER card's unit chip reads "meters",
   year-range "2013–2019", boundary "BG".
2. Tick the TIGER card → coverage panel mounts inline; same shape
   as Sprint 3 cards.
3. Tick all 4 variables → Review step → Run. Watch status.json:
   - `experiments` map shows bg_ndi_wi running first, zcta5_cbp
     and tiger_proximity pending; then progresses through all three
     in metadata-file order.
   - logs.jsonl carries entries from all three runners.
   - result.csv on completion carries
     ndi + NatWalkInd + all 10 r_* + dist_pri + dist_sec + dist_prisec
     columns.
4. Repeat the same task; second run should hit the
   `BG_TIGER` C3 cache (status.json shows c3_tiger_roads progresses
   to 100% in < 1s for the cached cohort + buffer).
5. Negative test: edit `configs/c4/tiger_roads_demo.yaml` to change
   `output_grouping: episode` to an unknown value (e.g.
   `output_grouping: foo`); run a fresh task. Expect a clear
   ValueError in logs.jsonl from `precomputed_areal_linkage.py`:
   `unsupported output_grouping: 'foo' (expected 'patient' or 'episode')`.
   Restore the YAML. NOTE: do NOT test by *removing* the key —
   `TimeConfig.output_grouping` defaults to `"patient"` at the
   dataclass level (`src/spacescans/models/config.py:100`), so a
   missing key silently falls back to patient-grouping instead of
   raising. Catching that regression requires the explicit-typo
   test, not an absent-field test.
```

## CDLA attribution / data provenance

TIGER/Line shapefiles are US Census Bureau public-domain releases;
no CDLA attribution is required for the road-distance variable
(distinct from the building-sampled patient cohort which uses
Microsoft Building Footprints under CDLA-Permissive 2.0). The
variable's description string names "US Census TIGER/Line
shapefiles" verbatim so the data source surfaces in the wizard UI;
no additional `LICENSES.md` entry is added in Sprint 5.

## Appendix: files NOT touched

Files the dispatcher/registry architecture lets Sprint 5 skip:

- `backend/app/dispatcher.py` — discovers `tiger_proximity` via the
  registry's filesystem glob.
- `backend/app/variable_registry.py` — new entry passes the existing
  whitelist.
- `backend/app/task_manager.py` — `start_task` dispatches via the
  registry.
- `backend/app/experiments/_merge.py` — `write_partial` reads
  `value_cols` from the registry.
- `backend/app/experiments/bg_ndi_wi.py`,
  `backend/app/experiments/zcta5_cbp.py` — existing `_BOUNDARY`
  constants unchanged; cache hits preserved.
- `frontend/src/lib/api.ts`, `frontend/src/lib/variable-grouping.ts`,
  `frontend/src/components/wizard/*.tsx` — registry-driven.
- `backend/app/routers/variables.py` — serves the registry payload.
