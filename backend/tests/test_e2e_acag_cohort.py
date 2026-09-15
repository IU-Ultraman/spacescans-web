"""e2e: single-experiment acag via task_manager.start_task.

Proves the whole path: grid_weights over the north-up ACAG template with
grid_id_offset=1, acag_multi walking the 16 species directories with the
reader's north-up flip, output_grouping=episode keeping (PATID, geoid),
_merge.write_partial joining on (pid, episode_id), and result.csv carrying
all 24 value columns one-to-one with the input cohort.
"""
import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config


_ACAG_COLUMNS = ['pm25', 'bc', 'dust', 'nh4', 'no3', 'om', 'so4', 'ss', 'pm25_bm', 'bc_bm', 'dust_bm', 'nh4_bm', 'no3_bm', 'om_bm', 'so4_bm', 'ss_bm', 'pm25_nbm', 'bc_nbm', 'dust_nbm', 'nh4_nbm', 'no3_nbm', 'om_nbm', 'so4_nbm', 'ss_nbm']


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    root = app.config.settings.SPACESCANS_DATA_DIR / "ACAG"
    if not (root / "C3" / "acag_template.tif").exists():
        return False
    if not any((root / "C4" / "xNorthAmerica" / "PM25" / "BiWeekly").glob("*.nc")):
        return False
    try:
        import rasterio  # noqa: F401
        import xarray  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / ACAG template + PM25 NetCDFs / pipeline CLI / rasterio+xarray not configured",
)


@pytest.fixture
def task_with_acag_cohort(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-acag")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["acag"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_acag_cohort(task_with_acag_cohort):
    task_id, task_dir = task_with_acag_cohort

    from app.task_manager import start_task
    start_task(task_id)

    status = {}
    deadline = time.monotonic() + 1800.0  # 16 species × 182 biweekly NetCDFs
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 1200s; last status={status}")

    assert status["status"] == "finished", f"unexpected terminal status: {status}"

    experiments = status.get("experiments", {})
    assert "acag" in experiments, (
        f"expected acag slot in status.experiments; got {list(experiments)}"
    )
    assert experiments["acag"]["status"] == "finished"
    assert experiments["acag"]["progress"] == 1.0

    logs_path = task_dir / "logs.jsonl"
    assert logs_path.exists(), "logs.jsonl must be written"
    log_lines = [json.loads(line) for line in logs_path.read_text().splitlines() if line.strip()]
    log_steps = {entry.get("source") for entry in log_lines if entry.get("source")}
    assert "c3_acag" in log_steps, (
        f"expected c3_acag in logs; got {log_steps}"
    )
    assert "c4_acag" in log_steps, (
        f"expected c4_acag in logs; got {log_steps}"
    )

    result_partial = task_dir / "output" / "result_acag.csv"
    assert result_partial.exists(), "result_acag.csv must be written"
    result_csv = task_dir / "output" / "result.csv"
    assert result_csv.exists(), "fan-in result.csv must be written"

    input_df = pd.read_csv(task_dir / "input.csv")
    df = pd.read_csv(result_csv)

    assert len(df) == len(input_df), (
        f"row count must match cohort episodes; "
        f"input={len(input_df)} result={len(df)} "
        "(if mismatched, the (pid, episode_id) join collapsed — "
        "acag_multi output_grouping=episode dispatch likely failed)"
    )
    # result.csv is a left join onto the cohort, so its row count and its
    # column names prove nothing about the linkage — an empty partial still
    # yields a full-length table of NaNs. The partial CSV is the evidence.
    partial = pd.read_csv(result_partial)
    assert len(partial) == len(input_df), (
        f"result_acag.csv has {len(partial)} rows for {len(input_df)} cohort rows — "
        "the C4 step produced fewer episodes than the cohort has (empty join?)"
    )
    for c in _ACAG_COLUMNS:
        filled = partial[c].notna().mean() if c in partial.columns else 0.0
        assert filled >= 0.9, (
            f"{c}: only {filled:.0%} of cohort rows carry a value in result_acag.csv"
        )
    missing = [c for c in _ACAG_COLUMNS if c not in df.columns]
    assert not missing, f"missing ACAG columns: {missing}; got {list(df.columns)}"
