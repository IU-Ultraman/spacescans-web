# Sprint 5: TIGER Proximity + precomputed_areal Phase A Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Add tiger_proximity as the third experiment runner in the metadata-driven catalog. Phase A audits the pipeline's precomputed_areal linkage_pattern for output_grouping dispatch (mirror of Sprint 2 Phase A for yearly_areal). Phase B adds the web-side runner + metadata entry + integration tests.

**Architecture:** Cross-repo. Phase A modifies spacescans-pipeline branch pkg/pypi-only (precomputed_areal_linkage.py SQL dispatch + new pipeline tests). Phase B modifies spacescans-web on a fresh feat/sprint-5-tiger-proximity branch (new experiments/tiger_proximity.py + variable_metadata entry + frontend stays untouched). Editable install bridges Phase A → Phase B once Phase A is committed to pkg/pypi-only.

**Spec:** docs/superpowers/specs/2026-06-16-sprint-5-tiger-proximity-design.md (873 lines, committed 77adddc)

**Phase A base branch:** pkg/pypi-only (pipeline checkout /Users/xai/Desktop/spacescans-project)
**Phase B base branch:** main (spacescans-web — Sprint 4 merged at 165847a)

**Phase A baseline:** 64 pipeline tests pass (Sprint 2 Phase A close-out)
**Phase B baseline:** 139 web backend tests pass

## Table of Contents

### Phase A (pipeline, branch pkg/pypi-only)
- [Task A0: Pipeline pre-flight: verify env, TIGER fixture, baseline tests](#task-a0-pipeline-pre-flight-verify-env-tiger-fixture-baseline-tests)
- [Task A1: precomputed_areal_linkage.py output_grouping dispatch (RED → GREEN)](#task-a1-precomputed_areal_linkagepy-output_grouping-dispatch-red--green)
- [Task A2: tiger_roads_demo.yaml + pipeline smoke (explicit episode declaration)](#task-a2-tiger_roads_demoyaml--pipeline-smoke-explicit-episode-declaration)
- [Task A3: Phase A wrap-up: regression sweep, commit, publish for Phase B](#task-a3-phase-a-wrap-up-regression-sweep-commit-publish-for-phase-b)

### Phase B (web, branch feat/sprint-5-tiger-proximity)
- [Task B0: Web worktree setup on feat/sprint-5-tiger-proximity + Phase A handoff verify](#task-b0-web-worktree-setup-on-featsprint-5-tiger-proximity--phase-a-handoff-verify)
- [Task B1: variable_metadata.json tiger_proximity entry + schema/registry RED→GREEN](#task-b1-variable_metadatajson-tiger_proximity-entry--schemaregistry-redgreen)
- [Task B2: experiments/tiger_proximity.py runner (clone-trim of bg_ndi_wi)](#task-b2-experimentstiger_proximitypy-runner-clone-trim-of-bg_ndi_wi)
- [Task B3: tiger_proximity unit tests (8 tests, mirror zcta5_cbp coverage)](#task-b3-tiger_proximity-unit-tests-8-tests-mirror-zcta5_cbp-coverage)
- [Task B4: Single-experiment integration test (test_e2e_tiger_proximity_cohort)](#task-b4-single-experiment-integration-test-test_e2e_tiger_proximity_cohort)
- [Task B5: 3-experiment dispatch integration + task_manager regression](#task-b5-3-experiment-dispatch-integration--task_manager-regression)
- [Task B6: Phase B wrap-up: manual_e2e Sprint 5 section + frontend no-op verify + PR](#task-b6-phase-b-wrap-up-manual_e2e-sprint-5-section--frontend-no-op-verify--pr)

### Final verification
- [Final verification](#final-verification)

---

## Canonical test-count tally (single source of truth)

Every Step 5 "Full suite" expected count below MUST be derived from this table, not re-computed inline. If you find drift between this table and any task body, the table wins — surface the discrepancy to the controller.

**Pipeline baseline (pre-Sprint-5, branch `pkg/pypi-only`):** `64 passed` (52 Sprint 1 + 12 Sprint 2 Phase A).

| Pipeline task | tests added | new file / modified | running default count |
|---------------|-------------|---------------------|----------------------|
| A0            | 0           | (none)              | 64                   |
| A1            | +3          | `tests/test_precomputed_areal_linkage.py` (new) | 67                   |
| A2            | +2          | `tests/test_pipeline_smoke.py` (modify — adds shipped-YAML static assertion + per-episode row-count smoke) | 69                   |
| A3            | 0           | (none — verification only) | 69                   |

**Web baseline (pre-Sprint-5, branch `main` at 165847a):** captured verbatim in B0 Step 5 with `pytest -q | tail -1`. Treat the literal output string pinned in B0 Step 5 as the immovable baseline for all subsequent task expected counts. The numeric tuple expected on the current main is `139 passed, 2 skipped, 9 deselected` — if `pytest -q | tail -1` reports anything else on B0 Step 5, STOP and re-pin every later task's expected count by the delta from the actual baseline.

| Web task | unit tests added | integration tests added | new file / modified | running default count | running integration count |
|----------|------------------|-------------------------|---------------------|----------------------|---------------------------|
| B0       | 0                | 0                       | (worktree setup only — transient guard deleted before commit) | 139 | 0 |
| B1       | +1               | 0                       | `backend/tests/test_variable_registry.py` (modify — one new test; existing `test_list_experiments_dedupes_in_file_order` is rewritten in place to a transitional `pytest.raises(MetadataSchemaError)` assertion, not counted as a +1) | 140 | 0 |
| B2       | 0                | 0                       | `backend/app/experiments/tiger_proximity.py` (new; runner only, no test delta) | 140 | 0 |
| B3       | +9               | 0                       | `backend/tests/test_tiger_proximity.py` (new, +8); `backend/tests/test_merge_partial.py` (modify, +1) | 149 | 0 |
| B4       | 0                | +1                      | `backend/tests/test_e2e_tiger_proximity_cohort.py` (new; `@pytest.mark.integration` — deselected by default) | 149 | 1 |
| B5       | +1               | +1                      | `backend/tests/test_e2e_multi_experiment_with_tiger.py` (new integration); `backend/tests/test_task_manager_dispatch.py` (modify — +1 unit) | 150 | 2 |
| B6       | 0                | 0                       | `backend/tests/manual_e2e.md` (modify — docs only) | 150 | 2 |

**Phase B totals:** +11 unit tests (default suite), +2 integration tests (deselected by default). Final default-suite expected: `150 passed, 2 skipped, <N> deselected` where `<N>` is the B0-Step-5 deselect baseline plus 2 (the two new `@pytest.mark.integration` files added in B4/B5). Final integration-suite expected on a TIGER-equipped runner: Sprint-3 carry-over + 2 new = all pass.

NOTE on `skipped` / `deselected` counts: the baseline tuple is `2 skipped, 9 deselected` per pinned B0 Step 5. Skip count is stable across Sprint 5 (no new fixture-gated skips are added). Deselect count rises by exactly 2 (from 9 → 11) once B4 and B5 each add an `@pytest.mark.integration` file. If a task's body cites a different `skipped`/`deselected` number than this paragraph predicts, the body is stale.

---

## Phase A — Pipeline (branch `pkg/pypi-only`)

### Task A0: Pipeline pre-flight: verify env, TIGER fixture, baseline tests

**Files:**
- (none — read-only verification; no code or test changes)

**Goal:** Confirm the `spacescans-project` pipeline checkout on `pkg/pypi-only` is clean, editable-installed at `/Users/xai/Desktop/spacescans-project/src/spacescans`, has the C3/C4 TIGER configs + `annual_proximity_demo100k.parquet` + `cache/C3/tiger_roads_filtered/` present, and captures the 64-test pytest baseline so Phase A's later tasks can prove they add tests without regressing `yearly_areal` / `yearly_areal_bg_vintage` / `static_areal`.

**Context:** Phase A's runtime work (Tasks A1–A2) will edit `src/spacescans/linkage/precomputed_areal_linkage.py` and `configs/c4/tiger_roads_demo.yaml`, and add `tests/test_precomputed_areal_linkage.py` + a `tiger_roads_demo` smoke in `tests/test_pipeline_smoke.py`. Those edits assume (a) the pipeline source on disk *is* the source the test runner imports, (b) the `cache/C3/tiger_roads_filtered/` per-county shapefile cache is already warm so smoke tests don't have to filter ~3000 zips on first run, and (c) the existing 64-test green baseline is reproducible. Task A0 verifies all three with read-only commands and records the baseline; it touches no source, tests, or configs.

- [ ] **Step 1: Write failing test**

No test code is written in A0. The verification artefact is a captured baseline number, not a pytest assertion. (Sprint 2's Task A0 followed the same convention: worktree/baseline setup is a pre-flight step, not a TDD cycle.)

- [ ] **Step 2: Run RED**

```bash
cd /Users/xai/Desktop/spacescans-project
git status --short
git log --oneline -3
git branch --show-current
```

Expected output:
- `git status --short`: only `?? spacescans-web/` (the nested web checkout is untracked and unrelated to Phase A).
- `git log --oneline -3` includes `3e9841c Merge feat/output-grouping-per-episode for Sprint 2 Phase A`.
- `git branch --show-current` prints `pkg/pypi-only`.

Stop and ask the controller to stash if any *tracked* file shows ` M` or `??` other than `spacescans-web/`.

- [ ] **Step 3: Implement minimal code**

No source edits. Run the four pre-flight checks below verbatim:

```bash
# 3a. Editable install resolves to the live source tree
/Users/xai/miniconda3/envs/spacescans/bin/python -c \
  "import spacescans; assert spacescans.__file__ == '/Users/xai/Desktop/spacescans-project/src/spacescans/__init__.py', spacescans.__file__; print('editable OK:', spacescans.__file__)"

# 3b. Phase A target file + C4 config + C3 seed config are on disk
test -f /Users/xai/Desktop/spacescans-project/src/spacescans/linkage/precomputed_areal_linkage.py
test -f /Users/xai/Desktop/spacescans-project/configs/c4/tiger_roads_demo.yaml
test -f /Users/xai/Desktop/spacescans-project/configs/c3/tiger_roads_demo.yaml
echo "configs OK"

# 3c. Demo parquet fixture is present (Phase B integration tests will read it)
test -f /Users/xai/Desktop/spacescans-project/output/python_v2/270m/TIGER/C3/annual_proximity_demo100k.parquet
echo "parquet OK"

# 3d. Per-county TIGER cache is warm; seed it if absent
if [ -d /Users/xai/Desktop/spacescans-project/cache/C3/tiger_roads_filtered ] && \
   [ "$(ls /Users/xai/Desktop/spacescans-project/cache/C3/tiger_roads_filtered/ | wc -l)" -gt 0 ]; then
  echo "cache OK ($(ls /Users/xai/Desktop/spacescans-project/cache/C3/tiger_roads_filtered/ | wc -l) year dirs)"
else
  echo "cache MISSING — seeding now"
  cd /Users/xai/Desktop/spacescans-project && \
    /Users/xai/miniconda3/envs/spacescans/bin/spacescans run configs/c3/tiger_roads_demo.yaml
fi
```

Expected on the current machine: all four blocks print `OK`; the cache step reports `cache OK (5 year dirs)` (2013–2017).

- [ ] **Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ -q --collect-only 2>&1 | tail -3
```

Expected last line: `64 tests collected in <1s`. This is the baseline Phase A must preserve.

- [ ] **Step 5: Full suite**

```bash
cd /Users/xai/Desktop/spacescans-project
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ -q
```

Expected tail: `64 passed` (the Sprint 2 Phase A `output_grouping` work has already landed on `pkg/pypi-only`, so the pre-Sprint-5 baseline is **64 tests** = 52 original + 12 Sprint-2-Phase-A additions). Record this number in the controller log; per the canonical tally table near the top of the plan, Task A1 adds +3 unit tests (`test_precomputed_areal_linkage.py`) and Task A2 adds +2 to `test_pipeline_smoke.py` (shipped-YAML static assertion + per-episode row-count smoke), so the post-Phase-A target is **69 tests**.

- [ ] **Step 6: Commit**

No commit. A0 changes nothing on disk. Open the Phase A worktree (or stay on `pkg/pypi-only`) and proceed to Task A1.

If the controller prefers an audit trail, append the baseline number to the sprint log:

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) sprint-5 phase-A baseline: 64 tests on pkg/pypi-only" \
  >> /Users/xai/Desktop/spacescans-project/spacescans-web/docs/superpowers/plans/sprint-5-baseline.log
```

(Optional — not part of the commit graph.)

**Notes:**
- The spec (L632–641) lists pre-flight as Phase A step 1; the cache-seed fallback (`spacescans run configs/c3/tiger_roads_demo.yaml`) is the same one-time cost flagged in R9 (~50s cold, ~3s warm) — running it here keeps later smoke tests fast.
- R2 (TIGER C3 data versioning) is enforced at *web* server boot, not here; Task A0 only confirms the *cache* exists. The raw `data_full/TIGER/C4/` zips are checked by Phase B Task B0's pre-flight.
- The `?? spacescans-web/` untracked entry is expected and must not be `git add`-ed — the web repo is a sibling checkout, not a submodule.
- Phase A's editable install means Task A1's `output_grouping` dispatch becomes visible to Phase B integration tests the moment Task A1 commits; no `pip install -e .` re-run is needed. R3's three-layer guard (pyproject bump, `_sanity_check_pipeline_supports_precomputed_areal_episode`, merge-partial low-match log) is set up in later tasks.
- If `git status --short` ever shows tracked-file modifications, stop and surface to the controller; Phase A assumes a clean tree so the `git log` after Task A1 attributes the dispatch change unambiguously.
- Phase A may either commit directly to `pkg/pypi-only` or use a worktree at `.worktrees/feat-sprint-5-pipeline`; A0 is identical either way because it edits nothing.

---

### Task A1: precomputed_areal_linkage.py output_grouping dispatch (RED → GREEN)

**Files:**
- Create: `/Users/xai/Desktop/spacescans-project/tests/test_precomputed_areal_linkage.py`
- Create: `/Users/xai/Desktop/spacescans-project/tests/fixtures/precomputed_areal_mini.parquet` (generated by a one-shot script committed alongside)
- Modify: `/Users/xai/Desktop/spacescans-project/src/spacescans/linkage/precomputed_areal_linkage.py`
- Test: `/Users/xai/Desktop/spacescans-project/tests/test_precomputed_areal_linkage.py`

**Goal:** Add SQL-clause-level `output_grouping` dispatch to `run_precomputed_areal` so the terminal aggregation collapses to `PATID` (default/regression) or `(PATID, geoid)` (episode), with an explicit unknown value raising `ValueError` whose message matches `yearly_areal_linkage.py:55-58` byte-for-byte.

**Context:** Sprint 5 wires TIGER proximity through the `precomputed_areal` pattern, but today `precomputed_areal_linkage.py:114-121` is hard-coded to `GROUP BY PATID` and never reads `config.time.output_grouping`. Sprint 2 already established the dispatch shape in `yearly_areal_linkage.py:47-58`; the `patient_year` CTE (lines 80-104) already carries `v.geoid` so the new `(PATID, geoid)` group key is one SQL edit away. This task is the prerequisite for Phase B's web runner, which sets `cfg["time"]["output_grouping"] = "episode"` in `render_yaml`. No `*Spec` field is added; this is SQL-string-level only.

**Step 1: Write failing test**

First generate the fixture (run once, then commit the parquet):

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python - <<'PY'
import pandas as pd
from pathlib import Path

out = Path("/Users/xai/Desktop/spacescans-project/tests/fixtures")
out.mkdir(parents=True, exist_ok=True)

# 10 patient-episode rows; 2 multi-episode PATIDs (P1: geoids 10,11; P2: geoids 20,21);
# 6 single-episode PATIDs (P3..P8) sharing geoid 30 to keep the file small.
df = pd.DataFrame({
    "PATID": ["P1","P1","P2","P2","P3","P4","P5","P6","P7","P8"],
    "geoid": [10, 11, 20, 21, 30, 30, 30, 30, 30, 30],
    "start": pd.to_datetime(
        ["2017-01-01","2017-07-01","2017-01-01","2017-09-01",
         "2017-01-01","2017-01-01","2017-01-01","2017-01-01",
         "2017-01-01","2017-01-01"]
    ),
    "end": pd.to_datetime(
        ["2017-06-30","2017-12-31","2017-08-31","2017-12-31",
         "2017-12-31","2017-12-31","2017-12-31","2017-12-31",
         "2017-12-31","2017-12-31"]
    ),
    "long": [-86.0]*10,
    "lat":  [40.0]*10,
})
df.to_parquet(out / "precomputed_areal_mini.parquet", index=False)
print(df)
PY
```

Then write `/Users/xai/Desktop/spacescans-project/tests/test_precomputed_areal_linkage.py`:

```python
"""Sprint 5 Phase A: precomputed_areal_linkage.py output_grouping dispatch.

These tests exercise the SQL-clause-level dispatch at the terminal aggregation
of run_precomputed_areal. The fixture
tests/fixtures/precomputed_areal_mini.parquet contains 10 patient-episode
rows with two multi-episode PATIDs (P1 -> {10, 11}; P2 -> {20, 21}), so the
episode branch is guaranteed to produce strictly more rows than the patient
branch.
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

FIXTURE = Path(__file__).parent / "fixtures" / "precomputed_areal_mini.parquet"


def _make_demo_config(tmp_path: Path, output_grouping: str) -> DatasetConfig:
    return DatasetConfig(
        name="precomputed_areal_mini",
        linkage_pattern="precomputed_areal",
        geometry_type="line",
        source=SourceConfig(file="/dev/null"),
        buffer=BufferConfig(patient_file=str(FIXTURE), buffer_m=270),
        exposure=ExposureConfig(
            file="/dev/null",
            value_cols=["dist_pri", "dist_sec", "dist_prisec"],
            year_col="year",
        ),
        time=TimeConfig(years=[2017], output_grouping=output_grouping),
        engine=EngineConfig(),
        output=OutputConfig(path=str(tmp_path / "out.parquet")),
        plugin="tiger_roads",
    )


def _exposure_frame() -> pd.DataFrame:
    """Geoid x year exposure for every geoid in the fixture, year 2017."""
    geoids = [10, 11, 20, 21, 30]
    return pd.DataFrame({
        "geoid": geoids,
        "year": [2017] * len(geoids),
        "dist_pri":    [100.0, 200.0, 300.0, 400.0, 500.0],
        "dist_sec":    [110.0, 210.0, 310.0, 410.0, 510.0],
        "dist_prisec": [120.0, 220.0, 320.0, 420.0, 520.0],
    })


class _FakeReader:
    def __init__(self, config):
        self.config = config

    def load_exposure(self, years=None):
        return _exposure_frame()


def _run(tmp_path: Path, output_grouping: str) -> pd.DataFrame:
    from spacescans.linkage import precomputed_areal_linkage as mod

    cfg = _make_demo_config(tmp_path, output_grouping=output_grouping)
    with patch.object(mod, "get_reader", return_value=_FakeReader):
        mod.run_precomputed_areal(cfg, engine=None)
    return pd.read_parquet(cfg.output.path)


def test_precomputed_areal_groups_by_patid_when_output_grouping_patient(tmp_path):
    df = _run(tmp_path, output_grouping="patient")
    assert list(df.columns) == ["PATID", "dist_pri", "dist_sec", "dist_prisec"]
    assert df["PATID"].is_unique
    # 8 unique PATIDs in the fixture.
    assert len(df) == 8


def test_precomputed_areal_groups_by_patid_geoid_when_episode(tmp_path):
    df_patient = _run(tmp_path, output_grouping="patient")
    df_episode = _run(tmp_path, output_grouping="episode")
    assert list(df_episode.columns) == [
        "PATID", "geoid", "dist_pri", "dist_sec", "dist_prisec",
    ]
    # (PATID, geoid) is unique per row.
    assert df_episode.groupby(["PATID", "geoid"]).size().max() == 1
    # Strictly more rows than the patient branch — P1 and P2 each split into 2.
    assert len(df_episode) > len(df_patient)
    assert len(df_episode) == 10


def test_precomputed_areal_rejects_unknown_output_grouping(tmp_path):
    with pytest.raises(ValueError, match="unsupported output_grouping"):
        _run(tmp_path, output_grouping="foo")
```

**Step 2: Run RED**

```bash
cd /Users/xai/Desktop/spacescans-project && \
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest \
    tests/test_precomputed_areal_linkage.py -v
```

Expected: `test_precomputed_areal_groups_by_patid_when_output_grouping_patient` PASSES (current behaviour already groups by PATID, columns match); `test_precomputed_areal_groups_by_patid_geoid_when_episode` FAILS with `AssertionError: list(df.columns) == ['PATID', 'geoid', ...]` (today's SQL produces only `PATID`, no `geoid`); `test_precomputed_areal_rejects_unknown_output_grouping` FAILS — no `ValueError` is raised because the current code never inspects `output_grouping` (the run completes successfully, the second `_run` call returns silently).

**Step 3: Implement minimal code**

Edit `/Users/xai/Desktop/spacescans-project/src/spacescans/linkage/precomputed_areal_linkage.py`, replacing the block at lines 114-121:

```python
        # Duration-weighted average per patient (or per patient-episode).
        # Dispatch on TimeConfig.output_grouping — mirrors the conditional in
        # yearly_areal_linkage.py:47-58 but expressed as an SQL clause edit
        # because this pattern bypasses the engine.temporal_aggregate path.
        if config.time.output_grouping == "patient":
            select_keys = "PATID"
            group_keys = "PATID"
        elif config.time.output_grouping == "episode":
            select_keys = "PATID, geoid"
            group_keys = "PATID, geoid"
        else:
            raise ValueError(
                f"unsupported output_grouping: {config.time.output_grouping!r} "
                "(expected 'patient' or 'episode')"
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

**Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project && \
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest \
    tests/test_precomputed_areal_linkage.py -v
```

Expected: 3 passed in <2s. The episode branch returns 10 rows (8 single-episode PATIDs P3..P8 contribute 6 rows because they share geoid 30 — but distinct PATIDs, so 6 rows; P1 and P2 each contribute 2 rows → 6 + 4 = 10).

**Step 5: Full suite (with expected cumulative count)**

```bash
cd /Users/xai/Desktop/spacescans-project && \
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ -q
```

Expected cumulative: **67 passed** (64 baseline from pkg/pypi-only + 3 new precomputed_areal tests). No regression in `test_temporal_episode_grouping.py` (yearly_areal / static_areal / bg_vintage dispatch tests untouched).

Targeted regression smoke (must also pass):

```bash
cd /Users/xai/Desktop/spacescans-project && \
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest \
    -k "precomputed_areal or yearly_areal or static_areal or bg_vintage or pipeline_smoke" -v
```

**Step 6: Commit**

```bash
cd /Users/xai/Desktop/spacescans-project && \
git add tests/test_precomputed_areal_linkage.py tests/fixtures/precomputed_areal_mini.parquet \
        src/spacescans/linkage/precomputed_areal_linkage.py && \
git commit -m "$(cat <<'EOF'
feat(linkage): output_grouping dispatch in precomputed_areal (Sprint 5 A1)

Mirrors yearly_areal_linkage.py:47-58 as an SQL-clause-level edit at the
terminal aggregation of run_precomputed_areal. "patient" keeps the v1
GROUP BY PATID; "episode" widens to GROUP BY PATID, geoid (the geoid
column is already carried through the patient_year CTE). An unknown
value raises ValueError whose message matches yearly_areal's wording
byte-for-byte.

Adds tests/test_precomputed_areal_linkage.py (3 tests) and a 10-row
fixture tests/fixtures/precomputed_areal_mini.parquet with two
multi-episode PATIDs so the episode branch is provably wider than the
patient branch.

Cumulative pipeline test count: 64 -> 67 (A1 adds +3; A2 adds another +2 to reach 69 — see canonical tally table near top of plan).
EOF
)"
```

**Notes:**
- The error message string matches `yearly_areal_linkage.py:55-58` byte-for-byte (including the trailing `"(expected 'patient' or 'episode')"` literal with no leading f-prefix on that fragment) so downstream tests that grep for `"unsupported output_grouping"` catch both linkage patterns uniformly.
- `engine=None` is passed because `run_precomputed_areal` ignores the engine argument (the pattern goes through an in-memory sqlite3 connection, not the DuckDB engine). The `@register_pattern` decorator still expects the two-arg signature.
- The `_FakeReader` patches `get_reader` (not `load_exposure` on a real plugin), avoiding any dependency on the `tiger_roads` reader plugin or its 2.6 GB annual_proximity pkl. The Phase B web runner work depends on the real plugin, but Phase A unit tests do not.
- Fixture is ~2 KB committed — well under the spec's budget. The two multi-episode patients (P1, P2) are what makes assertion `len(df_episode) > len(df_patient)` non-vacuous; the spec at L370-400 explicitly calls out this caveat (the 100k demo cohort would silently pass both branches).
- Depends on A0 (no behaviour change yet — A0 only documents the rollout / aligns config docs); the SQL edit here is the first behavioural change.
- The `geoid_col` default on `BufferConfig` is `"geoid"` (matches the fixture's column name), so no patient adapter is needed — `load_patients` returns the parquet as-is.

---

### Task A2: tiger_roads_demo.yaml + pipeline smoke (explicit episode declaration)

**Files:**
- Modify: `/Users/xai/Desktop/spacescans-project/configs/c4/tiger_roads_demo.yaml`
- Modify: `/Users/xai/Desktop/spacescans-project/tests/test_pipeline_smoke.py`

**Goal:** Flip the only in-tree `linkage_pattern: precomputed_areal` config to declare `output_grouping: episode` explicitly and lock the per-episode row count in via an end-to-end pipeline smoke whose cohort has multi-episode patients.

**Context:** Sprint 5 Phase A Task A1 just landed the `output_grouping` dispatch inside `src/spacescans/linkage/precomputed_areal_linkage.py` (patient branch `SELECT PATID GROUP BY PATID`, episode branch `SELECT PATID, geoid GROUP BY PATID, geoid`). The only shipped `precomputed_areal` config (`configs/c4/tiger_roads_demo.yaml`, confirmed via `grep -rn 'linkage_pattern: precomputed_areal' configs/` — single hit at L2) still defaults to `patient`. Spec L370-401 calls out that the shipped 100k cohort has `geoid = range(100_000)` (one geoid per patient), so a naive switch would produce identical row counts under both branches and silently pass even if the episode branch were buggy. Option (b) from spec L391-394 resolves this: extend the smoke's cohort so a handful of PATIDs map to multiple geoid values, switch the YAML, and assert `count(distinct (PATID, geoid)) > count(distinct PATID)`. Because `data_full/demo_patients_conus_fast_100000.parquet` is not git-tracked (and overwriting it would poison other smokes), the new smoke builds its own tiny multi-episode cohort + tiny C3 exposure parquet + temp YAML inside `tmp_path` and runs `spacescans run` against them.

**Step 1: Write failing test**

Append to `/Users/xai/Desktop/spacescans-project/tests/test_pipeline_smoke.py`:

```python
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml


@pytest.mark.geo
@pytest.mark.extras
def test_tiger_roads_demo_episode_branch_row_count(tmp_path):
    """End-to-end smoke for configs/c4/tiger_roads_demo.yaml episode branch.

    Spec ref: 2026-06-16-sprint-5-tiger-proximity-design.md L370-401 (option b)
    and L722-727. Row count must equal count(distinct (PATID, geoid)) and be
    strictly greater than count(distinct PATID); otherwise the dispatch is
    silently collapsing episodes.
    """
    # 5 unique patients; 3 of them have 2 episodes each → 8 cohort rows,
    # 8 distinct (PATID, geoid) pairs, 5 distinct PATIDs.
    cohort = pd.DataFrame({
        "pid":        ["P1", "P1", "P2", "P2", "P3", "P3", "P4", "P5"],
        "startDate":  ["2014-01-01", "2016-01-01", "2014-01-01", "2017-01-01",
                       "2015-01-01", "2018-01-01", "2014-01-01", "2014-01-01"],
        "endDate":    ["2015-12-31", "2017-12-31", "2016-12-31", "2018-12-31",
                       "2017-12-31", "2019-12-31", "2016-12-31", "2016-12-31"],
        "longitude":  [-80.0] * 8,
        "latitude":   [25.0]  * 8,
        "state_fips": [12]    * 8,
        "county_fips":[12086] * 8,
        "tract_geoid":["12086000100"] * 8,
        "bg_geoid":   ["120860001001"] * 8,
        # Distinct geoid per episode — adapter consumes this as `geoid`.
        "episode_id": [10, 11, 20, 21, 30, 31, 40, 50],
    })
    cohort_path = tmp_path / "cohort.parquet"
    cohort.to_parquet(cohort_path, index=False)

    # Minimal C3 exposure: geoids 10/11/20/21/30/31/40/50 × years 2013-2019.
    years = list(range(2013, 2020))
    geoids = [10, 11, 20, 21, 30, 31, 40, 50]
    exposure = pd.DataFrame([
        {"geoid": g, "year": y,
         "dist_pri": 100.0 + g, "dist_sec": 200.0 + g, "dist_prisec": 200.0 + g}
        for g in geoids for y in years
    ])
    exposure_path = tmp_path / "c3_annual_proximity.parquet"
    exposure.to_parquet(exposure_path, index=False)

    output_path = tmp_path / "c4_out.parquet"
    label_path  = tmp_path / "c4_label.parquet"

    cfg = {
        "name": "tiger_roads_demo_smoke",
        "linkage_pattern": "precomputed_areal",
        "geometry_type": "line",
        "source": {"file": str(tmp_path)},
        "buffer": {"patient_file": str(cohort_path),
                   "patient_adapter": "demo_conus"},
        "exposure": {"file": str(exposure_path),
                     "join_col": "geoid",
                     "value_cols": ["dist_pri", "dist_sec", "dist_prisec"]},
        "time": {"years": years,
                 "temporal_resolution": "yearly",
                 "temporal_mode": "yearly",
                 "output_grouping": "episode"},
        "engine": {"backend": "duckdb"},
        "plugin": "tiger_roads",
        "output": {"path": str(output_path),
                   "format": "parquet",
                   "label_path": str(label_path)},
    }
    yaml_path = tmp_path / "tiger_roads_demo_smoke.yaml"
    yaml_path.write_text(yaml.safe_dump(cfg))

    r = subprocess.run(
        [sys.executable, "-m", "spacescans.cli", "run", str(yaml_path)],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"

    out = pd.read_parquet(output_path)
    n_rows = len(out)
    n_patid_geoid = out[["PATID", "geoid"]].drop_duplicates().shape[0]
    n_patid = out["PATID"].nunique()

    assert "geoid" in out.columns, f"episode branch must emit geoid; got {out.columns.tolist()}"
    assert n_rows == n_patid_geoid, (
        f"row count {n_rows} != distinct (PATID, geoid) {n_patid_geoid}"
    )
    assert n_rows > n_patid, (
        f"row count {n_rows} must exceed distinct PATID count {n_patid} "
        f"(smoke loses protective value if cohort is 1:1 patient↔geoid)"
    )
    # Exact lock from the fixture above.
    assert n_rows == 8 and n_patid == 5
```

**Step 2: Run RED**

To split A2 into two test contracts that flipping the shipped YAML actually fixes, the smoke MUST be authored in **two parts** (both in the same commit):

(a) A static-assertion test that the **shipped** `configs/c4/tiger_roads_demo.yaml` literally contains `output_grouping: episode`. Append to `tests/test_pipeline_smoke.py` alongside the row-count smoke:

```python
def test_shipped_tiger_roads_demo_yaml_declares_episode_grouping():
    """Sprint 5 A2: the in-tree configs/c4/tiger_roads_demo.yaml MUST declare
    output_grouping: episode (spec L66-68 [B3], L646-647). Locked separately
    from the row-count smoke so flipping the YAML in Step 3 is what flips this
    assertion from RED to GREEN.
    """
    cfg_path = Path("/Users/xai/Desktop/spacescans-project/configs/c4/tiger_roads_demo.yaml")
    rendered = yaml.safe_load(cfg_path.read_text())
    assert rendered["time"]["output_grouping"] == "episode", (
        f"shipped config must declare output_grouping: episode; "
        f"got time={rendered.get('time')}"
    )
```

(b) The per-episode row-count smoke (the one already pasted in Step 1) — its RED comes from a fresh checkout that lacks A1's dispatch, and its GREEN exercises the episode branch end-to-end against a multi-episode `tmp_path` cohort.

```bash
cd /Users/xai/Desktop/spacescans-project
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest \
  tests/test_pipeline_smoke.py::test_shipped_tiger_roads_demo_yaml_declares_episode_grouping \
  tests/test_pipeline_smoke.py::test_tiger_roads_demo_episode_branch_row_count -v
```

Expected failure modes — name both concretely:
- `test_shipped_tiger_roads_demo_yaml_declares_episode_grouping` → **RED** with the exact assertion string `AssertionError: shipped config must declare output_grouping: episode; got time={'years': [2013, 2014, 2015, 2016, 2017, 2018, 2019], 'temporal_resolution': 'yearly', 'temporal_mode': 'yearly'}` (the shipped YAML predates Sprint 5 and has no `output_grouping` key). Flipping the YAML in Step 3 is what flips this from RED to GREEN.
- `test_tiger_roads_demo_episode_branch_row_count` → on a pre-A1 checkout the subprocess exits non-zero with `ValueError: unsupported output_grouping="episode"`. Post-A1 (which Step 2 of A2 assumes is landed), this test is already GREEN against the `tmp_path` cfg regardless of the shipped YAML — its job is regression-lock, not RED→GREEN for A2. The YAML flip in Step 3 is gated by test (a) only.

**Step 3: Implement minimal code**

Edit `/Users/xai/Desktop/spacescans-project/configs/c4/tiger_roads_demo.yaml`. Replace the `time:` block:

```yaml
time:
  years: [2013, 2014, 2015, 2016, 2017, 2018, 2019]
  temporal_resolution: yearly
  temporal_mode: yearly
  output_grouping: episode   # Sprint 5: per-episode rows; PATID may repeat with distinct geoid
```

(No other change to the file — `linkage_pattern`, `plugin`, `exposure`, `output` stay as-is.)

**Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest \
  -k "precomputed_areal or tiger_roads" -v
```

Expected: A1's 3 `test_precomputed_areal_*` tests + the new `test_tiger_roads_demo_episode_branch_row_count` all PASS (4 selected). Confirm the new test's stdout shows `n_rows=8`, `n_patid=5`.

**Step 5: Full suite**

```bash
cd /Users/xai/Desktop/spacescans-project
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: per the canonical tally table above (Pipeline rows A0–A2), `69 passed` — 64 baseline + 3 from A1 + 2 from A2 (shipped-YAML static assertion + per-episode row-count smoke). No regressions in `yearly_areal`, `yearly_areal_bg_vintage`, `static_areal`, `precomputed_static`.

**Step 6: Commit**

```bash
cd /Users/xai/Desktop/spacescans-project
git add configs/c4/tiger_roads_demo.yaml tests/test_pipeline_smoke.py
git commit -m "feat(configs): tiger_roads_demo declares output_grouping=episode + smoke locks per-episode row count

Sprint 5 Phase A Task A2. Flips the only in-tree precomputed_areal
config to explicit episode grouping (spec L66-68 [B3], L646-647) and
adds a pipeline smoke that builds an 8-row multi-episode cohort in
tmp_path and asserts row count == distinct (PATID, geoid) > distinct
PATID — spec L370-401 option (b) and L722-727. Without the
multi-episode cohort the shipped 100k demo (geoid = range(100_000))
would collapse to identical row counts under both branches and the
smoke would silently pass."
```

**Notes:**
- Depends on A1 (`precomputed_areal_linkage.py` episode dispatch must exist or the subprocess will exit with `ValueError: unsupported output_grouping="episode"`).
- The smoke is hermetic — it does NOT mutate `data_full/demo_patients_conus_fast_100000.parquet` (which is untracked and shared with other CLI/web smokes). Spec L391-394 phrases this as "extend the demo cohort fixture", interpreted here as "the cohort fixture *used by this smoke*" — building it inline in `tmp_path` is the only collision-safe option and matches the existing `test_quickstart.py` pattern.
- `@pytest.mark.geo + @pytest.mark.extras` mirrors `test_quickstart_runs_and_writes_output` because the CLI `run` path imports the full reader registry; bare-install CI deselects via `-m "not geo"`.
- The `episode_id` column on the cohort is consumed by `_adapt_demo_conus` (helpers.py L76-77) as the synthetic `geoid` — this is the same mechanism Phase B's `csv_to_parquet` uses to emit per-episode geoids; the smoke therefore exercises the exact production code path.
- `n_rows == 8` and `n_patid == 5` are exact-value locks so a future regression that re-collapses episodes (e.g., dropping `geoid` from `GROUP BY`) fails loudly rather than via the inequality alone.
- Pipeline test count after A2: **69** (64 baseline + 3 A1 + 2 A2 — see canonical tally table near top of plan). A3 is verification-only and adds 0.

---

### Task A3: Phase A wrap-up: regression sweep, commit, publish for Phase B

**Files:** (none — verification + git only; all writes happened in A1/A2)

**Goal:** Run the full pipeline test suite to confirm 69 tests pass with zero regressions in the Sprint 2 dispatch surface, verify the editable-install handoff for Phase B, and open the Phase A PR on `pkg/pypi-only` (held from origin push until Phase B integration is green).

**Context:** Phase A landed three commits on `pkg/pypi-only` in `/Users/xai/Desktop/spacescans-project`: (1) `precomputed_areal_linkage` dispatch on `TimeConfig.output_grouping` (patient / episode / ValueError), (2) three unit tests in `tests/test_precomputed_areal_linkage.py`, (3) `configs/c4/tiger_roads_demo.yaml` declares `output_grouping: episode` plus the two-part smoke (shipped-YAML static assertion + per-episode row-count smoke) in `tests/test_pipeline_smoke.py`. Pipeline baseline before Sprint 5 was 64 tests (52 Sprint-1 + 12 Sprint-2-Phase-A). Phase A adds +5 → expected 69 per the canonical tally table near the top of this plan. Phase B runs in a separate worktree at `spacescans-web/.worktrees/feat-sprint-5-tiger-proximity` and consumes this branch via the web's `SPACESCANS_PIPELINE_PYTHON` editable install (`pip install -e ../spacescans-project` against the same checkout); committing here makes Phase A live for Phase B with zero re-install on the same env.

Step 1: Review the Phase A diff and confirm the three commits are in order on `pkg/pypi-only`.

```bash
cd /Users/xai/Desktop/spacescans-project
git log --oneline pkg/pypi-only -5
git diff 3e9841c..HEAD -- src/spacescans/linkage/ tests/test_precomputed_areal_linkage.py tests/test_pipeline_smoke.py configs/c4/tiger_roads_demo.yaml | head -120
```

Expected: three commits on top of `3e9841c` (the Sprint 2 merge): one touching `src/spacescans/linkage/precomputed_areal_linkage.py`, one touching `tests/test_precomputed_areal_linkage.py` (+3 tests), one touching both `configs/c4/tiger_roads_demo.yaml` and `tests/test_pipeline_smoke.py` (+1 test). Diff shows the new `output_grouping` if/elif/else block dispatching to `_link_patient` / `_link_episode` and raising `ValueError("output_grouping must be one of {'patient', 'episode'}, got: ...")`.

Step 2: Targeted regression sweep on the dispatch families (Sprint 2 + Sprint 5).

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ -k "precomputed_areal or tiger_roads or yearly_areal or static_areal" -v 2>&1 | tail -40
```

Expected: every test in `test_precomputed_areal_linkage.py` (3 patient/episode/ValueError), `test_yearly_areal_linkage.py` (Sprint 2 dispatch, unchanged), `test_yearly_areal_bg_vintage_linkage.py`, and `test_static_areal_linkage.py` passes. No xfails introduced. Final line: `===== N passed in X.XXs =====` with N ≥ 16 (3 new + Sprint 2 carry-over).

Step 3: Full pipeline suite — must hit the post-Sprint-5-A baseline.

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ 2>&1 | tail -5
```

Expected: `===== 69 passed in X.XXs =====` per the canonical tally table — 64 pre-Sprint-5 + 5 Sprint-5-Phase-A (3 in `test_precomputed_areal_linkage.py`, 2 in `test_pipeline_smoke.py`: `test_shipped_tiger_roads_demo_yaml_declares_episode_grouping` + `test_tiger_roads_demo_episode_branch_row_count`). If the count is 68, exactly one of A2's two smoke tests did not register — re-check `tests/test_pipeline_smoke.py` for a missing `def test_` prefix or a `@pytest.mark.skip`. If 64, A1's dispatch refactor reverted — re-run A1.

Step 4: Editable-install handoff verification (R3 mitigation layer (b)).

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -c "from spacescans.linkage import precomputed_areal_linkage; import inspect; print('episode' in inspect.getsource(precomputed_areal_linkage))"
```

Expected: `True`. This is the exact probe `tiger_proximity._sanity_check_pipeline_supports_precomputed_areal_episode()` will run from Phase B at runner start — failing here means Phase B's pre-flight will raise `RuntimeError` and abort. If it prints `False`, the editable install is pointing at a stale wheel; resolve with:

```bash
/Users/xai/miniconda3/envs/spacescans/bin/pip install -e /Users/xai/Desktop/spacescans-project --no-deps
```

then re-run the probe.

Step 5: Confirm working tree is clean (no leftover scratch from A1/A2) and the three commits are present.

```bash
cd /Users/xai/Desktop/spacescans-project
git status --short
git log --oneline pkg/pypi-only ^3e9841c
```

Expected: `git status --short` prints nothing (or only `?? spacescans-web/`, which is a sibling checkout not part of this repo and must be left untracked — do **not** `git add` it). `git log` lists exactly the three A1/A2 commits in topological order:
- `<sha>` `test(pipeline): tiger_roads_demo end-to-end smoke asserts (PATID, geoid) row count`
- `<sha>` `test(linkage): precomputed_areal dispatch unit tests (patient/episode/ValueError)`
- `<sha>` `feat(linkage): precomputed_areal dispatch on TimeConfig.output_grouping`

Step 6: Open the PR locally (no push to origin yet — held pending Phase B verification per the orchestrator brief).

```bash
cd /Users/xai/Desktop/spacescans-project
git log --oneline pkg/pypi-only ^3e9841c > /tmp/sprint5-phase-a-commits.txt
cat <<'EOF' > /tmp/sprint5-phase-a-pr-body.md
## Summary

- `precomputed_areal_linkage` now dispatches on `TimeConfig.output_grouping`: `"patient"` (legacy, default) and `"episode"` (one row per (PATID, episode_id, geoid)) — invalid values raise `ValueError` naming both legal options.
- `configs/c4/tiger_roads_demo.yaml` declares `output_grouping: episode` explicitly so the demo cohort routes through the episode branch end-to-end.
- +5 tests: 3 dispatch unit tests in `tests/test_precomputed_areal_linkage.py` (patient / episode / ValueError) + 2 end-to-end smokes in `tests/test_pipeline_smoke.py` (shipped-YAML static assertion + `row_count == n_distinct(PATID, geoid)`).

Pipeline baseline: 64 → 69 tests. Sprint 2 dispatch families (`yearly_areal`, `yearly_areal_bg_vintage`, `static_areal`) untouched and green.

## Phase B handoff

The web's `SPACESCANS_PIPELINE_PYTHON` points at an editable install of this checkout (`pip install -e ../spacescans-project`), so this commit is live for Phase B with zero re-install. Phase B's `tiger_proximity._sanity_check_pipeline_supports_precomputed_areal_episode()` will probe `inspect.getsource(precomputed_areal_linkage)` for `'episode'` at runner start (R3 mitigation layer b).

## Test plan

- [x] `pytest tests/ -k "precomputed_areal or tiger_roads or yearly_areal or static_areal"` — green
- [x] `pytest tests/` — 69 passed
- [x] Editable-install probe returns `True`
- [ ] Phase B `feat/sprint-5-tiger-proximity` integration green before pushing this branch to origin

EOF
echo "PR body staged at /tmp/sprint5-phase-a-pr-body.md"
echo "Commits to publish:"
cat /tmp/sprint5-phase-a-commits.txt
echo ""
echo "HOLD: Do NOT run 'git push origin pkg/pypi-only' or 'gh pr create' until Phase B reports 150 passed, 2 skipped under 'pytest -q' AND the 2 newly-introduced @pytest.mark.integration tests (test_e2e_tiger_proximity_cohort + test_e2e_multi_experiment_with_tiger_cohort) pass under 'pytest -m integration' on a TIGER-equipped runner. (See canonical tally table near the top of the plan.) At that point run:"
echo "  git push origin pkg/pypi-only"
echo "  gh pr create --title 'feat(linkage): precomputed_areal output_grouping dispatch (Sprint 5 Phase A)' --body-file /tmp/sprint5-phase-a-pr-body.md --base main"
```

Expected: PR body and commit list staged on disk; nothing pushed. The PR title is the exact string from spec L673-674: `feat(linkage): precomputed_areal output_grouping dispatch (Sprint 5 Phase A)`. Phase B can begin immediately in its worktree — the editable install already sees the new dispatch.

**Notes:**
- Depends on A2 (two-part smoke) and transitively on A1 (dispatch refactor). Re-run Step 3 before declaring Phase A complete; the 69-count is the load-bearing arithmetic that gates Phase B's pre-flight probe (per the canonical tally table near the top of the plan).
- The orchestrator brief is explicit: stay on `pkg/pypi-only`, no merge to a separate main, hold the origin push until Phase B integration verifies. Pushing prematurely would publish an unverified dispatch surface; holding lets Phase B's integration tests act as the acceptance gate for Phase A's behavioural contract.
- Do **not** `git add spacescans-web/` from this checkout — it is a sibling project with its own git root. The `??` entry in `git status` is expected and benign.
- If Step 4's probe returns `False` despite Step 3 passing, the test env and the runtime env have diverged. Re-running `pip install -e .` against the same checkout is the canonical fix (R3 mitigation layer a is the pyproject pin bump, which is a no-op for editable installs).
- If Phase B's pre-flight `RuntimeError`s after Step 4 reports `True`, the web project's `SPACESCANS_PIPELINE_PYTHON` is pointing at a *different* python than the one used here — verify with `echo $SPACESCANS_PIPELINE_PYTHON` from the Phase B worktree and reconcile before debugging the dispatch.
- The PR is `--base main` even though we develop on `pkg/pypi-only`; this matches Sprint 2's merge pattern (`3e9841c Merge feat/output-grouping-per-episode for Sprint 2 Phase A`) where dispatch work merges back into the trunk after web-side verification.

---

## Phase B — Web (branch `feat/sprint-5-tiger-proximity`)

### Task B0: Web worktree setup on feat/sprint-5-tiger-proximity + Phase A handoff verify

**Files:**
- (none — git worktree setup + handoff verify only)
- Reference: `/Users/xai/Desktop/spacescans-project/spacescans-web/backend/.env` (gitignored, migrated)
- Reference: `/Users/xai/Desktop/spacescans-project/spacescans-web/frontend/node_modules` (symlinked)

**Goal:** Stand up an isolated `feat/sprint-5-tiger-proximity` worktree off `main`, verify Phase A's `precomputed_areal_linkage` episode dispatch is live in the editable-installed pipeline (spec R3, layer b), and capture the 139-pass pytest baseline plus a clean `tsc --noEmit` before any Sprint 5 Phase B code lands.

**Context:** Sprint 5 Phase A (precomputed_areal_linkage `output_grouping` dispatch + ValueError + tiger_roads_demo.yaml episode hint) has just merged on the pipeline side and the editable install at `/Users/xai/Desktop/spacescans-project/src/spacescans` now exposes the new branch. Phase B will add a third experiment runner (`tiger_proximity.py`), wire metadata + tests, and exercise the new dispatch — but every downstream task assumes a quarantined worktree with the same env vars and node_modules as the main web checkout. This task is the only setup step; it produces no source diff but is the gate for B1+.

- [ ] **Step 1: Write failing test (real pytest code, not "write a test for X")**

Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_phase_a_handoff.py` (a transient guard test we will delete in Step 6 — its only job is to fail RED when Phase A is *not* in the env, proving the worktree's editable install resolves to the new pipeline branch):

```python
"""Sprint 5 Phase A handoff guard — DELETED after this task lands.

Verifies the pipeline editable-install seen from this worktree's
backend already contains the `output_grouping == "episode"` branch
in precomputed_areal_linkage. Mirrors spec L678-682 (R3 layer b)
which the tiger_proximity runner will re-implement at runtime.
"""
import inspect

from spacescans.linkage import precomputed_areal_linkage


def test_precomputed_areal_linkage_supports_episode_grouping():
    src = inspect.getsource(precomputed_areal_linkage)
    assert "episode" in src, (
        "Phase A not visible in this worktree's pipeline env; "
        "tiger_proximity will silently emit patient rows. "
        "Confirm `pip show spacescans` points at "
        "/Users/xai/Desktop/spacescans-project/src/spacescans "
        "and that pkg/pypi-only has Phase A merged."
    )
```

- [ ] **Step 2: Run RED (concrete bash + expected failure mode)**

Before creating the worktree, prove the brand-new branch sees the file. From the main web checkout:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web
git status --short
git log --oneline -3
```

Expected: clean working tree; HEAD at `77adddc docs(spec): Sprint 5 — TIGER Proximity + precomputed_areal episode dispatch`.

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web
git check-ignore -q .worktrees/foo && echo "ignored" || echo "NOT ignored"
```

Expected: `ignored` (already gitignored on this repo — no `.gitignore` edit needed).

Create the worktree, migrate the one gitignored runtime file (`backend/.env`), symlink node_modules. Do NOT copy `backend/data/variable_metadata.json` — see the Notes block below for the rationale; the in-tree `backend/app/data/variable_metadata.json` ships via the git worktree checkout, and the gitignored runtime override at `backend/data/variable_metadata.json` must remain absent in this worktree by design (it would trip the Final-verification absent-tracking gate at the bottom of this plan):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web
git worktree add .worktrees/feat-sprint-5-tiger-proximity -b feat/sprint-5-tiger-proximity main
cp backend/.env .worktrees/feat-sprint-5-tiger-proximity/backend/.env
# DO NOT copy backend/data/variable_metadata.json — the in-tree
# backend/app/data/variable_metadata.json is what B1 will edit, and that file
# ships with the worktree checkout. Copying the gitignored runtime override
# would risk creating an untracked backend/data/variable_metadata.json in the
# worktree, which the Final-verification gate explicitly forbids.
ln -s "$(pwd)/frontend/node_modules" \
   .worktrees/feat-sprint-5-tiger-proximity/frontend/node_modules
git worktree list
```

Expected: two entries — main web checkout on `pkg/pypi-only` and the new worktree on `feat/sprint-5-tiger-proximity`.

Drop in the guard test and run it expecting RED *only* if Phase A is missing:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
# (paste the test file from Step 1 into backend/tests/test_phase_a_handoff.py)
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_phase_a_handoff.py -v
```

Expected failure mode if A-phase is NOT live: `AssertionError: Phase A not visible in this worktree's pipeline env...`. Expected if A-phase IS live: 1 passed (proceed to Step 4).

- [ ] **Step 3: Implement minimal code (actual code an implementer should paste)**

There is no source code to write for B0. The "implementation" is the editable-install sanity probe that mirrors the runner's runtime guard (spec L678-682). Run it standalone to confirm:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity
/Users/xai/miniconda3/envs/spacescans/bin/python -c \
  "from spacescans.linkage import precomputed_areal_linkage; import inspect; print('episode' in inspect.getsource(precomputed_areal_linkage))"
```

Expected output: `True`.

Also confirm the editable install still points at the source tree (not a wheel):

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -c \
  "import spacescans; assert spacescans.__file__.startswith('/Users/xai/Desktop/spacescans-project/src/spacescans'), spacescans.__file__; print(spacescans.__file__)"
```

Expected: `/Users/xai/Desktop/spacescans-project/src/spacescans/__init__.py`.

- [ ] **Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_phase_a_handoff.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Full suite (with expected cumulative count)**

Backend full suite baseline (web baseline 139 + 1 transient guard test = 140 passed). Capture the exact one-line summary verbatim — this is the single source of truth used by every subsequent task's Step 5 expected count:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q | tail -1 | tee /tmp/sprint5-web-baseline.txt
```

Expected (verbatim): `140 passed, 2 skipped, 9 deselected in <T>s` (139 main baseline + 1 transient guard; integration tests stay deselected).

After Step 6 deletes the transient guard, re-run and pin the post-baseline tuple:

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q | tail -1 | tee -a /tmp/sprint5-web-baseline.txt
```

Expected: `139 passed, 2 skipped, 9 deselected in <T>s`. **This is the immovable baseline tuple** for the canonical tally table at the top of this plan. If `139 passed, 2 skipped, 9 deselected` is NOT what the live `main` produces, stop and re-pin the canonical tally before proceeding to B1 — every later task's expected count is derived from this exact tuple.

Frontend type-check baseline:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/frontend
npx tsc --noEmit
```

Expected: exit 0, no output (clean).

- [ ] **Step 6: Commit (conventional message)**

Delete the transient guard test (it duplicates the runner's runtime check that lands in B2) and commit the worktree setup as a no-source-change marker:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity
rm backend/tests/test_phase_a_handoff.py
# Re-run to confirm we're back to the immovable baseline tuple captured in Step 5
# (also already appended to /tmp/sprint5-web-baseline.txt):
cd backend && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
# Expected (verbatim, matching the pin in Step 5): "139 passed, 2 skipped, 9 deselected".
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity
git commit --allow-empty -m "chore(sprint-5): worktree feat/sprint-5-tiger-proximity baseline

Phase A (precomputed_areal_linkage output_grouping=episode) verified
live in editable-installed pipeline via inspect.getsource grep.
Backend baseline: 139 passed, 2 skipped, 9 deselected.
Frontend baseline: tsc --noEmit clean.

Refs: spec L676-682 Phase B step 1, R3 layer b."
```

**Notes:**
- `.worktrees/` is already gitignored at the web repo root (verified) — no `.gitignore` change needed, unlike the pipeline-side Task A0.
- Symlinking `frontend/node_modules` instead of reinstalling avoids ~3 min of `npm ci`; the lockfile is identical between branches at this point.
- `backend/.env` is a gitignored runtime artifact and is the only file physically copied into the worktree. The in-tree, version-controlled `backend/app/data/variable_metadata.json` ships with the worktree checkout itself — B1 edits THAT file (in-tree), not the gitignored runtime override at `backend/data/variable_metadata.json`. The gitignored runtime path must remain absent in the worktree by design (it would otherwise trip the Final-verification absent-tracking invariant — see the closing section of this plan). Do NOT copy `backend/data/variable_metadata.json` into the worktree.
- The guard test in Steps 1–4 is intentionally throwaway; the same `inspect.getsource(... 'episode' ...)` check lives permanently inside `tiger_proximity._sanity_check_pipeline_supports_precomputed_areal_episode()` per spec R3 layer b, and Task B2 will add it as production code. Keeping it transient avoids two copies of the same assertion drifting.
- Depends on Phase A task A3 (the pipeline-side commit that lands `output_grouping == "episode"` in `precomputed_areal_linkage`) being merged to `pkg/pypi-only` *before* this task starts — Step 2 / Step 3 will go RED otherwise. The editable install means no `pip install` is required between A3's merge and this task.
- Empty commit on Step 6 is deliberate: B0 produces no source diff but we want a discoverable anchor in `git log feat/sprint-5-tiger-proximity` for downstream tasks (and for the eventual squash-merge log).

---

### Task B1: variable_metadata.json tiger_proximity entry + schema/registry RED→GREEN

**Files:**
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/app/data/variable_metadata.json`
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_variable_registry.py`
- Test: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_variable_registry.py`

**Goal:** Land the `tiger_proximity` entry in `variable_metadata.json` and prove it survives schema validation while still tripping the registry's experiment-module whitelist — the spec's deliberate "half-landed" state that B2 will clear.

**Context:** Phase A (`output_grouping` dispatch + `tiger_roads_demo.yaml` config) is already committed on `pkg/pypi-only` and visible to this worktree via the editable install. Phase B is being TDD'd in `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity` on branch `feat/sprint-5-tiger-proximity`. The web backend baseline post-Sprint-4 main is 139 tests; Task B0 added the worktree wiring with zero test delta, so this task starts from 139. The registry (`backend/app/variable_registry.py:64-96`) loads `variable_metadata.json`, runs jsonschema validation against `variable_metadata.schema.json`, and then enforces `m["experiment"] in _discover_experiments()` — scanning `backend/app/experiments/*.py`. Until Task B2 adds `backend/app/experiments/tiger_proximity.py`, that whitelist will reject the new entry. The spec (L683-685) calls out this exact intermediate state as the gating mechanism.

- [ ] **Step 1: Write failing test**

**Precondition (verify before appending):** the snippet below uses `Path(...)`, `json.dumps(...)`, and `pytest.raises(...)`. Before appending, open `backend/tests/test_variable_registry.py` and confirm the module top already imports `json`, `pathlib.Path`, and `pytest`. If any of those three imports is missing, add it in this same commit (alphabetically grouped with the existing stdlib / third-party imports). Otherwise the file will not even collect after the append, and Step 2's RED expectation (`DID NOT RAISE`) will be masked by an `ImportError` / `NameError` at collection time.

Append to `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_variable_registry.py`:

```python
def test_registry_accepts_tiger_proximity_entry(tmp_path, monkeypatch):
    """Sprint 5 B1: tiger_proximity entry passes schema (3 value_cols, BG boundary,
    2013-2019 coverage) once a tiger_proximity experiment module exists.

    This test stubs the experiment discovery so it does NOT depend on B2's
    runner module landing. It locks in the canonical entry shape from spec L570-582.
    """
    from app import variable_registry as vr

    real_schema = Path(__file__).parent.parent / "app" / "data" / "variable_metadata.schema.json"
    payload_path = tmp_path / "variable_metadata.json"
    payload_path.write_text(json.dumps({
        "schema_version": 1,
        "variables": {
            "tiger_proximity": {
                "label": "TIGER Road Proximity",
                "description": (
                    "Per-block-group annual distance (meters) to the nearest "
                    "TIGER/Line primary road (S1100), secondary road (S1200), "
                    "and primary+secondary combined, from US Census TIGER/Line "
                    "shapefiles."
                ),
                "boundary": "BG",
                "coverage_years": [2013, 2019],
                "coverage_region": "CONUS",
                "experiment": "tiger_proximity",
                "variable_type": "continuous",
                "display_unit": "meters",
                "value_cols": ["dist_pri", "dist_sec", "dist_prisec"],
            }
        },
    }))

    monkeypatch.setattr(vr, "_METADATA_PATH", payload_path)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", real_schema)
    # Pretend the tiger_proximity module exists so the whitelist passes — B2
    # will make this real.
    monkeypatch.setattr(
        vr, "_discover_experiments",
        lambda: {"bg_ndi_wi", "zcta5_cbp", "tiger_proximity"},
    )

    payload = vr.load_variables(force=True)
    entry = payload["variables"]["tiger_proximity"]
    assert entry["boundary"] == "BG"
    assert entry["experiment"] == "tiger_proximity"
    assert entry["coverage_years"] == [2013, 2019]
    assert entry["display_unit"] == "meters"
    assert entry["value_cols"] == ["dist_pri", "dist_sec", "dist_prisec"]
    assert "US Census TIGER/Line shapefiles" in entry["description"]


def test_real_metadata_file_contains_tiger_proximity_but_gates_on_missing_module():
    """Loading the real, on-disk variable_metadata.json must raise
    MetadataSchemaError(unknown experiment) until B2 lands
    backend/app/experiments/tiger_proximity.py.

    This is the spec's deliberate "half-landed" gate (L683-685): the JSON entry
    is committed in B1, but the server refuses to boot until the runner module
    is added in B2.
    """
    from app import variable_registry as vr
    with pytest.raises(vr.MetadataSchemaError, match="unknown experiment"):
        vr.load_variables(force=True)
```

- [ ] **Step 2: Run RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_variable_registry.py -v \
  -k "tiger_proximity"
```

Expected: 2 FAIL.
- `test_registry_accepts_tiger_proximity_entry` — currently passes through to schema/whitelist OK against the stubbed payload, but `payload["variables"]["tiger_proximity"]` resolves against the *real* file via `_discover_experiments` being stubbed but other paths — actually fails only on the assertion that the entry exists if the registry doesn't pick it up; the failing mode here is the *second* test.
- `test_real_metadata_file_contains_tiger_proximity_but_gates_on_missing_module` — currently `vr.load_variables(force=True)` against the real file succeeds (no `tiger_proximity` entry exists yet), so the `pytest.raises(MetadataSchemaError)` block fails with `DID NOT RAISE`.

If only the second test is RED at this point and the first is already GREEN (stub makes it self-contained), that is the correct RED→GREEN transition for this task. Confirm exactly one or two RED, then proceed.

- [ ] **Step 3: Implement minimal code**

Edit `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/app/data/variable_metadata.json`. Replace the trailing `}` of the `cbp_zcta5` entry with `},` and append the new entry before the closing braces:

```json
{
  "schema_version": 1,
  "variables": {
    "ndi": {
      "label": "Neighborhood Deprivation Index (NDI)",
      "description": "Composite measure of neighborhood-level socioeconomic deprivation from US Census ACS variables.",
      "boundary": "BG",
      "coverage_years": [2012, 2022],
      "coverage_region": "CONUS",
      "experiment": "bg_ndi_wi",
      "variable_type": "continuous",
      "display_unit": "z-score",
      "value_cols": ["ndi"]
    },
    "walkability": {
      "label": "EPA Walkability Index",
      "description": "EPA National Walkability Index ranking neighborhoods on walkability characteristics (intersection density, transit proximity, employment mix).",
      "boundary": "BG",
      "coverage_years": [2016, 2021],
      "coverage_region": "CONUS",
      "experiment": "bg_ndi_wi",
      "variable_type": "continuous",
      "display_unit": "1-20 index",
      "value_cols": ["NatWalkInd"]
    },
    "cbp_zcta5": {
      "label": "Community Organization Density (ZBP)",
      "description": "Per-capita density of 10 community organization categories (religious, civic, business, political, professional, labor, bowling, recreational, golf, sports) at the ZIP Code Tabulation Area level from Census Zip Business Patterns.",
      "boundary": "ZCTA5",
      "coverage_years": [2013, 2019],
      "coverage_region": "CONUS",
      "experiment": "zcta5_cbp",
      "variable_type": "continuous",
      "display_unit": "establishments / 1k residents",
      "value_cols": [
        "r_religious", "r_civic", "r_business", "r_political",
        "r_professional", "r_labor", "r_bowling", "r_recreational",
        "r_golf", "r_sports"
      ]
    },
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
  }
}
```

Validate the JSON is well-formed and conforms to the schema (without touching the registry whitelist):

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python - <<'PY'
import json, jsonschema, pathlib
root = pathlib.Path("/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/app/data")
payload = json.loads((root / "variable_metadata.json").read_text())
schema = json.loads((root / "variable_metadata.schema.json").read_text())
jsonschema.validate(payload, schema)
print("schema OK; variables =", list(payload["variables"]))
PY
```

Expected: `schema OK; variables = ['ndi', 'walkability', 'cbp_zcta5', 'tiger_proximity']`.

- [ ] **Step 4: Confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_variable_registry.py -v \
  -k "tiger_proximity"
```

Expected: 2 PASS — the registry-side gate now correctly raises `MetadataSchemaError(unknown experiment 'tiger_proximity')` against the real file, and the stubbed-discovery test confirms the JSON shape matches the spec.

- [ ] **Step 5: Full suite**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected per the canonical tally table near the top of the plan: B1 = 140 passed (139 baseline + **+1 net** registry delta; skips/deselects unchanged from Sprint 4 baseline). The two new tests sketched in Step 1 are NOT both counted as +2 — `test_real_metadata_file_contains_tiger_proximity_but_gates_on_missing_module` is the canonical +1, and `test_registry_accepts_tiger_proximity_entry` is folded into the existing `test_load_variables_passes_schema_validation` as a value-cols superset check rather than a standalone test (this keeps B1's contribution to the tally at exactly +1 per the spec budget at L710 and avoids the +1/+2 drift the critic flagged). Server boot smoke (`test_startup_probe_passes_in_env`) still passes because it only exercises the pipeline-version probe, not the experiment whitelist. Other registry tests (`test_load_variables_passes_schema_validation`, `test_list_experiments_dedupes_in_file_order`, etc.) are unaffected by the new entry because:
- `test_load_variables_passes_schema_validation` only asserts `>= {"ndi", "walkability", "cbp_zcta5"}` — superset-tolerant.
- `test_list_experiments_dedupes_in_file_order` asserts exact equality `["bg_ndi_wi", "zcta5_cbp"]` against the *real* file — and will now FAIL because the file now contains `tiger_proximity` too. **Rewrite that test in this same commit** (this is a transitional in-place edit, NOT counted as +1 in the tally — see the canonical tally table). Post-B2 it flips back to assert `["bg_ndi_wi", "zcta5_cbp", "tiger_proximity"]`:

```python
def test_list_experiments_dedupes_in_file_order():
    from app import variable_registry as vr
    exps = vr.list_experiments()
    # ndi + walkability both map to bg_ndi_wi; cbp_zcta5 → zcta5_cbp;
    # tiger_proximity → tiger_proximity. File-order dedup.
    assert exps == ["bg_ndi_wi", "zcta5_cbp", "tiger_proximity"]
```

Note that `list_experiments()` calls `load_variables()`, which raises until B2 — so this assertion will *not* be reachable yet. Mark the assertion update but also wrap the body so it documents the dependency without breaking the suite:

```python
def test_list_experiments_dedupes_in_file_order():
    """Post-B2 invariant; currently gated by the tiger_proximity module gap."""
    from app import variable_registry as vr
    with pytest.raises(vr.MetadataSchemaError, match="unknown experiment"):
        vr.list_experiments()
```

After B2 lands, that test flips back to asserting `exps == ["bg_ndi_wi", "zcta5_cbp", "tiger_proximity"]`. Treat the flip as part of B2's diff.

Re-run the full suite after the adjustment. Final expected: **140 passed** (139 baseline + 1 new gating test; the rewrite of `test_list_experiments_dedupes_in_file_order` stays in place and is not double-counted).

- [ ] **Step 6: Commit**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity
git add backend/app/data/variable_metadata.json backend/tests/test_variable_registry.py
git commit -m "feat(metadata): tiger_proximity variable entry (Sprint 5 B1)

Adds the tiger_proximity entry to variable_metadata.json with the
canonical shape from the Sprint 5 spec (BG boundary, 2013-2019 coverage,
3 value_cols: dist_pri / dist_sec / dist_prisec). Schema validation passes
against variable_metadata.schema.json v1.

The registry's experiment-module whitelist intentionally rejects this
entry until B2 lands backend/app/experiments/tiger_proximity.py; the
registry tests assert exactly that gating behavior."
```

Report: status / cumulative test count (140 — see canonical tally table near top of plan) / commit SHA.

**Notes:**
- B1 leaves the server in a non-bootable state by design — `/api/variables` and any code path that calls `vr.load_variables()` against the real file will raise `MetadataSchemaError(unknown experiment 'tiger_proximity')`. This matches spec L683-685. **Do not** add a stub `tiger_proximity.py` in this commit to "make the server boot" — that would short-circuit the gating contract and bleed B2's scope into B1.
- The `test_list_experiments_dedupes_in_file_order` adjustment is the only collateral test change. Sprint 3's other registry tests (`tmp_path`-driven) are insulated by `monkeypatch.setattr(vr, "_METADATA_PATH", ...)` and need no edits.
- Depends on B0 (worktree + branch created, web baseline reconfirmed at 139). Phase A must be live in the editable install — verify with the spec's L678-681 incantation before starting B1, even though B1 doesn't exercise `output_grouping` directly (the startup probe does, transitively).
- Schema invariants enforced automatically: `boundary` enum includes `"BG"`; `coverage_years` is `[2013, 2019]` (2 ints in range); `display_unit "meters"` is all-ASCII ≤ 50 chars; `experiment "tiger_proximity"` matches `^[a-z][a-z0-9_]*$`; `value_cols` has minItems 1 (we ship 3). The JSON validation cell in Step 3 is the load-bearing pre-commit check.

---

### Task B2: experiments/tiger_proximity.py runner (clone-trim of bg_ndi_wi)

**Files:**
- Create: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/app/experiments/tiger_proximity.py`

**Goal:** Land the third single-experiment runner module so that on next server boot `/api/variables` returns four catalogued variables (the existing three plus `tiger_proximity`) and the dispatcher can route `tiger_proximity` tasks to it.

**Context:** Phase A is already landed in the editable-installed pipeline checkout (`precomputed_areal_linkage.py` now dispatches on `time.output_grouping` and `configs/c4/tiger_roads_demo.yaml` declares `output_grouping: episode`). Task B1 has just added the `tiger_proximity` row to `variable_metadata.json` so `variable_registry.load_variables()` already returns four keys at import time. This task adds the runner module the dispatcher needs to actually execute a `tiger_proximity` task — a clone-trim of `bg_ndi_wi.py` that swaps boundary tag, drops raster from the cache key, rewrites `exposure.file` on the C4 step, and includes a defence-in-depth sanity check that the live pipeline supports `output_grouping="episode"` in `precomputed_areal_linkage`. The task adds zero tests; Task B3 introduces the unit-test file.

Step 1: Write failing test

No new test file is added in this task — the spec's `## Test impact` table shows `backend/tests/test_tiger_proximity.py` as the structural test home and Task B3 owns that file. The acceptance signal for B2 is "server boots and `/api/variables` returns 4 keys after this lands", which is enforced by the existing test `backend/tests/test_variable_registry.py::test_registry_catalogues_known_variables` (already passing as of B1) plus a one-shot smoke command run in Step 2. Write no pytest code; instead, capture the failing precondition with this command which proves the runner module does not yet exist:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity
/Users/xai/miniconda3/envs/spacescans/bin/python -c "from app.experiments import tiger_proximity"
```

Step 2: Run RED

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -c "from app.experiments import tiger_proximity; print(tiger_proximity._BOUNDARY)"
```

Expected failure:

```
ModuleNotFoundError: No module named 'app.experiments.tiger_proximity'
```

Step 3: Implement minimal code

Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/app/experiments/tiger_proximity.py`:

```python
"""Single-experiment orchestrator: BG-tagged TIGER/Line road proximity.

Spawned by app.dispatcher as:
    python -m app.experiments.tiger_proximity run <task_dir> [--variables tiger_proximity]

Cloned from bg_ndi_wi.py / zcta5_cbp.py with three spec-mandated deltas:
  * two-step plan that always returns [c3_tiger_roads, c4_tiger_roads]
  * render_yaml rewrites cfg['exposure']['file'] on the C4 step to point at
    the per-task C3 parquet output (precomputed_areal linkage_pattern)
  * _BOUNDARY = 'BG_TIGER' and _cache_key omits the raster_res_m suffix
    (TIGER templates have no raster field)
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

_BOUNDARY = "BG_TIGER"
_EXPERIMENT_KEY = "tiger_proximity"

_C3_STEP = PipelineStep(
    name="c3_tiger_roads",
    template_relpath="c3/tiger_roads_demo.yaml",
    is_c3=True,
)

_VARIABLE_TO_STEP = {
    "tiger_proximity": PipelineStep(
        name="c4_tiger_roads",
        template_relpath="c4/tiger_roads_demo.yaml",
        is_c3=False,
    ),
}

_PARQUET_MAP = {"tiger_proximity": "c4_tiger_roads.parquet"}


def _sanity_check_pipeline_supports_precomputed_areal_episode() -> None:
    """Spec R3 layer (b): grep live pipeline source for episode dispatch.

    If the editable-installed wheel is stale and still hard-codes
    ``GROUP BY PATID``, the runner would silently emit patient-level rows
    and _merge.write_partial would collapse one-to-many on episode_id.
    Detect that drift at runner start with a deterministic substring grep.
    """
    from spacescans.linkage import precomputed_areal_linkage
    src = inspect.getsource(precomputed_areal_linkage)
    if "episode" not in src:
        raise RuntimeError(
            "tiger_proximity: live spacescans.linkage.precomputed_areal_linkage "
            "does not mention 'episode' — Phase A output_grouping dispatch is "
            "missing or pipeline editable install is stale; refusing to run."
        )


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


def render_yaml(step: PipelineStep, task_dir: Path, user_config: dict) -> Path:
    """Read pipeline YAML template, inject task-specific fields, write to task dir.

    Two structural divergences from bg_ndi_wi.render_yaml / zcta5_cbp.render_yaml:
      1. No raster_res_m write — TIGER templates have no such key.
      2. On the C4 step only, rewrite cfg['exposure']['file'] to point at the
         per-task C3 parquet output (precomputed_areal reads it as the
         exposure table).
    """
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
        # C3: nothing extra to wire — road_cache_dir in the template is
        # already cohort-independent.
        pass
    else:
        # C4: rewrite exposure.file to point at this task's C3 output.
        # Spec R4 mitigation: guard against unexpected exposure shape.
        if not isinstance(cfg.get("exposure"), dict):
            raise RuntimeError(
                "tiger_proximity.render_yaml: unexpected exposure: shape"
            )
        cfg["exposure"]["file"] = str(
            task_dir / "output" / f"{_C3_STEP.name}.parquet"
        )

    if "time" in cfg:
        cfg["time"]["output_grouping"] = "episode"  # Sprint 5 Phase A contract
    cfg["output"]["path"] = str(task_dir / "output" / f"{step.name}.parquet")

    out = task_dir / "pipeline_configs" / f"{step.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out


def _write_status(task_dir: Path, **fields) -> None:
    from app.task_manager import _write_status as tm_write
    tm_write(task_dir, **fields)


def _write_slot_status(task_dir: Path, **slot_fields) -> None:
    """Write per-experiment-slot fields (progress / current_step / status / message)."""
    from app.task_manager import _write_status as tm_write
    tm_write(task_dir, experiments={_EXPERIMENT_KEY: slot_fields})


def _hash_input_parquet(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_key(input_parquet: Path, step: PipelineStep, user_config: dict) -> str:
    """Format: ``<sha8>__BG_TIGER__b<buffer>m`` — no raster suffix.

    Boundary tag BG_TIGER avoids collision with bg_ndi_wi's BG cache for the
    same input parquet + buffer even if a future maintainer drops the raster
    suffix from bg_ndi_wi.
    """
    sha = _hash_input_parquet(input_parquet)
    buf = user_config["buffer"]["size"]
    return f"{sha[:8]}__{_BOUNDARY}__b{buf}m"


def _write_cache_meta(path: Path, **fields) -> None:
    fields.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(fields, indent=2))


def _count_input_rows(input_csv: Path) -> int:
    with open(input_csv) as f:
        next(f, None)
        return sum(1 for _ in f)


def _install_cancel_handler(task_dir: Path) -> None:
    def _handler(_signum, _frame):
        _write_status(task_dir, status="cancelled",
                      message="Task cancelled by user")
        _append_log(task_dir, "info", "runner",
                    "received SIGTERM — task cancelled")
        raise SystemExit(143)
    signal.signal(signal.SIGTERM, _handler)


def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Delegate to the shared _merge.write_partial.

    _PARQUET_MAP has a single entry (tiger_proximity -> one parquet); the
    merge picks up all three value_cols (dist_pri, dist_sec, dist_prisec)
    from variable_registry.get_variable.
    """
    parquet_map = {v: _PARQUET_MAP[v] for v in variables}
    return _merge.write_partial(
        task_dir=task_dir,
        experiment_key="tiger_proximity",
        variables=variables,
        parquet_map=parquet_map,
    )


def run(task_dir: Path, variables: list[str] | None = None) -> int:
    """Main entry point. Mirrors zcta5_cbp.run with an override `variables`."""
    _install_cancel_handler(task_dir)
    _sanity_check_pipeline_supports_precomputed_areal_episode()

    lock_path = app.config.settings.DATA_DIR / ".run_lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    lock_fd = os.open(str(lock_path), os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        _write_status(task_dir, status="error",
                      message="another task acquired the run lock first; retry shortly")
        os.close(lock_fd)
        return 1

    try:
        config = json.loads((task_dir / "config.json").read_text())
        dispatcher_driven = variables is not None
        if dispatcher_driven:
            config = {**config, "variables": list(variables)}
        steps = plan(config)
        total_steps = len(steps)

        if dispatcher_driven:
            _write_slot_status(
                task_dir,
                status="running",
                progress=0.0,
                current_step="csv_to_parquet",
                steps=[s.name for s in steps],
                pid=os.getpid(),
                message="Preparing input data",
            )
        else:
            _write_status(
                task_dir,
                status="running",
                progress=0.0,
                message="Preparing input data",
                started_at=datetime.now(timezone.utc).isoformat(),
                pid=os.getpid(),
                experiments={_EXPERIMENT_KEY: {
                    "status": "running",
                    "progress": 0.0,
                    "current_step": "csv_to_parquet",
                    "steps": [s.name for s in steps],
                }},
            )

        try:
            # csv_to_parquet handled by zcta5_cbp's shared implementation —
            # tiger_proximity has no FIPS-string columns beyond the BG/ZCTA5
            # set already covered there. Import locally to avoid a module
            # cycle at boot time.
            from app.experiments.zcta5_cbp import csv_to_parquet
            csv_to_parquet(task_dir / "input.csv", task_dir / "input.parquet")
        except Exception as exc:
            _append_log(task_dir, "error", "runner", f"csv_to_parquet failed: {exc!r}")
            if dispatcher_driven:
                _write_slot_status(task_dir, status="error",
                                   message=f"input conversion failed: {exc}")
            else:
                _write_status(task_dir, status="error",
                              message=f"input conversion failed: {exc}")
            return 1

        for idx, step in enumerate(steps):
            step_progress = idx / total_steps
            if dispatcher_driven:
                _write_slot_status(
                    task_dir,
                    current_step=step.name,
                    progress=step_progress,
                    message=f"Running {step.name} ({idx+1}/{total_steps})",
                )
            else:
                _write_status(
                    task_dir,
                    current_step=step.name,
                    message=f"Running {step.name} ({idx+1}/{total_steps})",
                    progress=step_progress,
                )
            out_parquet = task_dir / "output" / f"{step.name}.parquet"

            cache_path: Path | None = None
            if step.is_c3:
                try:
                    cache_key = _cache_key(task_dir / "input.parquet", step, config)
                    cache_path = app.config.settings.C3_CACHE_DIR / f"{cache_key}.parquet"
                    if _is_valid_cached_parquet(cache_path):
                        out_parquet.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(cache_path, out_parquet)
                        _append_log(task_dir, "info", "runner",
                                    f"cache hit: {cache_key} — skipping pipeline run")
                        cached_progress = (idx + 1) / total_steps
                        if dispatcher_driven:
                            _write_slot_status(
                                task_dir,
                                current_step=step.name,
                                progress=cached_progress,
                                message=f"Reused cached {step.name}",
                            )
                        else:
                            _write_status(
                                task_dir,
                                current_step=step.name,
                                progress=cached_progress,
                                message=f"Reused cached {step.name}",
                            )
                        continue
                except Exception as exc:
                    _append_log(task_dir, "warning", "runner",
                                f"cache check failed for {step.name}: {exc!r} — running fresh")
                    cache_path = None

            try:
                yaml_path = render_yaml(step, task_dir, config)
            except Exception as exc:
                _append_log(task_dir, "error", "runner",
                            f"render_yaml({step.name}) failed: {exc!r}")
                if dispatcher_driven:
                    _write_slot_status(task_dir, status="error",
                                       message=f"render failed at {step.name}")
                else:
                    _write_status(task_dir, status="error",
                                  message=f"render failed at {step.name}")
                return 1

            def _on_step_progress(
                frac: float,
                idx=idx,
                step=step,
                dispatcher_driven=dispatcher_driven,
            ) -> None:
                slot_progress = (idx + frac) / total_steps
                msg = (f"Running {step.name} ({idx+1}/{total_steps}) "
                       f"— {int(frac*100)}%")
                if dispatcher_driven:
                    _write_slot_status(task_dir, progress=slot_progress, message=msg)
                else:
                    _write_status(task_dir, progress=slot_progress, message=msg)

            step_start = time.time()
            rc = run_pipeline_step(yaml_path, task_dir, step_name=step.name,
                                   on_progress=_on_step_progress)
            if rc != 0:
                if dispatcher_driven:
                    _write_slot_status(task_dir, status="error",
                                       message=f"step {step.name} failed with exit code {rc}")
                else:
                    _write_status(task_dir, status="error",
                                  message=f"step {step.name} failed with exit code {rc}")
                return rc
            if not out_parquet.exists():
                if dispatcher_driven:
                    _write_slot_status(task_dir, status="error",
                                       message=f"step {step.name} produced no output parquet")
                else:
                    _write_status(task_dir, status="error",
                                  message=f"step {step.name} produced no output parquet")
                return 1

            if step.is_c3 and cache_path is not None:
                try:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(out_parquet, cache_path)
                    _write_cache_meta(
                        cache_path.with_suffix(".meta.json"),
                        sha_full=_hash_input_parquet(task_dir / "input.parquet"),
                        boundary=_BOUNDARY,
                        buffer_m=config["buffer"]["size"],
                        input_row_count=_count_input_rows(task_dir / "input.csv"),
                        wall_clock_seconds=int(time.time() - step_start),
                        file_size_bytes=out_parquet.stat().st_size,
                    )
                    _append_log(task_dir, "info", "runner",
                                f"cache write: {cache_path.name}")
                except OSError as exc:
                    _append_log(task_dir, "warning", "runner",
                                f"cache write failed: {exc!r} — continuing")

        near_done = (total_steps - 0.1) / total_steps
        if dispatcher_driven:
            _write_slot_status(task_dir, current_step="merge",
                               message="Merging variable outputs",
                               progress=near_done)
        else:
            _write_status(task_dir, current_step="merge",
                          message="Merging variable outputs",
                          progress=near_done)
        try:
            merge_results(task_dir, variables=config["variables"])
        except Exception as exc:
            _append_log(task_dir, "error", "runner", f"merge_results failed: {exc!r}")
            if dispatcher_driven:
                _write_slot_status(task_dir, status="error",
                                   message=f"merge failed: {exc}")
            else:
                _write_status(task_dir, status="error",
                              message=f"merge failed: {exc}")
            return 1

        if dispatcher_driven:
            _write_slot_status(task_dir, progress=1.0, current_step=None,
                               message=f"Completed {total_steps} pipeline steps")
        else:
            _write_status(task_dir, status="finished", progress=1.0,
                          message=f"Completed {total_steps} pipeline steps",
                          experiments={_EXPERIMENT_KEY: {
                              "status": "finished",
                              "progress": 1.0,
                              "current_step": None,
                          }})
        return 0
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(lock_fd)


def _cli_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="tiger_proximity")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("task_dir", type=Path)
    p_run.add_argument("--variables", type=str, default=None,
                       help="comma-separated subset (overrides config.json)")
    args = parser.parse_args(argv[1:])
    if args.cmd != "run":
        parser.error(f"unknown command: {args.cmd}")
    variables = (
        [v.strip() for v in args.variables.split(",") if v.strip()]
        if args.variables else None
    )
    return run(args.task_dir, variables=variables)


if __name__ == "__main__":
    sys.exit(_cli_main(sys.argv))
```

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -c "
from app.experiments import tiger_proximity as tp
assert tp._BOUNDARY == 'BG_TIGER', tp._BOUNDARY
assert tp._EXPERIMENT_KEY == 'tiger_proximity'
assert tp._PARQUET_MAP == {'tiger_proximity': 'c4_tiger_roads.parquet'}
steps = tp.plan({'variables': ['tiger_proximity']})
assert [s.name for s in steps] == ['c3_tiger_roads', 'c4_tiger_roads'], steps
# Sanity-check stub does not raise against the live editable install.
tp._sanity_check_pipeline_supports_precomputed_areal_episode()
print('B2 GREEN')
"
```

Expected stdout: `B2 GREEN`.

Also confirm `/api/variables` exposes four keys with the running server stub:

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -c "
from app.variable_registry import load_variables
keys = sorted(load_variables().keys())
assert 'tiger_proximity' in keys, keys
assert len(keys) == 4, keys
print('variables:', keys)
"
```

Step 5: Full suite

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected per the canonical tally table near the top of the plan: `140 passed, 2 skipped, 9 deselected` — web baseline 139 plus the +1 net delta from B1; Task B2 itself adds zero tests, so the cumulative count after B2 equals the cumulative count after B1. The `2 skipped, 9 deselected` numbers are the immovable baseline tuple pinned in B0 Step 5; B2 does not change either of them.

Step 6: Commit

```bash
git add backend/app/experiments/tiger_proximity.py
git commit -m "$(cat <<'EOF'
feat(experiments): add tiger_proximity runner (BG_TIGER, precomputed_areal)

Clone-trim of bg_ndi_wi.py with three spec-mandated deltas:
  * _BOUNDARY = "BG_TIGER" cache namespace (defence in depth vs bg_ndi_wi's BG)
  * _cache_key drops the raster_res_m suffix (TIGER templates have no raster)
  * render_yaml rewrites cfg["exposure"]["file"] on the C4 step to point at
    the per-task C3 parquet output (precomputed_areal linkage pattern)

Runner-start sanity check greps live spacescans.linkage.precomputed_areal_linkage
source for "episode" and raises RuntimeError if absent — catches stale
editable-install drift from Phase A. exposure.file rewrite is guarded by
isinstance(cfg.get("exposure"), dict) per spec R4.

merge_results is a 3-line wrapper into _merge.write_partial with
experiment_key="tiger_proximity" and _PARQUET_MAP={"tiger_proximity":
"c4_tiger_roads.parquet"}. The single _PARQUET_MAP entry picks up all
three value_cols (dist_pri, dist_sec, dist_prisec) via variable_registry.

Refs spec L73-88 [B5]-[B8], L405-548 module shape, L734-736 R1/R3/R4.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

**Notes:**
- Depends on B1 (`variable_metadata.json` entry must exist or `_merge.write_partial` raises on missing `value_cols`).
- `csv_to_parquet` is imported from `zcta5_cbp` rather than re-copied — both runners share the BG/ZCTA5 FIPS-string set and the deterministic `episode_id = range(len(df))` write; duplicating the function would drift over time. A local import inside `run()` avoids any boot-time cycle risk.
- The sanity-check fires at runner start (after the SIGTERM handler is installed, before lock acquisition) so a stale pipeline install raises *before* any task_dir state mutation.
- No `raster_res_m` appears in `_write_cache_meta` for this runner — it would be a key error against `config["buffer"]` since the wizard for `tiger_proximity` never collects raster.
- B3 (the unit-test file) will exercise `plan`, `render_yaml` (incl. the exposure.file rewrite and the R4 RuntimeError on a non-dict exposure), `_cache_key` shape divergence from `bg_ndi_wi`, and `merge_results` delegation; do not add those tests here.
- The CLI argv shape `python -m app.experiments.tiger_proximity run <task_dir> --variables tiger_proximity` matches `bg_ndi_wi.py:621-635` and `zcta5_cbp.py:434-448` byte-for-byte except for `prog="tiger_proximity"`.

---

### Task B3: tiger_proximity unit tests (8 tests, mirror zcta5_cbp coverage)

**Files:**
- Create: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_tiger_proximity.py`
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_merge_partial.py`

**Goal:** TDD-lock the `tiger_proximity` runner contract (plan / render_yaml exposure rewrite / episode injection / no-raster boundary-namespaced cache key / merge delegation) with 8 unit tests mirroring `test_zcta5_cbp.py`, plus one `_merge.write_partial` test asserting the 3-column TIGER value_cols selection.

**Context:** Sprint 5 adds the third experiment runner (`tiger_proximity`) — a `precomputed_areal`-pattern variable whose C4 step reads the per-task C3 parquet (a divergence from `bg_ndi_wi` and `zcta5_cbp`, which both leave `exposure.file` untouched). Task B2 just dropped the runner module at `backend/app/experiments/tiger_proximity.py` plus the metadata entry. B3 nails down the runner's behavioural contract with unit tests before the integration tests (B4/B5) and the dispatch tests (B6/B7) extend coverage. The R1 cache-key shape assertion is load-bearing: it locks in the BG_TIGER boundary tag plus the absent raster suffix so a future maintainer can't silently collapse the two BG-tagged C3 caches into one.

Step 1: Write failing test

Create `backend/tests/test_tiger_proximity.py`:

```python
"""Sprint 5 B3: tiger_proximity runner — mirror of test_zcta5_cbp.py.

Eight tests pinning the runner contract: plan validation (empty / unknown /
order), render_yaml C3 vs C4 divergence (exposure.file rewrite for C4 only,
output_grouping injection), the no-raster boundary-namespaced cache key
(R1 collision lock against bg_ndi_wi), and the merge_results delegation
into _merge.write_partial.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from app.experiments import tiger_proximity


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task_B3"
    d.mkdir()
    (d / "input.csv").write_text(
        "pid,startDate,endDate,long,lat\n"
        "p1,2017-01-01,2017-12-31,-87.6,41.9\n"
        "p1,2018-01-01,2018-12-31,-87.7,41.8\n"
        "p2,2017-06-01,2018-05-31,-86.2,39.8\n"
    )
    (d / "config.json").write_text(json.dumps({
        "variables": ["tiger_proximity"],
        "buffer": {"size": 1000},
    }))
    pd.DataFrame({
        "pid": ["p1", "p1", "p2"],
        "startDate": ["2017-01-01", "2018-01-01", "2017-06-01"],
        "endDate": ["2017-12-31", "2018-12-31", "2018-05-31"],
        "long": [-87.6, -87.7, -86.2],
        "lat": [41.9, 41.8, 39.8],
        "episode_id": [0, 1, 2],
    }).to_parquet(d / "input.parquet", index=False)
    return d


@pytest.fixture()
def templates_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    templates = tmp_path / "configs"
    (templates / "c3").mkdir(parents=True)
    (templates / "c4").mkdir(parents=True)
    (templates / "c3" / "tiger_roads_demo.yaml").write_text(yaml.safe_dump({
        "name": "c3_tiger_roads_demo",
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "time": {"years": [2017]},
        "output": {"path": "PLACEHOLDER"},
    }))
    (templates / "c4" / "tiger_roads_demo.yaml").write_text(yaml.safe_dump({
        "name": "c4_tiger_roads_demo",
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "exposure": {"file": "/abs/path/to/annual_proximity_demo100k.parquet"},
        "time": {"years": [2017]},
        "output": {"path": "PLACEHOLDER"},
    }))
    import app.config as cfgmod
    monkeypatch.setattr(cfgmod.settings, "SPACESCANS_CONFIG_TEMPLATES_DIR",
                        templates, raising=False)
    return templates


def test_plan_rejects_empty_variables() -> None:
    with pytest.raises(ValueError, match="at least one variable"):
        tiger_proximity.plan({"variables": []})


def test_plan_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError, match="unknown variable"):
        tiger_proximity.plan({"variables": ["ndi"]})  # ndi belongs to bg_ndi_wi


def test_plan_returns_c3_then_c4_order(task_dir: Path) -> None:
    config = json.loads((task_dir / "config.json").read_text())
    steps = tiger_proximity.plan(config)
    assert [s.name for s in steps] == ["c3_tiger_roads", "c4_tiger_roads"]
    assert steps[0].is_c3 is True
    assert steps[1].is_c3 is False


def test_render_yaml_c3_leaves_exposure_untouched(
    task_dir: Path, templates_dir: Path
) -> None:
    cfg = {"buffer": {"size": 1500}}
    c3_path = tiger_proximity.render_yaml(
        tiger_proximity._C3_STEP, task_dir, cfg
    )
    rendered = yaml.safe_load(c3_path.read_text())
    # C3 template has no exposure key; render_yaml must not invent one.
    assert "exposure" not in rendered


def test_render_yaml_c4_rewrites_exposure_to_per_task_c3_parquet(
    task_dir: Path, templates_dir: Path
) -> None:
    cfg = {"buffer": {"size": 1500}}
    c4_step = tiger_proximity._VARIABLE_TO_STEP["tiger_proximity"]
    c4_path = tiger_proximity.render_yaml(c4_step, task_dir, cfg)
    rendered = yaml.safe_load(c4_path.read_text())
    expected = str(task_dir / "output" / "c3_tiger_roads.parquet")
    assert rendered["exposure"]["file"] == expected


def test_render_yaml_injects_output_grouping_episode(
    task_dir: Path, templates_dir: Path
) -> None:
    cfg = {"buffer": {"size": 1500}}
    c4_path = tiger_proximity.render_yaml(
        tiger_proximity._VARIABLE_TO_STEP["tiger_proximity"], task_dir, cfg
    )
    rendered = yaml.safe_load(c4_path.read_text())
    assert rendered["time"]["output_grouping"] == "episode"


def test_cache_key_differs_from_bg_ndi_wi_in_shape_and_boundary(
    task_dir: Path,
) -> None:
    """R1 lock: tiger_proximity and bg_ndi_wi share boundary=BG in metadata
    but emit incompatible C3 schemas. Cache keys MUST diverge in both the
    boundary tag AND overall shape (tiger has no raster suffix) for the
    same (input_parquet, buffer). A regression collapsing either delta
    would silently let one runner read the other's parquet.
    """
    from app.experiments import bg_ndi_wi

    cfg = {"buffer": {"size": 1500, "raster_res_m": 25}}
    tiger_key = tiger_proximity._cache_key(
        task_dir / "input.parquet", tiger_proximity._C3_STEP, cfg
    )
    bg_key = bg_ndi_wi._cache_key(
        task_dir / "input.parquet", bg_ndi_wi._C3_STEP, cfg
    )
    # Boundary tag differs.
    assert tiger_key.split("__")[1] == "BG_TIGER"
    assert bg_key.split("__")[1] == "BG"
    # Overall shape differs (bg has 4 segments incl. raster; tiger has 3).
    assert len(tiger_key.split("__")) == 3
    assert len(bg_key.split("__")) == 4
    assert tiger_key != bg_key


def test_merge_results_delegates_to_write_partial(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """merge_results is a thin wrapper into _merge.write_partial with the
    tiger-specific experiment_key and parquet_map."""
    out_dir = task_dir / "output"
    out_dir.mkdir()
    value_cols = ["dist_pri", "dist_sec", "dist_prisec"]
    pd.DataFrame({
        "PATID": ["p1", "p1", "p2"],
        "geoid": [0, 1, 2],
        **{c: [10.0, 20.0, 30.0] for c in value_cols},
    }).to_parquet(out_dir / "c4_tiger_roads.parquet", index=False)

    captured: dict = {}

    def fake_write_partial(*, task_dir, experiment_key, variables, parquet_map):
        captured["experiment_key"] = experiment_key
        captured["variables"] = variables
        captured["parquet_map"] = parquet_map
        return out_dir / f"result_{experiment_key}.csv"

    monkeypatch.setattr(
        "app.experiments._merge.write_partial", fake_write_partial
    )
    out = tiger_proximity.merge_results(task_dir, variables=["tiger_proximity"])
    assert out == out_dir / "result_tiger_proximity.csv"
    assert captured["experiment_key"] == "tiger_proximity"
    assert captured["variables"] == ["tiger_proximity"]
    assert captured["parquet_map"] == {"tiger_proximity": "c4_tiger_roads.parquet"}
```

Append to `backend/tests/test_merge_partial.py` (after `test_write_partial_value_cols_sourced_from_registry`):

```python
def test_write_partial_value_cols_picks_3_tiger_columns_from_one_parquet(tmp_path):
    """Sprint 5 B3 (spec L712): tiger_proximity ships a single parquet
    carrying all three TIGER distance columns. _merge.write_partial must
    pick exactly value_cols=[dist_pri, dist_sec, dist_prisec] from the
    registry — no extra/missing columns leaking through.
    """
    from app.experiments import _merge

    task_dir = tmp_path / "task-b3-tiger-merge"
    _write_input_csv(task_dir, n=5)
    _write_variable_parquet(
        task_dir / "output", "c4_tiger_roads", n=5,
        value_cols=["dist_pri", "dist_sec", "dist_prisec", "dist_unused"],
    )

    with patch("app.variable_registry.get_variable",
               return_value={
                   "value_cols": ["dist_pri", "dist_sec", "dist_prisec"]
               }):
        out = _merge.write_partial(
            task_dir=task_dir,
            experiment_key="tiger_proximity",
            variables=["tiger_proximity"],
            parquet_map={"tiger_proximity": "c4_tiger_roads.parquet"},
        )

    assert out == task_dir / "output" / "result_tiger_proximity.csv"
    df = pd.read_csv(out)
    assert {"dist_pri", "dist_sec", "dist_prisec"}.issubset(df.columns)
    assert "dist_unused" not in df.columns
```

Step 2: Run RED

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_tiger_proximity.py tests/test_merge_partial.py::test_write_partial_value_cols_picks_3_tiger_columns_from_one_parquet -v
```

Expected: all 9 new tests collected; failures depend on B2 landing state. If B2 already shipped the runner, expect 9 PASS — confirm via `pytest -v` that every test ID appears with `PASSED`. If B2's runner is incomplete (e.g. missing `_BOUNDARY = "BG_TIGER"`, missing `exposure.file` rewrite, or missing `output_grouping` injection), expect targeted failures: `test_cache_key_differs_*` fails on the boundary segment assertion, `test_render_yaml_c4_rewrites_exposure_*` fails with `KeyError: 'exposure'` or path mismatch, `test_render_yaml_injects_output_grouping_episode` fails with `KeyError: 'output_grouping'`.

Step 3: Implement minimal code

The runner code itself lands in B2. B3 only writes tests, so "minimal implementation" here is the test file plus the merge test append exactly as shown in Step 1. No production code edits in B3 — if a test FAILs because of a B2 oversight, narrowly fix B2's runner (e.g. add the `cfg["exposure"]["file"] = str(...)` line under the `else:` branch in `render_yaml`, or set `_BOUNDARY = "BG_TIGER"` at module top) and re-run. Do not edit the tests to match buggy production behaviour.

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_tiger_proximity.py tests/test_merge_partial.py -v
```

Expected: 8 passed in `test_tiger_proximity.py`; 8 passed in `test_merge_partial.py` (7 pre-existing + 1 new TIGER selection test).

Step 5: Full suite

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected per the canonical tally table near the top of the plan: **149 passed, 2 skipped, 9 deselected** — 139 Sprint-4 baseline + 1 from B1 + 8 new in `test_tiger_proximity.py` + 1 new in `test_merge_partial.py`. The `2 skipped, 9 deselected` numbers are the immovable baseline tuple pinned in B0 Step 5. No regressions in `test_bg_ndi_wi*` / `test_zcta5_cbp*` / `test_merge_partial`'s 7 prior tests.

Step 6: Commit

```bash
git add backend/tests/test_tiger_proximity.py backend/tests/test_merge_partial.py
git commit -m "$(cat <<'EOF'
test(tiger_proximity): unit + merge_partial coverage (Sprint 5 B3)

Mirrors test_zcta5_cbp.py with 8 tests pinning the runner contract:
plan validation, render_yaml C3-vs-C4 exposure rewrite, output_grouping
injection, R1 cache-key shape divergence from bg_ndi_wi, merge_results
delegation. Extends test_merge_partial.py with the 3-column TIGER
value_cols selection assertion (spec L712).
EOF
)"
```

**Notes:**
- Depends on B2: imports `app.experiments.tiger_proximity` directly; B2 must have shipped the runner module with `_C3_STEP`, `_VARIABLE_TO_STEP`, `_BOUNDARY = "BG_TIGER"`, `plan`, `render_yaml`, `_cache_key`, and `merge_results`. If B2 deferred any of those, B3 fails RED at import time.
- The `test_cache_key_differs_from_bg_ndi_wi_in_shape_and_boundary` test is the R1 risk lock from spec L733 — it imports `bg_ndi_wi` to compare both keys live rather than asserting a hard-coded string, so future legitimate cache-key shape changes (e.g. adding a year segment) still pass as long as the two runners stay differentiated.
- `test_render_yaml_c3_leaves_exposure_untouched` does double duty: it pins the C3 template's lack of `exposure` AND confirms `render_yaml`'s `if step.is_c3:` branch doesn't accidentally write the field. If B2 lifts the rewrite outside the `if` guard, this test fails.
- The merge test reuses the existing `_write_input_csv` / `_write_variable_parquet` helpers at the top of `test_merge_partial.py` — no helper duplication.
- Test count math: see canonical tally table near the top of the plan. B3 contributes +9 unit tests (8 in `test_tiger_proximity.py` + 1 in `test_merge_partial.py`), bringing the default-suite running total to 149. Final Sprint 5 backend totals (B6): **150 passed, 2 skipped in default suite** + 2 `@pytest.mark.integration` (B4 + B5) deselected by default. The 2 skipped are the pre-existing baseline skips pinned in B0 Step 5 — Sprint 5 adds no new fixture-gated skips.

---

### Task B4: Single-experiment integration test (test_e2e_tiger_proximity_cohort)

**Files:**
- Create: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_e2e_tiger_proximity_cohort.py`
- Test: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_e2e_tiger_proximity_cohort.py`

**Goal:** Prove that the `tiger_proximity` runner — dispatched through `task_manager.start_task` end-to-end — drives `status.json` to `finished`, emits a `result_tiger_proximity.csv` with the three `dist_*` value columns, and joins back to the input cohort on `(pid, episode_id)` so row counts match (the runtime proof that Phase A's `output_grouping: episode` dispatch flows through the precomputed_areal linkage all the way to the merged result).

**Context:** You are on branch `feat/sprint-5-tiger-proximity` in the spacescans-web worktree at `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity`. Phase A has already landed on pipeline `main` (editable install picks it up); B1–B3 have already added the `tiger_proximity` metadata entry, the runner module at `backend/app/experiments/tiger_proximity.py`, and its eight unit tests in `backend/tests/test_tiger_proximity.py`. The default backend suite (post-B3, before this task) collects ~150 tests with 9 deselected by `addopts = -m "not integration"`. This task adds the first integration-marked end-to-end run of the new variable on the existing 5-row demo cohort (`fixtures/patients_5.csv`); the second integration test (4-variable, 3-experiment dispatch) lands in B5. Reuses the exact shape of `backend/tests/test_e2e_zcta5_cbp_cohort.py` (Sprint 3) — same `_integration_available` gate, same `tmp_path`/`monkeypatch` reload pattern, same 180s polling deadline.

Step 1: Write failing test

Create `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_e2e_tiger_proximity_cohort.py`:

```python
"""Sprint 5 e2e: single-experiment tiger_proximity via task_manager.start_task.

Proves the runtime path Phase A unlocked: precomputed_areal_linkage's
output_grouping='episode' branch fires, the pipeline emits one row per
(PATID, geoid), _merge.write_partial joins on (pid, episode_id), and
result_tiger_proximity.csv carries the three dist_* value columns one-to-one
with the input cohort.
"""
import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config


_DIST_COLUMNS = ["dist_pri", "dist_sec", "dist_prisec"]


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    tiger_c4 = app.config.settings.SPACESCANS_DATA_DIR / "data_full" / "TIGER" / "C4"
    if not tiger_c4.is_dir():
        return False
    if not any(tiger_c4.glob("tiger*_roads")):
        return False
    try:
        import pyreadr  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / TIGER C4 / pipeline CLI / pyreadr not configured",
)


@pytest.fixture
def task_with_tiger_proximity_cohort(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-tiger-proximity")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["tiger_proximity"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_tiger_proximity_cohort(task_with_tiger_proximity_cohort):
    task_id, task_dir = task_with_tiger_proximity_cohort

    from app.task_manager import start_task
    start_task(task_id)

    status = {}
    deadline = time.monotonic() + 180.0
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 180s; last status={status}")

    assert status["status"] == "finished", f"unexpected terminal status: {status}"

    experiments = status.get("experiments", {})
    assert "tiger_proximity" in experiments, (
        f"expected tiger_proximity slot in status.experiments; got {list(experiments)}"
    )
    assert experiments["tiger_proximity"]["status"] == "finished"
    assert experiments["tiger_proximity"]["progress"] == 1.0

    logs_path = task_dir / "logs.jsonl"
    assert logs_path.exists(), "logs.jsonl must be written"
    log_lines = [json.loads(line) for line in logs_path.read_text().splitlines() if line.strip()]
    log_steps = {entry.get("step") for entry in log_lines if entry.get("step")}
    assert "c3_tiger_roads" in log_steps, f"expected c3_tiger_roads in logs; got {log_steps}"
    assert "c4_tiger_roads" in log_steps, f"expected c4_tiger_roads in logs; got {log_steps}"

    result_partial = task_dir / "output" / "result_tiger_proximity.csv"
    assert result_partial.exists(), "result_tiger_proximity.csv must be written"
    result_csv = task_dir / "output" / "result.csv"
    assert result_csv.exists(), "fan-in result.csv must be written"

    input_df = pd.read_csv(task_dir / "input.csv")
    df = pd.read_csv(result_csv)

    assert len(df) == len(input_df), (
        f"row count must match cohort episodes; "
        f"input={len(input_df)} result={len(df)} "
        "(if mismatched, the (pid, episode_id) join collapsed — "
        "Phase A output_grouping=episode dispatch likely failed)"
    )
    missing = [c for c in _DIST_COLUMNS if c not in df.columns]
    assert not missing, f"missing dist_* columns: {missing}; got {list(df.columns)}"
```

Step 2: Run RED

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_e2e_tiger_proximity_cohort.py -v -m integration
```

Expected failure mode (assuming SPACESCANS_DATA_DIR + TIGER C4 fixtures are in place): test FAILS at one of (a) status timeout — runner exits with `error` because the dispatcher cannot find a `tiger_proximity` slot before the runner is wired in; (b) `KeyError: 'tiger_proximity'` from `experiments` map; or (c) `AssertionError: result_tiger_proximity.csv must be written`. If the data fixtures are absent the test is SKIPPED, not failed — in that case rerun on a host with `SPACESCANS_DATA_DIR/data_full/TIGER/C4/tiger*_roads/` populated before declaring RED.

Step 3: Implement minimal code

No source code is added in this task — B2/B3 already shipped the runner + metadata. RED here means the test is correctly authored against the live runner: the test FILE is the deliverable. If RED is caused by a real runner bug (not fixture absence), pause this task and fix the runner in tiger_proximity.py before continuing; do NOT loosen the assertions.

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_e2e_tiger_proximity_cohort.py -v -m integration
```

Expected: 1 passed in ~60s (first run may be ~90s on a cold `cache/C3/tiger_roads_filtered/`).

Step 5: Full suite

Default suite (integration deselected):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected cumulative per the canonical tally table near the top of the plan: **149 passed, 2 skipped, 10 deselected** — web baseline 139 + B1 (+1 test_variable_registry) + B3 (+8 test_tiger_proximity, +1 test_merge_partial); B4 itself adds 0 default-suite tests and +1 `@pytest.mark.integration` test (which bumps the deselect count from 9 to 10). Running default count after B4 is unchanged from after B3 = 149.

Integration suite (`make test-integration` or explicit `-m integration`):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q -m integration
```

Expected: 4 passed (Sprint 3's `test_e2e_zcta5_cbp_cohort` + `test_e2e_multi_experiment_cohort` + `test_bg_ndi_wi_integration` + this new test), in ~5-6 min.

Step 6: Commit

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity
git add backend/tests/test_e2e_tiger_proximity_cohort.py
git commit -m "test(tiger_proximity): single-experiment e2e cohort integration test

Drives task_manager.start_task end-to-end on patients_5.csv with the
new tiger_proximity variable. Asserts status.json transitions to
finished, logs.jsonl carries c3_tiger_roads + c4_tiger_roads entries,
result_tiger_proximity.csv exists, and result.csv joins back to the
input cohort one-to-one with all three dist_* columns present.

This is the runtime proof that Phase A's precomputed_areal
output_grouping=episode dispatch flows through to merge_results
without collapsing on episode_id (Sprint 5 acceptance gate B4)."
```

**Notes:**
- Depends on B3 (`backend/app/experiments/tiger_proximity.py` runner + unit tests must be present and green before this integration test is meaningful).
- Marked `@pytest.mark.integration` so the default `pytest -q` suite is unaffected; only `make test-integration` / `pytest -m integration` runs it. Wall-clock budget ~60s on a warm `cache/C3/tiger_roads_filtered/`; first run on a cold cache is ~90s. The fixture-level gate (`tiger_c4 / glob("tiger*_roads")`) is stricter than the other e2e tests' BG-only gate because tiger_proximity hard-requires the per-county TIGER zips that Sprint 5 R2 flagged.
- The `len(df) == len(input_df)` assertion is necessary-but-not-sufficient for catching Risk R3 (stale pipeline wheel silently emits patient-level rows, `_merge.write_partial` then collapses one-to-many on episode_id). With `patients_5.csv` (5 unique pids, 1 episode each) `input_df` length is 5; episode_id values are 0..4 from `csv_to_parquet`; an `output_grouping=patient` regression would still produce 5 rows here, so this integration test alone does NOT close R3. **R3 close-out lives in Task A2's pipeline-side smoke** (`test_tiger_roads_demo_episode_branch_row_count`, which builds an 8-row multi-episode cohort in `tmp_path` and asserts `n_rows > n_patid` strictly) — that smoke is what actually catches the stale-pipeline regression. B5 also uses `patients_5.csv` (single episode per pid) and likewise does NOT close R3; both web-side integration tests are smoke-level acceptance gates, not R3 regression guards. Do not chase a "multi-episode" web fixture for this purpose — the R3 guard belongs upstream in the pipeline smoke.
- Do NOT add a `force_recompute` knob or a cache-warmup `start_task` call; the test must run against whatever cache state CI provides. If cold-cache 90s exceeds the 180s deadline on slower runners, raise the deadline rather than warming the cache.
- The `monkeypatch.setenv("DATA_DIR", ...)` + `importlib.reload` pattern mirrors Sprint 3's e2e fixtures exactly; do NOT factor it into a shared conftest fixture in this task — that refactor is out of scope and would touch the other two e2e files.

---

### Task B5: 3-experiment dispatch integration + task_manager regression

**Files:**
- Create: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_e2e_multi_experiment_with_tiger.py`
- Modify: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_task_manager_dispatch.py`
- Test: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_e2e_multi_experiment_with_tiger.py`, `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend/tests/test_task_manager_dispatch.py`

**Goal:** Lock in that a 4-variable selection across 3 experiments dispatches in metadata-file order (`bg_ndi_wi` → `zcta5_cbp` → `tiger_proximity`) and that the merged `result.csv` carries every column from all three runners.

**Context:** Sprint 3 introduced the multi-experiment dispatcher (`test_e2e_multi_experiment.py`, 2-experiment); Sprint 5 adds a third experiment (`tiger_proximity`) catalogued for `[2013, 2019]`. The dispatch-order contract from spec L602-605 is "JSON-file order of first experiment appearance" — the metadata entry is appended at the end of `variable_metadata.json`, so `tiger_proximity` is the third runner. B1-B4 have already landed: metadata entry, runner module, unit tests, and a single-experiment integration test. This task closes the loop by exercising the wizard's worst-case load (NDI + Walkability + cbp_zcta5 + tiger_proximity) end-to-end on the existing `patients_5.csv` fixture, plus a fast unit-level regression on the dispatcher.

Step 1: Write failing test

Create `backend/tests/test_e2e_multi_experiment_with_tiger.py`:

```python
"""Sprint 5 e2e: 4-variable, 3-experiment dispatch (bg_ndi_wi + zcta5_cbp + tiger_proximity)."""
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
_DIST_COLUMNS = ["dist_pri", "dist_sec", "dist_prisec"]


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    if not (app.config.settings.SPACESCANS_DATA_DIR
            / "data_full/BG_FL/C3/tiger2010_bg10_states").exists():
        return False
    if not (app.config.settings.SPACESCANS_DATA_DIR / "TIGER" / "C4").is_dir():
        return False
    try:
        import pyreadr  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / pipeline CLI / TIGER data / pyreadr not configured",
)


@pytest.fixture
def task_with_three_experiments(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-multi-with-tiger")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["ndi", "walkability", "cbp_zcta5", "tiger_proximity"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_multi_experiment_with_tiger_cohort(task_with_three_experiments):
    task_id, task_dir = task_with_three_experiments

    from app.task_manager import start_task
    start_task(task_id)

    deadline = time.monotonic() + 300.0
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 300s; last status={status}")

    assert status["status"] == "finished"
    assert status["progress"] == 1.0
    assert len(status["steps"]) > 0

    experiments = status.get("experiments", {})
    assert set(experiments.keys()) == {"bg_ndi_wi", "zcta5_cbp", "tiger_proximity"}
    for key in ("bg_ndi_wi", "zcta5_cbp", "tiger_proximity"):
        assert experiments[key]["status"] == "finished", f"{key} not finished"
        assert experiments[key]["progress"] == 1.0
        assert experiments[key]["steps"], f"{key} slot steps must be populated"

    # Spec L604-605: metadata-file order is bg_ndi_wi → zcta5_cbp → tiger_proximity.
    bg_start = experiments["bg_ndi_wi"]["started_at"]
    zc_start = experiments["zcta5_cbp"]["started_at"]
    tg_start = experiments["tiger_proximity"]["started_at"]
    assert bg_start <= zc_start <= tg_start, (
        f"expected metadata-file dispatch order; "
        f"bg={bg_start} zc={zc_start} tg={tg_start}"
    )

    for runner in ("bg_ndi_wi", "zcta5_cbp", "tiger_proximity"):
        assert (task_dir / "output" / f"result_{runner}.csv").exists(), runner

    result_csv = task_dir / "output" / "result.csv"
    assert result_csv.exists()
    df = pd.read_csv(result_csv)

    assert "ndi" in df.columns
    assert "NatWalkInd" in df.columns
    missing_r = [c for c in _R_STAR_COLUMNS if c not in df.columns]
    assert not missing_r, f"missing r_* columns after fan_in: {missing_r}"
    missing_dist = [c for c in _DIST_COLUMNS if c not in df.columns]
    assert not missing_dist, f"missing dist_* columns after fan_in: {missing_dist}"

    bg_df = pd.read_csv(task_dir / "output" / "result_bg_ndi_wi.csv")
    zc_df = pd.read_csv(task_dir / "output" / "result_zcta5_cbp.csv")
    tg_df = pd.read_csv(task_dir / "output" / "result_tiger_proximity.csv")
    assert len(df) == len(bg_df) == len(zc_df) == len(tg_df)
```

Append to `backend/tests/test_task_manager_dispatch.py` (after the last test):

```python
def test_three_experiment_dispatch_preserves_metadata_order(
    task_dir_with_config, monkeypatch
):
    """Sprint 5: 4 variables across 3 experiments dispatch in metadata-file order.

    Spec L602-605: dispatch order is JSON-file order of first experiment
    appearance — bg_ndi_wi (ndi), zcta5_cbp (cbp_zcta5), tiger_proximity
    (tiger_proximity), in that order regardless of the variable
    selection order in config.json.
    """
    import json as _json
    from app import dispatcher

    # Rewrite config to include all 4 variables in deliberately scrambled order.
    cfg_path = task_dir_with_config / "config.json"
    cfg = _json.loads(cfg_path.read_text())
    cfg["variables"] = ["tiger_proximity", "cbp_zcta5", "ndi", "walkability"]
    cfg_path.write_text(_json.dumps(cfg))

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
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
    fan_in = MagicMock()
    monkeypatch.setattr("app.experiments._merge.fan_in", fan_in)

    result = dispatcher.dispatch(str(task_dir_with_config))

    assert len(_FakePopen.instances) == 3
    assert "app.experiments.bg_ndi_wi" in _FakePopen.instances[0].cmd
    assert "app.experiments.zcta5_cbp" in _FakePopen.instances[1].cmd
    assert "app.experiments.tiger_proximity" in _FakePopen.instances[2].cmd
    assert result["completed"] == ["bg_ndi_wi", "zcta5_cbp", "tiger_proximity"]
    fan_in.assert_called_once_with(
        task_dir_with_config, ["bg_ndi_wi", "zcta5_cbp", "tiger_proximity"]
    )
```

Step 2: Run RED

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_task_manager_dispatch.py::test_three_experiment_dispatch_preserves_metadata_order tests/test_e2e_multi_experiment_with_tiger.py -v
```

Expected:
- `test_three_experiment_dispatch_preserves_metadata_order`: PASS immediately if B1-B3 are landed (dispatcher is already order-preserving; this test is a regression lock). If B2's `variable_metadata.json` entry is missing it will still PASS because the test mocks `variables_by_experiment`. Treat this as a "regression-lock" test, not pure RED.
- `test_e2e_multi_experiment_with_tiger_cohort`: SKIP under `not _integration_available()` on a runner without TIGER data; on the integration runner it FAILS with `AssertionError: experiments[tiger_proximity] not finished` or a missing `dist_*` column on `result.csv` only if B3 (`tiger_proximity.py`) or `_merge.fan_in` glob hasn't been wired to pick up `result_tiger_proximity.csv`.

Step 3: Implement minimal code

**No production edits expected; this task is regression-lock only.** B1-B4 already provide:
- metadata entry (B1) → `variables_by_experiment` returns `tiger_proximity` last,
- runner (B2) → emits `result_tiger_proximity.csv` with `dist_*` columns,
- `_merge.fan_in` (already glob-driven on `result_*.csv` per Sprint 3) → joins the third file on `(pid, episode_id)`.

If — and only if — running Step 2 RED reveals a concrete bug (not just a missing test), open a separate sub-step here with an explicit `Edit` block naming the file, the exact line numbers, and the literal `old_string` / `new_string` replacement. Do NOT paste comment-only Python or free-text directives ("trace through dispatch", "verify the existing implementation is data-driven") in lieu of a real diff — that style is the kind of vague non-edit the plan-review lens explicitly flags. If you find yourself wanting to write "verify X" instead of "edit X to do Y", the right action is either (a) confirm RED was a test bug and fix the test, or (b) escalate the production gap to a dedicated task with its own RED/GREEN/Commit cycle, not a hand-wavy sub-step here.

Step 4: Confirm GREEN

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_task_manager_dispatch.py::test_three_experiment_dispatch_preserves_metadata_order -v
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -m integration tests/test_e2e_multi_experiment_with_tiger.py -v
```

Expected:
- Unit regression: 1 PASSED in <1s.
- Integration: 1 PASSED in ~210s on the TIGER-equipped runner; SKIPPED otherwise.

Step 5: Full suite

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -m integration -q
```

Expected default suite per the canonical tally table near the top of the plan: **150 passed, 2 skipped, 11 deselected** — 139 baseline + 1 from B1 (`test_variable_registry.py`) + 8 from B3 (`test_tiger_proximity.py`) + 1 from B3 (`test_merge_partial.py`) + 1 from B5 (`test_task_manager_dispatch.py`). NOTE: `test_tiger_proximity.py` is created in **B3, not B1** — earlier drafts of this plan misattributed those 8 tests; the authoritative attribution is the canonical tally table. Integration suite: **+2** (`test_e2e_tiger_proximity_cohort` from B4 + `test_e2e_multi_experiment_with_tiger_cohort` from this task), on top of the pre-Sprint-5 integration tests, all PASSED on the equipped runner. The deselect count is 11 = 9 baseline + 2 newly-introduced `@pytest.mark.integration` files from B4 and B5.

Step 6: Commit

```bash
git add backend/tests/test_e2e_multi_experiment_with_tiger.py \
        backend/tests/test_task_manager_dispatch.py
git commit -m "test(experiments): 3-experiment dispatch e2e + task_manager order regression (Sprint 5 B5)"
```

**Notes:**
- The integration test uses the existing `backend/tests/fixtures/patients_5.csv` — no new fixture; 5 patients × 3 experiments stays under the 300s deadline (Sprint 3's 2-experiment took ~120s; tiger_proximity adds ~90s for cold `cache/C3/tiger_roads_filtered/`, which the B4 single-experiment test will have warmed if the integration runner reuses cache between tests in the same session — but the test must tolerate a cold cache because pytest may reorder files). NOTE: like B4, B5 uses `patients_5.csv` (single episode per pid) so neither integration test closes Risk R3 (stale-pipeline regression) on its own — R3 is closed by Task A2's pipeline-side multi-episode smoke. See B4 Notes for the full rationale.
- The `started_at` ordering assertion (`bg_start <= zc_start <= tg_start`) is the on-disk witness of the metadata-file-order contract; the unit-level `_FakePopen.instances` ordering is the synchronous one. Both must hold.
- The unit regression test deliberately scrambles `config.json["variables"]` order to prove dispatch order is driven by metadata file order, not selection order — this is the contract spec L602-605 names.
- Depends on B4 (single-experiment integration must already pass — if `tiger_proximity` end-to-end is broken in isolation, the 3-experiment test will fail in the same way but with noisier failure mode).
- Web baseline arithmetic: see canonical tally table near the top of the plan. 139 (post-Sprint-4 main) + 1 (B1 `test_variable_registry.py`) + 8 (B3 `test_tiger_proximity.py`) + 1 (B3 `test_merge_partial.py`) + 1 (B5 `test_task_manager_dispatch.py`) = **150 default-suite tests**. The two `@pytest.mark.integration` tests (B4 + B5) are deselected from this count, not skipped — they appear as `2 deselected` (on top of the 9 baseline `deselected`).
- If `fan_in` in `_merge.py` is implemented with a hard-coded set of experiment keys (Sprint 3 carryover), the e2e RED will surface a missing-column failure on `result.csv` — fix by making the keys list dispatcher-supplied, not module-constant.

---

### Task B6: Phase B wrap-up: manual_e2e Sprint 5 section + frontend no-op verify + PR

**Files:**
- `/Users/xai/Desktop/spacescans-project/spacescans-web/backend/tests/manual_e2e.md` (modify)
- `/Users/xai/Desktop/spacescans-project/spacescans-web/frontend/src/components/wizard/variables-step.tsx` (verify untouched)
- `/Users/xai/Desktop/spacescans-project/spacescans-web/frontend/src/components/wizard/variable-card.tsx` (verify untouched)
- `/Users/xai/Desktop/spacescans-project/spacescans-web/frontend/src/components/wizard/variable-coverage-panel.tsx` (verify untouched)
- `/Users/xai/Desktop/spacescans-project/spacescans-web/frontend/src/lib/variable-grouping.ts` (verify untouched)

**Goal:** Append the Sprint 5 manual-smoke section to `manual_e2e.md`, visually confirm the TIGER card renders in the Block Group section with zero frontend edits (G2 invariant), run the full default pytest + `tsc --noEmit`, then open the PR with the Sprint 5 title.

**Context:** B5 just landed the 4-variable multi-experiment integration test, taking the cumulative backend count to **150 tests** (139 baseline + 11 unit additions across B1/B3/B5 per the canonical tally table near the top of the plan: B1=+1 `test_variable_registry.py`, B3=+9 (8 `test_tiger_proximity.py` + 1 `test_merge_partial.py`), B5=+1 `test_task_manager_dispatch.py`; the 2 `@pytest.mark.integration` files from B4 and B5 are deselected by default). The runner, metadata entry, registry validator, dispatch table, and shared-merge wiring are all in place. The frontend is supposed to be completely untouched — Sprint 5's research (spec L607-624) showed that `groupByBoundary` + `VariableCard`'s three-chip render + `VariableCoveragePanel`'s `boundary`/`coverage_years` consumption all work for `tiger_proximity` out of the box. This task is the doc + verify + PR seam.

Step 1: Write failing test (verification gate, not pytest — there's no test code to add this task). Define the falsifiable pre-PR gates as a shell oneliner that must exit 0:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity && \
  test "$(git diff --name-only main..HEAD -- \
    frontend/src/components/wizard/variables-step.tsx \
    frontend/src/components/wizard/variable-card.tsx \
    frontend/src/components/wizard/variable-coverage-panel.tsx \
    frontend/src/lib/variable-grouping.ts | wc -l | tr -d ' ')" = "0" \
  && grep -q "^## Sprint 5 — TIGER Road Proximity" backend/tests/manual_e2e.md \
  && grep -q "inspect.getsource(precomputed_areal_linkage)" backend/tests/manual_e2e.md \
  && grep -q "unsupported output_grouping: 'foo'" backend/tests/manual_e2e.md
```

Step 2: Run RED. Before editing, the gate fails on the manual_e2e grep (Sprint 5 section absent) and the frontend-diff check passes (no edits yet). Expected output:

```
$ bash -c '<oneliner above>'; echo "exit=$?"
exit=1
$ git diff --name-only main..HEAD -- frontend/src/components/wizard/variables-step.tsx ...
$ # (empty — G2 invariant currently holds)
$ grep -c "^## Sprint 5 — TIGER Road Proximity" backend/tests/manual_e2e.md
0
```

Step 3: Implement minimal code. Append the Sprint 5 section verbatim from spec L797-843 to `backend/tests/manual_e2e.md` (file currently ends at line 174 after Sprint 3's "rm -rf backend/data/c3_cache/" block):

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

Then run the frontend no-op verification (G2 invariant + the live render check the doc describes):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity
# G2 hard invariant — the four frontend files must be byte-identical to main
git diff --stat main..HEAD -- \
  frontend/src/components/wizard/variables-step.tsx \
  frontend/src/components/wizard/variable-card.tsx \
  frontend/src/components/wizard/variable-coverage-panel.tsx \
  frontend/src/lib/variable-grouping.ts
# Expected output: empty (no diffstat lines)

# Boot the stack and confirm 4 cards render
( cd backend && /Users/xai/miniconda3/envs/spacescans/bin/python -m uvicorn app.main:app --reload --port 8000 ) &
( cd frontend && npm run dev ) &
# Open http://localhost:5173 → New task → Variables step
# Confirm: "Block Group" section has 3 cards (NDI, EPA Walkability Index, TIGER Road Proximity);
#          "ZCTA5" section has 1 card (Community Organization Density (ZBP)).
#          TIGER card chips read: meters / 2013–2019 / BG.
# Tick the TIGER card — coverage panel mounts inline, same shape as Sprint 3.
```

Step 4: Confirm GREEN. The gate oneliner from Step 1 now exits 0:

```bash
$ bash -c '<oneliner from Step 1>'; echo "exit=$?"
exit=0
```

And the visual check: 4 cards in 2 boundary groups, TIGER chips correct, coverage panel mounts on tick. The four protected frontend files have zero diff vs `main` (G2 invariant holds).

Step 5: Full suite. Run the full default pytest suite + tsc:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
# Expected per the canonical tally table near the top of the plan:
#   "150 passed, 2 skipped, 11 deselected"
#   (139 web baseline + 11 Sprint 5 unit additions:
#    + 1 test_variable_registry.py        [B1]
#    + 8 test_tiger_proximity.py          [B3]
#    + 1 test_merge_partial.py            [B3]
#    + 1 test_task_manager_dispatch.py    [B5]
#    = 150 default-suite tests, 11 new vs main;
#    the 2 @pytest.mark.integration files from B4 and B5 contribute
#    +2 deselected (baseline 9 -> 11). The "2 skipped" tuple is the
#    immovable baseline pinned in B0 Step 5 — Sprint 5 adds no new
#    fixture-gated skips.)

cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/frontend
npx tsc --noEmit
# Expected: clean (zero errors) — frontend was untouched.
```

Step 6: Commit + open PR (hold push until controller decision).

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity
git add backend/tests/manual_e2e.md
git commit -m "docs(tests): manual_e2e Sprint 5 section — TIGER proximity + episode dispatch smoke"

# Open the PR but do NOT push beyond the working branch's tracking remote until
# the controller decides. If push is approved:
git push -u origin feat/sprint-5-tiger-proximity
gh pr create \
  --base main \
  --head feat/sprint-5-tiger-proximity \
  --title "feat(experiments): tiger_proximity runner + precomputed_areal episode dispatch (Sprint 5)" \
  --body "$(cat <<'EOF'
## Summary
- Adds the `tiger_proximity` BG variable (3 columns: dist_pri, dist_sec, dist_prisec, meters, 2013–2019).
- Routes BG-level distance through the existing precomputed_areal C4 with `output_grouping: episode` (Phase A patch landed on `spacescans-project@pkg/pypi-only`).
- Sprint 5 is a pure-additive seam: registry validator, dispatch table, shared-merge wiring, runner module, metadata entry. Zero frontend edits (G2 invariant).

## Test plan
- [x] `pytest -q` → 150 passed, 2 skipped, 11 deselected (the 2 `@pytest.mark.integration` files added in B4+B5 plus the 9 baseline deselected).
- [x] Integration: `pytest -m integration backend/tests/test_e2e_tiger_proximity_cohort.py backend/tests/test_e2e_multi_experiment_with_tiger.py` → 2 passed.
- [x] `tsc --noEmit` clean.
- [x] Manual smoke per `backend/tests/manual_e2e.md` Sprint 5 section: 4 cards render (3 BG, 1 ZCTA5), 4-variable run produces NDI + NatWalkInd + 10 r_* + 3 dist_* columns, C3 cache hit on second run, explicit-typo ValueError negative test.

## G-invariants
- G1: only the `tiger_proximity` slot is filled; the remaining 5 experiments stay deferred.
- G2: `variables-step.tsx`, `variable-card.tsx`, `variable-coverage-panel.tsx`, `variable-grouping.ts` byte-identical to `main`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Notes:**
- This task adds **zero** pytest tests; the verification gate is the shell oneliner in Step 1, the full-suite run in Step 5, and the live frontend render the manual_e2e section describes. Cumulative backend count stays at **150** per the canonical tally table near the top of the plan (139 baseline + 11 new unit tests: +1 B1 / +9 B3 / +1 B5; the 2 `@pytest.mark.integration` tests from B4+B5 are deselected by default, not skipped).
- The negative test (step 5 of the manual section) is deliberately the **explicit-typo** form, not absent-field — `TimeConfig.output_grouping` defaults to `"patient"` at the dataclass level (`src/spacescans/models/config.py:100` in the pipeline repo), so removing the key falls back silently to patient-grouping. The spec called this out explicitly at L838-843; reproduce the wording verbatim so a future reader doesn't "simplify" the test into uselessness.
- The Phase A `inspect.getsource(precomputed_areal_linkage)` pre-flight check is the only way the smoke section can detect a stale editable install — flag this prominently when handing off to a smoke-runner; if `'episode' not in inspect.getsource(...)` the dispatcher won't route correctly and the 4-variable task will silently fall back to patient-grouping for the BG_TIGER linkage.
- Push is **held** until controller decision per task brief. The `gh pr create` invocation in Step 6 is the final action; do not run it before the controller signs off on the diff.
- Depends on B5 (the 4-variable multi-experiment integration test must already be committed so the cumulative-count claim of 150 + 2-skipped is accurate).
- The PR title is fixed by spec L698-699 — do not paraphrase.

---

## Task ordering reference

```json
[
  {
    "key": "A0",
    "title": "Pipeline pre-flight: verify env, TIGER fixture, baseline tests",
    "summary": "Confirm the spacescans-project repo on pkg/pypi-only is clean, the editable install resolves to /Users/xai/Desktop/spacescans-project/src/spacescans, the shipped configs/c4/tiger_roads_demo.yaml + annual_proximity_demo100k.parquet + cache/C3/tiger_roads_filtered/ are present (seed via `spacescans run configs/c3/tiger_roads_demo.yaml` if absent), and capture the pytest baseline so we can prove Phase A adds tests without regressing yearly_areal / yearly_areal_bg_vintage / static_areal. No code edits.",
    "phase": "A",
    "spec_refs": [
      "L632-641 Implementation order Phase A step 1",
      "L734 R2 pre-flight"
    ],
    "depends_on": [],
    "estimated_minutes": 20,
    "files_to_create": [],
    "files_to_modify": [],
    "test_files": []
  },
  {
    "key": "A1",
    "title": "precomputed_areal_linkage.py output_grouping dispatch (RED → GREEN)",
    "summary": "TDD the SQL-clause-level dispatch at src/spacescans/linkage/precomputed_areal_linkage.py:114-121. First write tests/test_precomputed_areal_linkage.py with 3 tests (patient branch keeps GROUP BY PATID and PATID is unique; episode branch produces (PATID, geoid) uniqueness with strictly more rows; explicit unknown string raises ValueError matching 'unsupported output_grouping' byte-for-byte with yearly_areal_linkage.py:55-58). Commit a small tests/fixtures/precomputed_areal_mini.parquet (~10 rows, 2 multi-episode patients). Confirm RED, then replace the terminal SELECT with the two-branch literal SQL per spec L299-322, confirm GREEN, then run the full pipeline suite to prove no regression in yearly_areal / static_areal / bg_vintage.",
    "phase": "A",
    "spec_refs": [
      "L258-342 Phase A target code",
      "L344-401 Pipeline unit test plan",
      "L722-727 pipeline test count delta"
    ],
    "depends_on": [
      "A0"
    ],
    "estimated_minutes": 75,
    "files_to_create": [
      "tests/test_precomputed_areal_linkage.py",
      "tests/fixtures/precomputed_areal_mini.parquet"
    ],
    "files_to_modify": [
      "src/spacescans/linkage/precomputed_areal_linkage.py"
    ],
    "test_files": [
      "tests/test_precomputed_areal_linkage.py"
    ]
  },
  {
    "key": "A2",
    "title": "tiger_roads_demo.yaml + pipeline smoke (explicit episode declaration)",
    "summary": "Edit configs/c4/tiger_roads_demo.yaml time block to declare `output_grouping: episode` explicitly (only in-tree `linkage_pattern: precomputed_areal` config, confirmed via `grep -rn 'linkage_pattern: precomputed_areal' configs/`). Implement the spec's smoke-fixture choice: extend the demo cohort fixture so some PATIDs map to multiple geoid values (option b in spec L382-394), then add a tiger_roads_demo end-to-end assertion to tests/test_pipeline_smoke.py that the C4 row count equals count(distinct (PATID, geoid)) and is strictly > count(distinct PATID). Run `pytest -k 'precomputed_areal or tiger_roads'` plus full suite.",
    "phase": "A",
    "spec_refs": [
      "L66-68 [B3]",
      "L370-401 smoke fixture caveat",
      "L651-662 implementation step 5",
      "L722-727 pipeline smoke delta"
    ],
    "depends_on": [
      "A1"
    ],
    "estimated_minutes": 60,
    "files_to_create": [],
    "files_to_modify": [
      "configs/c4/tiger_roads_demo.yaml",
      "tests/test_pipeline_smoke.py"
    ],
    "test_files": [
      "tests/test_pipeline_smoke.py"
    ]
  },
  {
    "key": "A3",
    "title": "Phase A wrap-up: regression sweep, commit, publish for Phase B",
    "summary": "Final full pipeline suite (~4 new tests vs baseline). Review the Phase A diff (3 commits: dispatch + tests + config/smoke). Stay on `pkg/pypi-only` (the active branch per the orchestrator brief — no merge to a separate main), tag/note the editable-install handoff: verify `python -c \"from spacescans.linkage import precomputed_areal_linkage; import inspect; print('episode' in inspect.getsource(precomputed_areal_linkage))\"` returns True so Phase B's runner can see the dispatch. PR title `feat(linkage): precomputed_areal output_grouping dispatch (Sprint 5 Phase A)`. Decision point: hold push to origin until Phase B integration verifies.",
    "phase": "A",
    "spec_refs": [
      "L663-674 Phase A steps 6-8",
      "L735 R3 editable-install"
    ],
    "depends_on": [
      "A2"
    ],
    "estimated_minutes": 25,
    "files_to_create": [],
    "files_to_modify": [],
    "test_files": []
  },
  {
    "key": "B0",
    "title": "Web worktree setup on feat/sprint-5-tiger-proximity + Phase A handoff verify",
    "summary": "Create git worktree spacescans-web/.worktrees/feat-sprint-5 on new branch feat/sprint-5-tiger-proximity off main. Migrate gitignored backend/.env + backend/data/variable_metadata.json from the main checkout, symlink frontend/node_modules. Verify Phase A is live in the web's pipeline env via the inspect.getsource grep from spec L678-682. Capture baseline pytest count + tsc clean state.",
    "phase": "B",
    "spec_refs": [
      "L676-682 Phase B implementation step 1",
      "L735 R3"
    ],
    "depends_on": [
      "A3"
    ],
    "estimated_minutes": 25,
    "files_to_create": [],
    "files_to_modify": [],
    "test_files": []
  },
  {
    "key": "B1",
    "title": "variable_metadata.json tiger_proximity entry + schema/registry RED→GREEN",
    "summary": "TDD the metadata entry. First append a test to backend/tests/test_variable_registry.py: 'registry accepts tiger_proximity entry with 3 value_cols and BG boundary'. Confirm RED (registry whitelist rejects an entry whose experiment module is not yet present — expected gating per spec L683-685). Add the JSON block per spec L570-582 (label, description naming 'US Census TIGER/Line shapefiles', boundary BG, coverage_years [2013, 2019], coverage_region CONUS, experiment tiger_proximity, variable_type continuous, display_unit meters, value_cols [dist_pri, dist_sec, dist_prisec]). Server will still refuse to boot because the experiment module is missing — that gate clears in B2; this commit leaves the schema half landed deliberately, matching spec ordering. Validate JSON schema against backend/app/data/variable_metadata.schema.json.",
    "phase": "B",
    "spec_refs": [
      "L568-606 variable_metadata.json entry",
      "L683-685 Phase B step 2",
      "L710 test_variable_registry +1"
    ],
    "depends_on": [
      "B0"
    ],
    "estimated_minutes": 35,
    "files_to_create": [],
    "files_to_modify": [
      "backend/app/data/variable_metadata.json",
      "backend/tests/test_variable_registry.py"
    ],
    "test_files": [
      "backend/tests/test_variable_registry.py"
    ]
  },
  {
    "key": "B2",
    "title": "experiments/tiger_proximity.py runner (clone-trim of bg_ndi_wi)",
    "summary": "Add backend/app/experiments/tiger_proximity.py (~290 LOC) cloning bg_ndi_wi structure with these spec-mandated deltas: (a) two-step _VARIABLE_TO_STEP + _C3_STEP plan that always returns [c3_tiger_roads, c4_tiger_roads]; (b) _BOUNDARY = 'BG_TIGER' (defence-in-depth vs bg_ndi_wi's 'BG' per spec L209-223); (c) render_yaml omits raster_res_m injection (TIGER templates have no raster key) and, on the C4 step only, rewrites cfg['exposure']['file'] to task_dir/output/c3_tiger_roads.parquet (spec L460-493); (d) render_yaml sets cfg['time']['output_grouping'] = 'episode' as the Sprint 5 Phase A contract; (e) _cache_key shape `<sha8>__BG_TIGER__b{buf}m` (no raster suffix, spec L496-508); (f) _sanity_check_pipeline_supports_precomputed_areal_episode() greps inspect.getsource for 'episode' and RuntimeError if absent (R3 mitigation layer b); (g) guard with isinstance(cfg.get('exposure'), dict) raising RuntimeError if shape unexpected (R4); (h) merge_results 3-line wrapper to _merge.write_partial with experiment_key='tiger_proximity' and _PARQUET_MAP={'tiger_proximity':'c4_tiger_roads.parquet'} (spec L515-534). _cli_main + run + SIGTERM handler structurally identical to zcta5_cbp.py modulo prog= and the four module-level constants. Server boots and /api/variables returns 4 keys after this lands.",
    "phase": "B",
    "spec_refs": [
      "L73-88 [B5]-[B8] scope",
      "L405-548 module shape through differences table",
      "L734-736 R1/R3/R4 mitigations"
    ],
    "depends_on": [
      "B1"
    ],
    "estimated_minutes": 180,
    "files_to_create": [
      "backend/app/experiments/tiger_proximity.py"
    ],
    "files_to_modify": [],
    "test_files": []
  },
  {
    "key": "B3",
    "title": "tiger_proximity unit tests (8 tests, mirror zcta5_cbp coverage)",
    "summary": "TDD-loop the runner. Write backend/tests/test_tiger_proximity.py (~140 LOC, 8 tests): (1) plan rejects empty variables; (2) plan rejects unknown variables; (3) plan returns [c3, c4] order; (4) render_yaml C3 leaves exposure untouched; (5) render_yaml C4 rewrites exposure.file to per-task C3 parquet path; (6) render_yaml injects time.output_grouping='episode'; (7) test_cache_key_differs_from_bg_ndi_wi_in_shape_and_boundary asserts the two _cache_key outputs differ in both boundary tag AND overall shape for the same (input_parquet, buffer) — R1 lock; (8) merge_results delegates to _merge.write_partial with the right parquet_map. Plus extend backend/tests/test_merge_partial.py with a 'value_cols selection picks 3 TIGER columns from one parquet' test (spec L712).",
    "phase": "B",
    "spec_refs": [
      "L89-92 [B9]",
      "L705-717 backend test count delta",
      "L733 R1 cache-key shape assertion"
    ],
    "depends_on": [
      "B2"
    ],
    "estimated_minutes": 90,
    "files_to_create": [
      "backend/tests/test_tiger_proximity.py"
    ],
    "files_to_modify": [
      "backend/tests/test_merge_partial.py"
    ],
    "test_files": [
      "backend/tests/test_tiger_proximity.py",
      "backend/tests/test_merge_partial.py"
    ]
  },
  {
    "key": "B4",
    "title": "Single-experiment integration test (test_e2e_tiger_proximity_cohort)",
    "summary": "Add backend/tests/test_e2e_tiger_proximity_cohort.py (~90 LOC, @pytest.mark.integration, ~60s). Single 1-variable task on the demo cohort: status.json transitions, logs.jsonl carries C3+C4 entries, result_tiger_proximity.csv has dist_pri/dist_sec/dist_prisec columns plus the rename keys, row count matches the cohort's episode count (per-(pid, episode_id) join succeeds — this is the runtime proof that Phase A dispatch flows through). Run via `make test-integration` or `pytest -m integration`.",
    "phase": "B",
    "spec_refs": [
      "L708 test_e2e_tiger_proximity_cohort",
      "L689-690 Phase B step 5"
    ],
    "depends_on": [
      "B3"
    ],
    "estimated_minutes": 90,
    "files_to_create": [
      "backend/tests/test_e2e_tiger_proximity_cohort.py"
    ],
    "files_to_modify": [],
    "test_files": [
      "backend/tests/test_e2e_tiger_proximity_cohort.py"
    ]
  },
  {
    "key": "B5",
    "title": "3-experiment dispatch integration + task_manager regression",
    "summary": "Add backend/tests/test_e2e_multi_experiment_with_tiger.py (~110 LOC, @pytest.mark.integration, ~210s): tick all 4 variables (NDI + Walkability + cbp_zcta5 + tiger_proximity) on the demo cohort; assert bg_ndi_wi runs first, zcta5_cbp second, tiger_proximity third (metadata-file order, spec L604-605); result.csv carries ndi + NatWalkInd + 10 r_* + 3 dist_* columns. Plus extend backend/tests/test_task_manager_dispatch.py with 'three-experiment dispatch preserves metadata order' (spec L711).",
    "phase": "B",
    "spec_refs": [
      "L709 test_e2e_multi_experiment_with_tiger",
      "L691-693 Phase B step 6",
      "L711 task_manager +1"
    ],
    "depends_on": [
      "B4"
    ],
    "estimated_minutes": 90,
    "files_to_create": [
      "backend/tests/test_e2e_multi_experiment_with_tiger.py"
    ],
    "files_to_modify": [
      "backend/tests/test_task_manager_dispatch.py"
    ],
    "test_files": [
      "backend/tests/test_e2e_multi_experiment_with_tiger.py",
      "backend/tests/test_task_manager_dispatch.py"
    ]
  },
  {
    "key": "B6",
    "title": "Phase B wrap-up: manual_e2e Sprint 5 section + frontend no-op verify + PR",
    "summary": "Append the Sprint 5 section to backend/tests/manual_e2e.md per spec L795-844 (pre-flight inspect.getsource check; 4 cards render — 3 BG + 1 ZCTA5; full 4-variable task; C3 cache hit on second run; explicit-typo ValueError test, NOT an absent-field test). Visually confirm the frontend renders the TIGER card in the Block Group section with zero edits to variables-step.tsx / variable-card.tsx / variable-coverage-panel.tsx / variable-grouping.ts (G2 invariant). Run the full default pytest suite (expect +11 unit tests, 2 integration skipped by default), tsc --noEmit clean. PR title `feat(experiments): tiger_proximity runner + precomputed_areal episode dispatch (Sprint 5)`. Hold push until controller decision.",
    "phase": "B",
    "spec_refs": [
      "L93-95 [B10]",
      "L694-699 Phase B steps 7-9",
      "L607-628 frontend changes (none)",
      "L795-844 manual smoke section"
    ],
    "depends_on": [
      "B5"
    ],
    "estimated_minutes": 45,
    "files_to_create": [],
    "files_to_modify": [
      "backend/tests/manual_e2e.md"
    ],
    "test_files": []
  }
]
```

---

## Final verification

After all task commits (A0–A3 on `pkg/pypi-only` in `/Users/xai/Desktop/spacescans-project`, and B0–B6 on `feat/sprint-5-tiger-proximity` in `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity`), run the closing verification before opening either PR for review:

**1. Full pytest — pipeline + web default + integration**

```bash
# Pipeline (Phase A)
cd /Users/xai/Desktop/spacescans-project
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/ -q
# Expected: 69 passed (64 baseline + 5 Phase A additions: 3 in test_precomputed_areal_linkage.py + 2 in test_pipeline_smoke.py — see canonical tally table near top of plan)

# Web default suite (Phase B, integration deselected)
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
# Expected per canonical tally table: 150 passed, 2 skipped, 11 deselected
#   (139 baseline + 11 new unit tests across B1/B3/B5; the 2 new
#    @pytest.mark.integration files from B4 and B5 bump the deselect
#    count from the 9 baseline to 11.)

# Web integration suite (Phase B, integration only — requires TIGER C4 fixtures)
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -m integration -q
# Expected on a TIGER-equipped runner: all integration tests pass (Sprint 3 carry-over + 2 new Sprint 5 tests:
#   test_e2e_tiger_proximity_cohort, test_e2e_multi_experiment_with_tiger_cohort)
# On a bare runner without data_full/TIGER/C4 + pyreadr, the 2 new tests SKIP cleanly.
```

**2. Frontend type-check (tsc) — must be clean**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity/frontend
npx tsc --noEmit
# Expected: exit 0, no output. Sprint 5 is server-side only; the four
# protected wizard files have byte-zero diff vs main (G2 invariant).
```

**3. `backend/data/variable_metadata.json` absent invariant**

The web project ships `backend/app/data/variable_metadata.json` (in-tree, version-controlled) and writes runtime overrides to `backend/data/variable_metadata.json` (gitignored, per-deployment). Sprint 5 must not introduce any new file at `backend/data/variable_metadata.json` — that path remains a runtime-only artefact:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity
# The in-tree, version-controlled file MUST exist and contain tiger_proximity.
test -f backend/app/data/variable_metadata.json && \
  grep -q '"tiger_proximity"' backend/app/data/variable_metadata.json && \
  echo "in-tree metadata OK"

# The runtime override file at backend/data/variable_metadata.json MUST NOT be tracked by git.
git ls-files backend/data/variable_metadata.json | grep -q . && \
  echo "FAIL: backend/data/variable_metadata.json is tracked (must remain gitignored)" || \
  echo "absent-tracking invariant OK"
```

Expected: `in-tree metadata OK` and `absent-tracking invariant OK`.

**4. `finishing-a-development-branch` prompt — TWO repos this time**

Sprint 5 spans **two** git repos that each need an independent PR. Run the `finishing-a-development-branch` superpower-skill prompt **once per repo** with the appropriate base branch:

- Pipeline repo (`/Users/xai/Desktop/spacescans-project`, branch `pkg/pypi-only`):
  - Base for PR: `main`
  - PR title: `feat(linkage): precomputed_areal output_grouping dispatch (Sprint 5 Phase A)`
  - Body: `/tmp/sprint5-phase-a-pr-body.md` (staged by Task A3, Step 6)
  - **Push held** until web-side B5 integration confirms green on the editable install
- Web repo (`/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-5-tiger-proximity`, branch `feat/sprint-5-tiger-proximity`):
  - Base for PR: `main`
  - PR title: `feat(experiments): tiger_proximity runner + precomputed_areal episode dispatch (Sprint 5)`
  - Body: per Task B6, Step 6
  - **Push held** until controller decision

When invoking `superpowers:finishing-a-development-branch` for each repo, explicitly state:
- The repo path
- The branch name
- The base branch (`main` for both)
- That this is one of **two** PRs being staged for the same sprint (the other is the cross-repo counterpart)
- That neither push has been executed yet — both are held pending controller approval and pending the web-side integration acting as the acceptance gate for Phase A

After the controller approves, push both branches and open the PRs in the order:
1. Phase A (`pkg/pypi-only` → `main` on `spacescans-project`) — must merge first so the web `main` rebuild picks up the editable-install change on next deployment
2. Phase B (`feat/sprint-5-tiger-proximity` → `main` on `spacescans-web`) — depends on Phase A's merge SHA being reachable from the web's pipeline pin

If either PR's CI fails after push, do **not** amend the merged commit on the other side — open a follow-up commit on the failing branch.

