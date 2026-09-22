"""Per-user custom exposome library — upload, preview, list, delete.

Kept off /api/variables on purpose: that endpoint is unauthenticated and its
schema_version is pinned, so per-user rows must not appear in it. The frontend
fetches both and merges them client-side.

See docs/superpowers/specs/2026-09-21-custom-exposome-design.md.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import app.config
from app import custom_exposomes
from app.auth import get_current_user

router = APIRouter(prefix="/api/custom-exposomes", tags=["custom-exposomes"])


async def _read_upload(file: UploadFile) -> bytes:
    """Stream with an early abort, like the cohort upload does."""
    max_bytes = app.config.settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    parts: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {app.config.settings.MAX_UPLOAD_SIZE_MB}MB limit",
            )
        parts.append(chunk)
    if total == 0:
        raise HTTPException(status_code=400, detail="File is empty")
    return b"".join(parts)


def _require_csv(file: UploadFile) -> None:
    name = (file.filename or "").lower()
    if not (name.endswith(".csv") or name.endswith(".txt")):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")


def _public(manifest: dict) -> dict:
    """The manifest minus the absolute server path, which is nobody's business."""
    return {k: v for k, v in manifest.items() if k != "values_path"}


@router.get("/boundaries")
def list_boundaries(user: dict = Depends(get_current_user)):
    """Which boundary layers this deployment can actually run a custom C3 on."""
    return {"boundaries": custom_exposomes.provisioned_boundaries()}


@router.get("")
def list_datasets(user: dict = Depends(get_current_user)):
    """The caller's datasets, shaped like /api/variables entries."""
    return {
        "variables": {
            m["variable_key"]: _public(m)
            for m in custom_exposomes.list_for_user(user["id"])
        }
    }


@router.post("/preview")
async def preview_upload(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Column names, a numeric-looking flag and a few rows, for the mapping UI."""
    _require_csv(file)
    content = await _read_upload(file)
    try:
        result = custom_exposomes.preview(content)
    except custom_exposomes.CustomExposomeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["filename"] = file.filename
    return result


@router.post("")
async def create_dataset(
    file: UploadFile = File(...),
    name: str = Form(...),
    boundary: str = Form(...),
    key_col: str = Form(...),
    value_cols: str = Form(..., description="JSON array of column names"),
    description: str = Form(""),
    year_col: str | None = Form(None),
    value_labels: str = Form("{}", description="JSON object column -> label"),
    value_units: str = Form("{}", description="JSON object column -> unit"),
    user: dict = Depends(get_current_user),
):
    _require_csv(file)
    content = await _read_upload(file)
    try:
        cols = json.loads(value_cols)
        labels = json.loads(value_labels or "{}")
        units = json.loads(value_units or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"value_cols/value_labels/value_units must be JSON: {exc}",
        ) from exc
    if not isinstance(cols, list) or not all(isinstance(c, str) for c in cols):
        raise HTTPException(status_code=400, detail="value_cols must be a list of strings")
    for field_name, mapping in (("value_labels", labels), ("value_units", units)):
        if not isinstance(mapping, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()
        ):
            raise HTTPException(
                status_code=400, detail=f"{field_name} must be an object of strings"
            )

    available = {
        b["boundary"] for b in custom_exposomes.provisioned_boundaries() if b["available"]
    }
    if boundary not in available:
        raise HTTPException(
            status_code=400,
            detail=(
                f"this deployment has no {boundary} boundary data provisioned, so a "
                f"dataset on it could never run"
            ),
        )

    try:
        manifest = custom_exposomes.create(
            user["id"],
            content=content,
            name=name,
            description=description,
            boundary=boundary,
            key_col=key_col,
            value_cols=cols,
            value_labels=labels,
            value_units=units,
            year_col=(year_col or None),
            uploaded_filename=file.filename or "values.csv",
        )
    except custom_exposomes.CustomExposomeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _public(manifest)


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, user: dict = Depends(get_current_user)):
    try:
        custom_exposomes.delete(user["id"], dataset_id)
    except custom_exposomes.CustomExposomeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="Dataset not found") from None
    return {"status": "deleted"}
