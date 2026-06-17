"""Unit tests for backend/app/task_manager.py.

Sprint 4 F1a (T4): exercise stop_task scope reduction — when at least one
runner pid is recorded under status.experiments, SIGTERM ONLY those runner
pids; fall back to the supervisor pid only when no runner pid is present.
"""


def test_stop_task_signals_only_runner_pids_when_present(tmp_path, monkeypatch):
    """F1a: when runner pids are recorded under status.experiments, stop_task
    must SIGTERM ONLY those runner pids — NOT the supervisor pid — so the
    dispatcher survives long enough to observe rc==143 from proc.wait()."""
    import json
    import signal as _signal
    from app import task_manager

    monkeypatch.setattr(task_manager.app.config.settings, "TASKS_DIR", tmp_path)
    task_id = "f1a-runner-only"
    task_dir = tmp_path / f"task-{task_id}"
    task_dir.mkdir(parents=True)
    supervisor_pid = 424242
    runner_pid = 525252
    status = {
        "task_id": task_id,
        "status": "running",
        "pid": supervisor_pid,
        "experiments": {
            "bg_ndi_wi": {
                "status": "running",
                "pid": runner_pid,
            },
        },
    }
    (task_dir / "status.json").write_text(json.dumps(status))

    signalled: list[tuple[int, int]] = []

    def _fake_kill(pid, sig):
        signalled.append((pid, sig))

    monkeypatch.setattr(task_manager.os, "kill", _fake_kill)

    result = task_manager.stop_task(task_id)

    sent_pids = [pid for (pid, _sig) in signalled]
    assert runner_pid in sent_pids, "runner pid must be signalled"
    assert supervisor_pid not in sent_pids, (
        "supervisor pid must NOT be signalled when a runner pid is recorded "
        "(F1a: lets dispatcher survive to observe rc==143)"
    )
    assert all(sig == _signal.SIGTERM for (_pid, sig) in signalled)
    assert result["status"] == "stopping"
    assert result["signalled_pids"] == [runner_pid]


def test_stop_task_falls_back_to_supervisor_when_no_runner_pids(tmp_path, monkeypatch):
    """F1a: when NO runner pid is recorded (early-cancel before dispatcher
    launched any slot), stop_task falls back to SIGTERMing the supervisor pid
    so the dispatcher process is still reaped."""
    import json
    import signal as _signal
    from app import task_manager

    monkeypatch.setattr(task_manager.app.config.settings, "TASKS_DIR", tmp_path)
    task_id = "f1a-supervisor-fallback"
    task_dir = tmp_path / f"task-{task_id}"
    task_dir.mkdir(parents=True)
    supervisor_pid = 313131
    status = {
        "task_id": task_id,
        "status": "running",
        "pid": supervisor_pid,
        "experiments": {},
    }
    (task_dir / "status.json").write_text(json.dumps(status))

    signalled: list[tuple[int, int]] = []
    monkeypatch.setattr(
        task_manager.os, "kill",
        lambda pid, sig: signalled.append((pid, sig)),
    )

    result = task_manager.stop_task(task_id)

    sent_pids = [pid for (pid, _sig) in signalled]
    assert supervisor_pid in sent_pids, (
        "supervisor pid MUST be signalled when no runner pid is recorded "
        "(defensive fallback for early-cancel)"
    )
    assert all(sig == _signal.SIGTERM for (_pid, sig) in signalled)
    assert result["status"] == "stopping"
    assert result["signalled_pids"] == [supervisor_pid]


def test_stop_task_writes_cancelled_sentinel_before_signal(tmp_path, monkeypatch):
    """Sprint 12 G6: stop_task MUST write the .cancelled sentinel BEFORE
    sending SIGTERM. Order matters — the dispatcher's rc==143 branch
    reads the sentinel to discriminate user-intent cancellation from
    external SIGTERM (OOM kill / sysadmin kill / container eviction).

    Asserts: (1) the sentinel exists in task_dir after stop_task returns,
    (2) os.kill observes the sentinel file already on disk at signal time.
    """
    import json
    import signal as _signal
    from app import task_manager

    monkeypatch.setattr(task_manager.app.config.settings, "TASKS_DIR", tmp_path)
    task_id = "g6-sentinel"
    task_dir = tmp_path / f"task-{task_id}"
    task_dir.mkdir(parents=True)
    runner_pid = 727272
    (task_dir / "status.json").write_text(json.dumps({
        "task_id": task_id,
        "status": "running",
        "pid": 111111,
        "experiments": {
            "bg_ndi_wi": {"status": "running", "pid": runner_pid},
        },
    }))

    sentinel_visible_at_kill: list[bool] = []

    def _kill_observes_sentinel(pid, sig):
        sentinel_visible_at_kill.append((task_dir / ".cancelled").exists())

    monkeypatch.setattr(task_manager.os, "kill", _kill_observes_sentinel)

    task_manager.stop_task(task_id)

    # Sentinel persists after stop_task returns.
    assert (task_dir / ".cancelled").exists(), (
        "stop_task must leave .cancelled sentinel in task_dir"
    )
    # And was present BEFORE os.kill was called — i.e. write-before-signal
    # ordering, the property the dispatcher relies on.
    assert sentinel_visible_at_kill == [True], (
        ".cancelled sentinel must be written BEFORE os.kill is invoked"
    )
