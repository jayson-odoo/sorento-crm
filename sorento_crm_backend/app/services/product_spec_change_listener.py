"""Keep derived specs in step with the catalog.

A product whose description, code or dimensions change has stale specs until something
re-derives it, and a stale spec is worse than a missing one: it ranks a product on a
value the catalog no longer states. So the re-derive is hooked to the write rather than
left to the nightly batch.

Two deliberate choices:

  * codes are collected during flush but derived AFTER COMMIT, in a fresh session.
    Deriving inside the flush would re-enter the flush that triggered it, because
    derivation writes rows of its own.
  * the derive is best-effort and never raises. A post-commit side effect that raises
    would 500 an operation that already succeeded, and the retry would take the
    idempotent path without ever backfilling the missed work.
  * a small batch is derived here, a large one is handed to the worker. One person
    editing a product wants the answer in the same click; an import commits per chunk,
    so deriving thousands of codes inline would run the whole catalogue's derivation
    inside the import's own commit hook.

Kept out of `embedding_change_listener` on purpose: different concern, and that module
is under active change on other branches.
"""
from __future__ import annotations

import logging

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.product import Product

logger = logging.getLogger(__name__)

_REGISTERED = False
_PENDING_KEY = "_spec_codes_to_rederive"

# One person editing a product is a handful of codes and wants the answer now; an import
# is thousands and belongs on the worker. The line between the two is arbitrary, which is
# why it is named rather than inlined.
INLINE_REDERIVE_LIMIT = 50

# Only these feed derivation, so only these justify the work. A price edit must not
# re-derive 22,805 rows' worth of specs.
DERIVATION_INPUTS = (
    "product_code",
    "description",
    "category_id",
    "dimensions_length",
    "dimensions_width",
    "dimensions_height",
)


def _derivation_input_changed(target: Product) -> bool:
    state = inspect(target)
    return any(state.attrs[field].history.has_changes() for field in DERIVATION_INPUTS)


def _collect(session: Session, target: Product) -> None:
    if not getattr(target, "product_code", None):
        return
    session.info.setdefault(_PENDING_KEY, set()).add(target.product_code)


def enqueue_spec_embedding(db: Session, product_id: str) -> None:
    """Queue a `product_spec` re-embed for one product. Best-effort, never raises.

    Guarded on there being something to embed: an empty sentence embeds to a vector
    that sits near everything, so the product would surface for every query. The
    canonicaliser refuses one too, but the cheaper place to stop it is here.
    """
    try:
        from app.models.product_spec import ProductSpecifications
        from app.services.embedding_service import EmbeddingEventService

        spec = (
            db.query(ProductSpecifications)
            .filter(ProductSpecifications.product_id == product_id)
            .first()
        )
        if spec is None or not (spec.rendered_text or "").strip():
            return

        EmbeddingEventService(db).queue_event(
            source_type="product_spec",
            source_id=str(product_id),
            event_type="product_spec.updated",
            source_updated_at=spec.updated_at or spec.created_at,
            triggered_by="spec_derivation",
        )
    except Exception:  # pragma: no cover - defensive by design
        logger.warning("spec embedding enqueue failed for %s", product_id, exc_info=True)


def _rederive_inline(codes: set[str]) -> None:
    """Derive the codes here and now, in a fresh session. Never raises."""
    try:
        from app.database import SessionLocal
        from app.services.product_spec_derivation import (
            configured_max_values,
            configured_rules,
            configured_scopes,
            derive_for_code,
        )

        with SessionLocal() as db:
            # A code exists once per company; one derivation must reach every copy.
            with company_scope(db, None):
                # Read ONCE, for the same reason `derive_all` does it: handed nothing,
                # `derive_for_code` re-reads the whole registry twice per code, and the
                # answer cannot change part-way through a run.
                rules_by_key = configured_rules(db)
                scopes_by_key = configured_scopes(db)
                max_values = configured_max_values(db)
                for code in codes:
                    derive_for_code(
                        db,
                        code,
                        rules_by_key=rules_by_key,
                        scopes_by_key=scopes_by_key,
                        max_values=max_values,
                    )
                db.commit()
    except Exception:  # pragma: no cover - defensive by design
        logger.warning("spec re-derivation failed for %s", sorted(codes), exc_info=True)


def _enqueue_rederive(codes: set[str]) -> bool:
    """Hand the batch to the worker. True when the queue took it."""
    try:
        from app.services.queue_service import enqueue_job
        from app.tasks.product_spec_tasks import derive_product_specs

        enqueue_job(
            derive_product_specs,
            sorted(codes),
            queue_name="imports",
            run_label="change-listener",
        )
        return True
    except Exception:  # pragma: no cover - Redis down, and the work still has to happen
        logger.warning(
            "spec re-derivation could not be queued for %s codes; deriving inline",
            len(codes),
            exc_info=True,
        )
        return False


def rederive_codes(codes: set[str]) -> None:
    """Re-derive in a fresh session, all-companies scope. Never raises.

    Above `INLINE_REDERIVE_LIMIT` the work goes to the worker instead. A catalogue
    import commits per chunk, so an 11,415-code import would otherwise run the whole
    catalogue's derivation inside the import's own commit hook, one code at a time. The
    queue is best-effort like everything else post-commit: when it cannot be reached the
    codes are still derived here rather than dropped.
    """
    if not codes:
        return
    if len(codes) > INLINE_REDERIVE_LIMIT and _enqueue_rederive(codes):
        return
    _rederive_inline(codes)


def register_product_spec_listeners() -> None:
    """Idempotent registration, mirroring register_embedding_change_listeners."""
    global _REGISTERED
    if _REGISTERED:
        return

    @event.listens_for(Product, "after_insert")
    def _on_insert(mapper, connection, target):  # noqa: ANN001
        _collect(inspect(target).session, target)

    @event.listens_for(Product, "after_update")
    def _on_update(mapper, connection, target):  # noqa: ANN001
        if _derivation_input_changed(target):
            _collect(inspect(target).session, target)

    @event.listens_for(Session, "after_commit")
    def _on_commit(session):  # noqa: ANN001
        codes = session.info.pop(_PENDING_KEY, None)
        if codes:
            rederive_codes(codes)

    _REGISTERED = True
