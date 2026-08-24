"""FastAPI entrypoint. Run from `backend/`: uvicorn app.main:app --reload"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents import llm_available
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import DomainError
from app.core.logging import configure_logging
from app.domain.lifecycle import IllegalTransition
from app.integrations.hms import get_hms
from app.services import hospital_config


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(settings.DEBUG)
    hospital_config.load()  # fail fast on a broken clinic config
    get_hms()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, debug=settings.DEBUG, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(IllegalTransition)
    async def illegal_transition(_: Request, exc: IllegalTransition):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/health", tags=["meta"])
    async def health():
        return {
            "status": "ok",
            "version": settings.APP_VERSION,
            "hospital": hospital_config.active_id(),
            "llm": {"configured": llm_available(), "model": settings.LLM_MODEL},
            "hms": get_hms().status().model_dump(),
        }

    app.include_router(api_router, prefix=settings.API_PREFIX)
    return app


app = create_app()