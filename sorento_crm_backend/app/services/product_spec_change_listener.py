"""Keep derived specs, and the index built on them, in step with the catalog.

A product whose description, code or dimensions change has stale specs until something
re-derives it, and a stale spec is worse than a missing one: it ranks a product on a
value the catalog no longer states. So the re-derive is hooked to the write rather than
left to the nightly batch.

The same argument applies one step further down. Once the spec sentence is rewritten,
the product's semantic index entry describes a sentence that no longer exists, so this
module carries a SECOND producer: spec rows changed in a transaction are collected and
re-embedded after it commits. Hooked at the ORM boundary rather than at the call sites
because there are four writers today (authored, derived, the RQ task, the batch) and a
per-call-site fix would be missed by the fifth.

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
from app.models.product_spec import ProductSpecifications

logger = logging.getLogger(__name__)

_REGISTERED = False
_PENDING_KEY = "_spec_codes_to_rederive"
# Its own key, not a second use of the one above: the two hold different things (codes
# to derive vs product ids to embed) and are drained by different code. Sharing one key
# would make the drain guess which it was handed.
_PENDING_EMBED_KEY = "_spec_products_to_embed"

# One person editing a product is a handful of codes and wants the answer now; an import
# is thousands and belongs on the worker. The line between the two is arbitrary, which is
# why it is named rather than inlined.
INLINE_REDERIVE_LIMIT = 50

# The same line, drawn for the same reason, on the embedding side. One person's edit is
# a couple of rows and is indexed on the next worker pass; a catalogue import is 22,805
# and must not run its whole embedding fan-out inside the import's own commit hook.
INLINE_ENQUEUE_LIMIT = 50

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


def _rendered_text_changed(target: ProductSpecifications) -> bool:
    """True when this write gave the row a DIFFERENT sentence.

    The sentence is the entire body the worker embeds for this source type, so an
    identical one cannot change the document, and re-embedding it spends a model call
    to write back what is already there. That matters because `write_spec_row` assigns
    `rendered_text` on EVERY derivation pass, including the provenance-only and
    status-only ones.

    Asking the attribute history is enough, and asking it is not the same as asking
    whether the attribute was assigned: SQLAlchemy compares a scalar assignment against
    the loaded value, so re-assigning an equal sentence comes back as `unchanged` and
    does not even emit an UPDATE. A row inserted without a sentence has no history
    either, so it is skipped here as well as by `enqueue_spec_embedding`'s own guard.
    """
    return inspect(target).attrs["rendered_text"].history.has_changes()


def _collect_embed(session: Session, target: ProductSpecifications) -> None:
    if not getattr(target, "product_id", None):
        return
    session.info.setdefault(_PENDING_EMBED_KEY, set()).add(str(target.product_id))


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
                for code in codes:
                    derive_for_code(
                        db,
                        code,
                        rules_by_key=rules_by_key,
                        scopes_by_key=scopes_by_key,
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


def embed_products_inline(product_ids: set[str]) -> None:
    """Queue the re-embeds here and now, in a fresh session. Never raises.

    The session has to be a fresh one rather than the caller's: `queue_event` commits,
    so running it inside the writer's transaction would commit that writer's
    half-finished work. Best-effort per id as well as overall, because one product
    whose enqueue fails must not take the rest of the batch with it.

    Public because the worker task calls it once per chunk. Routing is `embed_products`'
    job, and a chunk that came FROM the queue must not be handed back to it.
    """
    try:
        from app.database import SessionLocal

        with SessionLocal() as db:
            # A spec row exists per company copy; this drain is a system process and
            # must reach every one of them, exactly as the embedding worker does.
            with company_scope(db, None):
                for product_id in sorted(product_ids):
                    try:
                        enqueue_spec_embedding(db, product_id)
                    except Exception:  # pragma: no cover - backstop, see below
                        # `enqueue_spec_embedding` already swallows its own failures, so
                        # nothing should arrive here. It is caught anyway because the
                        # cost of being wrong is the rest of the batch: this loop is the
                        # only thing standing between one bad id and every other
                        # product's index entry staying stale.
                        logger.warning(
                            "spec embedding enqueue failed for %s", product_id, exc_info=True
                        )
                    finally:
                        # `queue_event` commits on success. Anything still open is a
                        # half-finished attempt whose failure was swallowed, and left
                        # alone it would ride along on the NEXT product's commit.
                        db.rollback()
    except Exception:  # pragma: no cover - defensive by design
        logger.warning(
            "spec embedding enqueue failed for %s products", len(product_ids), exc_info=True
        )


def _enqueue_embed(product_ids: set[str]) -> bool:
    """Hand the batch to the worker. True when the queue took it."""
    try:
        from app.services.queue_service import enqueue_job
        from app.tasks.product_spec_tasks import enqueue_spec_embeddings

        enqueue_job(
            enqueue_spec_embeddings,
            sorted(product_ids),
            queue_name="imports",
            run_label="change-listener",
        )
        return True
    except Exception:  # pragma: no cover - Redis down, and the work still has to happen
        logger.warning(
            "spec embedding could not be queued for %s products; enqueuing inline",
            len(product_ids),
            exc_info=True,
        )
        return False


def embed_products(product_ids: set[str]) -> None:
    """Queue a re-embed per changed product row. Never raises.

    Above `INLINE_ENQUEUE_LIMIT` the fan-out goes to the worker instead, on the same
    argument as `rederive_codes`: an import commits per chunk, so a catalogue-sized
    batch would otherwise run every enqueue (each of which commits and pushes an RQ
    job) inside the import's own commit hook. An unreachable queue falls back to
    enqueuing here rather than dropping the ids - a dropped id is a stale index entry
    that nothing will ever notice.
    """
    if not product_ids:
        return
    if len(product_ids) > INLINE_ENQUEUE_LIMIT and _enqueue_embed(product_ids):
        return
    embed_products_inline(product_ids)


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

    @event.listens_for(ProductSpecifications, "after_insert")
    def _on_spec_insert(mapper, connection, target):  # noqa: ANN001
        if _rendered_text_changed(target):
            _collect_embed(inspect(target).session, target)

    @event.listens_for(ProductSpecifications, "after_update")
    def _on_spec_update(mapper, connection, target):  # noqa: ANN001
        if _rendered_text_changed(target):
            _collect_embed(inspect(target).session, target)

    @event.listens_for(Session, "after_commit")
    def _on_commit(session):  # noqa: ANN001
        # Both keys are taken before either drain runs: each drain opens its own
        # session and neither is allowed to raise, so a key left behind by the first
        # would be drained again by whatever committed next.
        codes = session.info.pop(_PENDING_KEY, None)
        product_ids = session.info.pop(_PENDING_EMBED_KEY, None)
        if product_ids:
            embed_products(product_ids)
        if codes:
            rederive_codes(codes)

    _REGISTERED = True
