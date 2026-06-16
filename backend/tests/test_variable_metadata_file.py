"""Sprint 3 T1: variable_metadata.json + schema co-locate and validate.

This test is intentionally loader-free — it only checks the on-disk artefacts
so a schema bug shows up before the registry loader (T2) is wired in.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

BACKEND = Path(__file__).resolve().parent.parent
DATA_PATH = BACKEND / "app" / "data" / "variable_metadata.json"
SCHEMA_PATH = BACKEND / "app" / "data" / "variable_metadata.schema.json"


@pytest.fixture(scope="module")
def metadata() -> dict:
    return json.loads(DATA_PATH.read_text())


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def test_metadata_file_exists_at_new_path():
    assert DATA_PATH.is_file(), f"expected {DATA_PATH} to exist after git mv"


def test_schema_file_exists():
    assert SCHEMA_PATH.is_file(), f"expected {SCHEMA_PATH} to exist"


def test_old_metadata_path_is_gone():
    old = BACKEND / "data" / "variable_metadata.json"
    assert not old.exists(), (
        f"{old} should have been removed by git mv; stale copy would "
        "shadow the package-tree file"
    )


def test_schema_version_is_one(metadata):
    assert metadata["schema_version"] == 1


def test_variables_envelope_present(metadata):
    assert "variables" in metadata
    assert isinstance(metadata["variables"], dict)
    assert set(metadata["variables"].keys()) >= {"ndi", "walkability", "cbp_zcta5"}


def test_cbp_zcta5_entry_shape(metadata):
    entry = metadata["variables"]["cbp_zcta5"]
    assert entry["boundary"] == "ZCTA5"
    assert entry["experiment"] == "zcta5_cbp"
    assert entry["coverage_years"] == [2013, 2019]
    assert entry["coverage_region"] == "CONUS"
    assert entry["variable_type"] == "continuous"
    assert entry["value_cols"] == [
        "r_religious", "r_civic", "r_business", "r_political",
        "r_professional", "r_labor", "r_bowling", "r_recreational",
        "r_golf", "r_sports",
    ]


def test_metadata_validates_against_schema(metadata, schema):
    # Draft 2020-12 — jsonschema picks the validator from $schema
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator_cls(schema).validate(metadata)


def test_schema_rejects_unknown_top_level_key(schema):
    validator_cls = jsonschema.validators.validator_for(schema)
    bad = {"schema_version": 1, "variables": {"ndi": {}}, "unexpected": True}
    with pytest.raises(jsonschema.ValidationError):
        validator_cls(schema).validate(bad)


def test_schema_rejects_wrong_schema_version(schema):
    validator_cls = jsonschema.validators.validator_for(schema)
    bad = {"schema_version": 2, "variables": {}}
    with pytest.raises(jsonschema.ValidationError):
        validator_cls(schema).validate(bad)


def test_schema_rejects_bad_variable_key(schema):
    validator_cls = jsonschema.validators.validator_for(schema)
    bad = {
        "schema_version": 1,
        "variables": {
            "BadKey": {
                "label": "x", "description": "x", "boundary": "BG",
                "coverage_years": [2000, 2001], "coverage_region": "CONUS",
                "experiment": "bg_ndi_wi", "variable_type": "continuous",
                "display_unit": "u", "value_cols": ["c"],
            }
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        validator_cls(schema).validate(bad)
