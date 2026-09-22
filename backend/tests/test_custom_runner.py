"""The generic custom-exposome runner: planning, rendering, cache sharing.

What these pin, in order of how badly each would bite:

  * output_grouping is always "episode". static_areal feeds it into
    DurationWeightedSpec.group_by_episode; the "patient" default collapses a
    patient's episodes into one row and _merge.write_partial then has no geoid
    to rename to episode_id. ACAG and FAQSD each shipped this defect once.
  * the C3 cache tag equals the shipped runner's for that boundary, so a custom
    Tract variable reuses FARA's cached weights instead of recomputing them.
  * static_areal vs yearly_areal is chosen by the presence of a year column.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

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


def test_two_datasets_on_one_boundary_share_a_single_c3():
    other = f"{A}x"
    cfg = _config([A, other], {A: TRACT_DEF, other: {**TRACT_DEF, "label": "Second"}})
    steps = custom.plan(cfg)
    assert [s.name for s in steps] == ["c3_tract_us", f"c4_{A}", f"c4_{other}"]


def test_datasets_on_different_boundaries_each_get_their_c3():
    steps = custom.plan(_config([A, B], {A: TRACT_DEF, B: BG_DEF}))
    assert [s.name for s in steps] == ["c3_tract_us", "c3_bg", f"c4_{A}", f"c4_{B}"]


def test_plan_reuses_the_shipped_c3_step_names():
    """Sharing the step name and cache tag is what makes the C3 cache shared."""
    from app.experiments import fara_tract, bg_ndi_wi, zcta5_cbp
    assert custom.c3_step_for("Tract").name == fara_tract._C3_STEP.name
    assert custom.c3_step_for("BG").name == bg_ndi_wi._C3_STEP.name
    assert custom.c3_step_for("ZCTA5").name == zcta5_cbp._C3_STEP.name
    assert custom.BOUNDARY_C3["Tract"][2] == fara_tract._BOUNDARY
    assert custom.BOUNDARY_C3["BG"][2] == bg_ndi_wi._BOUNDARY
    assert custom.BOUNDARY_C3["ZCTA5"][2] == zcta5_cbp._BOUNDARY


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


# --------------------------------------------------------------------------
# render_yaml
# --------------------------------------------------------------------------

@pytest.fixture
def rendered(tmp_path, monkeypatch):
    """Render a step against the real templates and return the parsed YAML."""
    import app.config
    repo_configs = Path(__file__).resolve().parents[2] / "configs"
    monkeypatch.setattr(
        app.config.settings, "SPACESCANS_CONFIG_TEMPLATES_DIR", repo_configs
    )

    def _render(step, config, task_dir=None):
        task_dir = task_dir or (tmp_path / "task-abcdef12")
        task_dir.mkdir(parents=True, exist_ok=True)
        path = custom.render_yaml(step, task_dir, config)
        return yaml.safe_load(path.read_text()), task_dir

    return _render


def test_c4_static_dataset_renders_static_areal(rendered):
    cfg, task_dir = rendered(custom.c4_step_for(A), _config([A], {A: TRACT_DEF}))
    assert cfg["linkage_pattern"] == "static_areal"
    assert cfg["source"]["file"] == str(task_dir / "output" / "c3_tract_us.parquet")
    assert cfg["source"]["join_col"] == "GEOID10"
    assert cfg["exposure"]["file"] == TRACT_DEF["values_path"]
    assert cfg["exposure"]["join_col"] == "tract"
    assert cfg["exposure"]["value_cols"] == ["greenness", "heat"]
    assert "year_col" not in cfg["exposure"]
    assert "plugin" not in cfg          # no plugin -> generic read_table


def test_c4_yearly_dataset_renders_yearly_areal_with_its_years(rendered):
    cfg, _ = rendered(custom.c4_step_for(C), _config([C], {C: YEARLY_DEF}))
    assert cfg["linkage_pattern"] == "yearly_areal"
    assert cfg["exposure"]["year_col"] == "year"
    assert cfg["time"]["years"] == [2015, 2016, 2017]


def test_c4_always_sets_episode_grouping(rendered):
    """The defect ACAG and FAQSD each hit: 'patient' collapses episodes and the
    merge then raises KeyError on the missing geoid."""
    for key, definition in ((A, TRACT_DEF), (C, YEARLY_DEF)):
        cfg, _ = rendered(custom.c4_step_for(key), _config([key], {key: definition}))
        assert cfg["time"]["output_grouping"] == "episode"


def test_c3_gets_episode_grouping_and_the_task_buffer(rendered):
    cfg, task_dir = rendered(
        custom.c3_step_for("Tract"),
        _config([A], {A: TRACT_DEF}, buffer_m=500, raster_res_m=50),
    )
    assert cfg["buffer"]["buffer_m"] == 500
    # boundary_overlap_fast rasterises at this resolution, and it is part of
    # the cache key — the template's default must not survive.
    assert cfg["buffer"]["raster_res_m"] == 50
    assert cfg["buffer"]["patient_file"] == str(task_dir / "input.parquet")
    assert cfg["time"]["output_grouping"] == "episode"
    assert cfg["output"]["path"] == str(task_dir / "output" / "c3_tract_us.parquet")


def test_c3_source_stays_relative_for_the_data_dir(rendered):
    """The boundary shapefiles resolve against --data-dir; rewriting them to an
    absolute path would break every deployment whose data root differs."""
    cfg, _ = rendered(custom.c3_step_for("Tract"), _config([A], {A: TRACT_DEF}))
    files = cfg["source"]["file"]
    files = files if isinstance(files, list) else [files]
    assert all(not f.startswith("/") for f in files)


def test_render_names_the_config_after_the_task(rendered):
    cfg, _ = rendered(custom.c4_step_for(A), _config([A], {A: TRACT_DEF}))
    assert cfg["name"].endswith("_task_abcdef12")


# --------------------------------------------------------------------------
# cache key
# --------------------------------------------------------------------------

BUFFER = {"buffer": {"size": 270, "raster_res_m": 25}}


def test_cache_key_is_byte_identical_to_the_shipped_polygon_runners(tmp_path):
    """The whole cache-sharing claim rests on this. fara_tract appends a raster
    suffix; a key without it can never match, so the sharing would silently
    never happen and every custom Tract dataset would recompute the weights."""
    from app.experiments import fara_tract
    parquet = tmp_path / "input.parquet"
    parquet.write_bytes(b"cohort")
    theirs = fara_tract._cache_key(parquet, fara_tract._C3_STEP, BUFFER)
    ours = custom._cache_key(parquet, "TRACT_FARA", BUFFER)
    assert ours == theirs


def test_cache_key_matches_bg_too(tmp_path):
    from app.experiments import bg_ndi_wi
    parquet = tmp_path / "input.parquet"
    parquet.write_bytes(b"cohort")
    assert custom._cache_key(parquet, "BG", BUFFER) == bg_ndi_wi._cache_key(
        parquet, bg_ndi_wi._C3_STEP, BUFFER
    )


def test_cache_key_ignores_the_uploaded_file(tmp_path):
    """C4 is never cached, so the CSV must not enter the C3 key — otherwise two
    datasets on the same boundary would each recompute identical weights."""
    parquet = tmp_path / "input.parquet"
    parquet.write_bytes(b"cohort")
    assert (custom._cache_key(parquet, "TRACT_FARA", BUFFER)
            == custom._cache_key(parquet, "TRACT_FARA", BUFFER))


def test_cache_key_differs_per_boundary_buffer_and_raster(tmp_path):
    parquet = tmp_path / "input.parquet"
    parquet.write_bytes(b"cohort")
    base = custom._cache_key(parquet, "TRACT_FARA", BUFFER)
    assert base != custom._cache_key(parquet, "BG", BUFFER)
    assert base != custom._cache_key(
        parquet, "TRACT_FARA", {"buffer": {"size": 500, "raster_res_m": 25}})
    assert base != custom._cache_key(
        parquet, "TRACT_FARA", {"buffer": {"size": 270, "raster_res_m": 270}})


def test_boundary_tag_lookup_covers_every_c3_step():
    for boundary, (name, _template, tag) in custom.BOUNDARY_C3.items():
        step = custom.c3_step_for(boundary)
        assert custom._boundary_tag_for_step(step) == tag, boundary


def test_every_c3_template_referenced_actually_exists():
    configs = Path(__file__).resolve().parents[2] / "configs"
    for boundary, (_name, template, _tag) in custom.BOUNDARY_C3.items():
        assert (configs / template).is_file(), f"{boundary}: {template}"
    assert (configs / custom._C4_TEMPLATE).is_file()


# --------------------------------------------------------------------------
# registry overlay
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


def test_parquet_map_matches_the_c4_step_names():
    assert custom._parquet_map([A, C]) == {
        A: f"c4_{A}.parquet", C: f"c4_{C}.parquet",
    }


# --------------------------------------------------------------------------
# coverage diagnosis
# --------------------------------------------------------------------------

def _diagnosis_setup(tmp_path, touched, covered):
    """A task whose C3 weights touched `touched` and whose CSV covers `covered`."""
    import pandas as pd
    task_dir = tmp_path / "task-diag0001"
    (task_dir / "output").mkdir(parents=True)
    pd.DataFrame({"geoid": range(len(touched)), "GEOID10": touched,
                  "value": [1.0] * len(touched)}).to_parquet(
        task_dir / "output" / "c3_tract_us.parquet", index=False)
    values = tmp_path / "values.csv"
    values.write_text("tract,v\n" + "".join(f"{c},0.5\n" for c in covered))
    definition = {**TRACT_DEF, "values_path": str(values)}
    return task_dir, definition


def test_diagnosis_names_the_regions_when_nothing_overlaps(tmp_path):
    """The user's actual report: a Leon County file against a nationwide cohort,
    "0.0% linked" and no idea why."""
    touched = ["06037101110", "36061000100", "39035101100", "48201100000"]
    covered = ["12073000200", "12073000301"]
    task_dir, definition = _diagnosis_setup(tmp_path, touched, covered)
    msg = custom._coverage_diagnosis(task_dir, A, definition)
    assert "touch 4 distinct Tract codes across 4 states" in msg
    assert "06 (1)" in msg and "36 (1)" in msg
    assert "covers 2 codes across 1 state: 12 (2)" in msg
    assert "0 in common" in msg
    assert "does not cover where this cohort lives" in msg


def test_diagnosis_reports_partial_overlap(tmp_path):
    touched = ["12073000200", "12073000301", "06037101110"]
    covered = ["12073000200", "12073000301"]
    task_dir, definition = _diagnosis_setup(tmp_path, touched, covered)
    msg = custom._coverage_diagnosis(task_dir, A, definition)
    assert "2 in common" in msg
    assert "outside the file's geographies get no value" in msg


def test_diagnosis_never_raises(tmp_path):
    """Diagnostics run after the linkage; they must not turn a finished task
    into a failed one."""
    task_dir = tmp_path / "task-nofiles"
    task_dir.mkdir()
    msg = custom._coverage_diagnosis(task_dir, A, {**TRACT_DEF, "values_path": "/nope.csv"})
    assert msg.startswith(f"{A}: could not compare geographies")
