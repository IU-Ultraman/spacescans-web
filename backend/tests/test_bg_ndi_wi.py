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
