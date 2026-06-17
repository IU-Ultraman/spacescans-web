import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings, validate_pipeline_settings
from app.database import init_db
from app.routers.auth import router as auth_router
from app.routers.tasks import router as tasks_router
from app.routers.variables import router as variables_router
from app.task_manager import recover_orphaned_tasks
from app import variable_registry

_log = logging.getLogger(__name__)


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
    app.include_router(variables_router)

    @app.on_event("startup")
    async def startup():
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        settings.TASKS_DIR.mkdir(parents=True, exist_ok=True)
        init_db()
        recover_orphaned_tasks()
        validate_pipeline_settings()
        # Sprint 12 G5: eager-fire the pipeline-version probe at boot so a
        # stale spacescans-pipeline install fails fast on `uvicorn` startup
        # instead of on the first /api/variables request. The probe is
        # guarded by a module-level _PROBE_DONE flag, so the lazy call at
        # the first load_variables() is a defense-in-depth no-op once this
        # has run. Errors are logged but not re-raised — the existing lazy
        # call at /api/variables will still surface the failure to the
        # client, matching the previous "first-request" semantics.
        try:
            variable_registry._assert_pipeline_version_compatible()
        except Exception as exc:  # pragma: no cover - defensive
            _log.error("pipeline version probe failed at startup: %r", exc)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app

app = create_app()
