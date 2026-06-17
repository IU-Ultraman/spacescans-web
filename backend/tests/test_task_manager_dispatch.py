"""Sprint 3 T9: dispatcher supervisor + multi-experiment dispatch."""
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def task_dir_with_config(tmp_path: Path) -> Path:
    task_dir = tmp_path / "task-xyz"
    task_dir.mkdir()
    (task_dir / "config.json").write_text(json.dumps({
        "variables": ["ndi", "cbp_density"],
        "buffer": {"size": 270, "raster_res_m": 25},
        "experiment": "auto",
    }))
    (task_dir / "output").mkdir()
    return task_dir


class _FakePopen:
    instances: list["_FakePopen"] = []

    def __init__(self, cmd, *, returncode: int = 0, **kwargs):
        self.cmd = cmd
        self.kwargs = kwargs
        self._rc = returncode
        self.pid = 9000 + len(_FakePopen.instances)
        _FakePopen.instances.append(self)

    def wait(self, timeout=None):
        return self._rc


def test_dispatch_sequential_order_matches_registry(task_dir_with_config, monkeypatch):
    from app import dispatcher

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {"bg_ndi_wi": ["ndi"], "zcta5_cbp": ["cbp_density"]})
    fan_in = MagicMock()
    monkeypatch.setattr("app.experiments._merge.fan_in", fan_in)

    result = dispatcher.dispatch(str(task_dir_with_config))

    assert len(_FakePopen.instances) == 2
    assert "app.experiments.bg_ndi_wi" in _FakePopen.instances[0].cmd
    assert "app.experiments.zcta5_cbp" in _FakePopen.instances[1].cmd
    assert result["completed"] == ["bg_ndi_wi", "zcta5_cbp"]
    fan_in.assert_called_once_with(task_dir_with_config, ["bg_ndi_wi", "zcta5_cbp"])


def test_dispatch_initialises_experiments_map(task_dir_with_config, monkeypatch):
    from app import dispatcher

    _FakePopen.instances = []
    captured_writes = []

    monkeypatch.setattr(dispatcher, "_write_status",
                        lambda task_dir, **kwargs: captured_writes.append(kwargs))
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {"bg_ndi_wi": ["ndi"], "zcta5_cbp": ["cbp_density"]})
    monkeypatch.setattr("app.experiments._merge.fan_in", MagicMock())

    dispatcher.dispatch(str(task_dir_with_config))

    assert captured_writes
    first = captured_writes[0]
    assert first["status"] == "running"
    assert set(first["experiments"].keys()) == {"bg_ndi_wi", "zcta5_cbp"}
    assert first["experiments"]["bg_ndi_wi"]["status"] == "pending"


def test_dispatch_partial_failure_marks_remaining(task_dir_with_config, monkeypatch):
    """First runner fails → second is marked skipped; fan_in NOT called (no completed)."""
    from app import dispatcher

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {"bg_ndi_wi": ["ndi"], "zcta5_cbp": ["cbp_density"]})

    def popen_with_first_fail(cmd, **kw):
        idx = len(_FakePopen.instances)
        return _FakePopen(cmd, returncode=(2 if idx == 0 else 0), **kw)

    monkeypatch.setattr(dispatcher.subprocess, "Popen", popen_with_first_fail)
    marked = []
    monkeypatch.setattr(dispatcher, "_mark_experiment",
                        lambda task_dir, key, status, **extra: marked.append((key, status)))
    fan_in = MagicMock()
    monkeypatch.setattr("app.experiments._merge.fan_in", fan_in)

    result = dispatcher.dispatch(str(task_dir_with_config))

    assert len(_FakePopen.instances) == 1
    assert ("zcta5_cbp", "skipped_due_to_prior_failure") in marked
    fan_in.assert_not_called()
    assert result["failed"] == ["bg_ndi_wi", "zcta5_cbp"]


def test_dispatch_partial_failure_after_success_calls_fan_in(task_dir_with_config, monkeypatch):
    """Runner 1 succeeds, runner 2 fails → fan_in called on [bg_ndi_wi]."""
    from app import dispatcher

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {"bg_ndi_wi": ["ndi"], "zcta5_cbp": ["cbp_density"]})

    def popen_with_second_fail(cmd, **kw):
        idx = len(_FakePopen.instances)
        return _FakePopen(cmd, returncode=(0 if idx == 0 else 2), **kw)

    monkeypatch.setattr(dispatcher.subprocess, "Popen", popen_with_second_fail)
    monkeypatch.setattr(dispatcher, "_mark_experiment", lambda *a, **kw: None)
    fan_in = MagicMock()
    monkeypatch.setattr("app.experiments._merge.fan_in", fan_in)

    result = dispatcher.dispatch(str(task_dir_with_config))

    fan_in.assert_called_once_with(task_dir_with_config, ["bg_ndi_wi"])
    assert result["completed"] == ["bg_ndi_wi"]
    assert result["failed"] == ["zcta5_cbp"]


def test_start_task_popens_dispatcher_and_returns_pid(task_dir_with_config, monkeypatch):
    from app import task_manager

    captured = {}

    def fake_popen(cmd, **kw):
        captured["cmd"] = cmd
        captured["kwargs"] = kw
        return _FakePopen(cmd, returncode=0, **kw)

    monkeypatch.setattr(task_manager.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(task_manager, "_task_dir",
                        lambda task_id: task_dir_with_config)

    out = task_manager.start_task(task_dir_with_config.name)

    assert "app.dispatcher" in captured["cmd"]
    assert "run" in captured["cmd"]
    assert captured["kwargs"].get("start_new_session") is True
    assert isinstance(out["pid"], int)


def test_dispatch_derives_top_level_progress_and_steps_from_slots(
    task_dir_with_config, monkeypatch
):
    """Sprint 3 final-review (BLOCKER): dispatch must populate per-slot
    ``steps`` + ``progress`` so the atomic writer's _derive_flat_fields
    produces a real top-level ``progress=1.0`` + non-empty ``steps`` on
    a successful all-experiments-finished run.

    Pre-fix, status.json was always ``progress=0.0 / steps=[] / current_step=null``
    for any dispatcher-driven run because the dispatcher never seeded per-slot
    steps and the re-derivation clobbered the runner's top-level writes.
    """
    from app import dispatcher
    from app.experiments import bg_ndi_wi as _bg
    from app.experiments import zcta5_cbp as _zc

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {
                            "bg_ndi_wi": ["ndi"],
                            "zcta5_cbp": ["cbp_zcta5"],
                        })

    class _Step:
        def __init__(self, name): self.name = name

    monkeypatch.setattr(_bg, "plan",
                        lambda cfg: [_Step("c3_bg"), _Step("c4_ndi")])
    monkeypatch.setattr(_zc, "plan",
                        lambda cfg: [_Step("c3_zcta5"), _Step("c4_zcta5_cbp")])
    monkeypatch.setattr("app.experiments._merge.fan_in", MagicMock())

    dispatcher.dispatch(str(task_dir_with_config))

    status = json.loads((task_dir_with_config / "status.json").read_text())

    # Top-level fields must reflect a real, finished run.
    assert status["status"] == "finished"
    assert status["progress"] == 1.0, (
        f"expected top-level progress=1.0; got {status['progress']}"
    )
    assert status["steps"] == [
        "c3_bg", "c4_ndi", "c3_zcta5", "c4_zcta5_cbp"
    ], f"top-level steps must concatenate per-slot steps in dispatch order; got {status['steps']}"
    assert status["total_steps"] == 4
    # No experiment slot is "running" on finish — current_step must be None.
    assert status["current_step"] is None

    # Per-slot fields must be populated (this is what _derive_flat_fields reads).
    exp = status["experiments"]
    assert exp["bg_ndi_wi"]["progress"] == 1.0
    assert exp["bg_ndi_wi"]["steps"] == ["c3_bg", "c4_ndi"]
    assert exp["bg_ndi_wi"]["status"] == "finished"
    assert exp["zcta5_cbp"]["progress"] == 1.0
    assert exp["zcta5_cbp"]["steps"] == ["c3_zcta5", "c4_zcta5_cbp"]
    assert exp["zcta5_cbp"]["status"] == "finished"


def test_legacy_experiment_field_logged_but_ignored(task_dir_with_config, monkeypatch):
    """experiment='bg_ndi_wi' must not prevent dispatch of cbp_zcta5.

    Asserts the audit record lands in the per-task logs.jsonl (spec R10),
    NOT in stdlib's caplog — the spec contract is the on-disk audit trail.
    """
    from app import dispatcher

    cfg = json.loads((task_dir_with_config / "config.json").read_text())
    cfg["experiment"] = "bg_ndi_wi"
    (task_dir_with_config / "config.json").write_text(json.dumps(cfg))

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {"bg_ndi_wi": ["ndi"], "zcta5_cbp": ["cbp_density"]})
    monkeypatch.setattr("app.experiments._merge.fan_in", MagicMock())

    dispatcher.dispatch(str(task_dir_with_config))

    assert len(_FakePopen.instances) == 2
    log_lines = (task_dir_with_config / "logs.jsonl").read_text().splitlines()
    audit = [
        json.loads(line) for line in log_lines if line.strip()
        and json.loads(line).get("event") == "config_saved"
    ]
    assert len(audit) == 1, f"expected exactly one config_saved audit entry; got {audit}"
    assert audit[0]["experiment_field_received"] == "bg_ndi_wi"
    assert set(audit[0]["dispatch_plan"].keys()) == {"bg_ndi_wi", "zcta5_cbp"}


def test_three_experiment_dispatch_preserves_metadata_order(
    task_dir_with_config, monkeypatch
):
    """Sprint 5: 4 variables across 3 experiments dispatch in metadata-file order.

    Spec L602-605: dispatch order is JSON-file order of first experiment
    appearance — bg_ndi_wi (ndi), zcta5_cbp (cbp_zcta5), tiger_proximity
    (tiger_proximity), in that order regardless of the variable
    selection order in config.json.
    """
    import json as _json
    from app import dispatcher

    # Rewrite config to include all 4 variables in deliberately scrambled order.
    cfg_path = task_dir_with_config / "config.json"
    cfg = _json.loads(cfg_path.read_text())
    cfg["variables"] = ["tiger_proximity", "cbp_zcta5", "ndi", "walkability"]
    cfg_path.write_text(_json.dumps(cfg))

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
    fan_in = MagicMock()
    monkeypatch.setattr("app.experiments._merge.fan_in", fan_in)

    result = dispatcher.dispatch(str(task_dir_with_config))

    assert len(_FakePopen.instances) == 3
    assert "app.experiments.bg_ndi_wi" in _FakePopen.instances[0].cmd
    assert "app.experiments.zcta5_cbp" in _FakePopen.instances[1].cmd
    assert "app.experiments.tiger_proximity" in _FakePopen.instances[2].cmd
    assert result["completed"] == ["bg_ndi_wi", "zcta5_cbp", "tiger_proximity"]
    fan_in.assert_called_once_with(
        task_dir_with_config, ["bg_ndi_wi", "zcta5_cbp", "tiger_proximity"]
    )


def test_four_experiment_dispatch_preserves_metadata_order(
    task_dir_with_config, monkeypatch
):
    """Sprint 7: 5 variables across 4 experiments dispatch in metadata-file order.

    Dispatch order is JSON-file order of first experiment appearance —
    bg_ndi_wi (ndi, walkability), zcta5_cbp (cbp_zcta5),
    tiger_proximity (tiger_proximity), nhd_bluespace (nhd_bluespace), in
    that order regardless of the variable selection order in config.json.
    Pure mock — no subprocess, no status.json transitions beyond the
    dispatcher's own writes.
    """
    import json as _json
    from app import dispatcher

    cfg_path = task_dir_with_config / "config.json"
    cfg = _json.loads(cfg_path.read_text())
    # Scramble the variable order — dispatcher must serialise to metadata-file
    # order regardless.
    cfg["variables"] = [
        "nhd_bluespace", "tiger_proximity", "cbp_zcta5", "walkability", "ndi",
    ]
    cfg_path.write_text(_json.dumps(cfg))

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
    fan_in = MagicMock()
    monkeypatch.setattr("app.experiments._merge.fan_in", fan_in)

    result = dispatcher.dispatch(str(task_dir_with_config))

    assert len(_FakePopen.instances) == 4
    assert "app.experiments.bg_ndi_wi" in _FakePopen.instances[0].cmd
    assert "app.experiments.zcta5_cbp" in _FakePopen.instances[1].cmd
    assert "app.experiments.tiger_proximity" in _FakePopen.instances[2].cmd
    assert "app.experiments.nhd_bluespace" in _FakePopen.instances[3].cmd
    assert result["completed"] == [
        "bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace",
    ]
    fan_in.assert_called_once_with(
        task_dir_with_config,
        ["bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace"],
    )


def test_dispatch_writes_pid_and_running_status_atomically(
    task_dir_with_config, monkeypatch
):
    """Sprint 12 G1: close TOCTOU race in dispatcher.

    Before this fix, dispatcher wrote `status='running'` to a slot
    BEFORE subprocess.Popen, then wrote `pid` in a SEPARATE
    _write_status call after Popen. stop_task's predicate requires
    (pid present AND status=='running') for a slot to be a runner
    target — so a stop_task call landing in the inter-write window
    saw zero runner pids and fell back to SIGTERMing the supervisor,
    killing the dispatcher before proc.wait() could observe rc=143
    (breaking Sprint 4 F1b cancellation observability).

    Invariant: the per-slot _write_status call that flips status to
    'running' MUST carry the pid in the same write — i.e. status.json
    is never observable in a (status='running', pid=missing) state.
    """
    from app import dispatcher

    _FakePopen.instances = []
    captured_writes: list[dict] = []

    def capture_write(task_dir, **kwargs):
        # Snapshot every write keyed by the experiments dict it carries.
        captured_writes.append(kwargs)

    monkeypatch.setattr(dispatcher, "_write_status", capture_write)
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {"bg_ndi_wi": ["ndi"]})
    monkeypatch.setattr("app.experiments._merge.fan_in", MagicMock())

    dispatcher.dispatch(str(task_dir_with_config))

    # Locate the per-slot 'running' write — the one that stamps the
    # slot from 'pending' to 'running'.
    running_writes = [
        w for w in captured_writes
        if "experiments" in w
        and isinstance(w["experiments"].get("bg_ndi_wi"), dict)
        and w["experiments"]["bg_ndi_wi"].get("status") == "running"
    ]
    assert running_writes, (
        "expected at least one per-slot write flipping status -> 'running'"
    )
    # G1 invariant: the running-status write MUST carry the pid in the
    # same snapshot. Pre-fix, pid landed in a separate subsequent write.
    running_slot = running_writes[0]["experiments"]["bg_ndi_wi"]
    assert "pid" in running_slot, (
        "TOCTOU regression: status='running' write must include pid atomically"
    )
    assert isinstance(running_slot["pid"], int)
    # And no write should land status='running' without pid:
    for w in running_writes:
        slot = w["experiments"]["bg_ndi_wi"]
        assert slot.get("pid") is not None, (
            f"status='running' slot without pid: {slot!r}"
        )
