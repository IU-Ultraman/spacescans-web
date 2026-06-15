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


from app.experiments.bg_ndi_wi import parse_step_progress

def test_parse_step_progress_overlap_fast():
    line = "[overlap_fast] tile 7460/14938 ( 49.9%) elapsed=  1.64m  rate= 75.9/s  ETA= 1.64m  tiles_with_work=2807"
    assert parse_step_progress(line) == pytest.approx(0.499, abs=0.005)

def test_parse_step_progress_overlap_classic():
    line = "[overlap]   1600/3221 ( 49.7%)  elapsed=   2.0m  rate=13.20/s"
    assert parse_step_progress(line) == pytest.approx(0.497, abs=0.005)

def test_parse_step_progress_non_progress_returns_none():
    assert parse_step_progress("[overlap_fast] === SUMMARY ===") is None
    assert parse_step_progress("random log line") is None
    assert parse_step_progress("") is None


import json
import sys
from app.experiments.bg_ndi_wi import run_pipeline_step

@pytest.fixture
def fake_cli_settings(monkeypatch, tmp_path):
    """Point SPACESCANS_PIPELINE_CLI at the fake_spacescans.py fixture so the
    subprocess test does not need the real conda env."""
    fixture = Path(__file__).parent / "fixtures" / "fake_spacescans.py"
    import app.config
    monkeypatch.setattr(app.config.settings, "SPACESCANS_PIPELINE_CLI", fixture)
    monkeypatch.setattr(app.config.settings, "SPACESCANS_PIPELINE_PYTHON", Path(sys.executable))
    monkeypatch.setattr(app.config.settings, "SPACESCANS_DATA_DIR", tmp_path)
    return tmp_path


def _make_task(tmp_path, name="step.yaml") -> tuple[Path, Path]:
    task_dir = tmp_path / "task-deadbeef"
    task_dir.mkdir()
    (task_dir / "logs.jsonl").touch()
    yaml_path = task_dir / "pipeline_configs" / name
    yaml_path.parent.mkdir()
    yaml_path.write_text(yaml.safe_dump({
        "name": "fake",
        "output": {"path": str(task_dir / "output" / "step.parquet")},
    }))
    return task_dir, yaml_path


def test_run_pipeline_step_success(fake_cli_settings):
    task_dir, yaml_path = _make_task(fake_cli_settings)
    rc = run_pipeline_step(yaml_path, task_dir, step_name="c3_bg")
    assert rc == 0
    assert (task_dir / "output" / "step.parquet").exists()
    log_lines = (task_dir / "logs.jsonl").read_text().strip().split("\n")
    progress_lines = [json.loads(l) for l in log_lines if "tile" in l]
    assert len(progress_lines) >= 3
    # logs.jsonl rows are tagged with source = step name
    assert all(j["source"] == "c3_bg" for j in progress_lines)


def test_run_pipeline_step_nonzero_exit(fake_cli_settings):
    task_dir, yaml_path = _make_task(fake_cli_settings, name="fail_step.yaml")
    rc = run_pipeline_step(yaml_path, task_dir, step_name="c3_bg")
    assert rc != 0
    log_text = (task_dir / "logs.jsonl").read_text()
    assert "ERROR" in log_text or "exit code" in log_text


from app.experiments.bg_ndi_wi import merge_results

def _seed_task_for_merge(tmp_path, n_input=5, n_ndi=4, n_wi=3) -> Path:
    """Create a task_dir with input.csv + ndi/walkability parquets at common
    paths, so merge_results can be exercised without running the pipeline."""
    task_dir = tmp_path / "task-abcdef12"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    (task_dir / "logs.jsonl").touch()

    pids = [f"PID{i:07d}" for i in range(n_input)]
    pd.DataFrame({
        "pid": pids,
        "startDate": ["2017-01-01"] * n_input,
        "endDate": ["2017-12-31"] * n_input,
        "longitude": [-93.0] * n_input,
        "latitude": [45.0] * n_input,
    }).to_csv(task_dir / "input.csv", index=False)

    pd.DataFrame({
        "PATID": pids[:n_ndi],
        "ndi": [0.1 * i for i in range(n_ndi)],
    }).to_parquet(task_dir / "output" / "c4_ndi.parquet", index=False)

    pd.DataFrame({
        "PATID": pids[:n_wi],
        "NatWalkInd": [1.0 + i for i in range(n_wi)],
    }).to_parquet(task_dir / "output" / "c4_wi.parquet", index=False)

    return task_dir


def test_merge_results_both_variables(tmp_path):
    task_dir = _seed_task_for_merge(tmp_path, n_input=5, n_ndi=4, n_wi=3)
    out = merge_results(task_dir, variables=["ndi", "walkability"])

    assert out == task_dir / "output" / "result.csv"
    df = pd.read_csv(out)
    assert len(df) == 5
    assert "pid" in df.columns
    assert "ndi" in df.columns
    assert "NatWalkInd" in df.columns
    # First 3 patients matched both; pid #4 matched NDI only; pid #5 matched none.
    assert df["ndi"].isna().sum() == 1
    assert df["NatWalkInd"].isna().sum() == 2


def test_merge_results_ndi_only(tmp_path):
    task_dir = _seed_task_for_merge(tmp_path, n_input=3, n_ndi=3, n_wi=0)
    out = merge_results(task_dir, variables=["ndi"])
    df = pd.read_csv(out)
    assert len(df) == 3
    assert "ndi" in df.columns
    assert "NatWalkInd" not in df.columns


def test_merge_results_warns_on_low_match(tmp_path):
    """When only a small fraction of input patients have NDI values, a warning
    should be appended to logs.jsonl."""
    task_dir = _seed_task_for_merge(tmp_path, n_input=100, n_ndi=5, n_wi=0)
    merge_results(task_dir, variables=["ndi"])

    log_text = (task_dir / "logs.jsonl").read_text()
    assert "matched only" in log_text  # warning fired
    # 5 / 100 = 5% match rate
    assert "5.0%" in log_text
