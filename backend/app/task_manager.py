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


# Columns produced by the cohort upload or by geocoding — never an "exposure".
# Shared by /results/{preview,histogram,geo} so all three endpoints agree on
# what counts as input (cohort/geocode) vs. exposure (variable output) columns.
INPUT_COLS: frozenset[str] = frozenset({
    "pid",
    "episode_id",
    "startDate",
    "endDate",
    "longitude",
    "latitude",
    "state_fips",
    "county_fips",
    "tract_geoid",
    "bg_geoid",
})


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
                    "temporal": resolved[var].get("temporal", "yearly"),
                }
                for var in variable_keys
            },
        }

    out_vars: dict[str, dict] = {}
    for var in variable_keys:
        m = resolved[var]
        y0, y1 = m["coverage_years"]
        # Static products (e.g. NHD bluespace, BTS noise) have no temporal
        # dimension — their exposure value applies to any study year. Skip the
        # time-window gate so the coverage panel reflects spatial coverage only.
        temporal = m.get("temporal", "yearly")
        is_static = temporal == "static"
        if is_static:
            in_time = pd.Series(True, index=df.index)
        else:
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
        # No time-window warning for static products — only yearly ones can
        # fall "outside" their coverage years.
        if not is_static:
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
            "temporal": temporal,
        }

    return {"row_count": n_total, "variables": out_vars}


class TaskBusyError(RuntimeError):
    """Raised by start_task when another task currently holds .run_lock."""

    def __init__(self):
        super().__init__("another task is already running")


def _task_dir(task_id: str) -> Path:
    """Resolve task_id to its on-disk directory under TASKS_DIR."""
    return app.config.settings.TASKS_DIR / f"task-{task_id}"


def _name_taken(user_id: int, name: str, exclude_id: str | None = None) -> bool:
    """Is `name` already used by another of this user's tasks?
    Comparison is trimmed + case-insensitive."""
    target = name.strip().lower()
    if not target or not app.config.settings.TASKS_DIR.exists():
        return False
    for task_dir in app.config.settings.TASKS_DIR.iterdir():
        meta_path = task_dir / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            continue
        if meta.get("user_id") != user_id or meta.get("id") == exclude_id:
            continue
        if str(meta.get("task_name", "")).strip().lower() == target:
            return True
    return False


def create_task(user_id: int, task_name: str) -> dict:
    name = task_name.strip()
    if not name:
        raise ValueError("Task name is required")
    if _name_taken(user_id, name):
        raise ValueError(f"A task named '{name}' already exists")
    task_id = str(uuid.uuid4())
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    task_dir.mkdir(parents=True)
    (task_dir / "output").mkdir()
    meta = {
        "id": task_id,
        "user_id": user_id,
        "task_name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_summary": None,
    }
    (task_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def rename_task(task_id: str, user_id: int, new_name: str) -> dict:
    """Rename a task (updates meta.json). Raises ValueError on empty or
    duplicate (per-user) name."""
    name = new_name.strip()
    if not name:
        raise ValueError("Task name is required")
    if _name_taken(user_id, name, exclude_id=task_id):
        raise ValueError(f"A task named '{name}' already exists")
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    meta_path = task_dir / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["task_name"] = name
    meta_path.write_text(json.dumps(meta, indent=2))
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


def _attach_variables(meta: dict, task_dir: Path) -> None:
    """Pull the selected variables + buffer config out of config.json (if
    present) so the task endpoints can surface them. Missing/invalid → []/None."""
    config_path = task_dir / "config.json"
    if not config_path.exists():
        meta["variables"] = []
        meta["buffer"] = None
        return
    try:
        cfg = json.loads(config_path.read_text())
        vars_ = cfg.get("variables") or []
        meta["variables"] = [str(v) for v in vars_ if isinstance(v, str)]
        buf = cfg.get("buffer")
        meta["buffer"] = buf if isinstance(buf, dict) else None
    except Exception:
        meta["variables"] = []
        meta["buffer"] = None


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
        _reap_if_dead(task_dir)
        _flatten_status_into_meta(meta, _read_status(task_dir))
        _attach_variables(meta, task_dir)
        tasks.append(meta)
    return tasks

def get_task(task_id: str) -> dict | None:
    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    meta_path = task_dir / "meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    _reap_if_dead(task_dir)
    _flatten_status_into_meta(meta, _read_status(task_dir))
    _attach_variables(meta, task_dir)
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

    Sprint 4 F2: synchronously probe DATA_DIR/.run_lock before Popen. If
    another task currently holds it, raise TaskBusyError so the router can
    map to HTTP 409. The probe releases immediately — the runner will
    re-acquire the lock for real inside its own process.
    """
    task_dir = _task_dir(task_id)
    if not (task_dir / "config.json").exists():
        raise FileNotFoundError(f"config.json missing for task {task_id}")

    lock_path = app.config.settings.DATA_DIR / ".run_lock"
    lock_path.touch(exist_ok=True)
    probe_fd = os.open(str(lock_path), os.O_RDWR)
    try:
        try:
            fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise TaskBusyError() from exc
        finally:
            # Release immediately — the runner will re-acquire.
            fcntl.flock(probe_fd, fcntl.LOCK_UN)
    finally:
        os.close(probe_fd)

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
    # Stamp status='running' synchronously, in the same write that records the
    # supervisor pid. The dispatcher subprocess re-affirms 'running' once it has
    # booted (heavy imports take seconds), but the client navigates to the task
    # detail page the instant this call returns — and that page only begins
    # polling when status is already 'running'. Without this, the freshly
    # started task is observable as 'not_started' (rendered "Not Configured
    # Yet") for the whole boot window, and the page never re-polls out of it.
    _write_status(task_dir, status="running", pid=proc.pid)
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

    # Sprint 12 G6: write a .cancelled sentinel BEFORE SIGTERMing so the
    # dispatcher's rc==143 branch can distinguish user-intent cancellation
    # from external SIGTERM (OOM killer, sysadmin kill -15, container
    # eviction). Without the sentinel, any external SIGTERM that yields
    # rc=143 would be misreported as cancelled — a false positive on user
    # intent. The sentinel is created unconditionally on the stop_task
    # path, including the supervisor-fallback case, so an early-cancel
    # still records "user-intent" lineage.
    try:
        (task_dir / ".cancelled").touch()
    except OSError:
        # Best-effort sentinel — if the task_dir is unwritable we still
        # send SIGTERM and accept the legacy "rc=143 -> cancelled"
        # interpretation as a degraded fallback.
        pass

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
    _reap_if_dead(task_dir)
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

def _reap_if_dead(task_dir: Path) -> None:
    """If a task still claims 'running' but its recorded (supervisor) pid is no
    longer alive, mark it 'error'. Called before every status read so a task
    whose dispatcher died without writing a terminal status self-heals on the
    next poll instead of only at backend restart.

    Never overwrites a terminal status the orchestrator already wrote — a
    SIGTERM-cancelled task writes 'cancelled' before exit, which we preserve.
    """
    status_path = task_dir / "status.json"
    if not status_path.exists():
        return
    try:
        status = json.loads(status_path.read_text())
    except Exception:
        return
    if status.get("status") != "running":
        return
    pid = status.get("pid")
    if not pid:
        return
    try:
        os.kill(pid, 0)  # 0 = liveness probe, doesn't actually signal
    except OSError:
        status["status"] = "error"
        status["message"] = "Process terminated unexpectedly"
        try:
            status_path.write_text(json.dumps(status, indent=2))
        except OSError:
            pass


def recover_orphaned_tasks():
    """On startup, reap every task stuck 'running' with a dead pid."""
    if not app.config.settings.TASKS_DIR.exists():
        return
    for task_dir in app.config.settings.TASKS_DIR.iterdir():
        _reap_if_dead(task_dir)

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
