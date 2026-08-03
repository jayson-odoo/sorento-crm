"""Consumer ledger read surfaces."""
from fastapi import APIRouter

from app.api.v1.consumers import consumers

router = APIRouter()
router.include_router(consumers.router, tags=["consumers"])
