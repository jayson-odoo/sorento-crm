"""Forms management API routes."""
from fastapi import APIRouter
from app.api.v1.forms import forms

router = APIRouter()

router.include_router(forms.router, prefix="/forms", tags=["forms"])
