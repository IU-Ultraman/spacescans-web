"""Sprint 3 T1 (tier-2 phase C): the variable catalog is the package's.

The registry reads the catalog from the spacescans package
(``spacescans.catalog``: ``variables.json`` + ``variables.schema.json``, byte
copies of the web's files at 3991c3b). ``app/data/variable_metadata.json`` and
its schema stay in the repo this version as copies, because readers outside the
app open the file by path (the paper's ``catalog_summary.py``); the copies must
equal the package's byte for byte, or someone edited the wrong one. These tests
check the on-disk artefacts loader-free: the copies match, and the packaged
file still has the shape the web serves.
"""
from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path

import jsonschema
import pytest
from spacescans import catalog

BACKEND = Path(__file__).resolve().parent.parent
DATA = BACKEND / "app" / "data"


@pytest.fixture(scope="module")
def metadata() -> dict:
    return catalog.payload()


@pytest.fixture(scope="module")
def schema() -> dict:
    return catalog.schema()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("web_name, package_name", [
    ("variable_metadata.json", "variables.json"),
    ("variable_metadata.schema.json", "variables.schema.json"),
    ("feature_dictionary.json", "features.json"),
])
def test_web_copies_equal_the_package_catalog(web_name, package_name):
    """The web's copies are the package's files, byte for byte. A difference
    means one side was edited alone: change the package's file (the one the
    app reads) and copy it here, or copy a regenerated feature dictionary
    (``scripts/extend_ontology.py`` writes the web's) into the package."""
    web = (DATA / web_name).read_bytes()
    pkg = resources.files("spacescans.catalog").joinpath(package_name).read_bytes()
    assert _sha(web) == _sha(pkg), (
        f"app/data/{web_name} differs from spacescans.catalog/{package_name}")


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
    assert len(metadata["variables"]) == 11


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


def test_every_catalog_experiment_has_a_runner_module():
    """The dispatcher spawns ``python -m app.experiments.<experiment>``; a
    catalog experiment without a module here could never run."""
    from app import variable_registry as vr

    assert set(catalog.experiments()) <= vr._discover_experiments()


def test_private_experiment_modules_are_not_experiments():
    """Helper modules under app/experiments (``_merge``, and any other
    ``_``-prefixed one) are not runners the catalog may name."""
    from app import variable_registry as vr

    found = vr._discover_experiments()
    assert not {name for name in found if name.startswith("_")}, found
    assert "custom" in found and "bg_ndi_wi" in found
