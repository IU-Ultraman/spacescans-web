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
    """Subprocess-friendly raw-Path fixture used by test_stop_kills_pipeline_subprocess
    (which spawns the runner module directly via subprocess.Popen). The four Sprint 2
    e2e tests have migrated to the dispatcher-driven task_with_5_patients_dispatched
    fixture below (Sprint 4 F6)."""
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


@pytest.fixture
def task_with_5_patients_dispatched(tmp_path, monkeypatch):
    """Dispatcher-driven 5-patient cohort fixture (Sprint 4 F6 migration).

    Returns (task_id, task_dir). Caller invokes start_task(task_id) and polls
    status.json — replacing the Sprint 2 subprocess.run([..., '-m',
    'app.experiments.bg_ndi_wi', 'run', task_dir]) pattern.
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="bg-ndi-wi-int-5p")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["ndi", "walkability"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_small_cohort(task_with_5_patients_dispatched):
    task_id, task_dir = task_with_5_patients_dispatched

    from app.task_manager import start_task
    start_task(task_id)

    deadline = time.monotonic() + 240.0
    status = {}
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 240s; last status={status}")

    assert status["status"] == "finished", f"unexpected terminal status: {status}"

    result_csv = task_dir / "output" / "result.csv"
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
def test_two_sequential_runs_both_succeed(task_with_5_patients_dispatched, tmp_path, monkeypatch):
    """After one dispatcher run finishes, the lock must release so a second
    start_task can acquire it without TaskBusyError. Regression test for the
    Sprint 1 lock-leak bug, now exercising the dispatcher path."""
    task_id_1, task_dir_1 = task_with_5_patients_dispatched

    from app.task_manager import start_task, create_task, save_config

    # First run
    start_task(task_id_1)
    deadline = time.monotonic() + 240.0
    status1 = {}
    while time.monotonic() < deadline:
        status1 = json.loads((task_dir_1 / "status.json").read_text())
        if status1.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"first run did not terminate within 240s; last status={status1}")
    assert status1["status"] == "finished", f"first run not finished: {status1}"

    # Second task on a fresh task_id (dispatcher path), same fixture cohort + variables.
    meta2 = create_task(user_id=1, task_name="bg-ndi-wi-int-5p-2")
    import app.config as _config
    task_dir_2 = _config.settings.TASKS_DIR / f"task-{meta2['id']}"
    task_dir_2.mkdir(parents=True, exist_ok=True)
    (task_dir_2 / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir_2 / "input.csv",
    )
    save_config(meta2["id"], {
        "experiment": "auto",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })

    start_task(meta2["id"])
    deadline2 = time.monotonic() + 240.0
    status2 = {}
    while time.monotonic() < deadline2:
        status2 = json.loads((task_dir_2 / "status.json").read_text())
        if status2.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"second run did not terminate within 240s; last status={status2}")
    assert status2["status"] == "finished", f"second run not finished: {status2}"

    assert (task_dir_1 / "output" / "result.csv").exists()
    assert (task_dir_2 / "output" / "result.csv").exists()


@pytest.mark.integration
def test_e2e_cache_second_run_faster(task_with_5_patients_dispatched, tmp_path, monkeypatch):
    """Run the same 5-patient cohort twice via the dispatcher; the second run
    hits the c3_bg cache and finishes in a small fraction of the first run's
    wall-clock."""
    cache_dir = app.config.settings.C3_CACHE_DIR
    if cache_dir.exists():
        shutil.rmtree(cache_dir)

    task_id_1, task_dir_1 = task_with_5_patients_dispatched
    from app.task_manager import start_task, create_task, save_config

    # First run: full pipeline (cold cache).
    t1_start = time.monotonic()
    start_task(task_id_1)
    deadline = time.monotonic() + 240.0
    status1 = {}
    while time.monotonic() < deadline:
        status1 = json.loads((task_dir_1 / "status.json").read_text())
        if status1.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"first run did not terminate within 240s; last status={status1}")
    t1 = time.monotonic() - t1_start
    assert status1["status"] == "finished", f"first run not finished: {status1}"

    # Second task with byte-identical input.csv + config (cache hit).
    meta2 = create_task(user_id=1, task_name="bg-ndi-wi-int-cache-2")
    import app.config as _config
    task_dir_2 = _config.settings.TASKS_DIR / f"task-{meta2['id']}"
    task_dir_2.mkdir(parents=True, exist_ok=True)
    (task_dir_2 / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir_2 / "input.csv",
    )
    save_config(meta2["id"], {
        "experiment": "auto",
        "variables": ["ndi", "walkability"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })

    t2_start = time.monotonic()
    start_task(meta2["id"])
    deadline2 = time.monotonic() + 240.0
    status2 = {}
    while time.monotonic() < deadline2:
        status2 = json.loads((task_dir_2 / "status.json").read_text())
        if status2.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"second run did not terminate within 240s; last status={status2}")
    t2 = time.monotonic() - t2_start
    assert status2["status"] == "finished", f"second run not finished: {status2}"

    # Second run should be noticeably faster (C3 step skipped). Threshold 0.7
    # catches a cache regression without being flaky on slow hardware. Wall-clock
    # now includes dispatcher Popen overhead (~2s constant) on both sides, so the
    # ratio is preserved.
    assert t2 < 0.7 * t1, (
        f"expected second run to be < 70% of first; got t1={t1:.2f}s t2={t2:.2f}s"
    )

    parquets = list(cache_dir.glob("*.parquet"))
    assert len(parquets) >= 1


@pytest.fixture
def task_with_multi_episode_cohort(tmp_path, monkeypatch):
    """11-row cohort: 5 patients x 2 episodes + 1 single-episode patient.

    Dispatcher-driven (Sprint 4 F6 migration). Returns (task_id, task_dir).
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="bg-ndi-wi-int-multi-ep")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_multi_episode.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["ndi", "walkability"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_multi_episode_cohort(task_with_multi_episode_cohort):
    """Sprint 2: pipeline emits per-(patient, episode) rows; the 5x2+1 cohort
    must produce 11 result rows, not 6. Migrated to dispatcher path in Sprint 4 F6."""
    task_id, task_dir = task_with_multi_episode_cohort

    from app.task_manager import start_task
    start_task(task_id)

    deadline = time.monotonic() + 240.0
    status = {}
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 240s; last status={status}")

    assert status["status"] == "finished", f"unexpected terminal status: {status}"

    result_csv = task_dir / "output" / "result.csv"
    df = pd.read_csv(result_csv)

    # CRITICAL: one row per residential episode, not per patient.
    assert len(df) == 11, f"expected 11 rows (per-episode), got {len(df)}"

    assert df["pid"].tolist() == [
        "PID0000001", "PID0000001",
        "PID0000002", "PID0000002",
        "PID0000003", "PID0000003",
        "PID0000004", "PID0000004",
        "PID0000005", "PID0000005",
        "PID0000006",
    ]

    multi_episode_pids = ["PID0000001", "PID0000002", "PID0000003", "PID0000004", "PID0000005"]
    distinct_ndi_count = 0
    for pid in multi_episode_pids:
        vals = df[df["pid"] == pid]["ndi"].dropna().tolist()
        if len(vals) == 2 and vals[0] != vals[1]:
            distinct_ndi_count += 1
    assert distinct_ndi_count >= 2, (
        f"expected >=2 patients with distinct NDI across their 2 episodes; "
        f"only {distinct_ndi_count} differed. Result df:\n{df}"
    )
