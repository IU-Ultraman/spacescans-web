"""Sprint 3 T9: Supervisor subprocess that sequentially dispatches per-experiment runners.

Spawned by task_manager.start_task as: python -m app.dispatcher run <task_id>
"""
from __future__ import annotations

import importlib
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


def _mark_experiment(task_dir: Path, exp_key: str, status: str, **extra) -> None:
    payload = {"status": status, **extra}
    _write_status(task_dir, experiments={exp_key: payload})


def _runner_step_names(exp_key: str, exp_vars: list[str], config: dict) -> list[str]:
    """Import the runner module and call its plan() to get this slot's step names.

    Sprint 3 final-review fix (BLOCKER): _derive_flat_fields aggregates
    top-level ``steps`` / ``progress`` from each ``experiments[exp_key]``
    slot. The dispatcher used to seed only ``status`` / ``variables`` /
    ``started_at``, leaving ``steps=[]`` and ``progress=0.0`` — which then
    clobbered the top-level fields the runner had written. We now read the
    runner's plan() output ahead of Popen and seed the slot's ``steps``.

    Returns an empty list if the runner module / plan() is unavailable; the
    caller treats that as "this experiment contributes 0 steps" and proceeds.
    """
    try:
        module = importlib.import_module(f"app.experiments.{exp_key}")
    except ImportError:
        _log.warning("dispatcher: cannot import app.experiments.%s — slot steps will be empty",
                     exp_key)
        return []
    plan_fn = getattr(module, "plan", None)
    if plan_fn is None:
        _log.warning("dispatcher: app.experiments.%s has no plan() — slot steps will be empty",
                     exp_key)
        return []
    try:
        steps = plan_fn({**config, "variables": list(exp_vars)})
    except Exception as exc:
        _log.warning("dispatcher: %s.plan() raised %r — slot steps will be empty",
                     exp_key, exc)
        return []
    # plan() returns dataclass PipelineStep objects; project to their name.
    names: list[str] = []
    for s in steps:
        name = getattr(s, "name", None)
        if isinstance(name, str):
            names.append(name)
        elif isinstance(s, str):
            names.append(s)
    return names


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

    # Seed each experiment slot with its plan()'s step names + progress=0.0
    # so _derive_flat_fields produces a real top-level steps[] / progress.
    # Sprint 3 final-review fix (BLOCKER): previously we wrote only
    # status/variables/started_at, leaving steps=[] which then clobbered
    # the top-level steps/progress written by the runner.
    seeded_slots: dict[str, dict] = {}
    for exp_key, vars_ in by_exp.items():
        seeded_slots[exp_key] = {
            "status": "pending",
            "variables": list(vars_),
            "started_at": None,
            "progress": 0.0,
            "current_step": None,
            "steps": _runner_step_names(exp_key, list(vars_), config),
        }

    _write_status(
        task_dir,
        status="running",
        message="Dispatching experiments",
        experiments=seeded_slots,
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    completed: list[str] = []
    exp_keys = list(by_exp.keys())
    cancelled = False
    for i, exp_key in enumerate(exp_keys):
        exp_vars = by_exp[exp_key]
        cmd = [
            str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
            "-m", f"app.experiments.{exp_key}",
            "run", str(task_dir),
            "--variables", ",".join(exp_vars),
        ]
        # Sprint 12 G1: close TOCTOU window between status='running' and
        # pid being recorded. Previously, status='running' was stamped
        # BEFORE Popen and pid AFTER, so if stop_task fired in that window
        # the (pid present AND status=='running') predicate matched no
        # runner slot — stop_task fell back to SIGTERMing the supervisor,
        # killing the dispatcher before proc.wait() could observe rc=143
        # (breaking Sprint 4 F1b cancellation observability).
        #
        # Fix: keep the slot at status='pending' (seeded above) until AFTER
        # Popen returns, then write {pid, status='running', started_at}
        # atomically as one _write_status call. stop_task's lookup now
        # either sees the slot pre-Popen as 'pending' (so it correctly
        # falls back to the supervisor only when no runner exists yet) or
        # sees the slot post-Popen with both pid and status='running' set
        # in the same status.json snapshot.
        proc = subprocess.Popen(
            cmd,
            cwd=str(app.config.settings.BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _write_status(task_dir, experiments={exp_key: {
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "pid": proc.pid,
        }})
        rc = proc.wait()
        if rc != 0:
            if rc == 143:
                # SIGTERM cancellation (Sprint 4 F1b). Preserve cancelled
                # lineage end-to-end: this slot + all remaining slots get
                # status='cancelled', and the post-loop top-level write
                # branches on `cancelled` to write status='cancelled' /
                # message='Task cancelled by user' instead of 'error'.
                _mark_experiment(task_dir, exp_key, "cancelled", current_step=None)
                for skipped in exp_keys[i + 1:]:
                    _mark_experiment(task_dir, skipped, "cancelled",
                                     current_step=None)
                cancelled = True
                break
            # Generic non-zero rc — existing error + skipped cascade.
            _mark_experiment(task_dir, exp_key, "error", current_step=None)
            for skipped in exp_keys[i + 1:]:
                _mark_experiment(task_dir, skipped, "skipped_due_to_prior_failure",
                                 current_step=None)
            break
        # Runner succeeded — pin slot progress=1.0 (the runner already writes
        # this, but we restate it here so a fast-finishing runner that didn't
        # quite flush the final write still aggregates to top-level
        # progress=1.0 once all slots succeed).
        _mark_experiment(task_dir, exp_key, "finished",
                         progress=1.0, current_step=None)
        completed.append(exp_key)

    failed = [k for k in exp_keys if k not in completed]

    if completed and not cancelled:
        from app.experiments import _merge
        _merge.fan_in(task_dir, completed)

    if cancelled:
        _write_status(task_dir, status="cancelled",
                      message="Task cancelled by user")
        return {"task_id": task_dir.name, "completed": completed,
                "failed": failed, "cancelled": True}
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
