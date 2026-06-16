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
    import pandas as pd  # noqa: PLC0415
    from app import variable_registry  # noqa: PLC0415

    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    input_csv = task_dir / "input.csv"
    if not input_csv.exists():
        raise FileNotFoundError("No input uploaded")

    resolved: dict[str, dict] = {}
    unknown: list[str] = []
    for var in variable_keys:
        try:
            resolved[var] = variable_registry.get_variable(var)
        except KeyError:
            unknown.append(var)
    if unknown:
        raise KeyError(", ".join(unknown))

    df = pd.read_csv(
        input_csv,
        parse_dates=["startDate", "endDate"],
        dtype={"state_fips": "string", "county_fips": "string",
               "tract_geoid": "string", "bg_geoid": "string"},
    )
    n_total = len(df)

    if n_total == 0:
        return {
            "row_count": 0,
            "variables": {
                var: {
                    "coverage_years": list(resolved[var]["coverage_years"]),
                    "patients_in_time_window": 0,
                    "patients_in_region": 0,
                    "patients_covered": 0,
                    "coverage_pct": 0.0,
                    "warnings": ["Cohort is empty — no patients to evaluate"],
                    "boundary": resolved[var]["boundary"],
                    "display_unit": resolved[var]["display_unit"],
                }
                for var in variable_keys
            },
        }

    out_vars: dict[str, dict] = {}
    for var in variable_keys:
        m = resolved[var]
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
            "boundary": m["boundary"],
            "display_unit": m["display_unit"],
        }

    return {"row_count": n_total, "variables": out_vars}


class TaskBusyError(RuntimeError):
    """Raised by start_task when another task currently holds .run_lock."""

    def __init__(self):
        super().__init__("another task is already running")


def _task_dir(task_id: str) -> Path:
    """Resolve task_id to its on-disk directory under TASKS_DIR."""
    return app.config.settings.TASKS_DIR / f"task-{task_id}"


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
    """Sprint 3: Popen the supervisor and return its pid synchronously.

    Replaces the Sprint 2 single-runner spawn. The request thread now Popens
    `python -m app.dispatcher run <task_id>` (in a new session) and returns
    immediately with the supervisor pid. The supervisor sequentially spawns
    each per-experiment runner.
    """
    task_dir = _task_dir(task_id)
    if not (task_dir / "config.json").exists():
        raise FileNotFoundError(f"config.json missing for task {task_id}")

    cmd = [
        sys.executable,
        "-m", "app.dispatcher",
        "run", task_id,
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(app.config.settings.BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _write_status(task_dir, pid=proc.pid)
    return {"pid": proc.pid, "task_id": task_id}

def stop_task(task_id: str) -> dict:
    """Sprint 4 F1a: SIGTERM ONLY the recorded per-experiment runner pids
    when at least one is present. The supervisor pid is signalled ONLY as
    a fallback when no runner pid has been recorded yet (early-cancel
    before dispatcher.dispatch launched any slot).

    Rationale (spec 2026-06-16 lines 191-243): SIGTERM-ing the supervisor
    kills the dispatcher's Python interpreter before its blocking
    proc.wait() can observe rc == 143, defeating the cancellation
    discriminator added by Sprint 4 F1b. Narrowing the scope to runner
    pids lets the dispatcher reach its rc == 143 branch naturally.
    """
    task_dir = _task_dir(task_id)
    status_path = task_dir / "status.json"
    if not status_path.exists():
        return {"status": "no-op", "reason": "no status.json"}
    status = json.loads(status_path.read_text())

    runner_pids: list[int] = []
    for exp in (status.get("experiments") or {}).values():
        exp_pid = exp.get("pid")
        if isinstance(exp_pid, int) and exp.get("status") == "running":
            runner_pids.append(exp_pid)

    if runner_pids:
        pids_to_signal: list[int] = runner_pids
    else:
        # Defensive fallback: no runner recorded (early-cancel before
        # dispatcher launched any slot). SIGTERM the supervisor so the
        # dispatcher process is still reaped.
        pids_to_signal = []
        sup_pid = status.get("pid")
        if isinstance(sup_pid, int):
            pids_to_signal.append(sup_pid)

    sent: list[int] = []
    for pid in pids_to_signal:
        try:
            os.kill(pid, signal.SIGTERM)
            sent.append(pid)
        except ProcessLookupError:
            continue
    return {"status": "stopping", "signalled_pids": sent}

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
        return {"status": "not_started", "progress": 0.0, "message": "",
                "steps": [], "current_step": None, "total_steps": 0,
                "experiments": {}}
    return json.loads(status_path.read_text())


def _derive_flat_fields(experiments: dict) -> dict:
    """Compute legacy flat steps[]/current_step/total_steps/progress from
    the experiments map, preserving insertion (dispatch) order.

    Aggregated progress = sum(completed sub-steps) / total_steps.
    """
    flat_steps: list[str] = []
    completed = 0.0
    current_step = None
    for exp_key, exp in experiments.items():
        steps = list(exp.get("steps") or [])
        flat_steps.extend(steps)
        completed += float(exp.get("progress") or 0.0) * len(steps)
        if exp.get("status") == "running" and exp.get("current_step"):
            current_step = exp["current_step"]
    total = len(flat_steps)
    progress = (completed / total) if total else 0.0
    return {"steps": flat_steps, "current_step": current_step,
            "total_steps": total, "progress": round(progress, 6)}


def _write_status(task_dir: Path, **kwargs) -> dict:
    """Atomic read-modify-write of status.json with experiments-aware merge."""
    task_dir.mkdir(parents=True, exist_ok=True)
    lock_path = task_dir / ".status_lock"
    lock_path.touch()
    lock_fd = os.open(str(lock_path), os.O_RDWR)

    import time as _time
    deadline = _time.monotonic() + 5.0
    while True:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if _time.monotonic() >= deadline:
                os.close(lock_fd)
                raise TimeoutError(
                    f"_write_status: could not acquire {lock_path} within 5s"
                )
            _time.sleep(0.01)

    try:
        status_path = task_dir / "status.json"
        if status_path.exists():
            current = json.loads(status_path.read_text())
        else:
            current = {}

        incoming_experiments = kwargs.pop("experiments", None)
        if incoming_experiments is not None:
            merged_experiments = dict(current.get("experiments") or {})
            for exp_key, exp_payload in incoming_experiments.items():
                existing_slot = dict(merged_experiments.get(exp_key) or {})
                existing_slot.update(exp_payload)
                merged_experiments[exp_key] = existing_slot
            current["experiments"] = merged_experiments
        elif "experiments" not in current:
            current["experiments"] = {}

        current.update(kwargs)

        current.update(_derive_flat_fields(current["experiments"]))

        tmp_path = task_dir / "status.json.tmp"
        tmp_path.write_text(json.dumps(current, indent=2))
        os.replace(str(tmp_path), str(status_path))
        return current
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
