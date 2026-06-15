# backend/app/task_manager.py
"""File-based task management. Each task is a directory with meta.json."""
import json
import uuid
import shutil
import csv
import fcntl
import os
import signal
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
import app.config


# Module-level cache for variable_metadata.json (mtime-invalidated).
_VARIABLE_METADATA_CACHE: dict | None = None
_VARIABLE_METADATA_MTIME: float | None = None


def _load_variable_metadata() -> dict:
    """Read and cache backend/data/variable_metadata.json.

    Cache is invalidated whenever the file's mtime changes so dev edits
    are picked up without restarting the server.
    """
    global _VARIABLE_METADATA_CACHE, _VARIABLE_METADATA_MTIME
    path = app.config.settings.DATA_DIR / "variable_metadata.json"
    if not path.exists():
        raise FileNotFoundError(f"variable_metadata.json missing at {path}")
    mtime = path.stat().st_mtime
    if _VARIABLE_METADATA_CACHE is None or mtime != _VARIABLE_METADATA_MTIME:
        _VARIABLE_METADATA_CACHE = json.loads(path.read_text())
        _VARIABLE_METADATA_MTIME = mtime
    return _VARIABLE_METADATA_CACHE


def compute_coverage(task_id: str, variable_keys: list[str]) -> dict:
    """Compute per-variable cohort coverage statistics for a task's input.csv.

    Returns
    -------
    dict
        Shape:
            {
              "row_count": int,
              "variables": {
                  var_key: {
                      "coverage_years": [int, int],
                      "patients_in_time_window": int,
                      "patients_in_region": int,
                      "patients_covered": int,
                      "coverage_pct": float (2 dp),
                      "warnings": list[str],
                  },
                  ...
              }
            }

    Raises
    ------
    FileNotFoundError
        If the task's input.csv is missing.
    KeyError
        If any requested variable is not in variable_metadata.json (the
        exception args[0] is a comma-separated list of unknown keys).
    """
    import pandas as pd  # noqa: PLC0415  — local import to keep cold-import light

    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    input_csv = task_dir / "input.csv"
    if not input_csv.exists():
        raise FileNotFoundError("No input uploaded")

    metadata = _load_variable_metadata()
    unknown = [v for v in variable_keys if v not in metadata]
    if unknown:
        raise KeyError(", ".join(unknown))

    df = pd.read_csv(
        input_csv,
        parse_dates=["startDate", "endDate"],
        dtype={"state_fips": "string", "county_fips": "string",
               "tract_geoid": "string", "bg_geoid": "string"},
    )
    n_total = len(df)

    out_vars: dict[str, dict] = {}
    for var in variable_keys:
        m = metadata[var]
        y0, y1 = m["coverage_years"]
        cov_start = pd.Timestamp(f"{y0}-01-01")
        cov_end = pd.Timestamp(f"{y1}-12-31")
        in_time = (df["startDate"] <= cov_end) & (df["endDate"] >= cov_start)
        if m.get("coverage_region") == "CONUS":
            in_region = (
                df["longitude"].between(-125, -66)
                & df["latitude"].between(24, 50)
            )
        else:
            in_region = pd.Series(True, index=df.index)
        covered = in_time & in_region

        warnings: list[str] = []
        time_out_pct = (~in_time).sum() / n_total * 100
        if time_out_pct > 5:
            warnings.append(
                f"{time_out_pct:.0f}% of patients have episodes entirely outside "
                f"{y0}-{y1}"
            )
        region_out_pct = (~in_region).sum() / n_total * 100
        if region_out_pct > 5:
            warnings.append(
                f"{region_out_pct:.0f}% of patients fall outside the "
                f"{m['coverage_region']} coverage region"
            )

        out_vars[var] = {
            "coverage_years": [y0, y1],
            "patients_in_time_window": int(in_time.sum()),
            "patients_in_region": int(in_region.sum()),
            "patients_covered": int(covered.sum()),
            "coverage_pct": round(100 * covered.sum() / n_total, 2),
            "warnings": warnings,
        }

    return {"row_count": n_total, "variables": out_vars}


class TaskBusyError(RuntimeError):
    """Raised by start_task when another task currently holds .run_lock."""

    def __init__(self):
        super().__init__("another task is already running")

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

def _flatten_status_into_meta(meta: dict, status: dict) -> None:
    """Project the relevant status.json fields onto a task's meta dict.

    The frontend Task interface expects `status` as a string (one of
    not_started/running/finished/error/cancelled) plus optional top-level
    `progress` and `error_message` fields — not the raw status.json dict.
    """
    meta["status"] = status.get("status", "not_started")
    meta["progress"] = status.get("progress")
    err = status.get("error") or status.get("message") if status.get("status") == "error" else None
    if err:
        meta["error_message"] = err


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
        _flatten_status_into_meta(meta, _read_status(task_dir))
        tasks.append(meta)
    return tasks

def get_task(task_id: str) -> dict | None:
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    meta_path = task_dir / "meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    _flatten_status_into_meta(meta, _read_status(task_dir))
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
    # Default experiment to bg_ndi_wi but allow caller-provided override.
    config = {"experiment": "bg_ndi_wi", **config}
    config["version"] = 1
    config["input_file"] = "input.csv"
    (task_dir / "config.json").write_text(json.dumps(config, indent=2))

def start_task(task_id: str) -> dict:
    """Spawn the experiment subprocess for a task.

    The subprocess itself acquires .run_lock for its lifetime; the kernel
    releases the lock when the process exits. To surface TaskBusyError to
    HTTP callers without spawning a doomed subprocess, we do a quick
    pre-check here (acquire-then-release) before dispatch.

    There is a microsecond TOCTOU window between the pre-check release and
    the subprocess starting up: a concurrent caller could race in and grab
    the lock first. In that case the loser's subprocess will fail its own
    flock attempt and write status="error" — acceptable for v1.
    """
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    if not (task_dir / "config.json").exists():
        raise ValueError("Task not configured — missing config.json")
    if not (task_dir / "input.csv").exists():
        raise ValueError("No input file uploaded")

    config = json.loads((task_dir / "config.json").read_text())
    experiment = config.get("experiment", "bg_ndi_wi")

    # Pre-check the lock; the real acquisition happens inside the subprocess.
    lock_path = app.config.settings.DATA_DIR / ".run_lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    pre_fd = os.open(str(lock_path), os.O_RDWR)
    try:
        fcntl.flock(pre_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(pre_fd)
        raise TaskBusyError()
    # Release immediately — the subprocess re-acquires and holds it for life.
    fcntl.flock(pre_fd, fcntl.LOCK_UN)
    os.close(pre_fd)

    if experiment == "bg_ndi_wi":
        cmd = [
            str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
            "-m", "app.experiments.bg_ndi_wi", "run", str(task_dir),
        ]
    else:
        cmd = [sys.executable, "-m", "mock_cli.cli", "run", str(task_dir)]

    proc = subprocess.Popen(
        cmd,
        cwd=str(app.config.settings.BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"pid": proc.pid, "task_id": task_id}

def stop_task(task_id: str):
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    status = _read_status(task_dir)
    pid = status.get("pid")
    if not pid:
        raise ValueError("No running process found")
    try:
        # Send SIGTERM to the orchestrator's whole process group so the
        # spacescans grandchild (in a new session via start_new_session=True)
        # also receives it. Falls back to os.kill if the pid has no group.
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            os.kill(pid, signal.SIGTERM)
        # Wait up to 10s for graceful exit
        import time
        for _ in range(100):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except OSError:
                return
        # Force kill the group
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except OSError:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    except OSError:
        pass

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
    """On startup, check for tasks stuck in 'running' state with dead PIDs.

    Only marks status="error" when the pre-existing status was "running" and
    the recorded pid is no longer alive. Tasks that already wrote a terminal
    status (cancelled / finished / error) before exiting are left untouched —
    in particular, a task that was SIGTERMed via stop_task installs a handler
    that writes status="cancelled" before exit, and we must preserve that.
    """
    if not app.config.settings.TASKS_DIR.exists():
        return
    for task_dir in app.config.settings.TASKS_DIR.iterdir():
        status_path = task_dir / "status.json"
        if not status_path.exists():
            continue
        status = json.loads(status_path.read_text())
        # Only consider tasks still claiming "running"; never overwrite a
        # terminal status that the orchestrator already wrote.
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
