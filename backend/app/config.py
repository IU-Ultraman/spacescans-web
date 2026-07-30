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
    C3_CACHE_DIR: Path = DATA_DIR / "c3_cache"
    DB_PATH: Path = DATA_DIR / "spacescans.db"
    # Next.js dev server drifts to 3001/3002/... when 3000 is already taken
    # (e.g. a stale dev server still running). Allow the common range so a
    # port-drifted frontend isn't silently CORS-blocked on login.
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
    ]
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

# GitHub Codespaces: the browser reaches the app via
# https://<name>-3000.<domain> and the API via https://<name>-8000.<domain>,
# so the frontend origin must be CORS-allowed. Compose passes these two
# variables through (empty outside Codespaces — no effect locally).
_cs_name = os.environ.get("CODESPACE_NAME")
_cs_domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
if _cs_name and _cs_domain:
    settings.CORS_ORIGINS.append(f"https://{_cs_name}-3000.{_cs_domain}")


# Dataset folders expected directly under SPACESCANS_DATA_DIR (only those for
# the variables actually run are required — presence of ANY marks a real root).
_DATASET_DIRS = (
    "BG", "Community_Organization_Density", "County", "FARA", "NDI",
    "Noise", "TEMIS", "TRACT", "VNL", "Walkability", "ZCTA5",
    # TIGER roads and NHD water features are served from the distributed
    # prefiltered caches rather than raw dataset dirs; "cache" marks such a
    # root as provisioned too.
    "cache",
)


def validate_pipeline_settings() -> None:
    """Raise RuntimeError early if any pipeline path is missing.

    Called from app.main:create_app on startup so the FastAPI process refuses
    to serve traffic before its required external dependencies are present.

    Note on SPACESCANS_DATA_DIR semantics: this is the data root that the
    pipeline CLI's --data-dir parameter resolves YAML config relative paths
    against. The exposure dataset folders (BG/, Noise/, VNL/, ...) live
    directly under it.
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
    # Sanity-check the mount: YAML configs use dataset-folder prefixes
    # (`Noise/...`, `VNL/...`) resolved against the data root, so a wrong
    # mount should fail fast. A fresh clone passes because several dataset
    # dirs ship with the repo (small committed files + the VNL/TEMIS
    # skeleton) — this catches a mount pointing somewhere else entirely,
    # not a data root that simply has no data downloaded yet.
    data_root = settings.SPACESCANS_DATA_DIR
    if data_root.exists() and not any(
        (data_root / d).is_dir() for d in _DATASET_DIRS
    ):
        missing.append(f"SPACESCANS_DATA_DIR has no dataset folders={data_root}")
    if missing:
        raise RuntimeError(
            "Pipeline integration disabled. Missing paths: " + ", ".join(missing)
        )
