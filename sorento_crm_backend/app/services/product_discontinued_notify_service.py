"""Product-discontinued batch notification (scheduled task ``product_discontinued_check``).

Since PRODUCT-FIELD-CHANGE-NOTIFY this is the first ``WatchedField`` of the shared runner in
``product_watched_field_notify_service`` (the mechanism, its stamp-first contract and the
per-recipient brand scoping are documented there). Behaviour is unchanged: each tick reports
products newly discontinued since the last run, one message per company per recipient slice,
with the count plus a deep link to the product list filtered to that batch.

This module keeps the names the scheduler and the existing tests import.

Decision log: docs/plans/PLAN-product-discontinued-notification.md,
documentation/plans/PLAN-product-discontinued-brand-scope.md
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.notification_service import NotificationService  # noqa: F401 - tests patch it
from app.services.product_watched_field_notify_service import (
    DISCONTINUED,
    PendingProduct,  # noqa: F401 - re-exported
    Recipient,  # noqa: F401 - re-exported
    batch_link as _batch_link,
    run_watched_field_check,
    subset_for_scopes,  # noqa: F401 - re-exported
)

NOTIFY_TYPE = DISCONTINUED.notify_type
SOURCE_ENTITY_TYPE = DISCONTINUED.source_entity_type
EVENT_TYPE = DISCONTINUED.event_type
EMAIL_PREF = DISCONTINUED.email_pref
WHATSAPP_PREF = DISCONTINUED.whatsapp_pref


def batch_link(batch_id: str, brand_ids: Optional[list[str]] = None) -> str:
    """Deep link to the product list filtered to one discontinued notify batch."""
    return _batch_link(DISCONTINUED.link_param, batch_id, brand_ids)


def run_product_discontinued_check(db: Session, task: Any = None) -> dict:
    """Scheduled-task entry point (see the shared runner for the contract)."""
    return run_watched_field_check(db, DISCONTINUED, task)
