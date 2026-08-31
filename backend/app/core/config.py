"""Application settings, loaded once from `backend/.env`."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.integrations.hms.openemr.scopes import DEFAULT_SCOPES as OPENEMR_DEFAULT_SCOPES

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_NAME: str = "CareFlow Intake & Triage"
    APP_VERSION: str = "0.2.0"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1/healthcare"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    AUTH_MODE: Literal["disabled", "oidc"] = "oidc"
    OIDC_ISSUER_URL: str = "http://localhost:8500/realms/careflow"
    OIDC_AUDIENCE: str = "careflow-api"
    OIDC_WEB_CLIENT_ID: str = "careflow-web"
    OIDC_REDIRECT_URI: str = "http://localhost:3000/api/auth/callback"
    OIDC_JWKS_TTL_SECONDS: int = 300
    AUTH_SESSION_SECRET: str | None = None
    AUTH_SESSION_KEYS: dict[str, str] = Field(default_factory=dict)
    AUTH_ACTIVE_KEY_ID: str = "legacy"
    AUTH_SESSION_HOURS: int = 8
    AUTH_SESSION_RETENTION_DAYS: int = 7
    AUTH_MAINTENANCE_SECONDS: int = 3600
    RATE_LIMITING_ENABLED: bool = True
    AUTH_COOKIE_SECURE: bool = True
    FRONTEND_URL: str = "http://localhost:3000"

    DATABASE_URL: str

    # HIPAA technical safeguard: reject further intake processing on a session
    # that has sat unfinished (CREATED/INGESTING) longer than this.
    SESSION_TIMEOUT_MINUTES: int = 30

    WORKFLOW_WORKER_ENABLED: bool = True
    WORKFLOW_POLL_SECONDS: float = 1.0
    WORKFLOW_LEASE_SECONDS: int = 300
    WORKFLOW_MAX_ATTEMPTS: int = 3

    # LLM — every model call goes through app/agents/llm.py (agno OpenAIChat).
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-5.4-nano"
    LLM_TIMEOUT_SECONDS: float = 120.0
    LLM_SUPPORTS_EFFORT: bool = True
    LLM_EFFORT: str = "low"
    OPENAI_API_KEY: str | None = None

    TAVILY_API_KEY: str | None = None

    # Agent tracing (app/core/tracing.py). Both keys set = every agno run is exported.
    # Self-hosted Langfuse listens on http://localhost:3000.
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None

    # Synthetic uploads only.
    UPLOAD_DIR: Path = BACKEND_DIR / "data" / "uploads"
    MAX_UPLOAD_MB: int = 25

    # One YAML per clinic; the file stem is the hospital id.
    HOSPITALS_DIR: Path = BACKEND_DIR / "data" / "hospitals"
    DEFAULT_HOSPITAL_ID: str = "qss-demo-clinic"

    # The hospital system is the source of truth for patients, practitioners and documents.
    # Only OpenEMR is implemented; the tests install an in-memory stand-in instead
    # (app/integrations/hms/__init__.py::use_hms).
    HMS_PROVIDER: Literal["openemr"] = "openemr"

    # OpenEMR adapter - only used when HMS_PROVIDER=openemr. Reads use the FHIR API, clinical
    # writes the standard REST API; one OAuth client covers both. Register it with
    # `python scripts/openemr_register_client.py` (see README.md's OpenEMR setup section).
    OPENEMR_BASE_URL: str = "http://localhost:8300"
    OPENEMR_FHIR_PATH: str = "/apis/default/fhir"
    OPENEMR_API_PATH: str = "/apis/default/api"
    OPENEMR_TOKEN_URL: str = "http://localhost:8300/oauth2/default/token"
    OPENEMR_CLIENT_ID: str | None = None
    OPENEMR_CLIENT_SECRET: str | None = None
    # Scopes are fixed at client registration; this default is the list the registration
    # script requests. user/* scopes (not system/*) so the OAuth2 password grant applies,
    # which needs a real OpenEMR user login below. Only `.read`/`.write` suffixes exist.
    OPENEMR_SCOPES: str = OPENEMR_DEFAULT_SCOPES
    OPENEMR_USERNAME: str | None = None
    OPENEMR_PASSWORD: str | None = None

    # Direct MariaDB access for the one OpenEMR admin write with no REST/FHIR path at all:
    # creating a practitioner login (users/users_secure) and its facility_user_ids role rows.
    OPENEMR_MYSQL_HOST: str = "localhost"
    OPENEMR_MYSQL_PORT: int = 3307
    OPENEMR_MYSQL_DB: str = "openemr"
    OPENEMR_MYSQL_USER: str | None = None
    OPENEMR_MYSQL_PASSWORD: str | None = None

    # Keycloak Admin REST API - used only by self-registration/account provisioning to
    # create a Keycloak user. The `careflow-admin` client has only manage-users/view-users.
    KEYCLOAK_ADMIN_URL: str = "http://localhost:8500"
    KEYCLOAK_REALM: str = "careflow"
    KEYCLOAK_ADMIN_CLIENT_ID: str | None = None
    KEYCLOAK_ADMIN_CLIENT_SECRET: str | None = None

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", case_sensitive=True, extra="ignore")

    @property
    def llm_enabled(self) -> bool:
        return bool(self.OPENAI_API_KEY)

    @property
    def tracing_enabled(self) -> bool:
        return bool(self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY)

    @field_validator("CORS_ORIGINS")
    @classmethod
    def cors_origins_must_be_explicit(cls, origins: list[str]) -> list[str]:
        if not origins or any(origin.strip() == "*" for origin in origins):
            raise ValueError("CORS_ORIGINS must contain explicit origins when credentials are enabled.")
        return origins


def validate_runtime_settings(config: Settings) -> None:
    errors: list[str] = []
    if config.AUTH_MODE == "oidc":
        if config.AUTH_SESSION_KEYS:
            if any(not re.fullmatch(r"[A-Za-z0-9._-]{1,32}", key_id) for key_id in config.AUTH_SESSION_KEYS):
                errors.append("AUTH_SESSION_KEYS identifiers must be 1-32 safe characters")
            if config.AUTH_ACTIVE_KEY_ID not in config.AUTH_SESSION_KEYS:
                errors.append("AUTH_ACTIVE_KEY_ID must identify an AUTH_SESSION_KEYS entry")
            if any(len(value.encode()) < 32 for value in config.AUTH_SESSION_KEYS.values()):
                errors.append("Every AUTH_SESSION_KEYS value must contain at least 32 bytes")
        elif len(config.AUTH_SESSION_SECRET or "") < 32:
            errors.append("AUTH_SESSION_SECRET must contain at least 32 characters when OIDC is enabled")
    if config.ENVIRONMENT == "production":
        if config.DEBUG:
            errors.append("DEBUG must be false in production")
        if config.AUTH_MODE != "oidc":
            errors.append("AUTH_MODE must be oidc in production")
        if not config.AUTH_SESSION_KEYS:
            errors.append("AUTH_SESSION_KEYS must provide a versioned keyring in production")
        if not config.RATE_LIMITING_ENABLED:
            errors.append("RATE_LIMITING_ENABLED must be true in production")
        if not config.AUTH_COOKIE_SECURE:
            errors.append("AUTH_COOKIE_SECURE must be true in production")
        urls = {
            "FRONTEND_URL": config.FRONTEND_URL,
            "OIDC_ISSUER_URL": config.OIDC_ISSUER_URL,
            "OIDC_REDIRECT_URI": config.OIDC_REDIRECT_URI,
            "OPENEMR_BASE_URL": config.OPENEMR_BASE_URL,
            "OPENEMR_TOKEN_URL": config.OPENEMR_TOKEN_URL,
        }
        for name, value in urls.items():
            if urlsplit(value).scheme != "https":
                errors.append(f"{name} must use https in production")
        if any(urlsplit(origin).scheme != "https" for origin in config.CORS_ORIGINS):
            errors.append("Every CORS origin must use https in production")
        required_hms = {
            "OPENEMR_CLIENT_ID": config.OPENEMR_CLIENT_ID,
            "OPENEMR_CLIENT_SECRET": config.OPENEMR_CLIENT_SECRET,
            "OPENEMR_USERNAME": config.OPENEMR_USERNAME,
            "OPENEMR_PASSWORD": config.OPENEMR_PASSWORD,
        }
        errors.extend(f"{name} is required in production" for name, value in required_hms.items() if not value)
    if errors:
        raise RuntimeError("Invalid runtime configuration: " + "; ".join(errors))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
