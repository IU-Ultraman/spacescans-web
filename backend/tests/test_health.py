# backend/tests/test_health.py
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import variable_registry
from app.main import create_app


def test_health():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_startup_invokes_pipeline_version_probe():
    """Sprint 12 G5: the pipeline-version probe must be invoked at app boot
    (FastAPI startup event), not lazily on the first load_variables() call.

    Rationale: a misconfigured/stale spacescans-pipeline install should fail
    fast at `uvicorn` startup so it can't pass an external healthcheck and
    silently serve broken metadata. The lazy call inside load_variables()
    remains as defense-in-depth (CLI / non-FastAPI imports).
    """
    # Reset the once-per-process guard so we can observe the probe firing.
    variable_registry._PROBE_DONE = False
    with patch.object(
        variable_registry,
        "_assert_pipeline_version_compatible",
        wraps=variable_registry._assert_pipeline_version_compatible,
    ) as probe:
        app = create_app()
        with TestClient(app):  # context-manager triggers startup
            pass
        assert probe.called, "pipeline-version probe must fire at startup"
