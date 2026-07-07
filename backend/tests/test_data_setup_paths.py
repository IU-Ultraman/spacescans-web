"""Path-consistency guard for the Data Setup page.

The frontend Data Setup guide (frontend/src/lib/data-sources.json) tells users
where to place each downloaded dataset. Those placeDir values are a second copy
of the real input paths in configs/*.yaml. This test asserts every self-serve
placeDir prefix still appears in some config source/exposure/buffer path, so the
guide can't silently drift from where the pipeline actually reads its inputs.

Skips when configs/ isn't available (e.g. spacescans-web cloned on its own).
"""
import glob
import json
import os
from pathlib import Path

import pytest
import yaml

_WEB_ROOT = Path(__file__).resolve().parents[2]
_DATA_SOURCES_JSON = _WEB_ROOT / "frontend" / "src" / "lib" / "data-sources.json"


def _config_path_blob(configs_dir: Path) -> str:
    """Concatenate every source/exposure/buffer file path across configs/*.yaml."""
    paths: list[str] = []
    yamls = glob.glob(str(configs_dir / "c3" / "*.yaml")) + glob.glob(
        str(configs_dir / "c4" / "*.yaml")
    )
    for y in yamls:
        try:
            cfg = yaml.safe_load(Path(y).read_text())
        except Exception:
            continue
        if not isinstance(cfg, dict):
            continue
        for section in ("source", "exposure", "buffer"):
            sec = cfg.get(section)
            if not isinstance(sec, dict):
                continue
            f = sec.get("file")
            if isinstance(f, str):
                paths.append(f)
            elif isinstance(f, list):
                paths += [x for x in f if isinstance(x, str)]
    return "\n".join(paths)


def test_data_setup_place_dirs_match_configs():
    if not _DATA_SOURCES_JSON.exists():
        pytest.skip(f"data-sources.json not found at {_DATA_SOURCES_JSON}")
    configs_dir = Path(
        os.environ.get("SPACESCANS_CONFIG_TEMPLATES_DIR")
        or (_WEB_ROOT.parent / "configs")
    )
    if not (configs_dir / "c3").exists():
        pytest.skip(
            "configs/ not available (set SPACESCANS_CONFIG_TEMPLATES_DIR to the repo configs dir)"
        )

    blob = _config_path_blob(configs_dir)
    catalog = json.loads(_DATA_SOURCES_JSON.read_text())

    missing: list[str] = []
    # Both self-serve (public download) and preset (deployer-supplied) datasets
    # declare where their files land; both must match a real pipeline input path.
    for d in catalog["selfServe"] + catalog["preset"]:
        for place in d.get("placeDir", []):
            # Stable prefix up to the first {placeholder}; the exact
            # per-state/var/year suffix varies, but the prefix must exist verbatim.
            prefix = place.split("{")[0].rstrip("/ ")
            if prefix and prefix not in blob:
                missing.append(f"{d['key']}: {prefix!r}")

    assert not missing, (
        "Data Setup placeDir(s) not found in any configs/*.yaml source/exposure "
        "path — the guide has drifted from the pipeline: " + "; ".join(missing)
    )
