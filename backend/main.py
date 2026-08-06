from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from api.audit import router as audit_router
from api.cases import router as cases_router
from api.intake import router as intake_router
from api.review import router as review_router

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

# Include routers for different API endpoints
app.include_router(audit_router, prefix="/api/audit", tags=["audit"])
app.include_router(cases_router, prefix="/api/cases", tags=["cases"])
app.include_router(intake_router, prefix="/api/intake", tags=["intake"])
app.include_router(review_router, prefix="/api/review", tags=["review"])
