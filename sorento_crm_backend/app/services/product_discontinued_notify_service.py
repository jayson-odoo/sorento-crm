"""Product-discontinued batch notification (scheduled task ``product_discontinued_check``).

Each tick reports products that became discontinued since the last run — exactly
once, based on CURRENT state. A discontinue-then-revert before the tick is never
reported (the reverted product has ``is_discontinued = False``). Subscribed staff
(admin-configured per-user toggles) get ONE message with the COUNT of newly
discontinued products plus a deep link to the product list filtered to that batch.
Product names are intentionally omitted (WhatsApp template length); the link shows
the authoritative list.

Each recipient hears about THEIR slice of the batch, not the whole of it: a user's
``user_product_discontinued_scopes`` rows say which (company, brand) pairs they are
responsible for, and the count, the wording and the deep link are all built from
the products of that batch inside those scopes. A user whose scopes touch nothing
in a batch is skipped silently, and a user with no scopes at all hears nothing (the
migration gives everyone who already had a toggle on one all/all scope, which is
what they receive today).

Stamp-first, best-effort fan-out: the batch is stamped + committed BEFORE sending,
so a crash mid-fan-out cannot re-batch the same products under a new id (which would
double-notify). Miss-on-crash beats spam-on-crash for an anti-spam feature.

Decision log: docs/plans/PLAN-product-discontinued-notification.md,
documentation/plans/PLAN-product-discontinued-brand-scope.md
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.services.sla_service import MALAYSIA_TZ
from app.models.product import Product
from app.models.user import User, UserProductDiscontinuedScope
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

NOTIFY_TYPE = "product_discontinued"
SOURCE_ENTITY_TYPE = "product_discontinued_batch"
EVENT_TYPE = "discontinued"
EMAIL_PREF = "notify_email_on_product_discontinued"
WHATSAPP_PREF = "notify_whatsapp_on_product_discontinued"


def _frontend_base() -> str:
    return (getattr(settings, "frontend_base_url", None) or "").strip().rstrip("/")


def batch_link(batch_id: str, brand_ids: Optional[list[str]] = None) -> str:
    """Internal staff deep link to the product list filtered to one notify batch.

    With ``brand_ids`` the link additionally carries the recipient's brands, so it
    opens on exactly the subset their message counted. Without them it is the plain
    batch link, byte-identical to what an all-brands recipient has always received.
    """
    link = (
        f"{_frontend_base()}/master-data-management/products"
        f"?discontinued_batch_id={batch_id}"
    )
    if brand_ids:
        link += f"&brand_id={','.join(brand_ids)}"
    return link


def _plural(n: int) -> str:
    return "" if n == 1 else "s"


def _load_recipient_scopes(db: Session) -> tuple[list, dict[str, list]]:
    """Candidate recipients (either toggle on, not trashed) and their scope rows.

    Loaded ONCE per run and shared by every company batch. The scopes are read as
    raw ``(company_id, brand_id)`` pairs and matched against the product rows we
    already hold: no Brand query, which matters because brands are company-scoped
    and this runs under whatever scope the scheduled task carries.
    """
    users = (
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
    scopes: dict[str, list] = {}
    if users:
        rows = (
            db.query(UserProductDiscontinuedScope)
            .filter(UserProductDiscontinuedScope.user_id.in_([u.id for u in users]))
            .all()
        )
        for row in rows:
            scopes.setdefault(str(row.user_id), []).append(
                (
                    str(row.company_id) if row.company_id is not None else None,
                    str(row.brand_id) if row.brand_id is not None else None,
                )
            )
    return users, scopes


def subset_for_scopes(
    scopes: list, company_id: Optional[str], pending: list
) -> tuple[list, list[str]]:
    """The products of one company's batch this recipient is responsible for.

    Returns ``(products, brand_ids_for_link)``. An all-brands scope for the company
    (or an all-companies scope, which is the same thing everywhere) takes the whole
    batch with no brand filter on the link. Otherwise the subset is the products
    whose brand the recipient named, and the link carries those brands.

    A product with no brand therefore reaches only all-brands scopes, which is the
    honest reading of "I look after brand X": an unbranded product is not brand X.
    """
    relevant = [s for s in scopes if s[0] is None or s[0] == company_id]
    if not relevant:
        return [], []
    if any(brand_id is None for _, brand_id in relevant):
        return list(pending), []

    wanted = {brand_id for _, brand_id in relevant if brand_id}
    subset = [p for p in pending if getattr(p, "brand_id", None) and str(p.brand_id) in wanted]
    return subset, sorted(wanted)


def run_product_discontinued_check(db: Session, task: Any = None) -> dict:
    """Scheduled-task entry point (PLAN Q12/A: stamp-first, best-effort).

    WHICH companies this reports on is not decided here: the scheduler applies the
    task's own ``metadata.company_ids`` scope to the session, so the query below only
    ever sees the companies that task is allowed to touch (all of them when unset).
    Configuring it lives with every other per-task setting instead of in a bespoke
    column, and the same knob works for any scheduled job.

    What IS decided here is the batching: one batch PER company, never one spanning
    them. The count and the deep link are the whole message, and both are meaningless
    if they mix two catalogues that different people are responsible for.
    """
    from app.models.company import Company

    # Level-triggered on current state: a product discontinued then reverted before
    # this tick has is_discontinued=False and drops out on its own, no event log.
    pending = (
        db.query(Product)
        .filter(
            Product.is_discontinued.is_(True),
            Product.discontinued_notified_at.is_(None),
        )
        .all()
    )
    by_company: dict[Optional[str], list[Product]] = {}
    for p in pending:
        by_company.setdefault(getattr(p, "company_id", None), []).append(p)

    names = {}
    if by_company:
        ids = [c for c in by_company if c]
        if ids:
            names = {c.id: c.name for c in db.query(Company).filter(Company.id.in_(ids)).all()}
    # Name the company in the copy only when this run actually spans more than one,
    # so the single-company install keeps its existing wording.
    label_with_company = len(by_company) > 1

    # Recipients + scopes are a property of the RUN, not of a company: loaded once
    # and reused for every batch so a ten-company run is still two queries.
    candidates, scopes_by_user = _load_recipient_scopes(db) if by_company else ([], {})

    runs = [
        _run_for_company(
            db, cid, names.get(cid), label_with_company, rows, candidates, scopes_by_user
        )
        for cid, rows in by_company.items()
    ]
    if not runs:
        return {"pending": 0, "subscribers": 0, "notified_users": 0, "batch_id": None, "companies": []}
    return {
        # Top-level keys stay aggregate so existing task-run logs keep their shape.
        "pending": sum(r["pending"] for r in runs),
        "subscribers": max((r["subscribers"] for r in runs), default=0),
        "notified_users": sum(r["notified_users"] for r in runs),
        "batch_id": runs[0]["batch_id"] if len(runs) == 1 else None,
        "companies": runs,
    }


def _run_for_company(
    db: Session,
    company_id: Optional[str],
    company_name: Optional[str],
    label_with_company: bool,
    pending: list,
    candidates: list,
    scopes_by_user: dict[str, list],
) -> dict:
    now = datetime.utcnow()

    batch_id = str(uuid.uuid4())
    count = len(pending)
    # Stamp FIRST and commit before any send.
    for p in pending:
        p.discontinued_notified_at = now
        p.discontinued_notify_batch_id = batch_id
    db.commit()

    prefix = f"{company_name}: " if (label_with_company and company_name) else ""
    scope_label = f" for {company_name}" if (label_with_company and company_name) else ""
    # Date the batch is reported, in Malaysia local time (DD/MM/YYYY) — matches the
    # daily-summary label so templates can read "Discontinued summary at {{date}}".
    today_date = datetime.now(MALAYSIA_TZ).strftime("%d/%m/%Y")

    notified_users = 0
    subscribers = 0
    notifier = NotificationService(db)
    for user in candidates:
        subset, brand_ids = subset_for_scopes(
            scopes_by_user.get(str(user.id), []), company_id, pending
        )
        # Nothing of theirs in this batch: no in-app row, no delivery, no noise.
        if not subset:
            continue
        subscribers += 1

        user_count = len(subset)
        link = batch_link(batch_id, brand_ids)
        title = f"{prefix}{user_count} product{_plural(user_count)} discontinued"
        body = (
            f"{user_count} product{_plural(user_count)}{scope_label} "
            f"{'was' if user_count == 1 else 'were'} newly "
            f"marked as discontinued. View the list: {link}"
        )
        wa_text = (
            f"{prefix}{user_count} product{_plural(user_count)} discontinued. "
            f"View the list: {link}"
        )
        context_vars = {
            "discontinued_count": str(user_count),
            "discontinued_link": link,
            "company_name": company_name or "",
            "today_date": today_date,
            "system_url": _frontend_base(),
            # Aliased onto portal_url so templates can reuse the existing link slot.
            "portal_url": link,
            "message": wa_text,
        }

        # Best-effort per recipient: one failure must never abort the rest, and the
        # batch is already stamped so it won't be retried this loop. (Relies on
        # create_with_channel_preferences committing internally, so the except
        # rollback only discards the failing iteration's own partial flush.)
        try:
            # contact_name is the RECIPIENT (this batch goes to staff, not a contact),
            # so it varies per subscriber — merge it onto the shared context here.
            recipient_name = (user.name or user.email or "there").strip() or "there"
            user_context_vars = {**context_vars, "contact_name": recipient_name}
            notifier.create_with_channel_preferences(
                user_id=user.id,
                type=NOTIFY_TYPE,
                title=title,
                body=body,
                data={
                    "discontinued_count": user_count,
                    "discontinued_batch_id": batch_id,
                    "discontinued_link": link,
                    "whatsapp_use_case": NOTIFY_TYPE,
                    "whatsapp_text": wa_text,
                    "whatsapp_context_vars": user_context_vars,
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
        "company_id": company_id,
        "pending": count,
        "batch_id": batch_id,
        # Recipients this batch actually concerned, not everyone holding a toggle.
        "subscribers": subscribers,
        "notified_users": notified_users,
    }
