"""Warranty configuration routes (after-sales P2): policies, terms, kinds and kind rules."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.after_sales.warranty import kind_rules, kinds, policies, terms
from app.api.v1.after_sales.warranty.access import can_read
from app.database import get_db
from app.services import warranty_config_service as svc

router = APIRouter()


@router.get("/defect-types", tags=["warranty-defect-types"])
def list_defect_types(current_user: dict = Depends(can_read), db: Session = Depends(get_db)):
    return svc.list_defect_types(db)


router.include_router(policies.router, prefix="/policies", tags=["warranty-policies"])
router.include_router(terms.router, prefix="/terms", tags=["warranty-terms"])
router.include_router(kinds.router, prefix="/kinds", tags=["warranty-kinds"])
router.include_router(kind_rules.router, prefix="/kind-rules", tags=["warranty-kind-rules"])
