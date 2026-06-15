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
