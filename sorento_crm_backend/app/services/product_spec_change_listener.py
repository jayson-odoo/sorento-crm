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


def rederive_codes(codes: set[str]) -> None:
    """Re-derive in a fresh session, all-companies scope. Never raises."""
    if not codes:
        return
    try:
        from app.database import SessionLocal
        from app.services.product_spec_derivation import derive_for_code

        with SessionLocal() as db:
            # A code exists once per company; one derivation must reach every copy.
            with company_scope(db, None):
                for code in codes:
                    derive_for_code(db, code)
                db.commit()
    except Exception:  # pragma: no cover - defensive by design
        logger.warning("spec re-derivation failed for %s", sorted(codes), exc_info=True)


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
