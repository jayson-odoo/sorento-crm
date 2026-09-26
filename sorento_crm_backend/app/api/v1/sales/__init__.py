"""Sales module API routes, mounted at `/sales` behind the `sales` module guard (plan 3.7)."""
from fastapi import APIRouter

from app.api.v1.sales import targets, teams

router = APIRouter()
router.include_router(teams.router, prefix="/teams", tags=["sales-teams"])
router.include_router(targets.router, prefix="/targets", tags=["sales-targets"])
