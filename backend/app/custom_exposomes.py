"""Per-user library of uploaded exposures ("custom exposomes").

A user uploads a CSV of their own values keyed by a Census geography, or one
GeoTIFF per year, and the dataset becomes a selectable exposure in the task
wizard next to the shipped ones.

Since tier-2 phase B the domain half of that path lives in
``spacescans.custom``: CSV parsing and validation, GeoTIFF inspection, units,
the definition (the manifest's fields, in the same order), the C3/C4 steps and
the post-run diagnostics. This module keeps what is the web's own, storage and
ownership: where a dataset is stored, under which user, and the ``create`` /
``create_raster`` names the paper's scripts call.

    {DATA_DIR}/custom_exposomes/user-<uid>/<dataset_id>/
        manifest.json          catalog entry + provenance (= the definition)
        values.csv             polygon: the upload, byte for byte
        rasters/<year>.tif     raster: one file per year, or static.tif

See docs/superpowers/specs/2026-09-21-custom-exposome-design.md.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import app.config
from spacescans import custom as _c
from spacescans.custom import (  # noqa: F401  (re-exported names the routers and tests use)
    BOUNDARY_DATA_DIR,
    BOUNDARY_SPEC,
    CATALOG_FIELDS,
    EXPERIMENT_KEY,
    KEY_PREFIX,
    MAX_RASTER_YEARS,
    MAX_VALUE_COLS,
    TASK_CUSTOM_KEY,
    CustomExposomeError,
    catalog_entry,
    dataset_id_from_key,
    is_custom_key,
    preview_raster,
    variable_key,
)
from spacescans.custom.units import clean_unit as _clean_unit  # noqa: F401
from spacescans.custom.units import summarise_units as _summarise_units  # noqa: F401
from spacescans.custom.units import unit_as_typed as _unit_as_typed  # noqa: F401

# Validation and preview, under the web's names.
preview = _c.preview_csv
validate = _c.validate_csv
_check_band_columns = _c.check_band_columns


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


def _derive_id(uid: int | str, content: bytes, name: str) -> str:
    """Content+name hash, re-rolled on collision so a re-upload is distinct.

    The k-th candidate is ``spacescans.custom.derive_dataset_id`` with the uid
    as salt and ``attempt=k``, so the ids this library allocates are the ones
    the web always allocated.
    """
    for attempt in range(1000):
        candidate = _c.derive_dataset_id(content, name, salt=str(uid), attempt=attempt)
        if not dataset_dir(uid, candidate).exists():
            return candidate
    raise CustomExposomeError("could not allocate a dataset id")  # pragma: no cover


# --------------------------------------------------------------------------
# library
# --------------------------------------------------------------------------

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
    value_units: dict[str, str] | None = None,
    year_col: str | None = None,
    uploaded_filename: str = "values.csv",
) -> dict[str, Any]:
    """Validate (``spacescans.custom.define_polygon``), persist and return the manifest.

    Units are per value column; the catalog's one ``display_unit`` is derived
    from them (distinct units in column order, " / "-joined).
    """
    dataset_id = _derive_id(uid, content, (name or "").strip())
    ddir = dataset_dir(uid, dataset_id)
    manifest = _c.define_polygon(
        content, boundary=boundary, key_col=key_col, value_cols=value_cols, year_col=year_col,
        label=name, description=description, labels=value_labels, units=value_units,
        uploaded_filename=uploaded_filename, dataset_id=dataset_id, owner_uid=uid,
        values_path=ddir / "values.csv",
    )
    ddir.mkdir(parents=True, exist_ok=False)
    (ddir / "values.csv").write_bytes(content)
    (ddir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def create_raster(
    uid: int | str,
    *,
    rasters: list[tuple[str, bytes, int | None]],
    name: str,
    description: str,
    value_col: str = "value",
    band: int = 1,
    value_label: str = "",
    value_unit: str = "",
    bands: list[int] | None = None,
    value_cols: list[str] | None = None,
    value_labels: dict[str, str] | None = None,
    value_units: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Validate one GeoTIFF (static) or one per year (yearly)
    (``spacescans.custom.define_raster``), persist, return the manifest.

    ``rasters`` is ``[(filename, bytes, year)]``. One or more bands become one
    result column each: ``bands`` and the parallel ``value_cols`` name them;
    without ``bands`` the single-band arguments describe the one column.
    """
    digest = hashlib.sha256()
    for _f, content, _y in rasters:
        digest.update(content)
    dataset_id = _derive_id(uid, digest.digest(), (name or "").strip())
    rdir = dataset_dir(uid, dataset_id) / "rasters"
    paths = [rdir / (f"{y}.tif" if y is not None else "static.tif") for _f, _c2, y in rasters]
    manifest = _c.define_raster(
        rasters, label=name, description=description, bands=bands, value_cols=value_cols,
        labels=value_labels, units=value_units, band=band, value_col=value_col,
        value_label=value_label, value_unit=value_unit, paths=paths, dataset_id=dataset_id,
        owner_uid=uid,
    )
    rdir.mkdir(parents=True, exist_ok=False)
    for (_f, content, _y), path in zip(rasters, paths):
        path.write_bytes(content)
    (rdir.parent / "manifest.json").write_text(json.dumps(manifest, indent=2))
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
    return _c.provisioned_boundaries(app.config.settings.SPACESCANS_DATA_DIR)
