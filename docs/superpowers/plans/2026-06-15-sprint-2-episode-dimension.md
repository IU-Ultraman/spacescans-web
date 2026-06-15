# Sprint 2: Episode Dimension Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make spacescans-pipeline's C4 output groupable by `(PATID, geoid)` instead of just `PATID`, and route spacescans-web through this so result.csv preserves one row per residential episode.

**Architecture:** Phase A modifies the upstream `spacescans-pipeline` repo: adds `TimeConfig.output_grouping` field, plumbs it through three C4 linkage patterns (two via `TemporalAggSpec`, one via `DurationWeightedSpec`), and teaches `_adapt_demo_conus` to read an upstream-supplied `episode_id`. Phase B modifies `spacescans-web`: csv_to_parquet emits `episode_id = range(len(df))`, render_yaml injects `time.output_grouping="episode"`, merge_results joins on `(pid, episode_id)`, and the results page adds a "per-episode" hint. The two repos communicate via an editable conda install — `pip show spacescans` confirms `/Users/xai/Desktop/spacescans-project/src/spacescans` is the live source, so Phase A's commits in that worktree are visible to Phase B's web tests as soon as Phase A merges.

**Tech Stack:** FastAPI · pandas · DuckDB · Pydantic · Next.js 14 · pytest · subprocess + sha256 (Sprint 1 carry-over).

---

## Pre-implementation: environment confirmation

The implementer must verify these before starting:

```bash
# Pipeline is editable-installed (Phase A changes auto-apply to Phase B)
/Users/xai/miniconda3/envs/spacescans/bin/python -c \
  "import spacescans; assert spacescans.__file__.startswith('/Users/xai/Desktop/spacescans-project/src/spacescans'), spacescans.__file__"

# Both worktrees exist and Phase A target file is the live source
test -f /Users/xai/Desktop/spacescans-project/src/spacescans/models/config.py
test -f /Users/xai/Desktop/spacescans-project/spacescans-web/backend/.env

# Sprint 1 baseline still healthy
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
# Expect: 69 passed, 1 skipped, 5 deselected
```

Conventions used throughout the plan:

- `PY` = `/Users/xai/miniconda3/envs/spacescans/bin/python`
- Pipeline worktree: `/Users/xai/Desktop/spacescans-project/.worktrees/feat-output-grouping` (created in Task A0)
- Web worktree: `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-2` (created in Task B0)
- TDD discipline: write failing test → confirm RED → implement → confirm GREEN → commit.

---

## File Structure

### Phase A — spacescans-pipeline

| Path | Role |
|---|---|
| `src/spacescans/models/config.py` | Add `TimeConfig.output_grouping: str = "patient"` |
| `src/spacescans/models/specs.py` | Add `DurationWeightedSpec.group_by_episode: bool = False` |
| `src/spacescans/linkage/yearly_areal_linkage.py` | Dispatch group_by on TimeConfig.output_grouping |
| `src/spacescans/linkage/yearly_areal_bg_vintage_linkage.py` | Same dispatch |
| `src/spacescans/linkage/static_areal_linkage.py` | Pass `group_by_episode` to DurationWeightedSpec |
| `src/spacescans/engine/duckdb_engine.py` | `duration_weighted` honours `group_by_episode` |
| `src/spacescans/linkage/helpers.py` | `_adapt_demo_conus` uses upstream `episode_id` if present |
| `tests/test_temporal_episode_grouping.py` (new) | 5 unit tests for the three patterns |
| `tests/test_demo_conus_adapter.py` (new) | 1 unit test for the adapter fallback |

### Phase B — spacescans-web

| Path | Role |
|---|---|
| `backend/app/experiments/bg_ndi_wi.py` | `csv_to_parquet` emits `episode_id`; `render_yaml` injects `output_grouping`; `merge_results` joins on `(pid, episode_id)` |
| `frontend/src/app/dashboard/task/[id]/results/page.tsx` | "Result shape: per-episode" hint |
| `backend/tests/test_bg_ndi_wi.py` | 5 new unit tests |
| `backend/tests/test_bg_ndi_wi_integration.py` | 1 new e2e test |
| `backend/tests/fixtures/patients_multi_episode.csv` (new) | 10-row fixture |
| `backend/tests/manual_e2e.md` | Sprint 2 walk-through section |

---

## Task A0: Create pipeline worktree

**Files:**
- (none — git worktree setup only)

- [ ] **Step 1: Confirm pipeline repo state**

```bash
cd /Users/xai/Desktop/spacescans-project
git status --short
git log --oneline -3
```

Expected: clean working tree (no uncommitted local changes) and recent commits.

If there are uncommitted local changes that are NOT part of Sprint 2's scope, stop and ask the controller to stash or commit them first.

- [ ] **Step 2: Verify `.worktrees/` is gitignored**

```bash
cd /Users/xai/Desktop/spacescans-project
git check-ignore -q .worktrees/foo && echo "ignored" || echo "NOT ignored"
```

If "NOT ignored", append `.worktrees/` to `.gitignore` and commit before continuing:

```bash
echo ".worktrees/" >> .gitignore
git add .gitignore
git commit -m "chore: gitignore .worktrees for parallel feature work"
```

- [ ] **Step 3: Create the worktree on a new branch**

```bash
cd /Users/xai/Desktop/spacescans-project
git worktree add .worktrees/feat-output-grouping -b feat/output-grouping-per-episode main
git worktree list
```

Expected: two entries, one for the main worktree, one for the new branch.

- [ ] **Step 4: Confirm pytest baseline in the new worktree**

```bash
cd /Users/xai/Desktop/spacescans-project/.worktrees/feat-output-grouping
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Capture the count. We'll add ~6 new tests in this phase, so the final number should be `baseline + 6`.

Report: status / baseline test count / any issues.

---

## Task A1: `TimeConfig.output_grouping` field

**Files:**
- Modify: `src/spacescans/models/config.py`
- Test: `tests/test_temporal_episode_grouping.py` (new)

- [ ] **Step 1: Create the failing test file**

```bash
cd /Users/xai/Desktop/spacescans-project/.worktrees/feat-output-grouping
mkdir -p tests
```

Create `tests/test_temporal_episode_grouping.py`:

```python
"""Sprint 2: TimeConfig.output_grouping + 3 linkage pattern dispatch.

These tests use mocked engine calls so they exercise the linkage modules'
dispatch logic without spinning up DuckDB on real data.
"""
import pandas as pd
import pytest

from spacescans.models.config import TimeConfig


def test_time_config_default_output_grouping_is_patient():
    cfg = TimeConfig()
    assert cfg.output_grouping == "patient"


def test_time_config_accepts_episode():
    cfg = TimeConfig(output_grouping="episode")
    assert cfg.output_grouping == "episode"


def test_time_config_accepts_patient_explicitly():
    cfg = TimeConfig(output_grouping="patient")
    assert cfg.output_grouping == "patient"
```

- [ ] **Step 2: Run failing tests**

```bash
cd /Users/xai/Desktop/spacescans-project/.worktrees/feat-output-grouping
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_temporal_episode_grouping.py -v
```

Expected: 3 tests FAIL with `pydantic.ValidationError` or `AttributeError` (depending on Pydantic version) because the field doesn't exist.

- [ ] **Step 3: Add the field**

Edit `src/spacescans/models/config.py`. Find:

```python
class TimeConfig(BaseModel):
    years: list[int] | None = None
    start_date: str | None = None
    end_date: str | None = None
    temporal_resolution: str = "yearly"
    temporal_mode: str = "yearly"
```

Add one new field:

```python
class TimeConfig(BaseModel):
    years: list[int] | None = None
    start_date: str | None = None
    end_date: str | None = None
    temporal_resolution: str = "yearly"
    temporal_mode: str = "yearly"
    output_grouping: str = "patient"  # "patient" | "episode"
```

- [ ] **Step 4: Tests pass**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_temporal_episode_grouping.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/spacescans/models/config.py tests/test_temporal_episode_grouping.py
git commit -m "feat(config): TimeConfig.output_grouping field for per-episode output"
```

Report: status / test count / commit SHA.

---

## Task A2: `yearly_areal` linkage dispatch

**Files:**
- Modify: `src/spacescans/linkage/yearly_areal_linkage.py`
- Test: `tests/test_temporal_episode_grouping.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_temporal_episode_grouping.py`:

```python
from unittest.mock import MagicMock, patch
from pathlib import Path


def _make_fake_yearly_areal_config(output_grouping: str = "patient"):
    """Build a minimal config object the linkage function can dispatch on.

    The linkage function reads config.time.output_grouping then passes
    a TemporalAggSpec to engine.temporal_aggregate. We mock engine so
    only the dispatch logic is exercised.
    """
    from spacescans.models.config import (
        DatasetConfig, SourceConfig, BufferConfig, ExposureConfig,
        TimeConfig, EngineConfig, OutputConfig,
    )
    return DatasetConfig(
        name="test",
        linkage_pattern="yearly_areal",
        geometry_type="polygon",
        source=SourceConfig(file="/dev/null", join_col="GEOID10"),
        buffer=BufferConfig(patient_file="/dev/null", buffer_m=270),
        exposure=ExposureConfig(file="/dev/null", join_col="GEOID10",
                                value_cols=["v"], year_col="year"),
        time=TimeConfig(years=[2017], output_grouping=output_grouping),
        engine=EngineConfig(),
        output=OutputConfig(path="/tmp/test_out.parquet"),
    )


def test_yearly_areal_passes_patient_group_by_when_default(monkeypatch, tmp_path):
    """output_grouping='patient' → group_by=['PATID']."""
    captured = {}

    fake_engine = MagicMock()
    def capture_spec(data, spec):
        captured["group_by"] = spec.group_by
        return pd.DataFrame({"PATID": [], "v": []})
    fake_engine.join.return_value = pd.DataFrame()
    fake_engine.weighted_aggregate.return_value = pd.DataFrame()
    fake_engine.temporal_aggregate.side_effect = capture_spec

    from spacescans.linkage.yearly_areal_linkage import run_yearly_areal

    # Patch out IO + adapter + helpers so dispatch is what runs
    with patch("spacescans.linkage.yearly_areal_linkage.load_patients",
               return_value=pd.DataFrame({"PATID": [], "start": [], "end": [],
                                          "long": [], "lat": [], "geoid": []})), \
         patch("spacescans.linkage.yearly_areal_linkage.load_weights",
               return_value=pd.DataFrame()), \
         patch("spacescans.linkage.yearly_areal_linkage.read_table",
               return_value=pd.DataFrame()), \
         patch("spacescans.linkage.yearly_areal_linkage.build_episode_periods",
               return_value=pd.DataFrame({"PATID": [], "geoid": [],
                                          "period_id": [], "overlap_days": []})), \
         patch("spacescans.linkage.yearly_areal_linkage.apply_transforms",
               side_effect=lambda df, *a, **kw: df), \
         patch("spacescans.linkage.yearly_areal_linkage.write_table",
               return_value=Path("/tmp/test_out.parquet")):
        cfg = _make_fake_yearly_areal_config(output_grouping="patient")
        run_yearly_areal(cfg, fake_engine)

    assert captured["group_by"] == ["PATID"]


def test_yearly_areal_passes_patient_geoid_group_by_when_episode(monkeypatch, tmp_path):
    """output_grouping='episode' → group_by=['PATID', 'geoid']."""
    captured = {}

    fake_engine = MagicMock()
    def capture_spec(data, spec):
        captured["group_by"] = spec.group_by
        return pd.DataFrame({"PATID": [], "geoid": [], "v": []})
    fake_engine.join.return_value = pd.DataFrame()
    fake_engine.weighted_aggregate.return_value = pd.DataFrame()
    fake_engine.temporal_aggregate.side_effect = capture_spec

    from spacescans.linkage.yearly_areal_linkage import run_yearly_areal

    with patch("spacescans.linkage.yearly_areal_linkage.load_patients",
               return_value=pd.DataFrame({"PATID": [], "start": [], "end": [],
                                          "long": [], "lat": [], "geoid": []})), \
         patch("spacescans.linkage.yearly_areal_linkage.load_weights",
               return_value=pd.DataFrame()), \
         patch("spacescans.linkage.yearly_areal_linkage.read_table",
               return_value=pd.DataFrame()), \
         patch("spacescans.linkage.yearly_areal_linkage.build_episode_periods",
               return_value=pd.DataFrame({"PATID": [], "geoid": [],
                                          "period_id": [], "overlap_days": []})), \
         patch("spacescans.linkage.yearly_areal_linkage.apply_transforms",
               side_effect=lambda df, *a, **kw: df), \
         patch("spacescans.linkage.yearly_areal_linkage.write_table",
               return_value=Path("/tmp/test_out.parquet")):
        cfg = _make_fake_yearly_areal_config(output_grouping="episode")
        run_yearly_areal(cfg, fake_engine)

    assert captured["group_by"] == ["PATID", "geoid"]


def test_yearly_areal_invalid_output_grouping_raises(monkeypatch, tmp_path):
    fake_engine = MagicMock()
    from spacescans.linkage.yearly_areal_linkage import run_yearly_areal

    with patch("spacescans.linkage.yearly_areal_linkage.load_patients",
               return_value=pd.DataFrame({"PATID": [], "start": [], "end": [],
                                          "long": [], "lat": [], "geoid": []})), \
         patch("spacescans.linkage.yearly_areal_linkage.load_weights",
               return_value=pd.DataFrame()), \
         patch("spacescans.linkage.yearly_areal_linkage.read_table",
               return_value=pd.DataFrame()), \
         patch("spacescans.linkage.yearly_areal_linkage.build_episode_periods",
               return_value=pd.DataFrame()), \
         patch("spacescans.linkage.yearly_areal_linkage.apply_transforms",
               side_effect=lambda df, *a, **kw: df):
        cfg = _make_fake_yearly_areal_config(output_grouping="rubbish")
        with pytest.raises(ValueError, match="output_grouping"):
            run_yearly_areal(cfg, fake_engine)
```

- [ ] **Step 2: Run failing tests**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_temporal_episode_grouping.py -v -k yearly_areal
```

Expected: 3 FAIL — the linkage function still passes the literal string `"PATID"` instead of the list-based dispatch.

- [ ] **Step 3: Modify `run_yearly_areal`**

Edit `src/spacescans/linkage/yearly_areal_linkage.py`. Locate the existing block:

```python
    result = engine.temporal_aggregate(
        episode_exp,
        TemporalAggSpec(
            group_by="PATID",
            period_col="period_id",
            value_cols=config.exposure.value_cols,
            weight_col="overlap_days",
        ),
    )
    return write_table(result, config.output.path)
```

Replace with:

```python
    # Dispatch on TimeConfig.output_grouping: "patient" keeps the v1
    # per-PATID collapse; "episode" preserves the synthetic per-row
    # `geoid` (== episode_id when upstream supplies one).
    if config.time.output_grouping == "patient":
        group_by_keys = ["PATID"]
    elif config.time.output_grouping == "episode":
        group_by_keys = ["PATID", "geoid"]
    else:
        raise ValueError(
            f"unsupported output_grouping: {config.time.output_grouping!r} "
            "(expected 'patient' or 'episode')"
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
    return write_table(result, config.output.path)
```

- [ ] **Step 4: Tests pass**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_temporal_episode_grouping.py -v -k yearly_areal
```

Expected: 3 PASS.

- [ ] **Step 5: Run the full pipeline suite to check no regressions**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: baseline + 6 new passing tests (3 from Task A1 + 3 from this task).

- [ ] **Step 6: Commit**

```bash
git add src/spacescans/linkage/yearly_areal_linkage.py tests/test_temporal_episode_grouping.py
git commit -m "feat(linkage): yearly_areal dispatch on TimeConfig.output_grouping"
```

Report status / test count / commit SHA.

---

## Task A3: `yearly_areal_bg_vintage` linkage dispatch

**Files:**
- Modify: `src/spacescans/linkage/yearly_areal_bg_vintage_linkage.py`
- Test: `tests/test_temporal_episode_grouping.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_temporal_episode_grouping.py`:

```python
def _make_fake_bg_vintage_config(output_grouping: str = "episode"):
    from spacescans.models.config import (
        DatasetConfig, SourceConfig, BufferConfig, ExposureConfig,
        TimeConfig, EngineConfig, OutputConfig,
    )
    return DatasetConfig(
        name="test_bg_vintage",
        linkage_pattern="yearly_areal_bg_vintage",
        geometry_type="polygon",
        source=SourceConfig(file="/dev/null", join_col="GEOID10"),
        source_2020=SourceConfig(file="/dev/null", join_col="GEOID"),
        buffer=BufferConfig(patient_file="/dev/null", buffer_m=270),
        exposure=ExposureConfig(
            file="/dev/null",
            vintage_col="bg_vintage",
            join_col_2010="bg_fips_2010",
            join_col_2020="bg_fips_2020",
            value_cols=["v"],
            year_col="index_year",
        ),
        time=TimeConfig(years=[2017], output_grouping=output_grouping),
        engine=EngineConfig(),
        output=OutputConfig(path="/tmp/test_out.parquet"),
    )


def test_yearly_areal_bg_vintage_passes_episode_group_by(monkeypatch, tmp_path):
    """output_grouping='episode' → temporal_aggregate.group_by includes geoid."""
    captured = {}

    fake_engine = MagicMock()
    def capture_spec(data, spec):
        captured["group_by"] = spec.group_by
        return pd.DataFrame({"PATID": [], "geoid": [], "v": []})
    fake_engine.join.return_value = pd.DataFrame()
    fake_engine.weighted_aggregate.return_value = pd.DataFrame()
    fake_engine.temporal_aggregate.side_effect = capture_spec

    from spacescans.linkage import yearly_areal_bg_vintage_linkage as mod

    with patch.object(mod, "load_patients",
                      return_value=pd.DataFrame({"PATID": [], "start": [], "end": [],
                                                  "long": [], "lat": [], "geoid": []})), \
         patch.object(mod, "load_weights", return_value=pd.DataFrame()), \
         patch.object(mod, "read_table", return_value=pd.DataFrame({"bg_vintage": []})), \
         patch.object(mod, "build_episode_periods",
                      return_value=pd.DataFrame({"PATID": [], "geoid": [],
                                                  "period_id": [], "overlap_days": []})), \
         patch.object(mod, "apply_transforms",
                      side_effect=lambda df, *a, **kw: df), \
         patch.object(mod, "write_table",
                      return_value=Path("/tmp/test_out.parquet")):
        cfg = _make_fake_bg_vintage_config(output_grouping="episode")
        mod.run_yearly_areal_bg_vintage(cfg, fake_engine)

    assert captured["group_by"] == ["PATID", "geoid"]
```

NOTE: This test mocks an arbitrary subset of the bg_vintage flow. If the actual signature of `run_yearly_areal_bg_vintage` requires additional config fields, the implementer should adjust the fake config in `_make_fake_bg_vintage_config` to satisfy validation, NOT add additional `patch.object` calls.

- [ ] **Step 2: Run failing tests**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_temporal_episode_grouping.py -v -k bg_vintage
```

Expected: 1 FAIL — bg_vintage still passes literal `"PATID"`.

- [ ] **Step 3: Apply the same dispatch to bg_vintage**

Edit `src/spacescans/linkage/yearly_areal_bg_vintage_linkage.py`. Find the existing `engine.temporal_aggregate(...)` call near the bottom and replace the surrounding block with the same dispatch as Task A2:

```python
    if config.time.output_grouping == "patient":
        group_by_keys = ["PATID"]
    elif config.time.output_grouping == "episode":
        group_by_keys = ["PATID", "geoid"]
    else:
        raise ValueError(
            f"unsupported output_grouping: {config.time.output_grouping!r} "
            "(expected 'patient' or 'episode')"
        )

    result = engine.temporal_aggregate(
        episode_exp,
        TemporalAggSpec(
            group_by=group_by_keys,
            period_col="period_id",
            value_cols=ec.value_cols,  # NOTE: bg_vintage uses ec.value_cols, not config.exposure
            weight_col="overlap_days",
        ),
    )
    return write_table(result, config.output.path)
```

Verify the original used `ec.value_cols` (it does — the bg_vintage variant aliases `config.exposure` as `ec` near the top of the function).

- [ ] **Step 4: Tests pass**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_temporal_episode_grouping.py -v -k bg_vintage
```

Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/spacescans/linkage/yearly_areal_bg_vintage_linkage.py tests/test_temporal_episode_grouping.py
git commit -m "feat(linkage): yearly_areal_bg_vintage dispatch on output_grouping"
```

Report status / test count / commit SHA.

---

## Task A4: `static_areal` + `DurationWeightedSpec` + engine change

**Files:**
- Modify: `src/spacescans/models/specs.py`
- Modify: `src/spacescans/engine/duckdb_engine.py`
- Modify: `src/spacescans/linkage/static_areal_linkage.py`
- Test: `tests/test_temporal_episode_grouping.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_temporal_episode_grouping.py`:

```python
def test_static_areal_episode_grouping_widens_sql_output(monkeypatch, tmp_path):
    """static_areal with output_grouping='episode' should produce a result that
    has both PATID and geoid columns (vs just PATID in 'patient' mode)."""
    import pandas as pd
    from spacescans.engine.duckdb_engine import DuckDBEngine
    from spacescans.models.specs import DurationWeightedSpec

    engine = DuckDBEngine()

    # Per-geoid values: GEOID A has value 1.0, GEOID B has value 2.0
    values = pd.DataFrame({
        "geoid": [0, 1],
        "v": [1.0, 2.0],
    })

    # Patient PATID=P1 has 2 episodes (geoid 0 and geoid 1), 100 days each.
    episodes = pd.DataFrame({
        "PATID": ["P1", "P1"],
        "geoid": [0, 1],
        "start_date": pd.to_datetime(["2017-01-01", "2017-05-01"]),
        "end_date":   pd.to_datetime(["2017-04-10", "2017-08-08"]),
    })

    # Patient mode: one row, v = duration-weighted avg of 1.0 and 2.0
    result_patient = engine.duration_weighted(
        values, episodes, DurationWeightedSpec(value_cols=["v"])
    )
    assert len(result_patient) == 1
    assert "PATID" in result_patient.columns
    assert "geoid" not in result_patient.columns

    # Episode mode: two rows, one per (PATID, geoid)
    result_episode = engine.duration_weighted(
        values, episodes,
        DurationWeightedSpec(value_cols=["v"], group_by_episode=True),
    )
    assert len(result_episode) == 2
    assert "PATID" in result_episode.columns
    assert "geoid" in result_episode.columns
    # Each row's v equals the geoid's value (1.0 or 2.0) because there's
    # no within-(PATID, geoid) averaging.
    sorted_by_geoid = result_episode.sort_values("geoid").reset_index(drop=True)
    assert sorted_by_geoid["v"].tolist() == [1.0, 2.0]


def test_static_areal_linkage_passes_group_by_episode(monkeypatch, tmp_path):
    """Verify run_static_areal sets group_by_episode=True on the spec when
    config.time.output_grouping == 'episode'."""
    captured = {}
    fake_engine = MagicMock()
    def capture_spec(values, episodes, spec):
        captured["group_by_episode"] = spec.group_by_episode
        return pd.DataFrame()
    fake_engine.join.return_value = pd.DataFrame()
    fake_engine.weighted_aggregate.return_value = pd.DataFrame()
    fake_engine.duration_weighted.side_effect = capture_spec

    from spacescans.linkage import static_areal_linkage as mod
    from spacescans.models.config import (
        DatasetConfig, SourceConfig, BufferConfig, ExposureConfig,
        TimeConfig, EngineConfig, OutputConfig,
    )
    cfg = DatasetConfig(
        name="test_static",
        linkage_pattern="static_areal",
        geometry_type="polygon",
        source=SourceConfig(file="/dev/null", join_col="GEOID10"),
        buffer=BufferConfig(patient_file="/dev/null", buffer_m=270),
        exposure=ExposureConfig(file="/dev/null", join_col="GEOID10", value_cols=["v"]),
        time=TimeConfig(output_grouping="episode"),
        engine=EngineConfig(),
        output=OutputConfig(path="/tmp/test_static_out.parquet"),
    )

    with patch.object(mod, "load_patients",
                      return_value=pd.DataFrame({"PATID": [], "start": [], "end": [],
                                                  "long": [], "lat": [], "geoid": []})), \
         patch.object(mod, "load_weights", return_value=pd.DataFrame()), \
         patch.object(mod, "read_table", return_value=pd.DataFrame()), \
         patch.object(mod, "prepare_episodes",
                      return_value=pd.DataFrame({"PATID": [], "geoid": [],
                                                  "start_date": [], "end_date": []})), \
         patch.object(mod, "apply_transforms",
                      side_effect=lambda df, *a, **kw: df), \
         patch.object(mod, "write_table",
                      return_value=Path("/tmp/test_static_out.parquet")):
        mod.run_static_areal(cfg, fake_engine)

    assert captured["group_by_episode"] is True
```

- [ ] **Step 2: Run failing tests**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_temporal_episode_grouping.py -v -k static_areal
```

Expected: 2 FAIL — `DurationWeightedSpec` has no `group_by_episode` field; engine SQL has no per-episode branch.

- [ ] **Step 3: Add `group_by_episode` to `DurationWeightedSpec`**

Edit `src/spacescans/models/specs.py`. Find:

```python
class DurationWeightedSpec(BaseModel):
    patient_id_col: str = "PATID"
    geoid_col: str = "geoid"
    value_cols: list[str]
    start_col: str = "start_date"
    end_col: str = "end_date"
    missing_policy: MissingPolicy = MissingPolicy.SKIP
```

Add one field:

```python
class DurationWeightedSpec(BaseModel):
    patient_id_col: str = "PATID"
    geoid_col: str = "geoid"
    value_cols: list[str]
    start_col: str = "start_date"
    end_col: str = "end_date"
    missing_policy: MissingPolicy = MissingPolicy.SKIP
    group_by_episode: bool = False  # if True, GROUP BY patient_id_col, geoid_col
```

- [ ] **Step 4: Modify `duration_weighted` engine SQL**

Edit `src/spacescans/engine/duckdb_engine.py`. Find the existing `def duration_weighted(...)` method. The current SQL:

```python
sql = f"""
    WITH stays AS (
        SELECT
            p.{spec.patient_id_col},
            p.{spec.geoid_col},
            DATEDIFF('day', p.{spec.start_col}, p.{spec.end_col}) + 1 AS days
        FROM _ep p
        WHERE DATEDIFF('day', p.{spec.start_col}, p.{spec.end_col}) + 1 > 0
    )
    SELECT s.{spec.patient_id_col}, {', '.join(value_selects)}
    FROM stays s
    LEFT JOIN _vals v ON s.{spec.geoid_col} = v.{spec.geoid_col}
    GROUP BY s.{spec.patient_id_col}
"""
```

Replace the SELECT / GROUP BY block to conditionally include `geoid_col`:

```python
if spec.group_by_episode:
    select_cols = f"s.{spec.patient_id_col}, s.{spec.geoid_col}"
    group_by_cols = f"s.{spec.patient_id_col}, s.{spec.geoid_col}"
else:
    select_cols = f"s.{spec.patient_id_col}"
    group_by_cols = f"s.{spec.patient_id_col}"

sql = f"""
    WITH stays AS (
        SELECT
            p.{spec.patient_id_col},
            p.{spec.geoid_col},
            DATEDIFF('day', p.{spec.start_col}, p.{spec.end_col}) + 1 AS days
        FROM _ep p
        WHERE DATEDIFF('day', p.{spec.start_col}, p.{spec.end_col}) + 1 > 0
    )
    SELECT {select_cols}, {', '.join(value_selects)}
    FROM stays s
    LEFT JOIN _vals v ON s.{spec.geoid_col} = v.{spec.geoid_col}
    GROUP BY {group_by_cols}
"""
```

- [ ] **Step 5: Modify `run_static_areal` to pass the flag**

Edit `src/spacescans/linkage/static_areal_linkage.py`. Find the existing call:

```python
result = engine.duration_weighted(
    geoid_values,
    episodes,
    DurationWeightedSpec(value_cols=config.exposure.value_cols),
)
```

Replace with:

```python
# Dispatch on TimeConfig.output_grouping
if config.time.output_grouping == "patient":
    group_by_episode = False
elif config.time.output_grouping == "episode":
    group_by_episode = True
else:
    raise ValueError(
        f"unsupported output_grouping: {config.time.output_grouping!r} "
        "(expected 'patient' or 'episode')"
    )

result = engine.duration_weighted(
    geoid_values,
    episodes,
    DurationWeightedSpec(
        value_cols=config.exposure.value_cols,
        group_by_episode=group_by_episode,
    ),
)
```

- [ ] **Step 6: Run all related tests**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_temporal_episode_grouping.py -v
```

Expected: all tests in this file PASS (3 from Task A1 + 3 from A2 + 1 from A3 + 2 from this task = 9 total).

- [ ] **Step 7: Run the full pipeline suite**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: no regressions in any pre-existing engine / linkage / model tests.

- [ ] **Step 8: Commit**

```bash
git add src/spacescans/models/specs.py \
        src/spacescans/engine/duckdb_engine.py \
        src/spacescans/linkage/static_areal_linkage.py \
        tests/test_temporal_episode_grouping.py
git commit -m "feat(static_areal): group_by_episode flag through DurationWeightedSpec + engine SQL"
```

Report status / test count / commit SHA / concerns.

---

## Task A5: `_adapt_demo_conus` episode_id fallback

**Files:**
- Modify: `src/spacescans/linkage/helpers.py`
- Test: `tests/test_demo_conus_adapter.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_demo_conus_adapter.py`:

```python
"""Sprint 2: _adapt_demo_conus should prefer an upstream-supplied
episode_id column over its synthetic range(len(df)) fallback."""
import pandas as pd

from spacescans.linkage.helpers import _adapt_demo_conus


def test_adapter_uses_episode_id_when_present():
    """When the input df has an episode_id column, the adapter copies
    it (cast to int) into the `geoid` output column."""
    df = pd.DataFrame({
        "pid": ["P1", "P1", "P2"],
        "startDate": ["2014-01-01", "2018-01-01", "2017-01-01"],
        "endDate":   ["2017-12-31", "2020-12-31", "2018-06-30"],
        "longitude": [-87.6, -84.3, -95.0],
        "latitude":  [41.9, 30.4, 30.0],
        "episode_id": [0, 1, 2],
    })
    out = _adapt_demo_conus(df)
    # geoid should mirror episode_id
    assert out["geoid"].tolist() == [0, 1, 2]
    # Schema sanity
    assert list(out.columns) == ["PATID", "start", "end", "long", "lat", "geoid"]


def test_adapter_falls_back_to_range_without_episode_id():
    """When episode_id is absent, fallback to synthetic range(len(df))."""
    df = pd.DataFrame({
        "pid": ["P1", "P2"],
        "startDate": ["2017-01-01", "2017-01-01"],
        "endDate":   ["2017-12-31", "2017-12-31"],
        "longitude": [-87.6, -95.0],
        "latitude":  [41.9, 30.0],
    })
    out = _adapt_demo_conus(df)
    assert out["geoid"].tolist() == [0, 1]


def test_adapter_handles_non_consecutive_episode_id():
    """Non-zero-based or non-contiguous episode_ids must be honoured."""
    df = pd.DataFrame({
        "pid": ["P1", "P2"],
        "startDate": ["2017-01-01", "2017-01-01"],
        "endDate":   ["2017-12-31", "2017-12-31"],
        "longitude": [-87.6, -95.0],
        "latitude":  [41.9, 30.0],
        "episode_id": [10, 42],
    })
    out = _adapt_demo_conus(df)
    assert out["geoid"].tolist() == [10, 42]
```

- [ ] **Step 2: Run failing tests**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_demo_conus_adapter.py -v
```

Expected: 3 FAIL — the adapter always overwrites `geoid` with `range(len(df))`.

- [ ] **Step 3: Modify the adapter**

Edit `src/spacescans/linkage/helpers.py`. Find:

```python
def _adapt_demo_conus(df: pd.DataFrame) -> pd.DataFrame:
    """Map demo_patients_conus_fast_*.rds columns to pipeline's expected format.

    Source columns: pid, startDate, endDate, longitude, latitude, bg_geoid (12-digit str)
    Target columns: PATID, start, end, long, lat, geoid (int)
    """
    df = df.rename(columns={
        "pid": "PATID",
        "startDate": "start",
        "endDate": "end",
        "longitude": "long",
        "latitude": "lat",
    })
    # geoid must be unique per patient — pipeline (esp. grid_weights validation)
    # assumes 1:1 patient↔geoid; using factorize(bg_geoid) collides multiple
    # patients in the same block group onto the same geoid.
    df["geoid"] = range(len(df))
    return df[["PATID", "start", "end", "long", "lat", "geoid"]].copy()
```

Replace the `df["geoid"] = range(len(df))` line with episode_id-aware logic:

```python
def _adapt_demo_conus(df: pd.DataFrame) -> pd.DataFrame:
    """Map demo_patients_conus_fast_*.rds columns to pipeline's expected format.

    Source columns: pid, startDate, endDate, longitude, latitude, bg_geoid (12-digit str)
    Optional column: episode_id (int) — when supplied (e.g. by spacescans-web's
    csv_to_parquet) the adapter uses it as the synthetic per-row geoid,
    enabling per-episode output grouping downstream. Fallback is
    range(len(df)) for legacy callers (R / CLI users).
    Target columns: PATID, start, end, long, lat, geoid (int)
    """
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
        # geoid must be unique per patient — pipeline (esp. grid_weights
        # validation) assumes 1:1 patient↔geoid; using factorize(bg_geoid)
        # would collide multiple patients in the same block group.
        df["geoid"] = range(len(df))
    return df[["PATID", "start", "end", "long", "lat", "geoid"]].copy()
```

- [ ] **Step 4: Tests pass**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_demo_conus_adapter.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Full pipeline suite**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

No regressions.

- [ ] **Step 6: Commit**

```bash
git add src/spacescans/linkage/helpers.py tests/test_demo_conus_adapter.py
git commit -m "feat(adapter): _adapt_demo_conus prefers upstream episode_id"
```

Report status / test count / commit SHA.

---

## Task A6: Phase A wrap-up — merge to pipeline main

**Files:** (none — git workflow only)

- [ ] **Step 1: Final pipeline-side regression check**

```bash
cd /Users/xai/Desktop/spacescans-project/.worktrees/feat-output-grouping
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: baseline + 12 new (3 + 3 + 1 + 2 + 3) passing.

- [ ] **Step 2: Review the Phase A diff**

```bash
git log --oneline main..HEAD
git diff --stat main..HEAD
```

Expected: 5 commits, modifying ~6 source files + 2 new test files.

- [ ] **Step 3: Switch to pipeline main worktree and merge**

```bash
cd /Users/xai/Desktop/spacescans-project
git checkout main
git pull --ff-only 2>&1 | tail -3
git merge --no-ff feat/output-grouping-per-episode -m "Merge feat/output-grouping-per-episode for Sprint 2 Phase A

Adds TimeConfig.output_grouping field plus dispatch through three
C4 linkage patterns (yearly_areal, yearly_areal_bg_vintage,
static_areal). Default 'patient' preserves v1 behaviour for R / CLI
consumers. spacescans-web in Sprint 2 Phase B will pass 'episode'
to get per-(PATID, geoid) output rows.

Also: _adapt_demo_conus now uses an upstream-supplied episode_id
column when present (web), falling back to range(len(df)) otherwise.

12 new unit tests; all pre-existing tests pass."
```

- [ ] **Step 4: Sanity check the merge**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
git log --oneline -3
```

Expected: same test count as Step 1; merge commit visible.

- [ ] **Step 5: Delete the feature branch + remove the worktree**

```bash
git worktree remove .worktrees/feat-output-grouping
git branch -d feat/output-grouping-per-episode
git worktree list
git branch
```

Expected: only main remains; no worktrees besides the main checkout.

- [ ] **Step 6: Confirm editable install still resolves to the updated source**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -c \
  "from spacescans.models.config import TimeConfig; \
   print('output_grouping default:', TimeConfig().output_grouping)"
```

Expected: `output_grouping default: patient`. This confirms Phase B can now reference the new field.

- [ ] **Step 7: Decision point — push to origin?**

The plan does NOT push to pipeline's origin automatically. Report to the controller and let the user decide. The default action is to keep the changes local until Phase B integration verifies them end-to-end.

Report: status / final test count / merge commit SHA / whether to push to origin.

---

## Task B0: Create web worktree

**Files:** (git workflow only)

- [ ] **Step 1: Confirm web repo state**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web
git status --short
git log --oneline -3
```

Expected: clean working tree; recent log shows the Sprint 2 spec commit (`7fd2b9e`) at the top or near it.

- [ ] **Step 2: Verify `.worktrees/` is gitignored**

```bash
git check-ignore -q .worktrees/foo && echo "ignored" || echo "NOT ignored"
```

If "NOT ignored", add and commit (web repo's `.gitignore` already has it from Sprint 1's setup, but double-check).

- [ ] **Step 3: Create the worktree on a new branch**

```bash
git worktree add .worktrees/feat-sprint-2 -b feat/sprint-2-episode-dimension main
git worktree list
```

- [ ] **Step 4: Migrate local-only state into the new worktree**

The new worktree won't have `backend/.env` (gitignored) or `backend/data/variable_metadata.json` (gitignored from Sprint 1). Copy both:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-2
cp /Users/xai/Desktop/spacescans-project/spacescans-web/backend/.env backend/.env
mkdir -p backend/data
cp /Users/xai/Desktop/spacescans-project/spacescans-web/backend/data/variable_metadata.json backend/data/variable_metadata.json
```

Also symlink frontend `node_modules` so tsc works:

```bash
[ ! -d frontend/node_modules ] && ln -s /Users/xai/Desktop/spacescans-project/spacescans-web/frontend/node_modules frontend/node_modules
ls frontend/node_modules >/dev/null && echo "node_modules ok"
```

- [ ] **Step 5: Baseline test runs**

```bash
cd backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 69 passed, 1 skipped, 5 deselected — Sprint 1 baseline preserved.

```bash
cd ../frontend
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
node_modules/.bin/tsc --noEmit
```

Expected: zero errors.

Report: status / baseline test count / tsc result.

---

## Task B1: `csv_to_parquet` emits `episode_id`

**Files:**
- Modify: `backend/app/experiments/bg_ndi_wi.py`
- Test: `backend/tests/test_bg_ndi_wi.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_bg_ndi_wi.py`:

```python
def test_csv_to_parquet_adds_episode_id(tmp_path):
    """Every row gets episode_id = its row index, regardless of pid."""
    from app.experiments.bg_ndi_wi import csv_to_parquet

    src = tmp_path / "input.csv"
    src.write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "PID0000001,2017-01-01,2017-12-31,-93.0,45.0\n"
        "PID0000002,2017-01-01,2017-12-31,-95.0,30.0\n"
        "PID0000001,2018-01-01,2018-12-31,-87.0,42.0\n"  # same pid as row 0
    )
    dst = tmp_path / "input.parquet"
    csv_to_parquet(src, dst)

    df = pd.read_parquet(dst)
    assert "episode_id" in df.columns
    assert df["episode_id"].tolist() == [0, 1, 2]


def test_csv_to_parquet_overrides_user_episode_id_with_warn(tmp_path, caplog):
    """If the input CSV already has an episode_id column, it's overwritten
    deterministically and a warning is logged via standard logging."""
    from app.experiments.bg_ndi_wi import csv_to_parquet

    src = tmp_path / "input.csv"
    src.write_text(
        "pid,startDate,endDate,longitude,latitude,episode_id\n"
        "PID0000001,2017-01-01,2017-12-31,-93.0,45.0,999\n"
        "PID0000002,2017-01-01,2017-12-31,-95.0,30.0,888\n"
    )
    dst = tmp_path / "input.parquet"

    import logging
    with caplog.at_level(logging.WARNING, logger="app.experiments.bg_ndi_wi"):
        csv_to_parquet(src, dst)

    df = pd.read_parquet(dst)
    # User values overwritten to deterministic row-index series
    assert df["episode_id"].tolist() == [0, 1]
    # Warning emitted
    assert any("episode_id" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run failing tests**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-2/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_bg_ndi_wi.py -v -k "adds_episode_id or overrides_user_episode_id"
```

Expected: 2 FAIL — column doesn't get added.

- [ ] **Step 3: Modify `csv_to_parquet`**

Edit `backend/app/experiments/bg_ndi_wi.py`. Find the current `csv_to_parquet`:

```python
def csv_to_parquet(src: Path, dst: Path) -> None:
    """Convert uploaded CSV to parquet with explicit dtype handling.
    ...
    """
    header = pd.read_csv(src, nrows=0).columns.tolist()
    fips_dtypes = {c: "string" for c in _FIPS_STR_COLS if c in header}
    df = pd.read_csv(
        src,
        dtype=fips_dtypes,
        parse_dates=["startDate", "endDate"],
        date_format="%Y-%m-%d",
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dst, index=False)
```

Add an `import logging` at the top of the file (if not already present), define a module logger, and update the function:

```python
import logging
_log = logging.getLogger(__name__)


def csv_to_parquet(src: Path, dst: Path) -> None:
    """Convert uploaded CSV to parquet with explicit dtype handling.

    Adds a deterministic `episode_id = range(len(df))` column so the
    pipeline's `_adapt_demo_conus` can use it as the per-row geoid and
    merge_results can later reconstruct the same id to join back.
    """
    header = pd.read_csv(src, nrows=0).columns.tolist()
    fips_dtypes = {c: "string" for c in _FIPS_STR_COLS if c in header}
    df = pd.read_csv(
        src,
        dtype=fips_dtypes,
        parse_dates=["startDate", "endDate"],
        date_format="%Y-%m-%d",
    )
    if "episode_id" in df.columns:
        _log.warning(
            "input.csv carried an episode_id column; overwriting with "
            "deterministic row-index ids (Sprint 2 invariant)."
        )
    df["episode_id"] = range(len(df))
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dst, index=False)
```

- [ ] **Step 4: Tests pass**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_bg_ndi_wi.py -v -k "adds_episode_id or overrides_user_episode_id"
```

Expected: 2 PASS.

- [ ] **Step 5: Full suite**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 71 passed (was 69 + 2 new).

- [ ] **Step 6: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/tests/test_bg_ndi_wi.py
git commit -m "feat(experiments): csv_to_parquet emits deterministic episode_id"
```

Report: status / test count / commit SHA.

---

## Task B2: `render_yaml` injects `time.output_grouping`

**Files:**
- Modify: `backend/app/experiments/bg_ndi_wi.py`
- Test: `backend/tests/test_bg_ndi_wi.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_bg_ndi_wi.py`:

```python
def test_render_yaml_injects_output_grouping_episode(fake_template_dir, tmp_path):
    """Rendered C4 YAML must have time.output_grouping == 'episode'."""
    from app.experiments.bg_ndi_wi import render_yaml, _VARIABLE_TO_STEP

    task_dir = tmp_path / "task-grouping"
    task_dir.mkdir()
    user_config = {"buffer": {"size": 270, "raster_res_m": 25}}

    step = _VARIABLE_TO_STEP["ndi"]
    out = render_yaml(step, task_dir, user_config)
    cfg = yaml.safe_load(out.read_text())
    assert cfg["time"]["output_grouping"] == "episode"


def test_render_yaml_creates_time_block_if_absent(fake_template_dir, tmp_path):
    """C3 templates may not have a `time:` block. Render must create one
    safely, not crash."""
    from app.experiments.bg_ndi_wi import render_yaml, _C3_STEP

    task_dir = tmp_path / "task-c3-time-block"
    task_dir.mkdir()
    user_config = {"buffer": {"size": 270, "raster_res_m": 25}}

    out = render_yaml(_C3_STEP, task_dir, user_config)
    cfg = yaml.safe_load(out.read_text())
    assert cfg.get("time", {}).get("output_grouping") == "episode"
```

NOTE: these tests use the existing `fake_template_dir` fixture defined in `test_bg_ndi_wi.py`. The C3 fake template currently doesn't have a `time:` block — the second test exercises the `setdefault` behaviour.

- [ ] **Step 2: Run failing tests**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_bg_ndi_wi.py -v -k "output_grouping_episode or time_block_if_absent"
```

Expected: 2 FAIL — render_yaml doesn't touch the time block.

- [ ] **Step 3: Modify `render_yaml`**

Edit `backend/app/experiments/bg_ndi_wi.py`. Find the existing `render_yaml` function. Add the injection at the end, after the existing 5 keys are set, before the file is written:

```python
def render_yaml(step: PipelineStep, task_dir: Path, user_config: dict) -> Path:
    """Read a pipeline YAML template, inject task-specific fields, write to task dir.
    ..."""
    template_path = (
        app.config.settings.SPACESCANS_CONFIG_TEMPLATES_DIR / step.template_relpath
    )
    cfg = yaml.safe_load(template_path.read_text())

    task_id_short = task_dir.name[-8:]
    cfg["name"] = f"{cfg['name']}_task_{task_id_short}"
    cfg["buffer"]["patient_file"] = str(task_dir / "input.parquet")
    cfg["buffer"]["buffer_m"] = user_config["buffer"]["size"]
    if step.is_c3:
        cfg["buffer"]["raster_res_m"] = user_config["buffer"]["raster_res_m"]
    cfg["output"]["path"] = str(task_dir / "output" / f"{step.name}.parquet")

    # Sprint 2: switch pipeline to per-episode output grouping. Only
    # meaningful for C4 patterns that consume TimeConfig; C3 patterns
    # ignore it. setdefault() handles templates that don't have a
    # `time:` block.
    cfg.setdefault("time", {})["output_grouping"] = "episode"

    out = task_dir / "pipeline_configs" / f"{step.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out
```

- [ ] **Step 4: Tests pass**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_bg_ndi_wi.py -v -k "output_grouping_episode or time_block_if_absent"
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/tests/test_bg_ndi_wi.py
git commit -m "feat(experiments): render_yaml injects time.output_grouping=episode"
```

Report: status / test count / commit SHA.

---

## Task B3: `merge_results` joins on `(pid, episode_id)`

**Files:**
- Modify: `backend/app/experiments/bg_ndi_wi.py`
- Test: `backend/tests/test_bg_ndi_wi.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_bg_ndi_wi.py`:

```python
def test_merge_results_joins_on_pid_and_episode_id(tmp_path):
    """10-row input (5 PATID × 2 episodes) merges 1:1 with C4 (PATID, geoid, value)."""
    from app.experiments.bg_ndi_wi import merge_results

    task_dir = tmp_path / "task-multi-episode"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    (task_dir / "logs.jsonl").touch()

    # 5 patients × 2 episodes = 10 rows; episode_id = row index in input.
    rows = []
    for pi in range(5):
        for ei in range(2):
            rows.append(f"PID{pi+1:07d},2017-01-01,2018-12-31,-93.0,45.0")
    input_text = "pid,startDate,endDate,longitude,latitude\n" + "\n".join(rows) + "\n"
    (task_dir / "input.csv").write_text(input_text)

    # C4 emits (PATID, geoid, ndi) with 10 rows, geoid == row index (per the
    # pipeline's _adapt_demo_conus → temporal_aggregate(group_by=[PATID, geoid])).
    pids = [f"PID{(i//2)+1:07d}" for i in range(10)]
    geoids = list(range(10))
    pd.DataFrame({
        "PATID": pids,
        "geoid": geoids,
        "ndi": [0.1 * i for i in range(10)],
    }).to_parquet(task_dir / "output" / "c4_ndi.parquet", index=False)

    out = merge_results(task_dir, variables=["ndi"])
    df = pd.read_csv(out)

    # Row count preserved
    assert len(df) == 10
    # Every row's ndi non-null
    assert df["ndi"].notna().all()
    # Each (pid, episode_id) appears exactly once in the result
    assert df.drop_duplicates(subset=["pid", "episode_id"]).shape[0] == 10
    # episode_id column preserved in result
    assert "episode_id" in df.columns
    assert df["episode_id"].tolist() == list(range(10))


def test_merge_results_preserves_episode_id_column(tmp_path):
    """episode_id is a column in result.csv after merge."""
    from app.experiments.bg_ndi_wi import merge_results

    task_dir = tmp_path / "task-single"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    (task_dir / "logs.jsonl").touch()

    (task_dir / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "PID0000001,2017-01-01,2017-12-31,-93.0,45.0\n"
        "PID0000002,2017-01-01,2017-12-31,-95.0,30.0\n"
    )
    pd.DataFrame({
        "PATID": ["PID0000001", "PID0000002"],
        "geoid": [0, 1],
        "ndi": [-1.0, -2.0],
    }).to_parquet(task_dir / "output" / "c4_ndi.parquet", index=False)

    out = merge_results(task_dir, variables=["ndi"])
    df = pd.read_csv(out)
    assert "episode_id" in df.columns
    assert df["episode_id"].tolist() == [0, 1]
```

- [ ] **Step 2: Run failing tests**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_bg_ndi_wi.py -v -k "joins_on_pid_and_episode_id or preserves_episode_id_column"
```

Expected: 2 FAIL — merge currently joins on `pid` only, and the C4 parquet has a `geoid` column that today's join doesn't recognize.

- [ ] **Step 3: Modify `merge_results`**

Edit `backend/app/experiments/bg_ndi_wi.py`. Find the existing `merge_results`:

```python
def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Left-join each per-variable parquet onto the original input CSV by PATID.
    ..."""
    df = pd.read_csv(task_dir / "input.csv", dtype=str)
    for var in variables:
        parquet_name = _VARIABLE_PARQUET[var]
        var_df = pd.read_parquet(task_dir / "output" / parquet_name)
        var_df = var_df.rename(columns={"PATID": "pid"})
        df = df.merge(var_df, on="pid", how="left")

        # var_df was just left-merged into df; check how many input patients
        # got a real value (i.e., how many input rows are NOT null in the new col).
        value_col = next(c for c in var_df.columns if c != "pid")
        match_pct = df[value_col].notna().mean() * 100
        if match_pct < 90.0:
            _append_log(task_dir, "warning", "runner",
                        f"merge: {var} matched only {match_pct:.1f}% of patients")

    out = task_dir / "output" / "result.csv"
    df.to_csv(out, index=False)
    return out
```

Replace with:

```python
def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Left-join each per-variable parquet onto the original input CSV by
    (pid, episode_id).

    The csv_to_parquet step assigned episode_id = range(len(df)) so the
    pipeline's _adapt_demo_conus would copy it onto the synthetic `geoid`
    column. C4 outputs therefore carry (PATID, geoid, value) — we rename
    those to (pid, episode_id, value) and join on the pair so each input
    row gets exactly its own exposure value.
    """
    df = pd.read_csv(task_dir / "input.csv", dtype=str)
    df["episode_id"] = range(len(df))  # same deterministic assignment as csv_to_parquet

    for var in variables:
        parquet_name = _VARIABLE_PARQUET[var]
        var_df = pd.read_parquet(task_dir / "output" / parquet_name)
        # Pipeline returns (PATID, geoid, <value>) under Sprint 2's
        # output_grouping=episode mode; rename to align with input.
        var_df = var_df.rename(columns={"PATID": "pid", "geoid": "episode_id"})
        # Ensure episode_id dtype is integer-comparable; left side is python int.
        var_df["episode_id"] = var_df["episode_id"].astype(int)
        df = df.merge(var_df, on=["pid", "episode_id"], how="left")

        # Coverage check (carried over from Sprint 1).
        value_col = next(c for c in var_df.columns if c not in ("pid", "episode_id"))
        match_pct = df[value_col].notna().mean() * 100
        if match_pct < 90.0:
            _append_log(task_dir, "warning", "runner",
                        f"merge: {var} matched only {match_pct:.1f}% of episodes")

    out = task_dir / "output" / "result.csv"
    df.to_csv(out, index=False)
    return out
```

NOTE: the merge in Step 3 hard-casts `var_df["episode_id"]` to int. The input side has it as a Python int (`range(N)`), which round-trips to int after pandas reads. Both sides will compare as int. If the C4 parquet's `geoid` column is float (it shouldn't be, but just in case), the `astype(int)` covers it.

- [ ] **Step 4: Tests pass**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_bg_ndi_wi.py -v -k "joins_on_pid_and_episode_id or preserves_episode_id_column"
```

Expected: 2 PASS.

- [ ] **Step 5: Full unit suite**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: any Sprint-1 merge tests that previously used the schema-2-col parquets must continue to pass. If `test_merge_results_both_variables` or `test_merge_results_ndi_only` now fail because they hand-craft `c4_*.parquet` without a `geoid` column, update those test fixtures to add `geoid` matching the input's `episode_id`. Document each adjustment in the commit message.

- [ ] **Step 6: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/tests/test_bg_ndi_wi.py
git commit -m "feat(experiments): merge_results joins on (pid, episode_id) for per-episode output"
```

Report: status / test count / commit SHA / any Sprint-1 tests updated.

---

## Task B4: Multi-episode integration test + fixture

**Files:**
- Create: `backend/tests/fixtures/patients_multi_episode.csv`
- Modify: `backend/tests/test_bg_ndi_wi_integration.py` (append)

- [ ] **Step 1: Create the 10-row fixture**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-2
mkdir -p backend/tests/fixtures
cat > backend/tests/fixtures/patients_multi_episode.csv <<'EOF'
pid,startDate,endDate,longitude,latitude
PID0000001,2014-01-01,2017-06-30,-87.6298,41.8781
PID0000001,2017-07-01,2019-12-31,-84.27,30.44
PID0000002,2015-01-01,2018-06-30,-83.0458,42.3314
PID0000002,2018-07-01,2020-12-31,-84.29,30.46
PID0000003,2013-01-01,2019-12-31,-84.31,30.45
PID0000004,2016-01-01,2017-12-31,-95.3633,29.7604
PID0000004,2018-01-01,2020-12-31,-84.25,30.42
PID0000005,2014-01-01,2018-12-31,-84.30,30.48
PID0000005,2019-01-01,2020-12-31,-87.0,41.8
PID0000006,2017-01-01,2020-12-31,-84.28,30.46
EOF
```

Sanity check:
```bash
wc -l backend/tests/fixtures/patients_multi_episode.csv  # expect 11 (10 data + 1 header)
```

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/test_bg_ndi_wi_integration.py`:

```python
@pytest.mark.integration
def test_e2e_multi_episode_cohort(tmp_path):
    """Run the 10-row multi-episode fixture. Result must:
    - preserve 10 rows (not collapse to 6 unique PATIDs)
    - carry episode_id 0..9
    - have distinct ndi / NatWalkInd values for the two episodes of a
      PATID that lived in two different cities."""
    task_dir = tmp_path / "task-multi-episode-int"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_multi_episode.csv",
        task_dir / "input.csv",
    )
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi", "walkability"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))

    cmd = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        "-m", "app.experiments.bg_ndi_wi", "run", str(task_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, f"runner failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"

    result_csv = task_dir / "output" / "result.csv"
    assert result_csv.exists()
    df = pd.read_csv(result_csv)

    assert len(df) == 10, f"expected 10 episode rows, got {len(df)}"
    assert df["episode_id"].tolist() == list(range(10))
    # Sprint 1 demo invariant — both variable columns present
    assert "ndi" in df.columns
    assert "NatWalkInd" in df.columns
    # Multi-episode patients (PID0000001/2/4/5) should have at least
    # one episode pair where the two episodes are in different cities
    # → likely different exposure values. We don't assert numeric
    # equality (the pipeline's behaviour depends on real data) but we
    # do assert that the rows for the same pid are independently rows.
    pid001 = df[df["pid"] == "PID0000001"]
    assert len(pid001) == 2
    assert set(pid001["episode_id"]) == {0, 1}
```

- [ ] **Step 3: Pre-flight: clear C3 cache**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-2/backend
rm -rf data/c3_cache/
```

(The new `episode_id` column changes input.parquet bytes → sha256 → cache key, so old cache entries are stale. Pre-clearing avoids confusion.)

- [ ] **Step 4: Run the integration test**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -m integration -v \
    tests/test_bg_ndi_wi_integration.py::test_e2e_multi_episode_cohort
```

Expected: PASS in 60-120 seconds (cold cache, full pipeline).

If the assertion `len(df) == 10` fails with 6, the pipeline didn't honour `output_grouping=episode` (Phase A misapplied). Inspect `task_dir/pipeline_configs/c4_ndi.yaml` to confirm it has `time.output_grouping: episode`, and inspect `task_dir/output/c4_ndi.parquet` shape to confirm it has 10 rows.

- [ ] **Step 5: Run the full default suite**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 75 passed (was 71 + 4 new from B3 — note B3 doesn't actually add net new tests; the 4 came from B1+B2+B3).

Actually, recount: 69 baseline + 2 (B1) + 2 (B2) + 2 (B3) = 75. Confirm.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/fixtures/patients_multi_episode.csv \
        backend/tests/test_bg_ndi_wi_integration.py
git commit -m "test(integration): e2e multi-episode cohort proves per-episode output"
```

Report: status / test counts / wall-clock / commit SHA / concerns.

---

## Task B5: Frontend results-page hint

**Files:**
- Modify: `frontend/src/app/dashboard/task/[id]/results/page.tsx`

- [ ] **Step 1: Read the current download section**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-2/frontend
grep -n "Download result" src/app/dashboard/task/\[id\]/results/page.tsx | head -5
```

Locate the existing "Download result.csv" button block.

- [ ] **Step 2: Add the hint above the download section**

Inside the `<div className="rounded-lg border bg-card p-6 shadow-sm">` that wraps "Download Results", add a small hint block just before the button:

```tsx
<div className="mb-3 rounded-md border border-blue-500/20 bg-blue-500/5 p-2 text-xs text-blue-700 dark:text-blue-400">
  <strong>Result shape:</strong> one row per residential episode (matches
  your input CSV row count). Each row carries the original patient + episode
  metadata plus exposure values per selected variable.
</div>
```

Place this immediately after the `<h3>Download Results</h3>` heading (or its equivalent in the current file), so the hint appears between the section title and the description text.

- [ ] **Step 3: Typecheck**

```bash
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
node_modules/.bin/tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/dashboard/task/\[id\]/results/page.tsx frontend/tsconfig.tsbuildinfo
git commit -m "feat(wizard): result page 'one row per episode' hint"
```

Report: status / tsc output / commit SHA.

---

## Task B6: Final verification + manual smoke + Phase B wrap-up

**Files:**
- Modify: `backend/tests/manual_e2e.md` (append Sprint 2 section)

- [ ] **Step 1: Run the full backend suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-2/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 75 passed, 1 skipped, 6 deselected (the integration count went up by 1 with the new multi-episode test).

- [ ] **Step 2: Run integration tests**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -m integration -v
```

Expected: 6/6 integration tests pass (5 from Sprint 1 + 1 new multi-episode). Total wall-clock ≈ 75-120 s including the new multi-episode test.

- [ ] **Step 3: Frontend typecheck**

```bash
cd ../frontend
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
node_modules/.bin/tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 4: Append Sprint 2 section to manual_e2e.md**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-2
```

Append to `backend/tests/manual_e2e.md`:

```markdown
## Sprint 2 multi-episode walk-through

Upload `backend/tests/fixtures/patients_multi_episode.csv` (10 rows; 5
patients × 2 residential moves over 2013-2020 + 1 single-episode
control).

1. Reach the Variables step. The Sprint 1 coverage panel should still
   render (≈100 % covered on this small synthetic set).
2. Run with default 270 m buffer + both NDI and Walkability.
3. Download `result.csv`. Inspect:
   - 10 rows (NOT 6 — that's the unique PATID count).
   - `episode_id` column present, values 0..9.
   - PID0000001 appears twice (episode_id 0 + 1) with potentially
     different NDI / Walkability values (IL → FL move).
   - PID0000006 appears once (single-episode control), same as Sprint 1.
4. The results page should show a blue "Result shape: one row per
   residential episode" hint above the download button.

To force a fresh pipeline run after Sprint 2 deployment (Sprint 1 cache
keys are different because the parquet bytes now include the new
`episode_id` column):

    rm -rf backend/data/c3_cache/
```

- [ ] **Step 5: Final commit**

```bash
git add backend/tests/manual_e2e.md
git commit -m "docs(tests): manual_e2e Sprint 2 multi-episode walk-through"
```

- [ ] **Step 6: Branch summary**

```bash
git log --oneline main..HEAD
git diff --stat main..HEAD | tail -3
```

Expected: 6 commits (B1..B6), modifying ~5 source files + adding 2 test files + 1 fixture + 1 doc.

- [ ] **Step 7: Hand off to finishing-a-development-branch**

The Sprint 2 implementation is complete. Decide merge / PR / keep / discard via:

```
Use the superpowers:finishing-a-development-branch skill.
```

Report: status / final test counts (default + integration + tsc) / commit SHAs / any concerns / readiness for merge.

---

## Spec coverage map

| Spec section | Implemented by |
|---|---|
| Goal | All tasks collectively |
| Scope > In scope > TimeConfig.output_grouping field | Task A1 |
| Scope > In scope > 3 linkage pattern dispatch | Tasks A2, A3, A4 |
| Scope > In scope > _adapt_demo_conus episode_id fallback | Task A5 |
| Scope > In scope > csv_to_parquet episode_id | Task B1 |
| Scope > In scope > render_yaml output_grouping=episode | Task B2 |
| Scope > In scope > merge_results join (pid, episode_id) | Task B3 |
| Scope > In scope > frontend result-shape hint | Task B5 |
| Scope > In scope > unit + integration tests | Tasks A1-A5 (unit pipeline), B1-B3 (unit web), B4 (integration) |
| Scope > Out of scope (episode UI, real EHR, persisted episode_id, backward-compat) | Deliberately not implemented |
| Architecture > Phase A pipeline | Tasks A0-A6 |
| Architecture > Phase B web | Tasks B0-B6 |
| Architecture > Editable install ties Phase A → B | Task A6 Step 6 explicit verification |
| Backend Modules > TimeConfig | Task A1 |
| Backend Modules > yearly_areal | Task A2 |
| Backend Modules > yearly_areal_bg_vintage | Task A3 |
| Backend Modules > static_areal + DurationWeightedSpec + engine | Task A4 |
| Backend Modules > _adapt_demo_conus | Task A5 |
| Backend Modules > csv_to_parquet | Task B1 |
| Backend Modules > render_yaml | Task B2 |
| Backend Modules > merge_results | Task B3 |
| Frontend Changes > result-shape hint | Task B5 |
| Error Handling > Pipeline failure matrix | Tasks A2-A5 (ValueError on invalid output_grouping; adapter fallback; spec mocked) |
| Error Handling > Web failure matrix | Task B1 (overwrite + warn); B3 (low-match warning preserved) |
| Error Handling > C3 cache interaction | Task B4 Step 3 (pre-clear before integration test) |
| Testing > Unit tests | Tasks A1-A5, B1-B3 |
| Testing > Integration test | Task B4 |
| Testing > Manual smoke | Task B6 |
| Phase Sequencing | Tasks A0 → A6 first, then B0 → B6 |

All spec requirements have at least one implementing task. No gaps.
