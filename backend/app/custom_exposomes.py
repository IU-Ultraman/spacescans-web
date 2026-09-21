"""Per-user library of uploaded area-level exposures ("custom exposomes").

A user uploads a CSV of their own values keyed by a Census geography, names the
columns that hold values, and the dataset becomes a selectable exposure in the
task wizard next to the shipped ones.

v1 attaches values to a boundary layer the deployment already provisions, so no
geometry is uploaded and the pipeline needs no new code: ``static_areal`` and
``yearly_areal`` read the value table with ``read_table`` whenever the config
sets no ``plugin:``, which is exactly how Walkability and Community
Organization Density already run.

Storage mirrors how tasks are stored — on disk, not in the one-table DB:

    {DATA_DIR}/custom_exposomes/user-<uid>/<dataset_id>/
        manifest.json    catalog entry + provenance
        values.csv       the upload, header-normalised, otherwise untouched

See docs/superpowers/specs/2026-09-21-custom-exposome-design.md.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import app.config

# Boundary layer -> (join column in the C3 weights table, expected key width).
# The widths are what makes a GEOID10 string vs a numeric fips detectable at
# upload time instead of as an empty join twenty minutes into a run.
BOUNDARY_SPEC: dict[str, dict[str, Any]] = {
    "Tract": {"join_col": "GEOID10", "key_len": 11, "label": "Census Tract (2010)"},
    "BG": {"join_col": "GEOID10", "key_len": 12, "label": "Block Group (2010)"},
    "ZCTA5": {"join_col": "ZCTA5CE10", "key_len": 5, "label": "ZIP Code Tabulation Area (2010)"},
    "County": {"join_col": "GEOID10", "key_len": 5, "label": "County (2010)"},
}

# Which dataset dir under SPACESCANS_DATA_DIR must exist for a boundary's C3
# step to be runnable. Mirrors the provisioning gates in variable_registry.
BOUNDARY_DATA_DIR = {
    "Tract": "TRACT",
    "BG": "BG",
    "ZCTA5": "ZCTA5",
    "County": "County",
}

EXPERIMENT_KEY = "custom"
# Key under which a task's config.json records the datasets it selected. The
# config endpoint writes it, resolving each key against the authenticated
# caller's own library, so a runner subprocess never has to know who owns the
# task and a dataset deleted or re-uploaded mid-run cannot change what the task
# computes. config.json is the single source: the runner's plan() reads it from
# the config dict it is handed, variable_registry reads it from disk.
TASK_CUSTOM_KEY = "custom_variables"
KEY_PREFIX = "custom_"
MAX_VALUE_COLS = 40
_NON_NUMERIC_TOLERANCE = 0.5      # reject a value column that is >50% unparseable
_PREVIEW_ROWS = 5


# The fields variable_metadata.schema.json allows. A manifest is a documented
# SUPERSET of these: the runner needs join_col, values_path and friends, and the
# schema sets additionalProperties:false, so a manifest deliberately does not
# validate against it. That is safe because the task overlay is merged into the
# catalog *after* load_variables() has validated the shipped file — nothing ever
# validates a merged payload. catalog_entry() below extracts the valid subset
# for anywhere that needs one.
CATALOG_FIELDS = (
    "label", "description", "boundary", "spatial_method", "coverage_years",
    "coverage_region", "experiment", "ontology_id", "data_source", "temporal",
    "variable_type", "display_unit", "value_cols",
)


def catalog_entry(manifest: dict[str, Any]) -> dict[str, Any]:
    """The part of a manifest that satisfies the shipped catalog schema."""
    return {k: manifest[k] for k in CATALOG_FIELDS if k in manifest}


# Bounds taken from variable_metadata.schema.json so a custom entry stays
# catalog-shaped and the frontend can render it exactly like a shipped row.
_MAX_LABEL = 80
_MAX_DESCRIPTION = 400
_MAX_UNIT = 50
_DEFAULT_UNIT = "unitless"


def _clean_unit(raw: str) -> str:
    """Printable ASCII, non-empty — what the catalog schema allows.

    A unit typed in another script (or left blank) becomes "unitless" rather
    than an empty string the schema forbids.
    """
    kept = "".join(ch for ch in (raw or "").strip() if "\x20" <= ch <= "\x7e")
    return kept[:_MAX_UNIT].strip() or _DEFAULT_UNIT


class CustomExposomeError(ValueError):
    """Upload or manifest rejected. The message is shown to the user."""


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------

def library_root() -> Path:
    return app.config.settings.DATA_DIR / "custom_exposomes"


def user_dir(uid: int | str) -> Path:
    return library_root() / f"user-{uid}"


def dataset_dir(uid: int | str, dataset_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{8}", dataset_id):
        raise CustomExposomeError(f"malformed dataset id: {dataset_id!r}")
    return user_dir(uid) / dataset_id


def variable_key(dataset_id: str) -> str:
    return f"{KEY_PREFIX}{dataset_id}"


def dataset_id_from_key(key: str) -> str | None:
    if not key.startswith(KEY_PREFIX):
        return None
    candidate = key[len(KEY_PREFIX):]
    return candidate if re.fullmatch(r"[0-9a-f]{8}", candidate) else None


def is_custom_key(key: str) -> bool:
    return dataset_id_from_key(key) is not None


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def _normalise_header(name: str) -> str:
    """Trim and strip a UTF-8 BOM; otherwise leave the author's spelling."""
    return name.strip().lstrip("﻿")


def _parse_csv(content: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception as exc:  # pragma: no cover - latin-1 decodes anything
            raise CustomExposomeError(f"file is not readable text: {exc}") from exc
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise CustomExposomeError("file is empty") from None
    header = [_normalise_header(h) for h in header]
    if not any(header):
        raise CustomExposomeError("first line has no column names")
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        raise CustomExposomeError("file has a header but no data rows")
    return header, rows


def _column(header: list[str], rows: list[list[str]], name: str) -> list[str]:
    idx = header.index(name)
    return [(r[idx].strip() if idx < len(r) else "") for r in rows]


def _numeric_failures(values: list[str]) -> int:
    bad = 0
    for v in values:
        if v == "" or v.upper() in {"NA", "N/A", "NULL", "NAN", "."}:
            continue           # blanks are missing data, not a parse failure
        try:
            float(v)
        except ValueError:
            bad += 1
    return bad


def preview(content: bytes) -> dict[str, Any]:
    """Columns, sample rows and a numeric-looking flag, for the mapping UI."""
    header, rows = _parse_csv(content)
    columns = []
    for name in header:
        if not name:
            continue
        values = _column(header, rows, name)
        non_empty = [v for v in values if v != ""]
        columns.append({
            "name": name,
            "numeric": bool(non_empty) and _numeric_failures(values) == 0,
            "distinct_sample": sorted({v for v in non_empty[:200]})[:5],
        })
    return {
        "columns": columns,
        "row_count": len(rows),
        "sample_rows": [dict(zip(header, r)) for r in rows[:_PREVIEW_ROWS]],
    }


def validate(
    content: bytes,
    *,
    boundary: str,
    key_col: str,
    value_cols: list[str],
    year_col: str | None,
) -> dict[str, Any]:
    """Check the upload against the boundary's contract.

    Returns the derived facts the manifest needs (row count, coverage years).
    Raises CustomExposomeError with a message meant for the user.

    What this cannot check is set membership against the real national key
    universe — that would mean loading fifty tract shapefiles per preview. The
    key-width check below catches the class of defect that matters (a numeric
    fips against a zero-padded GEOID10 string); the true linkage rate is
    reported by the runner after the first run.
    """
    if boundary not in BOUNDARY_SPEC:
        raise CustomExposomeError(
            f"unknown boundary {boundary!r}; expected one of {sorted(BOUNDARY_SPEC)}"
        )
    if not value_cols:
        raise CustomExposomeError("select at least one value column")
    if len(value_cols) > MAX_VALUE_COLS:
        raise CustomExposomeError(
            f"{len(value_cols)} value columns exceeds the limit of {MAX_VALUE_COLS}"
        )

    header, rows = _parse_csv(content)
    missing = [c for c in [key_col, *value_cols, *( [year_col] if year_col else [] )]
               if c not in header]
    if missing:
        raise CustomExposomeError(
            f"column(s) not in the file: {', '.join(missing)}. "
            f"The file has: {', '.join(h for h in header if h)}"
        )
    overlap = set(value_cols) & ({key_col} | ({year_col} if year_col else set()))
    if overlap:
        raise CustomExposomeError(
            f"column(s) used twice: {', '.join(sorted(overlap))}"
        )

    # --- geography key ---
    keys = _column(header, rows, key_col)
    blanks = sum(1 for k in keys if k == "")
    if blanks:
        raise CustomExposomeError(
            f"{blanks:,} of {len(keys):,} rows have no value in {key_col!r}"
        )
    expected_len = BOUNDARY_SPEC[boundary]["key_len"]
    wrong_width = [k for k in keys if not (k.isdigit() and len(k) == expected_len)]
    if wrong_width:
        sample = ", ".join(repr(k) for k in wrong_width[:3])
        hint = ""
        if any(k.isdigit() and len(k) == expected_len - 1 for k in wrong_width):
            hint = (
                f" Values one digit short usually mean a leading zero was lost by a "
                f"spreadsheet; {boundary} keys are zero-padded to {expected_len} digits."
            )
        raise CustomExposomeError(
            f"{len(wrong_width):,} of {len(keys):,} values in {key_col!r} are not "
            f"{expected_len}-digit {boundary} codes (e.g. {sample}).{hint}"
        )

    # --- year ---
    years: list[int] = []
    if year_col:
        raw_years = _column(header, rows, year_col)
        bad_years = []
        for y in raw_years:
            try:
                year = int(float(y))
            except ValueError:
                bad_years.append(y)
                continue
            if not 1900 <= year <= 2100:
                bad_years.append(y)
            else:
                years.append(year)
        if bad_years:
            raise CustomExposomeError(
                f"{len(bad_years):,} rows have an unusable year in {year_col!r} "
                f"(e.g. {', '.join(repr(y) for y in bad_years[:3])})"
            )

    # --- duplicate keys: they would multiply rows in the C4 join ---
    if year_col:
        seen_pairs = list(zip(keys, years))
        dup_label = f"({key_col}, {year_col})"
    else:
        seen_pairs = keys
        dup_label = key_col
    if len(set(seen_pairs)) != len(seen_pairs):
        dupes = len(seen_pairs) - len(set(seen_pairs))
        raise CustomExposomeError(
            f"{dupes:,} duplicate {dup_label} rows. Each geography "
            f"{'and year ' if year_col else ''}must appear once."
        )

    # --- value columns ---
    non_numeric: dict[str, int] = {}
    all_blank = []
    for col in value_cols:
        values = _column(header, rows, col)
        if all(v == "" for v in values):
            all_blank.append(col)
            continue
        bad = _numeric_failures(values)
        if bad / max(1, len(values)) > _NON_NUMERIC_TOLERANCE:
            non_numeric[col] = bad
    if all_blank:
        raise CustomExposomeError(
            f"value column(s) with no data at all: {', '.join(all_blank)}"
        )
    if non_numeric:
        detail = ", ".join(f"{c} ({n:,} rows)" for c, n in non_numeric.items())
        raise CustomExposomeError(
            f"value column(s) mostly non-numeric: {detail}. "
            "Exposure values must be numbers."
        )

    coverage = [min(years), max(years)] if years else [0, 0]
    return {
        "row_count": len(rows),
        "coverage_years": coverage,
        "distinct_keys": len(set(keys)),
    }


# --------------------------------------------------------------------------
# library
# --------------------------------------------------------------------------

def _derive_id(uid: int | str, content: bytes, name: str) -> str:
    """Content+name hash, re-rolled on collision so a re-upload is distinct."""
    base = hashlib.sha256(content + name.encode() + str(uid).encode()).hexdigest()
    for attempt in range(1000):
        candidate = hashlib.sha256(f"{base}:{attempt}".encode()).hexdigest()[:8]
        if not dataset_dir(uid, candidate).exists():
            return candidate
    raise CustomExposomeError("could not allocate a dataset id")  # pragma: no cover


def create(
    uid: int | str,
    *,
    content: bytes,
    name: str,
    description: str,
    boundary: str,
    key_col: str,
    value_cols: list[str],
    value_labels: dict[str, str] | None = None,
    year_col: str | None = None,
    display_unit: str = "",
    uploaded_filename: str = "values.csv",
) -> dict[str, Any]:
    """Validate, persist and return the manifest."""
    name = name.strip()
    if not name:
        raise CustomExposomeError("give the dataset a name")
    if len(name) > _MAX_LABEL:
        raise CustomExposomeError(
            f"name is longer than {_MAX_LABEL} characters"
        )

    facts = validate(
        content,
        boundary=boundary,
        key_col=key_col,
        value_cols=value_cols,
        year_col=year_col,
    )

    dataset_id = _derive_id(uid, content, name)
    ddir = dataset_dir(uid, dataset_id)
    ddir.mkdir(parents=True, exist_ok=False)
    values_path = ddir / "values.csv"
    values_path.write_bytes(content)

    # coverage_years drives the wizard's coverage panel. A static dataset has no
    # years of its own, so it claims the full window the shipped variables use.
    coverage = facts["coverage_years"] if year_col else [2013, 2019]

    manifest = {
        # --- catalog-shaped fields, served as-is next to the shipped ones ---
        "label": name,
        "description": (description.strip() or f"User-uploaded {boundary} values.")[:_MAX_DESCRIPTION],
        "boundary": boundary,
        "spatial_method": "areal",
        "coverage_years": coverage,
        "coverage_region": "CONUS",
        "experiment": EXPERIMENT_KEY,
        # No ontology_id key at all: the catalog schema requires a non-empty
        # string when the key is present, and an absent key is falsy in the
        # frontend exactly as null would be. Custom exposomes have no ontology
        # node, which is why they render in their own block, not in the tree.
        "data_source": f"Uploaded by user: {uploaded_filename}",
        "temporal": "yearly" if year_col else "static",
        "variable_type": "continuous",
        "display_unit": _clean_unit(display_unit),
        "value_cols": list(value_cols),
        # --- private: the runner and the library need these ---
        "dataset_id": dataset_id,
        "variable_key": variable_key(dataset_id),
        "owner_uid": str(uid),
        "join_col": BOUNDARY_SPEC[boundary]["join_col"],
        "key_col": key_col,
        "year_col": year_col,
        "value_labels": dict(value_labels or {}),
        "values_path": str(values_path),
        "row_count": facts["row_count"],
        "distinct_keys": facts["distinct_keys"],
        "sha256": hashlib.sha256(content).hexdigest(),
        "uploaded_filename": uploaded_filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (ddir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def get(uid: int | str, dataset_id: str) -> dict[str, Any]:
    path = dataset_dir(uid, dataset_id) / "manifest.json"
    if not path.exists():
        raise KeyError(dataset_id)
    return json.loads(path.read_text())


def list_for_user(uid: int | str) -> list[dict[str, Any]]:
    root = user_dir(uid)
    if not root.is_dir():
        return []
    out = []
    for child in sorted(root.iterdir()):
        manifest = child / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            out.append(json.loads(manifest.read_text()))
        except json.JSONDecodeError:
            continue   # a half-written manifest should not break the listing
    out.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return out


def delete(uid: int | str, dataset_id: str) -> None:
    ddir = dataset_dir(uid, dataset_id)
    if not ddir.is_dir():
        raise KeyError(dataset_id)
    shutil.rmtree(ddir)


def resolve_selection(uid: int | str, keys: list[str]) -> dict[str, dict[str, Any]]:
    """Map the custom keys in a task's selection to their manifests.

    Raises KeyError for a key this user does not own — which is the ownership
    check for the whole feature, applied where the caller is authenticated.
    """
    resolved: dict[str, dict[str, Any]] = {}
    for key in keys:
        dataset_id = dataset_id_from_key(key)
        if dataset_id is None:
            continue
        resolved[key] = get(uid, dataset_id)   # KeyError if not this user's
    return resolved


def provisioned_boundaries() -> list[dict[str, Any]]:
    """Boundary layers whose C3 source data this deployment actually has.

    Offering a layer whose shapefiles are missing would let a user build a
    dataset that can never run.
    """
    from app.variable_registry import _unprovisioned
    root = app.config.settings.SPACESCANS_DATA_DIR
    out = []
    for boundary, spec in BOUNDARY_SPEC.items():
        data_dir = root / BOUNDARY_DATA_DIR[boundary]
        available = data_dir.is_dir() and not _unprovisioned(data_dir)
        out.append({
            "boundary": boundary,
            "label": spec["label"],
            "join_col": spec["join_col"],
            "key_len": spec["key_len"],
            "available": available,
        })
    return out
