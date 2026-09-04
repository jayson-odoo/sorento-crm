"""Master data ingest and current-state reads for the ESB (Phase C).

Two directions on one surface:

* **Ingest** (`POST /external/ingest/{entity}`) - the ESB pushes canonical
  masters in. Always `200` with a per-record verdict, even when records fail:
  a batch is not a transaction (AC-AC-15), so a non-2xx would tell the ESB
  nothing about which of 10,000 records landed.

* **Delete** (`POST /external/ingest/{entity}/deletions`) - the ESB says a
  record is gone upstream. A record something still points at is taken out of
  use rather than removed; see ``deletion_service``.

* **Read** (`POST /external/read/{entity}`) - the ESB fetches current values to
  render before/after diffs for human approval (AC-AC-19). POST rather than GET
  because the request carries a batch of source references, and a few hundred
  of them do not belong in a query string.

Permissions reuse the existing per-entity slugs. Writing a warehouse through
the ESB is the same act as writing one through the UI, so it is the same
permission -- an integration that may not edit warehouses must not gain the
ability by coming through a different door.

Both calls are **company-anchored** (group A1): a top-level ``companyCode``, or
the calling integration's binding, names the one company the request writes,
adopts and reads inside. The guard runs after the body has parsed and after the
batch cap, because a caller cannot supply an anchor for a request that never
parsed, and telling it about the anchor before telling it the batch is too big
would cost it a second round trip. See ``company_anchor.py``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.api.v1.external.company_anchor import resolve_company_anchor
from app.api.v1.external.permissions import require_external_permission_for_path
from app.dependencies import get_external_api_user
from app.database import get_db
from app.schemas.common import MAX_PAGE_LIMIT
from app.services.error_handler import AppException
from app.services.deletion_service import DeletionService
from app.services.document_ingest_service import (
    DOCUMENT_ENTITIES,
    DocumentIngestService,
    DocumentReadService,
)
from app.services.master_ingest_service import (
    ENTITY_SPECS,
    MasterIngestService,
    UnsupportedIngestEntity,
)
from app.services.master_read_service import MasterReadService
from app.services.shipping_order_ingest_service import (
    SHIPPING_ORDER_ENTITIES,
    ShippingOrderIngestService,
    ShippingOrderReadService,
)

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
    "sales_agents": "master_data.sales_agents.edit",
    # Documents (group A3). Pushing an order through the ESB is the same act as
    # editing one on the SCM screen, so it is the same slug.
    "sales_orders": "scm.sales_orders.edit",
    "purchase_orders": "scm.purchase_orders.edit",
    # Shipping orders (S3) - no header table, but the same slug shape.
    "shipping_orders": "scm.shipping_orders.edit",
}
READ_PERMISSIONS = {
    "product_categories": "master_data.product_categories.view",
    "units_of_measure": "master_data.units_of_measure.view",
    "warehouses": "inventory.warehouses.view",
    "suppliers": "procurement.suppliers.view",
    "customers": "order_management.customers.view",
    "products": "master_data.products.view",
    "sales_agents": "master_data.sales_agents.view",
    "sales_orders": "scm.sales_orders.view",
    "purchase_orders": "scm.purchase_orders.view",
    "shipping_orders": "scm.shipping_orders.view",
}
# Deleting through the ESB is its own act, so it takes its own slug on top of the
# ingest guard the router already carries (group A4 mounts the route). Declared
# here rather than there because this is the one file that says what an entity
# name means on this surface, and three maps that can disagree about the entity
# list is how a hole opens.
DELETE_PERMISSIONS = {
    "product_categories": "master_data.product_categories.delete",
    "units_of_measure": "master_data.units_of_measure.delete",
    "warehouses": "inventory.warehouses.delete",
    "suppliers": "procurement.suppliers.delete",
    "customers": "order_management.customers.delete",
    "products": "master_data.products.delete",
    "sales_agents": "master_data.sales_agents.delete",
    "sales_orders": "scm.sales_orders.delete",
    "purchase_orders": "scm.purchase_orders.delete",
    "shipping_orders": "scm.shipping_orders.delete",
}

# A batch cap the ESB can design against. Exceeding it errors rather than
# silently truncating (AC-AC-20): a partial response the caller believes is
# complete is worse than a refusal.
MAX_BATCH = 1000


# Masters, documents and shipping orders on one surface. The set is built from
# every registry rather than written out, so an entity that exists in none of
# them cannot become reachable here by being spelled correctly in this file.
SUPPORTED_ENTITIES = set(ENTITY_SPECS) | set(DOCUMENT_ENTITIES) | set(SHIPPING_ORDER_ENTITIES)

# Bumped whenever the wire shape of an entity changes in a way the ESB must gate
# on (a new required field, a changed enum). Read by `GET /external/contract`
# (D8) so the ESB can check compatibility without trial-and-error against this
# router.
CONTRACT_VERSION = 2


def _entity(entity: str) -> str:
    if entity not in SUPPORTED_ENTITIES:
        raise AppException(
            status_code=404,
            message=(
                f"Unsupported entity '{entity}'. "
                f"Expected one of: {', '.join(sorted(SUPPORTED_ENTITIES))}"
            ),
            code="UNKNOWN_ENTITY",
        )
    return entity


@ingest_router.post("/{entity}")
async def ingest_masters(
    entity: str = Path(...),
    payload: dict = Body(...),
    dry_run: bool = Query(
        False,
        description=(
            "Preview only. Resolves every record exactly as a real ingest would, "
            "adoption matching included, reports the outcome each record would "
            "receive plus a field-level diff for records that would overwrite an "
            "existing row, then writes nothing."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_external_api_user),
):
    """Accept a batch of canonical master records.

    Returns `200` with a per-record verdict -- created, updated, failed or
    retryable -- so the ESB can quarantine per record and re-drain the
    retryables without a human deciding what a 4xx meant.

    With `?dry_run=true` the same work happens and is then rolled back, so an
    operator can see what a sync would overwrite before it does. Defaults to
    false: an existing caller that does not know about the parameter must keep
    getting a real ingest.
    """
    entity = _entity(entity)

    records = payload.get("records")
    if not isinstance(records, list):
        raise AppException(
            status_code=422,
            message="Body must contain a 'records' array",
            code="INVALID_BODY",
        )
    if len(records) > MAX_BATCH:
        raise AppException(
            status_code=413,
            message=(
                f"Batch of {len(records)} exceeds the maximum of {MAX_BATCH}. "
                "Split it; the response is never silently truncated."
            ),
            code="BATCH_TOO_LARGE",
        )

    company_id = resolve_company_anchor(db, payload, current_user)

    # One endpoint, three services. A document owns its lines and points at
    # five masters, and a shipping order owns lines with no header at all -
    # both different write shapes from a master row - but the envelope, the
    # batch cap, the verdicts and the dry-run rollback are the caller's
    # contract and must not fork, so the branch is here and nowhere else.
    if entity in SHIPPING_ORDER_ENTITIES:
        ingester = ShippingOrderIngestService
    elif entity in DOCUMENT_ENTITIES:
        ingester = DocumentIngestService
    else:
        ingester = MasterIngestService
    service = ingester(
        db,
        integration_id=current_user.get("integration_id"),
        company_id=company_id,
    )
    try:
        result = service.ingest(entity, records, dry_run=dry_run)
    except UnsupportedIngestEntity as exc:
        raise AppException(status_code=404, message=str(exc), code="UNKNOWN_ENTITY")

    if dry_run:
        # The service has already rolled back; this is the second of two locks
        # on the same door. A preview that writes is the one outcome this
        # endpoint must never produce, so neither layer relies on the other.
        db.rollback()
    else:
        # Committed once for the batch. Each record already succeeded or rolled
        # back inside its own savepoint, so this persists exactly the good ones.
        db.commit()

    logger.info(
        "ingest.batch entity=%s integration=%s company=%s dry_run=%s "
        "created=%d updated=%d failed=%d retryable=%d",
        entity,
        current_user.get("integration_name"),
        company_id,
        dry_run,
        result.created,
        result.updated,
        result.failed,
        result.retryable,
    )
    return result.as_dict()


@ingest_router.post(
    "/{entity}/deletions",
    # TWO guards, both entity-resolved. The router already carries the ingest
    # guard (`.edit`), and this adds `.delete` on top: removing a record through
    # the ESB is a different act from syncing one, and an integration trusted to
    # keep masters up to date must not gain the ability to empty them.
    dependencies=[Depends(require_external_permission_for_path(DELETE_PERMISSIONS))],
)
async def delete_records(
    entity: str = Path(...),
    payload: dict = Body(...),
    dry_run: bool = Query(
        False,
        description=(
            "Preview only. Resolves every reference, probes its dependents and "
            "reports the verdict each one would receive - deleted, deactivated, "
            "not found or failed - then writes nothing."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_external_api_user),
):
    """Delete a batch of records the source system says are gone (group A4).

    Always `200` with a per-reference verdict, for the reason the ingest is: a
    batch is not a transaction, and a non-2xx would tell the caller nothing about
    which of its references landed.

    A record something still points at is NOT removed - it is taken out of use
    (`deactivated`) and keeps its reference. See ``deletion_service`` for why
    that is not left to the database to decide.
    """
    entity = _entity(entity)

    source_refs = payload.get("source_refs")
    if not isinstance(source_refs, list):
        raise AppException(
            status_code=422,
            message="Body must contain a 'source_refs' array",
            code="INVALID_BODY",
        )
    if len(source_refs) > MAX_BATCH:
        raise AppException(
            status_code=413,
            message=(
                f"Batch of {len(source_refs)} exceeds the maximum of {MAX_BATCH}. "
                "Split it; the response is never silently truncated."
            ),
            code="BATCH_TOO_LARGE",
        )

    company_id = resolve_company_anchor(db, payload, current_user)

    service = DeletionService(
        db,
        integration_id=current_user.get("integration_id"),
        company_id=company_id,
    )
    try:
        result = service.delete(entity, source_refs, dry_run=dry_run)
    except UnsupportedIngestEntity as exc:
        raise AppException(status_code=404, message=str(exc), code="UNKNOWN_ENTITY")

    if dry_run:
        # The service has already rolled back; this is the second of two locks on
        # the same door, exactly as on the ingest.
        db.rollback()
    else:
        db.commit()

    summary = result.as_dict()["summary"]
    logger.info(
        "deletion.batch entity=%s integration=%s company=%s dry_run=%s "
        "deleted=%d deactivated=%d not_found=%d failed=%d",
        entity,
        current_user.get("integration_name"),
        company_id,
        dry_run,
        summary["deleted"],
        summary["deactivated"],
        summary["not_found"],
        summary["failed"],
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
        raise AppException(
            status_code=422,
            message="Body must contain a 'source_refs' array",
            code="INVALID_BODY",
        )
    if len(source_refs) > MAX_BATCH:
        raise AppException(
            status_code=413,
            message=(
                f"Requested {len(source_refs)} references, above the maximum of {MAX_BATCH}. "
                "Page the request; the response is never silently truncated."
            ),
            code="BATCH_TOO_LARGE",
        )

    company_id = resolve_company_anchor(db, payload, current_user)

    if entity in SHIPPING_ORDER_ENTITIES:
        reader = ShippingOrderReadService
    elif entity in DOCUMENT_ENTITIES:
        reader = DocumentReadService
    else:
        reader = MasterReadService
    return reader(db, company_id=company_id).current_state(entity, source_refs)
