# Sprint 4 Spec — Sprint 3 Follow-ups (F1-F6)

**Date:** 2026-06-16
**Status:** Approved by user 2026-06-16 (Sprint 3 follow-up cleanup)
**Goal:** Address all 6 IMPORTANT findings from Sprint 3's adversarial cross-lens
final review. No new experiments, no new linkage patterns, no UI changes.
Pure tech-debt cleanup so subsequent multi-experiment sprints (Sprint 5+)
build on a stable foundation.

## Background

Sprint 3 shipped 19 commits, 130 tests, registry-driven variables UI, the
ZCTA5×CBP runner, and the fan-out / fan-in dispatcher. The post-T15
adversarial multi-lens review (correctness / spec compliance / test
quality / regression risk / security) surfaced one blocker — fixed
in-sprint at commit `6d07ad6` (dispatcher slot seeding + atomic
`_write_status` delegation) — plus 6 IMPORTANT findings that did not
gate Sprint 3 ship but compound risk if carried into Sprint 5's
multi-experiment work.

The findings live in
`spacescans-web/docs/superpowers/followups/2026-06-15-sprint-3-followups.md`:

- **F1.** Cancellation observability under dispatcher — `stop_task`
  SIGTERM → runner writes `status="cancelled"` → `SystemExit(143)`, but
  the dispatcher treats any non-zero rc as failure and overwrites the
  slot with `"error"` + cascades remaining slots to
  `"skipped_due_to_prior_failure"`.
- **F2.** `start_task` lock pre-check regression from T9 — the pre-Popen
  `fcntl.flock(LOCK_EX | LOCK_NB)` probe was lost when the dispatcher
  Popen replaced the in-process orchestrator; Sprint 2's
  `test_lock_prevents_concurrent_start` regression is currently failing.
- **F3.** R8 startup probe — spec lines 1605, 1696–1700 require a boot-time
  assertion that the editable-installed `spacescans` pipeline has
  `TimeConfig.output_grouping` and a working `pyreadr` extra; absent
  today.
- **F4.** `_merge.fan_in` `(pid, episode_id)` unit-test gap — covered only
  end-to-end; a unit-test mutation that drops `episode_id` from the join
  key would pass.
- **F5.** `require_user` is a Bearer-presence-only stub on `/api/variables`,
  inconsistent with `get_current_user` (full JWT decode) on
  `/api/tasks/*`.
- **F6.** T5's inline `_merge.fan_in` in `bg_ndi_wi.merge_results` — runs
  a redundant second fan-in on the dispatcher path, with asymmetry vs
  `zcta5_cbp.merge_results` and a transient bg-only `result.csv`
  visibility window.

These six findings are the full scope of Sprint 4.

## Goal

Resolve F1-F6 without adding new behaviour. The Sprint 4 diff should
read as a sequence of small, independent fixups with regression tests;
the system's user-visible surface area is unchanged except for
cancellation semantics (F1) and HTTP 409 on concurrent
start (F2) — both of which restore intended Sprint 2 behaviour that
regressed in Sprint 3.

## Scope

### In scope (Sprint 4)

- **F1.** Dispatcher distinguishes cancellation (rc==143) from error
  (non-zero rc with no cancellation signal): cancelled slot preserved,
  remaining slots cascade as `"cancelled"` (not
  `"skipped_due_to_prior_failure"`), top-level status written as
  `"cancelled"` (not `"error"` / `"partial"`).
- **F2.** Restore pre-Popen `.run_lock` probe in
  `task_manager.start_task`: `fcntl.flock(LOCK_EX | LOCK_NB)` on the
  global lock fd, immediately release; on `BlockingIOError` raise
  `TaskBusyError`. Confirm `routers/tasks.py` maps
  `TaskBusyError` → HTTP 409. Restore
  `test_lock_prevents_concurrent_start` to green.
- **F3.** Add `_assert_pipeline_version_compatible()` to
  `variable_registry`, invoked once per process at first
  `load_variables(...)` call: requires `spacescans._extras.require('rda',
  'pyreadr')` succeed AND `'output_grouping' in TimeConfig.model_fields`.
  Raise `MetadataSchemaError` with an actionable message on failure.
- **F4.** Add a `_merge.fan_in` unit test for the
  `(pid, episode_id)` composite-key contract: 5-pid × 2-episode
  fixture (10 rows input), partial CSV with only 7 of the 10
  episodes, assert output is exactly 10 rows with NaN in the 3
  missing rows. Lives in `backend/tests/test_merge_partial.py`.
- **F5.** Swap `Depends(require_user)` → `Depends(get_current_user)` in
  `routers/variables.py`; delete the now-unused `require_user` from
  `routers/tasks.py`; update any tests that pass a non-JWT Bearer string.
- **F6.** Drop the inline `_merge.fan_in` from
  `bg_ndi_wi.merge_results`; migrate ALL FOUR Sprint 2 standalone
  integration tests in `test_bg_ndi_wi_integration.py` to drive the
  dispatcher path via `task_manager.start_task`. Both runners'
  `merge_results` become symmetric (`write_partial` only).

### Out of scope (deferred)

- New experiments — `tiger_proximity`, `nhd_bluespace`, `vnl`, `temis`,
  `fara_tract`, `noise`. Sprint 5+.
- Multi-experiment parallel spawn. Sequential remains the dispatcher
  contract.
- Frontend test framework (jest / vitest). Manual smoke continues.
- Per-variable shapefile coverage. Still bbox-based with CONUS envelope.
- The `geoid` → `episode_id` global rename in the upstream pipeline.
  Local rename inside `_merge.write_partial` remains the boundary.
- A metadata editor UI. Edits are still JSON-file-only.
- LRU cap on C3 cache directory.
- Coverage panel UI changes — F1's introduction of a `"cancelled"`
  terminal status MAY surface a new `experiments[<key>].status` value
  in the polling response. If the frontend's status-display logic
  already has a `cancelled` branch (it does, from Sprint 2) no UI work
  is required; the only possible tweak is the coverage panel's
  status-chip color palette, deferred unless QA flags it.

## F1 — Cancellation observability under dispatcher

### Today's behaviour

`stop_task` sends SIGTERM to the dispatcher's process group. The
runner's installed cancel handler at
`backend/app/experiments/bg_ndi_wi.py:332-340` (mirror at
`backend/app/experiments/zcta5_cbp.py:180-186`) catches the signal,
writes top-level `status="cancelled"` via the module-level
`_write_status(task_dir, status="cancelled", message="Task cancelled by
user")`, then `raise SystemExit(143)`.

The dispatcher's `proc.wait()` returns 143. The code at
`backend/app/dispatcher.py:153-161` is unconditional:

```python
rc = proc.wait()
if rc != 0:
    _mark_experiment(task_dir, exp_key, "error", current_step=None)
    for skipped in exp_keys[i+1:]:
        _mark_experiment(task_dir, skipped, "skipped_due_to_prior_failure", ...)
    break
completed.append(exp_key)
```

After the loop, the top-level write at `dispatcher.py:170-191` does:

```python
failed = [k for k in exp_keys if k not in completed]
if not completed:
    _write_status(task_dir, status="error", message=f"All experiments failed (first failure: {failed[0]})")
elif failed:
    _write_status(task_dir, status="partial", ...)
else:
    _write_status(task_dir, status="finished", ...)
```

Net result of a cancellation: top-level `status="cancelled"`
(set by the runner) is overwritten by the dispatcher to
`status="error"` with message `"All experiments failed (first failure:
bg_ndi_wi)"`; the cancelled slot is overwritten to `status="error"`;
remaining slots get `status="skipped_due_to_prior_failure"`.

### Target behaviour

A cancellation produces:

- The cancelled slot: `experiments[<key>].status = "cancelled"`.
- Remaining slots: `experiments[<key>].status = "cancelled"` (not
  `"skipped_due_to_prior_failure"`).
- Top-level: `status = "cancelled"`, `message = "Task cancelled by user"`.

### Design decision — discriminator: rc==143, not slot status

The followup doc's prose suggests "inspect the slot status before
overwriting on non-zero rc: if the slot already reads `cancelled`,
preserve that." But the runner's `_install_cancel_handler` writes
`cancelled` at the TOP LEVEL of `status.json`, not into
`experiments[<key>]` — see `bg_ndi_wi.py:333-337` (`_write_status` is
the top-level wrapper, not `_write_slot_status`). At the moment
`proc.wait()` returns 143, the slot at `experiments[<key>]` still reads
`"running"` (whatever the runner set before SIGTERM arrived).

Two paths to fix this:

1. Move the runner's `cancelled` write into the slot
   (`_write_slot_status`) so the dispatcher can inspect it.
2. Use `rc == 143` as the discriminator.

**Chosen: rc == 143.** Rationale:

- Single source of truth — the SIGTERM exit code is a UNIX-level signal,
  not a status.json convention that future maintainers might forget.
- Zero changes to runner code — the handler stays at the top level (where
  it's also useful for non-dispatcher invocations, e.g. direct
  `python -m app.experiments.bg_ndi_wi`).
- Symmetric with how `_write_slot_status` is currently used: only the
  dispatcher writes slot status; the runner writes top-level.

### Design decision — dispatcher SIGTERM handling (stop_task scope reduction)

The rc==143 discriminator only works if the dispatcher actually survives
long enough to observe `rc == 143` from `proc.wait()` and execute the
new write path. As `stop_task` is written today
(`task_manager.py:291-325`), it SIGTERMs BOTH the supervisor
(`status.pid`, lines 310-312) AND each running runner pid (lines
313-316). The dispatcher has no SIGTERM handler installed (verified by
grep — `dispatcher.py:151` has only a comment, no `signal.signal(...)`
call). Python's default SIGTERM disposition terminates the interpreter
immediately, without unwinding `finally` blocks or returning from
`proc.wait()`. Net consequence under the current `stop_task`: the
dispatcher dies before it ever reaches the new `if rc == 143:` branch,
the cancelled-slot + cascade-as-cancelled writes never happen, and the
E2E integration test below would assert against a `status.json` the
dispatcher never had a chance to update.

Two paths to make the rc==143 discriminator real:

- **Option (a):** Install a dispatcher-side SIGTERM handler that sets
  a `_cancelled` flag, finishes draining `proc.wait()`, and writes the
  cancelled top-level + slot status before `SystemExit(143)`. Requires
  adding `signal.signal(signal.SIGTERM, ...)` in `dispatcher.py` plus
  unwind logic that's careful about the in-flight `proc.wait()` call
  (which is itself a blocking syscall, interruptible by EINTR on the
  handler return).
- **Option (b):** Narrow `stop_task` to signal ONLY the runner pids,
  not the supervisor pid. The dispatcher then observes `rc == 143`
  naturally via its already-blocking `proc.wait()` (since SIGTERM to
  the runner sets its exit code to 143) and proceeds into the new
  rc==143 write path with no extra signal handling.

**Chosen: option (b).** Rationale:

- Smaller diff — one conditional in `stop_task`, no new signal
  handlers, no EINTR reasoning.
- Keeps the dispatcher's control flow synchronous and inspectable; the
  rc==143 branch is the single seam where cancellation is observed,
  matching the "single source of truth" framing of the rc==143
  discriminator choice above.
- The supervisor pid was being signalled defensively in case no runner
  pids were recorded (early-cancel before any runner started); that
  early-cancel case is handled by `stop_task`'s top-level status write
  already and does not need a supervisor SIGTERM.

`backend/app/task_manager.py:291-325` (`stop_task`) — change: only
issue SIGTERM to recorded runner pids when at least one is present;
when no runner pid is recorded (early cancellation before dispatcher
launched any slot), keep the existing supervisor-SIGTERM fallback so
the dispatcher process is still reaped. The integration test below
(`test_e2e_cancellation_terminal_state`) exercises the runner-pid
path; the supervisor-SIGTERM fallback is left as defensive-only and
covered by existing `stop_task` unit tests.

### Code changes

`backend/app/dispatcher.py` lines 153-161 (rc handling):

```python
rc = proc.wait()
if rc != 0:
    if rc == 143:
        # SIGTERM cancellation. Preserve cancelled lineage.
        _mark_experiment(task_dir, exp_key, "cancelled", current_step=None)
        for skipped in exp_keys[i+1:]:
            _mark_experiment(task_dir, skipped, "cancelled", current_step=None)
        cancelled = True
        break
    _mark_experiment(task_dir, exp_key, "error", current_step=None)
    for skipped in exp_keys[i+1:]:
        _mark_experiment(task_dir, skipped, "skipped_due_to_prior_failure", current_step=None)
    break
completed.append(exp_key)
```

A new local `cancelled = False` is initialized above the loop.

`backend/app/dispatcher.py` lines 170-191 (top-level write):

```python
if cancelled:
    _write_status(task_dir, status="cancelled", message="Task cancelled by user")
elif not completed:
    _write_status(task_dir, status="error", message=f"All experiments failed (first failure: {failed[0]})")
elif failed:
    _write_status(task_dir, status="partial", ...)
else:
    _write_status(task_dir, status="finished", ...)
```

### Test plan

- **New unit test** `test_dispatcher_cancellation_preserves_cancelled_status`
  in `backend/tests/test_dispatcher.py`: mock two-slot run where the
  first runner exits with rc=143 (simulated via a stub script). Assert:
  slot 1 status=`cancelled`, slot 2 status=`cancelled` (not
  `skipped_due_to_prior_failure`), top-level `status=cancelled`.
- **New integration test** `test_e2e_cancellation_terminal_state` in
  `backend/tests/test_dispatcher_cancellation.py`: start a real
  two-experiment task, wait for the first runner to enter the `prepare`
  step, call `stop_task`, poll until terminal. Assert top-level
  `status=cancelled` and both slots end `cancelled`.

## F2 — `start_task` lock pre-check

### Today's behaviour

`backend/app/task_manager.py:264-289`:

```python
def start_task(task_id: str) -> dict:
    task_dir = _task_dir(task_id)
    if not (task_dir / "config.json").exists():
        raise FileNotFoundError(...)
    cmd = [sys.executable, "-m", "app.dispatcher", "run", task_id]
    proc = subprocess.Popen(cmd, start_new_session=True, ...)
    _write_status(task_dir, pid=proc.pid)
    return {"pid": proc.pid, "task_id": task_id}
```

No `.run_lock` interaction. Two near-simultaneous POSTs both succeed at
the HTTP layer. Both Popen children launch; both runners contend for
the global `.run_lock` (still held inside `bg_ndi_wi.run:378-393` and
`zcta5_cbp.run:209-219`). The loser's `fcntl.flock(LOCK_EX | LOCK_NB)`
raises `BlockingIOError`; the loser's runner writes
`status="error", message="another task acquired the run lock first;
retry shortly"` and returns 1. The dispatcher sees rc=1, marks the slot
`"error"`, cascades `"skipped_due_to_prior_failure"` (F1 path again).
The user sees a meaningless `error`; the 409-semantic of "another task
is running" is lost.

`TaskBusyError` is still defined at `task_manager.py:157-161` but no
longer raised by anyone in the live path; only
`test_lock_prevents_concurrent_start` still references it, and that
test is currently failing.

### Target behaviour

`start_task` synchronously probes `.run_lock` before Popen. On lock
held, raise `TaskBusyError`. The router layer maps to HTTP 409.

### Design decision — which lock

**Chosen: the same `.run_lock` the runners hold.** Rationale:

- The lock's invariant ("only one pipeline run at a time on this host")
  is what we want to enforce, and it's the one the runners already
  defend at line 378-393 / 209-219. A separate `.dispatcher_lock`
  introduces a second lock with overlapping semantics and a race
  window between the dispatcher-lock probe and the runner-lock
  acquisition.
- The runner-side acquisition remains as defense-in-depth (covers the
  direct `python -m app.experiments.bg_ndi_wi` standalone invocation
  path even after F6 migrates the tests off it — the standalone CLI
  remains valid for ops debugging).
- `start_task` only PROBES (LOCK_NB then close) — it does NOT hold the
  lock across the Popen. The runner will acquire it for real. This
  preserves the "no orphaned lock if Popen succeeds but the parent
  request gets interrupted" property.

### Code change

`backend/app/task_manager.py:272-280`, insert between the config.json
existence check and the Popen:

```python
lock_path = app.config.settings.DATA_DIR / ".run_lock"
lock_path.touch(exist_ok=True)
probe_fd = os.open(str(lock_path), os.O_RDWR)
try:
    try:
        fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise TaskBusyError() from exc
    finally:
        # Release immediately — the runner will re-acquire.
        fcntl.flock(probe_fd, fcntl.LOCK_UN)
finally:
    os.close(probe_fd)
```

The block lifts verbatim from `bg_ndi_wi.run:378-393` minus the
exclusive-hold body.

`backend/app/routers/tasks.py` — verify the existing `/api/tasks/{id}/start`
handler catches `TaskBusyError` and returns 409. If absent, add:

```python
except TaskBusyError as exc:
    raise HTTPException(status_code=409, detail=str(exc))
```

### Test plan

- **Restore green** `test_bg_ndi_wi_integration.py::test_lock_prevents_concurrent_start`
  (lines 82-119): externally holds `.run_lock` via `fcntl.flock`, then
  `with pytest.raises(TaskBusyError): start_task(meta["id"])`. No code
  change to the test — the fix is in `start_task`.
- **New API-layer test** `test_api_tasks.py::test_start_returns_409_when_busy`:
  externally hold `.run_lock`, POST `/api/tasks/{id}/start`, assert
  `response.status_code == 409`.

## F3 — R8 startup probe

### Today's state

`backend/app/variable_registry.py:40-68` has no pipeline-version probe.
The Sprint 3 spec at lines 1605, 1696–1700 promised one; it was not
implemented. A `zcta5_cbp` run against a stale editable install
(missing `TimeConfig.output_grouping` or missing `pyreadr`) fails only
at runtime, mid-pipeline.

Confirmed in env: `from spacescans._extras import require` works;
`require('rda', 'pyreadr')` returns silently when pyreadr is installed
and raises on miss. `TimeConfig.model_fields` is a Pydantic v2 dict
with `'output_grouping'` as a key (default `'patient'`).

The followup doc's prose ("`hasattr(TimeConfig, 'output_grouping')`")
is misleading — Pydantic v2 stores field defs in `model_fields`, not
as class attrs. The code block in the same followup uses
`TimeConfig.model_fields`, which is the correct check. Sprint 4 uses
`model_fields`.

### Design decision — invocation point: once per process

The followup says "Call once at first `load_variables(force=True)`."
But `load_variables(force=True)` is rare in practice; the mtime cache
means a probe placed inside `load_variables` would fire on the first
call (good) and on every `force=True` call (wasteful but cheap).

**Chosen: module-level `_PROBE_DONE: bool = False`, set on first
successful probe, checked at the top of `load_variables`.** Rationale:

- The editable-install drift case (someone runs
  `pip install -e ../spacescans-pipeline` against an older branch) is
  static within a single Python process — the probe doesn't need to
  re-run on metadata file changes.
- Cheaper than "every load_variables call" (zero overhead after the
  first successful boot).
- Pure FastAPI `@app.on_event("startup")` is rejected: it would force
  the import of `spacescans.models.config` at server boot, slowing
  cold-start. Lazy-on-first-`load_variables` keeps the cost paid by
  the first request that needs the registry (which is the first
  request that needs the pipeline anyway).

### Code change

`backend/app/variable_registry.py`:

```python
_PROBE_DONE: bool = False


def _assert_pipeline_version_compatible() -> None:
    """Defensive boot-time check. Raises MetadataSchemaError on drift."""
    global _PROBE_DONE
    if _PROBE_DONE:
        return
    try:
        from spacescans._extras import require as _require_extra
        _require_extra("rda", "pyreadr")
        from spacescans.models.config import TimeConfig
    except Exception as exc:
        raise MetadataSchemaError(
            f"pipeline import failed: {exc}. "
            "Install/upgrade spacescans-pipeline >= 0.2 (Sprint 2 episode-dimension contract)."
        ) from exc
    if "output_grouping" not in TimeConfig.model_fields:
        raise MetadataSchemaError(
            "pipeline missing TimeConfig.output_grouping — install/upgrade "
            "spacescans-pipeline >= 0.2 (Sprint 2 episode-dimension contract)."
        )
    _PROBE_DONE = True
```

Called unconditionally at the top of `load_variables(...)` — BEFORE
the mtime fast-path check. The probe's own internal `_PROBE_DONE`
guard makes the call O(1) after the first successful invocation, so
cache hits stay fast (the only cost on cache hits is a function-call
+ a boolean check against the module-level flag). Placing the call
ahead of the fast-path also removes any ambiguity about whether a
warm cache could skip the probe entirely on first request.

**Note on the pyreadr requirement:** this makes pyreadr a hard runtime
dependency of the web backend even for `bg_ndi_wi`-only deployments. This
is a deliberate policy choice — Sprint 3 ships zcta5_cbp, and the
backend now claims to host both experiments unconditionally; partial
deployments (one experiment but not the other) would silently
mis-advertise via `/api/variables`. The probe makes the install posture
honest.

### Test plan

- **New unit test** `test_variable_registry.py::test_startup_probe_passes_in_env`:
  call `_assert_pipeline_version_compatible()` directly; expect no
  raise.
- **New unit test** `test_variable_registry.py::test_startup_probe_raises_on_missing_field`:
  monkeypatch `TimeConfig.model_fields` to drop `output_grouping`,
  call `_assert_pipeline_version_compatible()` (after resetting
  `_PROBE_DONE = False`), assert `MetadataSchemaError` with substring
  `"output_grouping"`.
- **New unit test** `test_variable_registry.py::test_startup_probe_runs_once`:
  exercises the `_PROBE_DONE` short-circuit directly (no
  `load_variables` involvement). Call `_assert_pipeline_version_compatible()`
  once to set `_PROBE_DONE = True`; then monkeypatch
  `spacescans._extras.require` to raise on any call; then call
  `_assert_pipeline_version_compatible()` again and assert no raise.
  Confirms the second invocation never re-enters the import path.

## F4 — `_merge.fan_in` `(pid, episode_id)` unit test

### Today's state

`backend/tests/test_merge_partial.py:124-176` has two `fan_in` tests:
both use 5 unique pids with `episode_id = list(range(5))` — one
episode per pid. Neither covers (a) the same pid with two different
episode_ids, nor (b) a partial CSV missing rows.

`backend/app/experiments/_merge.py:84-107` assigns
`df['episode_id'] = list(range(len(df)))` (global row index) and joins
each partial on `['pid', 'episode_id']`. A mutation that drops
`episode_id` from the join key would compile and would not be caught
by either existing test.

### Test design

**Fixture:** 10 input rows, 5 pids each appearing twice with two
different global episode_ids:

| pid | episode_id |
|-----|------------|
| A   | 0          |
| A   | 1          |
| B   | 2          |
| B   | 3          |
| C   | 4          |
| C   | 5          |
| D   | 6          |
| D   | 7          |
| E   | 8          |
| E   | 9          |

**Partial CSV** (`result_test_exp.csv`): 7 rows — drop episodes 1, 5, 9
(one missing episode for pids A, C, E):

| pid | episode_id | value |
|-----|------------|-------|
| A   | 0          | 10    |
| B   | 2          | 11    |
| B   | 3          | 12    |
| C   | 4          | 13    |
| D   | 6          | 14    |
| D   | 7          | 15    |
| E   | 8          | 16    |

**Assertions** in the new test
`test_merge_partial.py::test_fan_in_preserves_episode_pairs_with_partial_data`:

- `len(result_df) == 10` (no row loss, no row duplication).
- `result_df[result_df['value'].isna()].shape[0] == 3` (NaN in 3 rows).
- The NaN rows are exactly `(A, 1)`, `(C, 5)`, `(E, 9)`.
- `result_df.sort_values(['pid', 'episode_id'])` matches the input
  ordering — confirms the left-join preserves input row order on the
  composite key.

### Location

Append to `backend/tests/test_merge_partial.py` as a new test function;
no new file.

## F5 — `require_user` → `get_current_user` migration

### Today's state

`backend/app/routers/tasks.py:15-23`:

```python
_require_user_security = HTTPBearer(auto_error=False)

def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_require_user_security),
) -> dict:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"token": credentials.credentials}
```

Bearer-presence-only. Any non-empty token (e.g., `Bearer foo`) passes.
Used solely by `routers/variables.py:8`:

```python
from app.routers.tasks import require_user
...
def list_variables(_user=Depends(require_user)) -> VariableCatalogResponse:
```

`backend/app/auth.py:33-43` has `get_current_user` which performs
`jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])` and returns
`{"id": int, "email": str}` — full signature + exp verification via
`jose.jwt`.

### Code change

`backend/app/routers/variables.py`:

```python
# remove:
from app.routers.tasks import require_user
# add:
from app.auth import get_current_user
...
def list_variables(_user=Depends(get_current_user)) -> VariableCatalogResponse:
```

`backend/app/routers/tasks.py:15-23` — delete the `require_user`
definition and its `_require_user_security` HTTPBearer (no other
importers; confirmed by grep against the backend tree).

Return-shape change is safe at the call site: the dependency value is
bound to `_user` (unused).

### Test impact

`backend/tests/test_api_variables.py` has 4 tests that hit
`/api/variables`. They currently pass the literal hardcoded string
`"Bearer test-token"` (`test_api_variables.py:25`), which works ONLY
because `require_user` is a presence-only stub — i.e., it works
because of the very bug F5 is fixing. After the swap they must pass
a real JWT.

Actual state of the test tree (verified):

- There is no `backend/tests/conftest.py`. No shared `authed_client`
  / token-building fixture exists.
- `test_tasks.py` does NOT call `create_access_token` directly; its
  pattern (lines 39-43) is to POST `/api/auth/signup` and harvest the
  returned `access_token` from the response body. That pattern is
  heavier than necessary for `/api/variables` (signup writes a user
  row; the variables router only needs a validly signed token).

Two options for Sprint 4:

- **Option (a):** Add a small LOCAL helper inside
  `test_api_variables.py` that imports `create_access_token` from
  `app.auth` and mints a token directly:
  `create_access_token({"sub": "1", "email": "test@example.com"})`.
  Requires the same env-reload pattern `test_tasks.py` already uses
  so `SECRET_KEY` / `ALGORITHM` are consistent between token mint
  and verification. This is the smallest diff (one helper, no new
  files, no new fixtures) but is a NEW helper — not a reuse of any
  existing fixture.
- **Option (b):** Introduce `backend/tests/conftest.py` with an
  `authed_client` fixture that yields `(TestClient, headers)` with a
  pre-minted token. Reusable by future test files but is more new
  surface than F5 needs.

**Chosen: option (a).** Rationale: minimum diff, scope-matched to
F5 (which only touches `/api/variables`), no new shared fixture to
maintain. The earlier draft of this spec claimed Sprint 4 would
"reuse the existing token-building fixture" — that fixture does not
exist; this section is the corrected statement.

Mechanical changes per affected test:

```python
# at top of test_api_variables.py — new local helper
from app.auth import create_access_token

def _auth_headers() -> dict[str, str]:
    token = create_access_token({"sub": "1", "email": "test@example.com"})
    return {"Authorization": f"Bearer {token}"}

# in each of the 4 tests:
# before
headers = {"Authorization": "Bearer test-token"}
# after
headers = _auth_headers()
```

The same env-reload guard `test_tasks.py` uses (ensuring `SECRET_KEY`
is loaded before `create_access_token` is called) is added once at
the top of `test_api_variables.py`.

### Test plan

- Run the existing 4 `test_api_variables.py` tests after the swap;
  expect green with the token-fixture update.
- **New negative test** `test_api_variables.py::test_list_variables_rejects_invalid_jwt`:
  POST with `Bearer not-a-real-jwt`, assert 401 (was 200 under the old
  stub). Locks the consistency contract.

## F6 — T5 inline `fan_in` cleanup

### Today's state

`backend/app/experiments/bg_ndi_wi.py:232-247` (`merge_results`):

```python
_merge.write_partial(...)
return _merge.fan_in(task_dir=task_dir, experiment_keys=['bg_ndi_wi'])
```

The docstring at lines 233-238 anticipates this cleanup: "T9
(dispatcher) will move the fan_in step to the dispatcher's
post-experiment loop and strip this inline call." That cleanup is F6.

`backend/app/experiments/zcta5_cbp.py:189-197` (`merge_results`):

```python
return _merge.write_partial(...)
```

No inline fan_in. Asymmetric.

`backend/app/dispatcher.py:168-174` runs `_merge.fan_in(task_dir,
completed)` over the full completed list after every runner returns
successfully — so the dispatcher path produces TWO fan_in writes when
bg_ndi_wi runs (inline + dispatcher-final), and a brief window during
which `result.csv` contains only bg-only columns before the dispatcher
overwrite lands.

### Four standalone tests depend on the inline fan_in

`backend/tests/test_bg_ndi_wi_integration.py` has four
`@pytest.mark.integration` tests that all invoke
`subprocess.run([SPACESCANS_PIPELINE_PYTHON, '-m',
'app.experiments.bg_ndi_wi', 'run', task_dir])` (NOT through
`start_task` / dispatcher) and all assert `result.csv` exists:

1. `test_e2e_small_cohort` (line 73)
2. `test_two_sequential_runs_both_succeed` (lines 199-200)
3. `test_e2e_cache_second_run_faster` (uses the same fixture pattern)
4. `test_e2e_multi_episode_cohort` (line 299)

Dropping the inline fan_in breaks all four.

### Design decision — Option (a), full migration

The followup doc literally names only test (4), but tests (1)-(3) share
the same root coupling (assert `result.csv` exists after a standalone
`python -m app.experiments.bg_ndi_wi run`). Two choices:

- **Option (a):** Migrate all four to dispatcher-driven (`start_task`
  + status polling), drop the inline fan_in, both runners' merge_results
  become symmetric.
- **Option (b):** Keep the inline fan_in flagged as "Sprint 2 standalone
  compat — do not remove"; accept the asymmetry indefinitely; migrate
  only test (4).

**Chosen: option (a).** Rationale:

- Option (b) is a permanent two-codepath state. Every future change to
  `merge_results` must reason about whether `result.csv` exists at
  function exit under both invocation paths.
- The dispatcher path is stable enough post-`6d07ad6` (slot seeding +
  atomic writes) that the four tests should be reliable under it.
- F2 lands before F6 (see implementation order), so the migrated tests
  do not collide with the lock-pre-check regression.
- Eliminates the 2× merge I/O and the transient bg-only `result.csv`
  visibility window.
- Makes both runners' `merge_results` signatures honest — the docstring
  comparison in `zcta5_cbp.py:189-197` ("matches bg_ndi_wi T5 wrapper")
  becomes accurate.

### Migration pattern per test

The canonical dispatcher-driven test shape lives at
`backend/tests/test_e2e_multi_experiment.py:41-82`. Each Sprint 2 test
is rewritten to:

1. Build the fixture as today (cohort + variables) but write `config.json`
   via `task_manager.save_config(meta['id'], {...})` with `experiment:
   "auto"` (the dispatcher infers per-variable experiments from registry).
2. Replace `subprocess.run([..., '-m', 'app.experiments.bg_ndi_wi',
   'run', task_dir])` with `start_task(meta["id"])`.
3. Replace the synchronous return-code check with a poll loop:

   ```python
   deadline = time.monotonic() + 240.0
   while time.monotonic() < deadline:
       status = json.loads((task_dir / "status.json").read_text())
       if status.get("status") in ("finished", "error", "partial", "cancelled"):
           break
       time.sleep(1.0)
   assert status["status"] == "finished"
   ```

4. Assert `result.csv` exists (unchanged from today's assertion).

`test_e2e_multi_episode_cohort` retains its single-experiment intent —
its config uses only `ndi` / `walkability` (bg_ndi_wi variables); the
dispatcher runs with a single slot. This is the right scope: the test
proves per-episode rows for bg_ndi_wi, not multi-experiment dispatch
(which is what `test_e2e_multi_experiment_cohort` covers).

`test_two_sequential_runs_both_succeed` already exercises sequential
runs; under the dispatcher path, the second `start_task` call simply
launches a second dispatcher Popen — semantics preserved.

### Code change

`backend/app/experiments/bg_ndi_wi.py:232-247`:

```python
def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Delegate to shared _merge.write_partial.

    The dispatcher's post-experiment loop performs the final fan-in.
    """
    return _merge.write_partial(...)
```

Drop the inline `_merge.fan_in` call. Update the docstring; remove
the T9 forward-reference comment (it's now implemented).

### Test plan

- All four Sprint 2 integration tests in `test_bg_ndi_wi_integration.py`
  migrated to `start_task` + poll; all four assert `result.csv` exists
  (assertion unchanged). All four must still pass.
- `test_e2e_multi_experiment.py::test_e2e_multi_experiment_cohort`
  must still pass (regression check on the dispatcher path).
- `test_lock_prevents_concurrent_start` must still pass (interacts
  with F2's restored pre-check).
- A new symmetry assertion in `test_merge_partial.py` (already
  implicitly tested by the four migrated integration tests, no
  separate test needed).

## Implementation order

**F3 → F4 → F5 → F1 → F2 → F6.** Rationale (independence-first,
riskiest-last):

- **F3** (startup probe): zero coupling to anything else; a self-contained
  defensive add. Land first to surface any env-drift surprises early.
- **F4** (unit test): pure additive test, no production code change.
  Easy to land.
- **F5** (auth swap): isolated to two files (`routers/variables.py`,
  `routers/tasks.py`); 4 existing test fixups. Low risk.
- **F1** (cancellation): dispatcher.py changes + 2 new tests. Touches
  the dispatcher control flow but in a narrow window (rc handling
  + top-level write).
- **F2** (lock pre-check): restores a Sprint 2 contract that's
  documented and tested; small diff in `task_manager.start_task` +
  router 409-mapping verification.
- **F6** (inline fan_in cleanup): largest in test-line-count terms (four
  Sprint 2 integration tests migrated to dispatcher-driven). Lands
  last so F1's cancellation work + F2's lock pre-check are already in
  place when the migrated tests start running through the dispatcher.

Each step is committable in isolation — if a step blocks, the
preceding steps remain mergeable.

## Test impact

| Step | New tests | Test fixups | Total delta |
|------|-----------|-------------|-------------|
| F1   | +2 (unit + integration) | 0 | +2 |
| F2   | +1 (API-layer 409) | +1 (restore green) | +2 |
| F3   | +3 (probe pass/fail/once) | 0 | +3 |
| F4   | +1 (composite-key partial) | 0 | +1 |
| F5   | +1 (invalid JWT) | +4 (token fixture) | +5 |
| F6   | 0 | +4 (dispatcher-driven migration) | +4 |

Net: ~7 new tests, ~9 test fixups. Sprint 3 ended at 130 tests; Sprint
4 ends ~137. No tests deleted.

## Risks

- **F3 policy change** — making `pyreadr` a hard backend dep at boot
  may surprise operators running `bg_ndi_wi`-only installs. Mitigation:
  the error message is explicit ("install/upgrade spacescans-pipeline
  >= 0.2"); the requirement is consistent with `/api/variables`
  advertising both experiments unconditionally.
- **F6 test flakiness under dispatcher** — the four migrated tests run
  the dispatcher's full Popen-of-Popen chain, which is slower (cold
  start) and has more failure surface than direct `subprocess.run`.
  Mitigation: 240s deadline (matches `test_e2e_multi_experiment_cohort`);
  `6d07ad6` hardened the slot-seeding race that previously caused
  flakes.
- **F1 rc==143 portability** — SIGTERM exit code is 128+15 on POSIX;
  Windows has no SIGTERM. Backend is POSIX-only (DuckDB/R stack); the
  risk is theoretical.
- **F5 token shape change** — `get_current_user` returns
  `{"id": int, "email": str}` vs `require_user`'s `{"token": str}`.
  Verified the only call site (`variables.py:35`) binds the value to
  `_user` (unused). Zero call-site fixups.
- **F2 lock fd leak window** — probe fd opens, fcntl.flock,
  fcntl.flock(UN), os.close. The double-try-finally in the snippet
  guarantees os.close even if flock raises. No leak risk.

## Explicitly out of scope (deferred to Sprint 5+)

- Multi-experiment parallel spawn. Sequential remains the contract.
- The 6 remaining experiments (`tiger_proximity`, `nhd_bluespace`,
  `vnl`, `temis`, `fara_tract`, `noise`).
- Per-variable shapefile coverage. Bbox-based CONUS envelope continues.
- The global `geoid` → `episode_id` rename in the upstream pipeline.
- A metadata editor UI.
- Frontend test framework (jest / vitest).
- LRU cap on the C3 cache directory.
- A `precomputed_areal` / `precomputed_static` / `cbp_fallback`
  episode-dispatch audit.
- Restructuring `merge_results(...)` signatures to take `task_dir` only
  (currently both runners take `variables: list[str]` they don't use
  inside merge_results itself). Pure refactor, no behaviour change;
  defer.
