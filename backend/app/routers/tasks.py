# backend/app/routers/tasks.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.auth import get_current_user
from app import task_manager

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    task_name: str

class RenameTaskRequest(BaseModel):
    task_name: str

class ConfigRequest(BaseModel):
    experiment: str | None = None
    buffer: dict
    variables: list[str]
    execution: dict | None = None

def _verify_ownership(task_id: str, user: dict):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return task

@router.post("")
def create_task(req: CreateTaskRequest, user: dict = Depends(get_current_user)):
    try:
        return task_manager.create_task(user["id"], req.task_name)
    except ValueError as e:
        # Empty or duplicate name.
        raise HTTPException(status_code=409, detail=str(e))

@router.patch("/{task_id}")
def rename_task(task_id: str, req: RenameTaskRequest,
                user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    try:
        return task_manager.rename_task(task_id, user["id"], req.task_name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@router.get("")
def list_tasks(user: dict = Depends(get_current_user)):
    return task_manager.list_tasks(user["id"])

@router.get("/{task_id}")
def get_task(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    return task_manager.get_task(task_id)

@router.delete("/{task_id}")
def delete_task(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    # Stop any running subprocess + release locks before removing the task dir
    # so we don't orphan a dispatcher / runner holding .run_lock.
    try:
        status = task_manager._read_status(task_manager._task_dir(task_id))
        if status.get("status") == "running":
            task_manager.stop_task(task_id)
    except Exception:
        pass  # best-effort; proceed with deletion even if status unreadable
    task_manager.delete_task(task_id)
    return {"status": "deleted"}

@router.post("/{task_id}/upload")
async def upload_file(task_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    # Stream in chunks and abort as soon as the limit is exceeded, so an
    # oversized upload isn't fully buffered into memory before being rejected.
    max_bytes = 100 * 1024 * 1024
    parts: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="File exceeds 100MB limit")
        parts.append(chunk)
    content = b"".join(parts)
    try:
        summary = task_manager.save_upload(task_id, content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return summary

@router.put("/{task_id}/config")
def save_config(task_id: str, config: ConfigRequest, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    task_manager.save_config(task_id, config.model_dump(exclude_none=True))
    return {"status": "saved"}

@router.post("/{task_id}/start")
def start_task(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    try:
        # Returns {"status": "running", ...} if started now, or
        # {"status": "queued"} if another task holds the run-lock (#1).
        return task_manager.start_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{task_id}/stop")
def stop_task(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    try:
        task_manager.stop_task(task_id)
        return {"status": "stopped"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{task_id}/status")
def get_status(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    return task_manager.get_status(task_id)

@router.get("/{task_id}/logs")
def get_logs(task_id: str, since: str | None = Query(None), user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    return task_manager.get_logs(task_id, since)

@router.get("/{task_id}/results")
def download_results(
    task_id: str,
    file: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Download a result file from a task's output/ directory.

    Without ?file=, returns the merged output/result.csv (the canonical final
    output). With ?file=<basename>, returns any file under output/ — used by
    the frontend to fetch intermediate per-step parquet artifacts.

    The `file` parameter must be a plain basename (no path separators, no
    parent-dir traversal) so callers cannot escape the task's output dir.
    """
    _verify_ownership(task_id, user)
    import app.config  # local import — module-level reload in tests rebinds it
    if file is not None:
        if "/" in file or ".." in file:
            raise HTTPException(status_code=400, detail="Invalid file parameter")
        result_path = (
            app.config.settings.TASKS_DIR / f"task-{task_id}" / "output" / file
        )
    else:
        result_path = task_manager.get_result_path(task_id)
        if result_path is None:
            raise HTTPException(status_code=404, detail="Results not ready")
    if not result_path.exists() or not result_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(result_path, filename=result_path.name)

@router.get("/{task_id}/results/preview")
def preview_results(
    task_id: str,
    limit: int = Query(20, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """Return first N rows of result.csv + per-column summary stats as JSON.

    Response shape:
      {
        columns: [str, ...],
        rows: [[...], ...],          # first N rows; NaN serialized as null
        total_rows: int,
        has_more: bool,
        summary: [
          {
            name: str,
            dtype: "numeric" | "categorical",
            non_null: int,
            null_count: int,
            unique: int | null,      # only for categorical
            min: number | null,      # only for numeric
            max: number | null,
            mean: number | null,     # rounded to 6 decimals
          }, ...
        ]
      }
    """
    _verify_ownership(task_id, user)
    result_path = task_manager.get_result_path(task_id)
    if result_path is None or not result_path.exists():
        raise HTTPException(status_code=404, detail="Results not ready")
    import math
    import pandas as pd  # local import — pandas is heavy; defer until needed

    df_full = pd.read_csv(result_path)
    total_rows = len(df_full)
    df = df_full.head(limit)
    # Cast to object dtype before substituting None, otherwise float columns
    # silently convert None back to NaN (which is not JSON-compliant).
    rows = df.astype(object).where(df.notna(), None).values.tolist()

    def _finite(v: float) -> float | None:
        if v is None or (isinstance(v, float) and not math.isfinite(v)):
            return None
        return round(float(v), 6)

    summary = []
    for col in df_full.columns:
        series = df_full[col]
        non_null = int(series.notna().sum())
        null_count = total_rows - non_null
        is_numeric = pd.api.types.is_numeric_dtype(series)
        entry: dict = {
            "name": col,
            "dtype": "numeric" if is_numeric else "categorical",
            "non_null": non_null,
            "null_count": null_count,
            "unique": None,
            "min": None,
            "max": None,
            "mean": None,
        }
        if is_numeric and non_null > 0:
            entry["min"] = _finite(series.min())
            entry["max"] = _finite(series.max())
            entry["mean"] = _finite(series.mean())
        elif not is_numeric:
            # Unique non-null values for categorical columns.
            entry["unique"] = int(series.nunique(dropna=True))
        summary.append(entry)

    return {
        "columns": list(df.columns),
        "rows": rows,
        "total_rows": max(total_rows, 0),
        "has_more": total_rows > len(rows),
        "summary": summary,
    }

@router.get("/{task_id}/results/histogram")
def results_histogram(
    task_id: str,
    bins: int = Query(20, ge=5, le=50),
    user: dict = Depends(get_current_user),
):
    """Per-column histograms for every numeric exposure column in result.csv.

    Skips columns listed in `task_manager.INPUT_COLS` (cohort + geocode fields)
    and any non-numeric columns. For each remaining column, returns:
      - bins: list of `bins+1` edge values (np.histogram convention)
      - counts: list of `bins` integer counts
      - min / max / sample_size: descriptors over the non-null subset
    Columns whose dropna() series is empty are silently skipped.
    """
    _verify_ownership(task_id, user)
    result_path = task_manager.get_result_path(task_id)
    if result_path is None or not result_path.exists():
        raise HTTPException(status_code=404, detail="Results not ready")

    import math
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    df = pd.read_csv(
        result_path,
        dtype={"state_fips": "string", "county_fips": "string",
               "tract_geoid": "string", "bg_geoid": "string"},
    )

    def _finite(v: float) -> float | None:
        if v is None or (isinstance(v, float) and not math.isfinite(v)):
            return None
        return round(float(v), 6)

    histograms: list[dict] = []
    for col in df.columns:
        if col in task_manager.INPUT_COLS:
            continue
        series = df[col]
        if not pd.api.types.is_numeric_dtype(series):
            continue
        clean = series.dropna()
        if clean.empty:
            continue
        counts, edges = np.histogram(clean.values, bins=bins)
        histograms.append({
            "name": col,
            "bins": [_finite(float(e)) for e in edges.tolist()],
            "counts": [int(c) for c in counts.tolist()],
            "min": _finite(float(clean.min())),
            "max": _finite(float(clean.max())),
            "sample_size": int(len(clean)),
        })

    return {"histograms": histograms}


@router.get("/{task_id}/results/geo")
def results_geo(
    task_id: str,
    value_col: str = Query("", description="Numeric exposure column to aggregate"),
    user: dict = Depends(get_current_user),
):
    """Per-state count + mean of one numeric exposure column.

    Groups rows of result.csv by `state_fips` (cast to 2-digit zero-padded
    string) and returns count of non-null `value_col` rows + their mean.
    Returns 400 if `value_col` is missing, unknown, an input column, or
    non-numeric.
    """
    _verify_ownership(task_id, user)
    result_path = task_manager.get_result_path(task_id)
    if result_path is None or not result_path.exists():
        raise HTTPException(status_code=404, detail="Results not ready")

    if not value_col:
        raise HTTPException(status_code=400, detail="value_col query is required")

    import math
    import pandas as pd  # noqa: PLC0415

    df = pd.read_csv(
        result_path,
        dtype={"state_fips": "string", "county_fips": "string",
               "tract_geoid": "string", "bg_geoid": "string"},
    )
    if value_col not in df.columns:
        raise HTTPException(status_code=400, detail=f"Unknown column: {value_col}")
    if value_col in task_manager.INPUT_COLS:
        raise HTTPException(
            status_code=400,
            detail=f"Column is input, not exposure: {value_col}",
        )
    if not pd.api.types.is_numeric_dtype(df[value_col]):
        raise HTTPException(status_code=400, detail=f"Column is not numeric: {value_col}")

    if "state_fips" not in df.columns:
        return {"by_state": []}

    # Defensive zfill — protects against int-coerced FIPS upstream.
    sub = df[["state_fips", value_col]].copy()
    sub = sub[sub["state_fips"].notna()]
    sub["state_fips"] = sub["state_fips"].astype("string").str.zfill(2)
    sub = sub.dropna(subset=[value_col])

    def _finite(v: float) -> float | None:
        if v is None or (isinstance(v, float) and not math.isfinite(v)):
            return None
        return round(float(v), 6)

    if sub.empty:
        return {"by_state": []}

    grouped = (
        sub.groupby("state_fips", dropna=True)[value_col]
        .agg(["size", "mean"])
        .reset_index()
        .rename(columns={"size": "n", "mean": "avg"})
        .sort_values("state_fips")
    )

    by_state = [
        {
            "state_fips": str(row.state_fips),
            "count": int(row.n),
            "mean": _finite(float(row.avg)),
        }
        for row in grouped.itertuples(index=False)
    ]

    return {"by_state": by_state}


@router.get("/{task_id}/coverage")
def get_coverage(
    task_id: str,
    variables: str = Query(..., description="Comma-separated variable keys"),
    user: dict = Depends(get_current_user),
):
    """Per-variable cohort coverage statistics for a task's input.csv."""
    _verify_ownership(task_id, user)
    var_keys = [v.strip() for v in variables.split(",") if v.strip()]
    if not var_keys:
        raise HTTPException(status_code=400, detail="variables query is required")
    try:
        return task_manager.compute_coverage(task_id, var_keys)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"unknown variable(s): {exc.args[0]}")
