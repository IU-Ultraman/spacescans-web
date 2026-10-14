"""frontend/src/lib/data-sources.json is generated from the spacescans data manifest.

``scripts/gen_data_sources.py`` (repo root) derives every structural field of
the Data Setup catalog from ``spacescans/data/manifest.json``; the committed
JSON must be its exact output, so the page can never drift from the manifest
(and test_data_setup_paths.py keeps the placeDirs honest against the templates).
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_WEB_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _WEB_ROOT / "scripts" / "gen_data_sources.py"
_JSON = _WEB_ROOT / "frontend" / "src" / "lib" / "data-sources.json"
_FETCH = _WEB_ROOT / "scripts" / "fetch_distribution.sh"


def _gen():
    spec = importlib.util.spec_from_file_location("gen_data_sources", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_json_is_the_generator_output():
    gen = _gen()
    assert _JSON.read_text(encoding="utf-8") == gen.render(gen.generate()), (
        "frontend/src/lib/data-sources.json is stale: run scripts/gen_data_sources.py")


def test_every_mirrored_dataset_has_a_card_and_every_variable_is_reachable():
    from spacescans.data import load_manifest

    gen = _gen()
    manifest = load_manifest()
    data = gen.generate(manifest)
    cards = data["selfServe"] + data["preset"]
    served = {v for c in cards for v in c["variableKeys"]}
    assert served == set(manifest.variables), served ^ set(manifest.variables)
    # Every artifact that is on the mirror is fetchable from some card.
    fetchable = {c.get("fetch") or c.get("fetchCmd") for c in cards} - {None}
    for name, art in manifest.artifacts.items():
        if art.available and name != "varnameCountRemoved.csv":
            assert any(cmd.endswith(" " + name) for cmd in fetchable), name
    # Sizes and hashes come from the manifest, not from prose.
    county = next(c for c in data["selfServe"] if c["key"] == "county-boundaries")
    art = manifest.artifacts["county_boundaries_v1.tar.gz"]
    assert county["files"][0]["name"] == art.name
    assert f"{art.bytes / 1e6:.0f} MB" in county["size"]
    assert county["sourceUrl"] == manifest.mirrors[art.mirror].url
    assert county["placeDir"] == ["County/C3/tl_2010_us_county10/"]
    # The page's fetch commands for provider-scripted datasets name the
    # manifest's dataset key and terms id (the prose is hand-written).
    for key, ds_key, _prose in gen.SELF_SERVE:
        ds = manifest.dataset(ds_key)
        if ds.acquire == "provider-scripted":
            card = next(c for c in data["selfServe"] if c["key"] == key)
            cmd = f"spacescans data fetch --dataset {ds_key} --accept-terms {ds.terms.id}"
            assert any(cmd in note for note in card["notes"]), (key, cmd)


def test_check_mode_passes_on_the_committed_file():
    r = subprocess.run([sys.executable, str(_SCRIPT), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not _FETCH.exists(), reason="fetch script missing")
def test_fetch_wrapper_lists_the_manifest_artifacts():
    """The fetch script wraps `python -m spacescans data fetch`; --list reads
    the same manifest the page is generated from."""
    from spacescans.data import load_manifest

    env = {"PATH": "/usr/bin:/bin", "SPACESCANS_PYTHON": sys.executable}
    r = subprocess.run(["bash", str(_FETCH), "--list"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    for name in load_manifest().artifacts:
        assert name in r.stdout, name
    bad = subprocess.run(["bash", str(_FETCH), "nope.tar.gz", "--", "--dry-run"],
                         capture_output=True, text=True, env=env)
    assert bad.returncode != 0
    assert "not a mirrored artifact or dataset" in bad.stdout + bad.stderr
