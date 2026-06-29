"""#3 stale not_started tasks.

A not_started task left untouched past the threshold is flagged stale so the
dashboard can offer one-click cleanup. delete_stale_tasks removes them on
demand — nothing is ever auto-deleted, and only the requesting user's tasks
are touched.
"""
import importlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import app.config


def _setup():
    tmp = tempfile.mkdtemp()
    os.environ["DATA_DIR"] = tmp
    os.environ["DB_PATH"] = str(Path(tmp) / "test.db")
    os.environ["TASKS_DIR"] = str(Path(tmp) / "tasks")
    importlib.reload(app.config)
    import app.task_manager as tm
    importlib.reload(tm)
    app.config.settings.TASKS_DIR.mkdir(parents=True, exist_ok=True)
    return tm


def _mk(tm, task_id, *, user_id=1, age_hours=0.0, status=None):
    d = tm._task_dir(task_id)
    (d / "output").mkdir(parents=True, exist_ok=True)
    created = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    (d / "meta.json").write_text(json.dumps({
        "id": task_id, "user_id": user_id, "task_name": task_id,
        "created_at": created.isoformat(),
    }))
    if status:
        tm._write_status(d, status=status)
    return d


def test_old_not_started_is_flagged_stale():
    tm = _setup()
    _mk(tm, "old", age_hours=25)    # not_started + old -> stale
    _mk(tm, "fresh", age_hours=1)   # not_started + recent -> not stale
    by_id = {t["id"]: t for t in tm.list_tasks(1)}
    assert by_id["old"]["stale"] is True
    assert by_id["fresh"]["stale"] is False


def test_running_old_task_not_stale():
    tm = _setup()
    _mk(tm, "run_old", age_hours=99, status="running")
    by_id = {t["id"]: t for t in tm.list_tasks(1)}
    assert by_id["run_old"]["stale"] is False


def test_delete_stale_removes_only_old_not_started():
    tm = _setup()
    _mk(tm, "s1", age_hours=30)
    _mk(tm, "s2", age_hours=48)
    _mk(tm, "fresh", age_hours=1)
    _mk(tm, "done_old", age_hours=99, status="finished")
    assert tm.delete_stale_tasks(1) == 2
    remaining = {t["id"] for t in tm.list_tasks(1)}
    assert remaining == {"fresh", "done_old"}


def test_delete_stale_scoped_to_user():
    tm = _setup()
    _mk(tm, "mine", user_id=1, age_hours=30)
    _mk(tm, "theirs", user_id=2, age_hours=30)
    assert tm.delete_stale_tasks(1) == 1
    assert tm._task_dir("theirs").exists()
    assert not tm._task_dir("mine").exists()
