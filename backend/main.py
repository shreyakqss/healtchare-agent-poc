from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.audit import router as audit_router
from api.cases import router as cases_router
from api.hospital import router as hospital_router
from api.intake import router as intake_router
from api.review import router as review_router
from config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "Healthcare Agent POC Backend",
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "message": "Healthcare Agent POC Backend is running",
    }


# Each router declares its own resource path (/intake-sessions, /cases, ...);
# the version prefix lives here so there is exactly one place to change it.
API_PREFIX = "/api/v1/healthcare"

app.include_router(intake_router, prefix=API_PREFIX)
app.include_router(cases_router, prefix=API_PREFIX)
app.include_router(review_router, prefix=API_PREFIX)
app.include_router(audit_router, prefix=API_PREFIX)
app.include_router(hospital_router, prefix=API_PREFIX)
