# backend/tests/test_auth.py
import tempfile
import importlib
import os
from pathlib import Path
from fastapi.testclient import TestClient

def get_test_app():
    tmp = tempfile.mkdtemp()
    os.environ["DATA_DIR"] = tmp
    os.environ["DB_PATH"] = str(Path(tmp) / "test.db")
    os.environ["TASKS_DIR"] = str(Path(tmp) / "tasks")

    # Reload config so settings picks up new env vars
    import app.config
    importlib.reload(app.config)

    # Reload modules that reference app.config.settings
    import app.database
    importlib.reload(app.database)

    import app.auth
    importlib.reload(app.auth)

    import app.routers.auth
    importlib.reload(app.routers.auth)

    import app.main
    importlib.reload(app.main)

    from app.main import create_app
    from app.database import init_db
    app_instance = create_app()
    # Manually init DB since on_event("startup") doesn't fire without ASGI lifespan
    init_db()
    return TestClient(app_instance)

def test_signup():
    client = get_test_app()
    resp = client.post("/api/auth/signup", json={
        "email": "test@example.com",
        "password": "secret123",
        "first_name": "Test",
        "last_name": "User"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_signup_duplicate_email():
    client = get_test_app()
    payload = {"email": "dup@example.com", "password": "secret123", "first_name": "A", "last_name": "B"}
    client.post("/api/auth/signup", json=payload)
    resp = client.post("/api/auth/signup", json=payload)
    assert resp.status_code == 400

def test_login():
    client = get_test_app()
    client.post("/api/auth/signup", json={
        "email": "login@example.com",
        "password": "secret123",
        "first_name": "Test",
        "last_name": "User"
    })
    resp = client.post("/api/auth/login", json={
        "email": "login@example.com",
        "password": "secret123"
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()

def test_login_wrong_password():
    client = get_test_app()
    client.post("/api/auth/signup", json={
        "email": "wrong@example.com",
        "password": "secret123",
        "first_name": "Test",
        "last_name": "User"
    })
    resp = client.post("/api/auth/login", json={
        "email": "wrong@example.com",
        "password": "wrongpassword"
    })
    assert resp.status_code == 401
