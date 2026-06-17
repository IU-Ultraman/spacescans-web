"""Sprint 3 T3: GET /api/variables endpoint contract.

Covers four cases from spec contract notes (lines 999-1018):
- unauthenticated → 401
- happy path → 200 with schema_version + 3-entry catalog
- registry FileNotFoundError → 503 metadata_unavailable
- registry MetadataSchemaError → 500 metadata_schema_invalid

Sprint 4 F5: auth dependency swapped require_user → get_current_user; tests now
mint a real JWT via create_access_token, and a negative test asserts garbage
tokens are rejected with 401.
"""
import os
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

# Reload .env before importing app modules so SECRET_KEY/ALGORITHM are available
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=True)

import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.main import app
from app import variable_registry


@pytest.fixture
def client():
    return TestClient(app)


def _auth_headers() -> dict[str, str]:
    """Mint a real JWT for tests so get_current_user accepts it."""
    token = create_access_token({"sub": "1", "email": "test@example.com"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers():
    return _auth_headers()


def _fake_catalog():
    return {
        "schema_version": 1,
        "variables": {
            "ndi": {
                "label": "Neighborhood Deprivation Index",
                "description": "Census-tract NDI (Messer 2006).",
                "boundary": "BG",
                "coverage_years": (2010, 2022),
                "coverage_region": "CONUS",
                "experiment": "bg_ndi_wi",
                "variable_type": "continuous",
                "display_unit": "z-score",
                "value_cols": ["ndi"],
            },
            "NatWalkInd": {
                "label": "National Walkability Index",
                "description": "EPA SLD walkability score.",
                "boundary": "BG",
                "coverage_years": (2021, 2021),
                "coverage_region": "CONUS",
                "experiment": "bg_ndi_wi",
                "variable_type": "continuous",
                "display_unit": "index",
                "value_cols": ["NatWalkInd"],
            },
            "cbp_zcta5": {
                "label": "County Business Patterns (ZCTA5)",
                "description": "10 sector ratios from CBP at ZCTA5.",
                "boundary": "ZCTA5",
                "coverage_years": (2017, 2022),
                "coverage_region": "CONUS",
                "experiment": "zcta5_cbp",
                "variable_type": "continuous",
                "display_unit": "ratio",
                "value_cols": [f"r_{i}" for i in range(10)],
            },
        },
    }


def test_unauthenticated_returns_401(client):
    # Sprint 12 G2: standardized on 401 across the API. HTTPBearer is configured
    # with auto_error=False; get_current_user raises 401 when no credentials
    # are present — matching /api/tasks/* and the rest of the auth contract.
    r = client.get("/api/variables")
    assert r.status_code == 401


def test_authenticated_returns_catalog(client, auth_headers):
    with patch.object(variable_registry, "load_variables", return_value=_fake_catalog()):
        r = client.get("/api/variables", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == 1
    assert set(body["variables"].keys()) == {"ndi", "NatWalkInd", "cbp_zcta5"}
    assert body["variables"]["cbp_zcta5"]["boundary"] == "ZCTA5"
    assert body["variables"]["cbp_zcta5"]["value_cols"] == [f"r_{i}" for i in range(10)]


def test_metadata_file_missing_returns_503(client, auth_headers):
    with patch.object(
        variable_registry, "load_variables",
        side_effect=FileNotFoundError("variable_metadata.json not found"),
    ):
        r = client.get("/api/variables", headers=auth_headers)
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "metadata_unavailable"
    assert "variable_metadata.json" in r.json()["detail"]["message"]


def test_metadata_schema_invalid_returns_500(client, auth_headers):
    with patch.object(
        variable_registry, "load_variables",
        side_effect=variable_registry.MetadataSchemaError("unknown experiment 'bogus'"),
    ):
        r = client.get("/api/variables", headers=auth_headers)
    assert r.status_code == 500
    assert r.json()["detail"]["error"] == "metadata_schema_invalid"
    assert "bogus" in r.json()["detail"]["message"]


def test_list_variables_rejects_invalid_jwt(client):
    """Garbage tokens must be rejected with 401 (was 200 under presence-only stub)."""
    headers = {"Authorization": "Bearer not-a-real-jwt"}
    response = client.get("/api/variables", headers=headers)
    assert response.status_code == 401


def test_unauthenticated_status_is_consistent_across_endpoints(client):
    """Sprint 12 G2 cross-product invariant: every authenticated endpoint must
    return 401 (NOT 403) for missing credentials, so the FE can branch on a
    single status code. Previously /api/variables returned 403 (HTTPBearer
    default) while /api/tasks/* returned 401."""
    assert client.get("/api/variables").status_code == 401
    assert client.get("/api/tasks").status_code == 401
