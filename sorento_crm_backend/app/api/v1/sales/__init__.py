"""Sales module API routes, mounted at `/sales` behind the `sales` module guard.

Sales teams (#1260, plan 3.7) and the chatbot's sales analysis
(PLAN-retail-sales-reports-26sep S1). The two report SCREENS are the reports kernel's own
routes (`/reports/{key}`)."""
from fastapi import APIRouter

from app.api.v1.sales import analysis, teams

router = APIRouter()
router.include_router(teams.router, prefix="/teams", tags=["sales-teams"])
router.include_router(analysis.router)
