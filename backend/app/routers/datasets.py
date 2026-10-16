"""Registered datasets: list (own + shared), register, read, edit or share, delete.

Phase D (PHASE_D.md section 2.2); the library and its access rules are ``app.datasets``.

``GET /api/datasets``
    A JSON list: the caller's datasets (newest first), then every dataset other users shared
    with the deployment. Each item: ``id, name, kind, temporal, variables, visibility,
    owned_by_me, owner_display, created_at, status`` (``"ready"`` or ``"error"``, with
    ``status_detail``), and the details: ``variable_key, key, source, version, description,
    license_note, files, checksum, spacescans_version, created_utc, updated_utc, entry``
    (the catalog-shaped entry a task shows: label, unit, coverage years...).
``GET /api/datasets/capabilities``
    What this deployment can register: ``{registry, kinds: {kind: [temporal...]},
    boundaries, limits}``.
``POST /api/datasets``
    multipart: the files (field ``files``, repeated; ``files[]`` is accepted too) and
    ``metadata``, a JSON object ``{name, kind, temporal, key?, variables?, periods?, source?,
    version?, description?, license_note?, visibility?}``:

    * ``kind``: ``polygon_table`` (one CSV; ``temporal`` static, yearly or daily),
      ``raster`` (GeoTIFFs on one grid; static, yearly, biweekly or daily; an optional
      periods manifest ``.csv``) or ``features`` (GeoPackage, GeoJSON or zipped Shapefile;
      static or yearly);
    * ``key`` (tables): ``{geography: Tract | BG | ZCTA5 | County, column, time_column?}``
      (the year column of a yearly table, the date column of a daily one); features with a
      year attribute: ``{time_column}``;
    * ``variables``: ``[{name, unit?, description?, band? (rasters)}]``; a features dataset
      has one, the distance in metres (default ``<name>_dist_m``);
    * ``periods`` (rasters, yearly features files): ``[{file, year}]`` or
      ``[{file, start, end?}]``; without them the period comes from each file name or a
      manifest;
    * ``visibility``: ``private`` (default) or ``deployment`` (every user of this
      deployment can select it; only the owner can change or delete it).

    -> ``201 {"dataset": {...}}``. Registration validates and prepares the data before it
    answers (the dataset is then ``ready``).
``GET /api/datasets/{id}`` -> ``{"dataset": {...}}``
``PATCH /api/datasets/{id}``
    Owner only. JSON ``{name?, description?, source?, version?, license_note?, visibility?,
    variables?: [{name, unit?, description?}]}`` -> ``{"dataset": {...}}``. The data, kind
    and variable names do not change; a task keeps the definition it snapshotted.
``DELETE /api/datasets/{id}``
    Owner only; ``409`` while a queued or running task uses it -> ``{"status": "deleted"}``.

Errors: ``{"detail": str, "issues": [{"field", "message"}]}`` with 400 (refused metadata or
data), 403 (another user's shared dataset), 404 (unknown, or another user's private
dataset), 409 (name taken, dataset in use), 413 (too large) or 503 (the deployment cannot
read that kind). Messages name fields, files and counts, never a data value or a server
path.
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import app.config
from app import custom_exposomes, dataset_registry, datasets
from app.auth import get_current_user

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _error(exc: datasets.DatasetsError) -> JSONResponse:
    return JSONResponse(status_code=exc.status,
                        content={"detail": exc.detail, "issues": exc.issues})


def _plain_error(status: int, detail: str, field: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status,
                        content={"detail": detail, "issues": [{"field": field, "message": detail}]})


def _limits() -> dict[str, int]:
    s = app.config.settings
    return {"max_file_mb": s.MAX_UPLOAD_SIZE_MB, "max_files": s.MAX_DATASET_FILES,
            "max_total_mb": s.MAX_DATASET_UPLOAD_MB}


@router.get("")
def list_datasets(user: dict = Depends(get_current_user)) -> list[dict]:
    items = datasets.visible_to(user["id"])
    names = datasets.display_names(d.owner for d in items)
    return [datasets.public(d, user["id"], names) for d in items]


@router.get("/capabilities")
def capabilities(user: dict = Depends(get_current_user)) -> dict:
    reg = dataset_registry.kinds()
    kinds = reg or {k: list(v) for k, v in datasets.LIBRARY_KINDS.items()}
    return {"registry": bool(reg), "kinds": kinds,
            "boundaries": custom_exposomes.provisioned_boundaries(), "limits": _limits()}


def _safe_name(raw: str | None) -> str | None:
    """The upload's file name, or None when it could not be a plain file name."""
    if not raw:
        return None
    name = raw.replace("\\", "/").split("/")[-1].strip()
    if (not name or name.startswith(".") or len(name) > 200
            or any(ord(c) < 32 for c in name)):
        return None
    return name


async def _save(upload: UploadFile, dest: Path, max_bytes: int) -> int:
    """Stream one upload to ``dest``; returns its size. Raises ValueError("too large")."""
    total = 0
    with dest.open("wb") as out:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("too large")
            out.write(chunk)
    return total


@router.post("", status_code=201)
async def create_dataset(request: Request, user: dict = Depends(get_current_user)):
    limits = _limits()
    # Starlette's own caps (1000 files and fields) give way to the configured limit,
    # checked below with a clear message.
    form = await request.form(max_files=limits["max_files"] + 1,
                              max_fields=limits["max_files"] + 10)
    raw_meta = form.get("metadata")
    if raw_meta is None:
        return _plain_error(400, "send the dataset's metadata as a JSON field named metadata",
                            "metadata")
    try:
        meta = datasets.parse_metadata(raw_meta if isinstance(raw_meta, str)
                                       else (await raw_meta.read()).decode("utf-8"))
    except datasets.DatasetsError as exc:
        return _error(exc)
    except UnicodeDecodeError:
        return _plain_error(400, "metadata must be UTF-8 JSON text", "metadata")
    uploads = [f for key in ("files", "files[]") for f in form.getlist(key)
               if hasattr(f, "filename") and hasattr(f, "read")]
    if not uploads:
        return _plain_error(400, "choose at least one file", "files")
    if len(uploads) > limits["max_files"]:
        return _plain_error(413, f"{len(uploads)} files exceed the limit of "
                                 f"{limits['max_files']}", "files")
    staging = custom_exposomes.library_root() / ".staging" / uuid.uuid4().hex
    staging.mkdir(parents=True)
    try:
        saved: dict[str, Path] = {}
        total = 0
        per_file = limits["max_file_mb"] * 1024 * 1024
        for upload in uploads:
            name = _safe_name(upload.filename)
            if name is None:
                return _plain_error(400, "a file has no usable name", "files")
            if name.lower() in {n.lower() for n in saved}:
                return _plain_error(400, f"{name} is given twice", "files")
            try:
                size = await _save(upload, staging / name, per_file)
            except ValueError:
                return _plain_error(413, f"{name} exceeds the {limits['max_file_mb']} MB limit",
                                    "files")
            if size == 0:
                return _plain_error(400, f"{name} is empty", "files")
            total += size
            if total > limits["max_total_mb"] * 1024 * 1024:
                return _plain_error(413, f"the files exceed {limits['max_total_mb']} MB in total",
                                    "files")
            saved[name] = staging / name
        try:
            ds = await run_in_threadpool(datasets.register, user["id"], saved, meta)
        except datasets.DatasetsError as exc:
            return _error(exc)
        names = datasets.display_names([ds.owner])
        return JSONResponse(status_code=201,
                            content={"dataset": datasets.public(ds, user["id"], names)})
    finally:
        shutil.rmtree(staging, ignore_errors=True)


@router.get("/{dataset_id}")
def get_dataset(dataset_id: str, user: dict = Depends(get_current_user)):
    try:
        ds = datasets.find(user["id"], dataset_id)
    except datasets.DatasetsError as exc:
        return _error(exc)
    return {"dataset": datasets.public(ds, user["id"], datasets.display_names([ds.owner]))}


@router.patch("/{dataset_id}")
def update_dataset(dataset_id: str, changes: dict[str, Any],
                   user: dict = Depends(get_current_user)):
    try:
        ds = datasets.update(user["id"], dataset_id, changes)
    except datasets.DatasetsError as exc:
        return _error(exc)
    return {"dataset": datasets.public(ds, user["id"], datasets.display_names([ds.owner]))}


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, user: dict = Depends(get_current_user)):
    try:
        datasets.delete(user["id"], dataset_id)
    except datasets.DatasetsError as exc:
        return _error(exc)
    return {"status": "deleted"}
