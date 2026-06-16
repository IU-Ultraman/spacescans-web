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
                        lambda task_dir, key, status: marked.append((key, status)))
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
