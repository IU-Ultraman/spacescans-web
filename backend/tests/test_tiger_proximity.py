"""Sprint 5 B3: tiger_proximity runner — mirror of test_zcta5_cbp.py.

Eight tests pinning the runner contract: plan validation (empty / unknown /
order), render_yaml C3 vs C4 divergence (exposure.file rewrite for C4 only,
output_grouping injection), the no-raster boundary-namespaced cache key
(R1 collision lock against bg_ndi_wi), and the merge_results delegation
into _merge.write_partial.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from app.experiments import tiger_proximity


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task_B3"
    d.mkdir()
    (d / "input.csv").write_text(
        "pid,startDate,endDate,long,lat\n"
        "p1,2017-01-01,2017-12-31,-87.6,41.9\n"
        "p1,2018-01-01,2018-12-31,-87.7,41.8\n"
        "p2,2017-06-01,2018-05-31,-86.2,39.8\n"
    )
    (d / "config.json").write_text(json.dumps({
        "variables": ["tiger_proximity"],
        "buffer": {"size": 1000},
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
    templates = tmp_path / "configs"
    (templates / "c3").mkdir(parents=True)
    (templates / "c4").mkdir(parents=True)
    (templates / "c3" / "tiger_roads_demo.yaml").write_text(yaml.safe_dump({
        "name": "c3_tiger_roads_demo",
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "time": {"years": [2017]},
        "output": {"path": "PLACEHOLDER"},
    }))
    (templates / "c4" / "tiger_roads_demo.yaml").write_text(yaml.safe_dump({
        "name": "c4_tiger_roads_demo",
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "exposure": {"file": "/abs/path/to/annual_proximity_demo100k.parquet"},
        "time": {"years": [2017]},
        "output": {"path": "PLACEHOLDER"},
    }))
    import app.config as cfgmod
    monkeypatch.setattr(cfgmod.settings, "SPACESCANS_CONFIG_TEMPLATES_DIR",
                        templates, raising=False)
    return templates


def test_plan_rejects_empty_variables() -> None:
    with pytest.raises(ValueError, match="at least one variable"):
        tiger_proximity.plan({"variables": []})


def test_plan_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError, match="unknown variable"):
        tiger_proximity.plan({"variables": ["ndi"]})  # ndi belongs to bg_ndi_wi


def test_plan_returns_c3_then_c4_order(task_dir: Path) -> None:
    config = json.loads((task_dir / "config.json").read_text())
    steps = tiger_proximity.plan(config)
    assert [s.name for s in steps] == ["c3_tiger_roads", "c4_tiger_roads"]
    assert steps[0].is_c3 is True
    assert steps[1].is_c3 is False


def test_render_yaml_c3_leaves_exposure_untouched(
    task_dir: Path, templates_dir: Path
) -> None:
    cfg = {"buffer": {"size": 1500}}
    c3_path = tiger_proximity.render_yaml(
        tiger_proximity._C3_STEP, task_dir, cfg
    )
    rendered = yaml.safe_load(c3_path.read_text())
    # C3 template has no exposure key; render_yaml must not invent one.
    assert "exposure" not in rendered


def test_render_yaml_c4_rewrites_exposure_to_per_task_c3_parquet(
    task_dir: Path, templates_dir: Path
) -> None:
    cfg = {"buffer": {"size": 1500}}
    c4_step = tiger_proximity._VARIABLE_TO_STEP["tiger_proximity"]
    c4_path = tiger_proximity.render_yaml(c4_step, task_dir, cfg)
    rendered = yaml.safe_load(c4_path.read_text())
    expected = str(task_dir / "output" / "c3_tiger_roads.parquet")
    assert rendered["exposure"]["file"] == expected


def test_render_yaml_injects_output_grouping_episode(
    task_dir: Path, templates_dir: Path
) -> None:
    cfg = {"buffer": {"size": 1500}}
    c4_path = tiger_proximity.render_yaml(
        tiger_proximity._VARIABLE_TO_STEP["tiger_proximity"], task_dir, cfg
    )
    rendered = yaml.safe_load(c4_path.read_text())
    assert rendered["time"]["output_grouping"] == "episode"


def test_cache_key_differs_from_bg_ndi_wi_in_shape_and_boundary(
    task_dir: Path,
) -> None:
    """R1 lock: tiger_proximity and bg_ndi_wi share boundary=BG in metadata
    but emit incompatible C3 schemas. Cache keys MUST diverge in both the
    boundary tag AND overall shape (tiger has no raster suffix) for the
    same (input_parquet, buffer). A regression collapsing either delta
    would silently let one runner read the other's parquet.
    """
    from app.experiments import bg_ndi_wi

    cfg = {"buffer": {"size": 1500, "raster_res_m": 25}}
    tiger_key = tiger_proximity._cache_key(
        task_dir / "input.parquet", tiger_proximity._C3_STEP, cfg
    )
    bg_key = bg_ndi_wi._cache_key(
        task_dir / "input.parquet", bg_ndi_wi._C3_STEP, cfg
    )
    # Boundary tag differs.
    assert tiger_key.split("__")[1] == "BG_TIGER"
    assert bg_key.split("__")[1] == "BG"
    # Overall shape differs (bg has 4 segments incl. raster; tiger has 3).
    assert len(tiger_key.split("__")) == 3
    assert len(bg_key.split("__")) == 4
    assert tiger_key != bg_key


def test_merge_results_delegates_to_write_partial(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """merge_results is a thin wrapper into _merge.write_partial with the
    tiger-specific experiment_key and parquet_map."""
    out_dir = task_dir / "output"
    out_dir.mkdir()
    value_cols = ["dist_pri", "dist_sec", "dist_prisec"]
    pd.DataFrame({
        "PATID": ["p1", "p1", "p2"],
        "geoid": [0, 1, 2],
        **{c: [10.0, 20.0, 30.0] for c in value_cols},
    }).to_parquet(out_dir / "c4_tiger_roads.parquet", index=False)

    captured: dict = {}

    def fake_write_partial(*, task_dir, experiment_key, variables, parquet_map):
        captured["experiment_key"] = experiment_key
        captured["variables"] = variables
        captured["parquet_map"] = parquet_map
        return out_dir / f"result_{experiment_key}.csv"

    monkeypatch.setattr(
        "app.experiments._merge.write_partial", fake_write_partial
    )
    out = tiger_proximity.merge_results(task_dir, variables=["tiger_proximity"])
    assert out == out_dir / "result_tiger_proximity.csv"
    assert captured["experiment_key"] == "tiger_proximity"
    assert captured["variables"] == ["tiger_proximity"]
    assert captured["parquet_map"] == {"tiger_proximity": "c4_tiger_roads.parquet"}


def test_sanity_check_passes_against_current_pipeline():
    """Positive case: live pipeline contains output_grouping dispatch."""
    from app.experiments import tiger_proximity
    tiger_proximity._sanity_check_pipeline_supports_precomputed_areal_episode()


def test_sanity_check_raises_on_stale_pipeline(monkeypatch):
    """Negative case: pipeline source without 'output_grouping' raises RuntimeError.
    Catches the R3 stale-editable-install silent-corruption scenario."""
    from app.experiments import tiger_proximity
    import inspect

    stale_src = '''
"""Run precomputed_areal linkage. For each patient episode..."""
def run_precomputed_areal(config, engine):
    # Prepare patient episodes
    # Compute overlap days between patient episode and each annual window
    # GROUP BY PATID
    pass
'''
    monkeypatch.setattr(inspect, "getsource", lambda mod: stale_src)
    import pytest
    with pytest.raises(RuntimeError, match="output_grouping"):
        tiger_proximity._sanity_check_pipeline_supports_precomputed_areal_episode()
