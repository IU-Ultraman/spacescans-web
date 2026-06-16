"""Sprint 3 T3: GET /api/variables endpoint contract.

Covers four cases from spec contract notes (lines 999-1018):
- unauthenticated → 401
- happy path → 200 with schema_version + 3-entry catalog
- registry FileNotFoundError → 503 metadata_unavailable
- registry MetadataSchemaError → 500 metadata_schema_invalid
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import variable_registry


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


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
