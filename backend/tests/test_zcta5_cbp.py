"""Sprint 3 T7: ZCTA5xCBP runner — clone-trim of bg_ndi_wi."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from app.experiments import zcta5_cbp


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task_T7"
    d.mkdir()
    (d / "input.csv").write_text(
        "pid,startDate,endDate,long,lat\n"
        "p1,2017-01-01,2017-12-31,-87.6,41.9\n"
        "p1,2018-01-01,2018-12-31,-87.7,41.8\n"
        "p2,2017-06-01,2018-05-31,-86.2,39.8\n"
    )
    (d / "config.json").write_text(json.dumps({
        "variables": ["cbp_zcta5"],
        "buffer": {"size": 1000, "raster_res_m": 25},
    }))
    return d


def test_plan_is_c3_then_c4(task_dir: Path) -> None:
    config = json.loads((task_dir / "config.json").read_text())
    steps = zcta5_cbp.plan(config)
    assert [s.name for s in steps] == ["c3_zcta5", "c4_zcta5_cbp"]
    assert steps[0].is_c3 is True
    assert steps[1].is_c3 is False


def test_plan_rejects_unknown_variable(task_dir: Path) -> None:
    with pytest.raises(ValueError, match="unknown variable"):
        zcta5_cbp.plan({"variables": ["ndi"]})  # ndi belongs to bg_ndi_wi


def test_csv_to_parquet_adds_episode_id(task_dir: Path) -> None:
    src = task_dir / "input.csv"
    dst = task_dir / "input.parquet"
    zcta5_cbp.csv_to_parquet(src, dst)
    df = pd.read_parquet(dst)
    assert "episode_id" in df.columns
    assert df["episode_id"].tolist() == [0, 1, 2]


def test_render_yaml_injects_output_grouping_episode(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    templates = tmp_path / "configs"
    (templates / "c3").mkdir(parents=True)
    (templates / "c4").mkdir(parents=True)
    (templates / "c3" / "zcta5_us_demo.yaml").write_text(yaml.safe_dump({
        "name": "c3_zcta5_us_demo",
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270,
                   "raster_res_m": 25},
        "time": {"years": [2017]},
        "output": {"path": "PLACEHOLDER"},
    }))
    (templates / "c4" / "zcta5_cbp_demo.yaml").write_text(yaml.safe_dump({
        "name": "c4_zcta5_cbp_demo",
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "time": {"years": [2017]},
        "output": {"path": "PLACEHOLDER"},
    }))
    import app.config as cfgmod
    monkeypatch.setattr(cfgmod.settings, "SPACESCANS_CONFIG_TEMPLATES_DIR",
                        templates, raising=False)

    cfg = {"buffer": {"size": 1500, "raster_res_m": 25}}
    c3_path = zcta5_cbp.render_yaml(zcta5_cbp._C3_STEP, task_dir, cfg)
    rendered = yaml.safe_load(c3_path.read_text())
    assert rendered["time"]["output_grouping"] == "episode"
    assert rendered["buffer"]["raster_res_m"] == 25
    assert rendered["buffer"]["buffer_m"] == 1500


def test_cache_key_contains_zcta5_boundary(task_dir: Path) -> None:
    zcta5_cbp.csv_to_parquet(task_dir / "input.csv", task_dir / "input.parquet")
    key = zcta5_cbp._cache_key(
        task_dir / "input.parquet",
        zcta5_cbp._C3_STEP,
        {"buffer": {"size": 1500, "raster_res_m": 25}},
    )
    parts = key.split("__")
    assert parts[1] == "ZCTA5"
    assert parts[2] == "b1500m"
    assert parts[3] == "r25m"


def test_merge_results_emits_result_zcta5_cbp_csv(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """zcta5_cbp.merge_results mirrors bg_ndi_wi.merge_results — both
    are thin wrappers around _merge.write_partial (see T5)."""
    out_dir = task_dir / "output"
    out_dir.mkdir()
    r_cols = ["r_religious", "r_civic", "r_business", "r_political",
              "r_professional", "r_labor", "r_bowling", "r_recreational",
              "r_golf", "r_sports"]
    parquet_df = pd.DataFrame({
        "PATID": ["p1", "p1", "p2"],
        "geoid": [0, 1, 2],
        **{c: [0.1, 0.2, 0.3] for c in r_cols},
    })
    parquet_df.to_parquet(out_dir / "c4_zcta5_cbp.parquet", index=False)

    with monkeypatch.context() as m:
        m.setattr("app.variable_registry.get_variable",
                  lambda k: {"value_cols": r_cols})
        out = zcta5_cbp.merge_results(task_dir, variables=["cbp_zcta5"])
    assert out == out_dir / "result_zcta5_cbp.csv"
    assert out.exists()


def test_cli_accepts_variables_comma_list(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: dict = {}

    def fake_run(td: Path, variables: list[str] | None = None) -> int:
        called["task_dir"] = td
        called["variables"] = variables
        return 0
    monkeypatch.setattr(zcta5_cbp, "run", fake_run)

    rc = zcta5_cbp._cli_main(
        ["zcta5_cbp", "run", str(task_dir), "--variables", "cbp_zcta5"]
    )
    assert rc == 0
    assert called["task_dir"] == task_dir
    assert called["variables"] == ["cbp_zcta5"]
