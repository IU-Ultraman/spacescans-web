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
import app.config

def create_task(user_id: int, task_name: str) -> dict:
    task_id = str(uuid.uuid4())
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
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
    if not app.config.settings.TASKS_DIR.exists():
        return tasks
    for task_dir in sorted(app.config.settings.TASKS_DIR.iterdir()):
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
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    meta_path = task_dir / "meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    meta["status"] = _read_status(task_dir)
    return meta

def delete_task(task_id: str):
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    if task_dir.exists():
        shutil.rmtree(task_dir)

def save_upload(task_id: str, file_content: bytes, filename: str) -> dict:
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    input_path = task_dir / "input.csv"
    input_path.write_bytes(file_content)
    # Parse summary
    text = file_content.decode("utf-8")
    reader = csv.DictReader(text.splitlines())
    rows = list(reader)
    columns = reader.fieldnames or []
    required = {"pid", "startDate", "endDate", "longitude", "latitude"}
    missing = required - set(columns)
    if missing:
        input_path.unlink()
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    dates = [r.get("startDate", "") for r in rows] + [r.get("endDate", "") for r in rows]
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
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    config["version"] = 1
    config["input_file"] = "input.csv"
    (task_dir / "config.json").write_text(json.dumps(config, indent=2))

def start_task(task_id: str) -> dict:
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    if not (task_dir / "config.json").exists():
        raise ValueError("Task not configured — missing config.json")
    if not (task_dir / "input.csv").exists():
        raise ValueError("No input file uploaded")
    # Spawn mock CLI subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "mock_cli.cli", "run", str(task_dir)],
        cwd=str(app.config.settings.BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"pid": proc.pid, "task_id": task_id}

def stop_task(task_id: str):
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
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
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    return _read_status(task_dir)

def get_logs(task_id: str, since: str | None = None) -> list[dict]:
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
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
    result_path = app.config.settings.TASKS_DIR / f"task-{task_id}" / "output" / "result.csv"
    if result_path.exists():
        return result_path
    return None

def recover_orphaned_tasks():
    """On startup, check for tasks stuck in 'running' state with dead PIDs."""
    if not app.config.settings.TASKS_DIR.exists():
        return
    for task_dir in app.config.settings.TASKS_DIR.iterdir():
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
