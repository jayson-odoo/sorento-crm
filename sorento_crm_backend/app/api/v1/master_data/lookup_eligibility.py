"""Eligibility listing endpoint - returns registered (table, column) pairs for the FE binding picker."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.lookup import LookupEligibilityResponse
from app.services.lookup_eligibility import all_eligibility

router = APIRouter()


@router.get("/", response_model=list[LookupEligibilityResponse])
async def list_eligibility(
    available: bool = Query(False),
    current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
    db: Session = Depends(get_db),
):
    """Return all registered (table, column) pairs.

    With ``?available=true`` only columns not yet bound to any LookupSet are returned,
    and ``is_bound`` is set to ``False`` for all returned rows (already-bound are excluded).
    Without the flag every registered column is returned; ``is_bound`` reflects whether a
    LookupBinding row exists for that pair.
    """
    rows = all_eligibility()
    bound: set[tuple[str, str]] = set()
    if available:
        from app.models.lookup import LookupBinding
        for b in db.query(LookupBinding).all():
            bound.add((b.table_name, b.column_name))
    out = []
    for e in rows:
        is_bound = (e.table_name, e.column_name) in bound
        if available and is_bound:
            continue
        out.append({
            "table_name": e.table_name,
            "column_name": e.column_name,
            "table_label": e.table_label,
            "column_label": e.column_label,
            "data_type": e.data_type,
            "nullable": e.nullable,
            "is_bound": is_bound,
        })
    return out
