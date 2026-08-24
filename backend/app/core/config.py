"""Application settings, loaded once from `backend/.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_NAME: str = "CareFlow Intake & Triage"
    APP_VERSION: str = "0.2.0"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1/healthcare"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    DATABASE_URL: str

    # LLM — every model call goes through app/agents/llm.py (agno OpenAIChat).
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-5.4-nano"
    LLM_TIMEOUT_SECONDS: float = 120.0
    LLM_SUPPORTS_EFFORT: bool = True
    LLM_EFFORT: str = "low"
    OPENAI_API_KEY: str | None = None

    # Synthetic uploads only.
    UPLOAD_DIR: Path = BACKEND_DIR / "data" / "uploads"
    MAX_UPLOAD_MB: int = 25

    # One YAML per clinic; the file stem is the hospital id.
    HOSPITALS_DIR: Path = BACKEND_DIR / "data" / "hospitals"
    DEFAULT_HOSPITAL_ID: str = "qss-demo-clinic"

    # HMS adapter: "mock" is the only implementation in the POC.
    HMS_PROVIDER: str = "mock"
    HMS_FIXTURE: Path = BACKEND_DIR / "data" / "hms" / "patients.yaml"

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", case_sensitive=True, extra="ignore")

    @property
    def llm_enabled(self) -> bool:
        return bool(self.OPENAI_API_KEY)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
