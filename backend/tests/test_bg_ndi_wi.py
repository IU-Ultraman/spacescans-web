import pytest
from app.experiments.bg_ndi_wi import plan, PipelineStep

def test_plan_with_both_variables():
    steps = plan({"variables": ["ndi", "walkability"], "buffer": {"size": 270, "raster_res_m": 25}})
    assert [s.name for s in steps] == ["c3_bg", "c4_ndi", "c4_wi"]
    assert [s.is_c3 for s in steps] == [True, False, False]
    assert steps[0].template_relpath == "c3/bg_us_demo.yaml"
    assert steps[1].template_relpath == "c4/bg_ndi_demo.yaml"
    assert steps[2].template_relpath == "c4/bg_wi_demo.yaml"

def test_plan_with_ndi_only():
    steps = plan({"variables": ["ndi"], "buffer": {"size": 270, "raster_res_m": 25}})
    assert [s.name for s in steps] == ["c3_bg", "c4_ndi"]

def test_plan_with_walkability_only():
    steps = plan({"variables": ["walkability"], "buffer": {"size": 270, "raster_res_m": 25}})
    assert [s.name for s in steps] == ["c3_bg", "c4_wi"]

def test_plan_with_no_variables_raises():
    with pytest.raises(ValueError, match="at least one variable"):
        plan({"variables": [], "buffer": {"size": 270, "raster_res_m": 25}})

def test_plan_with_unknown_variable_raises():
    with pytest.raises(ValueError, match="unknown variable.*pm25"):
        plan({"variables": ["ndi", "pm25"], "buffer": {"size": 270, "raster_res_m": 25}})


from pathlib import Path
import pandas as pd
from app.experiments.bg_ndi_wi import csv_to_parquet

def test_csv_to_parquet_preserves_fips(tmp_path):
    src = tmp_path / "input.csv"
    src.write_text(
        "pid,startDate,endDate,longitude,latitude,state_fips,county_fips,tract_geoid,bg_geoid\n"
        "PID0000001,2017-08-19,2017-11-11,-93.028635,45.088976,06,06037,06037263400,060372634001\n"
        "PID0000002,2017-03-24,2017-06-21,-95.345115,29.738952,48,48201,48201451601,482014516012\n"
    )
    dst = tmp_path / "input.parquet"
    csv_to_parquet(src, dst)

    df = pd.read_parquet(dst)
    assert df.shape == (2, 9)
    # pandas 2.x stores str as object; pandas 3.x infers `str` dtype by default.
    # Either is acceptable as long as values round-trip as strings with leading zeros.
    assert df["state_fips"].dtype == object or pd.api.types.is_string_dtype(df["state_fips"])
    assert df["state_fips"].iloc[0] == "06"  # leading zero preserved
    assert df["county_fips"].iloc[0] == "06037"
    assert df["bg_geoid"].iloc[0] == "060372634001"
    assert pd.api.types.is_datetime64_any_dtype(df["startDate"])
    assert pd.api.types.is_datetime64_any_dtype(df["endDate"])

def test_csv_to_parquet_works_without_optional_fips(tmp_path):
    src = tmp_path / "input.csv"
    src.write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "PID0000001,2017-08-19,2017-11-11,-93.028635,45.088976\n"
    )
    dst = tmp_path / "input.parquet"
    csv_to_parquet(src, dst)
    df = pd.read_parquet(dst)
    assert df.shape == (1, 5)
    assert pd.api.types.is_datetime64_any_dtype(df["startDate"])

def test_csv_to_parquet_rejects_malformed_dates(tmp_path):
    src = tmp_path / "input.csv"
    src.write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "PID0000001,not-a-date,2017-11-11,-93.0,45.0\n"
    )
    dst = tmp_path / "input.parquet"
    import pytest
    with pytest.raises((ValueError, pd.errors.ParserError)):
        csv_to_parquet(src, dst)


import yaml
from app.experiments.bg_ndi_wi import render_yaml, _C3_STEP, _VARIABLE_TO_STEP

@pytest.fixture
def fake_template_dir(tmp_path, monkeypatch):
    # Stub minimal C3 / C4 templates that mimic the real pipeline configs.
    c3 = tmp_path / "c3" / "bg_us_demo.yaml"
    c3.parent.mkdir(parents=True)
    c3.write_text(
        "name: bg_us_demo\n"
        "linkage_pattern: boundary_overlap_fast\n"
        "source:\n  file: data_full/BG_FL/C3/...\n  join_col: GEOID10\n"
        "buffer:\n"
        "  patient_file: data_full/demo_patients_conus_fast_100000.parquet\n"
        "  patient_adapter: demo_conus\n"
        "  buffer_m: 270\n"
        "  raster_res_m: 25\n"
        "output:\n  path: output/bg_us_demo.parquet\n"
    )
    c4 = tmp_path / "c4" / "bg_ndi_demo.yaml"
    c4.parent.mkdir(parents=True)
    c4.write_text(
        "name: bg_ndi_demo\n"
        "linkage_pattern: yearly_areal\n"
        "source:\n  file: data_full/BG_NDI/C4/ndi.Rda\n"
        "buffer:\n"
        "  patient_file: data_full/demo_patients_conus_fast_100000.parquet\n"
        "  patient_adapter: demo_conus\n"
        "  buffer_m: 270\n"
        "output:\n  path: output/bg_ndi_demo.parquet\n"
    )

    import app.config
    monkeypatch.setattr(app.config.settings, "SPACESCANS_CONFIG_TEMPLATES_DIR", tmp_path)
    return tmp_path


def test_render_yaml_c3_injects_all_five_keys(fake_template_dir, tmp_path):
    task_dir = tmp_path / "task-12345678"
    task_dir.mkdir()
    user_config = {"buffer": {"size": 500, "raster_res_m": 50}}

    out = render_yaml(_C3_STEP, task_dir, user_config)

    assert out == task_dir / "pipeline_configs" / "c3_bg.yaml"
    cfg = yaml.safe_load(out.read_text())
    assert cfg["name"].startswith("bg_us_demo_task_")
    assert cfg["buffer"]["patient_file"] == str(task_dir / "input.parquet")
    assert cfg["buffer"]["patient_adapter"] == "demo_conus"  # preserved
    assert cfg["buffer"]["buffer_m"] == 500
    assert cfg["buffer"]["raster_res_m"] == 50
    assert cfg["output"]["path"] == str(task_dir / "output" / "c3_bg.parquet")
    # source.file is left alone — pipeline resolves it via --data-dir
    assert cfg["source"]["file"] == "data_full/BG_FL/C3/..."
    # Preservation: keys not in the 5 injection points must round-trip unchanged.
    assert cfg["linkage_pattern"] == "boundary_overlap_fast"
    assert cfg["source"]["join_col"] == "GEOID10"


def test_render_yaml_c4_skips_raster_res_m(fake_template_dir, tmp_path):
    task_dir = tmp_path / "task-12345678"
    task_dir.mkdir()
    step = _VARIABLE_TO_STEP["ndi"]
    user_config = {"buffer": {"size": 270, "raster_res_m": 25}}

    out = render_yaml(step, task_dir, user_config)

    cfg = yaml.safe_load(out.read_text())
    # The fake C4 template does not have raster_res_m and rendering must not
    # add it (C4 doesn't use rasterization).
    assert "raster_res_m" not in cfg["buffer"]
    # Preservation: C4 template's source.file must round-trip unchanged.
    assert cfg["source"]["file"] == "data_full/BG_NDI/C4/ndi.Rda"
    assert cfg["linkage_pattern"] == "yearly_areal"
