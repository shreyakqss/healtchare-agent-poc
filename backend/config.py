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
    # providers means editing that one file plus these settings.
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-5.4-nano"
    LLM_TIMEOUT_SECONDS: float = 120.0
    OPENAI_API_KEY: str | None = None
    # Reasoning models (gpt-5.x) take `reasoning_effort` and reject
    # `temperature`; older chat models are the other way round. This picks
    # which one the client sends, so changing model family is a settings change.
    LLM_SUPPORTS_EFFORT: bool = True
    LLM_EFFORT: str = "low"

    # Uploaded medical documents and images. Synthetic fixtures only.
    UPLOAD_DIR: Path = BASE_DIR / "data" / "uploads"
    MAX_UPLOAD_MB: int = 25

    # One YAML per hospital/clinic; the file stem is the hospital id. The
    # active one is named in `active.txt` beside them (gitignored — it is local
    # demo state), falling back to DEFAULT_HOSPITAL_ID.
    HOSPITALS_DIR: Path = BASE_DIR / "data" / "hospitals"
    DEFAULT_HOSPITAL_ID: str = "qss-demo-clinic"

    model_config = SettingsConfigDict(
        # Absolute, so settings load no matter which directory the process
        # started in (pytest from the repo root, for instance).
        env_file=BASE_DIR / ".env",
        case_sensitive=True,
    )


settings = Settings()
