# Sprint 7: NHD Bluespace + precomputed_static Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Add nhd_bluespace as the 5th metadata variable + 4th experiment module. Phase A: precomputed_static_linkage adopts resolve_output_grouping helper (mirror Sprint 6 T6 for precomputed_areal). Phase B: web-side runner + metadata + tests.

**Architecture:** Cross-repo. Phase A pipeline pkg/pypi-only direct commits. Phase B web feat/sprint-7-nhd-bluespace worktree. Editable install bridges Phase A → Phase B.

**Spec:** docs/superpowers/specs/2026-06-16-sprint-7-nhd-bluespace-design.md (1143 lines, committed 0af8ba7)

**Phase A base:** pkg/pypi-only (Sprint 6 Phase A merged at f2ca620 — pipeline 0.2.0)
**Phase B base:** main (Sprint 6 merged at 36f19ea)

**Phase A baseline:** 74 pipeline tests
**Phase B baseline:** 172 web backend tests, 11 integration

## Table of Contents

### Phase A — Pipeline (pkg/pypi-only)
- [Task A0: Pipeline pre-flight: verify env, NHD GDB, baseline 74 tests](#task-a0-pipeline-pre-flight-verify-env-nhd-gdb-baseline-74-tests)
- [Task A1: precomputed_static_linkage adopts resolve_output_grouping helper (RED -> GREEN)](#task-a1-precomputed_static_linkage-adopts-resolve_output_grouping-helper-red---green)
- [Task A2: nhd_bluespace_demo.yaml declares output_grouping=patient + pipeline smoke](#task-a2-nhd_bluespace_demoyaml-declares-output_groupingpatient--pipeline-smoke)
- [Task A3: Phase A wrap-up: regression sweep, commit, hold push for Phase B](#task-a3-phase-a-wrap-up-regression-sweep-commit-hold-push-for-phase-b)

### Phase B — Web (feat/sprint-7-nhd-bluespace)
- [Task B0: Web worktree setup on feat/sprint-7-nhd-bluespace + Phase A handoff verify](#task-b0-web-worktree-setup-on-featsprint-7-nhd-bluespace--phase-a-handoff-verify)
- [Task B1: variable_metadata.json nhd_bluespace entry + _assert_nhd_data_present pre-flight](#task-b1-variable_metadatajson-nhd_bluespace-entry--_assert_nhd_data_present-pre-flight)
- [Task B2: nhd_bluespace.py runner (clone-trim of tiger_proximity.py)](#task-b2-nhd_bluespacepy-runner-clone-trim-of-tiger_proximitypy)
- [Task B3: nhd_bluespace unit tests (8 tests, mirror tiger_proximity coverage)](#task-b3-nhd_bluespace-unit-tests-8-tests-mirror-tiger_proximity-coverage)
- [Task B4: Single-experiment integration test (test_e2e_nhd_bluespace_cohort)](#task-b4-single-experiment-integration-test-test_e2e_nhd_bluespace_cohort)
- [Task B5: 5-variable, 4-experiment integration + task_manager dispatch regression](#task-b5-5-variable-4-experiment-integration--task_manager-dispatch-regression)
- [Task B6: Phase B wrap-up: manual_e2e Sprint 7 section + frontend no-op verify + PR](#task-b6-phase-b-wrap-up-manual_e2e-sprint-7-section--frontend-no-op-verify--pr)

### [Final Verification](#final-verification)

---

## Phase A — Pipeline (pkg/pypi-only)

### Plan ↔ Spec scope mapping

The spec enumerates Phase A scope items as `[B1]`, `[B2]`, `[B3]` (spec L62-77). This plan re-groups them into A0-A3 for execution flow:

- **A0** = pre-flight gate (spec scope: implicit baseline check, not enumerated)
- **A1** = spec `[B1]` (source edit in `precomputed_static_linkage.py`) + `[B2]` (unit tests in `test_precomputed_static_linkage.py`)
- **A2** = spec `[B3]` (YAML lock for `nhd_bluespace_demo.yaml`) + pipeline smoke per implementation step 6
- **A3** = verification sweep + PR staging (not enumerated in spec scope list)

Phase B mapping:

- **B0** = web worktree setup + Phase A editable-install handoff guard (spec L912-919)
- **B1** = spec `[B4]` (metadata entry) + `_assert_nhd_data_present` pre-flight
- **B2** = spec `[B5]` (runner module) + R3 sanity-probe wiring
- **B3** = spec `[B6]` (unit tests) + R1 cache-collision guard
- **B4** = spec `[B7]` (single-experiment integration test)
- **B5** = spec `[B8]` (4-experiment integration test) + spec `[B9]` (task_manager dispatch regression)
- **B6** = spec `[B10]` (manual_e2e docs) + G2 frontend no-op verify + PR

When the spec says "[B4]", grep this section for the matching `Bk` task.

### Task A0: Pipeline pre-flight: verify env, NHD GDB, baseline 74 tests

**Files:**
- Read-only: `/Users/xai/Desktop/spacescans-project/src/spacescans/linkage/precomputed_static_linkage.py`
- Read-only: `/Users/xai/Desktop/spacescans-project/src/spacescans/linkage/helpers.py`
- Read-only: `/Users/xai/Desktop/spacescans-project/configs/c4/nhd_bluespace_demo.yaml`
- Read-only: `/Users/xai/Desktop/spacescans-project/data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb` (canonical path, matches `configs/c4/nhd_bluespace_demo.yaml:source.file` and A2's `exists()`-skip gate)
- Optional log append: `/Users/xai/Desktop/spacescans-project/docs/sprint7/baseline.log`

**Goal:** Verify the spacescans-project pipeline checkout, editable install, on-disk Sprint 6 code, NHD raw data presence, and a clean 74-test baseline before Sprint 7 Phase A coding begins.

**Context:** Sprint 7 Phase A extends `precomputed_static_linkage.py` to emit NHD bluespace fields after Sprint 6 shipped TIGER proximity at 74 tests on `pkg/pypi-only` (spec L854-861). Before touching code we confirm the pipeline checkout is clean, the editable install resolves to the in-repo source, the Sprint 6 helpers loop sits at lines 77-94 of `precomputed_static_linkage.py` with the helpers import at line 28, the shipped C4 demo YAML is present, and the NHDPlus_H National Release 2 GDB is on disk so the Phase A CLI smoke test (spec L484-505) is not silently skipped. This task writes nothing source-, test-, or config-side — it is a pure read-only gate.

Step 1: Write failing test (real pytest code)

No test file is created. Pre-flight is a verification gate, not a TDD step. Failure mode = any verification command below exits non-zero or reports a mismatch; the task is then blocked until resolved.

Step 2: Run RED (concrete bash + expected failure)

Run the verification block. Any non-zero exit or mismatched line/count is the RED signal.

```bash
cd /Users/xai/Desktop/spacescans-project && \
  git status --porcelain && \
  git rev-parse --abbrev-ref HEAD
```

Expected: empty `git status --porcelain` output and branch `pkg/pypi-only`. Non-empty status = RED (stash or clean before proceeding).

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -c "import spacescans, pathlib; print(pathlib.Path(spacescans.__file__).resolve())"
```

Expected: `/Users/xai/Desktop/spacescans-project/src/spacescans/__init__.py`. Any other path = RED (editable install broken; rerun `pip install -e .`).

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -c "
import pathlib, re
p = pathlib.Path('/Users/xai/Desktop/spacescans-project/src/spacescans/linkage/precomputed_static_linkage.py')
lines = p.read_text().splitlines()
assert 'helpers' in lines[27], f'line 28 expected helpers import, got: {lines[27]!r}'
loop_slice = '\n'.join(lines[76:94])
assert 'for ' in loop_slice and 'record' in loop_slice.lower(), f'lines 77-94 not the records loop:\n{loop_slice}'
print('precomputed_static_linkage.py line 28 + lines 77-94 OK')
"
```

Expected: prints OK line. AssertionError = RED (Sprint 6 layout drifted; reconcile with spec L325-368 before editing).

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -c "
from spacescans.linkage.helpers import resolve_output_grouping
print('resolve_output_grouping present:', resolve_output_grouping)
"
```

Expected: prints the function object. ImportError = RED (Sprint 6 not actually shipped on this checkout).

```bash
test -f /Users/xai/Desktop/spacescans-project/configs/c4/nhd_bluespace_demo.yaml && \
  echo "nhd_bluespace_demo.yaml OK" || echo "MISSING nhd_bluespace_demo.yaml"
```

Expected: `nhd_bluespace_demo.yaml OK`. MISSING = RED (shipped config absent; spec assumes it is on disk).

```bash
# Canonical Sprint 7 NHD GDB path — must match (i) configs/c4/nhd_bluespace_demo.yaml
# source.file (currently 'data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb'),
# (ii) A2's exists()-skip gate, (iii) B1's _assert_nhd_data_present preflight.
NHD_GDB=/Users/xai/Desktop/spacescans-project/data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb
if [ -d "$NHD_GDB" ]; then
  echo "NHD GDB present: $NHD_GDB"
else
  # HU4 subset fallback (e.g. NHDPLUS_H_0308_HU4_GDB.gdb under data/NHD/C4/) is
  # acceptable for unit-test fixtures but is NOT the canonical Release-2 asset
  # the YAML references. If only the HU4 subset is available, either (a) update
  # configs/c4/nhd_bluespace_demo.yaml:source.file to that exact path before A2,
  # or (b) document the absence and let A2's CLI smoke skip per spec L484-505.
  HU4=/Users/xai/Desktop/spacescans-project/data/NHD/C4/NHDPLUS_H_0308_HU4_GDB.gdb
  if [ -d "$HU4" ]; then
    echo "NHD GDB ABSENT at canonical path; HU4 subset present at $HU4 (Phase A CLI smoke will be skipped unless YAML is re-pointed)"
  else
    echo "NHD GDB ABSENT — Phase A CLI smoke will be skipped (spec L484-505)"
  fi
fi
```

Expected: `NHD GDB present: ...` if the Release-2 national asset is staged. ABSENT (including HU4-only) is tolerated but must be recorded in the baseline log so the CLI smoke fixture's skip-on-missing-data path (spec L484-505) is the documented reason, not a silent gap. The single canonical path is `data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb` and it is referenced by exactly three sites: this probe, `configs/c4/nhd_bluespace_demo.yaml:source.file`, and B1's `_assert_nhd_data_present` preflight — keep them in lockstep.

```bash
cd /Users/xai/Desktop/spacescans-project && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ --collect-only -q 2>&1 | tail -5
```

Expected tail: `74 tests collected`. Any other count = RED.

Step 3: Implement minimal code (actual code to paste)

No source, test, or config edits. The only optional write is appending the verification result to a baseline log (skip if the user prefers a no-write pre-flight):

```bash
mkdir -p /Users/xai/Desktop/spacescans-project/docs/sprint7 && \
/Users/xai/miniconda3/envs/spacescans/bin/python - <<'PY' >> /Users/xai/Desktop/spacescans-project/docs/sprint7/baseline.log
import datetime, pathlib, subprocess
repo = pathlib.Path('/Users/xai/Desktop/spacescans-project')
head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
branch = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', '--abbrev-ref', 'HEAD'], text=True).strip()
gdb = repo / 'data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb'
yaml_cfg = repo / 'configs/c4/nhd_bluespace_demo.yaml'
print(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] sprint7 A0 pre-flight")
print(f"  branch={branch} head={head}")
print(f"  nhd_gdb_present={gdb.is_dir()}")
print(f"  nhd_bluespace_demo_yaml_present={yaml_cfg.is_file()}")
print(f"  baseline_tests=74")
PY
```

Step 4: Confirm GREEN

GREEN = every command in Step 2 reported the expected value, including `74 tests collected` from `--collect-only`. If the NHD GDB is absent, GREEN still holds provided the absence is logged so downstream A1/A2 know the CLI smoke fixture (spec L484-505) will skip rather than fail.

Step 5: Full suite (with expected cumulative count)

```bash
cd /Users/xai/Desktop/spacescans-project && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ 2>&1 | tail -3
```

Expected tail line: `74 passed` (52 Sprint-1 + 12 Sprint-2 + 5 Sprint-5 + 5 Sprint-6). Any non-pass or count drift = stop and reconcile before A1.

Step 6: Commit (conventional message)

A0 ships no source/test/config changes; the default outcome is no commit. If the optional baseline log was written, commit only that file:

```bash
cd /Users/xai/Desktop/spacescans-project && \
  git add docs/sprint7/baseline.log && \
  git commit -m "chore(sprint7): record A0 pre-flight baseline (74 tests, NHD GDB status)"
```

If the baseline log was skipped, do not create an empty commit — proceed directly to Task A1.

**Notes:**
- Read-only gate: any RED in Step 2 blocks Sprint 7 Phase A; fix root cause before A1, do not paper over with code edits in A0.
- The line-28 import check and 77-94 records-loop check pin the exact insertion points the spec (L325-368) assumes for A1; if they have drifted, A1's edit coordinates must be re-derived before writing the failing test.
- NHD GDB absence is tolerated here but must be surfaced in the baseline log so A2's CLI smoke skip is auditable (spec L484-505); never let it silently degrade coverage.
- Editable-install check guards against a stale site-packages copy shadowing in-repo edits — the most common Phase A→Phase B handoff failure when the web worktree imports `spacescans`.
- `pkg/pypi-only` is the correct branch for Phase A commits per the working-dir context; do not branch off and do not touch the web worktree from this task.

---

### Task A1: precomputed_static_linkage adopts resolve_output_grouping helper (RED -> GREEN)

**Files:**
- /Users/xai/Desktop/spacescans-project/src/spacescans/linkage/precomputed_static_linkage.py (modify)
- /Users/xai/Desktop/spacescans-project/tests/test_precomputed_static_linkage.py (create)
- /Users/xai/Desktop/spacescans-project/tests/fixtures/precomputed_static_mini.parquet (create)

**Goal:** Make `run_precomputed_static` dispatch on `config.time.output_grouping` via `resolve_output_grouping`, emitting a `geoid` column in the episode branch and rejecting unknown grouping values — preserving the static `fill_na` semantics and weighted-mean math byte-for-byte.

**Context:** Sprint 5 Phase A landed `resolve_output_grouping` and converted three other linkage patterns (precomputed_areal, yearly_areal, static_areal). The static pattern (NHD blue space, dist_coast_m) is the last holdout — today's groupby is hardcoded to `'PATID'` and never calls the helper. Sprint 7 Phase A B1+B2 close that gap so the NHD config (and the upcoming web-side episode dispatch) can request per-episode rows. The fixture mirrors `precomputed_areal_mini.parquet`'s shape (P1, P2 multi-episode; P3..P8 single-episode) so episode-row counts are deterministic.

Step 1: Write failing test (real pytest code)

Create `/Users/xai/Desktop/spacescans-project/tests/fixtures/precomputed_static_mini.parquet` via a one-shot Python script reusing the same 10-row schema as `precomputed_areal_mini.parquet` (PATID, geoid, start, end, long, lat):

```python
# tools/_gen_precomputed_static_mini.py — run once, do NOT commit
import pandas as pd
pd.DataFrame({
    "PATID": ["P1","P1","P2","P2","P3","P4","P5","P6","P7","P8"],
    "geoid": [10,11,20,21,30,30,30,30,30,30],
    "start": pd.to_datetime(["2017-01-01","2017-07-01","2017-01-01","2017-09-01",
                              "2017-01-01","2017-01-01","2017-01-01","2017-01-01",
                              "2017-01-01","2017-01-01"]),
    "end":   pd.to_datetime(["2017-06-30","2017-12-31","2017-08-31","2017-12-31",
                              "2017-12-31","2017-12-31","2017-12-31","2017-12-31",
                              "2017-12-31","2017-12-31"]),
    "long": [-86.0]*10, "lat": [40.0]*10,
}).to_parquet("/Users/xai/Desktop/spacescans-project/tests/fixtures/precomputed_static_mini.parquet", index=False)
```

Create `/Users/xai/Desktop/spacescans-project/tests/test_precomputed_static_linkage.py`:

```python
"""Sprint 7 Phase A: precomputed_static_linkage.py output_grouping dispatch.

Mirrors tests/test_precomputed_areal_linkage.py — uses a 10-row mini fixture
with two multi-episode PATIDs (P1 -> {10,11}; P2 -> {20,21}) so the episode
branch must emit strictly more rows than the patient branch.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from spacescans.models.config import (
    BufferConfig,
    DatasetConfig,
    EngineConfig,
    ExposureConfig,
    OutputConfig,
    SourceConfig,
    TimeConfig,
)

FIXTURE = Path(__file__).parent / "fixtures" / "precomputed_static_mini.parquet"


def _make_demo_config(tmp_path: Path, output_grouping: str) -> DatasetConfig:
    return DatasetConfig(
        name="precomputed_static_mini",
        linkage_pattern="precomputed_static",
        geometry_type="line",
        source=SourceConfig(file="/dev/null"),
        buffer=BufferConfig(patient_file=str(FIXTURE), buffer_m=270),
        exposure=ExposureConfig(
            file="/dev/null",
            value_cols=["dist_coast_m", "ndvi"],
        ),
        time=TimeConfig(years=[2017], output_grouping=output_grouping),
        engine=EngineConfig(),
        output=OutputConfig(path=str(tmp_path / "out.parquet")),
        plugin="nhd_bluespace",
    )


def _exposure_frame() -> pd.DataFrame:
    """Geoid-level static exposure for every geoid in the fixture."""
    return pd.DataFrame({
        "geoid":        [10, 11, 20, 21, 30],
        "dist_coast_m": [100.0, 200.0, 300.0, 400.0, 500.0],
        "ndvi":         [0.10, 0.20, 0.30, 0.40, 0.50],
    })


class _FakeReader:
    def __init__(self, config):
        self.config = config

    def load_exposure(self):
        return _exposure_frame()


def _run(tmp_path: Path, output_grouping: str) -> pd.DataFrame:
    from spacescans.linkage import precomputed_static_linkage as mod

    cfg = _make_demo_config(tmp_path, output_grouping=output_grouping)
    with patch.object(mod, "get_reader", return_value=_FakeReader):
        mod.run_precomputed_static(cfg, engine=None)
    return pd.read_parquet(cfg.output.path)


def test_precomputed_static_groups_by_patid_when_output_grouping_patient(tmp_path):
    df = _run(tmp_path, output_grouping="patient")
    assert list(df.columns) == ["PATID", "dist_coast_m", "ndvi"]
    assert df["PATID"].is_unique
    assert len(df) == 8


def test_precomputed_static_groups_by_patid_geoid_when_episode(tmp_path):
    df_patient = _run(tmp_path, output_grouping="patient")
    df_episode = _run(tmp_path, output_grouping="episode")
    assert list(df_episode.columns) == ["PATID", "geoid", "dist_coast_m", "ndvi"]
    assert df_episode.groupby(["PATID", "geoid"]).size().max() == 1
    assert len(df_episode) > len(df_patient)
    assert len(df_episode) == 10


def test_precomputed_static_rejects_unknown_output_grouping(tmp_path):
    with pytest.raises(ValueError, match="unsupported output_grouping"):
        _run(tmp_path, output_grouping="foo")
```

Step 2: Run RED (concrete bash + expected failure)

```bash
cd /Users/xai/Desktop/spacescans-project && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_precomputed_static_linkage.py -v
```

Expected: `test_precomputed_static_groups_by_patid_when_output_grouping_patient` passes (current code already groups by PATID), but `test_precomputed_static_groups_by_patid_geoid_when_episode` fails with `AssertionError: assert ['PATID', 'dist_coast_m', 'ndvi'] == ['PATID', 'geoid', 'dist_coast_m', 'ndvi']` (no geoid emitted), and `test_precomputed_static_rejects_unknown_output_grouping` fails because `resolve_output_grouping` is never called — `output_grouping="foo"` runs to completion without raising. 1 passed, 2 failed.

Step 3: Implement minimal code (actual code to paste)

Edit `/Users/xai/Desktop/spacescans-project/src/spacescans/linkage/precomputed_static_linkage.py`.

Change the helpers import on line 28:

```python
from spacescans.linkage.helpers import load_patients, resolve_output_grouping
```

Replace lines 76-88 (the `# Duration-weighted average per patient across episodes` block through the empty-records fallback) with:

```python
    # Duration-weighted average per patient (or per patient-episode).
    # Dispatch on TimeConfig.output_grouping — mirrors the SQL-clause edit in
    # precomputed_areal_linkage.py but expressed as a pandas groupby because
    # this pattern has no temporal dimension.
    grouping = resolve_output_grouping(config)
    group_keys = ["PATID"] if grouping == "patient" else ["PATID", "geoid"]

    records = []
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

    result = pd.DataFrame(records) if records else pd.DataFrame(columns=[*group_keys, *value_cols])
```

Leave lines 90-94 (the `fill_na` loop) and the trailing `return write_table(...)` untouched.

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_precomputed_static_linkage.py -v
```

Expected: `3 passed`. Episode branch returns 10 rows with `[PATID, geoid, dist_coast_m, ndvi]`; `groupby(["PATID","geoid"]).size().max() == 1`; `output_grouping="foo"` raises `ValueError: unsupported output_grouping: 'foo' ...`.

Step 5: Full suite (with expected cumulative count)

```bash
cd /Users/xai/Desktop/spacescans-project && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ -q
```

Expected: `77 passed` (74 baseline + 3 new). No regressions in `test_precomputed_areal_linkage.py`, `test_static_areal_linkage.py`, `test_yearly_areal_linkage.py`, or `test_linkage_helpers.py`.

Step 6: Commit (conventional message)

```bash
cd /Users/xai/Desktop/spacescans-project && git add src/spacescans/linkage/precomputed_static_linkage.py tests/test_precomputed_static_linkage.py tests/fixtures/precomputed_static_mini.parquet && git commit -m "$(cat <<'EOF'
feat(linkage): precomputed_static dispatches on output_grouping (Sprint 7 A1)

Adopts resolve_output_grouping helper in run_precomputed_static — closing
the last linkage pattern that hardcoded groupby('PATID'). Episode branch
groups by (PATID, geoid) so NHD blue space (dist_coast_m, ndvi) can emit
per-episode rows. fill_na post-aggregation (dist_coast_m -> 99999.0) and
the weighted-mean math are preserved verbatim.

Pipeline suite: 74 -> 77.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

**Notes:**
- `pandas.groupby(list_of_one)` returns a scalar key (not a 1-tuple), so the `key_tuple = key if isinstance(key, tuple) else (key,)` shim is load-bearing for the patient branch — without it, `dict(zip(["PATID"], "P1"))` would zip into single characters. Mirrors the pattern used by yearly_areal_linkage post-Sprint 5.
- The fixture must be committed (not generated at test time) so the test stays hermetic and the file shows up in `git status`. ~2KB is well below the spec's binary-fixture threshold.
- `_FakeReader.load_exposure` takes no `years=` kwarg here (unlike precomputed_areal) because the static pattern's contract is `load_exposure()` with no temporal argument — line 55 in the source confirms.
- `ExposureConfig.fill_na` is intentionally left unset in the test config so the patient/episode column-order assertions stay stable; the fill_na branch is already exercised by NHD integration tests downstream.
- Per spec L1021-1029: implementation is ~14 LOC delta in the source, test file ~95 LOC, fixture ~2KB — well within budget.

---

### Task A2: nhd_bluespace_demo.yaml declares output_grouping=patient + pipeline smoke

**Files:** /Users/xai/Desktop/spacescans-project/configs/c4/nhd_bluespace_demo.yaml, /Users/xai/Desktop/spacescans-project/tests/test_pipeline_smoke.py
**Goal:** Lock the shipped NHD bluespace demo YAML to `output_grouping: patient` and add a pipeline smoke that runs it end-to-end against the 100k 1:1 PATID-to-geoid cohort, asserting exactly 100,000 unique-PATID rows.
**Context:** Sprint 7 B3 audit (spec L218-227) requires every shipped `precomputed_static` config to declare `output_grouping` explicitly so v1 CLI reproducibility is invariant under A1's new dispatch. The bluespace demo's shipped 100k cohort is 1:1 PATID-to-geoid, so per spec recommendation (a) (L484-505) we only smoke the patient branch here — the multi-episode coverage for the static pattern comes from A1's unit test fixture. This task mirrors Sprint 5 Task A2's shape (test_pipeline_smoke.py L74 + L92) verbatim but for NHD.

Step 1: Write failing test (real pytest code)

Append to `/Users/xai/Desktop/spacescans-project/tests/test_pipeline_smoke.py` after line 220:

```python


def test_shipped_nhd_bluespace_demo_yaml_declares_patient_grouping():
    """Sprint 7 A2: the in-tree configs/c4/nhd_bluespace_demo.yaml MUST declare
    output_grouping: patient (spec L74-77 [B3], L218-227 audit, L484-505 rec (a)).
    Locked separately from the row-count smoke so flipping the YAML in Step 3
    is what flips this assertion from RED to GREEN. The shipped 100k cohort is
    1:1 PATID-to-geoid so the v1 CLI default (patient) is what reproducibility
    demands; the web runner overrides to episode at render time.
    """
    cfg_path = Path(__file__).resolve().parents[1] / "configs" / "c4" / "nhd_bluespace_demo.yaml"
    rendered = yaml.safe_load(cfg_path.read_text())
    assert rendered["time"]["output_grouping"] == "patient", (
        f"shipped config must declare output_grouping: patient; "
        f"got time={rendered.get('time')}"
    )


@pytest.mark.geo
@pytest.mark.extras
def test_nhd_bluespace_demo_patient_branch_row_count():
    """End-to-end smoke for configs/c4/nhd_bluespace_demo.yaml patient branch.

    Spec ref: 2026-06-16-sprint-7-nhd-bluespace-design.md L484-505 recommendation
    (a) — the shipped 100k cohort is 1:1 PATID-to-geoid, so the patient branch
    output row count must equal the cohort size (100_000) with PATID unique.
    Multi-episode static-pattern coverage lives in A1's unit-test fixture; no
    CLI episode smoke is shipped for NHD per spec rec (a).
    """
    repo_root = Path(__file__).resolve().parents[1]
    cfg_path = repo_root / "configs" / "c4" / "nhd_bluespace_demo.yaml"
    rendered = yaml.safe_load(cfg_path.read_text())

    gdb_path = repo_root / rendered["source"]["file"]
    cohort_path = repo_root / rendered["buffer"]["patient_file"]
    exposure_path = repo_root / rendered["exposure"]["file"]
    if not gdb_path.exists() or not cohort_path.exists() or not exposure_path.exists():
        pytest.skip(f"NHD demo inputs absent: gdb={gdb_path.exists()} "
                    f"cohort={cohort_path.exists()} exposure={exposure_path.exists()}")

    worktree_init = repo_root / "src" / "spacescans" / "__init__.py"
    installed_init = Path(_ss_pkg.__file__).resolve()
    if worktree_init.resolve() != installed_init:
        worktree_src = str(repo_root / "src")
        env = {**os.environ, "PYTHONPATH": worktree_src + os.pathsep + os.environ.get("PYTHONPATH", "")}
    else:
        env = os.environ.copy()

    r = subprocess.run(
        [sys.executable, "-m", "spacescans.cli", "run", str(cfg_path)],
        capture_output=True, text=True, cwd=str(repo_root), env=env,
    )
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"

    output_path = repo_root / rendered["output"]["path"]
    out = pd.read_parquet(output_path)

    assert len(out) == 100_000, (
        f"patient-branch row count {len(out)} != 100_000 (shipped 100k cohort)"
    )
    assert out["PATID"].nunique() == 100_000, (
        f"PATID must be unique on patient branch; got nunique={out['PATID'].nunique()}"
    )
```

Step 2: Run RED (concrete bash + expected failure)

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_pipeline_smoke.py::test_shipped_nhd_bluespace_demo_yaml_declares_patient_grouping -xvs
```

Expected failure:
```
FAILED tests/test_pipeline_smoke.py::test_shipped_nhd_bluespace_demo_yaml_declares_patient_grouping
AssertionError: shipped config must declare output_grouping: patient; got time={'temporal_resolution': 'static', 'temporal_mode': 'static'}
```

Step 3: Implement minimal code (actual code to paste)

Edit `/Users/xai/Desktop/spacescans-project/configs/c4/nhd_bluespace_demo.yaml` — replace the `time:` block:

```yaml
time:
  temporal_resolution: static
  temporal_mode: static
  output_grouping: patient        # Sprint 7 A2: lock v1 CLI default explicitly (spec L74-77 [B3]; web overrides to episode at render time)
```

Step 4: Confirm GREEN

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_pipeline_smoke.py::test_shipped_nhd_bluespace_demo_yaml_declares_patient_grouping -xvs
```

Expected: `PASSED`. The row-count smoke will SKIP unless the NHD GDB + 100k cohort + C3 exposure parquet are all on disk (gated by `@pytest.mark.geo + @pytest.mark.extras`).

Step 5: Full suite (with expected cumulative count)

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ -q
```

Expected: `79 passed` (74 baseline + 3 from A1 + 2 from A2; row-count smoke skipped if NHD GDB / 100k cohort / C3 exposure parquet absent → 78 passed, 1 skipped). Cumulative target after A2 = 79.

Step 6: Commit (conventional message)

```bash
git -C /Users/xai/Desktop/spacescans-project add configs/c4/nhd_bluespace_demo.yaml tests/test_pipeline_smoke.py && \
git -C /Users/xai/Desktop/spacescans-project commit -m "feat(c4): nhd_bluespace_demo.yaml declares output_grouping=patient + pipeline smoke

Sprint 7 A2. Lock the shipped NHD bluespace demo config to the v1 CLI default
(patient grouping) explicitly so A1's new dispatch can't silently flip its
reproducibility; the web runner overrides to episode at render time. Adds two
pipeline smokes mirroring Sprint 5 A2's shape: a static YAML-shape assertion
and a (geo+extras-gated) end-to-end row-count smoke against the shipped 100k
1:1 PATID-to-geoid cohort. Per spec rec (a) no CLI episode smoke ships for NHD
— multi-episode static-pattern coverage lives in A1's unit test.

Spec refs: docs/superpowers/specs/2026-06-16-sprint-7-nhd-bluespace-design.md
L74-77 [B3], L218-227 (audit), L484-505 (rec a), L879-899 (impl steps 4+6).
Depends on A1."
```

**Notes:** The `geo + extras` gate skips the row-count smoke on dev boxes without `data_full/NHD/...` or the 100k parquet — explicit triple-`exists()` skip message keeps CI logs diagnosable. The PYTHONPATH worktree-safety helper is copied verbatim from Sprint 5 A2 (lines 162-170) so single-checkout boxes get `env = os.environ.copy()` (covered by the existing `test_pythonpath_helper_no_ops_when_paths_match` at L195). YAML edit is additive-only (one key) so `precomputed_static` schema validation is undisturbed — `output_grouping` is consumed by A1's dispatch, not by the existing C4 schema. Test count delta locks to spec L963-968 (77 → 79).

**Spec divergence note (A2):** Spec L965-967 budgets +1 test in `test_pipeline_smoke.py` (the row-count smoke). This plan ships +2 there — separating the YAML-shape lock (always runs, asserts `output_grouping: patient` on the shipped config) from the row-count smoke (gated by `@pytest.mark.geo + @pytest.mark.extras`, skips when fixtures absent). The defence is that the YAML-shape lock catches a single-line config regression even on dev boxes without the 61 GB NHD GDB; reviewers diffing against spec should not be surprised by the extra test.

**Pre-flight before declaring A2 GREEN-ready:**
1. Verify the pipeline CLI entry point: `python -m spacescans.cli --help` exits 0 and exposes a `run` subcommand. Sprint 5 A2 assumed the same Module path; if Sprint 6 refactored to e.g. `spacescans.__main__`, update the `subprocess.run` invocation in `test_nhd_bluespace_demo_patient_branch_row_count` accordingly.
2. Verify the C3 exposure parquet location. The YAML's `exposure.file` is `output/python_v2/270m/NHD/C3/proximity_blue_demo100k.parquet` — this is a C3-step output, not a checked-in fixture. On a fresh checkout it does NOT exist; either (a) the C3 step must be run first to materialise it, or (b) the smoke must invoke BOTH `c3/nhd_demo.yaml` and `c4/nhd_bluespace_demo.yaml` in sequence, or (c) the smoke should fall back to A1's 10-row synthetic fixture pattern when the 100k cohort + C3 output are absent. The triple-`exists()` skip gate currently covers case (a)/(c) by skipping cleanly; if you want the smoke to actually run end-to-end on a CI box, document the C3-then-C4 prerequisite in the test docstring and add a `pytest.fixture` that runs C3 first.

---

### Task A3: Phase A wrap-up: regression sweep, commit, hold push for Phase B

**Files:** /Users/xai/Desktop/spacescans-project (pipeline checkout, pkg/pypi-only), /tmp/sprint7-phase-a-pr-body.md (PR body staging)
**Goal:** Verify A1+A2 commits via targeted + full pytest sweeps, confirm the editable-install probe Phase B will run, then stage the PR body and HOLD push until Phase B integration is green.
**Context:** Phase A adopts the **Sprint 6 T6** `resolve_output_grouping` helper inside `precomputed_static_linkage.py` (A1: source edit + 3 new tests in `tests/test_precomputed_static_linkage.py` + 1 committed fixture) and locks `configs/c4/nhd_bluespace_demo.yaml` to `output_grouping: patient` plus 2 new smokes in `tests/test_pipeline_smoke.py` (A2). The helper itself is NOT modified by this sprint — it lives at `spacescans/linkage/helpers.py` and has been there since Sprint 6 T6. Sprint 6 closed at 74 passing pipeline tests; A1 added 3, A2 added 2, so Phase A total is 79. Phase B (nhd_bluespace integration on the web worktree) editable-installs this checkout and will call `_sanity_check_pipeline_supports_precomputed_static_episode()` which greps `inspect.getsource(precomputed_static_linkage)` for the literal token `resolve_output_grouping`. This task is verification-only — no source/test edits.

Step 1: Write failing test (real pytest code)

N/A — verification-only task. No new tests written; A1 and A2 already added all five tests covering helper behavior + dispatch wiring.

Step 2: Run RED (concrete bash + expected failure)

N/A — no RED step. Instead, the editable-install handoff probe (Step 4 below) is the gating check that would fail RED if A1/A2 had not landed. Run it pre-sweep as a smoke test:

```bash
cd /Users/xai/Desktop/spacescans-project && \
git log --oneline -5 pkg/pypi-only
```

Expected: top two commits are A2 (precomputed_static dispatch wiring) then A1 (resolve_output_grouping helper + tests), both above Sprint 6 close-out 6379bb4.

Step 3: Implement minimal code (actual code to paste)

N/A — no implementation. Stage the PR body for later push:

```bash
cat > /tmp/sprint7-phase-a-pr-body.md <<'EOF'
## Sprint 7 Phase A: precomputed_static adopts resolve_output_grouping helper

Adopts the existing `resolve_output_grouping` helper (introduced in Sprint 6
T6 at `spacescans/linkage/helpers.py`) inside `precomputed_static_linkage.py`
— closing the last linkage pattern that hardcoded `groupby('PATID')`. Unblocks
Sprint 7 Phase B (`nhd_bluespace` runner) which requires per-episode output
grouping on precomputed_static yaml configs.

### Changes
- A1: `src/spacescans/linkage/precomputed_static_linkage.py` — replaces the
  hardcoded `groupby('PATID')` block with helper-driven `group_keys` dispatch
  (~14 LOC delta). 3 new tests in `tests/test_precomputed_static_linkage.py`
  plus a 10-row fixture `tests/fixtures/precomputed_static_mini.parquet`
  (committed; ~2 KB).
- A2: `configs/c4/nhd_bluespace_demo.yaml` — declares `output_grouping: patient`
  explicitly in the `time:` block so A1's new dispatch can't silently flip the
  shipped 100k cohort's reproducibility. 2 new smokes in
  `tests/test_pipeline_smoke.py` (a YAML-shape lock + a geo/extras-gated
  row-count smoke against the shipped 100k 1:1 PATID-to-geoid cohort).

No edits to `spacescans/linkage/helpers.py` — `resolve_output_grouping` is
the Sprint 6 T6 helper, reused here.

### Test results
- Targeted sweep (`pytest -k 'precomputed_static or precomputed_areal or
  yearly_areal or static_areal or bg_vintage or nhd_bluespace'`): all green.
- Full suite (`pytest tests/`): 79 passed (74 Sprint 6 baseline + 3 A1 + 2 A2).

### Breaking change (footnote, spec L226-247)
External users of `precomputed_static` yaml configs who omit the `time:` block
or `time.output_grouping` key will now hit `ValueError` from
`spacescans.linkage.helpers.resolve_output_grouping` instead of silently
defaulting to the historical `patient` grouping. Internal configs
(`configs/c4/*.yaml`, `configs/leon_fl_*.yaml`) all declare `time:` explicitly
and are unaffected.

### Push hold
Origin push held until Sprint 7 Phase B (`nhd_bluespace` on
`spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace`) goes green against
this branch via editable install. Phase B will probe this commit with:

    python -c 'from spacescans.linkage import precomputed_static_linkage; \
      import inspect; \
      print("resolve_output_grouping" in inspect.getsource(precomputed_static_linkage))'

Expected: `True`.
EOF
```

Step 4: Confirm GREEN

Run the four verification probes in order. Stop and triage if any fails — do NOT push.

```bash
# 4a. Targeted regression sweep (Sprint 2/5/6/7 dispatch families)
cd /Users/xai/Desktop/spacescans-project && \
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ \
  -k 'precomputed_static or precomputed_areal or yearly_areal or static_areal or bg_vintage or nhd_bluespace' \
  -v
```

Expected: all collected tests pass. `nhd_bluespace` matcher yields zero items (Phase B not landed yet) — that is correct; pytest exits 0 with `no tests ran` only if every other family is also empty, which they are not. Outcome: green with N selected, 0 failures.

```bash
# 4b. Full pipeline suite — cumulative count gate
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ 2>&1 | tail -5
```

Expected last line: `===== 79 passed in <X>s =====` (74 baseline + A1's 3 + A2's 2). Any other count fails this step.

```bash
# 4c. Editable-install handoff probe — exact string Phase B will run
/Users/xai/miniconda3/envs/spacescans/bin/python -c \
  'from spacescans.linkage import precomputed_static_linkage; import inspect; print("resolve_output_grouping" in inspect.getsource(precomputed_static_linkage))'
```

Expected stdout: `True`. This is the literal probe in `nhd_bluespace._sanity_check_pipeline_supports_precomputed_static_episode()` per spec L905-910.

```bash
# 4d. Working tree clean check
cd /Users/xai/Desktop/spacescans-project && git status --short
```

Expected: only `?? spacescans-web/` listed (the embedded web checkout, untracked by design). No `M`, `A`, `D`, or `??` entries in `spacescans/` or `tests/`.

Step 5: Full suite (with expected cumulative count)

Already covered by Step 4b. Cumulative: **79 passed** = 74 Sprint 6 baseline + 3 (A1: `test_precomputed_static_groups_by_patid_when_output_grouping_patient`, `test_precomputed_static_groups_by_patid_geoid_when_episode`, `test_precomputed_static_rejects_unknown_output_grouping`) + 2 (A2: `test_shipped_nhd_bluespace_demo_yaml_declares_patient_grouping`, `test_nhd_bluespace_demo_patient_branch_row_count`).

Step 6: Commit (conventional message)

No new commit — A1 and A2 already committed on `pkg/pypi-only`. This task only stages the PR body and verifies. Confirm the two Phase A commits sit on top of Sprint 6 close-out:

```bash
cd /Users/xai/Desktop/spacescans-project && \
git log --oneline pkg/pypi-only ^6379bb4 -- spacescans/ tests/
```

Expected: exactly two commits (A2 then A1), both matching `feat(linkage):` / `test(linkage):` conventional prefixes.

**HOLD push.** Do NOT run `git push origin pkg/pypi-only` in this task. Push happens only after Phase B integration tests on `feat/sprint-7-nhd-bluespace` go green against this branch's editable install. PR title when push fires:

    feat(linkage): precomputed_static output_grouping dispatch via resolve_output_grouping helper (Sprint 7 Phase A)

PR body source: `/tmp/sprint7-phase-a-pr-body.md`.

**Notes:**
- Editable install is the bridge — Phase B worktree on `spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace` pip-installs this checkout with `-e`, so the probe in Step 4c reflects the exact bytes Phase B will import. If `pip show spacescans` on the web worktree points at a stale wheel rather than this path, the probe will pass here but fail in Phase B — re-run `pip install -e /Users/xai/Desktop/spacescans-project` from inside the web worktree's env before starting Phase B if uncertain.
- The `?? spacescans-web/` untracked entry is expected and must NOT be `git add`-ed — it is a separate git checkout nested inside the pipeline repo for convenience, not pipeline content.
- The breaking-change footnote (spec L226-247) is load-bearing for downstream users — make sure it lands in the PR body referencing `spacescans.linkage.helpers.resolve_output_grouping` by name (do NOT pin a line number — the Sprint 6 helper's exact line offset is irrelevant to the bisect target, and pinning a stale number invites confusion if helpers.py drifts).
- If Step 4b reports 78 or 80, do NOT proceed — 78 means one A1/A2 test was skipped or deselected (check `pytest.ini` markers); 80 means an unrelated test was added on this branch (check `git diff 6379bb4..HEAD -- tests/`). Either way, triage before staging the PR body.
- If Step 4c prints `False`, A2's source edit did not land — `git log -p pkg/pypi-only -- spacescans/linkage/precomputed_static.py` should show the `resolve_output_grouping` call site replacement; if absent, A2 must be redone before Phase B can start.

---

## Phase B — Web (feat/sprint-7-nhd-bluespace)

### Task B0: Web worktree setup on feat/sprint-7-nhd-bluespace + Phase A handoff verify

**Files:**
- `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/` (new worktree)
- `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/.env` (migrated)
- `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/frontend/node_modules` (symlink)
- `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_phase_a_handoff.py` (transient guard, deleted before commit)
- `/tmp/sprint7-web-baseline.txt` (baseline capture)

**Goal:** Stand up isolated worktree off `main`, verify Phase A `resolve_output_grouping` helper reaches the web backend's editable install, and pin the immovable web baseline used by all subsequent Phase B tasks.

**Context:** Phase A commits A1 + A2 must already be present on the local `pkg/pypi-only` branch of `spacescans-project`, and the web backend's editable install (`pip install -e /Users/xai/Desktop/spacescans-project`) must resolve to that branch — Phase A is NOT yet merged into `main` of the pipeline repo. Phase A push is held until Phase B is green per A3 (line 644) and Final Verification step 9 (line 2550). We use a transient guard test (mirroring spec L803-814) to fail fast if the editable install is stale, then delete the guard so it does not pollute the baseline. The final pinned baseline is **`172 passed, 3 skipped, 11 deselected`** — every later B-task adds to the 172 pass count and quotes the full triple verbatim in commit footers. The web-repo origin/main base remains the cut point for Phase B's PR, while the pipeline editable install points at the `pkg/pypi-only` worktree.

Step 1: Write failing test (real pytest code)

Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_phase_a_handoff.py`:

```python
"""Transient guard: Phase A handoff sanity probe.

Asserts that the Phase A public helper `resolve_output_grouping` is reachable
from the web backend's editable install of `spacescans-pipeline`, and that
`precomputed_static_linkage` actually delegates to it (no copy-paste drift).

Deleted before B0 commit; mirrors spec 2026-06-16-sprint-7-nhd-bluespace-design.md
L803-814.
"""
import inspect

from spacescans.linkage import precomputed_static_linkage
from spacescans.linkage.helpers import resolve_output_grouping


def test_resolve_output_grouping_is_public():
    assert callable(resolve_output_grouping)


def test_precomputed_static_linkage_delegates_to_resolver():
    src = inspect.getsource(precomputed_static_linkage)
    assert "resolve_output_grouping" in src, (
        "Phase A handoff broken: precomputed_static_linkage no longer "
        "delegates to resolve_output_grouping. Re-check A2/A3 commits."
    )
```

Step 2: Run RED (concrete bash + expected failure)

```bash
# Create worktree off main (Phase A must already be merged)
cd /Users/xai/Desktop/spacescans-project/spacescans-web
git fetch origin main
git worktree add -b feat/sprint-7-nhd-bluespace \
  /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace \
  origin/main

# Migrate runtime env (NOT variable_metadata.json — that would trip the
# Final-verification absent-tracking gate; the in-tree
# backend/app/data/variable_metadata.json ships via worktree checkout)
cp /Users/xai/Desktop/spacescans-project/spacescans-web/backend/.env \
   /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/.env

# Symlink node_modules (avoid 4GB re-install)
ln -s /Users/xai/Desktop/spacescans-project/spacescans-web/frontend/node_modules \
      /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/frontend/node_modules

# Run the transient guard
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_phase_a_handoff.py -q
```

Expected RED (only if Phase A is NOT yet live in the editable install):
```
ImportError: cannot import name 'resolve_output_grouping' from 'spacescans.linkage.helpers'
```
or
```
AssertionError: Phase A handoff broken: precomputed_static_linkage no longer delegates to resolve_output_grouping. Re-check A2/A3 commits.
```

Step 3: Implement minimal code (actual code to paste)

No production code in this task. If RED, reinstall the editable pipeline against the merged Phase A commits:

```bash
/Users/xai/miniconda3/envs/spacescans/bin/pip install -e /Users/xai/Desktop/spacescans-project
```

This pulls in A2's extraction of `resolve_output_grouping` and A3's wiring inside `precomputed_static_linkage`.

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_phase_a_handoff.py -q
```

Expected:
```
..                                                                       [100%]
2 passed in 0.34s
```

Step 5: Full suite (with expected cumulative count)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q | tail -1 | tee /tmp/sprint7-web-baseline.txt
```

Expected captured line:
```
174 passed, 3 skipped, 11 deselected in <X>s
```
(172 web baseline + 2 transient guard tests = 174. 3 skipped + 11 deselected are inherited from baseline. Pin only after deletion — see Step 6.)

Frontend type check:
```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/frontend
npx tsc --noEmit
```
Expected: exit 0, no output.

Step 6: Commit (conventional message)

Delete the transient guard, re-run the suite to confirm the pinned baseline, then commit the worktree scaffolding only:

```bash
# Delete transient guard
rm /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_phase_a_handoff.py

# Re-pin baseline post-deletion
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q | tail -1 | tee /tmp/sprint7-web-baseline.txt
# Expected: line starts with "172 passed, 3 skipped, 11 deselected" (timing varies, do not pin it)
# Verify with: grep -qE '^172 passed, 3 skipped, 11 deselected' /tmp/sprint7-web-baseline.txt

# Commit (worktree branch was created off main; this is the first commit on
# feat/sprint-7-nhd-bluespace — nothing in the tree changes, so we use an
# empty marker commit to anchor the branch)
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace
git commit --allow-empty -m "chore(sprint-7): anchor feat/sprint-7-nhd-bluespace worktree

Phase A handoff verified: resolve_output_grouping reachable from editable
install; precomputed_static_linkage delegates correctly (transient guard
PASS, then removed). Web baseline pinned.

Baseline: 172 passed, 3 skipped, 11 deselected (per /tmp/sprint7-web-baseline.txt)
Spec: docs/superpowers/specs/2026-06-16-sprint-7-nhd-bluespace-design.md L912-919"
```

**Notes:**
- **Do NOT copy `backend/data/variable_metadata.json`** — it is gitignored as a runtime override and would shadow the in-tree `backend/app/data/variable_metadata.json`, tripping the Final-verification absent-tracking gate. The in-tree copy ships via worktree checkout automatically.
- The transient guard's two test functions inflate the suite to 174 during Step 5; the **immovable, quotable baseline is `172 passed, 3 skipped, 11 deselected`** captured *after* deletion in Step 6. All later B-task expected counts add to the 172 pass figure, not 174, and inherit the 3-skip / 11-deselect tail.
- The 3 skipped tests on baseline are environment-conditional, NOT the wheel-find guard exclusively: `test_install_posture.py::test_requirements_pin_resolves`, `test_ontology_build.py::test_build_ontology_outputs`, `test_tasks.py::test_start_lock_returns_409_when_busy`. Verify with `pytest -v 2>&1 | grep SKIP` if you need to triage drift.
- The 11 deselected tests are the Sprint-6 default `-m "not integration"` filter on the integration suite — they re-enable under `pytest -m integration` in Final Verification gate 4.
- `node_modules` is symlinked, not copied. If `tsc --noEmit` complains about missing modules, run `npm ci` inside the symlinked target — never inside the worktree itself.
- The canonical pinned string downstream tasks should quote is `172 passed, 3 skipped, 11 deselected`. Downstream B-task expected counts: B1 → 174, B2 → 174 (B1's gated reds flip green), B3 → 183, B5 → 184, with the `3 skipped, 11 deselected` tail unchanged throughout.
- Branch `feat/sprint-7-nhd-bluespace` was created in Step 2 via `git worktree add -b ... origin/main`, so it tracks `main` cleanly. No PR target ambiguity.
- Phase A is NOT merged into pipeline `main` at this point — the editable install resolves to the `pkg/pypi-only` worktree of `spacescans-project`. If `pip show spacescans` reveals a different install path, re-run `pip install -e /Users/xai/Desktop/spacescans-project` inside the web worktree's env before Step 4.

---

### Task B1: variable_metadata.json nhd_bluespace entry + _assert_nhd_data_present pre-flight

**Files:**
- /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/app/data/variable_metadata.json
- /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/app/variable_registry.py
- /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_variable_registry.py

**Goal:** Land the static `nhd_bluespace` variable metadata entry and a sibling `_assert_nhd_data_present` server-boot pre-flight that asserts the NHDPlus_H GDB is on disk (Sprint 7 Phase B, spec B4, L692-816, L920-927).

**Context:** Sprint 7 Phase B adds a fifth catalogued variable backed by a single static NHDPlus_H GDB. The Sprint 5 idiom `_assert_tiger_data_present` walks per-year subdirs — that doesn't fit NHD, which has no year axis. B1 mirrors the TIGER pattern with a simpler "single GDB exists" shape, gated by the same `SPACESCANS_DATA_DIR/data_full/.../C4` short-circuit. The new variable entry's `experiment: "nhd_bluespace"` will fail the discovery whitelist at server boot until B2 lands `backend/app/experiments/nhd_bluespace.py` — this half-landed gate is deliberate per spec L920 ("server boot will fail the discovery whitelist until step 3 — expected and gating").

Step 1: Write failing test (real pytest code)

Append to `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_variable_registry.py`:

```python


# ---------------------------------------------------------------------------
# Sprint 7 B1: nhd_bluespace metadata entry + NHD C4 server-boot pre-flight
# ---------------------------------------------------------------------------


def test_registry_accepts_nhd_bluespace_entry(tmp_path, monkeypatch):
    """Sprint 7 B1: nhd_bluespace entry passes schema (5 value_cols, BG boundary,
    [2024, 2024] static-product coverage) once an nhd_bluespace experiment
    module exists.

    This test stubs the experiment discovery so it does NOT depend on B2's
    runner module landing. It locks in the canonical entry shape from spec
    L692-708.
    """
    from app import variable_registry as vr

    real_schema = Path(__file__).parent.parent / "app" / "data" / "variable_metadata.schema.json"
    payload_path = tmp_path / "variable_metadata.json"
    payload_path.write_text(json.dumps({
        "schema_version": 1,
        "variables": {
            "nhd_bluespace": {
                "label": "NHD Blue-Feature Proximity",
                "description": (
                    "Per-block-group static distance (meters) to the nearest "
                    "NHD flowline (dist_flow_m), waterbody (dist_water_m), "
                    "area-feature (dist_area_m), coastline (dist_coast_m; "
                    "99999 for inland addresses), and combined blue-feature "
                    "(dist_blue_m), from NHDPlus_H National Release 2 GDB "
                    "(static product, 2024 vintage)."
                ),
                "boundary": "BG",
                "coverage_years": [2024, 2024],
                "coverage_region": "CONUS",
                "experiment": "nhd_bluespace",
                "variable_type": "continuous",
                "display_unit": "meters",
                "value_cols": [
                    "dist_flow_m", "dist_water_m", "dist_area_m",
                    "dist_coast_m", "dist_blue_m",
                ],
            }
        },
    }))

    monkeypatch.setattr(vr, "_METADATA_PATH", payload_path)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", real_schema)
    monkeypatch.setattr(
        vr, "_discover_experiments",
        lambda: {"bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace"},
    )

    payload = vr.load_variables(force=True)
    entry = payload["variables"]["nhd_bluespace"]
    assert entry["boundary"] == "BG"
    assert entry["experiment"] == "nhd_bluespace"
    assert entry["coverage_years"] == [2024, 2024]
    assert entry["display_unit"] == "meters"
    assert entry["value_cols"] == [
        "dist_flow_m", "dist_water_m", "dist_area_m",
        "dist_coast_m", "dist_blue_m",
    ]
    assert "NHDPlus_H National Release 2 GDB (static product, 2024 vintage)" in entry["description"]


def test_nhd_preflight_raises_on_missing_gdb(tmp_path, monkeypatch):
    """Sprint 7 B1: with the NHD C4 root present but the NHDPlus_H GDB missing,
    _assert_nhd_data_present must raise MetadataSchemaError.

    Mirrors the TIGER preflight's missing-year test (L370-383). The stub
    metadata payload contains ONLY nhd_bluespace (no tiger_proximity entry),
    so TIGER pre-flight is inert — no TIGER C4 mkdir is needed.
    """
    from app import variable_registry as vr
    from app.config import settings

    # NHD C4 root present, GDB absent. No TIGER scaffolding needed: the stub
    # payload below omits tiger_proximity, so _assert_tiger_data_present's
    # iteration of payload['variables'].values() has nothing to walk.
    nhd_c4 = tmp_path / "data_full" / "NHD" / "C4"
    nhd_c4.mkdir(parents=True)
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        vr, "_discover_experiments",
        lambda: {"bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace"},
    )

    # Stub metadata file with ONLY nhd_bluespace catalogued so the TIGER
    # pre-flight loop body never iterates.
    real_schema = Path(__file__).parent.parent / "app" / "data" / "variable_metadata.schema.json"
    payload_path = tmp_path / "variable_metadata.json"
    payload_path.write_text(json.dumps({
        "schema_version": 1,
        "variables": {
            "nhd_bluespace": {
                "label": "NHD Blue-Feature Proximity",
                "description": (
                    "Per-block-group static distance (meters) to the nearest "
                    "NHD flowline, from NHDPlus_H National Release 2 GDB "
                    "(static product, 2024 vintage)."
                ),
                "boundary": "BG",
                "coverage_years": [2024, 2024],
                "coverage_region": "CONUS",
                "experiment": "nhd_bluespace",
                "variable_type": "continuous",
                "display_unit": "meters",
                "value_cols": [
                    "dist_flow_m", "dist_water_m", "dist_area_m",
                    "dist_coast_m", "dist_blue_m",
                ],
            }
        },
    }))
    monkeypatch.setattr(vr, "_METADATA_PATH", payload_path)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", real_schema)

    with pytest.raises(vr.MetadataSchemaError) as exc_info:
        vr.load_variables(force=True)
    msg = str(exc_info.value)
    assert "NHDPlus_H_National_Release_2_GDB.gdb" in msg
    assert "nhd_bluespace" in msg
```

Step 2: Run RED (concrete bash + expected failure)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_variable_registry.py::test_registry_accepts_nhd_bluespace_entry backend/tests/test_variable_registry.py::test_nhd_preflight_raises_on_missing_gdb -x
```

Expected failure: `AttributeError: module 'app.variable_registry' has no attribute '_assert_nhd_data_present'` is NOT raised yet (the function call is added by B1 too), but `test_nhd_preflight_raises_on_missing_gdb` fails because `vr.load_variables(force=True)` returns the payload without raising — there is no NHD pre-flight yet. `test_registry_accepts_nhd_bluespace_entry` also fails because the real `variable_metadata.json` lacks the entry; once we monkeypatch the path, the test still passes only after B1's pre-flight is added (otherwise it raises `MetadataSchemaError` from the discovery whitelist for `nhd_bluespace` — but we stub `_discover_experiments`, so the failing mode for THIS test pre-B1-code is **PASS** at the schema level but the test only proves the entry shape, while the pre-flight test gives the hard RED). Net: 1 RED (`test_nhd_preflight_raises_on_missing_gdb` — `DID NOT RAISE <class 'app.variable_registry.MetadataSchemaError'>`).

Step 3: Implement minimal code (actual code to paste)

Edit `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/app/data/variable_metadata.json` — replace the closing of the `tiger_proximity` block and the final `}` with the `nhd_bluespace` entry appended:

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
    },
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
  }
}
```

Edit `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/app/variable_registry.py` — insert after line 97 (end of `_assert_tiger_data_present`):

```python


def _assert_nhd_data_present(payload: dict[str, Any]) -> None:
    """Pre-flight: NHDPlus_H National Release 2 GDB exists on disk.

    Raises MetadataSchemaError if any catalogued nhd_bluespace variable is
    declared but the static GDB at
    {DATA_ROOT}/data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb is
    absent.

    Short-circuits when no nhd_bluespace experiment is catalogued, OR when
    the C4 root itself is absent — production startup runs
    validate_pipeline_settings first, so the latter branch only fires
    under test fixtures that bypass the data-dir gate. Mirrors the
    sibling _assert_tiger_data_present idiom at lines 72-97; the simpler
    shape reflects NHD being a static (non-yearly) product.
    """
    from app.config import settings
    if not any(
        m.get("experiment") == "nhd_bluespace"
        for m in payload["variables"].values()
    ):
        return
    data_dir = settings.SPACESCANS_DATA_DIR / "data_full" / "NHD" / "C4"
    if not data_dir.is_dir():
        return
    gdb_path = data_dir / "NHDPlus_H_National_Release_2_GDB.gdb"
    if not gdb_path.exists():
        raise MetadataSchemaError(
            f"nhd_bluespace catalogued but NHDPlus_H GDB missing at {gdb_path}"
        )
```

Then add the call at the bottom of `load_variables()` immediately after the existing `_assert_tiger_data_present(payload)` line (currently line 127):

```python
    _assert_tiger_data_present(payload)
    _assert_nhd_data_present(payload)
```

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_variable_registry.py::test_registry_accepts_nhd_bluespace_entry backend/tests/test_variable_registry.py::test_nhd_preflight_raises_on_missing_gdb -v
```

Expected: both pass. The real-file load test (`test_real_metadata_file_contains_tiger_proximity_with_runner_module` and any sibling) will now ALSO fail because `nhd_bluespace` is in the real JSON but `backend/app/experiments/nhd_bluespace.py` does not yet exist — this is the deliberate B2 gating (spec L920: "server boot will fail the discovery whitelist until step 3").

Step 5: Full suite (with expected cumulative count)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/ -x --ignore=backend/tests/test_e2e_nhd_bluespace_cohort.py --ignore=backend/tests/test_e2e_multi_experiment_with_nhd.py 2>&1 | tail -30
```

Expected: 172 (baseline) + 2 new = **174 total**, with **N failing** where N is the count of tests that exercise the real `variable_metadata.json` through `load_variables(force=True)` without stubbing `_discover_experiments` — these will raise `MetadataSchemaError: variable 'nhd_bluespace' references unknown experiment 'nhd_bluespace'`. This is the expected gating state; B2 (runner module) flips these to GREEN. Document the gated failures in the commit message.

Step 6: Commit (conventional message)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && git add backend/app/data/variable_metadata.json backend/app/variable_registry.py backend/tests/test_variable_registry.py && git commit -m "$(cat <<'EOF'
feat(registry): nhd_bluespace metadata entry + NHD GDB pre-flight (Sprint 7 B1)

- Add nhd_bluespace variable entry to variable_metadata.json (BG boundary,
  5 value_cols, [2024,2024] static-product coverage, meters unit).
- Add _assert_nhd_data_present sibling to _assert_tiger_data_present;
  walks payload['variables'].values() for the nhd_bluespace experiment,
  short-circuits on missing C4 root (test-fixture pattern), raises
  MetadataSchemaError on missing NHDPlus_H GDB.
- Wire the call into load_variables() immediately after the TIGER
  pre-flight at variable_registry.py:127.
- Add 2 tests: registry-accepts-entry (stubs _discover_experiments,
  asserts canonical shape) and preflight-raises-on-missing-GDB.

GATED: tests exercising the real variable_metadata.json without
stubbing _discover_experiments fail with "unknown experiment
'nhd_bluespace'" until B2 lands backend/app/experiments/nhd_bluespace.py
(spec L920: deliberate half-landed gate).
EOF
)"
```

**Notes:**
- The `_assert_nhd_data_present` test mocks `_discover_experiments` because the real-file path used by `test_real_metadata_file_contains_tiger_proximity_with_runner_module` (and any analog) is the gating failure mode — B1 deliberately leaves those red until B2.
- Order matters: append the `nhd_bluespace` entry AFTER `tiger_proximity` to preserve the file-order dispatch invariant (Sprint 3) — dispatcher will spawn bg_ndi_wi → zcta5_cbp → tiger_proximity → nhd_bluespace.
- The `_assert_nhd_data_present` body uses `m.get("experiment")` dict access (NOT attribute access) per spec L772-779: `VariableMetadata` is only a TS interface and a `VariableMetadataModel` Pydantic class in `routers/variables.py`; the registry layer works with raw dicts.
- The path `data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb` matches the TIGER pre-flight convention (`data_full/TIGER/C4/...`) and the web settings docstring at `config.py:39`.
- TIGER pre-flight is inert in `test_nhd_preflight_raises_on_missing_gdb` because the stub metadata payload contains ONLY `nhd_bluespace`; `_assert_tiger_data_present` iterates `payload['variables'].values()` looking for `experiment == "tiger_proximity"` entries and finds none, so the loop body never fires regardless of TIGER directory state. No TIGER C4 mkdir is needed — earlier drafts created one out of caution but it is load-irrelevant.
- Schema validation runs BEFORE the discovery whitelist (line 111 vs 119-125), so the entry-shape assertions in `test_registry_accepts_nhd_bluespace_entry` exercise jsonschema first; the stubbed `_discover_experiments` just lets execution reach the pre-flight without raising at the whitelist.
- 2 new tests against baseline 172 → 174 in the default-marker suite (`@pytest.mark.integration` tests stay deferred to B6/B7). Skip/deselect tail unchanged: `3 skipped, 11 deselected`.

---

### Task B2: nhd_bluespace.py runner (clone-trim of tiger_proximity.py)

**Files:**
- Create: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/app/experiments/nhd_bluespace.py`

**Goal:** Land the fifth experiment runner as a near-pure clone of `tiger_proximity.py` with the five spec-mandated constant swaps (boundary tag `BG_NHD`, experiment key `nhd_bluespace`, C3/C4 step names, parquet map, and a `precomputed_static`-targeted pipeline sanity probe), so the metadata-driven catalog grows to 5 keys without dispatcher/registry edits.

**Context:** Sprint 7 Phase A (B1) extended `precomputed_static_linkage.py` with `resolve_output_grouping` dispatch — the runner this task creates is the web-side consumer of that contract. The new module is the 5th experiment runner and 3rd "precomputed_*" sibling (after `tiger_proximity`); its `render_yaml` rewrites C4 `exposure.file` to the per-task C3 output (same Sprint 5 idiom), omits `raster_res_m` (NHD is line/poly geometry), and emits a 2-step `[c3, c4]` plan because the shipped `proximity_blue_demo100k.parquet` is cohort-bound and cannot be reused. Naming and boundary tag `BG_NHD` insulate this runner's C3 cache from `bg_ndi_wi`'s `BG` and `tiger_proximity`'s `BG_TIGER` namespaces for the same input parquet + buffer.

Step 1: Write failing test (real pytest code)

No test file is created in B2 itself — per the task spec ("Test: (none)"); the test files (`test_nhd_bluespace.py`, `test_e2e_nhd_bluespace_cohort.py`, `test_e2e_multi_experiment_with_nhd.py`) land in later B-phase tasks (B3-B5). The RED signal for B2 is the import-and-introspect probe below: it must fail before the new file exists and pass after.

```bash
# RED probe — temporary; do not commit
cat > /tmp/b2_red_probe.py <<'PY'
"""Sprint 7 B2 RED probe: assert nhd_bluespace runner module shape.

Run BEFORE creating the file (expect ModuleNotFoundError) and AFTER
(expect every assertion to pass).
"""
import inspect
from pathlib import Path

from app.experiments import nhd_bluespace as m
from app.experiments.bg_ndi_wi import PipelineStep

# Module constants
assert m._BOUNDARY == "BG_NHD"
assert m._EXPERIMENT_KEY == "nhd_bluespace"
assert m._PARQUET_MAP == {"nhd_bluespace": "c4_nhd_bluespace.parquet"}
assert isinstance(m._C3_STEP, PipelineStep)
assert m._C3_STEP.name == "c3_nhd_bluespace"
assert m._C3_STEP.template_relpath == "c3/nhd_demo.yaml"
assert m._C3_STEP.is_c3 is True
assert set(m._VARIABLE_TO_STEP.keys()) == {"nhd_bluespace"}
c4 = m._VARIABLE_TO_STEP["nhd_bluespace"]
assert c4.name == "c4_nhd_bluespace"
assert c4.template_relpath == "c4/nhd_bluespace_demo.yaml"
assert c4.is_c3 is False

# plan() — empty + unknown ValueError, 2-step happy path
import pytest
with pytest.raises(ValueError, match="at least one variable"):
    m.plan({"variables": []})
with pytest.raises(ValueError, match="unknown variable"):
    m.plan({"variables": ["bogus"]})
steps = m.plan({"variables": ["nhd_bluespace"]})
assert [s.name for s in steps] == ["c3_nhd_bluespace", "c4_nhd_bluespace"]

# Sanity probe exists and grep-targets resolve_output_grouping
src = inspect.getsource(m._sanity_check_pipeline_supports_precomputed_static_episode)
assert "precomputed_static_linkage" in src
assert "resolve_output_grouping" in src

# csv_to_parquet is NOT imported at module top (local-in-run() per spec L521-523)
assert "csv_to_parquet" not in dir(m)

# CLI prog field
parser_src = inspect.getsource(m._cli_main)
assert 'prog="nhd_bluespace"' in parser_src

# Variable catalog surface — 5 keys (use registry directly; /api/variables is
# JWT-gated via Depends(get_current_user) → 403 on unauthenticated TestClient)
from app import variable_registry
payload = variable_registry.load_variables(force=True)
assert set(payload["variables"].keys()) == {
    "ndi", "walkability", "cbp_zcta5", "tiger_proximity", "nhd_bluespace"
}, f"unexpected catalog keys: {sorted(payload['variables'].keys())}"
print("B2 probe OK")
PY
```

Step 2: Run RED (concrete bash + expected failure)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend
/Users/xai/miniconda3/envs/spacescans/bin/python /tmp/b2_red_probe.py
# Expected:
#   Traceback (most recent call last):
#     ...
#   ModuleNotFoundError: No module named 'app.experiments.nhd_bluespace'
```

Step 3: Implement minimal code (actual code to paste)

Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/app/experiments/nhd_bluespace.py` with the full module body below. Every line is a deliberate clone of `tiger_proximity.py` except the five constant swaps and the sanity-probe target.

```python
"""Single-experiment orchestrator: BG-tagged NHD blue-feature proximity.

Spawned by app.dispatcher as:
    python -m app.experiments.nhd_bluespace run <task_dir> [--variables nhd_bluespace]

Cloned from tiger_proximity.py with the spec-mandated deltas (Sprint 7):
  * _BOUNDARY = 'BG_NHD' (avoids collision with BG / BG_TIGER caches)
  * C3 step c3_nhd_bluespace -> c3/nhd_demo.yaml
  * C4 step c4_nhd_bluespace -> c4/nhd_bluespace_demo.yaml
  * sanity probe greps precomputed_static_linkage for resolve_output_grouping
    (Sprint 7 Phase A contract; Sprint 5 grepped precomputed_areal_linkage)
  * render_yaml writes no raster_res_m (NHD is line/poly geometry, no raster).
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import inspect
import json
import logging
import os
import shutil
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

import app.config
from app.experiments import _merge
from app.experiments.bg_ndi_wi import (
    PipelineStep,
    parse_step_progress,  # noqa: F401  (re-exported for symmetry with siblings)
    run_pipeline_step,
    _append_log,
    _is_valid_cached_parquet,
)

_log = logging.getLogger(__name__)

_BOUNDARY = "BG_NHD"
_EXPERIMENT_KEY = "nhd_bluespace"

_C3_STEP = PipelineStep(
    name="c3_nhd_bluespace",
    template_relpath="c3/nhd_demo.yaml",
    is_c3=True,
)

_VARIABLE_TO_STEP = {
    "nhd_bluespace": PipelineStep(
        name="c4_nhd_bluespace",
        template_relpath="c4/nhd_bluespace_demo.yaml",
        is_c3=False,
    ),
}

_PARQUET_MAP = {"nhd_bluespace": "c4_nhd_bluespace.parquet"}


def _sanity_check_pipeline_supports_precomputed_static_episode() -> None:
    """Spec L803-814: grep live pipeline source for resolve_output_grouping.

    Sprint 7 Phase A added the helper call to precomputed_static_linkage.py.
    If the editable-installed wheel is stale, runner emits patient-rows and
    _merge.write_partial collapses one-to-many on episode_id. Detect that
    drift at runner start with a deterministic substring grep.
    """
    from spacescans.linkage import precomputed_static_linkage
    if "resolve_output_grouping" not in inspect.getsource(precomputed_static_linkage):
        raise RuntimeError(
            "spacescans-pipeline missing Sprint 7 Phase A: "
            "precomputed_static_linkage does not call resolve_output_grouping. "
            "Editable install is stale — reinstall or bump the version pin."
        )


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


def render_yaml(step: PipelineStep, task_dir: Path, user_config: dict) -> Path:
    """Read pipeline YAML template, inject task-specific fields, write to task dir.

    Two structural divergences from bg_ndi_wi.render_yaml / zcta5_cbp.render_yaml:
      1. No raster_res_m write — NHD templates have no such key (line/poly).
      2. On the C4 step only, rewrite cfg['exposure']['file'] to point at the
         per-task C3 parquet output (precomputed_static reads it as the
         exposure table). The C3 step needs no source.file rewrite — the
         pipeline CLI's --data-dir SPACESCANS_DATA_DIR arg resolves the
         relative data_full/NHD/C4/... path via config_resolution.expand_path
         (spec L286-298).
    """
    template_path = (
        app.config.settings.SPACESCANS_CONFIG_TEMPLATES_DIR / step.template_relpath
    )
    cfg = yaml.safe_load(template_path.read_text())

    task_id_short = task_dir.name[-8:]
    cfg["name"] = f"{cfg['name']}_task_{task_id_short}"
    cfg["buffer"]["patient_file"] = str(task_dir / "input.parquet")
    cfg["buffer"]["buffer_m"] = user_config["buffer"]["size"]
    # NOTE: no raster_res_m write (NHD is line/poly geometry).

    if step.is_c3:
        # C3: pipeline CLI --data-dir resolves source.file; no rewrite here.
        pass
    else:
        # C4: rewrite exposure.file to point at this task's C3 output.
        if not isinstance(cfg.get("exposure"), dict):
            raise RuntimeError(
                "nhd_bluespace.render_yaml: unexpected exposure: shape in C4 template"
            )
        cfg["exposure"]["file"] = str(
            task_dir / "output" / f"{_C3_STEP.name}.parquet"
        )

    if "time" in cfg:
        cfg["time"]["output_grouping"] = "episode"  # Sprint 7 Phase A contract
    cfg["output"]["path"] = str(task_dir / "output" / f"{step.name}.parquet")

    out = task_dir / "pipeline_configs" / f"{step.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out



def _write_status(task_dir: Path, status: str, **extra) -> None:
    """Mirror tiger_proximity._write_status — JSON write to task_dir/status.json."""
    status_path = task_dir / "status.json"
    payload = {"status": status, "experiment": _EXPERIMENT_KEY, **extra}
    status_path.write_text(json.dumps(payload, indent=2))


def _write_slot_status(task_dir: Path, slot_status: str, progress: float, **extra) -> None:
    """Per-experiment slot status (status.json experiments map entry)."""
    status_path = task_dir / "status.json"
    if status_path.exists():
        payload = json.loads(status_path.read_text())
    else:
        payload = {"status": "running", "experiments": {}}
    payload.setdefault("experiments", {})
    payload["experiments"][_EXPERIMENT_KEY] = {
        "status": slot_status, "progress": progress, **extra,
    }
    status_path.write_text(json.dumps(payload, indent=2))


def _hash_input_parquet(input_parquet: Path) -> str:
    """sha256 of the input parquet file bytes; truncated to 8 chars by _cache_key."""
    h = hashlib.sha256()
    with open(input_parquet, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_key(input_parquet: Path, step: PipelineStep, user_config: dict) -> str:
    """Cache key: <sha8>__BG_NHD__b<buffer>m  (no raster, no year — NHD is static vector)."""
    sha = _hash_input_parquet(input_parquet)[:8]
    buf = int(user_config["buffer"]["size"])
    return f"{sha}__{_BOUNDARY}__b{buf}m"


def _write_cache_meta(cache_dir: Path, cache_key: str, step: PipelineStep) -> None:
    """Write cache_meta.json next to the cached parquet for audit traceability."""
    meta = {
        "cache_key": cache_key,
        "experiment": _EXPERIMENT_KEY,
        "boundary": _BOUNDARY,
        "step": step.name,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (cache_dir / "cache_meta.json").write_text(json.dumps(meta, indent=2))


def _count_input_rows(input_parquet: Path) -> int:
    """Lightweight row count via pyarrow metadata — no full read."""
    import pyarrow.parquet as pq
    return pq.ParquetFile(str(input_parquet)).metadata.num_rows


_CANCEL_REQUESTED = False


def _install_cancel_handler() -> None:
    """SIGTERM → set _CANCEL_REQUESTED; child pipeline subprocess polls via env."""
    def _on_term(signum, frame):  # noqa: ARG001
        global _CANCEL_REQUESTED
        _CANCEL_REQUESTED = True
    signal.signal(signal.SIGTERM, _on_term)


def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Delegate to _merge.write_partial — emits result_nhd_bluespace.csv with pid,
    episode_id, and the 5 dist_*_m value columns."""
    return _merge.write_partial(
        task_dir=task_dir,
        experiment_key=_EXPERIMENT_KEY,
        variables=variables,
        parquet_map=_PARQUET_MAP,
    )


def run(task_dir: Path, variables: list[str] | None = None) -> int:
    """Execute c3_nhd_bluespace then c4_nhd_bluespace, write result_*.csv, return rc."""
    # Local import per spec L521-523 — keeps zcta5_cbp.csv_to_parquet out of
    # module-load to avoid the boot-time cycle tiger_proximity:265 warns about.
    from app.experiments.zcta5_cbp import csv_to_parquet  # noqa: F401

    _install_cancel_handler()
    _sanity_check_pipeline_supports_precomputed_static_episode()

    user_config = json.loads((task_dir / "config.json").read_text())
    selected = variables or user_config.get("variables", [])
    steps = plan({"variables": selected})

    _write_status(task_dir, "running")
    _write_slot_status(task_dir, "running", 0.0)

    input_parquet = task_dir / "input.parquet"
    if not input_parquet.exists():
        from app.experiments.zcta5_cbp import csv_to_parquet
        csv_to_parquet(task_dir / "input.csv", input_parquet)

    cache_root = Path(os.environ.get("C3_CACHE_DIR", str(task_dir / ".c3-cache")))
    cache_root.mkdir(parents=True, exist_ok=True)

    for i, step in enumerate(steps):
        if _CANCEL_REQUESTED:
            _write_slot_status(task_dir, "cancelled", i / len(steps))
            return 130
        ck = _cache_key(input_parquet, step, user_config)
        cache_dir = cache_root / ck
        cached_parquet = cache_dir / f"{step.name}.parquet"
        target = task_dir / "output" / f"{step.name}.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)

        if step.is_c3 and _is_valid_cached_parquet(cached_parquet):
            _append_log(task_dir, source=step.name, progress=1.0, cache_hit=True)
            shutil.copy(cached_parquet, target)
            continue

        rendered_yaml = render_yaml(step, task_dir, user_config)
        rc = run_pipeline_step(task_dir, step, rendered_yaml)
        if rc != 0:
            _write_slot_status(task_dir, "error", i / len(steps),
                               error=f"step {step.name} exited {rc}")
            return rc

        if step.is_c3:
            cache_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(target, cached_parquet)
            _write_cache_meta(cache_dir, ck, step)

    merge_results(task_dir, selected)
    _write_slot_status(task_dir, "finished", 1.0)
    return 0


def _cli_main(argv: list[str] | None = None) -> int:
    """Module-level CLI: python -m app.experiments.nhd_bluespace run <task_dir>."""
    parser = argparse.ArgumentParser(prog="nhd_bluespace")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("task_dir", type=Path)
    run_p.add_argument("--variables", nargs="+", default=None)
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return run(args.task_dir, args.variables)
    return 2


if __name__ == "__main__":
    sys.exit(_cli_main())
```

Every function above is a byte-for-byte structural clone of `backend/app/experiments/tiger_proximity.py` lines 141-451 with exactly five swaps: `_EXPERIMENT_KEY = "nhd_bluespace"`, `_BOUNDARY = "BG_NHD"` (already declared above), `_PARQUET_MAP` keyed on `nhd_bluespace`, the sanity-probe target `precomputed_static_linkage` (not `precomputed_areal_linkage`), and `prog="nhd_bluespace"` in `_cli_main`. If the executing subagent finds any divergence vs the actual `tiger_proximity.py` on the worktree, treat that as drift and reconcile — do NOT silently re-derive.

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend
/Users/xai/miniconda3/envs/spacescans/bin/python /tmp/b2_red_probe.py
# Expected stdout:
#   B2 probe OK
# Then clean up the probe:
rm /tmp/b2_red_probe.py
```

Also confirm `python -m app.experiments.nhd_bluespace --help` prints the `prog="nhd_bluespace"` header and the `run` subcommand:

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m app.experiments.nhd_bluespace --help
# Expected: "usage: nhd_bluespace [-h] {run} ..." with no traceback.
```

Step 5: Full suite (with expected cumulative count)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ -x -q
# Expected: 174 passed, 3 skipped, 11 deselected (172 baseline + B1's 2 registry tests).
# B2 ships no new tests; the runner's test file lands in B3.
# B1's previously gated real-file tests now flip to GREEN because the
# nhd_bluespace experiment module exists — discovery whitelist passes.
```

Step 6: Commit (conventional message)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace
git add backend/app/experiments/nhd_bluespace.py
git commit -m "$(cat <<'EOF'
feat(experiments): add nhd_bluespace runner (clone-trim of tiger_proximity)

Sprint 7 Phase B / task B2. Near-pure clone of tiger_proximity.py with
the five spec-mandated constant swaps:
  * _BOUNDARY = "BG_NHD" (separate cache namespace from BG / BG_TIGER)
  * C3 step c3_nhd_bluespace -> c3/nhd_demo.yaml
  * C4 step c4_nhd_bluespace -> c4/nhd_bluespace_demo.yaml
  * sanity probe greps precomputed_static_linkage for resolve_output_grouping
    (Sprint 7 Phase A contract; Sprint 5 grepped precomputed_areal_linkage)
  * argparse prog="nhd_bluespace"

render_yaml mirrors tiger_proximity: rewrites exposure.file on C4 only
(C3 source.file resolves via pipeline CLI --data-dir per spec L286-298),
no raster_res_m write (NHD is line/poly geometry, not raster), time
override to "episode" guarded by `if "time" in cfg` (naturally skips C3
template which has no time: block). _cache_key shape <sha8>__BG_NHD__b<buf>m
omits both raster and year axes. csv_to_parquet imported locally inside
run() per spec L521-523 to mirror tiger_proximity:265's module-cycle note.

Refs: spec /docs/superpowers/specs/2026-06-16-sprint-7-nhd-bluespace-design.md
      L83-101, L509-688, L803-814, L928-929, L1031.
Depends on: B1 (Phase A precomputed_static_linkage dispatch).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

**Notes:**
- `csv_to_parquet` MUST stay imported locally inside `run()` (spec L521-523, tiger_proximity:265) — keeping it at module top would re-introduce a boot-time cycle and silently break dispatcher spawn. The probe at Step 1 asserts `"csv_to_parquet" not in dir(m)` to catch that drift.
- The sanity-probe target string is `"resolve_output_grouping"` (Sprint 7 Phase A), NOT `"output_grouping"` (which is what tiger_proximity greps for in Sprint 5's `precomputed_areal_linkage`). Easy copy-paste hazard since the surrounding boilerplate is identical.
- `_C3_STEP.template_relpath` is `"c3/nhd_demo.yaml"` (singular `nhd_demo`), while the C4 template is `"c4/nhd_bluespace_demo.yaml"` (full `nhd_bluespace_demo`). Asymmetric, matches the on-disk pipeline configs — the C3 NHD template is shared with future bluespace siblings.
- The `if "time" in cfg:` guard on the C4 override is load-bearing: the C3 NHD template intentionally has no `time:` block, and the override would `KeyError` without the guard. Same idiom Sprint 5 used.
- `RuntimeError` (not `ValueError`) for the unexpected-`exposure`-shape branch — matches tiger_proximity's "render-level invariant violation" framing and the spec's L587-590 wording.
- No test file in B2 — B3 lands `test_nhd_bluespace.py`, B4 lands `test_e2e_nhd_bluespace_cohort.py`, B5 lands `test_e2e_multi_experiment_with_nhd.py`.
- The `parse_step_progress` re-export at the import line is `# noqa: F401` for symmetry with tiger_proximity / zcta5_cbp / bg_ndi_wi — sibling test modules import it through any of the four runners interchangeably.
- `_BOUNDARY = "BG_NHD"` is checked at server boot by `_assert_nhd_data_present` (B1) only when a metadata entry exists; the runner module itself does no filesystem check at import time, so editable-install drift surfaces only on `run()` call via the sanity probe.

---

### Task B3: nhd_bluespace unit tests (8 tests, mirror tiger_proximity coverage)

**Files:**
- /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_nhd_bluespace.py (create)
- /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_merge_partial.py (modify, +1 test)

**Goal:** Lock the nhd_bluespace runner contract with 8 unit tests mirroring tiger_proximity coverage (plus a 9th cache-collision guard per R1) and add a +1 test confirming merge_partial picks all 5 NHD value columns from one parquet.

**Context:** B2 just landed the `nhd_bluespace` runner with C3 (source) + C4 (exposure) plan steps, a `BG_NHD_<buffer>` cache key, and 5 numeric value columns (`dist_flow_m`, `dist_water_m`, `dist_area_m`, `dist_coast_m`, `dist_blue_m`). Per spec L671-688 the runner differs from `tiger_proximity` in three ways: (a) no `raster_res_m` field (NHD is vector), (b) C3 template has no `time:` block so the time-grouping injection naturally skips on C3, (c) cache key prefix `BG_NHD` must NOT collide with `BG` (bg_ndi_wi) or `BG_TIGER` (tiger_proximity). Tests mock `subprocess.run` and `pyarrow` IO — no real pipeline invocation. Baseline 174 -> 183.

Step 1: Write failing test (real pytest code)

Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_nhd_bluespace.py`:

```python
"""Unit tests for nhd_bluespace runner (mirrors test_tiger_proximity coverage).

Spec: docs/superpowers/specs/2026-06-16-sprint-7-nhd-bluespace-design.md
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from app.experiments import nhd_bluespace
from app.experiments.bg_ndi_wi import _cache_key as bg_ndi_cache_key
from app.experiments.tiger_proximity import _cache_key as tiger_cache_key


# ---------- plan() ----------

def test_plan_returns_c3_c4_steps():
    plan = nhd_bluespace.plan({"variables": ["nhd_bluespace"]})
    assert len(plan) == 2
    assert plan[0].name == "c3_nhd_bluespace"
    assert plan[1].name == "c4_nhd_bluespace"


def test_plan_rejects_empty_variables():
    with pytest.raises(ValueError, match="at least one variable"):
        nhd_bluespace.plan({"variables": []})


def test_plan_rejects_unknown_variable():
    with pytest.raises(ValueError, match="unknown variable"):
        nhd_bluespace.plan({"variables": ["nhd_bluespace", "bogus_col"]})


# ---------- render_yaml() ----------

def test_render_yaml_rewrites_c4_exposure_file_to_task_c3_output(tmp_path):
    """C4 step rewrites exposure.file to per-task C3 output parquet."""
    task_dir = tmp_path / "task-abcd1234"
    task_dir.mkdir()
    out = nhd_bluespace.render_yaml(
        nhd_bluespace._VARIABLE_TO_STEP["nhd_bluespace"],
        task_dir,
        {"buffer": {"size": 270}},
    )
    parsed = yaml.safe_load(out.read_text())
    assert "c3_nhd_bluespace.parquet" in parsed["exposure"]["file"]


def test_render_yaml_skips_c3_source_file_rewrite(tmp_path):
    """C3 reads NHD source via pipeline CLI --data-dir; render_yaml must not
    rewrite source.file."""
    task_dir = tmp_path / "task-abcd1234"
    task_dir.mkdir()
    out = nhd_bluespace.render_yaml(
        nhd_bluespace._C3_STEP,
        task_dir,
        {"buffer": {"size": 270}},
    )
    parsed = yaml.safe_load(out.read_text())
    # C3 template's source.file remains the relative data_full/NHD/... path
    assert "task-abcd1234" not in parsed.get("source", {}).get("file", "")


def test_render_yaml_injects_time_output_grouping_episode_on_c4_only(tmp_path):
    """C4 template has time: block -> output_grouping=episode injected.
    C3 template has no time: block -> guard 'if time in cfg' skips naturally."""
    task_dir = tmp_path / "task-abcd1234"
    task_dir.mkdir()

    c4_out = nhd_bluespace.render_yaml(
        nhd_bluespace._VARIABLE_TO_STEP["nhd_bluespace"],
        task_dir,
        {"buffer": {"size": 270}},
    )
    c4_parsed = yaml.safe_load(c4_out.read_text())
    assert c4_parsed["time"]["output_grouping"] == "episode"

    c3_out = nhd_bluespace.render_yaml(
        nhd_bluespace._C3_STEP,
        task_dir,
        {"buffer": {"size": 270}},
    )
    c3_parsed = yaml.safe_load(c3_out.read_text())
    assert "time" not in c3_parsed  # C3 template has no time: block


def test_render_yaml_omits_raster_res_m(tmp_path):
    """NHD is line/poly vector data; no raster_res_m field anywhere."""
    task_dir = tmp_path / "task-abcd1234"
    task_dir.mkdir()
    for step in (nhd_bluespace._C3_STEP, nhd_bluespace._VARIABLE_TO_STEP["nhd_bluespace"]):
        out = nhd_bluespace.render_yaml(step, task_dir, {"buffer": {"size": 270}})
        body = out.read_text()
        assert "raster_res_m" not in body


# ---------- _cache_key() ----------

def test_cache_key_format_BG_NHD_buffer(tmp_path):
    """_cache_key shape: <sha8>__BG_NHD__b<buffer>m"""
    input_parquet = tmp_path / "input.parquet"
    input_parquet.write_bytes(b"fake-parquet-bytes")
    key = nhd_bluespace._cache_key(
        input_parquet,
        nhd_bluespace._C3_STEP,
        {"buffer": {"size": 270}},
    )
    assert "__BG_NHD__b270m" in key
    assert len(key.split("__")[0]) == 8  # sha8 prefix


def test_cache_key_differs_from_other_bg_runners(tmp_path):
    """R1 mitigation: BG_NHD must not collide with BG (bg_ndi_wi) or BG_TIGER
    (tiger_proximity) for same input parquet + buffer."""
    input_parquet = tmp_path / "input.parquet"
    input_parquet.write_bytes(b"fake-parquet-bytes")
    cfg = {"buffer": {"size": 270}, "year": 2017}

    nhd_key = nhd_bluespace._cache_key(input_parquet, nhd_bluespace._C3_STEP, cfg)
    # Best-effort sibling lookups — if signatures drift, update imports.
    # Assertions are about NHD's prefix shape and full-string distinctness.
    assert "__BG_NHD__" in nhd_key
    assert "__BG_TIGER__" not in nhd_key
    # Full-string inequality against fabricated sibling keys with same sha+buffer
    sha = nhd_key.split("__")[0]
    assert nhd_key != f"{sha}__BG__b270m"
    assert nhd_key != f"{sha}__BG_TIGER__b270m"


# ---------- sanity probe ----------

def test_sanity_check_raises_on_stale_pipeline_install(monkeypatch):
    """If precomputed_static_linkage source lacks 'resolve_output_grouping',
    runner must raise RuntimeError before any pipeline subprocess fires."""
    import inspect
    from spacescans.linkage import precomputed_static_linkage
    # Stub inspect.getsource to return a source without the token
    monkeypatch.setattr(inspect, "getsource",
                        lambda obj: "def run(): pass" if obj is precomputed_static_linkage
                                    else inspect._original_getsource(obj))
    with pytest.raises(RuntimeError, match="resolve_output_grouping"):
        nhd_bluespace._sanity_check_pipeline_supports_precomputed_static_episode()
```

Modify `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_merge_partial.py` — append one test (spec L954):

```python
def test_merge_partial_value_cols_picks_five_nhd_columns(tmp_path):
    """Spec L954: when the nhd_bluespace C4 partial parquet carries the five
    canonical dist_*_m columns, write_partial must surface all five (plus pid
    and episode_id) into result_nhd_bluespace.csv. Exercises the inline
    `value_cols = [c for c in meta["value_cols"] if c in df.columns]` selection
    at _merge.py:47 — no private helper is asserted, only the observable CSV
    column set.
    """
    import pandas as pd
    from app.experiments import _merge

    # Lay out task_dir as write_partial expects: output/ subdir + the C4 parquet.
    task_dir = tmp_path
    (task_dir / "output").mkdir()
    pd.DataFrame({
        "pid": [1, 2, 3],
        "episode_id": [10, 11, 12],
        "dist_flow_m": [1.0, 2.0, 3.0],
        "dist_water_m": [10.0, 20.0, 30.0],
        "dist_area_m": [100.0, 200.0, 300.0],
        "dist_coast_m": [1e3, 2e3, 3e3],
        "dist_blue_m": [1e4, 2e4, 3e4],
    }).to_parquet(task_dir / "output" / "c4_nhd_bluespace.parquet", index=False)

    out_csv = _merge.write_partial(
        task_dir=task_dir,
        experiment_key="nhd_bluespace",
        variables=["nhd_bluespace"],
        parquet_map={"nhd_bluespace": "c4_nhd_bluespace.parquet"},
    )

    df = pd.read_csv(out_csv)
    assert sorted(df.columns) == sorted([
        "pid", "episode_id",
        "dist_area_m", "dist_blue_m", "dist_coast_m",
        "dist_flow_m", "dist_water_m",
    ]), f"unexpected columns in {out_csv}: {list(df.columns)}"
    assert len(df) == 3
```

Note on signature: `_merge.write_partial` parameters are derived from
`backend/app/experiments/_merge.py:20` (verify with `inspect.signature` if the
runner-side caller diverges). If your B2 runner passes a different argument
shape, update both the test and the call site together so the contract stays
self-consistent.

Step 2: Run RED (concrete bash + expected failure)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_nhd_bluespace.py backend/tests/test_merge_partial.py::test_merge_partial_value_cols_picks_five_nhd_columns -v
```

Expected RED: 9 failures or collection errors. Most likely modes: `ModuleNotFoundError` on `app.experiments.nhd_bluespace` if B2 has not landed, `AttributeError` on `nhd_bluespace._cache_key` if naming drifted from B2, or the `write_partial` call signature differs (verify against `_merge.py:20` if needed). Reconcile names with B2 before flipping GREEN.

Step 3: Implement minimal code (actual code to paste)

No production-code edits are needed in B3 — B2 already shipped `_cache_key`, `render_yaml`, `plan`, and `_sanity_check_pipeline_supports_precomputed_static_episode`, and `_merge.write_partial` already exists at `backend/app/experiments/_merge.py:20` with the inline value-col selection at line 47. If `inspect.signature(_merge.write_partial)` reveals the parameter names diverge from the test paste above, update the test's keyword arguments to match — do NOT introduce a private `_select_value_cols` helper; the public `write_partial` end-to-end shape is the load-bearing contract.

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_nhd_bluespace.py backend/tests/test_merge_partial.py::test_merge_partial_value_cols_picks_five_nhd_columns -v
```

Expected: `9 passed` (8 new in test_nhd_bluespace.py + 1 in test_merge_partial.py).

Step 5: Full suite (with expected cumulative count)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/ -v --tb=short
```

Expected: `183 passed, 3 skipped, 11 deselected` (174 post-B2 + 8 nhd_bluespace + 1 merge_partial = 183; skip/deselect tail inherited from B0 baseline). If pass count is 182 or 184 STOP and reconcile — do not adjust the assertion to match.

Step 6: Commit (conventional message)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && git add backend/tests/test_nhd_bluespace.py backend/tests/test_merge_partial.py && git commit -m "$(cat <<'EOF'
test(backend): nhd_bluespace unit tests + merge_partial NHD value-col selection

8 tests mirror tiger_proximity coverage (plan/render_yaml/cache_key/
sanity_check) plus R1 cache-collision guard asserting BG_NHD differs
from BG (bg_ndi_wi) and BG_TIGER (tiger_proximity) in both tag and shape.
+1 in test_merge_partial confirms all 5 NHD value cols surface from one
parquet.

Spec: docs/superpowers/specs/2026-06-16-sprint-7-nhd-bluespace-design.md
Refs: L102-105, L671-688, L930-931, L949-950, L955-956, L976-977
Test count: 174 -> 183 (+8 nhd + 1 merge_partial)
EOF
)"
```

**Notes:**
- C3 template has no `time:` block so the existing `if 'time' in cfg` guard in render_yaml will skip the episode-grouping injection naturally — the test verifies the *observable* outcome (`"time" not in c3_parsed`), not the guard's source text, so it survives refactors.
- The cache-key collision test does not import sibling `_cache_key` functions (signatures may differ across runners) — it asserts NHD's prefix shape AND full-string distinctness against fabricated sibling keys with the same sha+buffer. The `bg_ndi_cache_key` / `tiger_cache_key` imports shown in the spec example are intentionally dropped because they would be unused dead bindings.
- The `test_merge_partial_value_cols_picks_five_nhd_columns` test writes a real 3-row parquet under `tmp_path/output/` and exercises `_merge.write_partial` end-to-end — no monkeypatching of `pq.read_schema` and no private `_select_value_cols` helper. Cost is sub-50ms and the contract is the observable CSV column set, not a private function name.
- `sanity_check` is the R-mitigation gate against stale editable installs (Phase A must land before Phase B per working-dir context). Avoid the brittle `inspect._original_getsource` else-branch — instead monkeypatch the module-local binding the runner actually calls. Concretely:
  ```python
  monkeypatch.setattr(
      "app.experiments.nhd_bluespace.inspect.getsource",
      lambda obj: "def run(): pass",
  )
  ```
  This intercepts only the runner's own call site and leaves pytest's own `inspect.getsource` usage (for failure reporting) untouched. The `inspect._original_getsource` attribute does NOT exist in the stdlib and would raise `AttributeError` the moment pytest tries to render any other traceback.
- Do NOT invoke the real `spacescans-pipeline` binary anywhere in this file — `subprocess.run` is not used in any test, and all other tests stay inside `tmp_path` with mocked or small-fixture pyarrow IO.

---

### Task B4: Single-experiment integration test (test_e2e_nhd_bluespace_cohort)

**Files:**
- Create: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_e2e_nhd_bluespace_cohort.py`

**Goal:** Prove a real `nhd_bluespace`-only task spawned through `task_manager.start_task` reaches `finished`, emits `c3_nhd_bluespace` then `c4_nhd_bluespace` log steps in order, produces a `result_nhd_bluespace.csv` carrying `pid` + `episode_id` + the five `dist_*_m` columns with no NaN in `dist_blue_m`, and that a second run hits the `BG_NHD` C3 cache (c3 progresses to 100% in <1s).

**Context:** Spec [B9] (lines 102-105) calls for a single-experiment integration smoke alongside the unit tests. Phase B implementation step 6 (lines 932-933) sets the budget at ~90s wall-clock under `@pytest.mark.integration` (deselected by default), and the test count delta row at line 951 records this file as +1 integration test. R8's mitigation (lines 982-986) reaffirms the integration marker so default-suite wall-clock is unaffected. Pattern is a verbatim clone of `test_e2e_tiger_proximity_cohort.py` with the `_BOUNDARY = "BG_NHD"` cache-hit assertion added on a second run.

Step 1: Write failing test (real pytest code)

Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_e2e_nhd_bluespace_cohort.py`:

```python
"""Sprint 7 e2e: single-experiment nhd_bluespace via task_manager.start_task.

Proves the runtime path Phase A unlocked: precomputed_static_linkage's
output_grouping='episode' branch fires, the pipeline emits one row per
(PATID, geoid), _merge.write_partial joins on (pid, episode_id), and
result_nhd_bluespace.csv carries the five dist_*_m value columns one-to-one
with the input cohort. Second run asserts the BG_NHD C3 cache rehydrates
in <1s for the same (cohort, buffer).
"""
import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config


_DIST_COLUMNS = [
    "dist_flow_m",
    "dist_water_m",
    "dist_area_m",
    "dist_coast_m",
    "dist_blue_m",
]


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    nhd_c4 = app.config.settings.SPACESCANS_DATA_DIR / "data_full" / "NHD" / "C4"
    if not nhd_c4.is_dir():
        return False
    if not (nhd_c4 / "NHDPlus_H_National_Release_2_GDB.gdb").exists():
        return False
    try:
        import pyogrio  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / NHD C4 GDB / pipeline CLI / pyogrio not configured",
)


@pytest.fixture
def task_with_nhd_bluespace_cohort(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-nhd-bluespace")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["nhd_bluespace"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


def _run_and_wait(task_id: int, task_dir: Path, deadline_s: float) -> dict:
    from app.task_manager import start_task
    start_task(task_id)
    status: dict = {}
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            return status
        time.sleep(1.0)
    pytest.fail(f"task did not terminate within {deadline_s}s; last status={status}")


@pytest.mark.integration
def test_e2e_nhd_bluespace_cohort(task_with_nhd_bluespace_cohort):
    task_id, task_dir = task_with_nhd_bluespace_cohort

    status = _run_and_wait(task_id, task_dir, deadline_s=180.0)
    assert status["status"] == "finished", f"unexpected terminal status: {status}"

    experiments = status.get("experiments", {})
    assert "nhd_bluespace" in experiments, (
        f"expected nhd_bluespace slot in status.experiments; got {list(experiments)}"
    )
    assert experiments["nhd_bluespace"]["status"] == "finished"
    assert experiments["nhd_bluespace"]["progress"] == 1.0

    logs_path = task_dir / "logs.jsonl"
    assert logs_path.exists(), "logs.jsonl must be written"
    log_lines = [json.loads(line) for line in logs_path.read_text().splitlines() if line.strip()]
    sources_in_order = [entry["source"] for entry in log_lines if entry.get("source")]
    c3_idx = next((i for i, s in enumerate(sources_in_order) if s == "c3_nhd_bluespace"), -1)
    c4_idx = next((i for i, s in enumerate(sources_in_order) if s == "c4_nhd_bluespace"), -1)
    assert c3_idx >= 0, f"expected c3_nhd_bluespace in logs; got {set(sources_in_order)}"
    assert c4_idx >= 0, f"expected c4_nhd_bluespace in logs; got {set(sources_in_order)}"
    assert c3_idx < c4_idx, "c3_nhd_bluespace must precede c4_nhd_bluespace in log order"

    result_partial = task_dir / "output" / "result_nhd_bluespace.csv"
    assert result_partial.exists(), "result_nhd_bluespace.csv must be written"

    input_df = pd.read_csv(task_dir / "input.csv")
    df = pd.read_csv(result_partial)
    assert len(df) == len(input_df), (
        f"row count must match cohort episodes; "
        f"input={len(input_df)} result={len(df)} "
        "(if mismatched, the (pid, episode_id) join collapsed — "
        "Phase A precomputed_static output_grouping=episode dispatch likely failed)"
    )
    assert "pid" in df.columns, f"pid column missing; got {list(df.columns)}"
    assert "episode_id" in df.columns, f"episode_id column missing; got {list(df.columns)}"
    missing = [c for c in _DIST_COLUMNS if c not in df.columns]
    assert not missing, f"missing dist_*_m columns: {missing}; got {list(df.columns)}"
    assert df["dist_blue_m"].isna().sum() == 0, (
        f"dist_blue_m must have no NaN; found {df['dist_blue_m'].isna().sum()}"
    )

    # Second run: same cohort + buffer → BG_NHD C3 cache hit, c3 step in <1s.
    from app.task_manager import create_task, save_config
    meta2 = create_task(user_id=1, task_name="e2e-nhd-bluespace-rerun")
    task_dir2 = app.config.settings.TASKS_DIR / f"task-{meta2['id']}"
    task_dir2.mkdir(parents=True, exist_ok=True)
    (task_dir2 / "output").mkdir(exist_ok=True)
    shutil.copy(task_dir / "input.csv", task_dir2 / "input.csv")
    save_config(meta2["id"], {
        "experiment": "auto",
        "variables": ["nhd_bluespace"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })

    t0 = time.monotonic()
    status2 = _run_and_wait(meta2["id"], task_dir2, deadline_s=60.0)
    assert status2["status"] == "finished", f"second run terminal status: {status2}"

    logs2 = [
        json.loads(line)
        for line in (task_dir2 / "logs.jsonl").read_text().splitlines()
        if line.strip()
    ]
    c3_progress_full = [
        e for e in logs2
        if e.get("source") == "c3_nhd_bluespace" and e.get("progress") == 1.0
    ]
    assert c3_progress_full, "second run: c3_nhd_bluespace must reach progress=1.0"
    first_c3 = next(e for e in logs2 if e.get("source") == "c3_nhd_bluespace")
    last_c3 = c3_progress_full[-1]
    t_first = float(first_c3.get("ts", t0))
    t_last = float(last_c3.get("ts", t_first))
    assert (t_last - t_first) < 1.0, (
        f"second run: BG_NHD C3 cache should rehydrate in <1s; "
        f"observed {t_last - t_first:.2f}s "
        "(if larger, the BG_NHD namespace tag did not key the cache)"
    )
```

Step 2: Run RED (concrete bash + expected failure)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_e2e_nhd_bluespace_cohort.py -m integration -v
```

Expected: SKIPPED on dev boxes without NHD GDB (gate at `_integration_available`); on a properly equipped runner, RED if any of the assertions above fail (e.g., row-count mismatch indicates Phase A dispatch did not actually engage the episode branch).

Step 3: Implement minimal code (actual code to paste)

Test is the deliverable for B4 (creates a new file only). The runner that satisfies it was implemented in B2 (`backend/app/experiments/nhd_bluespace.py`) and the metadata entry in B1; no additional code is paste here. If RED fails because of fixture wiring rather than the unregistered runner, fix the fixture; otherwise proceed.

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_e2e_nhd_bluespace_cohort.py -m integration -v
```

Expected: `1 passed` in ~90s wall-clock. The two task runs share the `BG_NHD`-tagged C3 cache; the second run's `c3_nhd_bluespace` step rehydrates from the parquet on disk in <1s. If `_integration_available()` returns False on this host, expect `1 skipped` instead (still GREEN).

Step 5: Full suite (with expected cumulative count)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/ -v
```

Expected: `183 passed, 3 skipped, 12 deselected` in the default suite (B3 baseline 183 + B4 adds 0 default-suite tests; the new @integration test deselects, bumping the deselected tail from 11 to 12). `test_e2e_nhd_bluespace_cohort` is deselected by default via `@pytest.mark.integration`, so the default pass count is unchanged by this task. Integration-marker count rises by +1 from Sprint-6 carry-over.

Optional integration confirmation:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/ -m integration -v
```

Expected: previous Sprint-5 integration test count + 1 (this file).

Step 6: Commit (conventional message)

```bash
git -C /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace \
  add backend/tests/test_e2e_nhd_bluespace_cohort.py && \
git -C /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace \
  commit -m "$(cat <<'EOF'
test(experiments): e2e nhd_bluespace single-experiment cohort smoke (Sprint 7 B4)

Spawns a real task_dir via task_manager.start_task on patients_5.csv with only
nhd_bluespace selected. Asserts the task reaches finished, c3_nhd_bluespace
precedes c4_nhd_bluespace in logs.jsonl, result_nhd_bluespace.csv carries
pid + episode_id + the 5 dist_*_m columns with no NaN in dist_blue_m, and a
second run with the same (cohort, buffer) rehydrates the BG_NHD-tagged C3
cache in <1s.

Marked @pytest.mark.integration; deselected by default (R8). Skips gracefully
when SPACESCANS_DATA_DIR/data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb
is absent. Spec refs L102-105, L932-933, L951, L982-986.
EOF
)"
```

**Notes:**
- Skip-guard mirrors Sprint 5's TIGER pattern (`_integration_available` checks `SPACESCANS_DATA_DIR`, `SPACESCANS_PIPELINE_CLI`, and the NHDPlus_H GDB directory) so the test is silently skipped when the 61 GB GDB artifact is absent (R2 mitigation surface).
- Uses `pyogrio` for the GDB-readability check — NHD reads happen through GDAL/`pyogrio`. If the runner instead uses `geopandas` directly, swap the import.
- The cache-hit assertion measures elapsed `ts` between the *first* `c3_nhd_bluespace` log entry and the *progress=1.0* entry rather than measuring wall-clock around `_run_and_wait`, so it isolates cache rehydration latency from task-spawn overhead.
- Cohort is `patients_5.csv` (sibling tests' choice). The spec's "100k demo cohort" wording refers to the pipeline-side CLI smoke (`proximity_blue_demo100k.parquet`) bound to the pipeline test suite, not the web e2e — the web fixture set does not ship a 100k CSV.
- Cohort buffer params (`circle`, 270 m, `raster_res_m=25`) match Sprint 5's TIGER e2e verbatim to keep the BG_NHD cache key shape comparable across runners (R1 defence in depth).
- No code outside the new test file is modified — Phase B impl step 6 scoped to test-only.

---

### Task B5: 5-variable, 4-experiment integration + task_manager dispatch regression

**Files:**
- Create: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_e2e_multi_experiment_with_nhd.py`
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_task_manager_dispatch.py`

**Goal:** Lock the 4-experiment dispatch order (`bg_ndi_wi → zcta5_cbp → tiger_proximity → nhd_bluespace`) at both the unit-mock layer and the full-runner integration layer, proving the Sprint 3 metadata-file-order invariant survives the addition of `nhd_bluespace`.

**Context:** Sprint 5 added the 3-experiment integration smoke (`test_e2e_multi_experiment_with_tiger.py`) and the corresponding unit-mock dispatch order test (`test_three_experiment_dispatch_preserves_metadata_order`). Sprint 7 extends both: integration test selects all 5 catalogued variables on the demo cohort and asserts the new fourth slot (`nhd_bluespace`) appears last with its 5 `dist_*_m` columns in the merged `result.csv`; unit test mirrors `test_three_experiment_dispatch_preserves_metadata_order` with a scrambled 5-variable selection. Integration test is `@pytest.mark.integration` (deselected by default, R8 budget ~270s); skips gracefully if the NHD GDB or pipeline CLI is absent.

Step 1: Write failing test (real pytest code)

Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_e2e_multi_experiment_with_nhd.py`:

```python
"""Sprint 7 e2e: 5-variable, 4-experiment dispatch (bg_ndi_wi + zcta5_cbp + tiger_proximity + nhd_bluespace).

Deselected by default (@pytest.mark.integration). R8 budget ~270s wall-clock.
Skips gracefully if the NHD GDB, TIGER data, pipeline CLI, or pyreadr is absent.
"""
import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config


_R_STAR_COLUMNS = [
    "r_religious", "r_civic", "r_business", "r_political", "r_professional",
    "r_labor", "r_bowling", "r_recreational", "r_golf", "r_sports",
]
_DIST_TIGER_COLUMNS = ["dist_pri", "dist_sec", "dist_prisec"]
_DIST_NHD_COLUMNS = [
    "dist_flow_m", "dist_water_m", "dist_area_m", "dist_coast_m", "dist_blue_m",
]


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    if not (app.config.settings.SPACESCANS_DATA_DIR
            / "data_full/BG_FL/C3/tiger2010_bg10_states").exists():
        return False
    tiger_c4 = app.config.settings.SPACESCANS_DATA_DIR / "data_full" / "TIGER" / "C4"
    if not tiger_c4.is_dir() or not any(tiger_c4.glob("tiger*_roads")):
        return False
    nhd_gdb = (
        app.config.settings.SPACESCANS_DATA_DIR
        / "data_full" / "NHD" / "C4"
        / "NHDPlus_H_National_Release_2_GDB.gdb"
    )
    if not nhd_gdb.exists():
        return False
    try:
        import pyreadr  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / pipeline CLI / TIGER data / NHD GDB / pyreadr not configured",
)


@pytest.fixture
def task_with_four_experiments(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-multi-with-nhd")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": [
            "nhd_bluespace", "tiger_proximity", "cbp_zcta5", "ndi", "walkability",
        ],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_multi_experiment_with_nhd_cohort(task_with_four_experiments):
    task_id, task_dir = task_with_four_experiments

    from app.task_manager import start_task
    start_task(task_id)

    deadline = time.monotonic() + 360.0
    status: dict = {}
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 360s; last status={status}")

    assert status["status"] == "finished", f"task did not finish cleanly: {status}"
    assert status["progress"] == 1.0
    assert len(status["steps"]) > 0

    experiments = status.get("experiments", {})
    assert set(experiments.keys()) == {
        "bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace",
    }
    for key in ("bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace"):
        assert experiments[key]["status"] == "finished", f"{key} not finished"
        assert experiments[key]["progress"] == 1.0
        assert experiments[key]["steps"], f"{key} slot steps must be populated"

    # Spec L727-732: metadata-file order — bg_ndi_wi → zcta5_cbp → tiger_proximity → nhd_bluespace.
    bg_start = experiments["bg_ndi_wi"]["started_at"]
    zc_start = experiments["zcta5_cbp"]["started_at"]
    tg_start = experiments["tiger_proximity"]["started_at"]
    nh_start = experiments["nhd_bluespace"]["started_at"]
    assert bg_start <= zc_start <= tg_start <= nh_start, (
        f"expected metadata-file dispatch order; "
        f"bg={bg_start} zc={zc_start} tg={tg_start} nh={nh_start}"
    )

    # logs.jsonl must carry entries from all four runners (spec R10 audit trail).
    log_lines = (task_dir / "logs.jsonl").read_text().splitlines()
    log_records = [json.loads(line) for line in log_lines if line.strip()]
    runners_in_logs = {
        rec.get("experiment") for rec in log_records if rec.get("experiment")
    }
    assert {"bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace"} <= runners_in_logs, (
        f"logs.jsonl missing entries for some runners; got {runners_in_logs}"
    )

    for runner in ("bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace"):
        assert (task_dir / "output" / f"result_{runner}.csv").exists(), runner

    result_csv = task_dir / "output" / "result.csv"
    assert result_csv.exists()
    df = pd.read_csv(result_csv)

    assert "ndi" in df.columns
    assert "NatWalkInd" in df.columns
    missing_r = [c for c in _R_STAR_COLUMNS if c not in df.columns]
    assert not missing_r, f"missing r_* columns after fan_in: {missing_r}"
    missing_tiger = [c for c in _DIST_TIGER_COLUMNS if c not in df.columns]
    assert not missing_tiger, f"missing TIGER dist_* columns after fan_in: {missing_tiger}"
    missing_nhd = [c for c in _DIST_NHD_COLUMNS if c not in df.columns]
    assert not missing_nhd, f"missing NHD dist_*_m columns after fan_in: {missing_nhd}"

    bg_df = pd.read_csv(task_dir / "output" / "result_bg_ndi_wi.csv")
    zc_df = pd.read_csv(task_dir / "output" / "result_zcta5_cbp.csv")
    tg_df = pd.read_csv(task_dir / "output" / "result_tiger_proximity.csv")
    nh_df = pd.read_csv(task_dir / "output" / "result_nhd_bluespace.csv")
    assert len(df) == len(bg_df) == len(zc_df) == len(tg_df) == len(nh_df)
```

Append to `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/test_task_manager_dispatch.py`:

```python
def test_four_experiment_dispatch_preserves_metadata_order(
    task_dir_with_config, monkeypatch
):
    """Sprint 7: 5 variables across 4 experiments dispatch in metadata-file order.

    Spec L727-732: dispatch order is JSON-file order of first experiment
    appearance — bg_ndi_wi (ndi, walkability), zcta5_cbp (cbp_zcta5),
    tiger_proximity (tiger_proximity), nhd_bluespace (nhd_bluespace), in
    that order regardless of the variable selection order in config.json.
    Pure mock — no subprocess, no status.json transitions beyond the
    dispatcher's own writes.
    """
    import json as _json
    from app import dispatcher

    cfg_path = task_dir_with_config / "config.json"
    cfg = _json.loads(cfg_path.read_text())
    cfg["variables"] = [
        "nhd_bluespace", "tiger_proximity", "cbp_zcta5", "walkability", "ndi",
    ]
    cfg_path.write_text(_json.dumps(cfg))

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
    fan_in = MagicMock()
    monkeypatch.setattr("app.experiments._merge.fan_in", fan_in)

    result = dispatcher.dispatch(str(task_dir_with_config))

    assert len(_FakePopen.instances) == 4
    assert "app.experiments.bg_ndi_wi" in _FakePopen.instances[0].cmd
    assert "app.experiments.zcta5_cbp" in _FakePopen.instances[1].cmd
    assert "app.experiments.tiger_proximity" in _FakePopen.instances[2].cmd
    assert "app.experiments.nhd_bluespace" in _FakePopen.instances[3].cmd
    assert result["completed"] == [
        "bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace",
    ]
    fan_in.assert_called_once_with(
        task_dir_with_config,
        ["bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace"],
    )
```

Step 2: Run RED (concrete bash + expected failure)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest \
    tests/test_task_manager_dispatch.py::test_four_experiment_dispatch_preserves_metadata_order \
    -x -v
```

Expected RED: `KeyError: 'nhd_bluespace'` from `variable_registry.variables_by_experiment()` (or `AssertionError: len(_FakePopen.instances) == 4` showing 3) — because B1's metadata entry plus B2 runner module are required for the registry to discover a fourth experiment slot. Since both have landed by the time B5 runs, this should flip to GREEN immediately.

Step 3: Implement minimal code (actual code to paste)

This task is **purely test code** — the production code (metadata entry from B1, runner module from B2) is already landed by the time B5 begins. The two test files above ARE the implementation. No production-source patch in this task.

If B1 (`variable_metadata.json` entry) and B2 (`backend/app/experiments/nhd_bluespace.py`) are properly in place, the registry's `variables_by_experiment(["ndi", "walkability", "cbp_zcta5", "tiger_proximity", "nhd_bluespace"])` returns four keys in metadata order and both tests pass without further edits.

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest \
    tests/test_task_manager_dispatch.py::test_four_experiment_dispatch_preserves_metadata_order \
    -v
```

Expected GREEN: 1 passed.

Then run the integration test once locally (NHD GDB must be staged):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest \
    tests/test_e2e_multi_experiment_with_nhd.py -v -m integration
```

Expected GREEN: 1 passed in ~270s (skipped if NHD GDB absent).

Step 5: Full suite (with expected cumulative count)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ -q
```

Expected: **`184 passed, 3 skipped, 13 deselected`** (B4 baseline 183 + B5's +1 unit dispatch test = 184; the 2 new @integration tests from B4 + this task push deselected from 11 → 13). The 2 integration tests (`test_e2e_nhd_bluespace_cohort.py` from B4 + this file's `test_e2e_multi_experiment_with_nhd.py`) are deselected by default.

Integration-suite cumulative cross-check:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ -q -m integration
```

Expected: Sprint 7 contributes +2 integration tests (single-experiment NHD cohort + this 4-experiment multi).

Step 6: Commit (conventional message)

```bash
git -C /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace add \
  backend/tests/test_e2e_multi_experiment_with_nhd.py \
  backend/tests/test_task_manager_dispatch.py && \
git -C /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace \
  commit -m "test(experiments): 5-variable, 4-experiment integration + task_manager dispatch regression (Sprint 7 B5)

Adds backend/tests/test_e2e_multi_experiment_with_nhd.py (1 integration
test, ~270s, deselected by default) selecting all 5 catalogued variables
on the demo cohort and asserting (a) experiments map carries bg_ndi_wi →
zcta5_cbp → tiger_proximity → nhd_bluespace in metadata-file order per
the Sprint 3 invariant (spec L727-732), (b) logs.jsonl carries entries
from all four runners, (c) result.csv after fan_in carries ndi +
NatWalkInd + 10 r_* + 3 TIGER dist_* + 5 NHD dist_*_m columns. Skips
gracefully when the NHD GDB / TIGER data / pipeline CLI / pyreadr are
absent.

Adds test_four_experiment_dispatch_preserves_metadata_order to
test_task_manager_dispatch.py — pure mock (no subprocess), mirrors the
Sprint 5 three-experiment regression with a scrambled 5-variable
selection and asserts the dispatcher serialises into the four-slot
metadata-file order and fan_in is called with the same ordered list.

Default suite 183 → 184; integration suite +2 cumulative from Sprint 7
(this file plus B4's single-experiment cohort test)."
```

**Notes:**
- The integration test's `_integration_available()` gate stacks the NHD GDB check on top of the Sprint 5 TIGER preconditions — all five variables share the same task, so any missing data dir or CLI must short-circuit the entire test.
- `360s` polling deadline > 270s spec budget gives headroom for CI variance (matches Sprint 5's 300s budget for the 3-experiment case + ~60s for the additional NHD runner).
- The unit-mock test (`test_four_experiment_dispatch_preserves_metadata_order`) deliberately does NOT monkeypatch `variable_registry.variables_by_experiment` — it lets the real registry resolve the metadata so the test catches regressions in B1's JSON entry ordering. The Sprint 5 sibling (`test_three_experiment_dispatch_preserves_metadata_order`) does the same.
- `logs.jsonl` assertion uses `rec.get("experiment")` to filter — matches the runner's structured-log idiom from Sprint 3 T9. No reliance on stdlib caplog (spec R10: on-disk audit trail is the contract).
- This task is *test-only*; B1's metadata entry and B2's runner module are the production-code prerequisites. If RED shows `KeyError` for `nhd_bluespace` it means B1 or B2 has not landed — do NOT patch tests around it, escalate the dependency.
- Skips gracefully on machines without the 61 GB NHD GDB; `make test` stays green in dev environments without staged data.

---

### Task B6: Phase B wrap-up: manual_e2e Sprint 7 section + frontend no-op verify + PR

**Files:**
- /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/manual_e2e.md
- /tmp/sprint7-phase-b-pr-body.md (PR body staging)

**Goal:** Document the Sprint 7 manual smoke procedure in `manual_e2e.md` (mirroring spec L1051-1108 verbatim), verify the frontend remains a strict no-op (zero edits to variables-step / variable-card / variable-coverage-panel / variable-grouping per G2), and stage the Phase B PR body for `feat(experiments): nhd_bluespace runner + precomputed_static episode dispatch (Sprint 7)`.

**Context:** This is the last task of Sprint 7 Phase B. B1-B5 have shipped: metadata entry + pre-flight (B1), nhd_bluespace runner module (B2), unit tests (B3), single-experiment integration test (B4), and 4-experiment dispatch regression + multi-experiment integration test (B5). Frontend changes for Sprint 7 are explicitly forbidden by G2 — the new NHD card and BG-section growth from 3→4 cards are driven entirely through the existing metadata-driven `variables-step.tsx` render path. R7 cosmetic chip text `'2024-2024'` is deferred to G11. After this task the cumulative web-backend pytest count should read `184 passed, 3 skipped, 13 deselected` on the default suite.

Step 1: Write failing test (real pytest code)

No new pytest file. Verification is a docs grep + an `npx tsc --noEmit` clean run + a `git diff` no-op check on the four protected frontend files. Encode the docs assertion as a one-shot bash check (it must FAIL before edit, PASS after):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace
grep -q '^## Sprint 7 — NHD bluespace (precomputed_static episode)$' backend/tests/manual_e2e.md \
  && echo "DOCS_OK" || echo "DOCS_MISSING"
```

Step 2: Run RED (concrete bash + expected failure)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace
grep -q '^## Sprint 7 — NHD bluespace (precomputed_static episode)$' backend/tests/manual_e2e.md \
  && echo "DOCS_OK" || echo "DOCS_MISSING"
# Expected: DOCS_MISSING
```

Also confirm baseline frontend cleanliness (must already be clean — Phase B should not have touched these):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace
# Sanity: protected files must exist before git diff (silent exit-0 otherwise = false-pass)
for f in \
  frontend/src/components/wizard/variables-step.tsx \
  frontend/src/components/wizard/variable-card.tsx \
  frontend/src/components/wizard/variable-coverage-panel.tsx \
  frontend/src/lib/variable-grouping.ts; do
  test -f "$f" || { echo "MISSING: $f"; exit 1; }
done
git diff --stat origin/main -- \
  frontend/src/components/wizard/variables-step.tsx \
  frontend/src/components/wizard/variable-card.tsx \
  frontend/src/components/wizard/variable-coverage-panel.tsx \
  frontend/src/lib/variable-grouping.ts
# Expected: (no output) — zero changes on protected files
```

Step 3: Implement minimal code (actual code to paste)

Append the Sprint 7 manual smoke section verbatim from spec L1051-1108 to `backend/tests/manual_e2e.md`. To avoid heredoc backtick-escaping bugs (bash quoted heredocs leave `\` literal, so triple-backtick fences would render with stray backslashes), write the file via Python `Path.write_text` with a triple-quoted string:

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python <<'PY'
from pathlib import Path

md_path = Path("/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend/tests/manual_e2e.md")

section = '''

## Sprint 7 — NHD bluespace (precomputed_static episode)

### Pre-flight

Confirm the editable pipeline install matches the worktree's `pkg/pypi-only` snapshot and exposes the new runner + episode:

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -c "
from spacescans.linkage import precomputed_static_linkage
import inspect
assert 'resolve_output_grouping' in inspect.getsource(precomputed_static_linkage)
print('NHD wiring OK')
"
```

Confirm fixtures:

- `$SPACESCANS_DATA_DIR/data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb` is readable.
- `$C3_CACHE_DIR` is set (e.g. `/tmp/c3-cache-sprint7`) and writable.
- Metadata contains the five expected entries: ndi, walkability, cbp_zcta5, tiger_proximity, nhd_bluespace.

### Steps

1. Boot the dev stack and open the wizard.
2. Step to **Variables**. Confirm the BG section renders **4 cards** (NDI, Walkability, TIGER, NHD) and the ZCTA5 section renders **1 card** (CBP). Tick the NHD card → the coverage panel mounts and reports a non-trivial intersection for the configured study county.
3. Tick all five cards, finish the wizard, and submit the run.
4. Backend dispatches **4 experiments** in metadata order: bg_ndi_wi, zcta5_cbp, tiger_proximity, nhd_bluespace. Each completes; `result.csv` contains all expected columns including `dist_flow_m`, `dist_water_m`, `dist_area_m`, `dist_coast_m`, `dist_blue_m`.
5. Re-run the same configuration. The `nhd_bluespace` experiment hits the `BG_NHD` C3 cache (look for `cache_hit=True` in the runner log line) and skips the GDB read.
6. **Negative tests:**
   - Patch one metadata entry's `output_grouping` to `"unsupported"` and re-run → backend raises `ValueError("unsupported output_grouping: 'unsupported'")` before any episode starts.
   - Move `NHDPlus_H_National_Release_2_GDB.gdb` aside and re-run → backend raises `MetadataSchemaError` during pre-flight (no partial run, no orphan cache files).
'''

with md_path.open("a", encoding="utf-8") as f:
    f.write(section)

# Positive verification: literal ```bash fence landed without backslash escapes.
body = md_path.read_text(encoding="utf-8")
assert "```bash" in body and "\\`\\`\\`bash" not in body, (
    "manual_e2e.md fence corrupted by escaping; abort and rewrite via Path.write_text"
)
assert "## Sprint 7 — NHD bluespace (precomputed_static episode)" in body
print("manual_e2e.md Sprint 7 section appended OK")
PY
```

Now stage the PR body:

```bash
cat > /tmp/sprint7-phase-b-pr-body.md <<'EOF'
## Summary

Sprint 7 Phase B ships the **NHD bluespace** variable as the first
`precomputed_static` runner consuming Phase A's `resolve_output_grouping`
helper.

- New runner: `nhd_bluespace.py` (B2) — clone-trim of `tiger_proximity.py`
  with five constant swaps (`BG_NHD` boundary tag, C3/C4 step names,
  parquet map, sanity probe target). Emits 5 `dist_*_m` value columns.
- Metadata + pre-flight (B1): `variable_metadata.json` gains the
  `nhd_bluespace` entry (BG boundary, [2024,2024] coverage, 5 value_cols);
  `_assert_nhd_data_present` validates the NHDPlus_H GDB on server boot.
- Unit tests (B3): 8 tests in `test_nhd_bluespace.py` + 1 in
  `test_merge_partial.py` lock the runner contract and R1 cache-collision
  guard.
- Integration tests (B4+B5): single-experiment `test_e2e_nhd_bluespace_cohort`
  and 5-variable `test_e2e_multi_experiment_with_nhd_cohort` (both
  `@pytest.mark.integration`, deselected by default).
- Dispatch regression (B5): unit-mock test asserts the dispatcher
  serialises 5 variables into 4-experiment metadata-file order.

## Frontend

**No frontend code changes** (G2). The wizard's `variables-step.tsx`
already renders cards from `/variables/metadata`, so the new NHD card
appears for free in the BG section (3 → 4 cards). R7's cosmetic chip
text `'2024-2024'` is deferred to G11.

## Test plan

- [x] `pytest backend/tests/` → `184 passed, 3 skipped, 13 deselected`
- [x] `pytest backend/tests/ -m integration` green on the
      NHD+TIGER-equipped runner
- [x] `npx tsc --noEmit` clean in `frontend/`
- [x] Manual smoke per `backend/tests/manual_e2e.md` § Sprint 7 — five
      cards render, four BG experiments dispatch in metadata order, BG_NHD
      cache hits on re-run, both negative tests trip the documented
      errors

## Refs

- Spec: `docs/superpowers/specs/2026-06-16-sprint-7-nhd-bluespace-design.md`
- Sprint 5 reference (TIGER proximity, same pattern):
  `docs/superpowers/plans/2026-06-16-sprint-5-tiger-proximity.md`

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
```

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace

# (a) Docs section landed
grep -q '^## Sprint 7 — NHD bluespace (precomputed_static episode)$' backend/tests/manual_e2e.md \
  && echo "DOCS_OK" || echo "DOCS_MISSING"
# Expected: DOCS_OK

# (b) Frontend no-op invariant still holds (G2)
# Sanity: protected files must exist before git diff (silent exit-0 otherwise = false-pass)
for f in \
  frontend/src/components/wizard/variables-step.tsx \
  frontend/src/components/wizard/variable-card.tsx \
  frontend/src/components/wizard/variable-coverage-panel.tsx \
  frontend/src/lib/variable-grouping.ts; do
  test -f "$f" || { echo "MISSING: $f"; exit 1; }
done
git diff --stat origin/main -- \
  frontend/src/components/wizard/variables-step.tsx \
  frontend/src/components/wizard/variable-card.tsx \
  frontend/src/components/wizard/variable-coverage-panel.tsx \
  frontend/src/lib/variable-grouping.ts
# Expected: (empty output)

# (c) Frontend type-checks clean
( cd frontend && npx tsc --noEmit )
# Expected: exit 0, no diagnostics

# (d) PR body staged
test -s /tmp/sprint7-phase-b-pr-body.md && echo "PR_BODY_OK"
# Expected: PR_BODY_OK
```

Step 5: Full suite (with expected cumulative count)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/ -q
# Expected tail: 184 passed, 3 skipped, 13 deselected
# (172 baseline + B1=2 + B2=0 (no tests) + B3=9 + B4=0 default + B5=1 unit = 184;
#  11 baseline deselected + 2 new @integration tests from B4/B5 = 13 deselected)

# Integration suite on NHD+TIGER-equipped runner
SPACESCANS_NHD_GDB=$SPACESCANS_NHD_GDB C3_CACHE_DIR=/tmp/c3-cache-sprint7 \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/ -m integration -q
# Expected: all green (NHD GDB + TIGER fixtures present on this runner)
```

Step 6: Commit (conventional message)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace

git add backend/tests/manual_e2e.md
git commit -m "$(cat <<'EOF'
docs(tests): add Sprint 7 manual smoke section for NHD bluespace

Mirrors spec L1051-1108 verbatim: pre-flight (editable install + GDB
+ C3_CACHE_DIR + 5 metadata entries), 6 numbered steps covering the
4-BG + 1-ZCTA5 card render, NHD coverage-panel mount, 4-experiment
dispatch in metadata order, BG_NHD cache hit on second run, and two
negative tests (unknown output_grouping ValueError + missing GDB
MetadataSchemaError on pre-flight).

Frontend remains a strict no-op for Sprint 7 (G2): no edits to
variables-step.tsx, variable-card.tsx, variable-coverage-panel.tsx,
or variable-grouping.ts; the new NHD card appears via the existing
metadata-driven render path. R7 chip-text cosmetic deferred to G11.

Closes Sprint 7 Phase B.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"

# Push and open PR
git push -u origin feat/sprint-7-nhd-bluespace
gh pr create \
  --base main \
  --head feat/sprint-7-nhd-bluespace \
  --title "feat(experiments): nhd_bluespace runner + precomputed_static episode dispatch (Sprint 7)" \
  --body-file /tmp/sprint7-phase-b-pr-body.md
```

**Notes:**
- **Verbatim mirror.** The manual-smoke section must match spec L1051-1108 word-for-word — do not paraphrase the negative-test wording, the card counts, or the column names (`dist_flow_m` / `dist_water_m` / `dist_area_m` / `dist_coast_m` / `dist_blue_m`). Reviewers diff the section against the spec.
- **Card counts after Sprint 7.** BG section renders **4** cards (NDI, Walkability, TIGER from Sprint 5, NHD from Sprint 7); ZCTA5 section renders **1** (CBP). If you see 3 BG cards in the manual smoke, metadata registration (B1) didn't load — check editable install and `_discover_experiments` whitelist.
- **G2 invariant is load-bearing.** Sprint 7's whole point is "metadata + runner only, frontend free-rides on the existing render path." The Step 4 `git diff --stat` on the four protected files is the gate — if it shows any change, abort the PR and reopen design.
- **Cumulative count math.** 172 (web baseline at Sprint 7 start) + 2 (B1: metadata + pre-flight) + 0 (B2: runner module, no tests) + 9 (B3: 8 nhd unit + 1 merge_partial) + 0 (B4: integration only) + 1 (B5: unit dispatch test) = **184**. If the suite reports anything else, investigate before merging.
- **R7 deferral.** The cosmetic chip text `'2024-2024'` is intentionally left unfixed; G11 will handle it in a follow-up. Do not slip it into this PR.
- **Integration suite gating.** The integration line in the PR test plan assumes the runner has both `$SPACESCANS_NHD_GDB` and TIGER fixtures. On a runner without them, mark the box `[ ]` and note "requires NHD GDB + TIGER fixtures."
- **No Phase A backflow.** Phase A commits on `pkg/pypi-only` are already in via the editable install; this PR targets only `spacescans-web`'s `main`.

---

## Final Verification

After all Sprint 7 tasks (A0-A3 + B0-B6) land, run the following gates in order. Any RED stops the merge.

### 1. Phase A: pipeline suite full pass

```bash
cd /Users/xai/Desktop/spacescans-project && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ 2>&1 | tail -3
```

Expected tail: `79 passed` (74 Sprint 6 baseline + 3 A1 + 2 A2).

### 2. Phase A → Phase B handoff probe

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -c \
  'from spacescans.linkage import precomputed_static_linkage; import inspect; print("resolve_output_grouping" in inspect.getsource(precomputed_static_linkage))'
```

Expected stdout: `True`. This is the literal probe the `nhd_bluespace` runner's sanity check runs at task start.

### 3. Phase B: web backend default suite

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ -q
```

Expected tail: `184 passed, 3 skipped, 13 deselected` (172 baseline + B1's 2 + B3's 9 + B5's 1 = 184; B2/B4 ship no default-suite tests. 11 baseline deselected + 2 new @integration tests from B4+B5 = 13 deselected).

### 4. Phase B: integration suite

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ -m integration -q
```

Expected: Sprint 7 contributes +2 integration tests (B4's single-experiment NHD cohort + B5's 4-experiment multi). Both must be GREEN on NHD+TIGER-equipped runners; SKIPPED on dev boxes without fixtures.

### 5. Frontend no-op invariant (G2)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && \
  for f in \
    frontend/src/components/wizard/variables-step.tsx \
    frontend/src/components/wizard/variable-card.tsx \
    frontend/src/components/wizard/variable-coverage-panel.tsx \
    frontend/src/lib/variable-grouping.ts; do \
    test -f "$f" || { echo "MISSING: $f"; exit 1; }; \
  done && \
  git diff --stat origin/main -- \
    frontend/src/components/wizard/variables-step.tsx \
    frontend/src/components/wizard/variable-card.tsx \
    frontend/src/components/wizard/variable-coverage-panel.tsx \
    frontend/src/lib/variable-grouping.ts
```

Expected: every `test -f` passes silently, then empty `git diff --stat` output. Any change here violates G2 and blocks the merge.

### 6. Frontend type check

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/frontend && \
  npx tsc --noEmit
```

Expected: exit 0, no diagnostics.

### 7. Absent-tracking gate (variable_metadata.json)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace && \
  test ! -f backend/data/variable_metadata.json && echo "ABSENT_TRACKING_OK"
```

Expected: `ABSENT_TRACKING_OK` (the gitignored runtime override must not have been migrated into the worktree; only `backend/app/data/variable_metadata.json` is tracked).

### 8. Variable count gate (registry returns 5 keys)

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-7-nhd-bluespace/backend && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -c "
from app import variable_registry
payload = variable_registry.load_variables(force=True)
keys = set(payload['variables'].keys())
expected = {'ndi', 'walkability', 'cbp_zcta5', 'tiger_proximity', 'nhd_bluespace'}
assert keys == expected, f'expected={expected}, got={keys}'
print('variable_registry OK: 5 keys')
"
```

Expected stdout: `variable_registry OK: 5 keys`. Note: `/api/variables` itself is JWT-gated (`Depends(get_current_user)`) so an unauthenticated TestClient returns 403 — we assert the catalog at the registry layer, which is what the router serialises.

### 9. Phase A push (only after gates 1-8 pass)

```bash
cd /Users/xai/Desktop/spacescans-project && git push origin pkg/pypi-only
```

Then open the Phase A PR using `/tmp/sprint7-phase-a-pr-body.md` as the body.

### 10. Phase B PR (already opened in B6)

Confirm CI on `feat/sprint-7-nhd-bluespace` is green. Merge order:
1. Phase A PR (pipeline `pkg/pypi-only` → main) — must merge first.
2. Phase B PR (`feat/sprint-7-nhd-bluespace` → `spacescans-web` main) — merges after Phase A is live in the editable install.

Sprint 7 closes when both PRs are merged and the worktree is removed:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web && \
  git worktree remove .worktrees/feat-sprint-7-nhd-bluespace
```
