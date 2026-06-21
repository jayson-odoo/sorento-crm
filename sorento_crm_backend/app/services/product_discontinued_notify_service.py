"""Product-discontinued batch notification (scheduled task ``product_discontinued_check``).

Each tick reports products that became discontinued since the last run — exactly
once, based on CURRENT state. A discontinue-then-revert before the tick is never
reported (the reverted product has ``is_discontinued = False``). Subscribed staff
(admin-configured per-user toggles) get ONE message with the COUNT of newly
discontinued products plus a deep link to the product list filtered to that batch.
Product names are intentionally omitted (WhatsApp template length); the link shows
the authoritative list.

Stamp-first, best-effort fan-out: the batch is stamped + committed BEFORE sending,
so a crash mid-fan-out cannot re-batch the same products under a new id (which would
double-notify). Miss-on-crash beats spam-on-crash for an anti-spam feature.

Decision log: docs/plans/PLAN-product-discontinued-notification.md
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.services.sla_service import MALAYSIA_TZ
from app.models.product import Product
from app.models.user import User
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

NOTIFY_TYPE = "product_discontinued"
SOURCE_ENTITY_TYPE = "product_discontinued_batch"
EVENT_TYPE = "discontinued"
EMAIL_PREF = "notify_email_on_product_discontinued"
WHATSAPP_PREF = "notify_whatsapp_on_product_discontinued"


def _frontend_base() -> str:
    return (getattr(settings, "frontend_base_url", None) or "").strip().rstrip("/")


def batch_link(batch_id: str) -> str:
    """Internal staff deep link to the product list filtered to one notify batch."""
    return (
        f"{_frontend_base()}/master-data-management/products"
        f"?discontinued_batch_id={batch_id}"
    )


def _plural(n: int) -> str:
    return "" if n == 1 else "s"


def run_product_discontinued_check(db: Session, task: Any = None) -> dict:
    """Scheduled-task entry point (PLAN Q12/A: stamp-first, best-effort)."""
    now = datetime.utcnow()
    # Pending = currently discontinued AND not yet reported. A product reverted
    # before this tick has is_discontinued=False, so it is excluded automatically —
    # no event log needed (level-triggered on current state).
    pending = (
        db.query(Product)
        .filter(
            Product.is_discontinued.is_(True),
            Product.discontinued_notified_at.is_(None),
        )
        .all()
    )
    if not pending:
        return {"pending": 0, "subscribers": 0, "notified_users": 0, "batch_id": None}

    batch_id = str(uuid.uuid4())
    count = len(pending)
    # Stamp FIRST and commit before any send.
    for p in pending:
        p.discontinued_notified_at = now
        p.discontinued_notify_batch_id = batch_id
    db.commit()

    link = batch_link(batch_id)
    title = f"{count} product{_plural(count)} discontinued"
    body = (
        f"{count} product{_plural(count)} {'was' if count == 1 else 'were'} newly "
        f"marked as discontinued. View the list: {link}"
    )
    wa_text = f"{count} product{_plural(count)} discontinued. View the list: {link}"
    # Date the batch is reported, in Malaysia local time (DD/MM/YYYY) — matches the
    # daily-summary label so templates can read "Discontinued summary at {{date}}".
    today_date = datetime.now(MALAYSIA_TZ).strftime("%d/%m/%Y")
    context_vars = {
        "discontinued_count": str(count),
        "discontinued_link": link,
        "today_date": today_date,
        "system_url": _frontend_base(),
        # Aliased onto portal_url so templates can reuse the existing link slot.
        "portal_url": link,
        "message": wa_text,
    }

    # Recipient = a user with EITHER toggle on (in-app fires for every recipient;
    # email/whatsapp each gated by its own toggle inside create_with_channel_preferences).
    subscribers = (
        db.query(User)
        .filter(
            User.is_trashed.is_(False),
            or_(
                getattr(User, EMAIL_PREF).is_(True),
                getattr(User, WHATSAPP_PREF).is_(True),
            ),
        )
        .all()
    )

    notified_users = 0
    notifier = NotificationService(db)
    for user in subscribers:
        # Best-effort per recipient: one failure must never abort the rest, and the
        # batch is already stamped so it won't be retried this loop. (Relies on
        # create_with_channel_preferences committing internally, so the except
        # rollback only discards the failing iteration's own partial flush.)
        try:
            notifier.create_with_channel_preferences(
                user_id=user.id,
                type=NOTIFY_TYPE,
                title=title,
                body=body,
                data={
                    "discontinued_count": count,
                    "discontinued_batch_id": batch_id,
                    "discontinued_link": link,
                    "whatsapp_use_case": NOTIFY_TYPE,
                    "whatsapp_text": wa_text,
                    "whatsapp_context_vars": context_vars,
                },
                source_entity_type=SOURCE_ENTITY_TYPE,
                source_entity_id=batch_id,
                event_type=EVENT_TYPE,
                send_in_app=True,
                send_email=True,
                send_whatsapp=True,
                email_pref_attr=EMAIL_PREF,
                whatsapp_pref_attr=WHATSAPP_PREF,
            )
            notified_users += 1
        except Exception as e:  # noqa: BLE001 — best-effort fan-out
            db.rollback()
            logger.warning(
                "product_discontinued notify failed for user %s (batch %s): %s",
                user.id,
                batch_id,
                e,
            )

    return {
        "pending": count,
        "batch_id": batch_id,
        "subscribers": len(subscribers),
        "notified_users": notified_users,
    }
