"""Sprint 3 T4: compute_coverage gains boundary + display_unit, is registry-driven."""
import importlib
import json
from pathlib import Path

import pytest


_REGISTRY_FIXTURE = {
    "schema_version": 1,
    "variables": {
        "ndi": {
            "label": "Neighborhood Deprivation Index",
            "description": "NDI composite.",
            "boundary": "BG",
            "coverage_years": [2012, 2022],
            "coverage_region": "CONUS",
            "experiment": "bg_ndi_wi",
            "variable_type": "continuous",
            "display_unit": "z-score",
            "value_cols": ["ndi"],
        },
        "cbp_zcta5": {
            "label": "Community Organization Density (ZBP)",
            "description": "CBP per-capita densities at ZCTA5.",
            "boundary": "ZCTA5",
            "coverage_years": [2013, 2019],
            "coverage_region": "CONUS",
            "experiment": "zcta5_cbp",
            "variable_type": "continuous",
            "display_unit": "establishments / 1k residents",
            "value_cols": [
                "r_religious", "r_civic", "r_business", "r_political",
                "r_professional", "r_labor", "r_bowling", "r_recreational",
                "r_golf", "r_sports",
            ],
        },
        "noise": {
            "label": "BTS Transportation Noise (L50 dBA)",
            "description": "Static noise layer.",
            "boundary": "BG",
            "coverage_years": [2020, 2020],
            "coverage_region": "CONUS",
            "experiment": "noise",
            "temporal": "static",
            "variable_type": "continuous",
            "display_unit": "dBA",
            "value_cols": ["l50dba_exi"],
        },
    },
}


def _seed(monkeypatch, tmp_path, csv_body: str) -> str:
    """Boot a task dir with input.csv + registry JSON pointing app.config at tmp_path."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))

    import app.config
    importlib.reload(app.config)
    import app.variable_registry as vr
    importlib.reload(vr)

    reg_path = tmp_path / "variable_metadata.json"
    reg_path.write_text(json.dumps(_REGISTRY_FIXTURE))
    monkeypatch.setattr(vr, "_METADATA_PATH", reg_path)
    monkeypatch.setattr(vr, "_CACHE", {"mtime": None, "payload": None})
    monkeypatch.setattr(vr, "_SCHEMA_PATH", reg_path)
    monkeypatch.setattr("jsonschema.validate", lambda payload, schema: None)
    monkeypatch.setattr(vr, "_discover_experiments",
                        lambda: {"bg_ndi_wi", "zcta5_cbp", "noise"})

    import app.task_manager
    importlib.reload(app.task_manager)

    task_dir = app.config.settings.TASKS_DIR / "task-cov-meta-01"
    task_dir.mkdir(parents=True)
    (task_dir / "input.csv").write_text(csv_body)
    return "cov-meta-01"


def test_compute_coverage_response_includes_boundary_and_display_unit(monkeypatch, tmp_path):
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
    )
    task_id = _seed(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["ndi"])
    v = out["variables"]["ndi"]
    assert v["boundary"] == "BG"
    assert v["display_unit"] == "z-score"
    assert v["coverage_years"] == [2012, 2022]
    assert v["coverage_pct"] == 100.0


def test_compute_coverage_static_skips_time_window(monkeypatch, tmp_path):
    """A static product (noise, vintage 2020) must NOT report 0% for a cohort
    living entirely outside that year — the time-window gate is skipped, so
    coverage reflects spatial (CONUS) overlap only, and the response carries
    temporal='static'."""
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"   # in CONUS, far from 2020
    )
    task_id = _seed(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["noise"])
    v = out["variables"]["noise"]
    assert v["temporal"] == "static"
    # Time gate skipped → all patients "in time", so a CONUS patient is 100%.
    assert v["patients_in_time_window"] == 1
    assert v["coverage_pct"] == 100.0
    # No time-window warning for a static product.
    assert not any("outside" in w and "2020" in w for w in v["warnings"])


def test_compute_coverage_static_still_flags_non_conus(monkeypatch, tmp_path):
    """Static products keep the spatial check: an Alaska patient is out of the
    CONUS coverage area regardless of the (skipped) time window."""
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P_AK,2017-01-01,2017-12-31,-149.9,61.2\n"  # Anchorage — outside CONUS
    )
    task_id = _seed(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["noise"])
    v = out["variables"]["noise"]
    assert v["temporal"] == "static"
    assert v["patients_in_region"] == 0
    assert v["coverage_pct"] == 0.0  # spatial miss still drives 0


def test_compute_coverage_cbp_zcta5_returns_boundary_zcta5(monkeypatch, tmp_path):
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2015-06-01,2015-12-31,-93.0,45.0\n"
    )
    task_id = _seed(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["cbp_zcta5"])
    v = out["variables"]["cbp_zcta5"]
    assert v["boundary"] == "ZCTA5"
    assert v["display_unit"] == "establishments / 1k residents"


def test_compute_coverage_conus_filter_unchanged(monkeypatch, tmp_path):
    """CONUS bbox (-125..-66, 24..50) still rejects an Alaska coordinate."""
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P_AK,2017-01-01,2017-12-31,-149.9,61.2\n"
        "P_TX,2017-01-01,2017-12-31,-95.0,30.0\n"
    )
    task_id = _seed(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["ndi"])
    assert out["variables"]["ndi"]["patients_in_region"] == 1
    assert out["variables"]["ndi"]["coverage_pct"] == 50.0


def test_compute_coverage_unknown_variable_still_raises_keyerror(monkeypatch, tmp_path):
    csv = "pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-12-31,-93,45\n"
    task_id = _seed(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    with pytest.raises(KeyError) as excinfo:
        compute_coverage(task_id, ["pm25"])
    assert "pm25" in str(excinfo.value)
