# Sprint 2: Episode Dimension Preservation — Design Spec

## Goal

Stop collapsing residential episodes when emitting the merged
`result.csv`. Each row in the user's uploaded CSV is a distinct
(patient, episode) — a residential address with a time window. Today,
spacescans-pipeline's C4 patterns aggregate every episode into a single
overlap-days-weighted-average per PATID before the web app even sees
the output, so multi-address EHR cohorts lose their residential
history at the join step.

Sprint 2 makes the output dimension configurable. By default the
pipeline keeps its existing per-PATID collapse (so R / CLI consumers
are unaffected). When the web app renders a YAML it will pass
`time.output_grouping: episode`, which causes C4 patterns to emit one
row per (PATID, geoid) — with `geoid` being the synthetic per-row id
that the existing `demo_conus` adapter already manages. The web app
then joins on (pid, episode_id) instead of pid.

The change is small in code (~350 LOC) but architecturally important:
it aligns the web result with the pipeline's internal `build_episode_periods`
output and unlocks correct behaviour for any future cohort with multiple
addresses per patient.

## Scope

### In scope (Sprint 2)

- `TimeConfig.output_grouping: str = "patient"` field in spacescans-pipeline.
- Three C4 linkage patterns dispatch on this field: `yearly_areal`,
  `yearly_areal_bg_vintage`, `static_areal`. `"patient"` keeps the current
  `temporal_aggregate(group_by="PATID")` collapse; `"episode"` adds
  `geoid` to the group keys so each (PATID, geoid) tuple is preserved.
- `_adapt_demo_conus` reads `episode_id` from the input parquet when
  present (falling back to `range(len(df))` for legacy callers).
- spacescans-web's `csv_to_parquet` adds an `episode_id = range(len(df))`
  column to `input.parquet`.
- spacescans-web's `render_yaml` injects
  `time.output_grouping: "episode"` into every C4 YAML.
- spacescans-web's `merge_results` reconstructs the same `episode_id`
  on the input CSV side and joins each variable parquet on
  `(pid, episode_id)` instead of `pid`.
- Frontend results page renders a one-line "Result shape: one row per
  residential episode" hint above the download button.
- Unit + integration tests on both repos covering the new dispatch,
  the adapter fallback, the multi-episode join, and an end-to-end
  multi-episode cohort run.

### Out of scope (deferred)

- Episode-aware UI (per-episode time-series charts, residential
  timeline visualization). Sprint 3+.
- A real EHR cohort fixture. Tests use a synthetic
  `patients_multi_episode.csv` with 5 PATIDs × 2 episodes + 1
  single-episode patient.
- Persistence of `episode_id` across task re-creations on the same
  CSV. The id is derived from row position at csv_to_parquet time;
  re-uploading a re-ordered CSV will produce different ids. Acceptable
  for v2 since result.csv carries the id explicitly.
- Backwards-compatible mode for Sprint 1 result consumers. Anyone with
  an in-flight task from before this change should re-run.
- Episode overlap detection (same PATID, two episodes with overlapping
  date ranges). Pipeline silently TWA-weights by `overlap_days`, which
  is the documented behaviour. Cleanup of overlapping episodes is an
  EHR data-prep concern, not Sprint 2.
- User-supplied `episode_id` as a join key. If the input CSV has an
  `episode_id` column, csv_to_parquet **overwrites** it and logs a
  warning. Stable user identities can be reintroduced in Sprint 3+
  when cohort/task decoupling lands.

## Architecture

```text
spacescans-pipeline (upstream)              spacescans-web
────────────────────────────────────        ───────────────────────────────

models/config.py                            backend/app/experiments/bg_ndi_wi.py
  TimeConfig                                  csv_to_parquet:
    + output_grouping: str = "patient"          ★ df["episode_id"] = range(len(df))
                                              render_yaml:
linkage/{yearly_areal,                          ★ cfg.setdefault("time", {})[
            yearly_areal_bg_vintage,                 "output_grouping"] = "episode"
            static_areal}_linkage.py          merge_results:
    temporal_aggregate(                         ★ df["episode_id"] = range(len(df))
      group_by=                                   ★ join on (pid, episode_id)
        ["PATID", "geoid"]
          if output_grouping == "episode"     backend/tests/fixtures/
        else ["PATID"]                         + patients_multi_episode.csv
    )                                         backend/tests/manual_e2e.md
                                                ★ Sprint 2 section
linkage/helpers.py                          frontend/.../results/page.tsx
  _adapt_demo_conus:                          ★ "Result shape: per-episode" hint
    ★ if "episode_id" in df.columns:
        df["geoid"] = df["episode_id"].astype(int)
      else:
        df["geoid"] = range(len(df))


Phase order:
  A. Pipeline repo PR + merge (worktree, tests, push to spacescans-pipeline origin)
  B. Web repo: editable-installed spacescans picks up Phase A changes automatically
     → 4 web edits + tests + commit on feat/sprint-2-episode-dimension
```

### Architectural choices and rationale

- **YAML default `"patient"`.** Other pipeline consumers (R scripts, CLI
  users) don't pass this field; they keep getting per-PATID output.
  Web is the only caller that opts into `"episode"`.
- **`episode_id` is web-assigned, not user-supplied.** Anchoring on
  `range(len(df))` at csv_to_parquet time lets `merge_results`
  reconstruct the same id deterministically without storing it. The
  invariant: "row N of input.csv has episode_id == N."
- **Pipeline `geoid` is the carrier.** The `demo_conus` adapter already
  produces a synthetic per-row id named `geoid`; we hijack it to mean
  "episode_id" rather than introduce a new column name. Net: pipeline
  schema is unchanged; only `temporal_aggregate.group_by` widens.
- **Same `episode_id` recomputation in `csv_to_parquet` and
  `merge_results`.** Two `range(len(df))` calls produce identical
  series as long as the input.csv row order is the same — which it is,
  since merge_results reads the same file the pipeline read.
- **C3 cache is orthogonal.** Cache key is SHA256 of `input.parquet`;
  the new `episode_id` column changes the bytes, so adding it shifts
  every key, but the cache stays consistent: hit when the same CSV
  produces the same parquet, miss when a single byte changes. No
  cache invalidation needed.

## Data Flow

### Phase A — pipeline change

```text
1. YAML carries `time.output_grouping: "episode"` (web injects)
2. yearly_areal / yearly_areal_bg_vintage / static_areal compute
   group_by_keys = ["PATID"] + (["geoid"] if output_grouping == "episode" else [])
3. temporal_aggregate emits one row per (PATID, geoid) tuple
4. Result parquet schema becomes: PATID, geoid, <value_col>
   (was: PATID, <value_col>)
```

### Phase B — web change

```text
1. User uploads input.csv (N rows; some PATIDs may appear multiple times
   if the cohort represents multi-episode patients).

2. csv_to_parquet reads CSV:
   - parses startDate/endDate
   - assigns FIPS string dtype
   - assigns df["episode_id"] = range(len(df))    ← NEW
   - writes input.parquet (with episode_id column)

3. SHA256(input.parquet) feeds C3 cache key.

4. For each pipeline step:
   - render_yaml injects 5 + 1 keys (the new one is
     time.output_grouping="episode").
   - run_pipeline_step spawns spacescans subprocess.
   - Pipeline reads input.parquet → _adapt_demo_conus copies
     episode_id → geoid → temporal_aggregate groups by (PATID, geoid)
     → per-step parquet emitted with (PATID, geoid, value).

5. merge_results:
   - df = pd.read_csv(input.csv, dtype=str)
   - df["episode_id"] = range(len(df))            ← same assignment
   - for var in variables:
     - var_df = read_parquet(output/c4_<var>.parquet)
     - var_df = var_df.rename({"PATID": "pid", "geoid": "episode_id"})
     - df = df.merge(var_df, on=["pid", "episode_id"], how="left")
   - df.to_csv("result.csv")

6. result.csv schema:
   pid, startDate, endDate, longitude, latitude, [FIPS cols],
   episode_id, ndi, NatWalkInd
   - Row count == input.csv row count.
   - episode_id is 0..N-1 by input row position.
   - For demo cohort (1 episode per patient), behaviour is identical
     to v1 plus an additional episode_id column.
```

## Pipeline Modules (Phase A)

### Modified files (spacescans-pipeline)

**`src/spacescans/models/config.py`** — add one field to TimeConfig:

```python
class TimeConfig(BaseModel):
    years: list[int] | None = None
    start_date: str | None = None
    end_date: str | None = None
    temporal_resolution: str = "yearly"
    temporal_mode: str = "yearly"
    output_grouping: str = "patient"  # "patient" | "episode"
```

**`src/spacescans/linkage/yearly_areal_linkage.py`** — wider group_by:

```python
group_by_keys = ["PATID"]
if config.time.output_grouping == "episode":
    group_by_keys.append("geoid")
elif config.time.output_grouping != "patient":
    raise ValueError(
        f"unsupported output_grouping: {config.time.output_grouping!r}"
    )

result = engine.temporal_aggregate(
    episode_exp,
    TemporalAggSpec(
        group_by=group_by_keys,
        period_col="period_id",
        value_cols=config.exposure.value_cols,
        weight_col="overlap_days",
    ),
)
```

**`src/spacescans/linkage/yearly_areal_bg_vintage_linkage.py`** — same
dispatch pattern; the bg_vintage variant follows the same temporal
aggregation step as `yearly_areal`.

**`src/spacescans/linkage/static_areal_linkage.py`** — Walkability path
uses `engine.duration_weighted` instead of `temporal_aggregate`. Apply
the same dispatch:

```python
group_by_keys = ["PATID"]
if config.time.output_grouping == "episode":
    group_by_keys.append("geoid")
elif config.time.output_grouping != "patient":
    raise ValueError(...)

result = engine.duration_weighted(
    episodes,
    geoid_values,
    DurationWeightedSpec(
        group_by=group_by_keys,
        ...
    ),
)
```

(If `duration_weighted` doesn't currently accept a list `group_by`, that's
a separate small change in the engine layer documented in the
implementation plan.)

**`src/spacescans/linkage/helpers.py`** — adapter fallback:

```python
def _adapt_demo_conus(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={
        "pid": "PATID",
        "startDate": "start",
        "endDate": "end",
        "longitude": "long",
        "latitude": "lat",
    })
    if "episode_id" in df.columns:
        df["geoid"] = df["episode_id"].astype(int)
    else:
        df["geoid"] = range(len(df))
    return df[["PATID", "start", "end", "long", "lat", "geoid"]].copy()
```

### Tests (spacescans-pipeline)

`tests/test_temporal_episode_grouping.py` (new) — 5 tests covering both
groupings × all three patterns + invalid value.

`tests/test_demo_conus_adapter.py` (new) — adapter prefers
`episode_id` column when present, falls back otherwise.

## Web Modules (Phase B)

### Modified files (spacescans-web)

**`backend/app/experiments/bg_ndi_wi.py`** — three small changes:

```python
# csv_to_parquet:
df["episode_id"] = range(len(df))

# render_yaml:
cfg.setdefault("time", {})["output_grouping"] = "episode"

# merge_results:
df = pd.read_csv(task_dir / "input.csv", dtype=str)
df["episode_id"] = range(len(df))
for var in variables:
    var_df = pd.read_parquet(task_dir / "output" / _VARIABLE_PARQUET[var])
    var_df = var_df.rename(columns={"PATID": "pid", "geoid": "episode_id"})
    df = df.merge(var_df, on=["pid", "episode_id"], how="left")
    # match_pct warning unchanged (still operates on input rows)
df.to_csv(task_dir / "output" / "result.csv", index=False)
```

**`frontend/src/app/dashboard/task/[id]/results/page.tsx`** — add a
hint above the download section:

```tsx
<div className="text-xs text-muted-foreground mb-2">
  <strong>Result shape:</strong> one row per residential episode
  (matches your input CSV row count). Each row carries the original
  patient + episode metadata plus exposure values per selected variable.
</div>
```

### Tests (spacescans-web)

**`backend/tests/test_bg_ndi_wi.py`** — 5 new tests:

- `test_csv_to_parquet_adds_episode_id` — output parquet has the
  column with values 0..N-1.
- `test_csv_to_parquet_overrides_user_episode_id_with_warn` — if input
  CSV has an `episode_id` column it gets overwritten and a warning is
  emitted via `_append_log(task_dir, "warning", "runner", ...)` (the
  same channel Sprint 1's match_pct warning uses, so it appears in
  the LogViewer alongside other pipeline messages).
- `test_render_yaml_injects_output_grouping_episode` — rendered C4
  YAML's `time.output_grouping == "episode"`.
- `test_render_yaml_creates_time_block_if_absent` — C3 template
  without `time:` block gets one created safely.
- `test_merge_results_joins_on_pid_and_episode_id` — synthetic 10-row
  input (5 PATIDs × 2 episodes) + matching 10-row variable parquet →
  result.csv has 10 rows, `episode_id` column present, no row
  duplication.

**`backend/tests/test_bg_ndi_wi_integration.py`** — 1 new test:

- `test_e2e_multi_episode_cohort` — uses
  `tests/fixtures/patients_multi_episode.csv` (10 rows, 5 multi +
  1 single PATID), runs the real pipeline, asserts result.csv has 10
  rows and that each PATID's two episodes have **distinct
  `episode_id`** values.

**`backend/tests/fixtures/patients_multi_episode.csv`** (new) — see
Section 3 of the brainstorm for the exact 10-row contents (5 patients
× 2 residential moves over 2013–2020 + 1 single-episode control).

### Manual smoke addition (`backend/tests/manual_e2e.md`)

```markdown
## Sprint 2 multi-episode walk-through

Upload `backend/tests/fixtures/patients_multi_episode.csv` (10 rows, 5
multi-address patients + 1 single).

1. Reach the Variables step. The coverage panel should still render
   (Sprint 1 functionality unaffected) and show ~100% coverage on
   this small synthetic set.
2. Run the task with default 270m buffer + both NDI and Walkability.
3. Download result.csv. Open in spreadsheet / pandas.
4. Verify:
   - 10 rows (not 6 = unique PATID count).
   - `episode_id` column present, values 0..9.
   - PID0000001 appears twice (episode_id 0 + 1) with potentially
     different NDI values reflecting the IL → FL move.
   - PID0000006 appears once (single episode), same as Sprint 1.
```

## Error Handling

### Pipeline failure matrix

| # | Failure | Behaviour |
|---|---|---|
| 1 | YAML lacks `time.output_grouping` | TimeConfig default `"patient"` — v1 behaviour preserved. |
| 2 | YAML has `time.output_grouping: "rubbish"` | `ValueError("unsupported output_grouping: 'rubbish'")` — fail fast at C4 step. |
| 3 | `episode_id` column present in parquet but contains NaN | `astype(int)` raises `IntCastingNaNError` — clean traceback to runner. |
| 4 | `episode_id` column present with non-integer dtype | `astype(int)` either coerces (if floats representing ints) or raises. |
| 5 | `episode_id` column absent (legacy / non-web caller) | Adapter falls back to `range(len(df))` — old behaviour. |
| 6 | `output_grouping="episode"` but `geoid` column missing from `episode_exp` join input | Engine SQL error — clear "column not found" message. |

### Web failure matrix

| # | Failure | Behaviour |
|---|---|---|
| 1 | User uploads CSV that happens to have `episode_id` column | `csv_to_parquet` overwrites; a single warning line into `logs.jsonl` (`source="runner"`) explaining the overwrite. |
| 2 | Multi-episode patient (same PATID, two rows) | Fully supported; each row gets its own `episode_id`, joins back as a separate result row. |
| 3 | C4 parquet emits an unexpected number of rows | `how="left"` join keeps input row count stable. Missing matches surface as NaN in `result.csv`. Match_pct warning fires (existing behaviour). |
| 4 | Old Sprint 1 task's `result.csv` is still being viewed | Pre-existing files don't change; only newly-run tasks emit the new shape. UI handles missing `episode_id` column gracefully (just won't render the hint, or rather still renders it — the hint is informational). |
| 5 | User restarts FastAPI between csv_to_parquet and pipeline subprocess | input.parquet persists; restart-safe. |

### C3 cache interaction

The cache key is SHA256 of `input.parquet` bytes. Adding the
`episode_id` column means every Sprint 1 task's input.parquet now
hashes differently — i.e., **all Sprint 1 cache entries become stale
the moment Sprint 2 ships**. This is correct behaviour: a Sprint 2
task with the new parquet shape must not reuse a Sprint 1 C3 weight
file (the weights are still valid in pure numerical terms — boundary
overlap doesn't care about episode_id — but the cache pessimism is
safer than risk of cross-version drift). Users may notice a one-time
slowdown on their first Sprint 2 task; subsequent tasks on the same
cohort hit the cache as expected.

To pre-empt the slowdown a sysadmin can `rm -rf backend/data/c3_cache/`
before deploy. The manual_e2e Sprint 2 walk-through includes this
note.

### Security

No new attack surface. The new YAML field is constrained to
`"patient" | "episode"` by an explicit allow-list check in the
pipeline. The web doesn't expose this field through any HTTP endpoint;
it's set internally by `render_yaml`.

## Testing

### Pyramid

```text
                ┌───────────────────────────┐
                │  Manual smoke             │   1 — multi-episode walk-through
                └───────────────────────────┘
              ┌───────────────────────────────┐
              │  Integration                 │   1 new (web) — e2e multi-episode
              │  (5-patient fixture, real    │       Pipeline tests don't need
              │   spacescans subprocess)     │       integration; their unit
              └───────────────────────────────┘       tests use mocked engine
        ┌──────────────────────────────────────────┐
        │  Unit                                    │   ~11 — 6 pipeline + 5 web
        │  Pipeline: dispatch on output_grouping,  │
        │  adapter fallback                        │
        │  Web: episode_id assignment, render_yaml │
        │  injection, merge on (pid, episode_id)   │
        └──────────────────────────────────────────┘
```

### CI behaviour

- Pipeline repo: `pytest -q` runs the 6 new unit tests + existing
  suite. No integration tests needed (unit tests fully cover the new
  dispatch logic with mocked engine).
- Web repo: `pytest -q` runs the 5 new unit tests + existing 69. The
  integration test is `@pytest.mark.integration` and skipped by default.
- `pytest -m integration` runs all integration tests including the new
  `test_e2e_multi_episode_cohort`, which takes ~30-60s on top of the
  existing 5 integration tests.

## Implementation Estimate

| Component | New / Modified LOC |
|---|---:|
| Pipeline `TimeConfig.output_grouping` field | +1 |
| Pipeline 3 linkage patterns dispatch | ~20 |
| Pipeline `_adapt_demo_conus` fallback | +3 |
| Pipeline tests | ~150 |
| Web `csv_to_parquet` | +5 |
| Web `render_yaml` | +3 |
| Web `merge_results` | +10 |
| Web frontend results hint | +5 |
| Web tests | ~150 |
| Multi-episode fixture | ~12 |
| Manual smoke addition | ~20 |
| **Total** | **~380** |

Wall-clock estimate: **~2 focused work days**, split as 0.75d Phase A +
1d Phase B + 0.25d smoke/review.

## Phase Sequencing

**Phase A must land first** because Phase B depends on the new
`time.output_grouping` field in the upstream `TimeConfig`. Concretely:

1. Create a feature branch in `/Users/xai/Desktop/spacescans-project`:
   `feat/output-grouping-per-episode`.
2. Make the 4 pipeline changes + add the 2 pipeline test files.
3. Run pipeline test suite: green.
4. Merge Phase A back to `main` (locally; user decides whether to push
   to spacescans-pipeline's origin — the web repo's editable install
   picks it up either way as long as it's on `main`).
5. Switch to spacescans-web worktree and verify `python -c "from
   spacescans.models.config import TimeConfig; print(TimeConfig.model_fields)"`
   shows the new field.

**Then Phase B**:

6. Create a worktree in `spacescans-web`: `feat/sprint-2-episode-dimension`.
7. Make the 4 web changes + 5 unit tests + 1 integration test + fixture
   + manual_e2e + frontend hint.
8. Run web test suite (unit + integration): green.
9. Sprint 2 wrap-up (finishing-a-development-branch in the web repo).

## Open Questions for Sprint 3+

- Sprint 3 adds 7 more experiments using additional linkage patterns
  (`cbp_fallback`, `fara_tract`, `tiger_proximity`, etc.). Each needs
  the same `output_grouping` dispatch — flag a follow-up audit when
  introducing each new pattern.
- Once cohort/task decoupling lands (later sprint), `episode_id` may
  need to be persisted on the cohort artifact (not recomputed per
  task). Defer until the cohort model exists.
- The `geoid` column name doubles as both a Census GEOID and a
  synthetic episode id in different contexts. After Sprint 3, consider
  renaming the synthetic id to `episode_id` throughout the pipeline
  for clarity. Out of scope here to avoid churning every existing
  consumer.
