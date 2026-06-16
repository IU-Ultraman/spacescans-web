# Sprint 3 — Known Follow-ups for Sprint 4

Adversarial multi-lens review of Sprint 3 (correctness / spec compliance /
test quality / regression risk / security) ran post-T15 and produced one
blocker (fixed) plus 6 important findings deferred to Sprint 4.

The blocker (`status.json` always reported `progress: 0.0 / steps: []` in
dispatcher-driven runs) was fixed at commit `6d07ad6` —
dispatcher seeds each experiment slot's `steps` and `progress`,
runners write to their own slot under dispatcher mode, both runners now
delegate to the atomic `task_manager._write_status`.

## Important — address in Sprint 4

### F1. Cancellation observability under dispatcher

`stop_task` SIGTERM → runner writes `status="cancelled"` → `SystemExit(143)`.
The dispatcher's `proc.wait()` returns `143`, treats non-zero as failure,
marks the slot `"error"` and remaining slots `"skipped_due_to_prior_failure"`.
The runner's intended `"cancelled"` slot status is overwritten.

**Fix:** dispatcher inspects the slot status BEFORE overwriting on non-zero rc:
if the slot already reads `"cancelled"`, preserve that and skip the
"skipped_due_to_prior_failure" cascade (set them to `"cancelled"` instead).
Or, more cleanly, the dispatcher only stamps `"error"` when the rc is
non-143 AND the slot is not already cancelled.

### F2. start_task lock pre-check (regression from T9)

`start_task` no longer holds `.run_lock` before Popen-ing the dispatcher;
two near-simultaneous HTTP POSTs both succeed at the request layer. The
loser's dispatcher Popens, the loser's runner subprocess fails to acquire
`.run_lock` (fcntl exclusive in `bg_ndi_wi.run` / `zcta5_cbp.run`), the
dispatcher records the error and exits, the user sees `status="error"`
with no obvious 409 signal.

Sprint 2 integration test `test_lock_prevents_concurrent_start` was the
canonical regression for this; it now FAILS (acknowledged in T14 report).

**Fix:** restore the pre-Popen lock probe in `start_task` (try
`fcntl.flock(... LOCK_EX | LOCK_NB)` to a sentinel + immediately release;
if it fails raise `TaskBusyError` so the request returns 409). Or, more
robust: keep the lock probe inside the dispatcher and have the dispatcher
exit with a distinct rc that `start_task` can map to 409 — though that
requires synchronous wait which contradicts the async-supervisor model.

### F3. R8 startup probe (editable-install drift)

Spec lines 1605, 1696–1700 require `variable_registry.load_variables()`
to also import the upstream pipeline package and assert
`hasattr(TimeConfig, 'output_grouping')` — so a stale editable install
of spacescans-pipeline fails at boot, not mid-run.

Currently absent. A `zcta5_cbp` run against an older pipeline would
silently emit per-patient (not per-episode) rows, and only the integration
test would catch it.

**Fix:** add to `variable_registry.load_variables`:

```python
def _assert_pipeline_version_compatible() -> None:
    from spacescans._extras import require as _require_extra
    _require_extra('rda', 'pyreadr')          # blocks zcta5_cbp without pyreadr
    from spacescans.models.config import TimeConfig
    if 'output_grouping' not in TimeConfig.model_fields:
        raise MetadataSchemaError(
            "pipeline missing TimeConfig.output_grouping — install/upgrade "
            "spacescans-pipeline >= 0.2 (Sprint 2 episode-dimension contract)."
        )
```

Call once at first `load_variables(force=True)`.

### F4. `_merge.fan_in` (pid, episode_id) unit test gap

Sprint 2 R6 contract — fan_in preserves one row per `(pid, episode_id)`
even with NaN fills — is only covered end-to-end. A unit-test mutation
that drops the `episode_id` key from the merge would pass current unit
tests (only the e2e catches it).

**Fix:** add a `_merge.fan_in` unit test with a 5-pid × 2-episode fixture
(10 rows input) and a partial CSV missing 3 of the 10 episodes, asserting
output is exactly 10 rows with NaN in 3 of them.

### F5. `require_user` is a Bearer-presence-only stub

`backend/app/routers/tasks.py::require_user` checks `Authorization` header
existence but does NOT decode/verify the JWT. Any non-empty Bearer string
gates `/api/variables` open. Adequate for a non-sensitive catalog endpoint,
but inconsistent with `get_current_user` (which DOES verify) used by
`/api/tasks/*` routes.

**Fix:** swap `require_user` for `get_current_user`. `/api/variables`
response is non-PII; the change is purely a consistency / defense-in-depth
move.

### F6. T5 inline `_merge.fan_in` in `bg_ndi_wi.merge_results`

Sprint 3 T5 added an inline `_merge.fan_in([bg_ndi_wi])` call so Sprint 2's
standalone integration test (which spawns `bg_ndi_wi.run` directly, not
through the dispatcher) still produces `result.csv`. Under the dispatcher
path, the dispatcher then calls fan_in AGAIN over the full `completed`
list, overwriting the first write. Not corrupting (fan_in restarts from
input.csv), but:
- 2× merge I/O per dispatcher run for the bg_ndi_wi slot
- a polling client could see a transient `result.csv` with bg-only columns
  before the dispatcher's overwrite lands
- asymmetric with zcta5_cbp.merge_results (which does NOT inline fan_in)

**Fix (Sprint 4):** drop the inline fan_in from bg_ndi_wi.merge_results
and migrate Sprint 2's standalone integration test (`test_e2e_multi_episode_cohort`)
to drive the dispatcher path (via `task_manager.start_task`) so result.csv
is produced through the canonical fan-in.

## Already accepted as known minor gaps (not Sprint 4 follow-ups)

- markdown lint warnings in `manual_e2e.md` Sprint 3 section (verbatim block)
- `frontend/tsconfig.tsbuildinfo` shows as modified after tsc runs (cache artifact)
- `groupByExperiment` is O(catalog) — fine at ≤20 variables
