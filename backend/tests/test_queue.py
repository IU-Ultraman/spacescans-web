"""#1 serial queue.

A second `start_task` while the run-lock is held enqueues the task (status
"queued") instead of raising/409. A promoter starts the earliest-queued task
once the lock frees. Queue positions are ordered by queued_at across all tasks.
"""
import fcntl
import importlib
import json
import os
import tempfile
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


def _mk(tm, task_id, *, queued_at=None, status=None, with_config=True):
    d = tm._task_dir(task_id)
    (d / "output").mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(
        {"id": task_id, "user_id": 1, "task_name": task_id,
         "created_at": "2026-01-01T00:00:00+00:00"}))
    if with_config:
        (d / "config.json").write_text(json.dumps(
            {"experiment": "auto", "variables": ["noise"]}))
    if status:
        kw = {"status": status}
        if queued_at:
            kw["queued_at"] = queued_at
        tm._write_status(d, **kw)
    return d


class _FakeProc:
    def __init__(self, pid=4242):
        self.pid = pid


def _patch_popen(monkeypatch, tm, calls):
    monkeypatch.setattr(
        tm.subprocess, "Popen",
        lambda *a, **k: (calls.append(a), _FakeProc())[1],
    )


def _hold_run_lock():
    lock_path = app.config.settings.DATA_DIR / ".run_lock"
    lock_path.touch(exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def test_start_when_free_spawns(monkeypatch):
    tm = _setup()
    calls = []
    _patch_popen(monkeypatch, tm, calls)
    _mk(tm, "t1")
    out = tm.start_task("t1")
    assert out["status"] == "running"
    assert len(calls) == 1
    assert tm._read_status(tm._task_dir("t1"))["status"] == "running"


def test_start_when_busy_enqueues(monkeypatch):
    tm = _setup()
    calls = []
    _patch_popen(monkeypatch, tm, calls)
    fd = _hold_run_lock()
    try:
        _mk(tm, "t1")
        out = tm.start_task("t1")
        assert out["status"] == "queued"
        st = tm._read_status(tm._task_dir("t1"))
        assert st["status"] == "queued"
        assert st.get("queued_at")
        assert calls == []
    finally:
        os.close(fd)


def test_promote_spawns_earliest_when_free(monkeypatch):
    tm = _setup()
    calls = []
    _patch_popen(monkeypatch, tm, calls)
    _mk(tm, "early", queued_at="2026-01-01T00:00:00+00:00", status="queued")
    _mk(tm, "late", queued_at="2026-01-01T01:00:00+00:00", status="queued")
    tm._promote_queue()
    assert len(calls) == 1
    assert tm._read_status(tm._task_dir("early"))["status"] == "running"
    assert tm._read_status(tm._task_dir("late"))["status"] == "queued"


def test_promote_noop_when_busy(monkeypatch):
    tm = _setup()
    calls = []
    _patch_popen(monkeypatch, tm, calls)
    fd = _hold_run_lock()
    try:
        _mk(tm, "q1", queued_at="2026-01-01T00:00:00+00:00", status="queued")
        tm._promote_queue()
        assert calls == []
        assert tm._read_status(tm._task_dir("q1"))["status"] == "queued"
    finally:
        os.close(fd)


def test_queue_positions_are_ordered():
    tm = _setup()
    _mk(tm, "a", queued_at="2026-01-01T03:00:00+00:00", status="queued")
    _mk(tm, "b", queued_at="2026-01-01T01:00:00+00:00", status="queued")
    _mk(tm, "c", queued_at="2026-01-01T02:00:00+00:00", status="queued")
    assert tm._queue_positions() == {"b": 1, "c": 2, "a": 3}
