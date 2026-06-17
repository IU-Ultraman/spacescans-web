"""Sprint 10 e2e: single-experiment vnl via task_manager.start_task.

Proves the runtime path Sprint 10 A1 unlocked: gridded_linkage's
output_grouping='episode' branch fires (resolve_output_grouping dispatch),
the pipeline emits one row per (PATID, geoid), _merge.write_partial joins
on (pid, episode_id), and result_vnl.csv carries the 'value' column
one-to-one with the input cohort.
"""
import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config


_VNL_COLUMNS = ["value"]


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    vnl_c3 = app.config.settings.SPACESCANS_DATA_DIR / "data_full" / "VNL" / "C3"
    if not vnl_c3.is_dir():
        return False
    if not list(vnl_c3.glob("VNL_v21_*.tif")):
        return False
    try:
        import rasterio  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / VNL C3 TIFs / pipeline CLI / rasterio not configured",
)


@pytest.fixture
def task_with_vnl_cohort(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-vnl")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["vnl"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_vnl_cohort(task_with_vnl_cohort):
    task_id, task_dir = task_with_vnl_cohort

    from app.task_manager import start_task
    start_task(task_id)

    status = {}
    deadline = time.monotonic() + 600.0  # gridded can take longer than static
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 600s; last status={status}")

    assert status["status"] == "finished", f"unexpected terminal status: {status}"

    experiments = status.get("experiments", {})
    assert "vnl" in experiments, (
        f"expected vnl slot in status.experiments; got {list(experiments)}"
    )
    assert experiments["vnl"]["status"] == "finished"
    assert experiments["vnl"]["progress"] == 1.0

    logs_path = task_dir / "logs.jsonl"
    assert logs_path.exists(), "logs.jsonl must be written"
    log_lines = [json.loads(line) for line in logs_path.read_text().splitlines() if line.strip()]
    log_steps = {entry.get("source") for entry in log_lines if entry.get("source")}
    assert "c3_vnl" in log_steps, (
        f"expected c3_vnl in logs; got {log_steps}"
    )
    assert "c4_vnl" in log_steps, (
        f"expected c4_vnl in logs; got {log_steps}"
    )

    result_partial = task_dir / "output" / "result_vnl.csv"
    assert result_partial.exists(), "result_vnl.csv must be written"
    result_csv = task_dir / "output" / "result.csv"
    assert result_csv.exists(), "fan-in result.csv must be written"

    input_df = pd.read_csv(task_dir / "input.csv")
    df = pd.read_csv(result_csv)

    assert len(df) == len(input_df), (
        f"row count must match cohort episodes; "
        f"input={len(input_df)} result={len(df)} "
        "(if mismatched, the (pid, episode_id) join collapsed — "
        "Sprint 10 A1 gridded output_grouping=episode dispatch likely failed)"
    )
    missing = [c for c in _VNL_COLUMNS if c not in df.columns]
    assert not missing, f"missing VNL value columns: {missing}; got {list(df.columns)}"
