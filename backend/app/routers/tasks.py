# backend/app/routers/tasks.py
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.auth import get_current_user
from app import custom_exposomes, datasets, output_level, task_manager

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
    # Phase D: one row per participant (default) or per location episode.
    output_level: Literal["participant", "episode"] = output_level.DEFAULT_LEVEL
    # Phase D: registered datasets selected by id (own or shared); their
    # variables are linked after the other selected ones.
    custom_datasets: list[str] | None = None

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

@router.delete("/stale")
def delete_stale_tasks(user: dict = Depends(get_current_user)):
    """#3: remove the caller's stale not_started tasks. Declared before the
    /{task_id} routes so 'stale' isn't captured as a task id."""
    removed = task_manager.delete_stale_tasks(user["id"])
    return {"deleted": removed}

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
    payload = config.model_dump(exclude_none=True)
    # Resolve the custom datasets of the selection — by id (custom_datasets) or
    # by their custom_<id> keys in variables — against what THIS caller may see
    # (their own datasets and the ones shared with the deployment) and snapshot
    # the definitions into the config. This is the access check for the
    # feature — the runner subprocess has no user — and it freezes what the
    # task computes against a later edit, delete or re-upload. Anything the
    # client sent under this key is discarded.
    payload.pop(custom_exposomes.TASK_CUSTOM_KEY, None)
    dataset_ids = payload.pop("custom_datasets", None) or []
    variables = list(payload.get("variables", []))
    custom_keys = [k for k in variables if custom_exposomes.is_custom_key(k)]
    if dataset_ids or custom_keys:
        try:
            snapshot, used = datasets.resolve_for_task(user["id"], dataset_ids, custom_keys)
        except datasets.DatasetsError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        variables += [key for key in snapshot if key not in variables]
        payload["variables"] = variables
        payload[custom_exposomes.TASK_CUSTOM_KEY] = snapshot
        payload["custom_datasets"] = used
    task_manager.save_config(task_id, payload)
    return {"status": "saved"}

@router.post("/{task_id}/start")
def start_task(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    # Phase D: a dataset the task snapshotted must still exist and be visible
    # to the task's user (another user may have stopped sharing it); a finished
    # task keeps its results either way.
    config_path = task_manager._task_dir(task_id) / "config.json"
    if config_path.exists():
        import json  # noqa: PLC0415

        try:
            config = json.loads(config_path.read_text())
        except ValueError:
            config = {}
        gone = datasets.unusable_in_task(user["id"], config)
        if gone:
            raise HTTPException(
                status_code=409,
                detail=("this task uses custom dataset(s) that were deleted or are no "
                        f"longer shared with you ({', '.join(gone)}); choose its "
                        "exposures again"),
            )
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
    headers = None
    if file is None:
        # Phase D: what one row of result.csv is (participant or episode).
        headers = {"X-Output-Level": output_level.result_level(result_path.parent.parent)}
    return FileResponse(result_path, filename=result_path.name, headers=headers)

# result.csv columns read as text: ids (a zero-padded numeric pid is still an id)
# and the geography codes.
_TEXT_DTYPES = {"pid": "string", "state_fips": "string", "county_fips": "string",
                "tract_geoid": "string", "bg_geoid": "string"}


def _read_result(result_path):
    import pandas as pd  # noqa: PLC0415 - pandas is heavy; defer until needed

    return pd.read_csv(result_path, dtype=_TEXT_DTYPES)


def _exposure_columns(task_id: str, columns: list[str], level: str) -> list[str]:
    """result.csv columns that are linked values: at participant level every column
    but pid; at episode level not the cohort's own columns (input.csv's header) and
    not an id/geocode column."""
    import pandas as pd  # noqa: PLC0415

    if level == output_level.PARTICIPANT:
        return [c for c in columns if c != "pid"]
    input_csv = task_manager._task_dir(task_id) / "input.csv"
    cohort_cols: set[str] = set()
    if input_csv.exists():
        try:
            cohort_cols = set(pd.read_csv(input_csv, nrows=0).columns)
        except Exception:  # noqa: BLE001 - an unreadable cohort only widens the list
            cohort_cols = set()
    return [c for c in columns
            if c not in task_manager.INPUT_COLS and c not in cohort_cols]


@router.get("/{task_id}/results/preview")
def preview_results(
    task_id: str,
    limit: int = Query(20, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """Return first N rows of result.csv + per-column summary stats as JSON.

    Response shape:
      {
        level: "participant" | "episode",   # what one row is (phase D)
        row_unit: "participants" | "episodes",
        linkage: {column: {linked, total, rate_pct}},   # exposure columns, at the
                                                       # level of the table
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

    level = output_level.result_level(result_path.parent.parent)
    df_full = _read_result(result_path)
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
        "level": level,
        "row_unit": output_level.ROW_UNIT[level],
        "columns": list(df.columns),
        "rows": rows,
        "total_rows": max(total_rows, 0),
        "has_more": total_rows > len(rows),
        "summary": summary,
        "linkage": output_level.linkage_rates(
            df_full, _exposure_columns(task_id, list(df_full.columns), level)),
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

    level = output_level.result_level(result_path.parent.parent)
    df = _read_result(result_path)

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

    return {"histograms": histograms, "level": level,
            "row_unit": output_level.ROW_UNIT[level]}


@router.get("/{task_id}/results/geo")
def results_geo(
    task_id: str,
    value_col: str = Query("", description="Numeric exposure column to aggregate"),
    user: dict = Depends(get_current_user),
):
    """Per-state count + mean of one numeric exposure column.

    Episode level: groups rows of result.csv by `state_fips` (cast to 2-digit
    zero-padded string) and returns count of non-null `value_col` rows + their
    mean. Participant level (phase D): each participant is placed in the state
    of their longest episode in input.csv (ties: the most recent start, then
    the earlier row) and the participants' values are grouped by that state.
    No `state_fips` in the cohort -> no states, as before.
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

    task_dir = result_path.parent.parent
    level = output_level.result_level(task_dir)
    df = _read_result(result_path)
    if value_col not in df.columns:
        raise HTTPException(status_code=400, detail=f"Unknown column: {value_col}")
    if value_col in task_manager.INPUT_COLS:
        raise HTTPException(
            status_code=400,
            detail=f"Column is input, not exposure: {value_col}",
        )
    if not pd.api.types.is_numeric_dtype(df[value_col]):
        raise HTTPException(status_code=400, detail=f"Column is not numeric: {value_col}")

    extra = {"level": level, "row_unit": output_level.ROW_UNIT[level]}
    if level == output_level.PARTICIPANT:
        extra["state_rule"] = "longest_episode"
        try:
            states = output_level.participant_states(task_dir)
        except (OSError, ValueError):
            states = None
        if states is None or "pid" not in df.columns:
            return {"by_state": [], **extra}
        states["pid"] = states["pid"].astype("string")
        sub = states.merge(df[["pid", value_col]], on="pid", how="inner")
        sub = sub[["state_fips", value_col]]
    else:
        if "state_fips" not in df.columns:
            return {"by_state": [], **extra}
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
        return {"by_state": [], **extra}

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

    return {"by_state": by_state, **extra}


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
        # Custom datasets not yet in the task's config: the caller's own or
        # shared ones (phase D), so the wizard can show their coverage too.
        extra = datasets.overlay_for_keys(user["id"], var_keys)
        out = task_manager.compute_coverage(task_id, var_keys, extra_overlay=extra)
        # Phase D: the pre-execution check counts input rows (location episodes)
        # whatever the task's output level (dates and locations are per episode).
        out["level"] = output_level.EPISODE
        return out
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"unknown variable(s): {exc.args[0]}")
