# backend/tests/test_tasks.py
import json
import tempfile
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

def get_test_client():
    tmp = tempfile.mkdtemp()
    os.environ["DATA_DIR"] = tmp
    os.environ["DB_PATH"] = str(Path(tmp) / "test.db")
    os.environ["TASKS_DIR"] = str(Path(tmp) / "tasks")
    # Force reimport so settings picks up new env vars
    import importlib
    import app.config
    importlib.reload(app.config)
    import app.database
    importlib.reload(app.database)
    import app.auth
    importlib.reload(app.auth)
    import app.routers.auth
    importlib.reload(app.routers.auth)
    import app.task_manager
    importlib.reload(app.task_manager)
    import app.routers.tasks
    importlib.reload(app.routers.tasks)
    import app.main
    importlib.reload(app.main)
    from app.main import create_app
    from app.database import init_db
    app_instance = create_app()
    # Manually init DB and create dirs since startup event doesn't fire in TestClient
    Path(tmp).mkdir(parents=True, exist_ok=True)
    (Path(tmp) / "tasks").mkdir(parents=True, exist_ok=True)
    init_db()
    client = TestClient(app_instance)
    # Create user and get token
    resp = client.post("/api/auth/signup", json={
        "email": "t@t.com", "password": "pw123", "first_name": "T", "last_name": "U"
    })
    token = resp.json()["access_token"]
    return client, token, tmp

def auth_header(token):
    return {"Authorization": f"Bearer {token}"}

def test_create_task():
    client, token, _ = get_test_client()
    resp = client.post("/api/tasks", json={"task_name": "My Task"}, headers=auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["task_name"] == "My Task"

def test_list_tasks():
    client, token, _ = get_test_client()
    client.post("/api/tasks", json={"task_name": "Task 1"}, headers=auth_header(token))
    client.post("/api/tasks", json={"task_name": "Task 2"}, headers=auth_header(token))
    resp = client.get("/api/tasks", headers=auth_header(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2

def test_get_task():
    client, token, _ = get_test_client()
    create_resp = client.post("/api/tasks", json={"task_name": "Detail Task"}, headers=auth_header(token))
    task_id = create_resp.json()["id"]
    resp = client.get(f"/api/tasks/{task_id}", headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["task_name"] == "Detail Task"

def test_delete_task():
    client, token, _ = get_test_client()
    create_resp = client.post("/api/tasks", json={"task_name": "Delete Me"}, headers=auth_header(token))
    task_id = create_resp.json()["id"]
    resp = client.delete(f"/api/tasks/{task_id}", headers=auth_header(token))
    assert resp.status_code == 200
    resp = client.get(f"/api/tasks/{task_id}", headers=auth_header(token))
    assert resp.status_code == 404

def test_access_control():
    """User A cannot access User B's task."""
    client, token_a, tmp = get_test_client()
    create_resp = client.post("/api/tasks", json={"task_name": "A's Task"}, headers=auth_header(token_a))
    task_id = create_resp.json()["id"]
    # Create user B
    resp_b = client.post("/api/auth/signup", json={
        "email": "b@b.com", "password": "pw123", "first_name": "B", "last_name": "U"
    })
    token_b = resp_b.json()["access_token"]
    resp = client.get(f"/api/tasks/{task_id}", headers=auth_header(token_b))
    assert resp.status_code == 403

def test_upload_valid_csv():
    import io
    client, token, _ = get_test_client()
    resp = client.post("/api/tasks", json={"task_name": "Upload Test"}, headers=auth_header(token))
    task_id = resp.json()["id"]
    csv = "pid,startDate,endDate,longitude,latitude\nP1,2020-01-01,2020-12-31,-82.35,29.65\n"
    resp = client.post(f"/api/tasks/{task_id}/upload", headers=auth_header(token),
                       files={"file": ("test.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert resp.status_code == 200
    assert resp.json()["row_count"] == 1

def test_upload_missing_columns():
    import io
    client, token, _ = get_test_client()
    resp = client.post("/api/tasks", json={"task_name": "Bad Upload"}, headers=auth_header(token))
    task_id = resp.json()["id"]
    csv = "id,lon,lat\nP1,-82,29\n"
    resp = client.post(f"/api/tasks/{task_id}/upload", headers=auth_header(token),
                       files={"file": ("test.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert resp.status_code == 400

def test_save_config_and_start():
    import io, time
    client, token, _ = get_test_client()
    resp = client.post("/api/tasks", json={"task_name": "Run Test"}, headers=auth_header(token))
    task_id = resp.json()["id"]
    csv = "pid,startDate,endDate,longitude,latitude\nP1,2020-01-01,2020-12-31,-82.35,29.65\n"
    client.post(f"/api/tasks/{task_id}/upload", headers=auth_header(token),
                files={"file": ("test.csv", io.BytesIO(csv.encode()), "text/csv")})
    # Use mock experiment so this test doesn't require SPACESCANS_PIPELINE_PYTHON
    # to exist on disk (the bg_ndi_wi dispatch path needs the conda env binary,
    # which is only present when backend/.env is configured).
    config = {"experiment": "mock", "buffer": {"shape": "circle", "size": 1000, "unit": "meters"}, "variables": ["var_a"]}
    resp = client.put(f"/api/tasks/{task_id}/config", json=config, headers=auth_header(token))
    assert resp.status_code == 200
    resp = client.post(f"/api/tasks/{task_id}/start", headers=auth_header(token))
    assert resp.status_code == 200
    assert "pid" in resp.json()

def test_recover_orphaned_tasks():
    import json
    from pathlib import Path
    client, token, tmp = get_test_client()
    resp = client.post("/api/tasks", json={"task_name": "Orphan"}, headers=auth_header(token))
    task_id = resp.json()["id"]
    task_dir = Path(tmp) / "tasks" / f"task-{task_id}"
    # Write a fake running status with a dead PID
    (task_dir / "status.json").write_text(json.dumps({"status": "running", "pid": 99999999, "progress": 0.5}))
    from app.task_manager import recover_orphaned_tasks
    recover_orphaned_tasks()
    status = json.loads((task_dir / "status.json").read_text())
    assert status["status"] == "error"


def test_save_config_default_experiment_is_bg_ndi_wi(monkeypatch, tmp_path):
    import io, importlib, app.config, app.task_manager
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
    importlib.reload(app.config)
    importlib.reload(app.task_manager)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="t")
    save_config(meta["id"], {
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
        "variables": ["ndi"],
    })
    cfg_path = (app.config.settings.TASKS_DIR / f"task-{meta['id']}" / "config.json")
    saved = json.loads(cfg_path.read_text())
    assert saved["experiment"] == "bg_ndi_wi"


def test_start_lock_returns_409_when_busy(monkeypatch, tmp_path):
    """Acquire the lock from outside, then call start_task and expect TaskBusyError."""
    import io, importlib, fcntl, os, app.config, app.task_manager
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
    importlib.reload(app.config)
    importlib.reload(app.task_manager)

    # Externally acquire the lock to simulate another running task.
    lock_path = app.config.settings.DATA_DIR / ".run_lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    fd = os.open(str(lock_path), os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    from app.task_manager import create_task, save_config, start_task, TaskBusyError
    meta = create_task(user_id=1, task_name="t")
    save_config(meta["id"], {
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
        "variables": ["ndi"],
        "experiment": "mock",  # don't actually try to run bg_ndi_wi here
    })
    (app.config.settings.TASKS_DIR / f"task-{meta['id']}" / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-06-30,-93.0,45.0\n"
    )
    with pytest.raises(TaskBusyError):
        start_task(meta["id"])

    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def test_get_results_with_file_query(monkeypatch, tmp_path):
    """The /results endpoint accepts a ?file= query for any output/ subfile."""
    import io, importlib, json, app.config, app.task_manager
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
    importlib.reload(app.config)
    importlib.reload(app.task_manager)
    import app.main
    importlib.reload(app.main)

    from app.main import create_app
    from app.database import init_db
    from fastapi.testclient import TestClient

    init_db()
    app_instance = create_app()
    client = TestClient(app_instance)

    # Sign up
    resp = client.post("/api/auth/signup", json={
        "email": "f@f.com", "password": "pw123", "first_name": "F", "last_name": "U"
    })
    token = resp.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    # Create + populate a fake task with an intermediate parquet
    resp = client.post("/api/tasks", json={"task_name": "files"}, headers=auth)
    task_id = resp.json()["id"]
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    (task_dir / "output").mkdir(parents=True, exist_ok=True)
    (task_dir / "output" / "c3_bg.parquet").write_bytes(b"FAKE-PARQUET")

    # Without ?file= — 404 because result.csv missing
    resp = client.get(f"/api/tasks/{task_id}/results", headers=auth)
    assert resp.status_code == 404

    # With ?file=c3_bg.parquet — should succeed
    resp = client.get(f"/api/tasks/{task_id}/results?file=c3_bg.parquet", headers=auth)
    assert resp.status_code == 200
    assert resp.content == b"FAKE-PARQUET"

    # Reject traversal
    resp = client.get(f"/api/tasks/{task_id}/results?file=../../../etc/passwd", headers=auth)
    assert resp.status_code == 400


def test_results_preview(monkeypatch, tmp_path):
    """GET /results/preview returns columns + first N rows + total_rows."""
    import importlib, app.config, app.task_manager
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
    importlib.reload(app.config)
    importlib.reload(app.task_manager)
    import app.main
    importlib.reload(app.main)

    from app.main import create_app
    from app.database import init_db
    from fastapi.testclient import TestClient

    init_db()
    client = TestClient(create_app())

    resp = client.post("/api/auth/signup", json={
        "email": "pv@p.com", "password": "pw123", "first_name": "P", "last_name": "V"
    })
    token = resp.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/tasks", json={"task_name": "preview"}, headers=auth)
    task_id = resp.json()["id"]
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    (task_dir / "output").mkdir(parents=True, exist_ok=True)

    # No result.csv yet → 404
    resp = client.get(f"/api/tasks/{task_id}/results/preview", headers=auth)
    assert resp.status_code == 404

    # Write a 25-row result.csv with mixed types + a NaN
    csv = "pid,episode_id,ndi,note\n"
    csv += "\n".join(
        [f"PID{i:04d},{i},{0.1 * i:.4f},sample" for i in range(25)]
    )
    csv += "\nPID9999,99,,missing"
    (task_dir / "output" / "result.csv").write_text(csv)

    # Default limit 20
    resp = client.get(f"/api/tasks/{task_id}/results/preview", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["columns"] == ["pid", "episode_id", "ndi", "note"]
    assert len(body["rows"]) == 20
    assert body["total_rows"] == 26
    assert body["has_more"] is True
    assert body["rows"][0][0] == "PID0000"

    # limit=50 → all 26 rows
    resp = client.get(f"/api/tasks/{task_id}/results/preview?limit=50", headers=auth)
    body = resp.json()
    assert len(body["rows"]) == 26
    assert body["has_more"] is False
    nan_row = body["rows"][-1]
    assert nan_row[0] == "PID9999"
    assert nan_row[2] is None

    # Out-of-range limits rejected
    resp = client.get(f"/api/tasks/{task_id}/results/preview?limit=0", headers=auth)
    assert resp.status_code == 422
    resp = client.get(f"/api/tasks/{task_id}/results/preview?limit=500", headers=auth)
    assert resp.status_code == 422
