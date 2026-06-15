from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings, validate_pipeline_settings
from app.database import init_db
from app.routers.auth import router as auth_router
from app.routers.tasks import router as tasks_router
from app.task_manager import recover_orphaned_tasks


def create_app() -> FastAPI:
    app = FastAPI(title=settings.PROJECT_NAME)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(tasks_router)

    @app.on_event("startup")
    async def startup():
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        settings.TASKS_DIR.mkdir(parents=True, exist_ok=True)
        init_db()
        recover_orphaned_tasks()
        validate_pipeline_settings()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app

app = create_app()
