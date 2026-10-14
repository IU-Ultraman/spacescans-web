import importlib
import os
import pytest
from pathlib import Path

def test_pipeline_settings_load_from_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data-root"
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


# ---------------------------------------------------------------------------
# tier-2 phase C: templates come from the package; a configs/ dir must match
# ---------------------------------------------------------------------------

_REPO_CONFIGS = Path(__file__).resolve().parents[2] / "configs"


def _env_with_real_paths(tmp_path, monkeypatch, templates_dir):
    data_dir = tmp_path / "data-root"
    (data_dir / "BG").mkdir(parents=True)
    py = tmp_path / "python"; py.write_text("#!/bin/sh\n")
    cli = tmp_path / "spacescans"; cli.write_text("#!/bin/sh\n")
    monkeypatch.setenv("SPACESCANS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("SPACESCANS_PIPELINE_PYTHON", str(py))
    monkeypatch.setenv("SPACESCANS_PIPELINE_CLI", str(cli))
    if templates_dir is None:
        monkeypatch.delenv("SPACESCANS_CONFIG_TEMPLATES_DIR", raising=False)
    else:
        monkeypatch.setenv("SPACESCANS_CONFIG_TEMPLATES_DIR", str(templates_dir))
    import app.config
    importlib.reload(app.config)
    return app.config


def test_templates_dir_is_optional(tmp_path, monkeypatch):
    cfg = _env_with_real_paths(tmp_path, monkeypatch, None)
    assert cfg.settings.SPACESCANS_CONFIG_TEMPLATES_DIR is None
    cfg.validate_pipeline_settings()   # templates render from the package


def test_repo_configs_match_the_packaged_templates(tmp_path, monkeypatch):
    """configs/ stays in the repo this version (the paper's scripts read it);
    startup accepts it only while it is byte-identical to the package's."""
    from spacescans import catalog
    cfg = _env_with_real_paths(tmp_path, monkeypatch, _REPO_CONFIGS)
    assert cfg.check_config_templates(_REPO_CONFIGS) == []
    assert len(catalog.template_hashes()) == 25
    cfg.validate_pipeline_settings()


def test_startup_refuses_a_configs_dir_that_differs(tmp_path, monkeypatch):
    import shutil
    from spacescans import catalog
    copy = tmp_path / "configs"
    shutil.copytree(_REPO_CONFIGS, copy)
    edited = copy / "c4" / "noise_demo.yaml"
    edited.write_text(edited.read_text() + "\n# local edit\n")
    (copy / "c3" / "bg_us_demo.yaml").unlink()
    cfg = _env_with_real_paths(tmp_path, monkeypatch, copy)
    problems = cfg.check_config_templates(copy)
    assert problems == ["missing: c3/bg_us_demo.yaml", "differs: c4/noise_demo.yaml"]
    with pytest.raises(RuntimeError, match="does not match the templates packaged"):
        cfg.validate_pipeline_settings()
    # The package's hashes are what the check compares against.
    assert "c4/noise_demo.yaml" in catalog.template_hashes()
