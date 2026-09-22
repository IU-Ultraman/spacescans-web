"""Custom exposome library: validation rules and CRUD.

The validation tests are the point of the file. Upload is the only place where
a bad geography key can be caught cheaply; every rule here stands for a defect
that would otherwise surface as an empty join twenty minutes into a run, or
not at all.
"""
from __future__ import annotations

import json

import pytest

from app import custom_exposomes as lib

TRACT_A = "12073001100"
TRACT_B = "12073001200"


@pytest.fixture(autouse=True)
def _library_in_tmp(tmp_path, monkeypatch):
    import app.config
    monkeypatch.setattr(app.config.settings, "DATA_DIR", tmp_path)
    return tmp_path


def _csv(rows: list[str]) -> bytes:
    return "\n".join(rows).encode()


def _static_csv() -> bytes:
    return _csv([
        "tract,greenness,heat",
        f"{TRACT_A},0.41,88.2",
        f"{TRACT_B},0.55,86.0",
    ])


def _yearly_csv() -> bytes:
    return _csv([
        "tract,year,greenness",
        f"{TRACT_A},2015,0.41",
        f"{TRACT_A},2016,0.44",
        f"{TRACT_B},2015,0.55",
    ])


def _create(uid=1, content=None, **kw):
    params = dict(
        content=content if content is not None else _static_csv(),
        name="My greenness",
        description="",
        boundary="Tract",
        key_col="tract",
        value_cols=["greenness", "heat"],
        year_col=None,
    )
    params.update(kw)
    return lib.create(uid, **params)


# --------------------------------------------------------------------------
# keys
# --------------------------------------------------------------------------

def test_variable_key_round_trips():
    key = lib.variable_key("ab12cd34")
    assert key == "custom_ab12cd34"
    assert lib.dataset_id_from_key(key) == "ab12cd34"
    assert lib.is_custom_key(key)


@pytest.mark.parametrize("key", ["ndi", "custom_", "custom_NOTHEX", "custom_ab12"])
def test_non_custom_keys_are_rejected(key):
    assert lib.dataset_id_from_key(key) is None
    assert not lib.is_custom_key(key)


def test_variable_key_matches_the_catalog_key_pattern():
    """The catalog schema pins keys to ^[a-z][a-z0-9_]*$."""
    import re
    assert re.fullmatch(r"^[a-z][a-z0-9_]*$", lib.variable_key("0a1b2c3d"))


def test_dataset_dir_rejects_a_traversal_id():
    with pytest.raises(lib.CustomExposomeError):
        lib.dataset_dir(1, "../../etc")


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def test_static_csv_validates():
    facts = lib.validate(_static_csv(), boundary="Tract", key_col="tract",
                         value_cols=["greenness", "heat"], year_col=None)
    assert facts == {"row_count": 2, "coverage_years": [0, 0], "distinct_keys": 2}


def test_yearly_csv_reports_its_year_range():
    facts = lib.validate(_yearly_csv(), boundary="Tract", key_col="tract",
                         value_cols=["greenness"], year_col="year")
    assert facts["coverage_years"] == [2015, 2016]
    assert facts["row_count"] == 3


def test_numeric_fips_is_rejected_with_a_leading_zero_hint():
    """The FAQSD defect: a spreadsheet drops the leading zero and the join
    silently matches nothing. 11-digit tract codes starting with 0 become 10."""
    content = _csv(["tract,v", "1073001100,0.4", "6073001100,0.5"])
    with pytest.raises(lib.CustomExposomeError) as exc:
        lib.validate(content, boundary="Tract", key_col="tract",
                     value_cols=["v"], year_col=None)
    assert "11-digit" in str(exc.value)
    assert "leading zero" in str(exc.value)


def test_wrong_boundary_width_is_rejected():
    """Tract codes offered as a Block Group dataset are 12-digit there."""
    with pytest.raises(lib.CustomExposomeError, match="12-digit"):
        lib.validate(_static_csv(), boundary="BG", key_col="tract",
                     value_cols=["greenness"], year_col=None)


def test_duplicate_keys_are_rejected():
    """A duplicate geography multiplies rows in the C4 join."""
    content = _csv(["tract,v", f"{TRACT_A},0.4", f"{TRACT_A},0.5"])
    with pytest.raises(lib.CustomExposomeError, match="duplicate"):
        lib.validate(content, boundary="Tract", key_col="tract",
                     value_cols=["v"], year_col=None)


def test_duplicates_are_per_year_when_a_year_column_is_declared():
    """The same tract in two years is fine; twice in one year is not."""
    ok = _csv(["tract,year,v", f"{TRACT_A},2015,0.4", f"{TRACT_A},2016,0.5"])
    lib.validate(ok, boundary="Tract", key_col="tract",
                 value_cols=["v"], year_col="year")
    bad = _csv(["tract,year,v", f"{TRACT_A},2015,0.4", f"{TRACT_A},2015,0.5"])
    with pytest.raises(lib.CustomExposomeError, match="duplicate"):
        lib.validate(bad, boundary="Tract", key_col="tract",
                     value_cols=["v"], year_col="year")


def test_blank_geography_is_rejected():
    content = _csv(["tract,v", f"{TRACT_A},0.4", ",0.5"])
    with pytest.raises(lib.CustomExposomeError, match="no value in"):
        lib.validate(content, boundary="Tract", key_col="tract",
                     value_cols=["v"], year_col=None)


def test_mostly_non_numeric_value_column_is_rejected():
    content = _csv(["tract,v", f"{TRACT_A},high", f"{TRACT_B},low"])
    with pytest.raises(lib.CustomExposomeError, match="non-numeric"):
        lib.validate(content, boundary="Tract", key_col="tract",
                     value_cols=["v"], year_col=None)


def test_blanks_and_na_count_as_missing_not_as_parse_failures():
    content = _csv([
        "tract,v", f"{TRACT_A},0.4", f"{TRACT_B},NA",
        "12073001300,", "12073001400,0.6",
    ])
    facts = lib.validate(content, boundary="Tract", key_col="tract",
                         value_cols=["v"], year_col=None)
    assert facts["row_count"] == 4


def test_value_column_with_no_data_at_all_is_rejected():
    content = _csv(["tract,v,empty", f"{TRACT_A},0.4,", f"{TRACT_B},0.5,"])
    with pytest.raises(lib.CustomExposomeError, match="no data at all"):
        lib.validate(content, boundary="Tract", key_col="tract",
                     value_cols=["v", "empty"], year_col=None)


def test_missing_column_names_are_reported_with_what_the_file_has():
    with pytest.raises(lib.CustomExposomeError) as exc:
        lib.validate(_static_csv(), boundary="Tract", key_col="GEOID",
                     value_cols=["greenness"], year_col=None)
    assert "GEOID" in str(exc.value) and "tract" in str(exc.value)


def test_a_column_cannot_be_both_key_and_value():
    with pytest.raises(lib.CustomExposomeError, match="used twice"):
        lib.validate(_static_csv(), boundary="Tract", key_col="tract",
                     value_cols=["tract"], year_col=None)


def test_unusable_year_is_rejected():
    content = _csv(["tract,year,v", f"{TRACT_A},last year,0.4"])
    with pytest.raises(lib.CustomExposomeError, match="unusable year"):
        lib.validate(content, boundary="Tract", key_col="tract",
                     value_cols=["v"], year_col="year")


def test_header_only_file_is_rejected():
    with pytest.raises(lib.CustomExposomeError, match="no data rows"):
        lib.validate(b"tract,v\n", boundary="Tract", key_col="tract",
                     value_cols=["v"], year_col=None)


def test_no_value_columns_is_rejected():
    with pytest.raises(lib.CustomExposomeError, match="at least one value column"):
        lib.validate(_static_csv(), boundary="Tract", key_col="tract",
                     value_cols=[], year_col=None)


def test_unknown_boundary_is_rejected():
    with pytest.raises(lib.CustomExposomeError, match="unknown boundary"):
        lib.validate(_static_csv(), boundary="Parcel", key_col="tract",
                     value_cols=["greenness"], year_col=None)


def test_bom_in_the_header_is_stripped():
    content = "﻿tract,v\n12073001100,0.4\n".encode("utf-8")
    lib.validate(content, boundary="Tract", key_col="tract",
                 value_cols=["v"], year_col=None)


# --------------------------------------------------------------------------
# preview
# --------------------------------------------------------------------------

def test_preview_flags_which_columns_look_numeric():
    result = lib.preview(_static_csv())
    by_name = {c["name"]: c for c in result["columns"]}
    assert set(by_name) == {"tract", "greenness", "heat"}
    assert by_name["greenness"]["numeric"] is True
    assert by_name["tract"]["numeric"] is True   # a geoid is digits; the UI names it
    # The range is parsed numerically, not string-sorted, so 80.0 < 88.2 holds.
    assert by_name["greenness"]["range"] == [0.41, 0.55]
    assert by_name["heat"]["range"] == [86.0, 88.2]
    assert result["row_count"] == 2
    assert result["sample_rows"][0]["greenness"] == "0.41"


def test_preview_range_is_numeric_not_lexical():
    """A string sort would put "10" before "9"."""
    result = lib.preview(_csv(["tract,v", f"{TRACT_A},9", f"{TRACT_B},10"]))
    col = next(c for c in result["columns"] if c["name"] == "v")
    assert col["range"] == [9.0, 10.0]


def test_preview_text_column_has_no_range():
    result = lib.preview(_csv(["tract,label", f"{TRACT_A},high", f"{TRACT_B},low"]))
    col = next(c for c in result["columns"] if c["name"] == "label")
    assert col["numeric"] is False and "range" not in col


# --------------------------------------------------------------------------
# library CRUD
# --------------------------------------------------------------------------

def test_create_writes_a_catalog_shaped_manifest():
    m = _create()
    assert m["experiment"] == "custom"
    assert m["boundary"] == "Tract"
    assert m["spatial_method"] == "areal"
    assert m["temporal"] == "static"
    assert m["value_cols"] == ["greenness", "heat"]
    assert m["join_col"] == "GEOID10"          # the C3 weights table's column
    assert m["key_col"] == "tract"             # the user's own column
    assert "ontology_id" not in m      # absent, not null — see the schema
    assert m["row_count"] == 2
    assert m["variable_key"] == lib.variable_key(m["dataset_id"])


def test_catalog_subset_of_a_manifest_validates_against_the_shipped_schema():
    """A manifest is a superset: the schema sets additionalProperties:false and
    the runner needs private fields, so only the subset can validate. Nothing
    validates a merged payload at runtime — load_variables() validates the
    shipped file before the overlay is applied — but the catalog-shaped half
    must still be correct or the frontend cannot render it like a shipped row."""
    import jsonschema
    from pathlib import Path
    import app.variable_registry as vr
    schema = json.loads(Path(vr._SCHEMA_PATH).read_text())
    m = _create()
    entry = lib.catalog_entry(m)
    jsonschema.validate({"schema_version": 1, "variables": {m["variable_key"]: entry}},
                        schema)


def test_the_private_fields_are_exactly_the_documented_ones():
    """Pins the superset. A new private field is fine; a new *catalog* field
    that the schema does not allow would break the frontend's rendering."""
    m = _create()
    extra = set(m) - set(lib.CATALOG_FIELDS)
    assert extra == {
        "dataset_id", "variable_key", "owner_uid", "join_col", "key_col",
        "year_col", "value_labels", "values_path", "row_count",
        "distinct_keys", "sha256", "uploaded_filename", "created_at",
    }


def test_yearly_dataset_records_its_own_coverage_years():
    m = _create(content=_yearly_csv(), value_cols=["greenness"], year_col="year")
    assert m["temporal"] == "yearly"
    assert m["coverage_years"] == [2015, 2016]


def test_static_dataset_claims_the_full_window():
    assert _create()["coverage_years"] == [2013, 2019]


def test_values_file_is_stored_verbatim():
    m = _create()
    from pathlib import Path
    assert Path(m["values_path"]).read_bytes() == _static_csv()


def test_list_is_scoped_to_one_user():
    _create(uid=1)
    _create(uid=2, name="Someone else's")
    assert len(lib.list_for_user(1)) == 1
    assert len(lib.list_for_user(2)) == 1
    assert lib.list_for_user(3) == []


def test_two_uploads_of_the_same_file_are_distinct_datasets():
    a = _create()
    b = _create()
    assert a["dataset_id"] != b["dataset_id"]
    assert len(lib.list_for_user(1)) == 2


def test_delete_removes_it():
    m = _create()
    lib.delete(1, m["dataset_id"])
    assert lib.list_for_user(1) == []
    with pytest.raises(KeyError):
        lib.get(1, m["dataset_id"])


def test_a_half_written_manifest_does_not_break_the_listing():
    m = _create()
    from pathlib import Path
    broken = lib.dataset_dir(1, "deadbeef")
    broken.mkdir(parents=True)
    (broken / "manifest.json").write_text("{ truncated")
    assert [x["dataset_id"] for x in lib.list_for_user(1)] == [m["dataset_id"]]


def test_blank_unit_becomes_unitless():
    """The catalog schema forbids an empty display_unit (printable ASCII,
    non-empty), and the UI shows the unit next to the value."""
    assert _create()["display_unit"] == "unitless"
    assert _create(display_unit="  \u00b5g/m3 ")["display_unit"] == "g/m3"


def test_a_name_in_any_script_is_kept():
    """label has a length bound but no character pattern, unlike display_unit."""
    m = _create(name="\u7eff\u5730\u6307\u6570")
    assert m["label"] == "\u7eff\u5730\u6307\u6570"


def test_unnamed_dataset_is_rejected():
    with pytest.raises(lib.CustomExposomeError, match="give the dataset a name"):
        _create(name="   ")


def test_overlong_name_is_rejected():
    with pytest.raises(lib.CustomExposomeError, match="longer than 80"):
        _create(name="x" * 81)


# --------------------------------------------------------------------------
# selection resolution — the ownership check
# --------------------------------------------------------------------------

def test_resolve_selection_returns_only_custom_keys():
    m = _create(uid=1)
    resolved = lib.resolve_selection(1, ["ndi", m["variable_key"], "temis"])
    assert list(resolved) == [m["variable_key"]]
    assert resolved[m["variable_key"]]["values_path"].endswith("values.csv")


def test_resolve_selection_refuses_another_users_dataset():
    m = _create(uid=1)
    with pytest.raises(KeyError):
        lib.resolve_selection(2, [m["variable_key"]])


def test_provisioned_boundaries_marks_missing_data_unavailable(tmp_path, monkeypatch):
    import app.config
    root = tmp_path / "data-root"
    (root / "TRACT").mkdir(parents=True)
    (root / "TRACT" / "something.shp").write_text("x")
    (root / "BG").mkdir()                       # present but empty -> unprovisioned
    monkeypatch.setattr(app.config.settings, "SPACESCANS_DATA_DIR", root)
    by_boundary = {b["boundary"]: b for b in lib.provisioned_boundaries()}
    assert by_boundary["Tract"]["available"] is True
    assert by_boundary["BG"]["available"] is False
    assert by_boundary["County"]["available"] is False   # dir absent entirely
    assert by_boundary["ZCTA5"]["join_col"] == "ZCTA5CE10"
