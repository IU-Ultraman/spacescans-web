"""Sprint 4 F1b: dispatcher rc==143 cancellation lineage tests."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def task_dir_with_config(tmp_path: Path) -> Path:
    task_dir = tmp_path / "task-cxl"
    task_dir.mkdir()
    (task_dir / "config.json").write_text(json.dumps({
        "variables": ["ndi", "cbp_zcta5"],
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


def test_dispatcher_cancellation_preserves_cancelled_status(
    task_dir_with_config, monkeypatch
):
    """First runner exits rc=143 (SIGTERM). Expect:
      - slot 1 status='cancelled' (NOT 'error')
      - slot 2 status='cancelled' (NOT 'skipped_due_to_prior_failure')
      - top-level status='cancelled', message='Task cancelled by user'
    """
    from app import dispatcher

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {
                            "bg_ndi_wi": ["ndi"],
                            "zcta5_cbp": ["cbp_zcta5"],
                        })

    def popen_first_sigterm(cmd, **kw):
        idx = len(_FakePopen.instances)
        return _FakePopen(cmd, returncode=(143 if idx == 0 else 0), **kw)

    monkeypatch.setattr(dispatcher.subprocess, "Popen", popen_first_sigterm)
    monkeypatch.setattr("app.experiments._merge.fan_in", MagicMock())

    dispatcher.dispatch(str(task_dir_with_config))

    status = json.loads((task_dir_with_config / "status.json").read_text())

    # rc==143 must NOT spawn the second runner (the cascade is status-only).
    assert len(_FakePopen.instances) == 1, (
        f"rc==143 must break the dispatch loop; got {len(_FakePopen.instances)} Popens"
    )

    # Top-level: cancelled, with the specific message.
    assert status["status"] == "cancelled", (
        f"top-level status must be 'cancelled' on rc==143; got {status['status']}"
    )
    assert status.get("message") == "Task cancelled by user", (
        f"top-level message must be 'Task cancelled by user'; got {status.get('message')!r}"
    )

    # Slot lineage: cancelled slot preserved, remaining slot cascaded as cancelled.
    exp = status["experiments"]
    assert exp["bg_ndi_wi"]["status"] == "cancelled", (
        f"slot 1 status must be 'cancelled' on rc==143; got {exp['bg_ndi_wi']['status']}"
    )
    assert exp["zcta5_cbp"]["status"] == "cancelled", (
        f"remaining slot must cascade as 'cancelled', NOT 'skipped_due_to_prior_failure'; "
        f"got {exp['zcta5_cbp']['status']}"
    )
