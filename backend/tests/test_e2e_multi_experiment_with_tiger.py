"""Sprint 5 e2e: 4-variable, 3-experiment dispatch (bg_ndi_wi + zcta5_cbp + tiger_proximity)."""
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
_DIST_COLUMNS = ["dist_pri", "dist_sec", "dist_prisec"]


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    if not (app.config.settings.SPACESCANS_DATA_DIR
            / "data_full/BG_FL/C3/tiger2010_bg10_states").exists():
        return False
    tiger_c4 = app.config.settings.SPACESCANS_DATA_DIR / "data_full" / "TIGER" / "C4"
    if not tiger_c4.is_dir():
        return False
    if not any(tiger_c4.glob("tiger*_roads")):
        return False
    try:
        import pyreadr  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / pipeline CLI / TIGER data / pyreadr not configured",
)


@pytest.fixture
def task_with_three_experiments(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-multi-with-tiger")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["ndi", "walkability", "cbp_zcta5", "tiger_proximity"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_multi_experiment_with_tiger_cohort(task_with_three_experiments):
    task_id, task_dir = task_with_three_experiments

    from app.task_manager import start_task
    start_task(task_id)

    deadline = time.monotonic() + 300.0
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 300s; last status={status}")

    assert status["status"] == "finished"
    assert status["progress"] == 1.0
    assert len(status["steps"]) > 0

    experiments = status.get("experiments", {})
    assert set(experiments.keys()) == {"bg_ndi_wi", "zcta5_cbp", "tiger_proximity"}
    for key in ("bg_ndi_wi", "zcta5_cbp", "tiger_proximity"):
        assert experiments[key]["status"] == "finished", f"{key} not finished"
        assert experiments[key]["progress"] == 1.0
        assert experiments[key]["steps"], f"{key} slot steps must be populated"

    # Spec L604-605: metadata-file order is bg_ndi_wi → zcta5_cbp → tiger_proximity.
    bg_start = experiments["bg_ndi_wi"]["started_at"]
    zc_start = experiments["zcta5_cbp"]["started_at"]
    tg_start = experiments["tiger_proximity"]["started_at"]
    assert bg_start <= zc_start <= tg_start, (
        f"expected metadata-file dispatch order; "
        f"bg={bg_start} zc={zc_start} tg={tg_start}"
    )

    for runner in ("bg_ndi_wi", "zcta5_cbp", "tiger_proximity"):
        assert (task_dir / "output" / f"result_{runner}.csv").exists(), runner

    result_csv = task_dir / "output" / "result.csv"
    assert result_csv.exists()
    df = pd.read_csv(result_csv)

    assert "ndi" in df.columns
    assert "NatWalkInd" in df.columns
    missing_r = [c for c in _R_STAR_COLUMNS if c not in df.columns]
    assert not missing_r, f"missing r_* columns after fan_in: {missing_r}"
    missing_dist = [c for c in _DIST_COLUMNS if c not in df.columns]
    assert not missing_dist, f"missing dist_* columns after fan_in: {missing_dist}"

    bg_df = pd.read_csv(task_dir / "output" / "result_bg_ndi_wi.csv")
    zc_df = pd.read_csv(task_dir / "output" / "result_zcta5_cbp.csv")
    tg_df = pd.read_csv(task_dir / "output" / "result_tiger_proximity.csv")
    assert len(df) == len(bg_df) == len(zc_df) == len(tg_df)
