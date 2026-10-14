"""The backend image installs pinned Python packages (tier-2 phase-C review OPS-1).

A rebuild of backend/Dockerfile re-runs both pip lines whenever SPACESCANS_REF changes
(the cutover changes it). Without constraints pip took that day's PyPI release of every
dependency not pinned in requirements.txt (duckdb, geopandas, shapely, pyproj, pyogrio,
xarray, netCDF4, pyreadr, ...), so the image the cutover builds was not the one the gates
tested. These checks keep the Dockerfile and constraints.txt from drifting apart.
"""
from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s=;#]+)$")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _constraints() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in (BACKEND / "constraints.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = PIN.match(line)
        assert m, f"constraints.txt: not a name==version pin: {line!r}"
        assert _norm(m[1]) not in pins, f"constraints.txt pins {m[1]} twice"
        pins[_norm(m[1])] = m[2]
    return pins


def _pip_installs(dockerfile: str) -> list[str]:
    """Every RUN command of the Dockerfile that runs pip install, continuation lines joined."""
    joined = re.sub(r"\\\n", " ", dockerfile)
    return [line for line in joined.splitlines()
            if line.lstrip().startswith("RUN") and "pip install" in line]


def test_every_pip_install_of_the_image_uses_the_constraints() -> None:
    dockerfile = (BACKEND / "Dockerfile").read_text()
    installs = _pip_installs(dockerfile)
    assert len(installs) == 2, installs
    for command in installs:
        assert "-c constraints.txt" in command, command
    lines = dockerfile.splitlines()
    copy = next(i for i, line in enumerate(lines)
                if line.startswith("COPY") and "constraints.txt" in line)
    first_pip = next(i for i, line in enumerate(lines)
                     if "pip install" in line and not line.lstrip().startswith("#"))
    assert copy < first_pip, "constraints.txt must be copied before the first pip install"


def test_constraints_pin_the_cache_key_versions_and_not_the_package() -> None:
    pins = _constraints()
    assert "spacescans-pipeline" not in pins          # installed from SPACESCANS_REF
    requirements = (BACKEND / "requirements.txt").read_text()
    dockerfile = (BACKEND / "Dockerfile").read_text()
    for name, version in (("pandas", "3.0.5"), ("pyarrow", "26.0.0")):
        assert pins[name] == version
        assert re.search(rf"^{name}=={re.escape(version)}$", requirements, re.M), name
        assert f'"{name}=={version}"' in dockerfile, name
    # the libraries the pipeline computes with are all held, not only pandas and pyarrow
    for name in ("duckdb", "geopandas", "shapely", "pyproj", "pyogrio", "xarray", "netcdf4",
                 "pyreadr", "mercantile", "pydantic", "pyyaml"):
        assert name in pins, name
