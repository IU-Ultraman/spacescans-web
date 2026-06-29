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

    # Summary stats present (computed over ALL 26 rows, not just the preview limit)
    resp = client.get(f"/api/tasks/{task_id}/results/preview", headers=auth)
    body = resp.json()
    assert "summary" in body
    summary = {col["name"]: col for col in body["summary"]}
    assert set(summary) == {"pid", "episode_id", "ndi", "note"}

    # pid: categorical, 26 unique values, no nulls
    assert summary["pid"]["dtype"] == "categorical"
    assert summary["pid"]["non_null"] == 26
    assert summary["pid"]["null_count"] == 0
    assert summary["pid"]["unique"] == 26
    assert summary["pid"]["min"] is None  # categorical → no min/max

    # episode_id: numeric, range 0..99 across 26 rows, mean ≈ avg of [0..24, 99]
    assert summary["episode_id"]["dtype"] == "numeric"
    assert summary["episode_id"]["non_null"] == 26
    assert summary["episode_id"]["min"] == 0
    assert summary["episode_id"]["max"] == 99

    # ndi: numeric, 25 non-null + 1 null
    assert summary["ndi"]["dtype"] == "numeric"
    assert summary["ndi"]["non_null"] == 25
    assert summary["ndi"]["null_count"] == 1
    assert summary["ndi"]["min"] == 0.0
    assert summary["ndi"]["max"] == 2.4

    # note: categorical, 2 unique values ("sample", "missing")
    assert summary["note"]["dtype"] == "categorical"
    assert summary["note"]["unique"] == 2


def test_results_histogram(monkeypatch, tmp_path):
    """GET /results/histogram returns one entry per numeric exposure col."""
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
        "email": "hi@h.com", "password": "pw123", "first_name": "H", "last_name": "I"
    })
    token = resp.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/tasks", json={"task_name": "hist"}, headers=auth)
    task_id = resp.json()["id"]
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    (task_dir / "output").mkdir(parents=True, exist_ok=True)

    # 404 before result.csv exists
    resp = client.get(f"/api/tasks/{task_id}/results/histogram", headers=auth)
    assert resp.status_code == 404

    # Build result.csv: 1 input col (pid), 1 string col (note),
    # 2 numeric exposure cols (ndi, walkability).
    rows = ["pid,note,ndi,walkability"]
    for i in range(30):
        rows.append(f"PID{i:04d},sample,{0.1 * i:.4f},{(i % 5) * 1.5:.2f}")
    (task_dir / "output" / "result.csv").write_text("\n".join(rows) + "\n")

    # Happy path — default bins=20
    resp = client.get(f"/api/tasks/{task_id}/results/histogram", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert "histograms" in body
    by_name = {h["name"]: h for h in body["histograms"]}
    # Exactly the two numeric exposure columns — pid (input) and note (string) skipped.
    assert set(by_name.keys()) == {"ndi", "walkability"}
    ndi = by_name["ndi"]
    # np.histogram returns bins+1 edges and `bins` counts
    assert len(ndi["bins"]) == 21
    assert len(ndi["counts"]) == 20
    assert ndi["sample_size"] == 30
    assert ndi["min"] == 0.0
    assert ndi["max"] == round(0.1 * 29, 6)
    assert sum(ndi["counts"]) == 30

    # bins=10 respected
    resp = client.get(
        f"/api/tasks/{task_id}/results/histogram?bins=10", headers=auth
    )
    body = resp.json()
    by_name = {h["name"]: h for h in body["histograms"]}
    assert len(by_name["ndi"]["counts"]) == 10
    assert len(by_name["ndi"]["bins"]) == 11

    # Out-of-range bins rejected
    resp = client.get(
        f"/api/tasks/{task_id}/results/histogram?bins=2", headers=auth
    )
    assert resp.status_code == 422
    resp = client.get(
        f"/api/tasks/{task_id}/results/histogram?bins=100", headers=auth
    )
    assert resp.status_code == 422


def test_results_geo(monkeypatch, tmp_path):
    """GET /results/geo groups rows by state_fips for one exposure col."""
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
        "email": "g@g.com", "password": "pw123", "first_name": "G", "last_name": "E"
    })
    token = resp.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/tasks", json={"task_name": "geo"}, headers=auth)
    task_id = resp.json()["id"]
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    (task_dir / "output").mkdir(parents=True, exist_ok=True)

    # 404 before result.csv exists
    resp = client.get(
        f"/api/tasks/{task_id}/results/geo?value_col=ndi", headers=auth
    )
    assert resp.status_code == 404

    # Write result.csv with `state_fips` written as ints (Alabama=1, Florida=12)
    # plus a NaN in the value_col for one Florida row.
    csv = (
        "pid,state_fips,ndi\n"
        "P1,1,0.5\n"
        "P2,12,1.0\n"
        "P3,12,2.0\n"
        "P4,12,\n"
    )
    (task_dir / "output" / "result.csv").write_text(csv)

    # Missing value_col → 400
    resp = client.get(f"/api/tasks/{task_id}/results/geo", headers=auth)
    assert resp.status_code == 400

    # Unknown column → 400
    resp = client.get(
        f"/api/tasks/{task_id}/results/geo?value_col=nope", headers=auth
    )
    assert resp.status_code == 400

    # Input column rejected → 400
    resp = client.get(
        f"/api/tasks/{task_id}/results/geo?value_col=pid", headers=auth
    )
    assert resp.status_code == 400

    # Happy path — Alabama "01" zero-padded; Florida has 2 non-null rows.
    resp = client.get(
        f"/api/tasks/{task_id}/results/geo?value_col=ndi", headers=auth
    )
    assert resp.status_code == 200
    body = resp.json()
    by_state = {b["state_fips"]: b for b in body["by_state"]}
    assert set(by_state.keys()) == {"01", "12"}
    assert by_state["01"]["count"] == 1
    assert by_state["01"]["mean"] == 0.5
    assert by_state["12"]["count"] == 2
    assert by_state["12"]["mean"] == 1.5


def test_create_task_rejects_duplicate_name():
    client, token, _ = get_test_client()
    h = auth_header(token)
    assert client.post("/api/tasks", json={"task_name": "Dup"}, headers=h).status_code == 200
    # Same name (case-insensitive, trimmed) for the same user -> 409.
    dup = client.post("/api/tasks", json={"task_name": "  dup  "}, headers=h)
    assert dup.status_code == 409
    assert "already exists" in dup.json()["detail"]


def test_rename_task():
    client, token, _ = get_test_client()
    h = auth_header(token)
    tid = client.post("/api/tasks", json={"task_name": "Old"}, headers=h).json()["id"]
    resp = client.patch(f"/api/tasks/{tid}", json={"task_name": "New"}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["task_name"] == "New"
    assert client.get(f"/api/tasks/{tid}", headers=h).json()["task_name"] == "New"


def test_rename_rejects_duplicate_name():
    client, token, _ = get_test_client()
    h = auth_header(token)
    client.post("/api/tasks", json={"task_name": "A"}, headers=h)
    tid_b = client.post("/api/tasks", json={"task_name": "B"}, headers=h).json()["id"]
    resp = client.patch(f"/api/tasks/{tid_b}", json={"task_name": "A"}, headers=h)
    assert resp.status_code == 409
