"""Sprint 3 T8: _write_status atomic merge writer + experiments map."""
import json
import multiprocessing as mp
from pathlib import Path

import pytest


@pytest.fixture
def task_dir(tmp_path):
    d = tmp_path / "task-abc"
    d.mkdir()
    return d


def test_write_status_creates_file_with_experiments_initialiser(task_dir):
    from app.task_manager import _write_status
    _write_status(task_dir, status="running", experiments={})
    data = json.loads((task_dir / "status.json").read_text())
    assert data["status"] == "running"
    assert data["experiments"] == {}
    assert data["steps"] == []
    assert data["total_steps"] == 0
    assert data["current_step"] is None
    assert data["progress"] == 0.0


def test_write_status_experiments_amend_preserves_sibling_keys(task_dir):
    from app.task_manager import _write_status
    _write_status(task_dir, status="running", experiments={
        "bg_ndi_wi": {"status": "pending", "progress": 0.0,
                      "steps": ["c3_bg", "c4_ndi"], "current_step": None},
        "zcta5_cbp": {"status": "pending", "progress": 0.0,
                      "steps": ["c3_zcta5", "c4_zcta5_cbp"], "current_step": None},
    })
    _write_status(task_dir, experiments={
        "bg_ndi_wi": {"status": "running", "progress": 0.5,
                      "current_step": "c4_ndi"},
    })
    data = json.loads((task_dir / "status.json").read_text())
    assert data["experiments"]["bg_ndi_wi"]["status"] == "running"
    assert data["experiments"]["bg_ndi_wi"]["progress"] == 0.5
    assert data["experiments"]["bg_ndi_wi"]["steps"] == ["c3_bg", "c4_ndi"]
    assert data["experiments"]["zcta5_cbp"]["status"] == "pending"


def test_write_status_flat_steps_concatenated_in_insertion_order(task_dir):
    from app.task_manager import _write_status
    _write_status(task_dir, status="running", experiments={
        "bg_ndi_wi": {"status": "pending", "progress": 0.0,
                      "steps": ["c3_bg", "c4_ndi", "c4_walkability"],
                      "current_step": None},
        "zcta5_cbp": {"status": "pending", "progress": 0.0,
                      "steps": ["c3_zcta5", "c4_zcta5_cbp"],
                      "current_step": None},
    })
    data = json.loads((task_dir / "status.json").read_text())
    assert data["steps"] == ["c3_bg", "c4_ndi", "c4_walkability",
                             "c3_zcta5", "c4_zcta5_cbp"]
    assert data["total_steps"] == 5


def test_write_status_aggregated_progress(task_dir):
    from app.task_manager import _write_status
    # 3*1.0 + 2*0.5 = 4 completed / 5 total = 0.80
    _write_status(task_dir, status="running", experiments={
        "bg_ndi_wi": {"status": "finished", "progress": 1.0,
                      "steps": ["c3_bg", "c4_ndi", "c4_walkability"],
                      "current_step": None},
        "zcta5_cbp": {"status": "running", "progress": 0.5,
                      "steps": ["c3_zcta5", "c4_zcta5_cbp"],
                      "current_step": "c4_zcta5_cbp"},
    })
    data = json.loads((task_dir / "status.json").read_text())
    assert data["progress"] == pytest.approx(0.80, abs=1e-6)
    assert data["current_step"] == "c4_zcta5_cbp"


def test_write_status_top_level_keys_overwrite(task_dir):
    from app.task_manager import _write_status
    _write_status(task_dir, status="running", pid=123, started_at="2026-06-15T10:00:00Z")
    _write_status(task_dir, status="finished")
    data = json.loads((task_dir / "status.json").read_text())
    assert data["status"] == "finished"
    assert data["pid"] == 123
    assert data["started_at"] == "2026-06-15T10:00:00Z"


def _hammer(args):
    task_dir_str, exp_key, n = args
    import importlib
    import app.task_manager as tm
    importlib.reload(tm)
    for i in range(n):
        tm._write_status(Path(task_dir_str), experiments={
            exp_key: {"status": "running", "progress": i / n,
                      "steps": [f"{exp_key}_s1", f"{exp_key}_s2"],
                      "current_step": f"{exp_key}_s1"},
        })


def test_write_status_two_concurrent_writers_do_not_corrupt(task_dir):
    """fcntl.flock + os.replace must keep the file parseable under contention."""
    from app.task_manager import _write_status
    _write_status(task_dir, status="running", experiments={})
    with mp.get_context("spawn").Pool(2) as pool:
        pool.map(_hammer, [(str(task_dir), "bg_ndi_wi", 50),
                           (str(task_dir), "zcta5_cbp", 50)])
    raw = (task_dir / "status.json").read_text()
    data = json.loads(raw)
    assert set(data["experiments"].keys()) == {"bg_ndi_wi", "zcta5_cbp"}
    assert not (task_dir / "status.json.tmp").exists()
