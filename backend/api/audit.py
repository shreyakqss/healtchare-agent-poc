# Placeholder for audit API routes.
from fastapi import APIRouter

router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    responses={404: {"description": "Not found"}},  
)