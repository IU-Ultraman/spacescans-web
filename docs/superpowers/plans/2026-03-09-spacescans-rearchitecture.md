# SPACESCANS Web App Rearchitecture — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the SPACESCANS web app in a fresh repo with simplified architecture: Next.js + FastAPI + SQLite + file-based CLI contract.

**Architecture:** Frontend (Next.js + shadcn/ui + Tailwind) talks to backend (FastAPI + SQLite for auth). Tasks are file-based directories. Backend spawns a mock CLI subprocess that reads config.json and writes status/logs/results. Ontology served as pre-processed static JSON files.

**Tech Stack:** Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, FastAPI, SQLite, Python 3.11+, owlready2

**Spec:** `docs/superpowers/specs/2026-03-09-spacescans-rearchitecture-design.md`

---

## Chunk 1: Backend Foundation

### Task 1: Project Scaffolding

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Create backend directory and requirements.txt**

```txt
fastapi==0.115.6
uvicorn==0.34.0
pydantic==2.10.3
pydantic-settings==2.7.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.18
aiofiles==24.1.0
owlready2==0.47
pytest>=7.0
httpx>=0.24.0
```

- [ ] **Step 2: Create config.py**

```python
import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "SPACESCANS"
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    ALGORITHM: str = "HS256"
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    TASKS_DIR: Path = DATA_DIR / "tasks"
    DB_PATH: Path = DATA_DIR / "spacescans.db"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    MAX_UPLOAD_SIZE_MB: int = 100

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 3: Create main.py with CORS and health check**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.TASKS_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Write health check test**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient
from app.main import create_app

def test_health():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

Note: `main.py` must use `create_app()` factory pattern from the start (see Step 3).

- [ ] **Step 5: Run test**

Run: `cd backend && pip install -r requirements.txt && python -m pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: backend scaffolding with FastAPI, config, health check"
```

---

### Task 2: SQLite Database & User Model

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/schemas.py`
- Create: `backend/tests/test_database.py`

- [ ] **Step 1: Write failing test for database initialization**

```python
# backend/tests/test_database.py
import os
import tempfile
from pathlib import Path

def test_database_creates_tables():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        os.environ["DB_PATH"] = str(db_path)
        from app.database import init_db, get_db
        init_db(db_path)
        db = next(get_db(db_path))
        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        assert cursor.fetchone() is not None
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_database.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.database'`

- [ ] **Step 3: Create database.py with SQLite WAL mode**

```python
# backend/app/database.py
import sqlite3
from pathlib import Path
from typing import Generator
from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

def init_db(db_path: Path = None):
    path = db_path or settings.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

def get_db(db_path: Path = None) -> Generator:
    path = db_path or settings.DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()
```

- [ ] **Step 4: Create schemas.py**

```python
# backend/app/schemas.py
from pydantic import BaseModel
from typing import Optional

class UserCreate(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    is_active: bool
    created_at: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None

class ErrorResponse(BaseModel):
    error: str
    detail: str
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_database.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/database.py backend/app/schemas.py backend/app/models.py backend/tests/
git commit -m "feat: SQLite database with WAL mode and user schema"
```

---

### Task 3: Auth Endpoints (signup + login)

**Files:**
- Create: `backend/app/auth.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/auth.py`
- Create: `backend/tests/test_auth.py`
- Modify: `backend/app/main.py` (register router)

- [ ] **Step 1: Write failing tests for signup and login**

```python
# backend/tests/test_auth.py
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

def get_test_app():
    import os
    tmp = tempfile.mkdtemp()
    os.environ["DATA_DIR"] = tmp
    os.environ["DB_PATH"] = str(Path(tmp) / "test.db")
    os.environ["TASKS_DIR"] = str(Path(tmp) / "tasks")
    from app.main import create_app
    app = create_app()
    return TestClient(app)

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: FAIL

- [ ] **Step 3: Create auth.py (password hashing + JWT)**

```python
# backend/app/auth.py
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
from app.database import get_db
import sqlite3

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"id": int(user_id), "email": email}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

- [ ] **Step 4: Create routers/auth.py**

```python
# backend/app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException
from app.schemas import UserCreate, LoginRequest, Token, ErrorResponse
from app.auth import hash_password, verify_password, create_access_token
from app.database import get_db
import sqlite3

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/signup", response_model=Token)
def signup(user: UserCreate, db: sqlite3.Connection = Depends(get_db)):
    hashed = hash_password(user.password)
    try:
        cursor = db.execute(
            "INSERT INTO users (email, hashed_password, first_name, last_name) VALUES (?, ?, ?, ?)",
            (user.email, hashed, user.first_name, user.last_name)
        )
        db.commit()
        user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    token = create_access_token({"sub": str(user_id), "email": user.email})
    return Token(access_token=token)

@router.post("/login", response_model=Token)
def login(credentials: LoginRequest, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT id, hashed_password FROM users WHERE email = ?", (credentials.email,)).fetchone()
    if not row or not verify_password(credentials.password, row["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": str(row["id"]), "email": credentials.email})
    return Token(access_token=token)
```

- [ ] **Step 5: Update main.py to use create_app factory and register router**

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers.auth import router as auth_router

def create_app() -> FastAPI:
    app = FastAPI(title=settings.PROJECT_NAME)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)

    @app.on_event("startup")
    async def startup():
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        settings.TASKS_DIR.mkdir(parents=True, exist_ok=True)
        init_db()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app

app = create_app()
```

- [ ] **Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: All 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat: auth endpoints with JWT signup and login"
```

---

### Task 4: Mock CLI Pipeline

**Files:**
- Create: `backend/mock_cli/__init__.py`
- Create: `backend/mock_cli/__main__.py`
- Create: `backend/mock_cli/cli.py`
- Create: `backend/tests/test_mock_cli.py`

- [ ] **Step 1: Write failing test for mock CLI**

```python
# backend/tests/test_mock_cli.py
import json
import tempfile
import subprocess
import sys
from pathlib import Path

def create_task_dir(tmp_path: Path):
    task_dir = tmp_path / "task-test"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    config = {
        "version": 1,
        "input_file": "input.csv",
        "buffer": {"shape": "circle", "size": 1000, "unit": "meters"},
        "variables": ["var_a", "var_b"],
        "execution": {"cpu_cores": 2, "memory_limit_gb": 4}
    }
    (task_dir / "config.json").write_text(json.dumps(config))
    csv_content = "patient_id,longitude,latitude,start_date,end_date\n"
    for i in range(5):
        csv_content += f"P{i},-82.35,29.65,2020-01-01,2020-12-31\n"
    (task_dir / "input.csv").write_text(csv_content)
    return task_dir

def test_mock_cli_runs_to_completion():
    with tempfile.TemporaryDirectory() as tmp:
        task_dir = create_task_dir(Path(tmp))
        result = subprocess.run(
            [sys.executable, "-m", "mock_cli.cli", "run", str(task_dir)],
            capture_output=True, text=True, timeout=30,
            cwd=str(Path(__file__).resolve().parent.parent)
        )
        assert result.returncode == 0
        status = json.loads((task_dir / "status.json").read_text())
        assert status["status"] == "finished"
        assert status["progress"] == 1.0
        assert (task_dir / "output" / "result.csv").exists()
        assert (task_dir / "logs.jsonl").exists()
        logs = (task_dir / "logs.jsonl").read_text().strip().split("\n")
        assert len(logs) >= 2
        for line in logs:
            log = json.loads(line)
            assert "ts" in log
            assert "level" in log
            assert "msg" in log

def test_mock_cli_invalid_config():
    with tempfile.TemporaryDirectory() as tmp:
        task_dir = Path(tmp) / "task-bad"
        task_dir.mkdir()
        (task_dir / "config.json").write_text('{"bad": true}')
        result = subprocess.run(
            [sys.executable, "-m", "mock_cli.cli", "run", str(task_dir)],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).resolve().parent.parent)
        )
        status = json.loads((task_dir / "status.json").read_text())
        assert status["status"] == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_mock_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Create mock_cli/cli.py**

```python
# backend/mock_cli/cli.py
"""Mock CLI pipeline that simulates the SPACESCANS linkage process."""
import json
import sys
import signal
import time
import csv
import random
from pathlib import Path
from datetime import datetime, timezone

cancelled = False

def signal_handler(sig, frame):
    global cancelled
    cancelled = True

signal.signal(signal.SIGTERM, signal_handler)

def write_status(task_dir: Path, status: str, progress: float = 0.0, message: str = "", error: str = ""):
    data = {
        "status": status,
        "progress": progress,
        "message": message,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pid": None  # will be set below
    }
    if error:
        data["error"] = error
    data["pid"] = __import__("os").getpid()
    (task_dir / "status.json").write_text(json.dumps(data, indent=2))

def append_log(task_dir: Path, level: str, msg: str):
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "level": level, "msg": msg}
    with open(task_dir / "logs.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")

def validate_config(config: dict) -> list[str]:
    errors = []
    if "version" not in config:
        errors.append("Missing 'version' field")
    if "input_file" not in config:
        errors.append("Missing 'input_file' field")
    if "buffer" not in config or "shape" not in config.get("buffer", {}):
        errors.append("Missing or invalid 'buffer' field")
    if "variables" not in config or not isinstance(config.get("variables"), list):
        errors.append("Missing or invalid 'variables' field")
    return errors

def run(task_dir_path: str):
    global cancelled
    task_dir = Path(task_dir_path)

    # Validate config
    config_path = task_dir / "config.json"
    if not config_path.exists():
        write_status(task_dir, "error", error="config.json not found")
        return 1

    config = json.loads(config_path.read_text())
    errors = validate_config(config)
    if errors:
        write_status(task_dir, "error", error="; ".join(errors))
        append_log(task_dir, "error", f"Config validation failed: {'; '.join(errors)}")
        return 1

    input_path = task_dir / config["input_file"]
    if not input_path.exists():
        write_status(task_dir, "error", error=f"Input file not found: {config['input_file']}")
        return 1

    # Read input
    with open(input_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    variables = config["variables"]
    total = len(rows)
    batch_size = max(1, total // 5)
    batches = (total + batch_size - 1) // batch_size

    write_status(task_dir, "running", 0.0, f"Starting linkage for {total} records")
    append_log(task_dir, "info", f"Started linkage task")
    append_log(task_dir, "info", f"Loaded {total} patient records from {config['input_file']}")
    append_log(task_dir, "info", f"Buffer: {config['buffer']['shape']}, {config['buffer']['size']}{config['buffer']['unit']}")
    append_log(task_dir, "info", f"Variables: {', '.join(variables)}")
    exec_opts = config.get("execution", {})
    append_log(task_dir, "info", f"CPU cores: {exec_opts.get('cpu_cores', 'auto')}, Memory: {exec_opts.get('memory_limit_gb', 'auto')}GB")

    # Process in batches
    results = []
    for batch_idx in range(batches):
        if cancelled:
            write_status(task_dir, "cancelled", message="Task cancelled by user")
            append_log(task_dir, "info", "Task cancelled by user")
            return 0

        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        progress = (batch_idx + 1) / batches
        msg = f"Processing batch {batch_idx + 1}/{batches} (records {start + 1}-{end})"

        write_status(task_dir, "running", round(progress, 2), msg)
        append_log(task_dir, "info", msg)

        # Simulate work
        for row in rows[start:end]:
            result_row = dict(row)
            for var in variables:
                result_row[var] = round(random.uniform(0, 100), 4)
            results.append(result_row)

        time.sleep(0.5)  # Simulate processing time

    # Write output
    output_dir = task_dir / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "result.csv"

    if results:
        fieldnames = list(results[0].keys())
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

    write_status(task_dir, "finished", 1.0, f"Completed linkage for {total} records")
    append_log(task_dir, "info", f"Results written to output/result.csv ({len(results)} rows)")
    append_log(task_dir, "info", "Task completed successfully")
    return 0

def main():
    if len(sys.argv) < 3 or sys.argv[1] != "run":
        print("Usage: python -m mock_cli.cli run <task_dir>", file=sys.stderr)
        sys.exit(1)
    sys.exit(run(sys.argv[2]))

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create mock_cli/__init__.py**

Empty file.

- [ ] **Step 5: Create mock_cli/__main__.py**

```python
from mock_cli.cli import main
main()
```

- [ ] **Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_mock_cli.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/mock_cli/ backend/tests/test_mock_cli.py
git commit -m "feat: mock CLI pipeline with file-based contract"
```

---

### Task 5: Task Management Backend

**Files:**
- Create: `backend/app/routers/tasks.py`
- Create: `backend/app/task_manager.py`
- Create: `backend/tests/test_tasks.py`

- [ ] **Step 1: Write failing tests for task CRUD + lifecycle**

```python
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
    # Force reimport
    import importlib
    import app.config
    importlib.reload(app.config)
    from app.main import create_app
    app = create_app()
    client = TestClient(app)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_tasks.py -v`
Expected: FAIL

- [ ] **Step 3: Create task_manager.py**

```python
# backend/app/task_manager.py
"""File-based task management. Each task is a directory with meta.json."""
import json
import uuid
import shutil
import csv
import os
import signal
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from app.config import settings

def create_task(user_id: int, task_name: str) -> dict:
    task_id = str(uuid.uuid4())
    task_dir = settings.TASKS_DIR / f"task-{task_id}"
    task_dir.mkdir(parents=True)
    (task_dir / "output").mkdir()
    meta = {
        "id": task_id,
        "user_id": user_id,
        "task_name": task_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_summary": None,
    }
    (task_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta

def list_tasks(user_id: int) -> list[dict]:
    tasks = []
    if not settings.TASKS_DIR.exists():
        return tasks
    for task_dir in sorted(settings.TASKS_DIR.iterdir()):
        meta_path = task_dir / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if meta.get("user_id") != user_id:
            continue
        status = _read_status(task_dir)
        meta["status"] = status
        tasks.append(meta)
    return tasks

def get_task(task_id: str) -> dict | None:
    task_dir = settings.TASKS_DIR / f"task-{task_id}"
    meta_path = task_dir / "meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    meta["status"] = _read_status(task_dir)
    return meta

def delete_task(task_id: str):
    task_dir = settings.TASKS_DIR / f"task-{task_id}"
    if task_dir.exists():
        shutil.rmtree(task_dir)

def save_upload(task_id: str, file_content: bytes, filename: str) -> dict:
    task_dir = settings.TASKS_DIR / f"task-{task_id}"
    input_path = task_dir / "input.csv"
    input_path.write_bytes(file_content)
    # Parse summary
    text = file_content.decode("utf-8")
    reader = csv.DictReader(text.splitlines())
    rows = list(reader)
    columns = reader.fieldnames or []
    required = {"patient_id", "longitude", "latitude", "start_date", "end_date"}
    missing = required - set(columns)
    if missing:
        input_path.unlink()
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    dates = [r.get("start_date", "") for r in rows] + [r.get("end_date", "") for r in rows]
    dates = [d for d in dates if d]
    summary = {
        "row_count": len(rows),
        "columns": columns,
        "date_range": {"min": min(dates) if dates else None, "max": max(dates) if dates else None},
        "filename": filename,
    }
    # Update meta
    meta_path = task_dir / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["data_summary"] = summary
    meta_path.write_text(json.dumps(meta, indent=2))
    return summary

def save_config(task_id: str, config: dict):
    task_dir = settings.TASKS_DIR / f"task-{task_id}"
    config["version"] = 1
    config["input_file"] = "input.csv"
    (task_dir / "config.json").write_text(json.dumps(config, indent=2))

def start_task(task_id: str) -> dict:
    task_dir = settings.TASKS_DIR / f"task-{task_id}"
    if not (task_dir / "config.json").exists():
        raise ValueError("Task not configured — missing config.json")
    if not (task_dir / "input.csv").exists():
        raise ValueError("No input file uploaded")
    # Spawn mock CLI subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "mock_cli.cli", "run", str(task_dir)],
        cwd=str(settings.BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"pid": proc.pid, "task_id": task_id}

def stop_task(task_id: str):
    task_dir = settings.TASKS_DIR / f"task-{task_id}"
    status = _read_status(task_dir)
    pid = status.get("pid")
    if not pid:
        raise ValueError("No running process found")
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait up to 10 seconds
        import time
        for _ in range(100):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except OSError:
                return
        # Force kill
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass  # Process already dead

def get_status(task_id: str) -> dict:
    task_dir = settings.TASKS_DIR / f"task-{task_id}"
    return _read_status(task_dir)

def get_logs(task_id: str, since: str | None = None) -> list[dict]:
    task_dir = settings.TASKS_DIR / f"task-{task_id}"
    logs_path = task_dir / "logs.jsonl"
    if not logs_path.exists():
        return []
    logs = []
    for line in logs_path.read_text().strip().split("\n"):
        if not line:
            continue
        entry = json.loads(line)
        if since and entry.get("ts", "") <= since:
            continue
        logs.append(entry)
    return logs

def get_result_path(task_id: str) -> Path | None:
    result_path = settings.TASKS_DIR / f"task-{task_id}" / "output" / "result.csv"
    if result_path.exists():
        return result_path
    return None

def recover_orphaned_tasks():
    """On startup, check for tasks stuck in 'running' state with dead PIDs."""
    if not settings.TASKS_DIR.exists():
        return
    for task_dir in settings.TASKS_DIR.iterdir():
        status_path = task_dir / "status.json"
        if not status_path.exists():
            continue
        status = json.loads(status_path.read_text())
        if status.get("status") != "running":
            continue
        pid = status.get("pid")
        if pid:
            try:
                os.kill(pid, 0)  # Check if alive
            except OSError:
                status["status"] = "error"
                status["message"] = "Process terminated unexpectedly"
                status_path.write_text(json.dumps(status, indent=2))

def _read_status(task_dir: Path) -> dict:
    status_path = task_dir / "status.json"
    if not status_path.exists():
        return {"status": "not_started", "progress": 0.0, "message": ""}
    return json.loads(status_path.read_text())
```

- [ ] **Step 4: Create routers/tasks.py**

```python
# backend/app/routers/tasks.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.auth import get_current_user
from app import task_manager

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

class CreateTaskRequest(BaseModel):
    task_name: str

class ConfigRequest(BaseModel):
    buffer: dict
    variables: list[str]
    execution: dict | None = None

def _verify_ownership(task_id: str, user: dict):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return task

@router.post("")
def create_task(req: CreateTaskRequest, user: dict = Depends(get_current_user)):
    return task_manager.create_task(user["id"], req.task_name)

@router.get("")
def list_tasks(user: dict = Depends(get_current_user)):
    return task_manager.list_tasks(user["id"])

@router.get("/{task_id}")
def get_task(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    return task_manager.get_task(task_id)

@router.delete("/{task_id}")
def delete_task(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    task_manager.delete_task(task_id)
    return {"status": "deleted"}

@router.post("/{task_id}/upload")
async def upload_file(task_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 100MB limit")
    try:
        summary = task_manager.save_upload(task_id, content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return summary

@router.put("/{task_id}/config")
def save_config(task_id: str, config: ConfigRequest, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    task_manager.save_config(task_id, config.model_dump(exclude_none=True))
    return {"status": "saved"}

@router.post("/{task_id}/start")
def start_task(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    try:
        return task_manager.start_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{task_id}/stop")
def stop_task(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    try:
        task_manager.stop_task(task_id)
        return {"status": "stopped"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{task_id}/status")
def get_status(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    return task_manager.get_status(task_id)

@router.get("/{task_id}/logs")
def get_logs(task_id: str, since: str | None = Query(None), user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    return task_manager.get_logs(task_id, since)

@router.get("/{task_id}/results")
def download_results(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    path = task_manager.get_result_path(task_id)
    if not path:
        raise HTTPException(status_code=404, detail="Results not available")
    return FileResponse(path, media_type="text/csv", filename="result.csv")
```

- [ ] **Step 5: Register tasks router and recovery in main.py**

Add to `create_app()`:
```python
from app.routers.tasks import router as tasks_router
app.include_router(tasks_router)

# In startup event:
from app.task_manager import recover_orphaned_tasks
recover_orphaned_tasks()
```

- [ ] **Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_tasks.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat: task management with file-based lifecycle and access control"
```

---

### Task 6: Ontology Build Script

**Files:**
- Create: `backend/scripts/build_ontology.py`
- Create: `backend/tests/test_ontology_build.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_ontology_build.py
import tempfile
from pathlib import Path

OWL_PATH = Path(__file__).resolve().parent.parent.parent / "ontology files" / "SPACEO_20251203.owl"

def test_build_ontology_outputs():
    if not OWL_PATH.exists():
        import pytest
        pytest.skip("OWL file not found")
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        from scripts.build_ontology import build_ontology
        build_ontology(str(OWL_PATH), str(output_dir))
        assert (output_dir / "index.json").exists()
        assert (output_dir / "nodes").is_dir()
        import json
        index = json.loads((output_dir / "index.json").read_text())
        assert isinstance(index, list)
        assert len(index) > 0
        # Each root should have a name and id
        for item in index:
            assert "id" in item
            assert "label" in item
        # Check at least one node file exists
        node_files = list((output_dir / "nodes").glob("*.json"))
        assert len(node_files) > 0
        # Check search index and metadata were generated
        assert (output_dir / "search-index.json").exists()
        assert (output_dir / "metadata.json").exists()
        search = json.loads((output_dir / "search-index.json").read_text())
        assert isinstance(search, list)
        assert len(search) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_ontology_build.py -v`
Expected: FAIL

- [ ] **Step 3: Create build_ontology.py**

```python
# backend/scripts/build_ontology.py
"""Parse OWL file and output split JSON files for the frontend ontology browser."""
import json
import sys
from pathlib import Path
from collections import defaultdict

def build_ontology(owl_path: str, output_dir: str):
    from owlready2 import get_ontology

    output = Path(output_dir)
    nodes_dir = output / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)

    onto = get_ontology(f"file://{owl_path}").load()

    # Build parent -> children map
    children_map = defaultdict(list)
    class_info = {}

    for cls in onto.classes():
        cls_id = cls.name
        label = cls.label.first() if cls.label else cls_id
        definition = ""
        if hasattr(cls, "INDIRECT_definition"):
            definition = str(cls.INDIRECT_definition.first() or "")
        elif hasattr(cls, "comment") and cls.comment:
            definition = str(cls.comment.first() or "")
        # Try skos:definition
        for ann in cls.get_annotations():
            pass  # owlready2 handles annotations differently

        # Get skos:definition if available
        try:
            from owlready2 import IRIS
            skos_def = getattr(cls, "definition", [])
            if skos_def:
                definition = str(skos_def[0]) if isinstance(skos_def, list) else str(skos_def)
        except:
            pass

        class_info[cls_id] = {
            "id": cls_id,
            "label": label,
            "definition": definition,
        }

        parents = cls.is_a
        is_root = True
        for parent in parents:
            if hasattr(parent, "name") and parent.name != "Thing":
                children_map[parent.name].append(cls_id)
                is_root = False

        if is_root:
            children_map["__root__"].append(cls_id)

    # Write index.json (top-level classes)
    roots = []
    for cls_id in children_map["__root__"]:
        info = class_info.get(cls_id, {"id": cls_id, "label": cls_id, "definition": ""})
        info["has_children"] = cls_id in children_map
        roots.append(info)
    roots.sort(key=lambda x: x["label"])
    (output / "index.json").write_text(json.dumps(roots, indent=2))

    # Write per-node files
    for parent_id, child_ids in children_map.items():
        if parent_id == "__root__":
            continue
        children = []
        for cls_id in child_ids:
            info = class_info.get(cls_id, {"id": cls_id, "label": cls_id, "definition": ""})
            info["has_children"] = cls_id in children_map
            children.append(info)
        children.sort(key=lambda x: x["label"])
        (nodes_dir / f"{parent_id}.json").write_text(json.dumps(children, indent=2))

    # Write metadata.json (all class details)
    (output / "metadata.json").write_text(json.dumps(class_info, indent=2))

    # Write search index (simple: list of {id, label, definition} for client-side search)
    search_items = [{"id": v["id"], "label": v["label"], "definition": v["definition"]} for v in class_info.values()]
    (output / "search-index.json").write_text(json.dumps(search_items, indent=2))

    print(f"Built ontology: {len(class_info)} classes, {len(children_map) - 1} parent nodes, {len(roots)} roots")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python build_ontology.py <owl_path> <output_dir>")
        sys.exit(1)
    build_ontology(sys.argv[1], sys.argv[2])
```

- [ ] **Step 4: Run test**

Run: `cd backend && python -m pytest tests/test_ontology_build.py -v`
Expected: PASS

- [ ] **Step 5: Run the build script to generate ontology JSON**

Run: `cd backend && python scripts/build_ontology.py "../ontology files/SPACEO_20251203.owl" ../frontend/public/ontology`
Expected: Output directory created with index.json, nodes/*.json, metadata.json, search-index.json

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/ backend/tests/test_ontology_build.py
git commit -m "feat: ontology build script - OWL to split JSON files"
```

---

## Chunk 2: Frontend Foundation

> **Ontology delivery note:** The spec lists `/api/ontology/*` endpoints but also says "Frontend fetches static JSON files directly from Next.js `/public` directory." We use the static approach — no backend ontology router. The build script outputs to `frontend/public/ontology/`. Frontend components fetch directly from `/ontology/index.json`, `/ontology/nodes/{id}.json`, etc.

### Task 7: Next.js Project Setup

**Files:**
- Create: `frontend/` (via create-next-app)
- Modify: `frontend/package.json`

- [ ] **Step 1: Scaffold Next.js project**

Run:
```bash
npx create-next-app@14 frontend --typescript --tailwind --eslint --app --src-dir --no-import-alias
```

- [ ] **Step 2: Install shadcn/ui**

Run:
```bash
cd frontend && npx shadcn@latest init -d
```

- [ ] **Step 3: Add core shadcn components**

Run:
```bash
cd frontend && npx shadcn@latest add button input label card dialog table badge tabs separator scroll-area progress toast dropdown-menu sheet command checkbox tree-view
```

- [ ] **Step 4: Verify dev server starts**

Run: `cd frontend && npm run dev`
Expected: Next.js starts on localhost:3000

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: Next.js 14 scaffolding with shadcn/ui and Tailwind"
```

---

### Task 8: Auth Pages (Login + Signup)

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/auth.ts`
- Create: `frontend/src/app/login/page.tsx`
- Create: `frontend/src/app/signup/page.tsx`
- Create: `frontend/src/components/auth-form.tsx`

- [ ] **Step 1: Create API client**

```typescript
// frontend/src/lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    throw new ApiError(401, "Unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new ApiError(res.status, body.detail || body.error || "Request failed");
  }
  return res.json();
}

export const api = {
  // Auth
  signup: (data: { email: string; password: string; first_name: string; last_name: string }) =>
    request<{ access_token: string }>("/api/auth/signup", { method: "POST", body: JSON.stringify(data) }),
  login: (data: { email: string; password: string }) =>
    request<{ access_token: string }>("/api/auth/login", { method: "POST", body: JSON.stringify(data) }),

  // Tasks
  listTasks: () => request<any[]>("/api/tasks"),
  createTask: (task_name: string) => request<any>("/api/tasks", { method: "POST", body: JSON.stringify({ task_name }) }),
  getTask: (id: string) => request<any>(`/api/tasks/${id}`),
  deleteTask: (id: string) => request<any>(`/api/tasks/${id}`, { method: "DELETE" }),
  uploadFile: async (id: string, file: File) => {
    const token = localStorage.getItem("token");
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/api/tasks/${id}/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    if (!res.ok) throw new ApiError(res.status, (await res.json()).detail);
    return res.json();
  },
  saveConfig: (id: string, config: any) =>
    request<any>(`/api/tasks/${id}/config`, { method: "PUT", body: JSON.stringify(config) }),
  startTask: (id: string) => request<any>(`/api/tasks/${id}/start`, { method: "POST" }),
  stopTask: (id: string) => request<any>(`/api/tasks/${id}/stop`, { method: "POST" }),
  getStatus: (id: string) => request<any>(`/api/tasks/${id}/status`),
  getLogs: (id: string, since?: string) =>
    request<any[]>(`/api/tasks/${id}/logs${since ? `?since=${since}` : ""}`),
  downloadResults: (id: string) => `${API_BASE}/api/tasks/${id}/results`,
};
```

- [ ] **Step 2: Create auth helper**

```typescript
// frontend/src/lib/auth.ts
export function isAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("token");
}

export function setToken(token: string) {
  localStorage.setItem("token", token);
}

export function clearToken() {
  localStorage.removeItem("token");
}
```

- [ ] **Step 3: Create auth form component**

Use @frontend-design:frontend-design skill for the actual implementation. The form should include:
- Email + password fields (login) or email + password + first/last name (signup)
- Error display (show `ApiError.detail` in a red alert below the form)
- Loading state (disable submit button + show spinner while request is pending)
- Link to switch between login/signup
- Modern, clean styling with shadcn/ui `Input`, `Label`, `Button`, `Card` components
- Must be a `"use client"` component

- [ ] **Step 4: Create login page**

`"use client"` page. Uses `AuthForm` in login mode. On success: call `setToken(data.access_token)`, also store `email` in localStorage (from the login form input), then `router.push("/dashboard")` using `useRouter` from `next/navigation`.

- [ ] **Step 5: Create signup page**

`"use client"` page. Uses `AuthForm` in signup mode. Same token + redirect pattern as login.

- [ ] **Step 6: Verify auth flow works end-to-end**

Run backend + frontend. Test signup → redirect to dashboard → login works.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat: auth pages with login and signup"
```

---

### Task 9: Dashboard — Task List Page

**Files:**
- Create: `frontend/src/app/dashboard/page.tsx`
- Create: `frontend/src/app/dashboard/layout.tsx`
- Create: `frontend/src/components/task-list.tsx`
- Create: `frontend/src/components/status-badge.tsx`

- [ ] **Step 1: Create dashboard layout with auth guard**

`"use client"` layout component. This acts as the auth guard for ALL `/dashboard/**` routes.

Implementation:
- `useEffect` on mount: check `localStorage.getItem("token")`. If missing, `router.push("/login")`.
- Read user email from `localStorage.getItem("email")` (stored at login time).
- Render nav bar: left = "SPACESCANS" logo link to `/`, right = user email + "Logout" button.
- Logout button: call `clearToken()`, remove `email` from localStorage, `router.push("/login")`.
- Render `{children}` below nav bar.
- Use shadcn `Button`, `Separator` components.

- [ ] **Step 2: Create status badge component**

Maps status strings to colored badges:
- `not_started` → gray
- `running` → blue with progress
- `finished` → green
- `error` → red
- `cancelled` → yellow

- [ ] **Step 3: Create task list component**

- Fetches tasks via `api.listTasks()`
- Shows table with: name, created date, status badge (with inline progress if running), action link
- "New Task" button at top

- [ ] **Step 4: Create dashboard page**

```typescript
// frontend/src/app/dashboard/page.tsx
// Renders TaskList component
```

- [ ] **Step 5: Test dashboard with backend running**

Create a task via API, verify it shows in the list.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat: dashboard with task list and status badges"
```

---

### Task 10: Task Creation Wizard — Upload Step

**Files:**
- Create: `frontend/src/app/dashboard/task/new/page.tsx`
- Create: `frontend/src/components/wizard/wizard-layout.tsx`
- Create: `frontend/src/components/wizard/upload-step.tsx`

- [ ] **Step 1: Create wizard layout with stepper**

4 steps: Upload Data → Buffer Settings → Variables → Review & Run
Stepper component shows current step, completed steps, and upcoming steps.

**State management:** The `new/page.tsx` parent component manages all wizard state via `useState`:
- `step` (number, 0-3)
- `taskId` (string | null, set after task creation in step 0)
- `dataSummary` (object | null, returned from upload API)
- `bufferConfig` ({shape, size, unit})
- `selectedVariables` (string[])
- `executionOptions` ({cpu_cores, memory_limit_gb} | null)

Each step component receives relevant state as props and calls an `onComplete` callback to advance.

- [ ] **Step 2: Create upload step**

- Task name input
- File drop zone (drag & drop or click to upload)
- After upload: show data summary (row count, columns, date range)
- Validate required columns, show error if missing
- "Next" button enabled only after successful upload

- [ ] **Step 3: Wire up to API**

On file select: `api.createTask()` then `api.uploadFile()`

- [ ] **Step 4: Test upload flow end-to-end**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat: task wizard with upload step"
```

---

### Task 11: Task Creation Wizard — Buffer & Variables Steps

**Files:**
- Create: `frontend/src/components/wizard/buffer-step.tsx`
- Create: `frontend/src/components/wizard/variables-step.tsx`
- Create: `frontend/src/components/wizard/review-step.tsx`
- Create: `frontend/src/components/ontology-tree.tsx`
- Create: `frontend/src/components/ontology-search.tsx`

- [ ] **Step 1: Create buffer step**

- Shape selector: Circle / Square (toggle buttons with visual preview)
- Size input: numeric + "meters" unit label
- Visual preview showing the buffer shape

- [ ] **Step 2: Create ontology tree component**

- Fetches `/ontology/index.json` for roots
- On expand: fetches `/ontology/nodes/{id}.json`
- Lazy loading via shadcn tree-view or custom expandable tree
- Checkbox mode for variable selection

- [ ] **Step 3: Create ontology search component**

- Loads `/ontology/search-index.json` on mount
- Client-side filtering as user types
- Results link to tree expansion

- [ ] **Step 4: Create variables step**

- Left panel: ontology tree with search bar on top
- Selected variables shown as chips/badges below
- Breadcrumbs showing current path in hierarchy

- [ ] **Step 5: Create review step**

- Summary of all selections: file info, buffer, variables list
- **Date coverage check:** Compare `dataSummary.date_range` against each selected variable's `available_since` from `metadata.json`. Show a yellow warning banner if any variable's data range doesn't cover the input data range (non-blocking — user can still proceed).
- Advanced options toggle: CPU cores slider, memory limit dropdown
- "Start Task" button
- On start: `api.saveConfig()` then `api.startTask()` then redirect to `/dashboard/task/[id]`

- [ ] **Step 6: Test full wizard flow end-to-end**

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat: task wizard buffer, variable selection, and review steps"
```

---

## Chunk 3: Task Progress & Results

### Task 12: Task Detail — Progress View

**Files:**
- Create: `frontend/src/app/dashboard/task/[id]/page.tsx`
- Create: `frontend/src/components/progress-panel.tsx`
- Create: `frontend/src/components/log-viewer.tsx`

- [ ] **Step 1: Create log viewer component**

- Dark terminal-style panel
- Scrolling log lines with timestamps, colored by level (info=green, warn=yellow, error=red)
- Auto-scrolls to bottom on new entries
- Polls `api.getLogs(id, since)` every 2 seconds

- [ ] **Step 2: Create progress panel component**

- Progress bar with percentage
- Current message text
- Stop button (calls `api.stopTask()`)

- [ ] **Step 3: Create task detail page**

- Header: task name + status badge
- If running: progress panel + log viewer, polling every 2s
- If finished: "View Results" button
- If error: error message + log viewer (no polling)
- If not_started: "Configure" link back to wizard
- If cancelled: status message + log viewer

- [ ] **Step 4: Test with mock CLI running**

Create task, upload, configure, start. Watch progress update in real time.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat: task progress view with live logs"
```

---

### Task 13: Task Results Page

**Files:**
- Create: `frontend/src/app/dashboard/task/[id]/results/page.tsx`
- Create: `frontend/src/components/results-summary.tsx`

- [ ] **Step 1: Create results summary component**

- Shows task name, completion time
- Data summary: input rows, output rows, variables linked
- Download button (links to `api.downloadResults(id)`)

- [ ] **Step 2: Create results page**

- Renders results summary
- Download CSV button

- [ ] **Step 3: Test end-to-end flow**

Complete full cycle: signup → create task → upload → configure → start → wait for completion → view results → download CSV.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat: task results page with download"
```

---

### Task 14: Data Catalog Page (Public)

**Files:**
- Create: `frontend/src/app/catalog/page.tsx`
- Create: `frontend/src/components/catalog-browser.tsx`
- Create: `frontend/src/components/catalog-detail.tsx`

- [ ] **Step 1: Create catalog browser**

- Import `OntologyTree` from `@/components/ontology-tree` with `selectable={false}` (no checkboxes). Same static JSON paths (`/ontology/index.json`, `/ontology/nodes/{id}.json`).
- Search bar on top (reuse `OntologySearch` from Task 11)
- Left panel: tree, right panel: detail
- On click: load metadata from `/ontology/metadata.json` and show: label, definition, data source, coverage dates, spatial resolution. Use shadcn `Card` for the detail panel.

- [ ] **Step 2: Create catalog page**

- Public (no auth required)
- Full-width layout with tree + detail panel

- [ ] **Step 3: Create breadcrumbs for catalog navigation**

- [ ] **Step 4: Test catalog browsing**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat: public data catalog with ontology browser"
```

---

### Task 15: Landing Page

**Files:**
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/components/landing-hero.tsx`

- [ ] **Step 1: Create landing page**

Use @frontend-design:frontend-design skill. Should include:
- Hero section with project name and description
- Key features (task management, data linkage, ontology catalog)
- CTA buttons: "Get Started" → /signup, "Browse Catalog" → /catalog
- Clean, modern design

- [ ] **Step 2: Commit**

```bash
git add frontend/src/
git commit -m "feat: landing page"
```

---

### Task 16: Integration Testing & Polish

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && python -m pytest -v`

- [ ] **Step 2: Fix any failures**

- [ ] **Step 3: Test full E2E flow manually**

1. Start backend: `cd backend && uvicorn app.main:app --reload --port 8000`
2. Build ontology: `cd backend && python scripts/build_ontology.py "../ontology files/SPACEO_20251203.owl" ../frontend/public/ontology`
3. Start frontend: `cd frontend && npm run dev`
4. Signup → Create task → Upload CSV → Configure → Start → Watch progress → Download results
5. Browse catalog

- [ ] **Step 4: Fix any issues found**

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "fix: integration fixes and polish"
```
