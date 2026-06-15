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
import subprocess
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
