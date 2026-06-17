"""Sprint 10 e2e: single-experiment temis via task_manager.start_task.

Proves the runtime path Sprint 10 A1 unlocked: gridded_linkage's
output_grouping='episode' branch fires (resolve_output_grouping dispatch),
the pipeline emits one row per (PATID, geoid), _merge.write_partial joins
on (pid, episode_id), and result_temis.csv carries the four uv* value
columns one-to-one with the input cohort.
"""
import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config


_TEMIS_COLUMNS = ["uvddc", "uvdec", "uvdvc", "uvief"]


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    temis_raw = (
        app.config.settings.SPACESCANS_DATA_DIR
        / "data_full" / "TEMIS" / "C4" / "raw"
    )
    if not temis_raw.is_dir():
        return False
    # require at least one UV-var subdir present
    if not any((temis_raw / sub).is_dir()
               for sub in ("uvddc", "uvdec", "uvdvc", "uvief")):
        return False
    try:
        import rasterio  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / TEMIS C4 raw subdirs / pipeline CLI / rasterio not configured",
)


@pytest.fixture
def task_with_temis_cohort(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-temis")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["temis"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_temis_cohort(task_with_temis_cohort):
    task_id, task_dir = task_with_temis_cohort

    from app.task_manager import start_task
    start_task(task_id)

    status = {}
    deadline = time.monotonic() + 1200.0  # daily HDFs over 7 yrs is slow
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 1200s; last status={status}")

    assert status["status"] == "finished", f"unexpected terminal status: {status}"

    experiments = status.get("experiments", {})
    assert "temis" in experiments, (
        f"expected temis slot in status.experiments; got {list(experiments)}"
    )
    assert experiments["temis"]["status"] == "finished"
    assert experiments["temis"]["progress"] == 1.0

    logs_path = task_dir / "logs.jsonl"
    assert logs_path.exists(), "logs.jsonl must be written"
    log_lines = [json.loads(line) for line in logs_path.read_text().splitlines() if line.strip()]
    log_steps = {entry.get("source") for entry in log_lines if entry.get("source")}
    assert "c3_temis" in log_steps, (
        f"expected c3_temis in logs; got {log_steps}"
    )
    assert "c4_temis" in log_steps, (
        f"expected c4_temis in logs; got {log_steps}"
    )

    result_partial = task_dir / "output" / "result_temis.csv"
    assert result_partial.exists(), "result_temis.csv must be written"
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
    missing = [c for c in _TEMIS_COLUMNS if c not in df.columns]
    assert not missing, f"missing TEMIS uv* columns: {missing}; got {list(df.columns)}"
