"""The custom-exposome runner shim: planning from the task's definitions, and a run.

What these pin, in order of how badly each would bite:

  * one C3 per distinct boundary (or raster grid), reusing the shipped runner's
    step name and cache tag, so a custom Tract variable reuses FARA's cached
    tract weights instead of recomputing them;
  * one C4 per variable, in request order; the definitions come from
    ``config.json["custom_variables"]`` (the config endpoint's snapshot);
  * the run goes through ``app.experiments._adapter`` like every other runner,
    plus the per-column linkage report the web logs under source "merge".

Rendering, cache keys, value materialisation and the coverage diagnosis moved
to ``spacescans.custom`` / ``spacescans.catalog`` and are tested there (the
package's custom web-parity suite holds them to web 3991c3b).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from app.experiments import custom

TRACT_DEF = {
    "label": "My greenness",
    "boundary": "Tract",
    "join_col": "GEOID10",
    "key_col": "tract",
    "year_col": None,
    "value_cols": ["greenness", "heat"],
    "values_path": "/lib/user-1/ab12cd34/values.csv",
    "coverage_years": [2013, 2019],
    "experiment": "custom",
}
BG_DEF = {**TRACT_DEF, "boundary": "BG", "label": "My BG index",
          "value_cols": ["idx"], "values_path": "/lib/user-1/beefbeef/values.csv"}
YEARLY_DEF = {**TRACT_DEF, "year_col": "year", "value_cols": ["greenness"],
              "coverage_years": [2015, 2017],
              "values_path": "/lib/user-1/cafecafe/values.csv"}

A = "custom_ab12cd34"
B = "custom_beefbeef"
C = "custom_cafecafe"


def _config(variables, definitions, buffer_m=270, raster_res_m=25):
    return {
        "variables": list(variables),
        "buffer": {"size": buffer_m, "raster_res_m": raster_res_m},
        "custom_variables": definitions,
    }


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------

def test_plan_emits_one_c3_then_one_c4_per_variable():
    steps = custom.plan(_config([A], {A: TRACT_DEF}))
    assert [s.name for s in steps] == ["c3_tract_us", f"c4_{A}"]
    assert [s.is_c3 for s in steps] == [True, False]
    assert steps[1].template_relpath == "c4/custom_areal.yaml"


def test_two_datasets_on_one_boundary_share_a_single_c3():
    other = f"{A}x"
    cfg = _config([A, other], {A: TRACT_DEF, other: {**TRACT_DEF, "label": "Second"}})
    steps = custom.plan(cfg)
    assert [s.name for s in steps] == ["c3_tract_us", f"c4_{A}", f"c4_{other}"]


def test_datasets_on_different_boundaries_each_get_their_c3():
    steps = custom.plan(_config([A, B], {A: TRACT_DEF, B: BG_DEF}))
    assert [s.name for s in steps] == ["c3_tract_us", "c3_bg", f"c4_{A}", f"c4_{B}"]


def test_plan_reuses_the_shipped_c3_steps_and_cache_tags():
    """Sharing the step name and cache tag is what makes the C3 cache shared."""
    from app.experiments import bg_ndi_wi, fara_tract, zcta5_cbp
    buffer = {"size": 270, "raster_res_m": 25}
    tract = custom.plan(_config([A], {A: TRACT_DEF}))[0]
    bg = custom.plan(_config([B], {B: BG_DEF}))[0]
    zcta = custom.plan(_config([C], {C: {**TRACT_DEF, "boundary": "ZCTA5"}}))[0]
    shipped = {
        "Tract": fara_tract.plan({"variables": ["fara_tract"], "buffer": buffer})[0],
        "BG": bg_ndi_wi.plan({"variables": ["walkability"], "buffer": buffer})[0],
        "ZCTA5": zcta5_cbp.plan({"variables": ["cbp_zcta5"], "buffer": buffer})[0],
    }
    for ours, theirs in ((tract, shipped["Tract"]), (bg, shipped["BG"]), (zcta, shipped["ZCTA5"])):
        # same step name, template, tag and raster rule -> the same legacy cache key. The custom
        # YAML also sets time.output_grouping on the C3 step (the web's custom runner always did).
        assert (ours.name, ours.template_relpath, ours.cache_tag, ours.uses_raster_res) == \
            (theirs.name, theirs.template_relpath, theirs.cache_tag, theirs.uses_raster_res)
    assert (tract.cache_tag, bg.cache_tag, zcta.cache_tag) == ("TRACT_FARA", "BG", "ZCTA5")
    assert all(s.uses_raster_res for s in (tract, bg, zcta))


def test_plan_rejects_an_empty_selection():
    with pytest.raises(ValueError, match="at least one variable"):
        custom.plan(_config([], {}))


def test_plan_rejects_a_variable_with_no_definition():
    """The config endpoint resolves definitions; a missing one means the task
    config was written without them, and running would link nothing."""
    with pytest.raises(ValueError, match="no definition"):
        custom.plan(_config([A], {}))


def test_plan_rejects_an_unsupported_boundary():
    with pytest.raises(ValueError, match="unsupported boundary"):
        custom.plan(_config([A], {A: {**TRACT_DEF, "boundary": "Parcel"}}))


def test_plan_rejects_a_malformed_snapshot():
    with pytest.raises(ValueError, match="custom_variables is not a mapping"):
        custom.plan({"variables": [A], "buffer": {"size": 270}, "custom_variables": [TRACT_DEF]})


# --------------------------------------------------------------------------
# registry overlay (app.variable_registry reads the same snapshot)
# --------------------------------------------------------------------------

def _task_with_config(tmp_path, config) -> Path:
    task_dir = tmp_path / "task-abcdef12"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "config.json").write_text(json.dumps(config))
    return task_dir


def test_overlay_makes_a_custom_key_resolvable(tmp_path):
    from app import variable_registry
    task_dir = _task_with_config(tmp_path, _config([A], {A: TRACT_DEF}))
    assert variable_registry.get_variable(A, task_dir=task_dir)["value_cols"] == [
        "greenness", "heat"
    ]
    assert variable_registry.variables_by_experiment(
        [A], task_dir=task_dir
    ) == {"custom": [A]}


def test_overlay_does_not_leak_into_the_shipped_catalog(tmp_path):
    from app import variable_registry
    task_dir = _task_with_config(tmp_path, _config([A], {A: TRACT_DEF}))
    variable_registry.load_variables(task_dir=task_dir)
    plain = variable_registry.load_variables()
    assert A not in plain["variables"]
    with pytest.raises(KeyError):
        variable_registry.get_variable(A)


def test_custom_and_shipped_variables_group_into_separate_experiments(tmp_path):
    from app import variable_registry
    task_dir = _task_with_config(tmp_path, _config([A, "ndi"], {A: TRACT_DEF}))
    grouped = variable_registry.variables_by_experiment(
        [A, "ndi"], task_dir=task_dir
    )
    assert grouped["custom"] == [A]
    assert grouped["bg_ndi_wi"] == ["ndi"]


def test_an_unknown_key_now_raises_instead_of_being_dropped(tmp_path):
    """It used to be skipped silently: the loop walks the catalog and keeps
    what is in `keys`, so a task ran with fewer variables and reported success."""
    from app import variable_registry
    with pytest.raises(KeyError, match="no catalog knows"):
        variable_registry.variables_by_experiment(["custom_deadbeef"])


def test_a_task_without_custom_variables_is_unaffected(tmp_path):
    from app import variable_registry
    task_dir = _task_with_config(tmp_path, {"variables": ["ndi"], "buffer": {"size": 270}})
    assert variable_registry.load_variables(task_dir=task_dir) is (
        variable_registry.load_variables()
    )


def test_a_malformed_config_is_reported_not_swallowed(tmp_path):
    from app import variable_registry
    task_dir = tmp_path / "task-badcfg11"
    task_dir.mkdir(parents=True)
    (task_dir / "config.json").write_text("{ truncated")
    with pytest.raises(variable_registry.MetadataSchemaError, match="readable JSON"):
        variable_registry.load_variables(task_dir=task_dir)


# --------------------------------------------------------------------------
# raster datasets
# --------------------------------------------------------------------------

def _raster_def(grid_hash="abcd1234", col="ndvi", years=(None,)):
    rasters = [{"path": f"/lib/user-1/r/{y or 'static'}.tif", "year": y,
                "uploaded_filename": "r.tif", "sha256": "x", "bytes": 1} for y in years]
    return {
        "label": "My raster", "boundary": "Point", "geometry": "raster",
        "join_col": "grid_id", "key_col": "grid_id",
        "year_col": None if years == (None,) else "year",
        "value_cols": [col], "values_path": None, "rasters": rasters, "band": 1,
        "grid_hash": grid_hash,
        "grid": {"width": 5, "height": 4, "nodata": None,
                 "bounds_wgs84": [-85.0, 30.96, -84.95, 31.0]},
        "coverage_years": [2013, 2019] if years == (None,) else [min(years), max(years)],
        "experiment": "custom",
    }


R = "custom_raster01"


def test_plan_gives_a_raster_its_own_c3_named_by_grid():
    steps = custom.plan(_config([R], {R: _raster_def()}))
    assert [s.name for s in steps] == ["c3_customgrid_abcd1234", f"c4_{R}"]
    assert steps[0].template_relpath == "c3/custom_grid.yaml"
    assert steps[0].cache_tag == "CUSTOMGRIDND_abcd1234"  # R1-F1: nodata-free grid tag
    assert steps[0].uses_raster_res is False            # grid_weights: no __r suffix
    assert steps[1].materialise_values is True


def test_two_rasters_on_one_grid_share_the_c3():
    other = f"{R}b"
    cfg = _config([R, other], {R: _raster_def(), other: _raster_def(col="heat")})
    assert [s.name for s in custom.plan(cfg)] == ["c3_customgrid_abcd1234", f"c4_{R}", f"c4_{other}"]


def test_raster_and_polygon_get_separate_c3s():
    cfg = _config([R, A], {R: _raster_def(), A: TRACT_DEF})
    assert [s.name for s in custom.plan(cfg)] == [
        "c3_customgrid_abcd1234", "c3_tract_us", f"c4_{R}", f"c4_{A}"]


# --------------------------------------------------------------------------
# a run through the adapter (fake pipeline CLI)
# --------------------------------------------------------------------------

@pytest.fixture
def fake_cli(monkeypatch, tmp_path):
    import app.config

    (tmp_path / "data").mkdir()
    monkeypatch.setattr(app.config.settings, "SPACESCANS_PIPELINE_CLI",
                        Path(__file__).parent / "fixtures" / "fake_spacescans.py")
    monkeypatch.setattr(app.config.settings, "SPACESCANS_PIPELINE_PYTHON", Path(sys.executable))
    monkeypatch.setattr(app.config.settings, "SPACESCANS_DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(app.config.settings, "DATA_DIR", tmp_path / "appdata")
    monkeypatch.setattr(app.config.settings, "C3_CACHE_DIR", tmp_path / "appdata" / "c3_cache")
    return tmp_path


def test_run_links_two_polygon_datasets_and_reports_the_linkage_rate(fake_cli):
    values = fake_cli / "values.csv"
    values.write_text("tract,greenness,heat\n12073000200,0.5,80\n")
    definition = {**TRACT_DEF, "values_path": str(values)}
    other = f"{A}x"
    task_dir = fake_cli / "task-custom001"
    (task_dir / "output").mkdir(parents=True)
    (task_dir / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-84.3,30.45\nP2,2017-01-01,2017-12-31,-84.2,30.4\n")
    (task_dir / "config.json").write_text(json.dumps(
        {**_config([A, other], {A: definition, other: {**definition, "label": "Second"}}),
         "experiment": "auto"}))

    assert custom.run(task_dir, variables=[A, other]) == 0

    logs = [json.loads(l) for l in (task_dir / "logs.jsonl").read_text().splitlines()]
    spawned = [e["msg"].split(":")[0] for e in logs if e["msg"].startswith("spawning ")]
    assert spawned == ["spawning c3_tract_us", f"spawning c4_{A}", f"spawning c4_{other}"]
    cache = [e["msg"] for e in logs if e["msg"].startswith("cache write: ")]
    assert len(cache) == 1 and cache[0].endswith("__TRACT_FARA__b270m__r25m.parquet")
    merge = [e for e in logs if e["source"] == "merge"]
    # the fake CLI emits a `value` column, so the web's report says each value column is missing
    assert [e["level"] for e in merge] == ["warning"] * 4
    assert merge[0]["msg"] == f"{A}: value column 'greenness' missing from output"
    assert merge[2]["msg"] == f"{other}: value column 'greenness' missing from output"
    slot = json.loads((task_dir / "status.json").read_text())["experiments"]["custom"]
    assert slot["steps"] == ["c3_tract_us", f"c4_{A}", f"c4_{other}"]
    assert slot["progress"] == 1.0 and slot["message"] == "Completed 3 pipeline steps"
    partial = pd.read_csv(task_dir / "output" / "result_custom.csv")
    assert list(partial.columns) == ["pid", "episode_id"] and len(partial) == 2
    import yaml
    c4 = yaml.safe_load((task_dir / "pipeline_configs" / f"c4_{A}.yaml").read_text())
    assert c4["linkage_pattern"] == "static_areal"
    assert c4["source"] == {"file": str(task_dir / "output" / "c3_tract_us.parquet"),
                            "join_col": "GEOID10"}
    assert c4["exposure"] == {"file": str(values), "join_col": "tract",
                              "value_cols": ["greenness", "heat"]}
    assert c4["time"]["output_grouping"] == "episode"
