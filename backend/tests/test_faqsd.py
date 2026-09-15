"""faqsd runner — mirror of test_fara_tract.py.

faqsd shares fara_tract's C3 step and TRACT_FARA cache namespace on purpose
(identical tract weight table); the C4 step, template, parquet map, sanity
probe, and the o3/pm25 -> faqsd_o3/faqsd_pm25 rename in merge_results are
its own.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from app.experiments import faqsd


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task_S11"
    d.mkdir()
    (d / "input.csv").write_text(
        "pid,startDate,endDate,long,lat\n"
        "p1,2017-01-01,2017-12-31,-87.6,41.9\n"
        "p1,2018-01-01,2018-12-31,-87.7,41.8\n"
        "p2,2017-06-01,2018-05-31,-86.2,39.8\n"
    )
    (d / "config.json").write_text(json.dumps({
        "variables": ["faqsd"],
        "buffer": {"size": 270, "raster_res_m": 25},
    }))
    return d


def test_plan_is_c3_then_c4(task_dir: Path) -> None:
    config = json.loads((task_dir / "config.json").read_text())
    steps = faqsd.plan(config)
    assert [s.name for s in steps] == ["c3_tract_us", "c4_tract_faqsd"]
    assert steps[0].is_c3 is True
    assert steps[1].is_c3 is False


def test_plan_rejects_unknown_variable(task_dir: Path) -> None:
    with pytest.raises(ValueError, match="unknown variable"):
        faqsd.plan({"variables": ["ndi"]})  # ndi belongs to bg_ndi_wi


def test_plan_rejects_empty_variables(task_dir: Path) -> None:
    with pytest.raises(ValueError, match="at least one variable"):
        faqsd.plan({"variables": []})


def test_csv_to_parquet_adds_episode_id(task_dir: Path) -> None:
    # faqsd reuses zcta5_cbp.csv_to_parquet directly — sanity-check
    # that path by hand to lock the contract.
    from app.experiments.zcta5_cbp import csv_to_parquet
    src = task_dir / "input.csv"
    dst = task_dir / "input.parquet"
    csv_to_parquet(src, dst)
    df = pd.read_parquet(dst)
    assert "episode_id" in df.columns
    assert df["episode_id"].tolist() == [0, 1, 2]


def test_render_yaml_injects_output_grouping_episode(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    templates = tmp_path / "configs"
    (templates / "c3").mkdir(parents=True)
    (templates / "c4").mkdir(parents=True)
    (templates / "c3" / "tract_us_demo.yaml").write_text(yaml.safe_dump({
        "name": "c3_tract_us_demo",
        "source": {"file": ["t1.shp", "t2.shp"], "join_col": "GEOID10"},
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270,
                   "raster_res_m": 25},
        "engine": {"backend": "duckdb"},
        "output": {"path": "PLACEHOLDER"},
    }))
    (templates / "c4" / "tract_faqsd_demo.yaml").write_text(yaml.safe_dump({
        "name": "c4_tract_faqsd_demo",
        "linkage_pattern": "faqsd",
        "source": {"file": "PLACEHOLDER", "join_col": "GEOID10"},
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "exposure": {"file": "FAQSD/C4", "value_cols": ["o3", "pm25"]},
        "plugin": "faqsd",
        "time": {"years": [2017], "temporal_resolution": "yearly",
                 "temporal_mode": "yearly"},
        "output": {"path": "PLACEHOLDER"},
    }))
    import app.config as cfgmod
    monkeypatch.setattr(cfgmod.settings, "SPACESCANS_CONFIG_TEMPLATES_DIR",
                        templates, raising=False)

    cfg = {"buffer": {"size": 1500, "raster_res_m": 25}}
    c3_path = faqsd.render_yaml(faqsd._C3_STEP, task_dir, cfg)
    rendered = yaml.safe_load(c3_path.read_text())
    # C3 step doesn't get output_grouping (template has no time block in this
    # test fixture — but real template has none either, so the runner only
    # injects when time is already present).
    assert rendered["buffer"]["buffer_m"] == 1500
    # Source is unmodified on C3 (the C3 step reads bundled tract shapefiles).
    assert rendered["source"]["join_col"] == "GEOID10"


def test_render_yaml_c4_rewrites_source_file_to_c3_output(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """C4 step rewrites source.file (NOT exposure.file) to point at the
    per-task C3 buffer270mTRACT25m parquet. Same delta as fara_tract
    from tiger_proximity, which rewrote exposure.file instead.
    """
    templates = tmp_path / "configs"
    (templates / "c3").mkdir(parents=True)
    (templates / "c4").mkdir(parents=True)
    (templates / "c3" / "tract_us_demo.yaml").write_text(yaml.safe_dump({
        "name": "c3_tract_us_demo",
        "source": {"file": ["t1.shp"], "join_col": "GEOID10"},
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270,
                   "raster_res_m": 25},
        "output": {"path": "PLACEHOLDER"},
    }))
    (templates / "c4" / "tract_faqsd_demo.yaml").write_text(yaml.safe_dump({
        "name": "c4_tract_faqsd_demo",
        "linkage_pattern": "faqsd",
        "source": {"file": "PLACEHOLDER_C3_OUTPUT", "join_col": "GEOID10"},
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "exposure": {"file": "FAQSD/C4", "value_cols": ["o3", "pm25"]},
        "plugin": "faqsd",
        "time": {"years": [2017], "temporal_resolution": "yearly",
                 "temporal_mode": "yearly"},
        "output": {"path": "PLACEHOLDER"},
    }))
    import app.config as cfgmod
    monkeypatch.setattr(cfgmod.settings, "SPACESCANS_CONFIG_TEMPLATES_DIR",
                        templates, raising=False)

    cfg = {"buffer": {"size": 270, "raster_res_m": 25}}
    c4_path = faqsd.render_yaml(
        faqsd._VARIABLE_TO_STEP["faqsd"], task_dir, cfg
    )
    rendered = yaml.safe_load(c4_path.read_text())
    # source.file must point at C3 output for this task.
    expected_source = str(task_dir / "output" / "c3_tract_us.parquet")
    assert rendered["source"]["file"] == expected_source
    # exposure.file is NOT rewritten — FAQSD/C4 is a system-wide static resolved by --data-dir.
    assert rendered["exposure"]["file"] == "FAQSD/C4"
    # time.output_grouping injected.
    assert rendered["time"]["output_grouping"] == "episode"
    # output path rewritten to task local.
    assert rendered["output"]["path"] == str(
        task_dir / "output" / "c4_tract_faqsd.parquet"
    )


def test_render_yaml_c4_rejects_unexpected_source_shape(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Guards the R4 invariant: source: must be a dict (the C4 step
    rewrites cfg['source']['file']) — a list-shaped source: would silently
    discard the rewrite."""
    templates = tmp_path / "configs"
    (templates / "c4").mkdir(parents=True)
    (templates / "c4" / "tract_faqsd_demo.yaml").write_text(yaml.safe_dump({
        "name": "c4_tract_faqsd_demo",
        "linkage_pattern": "faqsd",
        "source": ["bad", "list", "shape"],  # spec R4 trip-wire
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "exposure": {"file": "FAQSD/C4", "value_cols": ["o3", "pm25"]},
        "plugin": "faqsd",
        "time": {"years": [2017]},
        "output": {"path": "PLACEHOLDER"},
    }))
    import app.config as cfgmod
    monkeypatch.setattr(cfgmod.settings, "SPACESCANS_CONFIG_TEMPLATES_DIR",
                        templates, raising=False)

    cfg = {"buffer": {"size": 270, "raster_res_m": 25}}
    with pytest.raises(RuntimeError, match="unexpected source"):
        faqsd.render_yaml(
            faqsd._VARIABLE_TO_STEP["faqsd"], task_dir, cfg
        )


def test_cache_key_contains_tract_fara_boundary(task_dir: Path) -> None:
    from app.experiments.zcta5_cbp import csv_to_parquet
    csv_to_parquet(task_dir / "input.csv", task_dir / "input.parquet")
    key = faqsd._cache_key(
        task_dir / "input.parquet",
        faqsd._C3_STEP,
        {"buffer": {"size": 270, "raster_res_m": 25}},
    )
    parts = key.split("__")
    assert parts[1] == "TRACT_FARA"
    assert parts[2] == "b270m"
    # Raster suffix pins the grid resolution — the C3 now honors the user's setting.
    assert parts[3] == "r25m"
    assert len(parts) == 4


def test_merge_results_renames_then_delegates(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """faqsd.merge_results renames the reader's o3/pm25 to faqsd_o3/faqsd_pm25
    (ACAG also emits pm25; result.csv is one flat table) and then delegates
    to _merge.write_partial. Inject a fake C4 parquet in the reader's own
    column contract plus the (PATID, geoid) episode key; the rename must
    reach the parquet on disk, and the result must carry the new names.
    """
    out_dir = task_dir / "output"
    out_dir.mkdir()
    parquet = out_dir / "c4_tract_faqsd.parquet"
    pd.DataFrame({
        "PATID": ["p1", "p1", "p2"],
        "geoid": [0, 1, 2],
        "o3": [30.0, 31.0, 32.0],
        "pm25": [5.0, 6.0, 7.0],
    }).to_parquet(parquet, index=False)
    with monkeypatch.context() as m:
        m.setattr("app.variable_registry.get_variable",
                  lambda k: {"value_cols": ["faqsd_o3", "faqsd_pm25"]})
        out = faqsd.merge_results(task_dir, variables=["faqsd"])
    assert out == out_dir / "result_faqsd.csv"
    assert set(pd.read_parquet(parquet).columns) == {"PATID", "geoid", "faqsd_o3", "faqsd_pm25"}
    result = pd.read_csv(out)
    assert {"faqsd_o3", "faqsd_pm25"} <= set(result.columns)
    assert "o3" not in result.columns and "pm25" not in result.columns
    assert result["faqsd_o3"].tolist() == [30.0, 31.0, 32.0]


def test_cli_accepts_variables_comma_list(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: dict = {}

    def fake_run(td: Path, variables: list[str] | None = None) -> int:
        called["task_dir"] = td
        called["variables"] = variables
        return 0
    monkeypatch.setattr(faqsd, "run", fake_run)

    rc = faqsd._cli_main(
        ["faqsd", "run", str(task_dir), "--variables", "faqsd"]
    )
    assert rc == 0
    assert called["task_dir"] == task_dir
    assert called["variables"] == ["faqsd"]


def test_sanity_check_passes_with_phase_a_installed() -> None:
    """Phase A landed output_grouping dispatch into spacescans.linkage.fara_linkage
    on pkg/pypi-only. The runner's sanity probe must not raise in a healthy env.
    """
    faqsd._sanity_check_pipeline_supports_faqsd_episode()


def test_sanity_check_raises_when_pipeline_lacks_phase_a(monkeypatch):
    """Mock out spacescans.linkage.fara_linkage with a stripped source string
    and verify the runner refuses to start. Patches faqsd.inspect (the
    runner module's own inspect reference) since the import is module-level.
    """
    class _FakeInspect:
        @staticmethod
        def getsource(_mod):
            # Simulate a stale wheel: source lacks the substring the
            # sanity probe greps for. Do NOT include the substring
            # 'output_grouping' anywhere in this string, even in
            # comments, or the probe will return cleanly.
            return (
                "@register_pattern('faqsd')\n"
                "def run_faqsd(config, engine):\n"
                "    pass  # stale wheel: legacy patient-only aggregation\n"
            )

    monkeypatch.setattr(faqsd, "inspect", _FakeInspect)
    with pytest.raises(RuntimeError, match="output_grouping"):
        faqsd._sanity_check_pipeline_supports_faqsd_episode()
