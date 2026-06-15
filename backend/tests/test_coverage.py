import importlib
import json
from pathlib import Path
import pytest


def test_load_variable_metadata_reads_ndi_and_walkability(monkeypatch, tmp_path):
    """The loader returns the canonical 2-entry catalog for Sprint 1."""
    data_dir = tmp_path
    (data_dir / "variable_metadata.json").write_text(json.dumps({
        "ndi": {
            "label": "Neighborhood Deprivation Index",
            "boundary": "BG",
            "coverage_years": [2012, 2022],
            "coverage_region": "CONUS",
            "experiment": "bg_ndi_wi",
        },
        "walkability": {
            "label": "EPA Walkability Index",
            "boundary": "BG",
            "coverage_years": [2016, 2021],
            "coverage_region": "CONUS",
            "experiment": "bg_ndi_wi",
        },
    }))
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DB_PATH", str(data_dir / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(data_dir / "tasks"))
    import app.config
    importlib.reload(app.config)
    import app.task_manager
    importlib.reload(app.task_manager)

    meta = app.task_manager._load_variable_metadata()
    assert "ndi" in meta
    assert meta["ndi"]["coverage_years"] == [2012, 2022]
    assert meta["walkability"]["coverage_years"] == [2016, 2021]


def test_load_variable_metadata_caches_until_mtime_changes(monkeypatch, tmp_path):
    """Loader uses mtime-based cache invalidation."""
    data_dir = tmp_path
    (data_dir / "variable_metadata.json").write_text(json.dumps({
        "ndi": {"coverage_years": [2012, 2022], "coverage_region": "CONUS", "label": "X", "boundary": "BG", "experiment": "bg_ndi_wi"},
    }))
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DB_PATH", str(data_dir / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(data_dir / "tasks"))
    import app.config
    importlib.reload(app.config)
    import app.task_manager
    importlib.reload(app.task_manager)

    first = app.task_manager._load_variable_metadata()
    second = app.task_manager._load_variable_metadata()
    assert first is second  # same object — cached
