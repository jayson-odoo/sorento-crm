"""Delete the consumer ledger's own data, and nothing else (AC-L2).

This module owns exactly three tables plus the review queue that hangs off the
profile. It reaches into no other module: a purge that removed a customer-service
record because somebody uninstalled a data module would destroy history nobody
asked it to touch.

Children first. The profile is deleted last because both other tables point at it.
"""
from __future__ import annotations

import logging
from typing import Dict

from sqlalchemy.orm import Session

from app.models.consumers import (
    ConsumerProfile,
    ConsumerProfileReview,
    ConsumerPurchase,
    ConsumerPurchaseLine,
)

logger = logging.getLogger(__name__)


def _deleted(db: Session, model, label: str) -> int:
    count = db.query(model).delete(synchronize_session=False)
    logger.info("Purge %s: deleted %s rows", label, count)
    return count


def purge(db: Session) -> Dict[str, int]:
    out: Dict[str, int] = {}
    out["consumer_purchase_lines"] = _deleted(db, ConsumerPurchaseLine, "consumer_purchase_lines")
    out["consumer_purchases"] = _deleted(db, ConsumerPurchase, "consumer_purchases")
    out["consumer_profile_reviews"] = _deleted(
        db, ConsumerProfileReview, "consumer_profile_reviews"
    )
    out["consumer_profiles"] = _deleted(db, ConsumerProfile, "consumer_profiles")
    return out
