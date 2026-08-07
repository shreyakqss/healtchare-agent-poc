from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    APP_NAME: str = "Healthcare Agent POC"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    DATABASE_URL: str

    # LLM provider. Everything goes through services/llm_client.py, so swapping
    # providers means editing that one file plus these two settings.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    LLM_TIMEOUT_SECONDS: float = 120.0

    # Uploaded medical documents and images. Synthetic fixtures only.
    UPLOAD_DIR: Path = BASE_DIR / "data" / "uploads"
    MAX_UPLOAD_MB: int = 25

    # Kept as a bare file, not a `config/` package — that directory name would
    # shadow this module the moment anyone added an __init__.py to it.
    HOSPITAL_CONFIG_PATH: Path = BASE_DIR / "hospital.yaml"

    model_config = SettingsConfigDict(
        # Absolute, so settings load no matter which directory the process
        # started in (pytest from the repo root, for instance).
        env_file=BASE_DIR / ".env",
        case_sensitive=True,
    )


settings = Settings()
