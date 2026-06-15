# backend/app/routers/tasks.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.auth import get_current_user
from app import task_manager
from app.task_manager import TaskBusyError

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

class CreateTaskRequest(BaseModel):
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
    return task_manager.create_task(user["id"], req.task_name)

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
    task_manager.delete_task(task_id)
    return {"status": "deleted"}

@router.post("/{task_id}/upload")
async def upload_file(task_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 100MB limit")
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
        return task_manager.start_task(task_id)
    except TaskBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
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
