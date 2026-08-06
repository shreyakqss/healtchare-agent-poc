# Placeholder for cases API routes.
from fastapi import APIRouter

router = APIRouter(
    prefix="/cases",
    tags=["cases"],
    responses={404: {"description": "Not found"}},
)