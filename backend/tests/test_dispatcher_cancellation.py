"""Sprint 4 F1b: e2e dispatcher cancellation — real start_task + real stop_task.

Mirrors test_e2e_multi_experiment_cohort's environment + 240s deadline.
The integration-availability gate is the same set of preconditions
(SPACESCANS_DATA_DIR, pipeline CLI, BG fixtures, pyreadr) — when missing
the test is skipped at module import.
"""
import json
import shutil
import time
from pathlib import Path

import pytest

import app.config


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    if not (app.config.settings.SPACESCANS_DATA_DIR
            / "data_full/BG_FL/C3/tiger2010_bg10_states").exists():
        return False
    try:
        import pyreadr  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / pipeline CLI / pyreadr not configured",
)


@pytest.fixture
def task_with_multi_experiment(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-cancellation")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["ndi", "cbp_zcta5"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_cancellation_terminal_state(task_with_multi_experiment):
    """Start a real two-experiment task, wait until the first runner enters
    the 'prepare' step, stop_task, poll until terminal (240s deadline).

    Assert top-level status='cancelled' AND both slots end 'cancelled'.
    """
    task_id, task_dir = task_with_multi_experiment

    from app.task_manager import start_task, stop_task
    start_task(task_id)

    # Wait for the first runner to write ANY current_step under status='running'
    # (proves the dispatcher has Popened a real runner whose SIGTERM handler is
    # armed, without depending on a specific step name — the bg_ndi_wi steps
    # are {csv_to_parquet, c3_bg, c4_ndi, c4_wi, merge} and zcta5_cbp's are
    # {csv_to_parquet, c3_zcta5, c4_zcta5_cbp, merge}; neither writes 'prepare').
    arm_deadline = time.monotonic() + 60.0
    armed = False
    while time.monotonic() < arm_deadline:
        if (task_dir / "status.json").exists():
            status = json.loads((task_dir / "status.json").read_text())
            slot = (status.get("experiments") or {}).get("bg_ndi_wi") or {}
            if slot.get("status") == "running" and slot.get("current_step") is not None:
                armed = True
                break
        time.sleep(0.5)
    assert armed, (
        f"first runner never reported a current_step under status='running' "
        f"within 60s; last status={status if 'status' in dir() else 'unread'}"
    )

    stop_task(task_id)

    # Match test_e2e_multi_experiment_cohort's 240s terminal-state deadline.
    deadline = time.monotonic() + 240.0
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 240s; last status={status}")

    assert status["status"] == "cancelled", (
        f"top-level status must be 'cancelled' after stop_task; got {status['status']}"
    )
    experiments = status.get("experiments") or {}
    assert experiments.get("bg_ndi_wi", {}).get("status") == "cancelled", (
        f"bg_ndi_wi slot must end 'cancelled'; got {experiments.get('bg_ndi_wi')}"
    )
    assert experiments.get("zcta5_cbp", {}).get("status") == "cancelled", (
        f"zcta5_cbp slot must cascade as 'cancelled' (NOT skipped_due_to_prior_failure); "
        f"got {experiments.get('zcta5_cbp')}"
    )
