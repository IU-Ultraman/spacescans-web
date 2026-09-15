"""e2e: single-experiment faqsd via task_manager.start_task.

Proves the whole path: the shared TRACT C3 rasterization (cache namespace
TRACT_FARA), faqsd_daily_areal reading the per-task parquet weights and
EPA's daily text files, output_grouping=episode keeping (PATID, geoid), the
web-side o3/pm25 -> faqsd_o3/faqsd_pm25 rename, and result.csv carrying
both columns one-to-one with the input cohort.
"""
import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config


_FAQSD_COLUMNS = ["faqsd_o3", "faqsd_pm25"]


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    # FAQSD C4 daily tract text files
    faqsd_c4 = app.config.settings.SPACESCANS_DATA_DIR / "FAQSD" / "C4"
    if not any(faqsd_c4.glob("*_ozone_daily_8hour_maximum.txt")):
        return False
    if not any(faqsd_c4.glob("*_pm25_daily_average.txt")):
        return False
    tract_c3 = app.config.settings.SPACESCANS_DATA_DIR / "TRACT" / "C3"
    if not tract_c3.is_dir():
        return False
    if not any(tract_c3.glob("tl_2010_*_tract10")):
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / FAQSD C4 txt / Tract C3 / pipeline CLI not configured",
)


@pytest.fixture
def task_with_faqsd_cohort(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-faqsd")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["faqsd"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_faqsd_cohort(task_with_faqsd_cohort):
    task_id, task_dir = task_with_faqsd_cohort

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
    assert "faqsd" in experiments, (
        f"expected faqsd slot in status.experiments; got {list(experiments)}"
    )
    assert experiments["faqsd"]["status"] == "finished"
    assert experiments["faqsd"]["progress"] == 1.0

    logs_path = task_dir / "logs.jsonl"
    assert logs_path.exists(), "logs.jsonl must be written"
    log_lines = [json.loads(line) for line in logs_path.read_text().splitlines() if line.strip()]
    log_steps = {entry.get("source") for entry in log_lines if entry.get("source")}
    assert "c3_tract_us" in log_steps, f"expected c3_tract_us in logs; got {log_steps}"
    assert "c4_tract_faqsd" in log_steps, f"expected c4_tract_faqsd in logs; got {log_steps}"

    result_partial = task_dir / "output" / "result_faqsd.csv"
    assert result_partial.exists(), "result_faqsd.csv must be written"
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
    # result.csv is a left join onto the cohort, so its row count and its
    # column names prove nothing about the linkage — an empty partial still
    # yields a full-length table of NaNs. The partial CSV is the evidence.
    partial = pd.read_csv(result_partial)
    assert len(partial) == len(input_df), (
        f"result_faqsd.csv has {len(partial)} rows for {len(input_df)} cohort rows — "
        "the C4 step produced fewer episodes than the cohort has (empty join?)"
    )
    for c in _FAQSD_COLUMNS:
        filled = partial[c].notna().mean() if c in partial.columns else 0.0
        assert filled >= 0.9, (
            f"{c}: only {filled:.0%} of cohort rows carry a value in result_faqsd.csv"
        )
    missing = [c for c in _FAQSD_COLUMNS if c not in df.columns]
    assert not missing, f"missing FAQSD value cols: {missing}; got {list(df.columns)}"
