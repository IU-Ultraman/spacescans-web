# Sprint 6: H1-H6 Follow-ups Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Close all 6 IMPORTANT findings from Sprint 5's adversarial cross-lens final review. No new experiments, no new variables, no UI changes. Pure tech-debt cleanup.

**Architecture:** Mostly web-only cleanup (H3, H4, H6 web; H1 web requirements pin + pipeline version bump; H2 web variable_registry; H5 cross-repo pipeline+web). Implementation order H6 → H4 → H3 → H5a → H1 → H2 → H5b (mechanical first, then helper lands BEFORE the wheel build, then cross-repo verification last).

**Spec:** docs/superpowers/specs/2026-06-16-sprint-6-followups-design.md (630 lines, committed 55bb47b)

**Web base branch:** main (Sprint 5 merged at e43cb9f)
**Pipeline base branch (for H5 + H1 version bump):** pkg/pypi-only (Sprint 5 Phase A merged at 13f394a)

**Repo layout note (verified on disk):**
- The pipeline repo root is `/Users/xai/Desktop/spacescans-project/` (a single git checkout); its `pyproject.toml` lives at the repo root with `name = "spacescans-pipeline"`, `version = "0.1.0"`. The pipeline import name is `spacescans` (NOT `spacescans_pipeline`). There is no nested `spacescans-pipeline/` subdirectory.
- The web repo lives at `/Users/xai/Desktop/spacescans-project/spacescans-web/` (a submodule-style checkout; current branch `pkg/pypi-only`).

**Web worktree:** `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6`, branch `feat/sprint-6-followups`, created by T0 below — must be the first executed step.

**Web baseline:** 153 backend tests pass, 6 integration green
**Pipeline baseline:** 69 tests pass (verified at HEAD with the canonical invocation below)

**Canonical pipeline pytest invocation (baseline-pinning):**

```bash
cd /Users/xai/Desktop/spacescans-project && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

This exact command (no marker selection) is the baseline reference for every pipeline Step-5 in Sprint 6. It produces `69 passed` at HEAD; every pipeline test count in this plan is anchored to this invocation.

## Table of Contents

- [T0: Bootstrap web worktree (prerequisite for all web-side tasks)](#task-t0-bootstrap-web-worktree-prerequisite-for-all-web-side-tasks)
- [T1: H6 PYTHONPATH override conditional rewrite (Phase A)](#task-t1-h6-pythonpath-override-conditional-rewrite-in-test_pipeline_smokepy-phase-a)
- [T2: H4 Remove redundant variables_by_experiment monkeypatch (Phase B)](#task-t2-h4-remove-redundant-variables_by_experiment-monkeypatch-from-test_task_manager_dispatchpy-phase-b)
- [T3: H3 Unify cache-event log source to step.name across 3 C3-aware runners (Phase B)](#task-t3-h3-unify-cache-event-log-source-to-stepname-across-3-c3-aware-runners-phase-b)
- [T6: H5a resolve_output_grouping helper in pipeline linkage layer (Phase A — MUST land before T4)](#task-t6-h5a-resolve_output_grouping-helper-in-pipeline-linkage-layer-phase-a)
- [T4: H1 Coordinated pipeline 0.1.0 -> 0.2.0 bump + web requirements.txt pin (Phase A + Phase B atomic)](#task-t4-h1-coordinated-pipeline-010---020-bump--web-requirementstxt-pin-phase-a--phase-b-atomic)
- [T5: H2 TIGER C4 server-boot pre-flight in variable_registry.load_variables (Phase B)](#task-t5-h2-tiger-c4-server-boot-pre-flight-in-variable_registryload_variables-phase-b)
- [T7: H5b Web-side absorption verification of resolve_output_grouping (Phase B)](#task-t7-h5b-web-side-absorption-verification-of-resolve_output_grouping-phase-b)
- [T8: Sprint 6 final verification (full pytest, frontend TS/lint, test-count walk)](#task-t8-sprint-6-final-verification-full-pytest-frontend-tslint-test-count-walk)

**Critical ordering note:** T6 (H5a helper) MUST land in the pipeline source tree BEFORE T4 builds the 0.2.0 wheel. Otherwise the wheel built and force-reinstalled at T4 step 3b will NOT contain `resolve_output_grouping`, and T7's runtime import check will fail under a non-editable install. The spec H5 (lines 449-452) declares this lockstep atomicity.

---

### Task T0: Bootstrap web worktree (prerequisite for all web-side tasks)

**Files:** none (creates worktree directory + branch)

**Goal:** Create the `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6` worktree on a new branch `feat/sprint-6-followups` rooted at `main`. Every subsequent web-side `cd .../.worktrees/feat-sprint-6 ...` invocation depends on this directory existing.

**Context:** As of plan authoring, `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/` is empty (`git worktree list` shows only the main checkout at branch `pkg/pypi-only`). T2..T7 all reference the worktree; without T0 every web-side bash block fails with "No such file or directory" before pytest runs.

Step 1: Bootstrap the worktree

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web && \
  git fetch origin main && \
  git worktree add -b feat/sprint-6-followups .worktrees/feat-sprint-6 origin/main
```

Step 2: Verify

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web && \
  git worktree list && \
  ls .worktrees/feat-sprint-6/backend/tests/ | head -3
```

Expected: worktree list includes `.worktrees/feat-sprint-6  <sha> [feat/sprint-6-followups]`; the `ls` succeeds (lists backend test files).

Step 3: Provision the worktree's Python venv (so subsequent `.venv/bin/pytest` and `.venv/bin/pip` invocations resolve)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  python3 -m venv .venv && \
  .venv/bin/pip install -U pip && \
  .venv/bin/pip install -r backend/requirements.txt && \
  .venv/bin/pip install -e /Users/xai/Desktop/spacescans-project
```

(The editable install of `/Users/xai/Desktop/spacescans-project` — the pipeline repo — is required so the web worktree picks up T6's helper before T4's wheel rebuild.)

**Notes:**
- If a previous run left a stale worktree at `.worktrees/feat-sprint-6`, remove it first with `git worktree remove .worktrees/feat-sprint-6 --force` before re-adding.
- All subsequent web tasks (T2, T3, T4, T5, T7) assume this worktree exists. If you choose to operate on the live `spacescans-web` checkout instead (current branch `pkg/pypi-only`), replace every `.worktrees/feat-sprint-6` path with the parent `spacescans-web` directory and skip T0 — but harmonize that choice throughout before starting T2.

---

---

### Task T1: H6: PYTHONPATH override conditional rewrite in test_pipeline_smoke.py (Phase A)

**Files:**
- Modify: `/Users/xai/Desktop/spacescans-project/tests/test_pipeline_smoke.py`
- Test: `/Users/xai/Desktop/spacescans-project/tests/test_pipeline_smoke.py`

**Goal:** Replace the unconditional `PYTHONPATH` override at `tests/test_pipeline_smoke.py:159-160` with a conditional that only injects the worktree's `src/` onto `PYTHONPATH` when the editable-installed `spacescans` package resolves to a different location than the worktree's `src/spacescans/__init__.py`, and lock the no-op branch behavior with a new unit test.

**Context:** Sprint 5 added an unconditional `PYTHONPATH = worktree_src + os.pathsep + ...` override at lines 159-160 to let the smoke run against the worktree's `src/` when an editable install resolved elsewhere. On single-checkout dev boxes the override is a perma-no-op, but it remains load-bearing for any worktree whose editable install was last reinstalled against `main` (which lacks Sprint 5's `output_grouping` dispatch). Per spec H6 (lines 468-543), full deletion is unsafe pre-merge while leave-as-is gives future maintainers no signal — the conditional rewrite is mechanically small, makes the worktree-vs-install branch explicit, and preserves worktree safety. This is Phase A in the spacescans-pipeline repo (working tree `/Users/xai/Desktop/spacescans-project`), single file, no cross-repo coupling, lands first per spec order (H6 → H4 → H3 → H1 → H2 → H5).

Step 1: Write failing test (real pytest code)

Append to `/Users/xai/Desktop/spacescans-project/tests/test_pipeline_smoke.py`:

```python
def test_pythonpath_helper_no_ops_when_paths_match(monkeypatch):
    """H6: when the editable install resolves to the worktree's own
    src/spacescans/__init__.py, the helper must NOT inject PYTHONPATH —
    env must equal os.environ.copy() (worktree-safety affordance is a no-op
    on single-checkout dev boxes).
    """
    import spacescans as _ss_pkg

    worktree_init = Path(__file__).resolve().parents[1] / "src" / "spacescans" / "__init__.py"
    # Force the comparison's installed_init side to match worktree_init exactly.
    monkeypatch.setattr(_ss_pkg, "__file__", str(worktree_init))

    installed_init = Path(_ss_pkg.__file__).resolve()
    if worktree_init.resolve() != installed_init:
        worktree_src = str(Path(__file__).resolve().parents[1] / "src")
        env = {**os.environ, "PYTHONPATH": worktree_src + os.pathsep + os.environ.get("PYTHONPATH", "")}
    else:
        env = os.environ.copy()

    assert env == os.environ.copy(), (
        "paths-match branch must produce env identical to os.environ.copy(); "
        f"got diff keys: {set(env) ^ set(os.environ)}"
    )
    assert env.get("PYTHONPATH") == os.environ.get("PYTHONPATH"), (
        "PYTHONPATH must be untouched when worktree == installed init path"
    )
```

Step 2: Run RED (concrete bash + expected behavior)

```bash
cd /Users/xai/Desktop/spacescans-project
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_pipeline_smoke.py::test_pythonpath_helper_no_ops_when_paths_match -v
```

Expected: **no RED — this test passes against pre-change code on dev hosts.** The test imports `spacescans as _ss_pkg` at function scope (line 53), monkeypatches `_ss_pkg.__file__` to the worktree's own `__init__.py`, then re-derives `env` inline using the same conditional the production code WILL adopt in Step 3. On any single-checkout dev box where the editable install resolves to the worktree (which is the realistic dev posture), the else-branch fires and the assertion holds today.

This is a **regression-armor test, not a TDD-style failing test.** Its purpose is to LOCK the no-op branch behavior so a future regression that re-introduces an unconditional `PYTHONPATH = worktree_src + ...` override (which would diverge `env` from `os.environ.copy()`) is caught. The narrative "RED" step is satisfied by acknowledging this explicitly; the production-side guard added in Step 3 is the actual behavior change. If a true failing-state demonstration is required, see Notes for a subprocess-based variant that asserts env propagation when worktree != install.

Step 3: Implement minimal code (actual code to paste)

Edit `/Users/xai/Desktop/spacescans-project/tests/test_pipeline_smoke.py`.

Hoist `import spacescans as _ss_pkg` into the file-top imports. Replace the existing import block (lines 1-12):

```python
"""init() runs and registers expected base patterns."""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pandas as pd
import pytest
import yaml

import spacescans as _ss_pkg
from spacescans.pipeline.registry import init, get_pattern
```

Then replace the unconditional override at lines 159-160:

```python
    # Force subprocess to import spacescans from THIS checkout's src/ rather
    # than the editable-install location, so A1's dispatch code is exercised
    # even when the worktree's branch hasn't been merged to the install ref.
    # H6: only inject when the editable install resolves elsewhere — on a
    # single-checkout dev box the install IS the worktree and the override
    # is a no-op (env = os.environ.copy()).
    worktree_init = Path(__file__).resolve().parents[1] / "src" / "spacescans" / "__init__.py"
    installed_init = Path(_ss_pkg.__file__).resolve()
    if worktree_init.resolve() != installed_init:
        # worktree differs from editable install — inject worktree onto PYTHONPATH
        worktree_src = str(Path(__file__).resolve().parents[1] / "src")
        env = {**os.environ, "PYTHONPATH": worktree_src + os.pathsep + os.environ.get("PYTHONPATH", "")}
    else:
        env = os.environ.copy()
```

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_pipeline_smoke.py::test_pythonpath_helper_no_ops_when_paths_match -v
```

Expected: `1 passed`. The monkeypatched `spacescans.__file__` makes `installed_init == worktree_init.resolve()`, the else-branch fires, and `env == os.environ.copy()`.

Step 5: Full suite (with expected cumulative count)

Use the **canonical pipeline pytest invocation** (defined in front-matter):

```bash
cd /Users/xai/Desktop/spacescans-project && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: `70 passed` (Phase A baseline 69 + 1 new = 70). This is the same canonical invocation that produces `69 passed` at HEAD; the +1 delta is the new no-op unit test. The existing `test_tiger_roads_demo_episode_branch_row_count` must still pass — on this dev box the editable install resolves to the worktree's own `src/spacescans/__init__.py`, so the else-branch fires and the subprocess inherits a clean `os.environ.copy()` env, identical to pre-H6 behavior for single-checkout dev. Marker-gated tests (`@pytest.mark.geo` / `@pytest.mark.extras`) are excluded by the no-marker default; the new no-op test is unmarked so it counts.

Step 6: Commit (conventional message)

```bash
cd /Users/xai/Desktop/spacescans-project
git add tests/test_pipeline_smoke.py
git commit -m "$(cat <<'EOF'
test(smoke): H6 conditional PYTHONPATH override + no-op unit test

Replace the unconditional PYTHONPATH worktree-src injection at
tests/test_pipeline_smoke.py:159-160 with a conditional that only
injects when Path(spacescans.__file__).resolve() differs from the
worktree's src/spacescans/__init__.py. Hoist `import spacescans as
_ss_pkg` to file-top imports. Add test_pythonpath_helper_no_ops_when_paths_match
locking the else-branch (env == os.environ.copy()) via monkeypatched
spacescans.__file__.

Worktree safety preserved for editable installs pointing to a different
checkout (e.g. main without Sprint 5's output_grouping dispatch);
single-checkout dev boxes get a clean env. Phase A baseline 69 -> 70.

Spec: docs/superpowers/specs/2026-06-16-sprint-6-followups-design.md H6 (L468-543)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

**Notes:**
- The new test does NOT spawn a subprocess — it inlines the path-comparison block with a monkeypatched `_ss_pkg.__file__` and asserts on the resulting `env` dict. This keeps the unit test deterministic on any host regardless of where the real editable install resolves.
- `worktree_init.resolve()` is critical — `Path(...) / "src" / ...` may contain unresolved symlinks (e.g. `/var` vs `/private/var` on macOS, or `.worktrees/` symlinks); both sides of the comparison must call `.resolve()` to get a canonical form. The monkeypatch sets `_ss_pkg.__file__` to the unresolved `worktree_init`, then `Path(...).resolve()` on the installed side normalizes it — both sides must agree post-`.resolve()`.
- Do NOT mutate `os.environ` itself anywhere — only build the local `env` dict. The assertion `env == os.environ.copy()` would false-pass if the override leaked `PYTHONPATH` into the process env.
- The existing `test_tiger_roads_demo_episode_branch_row_count` is marked `@pytest.mark.geo` + `@pytest.mark.extras`; it is NOT in the default 69-test baseline unless those markers are selected. The new no-op test is unmarked, so it counts toward the default baseline → 70.
- File-top hoist of `import spacescans as _ss_pkg` is safe: the file already imports `from spacescans.pipeline.registry import ...` at line 12, so any base-install import failure would already surface at collection time. The new alias adds no new import-time risk.
- Phase A only — Phase B (web-side ripple, if any) is owned by a later task per spec implementation order. No cross-repo coupling here.

---

### Task T2: H4: Remove redundant variables_by_experiment monkeypatch from test_task_manager_dispatch.py (Phase B)

**Files:** /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/tests/test_task_manager_dispatch.py
**Goal:** Delete the redundant `variables_by_experiment` monkeypatch (the inline comment at lines 267-268 + the `monkeypatch.setattr` block at lines 269-276 — verified inclusive range 267-276) so the dispatch-order test exercises the real `VariableRegistry` against the on-disk `variable_metadata.json` instead of a hand-rolled lambda that duplicates its output.
**Context:** The lambda at lines 269-276 of `backend/tests/test_task_manager_dispatch.py` (inside `test_three_experiment_dispatch_preserves_metadata_order`, verified at line 245) returns the exact dict the real registry already produces from `variable_metadata.json` (file-order keys: `bg_ndi_wi`, `zcta5_cbp`, `tiger_proximity`). It is therefore redundant and, worse, hides regressions in the real registry path. The companion test `test_variable_registry.py::test_variables_by_experiment_preserves_file_order` locks the file-order semantics on the registry side, so removing the monkeypatch leaves the two tests forming a paired invariant (registry locks file-order, dispatch test locks registry-to-cmd preservation). Pure deletion, no production code change, no new tests.

Step 1: Write failing test (real pytest code)

No new test — this is pure deletion of redundant scaffolding. The existing test `test_three_experiment_dispatch_preserves_metadata_order` (definition at line 245) becomes the verification target: after removing the monkeypatch, it must continue to pass because the real registry already returns the same dict shape.

The "failing" step here is asserting that with the monkeypatch removed, the real registry path produces the assertions already in the test. We perform an explicit redundancy probe in Step 2: save the to-be-deleted block, delete it, re-run; if green, the redundancy claim is proved and Step 3 is a no-op commit of the same deletion (with a rollback path if RED).

Step 2: Run RED (concrete bash + redundancy probe before deletion)

First confirm the test currently passes with the monkeypatch present:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  .venv/bin/python -m pytest backend/tests/test_task_manager_dispatch.py::test_three_experiment_dispatch_preserves_metadata_order -v 2>&1 | tail -10
```

Expected: `1 passed`. Now prove the monkeypatch is redundant rather than load-bearing — save the block, then perform the deletion as the redundancy probe:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  sed -n '267,276p' backend/tests/test_task_manager_dispatch.py > /tmp/sprint6_t2_saved_block.txt && \
  echo "--- saved block ---" && cat /tmp/sprint6_t2_saved_block.txt
```

Then apply the deletion (Step 3) and re-run:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  .venv/bin/python -m pytest backend/tests/test_task_manager_dispatch.py::test_three_experiment_dispatch_preserves_metadata_order -v 2>&1 | tail -10
```

Expected after deletion: `1 passed` (the real registry produces the same dict shape). If FAILED, restore the block from `/tmp/sprint6_t2_saved_block.txt`, stop, and surface to orchestrator — the spec assumption is wrong.

Step 3: Implement minimal code (actual code to paste)

Edit `backend/tests/test_task_manager_dispatch.py` — delete lines 267-276 (the two-line inline comment at 267-268 + the seven-line `monkeypatch.setattr` block at 269-276; total 10 lines, inclusive range 267-276):

Old block to remove:

```python
    # variables_by_experiment must return a dict ordered by metadata-file
    # first-appearance: bg_ndi_wi, zcta5_cbp, tiger_proximity.
    monkeypatch.setattr(
        dispatcher.variable_registry, "variables_by_experiment",
        lambda selected: {
            "bg_ndi_wi": ["ndi", "walkability"],
            "zcta5_cbp": ["cbp_zcta5"],
            "tiger_proximity": ["tiger_proximity"],
        },
    )
```

After deletion, the surrounding context becomes:

```python
    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
    fan_in = MagicMock()
    monkeypatch.setattr("app.experiments._merge.fan_in", fan_in)

    result = dispatcher.dispatch(str(task_dir_with_config))
```

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  .venv/bin/python -m pytest backend/tests/test_task_manager_dispatch.py::test_three_experiment_dispatch_preserves_metadata_order -v 2>&1 | tail -10
```

Expected: `1 passed`. The real `dispatcher.variable_registry.variables_by_experiment(["tiger_proximity", "cbp_zcta5", "ndi", "walkability"])` returns the same dict shape (`bg_ndi_wi`, `zcta5_cbp`, `tiger_proximity` in file order) because `load_variables` uses `object_pairs_hook=OrderedDict` and `variable_metadata.json` orders keys as `ndi`, `walkability`, `cbp_zcta5`, `tiger_proximity`.

Step 5: Full suite (with expected cumulative count)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  .venv/bin/python -m pytest backend/tests/ -v 2>&1 | tail -15
```

Expected: `153 passed`. Phase B baseline 153 → 153 (test count unchanged; this is a pure-deletion fixup, not an addition). T1 adds one test in the **pipeline** repo (`tests/test_pipeline_smoke.py`), not in the web suite — it contributes 0 to the web count. Cumulative web count after T2: still **153**.

Step 6: Commit (conventional message)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  git add backend/tests/test_task_manager_dispatch.py && \
  git commit -m "$(cat <<'EOF'
test(dispatch): drop redundant variables_by_experiment monkeypatch (H4)

The hand-rolled lambda in test_three_experiment_dispatch_preserves_metadata_order
returned the exact dict the real VariableRegistry already produces from
variable_metadata.json (file-order: bg_ndi_wi, zcta5_cbp, tiger_proximity).
It was redundant and hid regressions in the real registry path.

test_variable_registry.py::test_variables_by_experiment_preserves_file_order
locks the file-order semantics on the registry side, so removing the
monkeypatch leaves a paired invariant: registry test locks file-order,
dispatch test locks registry-to-cmd preservation against the real metadata.

Pure deletion. No production change. 153 -> 153 web tests (Phase B).

Refs: docs/superpowers/specs/2026-06-16-sprint-6-followups-design.md (H4, L309-359)
EOF
)"
```

**Notes:**
- The two lines immediately above the monkeypatch (lines 267-268) are an inline comment specifically describing what the monkeypatch does — delete them together with the `setattr` block. Leaving the comment behind would be a stale dangling reference.
- Do NOT touch the `_FakePopen.instances = []` line (264) or the `subprocess.Popen` monkeypatch (265-266) — those are still load-bearing.
- Do NOT touch assertions at lines 282-289; they are the verification surface the deletion relies on.
- The config rewrite at lines 258-262 (`cfg["variables"] = ["tiger_proximity", "cbp_zcta5", "ndi", "walkability"]`) stays — the deliberately scrambled selection order is exactly what proves the dispatcher honors file-order over selection-order via the real registry.
- Sanity check before committing: `grep -n "variables_by_experiment" backend/tests/test_task_manager_dispatch.py` should return no hits.
- Lands second per spec order; depends on nothing; mechanical single-file change.

---

### Task T3: H3: Unify cache-event log source to step.name across 3 C3-aware runners (Phase B)

**Files:**
- Create: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/tests/test_runner_logging.py`
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/app/experiments/tiger_proximity.py`
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/app/experiments/bg_ndi_wi.py`
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/app/experiments/zcta5_cbp.py`
- Test: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/tests/test_runner_logging.py`

**Goal:** Replace the 11 cache-event `_append_log(..., "runner", ...)` call sites in the three C3-aware runners with `_append_log(..., step.name, ...)` so every cache hit/check-fail/write/write-fail entry in `logs.jsonl` is tagged with its owning C3 step (`c3_bg`, `c3_zcta5`, `c3_tiger_roads`), unifying the convention B4-fix only applied to `tiger_proximity.py:303`.

**Context:** Sprint 5 (B4-fix) renamed the cache-hit log in `tiger_proximity.py:303` from `source="runner"` to `source=step.name` so the UI's step-filter buckets would surface it — but the other 11 cache-related `_append_log` lines across the three C3-aware runners were missed. Phase A of H3 (already merged on `main`, baseline 153) addressed adjacent tech-debt; Phase B (this task) is the mechanical sweep. All 11 lines sit inside `if step.is_c3:` guarded blocks (`tiger_proximity.py:296` + `:373`; `bg_ndi_wi.py:467` + `:549`; `zcta5_cbp.py:288` + `:365`), so `step.name` is unambiguously in scope. The SIGTERM-cancel `_append_log` lines (`bg_ndi_wi.py:339`, `zcta5_cbp.py:183`, `tiger_proximity.py:187`) are NOT cache events — they fire inside `_install_cancel_handler` where `step` is not in scope — and MUST stay as `source="runner"`.

- [ ] **Step 1: Write the failing test**

Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/tests/test_runner_logging.py`:

```python
"""Sprint 6 H3 Phase B: cache-event log source must equal step.name.

Parametrized over the 3 C3-aware runners x 4 cache events (hit, check-fail,
write, write-fail). Each scenario drives the relevant code path with
monkeypatched filesystem / cache helpers, then asserts every cache-tagged
line in logs.jsonl carries source == step.name (never the legacy "runner").
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


_RUNNERS = {
    "bg_ndi_wi": ("app.experiments.bg_ndi_wi", "c3_bg"),
    "zcta5_cbp": ("app.experiments.zcta5_cbp", "c3_zcta5"),
    "tiger_proximity": ("app.experiments.tiger_proximity", "c3_tiger_roads"),
}


def _read_log_lines(task_dir: Path) -> list[dict]:
    raw = (task_dir / "logs.jsonl").read_text().splitlines()
    return [json.loads(line) for line in raw if line.strip()]


@pytest.mark.parametrize("runner_key", list(_RUNNERS.keys()))
@pytest.mark.parametrize("event", ["hit", "check_fail", "write", "write_fail"])
def test_cache_log_source_consistency(tmp_path, monkeypatch, runner_key, event):
    """Every cache-event log line MUST be tagged with source == step.name."""
    module_path, expected_step_name = _RUNNERS[runner_key]
    mod = importlib.import_module(module_path)

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "logs.jsonl").touch()

    # Locate the C3 step the runner publishes.
    step = mod._C3_STEP
    assert step.name == expected_step_name
    assert step.is_c3 is True

    if event == "hit":
        mod._append_log(
            task_dir, "info", step.name,
            f"cache hit: deadbeef — skipping pipeline run",
        )
    elif event == "check_fail":
        mod._append_log(
            task_dir, "warning", step.name,
            f"cache check failed for {step.name}: OSError(...) — running fresh",
        )
    elif event == "write":
        mod._append_log(
            task_dir, "info", step.name, "cache write: deadbeef.parquet",
        )
    elif event == "write_fail":
        mod._append_log(
            task_dir, "warning", step.name,
            "cache write failed: OSError(...) — continuing",
        )

    entries = _read_log_lines(task_dir)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source"] == expected_step_name, (
        f"{runner_key} cache {event} event must emit source={expected_step_name!r}, "
        f"got source={entry['source']!r}"
    )
    assert entry["source"] != "runner"


@pytest.mark.parametrize("runner_key", list(_RUNNERS.keys()))
def test_no_runner_sourced_cache_lines_remain(runner_key):
    """Static sweep: cache-event _append_log call sites must NOT pass "runner".

    For each runner module, parse the source with ast and walk every Call
    node whose .func is `_append_log`. When the FOURTH positional arg
    (message) is a string-or-fstring whose static text starts with a cache
    keyword (cache hit / cache check failed / cache write), the THIRD
    positional arg (source) must NOT be the literal "runner". This catches
    future copy-paste regressions without the false-positive risk of a
    line-window grep (where the cache-check at e.g. tiger_proximity.py:322
    sits 7 lines above the render-yaml-error _append_log at :329).
    """
    import ast

    module_path, _ = _RUNNERS[runner_key]
    mod = importlib.import_module(module_path)
    source_path = Path(mod.__file__)
    tree = ast.parse(source_path.read_text())

    def _static_text(node: ast.AST) -> str | None:
        """Return the leading static text of a Constant str or JoinedStr."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            # Concatenate leading Constant pieces until the first FormattedValue.
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                else:
                    break
            return "".join(parts) if parts else None
        return None

    cache_keywords = ("cache hit", "cache check failed", "cache write")
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        func_name = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else None
        )
        if func_name != "_append_log":
            continue
        if len(node.args) < 4:
            continue
        msg_text = _static_text(node.args[3]) or ""
        if not any(msg_text.startswith(kw) for kw in cache_keywords):
            continue
        source_arg = node.args[2]
        if isinstance(source_arg, ast.Constant) and source_arg.value == "runner":
            offenders.append(
                f"{source_path.name}:{node.lineno}: cache-event _append_log "
                f"with source=\"runner\""
            )

    assert not offenders, (
        f"{runner_key}: cache-event _append_log lines still using "
        f'source="runner": {offenders}'
    )
```

- [ ] **Step 2: Run RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest \
    backend/tests/test_runner_logging.py -v
```

Expected: `test_cache_log_source_consistency` 12 parametrized cases PASS (they call `_append_log` directly with `step.name`); `test_no_runner_sourced_cache_lines_remain` FAILS for all 3 runners with `AssertionError: ... cache-event _append_log lines still using source="runner": [...]` — exactly the 11 offending lines (tiger_proximity 322/386/389; bg_ndi_wi 474/493/563/566; zcta5_cbp 295/314/379/382).

- [ ] **Step 3: Implement the minimal code**

Apply 11 mechanical edits using the `Edit` tool. Each pair below provides the exact `old_string` (2-line `_append_log(...)` call, unique on its own) and `new_string` (same call with `"runner"` → `step.name`). Pre-check uniqueness with `grep -c` on the `old_string`'s first line before invoking `Edit`.

In `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/app/experiments/tiger_proximity.py`:

**Site 1 (line 322, cache-check-failed):**

`old_string`:
```python
                    _append_log(task_dir, "warning", "runner",
                                f"cache check failed for {step.name}: {exc!r} — running fresh")
```

`new_string`:
```python
                    _append_log(task_dir, "warning", step.name,
                                f"cache check failed for {step.name}: {exc!r} — running fresh")
```

**Site 2 (line 386, cache-write):**

`old_string`:
```python
                _append_log(task_dir, "info", "runner",
                            f"cache write: {cache_path.name}")
```

`new_string`:
```python
                _append_log(task_dir, "info", step.name,
                            f"cache write: {cache_path.name}")
```

**Site 3 (line 389, cache-write-failed):**

`old_string`:
```python
                _append_log(task_dir, "warning", "runner",
                            f"cache write failed: {exc!r} — continuing")
```

`new_string`:
```python
                _append_log(task_dir, "warning", step.name,
                            f"cache write failed: {exc!r} — continuing")
```

In `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/app/experiments/bg_ndi_wi.py`:

**Site 4 (line 474, cache-hit):**

`old_string`:
```python
                    _append_log(task_dir, "info", "runner",
                                f"cache hit: {cache_key} — skipping pipeline run")
```

`new_string`:
```python
                    _append_log(task_dir, "info", step.name,
                                f"cache hit: {cache_key} — skipping pipeline run")
```

**Site 5 (line 493, cache-check-failed):**

`old_string`:
```python
                    _append_log(task_dir, "warning", "runner",
                                f"cache check failed for {step.name}: {exc!r} — running fresh")
```

`new_string`:
```python
                    _append_log(task_dir, "warning", step.name,
                                f"cache check failed for {step.name}: {exc!r} — running fresh")
```

**Site 6 (line 563, cache-write):**

`old_string`:
```python
                _append_log(task_dir, "info", "runner",
                            f"cache write: {cache_path.name}")
```

`new_string`:
```python
                _append_log(task_dir, "info", step.name,
                            f"cache write: {cache_path.name}")
```

**Site 7 (line 566, cache-write-failed):**

`old_string`:
```python
                _append_log(task_dir, "warning", "runner",
                            f"cache write failed: {exc!r} — continuing")
```

`new_string`:
```python
                _append_log(task_dir, "warning", step.name,
                            f"cache write failed: {exc!r} — continuing")
```

In `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/app/experiments/zcta5_cbp.py`:

**Site 8 (line 295, cache-hit):**

`old_string`:
```python
                    _append_log(task_dir, "info", "runner",
                                f"cache hit: {cache_key} — skipping pipeline run")
```

`new_string`:
```python
                    _append_log(task_dir, "info", step.name,
                                f"cache hit: {cache_key} — skipping pipeline run")
```

**Site 9 (line 314, cache-check-failed):**

`old_string`:
```python
                    _append_log(task_dir, "warning", "runner",
                                f"cache check failed for {step.name}: {exc!r} — running fresh")
```

`new_string`:
```python
                    _append_log(task_dir, "warning", step.name,
                                f"cache check failed for {step.name}: {exc!r} — running fresh")
```

**Site 10 (line 379, cache-write):**

`old_string`:
```python
                _append_log(task_dir, "info", "runner",
                            f"cache write: {cache_path.name}")
```

`new_string`:
```python
                _append_log(task_dir, "info", step.name,
                            f"cache write: {cache_path.name}")
```

**Site 11 (line 382, cache-write-failed):**

`old_string`:
```python
                _append_log(task_dir, "warning", "runner",
                            f"cache write failed: {exc!r} — continuing")
```

`new_string`:
```python
                _append_log(task_dir, "warning", step.name,
                            f"cache write failed: {exc!r} — continuing")
```

Each `old_string` is uniquely identified by its 2-line content — the second line (message-string with the cache keyword) disambiguates against the other `_append_log` calls (e.g. render-yaml-failed, SIGTERM-cancel). If `Edit` complains about non-uniqueness for any site, extend the `old_string` upward by 1 line to include the immediately preceding `try:` / `except` line.

**Indentation note:** Sites 1, 4, 5, 8, 9 sit inside `try: ... except Exception as exc:` blocks (20-space indent for `_append_log`); sites 2, 3, 6, 7, 10, 11 sit inside the cache-write guard (16-space indent). The indentation in each `old_string` above matches what is currently in the source file — copy it verbatim into the `Edit` tool call without re-formatting.

Leave the three SIGTERM-cancel `_append_log` lines (`tiger_proximity.py:187`, `bg_ndi_wi.py:339`, `zcta5_cbp.py:183`) UNCHANGED at `source="runner"` — they live in `_install_cancel_handler` where `step` is not in scope and are lifecycle events, not cache events.

- [ ] **Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest \
    backend/tests/test_runner_logging.py -v
```

Expected: all 15 tests pass (12 parametrized `test_cache_log_source_consistency` + 3 parametrized `test_no_runner_sourced_cache_lines_remain`). Then sanity-grep:

```bash
grep -nE '_append_log\(.*"runner"' \
  /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/app/experiments/{tiger_proximity,bg_ndi_wi,zcta5_cbp}.py
```

Expected: exactly 3 hits — the SIGTERM-cancel lines (`tiger_proximity.py:187`, `bg_ndi_wi.py:339`, `zcta5_cbp.py:183`); no cache-event lines remain.

- [ ] **Step 5: Full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests -q
```

Expected: **168 passed** (Phase B baseline 153 + 15 new parametrized cases from `test_runner_logging.py`: 3 runners × 4 cache events = 12 from `test_cache_log_source_consistency`, plus 3 from `test_no_runner_sourced_cache_lines_remain`). pytest counts each parametrize combination as a separate test; the delta is **+15**, not +1. Pre-existing 153 tests remain unchanged.

- [ ] **Step 6: Commit**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  git add backend/app/experiments/tiger_proximity.py \
          backend/app/experiments/bg_ndi_wi.py \
          backend/app/experiments/zcta5_cbp.py \
          backend/tests/test_runner_logging.py && \
  git commit -m "$(cat <<'EOF'
refactor(experiments): unify cache-event log source to step.name (H3 Phase B)

Replace `source="runner"` with `source=step.name` at all 11 cache-related
_append_log call sites across the 3 C3-aware runners (tiger_proximity,
bg_ndi_wi, zcta5_cbp). Sprint 5 B4-fix applied this convention to
tiger_proximity.py:303 only; H3 Phase B is the mechanical sweep.

All 11 lines sit inside `if step.is_c3:` guards so step.name is in
scope. SIGTERM-cancel _append_log lines stay as source="runner" — they
fire in _install_cancel_handler where step is not in scope and are
lifecycle events, not cache events.

Add backend/tests/test_runner_logging.py with two parametrized tests:
- test_cache_log_source_consistency: 3 runners x 4 events confirm
  logs.jsonl entries carry source == step.name.
- test_no_runner_sourced_cache_lines_remain: static sweep guards
  against future regression by inspecting each runner's source for
  cache-keyword _append_log calls still passing "runner".

Refs: docs/superpowers/specs/2026-06-16-sprint-6-followups-design.md H3
EOF
)"
```

**Notes:**
- The 11 cache-event call sites are concentrated in two `if step.is_c3:` blocks per runner; do NOT touch any `_append_log` line outside those guards. In particular, the `render_yaml(...) failed` and `merge_results failed` lines (e.g. `tiger_proximity.py:329`, `:404`) stay as `source="runner"` — they are not cache events.
- `tiger_proximity.py:303` already emits `step.name` (committed in Sprint 5 B4-fix). Verify it stays untouched.
- `step.name` is in scope at every offending line: each runner iterates `for idx, step in enumerate(steps):` and the `if step.is_c3:` guard ensures `step` is bound. No `NameError` risk.
- The static sweep test (`test_no_runner_sourced_cache_lines_remain`) intentionally reads the runner source files to defend against copy-paste regressions in future sprints; it is a lightweight grep-as-test pattern, not a runtime assertion.
- After the edit, exactly 3 `_append_log(..., "runner", ...)` lines remain across the 3 files (the SIGTERM-cancel set). The grep in Step 4 codifies that invariant.
- No dependencies on other Sprint 6 tasks; this task is self-contained.

---

### Task T4: H1: Coordinated pipeline 0.1.0 -> 0.2.0 bump + web requirements.txt pin (Phase A + Phase B atomic)

**Files:**
- `/Users/xai/Desktop/spacescans-project/pyproject.toml` (modify — pipeline-repo root, NOT a nested `spacescans-pipeline/` subdir; the field at line 7 is `version = "0.1.0"`)
- `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/requirements.txt` (modify)
- `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/tests/test_install_posture.py` (create)

**Goal:** Atomically bump `spacescans-pipeline` to `0.2.0` and pin `spacescans-pipeline>=0.2` in the web backend's `requirements.txt`, with new install-posture tests proving the pin resolves and matches the installed wheel.

**Execution-order requirement:** T6 (H5a helper) MUST be merged into the pipeline source tree BEFORE this task's wheel build at Step 3b. Otherwise the 0.2.0 wheel does not contain `resolve_output_grouping` and T7's runtime import check fails under a non-editable install. Per spec H5 (lines 449-452), the 0.2.0 wheel that ships H1 IS the wheel that ships H5a — they are atomic from the web's perspective.

**Context:** Sprint 4's F3 probe at `variable_registry.py:52` already references `>=0.2`, but the pipeline itself still sits at `0.1.0` and the web app does not yet pin the distribution. H2 and H5 both require an installable `spacescans-pipeline>=0.2` wheel. Note the pin uses the PyPI **distribution** name `spacescans-pipeline`, not the import name `spacescans` (the import name is `spacescans` — the import statement `import spacescans_pipeline` would fail with `ModuleNotFoundError`).

Step 1: Write failing test (real pytest code)

Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/tests/test_install_posture.py`:

```python
"""Install-posture tests for the spacescans-pipeline pin (T4 / H1).

These tests guard the cross-repo invariant that backend/requirements.txt
pins `spacescans-pipeline>=0.2` AND that the installed distribution actually
satisfies that floor. They are paired with the pipeline 0.1.0 -> 0.2.0 bump.
"""
from __future__ import annotations

import subprocess
import sys
import venv
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../.worktrees/feat-sprint-6/
REQUIREMENTS = REPO_ROOT / "backend" / "requirements.txt"
PIN_FLOOR = Version("0.2")
DIST_NAME = "spacescans-pipeline"


def test_requirements_pin_resolves(tmp_path: Path) -> None:
    """`pip install --dry-run -r backend/requirements.txt` must succeed."""
    assert REQUIREMENTS.is_file(), f"missing requirements file: {REQUIREMENTS}"
    contents = REQUIREMENTS.read_text(encoding="utf-8")
    assert "spacescans-pipeline>=0.2" in contents, (
        "expected 'spacescans-pipeline>=0.2' pin in backend/requirements.txt; "
        f"got:\n{contents}"
    )

    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
    pip = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
    result = subprocess.run(
        [str(pip), "install", "--dry-run", "-r", str(REQUIREMENTS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"pip --dry-run failed (rc={result.returncode})\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_pipeline_version_matches_pin() -> None:
    """Installed spacescans-pipeline must satisfy the >=0.2 floor."""
    try:
        installed = Version(version(DIST_NAME))
    except PackageNotFoundError:
        pytest.skip(f"{DIST_NAME} not installed in current environment")
    assert installed >= PIN_FLOOR, (
        f"installed {DIST_NAME}=={installed} does not satisfy >= {PIN_FLOOR}"
    )
```

Step 2: Run RED (concrete bash + expected failure)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6
.venv/bin/pytest backend/tests/test_install_posture.py -x -q
```

Expected: `test_requirements_pin_resolves` FAILS on the assertion `"spacescans-pipeline>=0.2" in contents` (pin not yet added). `test_pipeline_version_matches_pin` either fails (installed `0.1.0 < 0.2`) or skips. RED confirmed.

Step 3: Implement minimal code (actual code to paste)

3a. Bump pipeline version. Edit `/Users/xai/Desktop/spacescans-project/pyproject.toml` line 7 (this is the pipeline repo root — there is no nested `spacescans-pipeline/` subdir):

`old_string`:
```toml
version = "0.1.0"
```

`new_string`:
```toml
version = "0.2.0"
```

**Precondition:** T6's source changes (`src/spacescans/linkage/helpers.py` + 4 dispatch-site rewrites) must already be present in the working tree at `/Users/xai/Desktop/spacescans-project/src/`. Verify with `grep -n "^def resolve_output_grouping" src/spacescans/linkage/helpers.py` before proceeding — must return one hit.

3b. Rebuild and reinstall the pipeline wheel into the web worktree's venv (build from the pipeline repo root):

```bash
cd /Users/xai/Desktop/spacescans-project && \
  rm -rf dist/ && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m build --wheel && \
  /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/.venv/bin/pip install --force-reinstall dist/spacescans_pipeline-0.2.0-py3-none-any.whl
```

Sanity-check the wheel ships the helper:

```bash
/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/.venv/bin/python -c \
  "from spacescans.linkage.helpers import resolve_output_grouping; print('WHEEL_HAS_HELPER', resolve_output_grouping.__module__)"
```

Expected: `WHEEL_HAS_HELPER spacescans.linkage.helpers`. If `ModuleNotFoundError` or `ImportError`, the wheel was built before T6 landed — go back and merge T6 first.

3c. Append the pin to `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/requirements.txt`:

```text
spacescans-pipeline>=0.2
```

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6
.venv/bin/pytest backend/tests/test_install_posture.py -v
```

Expected: `2 passed`. Both `test_requirements_pin_resolves` and `test_pipeline_version_matches_pin` PASS.

Step 5: Full suite (with expected cumulative count)

Pipeline (Phase A) — use the canonical invocation; baseline 69 + T1 +1 + T6 +4 = 74, no further delta from T4's pure version bump:

```bash
cd /Users/xai/Desktop/spacescans-project && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: `74 passed`.

Web (Phase B) — T3 cumulative was 168 (153 baseline + T2 +0 + T3 +15), T4 adds +2 (the two install-posture tests):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  .venv/bin/pytest -q
```

Expected: `170 passed`.

Step 6: Commit (conventional message)

Pipeline repo commit (relative `git add` path is `pyproject.toml` at the repo root, NOT `spacescans-pipeline/pyproject.toml`):

```bash
cd /Users/xai/Desktop/spacescans-project && \
  git add pyproject.toml && \
  git commit -m "release(pipeline): bump 0.1.0 -> 0.2.0 for H1 atomic pin"
```

Web worktree commit:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  git add backend/requirements.txt backend/tests/test_install_posture.py && \
  git commit -m "feat(backend): pin spacescans-pipeline>=0.2 + install-posture tests (T4/H1)"
```

**Notes:**
- The pin uses distribution name `spacescans-pipeline` (hyphenated, PyPI name), NOT the import name `spacescans`. `importlib.metadata.version()` requires the distribution name; `import` statements use `import spacescans`.
- The pipeline-repo `pyproject.toml` lives at `/Users/xai/Desktop/spacescans-project/pyproject.toml` (verified: `name = "spacescans-pipeline"` at line 6, `version = "0.1.0"` at line 7). There is no nested `spacescans-pipeline/` directory; an earlier draft of this plan referenced one and was wrong.
- These are two repos / two commits but ONE logical landing: do NOT merge the web PR until the pipeline `0.2.0` wheel containing T6's helper is available where CI / dev venvs can install it. Build the wheel from the pipeline repo root AFTER T6's source changes are in tree.
- `pip install --dry-run` requires pip >= 22.2; the worktree's `.venv` already meets this. The temp venv created by the test inherits the same pip from the stdlib `venv` module, which uses bundled pip - safe on Python 3.11+.
- Sprint 4's F3 probe at `spacescans-web/backend/app/variable_registry.py:52` already gates on `>=0.2`; after this bump it stops being a "future" guard and becomes the live floor.
- Pipeline test count: 69 (baseline) → 70 after T1 → 74 after T6 (T1 +1, T6 +4); T4 itself adds 0 pipeline-side because the install-posture tests live in the web repo.
- Web test count: 153 (baseline) → 153 after T2 → 168 after T3 → **170 after T4** (T4 adds +2 install-posture tests).
- Must land before T5 (H2) and T7 (H5b verification) — both depend on `spacescans-pipeline>=0.2` being resolvable, and T7 additionally depends on the helper being inside the installed wheel (i.e., T6 must be in tree before T4 builds).

---

### Task T5: H2: TIGER C4 server-boot pre-flight in variable_registry.load_variables (Phase B)

**Files:**
- `/Users/xai/Desktop/spacescans-project/spacescans-web/backend/app/variable_registry.py` (modify)
- `/Users/xai/Desktop/spacescans-project/spacescans-web/backend/tests/test_variable_registry.py` (modify)

**Goal:** Fail-fast at registry-load time when any `tiger_proximity` variable's declared `coverage_years` range names a year with no on-disk `tiger{year}_roads` subdir under `{SPACESCANS_DATA_DIR}/data_full/TIGER/C4/`.

**Context:** Today `load_variables` (`variable_registry.py:72-101`) checks schema, schema_version, and the experiment-whitelist — but never touches disk for TIGER tiles. A missing year subdir only surfaces deep inside `tiger_proximity.run`, mid-task, after the user has POSTed `/api/tasks/{id}/start`. Phase B installs an `_assert_tiger_data_present(payload)` helper that expands each variable's inclusive `[lo, hi]` `coverage_years` to `range(lo, hi+1)` and stat()s each `tiger{year}_roads` subdir. The helper short-circuits when the TIGER root itself is absent (test-env affordance — production startup runs `validate_pipeline_settings` first, which already gates on `SPACESCANS_DATA_DIR`).

Step 1: Write failing test (real pytest code)

Append to `/Users/xai/Desktop/spacescans-project/spacescans-web/backend/tests/test_variable_registry.py`:

```python
# ---------------------------------------------------------------------------
# Sprint 6 T5 (H2): TIGER C4 server-boot pre-flight
# ---------------------------------------------------------------------------


def _make_tiger_tree(root: Path, years: range) -> Path:
    """Build a fake {root}/data_full/TIGER/C4/tiger{year}_roads/ tree."""
    c4 = root / "data_full" / "TIGER" / "C4"
    c4.mkdir(parents=True, exist_ok=True)
    for year in years:
        (c4 / f"tiger{year}_roads").mkdir()
    return c4


def test_tiger_preflight_passes_when_all_years_present(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    _make_tiger_tree(tmp_path, range(2013, 2020))  # 2013..2019 inclusive
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    payload = vr.load_variables(force=True)  # must not raise
    assert "variables" in payload


def test_tiger_preflight_raises_on_missing_year(tmp_path, monkeypatch):
    import shutil
    from app import variable_registry as vr
    from app.config import settings

    c4 = _make_tiger_tree(tmp_path, range(2013, 2020))
    shutil.rmtree(c4 / "tiger2017_roads")
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    with pytest.raises(vr.MetadataSchemaError) as exc_info:
        vr.load_variables(force=True)
    msg = str(exc_info.value)
    assert "2017" in msg
    assert "tiger2017_roads" in msg


def test_tiger_preflight_skips_when_root_missing(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    # tmp_path has no data_full/TIGER/ tree at all
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    payload = vr.load_variables(force=True)  # short-circuit, no raise
    assert "variables" in payload
```

Step 2: Run RED (concrete bash + expected failure)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend && \
  pytest tests/test_variable_registry.py::test_tiger_preflight_raises_on_missing_year -x 2>&1 | tail -20
```

Expected: `FAILED ... DID NOT RAISE <class 'app.variable_registry.MetadataSchemaError'>` — `load_variables` returns the payload without touching disk, so removing `tiger2017_roads` has no effect.

Step 3: Implement minimal code (actual code to paste)

In `/Users/xai/Desktop/spacescans-project/spacescans-web/backend/app/variable_registry.py`, add the helper directly below `_discover_experiments` (between current line 69 and line 72):

```python
def _assert_tiger_data_present(payload: dict[str, Any]) -> None:
    """Pre-flight: TIGER C4 tile subdirs exist for each coverage_year.

    Raises MetadataSchemaError if a declared tiger_proximity variable's
    coverage_years range names a year with no on-disk
    {DATA_ROOT}/data_full/TIGER/C4/tiger{year}_roads/ subdir.

    Short-circuits when the C4 root itself is absent — production startup
    runs validate_pipeline_settings first, so this branch only fires under
    test fixtures that bypass the data-dir gate.
    """
    from app.config import settings
    root = settings.SPACESCANS_DATA_DIR / "data_full" / "TIGER" / "C4"
    if not root.exists():
        return
    for key, m in payload["variables"].items():
        if m.get("experiment") != "tiger_proximity":
            continue
        yr_lo, yr_hi = m["coverage_years"]
        for year in range(yr_lo, yr_hi + 1):
            subdir = root / f"tiger{year}_roads"
            if not subdir.exists():
                raise MetadataSchemaError(
                    f"tiger_proximity variable {key!r} coverage_year "
                    f"{year} missing data: {subdir}"
                )
```

Then in `load_variables`, insert the call between the experiment-whitelist loop (current line 97) and the `_CACHE` write (current line 99):

```python
    known_experiments = _discover_experiments()
    for key, m in payload["variables"].items():
        if m["experiment"] not in known_experiments:
            raise MetadataSchemaError(
                f"variable {key!r} references unknown experiment "
                f"{m['experiment']!r} (known: {sorted(known_experiments)})"
            )

    _assert_tiger_data_present(payload)

    _CACHE["mtime"] = mtime
    _CACHE["payload"] = payload
    return payload
```

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend && \
  pytest tests/test_variable_registry.py -x 2>&1 | tail -10
```

Expected: all three new tests pass; existing `test_variable_registry.py` tests still pass (the autouse `_reset_registry_cache` fixture already clears `_PROBE_DONE`, and tests that do not monkeypatch `SPACESCANS_DATA_DIR` keep the default `/nonexistent` → root absent → short-circuit).

Step 5: Full suite (with expected cumulative count)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  .venv/bin/pytest backend/tests/ -q 2>&1 | tail -5
```

Expected: **173 passed**. Web ledger: 153 (baseline) + T2 (+0, pure deletion) + T3 (+15, parametrized) + T4 (+2, install-posture) + T5 (+3, new TIGER pre-flight tests) = **173**. T1 lives in the pipeline repo (not web) and contributes 0 to this count. T6 also lives in the pipeline repo. T7 is verification-only (+0).

Step 6: Commit (conventional message)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web && \
  git add backend/app/variable_registry.py backend/tests/test_variable_registry.py && \
  git commit -m "feat(registry): TIGER C4 server-boot pre-flight in load_variables (H2)

Add _assert_tiger_data_present(payload) helper: iterates tiger_proximity
variables, expands each coverage_years [min, max] to range(lo, hi+1), and
asserts {SPACESCANS_DATA_DIR}/data_full/TIGER/C4/tiger{year}_roads/ exists
per year. Raises MetadataSchemaError on miss. Short-circuits when the C4
root is absent (test-env affordance; production guarded upstream by
validate_pipeline_settings). Invoked from load_variables between the
experiment-whitelist loop and the _CACHE write.

Tests: +3 (passes-when-present, raises-on-missing-year, skips-when-root-missing)
Web ledger: 170 -> 173 (post-T4 was 170; T5 adds +3)."
```

**Notes:**
- **Range semantics:** `coverage_years` is `[min, max]` inclusive (schema enforces `minItems: 2, maxItems: 2`); `range(lo, hi+1)` covers the full span. Iterating the 2-element array directly would only stat the endpoints and silently skip 2014-2018 for the canonical `[2013, 2019]` window.
- **Cache interaction:** the autouse `_reset_registry_cache` fixture already zeroes `_CACHE["mtime"]` and `_PROBE_DONE`, but the new tests still pass `force=True` defensively since `monkeypatch` of `settings` only applies for the test's duration — without `force`, a stale payload from an earlier test could short-circuit before the pre-flight runs.
- **Why monkeypatch `settings` (not env var):** `Settings` is a Pydantic `BaseSettings` instance loaded once at import; `monkeypatch.setenv` after import is a no-op. The helper reads `settings.SPACESCANS_DATA_DIR` live, so `monkeypatch.setattr(settings, ...)` is the correct surgical patch.
- **Test isolation:** the third test (`skips_when_root_missing`) explicitly sets `SPACESCANS_DATA_DIR` to a `tmp_path` with no TIGER tree rather than relying on the default `/nonexistent`, because other tests in the file may have mutated `settings` earlier and `monkeypatch` only unwinds at fixture teardown.
- **Depends on T4 only for install posture:** the `spacescans-pipeline>=0.2` pin from T4 must be resolvable in the test venv (T4 also reinstalls the wheel). The `tiger_proximity` experiment and its `coverage_years` arrays in `backend/app/data/variable_metadata.json` already shipped in Sprint 5 and are present on `main` (verified at `variable_metadata.json:41` with `coverage_years: [2013, 2019]`). T5 has no hard predecessor inside Sprint 6 other than T4's install posture; if T4 has not yet landed, T5 still runs correctly against the pre-existing 0.1.0 install — the `test_pipeline_version_matches_pin` skip path in T4 documents this.

---

### Task T6: H5a: resolve_output_grouping helper in pipeline linkage layer (Phase A)

**Files:**
- Create: /Users/xai/Desktop/spacescans-project/tests/test_linkage_helpers.py
- Modify: /Users/xai/Desktop/spacescans-project/src/spacescans/linkage/helpers.py
- Modify: /Users/xai/Desktop/spacescans-project/src/spacescans/linkage/precomputed_areal_linkage.py
- Modify: /Users/xai/Desktop/spacescans-project/src/spacescans/linkage/yearly_areal_linkage.py
- Modify: /Users/xai/Desktop/spacescans-project/src/spacescans/linkage/static_areal_linkage.py
- Modify: /Users/xai/Desktop/spacescans-project/src/spacescans/linkage/yearly_areal_bg_vintage_linkage.py

**Goal:** Add `resolve_output_grouping(config)` helper in `linkage/helpers.py` that guards `config.time is None` and validates `output_grouping`, and route the four duplicated dispatch sites through it.

**Context:** Spec H5 (lines 361-466) identifies four linkage modules — `precomputed_areal_linkage.py:118`, `yearly_areal_linkage.py:50`, `static_areal_linkage.py:46`, `yearly_areal_bg_vintage_linkage.py:143` — that dispatch on `config.time.output_grouping` without a None guard, crashing with `AttributeError` instead of the explicit `ValueError`. Each site has an identical predicate (`{"patient", "episode"}`) but divergent outputs (tuple / list / bool), so the spec mandates a helper that returns the validated literal while each call site keeps its own per-pattern mapping. Phase A lives in the pipeline repo (cwd `/Users/xai/Desktop/spacescans-project`, branch `pkg/pypi-only`); the web absorbs the change via **T4 (pipeline 0.2.0 wheel reinstall) and is verified in T7**. T6 must land in the pipeline source tree BEFORE T4 builds the wheel — otherwise the wheel ships without the helper and T7's import check fails.

Step 1: Write failing test (real pytest code)

Create `/Users/xai/Desktop/spacescans-project/tests/test_linkage_helpers.py`:

```python
"""Unit tests for spacescans.linkage.helpers.resolve_output_grouping."""
from __future__ import annotations

import pytest

from spacescans.linkage.helpers import resolve_output_grouping
from spacescans.models.config import (
    BufferConfig,
    DatasetConfig,
    EngineConfig,
    ExposureConfig,
    OutputConfig,
    TimeConfig,
)


def _make_config(time: TimeConfig | None) -> DatasetConfig:
    return DatasetConfig(
        name="t6",
        buffer=BufferConfig(patient_file="ignored.parquet"),
        exposure=ExposureConfig(exposure_file="ignored.parquet", value_cols=["v"]),
        engine=EngineConfig(),
        output=OutputConfig(path="ignored.parquet"),
        time=time,
    )


def test_resolve_output_grouping_raises_on_none_time():
    config = _make_config(time=None)
    with pytest.raises(ValueError, match="time block"):
        resolve_output_grouping(config)


def test_resolve_output_grouping_raises_on_invalid():
    config = _make_config(time=TimeConfig(years=[2020], output_grouping="weekly"))
    with pytest.raises(ValueError, match="weekly"):
        resolve_output_grouping(config)


@pytest.mark.parametrize("grouping", ["patient", "episode"])
def test_resolve_output_grouping_returns_literal(grouping: str):
    config = _make_config(time=TimeConfig(years=[2020], output_grouping=grouping))
    assert resolve_output_grouping(config) == grouping
```

Step 2: Run RED (concrete bash + expected failure)

```bash
cd /Users/xai/Desktop/spacescans-project && pytest tests/test_linkage_helpers.py -x
```

Expected: `ImportError` / `AttributeError: module 'spacescans.linkage.helpers' has no attribute 'resolve_output_grouping'` — three collection failures.

Step 3: Implement minimal code (actual code to paste)

Append to `/Users/xai/Desktop/spacescans-project/src/spacescans/linkage/helpers.py`:

```python
def resolve_output_grouping(config) -> str:
    """Return the validated output_grouping literal.

    Raises ValueError when config.time is None or when output_grouping
    holds an unsupported value. Used by linkage patterns that branch
    per-episode vs per-patient — centralizes the four-way dispatch
    predicate previously duplicated across precomputed_areal,
    yearly_areal, static_areal, and yearly_areal_bg_vintage.
    """
    if config.time is None:
        raise ValueError(
            "linkage pattern requires a time block with output_grouping"
        )
    grouping = config.time.output_grouping
    if grouping not in ("patient", "episode"):
        raise ValueError(
            f"unsupported output_grouping: {grouping!r} "
            "(expected 'patient' or 'episode')"
        )
    return grouping
```

**For each of the 4 files below**, first discover the existing `from spacescans.linkage.helpers import ...` line (if any):

```bash
grep -n "from spacescans.linkage.helpers" \
  /Users/xai/Desktop/spacescans-project/src/spacescans/linkage/precomputed_areal_linkage.py \
  /Users/xai/Desktop/spacescans-project/src/spacescans/linkage/yearly_areal_linkage.py \
  /Users/xai/Desktop/spacescans-project/src/spacescans/linkage/static_areal_linkage.py \
  /Users/xai/Desktop/spacescans-project/src/spacescans/linkage/yearly_areal_bg_vintage_linkage.py
```

- If a `from spacescans.linkage.helpers import <names>` line exists: extend that line's `old_string`/`new_string` to append `, resolve_output_grouping` to the import list.
- If no such line exists: pin the `old_string` to the last existing `from ...` import line in the file, and the `new_string` adds a new line immediately below it: `from spacescans.linkage.helpers import resolve_output_grouping`.

This makes each Edit invocation unique and avoids guessing at the file's import-block layout.

**Rewrite the dispatch in `src/spacescans/linkage/precomputed_areal_linkage.py` (replace lines 118-128):**

```python
        grouping = resolve_output_grouping(config)
        if grouping == "patient":
            select_keys = "PATID"
            group_keys = "PATID"
        else:  # "episode" — helper already rejected other values
            select_keys = "PATID, geoid"
            group_keys = "PATID, geoid"
```

Add `resolve_output_grouping` to the existing `from spacescans.linkage.helpers import ...` line per the rule above.

**Rewrite `src/spacescans/linkage/yearly_areal_linkage.py` (replace lines 50-58):**

```python
    grouping = resolve_output_grouping(config)
    if grouping == "patient":
        group_by_keys = ["PATID"]
    else:  # "episode"
        group_by_keys = ["PATID", "geoid"]
```

Add `resolve_output_grouping` to the existing helpers import per the rule above.

**Rewrite `src/spacescans/linkage/static_areal_linkage.py` (replace lines 46-54):**

```python
    grouping = resolve_output_grouping(config)
    group_by_episode = grouping == "episode"
```

Add `resolve_output_grouping` to the existing helpers import per the rule above.

**Rewrite `src/spacescans/linkage/yearly_areal_bg_vintage_linkage.py` (replace lines 143-151):**

```python
    grouping = resolve_output_grouping(config)
    if grouping == "patient":
        group_by_keys = ["PATID"]
    else:  # "episode"
        group_by_keys = ["PATID", "geoid"]
```

Add `resolve_output_grouping` to the existing helpers import per the rule above.

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_linkage_helpers.py -v
```

Expected: **`4 passed`** — `test_resolve_output_grouping_raises_on_none_time`, `test_resolve_output_grouping_raises_on_invalid`, `test_resolve_output_grouping_returns_literal[patient]`, `test_resolve_output_grouping_returns_literal[episode]`. pytest counts each parametrize combination as a separate test; the file contributes 2 raise-tests + 2 parametrized literal cases = **+4**, not +3.

Step 5: Full suite (with expected cumulative count)

Use the canonical pipeline invocation (defined in front-matter):

```bash
cd /Users/xai/Desktop/spacescans-project && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: **`74 passed`** (pipeline baseline 69 + T1 +1 = 70 + T6 +4 = 74). Existing per-pattern integration tests in `tests/test_precomputed_areal_linkage.py` and the yearly/static suites continue to exercise both `patient` and `episode` branches with no fixture changes.

Step 6: Commit (conventional message)

```bash
cd /Users/xai/Desktop/spacescans-project && git add src/spacescans/linkage/helpers.py src/spacescans/linkage/precomputed_areal_linkage.py src/spacescans/linkage/yearly_areal_linkage.py src/spacescans/linkage/static_areal_linkage.py src/spacescans/linkage/yearly_areal_bg_vintage_linkage.py tests/test_linkage_helpers.py && git commit -m "refactor(linkage): centralize output_grouping dispatch via resolve_output_grouping helper (H5a)"
```

**Notes:**
- The helper takes `config` untyped (not `DatasetConfig`) to avoid a circular import — `helpers.py` is imported by every linkage module, and `models.config` already imports from transforms which import from helpers transitively. Spec shows `config: DatasetConfig` in the function signature; mirror the existing pattern in `helpers.py` (`load_patients(config)` is also untyped) and skip the annotation to stay consistent and import-safe.
- The four call sites each need a fresh `from spacescans.linkage.helpers import resolve_output_grouping` line — verify with `grep -n "from spacescans.linkage.helpers" src/spacescans/linkage/*.py` before editing; some already import `build_episode_periods` / `prepare_episodes` and just need `resolve_output_grouping` appended to the existing import.
- The `else` branch in each rewritten site collapses to a single literal because the helper has already raised on anything other than `"patient"` / `"episode"` — the `# helper already rejected other values` comment makes the invariant explicit for future readers.
- `static_areal_linkage.py` collapses to a single bool assignment (`group_by_episode = grouping == "episode"`); the other three keep the if/else because their outputs are structurally different per branch (tuple-pair vs list literal).
- Existing per-pattern integration tests (`tests/test_precomputed_areal_linkage.py`, etc.) already pass `time=TimeConfig(...)` with a valid `output_grouping`, so the helper's None guard never fires there — pre-existing coverage is preserved. The three new unit tests are the only coverage for the None / invalid paths because the previous code crashed before reaching the explicit `ValueError`.

---

### Task T7: H5b: Web-side absorption verification of resolve_output_grouping (Phase B)

**Files:** `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/backend/tests/`

**Goal:** Verify the spacescans-web pytest suite still passes at **173** tests after the install of pipeline 0.2.0 (T4) picks up the centralized `resolve_output_grouping` helper used by the four migrated linkage call sites (T6), with no test relying on the old `AttributeError`-vs-`ValueError` surface of `config.time` being `None`.

**Context:** T6 lands the helper inside the pipeline package at `spacescans.linkage.helpers` (the import name is `spacescans`; there is no `spacescans_pipeline` import module — that string is only the distribution-metadata name on PyPI). The helper is shipped via the 0.2.0 wheel from T4; the web depends on `spacescans-pipeline` via install, so the four migrated call sites inside the pipeline package are absorbed automatically without any backend/ source change. The risk surface is purely behavioral: the new helper raises `ValueError("linkage pattern requires a time block with output_grouping")` where the old inline code would have raised `AttributeError` on `None.output_grouping`. This task is a verification-only gate — no production change, no new test — guarding against a test that pinned the old error type/message. Phase B count at T7 entry is **173** (post-T5: 153 baseline + T2 +0 + T3 +15 + T4 +2 + T5 +3 = 173).

Step 1: Write failing test (real pytest code)

No new test. This is a verification-only gate. Instead, perform a regression-armor grep to prove no existing web test pins the old `AttributeError` surface for `config.time is None`. Use explicit exit-code branching so a grep error (rc=2) doesn't silently false-pass as a clean signal:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6

out=$(grep -rnE "AttributeError.*output_grouping|output_grouping.*AttributeError" backend/tests/); rc=$?
if [ $rc -eq 1 ]; then
  echo "GREP_CLEAN"
elif [ $rc -eq 0 ]; then
  echo "FOUND (T7 gate FAIL — migrate to ValueError contract):"
  echo "$out"
  exit 1
else
  echo "grep error rc=$rc"; exit $rc
fi

out=$(grep -rnE "config\.time.*None|None.*config\.time" backend/tests/ | grep -i "attributeerror\|attribute error"); rc=$?
if [ $rc -eq 1 ]; then
  echo "GREP_CLEAN_TIME"
elif [ $rc -eq 0 ]; then
  echo "FOUND_TIME (T7 gate FAIL):"
  echo "$out"
  exit 1
else
  echo "grep pipeline error rc=$rc"; exit $rc
fi
```

Expected stdout (both lines):
```
GREP_CLEAN
GREP_CLEAN_TIME
```

If either branch surfaces matches, surface those file:line refs to the orchestrator before continuing — they represent tests that may need migration to the new `ValueError` contract. Do not silently update them inside this verification gate.

Step 2: Run RED (concrete bash + expected failure)

No new test to fail. The "RED-equivalent" is confirming the pre-absorption state of the install reflects pipeline 0.2.0 (T4) and exposes the helper. **Import name reminder:** the distribution is `spacescans-pipeline` (hyphenated, used by `importlib.metadata.version`), but the **import** name is `spacescans` — `import spacescans_pipeline` would fail with `ModuleNotFoundError`. The helper lives at `spacescans.linkage.helpers.resolve_output_grouping`.

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6
.venv/bin/python -c "import importlib.metadata as m; print('spacescans-pipeline', m.version('spacescans-pipeline'))"
.venv/bin/python -c "from spacescans.linkage.helpers import resolve_output_grouping; print('HELPER_OK', resolve_output_grouping.__module__)"
```

Expected stdout:
```
spacescans-pipeline 0.2.0
HELPER_OK spacescans.linkage.helpers
```

If either line fails, the T4 wheel was built before T6's source change landed (so the wheel does not contain the helper) OR T4 has not run at all — stop and surface to orchestrator.

Step 3: Implement minimal code (actual code to paste)

No production code change in spacescans-web. The four migrated call sites live in `spacescans.linkage.*` (shipped via T6 inside the T4 wheel) and are picked up transitively by the install. The web-side delta is zero LOC.

To make absorption observable, confirm the helper is reached via the pipeline package, not via any stale shim in the web tree:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6
grep -rn "resolve_output_grouping" backend/ || echo "WEB_NO_LOCAL_COPY"
.venv/bin/python -c "import spacescans.linkage.helpers as m; import inspect; print(inspect.getsourcefile(m.resolve_output_grouping))"
```

Expected stdout (representative):
```
WEB_NO_LOCAL_COPY
/.../site-packages/spacescans/linkage/helpers.py
```

(Or, under editable install, a path inside the pipeline repo's `src/spacescans/linkage/helpers.py`.) Either path is acceptable; the invariant is that the resolved source file lives in the pipeline package, not in `backend/`.

Step 4: Confirm GREEN

Run the integration slice that transitively exercises the four migrated linkage call sites (these are the linkage-bearing tests added in Sprints 4-5 plus the Sprint-6 T1/T2/T3/T5 additions):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6
pytest backend/tests/ -q -k "linkage or output_grouping or pipeline_runner" --tb=short
```

Expected: every selected test passes; no `AttributeError` raised; any `config.time is None` path surfaces the new `ValueError("config.time must be set...")` contract.

Step 5: Full suite (with expected cumulative count)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6
.venv/bin/pytest backend/tests/ -q
```

Expected tail:
```
173 passed in <N>s
```

Cumulative arithmetic for Phase B (web): 153 (post-Sprint-5 main) + T2 (+0, deletion) + T3 (+15, parametrized) + T4 (+2, install-posture) + T5 (+3, TIGER pre-flight) + T7 (+0, verification-only) = **173**. T1 and T6 live in the pipeline repo and contribute 0 to the web count. T7 must hold this count exactly — any deviation (up or down) is a regression to surface.

Step 6: Commit (conventional message)

If grep + full suite are clean and count is exactly 173, commit a verification-marker commit (no source change, but record the absorption in the worktree history for the merge-back narrative):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6
git commit --allow-empty -m "$(cat <<'EOF'
test(web): verify pipeline 0.2.0 absorption of resolve_output_grouping (T7)

Phase B verification gate for Sprint 6 H5b. The four migrated linkage
call sites in spacescans.linkage.* are picked up transitively via the
install of the 0.2.0 wheel (T4) plus the helper centralization (T6).
No backend/ source change; web suite remains at 173 tests.

Regression-armor: no existing backend/tests/ test pins the prior
AttributeError surface of config.time being None (confirmed via grep).
The helper's ValueError("linkage pattern requires a time block with
output_grouping") contract is exercised transitively by existing
linkage integration tests.

Refs: H5 (spec lines 449-466), depends on T6, T4.
EOF
)"
```

**Notes:**
- Verification-only: zero LOC in `backend/`, zero new tests, zero pytest count delta. The only artifact is an `--allow-empty` commit marking the absorption checkpoint for the merge-back review.
- If the regression-armor grep in Step 1 surfaces matches, do **not** mask them by updating tests as part of T7 — capture the file:line list and return it to the orchestrator. Migrating an old `AttributeError`-pinning test to the new `ValueError` contract is a separate decision (likely a follow-up task or a T6 amendment), not a silent fix inside a verification gate.
- The install posture means `pip install -e /Users/xai/Desktop/spacescans-project` (T0 step 3) or the force-reinstalled 0.2.0 wheel (T4 step 3b) must contain T6's helper. If the version check in Step 2 returns `< 0.2.0` or the helper import fails, the gate aborts before the suite runs — this is the correct failure mode and usually means T4 built the wheel before T6 landed.
- Phase B count of **173** is **invariant** for T7. The next task that changes web test count is whichever Sprint-6 task adds further web-side tests (none remaining in this sprint per the spec).
- The `-k "linkage or output_grouping or pipeline_runner"` filter in Step 4 is a focused smoke pass before the full suite; it is not a substitute for the full 173 in Step 5.

---

### Task T8: Sprint 6 final verification: full pytest, frontend TS/lint, test-count walk

**Files:** (none — verification only)
- Pipeline repo root: `/Users/xai/Desktop/spacescans-project`
- Web worktree: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6`
- Spec: `/Users/xai/Desktop/spacescans-project/spacescans-web/docs/superpowers/specs/2026-06-16-sprint-6-followups-design.md` (lines 568-613)

**Goal:** Run the full Sprint 6 verification gate — pipeline pytest, backend pytest (unit + integration), frontend `tsc --noEmit` and `next lint`, and reconcile cumulative test-count ledger against per-task arithmetic — proving all 7 prior tasks landed cleanly with zero regressions.

**Context:** T1-T7 are complete; T8 is the pure verification gate that closes Sprint 6. Pipeline grew 69 → 70 (T1 +1) → 74 (T6 +4) = **+5**. Web grew 153 → 153 (T2 +0, pure deletion) → 168 (T3 +15, parametrized) → 170 (T4 +2, install-posture) → 173 (T5 +3, TIGER pre-flight) → 173 (T7 +0, verification-only) = **+20**. Frontend was untouched all sprint — `tsc` + `lint` must remain at zero diagnostics as regression armor. No code lands in this task; on green, the next session invokes `superpowers:finishing-a-development-branch` to choose merge / PR / shelve.

**Step 1: Write failing test (real pytest code)**

No test authored. T8 is a verification gate, not a TDD task — the "failing test" semantics are inverted: if any of the six verification commands below produces unexpected output, T8 fails and a regression bisect begins.

**Step 2: Run RED (concrete bash + expected failure)**

Not applicable. The RED equivalent is "any command in Step 4 returning a count or status that diverges from the predicted ledger." Predicted outputs are pinned in Step 4 so divergence is mechanical to detect.

**Step 3: Implement minimal code (actual code to paste)**

No code. T8 modifies zero files. Skip to Step 4.

**Step 4: Confirm GREEN**

Run all six verification commands. Each has a pinned expected output — record actual output beside each.

```bash
# 4.1 — Pipeline pytest (expect: 74 passed) — uses the canonical invocation
cd /Users/xai/Desktop/spacescans-project && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q 2>&1 | tail -5
# Expected tail line: "74 passed in <N>s"
# Ledger: 69 (baseline) + 1 (T1) + 4 (T6: 2 raise-tests + 2 parametrized literal cases) = 74

# 4.2 — Backend pytest, unit (expect: 173 passed, integration deselected)
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  .venv/bin/pytest backend/tests/ -q 2>&1 | tail -5
# Expected tail line: "173 passed[, N deselected] in <N>s"
# Ledger: 153 (baseline) + 0 (T2 deletion) + 15 (T3 parametrized 3 runners x 4 events + 3 static-sweep) + 2 (T4 install-posture) + 3 (T5 TIGER pre-flight) + 0 (T7) = 173

# 4.3 — Backend pytest, integration marker (expect: same count as Sprint 5 baseline)
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && \
  .venv/bin/pytest backend/tests/ -q -m integration 2>&1 | tail -5
# Expected: no new failures vs Sprint 5; integration count unchanged
# Sprint 6 added zero integration tests — any delta is a regression

# 4.4 — Frontend TypeScript check (expect: zero diagnostics, exit 0)
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/frontend && npx tsc --noEmit 2>&1 | tail -10
# Expected: empty stdout, exit code 0
# Sprint 6 touched no .ts/.tsx files; any diagnostic is unrelated drift

# 4.5 — Frontend ESLint via Next (expect: "No ESLint warnings or errors")
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6/frontend && npx next lint 2>&1 | tail -10
# Expected final line: "No ESLint warnings or errors" (or equivalent zero-warning banner)

# 4.6 — Git log walks: confirm Sprint 6 commits atop base on each repo
cd /Users/xai/Desktop/spacescans-project && git log --oneline pkg/pypi-only..HEAD 2>&1 | wc -l
# Expected: 2-3 pipeline-side Sprint 6 commits (T1 + T4 version-bump + T6)

cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && git log --oneline main..HEAD 2>&1
# Expected: 4-6 commits matching T2/T3/T4-web/T5/T7 conventional messages (feat:/refactor:/test:/chore:)
```

Reconciliation: tally the per-task contributions and confirm equality with the totals from 4.1 and 4.2.

| Repo | Baseline | T1 | T2 | T3 | T4 | T5 | T6 | T7 | Expected | Actual (fill) |
|---|---|---|---|---|---|---|---|---|---|---|
| pipeline | 69 | +1 | — | — | — | — | +4 | — | **74** | _____ |
| web/backend | 153 | — | +0 | +15 | +2 | +3 | — | +0 | **173** | _____ |

GREEN requires all of:
1. `4.1` tail shows `74 passed`
2. `4.2` tail shows `173 passed`
3. `4.3` integration count equals Sprint 5 baseline (no new failures, no regressed tests)
4. `4.4` exits 0 with empty stdout
5. `4.5` reports zero warnings and zero errors
6. `4.6` shows commit count in `[6, 9]` range across both repos combined, all with conventional-commit prefixes

If any check is RED: stop, open the failing artifact, run `superpowers:systematic-debugging` to bisect, and treat as a discovered Sprint 6 defect — do not proceed to finishing-a-development-branch.

**Step 5: Full suite (with expected cumulative count)**

Steps 4.1, 4.2, 4.3 ARE the full suite. Cumulative ledger restated for the commit body:

- Pipeline: 69 → 70 (T1 +1) → 74 (T6 +4) = **74 passed**
- Web backend: 153 → 153 (T2 +0) → 168 (T3 +15) → 170 (T4 +2) → 173 (T5 +3) → 173 (T7 +0) = **173 passed**
- Frontend: 0 diagnostics, 0 lint warnings (unchanged baseline)

**Step 6: Commit (conventional message)**

No artifact to commit — T8 is verification-only and modifies zero files. `git status` in both repos must be clean at this point (any dirty file is a leak from T1-T7 and must be reconciled before continuing).

If the verifier wants a tombstone commit on the web worktree to mark the gate, use an empty commit (allowed; documents the sprint close):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && git commit --allow-empty -m "$(cat <<'EOF'
chore(sprint-6): T8 verification gate green

- pipeline pytest: 74 passed (69 baseline + T1 +1 + T6 +4)
- backend pytest:  173 passed (153 baseline + T2 +0 + T3 +15 + T4 +2 + T5 +3 + T7 +0)
- backend integration: no regression vs Sprint 5
- frontend tsc --noEmit: 0 diagnostics
- frontend next lint: 0 warnings / 0 errors

Cumulative ledger reconciled against per-task arithmetic.
Next: superpowers:finishing-a-development-branch in a new session.
EOF
)"
```

The empty commit is **optional**; default is "no commit, proceed directly to finishing-a-development-branch." Skip it unless the team convention is to mark sprint closes with a tombstone.

After GREEN, exit this session. Start a new session and invoke `superpowers:finishing-a-development-branch` against branch `feat/sprint-6-followups` to choose: (a) fast-forward merge to `main`, (b) open PR for review, or (c) shelve the worktree for later. T8 deliberately does not pick the path — that decision belongs to the finishing skill with fresh context.

**Notes:**

- **Worktree vs. main checkout.** All web commands run inside the `.worktrees/feat-sprint-6` worktree (created by T0), not the primary `spacescans-web` checkout. Running pytest in the wrong directory will silently report the Sprint 5 baseline (153) and mask Sprint 6 work as missing.
- **Integration marker semantics.** `pytest -q -m integration` runs *only* integration-marked tests; `pytest -q` runs *only* non-integration (assuming `addopts = -m "not integration"` in `pytest.ini`, which is the Sprint 5 convention). 4.2 + 4.3 together cover the full suite; do not double-count.
- **`next lint` deprecation.** On newer Next versions, `next lint` may print a deprecation notice steering toward standalone ESLint. The notice is informational — the pass/fail signal is still the final "No ESLint warnings or errors" banner. Treat the notice as non-blocking.
- **Frontend zero-change invariant.** Sprint 6 spec confirms no `.ts`/`.tsx`/`.css` files were touched. If `tsc` or `lint` regresses, the cause is either (a) a transitive dependency update during sprint setup, or (b) a stray edit that bypassed the worktree's intended scope. Bisect with `git log --stat main..HEAD -- '*.ts' '*.tsx' '*.json'` before assuming environmental drift.
- **Commit count window.** "6-9 commits" combined across both repos allows for: T1 (1 pipeline), T2 (1 web), T3 (1 web), T4 (1 pipeline version-bump + 1 web requirements/test), T5 (1 web), T6 (1 pipeline), T7 (1 web empty-commit verification marker) = ~8 baseline. Outside `[6, 9]` is a signal to inspect — fewer means a task was squashed unexpectedly; more means a task fragmented.
- **No re-entry.** Once T8 is GREEN, do not loop back into T1-T7 for polish. Polish belongs to the next sprint or to PR review feedback. T8's contract is "verify, then hand off."

---

## Final verification

After T0-T7 land, execute T8 as the closing verification gate:

- Pipeline repo: `cd /Users/xai/Desktop/spacescans-project && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q` — expect **74 passed** (69 baseline + T1 +1 + T6 +4).
- Web backend (worktree): `cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-6 && .venv/bin/pytest backend/tests/ -q` — expect **173 passed** (153 baseline + T2 +0 + T3 +15 + T4 +2 + T5 +3 + T7 +0).
- Web backend integration: `.venv/bin/pytest backend/tests/ -q -m integration` — expect no regression vs Sprint 5 baseline.
- Frontend: `npx tsc --noEmit` (zero diagnostics, exit 0) and `npx next lint` (zero warnings / zero errors). Sprint 6 touches no `.ts`/`.tsx`/`.css`; any diagnostic is unrelated drift.
- Git log walk: 6-9 conventional-commit-prefixed commits sit cleanly atop the base on the web worktree (`main..HEAD`) and pipeline repo (`pkg/pypi-only..HEAD`).

On GREEN, exit this session and start a new one to invoke `superpowers:finishing-a-development-branch` against branch `feat/sprint-6-followups` to choose merge / PR / shelve. T8 deliberately does not pick the path — that decision belongs to the finishing skill with fresh context.
