"""Per-run feature dictionary — the companion CSV to result.csv.

Downstream analyses label tables and figures with the exposure column names
(`LILATracts_1And10`, `dist_pri`, ...), which nobody outside this project can
read. The merge writes a dictionary alongside each run's result.csv:

    feature_name,short_description,detailed_description

Written at merge time rather than served on demand, so it is archived with the
run it describes: the dictionary always lists exactly the columns that run
produced, even after the catalog gains or renames variables.

Shim: the table and the writer live in ``spacescans.catalog`` since tier-2
phase B (``features.json``, a byte copy of the ``app/data/feature_dictionary.json``
this module used to read; ``feature_rows`` / ``write_feature_csv`` write the same
bytes). The web's names are kept for the merge step and the tests. The entries
are still authored by ``scripts/extend_ontology.py``, which writes the web's
``app/data/feature_dictionary.json`` (also read by
``scripts/make_workshop_feature_labels.py``); until it writes into the package,
copy its output there — tests/test_variable_metadata_file.py fails while the
two files differ.
"""
from __future__ import annotations

import csv
from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any

from spacescans.catalog import FEATURE_FIELDNAMES, feature_rows, features, write_feature_csv
from spacescans.catalog._features import FEATURES_FILE

_DICT_PATH = Path(str(resources.files("spacescans.catalog").joinpath(FEATURES_FILE)))
FIELDNAMES = FEATURE_FIELDNAMES


def _features() -> dict[str, dict]:
    """``{column: {"label", "definition"}}``, the shape of ``features.json``."""
    return {name: {"label": f.label, "definition": f.definition}
            for name, f in features().items()}


def rows_for(columns: list[str]) -> list[dict[str, str]]:
    """Dictionary rows for `columns`, in the order given.

    Columns with no entry are skipped rather than emitted blank: the caller
    passes result.csv's full header, which includes the cohort's own columns
    (pid, dates, coordinates, any geography the user supplied) — those are
    inputs the user already understands, not linked features.
    """
    return feature_rows(columns)


#: The participant table's id column (phase D): what one row is and what its values mean.
PID_ROW = {
    "feature_name": "pid",
    "short_description": "Participant identifier",
    "detailed_description": (
        "The participant id from the uploaded cohort. One row per participant, in order of "
        "first appearance. Each exposure value is the mean over the participant's location "
        "episodes and source periods, weighted by the days that contributed a value for that "
        "variable; it is missing when no day contributed."
    ),
}


def _custom_columns(config: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Result column -> the custom definition it comes from (value columns no shipped
    variable of the selection also produces; a shipped column keeps its description)."""
    from spacescans import catalog

    definitions = config.get("custom_variables") or {}
    if not isinstance(definitions, Mapping):
        return {}
    shipped: set[str] = set()
    for key in config.get("variables") or []:
        if key in definitions:
            continue
        try:
            shipped.update(catalog.variable(key).value_cols)
        except Exception:  # noqa: BLE001 - an unknown key has no columns to describe
            continue
    out: dict[str, Mapping[str, Any]] = {}
    for definition in definitions.values():
        if not isinstance(definition, Mapping):
            continue
        for col in definition.get("value_cols") or []:
            if col not in shipped:
                out.setdefault(str(col), definition)
    return out


def write_csv(columns: list[str], out_path: Path, *, level: str | None = None,
              config: Mapping[str, Any] | None = None) -> Path:
    """Write the dictionary for `columns`. Always writes a header, even when
    no column matched, so downstream code can read the file unconditionally.

    With neither ``level`` nor ``config`` this is the package's writer (the bytes
    of every run before phase D). With them (the merge step): the participant
    table's ``pid`` row first at participant level, the shipped columns from the
    catalog's dictionary, and the task's custom columns from their own
    definitions (label, description, unit), all in result column order.
    """
    if level is None and config is None:
        return write_feature_csv(columns, out_path)
    from spacescans.custom import feature_rows as custom_rows

    shipped = {row["feature_name"]: row for row in feature_rows(columns)}
    custom = _custom_columns(config or {})
    rows: list[dict[str, str]] = []
    for col in columns:
        if col == "pid" and level == "participant":
            rows.append(dict(PID_ROW))
        elif col in custom:
            rows.extend(custom_rows(custom[col], [col]))
        elif col in shipped:
            rows.append(shipped[col])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return out_path
