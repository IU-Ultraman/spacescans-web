"""Every web process turns PROJ's network grid downloads off before anything uses PROJ.

In the backend image conda-forge's PROJ activation exports PROJ_NETWORK=ON, so PROJ tried
to download NOAA grids from cdn.proj.org for each EPSG:4326 -> 5070 transformation; in
the API's worker threads the download failed and pyproj returned inf, so a features
dataset was stored with infinite coordinates (phase-D integration gate). A machine without
that environment cannot show the failure, so this checks the mechanism: importing any web
entry point sets PROJ_NETWORK=OFF even when the environment says ON, pyproj then reports
the network disabled, and the pipeline subprocesses inherit the setting.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

_PROBE = """
import os, subprocess, sys
import {module}
assert os.environ.get("PROJ_NETWORK") == "OFF", os.environ.get("PROJ_NETWORK")
try:
    import pyproj.network
except ImportError:
    pass
else:
    assert not pyproj.network.is_network_enabled(), "pyproj network still enabled"
child = subprocess.run([sys.executable, "-c", "import os; print(os.environ.get('PROJ_NETWORK'))"],
                       capture_output=True, text=True).stdout.strip()
assert child == "OFF", child
print("ok")
"""


@pytest.mark.parametrize("module", ["app", "app.main", "app.dispatcher", "app.experiments.custom"])
def test_web_entry_points_turn_proj_network_off(module):
    env = {**os.environ, "PROJ_NETWORK": "ON"}  # what the image's conda activation exports
    proc = subprocess.run([sys.executable, "-c", _PROBE.format(module=module)], cwd=BACKEND,
                          env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("ok"), proc.stderr[-2000:]
