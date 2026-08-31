"""FastAPI entrypoint. Run from `backend/`: uvicorn app.main:app --reload"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings, validate_runtime_settings
from app.core.errors import DomainError, RateLimited
from app.core.logging import bind_request_id, configure_logging, reset_request_id
from app.core.tracing import configure as configure_tracing
from app.db import SessionLocal
from app.domain.lifecycle import IllegalTransition
from app.integrations.hms import get_hms
from app.services import auth_maintenance, hospital_config, workflow_jobs

logger = logging.getLogger(__name__)


async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    route = getattr(request.scope.get("route"), "path", "unmatched")
    logger.error(
        "Unhandled request error (%s)",
        type(exc).__name__,
        extra={"http_method": request.method, "http_route": route, "status_code": 500},
    )
    return JSONResponse(status_code=500, content={"detail": "The request could not be completed."})


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_runtime_settings(settings)
    configure_logging(settings.DEBUG, structured=settings.ENVIRONMENT == "production")
    configure_tracing()
    hospital_config.load()  # fail fast on a broken clinic config
    status = get_hms().status()
    if not status.connected:
        # Not fatal: the API still serves cases already in Postgres, and /health reports the
        # outage. But intake cannot register a patient while the hospital system is down, so
        # say so once at boot rather than leaving it to the first failed request.
        logger.warning(
            "Hospital system (%s) is not reachable at startup - patient lookup and registration "
            "will fail until it is. See README.md's OpenEMR setup section.", settings.HMS_PROVIDER,
        )
    else:
        logger.info(
            "Hospital system (%s) connected: %s patients, %s practitioners on file.",
            settings.HMS_PROVIDER, status.patients, status.practitioners,
        )
    stop_worker = asyncio.Event()
    worker = (
        asyncio.create_task(workflow_jobs.run_worker(stop_worker))
        if settings.WORKFLOW_WORKER_ENABLED
        else None
    )
    auth_maintenance_worker = asyncio.create_task(auth_maintenance.run_worker(stop_worker))
    try:
        yield
    finally:
        if worker is not None:
            stop_worker.set()
            await worker
        else:
            stop_worker.set()
        await auth_maintenance_worker


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, debug=settings.DEBUG, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type", "X-CSRF-Token"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        request_id = uuid.uuid4().hex
        context_token = bind_request_id(request_id)
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                response = await unexpected_error(request, exc)
            route = getattr(request.scope.get("route"), "path", "unmatched")
            logger.info(
                "HTTP request completed",
                extra={
                    "http_method": request.method,
                    "http_route": route,
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            if request.url.path.startswith(settings.API_PREFIX) or request.url.path in {"/health", "/ready"}:
                response.headers["Cache-Control"] = "no-store"
                response.headers["Pragma"] = "no-cache"
            if request.url.scheme == "https":
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            return response
        finally:
            reset_request_id(context_token)

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError):
        headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, RateLimited) else None
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)

    @app.exception_handler(IllegalTransition)
    async def illegal_transition(_: Request, exc: IllegalTransition):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok", "version": settings.APP_VERSION}

    @app.get("/ready", tags=["meta"])
    def readiness():
        checks = {"database": "ok", "hospital_system": "ok"}
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - readiness must report any dependency failure
            logger.warning("Database readiness check failed (%s)", type(exc).__name__)
            checks["database"] = "unavailable"
        try:
            if not get_hms().status().connected:
                checks["hospital_system"] = "unavailable"
        except Exception as exc:  # noqa: BLE001 - readiness must report any dependency failure
            logger.warning("Hospital-system readiness check failed (%s)", type(exc).__name__)
            checks["hospital_system"] = "unavailable"
        ready = all(value == "ok" for value in checks.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "not_ready", "checks": checks},
        )

    app.include_router(api_router, prefix=settings.API_PREFIX)
    return app


app = create_app()
