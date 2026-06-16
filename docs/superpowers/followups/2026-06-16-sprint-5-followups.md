# Sprint 5 — Known Follow-ups for Sprint 6

Adversarial multi-lens review of Sprint 5 (5 lenses: correctness / spec
compliance / test quality / regression risk / cross-repo) ran post-B6.
1 blocker (fixed inline at commit `3eabacb`) plus 6 important findings
deferred to Sprint 6.

The blocker (`_sanity_check_pipeline_supports_precomputed_areal_episode`
grep needle was a no-op — pre-A1 source already contained "episode" 3
times in docstrings/comments) was fixed by switching the needle to
`"output_grouping"` plus adding 2 unit tests (positive + negative
monkeypatched stale source) at commit `3eabacb`.

## Important — address in Sprint 6

### H1. spacescans-pipeline version pin missing (R3 layer a vacuous)

Spec R3 layer (a) reads: "Phase A pyproject bump publishes a new wheel;
web's pin moves forward in the same PR". The web repo has no
`pyproject.toml` and `backend/requirements.txt` contains no
spacescans-pipeline pin. Without a version-pin gate the live pipeline
is whatever editable install happens to be on PYTHONPATH.

The fixed probe (commit `3eabacb`) is now load-bearing, but defence in
depth requires a structural pin too.

**Fix:** add `spacescans>=0.2` (or whichever version contains Phase A)
to `backend/requirements.txt`. Bump on each pipeline-side dispatch
change.

### H2. TIGER C4 server-boot pre-flight in variable_registry (R2 deferred)

Spec R2 describes a server-boot pre-flight inside
`variable_registry.load_variables()`: when `tiger_proximity` is
catalogued, assert `SPACESCANS_DATA_DIR/data_full/TIGER/C4` exists with
at least one `tiger{year}_roads/` subdir per coverage_years entry; raise
`MetadataSchemaError` at startup.

Sprint 5 shipped only `_assert_pipeline_version_compatible` (pipeline
imports + `TimeConfig.output_grouping`). The TIGER data presence check
is not implemented. Missing TIGER zips fail late, after lock
acquisition + a UI-visible "running" state.

**Fix:** in `variable_registry.load_variables`, iterate
`payload["variables"].values()` and for any `v["experiment"] ==
"tiger_proximity"` loop through `v["coverage_years"]` asserting per-year
subdir exists. Raise `MetadataSchemaError` with the missing path.

### H3. Cache-hit log source inconsistency across runners

T4-fix (commit `ae6ca7c`) switched the warm-cache-hit `_append_log`
source from `"runner"` to `step.name` in `tiger_proximity.py` only.
`bg_ndi_wi.py:474` + `zcta5_cbp.py` still use `source="runner"` for the
cache-hit log. UI step-filters keyed on c3 step names see warm-cache
`c3_tiger_roads` but NOT warm-cache `c3_bg` / `c3_zcta5`.

Same divergence likely exists for the other cache log lines
("cache check failed", "cache write", "cache write failed") which still
use `"runner"` even in `tiger_proximity.py`.

**Fix:** back-port `_append_log(step.name)` to `bg_ndi_wi.py` and
`zcta5_cbp.py` cache-hit lines for parity. Decide whether ALL
cache-related logs for a step should use `step.name` and apply
consistently.

### H4. test_three_experiment_dispatch_preserves_metadata_order
monkeypatches the order

`backend/tests/test_task_manager_dispatch.py:269-276` monkeypatches
`variables_by_experiment` to return a hard-coded dict in the expected
order. Tests dispatcher's order-preservation only — does NOT test that
`variable_registry.variables_by_experiment` actually returns that order
from `metadata.json`.

The real coverage of file-order lives in `test_variable_registry.py:177`
+ the integration test (timestamp comparison). The unit test as written
would pass even if `variables_by_experiment` returned scrambled order.

**Fix:** remove the monkeypatch, let the test exercise the real metadata
file. OR add a clarifying comment that ordering correctness in this test
is dispatcher-only.

### H5. precomputed_areal_linkage.py:118 NoneType risk

`config.time.output_grouping` is dereferenced unconditionally;
`src/spacescans/models/config.py:189` declares `time: TimeConfig | None
= None`. A future call site without a time block raises `AttributeError`
(NoneType) not `ValueError`.

Pre-existing pattern shared with `yearly_areal_linkage.py:50` (Sprint 2)
— not Phase A regression, but Phase A reproduced the shape rather than
fixing it.

**Fix:** in both `precomputed_areal_linkage.py` and
`yearly_areal_linkage.py`, guard `config.time` for None and raise
`ValueError("precomputed_areal requires a time block")` early.

### H6. Smoke test PYTHONPATH workaround for editable-install drift

A2 implementer added a PYTHONPATH override to the smoke test subprocess
to ensure the worktree's A1 dispatch code is loaded (since editable
install resolves to main checkout). Once Phase A is merged this override
becomes a no-op but stays in the test as developer affordance.

**Fix (cleanup):** remove the PYTHONPATH override from
`test_pipeline_smoke.py` once Sprint 5 has been stable in production for
a release cycle (or move to a test-helper that conditionally sets it
only when the test is run from a worktree differing from the editable
install's path).

## Already accepted as known minor gaps (not Sprint 6 follow-ups)

- `frontend/tsconfig.tsbuildinfo` shows modified after tsc runs (cache
  artifact)
- A2 smoke test's KeyError vs AssertionError RED message divergence
  (functionally equivalent, plan-prediction off by Python evaluation
  order)
