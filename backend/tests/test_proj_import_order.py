"""The app package loads pyproj before anything can load rasterio.

The backend image carries two PROJ libraries (conda-forge GDAL/rasterio and the pip pyproj
wheel). With rasterio loaded first, pyproj returned inf coordinates in the container, so a
features dataset registered after a raster upload linked nothing (phase-D integration
gate). macOS does not show the clash, so this checks the mechanism: importing the app
package, as every web process does first, loads pyproj, and does so before rasterio.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

_PROBE = """
import sys
import {module}
mods = list(sys.modules)
assert "pyproj" in sys.modules, "pyproj was not loaded"
if "rasterio" in sys.modules:
    assert mods.index("pyproj") < mods.index("rasterio"), "rasterio was loaded before pyproj"
print("ok")
"""


@pytest.mark.parametrize("module", ["app", "app.main", "app.dispatcher", "app.experiments.custom"])
def test_importing_the_app_loads_pyproj_first(module):
    pytest.importorskip("pyproj")
    proc = subprocess.run([sys.executable, "-c", _PROBE.format(module=module)], cwd=BACKEND,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("ok"), proc.stderr[-2000:]
