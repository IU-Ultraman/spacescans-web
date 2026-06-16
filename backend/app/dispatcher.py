"""Sprint 3 T9: Supervisor subprocess that sequentially dispatches per-experiment runners.

Spawned by task_manager.start_task as: python -m app.dispatcher run <task_id>
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import app.config
from app import variable_registry

_log = logging.getLogger(__name__)


def _task_dir(task_id: str) -> Path:
    return app.config.settings.TASKS_DIR / f"task-{task_id}"


def _write_status(task_dir: Path, **kwargs) -> None:
    from app.task_manager import _write_status as tm_write
    tm_write(task_dir, **kwargs)


def _mark_experiment(task_dir: Path, exp_key: str, status: str) -> None:
    _write_status(task_dir, experiments={exp_key: {"status": status}})


def dispatch(task_id_or_dir: str) -> dict:
    task_dir = Path(task_id_or_dir)
    if not task_dir.is_absolute():
        task_dir = _task_dir(task_id_or_dir)

    config = json.loads((task_dir / "config.json").read_text())
    selected = config.get("variables", [])
    legacy_exp_field = config.get("experiment")
    by_exp = variable_registry.variables_by_experiment(selected)

    # Audit-log the legacy `experiment` field receipt into the per-task
    # logs.jsonl (NOT stdlib logging) so spec R10 is structurally provable
    # from the task directory's audit stream.
    _audit_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": "info",
        "source": "dispatcher",
        "event": "config_saved",
        "experiment_field_received": legacy_exp_field,
        "dispatch_plan": {k: list(v) for k, v in by_exp.items()},
    }
    with open(task_dir / "logs.jsonl", "a") as _f:
        _f.write(json.dumps(_audit_entry) + "\n")

    if not by_exp:
        _write_status(task_dir, status="error", progress=0.0,
                      message="no variables selected")
        return {"task_id": task_dir.name, "failed": []}

    _write_status(
        task_dir,
        status="running",
        progress=0.0,
        message="Dispatching experiments",
        experiments={
            exp_key: {"status": "pending", "variables": list(vars_),
                      "started_at": None}
            for exp_key, vars_ in by_exp.items()
        },
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    completed: list[str] = []
    exp_keys = list(by_exp.keys())
    for i, exp_key in enumerate(exp_keys):
        exp_vars = by_exp[exp_key]
        cmd = [
            str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
            "-m", f"app.experiments.{exp_key}",
            "run", str(task_dir),
            "--variables", ",".join(exp_vars),
        ]
        _write_status(task_dir, experiments={exp_key: {
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }})
        proc = subprocess.Popen(
            cmd,
            cwd=str(app.config.settings.BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Record the runner pid into the experiments map so stop_task (and
        # any external supervisor) can walk it to send SIGTERM directly.
        _write_status(task_dir, experiments={exp_key: {"pid": proc.pid}})
        rc = proc.wait()
        if rc != 0:
            _mark_experiment(task_dir, exp_key, "error")
            for skipped in exp_keys[i + 1:]:
                _mark_experiment(task_dir, skipped, "skipped_due_to_prior_failure")
            break
        _mark_experiment(task_dir, exp_key, "finished")
        completed.append(exp_key)

    failed = [k for k in exp_keys if k not in completed]

    if completed:
        from app.experiments import _merge
        _merge.fan_in(task_dir, completed)

    if not completed:
        _write_status(task_dir, status="error", progress=0.0,
                      message=f"All experiments failed (first failure: {failed[0]})")
        return {"task_id": task_dir.name, "failed": failed}
    if failed:
        _write_status(
            task_dir,
            status="partial",
            progress=round(len(completed) / len(exp_keys), 2),
            message=f"{len(completed)}/{len(exp_keys)} experiments completed",
        )
        return {"task_id": task_dir.name, "completed": completed, "failed": failed}

    _write_status(task_dir, status="finished", progress=1.0,
                  message=f"Completed {len(completed)} experiments")
    return {"task_id": task_dir.name, "completed": completed}


def _main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "run":
        print("usage: python -m app.dispatcher run <task_id>", file=sys.stderr)
        return 2
    try:
        dispatch(argv[2])
    except Exception:
        _log.exception("dispatcher crashed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
