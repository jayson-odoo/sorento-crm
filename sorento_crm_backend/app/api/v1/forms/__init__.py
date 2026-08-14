"""Forms management API routes."""
from fastapi import APIRouter
from app.api.v1.forms import forms, revision_configs

router = APIRouter()

router.include_router(forms.router, prefix="/forms", tags=["forms"])
# Portal revision policy, one row per portal submission type. Mounted at the
# router root so it lands on /api/v1/forms-management/revision-configs, which is
# what the settings page calls.
router.include_router(revision_configs.router, tags=["forms"])
