"""Sprint 11 e2e: single-experiment fara_tract via task_manager.start_task.

Proves the runtime path Phase A unlocked: fara_linkage's
output_grouping='episode' branch fires, the pipeline emits one row per
(PATID, geoid), _merge.write_partial joins on (pid, episode_id), and
result_fara_tract.csv carries the four headline FARA value columns
one-to-one with the input cohort.

Tract boundary is the first non-BG/non-ZCTA5 slot in the catalog — this
test also indirectly proves the frontend BOUNDARY_ORDER includes 'Tract'
and the merge / coverage stack handles a Tract-boundary experiment.
"""
import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config


_HEADLINE_COLUMNS = ["LILATracts_1And10", "LATracts1", "HUNVFlag", "LowIncomeTracts"]


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    # FARA C4 panel
    fara_c4 = app.config.settings.SPACESCANS_DATA_DIR / "data_full" / "FARA" / "C4"
    if not (fara_c4 / "fara_nationwide_2010_2019_interpolated.Rda").exists():
        return False
    if not (fara_c4 / "varnameCountRemoved.csv").exists():
        return False
    # Tract C3 shapefile set (at least one state — boundary_overlap_fast
    # pulls the full set, but checking one is enough for the gate).
    tract_c3 = app.config.settings.SPACESCANS_DATA_DIR / "data_full" / "TRACT" / "C3"
    if not tract_c3.is_dir():
        return False
    if not any(tract_c3.glob("tl_2010_*_tract10")):
        return False
    try:
        import pyreadr  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / FARA C4 / Tract C3 / pipeline CLI / pyreadr not configured",
)


@pytest.fixture
def task_with_fara_tract_cohort(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-fara-tract")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["fara_tract"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_fara_tract_cohort(task_with_fara_tract_cohort):
    task_id, task_dir = task_with_fara_tract_cohort

    from app.task_manager import start_task
    start_task(task_id)

    # Tract C3 rasterizes the full CONUS tract shapefile set — slower than
    # BG / ZCTA5 — so we give the integration test a generous timeout.
    status = {}
    deadline = time.monotonic() + 600.0
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(2.0)
    else:
        pytest.fail(f"task did not terminate within 600s; last status={status}")

    assert status["status"] == "finished", f"unexpected terminal status: {status}"

    experiments = status.get("experiments", {})
    assert "fara_tract" in experiments, (
        f"expected fara_tract slot in status.experiments; got {list(experiments)}"
    )
    assert experiments["fara_tract"]["status"] == "finished"
    assert experiments["fara_tract"]["progress"] == 1.0

    logs_path = task_dir / "logs.jsonl"
    assert logs_path.exists(), "logs.jsonl must be written"
    log_lines = [json.loads(line) for line in logs_path.read_text().splitlines() if line.strip()]
    log_steps = {entry.get("source") for entry in log_lines if entry.get("source")}
    assert "c3_tract_us" in log_steps, f"expected c3_tract_us in logs; got {log_steps}"
    assert "c4_tract_fara" in log_steps, f"expected c4_tract_fara in logs; got {log_steps}"

    result_partial = task_dir / "output" / "result_fara_tract.csv"
    assert result_partial.exists(), "result_fara_tract.csv must be written"
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
    missing = [c for c in _HEADLINE_COLUMNS if c not in df.columns]
    assert not missing, f"missing FARA value cols: {missing}; got {list(df.columns)}"
