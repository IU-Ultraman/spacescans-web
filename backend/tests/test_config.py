import importlib
import os
import pytest
from pathlib import Path

def test_pipeline_settings_load_from_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data_full"
    data_dir.mkdir()
    py = tmp_path / "python"
    py.write_text("#!/bin/sh\n")
    py.chmod(0o755)
    cli = tmp_path / "spacescans"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o755)
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()

    monkeypatch.setenv("SPACESCANS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("SPACESCANS_PIPELINE_PYTHON", str(py))
    monkeypatch.setenv("SPACESCANS_PIPELINE_CLI", str(cli))
    monkeypatch.setenv("SPACESCANS_CONFIG_TEMPLATES_DIR", str(cfg_dir))

    import app.config
    importlib.reload(app.config)
    s = app.config.settings

    assert s.SPACESCANS_DATA_DIR == data_dir
    assert s.SPACESCANS_PIPELINE_PYTHON == py
    assert s.SPACESCANS_PIPELINE_CLI == cli
    assert s.SPACESCANS_CONFIG_TEMPLATES_DIR == cfg_dir

def test_validate_pipeline_settings_raises_on_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SPACESCANS_DATA_DIR", str(tmp_path / "does-not-exist"))
    monkeypatch.setenv("SPACESCANS_PIPELINE_PYTHON", str(tmp_path / "nope"))
    monkeypatch.setenv("SPACESCANS_PIPELINE_CLI", str(tmp_path / "nope"))
    monkeypatch.setenv("SPACESCANS_CONFIG_TEMPLATES_DIR", str(tmp_path / "nope"))

    import app.config
    importlib.reload(app.config)
    with pytest.raises(RuntimeError, match="SPACESCANS_DATA_DIR"):
        app.config.validate_pipeline_settings()
