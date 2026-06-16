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
    # 9 original columns + episode_id added by Sprint 2 B1 invariant.
    assert df.shape == (2, 10)
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
    # 5 original columns + episode_id added by Sprint 2 B1 invariant.
    assert df.shape == (1, 6)
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
        "time:\n"
        "  years: [2017, 2018, 2019]\n"
        "  temporal_resolution: yearly\n"
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
    # Redirect the C3 weights cache into the test's tmp_path so cache-aware
    # runs don't pollute the real on-disk cache or pick up state across tests.
    cache_dir = tmp_path / "c3_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app.config.settings, "C3_CACHE_DIR", cache_dir)
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


def test_run_pipeline_step_invokes_on_progress(fake_cli_settings):
    """fake_spacescans emits 3 progress lines; on_progress must be called for each."""
    task_dir, yaml_path = _make_task(fake_cli_settings)
    fractions: list[float] = []
    rc = run_pipeline_step(yaml_path, task_dir, step_name="c3_bg",
                            on_progress=fractions.append)
    assert rc == 0
    # 3 progress lines: 1/3, 2/3, 3/3
    assert fractions == pytest.approx([1/3, 2/3, 1.0], abs=0.01)


from app.experiments.bg_ndi_wi import merge_results

def _seed_task_for_merge(tmp_path, n_input=5, n_ndi=4, n_wi=3) -> Path:
    """Create a task_dir with input.csv + ndi/walkability parquets at common
    paths, so merge_results can be exercised without running the pipeline.

    Sprint 2 pipeline contract: each pipeline parquet is one row per
    (PATID, episode_id) with the per-episode key carried in the ``geoid``
    column. The test fixtures mirror that — input CSV carries an episode_id
    (one episode per pid here for simplicity), pipeline parquets carry a
    matching ``geoid`` column.
    """
    task_dir = tmp_path / "task-abcdef12"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    (task_dir / "logs.jsonl").touch()

    pids = [f"PID{i:07d}" for i in range(n_input)]
    episode_ids = list(range(n_input))
    pd.DataFrame({
        "pid": pids,
        "startDate": ["2017-01-01"] * n_input,
        "endDate": ["2017-12-31"] * n_input,
        "longitude": [-93.0] * n_input,
        "latitude": [45.0] * n_input,
        "episode_id": episode_ids,
    }).to_csv(task_dir / "input.csv", index=False)

    pd.DataFrame({
        "PATID": pids[:n_ndi],
        "geoid": episode_ids[:n_ndi],
        "ndi": [0.1 * i for i in range(n_ndi)],
    }).to_parquet(task_dir / "output" / "c4_ndi.parquet", index=False)

    pd.DataFrame({
        "PATID": pids[:n_wi],
        "geoid": episode_ids[:n_wi],
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
    """When only a small fraction of input patients have NDI values, a
    structured ``merge_partial_low_match_pct`` warning should be appended to
    logs.jsonl. Format updated in Sprint 3 T5: emit JSON events instead of a
    human-readable substring (see app/experiments/_merge.py:_emit_log_warning)."""
    task_dir = _seed_task_for_merge(tmp_path, n_input=100, n_ndi=5, n_wi=0)
    merge_results(task_dir, variables=["ndi"])

    log_lines = (task_dir / "logs.jsonl").read_text().splitlines()
    events = [json.loads(line) for line in log_lines if line.strip()]
    low = [e for e in events if e.get("event") == "merge_partial_low_match_pct"]
    assert len(low) == 1
    # 5 / 100 = 5% match rate
    assert low[0]["match_pct"] == 5.0
    assert low[0]["cohort_n"] == 100
    assert low[0]["matched_n"] == 5


from app.experiments.bg_ndi_wi import run

def test_run_writes_status_file_on_completion(fake_template_dir, fake_cli_settings, tmp_path):
    # Re-stub templates dir to wherever fake_cli_settings put SPACESCANS_DATA_DIR;
    # both fixtures use the same tmp_path so they coexist.
    # The fake_template_dir fixture created c3/ and c4/ under tmp_path.
    # fake_cli_settings already monkeypatched CLI/PYTHON/DATA_DIR to tmp_path.
    # Now also monkeypatch templates dir to the same tmp_path.
    import app.config
    # (fake_template_dir already did this monkeypatch)

    task_dir = tmp_path / "task-runtest1"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    (task_dir / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
        "P2,2017-01-01,2017-12-31,-94.0,44.0\n"
    )
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))

    rc = run(task_dir)

    assert rc == 0
    status = json.loads((task_dir / "status.json").read_text())
    assert status["status"] == "finished"
    assert status["total_steps"] == 2  # c3_bg + c4_ndi
    assert (task_dir / "output" / "result.csv").exists()
    df = pd.read_csv(task_dir / "output" / "result.csv")
    assert len(df) == 2  # input rows preserved


def test_hash_input_parquet_is_deterministic(tmp_path):
    """Same bytes → same hash; one byte change → different hash."""
    from app.experiments.bg_ndi_wi import _hash_input_parquet

    p = tmp_path / "in.parquet"
    p.write_bytes(b"hello world" * 1000)
    h1 = _hash_input_parquet(p)
    h2 = _hash_input_parquet(p)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex digest

    p.write_bytes(b"hello WORLD" * 1000)  # one byte case change
    h3 = _hash_input_parquet(p)
    assert h3 != h1


def test_cache_key_stable_same_inputs(tmp_path):
    from app.experiments.bg_ndi_wi import _cache_key, _C3_STEP

    p = tmp_path / "in.parquet"
    p.write_bytes(b"\x00" * 4096)
    cfg = {"buffer": {"size": 270, "raster_res_m": 25}}
    k1 = _cache_key(p, _C3_STEP, cfg)
    k2 = _cache_key(p, _C3_STEP, cfg)
    assert k1 == k2


def test_cache_key_changes_on_input(tmp_path):
    from app.experiments.bg_ndi_wi import _cache_key, _C3_STEP

    p = tmp_path / "in.parquet"
    p.write_bytes(b"\x00" * 4096)
    cfg = {"buffer": {"size": 270, "raster_res_m": 25}}
    k1 = _cache_key(p, _C3_STEP, cfg)
    p.write_bytes(b"\x01" * 4096)
    k2 = _cache_key(p, _C3_STEP, cfg)
    assert k1 != k2


def test_cache_key_changes_on_buffer(tmp_path):
    from app.experiments.bg_ndi_wi import _cache_key, _C3_STEP

    p = tmp_path / "in.parquet"
    p.write_bytes(b"\x00" * 4096)
    k1 = _cache_key(p, _C3_STEP, {"buffer": {"size": 270, "raster_res_m": 25}})
    k2 = _cache_key(p, _C3_STEP, {"buffer": {"size": 500, "raster_res_m": 25}})
    assert k1 != k2


def test_cache_key_changes_on_raster(tmp_path):
    from app.experiments.bg_ndi_wi import _cache_key, _C3_STEP

    p = tmp_path / "in.parquet"
    p.write_bytes(b"\x00" * 4096)
    k1 = _cache_key(p, _C3_STEP, {"buffer": {"size": 270, "raster_res_m": 25}})
    k2 = _cache_key(p, _C3_STEP, {"buffer": {"size": 270, "raster_res_m": 50}})
    assert k1 != k2


def test_cache_key_format_human_readable(tmp_path):
    """Sanity-check the filename grammar so devs can identify cache entries."""
    from app.experiments.bg_ndi_wi import _cache_key, _C3_STEP

    p = tmp_path / "in.parquet"
    p.write_bytes(b"\x00" * 4096)
    k = _cache_key(p, _C3_STEP, {"buffer": {"size": 270, "raster_res_m": 25}})
    assert "__BG__" in k
    assert "__b270m__" in k
    assert "__r25m" in k


def test_is_valid_cached_parquet_rejects_short_file(tmp_path):
    from app.experiments.bg_ndi_wi import _is_valid_cached_parquet

    p = tmp_path / "fake.parquet"
    p.write_bytes(b"too short")
    assert not _is_valid_cached_parquet(p)


def test_is_valid_cached_parquet_rejects_missing(tmp_path):
    from app.experiments.bg_ndi_wi import _is_valid_cached_parquet

    assert not _is_valid_cached_parquet(tmp_path / "does-not-exist.parquet")


def test_is_valid_cached_parquet_accepts_real_parquet(tmp_path):
    import pandas as pd
    from app.experiments.bg_ndi_wi import _is_valid_cached_parquet

    p = tmp_path / "real.parquet"
    pd.DataFrame({"a": [1, 2, 3]}).to_parquet(p, index=False)
    assert _is_valid_cached_parquet(p)


import shutil


def test_cache_miss_creates_artifact_and_meta(fake_template_dir, fake_cli_settings, tmp_path):
    """First run with no cache → cache dir gets <key>.parquet + <key>.meta.json."""
    import app.config

    task_dir = tmp_path / "task-cache-01"
    task_dir.mkdir()
    (task_dir / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
    )
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))

    from app.experiments.bg_ndi_wi import run
    rc = run(task_dir)
    assert rc == 0

    cache_dir = app.config.settings.C3_CACHE_DIR
    parquets = list(cache_dir.glob("*.parquet"))
    metas = list(cache_dir.glob("*.meta.json"))
    assert len(parquets) == 1
    assert len(metas) == 1
    # filename grammar
    assert "__BG__b270m__r25m" in parquets[0].name


def test_cache_hit_skips_subprocess(fake_template_dir, fake_cli_settings, tmp_path, monkeypatch):
    """Second run with same inputs → Popen called 0 times for c3_bg."""
    import app.config

    # Run 1: populates cache.
    task_dir = tmp_path / "task-cache-A"
    task_dir.mkdir()
    (task_dir / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
    )
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))
    from app.experiments.bg_ndi_wi import run
    assert run(task_dir) == 0

    # Run 2: byte-identical input + same config. Should hit cache for c3_bg.
    task_dir_2 = tmp_path / "task-cache-B"
    task_dir_2.mkdir()
    shutil.copy(task_dir / "input.csv", task_dir_2 / "input.csv")
    shutil.copy(task_dir / "config.json", task_dir_2 / "config.json")

    # Monkeypatch run_pipeline_step to count invocations BY STEP NAME.
    from app.experiments import bg_ndi_wi
    calls: list[str] = []
    real_run_step = bg_ndi_wi.run_pipeline_step

    def counting_run_step(yaml_path, task_dir, step_name, on_progress=None):
        calls.append(step_name)
        return real_run_step(yaml_path, task_dir, step_name, on_progress)

    monkeypatch.setattr(bg_ndi_wi, "run_pipeline_step", counting_run_step)
    assert run(task_dir_2) == 0

    # c3_bg should be a cache hit (not in calls); c4_ndi must still run.
    assert "c3_bg" not in calls, f"c3_bg should have hit cache; calls={calls}"
    assert "c4_ndi" in calls


def test_cache_corrupted_falls_through(fake_template_dir, fake_cli_settings, tmp_path):
    """Pre-existing 10-byte fake cache entry → ignored, fresh run, cache overwritten."""
    import app.config

    task_dir = tmp_path / "task-cache-C"
    task_dir.mkdir()
    (task_dir / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
    )
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))

    # Pre-populate the cache with a corrupted file at the EXACT key the run will compute.
    # Easiest: do one real run first to learn the key, then truncate the file.
    from app.experiments.bg_ndi_wi import run
    run(task_dir)  # populates cache
    cache_dir = app.config.settings.C3_CACHE_DIR
    parquets = list(cache_dir.glob("*.parquet"))
    assert len(parquets) == 1
    parquets[0].write_bytes(b"truncated!")  # corrupt it

    # Now run again — should detect corruption and rebuild.
    task_dir_2 = tmp_path / "task-cache-D"
    task_dir_2.mkdir()
    shutil.copy(task_dir / "input.csv", task_dir_2 / "input.csv")
    shutil.copy(task_dir / "config.json", task_dir_2 / "config.json")
    assert run(task_dir_2) == 0
    # Cache should be rewritten with valid content.
    assert parquets[0].stat().st_size > 100


def test_cache_write_failure_does_not_break_task(
    fake_template_dir, fake_cli_settings, tmp_path, monkeypatch
):
    """shutil.copy raising OSError on cache write → task still finishes."""
    import shutil as real_shutil
    from app.experiments import bg_ndi_wi

    task_dir = tmp_path / "task-cache-E"
    task_dir.mkdir()
    (task_dir / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
    )
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))

    # Sabotage cache writes only — keep other copies working.
    real_copy = real_shutil.copy

    def failing_copy(src, dst, *a, **kw):
        # Identify cache-write copies by destination containing /c3_cache/.
        if "c3_cache" in str(dst):
            raise OSError(28, "No space left on device")
        return real_copy(src, dst, *a, **kw)

    monkeypatch.setattr(bg_ndi_wi.shutil, "copy", failing_copy)

    rc = bg_ndi_wi.run(task_dir)
    assert rc == 0  # task still finishes
    status = json.loads((task_dir / "status.json").read_text())
    assert status["status"] == "finished"


def test_csv_to_parquet_adds_episode_id(tmp_path):
    """Every row gets episode_id = its row index, regardless of pid."""
    from app.experiments.bg_ndi_wi import csv_to_parquet

    src = tmp_path / "input.csv"
    src.write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "PID0000001,2017-01-01,2017-12-31,-93.0,45.0\n"
        "PID0000002,2017-01-01,2017-12-31,-95.0,30.0\n"
        "PID0000001,2018-01-01,2018-12-31,-87.0,42.0\n"  # same pid as row 0
    )
    dst = tmp_path / "input.parquet"
    csv_to_parquet(src, dst)

    df = pd.read_parquet(dst)
    assert "episode_id" in df.columns
    assert df["episode_id"].tolist() == [0, 1, 2]


def test_csv_to_parquet_overrides_user_episode_id_with_warn(tmp_path, caplog):
    """If the input CSV already has an episode_id column, it's overwritten
    deterministically and a warning is logged via standard logging."""
    from app.experiments.bg_ndi_wi import csv_to_parquet

    src = tmp_path / "input.csv"
    src.write_text(
        "pid,startDate,endDate,longitude,latitude,episode_id\n"
        "PID0000001,2017-01-01,2017-12-31,-93.0,45.0,999\n"
        "PID0000002,2017-01-01,2017-12-31,-95.0,30.0,888\n"
    )
    dst = tmp_path / "input.parquet"

    import logging
    with caplog.at_level(logging.WARNING, logger="app.experiments.bg_ndi_wi"):
        csv_to_parquet(src, dst)

    df = pd.read_parquet(dst)
    # User values overwritten to deterministic row-index series
    assert df["episode_id"].tolist() == [0, 1]
    # Warning emitted
    assert any("episode_id" in r.message for r in caplog.records)


def test_render_yaml_emits_episode_grouping(fake_template_dir, tmp_path):
    """The emitted YAML must set time.output_grouping = 'episode' so the
    pipeline keeps one output row per (PATID, episode) instead of collapsing
    to one row per PATID."""
    task_dir = tmp_path / "task-ep000001"
    task_dir.mkdir()
    step = _VARIABLE_TO_STEP["ndi"]
    user_config = {"buffer": {"size": 270, "raster_res_m": 25}}

    out = render_yaml(step, task_dir, user_config)
    cfg = yaml.safe_load(out.read_text())
    assert cfg["time"]["output_grouping"] == "episode"


def test_render_yaml_preserves_other_time_fields(fake_template_dir, tmp_path):
    """output_grouping is additive; existing time fields keep working."""
    task_dir = tmp_path / "task-ep000002"
    task_dir.mkdir()
    step = _VARIABLE_TO_STEP["ndi"]
    user_config = {"buffer": {"size": 270, "raster_res_m": 25}}

    out = render_yaml(step, task_dir, user_config)
    cfg = yaml.safe_load(out.read_text())
    # whatever existing keys were already populated should still be there
    assert "years" in cfg["time"] or "start_date" in cfg["time"]


def test_merge_results_joins_on_pid_and_episode_id(tmp_path):
    """When pipeline emits one row per (PATID, episode_id), merge_results must
    join on BOTH so a patient with 2 episodes gets 2 result rows, not 1."""
    task_dir = tmp_path / "task-ep-merge1"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    (task_dir / "logs.jsonl").touch()

    # Input: pid=A has 2 episodes (episode_id 0 and 1), pid=B has 1 (episode_id 2)
    input_df = pd.DataFrame({
        "pid": ["A", "A", "B"],
        "startDate": pd.to_datetime(["2017-01-01", "2018-01-01", "2017-01-01"]),
        "endDate": pd.to_datetime(["2017-12-31", "2018-12-31", "2017-12-31"]),
        "longitude": [-93.0, -94.0, -95.0],
        "latitude": [45.0, 41.0, 30.0],
        "episode_id": [0, 1, 2],
    })
    input_df.to_csv(task_dir / "input.csv", index=False)

    # Pipeline output: PATID + geoid (= episode_id), one row per (PATID, geoid)
    pipeline_df = pd.DataFrame({
        "PATID": ["A", "A", "B"],
        "geoid": [0, 1, 2],
        "ndi": [3, 1, 5],
    })
    pipeline_df.to_parquet(task_dir / "output" / "c4_ndi.parquet", index=False)

    merge_results(task_dir, variables=["ndi"])

    out = pd.read_csv(task_dir / "output" / "result.csv")
    # 3 rows out (one per residential episode), not 2 (one per patient)
    assert len(out) == 3
    assert out["pid"].tolist() == ["A", "A", "B"]
    # Each row got its OWN exposure value, distinguishable per episode
    assert out["ndi"].tolist() == [3, 1, 5]


def test_merge_results_missing_pipeline_row_fills_na(tmp_path):
    """Left-join semantics: an input episode with no matching pipeline row
    keeps its input columns + NaN exposures."""
    task_dir = tmp_path / "task-ep-merge2"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    (task_dir / "logs.jsonl").touch()

    input_df = pd.DataFrame({
        "pid": ["A", "A"],
        "startDate": pd.to_datetime(["2017-01-01", "2018-01-01"]),
        "endDate": pd.to_datetime(["2017-12-31", "2018-12-31"]),
        "longitude": [-93.0, -94.0],
        "latitude": [45.0, 41.0],
        "episode_id": [0, 1],
    })
    input_df.to_csv(task_dir / "input.csv", index=False)

    # Pipeline only has episode_id=0; episode_id=1 (maybe geocode failed) is missing.
    pipeline_df = pd.DataFrame({
        "PATID": ["A"],
        "geoid": [0],
        "ndi": [3],
    })
    pipeline_df.to_parquet(task_dir / "output" / "c4_ndi.parquet", index=False)

    merge_results(task_dir, variables=["ndi"])

    out = pd.read_csv(task_dir / "output" / "result.csv")
    assert len(out) == 2  # both input rows preserved
    assert out["pid"].tolist() == ["A", "A"]
    # First row matched, second is NaN
    assert out["ndi"].tolist()[0] == 3
    assert pd.isna(out["ndi"].tolist()[1])


def test_boundary_constant_is_BG():
    """Sprint 3 B15: the per-runner boundary literal must be a module constant."""
    from app.experiments import bg_ndi_wi
    assert bg_ndi_wi._BOUNDARY == "BG"


def test_cache_key_byte_identical_after_boundary_refactor(tmp_path):
    """Refactoring 'BG' into _BOUNDARY must NOT change the emitted key bytes."""
    from app.experiments.bg_ndi_wi import _cache_key, _C3_STEP, _hash_input_parquet

    p = tmp_path / "in.parquet"
    p.write_bytes(b"\x00" * 4096)
    cfg = {"buffer": {"size": 270, "raster_res_m": 25}}

    sha8 = _hash_input_parquet(p)[:8]
    expected = f"{sha8}__BG__b270m__r25m"
    assert _cache_key(p, _C3_STEP, cfg) == expected
