"""Consumer 360 - the screen that makes the module's commercial purpose real.

Sorento sells through dealers and therefore does not know who owns its products. S1 built
the ledger that fixes that, S2 built the engine that decides cover, S3 built the journey
that fills them - and until now none of it had a read surface. An asset nobody can look at
is indistinguishable from one that was never collected.

**One page answers one question: what do we know about this person.** Profile, every
purchase with its dealer and that dealer's own document number, every complaint, every
stored document. Not four screens the user has to join up mentally - the joining up is the
product.

Two rules the endpoints enforce rather than leave to the frontend:

1. **Purchase value is OMITTED, not nulled, without `consumers.purchase_value.view`**
   (AC-L24). `None` means "the receipt showed no total", which is a different fact from
   "you may not see it"; serialising the first when you mean the second tells a CS agent
   the dealer sold it for nothing. The permission is granted to nobody by the seed.

2. **A merged profile redirects rather than 404s** (AC-L10). "Where did this consumer go"
   has to be answerable, or a CS agent following an old link concludes the record was
   deleted.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.complaints import Complaint, ComplaintProductLine
from app.models.consumers import ConsumerProfile, ConsumerPurchase, ConsumerPurchaseLine
from app.services import consumer_service
from app.services.error_handler import handle_not_found
from app.services.uuid_path_param import validate_uuid_path
from app.services.user_service import UserPermissionService

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW_PERMISSION = "consumers.profiles.view"
VALUE_PERMISSION = "consumers.purchase_value.view"


def _can_view_value(db: Session, current_user: dict) -> bool:
    """Deny by default. The seed grants this to nobody, so an install where somebody
    can see purchase values is one where a human deliberately granted it.
    """
    try:
        return bool(
            UserPermissionService(db).check_user_has_permission(
                current_user["id"], VALUE_PERMISSION
            )
        )
    except Exception as exc:  # noqa: BLE001 - a failed check is not a grant
        logger.warning("Purchase-value permission check failed: %s", exc)
        return False


def _profile_payload(profile: ConsumerProfile) -> Dict[str, Any]:
    return {
        "id": profile.id,
        "full_name": profile.full_name,
        "phone_e164": profile.phone_e164,
        "email": profile.email,
        "respond_contact_id": profile.respond_contact_id,
        # A provisional profile is a phone somebody typed into a message, not a person
        # who authenticated. Showing which is which stops "we have N consumers" being
        # read as N real people.
        "is_provisional": bool(profile.is_provisional),
        "confirmed_at": profile.confirmed_at,
        # Fork 6. Which wording they saw, and when - the only answerable form of
        # "did this person consent".
        "consent_purpose": profile.consent_purpose,
        "consent_notice_version": profile.consent_notice_version,
        "consent_recorded_at": profile.consent_recorded_at,
        "anonymised_at": profile.anonymised_at,
        "merged_into_id": profile.merged_into_id,
        "created_at": profile.created_at,
    }


@router.get("/consumers")
async def list_consumers(
    query: Optional[str] = Query(None, description="Phone or name, partial."),
    include_provisional: bool = Query(True),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    _perm: dict = Depends(require_permission(VIEW_PERMISSION)),
):
    """Find a consumer. Phone first, because that is what a CS agent has in hand.

    Merged and anonymised profiles are excluded: the first would show a person twice
    under two names, and the second is a row kept only so its purchases have a parent -
    there is no longer a person in it to find.
    """
    q = (
        db.query(ConsumerProfile)
        .filter(ConsumerProfile.merged_into_id.is_(None))
        .filter(ConsumerProfile.anonymised_at.is_(None))
    )
    if not include_provisional:
        q = q.filter(ConsumerProfile.is_provisional.is_(False))

    term = (query or "").strip()
    if term:
        # The phone is matched on its NORMALISED form as well as verbatim: a CS agent
        # types "012-345 6789" and the column holds "+60123456789".
        e164 = consumer_service.normalize_phone_e164(term)
        like = f"%{term}%"
        clauses = [
            ConsumerProfile.full_name.ilike(like),
            ConsumerProfile.phone_e164.ilike(like),
        ]
        if e164:
            clauses.append(ConsumerProfile.phone_e164 == e164)
        q = q.filter(or_(*clauses))

    total = q.count()
    rows = (
        q.order_by(ConsumerProfile.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "data": [_profile_payload(row) for row in rows],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/consumers/{profile_id}")
async def get_consumer_360(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _perm: dict = Depends(require_permission(VIEW_PERMISSION)),
):
    """Everything the ledger holds about one person, on one response.

    Assembled server-side rather than left to four frontend calls: the join between a
    complaint line and the purchase that supplies its DATE is the whole point of AC-L16,
    and a frontend re-deriving it would eventually derive it differently.
    """
    # A malformed id is, from the caller's view, a guaranteed-missing row. Turning it
    # into a clean 404 here stops it reaching the DB layer as a 500.
    profile_id = validate_uuid_path(profile_id, resource="Consumer")
    profile = (
        db.query(ConsumerProfile).filter(ConsumerProfile.id == profile_id).first()
    )
    if profile is None:
        raise handle_not_found("Consumer", profile_id)

    # AC-L10. The losing side of a merge is retained pointing at the survivor, so an old
    # link answers "it is over there" instead of "it is gone".
    if profile.merged_into_id:
        return {
            "profile": _profile_payload(profile),
            "merged_into_id": profile.merged_into_id,
            "purchases": [],
            "complaints": [],
        }

    can_view_value = _can_view_value(db, current_user)

    purchases = consumer_service.purchases_for_profile(db, str(profile.id))
    purchase_ids = [p.id for p in purchases]
    lines_by_purchase: Dict[str, List[ConsumerPurchaseLine]] = {}
    if purchase_ids:
        for line in (
            db.query(ConsumerPurchaseLine)
            .filter(ConsumerPurchaseLine.purchase_id.in_(purchase_ids))
            .order_by(ConsumerPurchaseLine.sort_order)
            .all()
        ):
            lines_by_purchase.setdefault(line.purchase_id, []).append(line)

    purchase_payload = []
    for purchase in purchases:
        row = consumer_service.serialize_purchase(purchase, can_view_value=can_view_value)
        row["lines"] = [
            {
                "id": line.id,
                "kind_code": line.kind_code,
                "product_id": line.product_id,
                # Verbatim, and the only evidence when the variant never resolved.
                "claimed_text": line.claimed_text,
                "quantity": line.quantity,
                **({"line_value": line.line_value} if can_view_value else {}),
            }
            for line in lines_by_purchase.get(purchase.id, [])
        ]
        purchase_payload.append(row)

    # Complaints reach a consumer two ways and both count: through a line that names one
    # of their purchases (AC-L16), and through the phone on the complaint itself. A
    # complaint lodged before any receipt arrived has no purchase link at all, and it is
    # exactly the one a CS agent is looking for.
    complaint_ids = set()
    if purchase_ids:
        line_ids = [
            line.id for rows in lines_by_purchase.values() for line in rows
        ]
        if line_ids:
            complaint_ids.update(
                row[0]
                for row in db.query(ComplaintProductLine.complaint_id)
                .filter(ComplaintProductLine.consumer_purchase_line_id.in_(line_ids))
                .all()
            )
    if profile.phone_e164:
        complaint_ids.update(
            row[0]
            for row in db.query(Complaint.id)
            .filter(
                or_(
                    Complaint.contact_number == profile.phone_e164,
                    Complaint.site_contact_phone == profile.phone_e164,
                )
            )
            .all()
        )

    complaints = []
    if complaint_ids:
        complaints = (
            db.query(Complaint)
            .filter(Complaint.id.in_(list(complaint_ids)))
            .order_by(Complaint.created_at.desc())
            .all()
        )

    return {
        "profile": _profile_payload(profile),
        "merged_into_id": None,
        "purchases": purchase_payload,
        "complaints": [
            {
                "id": row.id,
                "complaint_number": row.complaint_number,
                "complaint_date": row.complaint_date,
                "status": row.status,
                "defect_description": row.defect_description,
                "site_address": row.site_address,
                "customer_id": row.customer_id,
            }
            for row in complaints
        ],
        # Counts stay on the response so the page can render an honest empty state per
        # section rather than hiding a section that happens to be empty.
        "counts": {
            "purchases": len(purchase_payload),
            "complaints": len(complaints),
        },
    }


@router.get("/consumers/stats/headline")
async def consumer_headline(
    db: Session = Depends(get_db),
    _perm: dict = Depends(require_permission(VIEW_PERMISSION)),
):
    """"How many consumers do we know?" - the number the module exists to grow.

    Provisional profiles are excluded (AC-L7). A phone somebody typed into a message is
    not a consumer Sorento knows, and counting it makes the headline go up without the
    asset going up, which is the one number that must not lie.
    """
    confirmed = consumer_service.count_consumers(db)
    provisional = (
        db.query(func.count(ConsumerProfile.id))
        .filter(ConsumerProfile.is_provisional.is_(True))
        .filter(ConsumerProfile.merged_into_id.is_(None))
        .filter(ConsumerProfile.anonymised_at.is_(None))
        .scalar()
        or 0
    )
    purchases = db.query(func.count(ConsumerPurchase.id)).scalar() or 0
    return {
        "consumers": confirmed,
        "provisional": provisional,
        "purchases": purchases,
    }
