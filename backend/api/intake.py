# Placeholder for intake API routes.
from fastapi import APIRouter

router = APIRouter(
    prefix="/intake",
    tags=["intake"],
    responses={404: {"description": "Not found"}},
)