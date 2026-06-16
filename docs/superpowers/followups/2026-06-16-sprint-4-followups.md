# Sprint 4 — Known Follow-ups for Sprint 5

Adversarial multi-lens review of Sprint 4 (correctness / spec compliance /
test quality / regression risk / security) ran post-final-review and produced
7 important findings deferred to Sprint 5. The Sprint 4 in-scope blockers
(F1a/F1b cancellation observability, F2 start_task lock pre-check, F3 startup
probe, F4 fan_in unit test, F5 require_user JWT verification, F6 inline
fan_in removal) are all addressed; these G-items are the residual deltas
exposed during final review.

## Important — address in Sprint 5

### G1. F1a TOCTOU race in dispatcher (dispatcher.py:140-153)

The dispatcher writes `experiments[exp_key].status = 'running'` BEFORE
`subprocess.Popen`, but only records `pid` AFTER Popen returns. If
`stop_task` fires inside that window, `runner_pids` is empty (the lookup
requires both `pid` present AND `status == 'running'`), so `stop_task`
falls back to SIGTERMing the supervisor — which kills the dispatcher
process itself before `proc.wait()` can return 143, breaking the
cancellation observability invariant Sprint 4 just established.

**Fix (Sprint 5):** re-order so the (pid, status='running') invariant
becomes true atomically. Two options:
- Dispatcher records `pid` first, then flips `status` to `'running'` —
  so the lookup never sees a half-armed slot.
- Each runner writes its OWN slot's `pid` as the first action on entry
  (before any heavy I/O), and the dispatcher only stamps
  `status='running'` after observing the pid land.

The second option is more robust against future dispatcher refactors.

### G2. F5 401 vs 403 inconsistency (routers/variables.py + routers/tasks.py)

T3 swapped `/api/variables` from the stub `require_user` to the real
`get_current_user` dependency. The new path uses FastAPI's `HTTPBearer`
with its default `auto_error=True`, which returns **403** on missing
`Authorization` header. Other endpoints (e.g. `/api/tasks/*`) consistently
return **401** for the same condition. Inconsistent contract for clients.

**Fix (Sprint 5):** standardize to **401** across the API. Either:
- Wrap `HTTPBearer` in a custom dependency that re-raises missing-header
  as `HTTPException(401)` before reaching `get_current_user`, or
- Set `HTTPBearer(auto_error=False)` and have `get_current_user` itself
  raise 401 when the credentials object is `None`.

### G3. F6 test_merge_results_missing_pipeline_row_fills_na weakened (unit-level coverage gap)

T7 updated this Sprint 2 unit test to assert `len(out) == 1` — i.e. only
the pipeline rows survive at the `write_partial` level, since the inline
fan_in was dropped from `bg_ndi_wi.merge_results`. The original
input-anchored NaN-fill assertion (input has N rows, output has N rows
with NaN for missing pipeline rows) was migrated to integration-only.

That leaves no unit-level guard on the dispatcher-level fan-in
behavior: a regression that drops the NaN-fill in `_merge.fan_in` is
only caught by the slow integration suite.

**Fix (Sprint 5):** add a unit test that calls `_merge.fan_in` directly
on a fixture with N input rows and a partial CSV missing some of them,
asserting the output preserves all N input rows with NaN for the
missing ones. This complements F4's `(pid, episode_id)` coverage and
restores parity with the assertion strength the Sprint 2 unit test had
pre-T7.

### G4. F6 standalone runner path no longer produces result.csv

With the inline `_merge.fan_in` removed from `bg_ndi_wi.merge_results`,
running `python -m app.experiments.bg_ndi_wi run <task_dir>` directly
(outside the dispatcher) produces only `result_bg_ndi_wi.csv`, NOT the
canonical `result.csv`. The dispatcher path produces `result.csv` via its
own fan-in over the completed slot list; the standalone path has no
equivalent step.

**Fix (Sprint 5):** pick one of:
- Document the limitation in `manual_e2e.md` and deprecate the standalone
  CLI invocation in favor of `task_manager.start_task` for all e2e flows.
- Add a `--standalone` flag to the bg_ndi_wi runner that re-enables an
  inline `_merge.fan_in` call, gated explicitly so the dispatcher path
  is never affected.

Option A is cleaner if no internal consumers still rely on the
standalone path; option B is the back-compat hedge.

### G5. F3 lazy probe vs spec "startup" language

`_assert_pipeline_version_compatible` is currently invoked at the first
`load_variables()` call, not at FastAPI app boot. The Sprint 3 spec
described this as a "boot-time / startup probe" — the first HTTP request
that hits `/api/variables` will still fail fast on a stale pipeline, but
a misconfigured server can pass `uvicorn --workers N` healthchecks
without ever surfacing the incompatibility.

**Fix (Sprint 5):** wire the probe into `app.main.create_app()` as a
FastAPI startup event so the server fails fast on stale pipeline at
boot. Keep the lazy call as defense-in-depth (the registry can still be
imported from CLI contexts without going through `create_app`).

### G6. F1b rc==143 conflates external SIGTERM with user cancellation

The dispatcher currently treats any `proc.wait()` returning **143** as a
user cancellation (preserving the runner's `cancelled` slot status). But
**143 == 128 + SIGTERM** is also produced by:
- the OOM killer (kernel SIGTERM under memory pressure),
- a sysadmin running `kill -15 <runner-pid>`,
- container shutdown (Docker/Kubernetes SIGTERM during pod eviction).

In all three cases the slot will be reported as `cancelled` rather than
`error`, which is a false-positive on user intent.

**Fix (Sprint 5):** add a sentinel mechanism so the dispatcher only
enters the cancelled branch when user intent is provable. Options:
- `stop_task` writes `.cancelled` in the task_dir before SIGTERMing;
  dispatcher checks for the sentinel on rc==143 and falls through to
  `error` if absent.
- `stop_task` sends a custom signal (SIGUSR1) the runner handler
  translates into a distinct exit code (e.g. 144), reserving 143 for
  external SIGTERM → `error`.

The sentinel-file approach is simpler and survives signal delivery
reordering.

### G7. test_tasks.py:167 stale @pytest.mark.skip

`test_start_lock_returns_409_when_busy` (in `backend/tests/test_tasks.py`
around line 167) carries a Sprint 3 `@pytest.mark.skip` with rationale
"TaskBusyError-on-busy is no longer the contract" — left over from the
T9 regression. Sprint 4's F2 fix **restored** that contract (start_task
pre-Popen lock probe → 409). The skip mark is now factually obsolete.

**Fix (Sprint 5):** remove the `@pytest.mark.skip` decorator on
`test_start_lock_returns_409_when_busy`. The test should pass against
the restored contract. If it doesn't, that's a separate Sprint 5 bug
report against F2.

## Already accepted as known minor gaps (not Sprint 5 follow-ups)

- markdown lint warnings in `manual_e2e.md` Sprint 4 section (verbatim block)
- `frontend/tsconfig.tsbuildinfo` shows as modified after tsc runs (cache artifact)
- `groupByExperiment` is O(catalog) — fine at <=20 variables
