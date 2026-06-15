import importlib
import json
from pathlib import Path
import pytest


def test_load_variable_metadata_reads_ndi_and_walkability(monkeypatch, tmp_path):
    """The loader returns the canonical 2-entry catalog for Sprint 1."""
    data_dir = tmp_path
    (data_dir / "variable_metadata.json").write_text(json.dumps({
        "ndi": {
            "label": "Neighborhood Deprivation Index",
            "boundary": "BG",
            "coverage_years": [2012, 2022],
            "coverage_region": "CONUS",
            "experiment": "bg_ndi_wi",
        },
        "walkability": {
            "label": "EPA Walkability Index",
            "boundary": "BG",
            "coverage_years": [2016, 2021],
            "coverage_region": "CONUS",
            "experiment": "bg_ndi_wi",
        },
    }))
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DB_PATH", str(data_dir / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(data_dir / "tasks"))
    import app.config
    importlib.reload(app.config)
    import app.task_manager
    importlib.reload(app.task_manager)

    meta = app.task_manager._load_variable_metadata()
    assert "ndi" in meta
    assert meta["ndi"]["coverage_years"] == [2012, 2022]
    assert meta["walkability"]["coverage_years"] == [2016, 2021]


def test_load_variable_metadata_caches_until_mtime_changes(monkeypatch, tmp_path):
    """Loader uses mtime-based cache invalidation."""
    data_dir = tmp_path
    (data_dir / "variable_metadata.json").write_text(json.dumps({
        "ndi": {"coverage_years": [2012, 2022], "coverage_region": "CONUS", "label": "X", "boundary": "BG", "experiment": "bg_ndi_wi"},
    }))
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DB_PATH", str(data_dir / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(data_dir / "tasks"))
    import app.config
    importlib.reload(app.config)
    import app.task_manager
    importlib.reload(app.task_manager)

    first = app.task_manager._load_variable_metadata()
    second = app.task_manager._load_variable_metadata()
    assert first is second  # same object — cached


def _seed_task_with_csv(monkeypatch, tmp_path, rows_csv: str) -> str:
    """Helper: create a task dir with an input.csv and return its task_id."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
    (tmp_path / "variable_metadata.json").write_text(json.dumps({
        "ndi": {"label": "NDI", "boundary": "BG", "coverage_years": [2012, 2022],
                "coverage_region": "CONUS", "experiment": "bg_ndi_wi"},
        "walkability": {"label": "WI", "boundary": "BG", "coverage_years": [2016, 2021],
                        "coverage_region": "CONUS", "experiment": "bg_ndi_wi"},
    }))
    import app.config
    importlib.reload(app.config)
    import app.task_manager
    importlib.reload(app.task_manager)

    task_dir = app.config.settings.TASKS_DIR / "task-cov-test-01"
    task_dir.mkdir(parents=True)
    (task_dir / "input.csv").write_text(rows_csv)
    return "cov-test-01"


def test_compute_coverage_basic_ndi(monkeypatch, tmp_path):
    """100% covered: cohort in 2017, all coords in CONUS."""
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
        "P2,2017-06-01,2018-06-01,-95.0,30.0\n"
    )
    task_id = _seed_task_with_csv(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["ndi"])
    assert out["row_count"] == 2
    assert out["variables"]["ndi"]["coverage_pct"] == 100.0
    assert out["variables"]["ndi"]["patients_covered"] == 2


def test_compute_coverage_time_window_filter(monkeypatch, tmp_path):
    """Walkability covers 2016-2021. Patients in 2014 fall outside."""
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2014-01-01,2014-12-31,-93.0,45.0\n"
        "P2,2018-01-01,2018-06-01,-93.0,45.0\n"
    )
    task_id = _seed_task_with_csv(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["walkability"])
    assert out["variables"]["walkability"]["patients_in_time_window"] == 1
    assert out["variables"]["walkability"]["coverage_pct"] == 50.0


def test_compute_coverage_region_filter_conus(monkeypatch, tmp_path):
    """CONUS box rejects an Alaska longitude."""
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P_AK,2017-01-01,2017-12-31,-149.9,61.2\n"
        "P_TX,2017-01-01,2017-12-31,-95.0,30.0\n"
    )
    task_id = _seed_task_with_csv(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["ndi"])
    assert out["variables"]["ndi"]["patients_in_region"] == 1
    assert out["variables"]["ndi"]["coverage_pct"] == 50.0


def test_compute_coverage_unknown_variable_raises(monkeypatch, tmp_path):
    csv = "pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-12-31,-93,45\n"
    task_id = _seed_task_with_csv(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    with pytest.raises(KeyError):
        compute_coverage(task_id, ["pm25"])


def test_compute_coverage_no_input_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
    (tmp_path / "variable_metadata.json").write_text(json.dumps({
        "ndi": {"label": "x", "boundary": "BG", "coverage_years": [2012, 2022],
                "coverage_region": "CONUS", "experiment": "bg_ndi_wi"},
    }))
    import app.config
    importlib.reload(app.config)
    import app.task_manager
    importlib.reload(app.task_manager)
    # Create task dir but no input.csv
    (app.config.settings.TASKS_DIR / "task-cov-test-02").mkdir(parents=True)
    from app.task_manager import compute_coverage
    with pytest.raises(FileNotFoundError):
        compute_coverage("cov-test-02", ["ndi"])


def test_compute_coverage_emits_warning_on_low_time_coverage(monkeypatch, tmp_path):
    """When >5% of patients are outside the time window, append a human-readable warning."""
    rows = ["pid,startDate,endDate,longitude,latitude"]
    for i in range(100):
        # 10 patients in 2014 (out of WI 2016-2021), 90 in 2018
        year = 2014 if i < 10 else 2018
        rows.append(f"P{i},{year}-01-01,{year}-12-31,-93.0,45.0")
    csv = "\n".join(rows) + "\n"
    task_id = _seed_task_with_csv(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["walkability"])
    assert out["variables"]["walkability"]["coverage_pct"] == 90.0
    assert len(out["variables"]["walkability"]["warnings"]) >= 1
    assert "2016-2021" in out["variables"]["walkability"]["warnings"][0]


def _make_authed_client(monkeypatch, tmp_path):
    """Boot a TestClient with the variable_metadata fixture + a signed-in user."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
    (tmp_path / "variable_metadata.json").write_text(json.dumps({
        "ndi": {"label": "NDI", "boundary": "BG", "coverage_years": [2012, 2022],
                "coverage_region": "CONUS", "experiment": "bg_ndi_wi"},
        "walkability": {"label": "WI", "boundary": "BG", "coverage_years": [2016, 2021],
                        "coverage_region": "CONUS", "experiment": "bg_ndi_wi"},
    }))
    for mod_name in [
        "app.config", "app.database", "app.auth", "app.routers.auth",
        "app.task_manager", "app.routers.tasks", "app.main",
    ]:
        mod = importlib.import_module(mod_name)
        importlib.reload(mod)

    from app.main import create_app
    from app.database import init_db
    from fastapi.testclient import TestClient

    init_db()
    client = TestClient(create_app())
    resp = client.post("/api/auth/signup", json={
        "email": "c@c.com", "password": "pw123", "first_name": "C", "last_name": "U"
    })
    token = resp.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_coverage_endpoint_basic(monkeypatch, tmp_path):
    import io
    client, auth = _make_authed_client(monkeypatch, tmp_path)
    task_id = client.post("/api/tasks", json={"task_name": "cov"}, headers=auth).json()["id"]
    csv = b"pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-12-31,-93.0,45.0\n"
    client.post(f"/api/tasks/{task_id}/upload", headers=auth,
                files={"file": ("in.csv", io.BytesIO(csv), "text/csv")})

    resp = client.get(f"/api/tasks/{task_id}/coverage?variables=ndi", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["row_count"] == 1
    assert body["variables"]["ndi"]["coverage_pct"] == 100.0


def test_coverage_endpoint_unknown_variable(monkeypatch, tmp_path):
    import io
    client, auth = _make_authed_client(monkeypatch, tmp_path)
    task_id = client.post("/api/tasks", json={"task_name": "cov"}, headers=auth).json()["id"]
    csv = b"pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-12-31,-93.0,45.0\n"
    client.post(f"/api/tasks/{task_id}/upload", headers=auth,
                files={"file": ("in.csv", io.BytesIO(csv), "text/csv")})

    resp = client.get(f"/api/tasks/{task_id}/coverage?variables=pm25", headers=auth)
    assert resp.status_code == 400
    assert "unknown variable" in resp.json()["detail"].lower()


def test_coverage_endpoint_multi_variables(monkeypatch, tmp_path):
    import io
    client, auth = _make_authed_client(monkeypatch, tmp_path)
    task_id = client.post("/api/tasks", json={"task_name": "cov"}, headers=auth).json()["id"]
    csv = b"pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-12-31,-93.0,45.0\n"
    client.post(f"/api/tasks/{task_id}/upload", headers=auth,
                files={"file": ("in.csv", io.BytesIO(csv), "text/csv")})

    resp = client.get(f"/api/tasks/{task_id}/coverage?variables=ndi,walkability", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert "ndi" in body["variables"]
    assert "walkability" in body["variables"]


def test_coverage_endpoint_no_input(monkeypatch, tmp_path):
    client, auth = _make_authed_client(monkeypatch, tmp_path)
    task_id = client.post("/api/tasks", json={"task_name": "cov"}, headers=auth).json()["id"]
    # No upload — task exists but no input.csv
    resp = client.get(f"/api/tasks/{task_id}/coverage?variables=ndi", headers=auth)
    assert resp.status_code == 400
    assert "no input" in resp.json()["detail"].lower()


def test_coverage_endpoint_ownership_403(monkeypatch, tmp_path):
    import io
    client, auth_a = _make_authed_client(monkeypatch, tmp_path)
    task_id = client.post("/api/tasks", json={"task_name": "A's task"}, headers=auth_a).json()["id"]
    csv = b"pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-12-31,-93.0,45.0\n"
    client.post(f"/api/tasks/{task_id}/upload", headers=auth_a,
                files={"file": ("in.csv", io.BytesIO(csv), "text/csv")})

    # User B
    resp_b = client.post("/api/auth/signup", json={
        "email": "b@b.com", "password": "pw123", "first_name": "B", "last_name": "U"
    })
    token_b = resp_b.json()["access_token"]
    auth_b = {"Authorization": f"Bearer {token_b}"}

    resp = client.get(f"/api/tasks/{task_id}/coverage?variables=ndi", headers=auth_b)
    assert resp.status_code == 403
