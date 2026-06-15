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
import signal
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
    if not (app.config.settings.SPACESCANS_DATA_DIR / "data_full/BG_FL/C3/tiger2010_bg10_states").exists():
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / pipeline CLI not configured",
)


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


@pytest.mark.integration
def test_lock_prevents_concurrent_start(tmp_path, monkeypatch):
    """Externally hold .run_lock, then call start_task() — expect TaskBusyError."""
    # Configure DATA_DIR/TASKS_DIR for the manager-level test (separate from
    # the pipeline subprocess test path).
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "manager_data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "manager_data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "manager_data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    # Externally hold the lock to simulate another running task.
    import fcntl
    lock_path = _config.settings.DATA_DIR / ".run_lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    fd = os.open(str(lock_path), os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        from app.task_manager import create_task, save_config, start_task, TaskBusyError
        meta = create_task(user_id=1, task_name="lock-test")
        save_config(meta["id"], {
            "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
            "variables": ["ndi"],
            "experiment": "mock",  # don't actually run pipeline
        })
        (_config.settings.TASKS_DIR / f"task-{meta['id']}" / "input.csv").write_text(
            "pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-06-30,-84.3,30.45\n"
        )
        with pytest.raises(TaskBusyError):
            start_task(meta["id"])
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


@pytest.mark.integration
def test_stop_kills_pipeline_subprocess(task_with_5_patients):
    """Spawn the runner subprocess, SIGTERM its process group, verify it dies
    quickly and no leftover spacescans subprocesses remain."""
    cmd = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        "-m", "app.experiments.bg_ndi_wi", "run", str(task_with_5_patients),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    time.sleep(2.0)  # let csv_to_parquet + start of C3 happen

    # Kill the runner's process group (catches the runner + its `spacescans` child).
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    try:
        rc = proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        rc = proc.wait(timeout=5)
        pytest.fail("Subprocess required SIGKILL to die (SIGTERM ignored)")
    assert rc != 0

    # Verify no zombie spacescans CLI processes left behind (excluding defunct).
    # Note: match on the executable basename, not substring — the python interpreter
    # itself lives under .../envs/spacescans/bin/python which would false-positive.
    ps = subprocess.run(["ps", "-A", "-o", "pid,comm"], capture_output=True, text=True)
    live_spacescans = []
    for line in ps.stdout.splitlines():
        if "<defunct>" in line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        comm = parts[1].strip()
        if os.path.basename(comm) == "spacescans":
            live_spacescans.append(line)
    assert not live_spacescans, f"leftover spacescans procs: {live_spacescans}"


@pytest.mark.integration
def test_two_sequential_runs_both_succeed(task_with_5_patients, tmp_path):
    """After one orchestrator subprocess finishes, the lock must release so
    a second can acquire it without 409. Regression test for v1's lock-leak bug."""
    cmd = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        "-m", "app.experiments.bg_ndi_wi", "run", str(task_with_5_patients),
    ]
    # First run
    proc1 = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert proc1.returncode == 0, (
        f"first run failed: stdout={proc1.stdout!r} stderr={proc1.stderr!r}"
    )

    # Second run on a fresh task_dir
    task_dir_2 = tmp_path / "task-int00002"
    task_dir_2.mkdir()
    (task_dir_2 / "output").mkdir()
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir_2 / "input.csv",
    )
    (task_dir_2 / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))

    cmd2 = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        "-m", "app.experiments.bg_ndi_wi", "run", str(task_dir_2),
    ]
    proc2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=600)
    assert proc2.returncode == 0, (
        f"second run failed: stdout={proc2.stdout!r} stderr={proc2.stderr!r}"
    )

    # Both result.csv must exist
    assert (task_with_5_patients / "output" / "result.csv").exists()
    assert (task_dir_2 / "output" / "result.csv").exists()


@pytest.mark.integration
def test_e2e_cache_second_run_faster(task_with_5_patients, tmp_path):
    """Run the same 5-patient cohort twice; the second run hits the c3_bg cache
    and finishes in a small fraction of the first run's wall-clock."""
    # Clear any cache entries left over from earlier tests in the suite so the
    # first run below is guaranteed cold. Without this, the assertion on
    # t2 < 0.7 * t1 is order-dependent: an earlier integration test that runs
    # the same fixture (e.g. test_e2e_same_inputs_run_twice) will populate the
    # cache, making run 1 a cache hit and collapsing the speedup.
    cache_dir = app.config.settings.C3_CACHE_DIR
    if cache_dir.exists():
        shutil.rmtree(cache_dir)

    cmd = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        "-m", "app.experiments.bg_ndi_wi", "run", str(task_with_5_patients),
    ]

    # First run: full pipeline.
    t1_start = time.monotonic()
    proc1 = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    t1 = time.monotonic() - t1_start
    assert proc1.returncode == 0

    # Second task with byte-identical input.csv + config.
    task_dir_2 = tmp_path / "task-int-cache-02"
    task_dir_2.mkdir()
    (task_dir_2 / "output").mkdir()
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir_2 / "input.csv",
    )
    (task_dir_2 / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi", "walkability"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))
    cmd2 = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        "-m", "app.experiments.bg_ndi_wi", "run", str(task_dir_2),
    ]
    t2_start = time.monotonic()
    proc2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=300)
    t2 = time.monotonic() - t2_start
    assert proc2.returncode == 0

    # Second run should be noticeably faster (C3 step skipped).
    # On the 5-patient fixture C3 takes ~5-6s of the ~14s total; the other ~8s
    # is NDI .Rda load + walkability raster crop, which the cache does NOT skip.
    # So a cache hit shaves ~40%, giving t2 ≈ 0.6 * t1. Threshold 0.7 catches a
    # cache regression (no cache → t2 ≈ t1) without being flaky on slow hardware.
    assert t2 < 0.7 * t1, (
        f"expected second run to be < 70% of first; got t1={t1:.2f}s t2={t2:.2f}s"
    )

    # Cache directory exists with one entry.
    parquets = list(cache_dir.glob("*.parquet"))
    assert len(parquets) >= 1
