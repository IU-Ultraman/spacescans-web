"""Sprint 7 B3: nhd_bluespace runner — mirror of test_tiger_proximity.py.

Eight tests pinning the runner contract: plan validation (empty / unknown /
order), render_yaml C3 vs C4 divergence (exposure.file rewrite for C4 only,
output_grouping injection), the no-raster boundary-namespaced cache key
(R1 collision lock against bg_ndi_wi AND tiger_proximity), and the
merge_results delegation into _merge.write_partial.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from app.experiments import nhd_bluespace


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task_nhd_B3"
    d.mkdir()
    (d / "input.csv").write_text(
        "pid,startDate,endDate,long,lat\n"
        "p1,2017-01-01,2017-12-31,-87.6,41.9\n"
        "p1,2018-01-01,2018-12-31,-87.7,41.8\n"
        "p2,2017-06-01,2018-05-31,-86.2,39.8\n"
    )
    (d / "config.json").write_text(json.dumps({
        "variables": ["nhd_bluespace"],
        "buffer": {"size": 270},
    }))
    pd.DataFrame({
        "pid": ["p1", "p1", "p2"],
        "startDate": ["2017-01-01", "2018-01-01", "2017-06-01"],
        "endDate": ["2017-12-31", "2018-12-31", "2018-05-31"],
        "long": [-87.6, -87.7, -86.2],
        "lat": [41.9, 41.8, 39.8],
        "episode_id": [0, 1, 2],
    }).to_parquet(d / "input.parquet", index=False)
    return d


@pytest.fixture()
def templates_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stub C3 + C4 templates. The C3 NHD template intentionally has no
    `time:` block — the `if "time" in cfg` guard in render_yaml must skip
    the output_grouping injection naturally on C3."""
    templates = tmp_path / "configs"
    (templates / "c3").mkdir(parents=True)
    (templates / "c4").mkdir(parents=True)
    (templates / "c3" / "nhd_demo.yaml").write_text(yaml.safe_dump({
        "name": "c3_nhd_demo",
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "source": {"file": "data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb"},
        "output": {"path": "PLACEHOLDER"},
    }))
    (templates / "c4" / "nhd_bluespace_demo.yaml").write_text(yaml.safe_dump({
        "name": "c4_nhd_bluespace_demo",
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "exposure": {"file": "/abs/path/to/proximity_blue_demo100k.parquet"},
        "time": {"temporal_resolution": "static", "temporal_mode": "static",
                 "output_grouping": "patient"},
        "output": {"path": "PLACEHOLDER"},
    }))
    import app.config as cfgmod
    monkeypatch.setattr(cfgmod.settings, "SPACESCANS_CONFIG_TEMPLATES_DIR",
                        templates, raising=False)
    return templates


# ---------- plan() ----------

def test_plan_rejects_empty_variables() -> None:
    with pytest.raises(ValueError, match="at least one variable"):
        nhd_bluespace.plan({"variables": []})


def test_plan_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError, match="unknown variable"):
        nhd_bluespace.plan({"variables": ["ndi"]})  # ndi belongs to bg_ndi_wi


def test_plan_returns_c3_then_c4_order(task_dir: Path) -> None:
    config = json.loads((task_dir / "config.json").read_text())
    steps = nhd_bluespace.plan(config)
    assert [s.name for s in steps] == ["c3_nhd_bluespace", "c4_nhd_bluespace"]
    assert steps[0].is_c3 is True
    assert steps[1].is_c3 is False


# ---------- render_yaml() ----------

def test_render_yaml_c3_leaves_exposure_untouched(
    task_dir: Path, templates_dir: Path
) -> None:
    """C3 template has no exposure: key; render_yaml must not invent one
    and must not rewrite source.file (resolved by pipeline CLI --data-dir).
    """
    cfg = {"buffer": {"size": 270}}
    c3_path = nhd_bluespace.render_yaml(
        nhd_bluespace._C3_STEP, task_dir, cfg
    )
    rendered = yaml.safe_load(c3_path.read_text())
    assert "exposure" not in rendered
    # source.file untouched — task-specific path NOT injected
    assert str(task_dir) not in rendered.get("source", {}).get("file", "")


def test_render_yaml_c4_rewrites_exposure_to_per_task_c3_parquet(
    task_dir: Path, templates_dir: Path
) -> None:
    cfg = {"buffer": {"size": 270}}
    c4_step = nhd_bluespace._VARIABLE_TO_STEP["nhd_bluespace"]
    c4_path = nhd_bluespace.render_yaml(c4_step, task_dir, cfg)
    rendered = yaml.safe_load(c4_path.read_text())
    expected = str(task_dir / "output" / "c3_nhd_bluespace.parquet")
    assert rendered["exposure"]["file"] == expected


def test_render_yaml_injects_output_grouping_episode(
    task_dir: Path, templates_dir: Path
) -> None:
    """C4 has time: block -> output_grouping=episode injected.
    C3 has no time: block -> guard `if "time" in cfg` skips naturally."""
    cfg = {"buffer": {"size": 270}}
    c4_path = nhd_bluespace.render_yaml(
        nhd_bluespace._VARIABLE_TO_STEP["nhd_bluespace"], task_dir, cfg
    )
    rendered = yaml.safe_load(c4_path.read_text())
    assert rendered["time"]["output_grouping"] == "episode"

    c3_path = nhd_bluespace.render_yaml(
        nhd_bluespace._C3_STEP, task_dir, cfg
    )
    c3_rendered = yaml.safe_load(c3_path.read_text())
    assert "time" not in c3_rendered


# ---------- _cache_key() ----------

def test_cache_key_differs_from_bg_ndi_wi_and_tiger_in_shape_and_boundary(
    task_dir: Path,
) -> None:
    """R1 lock: nhd_bluespace, tiger_proximity and bg_ndi_wi share
    boundary=BG in metadata but emit incompatible C3 schemas. Cache keys
    MUST diverge in both the boundary tag AND overall shape (NHD/tiger
    have no raster suffix) for the same (input_parquet, buffer). A
    regression collapsing either delta would silently let one runner read
    another's parquet.
    """
    from app.experiments import bg_ndi_wi, tiger_proximity

    cfg = {"buffer": {"size": 270, "raster_res_m": 25}}
    nhd_key = nhd_bluespace._cache_key(
        task_dir / "input.parquet", nhd_bluespace._C3_STEP, cfg
    )
    tiger_key = tiger_proximity._cache_key(
        task_dir / "input.parquet", tiger_proximity._C3_STEP, cfg
    )
    bg_key = bg_ndi_wi._cache_key(
        task_dir / "input.parquet", bg_ndi_wi._C3_STEP, cfg
    )
    # Boundary tags differ across all three.
    assert nhd_key.split("__")[1] == "BG_NHD"
    assert tiger_key.split("__")[1] == "BG_TIGER"
    assert bg_key.split("__")[1] == "BG"
    # NHD and TIGER share 3-segment shape (no raster suffix);
    # bg_ndi_wi has 4-segment shape (raster suffix).
    assert len(nhd_key.split("__")) == 3
    assert len(tiger_key.split("__")) == 3
    assert len(bg_key.split("__")) == 4
    # All three keys mutually distinct.
    assert nhd_key != tiger_key
    assert nhd_key != bg_key
    assert tiger_key != bg_key


# ---------- merge_results() ----------

def test_merge_results_delegates_to_write_partial(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """merge_results is a thin wrapper into _merge.write_partial with the
    nhd-specific experiment_key and parquet_map."""
    out_dir = task_dir / "output"
    out_dir.mkdir()
    value_cols = [
        "dist_flow_m", "dist_water_m", "dist_area_m",
        "dist_coast_m", "dist_blue_m",
    ]
    pd.DataFrame({
        "PATID": ["p1", "p1", "p2"],
        "geoid": [0, 1, 2],
        **{c: [10.0, 20.0, 30.0] for c in value_cols},
    }).to_parquet(out_dir / "c4_nhd_bluespace.parquet", index=False)

    captured: dict = {}

    def fake_write_partial(*, task_dir, experiment_key, variables, parquet_map):
        captured["experiment_key"] = experiment_key
        captured["variables"] = variables
        captured["parquet_map"] = parquet_map
        return out_dir / f"result_{experiment_key}.csv"

    monkeypatch.setattr(
        "app.experiments._merge.write_partial", fake_write_partial
    )
    out = nhd_bluespace.merge_results(task_dir, variables=["nhd_bluespace"])
    assert out == out_dir / "result_nhd_bluespace.csv"
    assert captured["experiment_key"] == "nhd_bluespace"
    assert captured["variables"] == ["nhd_bluespace"]
    assert captured["parquet_map"] == {"nhd_bluespace": "c4_nhd_bluespace.parquet"}


# ---------- sanity probe ----------

def test_sanity_check_passes_against_current_pipeline():
    """Positive case: live pipeline contains output_grouping dispatch
    (Phase A landed resolve_output_grouping in precomputed_static_linkage)."""
    nhd_bluespace._sanity_check_pipeline_supports_precomputed_static_episode()


def test_sanity_check_raises_on_stale_pipeline(monkeypatch):
    """Negative case: pipeline source without 'output_grouping' raises
    RuntimeError. Catches the R3 stale-editable-install silent-corruption
    scenario for the precomputed_static linkage pattern.
    """
    import inspect

    stale_src = '''
"""Run precomputed_static linkage. For each patient..."""
def run_precomputed_static(config, engine):
    # Compute duration-weighted means per patient
    # GROUP BY PATID
    pass
'''
    monkeypatch.setattr(inspect, "getsource", lambda mod: stale_src)
    with pytest.raises(RuntimeError, match="output_grouping"):
        nhd_bluespace._sanity_check_pipeline_supports_precomputed_static_episode()
