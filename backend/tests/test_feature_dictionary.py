"""The per-run feature dictionary written alongside result.csv.

Downstream analyses label tables and figures from this file, so it has to
describe exactly the columns a given run produced — no more (a task that ran
three variables must not advertise all nine) and no fewer (a column with no
description sends the analyst back to guessing from the raw name).
"""
import csv
import json
from pathlib import Path

import pytest

from app import feature_dictionary as fd


def _dict_json() -> dict:
    return json.loads(fd._DICT_PATH.read_text())["features"]


def test_every_catalog_value_col_has_an_entry():
    """The dictionary is generated from the same table that authors the
    ontology nodes; this catches a variable gaining a value_col without one."""
    meta = json.loads(
        (Path(fd.__file__).parent / "data" / "variable_metadata.json").read_text()
    )["variables"]
    declared = {c for v in meta.values() for c in v["value_cols"]}
    described = set(_dict_json())
    assert not declared - described, f"no dictionary entry: {declared - described}"


def test_entries_carry_both_descriptions():
    for col, spec in _dict_json().items():
        assert spec["label"].strip(), col
        assert spec["definition"].strip(), col
        # The "(Result column: X.)" suffix belongs to the ontology, where
        # there is no separate column-name field. Here it is noise.
        assert "(Result column:" not in spec["definition"], col


def test_rows_cover_exposure_columns_in_order_and_skip_cohort_columns():
    columns = ["pid", "startDate", "longitude", "state_fips",
               "dist_pri", "ndi", "l50dba_exi"]
    rows = fd.rows_for(columns)
    assert [r["feature_name"] for r in rows] == ["dist_pri", "ndi", "l50dba_exi"]
    assert rows[0]["short_description"] == "Distance to primary road"
    assert "meters" in rows[0]["detailed_description"]


def test_unknown_columns_are_skipped_not_blank():
    rows = fd.rows_for(["not_a_feature", "dist_pri"])
    assert [r["feature_name"] for r in rows] == ["dist_pri"]


def test_write_csv_round_trips_commas_and_dashes(tmp_path):
    """Labels carry commas, ampersands and em dashes — a naive writer would
    corrupt the file exactly where the descriptions are most useful."""
    out = fd.write_csv(["r_civic", "l50dba_exi", "LILATracts_1And10"],
                       tmp_path / "feature_dictionary.csv")
    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["feature_name"] for r in rows] == [
        "r_civic", "l50dba_exi", "LILATracts_1And10"]
    assert rows[0]["short_description"] == "Civic & social associations"
    assert "10,000" in rows[0]["detailed_description"]      # comma survived
    assert "—" in rows[1]["short_description"]              # em dash survived


def test_header_written_even_with_no_matching_columns(tmp_path):
    """A cohort-only column list still yields a readable file, so downstream
    code can open it unconditionally."""
    out = fd.write_csv(["pid", "latitude"], tmp_path / "d.csv")
    assert out.read_text() == ",".join(fd.FIELDNAMES) + "\n"


def test_fara_descriptions_state_the_share_semantics():
    """The USDA source is a 0/1 tract flag, but the exported value is the
    share of the residential buffer in flagged tracts (measured: 7 of 100 demo
    patients, all boundary-straddling). Calling it a "flag" would invite
    astype(bool) downstream."""
    entries = _dict_json()
    for col in ("LILATracts_1And10", "LATracts1", "HUNVFlag", "LowIncomeTracts"):
        d = entries[col]["definition"]
        assert d.startswith("Share of the residential buffer"), (col, d)


def test_merge_writes_the_dictionary_next_to_result(tmp_path, monkeypatch):
    """fan_in is where a run's final column set is known — the dictionary has
    to be produced there, not reconstructed later from the catalog."""
    import pandas as pd
    from app.experiments import _merge

    task_dir = tmp_path / "task-x"
    (task_dir / "output").mkdir(parents=True)
    pd.DataFrame({"pid": ["P1"], "startDate": ["2017-01-01"],
                  "longitude": [-86.1], "latitude": [39.7]}).to_csv(
        task_dir / "input.csv", index=False)
    pd.DataFrame({"pid": ["P1"], "episode_id": [0], "dist_pri": [123.4]}).to_csv(
        task_dir / "output" / "result_tiger_proximity.csv", index=False)

    _merge.fan_in(task_dir, ["tiger_proximity"])

    written = task_dir / "output" / "feature_dictionary.csv"
    with written.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["feature_name"] for r in rows] == ["dist_pri"]
