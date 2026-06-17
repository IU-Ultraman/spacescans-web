"""Sprint 9 T3: noise runner — mirror of test_nhd_bluespace.py.

Ten tests pinning the runner contract: plan validation (empty / unknown /
order), render_yaml C3 vs C4 divergence (source.file rewrite for C4 only —
NOT exposure.file, which differs from TIGER/NHD — and output_grouping
injection), the no-raster boundary-namespaced cache key (R1 collision lock
against bg_ndi_wi AND tiger_proximity AND nhd_bluespace), the static_areal
sanity probe, and merge_results delegation into _merge.write_partial.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from app.experiments import noise


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task_noise_T3"
    d.mkdir()
    (d / "input.csv").write_text(
        "pid,startDate,endDate,long,lat\n"
        "p1,2017-01-01,2017-12-31,-87.6,41.9\n"
        "p1,2018-01-01,2018-12-31,-87.7,41.8\n"
        "p2,2017-06-01,2018-05-31,-86.2,39.8\n"
    )
    (d / "config.json").write_text(json.dumps({
        "variables": ["noise"],
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
    """Stub C3 + C4 templates. The C3 noise template intentionally has no
    `time:` block — the `if "time" in cfg` guard in render_yaml must skip
    the output_grouping injection naturally on C3.

    The C4 template includes both `source` (the weights table — rewritten
    by render_yaml) and `exposure` (the static TIF path — left untouched
    by render_yaml; resolved by pipeline CLI --data-dir).
    """
    templates = tmp_path / "configs"
    (templates / "c3").mkdir(parents=True)
    (templates / "c4").mkdir(parents=True)
    (templates / "c3" / "noise_grid_demo.yaml").write_text(yaml.safe_dump({
        "name": "c3_noise_demo",
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "source": {"file": "data/Noise/C3/CONUS_L50dBA_sumDay_exi.tif"},
        "output": {"path": "PLACEHOLDER"},
    }))
    (templates / "c4" / "noise_demo.yaml").write_text(yaml.safe_dump({
        "name": "c4_noise_demo",
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "source": {
            "file": "output/python_v2/270m/Noise/C3/buffer270m_noise_weights_demo100k.parquet",
            "join_col": "grid_id",
        },
        "exposure": {
            "file": "data/Noise/C3/CONUS_L50dBA_sumDay_exi.tif",
            "join_col": "grid_id",
            "value_cols": ["l50dba_exi", "l50dba_imp", "l50dba_nat"],
        },
        "time": {"temporal_resolution": "static", "temporal_mode": "static",
                 "output_grouping": "patient"},
        "plugin": "noise",
        "output": {"path": "PLACEHOLDER"},
    }))
    import app.config as cfgmod
    monkeypatch.setattr(cfgmod.settings, "SPACESCANS_CONFIG_TEMPLATES_DIR",
                        templates, raising=False)
    return templates


# ---------- plan() ----------

def test_plan_rejects_empty_variables() -> None:
    with pytest.raises(ValueError, match="at least one variable"):
        noise.plan({"variables": []})


def test_plan_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError, match="unknown variable"):
        noise.plan({"variables": ["ndi"]})  # ndi belongs to bg_ndi_wi


def test_plan_returns_c3_then_c4_order(task_dir: Path) -> None:
    config = json.loads((task_dir / "config.json").read_text())
    steps = noise.plan(config)
    assert [s.name for s in steps] == ["c3_noise", "c4_noise"]
    assert steps[0].is_c3 is True
    assert steps[1].is_c3 is False


# ---------- render_yaml() ----------

def test_render_yaml_c3_leaves_source_untouched(
    task_dir: Path, templates_dir: Path
) -> None:
    """C3 template's source.file (the static TIF) must NOT be rewritten to a
    per-task path — pipeline CLI --data-dir resolves the relative
    'data/Noise/C3/...' against SPACESCANS_DATA_DIR.
    """
    cfg = {"buffer": {"size": 270}}
    c3_path = noise.render_yaml(noise._C3_STEP, task_dir, cfg)
    rendered = yaml.safe_load(c3_path.read_text())
    assert str(task_dir) not in rendered.get("source", {}).get("file", "")
    assert "exposure" not in rendered


def test_render_yaml_c4_rewrites_source_to_per_task_c3_parquet(
    task_dir: Path, templates_dir: Path
) -> None:
    """C4 source.file (weights table) MUST be rewritten to per-task C3 output.
    This is the key Sprint 9 divergence from NHD/TIGER (which rewrite
    exposure.file): static_areal reads the weights as source, NOT exposure.
    """
    cfg = {"buffer": {"size": 270}}
    c4_step = noise._VARIABLE_TO_STEP["noise"]
    c4_path = noise.render_yaml(c4_step, task_dir, cfg)
    rendered = yaml.safe_load(c4_path.read_text())
    expected = str(task_dir / "output" / "c3_noise.parquet")
    assert rendered["source"]["file"] == expected


def test_render_yaml_c4_leaves_exposure_file_untouched(
    task_dir: Path, templates_dir: Path
) -> None:
    """C4 exposure.file (the static TIF path) MUST NOT be rewritten — pipeline
    CLI --data-dir resolves the relative 'data/Noise/C3/CONUS_L50dBA_*.tif'
    path against SPACESCANS_DATA_DIR. A regression that rewrote exposure.file
    to a per-task path (mirroring TIGER/NHD) would silently break the
    noise reader plugin which expects the static raster directory.
    """
    cfg = {"buffer": {"size": 270}}
    c4_step = noise._VARIABLE_TO_STEP["noise"]
    c4_path = noise.render_yaml(c4_step, task_dir, cfg)
    rendered = yaml.safe_load(c4_path.read_text())
    assert str(task_dir) not in rendered["exposure"]["file"]
    assert "CONUS_L50dBA" in rendered["exposure"]["file"]


def test_render_yaml_injects_output_grouping_episode(
    task_dir: Path, templates_dir: Path
) -> None:
    """C4 has time: block -> output_grouping=episode injected.
    C3 has no time: block -> guard `if "time" in cfg` skips naturally."""
    cfg = {"buffer": {"size": 270}}
    c4_path = noise.render_yaml(
        noise._VARIABLE_TO_STEP["noise"], task_dir, cfg
    )
    rendered = yaml.safe_load(c4_path.read_text())
    assert rendered["time"]["output_grouping"] == "episode"

    c3_path = noise.render_yaml(noise._C3_STEP, task_dir, cfg)
    c3_rendered = yaml.safe_load(c3_path.read_text())
    assert "time" not in c3_rendered


def test_render_yaml_does_not_inject_raster_res_m(
    task_dir: Path, templates_dir: Path
) -> None:
    """Noise TIFs are precomputed at a fixed grid — render_yaml must not
    invent a raster_res_m key in either C3 or C4 (parallels NHD/TIGER).
    """
    cfg = {"buffer": {"size": 270, "raster_res_m": 25}}  # user supplied; runner must ignore
    for step in (noise._C3_STEP, noise._VARIABLE_TO_STEP["noise"]):
        path = noise.render_yaml(step, task_dir, cfg)
        rendered = yaml.safe_load(path.read_text())
        assert "raster_res_m" not in rendered.get("buffer", {})


# ---------- _cache_key() ----------

def test_cache_key_differs_from_bg_ndi_wi_tiger_nhd_in_shape_and_boundary(
    task_dir: Path,
) -> None:
    """R1 lock: noise, nhd_bluespace, tiger_proximity, bg_ndi_wi all share
    boundary=BG in metadata but emit incompatible C3 schemas. Cache keys
    MUST diverge in both the boundary tag AND overall shape (noise/NHD/tiger
    have no raster suffix) for the same (input_parquet, buffer). A regression
    collapsing any delta would silently let one runner read another's parquet.
    """
    from app.experiments import bg_ndi_wi, nhd_bluespace, tiger_proximity

    cfg = {"buffer": {"size": 270, "raster_res_m": 25}}
    noise_key = noise._cache_key(
        task_dir / "input.parquet", noise._C3_STEP, cfg
    )
    nhd_key = nhd_bluespace._cache_key(
        task_dir / "input.parquet", nhd_bluespace._C3_STEP, cfg
    )
    tiger_key = tiger_proximity._cache_key(
        task_dir / "input.parquet", tiger_proximity._C3_STEP, cfg
    )
    bg_key = bg_ndi_wi._cache_key(
        task_dir / "input.parquet", bg_ndi_wi._C3_STEP, cfg
    )
    # Boundary tags differ across all four.
    assert noise_key.split("__")[1] == "BG_NOISE"
    assert nhd_key.split("__")[1] == "BG_NHD"
    assert tiger_key.split("__")[1] == "BG_TIGER"
    assert bg_key.split("__")[1] == "BG"
    # noise / NHD / TIGER share 3-segment shape (no raster suffix);
    # bg_ndi_wi has 4-segment shape (raster suffix).
    assert len(noise_key.split("__")) == 3
    assert len(nhd_key.split("__")) == 3
    assert len(tiger_key.split("__")) == 3
    assert len(bg_key.split("__")) == 4
    # All four keys mutually distinct.
    assert len({noise_key, nhd_key, tiger_key, bg_key}) == 4


# ---------- merge_results() ----------

def test_merge_results_delegates_to_write_partial(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """merge_results is a thin wrapper into _merge.write_partial with the
    noise-specific experiment_key and parquet_map."""
    out_dir = task_dir / "output"
    out_dir.mkdir()
    value_cols = ["l50dba_exi", "l50dba_imp", "l50dba_nat"]
    pd.DataFrame({
        "PATID": ["p1", "p1", "p2"],
        "geoid": [0, 1, 2],
        **{c: [50.0, 55.0, 60.0] for c in value_cols},
    }).to_parquet(out_dir / "c4_noise.parquet", index=False)

    captured: dict = {}

    def fake_write_partial(*, task_dir, experiment_key, variables, parquet_map):
        captured["experiment_key"] = experiment_key
        captured["variables"] = variables
        captured["parquet_map"] = parquet_map
        return out_dir / f"result_{experiment_key}.csv"

    monkeypatch.setattr(
        "app.experiments._merge.write_partial", fake_write_partial
    )
    out = noise.merge_results(task_dir, variables=["noise"])
    assert out == out_dir / "result_noise.csv"
    assert captured["experiment_key"] == "noise"
    assert captured["variables"] == ["noise"]
    assert captured["parquet_map"] == {"noise": "c4_noise.parquet"}


# ---------- sanity probe ----------

def test_sanity_check_passes_against_current_pipeline():
    """Positive case: live pipeline contains output_grouping dispatch
    (Sprint 6 T6 landed resolve_output_grouping in static_areal_linkage)."""
    noise._sanity_check_pipeline_supports_static_areal_episode()


def test_sanity_check_raises_on_stale_pipeline(monkeypatch):
    """Negative case: pipeline source without 'output_grouping' raises
    RuntimeError. Catches the R3 stale-editable-install silent-corruption
    scenario for the static_areal linkage pattern.
    """
    import inspect

    stale_src = '''
"""Run static_areal linkage. For each patient..."""
def run_static_areal(config, engine):
    # Compute duration-weighted means per patient
    # GROUP BY PATID
    pass
'''
    monkeypatch.setattr(inspect, "getsource", lambda mod: stale_src)
    with pytest.raises(RuntimeError, match="output_grouping"):
        noise._sanity_check_pipeline_supports_static_areal_episode()
