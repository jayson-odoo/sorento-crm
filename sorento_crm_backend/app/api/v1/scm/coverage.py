"""SCM S3 - the Coverage Timeline endpoint (UAC Group B).

``GET /api/v1/scm/coverage?product_code=&pool_code=&floor=`` - one read, gated on
``scm.dashboard.view``, mirroring ``explainer.py``. Nothing here writes, and the timeline is
computed per request and never stored (AC-B6).

**Addressed by human codes, not ids, deliberately.** No UUID may reach the UI (AC-B2), so a
screen that only ever holds a product code and a warehouse code cannot be asked to send
ids: it would have to fetch one first, and that id would then be one refresh away from
being rendered. The route resolves both codes itself and the response carries neither.

``pool_code`` accepts EITHER a pool code or ANY location code that points at a pool. Pool
membership is a stored pointer per location (AC-B1a) and ``pool_for_location`` resolves a
location with no pointer to itself, so the results grid can pass the recommendation row's
own bin (``BRW-BB``) and the netting still happens over the shared pool (``BRW``). A route
that demanded a true pool code would 404 on every per-warehouse row on that grid. The 404
here is therefore "no location with this code", not "not a pool".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.models.inventory import Warehouse
from app.models.product import Product
from app.schemas.scm_coverage import CoverageTimelineResult
from app.services.error_handler import AppException
from app.services.scm.coverage_service import Coverage, CoverageService

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")


def _payload(cov: Coverage) -> dict:
    """Flatten ``Coverage`` onto the wire, dropping every identifier.

    Written by hand rather than by dumping the dataclass, because ``Coverage`` carries
    ``product_id`` and ``pool_id`` for the service's own use and an automatic dump would
    leak both the moment somebody adds a field.
    """
    timeline = cov.timeline
    return {
        "product_code": cov.product_code,
        "product_name": cov.product_name,
        "pool_code": cov.pool_code,
        "locations": list(cov.locations),
        "floor": cov.floor,
        "opening_balance": cov.opening_balance,
        "rows": [
            {
                "event": {
                    "at": row.event.at,
                    "qty": row.event.qty,
                    "kind": row.event.kind,
                    "ref": row.event.ref,
                    "label": row.event.label,
                    "location": row.event.location,
                    "supply_stage": row.event.supply_stage,
                },
                "balance": row.balance,
            }
            for row in timeline.rows
        ],
        "closing_balance": timeline.closing_balance,
        "shortfall": (
            None
            if timeline.shortfall is None
            else {
                "at": timeline.shortfall.at,
                "qty": timeline.shortfall.qty,
                "ref": timeline.shortfall.ref,
                "label": timeline.shortfall.label,
            }
        ),
        "peak_deficit": timeline.peak_deficit,
        "availability": {
            "own": cov.availability.own,
            "pool": cov.availability.pool,
            "other": cov.availability.other,
            "pool_location": cov.availability.pool_location,
            "other_locations": list(cov.availability.other_locations),
        },
        "allocations": [
            {
                "source_type": a.source_type,
                "qty": a.qty,
                "location": a.location,
                "needs_claim": a.needs_claim,
            }
            for a in cov.allocations
        ],
        "buy_qty": cov.buy_qty,
        "use_stock": cov.use_stock,
        "undated_demand": [
            {
                "so_number": u.so_number,
                "item_code": u.item_code,
                "qty": u.qty,
                "location": u.location,
            }
            for u in cov.undated_demand
        ],
        "transfer_proposals": [
            {
                "proposal_ref": p.proposal_ref,
                "from_pool_code": p.from_pool_code,
                "available_qty": p.available_qty,
                "qty": p.qty,
                "transfer_cost": p.transfer_cost,
                "lead_time_days": p.lead_time_days,
                "arrives_at": p.arrives_at,
            }
            for p in cov.transfer_proposals
        ],
        "horizon_months": cov.horizon_months,
        "horizon_end": cov.horizon_end,
        "excluded_event_count": cov.excluded_event_count,
        "unattributed_in_transit_qty": cov.unattributed_in_transit_qty,
        "unplaceable_demand_qty": cov.unplaceable_demand_qty,
        "unplaceable_on_order_qty": cov.unplaceable_on_order_qty,
        # Naive Malaysia wall-clock. Serialised as a string on purpose: an offset-aware
        # timestamp is re-normalised to UTC by downstream consumers and displays eight
        # hours out, which makes a report that is seconds old look like the middle of the
        # night.
        "computed_at": cov.computed_at.isoformat(),
    }


@router.get("/coverage", response_model=CoverageTimelineResult)
def get_coverage(
    product_code: str = Query(
        ...,
        min_length=1,
        description="Product code, e.g. SRTWT7408. Required: defaulting it would answer a "
        "question nobody asked, and the answer would look like a real position.",
    ),
    pool_code: str = Query(
        ...,
        min_length=1,
        description="A pool code, or ANY location code pointing at one (e.g. BRW-BB). The "
        "netting always happens over the resolved pool.",
    ),
    floor: float = Query(
        0.0,
        description="The level the balance must not fall below. 0 for project demand, the "
        "reorder point for a continuous SKU.",
    ),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    product = (
        db.query(Product).filter(Product.product_code == product_code).one_or_none()
    )
    if product is None:
        # Naming WHICH of the two codes failed: told only "not found", the planner's only
        # way forward is to try both.
        raise AppException(
            status_code=404,
            message=f"No product found with code '{product_code}'.",
            code="NOT_FOUND",
        )

    location = (
        db.query(Warehouse).filter(Warehouse.warehouse_code == pool_code).one_or_none()
    )
    if location is None:
        raise AppException(
            status_code=404,
            message=(
                f"No location found with code '{pool_code}', so no fulfilment pool could "
                "be resolved."
            ),
            code="NOT_FOUND",
        )

    service = CoverageService(db)
    pool_id = service.pool_for_location(location.id)
    coverage = service.coverage_for(
        product.id,
        pool_id=pool_id,
        floor=floor,
        own_warehouse_id=location.id,
    )
    return _payload(coverage)
