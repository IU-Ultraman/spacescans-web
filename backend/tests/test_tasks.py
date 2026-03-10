# backend/tests/test_tasks.py
import json
import tempfile
import os
from pathlib import Path
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
    csv = "patient_id,longitude,latitude,start_date,end_date\nP1,-82.35,29.65,2020-01-01,2020-12-31\n"
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
    csv = "patient_id,longitude,latitude,start_date,end_date\nP1,-82.35,29.65,2020-01-01,2020-12-31\n"
    client.post(f"/api/tasks/{task_id}/upload", headers=auth_header(token),
                files={"file": ("test.csv", io.BytesIO(csv.encode()), "text/csv")})
    config = {"buffer": {"shape": "circle", "size": 1000, "unit": "meters"}, "variables": ["var_a"]}
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
