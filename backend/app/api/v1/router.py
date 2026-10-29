from fastapi import APIRouter

from app.api.v1 import admin_doctors, admin_patients, audit, auth, cases, hms, hospital, intake, reviews

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(intake.router)
api_router.include_router(cases.router)
api_router.include_router(reviews.router)
api_router.include_router(audit.router)
api_router.include_router(hospital.router)
api_router.include_router(hms.router)
api_router.include_router(admin_doctors.router)
api_router.include_router(admin_patients.router)
