"""Warranty configuration surface - `/api/v1/warranty-management/*` (S7b).

One area, three tabs: Policies (with their Terms), Kinds and Rules. It lives under
its OWN module key rather than under `/master-data-management`, whose prefix
`lib/route-module-map.ts` gates on the PRODUCT module - a warranty editor placed
there survives uninstalling warranty and disappears when the product module goes,
which is exactly backwards (AC-P0a).
"""
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.warranty import kind_rules, kinds, policies, terms
from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.warranty_config import DefectTypeOption
from app.services.warranty_config_service import WarrantyConfigService

router = APIRouter()


@router.get("/defect-types", response_model=List[DefectTypeOption])
async def list_warranty_defect_types(
    limit: int = Query(500, ge=1, le=1000),
    current_user: dict = Depends(require_permission_with_api_key("warranty.policies.view")),
    db: Session = Depends(get_db),
):
    """The picker behind a Term's `covered_defect_type_ids` (AC-P18).

    Load-bearing rather than convenient: the column is a `uuid[]` of
    `lookup_options.id`, and the existing `GET /api/v1/lookup/{set_key}/options`
    returns `value` + `label` and never the id - so without this the Term editor
    cannot write a defect scope at all. Guarded by the policies slug, because Terms
    ride it.
    """
    return WarrantyConfigService(db).list_defect_types(limit=limit)


router.include_router(policies.router, prefix="/policies", tags=["warranty-policies"])
# Terms are NESTED under their policy (AC-P9), so they share the policies prefix.
router.include_router(terms.router, prefix="/policies", tags=["warranty-terms"])
router.include_router(kinds.router, prefix="/kinds", tags=["warranty-kinds"])
router.include_router(kind_rules.router, prefix="/kind-rules", tags=["warranty-kind-rules"])
