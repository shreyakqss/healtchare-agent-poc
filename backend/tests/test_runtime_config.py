import pytest

from app.core.config import Settings, validate_runtime_settings


def _settings(**overrides):
    values = {
        "DATABASE_URL": "postgresql://careflow:secret@db/careflow",
        "AUTH_SESSION_SECRET": "a" * 48,
        "RATE_LIMITING_ENABLED": True,
        **overrides,
    }
    return Settings(
        _env_file=None,
        **values,
    )


def test_oidc_requires_a_session_secret():
    with pytest.raises(RuntimeError, match="AUTH_SESSION_SECRET"):
        validate_runtime_settings(_settings(AUTH_SESSION_SECRET=None))


def test_production_requires_secure_urls_and_hms_credentials():
    with pytest.raises(RuntimeError) as raised:
        validate_runtime_settings(_settings(ENVIRONMENT="production"))

    message = str(raised.value)
    assert "FRONTEND_URL must use https" in message
    assert "OPENEMR_CLIENT_ID is required" in message


def test_secure_production_configuration_is_accepted():
    validate_runtime_settings(
        _settings(
            ENVIRONMENT="production",
            AUTH_SESSION_KEYS={"2026-08": "k" * 48},
            AUTH_ACTIVE_KEY_ID="2026-08",
            FRONTEND_URL="https://careflow.example",
            CORS_ORIGINS=["https://careflow.example"],
            OIDC_ISSUER_URL="https://identity.example/realms/careflow",
            OIDC_REDIRECT_URI="https://careflow.example/api/auth/callback",
            OPENEMR_BASE_URL="https://openemr.example",
            OPENEMR_TOKEN_URL="https://openemr.example/oauth2/default/token",
            OPENEMR_CLIENT_ID="client",
            OPENEMR_CLIENT_SECRET="secret",
            OPENEMR_USERNAME="service-user",
            OPENEMR_PASSWORD="secret",
        )
    )


def test_session_keyring_requires_active_key_and_strong_values():
    with pytest.raises(RuntimeError, match="AUTH_ACTIVE_KEY_ID"):
        validate_runtime_settings(_settings(AUTH_SESSION_KEYS={"old": "o" * 48}, AUTH_ACTIVE_KEY_ID="new"))
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        validate_runtime_settings(_settings(AUTH_SESSION_KEYS={"weak": "short"}, AUTH_ACTIVE_KEY_ID="weak"))
