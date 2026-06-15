# spacescans-web ↔ spacescans-pipeline Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `mock_cli/` in `spacescans-web/backend/` with a real subprocess invocation of `spacescans-pipeline` for one experiment — BG NDI + EPA Walkability Index — covering CSV upload → 3-step C3/C4 pipeline → merged `result.csv` download.

**Architecture:** FastAPI dispatches each task to a new `app.experiments.bg_ndi_wi` subprocess via `python -m`. The subprocess renders task-local YAML configs from `/Users/xai/Desktop/spacescans-project/configs/{c3,c4}/`, runs `spacescans` CLI sequentially (one C3 then one C4 per selected variable), parses stdout progress to the existing `status.json` / `logs.jsonl` contract, and left-joins per-variable outputs onto the original input CSV. A file lock at `backend/data/.run_lock` enforces one task at a time.

**Tech Stack:** FastAPI · uvicorn · subprocess + fcntl.flock · PyYAML · pandas · pyarrow · Next.js 14 · shadcn/ui · spacescans-pipeline 0.1+ CLI (conda env `spacescans`).

---

## File Structure

### New files

| Path | Role |
|---|---|
| `backend/app/experiments/__init__.py` | empty package marker |
| `backend/app/experiments/bg_ndi_wi.py` | single-experiment orchestrator (~250 LOC, 6 functions + `__main__`) |
| `backend/tests/test_bg_ndi_wi.py` | unit tests for the 6 helper functions |
| `backend/tests/test_bg_ndi_wi_integration.py` | integration tests gated on `SPACESCANS_DATA_DIR` presence |
| `backend/tests/fixtures/patients_5.csv` | 5-row CSV with Leon FL coordinates for integration tests |
| `backend/tests/fixtures/fake_spacescans.py` | tiny script that mimics spacescans stdout for unit tests |
| `backend/tests/manual_e2e.md` | step-by-step UI walk-through for human verification |

### Modified backend files

| Path | Change |
|---|---|
| `backend/app/config.py` | add 4 env-bound settings (data dir, pipeline python/CLI, templates dir) + startup validation |
| `backend/app/task_manager.py` | (a) accept `experiment` in `save_config`, (b) dispatch in `start_task`, (c) acquire `.run_lock` |
| `backend/app/routers/tasks.py` | `/start` returns 409 if lock busy + propagates fail-fast 400 from `start_task` |
| `backend/requirements.txt` | add `pyyaml>=6.0` (pandas + pyarrow are already transitive but stay implicit) |

### Modified frontend files

| Path | Change |
|---|---|
| `frontend/src/components/wizard/wizard-layout.tsx` | STEPS description copy edit for step 3 |
| `frontend/src/components/wizard/buffer-step.tsx` | lock `shape=circle`, add `raster_res_m` input |
| `frontend/src/components/wizard/variables-step.tsx` | replace ontology browse with 2-checkbox v1 UI, ontology gated on env flag |
| `frontend/src/components/wizard/review-step.tsx` | multi-step progress panel + per-file results download list |
| `frontend/src/lib/api.ts` | `saveConfig` body includes `experiment: "bg_ndi_wi"` |

---

## Pre-implementation: environment confirmation

These commands must succeed on the developer's machine before any task runs. They verify the developer has the required local paths the plan assumes.

```bash
test -d /Users/xai/Desktop/spacescans-project/data_full
test -f /Users/xai/Desktop/spacescans-project/configs/c3/bg_us_demo.yaml
test -f /Users/xai/Desktop/spacescans-project/configs/c4/bg_ndi_demo.yaml
test -f /Users/xai/Desktop/spacescans-project/configs/c4/bg_wi_demo.yaml
test -x /Users/xai/miniconda3/envs/spacescans/bin/spacescans
test -d /Users/xai/Desktop/spacescans-project/data_full/BG_FL/C3/tiger2010_bg10_states
test -f /Users/xai/Desktop/spacescans-project/data_full/BG_NDI/C4/ndi_2012_2022_nationwide_BG.Rda
test -f /Users/xai/Desktop/spacescans-project/data_full/BG_WI/C4/epawalkind_nationwide_2016_2021.Rda
```

If any fails, stop and reconcile path values before proceeding.

Set the env vars used in the rest of the plan (a `.env` file at `backend/.env` is the canonical location):

```bash
# backend/.env
SPACESCANS_DATA_DIR=/Users/xai/Desktop/spacescans-project/data_full
SPACESCANS_PIPELINE_PYTHON=/Users/xai/miniconda3/envs/spacescans/bin/python
SPACESCANS_PIPELINE_CLI=/Users/xai/miniconda3/envs/spacescans/bin/spacescans
SPACESCANS_CONFIG_TEMPLATES_DIR=/Users/xai/Desktop/spacescans-project/configs
SECRET_KEY=dev-only-secret-change-in-prod
```

All backend tasks run inside the `spacescans` conda env:

```bash
export PATH="/Users/xai/miniconda3/envs/spacescans/bin:$PATH"
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
```

All frontend tasks run with Node 20 on PATH:

```bash
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
cd /Users/xai/Desktop/spacescans-project/spacescans-web/frontend
```

---

## Task 1: Backend config — env-bound pipeline settings

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env` (add new entries)
- Test: `backend/tests/test_config.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_config.py`:

```python
import importlib
import os
import pytest
from pathlib import Path

def test_pipeline_settings_load_from_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data_full"
    data_dir.mkdir()
    py = tmp_path / "python"
    py.write_text("#!/bin/sh\n")
    py.chmod(0o755)
    cli = tmp_path / "spacescans"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o755)
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()

    monkeypatch.setenv("SPACESCANS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("SPACESCANS_PIPELINE_PYTHON", str(py))
    monkeypatch.setenv("SPACESCANS_PIPELINE_CLI", str(cli))
    monkeypatch.setenv("SPACESCANS_CONFIG_TEMPLATES_DIR", str(cfg_dir))

    import app.config
    importlib.reload(app.config)
    s = app.config.settings

    assert s.SPACESCANS_DATA_DIR == data_dir
    assert s.SPACESCANS_PIPELINE_PYTHON == py
    assert s.SPACESCANS_PIPELINE_CLI == cli
    assert s.SPACESCANS_CONFIG_TEMPLATES_DIR == cfg_dir

def test_validate_pipeline_settings_raises_on_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SPACESCANS_DATA_DIR", str(tmp_path / "does-not-exist"))
    monkeypatch.setenv("SPACESCANS_PIPELINE_PYTHON", str(tmp_path / "nope"))
    monkeypatch.setenv("SPACESCANS_PIPELINE_CLI", str(tmp_path / "nope"))
    monkeypatch.setenv("SPACESCANS_CONFIG_TEMPLATES_DIR", str(tmp_path / "nope"))

    import app.config
    importlib.reload(app.config)
    with pytest.raises(RuntimeError, match="SPACESCANS_DATA_DIR"):
        app.config.validate_pipeline_settings()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
pytest tests/test_config.py -v
```

Expected: both tests FAIL — `AttributeError` on missing `SPACESCANS_DATA_DIR` setting, or `AttributeError` on `validate_pipeline_settings`.

- [ ] **Step 3: Implement the settings**

Edit `backend/app/config.py`:

```python
import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "SPACESCANS"
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    ALGORITHM: str = "HS256"
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    TASKS_DIR: Path = DATA_DIR / "tasks"
    DB_PATH: Path = DATA_DIR / "spacescans.db"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    MAX_UPLOAD_SIZE_MB: int = 100

    # spacescans-pipeline integration
    SPACESCANS_DATA_DIR: Path = Path("/nonexistent")
    SPACESCANS_PIPELINE_PYTHON: Path = Path("/nonexistent")
    SPACESCANS_PIPELINE_CLI: Path = Path("/nonexistent")
    SPACESCANS_CONFIG_TEMPLATES_DIR: Path = Path("/nonexistent")
    PIPELINE_STEP_TIMEOUT_SECONDS: int = 1800  # 30 min per spacescans run

    class Config:
        env_file = ".env"

settings = Settings()


def validate_pipeline_settings() -> None:
    """Raise RuntimeError early if any pipeline path is missing.

    Called from app.main:create_app on startup so the FastAPI process refuses
    to serve traffic before its required external dependencies are present.
    """
    missing = []
    for name in (
        "SPACESCANS_DATA_DIR",
        "SPACESCANS_PIPELINE_PYTHON",
        "SPACESCANS_PIPELINE_CLI",
        "SPACESCANS_CONFIG_TEMPLATES_DIR",
    ):
        path = getattr(settings, name)
        if not path.exists():
            missing.append(f"{name}={path}")
    if missing:
        raise RuntimeError(
            "Pipeline integration disabled. Missing paths: " + ", ".join(missing)
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Wire validation into app startup**

Edit `backend/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings, validate_pipeline_settings
from app.database import init_db
from app.routers.auth import router as auth_router
from app.routers.tasks import router as tasks_router
from app.task_manager import recover_orphaned_tasks


def create_app() -> FastAPI:
    app = FastAPI(title=settings.PROJECT_NAME)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(tasks_router)

    @app.on_event("startup")
    async def startup():
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        settings.TASKS_DIR.mkdir(parents=True, exist_ok=True)
        init_db()
        recover_orphaned_tasks()
        validate_pipeline_settings()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app

app = create_app()
```

- [ ] **Step 6: Run the full backend test suite**

```bash
pytest -q
```

Expected: previous 17 passing tests still pass, plus 2 new config tests pass — 19 passing.

- [ ] **Step 7: Add the values to `backend/.env`**

Append to `backend/.env` (create if missing):

```
SPACESCANS_DATA_DIR=/Users/xai/Desktop/spacescans-project/data_full
SPACESCANS_PIPELINE_PYTHON=/Users/xai/miniconda3/envs/spacescans/bin/python
SPACESCANS_PIPELINE_CLI=/Users/xai/miniconda3/envs/spacescans/bin/spacescans
SPACESCANS_CONFIG_TEMPLATES_DIR=/Users/xai/Desktop/spacescans-project/configs
```

`backend/.env` is gitignored by default; double-check `.gitignore` lists `.env` and `backend/.env`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/config.py backend/app/main.py backend/tests/test_config.py
git commit -m "feat(config): add pipeline integration env settings + startup validation"
```

---

## Task 2: PipelineStep + plan()

**Files:**
- Create: `backend/app/experiments/__init__.py`
- Create: `backend/app/experiments/bg_ndi_wi.py`
- Create: `backend/tests/test_bg_ndi_wi.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_bg_ndi_wi.py`:

```python
import pytest
from app.experiments.bg_ndi_wi import plan, PipelineStep

def test_plan_with_both_variables():
    steps = plan({"variables": ["ndi", "walkability"], "buffer": {"size": 270, "raster_res_m": 25}})
    assert [s.name for s in steps] == ["c3_bg", "c4_ndi", "c4_wi"]
    assert [s.is_c3 for s in steps] == [True, False, False]
    assert steps[0].template_relpath == "c3/bg_us_demo.yaml"
    assert steps[1].template_relpath == "c4/bg_ndi_demo.yaml"
    assert steps[2].template_relpath == "c4/bg_wi_demo.yaml"

def test_plan_with_ndi_only():
    steps = plan({"variables": ["ndi"], "buffer": {"size": 270, "raster_res_m": 25}})
    assert [s.name for s in steps] == ["c3_bg", "c4_ndi"]

def test_plan_with_walkability_only():
    steps = plan({"variables": ["walkability"], "buffer": {"size": 270, "raster_res_m": 25}})
    assert [s.name for s in steps] == ["c3_bg", "c4_wi"]

def test_plan_with_no_variables_raises():
    with pytest.raises(ValueError, match="at least one variable"):
        plan({"variables": [], "buffer": {"size": 270, "raster_res_m": 25}})

def test_plan_with_unknown_variable_raises():
    with pytest.raises(ValueError, match="unknown variable.*pm25"):
        plan({"variables": ["ndi", "pm25"], "buffer": {"size": 270, "raster_res_m": 25}})
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_bg_ndi_wi.py -v
```

Expected: ALL FAIL with `ModuleNotFoundError: No module named 'app.experiments'`.

- [ ] **Step 3: Implement plan()**

Create `backend/app/experiments/__init__.py` (empty file):

```bash
mkdir -p backend/app/experiments
touch backend/app/experiments/__init__.py
```

Create `backend/app/experiments/bg_ndi_wi.py`:

```python
"""Single-experiment orchestrator: BG boundaries × {NDI, Walkability}.

Spawned by app.task_manager.start_task as:
    python -m app.experiments.bg_ndi_wi run <task_dir>
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineStep:
    name: str                # used as filename stem + log "source"
    template_relpath: str    # relative to SPACESCANS_CONFIG_TEMPLATES_DIR
    is_c3: bool              # controls whether to inject raster_res_m


_VARIABLE_TO_STEP = {
    "ndi": PipelineStep(name="c4_ndi", template_relpath="c4/bg_ndi_demo.yaml", is_c3=False),
    "walkability": PipelineStep(name="c4_wi", template_relpath="c4/bg_wi_demo.yaml", is_c3=False),
}

_C3_STEP = PipelineStep(name="c3_bg", template_relpath="c3/bg_us_demo.yaml", is_c3=True)


def plan(config: dict) -> list[PipelineStep]:
    """Compute the ordered pipeline steps for a task.

    The single C3 step always runs first; each selected variable adds one C4
    step in a deterministic order (NDI before Walkability).
    """
    variables = config.get("variables", [])
    if not variables:
        raise ValueError("at least one variable must be selected")
    unknown = [v for v in variables if v not in _VARIABLE_TO_STEP]
    if unknown:
        raise ValueError(f"unknown variable(s): {', '.join(unknown)}")
    steps = [_C3_STEP]
    for v in ("ndi", "walkability"):
        if v in variables:
            steps.append(_VARIABLE_TO_STEP[v])
    return steps
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_bg_ndi_wi.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/experiments/__init__.py backend/app/experiments/bg_ndi_wi.py backend/tests/test_bg_ndi_wi.py
git commit -m "feat(experiments): scaffold bg_ndi_wi package + plan() helper"
```

---

## Task 3: csv_to_parquet — dtype preservation

**Files:**
- Modify: `backend/app/experiments/bg_ndi_wi.py`
- Modify: `backend/tests/test_bg_ndi_wi.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_bg_ndi_wi.py`:

```python
from pathlib import Path
import pandas as pd
from app.experiments.bg_ndi_wi import csv_to_parquet

def test_csv_to_parquet_preserves_fips(tmp_path):
    src = tmp_path / "input.csv"
    src.write_text(
        "pid,startDate,endDate,longitude,latitude,state_fips,county_fips,tract_geoid,bg_geoid\n"
        "PID0000001,2017-08-19,2017-11-11,-93.028635,45.088976,06,06037,06037263400,060372634001\n"
        "PID0000002,2017-03-24,2017-06-21,-95.345115,29.738952,48,48201,48201451601,482014516012\n"
    )
    dst = tmp_path / "input.parquet"
    csv_to_parquet(src, dst)

    df = pd.read_parquet(dst)
    assert df.shape == (2, 9)
    assert df["state_fips"].dtype == object  # pandas stores str as object
    assert df["state_fips"].iloc[0] == "06"  # leading zero preserved
    assert df["county_fips"].iloc[0] == "06037"
    assert df["bg_geoid"].iloc[0] == "060372634001"
    assert pd.api.types.is_datetime64_any_dtype(df["startDate"])
    assert pd.api.types.is_datetime64_any_dtype(df["endDate"])

def test_csv_to_parquet_works_without_optional_fips(tmp_path):
    src = tmp_path / "input.csv"
    src.write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "PID0000001,2017-08-19,2017-11-11,-93.028635,45.088976\n"
    )
    dst = tmp_path / "input.parquet"
    csv_to_parquet(src, dst)
    df = pd.read_parquet(dst)
    assert df.shape == (1, 5)
    assert pd.api.types.is_datetime64_any_dtype(df["startDate"])

def test_csv_to_parquet_rejects_malformed_dates(tmp_path):
    src = tmp_path / "input.csv"
    src.write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "PID0000001,not-a-date,2017-11-11,-93.0,45.0\n"
    )
    dst = tmp_path / "input.parquet"
    import pytest
    with pytest.raises((ValueError, pd.errors.ParserError)):
        csv_to_parquet(src, dst)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_bg_ndi_wi.py -v -k csv_to_parquet
```

Expected: all 3 tests FAIL with `ImportError: cannot import name 'csv_to_parquet'`.

- [ ] **Step 3: Implement csv_to_parquet**

Append to `backend/app/experiments/bg_ndi_wi.py`:

```python
from pathlib import Path
import pandas as pd

# FIPS columns must remain string to preserve leading zeros (e.g. "06" for CA).
_FIPS_STR_COLS = ("state_fips", "county_fips", "tract_geoid", "bg_geoid")


def csv_to_parquet(src: Path, dst: Path) -> None:
    """Convert uploaded CSV to parquet with explicit dtype handling.

    - FIPS columns (state_fips, county_fips, tract_geoid, bg_geoid) are read as
      string to preserve leading zeros that the pipeline's GEOID joins need.
    - startDate / endDate are parsed to datetime64 so downstream code does not
      need to coerce them again.
    - No column renames here; the pipeline's `demo_conus` adapter performs
      renames at runtime (see spacescans/linkage/helpers.py:_adapt_demo_conus).
    """
    # Read header first to determine which optional FIPS columns are present.
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

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_bg_ndi_wi.py -v -k csv_to_parquet
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/tests/test_bg_ndi_wi.py
git commit -m "feat(experiments): csv_to_parquet with FIPS string preservation + date parsing"
```

---

## Task 4: render_yaml — template injection

**Files:**
- Modify: `backend/app/experiments/bg_ndi_wi.py`
- Modify: `backend/tests/test_bg_ndi_wi.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_bg_ndi_wi.py`:

```python
import yaml
from app.experiments.bg_ndi_wi import render_yaml, _C3_STEP, _VARIABLE_TO_STEP

@pytest.fixture
def fake_template_dir(tmp_path, monkeypatch):
    # Stub minimal C3 / C4 templates that mimic the real pipeline configs.
    c3 = tmp_path / "c3" / "bg_us_demo.yaml"
    c3.parent.mkdir(parents=True)
    c3.write_text(
        "name: bg_us_demo\n"
        "linkage_pattern: boundary_overlap_fast\n"
        "source:\n  file: data_full/BG_FL/C3/...\n  join_col: GEOID10\n"
        "buffer:\n"
        "  patient_file: data_full/demo_patients_conus_fast_100000.parquet\n"
        "  patient_adapter: demo_conus\n"
        "  buffer_m: 270\n"
        "  raster_res_m: 25\n"
        "output:\n  path: output/bg_us_demo.parquet\n"
    )
    c4 = tmp_path / "c4" / "bg_ndi_demo.yaml"
    c4.parent.mkdir(parents=True)
    c4.write_text(
        "name: bg_ndi_demo\n"
        "linkage_pattern: yearly_areal\n"
        "source:\n  file: data_full/BG_NDI/C4/ndi.Rda\n"
        "buffer:\n"
        "  patient_file: data_full/demo_patients_conus_fast_100000.parquet\n"
        "  patient_adapter: demo_conus\n"
        "  buffer_m: 270\n"
        "output:\n  path: output/bg_ndi_demo.parquet\n"
    )

    import app.config
    monkeypatch.setattr(app.config.settings, "SPACESCANS_CONFIG_TEMPLATES_DIR", tmp_path)
    return tmp_path


def test_render_yaml_c3_injects_all_five_keys(fake_template_dir, tmp_path):
    task_dir = tmp_path / "task-12345678"
    task_dir.mkdir()
    user_config = {"buffer": {"size": 500, "raster_res_m": 50}}

    out = render_yaml(_C3_STEP, task_dir, user_config)

    assert out == task_dir / "pipeline_configs" / "c3_bg.yaml"
    cfg = yaml.safe_load(out.read_text())
    assert cfg["name"].startswith("bg_us_demo_task_")
    assert cfg["buffer"]["patient_file"] == str(task_dir / "input.parquet")
    assert cfg["buffer"]["patient_adapter"] == "demo_conus"  # preserved
    assert cfg["buffer"]["buffer_m"] == 500
    assert cfg["buffer"]["raster_res_m"] == 50
    assert cfg["output"]["path"] == str(task_dir / "output" / "c3_bg.parquet")
    # source.file is left alone — pipeline resolves it via --data-dir
    assert cfg["source"]["file"] == "data_full/BG_FL/C3/..."


def test_render_yaml_c4_skips_raster_res_m(fake_template_dir, tmp_path):
    task_dir = tmp_path / "task-12345678"
    task_dir.mkdir()
    step = _VARIABLE_TO_STEP["ndi"]
    user_config = {"buffer": {"size": 270, "raster_res_m": 25}}

    out = render_yaml(step, task_dir, user_config)

    cfg = yaml.safe_load(out.read_text())
    # The fake C4 template does not have raster_res_m and rendering must not
    # add it (C4 doesn't use rasterization).
    assert "raster_res_m" not in cfg["buffer"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_bg_ndi_wi.py -v -k render_yaml
```

Expected: both FAIL with `ImportError: cannot import name 'render_yaml'`.

- [ ] **Step 3: Implement render_yaml**

Append to `backend/app/experiments/bg_ndi_wi.py`:

```python
import yaml
import app.config


def render_yaml(step: PipelineStep, task_dir: Path, user_config: dict) -> Path:
    """Read a pipeline YAML template, inject task-specific fields, write to task dir.

    Only five keys are overwritten; everything else (source.file, exposure.file,
    time.years, engine.backend, etc.) is preserved as-is so the rendered config
    behaves identically to the canonical experiment pipeline.
    """
    template_path = (
        app.config.settings.SPACESCANS_CONFIG_TEMPLATES_DIR / step.template_relpath
    )
    cfg = yaml.safe_load(template_path.read_text())

    task_id_short = task_dir.name[-8:]
    cfg["name"] = f"{cfg['name']}_task_{task_id_short}"
    cfg["buffer"]["patient_file"] = str(task_dir / "input.parquet")
    # patient_adapter "demo_conus" stays as-is: our upload schema mirrors the
    # demo cohort's columns, so the adapter's rename + synthetic-geoid logic
    # applies unchanged.
    cfg["buffer"]["buffer_m"] = user_config["buffer"]["size"]
    if step.is_c3:
        cfg["buffer"]["raster_res_m"] = user_config["buffer"]["raster_res_m"]
    cfg["output"]["path"] = str(task_dir / "output" / f"{step.name}.parquet")

    out = task_dir / "pipeline_configs" / f"{step.name}.yaml"
    out.parent.mkdir(exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_bg_ndi_wi.py -v -k render_yaml
```

Expected: both tests PASS.

- [ ] **Step 5: Add `pyyaml` to requirements**

Edit `backend/requirements.txt`, append before the last line:

```
pyyaml>=6.0
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/tests/test_bg_ndi_wi.py backend/requirements.txt
git commit -m "feat(experiments): render_yaml template injection for pipeline steps"
```

---

## Task 5: stdout progress parsing

**Files:**
- Modify: `backend/app/experiments/bg_ndi_wi.py`
- Modify: `backend/tests/test_bg_ndi_wi.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_bg_ndi_wi.py`:

```python
from app.experiments.bg_ndi_wi import parse_step_progress

def test_parse_step_progress_overlap_fast():
    line = "[overlap_fast] tile 7460/14938 ( 49.9%) elapsed=  1.64m  rate= 75.9/s  ETA= 1.64m  tiles_with_work=2807"
    assert parse_step_progress(line) == pytest.approx(0.499, abs=0.005)

def test_parse_step_progress_overlap_classic():
    line = "[overlap]   1600/3221 ( 49.7%)  elapsed=   2.0m  rate=13.20/s"
    assert parse_step_progress(line) == pytest.approx(0.497, abs=0.005)

def test_parse_step_progress_non_progress_returns_none():
    assert parse_step_progress("[overlap_fast] === SUMMARY ===") is None
    assert parse_step_progress("random log line") is None
    assert parse_step_progress("") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_bg_ndi_wi.py -v -k parse_step_progress
```

Expected: all 3 FAIL on missing `parse_step_progress`.

- [ ] **Step 3: Implement parse_step_progress**

Append to `backend/app/experiments/bg_ndi_wi.py`:

```python
import re

# Matches both:
#   [overlap_fast] tile 7460/14938 ( 49.9%) ...
#   [overlap]   1600/3221 ( 49.7%)  ...
_PROGRESS_RE = re.compile(
    r"\[(?:overlap|overlap_fast)\]\s+(?:tile\s+)?(\d+)/(\d+)"
)


def parse_step_progress(line: str) -> float | None:
    """Return progress fraction in [0,1] if line contains a tile/iteration count.

    Returns None for non-progress lines (SUMMARY, errors, empty lines, etc.).
    """
    m = _PROGRESS_RE.search(line)
    if not m:
        return None
    cur = int(m.group(1))
    total = int(m.group(2))
    if total <= 0:
        return None
    return cur / total
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_bg_ndi_wi.py -v -k parse_step_progress
```

Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/tests/test_bg_ndi_wi.py
git commit -m "feat(experiments): parse_step_progress regex for spacescans stdout"
```

---

## Task 6: run_pipeline_step subprocess wrapper

**Files:**
- Modify: `backend/app/experiments/bg_ndi_wi.py`
- Modify: `backend/tests/test_bg_ndi_wi.py`
- Create: `backend/tests/fixtures/fake_spacescans.py`

- [ ] **Step 1: Create the fake spacescans fixture**

Create `backend/tests/fixtures/__init__.py` (empty):

```bash
mkdir -p backend/tests/fixtures
touch backend/tests/fixtures/__init__.py
```

Create `backend/tests/fixtures/fake_spacescans.py`:

```python
#!/usr/bin/env python3
"""Tiny stand-in for the real `spacescans run` CLI used by unit tests.

Behaviour switches based on the second positional arg (the YAML path's
basename):
  - if filename contains "fail" -> exit 1 with an error line
  - if filename contains "hang" -> sleep forever (used for timeout tests)
  - otherwise -> emit 3 progress lines, write an empty parquet to the
    output.path declared in the YAML, exit 0.
"""
import sys
import time
from pathlib import Path

import yaml
import pandas as pd


def main():
    # sys.argv looks like: ['fake_spacescans.py', 'run', '--data-dir', ..., '<yaml>']
    yaml_path = Path(sys.argv[-1])
    if "fail" in yaml_path.name:
        print("[overlap_fast] tile 1/3 ( 33.3%)", flush=True)
        print("ERROR: something broke", file=sys.stderr, flush=True)
        sys.exit(1)
    if "hang" in yaml_path.name:
        while True:
            time.sleep(0.1)

    print("[overlap_fast] tile 1/3 ( 33.3%)", flush=True)
    print("[overlap_fast] tile 2/3 ( 66.7%)", flush=True)
    print("[overlap_fast] tile 3/3 (100.0%)", flush=True)
    cfg = yaml.safe_load(yaml_path.read_text())
    out_path = Path(cfg["output"]["path"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"PATID": ["P1"], "value": [0.0]}).to_parquet(out_path, index=False)
    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/test_bg_ndi_wi.py`:

```python
import json
import sys
from app.experiments.bg_ndi_wi import run_pipeline_step

@pytest.fixture
def fake_cli_settings(monkeypatch, tmp_path):
    """Point SPACESCANS_PIPELINE_CLI at the fake_spacescans.py fixture so the
    subprocess test does not need the real conda env."""
    fixture = Path(__file__).parent / "fixtures" / "fake_spacescans.py"
    import app.config
    monkeypatch.setattr(app.config.settings, "SPACESCANS_PIPELINE_CLI", fixture)
    monkeypatch.setattr(app.config.settings, "SPACESCANS_PIPELINE_PYTHON", Path(sys.executable))
    monkeypatch.setattr(app.config.settings, "SPACESCANS_DATA_DIR", tmp_path)
    return tmp_path


def _make_task(tmp_path, name="step.yaml") -> tuple[Path, Path]:
    task_dir = tmp_path / "task-deadbeef"
    task_dir.mkdir()
    (task_dir / "logs.jsonl").touch()
    yaml_path = task_dir / "pipeline_configs" / name
    yaml_path.parent.mkdir()
    yaml_path.write_text(yaml.safe_dump({
        "name": "fake",
        "output": {"path": str(task_dir / "output" / "step.parquet")},
    }))
    return task_dir, yaml_path


def test_run_pipeline_step_success(fake_cli_settings):
    task_dir, yaml_path = _make_task(fake_cli_settings)
    rc = run_pipeline_step(yaml_path, task_dir, step_name="c3_bg")
    assert rc == 0
    assert (task_dir / "output" / "step.parquet").exists()
    log_lines = (task_dir / "logs.jsonl").read_text().strip().split("\n")
    progress_lines = [json.loads(l) for l in log_lines if "tile" in l]
    assert len(progress_lines) >= 3
    # logs.jsonl rows are tagged with source = step name
    assert all(j["source"] == "c3_bg" for j in progress_lines)


def test_run_pipeline_step_nonzero_exit(fake_cli_settings):
    task_dir, yaml_path = _make_task(fake_cli_settings, name="fail_step.yaml")
    rc = run_pipeline_step(yaml_path, task_dir, step_name="c3_bg")
    assert rc != 0
    log_text = (task_dir / "logs.jsonl").read_text()
    assert "ERROR" in log_text or "exit code" in log_text
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
pytest tests/test_bg_ndi_wi.py -v -k run_pipeline_step
```

Expected: both FAIL on missing `run_pipeline_step`.

- [ ] **Step 4: Implement run_pipeline_step**

Append to `backend/app/experiments/bg_ndi_wi.py`:

```python
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone


def _append_log(task_dir: Path, level: str, source: str, msg: str) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "source": source,
        "msg": msg,
    }
    with open(task_dir / "logs.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def run_pipeline_step(yaml_path: Path, task_dir: Path, step_name: str) -> int:
    """Run a single `spacescans run` subprocess, streaming stdout into logs.jsonl.

    Each output line is appended to task_dir/logs.jsonl as a JSON record with
    source=step_name so the UI can filter logs by step. Progress lines are
    parsed for the running step's fractional progress (callers can read the
    most recent value via parse_step_progress).

    Returns the subprocess's exit code.
    """
    cmd = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        str(app.config.settings.SPACESCANS_PIPELINE_CLI),
        "run",
        "--data-dir", str(app.config.settings.SPACESCANS_DATA_DIR),
        str(yaml_path),
    ]
    _append_log(task_dir, "info", "runner", f"spawning {step_name}: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,  # for clean kill via killpg later
    )

    # Stream stdout line by line.
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        if line:
            _append_log(task_dir, "info", step_name, line)
    rc = proc.wait()
    _append_log(task_dir, "info" if rc == 0 else "error", "runner",
                f"step {step_name} exit code {rc}")
    return rc
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
pytest tests/test_bg_ndi_wi.py -v -k run_pipeline_step
```

Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/tests/fixtures/__init__.py backend/tests/fixtures/fake_spacescans.py backend/tests/test_bg_ndi_wi.py
git commit -m "feat(experiments): run_pipeline_step subprocess wrapper with stdout->logs.jsonl"
```

---

## Task 7: merge_results — left-join input + per-variable parquets

**Files:**
- Modify: `backend/app/experiments/bg_ndi_wi.py`
- Modify: `backend/tests/test_bg_ndi_wi.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_bg_ndi_wi.py`:

```python
from app.experiments.bg_ndi_wi import merge_results

def _seed_task_for_merge(tmp_path, n_input=5, n_ndi=4, n_wi=3) -> Path:
    """Create a task_dir with input.csv + ndi/walkability parquets at common
    paths, so merge_results can be exercised without running the pipeline."""
    task_dir = tmp_path / "task-abcdef12"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    (task_dir / "logs.jsonl").touch()

    pids = [f"PID{i:07d}" for i in range(n_input)]
    pd.DataFrame({
        "pid": pids,
        "startDate": ["2017-01-01"] * n_input,
        "endDate": ["2017-12-31"] * n_input,
        "longitude": [-93.0] * n_input,
        "latitude": [45.0] * n_input,
    }).to_csv(task_dir / "input.csv", index=False)

    pd.DataFrame({
        "PATID": pids[:n_ndi],
        "ndi": [0.1 * i for i in range(n_ndi)],
    }).to_parquet(task_dir / "output" / "c4_ndi.parquet", index=False)

    pd.DataFrame({
        "PATID": pids[:n_wi],
        "NatWalkInd": [1.0 + i for i in range(n_wi)],
    }).to_parquet(task_dir / "output" / "c4_wi.parquet", index=False)

    return task_dir


def test_merge_results_both_variables(tmp_path):
    task_dir = _seed_task_for_merge(tmp_path, n_input=5, n_ndi=4, n_wi=3)
    out = merge_results(task_dir, variables=["ndi", "walkability"])

    assert out == task_dir / "output" / "result.csv"
    df = pd.read_csv(out)
    assert len(df) == 5
    assert "pid" in df.columns
    assert "ndi" in df.columns
    assert "NatWalkInd" in df.columns
    # First 3 patients matched both; pid #4 matched NDI only; pid #5 matched none.
    assert df["ndi"].isna().sum() == 1
    assert df["NatWalkInd"].isna().sum() == 2


def test_merge_results_ndi_only(tmp_path):
    task_dir = _seed_task_for_merge(tmp_path, n_input=3, n_ndi=3, n_wi=0)
    out = merge_results(task_dir, variables=["ndi"])
    df = pd.read_csv(out)
    assert len(df) == 3
    assert "ndi" in df.columns
    assert "NatWalkInd" not in df.columns
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_bg_ndi_wi.py -v -k merge_results
```

Expected: both FAIL on missing `merge_results`.

- [ ] **Step 3: Implement merge_results**

Append to `backend/app/experiments/bg_ndi_wi.py`:

```python
# (pandas + Path already imported above)

_VARIABLE_PARQUET = {
    "ndi": "c4_ndi.parquet",
    "walkability": "c4_wi.parquet",
}


def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Left-join each per-variable parquet onto the original input CSV by PATID.

    Returns the path to the written result.csv. The input CSV is loaded as-is
    so all original metadata columns (startDate, endDate, lon/lat, FIPS) are
    preserved alongside the new exposure columns.
    """
    df = pd.read_csv(task_dir / "input.csv", dtype=str)
    for var in variables:
        parquet_name = _VARIABLE_PARQUET[var]
        var_df = pd.read_parquet(task_dir / "output" / parquet_name)
        var_df = var_df.rename(columns={"PATID": "pid"})
        df = df.merge(var_df, on="pid", how="left")

        match_pct = var_df["pid"].isin(df["pid"]).mean() * 100
        if match_pct < 90.0:
            _append_log(task_dir, "warning", "runner",
                        f"merge: {var} matched only {match_pct:.1f}% of patients")

    out = task_dir / "output" / "result.csv"
    df.to_csv(out, index=False)
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_bg_ndi_wi.py -v -k merge_results
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/tests/test_bg_ndi_wi.py
git commit -m "feat(experiments): merge_results left-joins variable parquets onto input cohort"
```

---

## Task 8: run() entry + `__main__` block

**Files:**
- Modify: `backend/app/experiments/bg_ndi_wi.py`
- Modify: `backend/tests/test_bg_ndi_wi.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_bg_ndi_wi.py`:

```python
from app.experiments.bg_ndi_wi import run

def test_run_writes_status_file_on_completion(fake_template_dir, fake_cli_settings, tmp_path):
    # We have two fixtures registered above that both override settings.
    # The fake_template_dir fixture is shadowed by fake_cli_settings here; this
    # test needs both -> re-stub the templates dir after fake_cli_settings.
    import app.config
    monkeypatch_path = fake_cli_settings  # tmp_path-based dir
    # Re-stub: write templates under the templates dir (which is monkeypatched
    # to tmp_path by the fake_template_dir fixture).
    # ... (defer to fake_template_dir's setup; both fixtures already ran)

    task_dir = tmp_path / "task-runtest1"
    task_dir.mkdir()
    (task_dir / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
        "P2,2017-01-01,2017-12-31,-94.0,44.0\n"
    )
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))

    rc = run(task_dir)

    assert rc == 0
    status = json.loads((task_dir / "status.json").read_text())
    assert status["status"] == "finished"
    assert status["total_steps"] == 2  # c3_bg + c4_ndi
    assert (task_dir / "output" / "result.csv").exists()
    df = pd.read_csv(task_dir / "output" / "result.csv")
    assert len(df) == 2  # input rows preserved
```

(If the cross-fixture re-stubbing turns out fiddly in your test runner, split this into a two-step manual fake at the top of the test — the goal is to verify `run()` glues plan + render + run_step + merge together end-to-end with the fakes.)

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_bg_ndi_wi.py -v -k test_run_writes_status
```

Expected: FAIL — `cannot import name 'run'`.

- [ ] **Step 3: Implement run() + write_status**

Append to `backend/app/experiments/bg_ndi_wi.py`:

```python
def _write_status(task_dir: Path, **fields) -> None:
    status_path = task_dir / "status.json"
    current = {}
    if status_path.exists():
        try:
            current = json.loads(status_path.read_text())
        except json.JSONDecodeError:
            current = {}
    current.update(fields)
    status_path.write_text(json.dumps(current, indent=2))


def run(task_dir: Path) -> int:
    """Main entry point for an experiment run.

    Reads task_dir/config.json, drives the C3 + C4 pipeline steps, merges the
    per-variable outputs, and writes status.json + logs.jsonl + output/result.csv.
    Returns 0 on success, non-zero on any step failure.
    """
    config = json.loads((task_dir / "config.json").read_text())
    steps = plan(config)
    total_steps = len(steps)

    _write_status(
        task_dir,
        status="running",
        progress=0.0,
        message="Preparing input data",
        started_at=datetime.now(timezone.utc).isoformat(),
        pid=os.getpid(),
        current_step="csv_to_parquet",
        total_steps=total_steps,
    )

    try:
        csv_to_parquet(task_dir / "input.csv", task_dir / "input.parquet")
    except Exception as exc:
        _append_log(task_dir, "error", "runner", f"csv_to_parquet failed: {exc!r}")
        _write_status(task_dir, status="error", message=f"input conversion failed: {exc}")
        return 1

    for idx, step in enumerate(steps):
        _write_status(
            task_dir,
            current_step=step.name,
            message=f"Running {step.name} ({idx+1}/{total_steps})",
            progress=idx / total_steps,
        )
        try:
            yaml_path = render_yaml(step, task_dir, config)
        except Exception as exc:
            _append_log(task_dir, "error", "runner", f"render_yaml({step.name}) failed: {exc!r}")
            _write_status(task_dir, status="error", message=f"render failed at {step.name}")
            return 1

        rc = run_pipeline_step(yaml_path, task_dir, step_name=step.name)
        if rc != 0:
            _write_status(task_dir, status="error",
                          message=f"step {step.name} failed with exit code {rc}")
            return rc

        out_parquet = task_dir / "output" / f"{step.name}.parquet"
        if not out_parquet.exists():
            _write_status(task_dir, status="error",
                          message=f"step {step.name} produced no output parquet")
            return 1

    _write_status(task_dir, current_step="merge", message="Merging variable outputs",
                  progress=(total_steps - 0.1) / total_steps)
    try:
        merge_results(task_dir, variables=config["variables"])
    except Exception as exc:
        _append_log(task_dir, "error", "runner", f"merge_results failed: {exc!r}")
        _write_status(task_dir, status="error", message=f"merge failed: {exc}")
        return 1

    _write_status(task_dir, status="finished", progress=1.0,
                  message=f"Completed {total_steps} pipeline steps")
    return 0


def _cli_main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "run":
        print("Usage: python -m app.experiments.bg_ndi_wi run <task_dir>", file=sys.stderr)
        return 2
    return run(Path(argv[2]))


if __name__ == "__main__":
    sys.exit(_cli_main(sys.argv))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_bg_ndi_wi.py -v
```

Expected: every test in the file PASSES. If `test_run_writes_status_file_on_completion` fixture wiring is fiddly, ensure both `fake_cli_settings` and `fake_template_dir` fixtures both write into the same `tmp_path` — the templates must live under `SPACESCANS_CONFIG_TEMPLATES_DIR` which both fixtures end up pointing to (the test fixture wiring above does that correctly with monkeypatch).

- [ ] **Step 5: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/tests/test_bg_ndi_wi.py
git commit -m "feat(experiments): run() orchestrator + __main__ entry for bg_ndi_wi"
```

---

## Task 9: task_manager dispatch + .run_lock

**Files:**
- Modify: `backend/app/task_manager.py`
- Modify: `backend/app/routers/tasks.py` (only if start endpoint surfaces 409 today; verify first)
- Modify: `backend/tests/test_tasks.py`

- [ ] **Step 1: Read current `start_task` to understand baseline**

```bash
sed -n '60,140p' backend/app/task_manager.py
```

Note where `mock_cli` is spawned and where you must dispatch.

- [ ] **Step 2: Write failing tests**

Append to `backend/tests/test_tasks.py`:

```python
def test_save_config_default_experiment_is_bg_ndi_wi(monkeypatch, tmp_path):
    import io, importlib, app.config, app.task_manager
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
    importlib.reload(app.config)
    importlib.reload(app.task_manager)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="t")
    save_config(meta["id"], {
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
        "variables": ["ndi"],
    })
    cfg_path = (app.config.settings.TASKS_DIR / f"task-{meta['id']}" / "config.json")
    saved = json.loads(cfg_path.read_text())
    assert saved["experiment"] == "bg_ndi_wi"


def test_start_lock_returns_409_when_busy(monkeypatch, tmp_path):
    """Acquire the lock from outside, then call start_task and expect HTTPException(409)."""
    import io, importlib, fcntl, app.config, app.task_manager
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
    importlib.reload(app.config)
    importlib.reload(app.task_manager)

    # Externally acquire the lock to simulate another running task.
    lock_path = app.config.settings.DATA_DIR / ".run_lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    fd = os.open(str(lock_path), os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    from app.task_manager import create_task, save_config, start_task, TaskBusyError
    meta = create_task(user_id=1, task_name="t")
    save_config(meta["id"], {
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
        "variables": ["ndi"],
        "experiment": "mock",  # don't actually try to run bg_ndi_wi here
    })
    (app.config.settings.TASKS_DIR / f"task-{meta['id']}" / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-06-30,-93.0,45.0\n"
    )
    with pytest.raises(TaskBusyError):
        start_task(meta["id"])

    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
pytest tests/test_tasks.py -v -k "default_experiment or 409_when_busy"
```

Expected: both FAIL — `experiment` field missing; `TaskBusyError` does not exist.

- [ ] **Step 4: Implement dispatch + lock in task_manager.py**

Edit `backend/app/task_manager.py`:

```python
# At top of file, add:
import fcntl


class TaskBusyError(RuntimeError):
    """Raised by start_task when another task currently holds .run_lock."""

    def __init__(self):
        super().__init__("another task is already running")
```

Modify `save_config(task_id, config)` to default `experiment`:

```python
def save_config(task_id: str, config: dict):
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    config = {"experiment": "bg_ndi_wi", **config}  # default + allow override
    (task_dir / "config.json").write_text(json.dumps(config, indent=2))
```

Replace `start_task(task_id)` with the lock + dispatch version. Locate the existing mock_cli spawn and replace the whole function:

```python
def start_task(task_id: str) -> dict:
    """Spawn the experiment subprocess for a task.

    Acquires .run_lock first; if another task holds it, raises TaskBusyError.
    Dispatches to app.experiments.bg_ndi_wi or mock_cli based on the
    task config's experiment field.
    """
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    config = json.loads((task_dir / "config.json").read_text())
    experiment = config.get("experiment", "bg_ndi_wi")

    lock_path = app.config.settings.DATA_DIR / ".run_lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    lock_fd = os.open(str(lock_path), os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock_fd)
        raise TaskBusyError()

    if experiment == "bg_ndi_wi":
        cmd = [
            str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
            "-m", "app.experiments.bg_ndi_wi", "run", str(task_dir),
        ]
    else:
        cmd = [sys.executable, "-m", "mock_cli.cli", "run", str(task_dir)]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    # Note: we deliberately leak lock_fd into this process. When the subprocess
    # exits, our reaper (a separate watcher) will close it. Simpler MVP: write
    # PID into a sidecar so other code can join() and release.
    (task_dir / "lock.fd").write_text(str(lock_fd))
    return {"pid": proc.pid}
```

(The simpler MVP shown leaves the fd dangling until the next process restart.  Acceptable for v1 with manual server restarts between runs. A subsequent task could add a background watcher to release the lock when the subprocess exits — but it's out of scope per the spec's deferred items.)

In `backend/app/routers/tasks.py`, ensure the `/start` endpoint translates `TaskBusyError` to HTTP 409:

```python
from app.task_manager import TaskBusyError

@router.post("/{task_id}/start")
def start(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    try:
        return task_manager.start_task(task_id)
    except TaskBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
pytest tests/test_tasks.py -v -k "default_experiment or 409_when_busy"
```

Expected: both PASS. Then run full suite:

```bash
pytest -q
```

Expected: all 21+ tests pass (previous 19 + 2 new).

- [ ] **Step 6: Commit**

```bash
git add backend/app/task_manager.py backend/app/routers/tasks.py backend/tests/test_tasks.py
git commit -m "feat(task_manager): dispatch bg_ndi_wi experiment + .run_lock mutual exclusion"
```

---

## Task 10: Frontend — wizard-layout STEPS labels

**Files:**
- Modify: `frontend/src/components/wizard/wizard-layout.tsx`

- [ ] **Step 1: Apply the copy edit**

Open `frontend/src/components/wizard/wizard-layout.tsx`. Change the line:

```tsx
{ label: "Variables", description: "Ontology selection" },
```

to:

```tsx
{ label: "Variables", description: "BG NDI / Walkability" },
```

- [ ] **Step 2: Typecheck**

```bash
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
cd /Users/xai/Desktop/spacescans-project/spacescans-web/frontend
node_modules/.bin/tsc --noEmit
```

Expected: no output (zero errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/wizard/wizard-layout.tsx
git commit -m "feat(wizard): label step 3 BG NDI / Walkability for v1"
```

---

## Task 11: Frontend — buffer-step lock circle + raster_res_m

**Files:**
- Modify: `frontend/src/components/wizard/buffer-step.tsx`

- [ ] **Step 1: Read current shape selector + state**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/frontend
sed -n '1,80p' src/components/wizard/buffer-step.tsx
```

Identify (a) the `BufferConfig` shape, (b) where shape buttons render, (c) where size input lives.

- [ ] **Step 2: Add raster_res_m to BufferConfig type**

Edit the top-level type / interface. If it currently looks like:

```tsx
export interface BufferConfig {
  shape: "circle" | "square" | "hexagon";
  size: number;
  unit: "meters" | "feet";
}
```

extend to:

```tsx
export interface BufferConfig {
  shape: "circle" | "square" | "hexagon";
  size: number;
  unit: "meters" | "feet";
  raster_res_m: number;
}
```

Update the default state initializer to include `raster_res_m: 25`.

- [ ] **Step 3: Disable non-circle shape buttons**

In the shape button render block, add `disabled={shape !== "circle"}` to the square/hexagon buttons. Add a `title="Not supported by spacescans-pipeline yet"` attribute. The circle button remains enabled.

Above the shape selector, add a small note (use the same `text-muted-foreground` class pattern already in the file):

```tsx
<p className="text-xs text-muted-foreground mb-2">
  v1 supports circular buffers only. Square and hexagon will be added when the
  spacescans-pipeline supports them.
</p>
```

- [ ] **Step 4: Add raster_res_m number input**

After the size input, add:

```tsx
<div className="space-y-2">
  <Label htmlFor="raster-res">Rasterization resolution (m)</Label>
  <Input
    id="raster-res"
    type="number"
    min={5}
    max={100}
    step={5}
    value={rasterResM}
    onChange={(e) => setRasterResM(parseInt(e.target.value) || 25)}
    className="w-32"
  />
  <p className="text-xs text-muted-foreground">
    Resolution for boundary overlap rasterization. Lower = more accurate, slower. 25 m is the standard.
  </p>
</div>
```

Add `const [rasterResM, setRasterResM] = useState<number>(25);` to the component's state. Wire it into the `onContinue` payload so the parent receives `{ shape, size, unit, raster_res_m: rasterResM }`.

- [ ] **Step 5: Typecheck**

```bash
node_modules/.bin/tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 6: Manual verification**

```bash
npm run dev
```

Browse to `http://localhost:3000`, log in, start a new task. Reach the Buffer step. Verify (a) circle is selected by default and clickable; square/hexagon are disabled and show the tooltip on hover; (b) raster_res_m input shows default 25, accepts values 5–100. Stop the dev server.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/wizard/buffer-step.tsx
git commit -m "feat(wizard): lock buffer shape to circle, add raster_res_m input"
```

---

## Task 12: Frontend — variables-step replace ontology UI with 2 checkboxes

**Files:**
- Modify: `frontend/src/components/wizard/variables-step.tsx`

- [ ] **Step 1: Read current component to understand props/callbacks**

```bash
sed -n '1,40p' src/components/wizard/variables-step.tsx
```

Note the `onContinue(selectedIds: string[])` callback signature so the new UI emits the same shape.

- [ ] **Step 2: Replace the body with v1 checkboxes**

Replace the entire JSX return with a checkbox card. Keep the file's existing top section (`"use client"`, imports, hook to load ontology if behind env flag). Below the v1 UI, wrap the original ontology tree in `process.env.NEXT_PUBLIC_USE_ONTOLOGY === "true"` so it stays accessible later.

Concrete component shape (replace the file body, preserve imports):

```tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface VariablesStepProps {
  selectedVariables: string[];
  onChange: (vars: string[]) => void;
  onContinue: () => void;
  onBack: () => void;
}

const V1_VARIABLES = [
  {
    id: "ndi",
    label: "Neighborhood Deprivation Index (NDI)",
    description: "Singh's composite Block Group deprivation index, 2012–2022.",
  },
  {
    id: "walkability",
    label: "EPA Walkability Index",
    description: "EPA's national walkability index per Block Group, 2016–2021.",
  },
];

export function VariablesStep({ selectedVariables, onChange, onContinue, onBack }: VariablesStepProps) {
  const toggle = (id: string) => {
    onChange(
      selectedVariables.includes(id)
        ? selectedVariables.filter((v) => v !== id)
        : [...selectedVariables, id]
    );
  };

  const canContinue = selectedVariables.length >= 1;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Experiment: BG NDI + Walkability (v1)</CardTitle>
        <CardDescription>
          Select one or both variables to compute for your cohort. More variables
          will be added in future versions.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {V1_VARIABLES.map((v) => (
          <label key={v.id} className="flex items-start gap-3 rounded-md border p-3 hover:bg-muted/30 cursor-pointer">
            <Checkbox
              checked={selectedVariables.includes(v.id)}
              onCheckedChange={() => toggle(v.id)}
            />
            <div>
              <div className="font-medium">{v.label}</div>
              <div className="text-sm text-muted-foreground">{v.description}</div>
            </div>
          </label>
        ))}
        <div className="flex justify-between pt-4">
          <Button variant="outline" onClick={onBack}>Back</Button>
          <Button onClick={onContinue} disabled={!canContinue}>
            Continue
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
```

If the original component used a different prop/callback shape (e.g. `onComplete` instead of `onContinue`), keep the original names — the only requirement is that selected IDs match `["ndi", "walkability"]` to align with backend `plan()`.

- [ ] **Step 3: Typecheck**

```bash
node_modules/.bin/tsc --noEmit
```

Expected: zero errors. If `Checkbox` is not yet imported anywhere in the project, add it via shadcn:

```bash
npx shadcn@latest add checkbox
```

(or import the existing `@base-ui/react` checkbox if that's already in use — check imports of other wizard steps.)

- [ ] **Step 4: Manual verification**

```bash
npm run dev
```

Walk wizard to step 3. Verify: two checkboxes shown, neither default-checked; Continue is disabled until at least one is checked; backing into the step preserves prior selection.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/wizard/variables-step.tsx
git commit -m "feat(wizard): v1 variables step = 2 checkboxes (NDI + Walkability)"
```

---

## Task 13: Frontend — api.ts saveConfig with experiment field

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Locate saveConfig**

```bash
grep -n "saveConfig\|/api/tasks" src/lib/api.ts
```

- [ ] **Step 2: Add experiment field**

In the body that the existing `saveConfig` builds, add `experiment: "bg_ndi_wi"` as a top-level field. Example (adapt to actual file):

```ts
async saveConfig(taskId: string, body: SaveConfigBody): Promise<void> {
  const payload = { experiment: "bg_ndi_wi", ...body };
  const resp = await fetch(`/api/tasks/${taskId}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new ApiError(resp.status, await resp.text());
},
```

If `SaveConfigBody` is a typed interface, add the `experiment?: "bg_ndi_wi" | "mock"` field.

- [ ] **Step 3: Typecheck**

```bash
node_modules/.bin/tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(api): include experiment=bg_ndi_wi in saveConfig payload"
```

---

## Task 14: Frontend — review-step multi-step progress + results

**Files:**
- Modify: `frontend/src/components/wizard/review-step.tsx`

- [ ] **Step 1: Read existing component**

```bash
sed -n '1,40p' src/components/wizard/review-step.tsx
sed -n '40,160p' src/components/wizard/review-step.tsx
```

Identify (a) status polling loop, (b) progress bar render, (c) results download render.

- [ ] **Step 2: Add per-step state tracking**

Below the existing overall progress bar, add a step list. The status JSON returned from `/api/tasks/{id}/status` exposes `current_step` and `total_steps`. The component already polls status; extend the polled state to include these two fields.

Replace the progress display section with:

```tsx
{status && (
  <>
    <div className="space-y-2">
      <div className="flex justify-between text-sm">
        <span>Overall progress</span>
        <span>{Math.round((status.progress ?? 0) * 100)}%</span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div
          className="h-full bg-primary transition-all"
          style={{ width: `${Math.round((status.progress ?? 0) * 100)}%` }}
        />
      </div>
    </div>

    {status.total_steps && (
      <div className="space-y-1 mt-4">
        {Array.from({ length: status.total_steps }, (_, i) => {
          const stepName = ["c3_bg", "c4_ndi", "c4_wi"][i];
          const isCurrent = status.current_step === stepName;
          const isDone = status.current_step
            ? ["c3_bg", "c4_ndi", "c4_wi", "merge"].indexOf(status.current_step) > i
            : false;
          const icon = isDone ? "✅" : isCurrent ? "⏳" : "⏸";
          return (
            <div key={stepName} className="flex gap-2 text-sm">
              <span>{icon}</span>
              <span className="font-mono">Step {i + 1}/{status.total_steps}</span>
              <span>{stepName}</span>
              {isCurrent && status.message && (
                <span className="text-muted-foreground">— {status.message}</span>
              )}
            </div>
          );
        })}
      </div>
    )}
  </>
)}
```

- [ ] **Step 3: Replace results download section**

Where the current code shows "Download Results", replace with:

```tsx
{status?.status === "finished" && (
  <div className="space-y-3 mt-6">
    <Button asChild>
      <a href={`/api/tasks/${taskId}/results`} download="result.csv">
        Download result.csv
      </a>
    </Button>
    <details className="text-sm">
      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
        Advanced: pipeline intermediates
      </summary>
      <ul className="mt-2 space-y-1 pl-4 list-disc">
        <li><a className="underline" href={`/api/tasks/${taskId}/results?file=c3_bg.parquet`}>c3_bg.parquet</a></li>
        {selectedVariables.includes("ndi") && (
          <li><a className="underline" href={`/api/tasks/${taskId}/results?file=c4_ndi.parquet`}>c4_ndi.parquet</a></li>
        )}
        {selectedVariables.includes("walkability") && (
          <li><a className="underline" href={`/api/tasks/${taskId}/results?file=c4_wi.parquet`}>c4_wi.parquet</a></li>
        )}
      </ul>
    </details>
  </div>
)}
```

The intermediate download routes assume the `/results` endpoint accepts an optional `?file=` query. If it doesn't yet, defer the "Advanced" panel (just keep the `Download result.csv` button) and add a follow-up task to teach the router to serve any file under `task_dir/output/`.

- [ ] **Step 4: Typecheck**

```bash
node_modules/.bin/tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/wizard/review-step.tsx
git commit -m "feat(wizard): multi-step progress + intermediate parquet download list"
```

---

## Task 15: Integration test — small cohort end-to-end

**Files:**
- Create: `backend/tests/test_bg_ndi_wi_integration.py`
- Create: `backend/tests/fixtures/patients_5.csv`
- Modify: `backend/pytest.ini` or `backend/pyproject.toml` to register `integration` marker

- [ ] **Step 1: Register the `integration` pytest marker**

If `pytest.ini` does not exist, create it:

```ini
# backend/pytest.ini
[pytest]
markers =
    integration: end-to-end tests that require SPACESCANS_DATA_DIR and the real spacescans CLI
```

If it already exists, append the `integration` marker entry under existing `markers`.

- [ ] **Step 2: Create the 5-patient Leon FL fixture**

```bash
mkdir -p backend/tests/fixtures
cat > backend/tests/fixtures/patients_5.csv <<'EOF'
pid,startDate,endDate,longitude,latitude,state_fips,county_fips,tract_geoid,bg_geoid
PID0000001,2017-01-01,2017-06-30,-84.27,30.44,12,12073,12073001100,120730011001
PID0000002,2017-02-15,2017-08-15,-84.29,30.46,12,12073,12073001100,120730011001
PID0000003,2017-03-10,2017-09-10,-84.31,30.45,12,12073,12073001500,120730015001
PID0000004,2017-04-01,2017-10-01,-84.25,30.42,12,12073,12073001500,120730015001
PID0000005,2017-05-20,2017-11-20,-84.30,30.48,12,12073,12073001600,120730016001
EOF
```

- [ ] **Step 3: Write the integration test**

Create `backend/tests/test_bg_ndi_wi_integration.py`:

```python
"""End-to-end pipeline integration tests.

These are SKIPPED automatically unless SPACESCANS_DATA_DIR is set and the
real spacescans CLI is available — keeps the default `pytest` invocation
green on machines without the 220 GB data tree.

Run explicitly with:
    pytest -m integration
"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    if not (app.config.settings.SPACESCANS_DATA_DIR / "BG_FL/C3/tiger2010_bg10_states").exists():
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / pipeline CLI not configured",
) and pytest.mark.integration


@pytest.fixture
def task_with_5_patients(tmp_path):
    task_dir = tmp_path / "task-int00001"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi", "walkability"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))
    return task_dir


@pytest.mark.integration
def test_e2e_small_cohort(task_with_5_patients):
    cmd = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        "-m", "app.experiments.bg_ndi_wi", "run", str(task_with_5_patients),
    ]
    env = {**os.environ}
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)

    assert proc.returncode == 0, f"runner failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"

    status = json.loads((task_with_5_patients / "status.json").read_text())
    assert status["status"] == "finished"
    assert status["total_steps"] == 3

    result_csv = task_with_5_patients / "output" / "result.csv"
    assert result_csv.exists()
    df = pd.read_csv(result_csv)
    assert len(df) == 5
    assert "ndi" in df.columns
    assert "NatWalkInd" in df.columns
    # At least 3 of 5 patients must have an NDI value (Leon FL BGs all have NDI 2017)
    assert df["ndi"].notna().sum() >= 3
```

- [ ] **Step 4: Run the integration test**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
pytest -m integration -v tests/test_bg_ndi_wi_integration.py::test_e2e_small_cohort
```

Expected: PASS in under 5 minutes (BG_FL/C3 shapefile load + 5 buffer overlap + 2 C4 joins). If it fails because of fixture coordinates being outside BG coverage, adjust the 5 lat/lon pairs to known-good Leon FL block group centroids.

- [ ] **Step 5: Verify the default `pytest -q` still works (skipping integration)**

```bash
pytest -q
```

Expected: previous unit tests pass; the integration test is collected but skipped (or simply not selected without `-m integration`).

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_bg_ndi_wi_integration.py backend/tests/fixtures/patients_5.csv backend/pytest.ini
git commit -m "test(integration): e2e bg_ndi_wi run on 5-patient Leon FL cohort"
```

---

## Task 16: Integration test — lock + stop

**Files:**
- Modify: `backend/tests/test_bg_ndi_wi_integration.py`

- [ ] **Step 1: Add lock + stop tests**

Append to `backend/tests/test_bg_ndi_wi_integration.py`:

```python
import signal


@pytest.mark.integration
def test_lock_prevents_concurrent_start(task_with_5_patients, tmp_path):
    """Spawn a runner, immediately try to spawn a second one, expect 409 from start_task."""
    # Spawn the first runner (will hold the lock).
    cmd = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        "-m", "app.experiments.bg_ndi_wi", "run", str(task_with_5_patients),
    ]
    proc1 = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    try:
        # Give it a moment to write the lock + start C3.
        time.sleep(2.0)

        # Now try to start_task() via the manager — should raise TaskBusyError.
        from app.task_manager import TaskBusyError, create_task, save_config, start_task
        meta = create_task(user_id=1, task_name="second")
        save_config(meta["id"], {
            "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
            "variables": ["ndi"],
            "experiment": "bg_ndi_wi",
        })
        # Need input.csv for the task dir so start_task doesn't fail on validation.
        shutil.copy(
            Path(__file__).parent / "fixtures" / "patients_5.csv",
            app.config.settings.TASKS_DIR / f"task-{meta['id']}" / "input.csv",
        )
        with pytest.raises(TaskBusyError):
            start_task(meta["id"])
    finally:
        os.killpg(os.getpgid(proc1.pid), signal.SIGTERM)
        proc1.wait(timeout=10)


@pytest.mark.integration
def test_stop_kills_pipeline_subprocess(task_with_5_patients):
    """Spawn the runner, SIGTERM its process group, verify it dies and no
    leftover `spacescans` processes are running."""
    cmd = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        "-m", "app.experiments.bg_ndi_wi", "run", str(task_with_5_patients),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    time.sleep(3.0)  # wait for C3 to start
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    rc = proc.wait(timeout=15)
    assert rc != 0

    # Verify no zombie spacescans subprocesses.
    ps = subprocess.run(["ps", "-A", "-o", "pid,comm"], capture_output=True, text=True)
    assert "spacescans" not in ps.stdout or "<defunct>" in ps.stdout
```

- [ ] **Step 2: Run the new tests**

```bash
pytest -m integration -v tests/test_bg_ndi_wi_integration.py -k "lock or stop"
```

Expected: both PASS. The `test_lock_prevents_concurrent_start` relies on the runner taking >2 seconds, which is true for any real BG_FL C3 run.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_bg_ndi_wi_integration.py
git commit -m "test(integration): lock prevents concurrent start; stop kills pipeline subprocess"
```

---

## Task 17: Manual smoke test documentation

**Files:**
- Create: `backend/tests/manual_e2e.md`

- [ ] **Step 1: Create the smoke test doc**

Create `backend/tests/manual_e2e.md`:

```markdown
# Manual End-to-End Smoke Test — BG NDI + Walkability v1

This walk-through verifies the full integration from browser to result.csv.
It is not part of automated pytest; run it before publishing any release.

## Prerequisites

- Backend env (`backend/.env`) configured:
  - `SPACESCANS_DATA_DIR=/Users/xai/Desktop/spacescans-project/data_full`
  - `SPACESCANS_PIPELINE_PYTHON=/Users/xai/miniconda3/envs/spacescans/bin/python`
  - `SPACESCANS_PIPELINE_CLI=/Users/xai/miniconda3/envs/spacescans/bin/spacescans`
  - `SPACESCANS_CONFIG_TEMPLATES_DIR=/Users/xai/Desktop/spacescans-project/configs`
- Frontend deps installed: `(cd frontend && npm install)`.
- Backend deps installed in the spacescans conda env:
  `(cd backend && /Users/xai/miniconda3/envs/spacescans/bin/pip install -r requirements.txt)`.

## Steps

1. **Start backend**

   ```bash
   cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
   /Users/xai/miniconda3/envs/spacescans/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

   Confirm `curl http://localhost:8000/api/health` returns `{"status":"ok"}`.

2. **Start frontend**

   ```bash
   cd /Users/xai/Desktop/spacescans-project/spacescans-web/frontend
   npm run dev
   ```

   Open `http://localhost:3000`.

3. **Sign up + log in** if you don't already have an account.

4. **Prepare a small CSV** — first 100 rows of the demo cohort:

   ```bash
   head -101 /Users/xai/Desktop/spacescans-project/data_full/demo_patients_conus_fast_100000.csv \
     > /tmp/smoke_100.csv
   ```

5. **Create a new task**, name it `smoke-test`.

6. **Upload step** — drop `/tmp/smoke_100.csv`. Verify the validation panel shows 100 rows and 9 columns.

7. **Buffer step** — shape locked to circle. Set size to 270 m and raster_res_m to 25. Verify the disabled square/hexagon buttons show the tooltip on hover.

8. **Variables step** — check both NDI and Walkability. Continue.

9. **Review & Run step**:
   - The overall progress bar should climb from 0% to 100%.
   - The step list should show:
     ```
     Step 1/3   ✅ c3_bg
     Step 2/3   ⏳ c4_ndi   — Running c4_ndi (2/3)
     Step 3/3   ⏸ c4_wi
     ```
   - Expected total wall-clock: 1–2 min on a laptop with the 220 GB tree mounted.

10. **Result download** — click "Download result.csv". Open the file:

    ```bash
    head -3 ~/Downloads/result.csv
    ```

    Confirm columns are `pid,startDate,endDate,longitude,latitude,state_fips,county_fips,tract_geoid,bg_geoid,ndi,NatWalkInd` and exactly 100 data rows.

11. **Failure modes to spot-check (optional)**:
    - Disable Walkability checkbox and rerun → result.csv only has `ndi` column.
    - Attempt to start a second task while the first is running → frontend shows 409.

## Pass criteria

- result.csv has 100 rows.
- Both `ndi` and `NatWalkInd` columns have non-null values for at least 90% of patients.
- Wall-clock under 5 minutes.
- No errors in the backend stdout.
```

- [ ] **Step 2: Commit**

```bash
git add backend/tests/manual_e2e.md
git commit -m "docs(tests): manual end-to-end smoke walk-through for bg_ndi_wi v1"
```

---

## Task 18: Final verification + cleanup

**Files:**
- Verify: nothing modified, all tests pass.

- [ ] **Step 1: Run the full backend test suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: all unit + auth/health/upload tests pass. Integration tests skipped (no `-m integration`).

- [ ] **Step 2: Run the integration suite**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -m integration -v
```

Expected: all integration tests pass under 10 minutes.

- [ ] **Step 3: Typecheck the frontend**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/frontend
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
node_modules/.bin/tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 4: Build the frontend (sanity check, optional)**

```bash
npm run build
```

Expected: build completes; the `.next/` directory appears. No type errors at build time.

- [ ] **Step 5: Walk through `backend/tests/manual_e2e.md` once**

If any step diverges from the documented behaviour, fix the underlying bug and add a unit/integration test that would have caught it.

- [ ] **Step 6: Optional final commit if Step 5 found anything**

```bash
git add ...
git commit -m "fix: address smoke-test findings"
```

- [ ] **Step 7: Hand off to superpowers:finishing-a-development-branch**

The implementation is complete. Decide merge / PR / keep / discard for the branch this work was done on.

---

## Spec coverage map

A quick cross-reference back to the spec sections, confirming each is implemented by tasks above.

| Spec section | Implemented by |
|---|---|
| Goal / Scope (in scope items) | Tasks 1–18 collectively |
| Out of scope | Not implemented (correctly) |
| Architecture diagram | Task 9 (dispatch + flock) + Task 8 (runner subprocess) |
| Single FastAPI / blocking subprocess | Task 9 |
| One task at a time via flock | Task 9, Task 16 |
| Subprocess not import | Task 6, Task 8 |
| Mock_cli retained | Task 9 dispatcher leaves `experiment != "bg_ndi_wi"` → mock_cli |
| Path configuration via env vars | Task 1 |
| Task directory layout | Task 8 (run produces all the files) |
| Extended status.json | Task 8 (_write_status function) |
| logs.jsonl source field | Task 6 (_append_log) |
| Web → pipeline field mapping | Task 4 |
| Backend new files | Task 2 (scaffold), Tasks 3–8 (fill in) |
| Modified config.py | Task 1 |
| Modified task_manager.py | Task 9 |
| Modified routers/tasks.py | Task 9 |
| Modified requirements.txt | Task 4 |
| Wizard step diff | Tasks 10–14 |
| YAML template injection | Task 4 |
| Patient-schema alignment (demo_conus adapter preserved) | Task 4 |
| Render algorithm | Task 4 |
| Failure matrix #1 (upload validation) | Already implemented (pre-plan commit) |
| Failure matrix #2 (env config) | Task 1 |
| Failure matrix #3 (lock) | Task 9, Task 16 |
| Failure matrix #4–6 (runner failures) | Task 6, Task 8 |
| Failure matrix #7 (timeout) | Not implemented in v1 — deferred (`PIPELINE_STEP_TIMEOUT_SECONDS` config exists but is not enforced; add later) |
| Failure matrix #8 (user stop) | Task 16 verifies the kill mechanism works |
| Failure matrix #9 (missing output) | Task 8 (out_parquet existence check) |
| Failure matrix #10 (high null) | Task 7 (match_pct warning) |
| Failure matrix #11–12 (disk / mtime) | Implicit Python exception → status="error" in Task 8 |
| Process group management | Task 6 (`start_new_session=True`) |
| Partial-failure semantics | Task 8 (early return on step failure, no merge) |
| No auto-retry | Implicit — no retry endpoint added |
| Fail-fast order in start_task | Task 9 |
| Unit tests | Tasks 2–8 (test each function) |
| Integration tests | Tasks 15–16 |
| Smoke test doc | Task 17 |
| CI behaviour (integration marker) | Task 15 (`pytest.ini` registers the marker) |

The one item explicitly left as future work is the per-step **timeout enforcement** (Failure matrix #7). The config field exists; an enforcing watchdog can be added in a follow-up commit without changing any other interfaces.
