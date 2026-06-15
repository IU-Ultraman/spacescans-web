import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "SPACESCANS"
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    ALGORITHM: str = "HS256"
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    TASKS_DIR: Path = DATA_DIR / "tasks"
    DB_PATH: Path = DATA_DIR / "spacescans.db"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    MAX_UPLOAD_SIZE_MB: int = 100

    # spacescans-pipeline integration
    SPACESCANS_DATA_DIR: Path = Path("/nonexistent")
    SPACESCANS_PIPELINE_PYTHON: Path = Path("/nonexistent")
    SPACESCANS_PIPELINE_CLI: Path = Path("/nonexistent")
    SPACESCANS_CONFIG_TEMPLATES_DIR: Path = Path("/nonexistent")
    PIPELINE_STEP_TIMEOUT_SECONDS: int = 1800  # 30 min per spacescans run

    class Config:
        env_file = ".env"

settings = Settings()


def validate_pipeline_settings() -> None:
    """Raise RuntimeError early if any pipeline path is missing.

    Called from app.main:create_app on startup so the FastAPI process refuses
    to serve traffic before its required external dependencies are present.

    Note on SPACESCANS_DATA_DIR semantics: this is the project root that the
    pipeline CLI's --data-dir parameter resolves YAML config relative paths
    against. The actual exposure data lives under <SPACESCANS_DATA_DIR>/data_full/.
    """
    missing = []
    for name in (
        "SPACESCANS_DATA_DIR",
        "SPACESCANS_PIPELINE_PYTHON",
        "SPACESCANS_PIPELINE_CLI",
        "SPACESCANS_CONFIG_TEMPLATES_DIR",
    ):
        path = getattr(settings, name)
        if not path.exists():
            missing.append(f"{name}={path}")
    # Check the data subtree exists since YAML configs use `data_full/...` prefixes
    data_subdir = settings.SPACESCANS_DATA_DIR / "data_full"
    if settings.SPACESCANS_DATA_DIR.exists() and not data_subdir.exists():
        missing.append(f"SPACESCANS_DATA_DIR/{data_subdir.name}={data_subdir}")
    if missing:
        raise RuntimeError(
            "Pipeline integration disabled. Missing paths: " + ", ".join(missing)
        )
