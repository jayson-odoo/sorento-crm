"""The revision fence: no office action may land against a superseded version.

UAC ``portal-submission-revisions`` section C-bis (CB1-CB4).

Once a contact revision voids the stage an office user was working, that user's
open tab is holding a version that no longer exists. Voiding the tracker alone
does not stop them: the stock-inquiry respond path stamps ``last_responded_*``
and messages the contact from any status, and every lifecycle action (approve,
reject, process, close, void) would otherwise apply cleanly to the new revision
while having been decided against the old one (CB2).

So every office write on a revisable form carries the ``revision_no`` the client
was looking at, in the ``X-Revision-No`` request header, and this refuses the
write with **409** when it no longer matches.

Three deliberate properties:

* **One shared dependency** (CB3). A new revisable form type inherits the fence
  by adding a target below plus its config row, never by re-deriving the check
  per endpoint.
* **The header is optional.** A request that does not carry it is not fenced.
  That is what keeps every existing integration principal working (n8n, the MCP
  server, the external API), none of which has any notion of a revision. The
  fence protects the surface that CAN send it - the office UI - and the portal
  revise path has its own, mandatory, ``expected_revision_no`` guard (UAC C5).
* **Revisability is config-driven** (CB4). A type whose
  ``portal_revision_configs`` row is disabled - complaint today - costs one
  cached-free config read and nothing else; the row is never loaded.

NOT fenced, on purpose: ``POST /{entity}/{id}/conversation/send-message``. That
is the plain chat send, it never mutates the entity, and AC O2 keeps messaging a
contact working at any status and any revision. The fence guards entity writes,
not the conversation.

Ordering note: FastAPI solves route-level dependencies BEFORE the handler's own,
so on a permission-gated route a stale header yields 409 rather than 403. The
fence authenticates (below) so this is never reachable anonymously; beyond that,
telling an authenticated user their view is stale before telling them they lack
the permission is a harmless ordering, and the write still never happens.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.services.error_handler import handle_conflict

logger = logging.getLogger(__name__)

#: The header an office client sends with the revision it was viewing.
REVISION_HEADER = "X-Revision-No"


@dataclass(frozen=True)
class _FenceTarget:
    """One fenced route family: how to load the row and what type it is.

    ``entity_types`` is every ``source_entity_type`` the target can resolve to,
    used to skip the row load entirely when none of them is revisable.
    ``resolve_entity_type`` picks the exact one off the loaded row - purchase
    request and sponsorship form share a table, discriminated by
    ``request_type``.
    """

    load_model: Callable[[], Any]
    entity_types: tuple[str, ...]
    resolve_entity_type: Callable[[Any], str]


def _stock_inquiry_model() -> Any:
    from app.models.procurement import StockInquiry

    return StockInquiry


def _purchase_request_model() -> Any:
    from app.models.procurement import PurchaseRequestHeader

    return PurchaseRequestHeader


def _complaint_model() -> Any:
    from app.models.complaints import Complaint

    return Complaint


STOCK_INQUIRY = "stock_inquiry"
PURCHASE_REQUEST = "purchase_request"
COMPLAINT = "complaint"

_TARGETS: dict[str, _FenceTarget] = {
    STOCK_INQUIRY: _FenceTarget(
        load_model=_stock_inquiry_model,
        entity_types=("stock_inquiry",),
        resolve_entity_type=lambda row: "stock_inquiry",
    ),
    # One route family, two revisable types. Both are enabled from day one, so
    # the cheap pre-check passes and the row decides which config applies.
    PURCHASE_REQUEST: _FenceTarget(
        load_model=_purchase_request_model,
        entity_types=("purchase_request", "sponsorship_form"),
        resolve_entity_type=lambda row: (
            (getattr(row, "request_type", None) or "purchase_request").strip().lower()
            or "purchase_request"
        ),
    ),
    # Wired but inert: the complaint config row ships disabled (UAC A5), so this
    # short-circuits before touching the database. Flipping the checkbox arms it
    # with no code change - which is the point of CB4.
    COMPLAINT: _FenceTarget(
        load_model=_complaint_model,
        entity_types=("complaint",),
        resolve_entity_type=lambda row: "complaint",
    ),
}

# How the refusal names the document. Same vocabulary the contact-facing
# revision copy uses, so the two sides of the feature read alike.
_LABELS: dict[str, str] = {
    "stock_inquiry": "stock inquiry",
    "purchase_request": "purchase request",
    "sponsorship_form": "sponsorship form",
    "complaint": "complaint",
}


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _revisable_types(db: Session, candidates: tuple[str, ...]) -> set[str]:
    """Which of ``candidates`` currently has an ENABLED revision config.

    Fails closed on content (a missing row means disabled, UAC A3) and open on
    infrastructure: if the config table is not there at all, the fence is simply
    absent rather than 500-ing every office write.
    """
    try:
        from app.models.portal import PortalRevisionConfig

        rows = (
            db.query(PortalRevisionConfig.source_entity_type, PortalRevisionConfig.is_enabled)
            .filter(PortalRevisionConfig.source_entity_type.in_(candidates))
            .all()
        )
    except Exception:  # noqa: BLE001 - partial schema; never block a write on the fence
        db.rollback()
        logger.warning("Revision fence: config lookup failed for %s", candidates, exc_info=True)
        return set()
    return {str(entity_type) for entity_type, enabled in rows if enabled}


def assert_revision_current(
    db: Session,
    target: str,
    entity_id: Any,
    expected_revision_no: Optional[int],
) -> None:
    """Refuse a write aimed at a superseded revision (CB1). 409, or nothing.

    Silent no-op when: the client sent no expectation, the id is not a UUID (the
    route's own validation owns that error), the row is gone (the route's 404
    owns that), or the type is not currently revisable.
    """
    if expected_revision_no is None:
        return
    spec = _TARGETS.get(target)
    if spec is None or not entity_id or not _is_uuid(entity_id):
        return

    enabled = _revisable_types(db, spec.entity_types)
    if not enabled:
        return

    model = spec.load_model()
    row = db.query(model).filter(model.id == str(entity_id)).first()
    if row is None:
        return
    if spec.resolve_entity_type(row) not in enabled:
        return

    current = int(getattr(row, "revision_no", 0) or 0)
    if int(expected_revision_no) == current:
        return

    label = _LABELS.get(spec.resolve_entity_type(row), "record")
    # A mismatch does not always mean "a revision happened". When `current` is 0 the
    # record has never been revised, so the client sent a number that was never real
    # (a stale tab from before a reset, a hand-built request, a bug). Saying "was
    # revised ... reload to see revision 0" in that case is self-contradictory and
    # tells the reader nothing they can act on, so name only what is certain.
    if current == 0:
        raise handle_conflict(
            f"This {label} has changed since you opened it. Reload and try again."
        )
    raise handle_conflict(
        f"This {label} was revised while you were working on it. "
        f"Reload to see revision {current}."
    )


def require_current_revision(target: str, id_param: str) -> Callable:
    """FastAPI dependency for one fenced route family.

    ``target`` keys :data:`_TARGETS`; ``id_param`` is the path parameter holding
    the entity id (``inquiry_id`` / ``request_id`` / ``complaint_id``), read off
    the request rather than declared, because the name differs per router and
    the whole point is one dependency.

    Mount with ``dependencies=[Depends(require_current_revision(...))]`` so the
    check runs before the handler and no write happens on a refusal.
    """

    def _fence(
        request: Request,
        x_revision_no: Optional[int] = Header(
            default=None,
            alias=REVISION_HEADER,
            description=(
                "The revision_no the client was viewing. When present and stale, "
                "the write is refused with 409."
            ),
        ),
        # Route-level dependencies are solved BEFORE the handler's own, so without
        # this an anonymous caller could probe a record's revision through the 409.
        # Authenticating here keeps the fence behind the same door as the write.
        _principal: dict = Depends(get_current_user_or_api_key),
        db: Session = Depends(get_db),
    ) -> None:
        if x_revision_no is None:
            return
        assert_revision_current(
            db, target, request.path_params.get(id_param), x_revision_no
        )

    return _fence
