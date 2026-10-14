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

from importlib import resources
from pathlib import Path

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


def write_csv(columns: list[str], out_path: Path) -> Path:
    """Write the dictionary for `columns`. Always writes a header, even when
    no column matched, so downstream code can read the file unconditionally."""
    return write_feature_csv(columns, out_path)
