# Placeholder for review API routes.
from fastapi import APIRouter

router = APIRouter(
    prefix="/review",
    tags=["review"],
    responses={404: {"description": "Not found"}},
)