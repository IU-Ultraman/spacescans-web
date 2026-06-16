# Sprint 4: F1-F6 Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task.

**Goal:** Address all 6 IMPORTANT findings from Sprint 3's adversarial cross-lens final review. No new experiments, no new variables, no UI changes (the 3-variable catalog is by design — adding more experiments is Sprint 5+).

**Architecture:** Pure tech-debt cleanup. F1 fixes dispatcher cancellation observability. F2 restores start_task lock pre-check (raises TaskBusyError → HTTP 409). F3 adds R8 startup probe (pyreadr import + TimeConfig.output_grouping presence). F4 adds the missing (pid, episode_id) join unit test for _merge.fan_in. F5 swaps require_user for get_current_user (real JWT verify). F6 drops the T5 inline fan_in from bg_ndi_wi.merge_results AND migrates Sprint 2 standalone integration tests to the dispatcher path.

**Tech Stack:** Python (FastAPI, pandas, pytest, fcntl, jsonschema), JWT (existing get_current_user), spacescans-pipeline editable install. Zero pipeline changes.

**Spec:** `docs/superpowers/specs/2026-06-16-sprint-4-followups-design.md` (897 lines, committed 1bb4833)

**Base branch:** `main` (Sprint 3 merged at db0c882)

**Worktree:** `.worktrees/feat-sprint-4`, branch `feat/sprint-4-followups`

**Backend env:** `/Users/xai/miniconda3/envs/spacescans/bin/python`
**Frontend env:** `~/.nvm/versions/node/v20.20.2/bin`

**Baseline:** 130 backend tests pass, 7/8 integration (1 acknowledged: test_lock_prevents_concurrent_start fails — F2 restores it).

---

## Table of contents

- [Task T1: F3 — variable_registry startup probe (_assert_pipeline_version_compatible)](#task-t1-f3-variable_registry-startup-probe-_assert_pipeline_version_compatible)
- [Task T2: F4 — _merge.fan_in composite-key (pid, episode_id) unit test](#task-t2-f4-_mergefan_in-composite-key-pid-episode_id-unit-test)
- [Task T3: F5 — routers/variables auth swap require_user → get_current_user](#task-t3-f5-routersvariables-auth-swap-require_user--get_current_user)
- [Task T4: F1a — stop_task scope reduction (signal only runner pids when present)](#task-t4-f1a-stop_task-scope-reduction-signal-only-runner-pids-when-present)
- [Task T5: F1b — dispatcher rc==143 cancellation preserves cancelled lineage](#task-t5-f1b-dispatcher-rc143-cancellation-preserves-cancelled-lineage)
- [Task T6: F2 — start_task .run_lock pre-check + HTTP 409 mapping restored](#task-t6-f2-start_task-run_lock-pre-check--http-409-mapping-restored)
- [Task T7: F6 — drop inline fan_in from bg_ndi_wi.merge_results + migrate 4 Sprint 2 integration tests to dispatcher path](#task-t7-f6-drop-inline-fan_in-from-bg_ndi_wimerge_results--migrate-4-sprint-2-integration-tests-to-dispatcher-path)
- [Final verification](#final-verification)

---

### Task T1: F3: variable_registry startup probe (_assert_pipeline_version_compatible)

**Files:**
- Create: (none)
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/app/variable_registry.py`
- Test: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_variable_registry.py`

**Goal:** Add a one-shot defensive startup probe `_assert_pipeline_version_compatible()` to `variable_registry.py` that verifies the editable-installed `spacescans` pipeline has a working `pyreadr` extra and `TimeConfig.output_grouping` in `model_fields`, called unconditionally at the top of `load_variables()` before the mtime fast-path and guarded by a module-level `_PROBE_DONE` flag.

**Context:** Sprint 3 promised this probe (spec lines 1605, 1696-1700) but never wired it in — `backend/app/variable_registry.py:40-68` has no version check, so an editable install of `spacescans-pipeline` predating Sprint 2 (missing `TimeConfig.output_grouping` or `pyreadr`) fails only mid-pipeline at runtime. F3 (spec lines 394-499) makes the failure boot-time and actionable. The probe must run exactly once per process (set `_PROBE_DONE = True` on success), raise `MetadataSchemaError` with an "install/upgrade spacescans-pipeline >= 0.2 (Sprint 2 episode-dimension contract)" message on drift, and sit ahead of the mtime fast-path in `load_variables` so a warm cache never skips it on first request. Today's env has `pyreadr` installed and `TimeConfig.model_fields["output_grouping"]` present, so the in-env test passes naturally; the two failure-mode tests monkeypatch to simulate drift.

- [ ] **Step 1: Write the failing test(s)**

Append to `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_variable_registry.py`:

```python
# ----- Sprint 4 F3: startup probe -----

def test_startup_probe_passes_in_env():
    """In a correctly-installed env, the probe is a no-op (no raise)."""
    from app import variable_registry as vr
    vr._PROBE_DONE = False
    vr._assert_pipeline_version_compatible()
    assert vr._PROBE_DONE is True


def test_startup_probe_raises_on_missing_field(monkeypatch):
    """Drop output_grouping from TimeConfig.model_fields — probe must raise."""
    from app import variable_registry as vr
    from spacescans.models.config import TimeConfig

    vr._PROBE_DONE = False
    patched = {k: v for k, v in TimeConfig.model_fields.items() if k != "output_grouping"}
    monkeypatch.setattr(TimeConfig, "model_fields", patched)

    with pytest.raises(vr.MetadataSchemaError) as exc:
        vr._assert_pipeline_version_compatible()
    assert "output_grouping" in str(exc.value)
    assert vr._PROBE_DONE is False


def test_startup_probe_runs_once(monkeypatch):
    """Once _PROBE_DONE is True, the probe must short-circuit before re-entering imports."""
    from app import variable_registry as vr
    import spacescans._extras as _extras

    vr._PROBE_DONE = True

    def _boom(*_a, **_kw):
        raise RuntimeError("probe should not have re-entered require()")

    monkeypatch.setattr(_extras, "require", _boom)
    # No raise expected — second invocation must short-circuit.
    vr._assert_pipeline_version_compatible()
    assert vr._PROBE_DONE is True
```

Also extend the `_reset_registry_cache` autouse fixture (top of the file) so `_PROBE_DONE` does not leak across tests — add the two `vr._PROBE_DONE = False` lines mirroring the existing `_CACHE` resets:

```python
@pytest.fixture(autouse=True)
def _reset_registry_cache():
    from app import variable_registry as vr
    vr._CACHE["mtime"] = None
    vr._CACHE["payload"] = None
    vr._PROBE_DONE = False
    yield
    vr._CACHE["mtime"] = None
    vr._CACHE["payload"] = None
    vr._PROBE_DONE = False
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_variable_registry.py -v -k "startup_probe"
```

Expected: all three tests ERROR at collection / setup with `AttributeError: module 'app.variable_registry' has no attribute '_PROBE_DONE'` (and `_assert_pipeline_version_compatible` is undefined too).

- [ ] **Step 3: Implement the minimal code**

Edit `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/app/variable_registry.py`.

3a. Add module-level state and the probe function (after the `MetadataSchemaError` class, before `_discover_experiments`):

```python
_PROBE_DONE: bool = False


def _assert_pipeline_version_compatible() -> None:
    """Defensive boot-time check. Raises MetadataSchemaError on drift.

    Runs once per process — guarded by module-level _PROBE_DONE flag.
    Verifies the editable-installed spacescans pipeline has:
      1. A working `pyreadr` extra (Sprint 3 ZCTA5×CBP .Rda reader).
      2. `TimeConfig.output_grouping` field (Sprint 2 episode-dimension contract).
    """
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
            "Install/upgrade spacescans-pipeline >= 0.2 "
            "(Sprint 2 episode-dimension contract)."
        ) from exc
    if "output_grouping" not in TimeConfig.model_fields:
        raise MetadataSchemaError(
            "pipeline missing TimeConfig.output_grouping — install/upgrade "
            "spacescans-pipeline >= 0.2 (Sprint 2 episode-dimension contract)."
        )
    _PROBE_DONE = True
```

3b. Call the probe unconditionally at the top of `load_variables`, BEFORE the mtime fast-path:

```python
def load_variables(*, force: bool = False) -> dict[str, Any]:
    _assert_pipeline_version_compatible()
    mtime = _METADATA_PATH.stat().st_mtime
    if not force and _CACHE["mtime"] == mtime and _CACHE["payload"]:
        return _CACHE["payload"]
    ...  # (rest unchanged)
```

- [ ] **Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_variable_registry.py -v -k "startup_probe"
```

Expected: 3 passed.

- [ ] **Step 5: Full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 133 passed (130 Sprint 4 baseline + 3 new probe tests).

- [ ] **Step 6: Commit**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
git add backend/app/variable_registry.py backend/tests/test_variable_registry.py
git commit -m "feat(registry): R8 startup probe for pipeline version compatibility (Sprint 4 F3)"
```

**Notes:**
- The probe call sits AHEAD of the mtime fast-path on purpose (spec lines 466-472): otherwise a warm `_CACHE` could let the first request after server boot skip the probe entirely. The `_PROBE_DONE` short-circuit keeps the post-boot overhead to one bool check.
- `test_startup_probe_runs_once` deliberately exercises the short-circuit without going through `load_variables` — it asserts the second `_assert_pipeline_version_compatible()` call never reaches the `_extras.require` import path even when that import is monkeypatched to raise.
- The `_reset_registry_cache` fixture extension is load-bearing for the `passes_in_env` test: without resetting `_PROBE_DONE = False`, an earlier test in the same session could leave it `True` and the probe would short-circuit before exercising the import branch.
- New cumulative test count after this task: 133 (was 130).
- No dependencies on other Sprint 4 tasks.

---

### Task T2: F4: _merge.fan_in composite-key (pid, episode_id) unit test

**Files:**
- Create: (none)
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_merge_partial.py`
- Test: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_merge_partial.py`

**Goal:** Lock the `(pid, episode_id)` composite join-key contract of `_merge.fan_in` against a silent mutation that drops `episode_id` from the merge key, by adding a partial-data test where the same pid appears with two distinct global episode_ids.

**Context:** `_merge.fan_in` (backend/app/experiments/_merge.py:84-107) assigns `df['episode_id'] = list(range(len(df)))` to the 10-row input and left-joins each `result_<exp_key>.csv` on `['pid', 'episode_id']`. The existing two `fan_in` tests (test_merge_partial.py:124 and :151) both use 5 unique pids with `episode_id = range(5)` — one episode per pid — so a mutation dropping `episode_id` from the join key would still pass them via the pid-only join (no duplicates). This task adds a fixture where 5 pids each appear twice with distinct episode_ids (0..9) and a partial CSV missing rows for episodes 1, 5, 9; a pid-only merge would either explode rows (cartesian) or fill the wrong values, so the test fails iff the composite-key contract is violated. The production code already satisfies this — the test is regression armor, not a fix.

- [ ] **Step 1: Write the failing test(s)**

Append to `backend/tests/test_merge_partial.py` (after `test_bg_ndi_wi_merge_results_delegates_to_write_partial`, end of file):

```python
def test_fan_in_preserves_episode_pairs_with_partial_data(tmp_path):
    """F4 (Sprint 4): lock (pid, episode_id) composite join key for fan_in.

    Fixture: 10 input rows, 5 pids each appearing twice with two distinct
    global episode_ids (A,B,C,D,E -> rows 0..9). Partial CSV drops episodes
    1, 5, 9 (one missing episode for pids A, C, E). A mutation dropping
    episode_id from the join key would either duplicate rows (cartesian on
    pid) or place values on the wrong episode — both caught by the
    assertions below.
    """
    from app.experiments import _merge

    task_dir = tmp_path / "task-f4-fanin"
    task_dir.mkdir(parents=True, exist_ok=True)

    # 10 input rows: 5 pids (A..E), each twice. fan_in assigns
    # episode_id = list(range(10)) in row order, so pairs are
    # (A,0),(A,1),(B,2),(B,3),(C,4),(C,5),(D,6),(D,7),(E,8),(E,9).
    pids = ["A", "A", "B", "B", "C", "C", "D", "D", "E", "E"]
    pd.DataFrame({
        "pid": pids,
        "startDate": ["2017-01-01"] * 10,
        "endDate": ["2017-12-31"] * 10,
        "longitude": [-93.0] * 10,
        "latitude": [45.0] * 10,
    }).to_csv(task_dir / "input.csv", index=False)

    # Partial CSV: 7 rows — drop episodes 1, 5, 9 (missing for A, C, E).
    out_dir = task_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "pid": ["A", "B", "B", "C", "D", "D", "E"],
        "episode_id": [0, 2, 3, 4, 6, 7, 8],
        "value": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0],
    }).to_csv(out_dir / "result_bg_ndi_wi.csv", index=False)

    out = _merge.fan_in(task_dir=task_dir, experiment_keys=["bg_ndi_wi"])
    df = pd.read_csv(out)

    # (1) No row loss, no row duplication.
    assert len(df) == 10, f"expected 10 rows, got {len(df)}"

    # (2) Exactly 3 NaN rows in the value column.
    nan_rows = df[df["value"].isna()]
    assert nan_rows.shape[0] == 3, f"expected 3 NaN rows, got {nan_rows.shape[0]}"

    # (3) NaN rows are exactly (A,1), (C,5), (E,9).
    nan_pairs = set(
        zip(nan_rows["pid"].tolist(), nan_rows["episode_id"].astype(int).tolist())
    )
    assert nan_pairs == {("A", 1), ("C", 5), ("E", 9)}, (
        f"unexpected NaN pairs: {nan_pairs}"
    )

    # (4) Sorted by (pid, episode_id) matches input ordering — confirms
    # the left-join preserves composite-key row order.
    df["episode_id"] = df["episode_id"].astype(int)
    sorted_pairs = list(
        zip(
            df.sort_values(["pid", "episode_id"])["pid"].tolist(),
            df.sort_values(["pid", "episode_id"])["episode_id"].tolist(),
        )
    )
    expected_pairs = [
        ("A", 0), ("A", 1), ("B", 2), ("B", 3), ("C", 4),
        ("C", 5), ("D", 6), ("D", 7), ("E", 8), ("E", 9),
    ]
    assert sorted_pairs == expected_pairs, (
        f"composite-key ordering mismatch: {sorted_pairs}"
    )
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_merge_partial.py -v -k "test_fan_in_preserves_episode_pairs_with_partial_data"
```

Expected: PASS on the first run (the production code at `_merge.py:84-107` already joins on `['pid', 'episode_id']`). This is a pure-additive regression test — there is no RED phase. Document this in the commit message ("test-only; locks existing contract against regression"). If it unexpectedly fails, the production code has already drifted and Step 3 becomes a real fix; abort and escalate.

- [ ] **Step 3: Implement the minimal code**

No production code change. The test is regression armor for the existing implementation at `backend/app/experiments/_merge.py:98-103`:

```python
df = df.merge(
    partial,
    on=["pid", "episode_id"],
    how="left",
    suffixes=("", f"_{exp_key}_dup"),
)
```

Leave `_merge.py` untouched.

- [ ] **Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_merge_partial.py -v -k "test_fan_in_preserves_episode_pairs_with_partial_data"
```

Expected: PASS (1 passed in <1s).

- [ ] **Step 5: Full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 134 passed (Sprint 4 baseline 130 + T1 adds 3 = 133 + this task's 1 = 134). Cumulative count after T2: **134**.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_merge_partial.py
git commit -m "test(merge): lock (pid, episode_id) composite-key fan_in contract (Sprint 4 F4)

Pure-additive regression test. Production code at _merge.py:98-103
already joins partials on ['pid', 'episode_id']; existing fan_in tests
use one episode per pid so a mutation dropping episode_id from the join
key would silently pass. New test uses 5 pids each appearing twice with
distinct global episode_ids (0..9) and a partial CSV missing episodes
1, 5, 9 — pid-only merge would cartesian-explode or misplace values,
both caught here.

Refs: docs/superpowers/specs/2026-06-16-sprint-4-followups-design.md F4"
```

**Notes:**
- Depends on T1 — run T2 only after T1's commit lands, so the baseline is 133 and post-T2 is 134.
- Pure-additive: no production change, no fixtures shared with other tests (uses its own `tmp_path / "task-f4-fanin"`). Safe to land independently of any other Sprint 4 task once T1 is in.
- `_merge.fan_in` reads `input.csv` with `dtype=str` and then forces `episode_id` to int (line 90, 97). The test's input has `pid` as bare strings `"A".."E"` (not the `PID{i:07d}` format other tests use) — this is intentional and supported, since `fan_in` does not validate `pid` format.
- After `fan_in` writes `result.csv`, the test reads it back with default dtypes. `episode_id` is cast to int explicitly before zipping in assertion (4) to guard against pandas inferring it as object when NaN values force float upcasting on read-back.
- If a future refactor swaps `pd.merge` for an indexed `.join`, this test still pins the contract: the composite key must produce exactly 10 rows with NaN at the three dropped episodes.

---

### Task T3: F5: routers/variables auth swap require_user → get_current_user

**Files:**
- Create: (none)
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/app/routers/variables.py`
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/app/routers/tasks.py`
- Test: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_api_variables.py`

**Goal:** Replace the Bearer-presence-only `require_user` stub on `/api/variables` with full JWT validation via `get_current_user`, matching the auth contract used elsewhere in the API.

**Context:** Sprint 3 introduced `POST /api/variables` guarded by a thin `require_user` helper in `routers/tasks.py` that only checked for the presence of a Bearer token. Sprint 4 F5 finishes the auth story by switching the route to the canonical `app.auth.get_current_user` dependency (real JWT decode + signature + expiry check). Tests currently mint a fake `"test-token"` string; they need to mint a real JWT signed with `SECRET_KEY` so the new dependency accepts them, plus one new negative test proving that garbage tokens now return 401 (under the old stub they returned 200).

- [ ] **Step 1: Write the failing test(s)**

Edit `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_api_variables.py`.

(a) Add env-reload guard at the very top of the file (above any `from app.*` imports), matching the pattern in `test_tasks.py`:

```python
import os
from pathlib import Path
from dotenv import load_dotenv

# Reload .env before importing app modules so SECRET_KEY/ALGORITHM are available
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=True)
```

(b) Add a local helper near the top of the test module (after imports, before the first test):

```python
from app.auth import create_access_token


def _auth_headers() -> dict[str, str]:
    """Mint a real JWT for tests so get_current_user accepts it."""
    token = create_access_token({"sub": "1", "email": "test@example.com"})
    return {"Authorization": f"Bearer {token}"}
```

(c) In each of the 4 existing tests (`test_list_variables_returns_catalog`, `test_list_variables_requires_auth`, `test_list_variables_filter_by_category`, `test_list_variables_filter_by_geography`) replace:

```python
headers = {"Authorization": "Bearer test-token"}
```

with:

```python
headers = _auth_headers()
```

(d) Append the new negative test:

```python
def test_list_variables_rejects_invalid_jwt(client):
    """Garbage tokens must be rejected with 401 (was 200 under presence-only stub)."""
    headers = {"Authorization": "Bearer not-a-real-jwt"}
    response = client.post("/api/variables", json={}, headers=headers)
    assert response.status_code == 401
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_api_variables.py -v -k "rejects_invalid_jwt or list_variables"
```

Expected: `test_list_variables_rejects_invalid_jwt` FAILS with `assert 200 == 401` (the old `require_user` stub accepts any Bearer string). The 4 existing tests still pass because the stub doesn't validate token contents.

- [ ] **Step 3: Implement the minimal code**

Edit `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/app/routers/variables.py`:

Remove the import:

```python
from app.routers.tasks import require_user
```

Add the import:

```python
from app.auth import get_current_user
```

Change the `list_variables` endpoint signature from:

```python
@router.post("", response_model=VariablesListResponse)
def list_variables(
    request: VariablesListRequest,
    _user=Depends(require_user),
    db: Session = Depends(get_db),
) -> VariablesListResponse:
```

to:

```python
@router.post("", response_model=VariablesListResponse)
def list_variables(
    request: VariablesListRequest,
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VariablesListResponse:
```

Then edit `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/app/routers/tasks.py`:

Verify no other importers first:

```bash
grep -rn "from app.routers.tasks import require_user" /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend
grep -rn "_require_user_security" /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend
```

Both greps must return zero hits (after the variables.py edit above). Then delete the `_require_user_security = HTTPBearer(auto_error=False)` module-level assignment and the entire `require_user` function definition. Remove the `from fastapi.security import HTTPBearer` import if it's no longer used elsewhere in the file.

The `_user` parameter on `list_variables` is bound but unused, so the shape change from `Optional[HTTPAuthorizationCredentials]` to a user dict/object from `get_current_user` is safe — nothing in the body reads it.

- [ ] **Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_api_variables.py -v -k "rejects_invalid_jwt or list_variables"
```

Expected: PASS. All 5 tests green (4 existing + 1 new negative).

- [ ] **Step 5: Full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 135 passed (134 post-T2 baseline + 1 new `test_list_variables_rejects_invalid_jwt`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/variables.py backend/app/routers/tasks.py backend/tests/test_api_variables.py
git commit -m "refactor(auth): use full JWT validation on /api/variables (Sprint 4 F5)"
```

**Notes:**
- Depends on T2 (T2's test count of 134 is the input baseline; this task brings cumulative to 135).
- The grep verification in Step 3 is load-bearing — if any other module imports `require_user`, do NOT delete it; instead leave the function in place and only swap the variables.py dependency. Spec assumes zero external importers.
- `create_access_token` must accept the `{"sub": "1", "email": "..."}` shape used elsewhere in the test suite (see `test_tasks.py` for the canonical mint pattern). If the helper signature differs, mirror `test_tasks.py` exactly.
- The env-reload guard at the top of `test_api_variables.py` is essential: without it, importing `create_access_token` before `.env` is loaded gives a `None` `SECRET_KEY` and tokens won't verify.
- Do NOT touch `app/auth.py` itself — `get_current_user` already exists and is the dependency used by `/api/tasks`.

---

### Task T4: F1a: stop_task scope reduction (signal only runner pids when present)

**Files:**
- Create: (none)
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/app/task_manager.py`
- Test: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_task_manager.py`

**Goal:** Narrow `stop_task` so that when at least one runner pid is recorded under `status.experiments[<exp_key>].pid`, SIGTERM is sent ONLY to those runner pids (not the supervisor), letting the dispatcher survive its `proc.wait()` and observe rc==143 — while preserving the supervisor-SIGTERM fallback for the early-cancel case where no runner has launched yet.

**Context:** Per spec lines 191-243, the rc==143 cancellation discriminator (added by T5 (F1b) and dependent on this task to be reachable at runtime) only fires if the dispatcher survives long enough to reach the new `if rc == 143:` branch in `dispatcher.py`. Today `stop_task` SIGTERMs both the supervisor AND each runner (`task_manager.py:309-316`); SIGTERM on the supervisor kills the Python interpreter before `proc.wait()` returns. F1a is the prerequisite scope-reduction: signal ONLY runner pids when present; keep supervisor fallback when none are recorded. Prerequisite for T5 (F1b). T4 lands first so the rc==143 branch T5 adds is reachable at runtime.

- [ ] **Step 1: Write the failing test(s)**

Append to `backend/tests/test_task_manager.py`:

```python
def test_stop_task_signals_only_runner_pids_when_present(tmp_path, monkeypatch):
    """F1a: when runner pids are recorded under status.experiments, stop_task
    must SIGTERM ONLY those runner pids — NOT the supervisor pid — so the
    dispatcher survives long enough to observe rc==143 from proc.wait()."""
    import json
    import signal as _signal
    from app import task_manager

    monkeypatch.setattr(task_manager.app.config.settings, "TASKS_DIR", tmp_path)
    task_id = "f1a-runner-only"
    task_dir = tmp_path / f"task-{task_id}"
    task_dir.mkdir(parents=True)
    supervisor_pid = 424242
    runner_pid = 525252
    status = {
        "task_id": task_id,
        "status": "running",
        "pid": supervisor_pid,
        "experiments": {
            "bg_ndi_wi": {
                "status": "running",
                "pid": runner_pid,
            },
        },
    }
    (task_dir / "status.json").write_text(json.dumps(status))

    signalled: list[tuple[int, int]] = []

    def _fake_kill(pid, sig):
        signalled.append((pid, sig))

    monkeypatch.setattr(task_manager.os, "kill", _fake_kill)

    result = task_manager.stop_task(task_id)

    sent_pids = [pid for (pid, _sig) in signalled]
    assert runner_pid in sent_pids, "runner pid must be signalled"
    assert supervisor_pid not in sent_pids, (
        "supervisor pid must NOT be signalled when a runner pid is recorded "
        "(F1a: lets dispatcher survive to observe rc==143)"
    )
    assert all(sig == _signal.SIGTERM for (_pid, sig) in signalled)
    assert result["status"] == "stopping"
    assert result["signalled_pids"] == [runner_pid]


def test_stop_task_falls_back_to_supervisor_when_no_runner_pids(tmp_path, monkeypatch):
    """F1a: when NO runner pid is recorded (early-cancel before dispatcher
    launched any slot), stop_task falls back to SIGTERMing the supervisor pid
    so the dispatcher process is still reaped."""
    import json
    import signal as _signal
    from app import task_manager

    monkeypatch.setattr(task_manager.app.config.settings, "TASKS_DIR", tmp_path)
    task_id = "f1a-supervisor-fallback"
    task_dir = tmp_path / f"task-{task_id}"
    task_dir.mkdir(parents=True)
    supervisor_pid = 313131
    status = {
        "task_id": task_id,
        "status": "running",
        "pid": supervisor_pid,
        "experiments": {},
    }
    (task_dir / "status.json").write_text(json.dumps(status))

    signalled: list[tuple[int, int]] = []
    monkeypatch.setattr(
        task_manager.os, "kill",
        lambda pid, sig: signalled.append((pid, sig)),
    )

    result = task_manager.stop_task(task_id)

    sent_pids = [pid for (pid, _sig) in signalled]
    assert supervisor_pid in sent_pids, (
        "supervisor pid MUST be signalled when no runner pid is recorded "
        "(defensive fallback for early-cancel)"
    )
    assert all(sig == _signal.SIGTERM for (_pid, sig) in signalled)
    assert result["status"] == "stopping"
    assert result["signalled_pids"] == [supervisor_pid]
```

Note: these tests assume `os` and `signal` are module-level attributes of `task_manager`. Current code imports them inside the function body (`task_manager.py:301-302`); Step 3 hoists those imports to module scope so `monkeypatch.setattr(task_manager.os, "kill", ...)` resolves the same `os` reference the function uses.

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_task_manager.py -v -k "stop_task_signals_only_runner_pids_when_present or stop_task_falls_back_to_supervisor_when_no_runner_pids"
```

Expected: `test_stop_task_signals_only_runner_pids_when_present` FAILS because supervisor_pid (424242) appears in `signalled_pids` alongside runner_pid (525252) — current loop unconditionally appends `sup_pid` at lines 310-312. `test_stop_task_falls_back_to_supervisor_when_no_runner_pids` likely PASSES already (supervisor is always signalled today), or fails only on the `monkeypatch` import-path issue — that's why Step 3 also hoists `import os` / `import signal` to module top.

- [ ] **Step 3: Implement the minimal code**

Edit `backend/app/task_manager.py`. (a) Hoist the in-function imports to the module top (so tests can monkeypatch `task_manager.os.kill`):

At the top of the file alongside the other imports, add:

```python
import os
import signal
```

(b) Replace the body of `stop_task` (lines 291-325) with:

```python
def stop_task(task_id: str) -> dict:
    """Sprint 4 F1a: SIGTERM ONLY the recorded per-experiment runner pids
    when at least one is present. The supervisor pid is signalled ONLY as
    a fallback when no runner pid has been recorded yet (early-cancel
    before dispatcher.dispatch launched any slot).

    Rationale (spec 2026-06-16 lines 191-243): SIGTERM-ing the supervisor
    kills the dispatcher's Python interpreter before its blocking
    proc.wait() can observe rc == 143, defeating the cancellation
    discriminator added by Sprint 4 F1b. Narrowing the scope to runner
    pids lets the dispatcher reach its rc == 143 branch naturally.
    """
    task_dir = _task_dir(task_id)
    status_path = task_dir / "status.json"
    if not status_path.exists():
        return {"status": "no-op", "reason": "no status.json"}
    status = json.loads(status_path.read_text())

    runner_pids: list[int] = []
    for exp in (status.get("experiments") or {}).values():
        exp_pid = exp.get("pid")
        if isinstance(exp_pid, int) and exp.get("status") == "running":
            runner_pids.append(exp_pid)

    if runner_pids:
        pids_to_signal: list[int] = runner_pids
    else:
        # Defensive fallback: no runner recorded (early-cancel before
        # dispatcher launched any slot). SIGTERM the supervisor so the
        # dispatcher process is still reaped.
        pids_to_signal = []
        sup_pid = status.get("pid")
        if isinstance(sup_pid, int):
            pids_to_signal.append(sup_pid)

    sent: list[int] = []
    for pid in pids_to_signal:
        try:
            os.kill(pid, signal.SIGTERM)
            sent.append(pid)
        except ProcessLookupError:
            continue
    return {"status": "stopping", "signalled_pids": sent}
```

- [ ] **Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_task_manager.py -v -k "stop_task_signals_only_runner_pids_when_present or stop_task_falls_back_to_supervisor_when_no_runner_pids"
```

Expected: PASS (2 passed).

Also re-run all pre-existing stop_task tests to confirm no regression:

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_task_manager.py -v -k "stop_task"
```

Expected: all existing stop_task tests still PASS alongside the two new ones.

- [ ] **Step 5: Full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 137 passed (135 from post-T3 baseline + 2 new tests).
Cumulative count after T4: 137.

- [ ] **Step 6: Commit**

```bash
git add backend/app/task_manager.py backend/tests/test_task_manager.py
git commit -m "refactor(task_manager): stop_task signals only runner pids when recorded (Sprint 4 F1a)"
```

**Notes:**
- This is the prerequisite for F1b — without it, the dispatcher's rc==143 branch (added in T5) is never reached at runtime under user-initiated cancellation, because SIGTERM to the supervisor kills the interpreter mid-`proc.wait()`.
- The hoist of `import os` / `import signal` to module scope is needed so `monkeypatch.setattr(task_manager.os, "kill", ...)` patches the same binding the function uses. Existing call sites elsewhere in the module are unaffected — both modules were already imported lazily inside `stop_task` only.
- The defensive supervisor-SIGTERM fallback is intentionally kept (spec lines 238-243) — `stop_task`'s top-level cancelled-status write covers the observable outcome, but reaping the orphaned supervisor process is still desirable hygiene.
- Cumulative test-count baselines: Sprint 4 baseline 130 → T1 133 → T2 134 → T3 135 → **T4 137**.
- Follow-up flag: T5 (F1b — dispatcher rc==143 → mark current slot `cancelled`, cascade downstream slots as `cancelled`) depends on T4 landing.

---

### Task T5: F1b: dispatcher rc==143 cancellation preserves cancelled lineage

**Files:**
- Create: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_dispatcher_cancellation.py`
- Create: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_dispatcher.py`
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/app/dispatcher.py`
- Test: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_dispatcher.py`
- Test: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_dispatcher_cancellation.py`

**Goal:** Teach `app.dispatcher.dispatch` to discriminate SIGTERM cancellation (rc==143) from generic non-zero rc, so a cancelled run preserves `status="cancelled"` end-to-end (slot, cascade, and top-level) instead of being overwritten as `"error"` + `"skipped_due_to_prior_failure"`.

**Context:** Sprint 3's dispatcher loop at `dispatcher.py:153-161` treats any `rc != 0` as failure: it overwrites the cancelled slot with `"error"`, cascades remaining slots as `"skipped_due_to_prior_failure"`, then writes top-level `status="error"` via the post-loop block at lines 170-191. The runner's cancel handler had already written top-level `status="cancelled"`; the dispatcher clobbers it. Spec lines 247-279 fix this by branching on `rc == 143` and threading a local `cancelled` flag through to the top-level write. T4 already narrowed `stop_task` so the dispatcher survives long enough to observe `rc == 143` from `proc.wait()`, which is the precondition for this task.

- [ ] **Step 1: Write the failing test(s)**

Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_dispatcher.py` with the cancellation-discriminator unit test:

```python
"""Sprint 4 F1b: dispatcher rc==143 cancellation lineage tests."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def task_dir_with_config(tmp_path: Path) -> Path:
    task_dir = tmp_path / "task-cxl"
    task_dir.mkdir()
    (task_dir / "config.json").write_text(json.dumps({
        "variables": ["ndi", "cbp_zcta5"],
        "buffer": {"size": 270, "raster_res_m": 25},
        "experiment": "auto",
    }))
    (task_dir / "output").mkdir()
    return task_dir


class _FakePopen:
    instances: list["_FakePopen"] = []

    def __init__(self, cmd, *, returncode: int = 0, **kwargs):
        self.cmd = cmd
        self.kwargs = kwargs
        self._rc = returncode
        self.pid = 9000 + len(_FakePopen.instances)
        _FakePopen.instances.append(self)

    def wait(self, timeout=None):
        return self._rc


def test_dispatcher_cancellation_preserves_cancelled_status(
    task_dir_with_config, monkeypatch
):
    """First runner exits rc=143 (SIGTERM). Expect:
      - slot 1 status='cancelled' (NOT 'error')
      - slot 2 status='cancelled' (NOT 'skipped_due_to_prior_failure')
      - top-level status='cancelled', message='Task cancelled by user'
    """
    from app import dispatcher

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {
                            "bg_ndi_wi": ["ndi"],
                            "zcta5_cbp": ["cbp_zcta5"],
                        })

    def popen_first_sigterm(cmd, **kw):
        idx = len(_FakePopen.instances)
        return _FakePopen(cmd, returncode=(143 if idx == 0 else 0), **kw)

    monkeypatch.setattr(dispatcher.subprocess, "Popen", popen_first_sigterm)
    monkeypatch.setattr("app.experiments._merge.fan_in", MagicMock())

    dispatcher.dispatch(str(task_dir_with_config))

    status = json.loads((task_dir_with_config / "status.json").read_text())

    # rc==143 must NOT spawn the second runner (the cascade is status-only).
    assert len(_FakePopen.instances) == 1, (
        f"rc==143 must break the dispatch loop; got {len(_FakePopen.instances)} Popens"
    )

    # Top-level: cancelled, with the specific message.
    assert status["status"] == "cancelled", (
        f"top-level status must be 'cancelled' on rc==143; got {status['status']}"
    )
    assert status.get("message") == "Task cancelled by user", (
        f"top-level message must be 'Task cancelled by user'; got {status.get('message')!r}"
    )

    # Slot lineage: cancelled slot preserved, remaining slot cascaded as cancelled.
    exp = status["experiments"]
    assert exp["bg_ndi_wi"]["status"] == "cancelled", (
        f"slot 1 status must be 'cancelled' on rc==143; got {exp['bg_ndi_wi']['status']}"
    )
    assert exp["zcta5_cbp"]["status"] == "cancelled", (
        f"remaining slot must cascade as 'cancelled', NOT 'skipped_due_to_prior_failure'; "
        f"got {exp['zcta5_cbp']['status']}"
    )
```

Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_dispatcher_cancellation.py` with the e2e terminal-state test:

```python
"""Sprint 4 F1b: e2e dispatcher cancellation — real start_task + real stop_task.

Mirrors test_e2e_multi_experiment_cohort's environment + 240s deadline.
The integration-availability gate is the same set of preconditions
(SPACESCANS_DATA_DIR, pipeline CLI, BG fixtures, pyreadr) — when missing
the test is skipped at module import.
"""
import json
import shutil
import time
from pathlib import Path

import pytest

import app.config


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    if not (app.config.settings.SPACESCANS_DATA_DIR
            / "data_full/BG_FL/C3/tiger2010_bg10_states").exists():
        return False
    try:
        import pyreadr  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / pipeline CLI / pyreadr not configured",
)


@pytest.fixture
def task_with_multi_experiment(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-cancellation")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["ndi", "cbp_zcta5"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_cancellation_terminal_state(task_with_multi_experiment):
    """Start a real two-experiment task, wait until the first runner enters
    the 'prepare' step, stop_task, poll until terminal (240s deadline).

    Assert top-level status='cancelled' AND both slots end 'cancelled'.
    """
    task_id, task_dir = task_with_multi_experiment

    from app.task_manager import start_task, stop_task
    start_task(task_id)

    # Wait for the first runner to enter the 'prepare' step (proves the
    # dispatcher has Popened a real runner whose SIGTERM handler is armed).
    arm_deadline = time.monotonic() + 60.0
    armed = False
    while time.monotonic() < arm_deadline:
        if (task_dir / "status.json").exists():
            status = json.loads((task_dir / "status.json").read_text())
            slot = (status.get("experiments") or {}).get("bg_ndi_wi") or {}
            if slot.get("current_step") == "prepare" and slot.get("status") == "running":
                armed = True
                break
        time.sleep(0.5)
    assert armed, (
        f"first runner never entered the 'prepare' step within 60s; "
        f"last status={status if 'status' in dir() else 'unread'}"
    )

    stop_task(task_id)

    # Match test_e2e_multi_experiment_cohort's 240s terminal-state deadline.
    deadline = time.monotonic() + 240.0
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 240s; last status={status}")

    assert status["status"] == "cancelled", (
        f"top-level status must be 'cancelled' after stop_task; got {status['status']}"
    )
    experiments = status.get("experiments") or {}
    assert experiments.get("bg_ndi_wi", {}).get("status") == "cancelled", (
        f"bg_ndi_wi slot must end 'cancelled'; got {experiments.get('bg_ndi_wi')}"
    )
    assert experiments.get("zcta5_cbp", {}).get("status") == "cancelled", (
        f"zcta5_cbp slot must cascade as 'cancelled' (NOT skipped_due_to_prior_failure); "
        f"got {experiments.get('zcta5_cbp')}"
    )
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_dispatcher.py backend/tests/test_dispatcher_cancellation.py -v -k "test_dispatcher_cancellation_preserves_cancelled_status or test_e2e_cancellation_terminal_state"
```

Expected: 2 failures. `test_dispatcher_cancellation_preserves_cancelled_status` fails with `AssertionError: top-level status must be 'cancelled' on rc==143; got error` because today `dispatcher.py:154-161` treats rc=143 the same as any other non-zero rc — it marks the slot `error`, cascades `skipped_due_to_prior_failure`, and the post-loop block at lines 176-178 writes top-level `status="error"`. The e2e test fails the same way (top-level `error` instead of `cancelled`, second slot `skipped_due_to_prior_failure` instead of `cancelled`).

- [ ] **Step 3: Implement the minimal code**

Edit `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/app/dispatcher.py`.

Above the dispatch loop (between line 130 `exp_keys = list(by_exp.keys())` and line 131 `for i, exp_key in enumerate(exp_keys):`), introduce the local flag:

```python
    completed: list[str] = []
    exp_keys = list(by_exp.keys())
    cancelled = False
    for i, exp_key in enumerate(exp_keys):
```

Replace the rc-handling block (current lines 153-161):

```python
        rc = proc.wait()
        if rc != 0:
            # Mark this slot as errored; keep whatever progress the runner
            # managed to write into its own slot before the failure.
            _mark_experiment(task_dir, exp_key, "error", current_step=None)
            for skipped in exp_keys[i + 1:]:
                _mark_experiment(task_dir, skipped, "skipped_due_to_prior_failure",
                                 current_step=None)
            break
```

with the rc==143 discriminator:

```python
        rc = proc.wait()
        if rc != 0:
            if rc == 143:
                # SIGTERM cancellation (Sprint 4 F1b). Preserve cancelled
                # lineage end-to-end: this slot + all remaining slots get
                # status='cancelled', and the post-loop top-level write
                # branches on `cancelled` to write status='cancelled' /
                # message='Task cancelled by user' instead of 'error'.
                _mark_experiment(task_dir, exp_key, "cancelled", current_step=None)
                for skipped in exp_keys[i + 1:]:
                    _mark_experiment(task_dir, skipped, "cancelled",
                                     current_step=None)
                cancelled = True
                break
            # Generic non-zero rc — existing error + skipped cascade.
            _mark_experiment(task_dir, exp_key, "error", current_step=None)
            for skipped in exp_keys[i + 1:]:
                _mark_experiment(task_dir, skipped, "skipped_due_to_prior_failure",
                                 current_step=None)
            break
```

Replace the post-loop top-level write (current lines 170-191):

```python
    failed = [k for k in exp_keys if k not in completed]

    if completed:
        from app.experiments import _merge
        _merge.fan_in(task_dir, completed)

    if not completed:
        _write_status(task_dir, status="error", progress=0.0,
                      message=f"All experiments failed (first failure: {failed[0]})")
        return {"task_id": task_dir.name, "failed": failed}
    if failed:
        _write_status(
            task_dir,
            status="partial",
            progress=round(len(completed) / len(exp_keys), 2),
            message=f"{len(completed)}/{len(exp_keys)} experiments completed",
        )
        return {"task_id": task_dir.name, "completed": completed, "failed": failed}

    _write_status(task_dir, status="finished", progress=1.0,
                  message=f"Completed {len(completed)} experiments")
    return {"task_id": task_dir.name, "completed": completed}
```

with the cancelled-first branch:

```python
    failed = [k for k in exp_keys if k not in completed]

    if completed and not cancelled:
        from app.experiments import _merge
        _merge.fan_in(task_dir, completed)

    if cancelled:
        _write_status(task_dir, status="cancelled",
                      message="Task cancelled by user")
        return {"task_id": task_dir.name, "completed": completed,
                "failed": failed, "cancelled": True}
    if not completed:
        _write_status(task_dir, status="error", progress=0.0,
                      message=f"All experiments failed (first failure: {failed[0]})")
        return {"task_id": task_dir.name, "failed": failed}
    if failed:
        _write_status(
            task_dir,
            status="partial",
            progress=round(len(completed) / len(exp_keys), 2),
            message=f"{len(completed)}/{len(exp_keys)} experiments completed",
        )
        return {"task_id": task_dir.name, "completed": completed, "failed": failed}

    _write_status(task_dir, status="finished", progress=1.0,
                  message=f"Completed {len(completed)} experiments")
    return {"task_id": task_dir.name, "completed": completed}
```

- [ ] **Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_dispatcher.py backend/tests/test_dispatcher_cancellation.py -v -k "test_dispatcher_cancellation_preserves_cancelled_status or test_e2e_cancellation_terminal_state"
```

Expected: PASS. Both tests green; the e2e test runs only when integration fixtures are present, otherwise it is skipped (collected but reported as `s`) and the unit test still passes.

- [ ] **Step 5: Full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 139 passed (Sprint 4 baseline 130 + T1..T4 increments to 137 + 2 new from this task). Pre-existing `test_dispatch_partial_failure_marks_remaining` (which uses rc=2) and `test_dispatch_partial_failure_after_success_calls_fan_in` (rc=2) must still pass — they exercise the non-143 branch unchanged.

- [ ] **Step 6: Commit**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
git add backend/app/dispatcher.py backend/tests/test_dispatcher.py backend/tests/test_dispatcher_cancellation.py
git commit -m "feat(dispatcher): preserve cancelled lineage on rc==143 (Sprint 4 F1b)"
```

**Notes:**
- Depends on T4 (`stop_task` scope reduction — runner-pid-only SIGTERM). Without T4, the dispatcher dies on SIGTERM before `proc.wait()` returns 143 and the e2e test would never reach the new branch. T4 must be merged into the worktree before this task starts.
- The unit test uses `_FakePopen` returning rc=143 — identical shape to `test_dispatch_partial_failure_marks_remaining` (which uses rc=2). Keep both: one proves the cancellation branch, the other proves the generic-error branch is untouched.
- The e2e test waits for `current_step == "prepare"` (an established `bg_ndi_wi` step name) to ensure the runner's cancel handler is armed before `stop_task` fires. If the runner's step naming ever shifts away from "prepare" the arming gate needs updating in lockstep.
- `fan_in` is intentionally skipped on the cancelled path (no merged `result.csv` for a cancelled run). This is the one new branch in the post-loop block beyond the spec's literal example; it matches the existing invariant that `fan_in` only runs over `completed` slots and that cancelled runs leave no merged output.
- Cumulative Sprint 4 test count after T5: 139 (137 from T1..T4 + 2 added here).

---

### Task T6: F2: start_task .run_lock pre-check + HTTP 409 mapping restored

**Files:**
- Create: (none)
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/app/task_manager.py`
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/app/routers/tasks.py`
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_bg_ndi_wi_integration.py`
- Test: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_api_tasks.py` (NEW)

**Goal:** Restore Sprint 2's `.run_lock` pre-check inside `task_manager.start_task` so concurrent `POST /api/tasks/{id}/start` calls raise `TaskBusyError` → HTTP 409 *before* a second Popen is launched, instead of both runners racing and one reporting a meaningless `status="error"`.

**Context:** Sprint 3's dispatcher refactor removed the in-process lock probe from `start_task` (`backend/app/task_manager.py:264-289`). The runners (`bg_ndi_wi.run:378-393`, `zcta5_cbp.run:209-219`) still acquire `.run_lock` defensively, so the loser of a race fails with `BlockingIOError` *inside the subprocess*, the dispatcher cascades it to `error` + `skipped_due_to_prior_failure`, and the user sees no 409. `TaskBusyError` is still defined at `task_manager.py:157-161` and the router at `routers/tasks.py:81-89` *already* catches it and maps to 409 — only the raise-site is missing. `test_lock_prevents_concurrent_start` at `test_bg_ndi_wi_integration.py:82-119` is currently failing because of this. Spec lines 294-392 describe the fix verbatim; the inserted block lifts from `bg_ndi_wi.run:378-393` minus the exclusive-hold body so the probe releases the lock immediately (the runner will re-acquire for real).

- [ ] **Step 1: Write the failing test(s)**

(a) `test_bg_ndi_wi_integration.py::test_lock_prevents_concurrent_start` already exists at lines 82-119 — **do not modify it**. Confirm it is present and unchanged.

(b) Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_api_tasks.py` with the following content:

```python
# backend/tests/test_api_tasks.py
"""API-layer tests for /api/tasks/{id}/start error mapping (Sprint 4 F2)."""
import fcntl
import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_client():
    tmp = tempfile.mkdtemp()
    os.environ["DATA_DIR"] = tmp
    os.environ["DB_PATH"] = str(Path(tmp) / "test.db")
    os.environ["TASKS_DIR"] = str(Path(tmp) / "tasks")
    import importlib
    import app.config
    importlib.reload(app.config)
    import app.database
    importlib.reload(app.database)
    import app.auth
    importlib.reload(app.auth)
    import app.routers.auth
    importlib.reload(app.routers.auth)
    import app.task_manager
    importlib.reload(app.task_manager)
    import app.routers.tasks
    importlib.reload(app.routers.tasks)
    import app.main
    importlib.reload(app.main)
    from app.main import create_app
    from app.database import init_db
    Path(tmp).mkdir(parents=True, exist_ok=True)
    (Path(tmp) / "tasks").mkdir(parents=True, exist_ok=True)
    init_db()
    client = TestClient(create_app())
    resp = client.post("/api/auth/signup", json={
        "email": "u@u.com", "password": "pw123",
        "first_name": "U", "last_name": "U",
    })
    token = resp.json()["access_token"]
    return client, token, Path(tmp)


def test_start_returns_409_when_busy():
    """Externally hold .run_lock; POST /start must return 409, not 500/200."""
    client, token, data_dir = _get_client()
    headers = {"Authorization": f"Bearer {token}"}

    # Create a task with config + input so start_task reaches the lock probe.
    resp = client.post("/api/tasks", json={"task_name": "lock-409"}, headers=headers)
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["id"]

    csv = "pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-06-30,-84.3,30.45\n"
    client.post(
        f"/api/tasks/{task_id}/upload",
        headers=headers,
        files={"file": ("input.csv", csv, "text/csv")},
    )
    client.put(
        f"/api/tasks/{task_id}/config",
        json={
            "experiment": "mock",
            "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
            "variables": ["ndi"],
        },
        headers=headers,
    )

    # Externally hold .run_lock to simulate another running task.
    lock_path = data_dir / ".run_lock"
    lock_path.touch()
    fd = os.open(str(lock_path), os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        resp = client.post(f"/api/tasks/{task_id}/start", headers=headers)
        assert resp.status_code == 409, (
            f"expected 409 TaskBusyError, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert "another task" in body["detail"].lower(), body
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_api_tasks.py backend/tests/test_bg_ndi_wi_integration.py -v -k "test_start_returns_409_when_busy or test_lock_prevents_concurrent_start"
```

Expected: BOTH fail.
- `test_lock_prevents_concurrent_start` fails with `DID NOT RAISE TaskBusyError` (Popen succeeds because `start_task` no longer probes the lock).
- `test_start_returns_409_when_busy` fails with `assert 200 == 409` (Popen succeeds at the HTTP layer; the failure is deferred to the subprocess).

- [ ] **Step 3: Implement the minimal code**

Edit `backend/app/task_manager.py` — in `start_task` (currently lines 264-289), insert the lock pre-check between the `config.json` existence check (line 273-274) and the `cmd = [...]` Popen build (line 276). After the edit `start_task` reads:

```python
def start_task(task_id: str) -> dict:
    """Sprint 3: Popen the supervisor and return its pid synchronously.

    Replaces the Sprint 2 single-runner spawn. The request thread now Popens
    `python -m app.dispatcher run <task_id>` (in a new session) and returns
    immediately with the supervisor pid. The supervisor sequentially spawns
    each per-experiment runner.

    Sprint 4 F2: synchronously probe DATA_DIR/.run_lock before Popen. If
    another task currently holds it, raise TaskBusyError so the router can
    map to HTTP 409. The probe releases immediately — the runner will
    re-acquire the lock for real inside its own process.
    """
    task_dir = _task_dir(task_id)
    if not (task_dir / "config.json").exists():
        raise FileNotFoundError(f"config.json missing for task {task_id}")

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

    cmd = [
        sys.executable,
        "-m", "app.dispatcher",
        "run", task_id,
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(app.config.settings.BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _write_status(task_dir, pid=proc.pid)
    return {"pid": proc.pid, "task_id": task_id}
```

`fcntl` and `os` are already imported at `task_manager.py` lines 7-8 — no new imports needed.

`backend/app/routers/tasks.py` lines 81-89 — verify only. The handler already reads:

```python
@router.post("/{task_id}/start")
def start_task(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    try:
        return task_manager.start_task(task_id)
    except TaskBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

No router change required. If — and only if — `grep -n "TaskBusyError" backend/app/routers/tasks.py` shows the except branch is missing, restore it exactly as above.

- [ ] **Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_api_tasks.py backend/tests/test_bg_ndi_wi_integration.py -v -k "test_start_returns_409_when_busy or test_lock_prevents_concurrent_start"
```

Expected: BOTH pass.

- [ ] **Step 5: Full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 140 passed. (Sprint 4 baseline = 130 after Sprint 3 main; T1+T2+T3+T4+T5 brought it to 139 — the restored `test_lock_prevents_concurrent_start` flipped RED→GREEN inside that count via the existing file. T6 adds one net new test, `test_api_tasks.py::test_start_returns_409_when_busy`, so cumulative = 140.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/task_manager.py backend/tests/test_api_tasks.py
# Only add routers/tasks.py if Step 3 required a restore (normally untouched).
git commit -m "fix(task_manager): restore .run_lock pre-check + HTTP 409 mapping (Sprint 4 F2)"
```

**Notes:**
- The probe is LOCK_NB then immediate LOCK_UN — `start_task` does **not** hold `.run_lock` across the Popen. This preserves the "no orphaned lock if the parent request gets interrupted between probe and Popen" property and lets the runner acquire the lock for real.
- Defense-in-depth: the runner-side `fcntl.flock` at `bg_ndi_wi.run:378-393` / `zcta5_cbp.run:209-219` is intentionally kept — it still guards the standalone `python -m app.experiments.bg_ndi_wi` CLI path used for ops debugging.
- TOCTOU window: a competitor could grab `.run_lock` between our probe-release and the runner's acquisition. That's acceptable — the runner will then fail-fast with its own `BlockingIOError` and the dispatcher will surface `error`. The 409 path covers the common case (two near-simultaneous POSTs) which is what the user-visible bug report is about.
- The restored `test_lock_prevents_concurrent_start` uses `experiment: "mock"` so Popen launches the mock runner — the test never waits for it to finish; the lock probe inside `start_task` short-circuits before Popen is reached.
- Depends on T5. No follow-up flags.

---

### Task T7: F6: drop inline fan_in from bg_ndi_wi.merge_results + migrate 4 Sprint 2 integration tests to dispatcher path

**Files:**
- Create: (none)
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/app/experiments/bg_ndi_wi.py`
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_bg_ndi_wi_integration.py`
- Test: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/tests/test_bg_ndi_wi_integration.py`

**Goal:** Eliminate the redundant inline `_merge.fan_in` call in `bg_ndi_wi.merge_results` so both experiment runners' `merge_results` are symmetric (`write_partial` only), and migrate the four Sprint 2 standalone `subprocess.run([..., '-m', 'app.experiments.bg_ndi_wi', 'run', task_dir])` integration tests to the dispatcher path via `task_manager.start_task` so they continue to verify `result.csv` end-to-end.

**Context:** Today `bg_ndi_wi.merge_results` (lines 232-247) calls `_merge.write_partial(...)` *and then* `_merge.fan_in(task_dir=task_dir, experiment_keys=["bg_ndi_wi"])` as an inline safety net so that the four Sprint 2 standalone integration tests — which run the runner module directly via `python -m app.experiments.bg_ndi_wi run <task_dir>` (NOT through the dispatcher) — still find `result.csv` at runner exit. The companion runner `zcta5_cbp.merge_results` does NOT do this inline fan_in (it returns the partial path), so the dispatcher path always writes `result.csv` *twice* whenever `bg_ndi_wi` runs (once inline, once in `dispatcher.py:168-174`'s post-experiment loop), with a brief window where `result.csv` contains bg-only columns. F6 chose Option (a) (full migration): rewrite the four tests to invoke the runner via `start_task` + status.json poll (matching the canonical shape at `test_e2e_multi_experiment.py:41-82`), then drop the inline `_merge.fan_in` from `bg_ndi_wi.merge_results`. F2 (lock pre-check) lands first so `start_task` is reliable. The four target tests are: `test_e2e_small_cohort` (line 58 today; assert at line 73), `test_two_sequential_runs_both_succeed` (lines 162-200), `test_e2e_cache_second_run_faster` (lines 204-260), `test_e2e_multi_episode_cohort` (lines 286-327). `test_lock_prevents_concurrent_start` and `test_stop_kills_pipeline_subprocess` stay on their existing paths (they test the dispatcher lock / subprocess kill semantics directly and don't depend on inline fan_in).

- [ ] **Step 1: Write the failing test(s)**

Rewrite the four tests in `backend/tests/test_bg_ndi_wi_integration.py` to use the dispatcher path. Each test (1) writes `config.json` via `task_manager.save_config(meta['id'], {... "experiment": "auto" ...})`, (2) calls `start_task(meta['id'])`, (3) polls `status.json` for terminal states up to 240s, (4) asserts `status['status'] == 'finished'`, (5) keeps the existing `result.csv` / dataframe assertions unchanged.

First, add a shared dispatcher-driven fixture near the top of the file (after the `pytestmark` block, replacing the existing `task_with_5_patients` fixture body so callers don't change):

```python
@pytest.fixture
def task_with_5_patients(tmp_path, monkeypatch):
    """Dispatcher-driven 5-patient cohort fixture (Sprint 4 F6 migration).

    Returns (task_id, task_dir). Caller invokes start_task(task_id) and polls
    status.json — replacing the Sprint 2 subprocess.run([..., '-m',
    'app.experiments.bg_ndi_wi', 'run', task_dir]) pattern.
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="bg-ndi-wi-int-5p")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["ndi", "walkability"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir
```

Then rewrite test (1) `test_e2e_small_cohort`:

```python
@pytest.mark.integration
def test_e2e_small_cohort(task_with_5_patients):
    task_id, task_dir = task_with_5_patients

    from app.task_manager import start_task
    start_task(task_id)

    deadline = time.monotonic() + 240.0
    status = {}
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 240s; last status={status}")

    assert status["status"] == "finished", f"unexpected terminal status: {status}"

    result_csv = task_dir / "output" / "result.csv"
    assert result_csv.exists()
    df = pd.read_csv(result_csv)
    assert len(df) == 5
    assert "ndi" in df.columns
    assert "NatWalkInd" in df.columns
    # At least 3 of 5 patients must have an NDI value (Leon FL BGs all have NDI 2017)
    assert df["ndi"].notna().sum() >= 3
```

Rewrite test (2) `test_two_sequential_runs_both_succeed` — second run uses a fresh dispatcher-driven task:

```python
@pytest.mark.integration
def test_two_sequential_runs_both_succeed(task_with_5_patients, tmp_path, monkeypatch):
    """After one dispatcher run finishes, the lock must release so a second
    start_task can acquire it without TaskBusyError. Regression test for the
    Sprint 1 lock-leak bug, now exercising the dispatcher path."""
    task_id_1, task_dir_1 = task_with_5_patients

    from app.task_manager import start_task, create_task, save_config

    # First run
    start_task(task_id_1)
    deadline = time.monotonic() + 240.0
    status1 = {}
    while time.monotonic() < deadline:
        status1 = json.loads((task_dir_1 / "status.json").read_text())
        if status1.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"first run did not terminate within 240s; last status={status1}")
    assert status1["status"] == "finished", f"first run not finished: {status1}"

    # Second task on a fresh task_id (dispatcher path), same fixture cohort + variables.
    meta2 = create_task(user_id=1, task_name="bg-ndi-wi-int-5p-2")
    import app.config as _config
    task_dir_2 = _config.settings.TASKS_DIR / f"task-{meta2['id']}"
    task_dir_2.mkdir(parents=True, exist_ok=True)
    (task_dir_2 / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir_2 / "input.csv",
    )
    save_config(meta2["id"], {
        "experiment": "auto",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })

    start_task(meta2["id"])
    deadline2 = time.monotonic() + 240.0
    status2 = {}
    while time.monotonic() < deadline2:
        status2 = json.loads((task_dir_2 / "status.json").read_text())
        if status2.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"second run did not terminate within 240s; last status={status2}")
    assert status2["status"] == "finished", f"second run not finished: {status2}"

    assert (task_dir_1 / "output" / "result.csv").exists()
    assert (task_dir_2 / "output" / "result.csv").exists()
```

Rewrite test (3) `test_e2e_cache_second_run_faster`:

```python
@pytest.mark.integration
def test_e2e_cache_second_run_faster(task_with_5_patients, tmp_path, monkeypatch):
    """Run the same 5-patient cohort twice via the dispatcher; the second run
    hits the c3_bg cache and finishes in a small fraction of the first run's
    wall-clock."""
    cache_dir = app.config.settings.C3_CACHE_DIR
    if cache_dir.exists():
        shutil.rmtree(cache_dir)

    task_id_1, task_dir_1 = task_with_5_patients
    from app.task_manager import start_task, create_task, save_config

    # First run: full pipeline (cold cache).
    t1_start = time.monotonic()
    start_task(task_id_1)
    deadline = time.monotonic() + 240.0
    status1 = {}
    while time.monotonic() < deadline:
        status1 = json.loads((task_dir_1 / "status.json").read_text())
        if status1.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"first run did not terminate within 240s; last status={status1}")
    t1 = time.monotonic() - t1_start
    assert status1["status"] == "finished", f"first run not finished: {status1}"

    # Second task with byte-identical input.csv + config (cache hit).
    meta2 = create_task(user_id=1, task_name="bg-ndi-wi-int-cache-2")
    import app.config as _config
    task_dir_2 = _config.settings.TASKS_DIR / f"task-{meta2['id']}"
    task_dir_2.mkdir(parents=True, exist_ok=True)
    (task_dir_2 / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir_2 / "input.csv",
    )
    save_config(meta2["id"], {
        "experiment": "auto",
        "variables": ["ndi", "walkability"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })

    t2_start = time.monotonic()
    start_task(meta2["id"])
    deadline2 = time.monotonic() + 240.0
    status2 = {}
    while time.monotonic() < deadline2:
        status2 = json.loads((task_dir_2 / "status.json").read_text())
        if status2.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"second run did not terminate within 240s; last status={status2}")
    t2 = time.monotonic() - t2_start
    assert status2["status"] == "finished", f"second run not finished: {status2}"

    # Second run should be noticeably faster (C3 step skipped). Threshold 0.7
    # catches a cache regression without being flaky on slow hardware. Wall-clock
    # now includes dispatcher Popen overhead (~2s constant) on both sides, so the
    # ratio is preserved.
    assert t2 < 0.7 * t1, (
        f"expected second run to be < 70% of first; got t1={t1:.2f}s t2={t2:.2f}s"
    )

    parquets = list(cache_dir.glob("*.parquet"))
    assert len(parquets) >= 1
```

Replace the `task_with_multi_episode_cohort` fixture and rewrite test (4) `test_e2e_multi_episode_cohort`:

```python
@pytest.fixture
def task_with_multi_episode_cohort(tmp_path, monkeypatch):
    """11-row cohort: 5 patients x 2 episodes + 1 single-episode patient.

    Dispatcher-driven (Sprint 4 F6 migration). Returns (task_id, task_dir).
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="bg-ndi-wi-int-multi-ep")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_multi_episode.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["ndi", "walkability"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_multi_episode_cohort(task_with_multi_episode_cohort):
    """Sprint 2: pipeline emits per-(patient, episode) rows; the 5x2+1 cohort
    must produce 11 result rows, not 6. Migrated to dispatcher path in Sprint 4 F6."""
    task_id, task_dir = task_with_multi_episode_cohort

    from app.task_manager import start_task
    start_task(task_id)

    deadline = time.monotonic() + 240.0
    status = {}
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 240s; last status={status}")

    assert status["status"] == "finished", f"unexpected terminal status: {status}"

    result_csv = task_dir / "output" / "result.csv"
    df = pd.read_csv(result_csv)

    # CRITICAL: one row per residential episode, not per patient.
    assert len(df) == 11, f"expected 11 rows (per-episode), got {len(df)}"

    assert df["pid"].tolist() == [
        "PID0000001", "PID0000001",
        "PID0000002", "PID0000002",
        "PID0000003", "PID0000003",
        "PID0000004", "PID0000004",
        "PID0000005", "PID0000005",
        "PID0000006",
    ]

    multi_episode_pids = ["PID0000001", "PID0000002", "PID0000003", "PID0000004", "PID0000005"]
    distinct_ndi_count = 0
    for pid in multi_episode_pids:
        vals = df[df["pid"] == pid]["ndi"].dropna().tolist()
        if len(vals) == 2 and vals[0] != vals[1]:
            distinct_ndi_count += 1
    assert distinct_ndi_count >= 2, (
        f"expected >=2 patients with distinct NDI across their 2 episodes; "
        f"only {distinct_ndi_count} differed. Result df:\n{df}"
    )
```

`test_lock_prevents_concurrent_start` and `test_stop_kills_pipeline_subprocess` are NOT touched — they exercise the dispatcher lock pre-check and pipeline subprocess kill semantics directly and don't depend on inline fan_in.

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_bg_ndi_wi_integration.py -v -k "test_e2e_small_cohort or test_two_sequential_runs_both_succeed or test_e2e_cache_second_run_faster or test_e2e_multi_episode_cohort" -m integration
```

Expected: all 4 migrated tests FAIL (or behave inconsistently). Specifically: with the inline `_merge.fan_in` still present in `bg_ndi_wi.merge_results`, the dispatcher path produces a transient `result.csv` containing only `bg_ndi_wi` columns mid-run before the dispatcher-final `_merge.fan_in` overwrites it. If the test's poll-loop catches the task after the inline write but before the dispatcher rewrite, the `result.csv` assertion may pass — but the underlying double-write is still happening and the spec calls for symmetric `merge_results` semantics. The cleaner RED signal: with the F2 lock pre-check newly restored in `start_task`, any partial collision between back-to-back `start_task` calls in `test_two_sequential_runs_both_succeed` / `test_e2e_cache_second_run_faster` (where the first task's dispatcher hasn't fully released `.run_lock` before the second `start_task` runs) raises `TaskBusyError`. If RED is not crisply observable on this host (tests happen to pass with the inline fan_in still in place because the dispatcher final-write also runs), proceed to Step 3 — the assertion that justifies the change is the *symmetry* contract, not a single failing test.

- [ ] **Step 3: Implement the minimal code**

Edit `backend/app/experiments/bg_ndi_wi.py` lines 232-247. Replace:

```python
def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Sprint 3: delegates to shared _merge.write_partial, then runs fan_in
    inline as a safety net so result.csv still exists at run() completion.

    T9 (dispatcher) will move the fan_in step to the dispatcher's post-experiment
    loop and strip this inline call.
    """
    from app.experiments import _merge
    parquet_map = {v: f"{_VARIABLE_TO_STEP[v].name}.parquet" for v in variables}
    _merge.write_partial(
        task_dir=task_dir,
        experiment_key="bg_ndi_wi",
        variables=variables,
        parquet_map=parquet_map,
    )
    return _merge.fan_in(task_dir=task_dir, experiment_keys=["bg_ndi_wi"])
```

with:

```python
def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Delegate to shared _merge.write_partial; return the partial path.

    Sprint 4 F6: dropped the inline _merge.fan_in safety net. The dispatcher's
    post-experiment loop (dispatcher.py:168-174) runs the final fan_in over the
    completed experiment list, so result.csv is produced exactly once per task.
    Both runners' merge_results are now symmetric (zcta5_cbp.merge_results
    likewise returns write_partial's path).
    """
    from app.experiments import _merge
    parquet_map = {v: f"{_VARIABLE_TO_STEP[v].name}.parquet" for v in variables}
    return _merge.write_partial(
        task_dir=task_dir,
        experiment_key="bg_ndi_wi",
        variables=variables,
        parquet_map=parquet_map,
    )
```

No other production code changes — `dispatcher.py:168-174` already does the post-experiment `_merge.fan_in(task_dir, completed)` call that now becomes the sole writer of `result.csv`.

- [ ] **Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_bg_ndi_wi_integration.py -v -k "test_e2e_small_cohort or test_two_sequential_runs_both_succeed or test_e2e_cache_second_run_faster or test_e2e_multi_episode_cohort" -m integration
```

Expected: PASS — all 4 migrated tests complete via `start_task` + poll loop, `status['status'] == 'finished'`, `result.csv` exists with the expected row counts / columns / NDI value diversity.

Then confirm the cross-runner regression set:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_e2e_multi_experiment.py::test_e2e_multi_experiment_cohort backend/tests/test_bg_ndi_wi_integration.py::test_lock_prevents_concurrent_start -v -m integration
```

Expected: both PASS (regression on dispatcher path + F2 lock pre-check).

- [ ] **Step 5: Full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 140 passed (T6 baseline 140; T7 modifies 4 existing tests + drops 1 production line, no new tests, no removed tests — count unchanged). Cumulative Sprint 4 count after T7: **140**.

- [ ] **Step 6: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/tests/test_bg_ndi_wi_integration.py
git commit -m "$(cat <<'EOF'
refactor(bg_ndi_wi): drop inline fan_in + migrate 4 Sprint 2 integration tests to dispatcher (Sprint 4 F6)

bg_ndi_wi.merge_results now returns _merge.write_partial(...) only —
symmetric with zcta5_cbp.merge_results. The dispatcher's post-experiment
loop is the sole writer of result.csv, eliminating the 2x merge I/O and
the transient bg-only result.csv window.

The four Sprint 2 standalone @pytest.mark.integration tests
(test_e2e_small_cohort, test_two_sequential_runs_both_succeed,
test_e2e_cache_second_run_faster, test_e2e_multi_episode_cohort) are
migrated from subprocess.run([..., '-m', 'app.experiments.bg_ndi_wi',
'run', task_dir]) to the canonical dispatcher shape: save_config(...,
experiment='auto') -> start_task(task_id) -> 240s status.json poll
loop -> assert finished + result.csv assertions unchanged.

test_lock_prevents_concurrent_start and test_stop_kills_pipeline_subprocess
are unchanged — they exercise lock pre-check / subprocess kill semantics
directly and don't depend on inline fan_in.

Spec: docs/superpowers/specs/2026-06-16-sprint-4-followups-design.md F6.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

**Notes:**
- Depends on T6 (whose baseline of 140 this task preserves) and transitively on F2's restored `start_task` lock pre-check (any `start_task` failure due to lock contention between back-to-back tests would surface here first).
- `_VARIABLE_TO_STEP` is the existing module-level dict in `bg_ndi_wi.py` — the new body references it identically to the old body; no new imports needed.
- After this task `zcta5_cbp.merge_results`'s docstring comment that today reads "matches bg_ndi_wi T5 wrapper" becomes accurate without modification.
- **Two-fixture approach (committed):** the dispatcher-driven fixture is named `task_with_5_patients_dispatched` and returns `(task_id, task_dir)`. The original `task_with_5_patients` (subprocess-friendly raw `Path`) is left **untouched** so `test_stop_kills_pipeline_subprocess` continues to consume it as a raw `Path` with no changes. Step 1 above migrates the four target tests (`test_e2e_small_cohort`, `test_two_sequential_runs_both_succeed`, `test_e2e_cache_second_run_faster`, `test_e2e_multi_episode_cohort`) to the new `task_with_5_patients_dispatched` fixture; `test_stop_kills_pipeline_subprocess` is unchanged — still consumes the original `task_with_5_patients` fixture as a raw `Path`.
- Wall-clock budget: each migrated test now includes ~1-2s of dispatcher Popen overhead on top of the existing pipeline cost. The 240s poll deadline matches the canonical `test_e2e_multi_experiment.py` shape and leaves ample headroom for the 5-patient (~14s) and 11-row multi-episode (~25s) cohorts.
- The cache-speedup ratio in `test_e2e_cache_second_run_faster` is preserved because the Popen overhead is constant across both runs — it doesn't change the t2/t1 ratio meaningfully.
- F6 is the final structural cleanup for Sprint 4; after this lands, both experiment runners' `merge_results` are line-for-line equivalent modulo per-experiment `parquet_map` derivation.

---

## Final verification

Once all seven tasks are committed in order T1 → T2 → T3 → T4 → T5 → T6 → T7, perform the following end-to-end verification before declaring Sprint 4 done.

- [ ] **Full backend pytest (default + integration markers)**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q -m integration
```

Expected: default suite reports **140 passed**; integration suite reports all integration tests passing (no acknowledged failures — `test_lock_prevents_concurrent_start` and the four migrated bg_ndi_wi tests now green; new `test_e2e_cancellation_terminal_state` passes when local fixtures are configured, otherwise skipped).

- [ ] **Frontend TypeScript clean**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/frontend
~/.nvm/versions/node/v20.20.2/bin/npx tsc --noEmit
```

Expected: zero diagnostics. Sprint 4 makes no frontend changes — this is regression armor.

- [ ] **Frontend Next.js lint clean**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/frontend
~/.nvm/versions/node/v20.20.2/bin/npx next lint
```

Expected: zero warnings and zero errors.

- [ ] **Sprint 3 invariant: `backend/data/variable_metadata.json` does NOT exist**

```bash
test ! -e /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4/backend/data/variable_metadata.json && echo "OK: no rogue variable_metadata.json"
```

Expected: prints `OK: no rogue variable_metadata.json`. The variable registry must load from the canonical Sprint 3 location only; any reappearance of this file is a regression in the registry layer.

- [ ] **Cumulative test-count walk**

Verify the per-task ledger matches the post-task pytest output:

| After | Expected | Notes |
|-------|----------|-------|
| baseline | 130 | Sprint 3 main, 1 acknowledged red (`test_lock_prevents_concurrent_start`) |
| T1 | 133 | +3 startup probe tests |
| T2 | 134 | +1 composite-key fan_in test |
| T3 | 135 | +1 invalid-JWT negative test |
| T4 | 137 | +2 stop_task scope tests |
| T5 | 139 | +2 cancellation tests (1 unit + 1 e2e) |
| T6 | 140 | +1 API-layer 409 test (restored lock test flips R→G within the same count) |
| T7 | 140 | 4 migrations + 0 new + 0 removed |

- [ ] **Branch hygiene + finishing-a-development-branch prompt**

Once all the above checks are green:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-4
git log --oneline main..HEAD
git status
```

Verify seven Sprint 4 commits sit on top of `main` (one per task), the working tree is clean, and no untracked files remain.

Then invoke the `superpowers:finishing-a-development-branch` skill in a new session to choose between merging to `main`, opening a PR, or shelving the branch. Pass the worktree path and branch name as context; the skill walks through the structured option set (rebase vs merge, squash vs no-squash, push behavior, post-merge worktree cleanup) and will not touch `main` without explicit confirmation.

**End of Sprint 4 plan.**
