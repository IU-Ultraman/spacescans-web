"""Sprint 3 e2e: multi-experiment dispatch (bg_ndi_wi + zcta5_cbp)."""
import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config


_R_STAR_COLUMNS = [
    "r_religious", "r_civic", "r_business", "r_political", "r_professional",
    "r_labor", "r_bowling", "r_recreational", "r_golf", "r_sports",
]


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
    meta = create_task(user_id=1, task_name="e2e-multi-experiment")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["ndi", "walkability", "cbp_zcta5"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_multi_experiment_cohort(task_with_multi_experiment):
    task_id, task_dir = task_with_multi_experiment

    from app.task_manager import start_task
    start_task(task_id)

    deadline = time.monotonic() + 240.0
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 240s; last status={status}")

    assert status["status"] == "finished"

    # Sprint 3 final-review regression: top-level progress / steps / current_step
    # were silently clobbered to 0.0 / [] / null on every finished run because the
    # dispatcher never populated per-slot steps + progress and _write_status'
    # _derive_flat_fields then re-derived them as zero.
    assert status["progress"] == 1.0, (
        f"top-level progress must be 1.0 on finished; got {status['progress']}"
    )
    assert len(status["steps"]) > 0, (
        f"top-level steps must be non-empty; got {status.get('steps')}"
    )
    assert status["current_step"] is None or status["current_step"] in status["steps"], (
        f"current_step={status['current_step']} must be None or in steps={status['steps']}"
    )

    experiments = status.get("experiments", {})
    assert set(experiments.keys()) == {"bg_ndi_wi", "zcta5_cbp"}
    assert experiments["bg_ndi_wi"]["status"] == "finished"
    assert experiments["zcta5_cbp"]["status"] == "finished"
    assert experiments["bg_ndi_wi"]["progress"] == 1.0
    assert experiments["zcta5_cbp"]["progress"] == 1.0
    assert experiments["bg_ndi_wi"]["steps"], "bg_ndi_wi slot steps must be populated"
    assert experiments["zcta5_cbp"]["steps"], "zcta5_cbp slot steps must be populated"

    bg_start = experiments["bg_ndi_wi"]["started_at"]
    zc_start = experiments["zcta5_cbp"]["started_at"]
    assert bg_start <= zc_start, (
        f"expected bg_ndi_wi to start before zcta5_cbp; bg={bg_start} zc={zc_start}"
    )

    assert (task_dir / "output" / "result_bg_ndi_wi.csv").exists()
    assert (task_dir / "output" / "result_zcta5_cbp.csv").exists()
    result_csv = task_dir / "output" / "result.csv"
    assert result_csv.exists()

    df = pd.read_csv(result_csv)

    assert "ndi" in df.columns
    assert "NatWalkInd" in df.columns

    missing = [c for c in _R_STAR_COLUMNS if c not in df.columns]
    assert not missing, f"missing r_* columns after fan_in: {missing}"

    bg_df = pd.read_csv(task_dir / "output" / "result_bg_ndi_wi.csv")
    zc_df = pd.read_csv(task_dir / "output" / "result_zcta5_cbp.csv")
    assert len(df) == len(bg_df) == len(zc_df)
