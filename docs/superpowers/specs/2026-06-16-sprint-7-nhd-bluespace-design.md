# Sprint 7 Spec — NHD Bluespace Experiment

**Date:** 2026-06-16
**Status:** Approved by user 2026-06-16 (Sprint 7 = next experiment after Sprint 5 TIGER pilot).
**Goal:** Add nhd_bluespace as the 5th experiment runner (4th experiment module) in the metadata-driven catalog, exercising precomputed_static linkage_pattern for first web use. Phase A audits the pipeline's precomputed_static for output_grouping dispatch via resolve_output_grouping helper (Sprint 6 T6 pattern). Phase B adds web-side runner + metadata entry + integration test.

## Background

Sprint 5 landed the first `precomputed_areal` consumer (`tiger_proximity`)
with a Sprint 2-style two-phase change: a pipeline-side
`output_grouping` dispatch in `precomputed_areal_linkage.py`, then a
web-side runner clone-trimmed from `bg_ndi_wi.py`. Sprint 6 refactored
the Sprint 5 dispatch into a shared
`spacescans.linkage.helpers.resolve_output_grouping` helper (task T6)
so that future linkage patterns adopt the same patient-vs-episode
branching with a one-line import + one-line helper call rather than a
copy-pasted ten-line conditional.

`precomputed_static_linkage.py` is the next linkage pattern in line.
Today it has no `output_grouping` dispatch at all — it hard-codes
`for patid, grp in joined.groupby("PATID")` at lines 77-78 with
output row `{"PATID": patid}`. The only helpers import is
`from spacescans.linkage.helpers import load_patients` (line 28). The
sibling `precomputed_areal_linkage.py` already routes through the
Sprint 6 helper (lines 118-124 dispatch on `select_keys` / `group_keys`).

The `nhd_bluespace` experiment is the first catalogued variable to
read `precomputed_static`. Without a Sprint 6-style helper adoption,
the runner's `_merge.write_partial` (pid, episode_id) join either
collapses rows or matches nothing — the same regression Sprint 5
documented for `precomputed_areal`.

Sprint 7 is therefore a Sprint 5-style two-phase change scoped to
exactly one linkage pattern and exactly one new variable:

- **Phase A (`spacescans-pipeline`)** — extend
  `precomputed_static_linkage.py` with the same `resolve_output_grouping`
  helper call yearly_areal + precomputed_areal already use, applied as
  a pandas `groupby(group_keys)` edit rather than the SQL clause edit
  Sprint 5 used.
- **Phase B (`spacescans-web`)** — add the `nhd_bluespace` runner
  (clone-trim of `tiger_proximity.py`) and metadata entry; no
  dispatcher, registry, or wizard changes.

The payoff matches Sprint 5: future `precomputed_static` variables
inherit episode dispatch for free.

## Goal

Land the fourth end-to-end experiment runner — NHD blue-feature
proximity on BG-tagged cohort points — by extending
`precomputed_static_linkage.py` with `resolve_output_grouping` dispatch
(Phase A) and registering a single new `nhd_bluespace` variable
(Phase B). Prove that the dispatcher + registry + merge chain stays
unchanged when a fourth runner type and a third linkage pattern
arrive.

## Scope

### In scope (Sprint 7)

- [B1] Phase A: extend
  `src/spacescans/linkage/precomputed_static_linkage.py:28` to import
  `resolve_output_grouping` alongside `load_patients`, and replace the
  hard-coded `groupby("PATID")` at line 78 (with `row = {"PATID": patid}`
  on line 80) with a `group_keys`-driven branch matching Sprint 6's T6
  pattern. Patient branch → `group_keys = ["PATID"]`. Episode branch →
  `group_keys = ["PATID", "geoid"]`. ValueError on unknown values is
  raised by the helper itself (no per-linkage error path). The
  post-aggregation `fill_na` loop at lines 91-94 is preserved verbatim.
- [B2] Phase A: add unit tests under
  `tests/test_precomputed_static_linkage.py` covering both branches
  plus the helper-raised ValueError path.
- [B3] Phase A: update `configs/c4/nhd_bluespace_demo.yaml` time
  block to declare `output_grouping: patient` so the CLI smoke run
  continues to reproduce v1 single-row-per-patient output. The web
  runner overrides via `render_yaml` to `episode` at runtime.
- [B4] Phase B: new variable entry `nhd_bluespace` in
  `backend/app/data/variable_metadata.json` (boundary `BG`,
  `value_cols: [dist_flow_m, dist_water_m, dist_area_m, dist_coast_m,
  dist_blue_m]`, `display_unit: meters`, `coverage_years: [2024, 2024]`).
- [B5] Phase B: new runner
  `backend/app/experiments/nhd_bluespace.py` (~300 LOC, cloned from
  `tiger_proximity.py`). Two-step plan (C3 + C4) — both per-task,
  because the shipped `proximity_blue_demo100k.parquet` is bound to
  the demo cohort (geoid 0..99999 is a per-patient-row synthetic key,
  not a Census GEOID) and CAN NOT be reused for arbitrary uploads.
- [B6] Phase B: lift the cache namespace into a step-specific tag —
  the new runner uses `_BOUNDARY = "BG_NHD"` to avoid colliding with
  the BG NDI/Walkability and BG_TIGER caches for the same input
  parquet + buffer.
- [B7] Phase B: in `nhd_bluespace.render_yaml`, rewrite
  `cfg["exposure"]["file"]` on the C4 template so it points at the
  per-task C3 output — same idiom Sprint 5 introduced for
  `tiger_proximity`. The C3 step requires no `source.file` rewrite —
  the pipeline CLI's `--data-dir SPACESCANS_DATA_DIR` arg resolves the
  relative `data_full/NHD/C4/…` path via `config_resolution.expand_path`
  (same pattern Sprint 5's TIGER C3 template uses, unmodified).
- [B8] Phase B: shared merge integration — runner's `merge_results`
  is a 3-line wrapper into `_merge.write_partial(...,
  experiment_key="nhd_bluespace", parquet_map={…})`.
- [B9] Phase B: unit + integration tests
  (`backend/tests/test_nhd_bluespace.py`,
  `backend/tests/test_e2e_nhd_bluespace_cohort.py`,
  `backend/tests/test_e2e_multi_experiment_with_nhd.py`).
- [B10] Phase B: `backend/tests/manual_e2e.md` gains a Sprint 7
  section covering the new variable on the demo cohort and the
  four-experiment dispatch path.

### Out of scope (deferred)

- **G1.** The remaining 4 experiments (`vnl`, `temis`, `noise`,
  `fara_tract`, `county_cbp`). Sprint 8+.
- **G2.** Frontend code changes. The `nhd_bluespace` variable renders
  in the existing "Block Group" section with no edits to
  `variables-step.tsx`, `variable-card.tsx`,
  `variable-coverage-panel.tsx`, or `variable-grouping.ts`. Sprint 7
  verifies (not modifies) this invariant per the frontend research.
- **G3.** Per-`value_col` `display_unit`. The wizard renders a single
  unit chip; "meters" covers all five NHD distance columns
  unambiguously (same as Sprint 5's TIGER framing).
- **G4.** Per-column tooltip / result preview surfaces. No frontend
  consumer reads `VariableMetadata.value_cols` today.
- **G5.** Cohort-coverage gating for the `nhd_bluespace` variable on
  the wizard. The bbox-CONUS check Sprints 1-5 use already covers
  NHDPlus_H National Release 2 (CONUS).
- **G6.** `cbp_fallback` `output_grouping` dispatch — still not read
  by a catalogued variable.
- **G7.** Disposition of the legacy `proximity_blue_demo100k.parquet`
  fixture. Same status as Sprint 5's TIGER fixture: cohort-bound
  (geoid 0..99999 maps to demo cohort row order), CLI smoke depends
  on it, leave in place + add README warning.
- **G8.** Renaming the synthetic `geoid` column to `episode_id` in
  the pipeline. Sprint 2/3/5 open question; still out of scope.
- **G9.** `coverage_years` schema_version=2 supporting length-1
  arrays for static products. Sprint 7 picks `[2024, 2024]` as the
  static-product convention; a length-1 form is orthogonal future
  work.
- **G10.** Multi-experiment parallel spawn. Sprint 3/5 deferral still
  applies; Sprint 7 adds a fourth runner under the same sequential
  dispatcher with the same orchestrator-lifetime `.run_lock`.
- **G11.** `temporal_resolution: static` hint in
  `variable_metadata.schema.json` so the UI can render "Static /
  2024 release" rather than a year-range slider. Today the schema
  has no static escape hatch; documented as a schema_version=2
  follow-up under R10.
- **G12.** Generalising `render_yaml` C3 `source.file` rewriting
  across runners. Not needed today — the pipeline CLI's `--data-dir`
  resolves relative source paths uniformly across all C3 templates.

## Architecture

```text
   spacescans-pipeline (Phase A)
   precomputed_static_linkage.py
     grouping = resolve_output_grouping(config)
     group_keys = ['PATID']            if grouping == 'patient'
     group_keys = ['PATID', 'geoid']   if grouping == 'episode'
     # ValueError raised by helper for any other value
                       │
                       ▼  C4 emits per-episode rows
   spacescans-web (Phase B)
   experiments/nhd_bluespace.py
     plan() → [c3_nhd_bluespace, c4_nhd_bluespace]
     render_yaml: rewrite exposure.file (C4 only; C3 source.file
       resolves via pipeline CLI --data-dir)
     _BOUNDARY = "BG_NHD"  (cache namespace)
     merge_results → _merge.write_partial(
       experiment_key="nhd_bluespace",
       parquet_map={"nhd_bluespace": "c4_nhd_bluespace.parquet"})
                       │
                       ▼
   variable_metadata.json adds 1 entry → GET /api/variables returns 5 entries
   Variables-step renders 5 BG cards (NDI, Walkability, TIGER, NHD) + 1 ZCTA5
```

The fan-out / fan-in chain (Sprint 3 architecture) is unchanged.
`nhd_bluespace` is the fourth experiment key; the dispatcher
discovers it via `variable_registry._discover_experiments()` globbing
`backend/app/experiments/*.py` — no dispatcher edits.

### Architectural choices and rationale

- **Phase A first, Phase B depends on it.** The web runner emits
  `time.output_grouping: episode` in its rendered YAML. Without
  Phase A live in the runner's pipeline env, the C4 step silently
  aggregates to PATID-level and `_merge.write_partial`'s
  (pid, episode_id) join either collapses rows or matches nothing.
  Phase A's smoke (and the runner-side sanity probe, R3) catches
  this. Identical contract to Sprint 5 R3.
- **Adopt Sprint 6's `resolve_output_grouping` helper, not a
  copy-pasted SQL branch.** `precomputed_areal_linkage.py:118-124`
  was patched in Sprint 5 with the original ten-line conditional;
  Sprint 6 T6 then refactored that into the
  `spacescans.linkage.helpers.resolve_output_grouping` helper.
  Sprint 7 picks up the helper directly — the dispatch is one
  import edit + one helper call + one ternary list, totalling ~4
  new lines in `precomputed_static_linkage.py`. Future linkage
  patterns (cbp_fallback, etc.) follow the same template.
- **Pandas groupby key list, not SQL.** `precomputed_static_linkage`
  is a pandas-only path (no DuckDB/SQLite). The episode branch
  replaces `groupby("PATID")` with `groupby(["PATID", "geoid"])` and
  the output row construction with `dict(zip(group_keys, key if
  isinstance(key, tuple) else (key,)))`. The empty-records fallback
  DataFrame at line 88 also needs `columns=group_keys + value_cols`.
- **Episode semantics for static exposures are well-defined.** When
  `temporal_mode: static`, each `(PATID, geoid)` row represents one
  patient-episode at one address (the demo_conus adapter encodes
  episode_id as a synthetic per-row `geoid`). Episode-grouped output
  produces one row per address-period per patient with the same
  static distance repeated — exactly what `_merge.write_partial`
  expects when joining on (pid, episode_id). This matches
  `precomputed_areal` for static-ish exposures and is the contract
  Sprint 5 already validated.
- **`output_grouping` must be declared explicitly in every shipped
  `precomputed_static` YAML.** The `TimeConfig.output_grouping`
  default is `"patient"` (`src/spacescans/models/config.py:100`), so
  a missing YAML key silently routes to the patient branch — the
  same hazard Sprint 5 documented for `precomputed_areal`. Audit:
  `grep -rn "linkage_pattern: precomputed_static" configs/` returns
  exactly one hit
  (`configs/c4/nhd_bluespace_demo.yaml`) which gets the one-line
  edit `output_grouping: patient` in Phase A step 3 (preserving v1
  CLI smoke reproducibility — the web runner overrides to `episode`
  at render time). Optionally consider tightening the dataclass
  default to `Optional[str] = None` in a follow-up sprint so absent
  keys raise; out of scope here.
- **Phase A makes a `time:` block mandatory for precomputed_static.**
  Today the file has zero references to `config.time`
  (`grep config.time src/spacescans/linkage/precomputed_static_linkage.py`
  returns 0 hits) — i.e., a C4 yaml without a `time:` block is
  currently legal for precomputed_static. After Phase A,
  `resolve_output_grouping(config)` (`helpers.py:120`) raises
  `ValueError("linkage pattern requires a time block with
  output_grouping")` when `config.time is None`, so the `time:` block
  becomes mandatory at registration time. The only in-tree yaml
  (`configs/c4/nhd_bluespace_demo.yaml`) already has a `time:` block
  (lines 24-26), so no shipped config breaks. **External users**
  (notebooks, downstream forks) who omit `time:` from a
  precomputed_static yaml will hit a new ValueError after Phase A —
  this is a breaking change worth calling out in the Phase A PR
  description. Optional future work: extend the helper or the static
  pattern to accept `config.time is None` as an implicit `"patient"`
  to preserve backwards compatibility.
- **Boundary cache namespace `BG_NHD`, not `BG` and not `BG_TIGER`.**
  Three runners now write BG-tagged metadata (bg_ndi_wi,
  tiger_proximity, nhd_bluespace) but emit incompatible C3 parquet
  schemas: bg_ndi_wi writes `(PATID, bg_geoid, weight)` raster
  weights with raster suffix in the cache key; tiger_proximity
  writes `(geoid, year, dist_pri, dist_sec, dist_prisec)`
  point-grain distances; nhd_bluespace writes
  `(geoid, dist_flow_m, dist_water_m, dist_area_m, dist_coast_m,
  dist_blue_m)` static distances with no year axis at all. The
  three cache-key shapes already diverge today, but the distinct
  `BG_NHD` tag insulates against a future raster-add or year-drop
  that would otherwise re-introduce collision. Note `BG_NHD` is
  purely a cache namespace — NHD output is per-patient-row, not
  block-group-aggregated; the variable_metadata `boundary` key
  stays plain `BG` for wizard grouping.
- **Static time semantics: `coverage_years: [2024, 2024]`.** The
  schema requires `minItems: 2, maxItems: 2` for `coverage_years`;
  static products have no real range. The two reasonable
  conventions are `[2024, 2024]` (NHDPlus_H National Release 2
  vintage) or `[2013, 2019]` (align with cohort years used by
  tiger_proximity/cbp_zcta5). Sprint 7 picks `[2024, 2024]` because
  faking a year range is misleading — the UI's coverage-year filter
  would falsely promise per-year resolution. The duplicated
  endpoint is the cleanest schema_version=1 representation of a
  static product. A schema_version=2 with explicit
  `temporal_resolution: static` is deferred (G11).
- **C3 step is mandatory, not optional.** The shipped
  `proximity_blue_demo100k.parquet` (geoid 0..99999, 100k rows) is
  bound to the 100k demo cohort: its `geoid` column is the
  per-patient row index baked at C3 time by the demo_conus adapter
  (`src/spacescans/linkage/helpers.py:82`: `df["geoid"] =
  range(len(df))` with comment "geoid must be unique per patient —
  pipeline assumes 1:1 patient↔geoid"). A user-uploaded cohort
  with a different row range would either match nothing or
  silently match row 0 to demo patient #0's blue-feature distances.
  The runner re-runs C3 per task; the cohort-independent
  tile-level feature cache survives across tasks (NHD's per-tile
  shapefile filter is reused).
- **`render_yaml` rewrites `exposure.file` (C4) only.** The C4
  template's `exposure.file` literal points at the shipped demo
  parquet (`output/python_v2/270m/NHD/C3/proximity_blue_demo100k.parquet`,
  cohort-bound); the runner MUST rewrite that to the per-task C3
  output — same idiom Sprint 5 introduced for tiger_proximity. The C3
  template's `source.file` (`data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb`)
  is a relative path that resolves via the pipeline CLI's
  `--data-dir SPACESCANS_DATA_DIR` arg: `config_resolution.expand_path`
  (`src/spacescans/config_resolution.py:38-76`) joins relative YAML
  paths to `data_dir` before reading. The web subprocess already
  passes `--data-dir` (see `bg_ndi_wi.py:194-196`), so no source.file
  rewrite is needed. The tiger C3 template (`configs/c3/tiger_roads_demo.yaml:5-8`)
  uses the exact same `data_full/TIGER/C4` relative-path pattern and
  Sprint 5 deliberately did NOT add a source.file rewrite. Sprint 7
  follows the same convention — `if step.is_c3: pass` in render_yaml.
- **Do NOT inject `time.output_grouping = "episode"` on the C3
  step.** The C3 nhd template has no `time:` block at all (see
  `configs/c3/nhd_demo.yaml`); the C4 template does carry `time:`
  (with `temporal_mode: static`). The `if "time" in cfg:` guard
  Sprint 5 introduced for tiger_proximity still works — it skips
  the C3 step naturally and writes to the C4 step only. No change
  to the guard idiom is needed.
- **One variable, five columns.** Same rationale as Sprint 5's
  TIGER: the wizard UI is `value_cols`-agnostic outside the type
  declaration at `api.ts:116`. A single `nhd_bluespace` variable
  emitting five `dist_*_m` columns renders as one card with one
  unit chip ("meters"); the merge step picks up all five columns
  from `value_cols`. Splitting into five variables would 5x cache
  pressure for zero UI gain.
- **NHD `fill_na: {dist_coast_m: 99999.0}` runs post-TWA.** The
  reader leaves `dist_coast_m` NaN so the duration-weighted average
  correctly skips inland addresses (whose `dist_coast_m` is null at
  C3 time); the YAML's `fill_na` block in
  `configs/c4/nhd_bluespace_demo.yaml:20-22` is applied AFTER
  patient-level aggregation. Sprint 7 does not change this semantics
  — Phase A only adjusts the groupby key list, not the post-aggregation
  fill_na step.

## Phase A: `precomputed_static_linkage.py` output_grouping dispatch

### Today's code

`src/spacescans/linkage/precomputed_static_linkage.py:28`:

```python
from spacescans.linkage.helpers import load_patients
```

`src/spacescans/linkage/precomputed_static_linkage.py:77-94`:

```python
records: list[dict] = []
for patid, grp in joined.groupby("PATID"):
    weights = grp["overlap_days"].values.astype(float)
    row: dict = {"PATID": patid}
    for col in value_cols:
        if col in grp.columns:
            row[col] = _wtd_mean(grp[col].values, weights)
        else:
            row[col] = float("nan")
    records.append(row)

result = pd.DataFrame.from_records(records) if records else pd.DataFrame(
    columns=["PATID", *value_cols],
)

# Post-aggregation fill_na (e.g. dist_coast_m: 99999.0 for inland addresses).
for col, fill in (config.exposure.fill_na or {}).items():
    if col in result.columns:
        result[col] = result[col].fillna(fill)
```

The terminal aggregation hard-codes `groupby("PATID")` and constructs
output rows as `{"PATID": patid}`. The helper is `_wtd_mean(vals, wts)`
defined at lines 32-40 (two args: values array AND weights array);
`weights = grp["overlap_days"].values.astype(float)` is computed once
per group before the value-cols loop. There is no reference to
`config.time.output_grouping` anywhere in the file. The empty-records
fallback DataFrame (line 88) is also keyed only on `PATID`. The
post-aggregation `fill_na` loop at lines 91-94 is unaffected by the
Phase A change (it operates on `result` after aggregation).

The sibling `precomputed_areal_linkage.py:26` already imports
`resolve_output_grouping` and dispatches at lines 118-124; Sprint 7
mirrors that adoption for the static path.

### Target code

Mirror Sprint 6's helper-driven dispatch (the same pattern Sprint 5
applied to `precomputed_areal_linkage.py:118-124`), translated from
SQL `select_keys/group_keys` to pandas `groupby` key list:

```python
# precomputed_static_linkage.py — line 28 (import edit)
from spacescans.linkage.helpers import load_patients, resolve_output_grouping

# precomputed_static_linkage.py — replace lines 77-89 (records list +
# groupby + records build + empty-records fallback). The post-aggregation
# fill_na block at lines 91-94 stays unchanged.

grouping = resolve_output_grouping(config)
group_keys = ["PATID"] if grouping == "patient" else ["PATID", "geoid"]

records: list[dict] = []
for key, grp in joined.groupby(group_keys):
    key_tuple = key if isinstance(key, tuple) else (key,)
    weights = grp["overlap_days"].values.astype(float)
    row: dict = dict(zip(group_keys, key_tuple))
    for col in value_cols:
        if col in grp.columns:
            row[col] = _wtd_mean(grp[col].values, weights)
        else:
            row[col] = float("nan")
    records.append(row)

result = pd.DataFrame.from_records(records) if records else pd.DataFrame(
    columns=[*group_keys, *value_cols],
)
# fill_na loop at lines 91-94 stays as-is (operates on result post-aggregation).
```

Notes:

- The helper itself raises `ValueError` on unknown values (the
  Sprint 6 T6 contract); no per-linkage error path is needed.
- The `joined` DataFrame already carries a `geoid` column from the
  patient-exposure join (per the precomputed_static contract that
  the exposure table is keyed on `geoid`). The episode branch's
  `geoid` IS the patient-episode's geoid that the join keyed on;
  there is no separate "exposure-table geoid" to choose between —
  they are the same column post-join.
- `groupby` with a single-element list returns scalar keys (not
  1-tuples), hence the `isinstance(key, tuple)` guard. The same
  guard appears in Sprint 6's helper-adoption tests; mirror its
  shape verbatim.
- The empty-records fallback DataFrame's `columns` list moves from
  hard-coded `["PATID", *value_cols]` to `[*group_keys, *value_cols]`
  so the schema agrees with the non-empty branch.
- The duration-weighting (`weights = grp["overlap_days"].values.astype(float)`
  + `_wtd_mean(grp[col].values, weights)`) is preserved verbatim under
  both branches; Phase A only swaps the groupby key list. The per-col
  `if col in grp.columns: ... else float("nan")` defensive guard at
  lines 82-85 is also preserved.
- The post-aggregation `fill_na` loop at lines 91-94 is NOT touched —
  it runs on `result` after aggregation and is invariant to the groupby
  key change (essential for `dist_coast_m: 99999.0` semantics).
- The NHD reader plugin (`src/spacescans/plugins/readers/nhd.py:62-84`)
  needs zero modification: the C3 parquet's `geoid` column is
  already int64 and the precomputed_static load already keys on
  `geoid`. No reader changes.

### Pipeline unit test plan

`tests/test_precomputed_static_linkage.py` (NEW, ~80 LOC, three
tests):

1. `test_precomputed_static_groups_by_patid_when_output_grouping_patient`
   — regression lock for today's behaviour; columns
   `[PATID, dist_flow_m, dist_water_m, dist_area_m, dist_coast_m,
   dist_blue_m]`; `df["PATID"].is_unique`.
2. `test_precomputed_static_groups_by_patid_geoid_when_episode` —
   Sprint 7 new branch; columns
   `[PATID, geoid, dist_flow_m, …, dist_blue_m]`;
   `df.groupby(["PATID", "geoid"]).size().max() == 1`.
3. `test_precomputed_static_rejects_unknown_output_grouping` —
   typo-catch test: constructs a config with `output_grouping="foo"`
   (TimeConfig populated); asserts the helper-raised
   `pytest.raises(ValueError, match="unsupported output_grouping: 'foo'")`.
   The stricter substring binds to the explicit-value-error branch of
   `resolve_output_grouping` (`helpers.py:111-130`) which raises
   `f"unsupported output_grouping: {grouping!r} (expected 'patient' or
   'episode')"`. NOTE: the helper has a second orthogonal failure
   mode — when `config.time is None`, it raises
   `"linkage pattern requires a time block with output_grouping"`. The
   fixture `make_static_demo_config` constructs a TimeConfig
   explicitly so the first message fires; if a downstream author
   forgets the TimeConfig the test would silently exercise the
   `time is None` path with a different message and the stricter
   `match=` substring catches that misconfiguration. Consistent with
   Sprint 6 T6.

A `make_static_demo_config` fixture builds the minimal TimeConfig
(with `temporal_mode: static`) + BufferConfig + ExposureConfig +
OutputConfig pointing at
`tests/fixtures/precomputed_static_mini.parquet` (~10 rows, two
multi-episode patients with shared static exposure values; ~2K bytes
committed).

Smoke run: `pytest -k "precomputed_static or nhd_bluespace"`.

**Smoke fixture caveat (mirrors Sprint 5).** The shipped 100k demo
cohort `data_full/demo_patients_conus_fast_100000.parquet` has
`geoid = episode_id = range(100_000)` — every patient maps to a
single geoid by construction (via `_adapt_demo_conus` falling back
to `range(len(df))` when no `episode_id` column —
`helpers.py:78-82`). A naive switch from `groupby("PATID")` to
`groupby(["PATID", "geoid"])` produces the same 100,000 rows under
both branches; an assertion that only counts distinct
`(PATID, geoid)` pairs would silently pass even if the episode
branch were buggy. Sprint 7 resolves this the same way Sprint 5 did:

- (a) **Recommended.** Leave `configs/c4/nhd_bluespace_demo.yaml` at
  `output_grouping: patient` for the CLI-only smoke (the web runner
  overrides via `render_yaml` anyway, per Phase B's
  `cfg["time"]["output_grouping"] = "episode"` line). Multi-episode
  coverage comes from the **unit-test fixture only** —
  `tests/fixtures/precomputed_static_mini.parquet` (~10 rows, two
  multi-episode patients with shared static exposure values; ~2K bytes
  committed). The CLI smoke asserts `len(out) == 100_000` (patient
  branch); the unit test asserts
  `count(distinct (PATID, geoid)) > count(distinct PATID)` against the
  mini fixture. **No new CLI episode smoke is added** because the
  shipped 100k demo cohort is 1:1 PATID-to-geoid and no multi-episode
  CLI-scale parquet is in scope for Sprint 7.
- (b) **Deferred alternative.** Commit a small explicit multi-episode
  demo cohort under `tests/fixtures/` (e.g., 50 patients × 2 episodes)
  and reference it from a new episode CLI smoke variant. Out of scope
  here; would add another fixture line to the implementation estimate.

Sprint 7 recommends (a) — the demo cohort remains 1:1 PATID-to-geoid
and the unit-test fixture provides the multi-episode coverage. This
keeps the demo CLI smoke bit-for-bit reproducible against v1 output.

## Phase B: web experiment runner `nhd_bluespace.py`

### Module shape

```python
# backend/app/experiments/nhd_bluespace.py

from app.experiments import _merge
from app.experiments.bg_ndi_wi import (
    PipelineStep,
    _append_log,
    _is_valid_cached_parquet,
    parse_step_progress,
    run_pipeline_step,
)
# NOTE: `csv_to_parquet` is imported LOCALLY inside run() (not here at
# module top) to mirror tiger_proximity.py:265's "avoid module cycle at
# boot time" comment.

_VARIABLE_TO_STEP = {
    "nhd_bluespace": PipelineStep(
        name="c4_nhd_bluespace",
        template_relpath="c4/nhd_bluespace_demo.yaml",
        is_c3=False,
    ),
}
_C3_STEP = PipelineStep(
    name="c3_nhd_bluespace",
    template_relpath="c3/nhd_demo.yaml",
    is_c3=True,
)
_BOUNDARY = "BG_NHD"     # cache-key namespace; distinct from BG / BG_TIGER
_EXPERIMENT_KEY = "nhd_bluespace"
_PARQUET_MAP = {"nhd_bluespace": "c4_nhd_bluespace.parquet"}
```

### `plan(config)` — two-step plan, always

```python
def plan(config: dict) -> list[PipelineStep]:
    """Always emits [c3_nhd_bluespace, c4_nhd_bluespace].

    nhd_bluespace has a single variable with five value_cols emitted by a
    single C4 parquet — so the plan is deterministic.
    """
    variables = config.get("variables", [])
    if not variables:
        raise ValueError("at least one variable must be selected")
    unknown = [v for v in variables if v not in _VARIABLE_TO_STEP]
    if unknown:
        raise ValueError(f"unknown variable(s): {', '.join(unknown)}")
    return [_C3_STEP, _VARIABLE_TO_STEP["nhd_bluespace"]]
```

### `render_yaml` — C4 exposure rewrite

Structurally identical to `tiger_proximity.render_yaml`: the C4 step
rewrites `cfg["exposure"]["file"]` to point at the per-task C3 output;
the C3 step needs no template rewrite because the pipeline CLI's
`--data-dir SPACESCANS_DATA_DIR` arg resolves the C3 template's
relative `data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb` path
via `config_resolution.expand_path`.

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
    # NOTE: no raster_res_m write (template has no such key; NHD is line/poly geometry).

    if step.is_c3:
        # C3: no template rewrite — pipeline CLI --data-dir resolves source.file.
        pass
    else:
        # C4: rewrite exposure.file to point at the per-task C3 output.
        if not isinstance(cfg.get("exposure"), dict):
            raise RuntimeError(
                "nhd_bluespace.render_yaml: unexpected exposure: shape in C4 template"
            )
        cfg["exposure"]["file"] = str(
            task_dir / "output" / f"{_C3_STEP.name}.parquet"
        )

    if "time" in cfg:
        cfg["time"]["output_grouping"] = "episode"   # Sprint 7 Phase A contract
    cfg["output"]["path"] = str(task_dir / "output" / f"{step.name}.parquet")

    out = task_dir / "pipeline_configs" / f"{step.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out
```

The `if "time" in cfg:` guard naturally skips the C3 nhd template
(which has no `time:` block) and writes the override only to the C4
step.

### `_cache_key` — no raster, no year, boundary-namespaced

```python
def _cache_key(input_parquet: Path, step: PipelineStep, user_config: dict) -> str:
    """Format: ``<sha8>__BG_NHD__b<buffer>m``.

    Omits raster_res_m (template has no raster field; NHD is line/poly geometry).
    Omits any year axis (NHD product is truly static — no year column in C3 output).
    Boundary tag BG_NHD avoids collision with bg_ndi_wi's BG cache and
    tiger_proximity's BG_TIGER cache for the same input parquet + buffer.
    """
    sha = _hash_input_parquet(input_parquet)
    buf = user_config["buffer"]["size"]
    return f"{sha[:8]}__{_BOUNDARY}__b{buf}m"
```

(`_hash_input_parquet` is copied verbatim from `tiger_proximity.py`.)

Buffer is included in the cache key even though `nhd_proximity_linkage`
uses a fixed `_BUFFER_M = 15000` padding around tiles independent of
user buffer (per `src/spacescans/linkage/nhd_proximity_linkage.py:36`).
This matches tiger_proximity convention and insulates against future
NHD reader changes that may consume the user buffer.

### `merge_results` — delegates to `_merge.write_partial`

```python
def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Delegate to the shared _merge.write_partial.

    The _PARQUET_MAP carries a single entry (nhd_bluespace → one parquet);
    the merge picks up all five value_cols (dist_flow_m, dist_water_m,
    dist_area_m, dist_coast_m, dist_blue_m) from the variable_metadata.json
    entry via variable_registry.get_variable.
    """
    parquet_map = {v: _PARQUET_MAP[v] for v in variables}
    return _merge.write_partial(
        task_dir=task_dir,
        experiment_key="nhd_bluespace",
        variables=variables,
        parquet_map=parquet_map,
    )
```

The `_merge.write_partial` body itself is unchanged from Sprint 3 —
it reads `value_cols` from `variable_registry.get_variable(key)`,
selects those plus the rename keys, joins on `(pid, episode_id)`,
and writes `result_nhd_bluespace.csv`.

### `run(task_dir, variables=None)` and `_cli_main`

Structurally identical to `tiger_proximity.run` / `tiger_proximity._cli_main`
modulo the four module-level constants. Runner: SIGTERM handler →
acquire `.run_lock` → read config + apply dispatcher override →
`plan()` → per-step `render_yaml` + `run_pipeline_step` + slot
progress update → `merge_results` → terminal slot status → release
lock. The CLI argv shape
`python -m app.experiments.nhd_bluespace run <task_dir>
--variables nhd_bluespace` matches tiger_proximity byte-for-byte
except for the parser `prog=` field.

### Differences from prior runners

| Aspect | `bg_ndi_wi` | `zcta5_cbp` | `tiger_proximity` | `nhd_bluespace` (new) |
|---|---|---|---|---|
| Linkage pattern (C4) | `yearly_areal` | `yearly_areal` | `precomputed_areal` | `precomputed_static` |
| C3 step | `c3_bg` (boundary_overlap_fast) | `c3_zcta5` | `c3_tiger_roads` | `c3_nhd_bluespace` (nhd_proximity) |
| C4 reads exposure via | raster | `.Rda` (pyreadr) | per-task C3 parquet | per-task C3 parquet |
| `render_yaml` rewrites `exposure.file`? | no | no | yes (C4 only) | yes (C4 only) |
| `render_yaml` injects `raster_res_m`? | yes (C3) | no | no | no |
| `_BOUNDARY` cache tag | `"BG"` | `"ZCTA5"` | `"BG_TIGER"` | `"BG_NHD"` |
| `_cache_key` shape | `<sha8>__BG__b{buf}m__r{raster}m` | `<sha8>__ZCTA5__b{buf}m__r{raster}m` | `<sha8>__BG_TIGER__b{buf}m` | `<sha8>__BG_NHD__b{buf}m` |
| Year axis | per-year | per-year | per-year | static (no year) |
| Variables per runner | 2 (NDI, Walkability) | 1 (cbp_zcta5) | 1 (tiger_proximity, 3 cols) | 1 (nhd_bluespace, 5 cols) |
| C4 parquets per run | one per variable | one (10 cols) | one (3 cols) | one (5 cols) |

Sprint 7 has no new render_yaml logic vs Sprint 5 — every difference
is parameterised over module-level constants (`_BOUNDARY`,
`_EXPERIMENT_KEY`, `_VARIABLE_TO_STEP`, `_PARQUET_MAP`, `_C3_STEP`).
The runner is a near-pure clone of tiger_proximity.py.

## Phase B: `variable_metadata.json` entry

```json
"nhd_bluespace": {
  "label": "NHD Blue-Feature Proximity",
  "description": "Per-block-group static distance (meters) to the nearest NHD flowline (dist_flow_m), waterbody (dist_water_m), area-feature (dist_area_m), coastline (dist_coast_m; 99999 for inland addresses), and combined blue-feature (dist_blue_m), from NHDPlus_H National Release 2 GDB (static product, 2024 vintage).",
  "boundary": "BG",
  "coverage_years": [2024, 2024],
  "coverage_region": "CONUS",
  "experiment": "nhd_bluespace",
  "variable_type": "continuous",
  "display_unit": "meters",
  "value_cols": ["dist_flow_m", "dist_water_m", "dist_area_m", "dist_coast_m", "dist_blue_m"]
}
```

Schema validation passes against
`backend/app/data/variable_metadata.schema.json` v1:

- `^[a-z][a-z0-9_]*$` matches the key `nhd_bluespace`.
- `boundary: BG` is in the enum (the variable's spatial dispatch is
  at point grain at C3 time, then duration-weighted-averaged in C4;
  the Block Group framing reflects how the wizard groups the card,
  not the C3 implementation — same convention Sprint 5 used for
  `tiger_proximity`).
- `coverage_years: [2024, 2024]` — minItems 2, maxItems 2, integers
  in [1900, 2100]. Duplicated endpoint is the static-product
  convention until schema_version=2 lands (G11).
- `display_unit: "meters"` — ASCII printable, ≤ 50 chars.
- `value_cols: ["dist_flow_m", "dist_water_m", "dist_area_m",
  "dist_coast_m", "dist_blue_m"]` — minItems 1, all five match
  reader emit list at `src/spacescans/plugins/readers/nhd.py:82`.
- `experiment: "nhd_bluespace"` — `^[a-z][a-z0-9_]*$` pattern AND
  matches a discoverable Python module name at
  `backend/app/experiments/nhd_bluespace.py` (registry load-time
  whitelist check).

The entry is appended to the existing `variables` map at the end of
the file. Dispatch order is JSON-file order of first experiment
appearance (Sprint 3 invariant); for a `[ndi, walkability, cbp_zcta5,
tiger_proximity, nhd_bluespace]` selection the dispatcher would spawn
`bg_ndi_wi` first, then `zcta5_cbp`, then `tiger_proximity`, then
`nhd_bluespace`.

## Phase B: NHD data pre-flight

Sprint 5 added `_assert_tiger_data_present` at
`backend/app/variable_registry.py:72-97` as a server-boot pre-flight
that walks `coverage_years` and asserts per-year subdirs exist.
That idiom doesn't fit NHD because NHD has no year subdirs —
NHDPlus_H National Release 2 is a single static GDB.

Sprint 7 adds a sibling `_assert_nhd_data_present` with a simpler
shape: short-circuit if the data dir is absent (prod-vs-test
fixture pattern), otherwise assert the single GDB subpath exists,
raise `MetadataSchemaError` otherwise:

```python
def _assert_nhd_data_present(payload: dict[str, Any]) -> None:
    """Server-boot pre-flight for the nhd_bluespace experiment.

    Asserts that the NHDPlus_H National Release 2 GDB exists under
    SPACESCANS_DATA_DIR/data_full/NHD/C4. Short-circuits if the data
    dir itself is absent (test-fixture pattern matching
    _assert_tiger_data_present at variable_registry.py:72-97).
    """
    if not any(
        m.get("experiment") == "nhd_bluespace"
        for m in payload["variables"].values()
    ):
        return
    data_dir = (
        Path(app.config.settings.SPACESCANS_DATA_DIR)
        / "data_full" / "NHD" / "C4"
    )
    if not data_dir.is_dir():
        # Test/CI environments may not stage NHD data; defer to runtime errors.
        return
    gdb_path = data_dir / "NHDPlus_H_National_Release_2_GDB.gdb"
    if not gdb_path.exists():
        raise MetadataSchemaError(
            f"nhd_bluespace catalogued but NHDPlus_H GDB missing at {gdb_path}"
        )
```

Signature/body mirrors the sibling `_assert_tiger_data_present`
(`backend/app/variable_registry.py:72`) verbatim: takes the full
`payload: dict[str, Any]`, walks `payload["variables"].items()` (or
`.values()` here, since this pre-flight does not need the key), and
uses `m.get("experiment")` dict access (NOT attribute access — the
class `VariableMetadata` does not exist in `backend/app/`; only a
TypeScript interface in `frontend/src/lib/api.ts:107` and a
`VariableMetadataModel` BaseModel in
`backend/app/routers/variables.py:13`). The path includes the
`data_full` segment to match every other consumer (tiger pre-flight at
`variable_registry.py:84`: `SPACESCANS_DATA_DIR / "data_full" / "TIGER"
/ "C4"`; web settings docstring at `config.py:39`: "The actual exposure
data lives under <SPACESCANS_DATA_DIR>/data_full/").

Called unconditionally from `load_variables()` after
`_assert_tiger_data_present(payload)` at line 127 — the new call is
`_assert_nhd_data_present(payload)` (NOT `variables`). The dual
pre-flight is intentional symmetric — each experiment gets one
explicit check.

A second pre-flight layer matching Sprint 5's
`_sanity_check_pipeline_supports_precomputed_areal_episode` is NOT
needed for nhd_bluespace. Sprint 5's check uses `inspect.getsource`
to guard against a stale editable wheel that lacks Sprint 5's
dispatch in `precomputed_areal_linkage.py`. Sprint 7's Phase A
analog would grep `precomputed_static_linkage.py` for the
`resolve_output_grouping` string. This is cheap and follows the
Sprint 5 template; runner adds the symmetric probe:

```python
def _sanity_check_pipeline_supports_precomputed_static_episode() -> None:
    import inspect
    from spacescans.linkage import precomputed_static_linkage
    if "resolve_output_grouping" not in inspect.getsource(precomputed_static_linkage):
        raise RuntimeError(
            "spacescans-pipeline missing Sprint 7 Phase A: "
            "precomputed_static_linkage does not call resolve_output_grouping. "
            "Editable install is stale — reinstall or bump the version pin."
        )
```

Invoked at runner start, before `plan()`.

## Phase B: frontend changes

**None.** Per the research:

- `VariablesStep` groups by `meta.boundary` via `groupByBoundary`
  (`variable-grouping.ts:17-19`); `BG` is first in `BOUNDARY_ORDER`
  with label "Block Group" — `nhd_bluespace` joins NDI, Walkability,
  and TIGER with zero `variables-step.tsx` edits.
- `VariableCard` (`variable-card.tsx:25-29`) renders the three
  chips (display_unit "meters", coverage range "2024–2024",
  boundary "BG") directly from `VariableMetadata` — no template
  change. The duplicated-year chip will read "2024" (the chip
  renderer collapses identical endpoints — verify in manual smoke
  step 1; if it renders as "2024–2024" instead, the chip text is
  cosmetic-only and Sprint 7 ships as-is, with G11 follow-up
  for a static-product chip mode).
- `VariableCoveragePanel` (`variable-coverage-panel.tsx:74-75`)
  consumes only `boundary` and `coverage_years`; backend's
  registry-driven `compute_coverage` already returns both.
- `value_cols` is declared on the type (`api.ts:116`) but read
  nowhere under `spacescans-web/` — one-card-five-columns works
  out of the box.

Sprint 7 manual smoke includes a no-op verification step: visually
confirm the BG section renders four cards after the metadata entry
lands.

### Cosmetic stepper subtitle (out of scope reminder)

`frontend/src/components/wizard/wizard-layout.tsx:9` hardcodes the
description string "BG NDI / Walkability". This is cosmetic copy
only; it does not gate rendering. As a fourth BG variable lands it
becomes increasingly stale, but Sprint 7 defers the rewrite to a
future cleanup (G2 reaffirms zero frontend edits).

## Implementation order

Phase A lands on the `pkg/pypi-only` branch of the `spacescans-project`
repo (where Sprints 4–6's pipeline-side work lives). Phase B lands
on a fresh `feat/sprint-7-nhd-bluespace` branch (or worktree) of
`spacescans-web`. The phase boundary is the only pipeline-vs-web
split; within each phase the order matches the brainstorm structure.

### Phase A (spacescans-pipeline, branch `pkg/pypi-only`)

1. Pre-flight: confirm
   `$SPACESCANS_DATA_DIR/data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb`
   exists (61 GB); if absent, skip the CLI smoke and rely on the
   unit-test fixture only.
2. Edit `src/spacescans/linkage/precomputed_static_linkage.py:28`
   to add `resolve_output_grouping` to the helpers import.
3. Edit `src/spacescans/linkage/precomputed_static_linkage.py`
   lines 77-89 (the records list + groupby + records build + empty-
   records fallback DataFrame) to add the `group_keys`-driven groupby
   branch (~6 new / ~3 deleted lines, including the empty-records
   fallback's columns list). **Preserve verbatim:**
   `weights = grp["overlap_days"].values.astype(float)` precompute,
   the per-col `if col in grp.columns: ... else float("nan")`
   defensive guard, AND the post-aggregation `fill_na` loop at lines
   91-94 (essential for `dist_coast_m: 99999.0` semantics — operates
   on `result` after aggregation and is invariant to the groupby key
   change).
4. Edit `configs/c4/nhd_bluespace_demo.yaml` to add
   `output_grouping: patient` under the time block (preserves v1
   CLI smoke; web runner overrides to episode).
5. Add `tests/test_precomputed_static_linkage.py` (~80 LOC, three
   tests above) and
   `tests/fixtures/precomputed_static_mini.parquet` (multi-episode
   fixture).
6. Add a new pipeline smoke test that executes
   `configs/c4/nhd_bluespace_demo.yaml` end-to-end (CLI smoke,
   patient-grouping) and asserts row count == 100,000. (Audit:
   `grep -rn "nhd_bluespace_demo\|nhd_demo" tests/` returns zero hits
   today; `tests/test_pipeline_smoke.py` already contains the Sprint 5
   tiger smoke tests — e.g. `test_shipped_tiger_roads_demo_yaml_declares_episode_grouping`
   at line 74 and `test_tiger_roads_demo_episode_branch_row_count` at
   line 92 — Sprint 7 adds parallel `nhd_bluespace_demo` smoke tests
   alongside.) The explicit-episode CLI smoke is dropped from Sprint 7
   in favour of (a) below — the multi-episode coverage comes from the
   unit-test fixture `tests/fixtures/precomputed_static_mini.parquet`
   only; the demo CLI smoke remains patient-grouping for v1
   reproducibility.
7. Run `pytest -k "precomputed_static or nhd_bluespace"` — must
   pass. Full suite — no regressions in `yearly_areal`,
   `yearly_areal_bg_vintage`, `static_areal`, `precomputed_areal`.
8. **Editable install dependency:** Phase B's integration tests
   require Phase A live in the runner's pipeline env. The web's
   `SPACESCANS_PIPELINE_PYTHON` points at a Python env where
   `pip install -e ../spacescans-project` reflects the pipeline
   source. If Phase A lands as a release-pin instead, bump the pin
   in `spacescans-web/backend/pyproject.toml` and re-install
   before Phase B smoke. (See Risk R3.)
9. PR title: `feat(linkage): precomputed_static output_grouping
   dispatch via resolve_output_grouping helper (Sprint 7 Phase A)`.

### Phase B (spacescans-web, branch `feat/sprint-7-nhd-bluespace`)

1. Pre-flight: verify Phase A is live in the web's pipeline env via
   `python -c "from spacescans.linkage import
   precomputed_static_linkage; import inspect; print('resolve_output_grouping'
   in inspect.getsource(precomputed_static_linkage))"` — expect
   `True`.
2. Add the `nhd_bluespace` entry to
   `backend/app/data/variable_metadata.json` (server boot will fail
   the discovery whitelist until step 3 — expected and gating).
3. Add `_assert_nhd_data_present(payload: dict[str, Any])` to
   `backend/app/variable_registry.py:97` (after the TIGER
   pre-flight) and call it from `load_variables()` as
   `_assert_nhd_data_present(payload)` (matching the sibling call
   `_assert_tiger_data_present(payload)` at line 127).
4. Add `backend/app/experiments/nhd_bluespace.py` (~300 LOC).
   Server starts; `/api/variables` returns 5 keys.
5. Add `backend/tests/test_nhd_bluespace.py` (~140 LOC). Pass
   locally.
6. Add `backend/tests/test_e2e_nhd_bluespace_cohort.py`
   (`@pytest.mark.integration`, ~90s).
7. Add `backend/tests/test_e2e_multi_experiment_with_nhd.py`
   (5-variable, 4-experiment dispatch on the demo cohort;
   `@pytest.mark.integration`, ~270s).
8. Update `backend/tests/manual_e2e.md` with the Sprint 7 section.
9. Manual smoke: variables-step renders 5 cards (4 BG, 1 ZCTA5);
   5-variable task produces a `result.csv` with NDI + NatWalkInd +
   10 `r_*` + 3 `dist_*` (TIGER) + 5 `dist_*_m` (NHD) columns.
10. PR title: `feat(experiments): nhd_bluespace runner +
    precomputed_static episode dispatch (Sprint 7)`.

## Test impact

### Backend test count delta

| Test file | Status | Tests | Notes |
|---|---|---:|---|
| `backend/tests/test_nhd_bluespace.py` | NEW | +8 | plan/render_yaml/cache_key/merge_results/run smoke |
| `backend/tests/test_e2e_nhd_bluespace_cohort.py` | NEW | +1 | single-experiment integration (demo cohort) |
| `backend/tests/test_e2e_multi_experiment_with_nhd.py` | NEW | +1 | 5-variable, 4-experiment dispatch |
| `backend/tests/test_variable_registry.py` | MODIFIED | +2 | "registry accepts nhd_bluespace entry" + "_assert_nhd_data_present raises on missing GDB" |
| `backend/tests/test_task_manager_dispatch.py` | MODIFIED | +1 | "four-experiment dispatch preserves metadata order" |
| `backend/tests/test_merge_partial.py` | MODIFIED | +1 | "value_cols selection picks 5 NHD columns from one parquet" |

Backend net: +14 tests across 3 new + 3 modified files. Two
integration tests are `@pytest.mark.integration` and skipped by
default; the other 12 run in the default suite (~3s additional
wall-clock).

### Pipeline test count delta

| Test file | Status | Tests | Notes |
|---|---|---:|---|
| `tests/test_precomputed_static_linkage.py` | NEW | +3 | patient/episode/ValueError branches |
| `tests/test_pipeline_smoke.py` (new `nhd_bluespace_demo` patient end-to-end smoke, added alongside the Sprint 5 tiger smoke tests at lines 74 + 92) | MODIFIED | +1 | patient branch row count == 100,000; episode-branch coverage comes from the unit-test mini fixture (no CLI episode smoke — recommendation (a)) |
| `tests/test_precomputed_areal_linkage.py` | UNCHANGED | 0 | confirms Sprint 5 dispatch still passes |
| `tests/test_yearly_areal_linkage.py` | UNCHANGED | 0 | confirms Sprint 2 dispatch still passes |

Pipeline net: +4 tests.

## Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Future C3 cache key collision across BG-tagged runners.** Three runners now share `boundary: BG` in metadata (`bg_ndi_wi`, `tiger_proximity`, `nhd_bluespace`) but emit incompatible C3 parquet schemas. The three cache-key shapes already diverge today (`__BG__…__r{raster}m`, `__BG_TIGER__…`, `__BG_NHD__…`), so no collision exists at landing time. A future shape change (raster dropped, raster added, year axis added/removed) under a shared `_BOUNDARY` would re-introduce collision; the second runner would read the first's parquet with the wrong schema and exit 0 (silent corruption). | New runner uses `_BOUNDARY = "BG_NHD"` as defence in depth. `test_nhd_bluespace.py::test_cache_key_differs_from_other_bg_runners` asserts the three `_cache_key` outputs differ in both the boundary tag *and* the overall shape for the same `(input_parquet, buffer)`. |
| R2 | **NHD C3 data versioning.** The NHDPlus_H National Release 2 GDB is a single 61 GB artifact at `data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb`; missing file fails late after lock acquisition. | Server-boot pre-flight `_assert_nhd_data_present` (see Phase B section above) catches this at startup, not runtime. Short-circuits if `SPACESCANS_DATA_DIR/NHD/C4` is absent entirely (test-fixture pattern matching Sprint 5's TIGER pre-flight). |
| R3 | **Pipeline editable-install drift between Phase A and Phase B.** The web runner subprocess uses `SPACESCANS_PIPELINE_PYTHON`; a stale wheel ignores the new `resolve_output_grouping` adoption, silently emits patient-level rows, and `_merge.write_partial` collapses one-to-many on episode_id. | Three layers (same template as Sprint 5 R3): (a) Phase A pyproject bump publishes a new wheel; web's pin moves forward in the same PR. (b) `nhd_bluespace._sanity_check_pipeline_supports_precomputed_static_episode()` imports `precomputed_static_linkage` at runner start and greps its source for `'resolve_output_grouping'`; raises `RuntimeError` if absent. (c) `_merge.write_partial`'s existing `merge_partial_low_match_pct` log signal catches silent regressions if (a) and (b) both fail. |
| R4 | *(removed — Sprint 7 no longer rewrites C3 `source.file`; the pipeline CLI's `--data-dir` resolves the relative path uniformly. The C4 `exposure.file` shape-guard from Sprint 5 is preserved verbatim.)* | n/a |
| R5 | **`proximity_blue_demo100k.parquet` foot-gun.** Fixture's `geoid` column is per-patient row index 0..99999, bound to the demo cohort. A future cache keying on `(boundary, geoid)` could serve it to a non-demo cohort. | Leave in place (CLI smoke tests depend on it); add a one-line README warning under `output/python_v2/270m/NHD/C3/README.md`. Sprint 8+ may relocate to `fixtures/`. |
| R6 | **Phase A's helper-raised ValueError changes the failure mode of any other call site that explicitly passes an unknown `output_grouping` string through `precomputed_static`.** A *missing* key still inherits the `TimeConfig.output_grouping = "patient"` default and silently routes to the patient branch; the ValueError fires only on an explicitly invalid value. | Audit: `grep -rn "linkage_pattern: precomputed_static" configs/` returns exactly one hit (`configs/c4/nhd_bluespace_demo.yaml`), patched in Phase A step 4 to declare `patient` explicitly. No other in-tree call sites. Notebook users supplying a typo'd value get a clear ValueError with both legal values named (via the Sprint 6 helper). |
| R7 | **Static product `coverage_years: [2024, 2024]` produces a duplicated-endpoint chip in the wizard.** The chip renderer may render "2024–2024" instead of "2024". | Cosmetic only — does not block the variable from being selectable or runnable. Verify rendering in manual smoke step 1. If the chip text reads "2024–2024", defer to G11 (schema_version=2 with `temporal_resolution: static`) rather than patching the chip renderer for one product. |
| R8 | **Four-experiment integration test wall-clock ~270s.** | `@pytest.mark.integration`; runs only on `make test-integration` or nightly CI. Default suite adds ~3s for the 12 unit tests. |
| R9 | **`nhd_bluespace` is BG-tagged in metadata but runs at point grain in C3** (same as tiger_proximity). Users may expect BG-centroid aggregation. | Description string says "Per-block-group static distance (meters) to the nearest NHD…" verbatim. Sprint 8+ may add a `granularity: point \| polygon` field. |
| R10 | **NHD C3 per-task wall-clock dominated by NHDPlus_H GDB tile reads.** First task on a fresh cache takes minutes; subsequent same-bbox tasks reuse the cohort-independent tile feature cache. | Cohort-independent cache survives across tasks; document on the variable card if first-task latency becomes a support burden. Same template as Sprint 5 R9 for TIGER. |
| R11 | *(removed — Sprint 7 has no render_yaml divergence vs Sprint 5; the C4 `exposure.file` rewrite is the only delta.)* | n/a |
| R12 | **Cache size for NHD C3 outputs may be larger than TIGER's.** NHDPlus_H covers continental US blue features at fine-grained line/poly geometry; per-task C3 outputs are bounded by cohort size (~5 floats × N rows) but the cohort-independent tile cache is bounded by national feature coverage. | Reuse the existing `C3_CACHE_DIR` with the `BG_NHD` namespace tag (no carve-out). Add a cache-size monitoring line to Sprint 7's manual smoke step 4 ("inspect `C3_CACHE_DIR` total size; alert if > 10 GB"). Sprint 8+ may add an LRU eviction policy if size becomes a support burden. |

## Out of scope / open questions for Sprint 8+

- **G1.** Onboarding the next experiment. Once Phase A lands,
  remaining candidates (`vnl`, `noise`, `temis` — all
  `precomputed_areal`; `fara_tract` — `yearly_areal_bg_vintage`;
  `county_cbp` — `yearly_areal`) each collapse to a runner clone +
  metadata entry. Phase A is done for all four linkage patterns
  catalogued today.
- **G3.** Per-`value_col` `display_unit` — requires
  `api.ts:115` + `variable-card.tsx:26` changes.
- **G4.** Per-column tooltip / result preview surfaces — would read
  `VariableMetadata.value_cols`; no consumer today.
- **G6.** `cbp_fallback` `output_grouping` dispatch; still not read
  by a catalogued variable.
- **G9.** schema_version=2 with length-1 `coverage_years` arrays
  for static products, OR a `temporal_resolution: static` escape
  hatch. Sprint 7 documents the `[year, year]` workaround under R7.
- **NHD vintage tracking** — NHDPlus_H is on a 2–3 year release
  cadence; future updates would bump `coverage_years` to the new
  vintage. No automation for vintage rollovers in Sprint 7.
- **Multi-experiment parallel spawn** — still blocked by
  `.run_lock` orchestrator-lifetime scope and DuckDB + workspace
  contention.
- **Stepper subtitle cleanup** —
  `frontend/src/components/wizard/wizard-layout.tsx:9` reads "BG
  NDI / Walkability"; increasingly stale as BG variables land.
  Generic copy ("Choose exposures") deferred to a future cleanup.

## Implementation estimate

| Component | New / Modified LOC |
|---|---:|
| **Phase A** | |
| `src/spacescans/linkage/precomputed_static_linkage.py` (helper import + group_keys dispatch) | ~10 |
| `configs/c4/nhd_bluespace_demo.yaml` (add `output_grouping: patient`) | +1 |
| `tests/test_precomputed_static_linkage.py` (3 tests) | ~80 |
| `tests/fixtures/precomputed_static_mini.parquet` (committed fixture, ~2K bytes) | 0 LOC |
| `tests/test_pipeline_smoke.py` (patient + episode CLI smoke) | ~25 |
| **Phase A total** | **~116** |
| **Phase B** | |
| `backend/app/data/variable_metadata.json` (nhd_bluespace entry) | +12 |
| `backend/app/variable_registry.py` (`_assert_nhd_data_present`) | ~25 |
| `backend/app/experiments/nhd_bluespace.py` | ~300 |
| `backend/tests/test_nhd_bluespace.py` (8 tests) | ~150 |
| `backend/tests/test_e2e_nhd_bluespace_cohort.py` | ~95 |
| `backend/tests/test_e2e_multi_experiment_with_nhd.py` | ~125 |
| `backend/tests/test_variable_registry.py` (+2 tests) | ~20 |
| `backend/tests/test_task_manager_dispatch.py` (+1 test) | ~15 |
| `backend/tests/test_merge_partial.py` (+1 test) | ~14 |
| `backend/tests/manual_e2e.md` (Sprint 7 section) | ~35 |
| **Phase B total** | **~791** |
| **Grand total** | **~907** |

Wall-clock estimate: **2-3 focused work days.** Phase A is 0.5d
(scoped pipeline patch + three unit tests + helper adoption is
mechanical because Sprint 6 already established the template).
Phase B is 1.5-2d (cloned-and-trimmed runner from tiger_proximity
+ tests + smoke; no new render_yaml logic vs Sprint 5). The
4-experiment integration test is the longest single task — budget
2.5 hours.

## Manual smoke (`backend/tests/manual_e2e.md` Sprint 7 section)

```markdown
## Sprint 7 — NHD Bluespace + precomputed_static episode dispatch

Pre-flight:
- spacescans-pipeline editable install reflects Phase A
  (`resolve_output_grouping` adoption in
  `precomputed_static_linkage.py`). Verify with `python -c "from
  spacescans.linkage import precomputed_static_linkage; import
  inspect; print('resolve_output_grouping' in
  inspect.getsource(precomputed_static_linkage))"` — expect True.
- `$SPACESCANS_DATA_DIR/data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb`
  exists (61 GB). If missing, `_assert_nhd_data_present` short-circuits
  in test envs but the manual smoke needs the GDB to run C3.
- `C3_CACHE_DIR` exists (first run on a fresh cache takes longer).
- `backend/app/data/variable_metadata.json` has 5 entries including
  `nhd_bluespace`.

1. Variables-step renders 5 cards grouped by boundary:
   - "Block Group" section: NDI, EPA Walkability Index, TIGER Road
     Proximity, NHD Blue-Feature Proximity
   - "ZCTA5" section: Community Organization Density (ZBP)
   Each card shows label, description, unit chip, year-range chip,
   boundary chip. The NHD card's unit chip reads "meters",
   year-range "2024" (or "2024–2024" — cosmetic, see R7),
   boundary "BG".
2. Tick the NHD card → coverage panel mounts inline; same shape
   as Sprint 3/5 cards.
3. Tick all 5 variables → Review step → Run. Watch status.json:
   - `experiments` map shows bg_ndi_wi running first, then
     zcta5_cbp, tiger_proximity, nhd_bluespace in metadata-file
     order.
   - logs.jsonl carries entries from all four runners.
   - result.csv on completion carries
     ndi + NatWalkInd + all 10 r_* + 3 dist_* (TIGER) +
     5 dist_*_m (NHD) columns.
4. Repeat the same task; second run should hit the `BG_NHD` C3
   cache (status.json shows c3_nhd_bluespace progresses to 100% in
   < 1s for the cached cohort + buffer). Inspect `C3_CACHE_DIR`
   total size; alert if > 10 GB (R12).
5. Negative test: edit `configs/c4/nhd_bluespace_demo.yaml` to
   change `output_grouping: patient` to an unknown value (e.g.
   `output_grouping: foo`); run a fresh task. Expect a clear
   ValueError in logs.jsonl from
   `spacescans.linkage.helpers.resolve_output_grouping`:
   `unsupported output_grouping: 'foo' (expected 'patient' or 'episode')`.
   Restore the YAML. NOTE: do NOT test by *removing* the key —
   `TimeConfig.output_grouping` defaults to `"patient"` at the
   dataclass level, so a missing key silently falls back to
   patient-grouping instead of raising. Catching that regression
   requires the explicit-typo test, not an absent-field test.
6. Pre-flight failure test: temporarily rename
   `$SPACESCANS_DATA_DIR/data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb`
   to `.bak`; restart the server. Expect server boot to fail with
   `MetadataSchemaError: nhd_bluespace catalogued but NHDPlus_H GDB
   missing at …`. Restore the file and restart.
```

## CDLA attribution / data provenance

NHDPlus_H National Release 2 GDB is a USGS / EPA joint public-domain
release; no CDLA attribution is required for the blue-feature
distance variable (distinct from the building-sampled patient cohort
which uses Microsoft Building Footprints under CDLA-Permissive 2.0).
The variable's description string names "NHDPlus_H National Release 2
GDB" verbatim so the data source surfaces in the wizard UI; no
additional `LICENSES.md` entry is added in Sprint 7.

## Appendix: files NOT touched

Files the dispatcher/registry architecture lets Sprint 7 skip:

- `backend/app/dispatcher.py` — discovers `nhd_bluespace` via the
  registry's filesystem glob.
- `backend/app/task_manager.py` — `start_task` dispatches via the
  registry.
- `backend/app/experiments/_merge.py` — `write_partial` reads
  `value_cols` from the registry.
- `backend/app/experiments/bg_ndi_wi.py`,
  `backend/app/experiments/zcta5_cbp.py`,
  `backend/app/experiments/tiger_proximity.py` — existing `_BOUNDARY`
  constants unchanged; cache hits preserved.
- `frontend/src/lib/api.ts`, `frontend/src/lib/variable-grouping.ts`,
  `frontend/src/components/wizard/*.tsx` — registry-driven.
- `backend/app/routers/variables.py` — serves the registry payload.
- `src/spacescans/plugins/readers/nhd.py` — reader already returns
  the five `dist_*_m` value_cols with `geoid` as int64; no schema
  edits needed.
- `src/spacescans/linkage/precomputed_areal_linkage.py` — Sprint 5
  dispatch unchanged; Sprint 6 helper adoption already landed.
- `src/spacescans/linkage/helpers.py:resolve_output_grouping` —
  Sprint 6 T6 helper; Sprint 7 only consumes it.
