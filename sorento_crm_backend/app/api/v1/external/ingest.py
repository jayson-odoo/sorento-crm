"""Master data ingest and current-state reads for the ESB (Phase C).

Two directions on one surface:

* **Ingest** (`POST /external/ingest/{entity}`) — the ESB pushes canonical
  masters in. Always `200` with a per-record verdict, even when records fail:
  a batch is not a transaction (AC-AC-15), so a non-2xx would tell the ESB
  nothing about which of 10,000 records landed.

* **Read** (`POST /external/read/{entity}`) — the ESB fetches current values to
  render before/after diffs for human approval (AC-AC-19). POST rather than GET
  because the request carries a batch of source references, and a few hundred
  of them do not belong in a query string.

Permissions reuse the existing per-entity slugs. Writing a warehouse through
the ESB is the same act as writing one through the UI, so it is the same
permission -- an integration that may not edit warehouses must not gain the
ability by coming through a different door.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, Path, status
from sqlalchemy.orm import Session

from app.api.v1.external.permissions import require_external_permission_for_path
from app.dependencies import get_external_api_user
from app.database import get_db
from app.schemas.common import MAX_PAGE_LIMIT
from app.services.error_handler import AppException
from app.services.master_ingest_service import (
    ENTITY_SPECS,
    MasterIngestService,
    UnsupportedIngestEntity,
)
from app.services.master_read_service import MasterReadService

ingest_router = APIRouter()
read_router = APIRouter()
logger = logging.getLogger(__name__)

# Per-entity permissions. Ingest writes, so it takes the edit slug; reads take
# view. Deliberately the same slugs the UI uses.
INGEST_PERMISSIONS = {
    "product_categories": "master_data.product_categories.edit",
    "units_of_measure": "master_data.units_of_measure.edit",
    "warehouses": "inventory.warehouses.edit",
    "suppliers": "procurement.suppliers.edit",
    "customers": "order_management.customers.edit",
    "products": "master_data.products.edit",
}
READ_PERMISSIONS = {
    "product_categories": "master_data.product_categories.view",
    "units_of_measure": "master_data.units_of_measure.view",
    "warehouses": "inventory.warehouses.view",
    "suppliers": "procurement.suppliers.view",
    "customers": "order_management.customers.view",
    "products": "master_data.products.view",
}

# A batch cap the ESB can design against. Exceeding it errors rather than
# silently truncating (AC-AC-20): a partial response the caller believes is
# complete is worse than a refusal.
MAX_BATCH = 1000


def _entity(entity: str) -> str:
    if entity not in ENTITY_SPECS:
        raise AppException(
            f"Unsupported entity '{entity}'. Expected one of: {', '.join(sorted(ENTITY_SPECS))}",
            status_code=404,
        )
    return entity


@ingest_router.post("/{entity}")
async def ingest_masters(
    entity: str = Path(...),
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_external_api_user),
):
    """Accept a batch of canonical master records.

    Returns `200` with a per-record verdict -- created, updated, failed or
    retryable -- so the ESB can quarantine per record and re-drain the
    retryables without a human deciding what a 4xx meant.
    """
    entity = _entity(entity)

    records = payload.get("records")
    if not isinstance(records, list):
        raise AppException("Body must contain a 'records' array", status_code=422)
    if len(records) > MAX_BATCH:
        raise AppException(
            f"Batch of {len(records)} exceeds the maximum of {MAX_BATCH}. "
            "Split it; the response is never silently truncated.",
            status_code=413,
        )

    service = MasterIngestService(db, integration_id=current_user.get("integration_id"))
    try:
        result = service.ingest(entity, records)
    except UnsupportedIngestEntity as exc:
        raise AppException(str(exc), status_code=404)

    # Committed once for the batch. Each record already succeeded or rolled
    # back inside its own savepoint, so this persists exactly the good ones.
    db.commit()

    logger.info(
        "ingest.batch entity=%s integration=%s created=%d updated=%d failed=%d retryable=%d",
        entity,
        current_user.get("integration_name"),
        result.created,
        result.updated,
        result.failed,
        result.retryable,
    )
    return result.as_dict()


@read_router.post("/{entity}")
async def read_current_state(
    entity: str = Path(...),
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_external_api_user),
):
    """Current canonical values for a batch of source references (AC-AC-19).

    Batched by design: rendering a diff over a few hundred records must not
    become a few hundred round trips.
    """
    entity = _entity(entity)

    source_refs = payload.get("source_refs")
    if not isinstance(source_refs, list):
        raise AppException("Body must contain a 'source_refs' array", status_code=422)
    if len(source_refs) > MAX_BATCH:
        raise AppException(
            f"Requested {len(source_refs)} references, above the maximum of {MAX_BATCH}. "
            "Page the request; the response is never silently truncated.",
            status_code=413,
        )

    return MasterReadService(db).current_state(entity, source_refs)
