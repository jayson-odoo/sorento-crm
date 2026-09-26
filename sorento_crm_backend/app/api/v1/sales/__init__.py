"""Routes of the `sales` module (PLAN-retail-sales-reports-26sep, S1): the chatbot's sales
analysis. The two report SCREENS are the reports kernel's own routes (`/reports/{key}`)."""
from fastapi import APIRouter

from app.api.v1.sales import analysis

router = APIRouter()
router.include_router(analysis.router)
