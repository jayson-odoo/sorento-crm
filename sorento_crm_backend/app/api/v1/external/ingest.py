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

import json
import logging
from typing import Optional

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
from app.services import planning_change_service
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.scm import plan_exception_service, reorder_run_service
from app.services.scm.outstanding_diff import diff_lines
from app.services.scm.outstanding_import_service import supersede_crm_raised_pos
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

# Fix round 6 (live need): the batch summary line names how many records
# failed or stayed retryable, but not WHICH ones - so a record retryable
# across several pushes had no server-side trail at all beyond that count.
# Capped so one pathological batch (every record failing the same way)
# cannot turn this into its own flood.
MAX_RECORD_LOG_LINES = 50
# Error VALUES are free text (a resolver's own message, or a raw exception
# string on the sanitized paths) - capped so one long one cannot blow out a
# log line; the KEYS (field names) are never truncated, they are the whole
# point of a machine-readable error.
_ERROR_VALUE_LOG_LIMIT = 200


def _log_record_outcomes(
    entity: str, integration_name, company_id: str, result
) -> None:
    """One INFO line per FAILED/RETRYABLE record, capped at `MAX_RECORD_LOG_LINES`.

    Never logs a payload field beyond `source_ref` and the record's own
    `errors` dict - no line bodies, no customer/agent/product names, nothing
    that was actually sent. Skipped entirely for a dry run: a preview never
    happened as far as the operational log is concerned, the same reason the
    batch summary line's own counts are for the real run only in spirit
    (dry-run callers read the response body, not the server log).
    """
    logged = 0
    suppressed = 0
    for record in result.records:
        if record.outcome.value not in ("failed", "retryable"):
            continue
        if logged >= MAX_RECORD_LOG_LINES:
            suppressed += 1
            continue
        errors = {
            field: (reason[:_ERROR_VALUE_LOG_LIMIT] if isinstance(reason, str) else reason)
            for field, reason in record.errors.items()
        }
        logger.info(
            "ingest.record entity=%s integration=%s company=%s source_ref=%s "
            "outcome=%s errors=%s",
            entity,
            integration_name,
            company_id,
            record.source_ref,
            record.outcome.value,
            json.dumps(errors),
        )
        logged += 1
    if suppressed:
        logger.info(
            "ingest.record_overflow entity=%s suppressed=%d", entity, suppressed
        )


# Masters, documents and shipping orders on one surface. The set is built from
# every registry rather than written out, so an entity that exists in none of
# them cannot become reachable here by being spelled correctly in this file.
SUPPORTED_ENTITIES = set(ENTITY_SPECS) | set(DOCUMENT_ENTITIES) | set(SHIPPING_ORDER_ENTITIES)

# Bumped whenever the wire shape of an entity changes in a way the ESB must gate
# on (a new required field, a changed enum). Read by `GET /external/contract`
# (D8) so the ESB can check compatibility without trial-and-error against this
# router. A STRING (S4, ingest-parity-standardisation D-final): "2.1" is a
# point release of the same major contract, and a bare int can never express
# that - the ESB's own gate compares it as an opaque value, never arithmetic.
CONTRACT_VERSION = "2.1"


def _run_document_hooks(
    db: Session, entity: str, service, *, actor: Optional[str]
) -> None:
    """D7/S5 (plan section 2.6): post-write reactions, non-dry only.

    Runs AFTER the batch's own `db.commit()` - every hook here reacts to a
    write that has already landed, never to one this call itself decides.
    Each reaction is its OWN try/except -> `logger.warning` and its OWN
    commit: a failed reaction must cost the operator only that reaction (the
    next push produces it again), never the ingest that already succeeded,
    and one reaction's failure must not roll back a sibling reaction that
    already committed.

    `actor` (N1 review fix) is the calling principal's own user id - the
    integration's `act_as_user_id`, resolved once by `get_external_api_user`
    - threaded through to whichever hook records who/what caused the
    reaction, the same attribution an interactive user's action gets.

    `shipping_orders` reacts here too (security review, blocker 2): the
    forward-match sweep used to run INSIDE `ShippingOrderIngestService
    .ingest()` itself, before this route's own `db.commit()` -
    `forward_match_grn_lines_for_spo` commits on success and rolls back on
    failure, so one exception mid-batch discarded every not-yet-committed
    record of the batch while the route still answered 200. Moved here so it
    runs against a batch that has already landed, same as every other hook.
    """
    if entity == "sales_orders":
        _run_plan_exception_hook(db, service, actor=actor)
        _run_planning_change_hook(db, service, actor=actor)
    elif entity == "purchase_orders":
        _run_supersede_and_relink_hooks(db, service, actor=actor)
    elif entity == "shipping_orders":
        _run_shipping_order_forward_match_hook(db, service, actor=actor)


def _run_plan_exception_hook(db: Session, service, *, actor: Optional[str]) -> None:
    """AC-V5-1: a before/after plan-exception batch over this push's products.

    `before` is `service.plan_exception_before` - captured INSIDE the service,
    per product, the first time this batch touched it and before anything was
    written for it (mirrors `outstanding_import_service.apply`'s own
    `before_positions`, taken while the old position is still the one in the
    database). `after` is read here, post-commit, over every product the
    batch actually touched. Called through the MODULE attribute
    (`plan_exception_service.generate_batch`, not a bound import) so a caller
    that monkeypatches the module - the ESB's own smoke tests, this slice's
    own failure-is-logged test - sees the same function this route runs.
    """
    if not service.touched_product_ids or not service.so_numbers:
        return
    try:
        after = plan_exception_service.snapshot(db, list(service.touched_product_ids))
        current = reorder_run_service.today_or_latest_run(db)
        # A run still being built contradicts nothing yet (mirrors the upload's
        # own guard) - only a completed plan can be contradicted.
        if current and current["row"].get("status") != "completed":
            current = None
        plan_exception_service.generate_batch(
            db,
            run_id=str(current["row"]["id"]) if current else None,
            before=service.plan_exception_before,
            after=after,
            # The ingest's own count of changed documents, the same role
            # `diff.counts` plays for the upload (AC-D2b's rule, carried
            # through unchanged rather than recounted from the exceptions).
            delta_count=len(service.written_header_ids),
            source_documents=sorted(service.so_numbers),
            actor=actor,
        )
        db.commit()
    except Exception:  # noqa: BLE001 - best-effort, the ingest already succeeded
        db.rollback()
        logger.warning("ingest.plan_exception_hook_failed", exc_info=True)


def _run_planning_change_hook(db: Session, service, *, actor: Optional[str]) -> None:
    """D10 (S2, BL-058): the ESB's own `planning_change_batches` row, built
    from the SAME before/after line picture `outstanding_import_service
    .apply()` diffs after its own upload - `service.so_diff_before`/
    `so_diff_after`, gathered per record in `DocumentIngestService._apply`
    (`Diff` docstring: "the documents named in the extract ARE the scope",
    which is exactly the batch this push named). Called through the MODULE
    attribute (`planning_change_service.build_batch`), same reason as
    `plan_exception_service.generate_batch` above - a caller monkeypatching
    the module sees this call.
    """
    if not service.so_diff_before and not service.so_diff_after:
        return
    try:
        diff = diff_lines(service.so_diff_before, service.so_diff_after)
        applied_line_ids: dict[int, str] = {}
        for change in diff.changes:
            line_id = (change.after.row_ref if change.after else None) or (
                change.before.row_ref if change.before else None
            )
            if line_id:
                applied_line_ids[id(change)] = line_id
        planning_change_service.build_batch(
            db,
            diff,
            applied_line_ids=applied_line_ids,
            order_ids=dict(service.so_header_id_by_number),
            actor=actor,
            import_job_id=None,
            file_name=None,
        )
        db.commit()
    except Exception:  # noqa: BLE001 - best-effort, the ingest already succeeded
        db.rollback()
        logger.warning("ingest.planning_change_hook_failed", exc_info=True)


def _run_supersede_and_relink_hooks(db: Session, service, *, actor: Optional[str]) -> None:
    """AC-V5-2: retire CRM-raised POs this push confirms, then relink placements.

    Two hooks, two try/except blocks, two commits - not one wrapping both -
    so a relink failure can never undo a supersession that already landed,
    and vice versa.
    """
    if service.po_supersede_triples:
        try:
            supersede_crm_raised_pos(db, service.po_supersede_triples)
            db.commit()
        except Exception:  # noqa: BLE001 - best-effort, the ingest already succeeded
            db.rollback()
            logger.warning("ingest.supersede_crm_raised_pos_failed", exc_info=True)

    if service.written_header_ids:
        try:
            with db.begin_nested():
                ProjectOrderInquiryService(db).relink_to_matching_lines(
                    list(service.written_header_ids),
                    actor_user_id=actor,
                    trigger="autocount_ingest",
                )
            db.commit()
        except Exception:  # noqa: BLE001 - best-effort, the ingest already succeeded
            db.rollback()
            logger.warning("ingest.relink_to_matching_lines_failed", exc_info=True)


def _run_shipping_order_forward_match_hook(
    db: Session, service, *, actor: Optional[str]
) -> None:
    """D7 (S3), moved here by the security review (blocker 2): GRN
    forward-match, once per SPO number this batch touched, AFTER the batch's
    own commit rather than inside `ShippingOrderIngestService.ingest()`.

    `forward_match_grn_lines_for_spo_best_effort` is itself already a
    best-effort wrapper (catches, rolls back its OWN transaction, warns), so
    the outer try/except here is defensive symmetry with the SO/PO hooks
    above rather than a defect it is patching over - it should never actually
    fire. Called through the MODULE attribute so a caller monkeypatching
    `grn_spo_matching` sees this call, same reason the SO/PO hooks call
    `plan_exception_service`/`planning_change_service` that way.
    """
    if not service.spo_numbers_touched:
        return
    import app.services.grn_spo_matching as grn_spo_matching

    try:
        for spo_number in sorted(service.spo_numbers_touched):
            grn_spo_matching.forward_match_grn_lines_for_spo_best_effort(
                db, spo_number, company_id=service.company_id
            )
        db.commit()
    except Exception:  # noqa: BLE001 - best-effort, the ingest already succeeded
        db.rollback()
        logger.warning("ingest.shipping_order_forward_match_hook_failed", exc_info=True)


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
        # D7/S5: post-write hooks, non-dry only (AC-V5-4). `MasterIngestService`
        # carries none of the attributes these read, so only a
        # `DocumentIngestService` or `ShippingOrderIngestService` batch
        # reaches this.
        if isinstance(service, (DocumentIngestService, ShippingOrderIngestService)):
            _run_document_hooks(
                db, entity, service, actor=current_user.get("id")
            )

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
    if not dry_run:
        _log_record_outcomes(
            entity, current_user.get("integration_name"), company_id, result
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
