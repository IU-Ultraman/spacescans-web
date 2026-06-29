# backend/tests/test_api_tasks.py
"""API-layer tests for /api/tasks/{id}/start error mapping (Sprint 4 F2)."""
import fcntl
import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _get_client():
    tmp = tempfile.mkdtemp()
    os.environ["DATA_DIR"] = tmp
    os.environ["DB_PATH"] = str(Path(tmp) / "test.db")
    os.environ["TASKS_DIR"] = str(Path(tmp) / "tasks")
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
    Path(tmp).mkdir(parents=True, exist_ok=True)
    (Path(tmp) / "tasks").mkdir(parents=True, exist_ok=True)
    init_db()
    client = TestClient(create_app())
    resp = client.post("/api/auth/signup", json={
        "email": "u@u.com", "password": "pw123",
        "first_name": "U", "last_name": "U",
    })
    token = resp.json()["access_token"]
    return client, token, Path(tmp)


def test_start_enqueues_when_busy():
    """#1 serial queue: externally hold .run_lock; POST /start must enqueue
    (200 + status 'queued'), not reject with 409."""
    client, token, data_dir = _get_client()
    headers = {"Authorization": f"Bearer {token}"}

    # Create a task with config + input so start_task reaches the lock probe.
    resp = client.post("/api/tasks", json={"task_name": "lock-queue"}, headers=headers)
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["id"]

    csv = "pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-06-30,-84.3,30.45\n"
    client.post(
        f"/api/tasks/{task_id}/upload",
        headers=headers,
        files={"file": ("input.csv", csv, "text/csv")},
    )
    client.put(
        f"/api/tasks/{task_id}/config",
        json={
            "experiment": "mock",
            "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
            "variables": ["ndi"],
        },
        headers=headers,
    )

    # Externally hold .run_lock to simulate another running task.
    lock_path = data_dir / ".run_lock"
    lock_path.touch()
    fd = os.open(str(lock_path), os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        resp = client.post(f"/api/tasks/{task_id}/start", headers=headers)
        assert resp.status_code == 200, (
            f"expected 200 enqueue, got {resp.status_code}: {resp.text}"
        )
        assert resp.json()["status"] == "queued", resp.text
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
