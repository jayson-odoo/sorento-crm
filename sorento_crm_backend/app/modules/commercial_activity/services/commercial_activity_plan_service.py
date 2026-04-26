"""Compatibility shim — service moved to app.modules.commercial_activity.services.plan_service."""
from app.modules.commercial_activity.services.plan_service import (  # noqa: F401
    CommercialActivityPlanError,
    CommercialActivityPlanService,
)
