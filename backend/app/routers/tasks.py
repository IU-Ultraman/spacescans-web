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
def download_results(task_id: str, user: dict = Depends(get_current_user)):
    _verify_ownership(task_id, user)
    path = task_manager.get_result_path(task_id)
    if not path:
        raise HTTPException(status_code=404, detail="Results not available")
    return FileResponse(path, media_type="text/csv", filename="result.csv")
