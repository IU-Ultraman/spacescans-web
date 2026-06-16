"""Sprint 7 e2e: single-experiment nhd_bluespace via task_manager.start_task.

Proves the runtime path Phase A unlocked: precomputed_static_linkage's
output_grouping='episode' branch fires (resolve_output_grouping dispatch),
the pipeline emits one row per (PATID, geoid), _merge.write_partial joins on
(pid, episode_id), and result_nhd_bluespace.csv carries the five dist_*_m
value columns one-to-one with the input cohort.
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


@pytest.mark.integration
def test_e2e_nhd_bluespace_cohort(task_with_nhd_bluespace_cohort):
    task_id, task_dir = task_with_nhd_bluespace_cohort

    from app.task_manager import start_task
    start_task(task_id)

    status = {}
    deadline = time.monotonic() + 240.0
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 240s; last status={status}")

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
    log_steps = {entry.get("source") for entry in log_lines if entry.get("source")}
    assert "c3_nhd_bluespace" in log_steps, (
        f"expected c3_nhd_bluespace in logs; got {log_steps}"
    )
    assert "c4_nhd_bluespace" in log_steps, (
        f"expected c4_nhd_bluespace in logs; got {log_steps}"
    )

    result_partial = task_dir / "output" / "result_nhd_bluespace.csv"
    assert result_partial.exists(), "result_nhd_bluespace.csv must be written"
    result_csv = task_dir / "output" / "result.csv"
    assert result_csv.exists(), "fan-in result.csv must be written"

    input_df = pd.read_csv(task_dir / "input.csv")
    df = pd.read_csv(result_csv)

    assert len(df) == len(input_df), (
        f"row count must match cohort episodes; "
        f"input={len(input_df)} result={len(df)} "
        "(if mismatched, the (pid, episode_id) join collapsed — "
        "Phase A precomputed_static output_grouping=episode dispatch likely failed)"
    )
    missing = [c for c in _DIST_COLUMNS if c not in df.columns]
    assert not missing, f"missing dist_*_m columns: {missing}; got {list(df.columns)}"
