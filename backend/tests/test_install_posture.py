"""Install-posture tests for the spacescans-pipeline pin (T4 / H1).

These tests guard the cross-repo invariant that backend/requirements.txt
pins `spacescans-pipeline>=0.2` AND that the installed distribution actually
satisfies that floor. They are paired with the pipeline 0.1.0 -> 0.2.0 bump.
"""
from __future__ import annotations

import subprocess
import sys
import venv
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../.worktrees/feat-sprint-6/
REQUIREMENTS = REPO_ROOT / "backend" / "requirements.txt"
PIN_FLOOR = Version("0.2")
DIST_NAME = "spacescans-pipeline"
# Pipeline repo wheel-output dir for find-links. spacescans-pipeline is not
# published to PyPI, so dry-run resolution needs a local --find-links pointer.
PIPELINE_DIST_DIR = REPO_ROOT.parent.parent.parent / "dist"


def test_requirements_pin_resolves(tmp_path: Path) -> None:
    """`pip install --dry-run -r backend/requirements.txt` must succeed."""
    assert REQUIREMENTS.is_file(), f"missing requirements file: {REQUIREMENTS}"
    contents = REQUIREMENTS.read_text(encoding="utf-8")
    assert "spacescans-pipeline>=0.2" in contents, (
        "expected 'spacescans-pipeline>=0.2' pin in backend/requirements.txt; "
        f"got:\n{contents}"
    )

    if not PIPELINE_DIST_DIR.is_dir() or not any(
        PIPELINE_DIST_DIR.glob("spacescans_pipeline-*.whl")
    ):
        pytest.skip(
            f"no local spacescans-pipeline wheel found in {PIPELINE_DIST_DIR}; "
            "run `python -m build --wheel` in the pipeline repo first"
        )

    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
    pip = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
    result = subprocess.run(
        [
            str(pip),
            "install",
            "--dry-run",
            "--find-links",
            str(PIPELINE_DIST_DIR),
            "-r",
            str(REQUIREMENTS),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"pip --dry-run failed (rc={result.returncode})\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_pipeline_version_matches_pin() -> None:
    """Installed spacescans-pipeline must satisfy the >=0.2 floor."""
    try:
        installed = Version(version(DIST_NAME))
    except PackageNotFoundError:
        pytest.skip(f"{DIST_NAME} not installed in current environment")
    assert installed >= PIN_FLOOR, (
        f"installed {DIST_NAME}=={installed} does not satisfy >= {PIN_FLOOR}"
    )
