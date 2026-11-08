"""Shared "a watched product field changed" batch notifier (PRODUCT-FIELD-CHANGE-NOTIFY).

One runner, one ``WatchedField`` spec per product column. Each spec is a scheduled task of
its own (``product_discontinued_check``, ``product_list_price_check``) so its cadence and
company scope live with every other per-task setting.

The mechanism, the same for every field (it was the discontinued notifier's, unchanged):

* Level-triggered on CURRENT state against a watermark on the product row, never on an
  event log. So every write path (UI edit, AutoCount raw-SQL ingest, Excel import) is
  covered without a hook, and a change reverted before the tick is never reported.
* One batch PER company, never one spanning two catalogues.
* Stamp-first: the batch is stamped and committed BEFORE any send, so a crash mid-fan-out
  cannot re-batch the same products (miss-on-crash beats spam-on-crash).
* Recipients are users with either of the field's two toggles on; each hears about only
  their slice of the batch, by their ``user_product_discontinued_scopes`` (company, brand)
  rows (the table predates this module; the scope means "the brands I look after", which
  is the same fact for every watched field). In-app always, email / WhatsApp per toggle.

What a spec owns: which products are pending, the snapshot of them taken before the stamp
commit (plain values, see ``_run_for_company``), how they are stamped, and the message.

Plans: documentation/plans/products/PLAN-product-field-change-notify-07nov.md,
docs/plans/PLAN-product-discontinued-notification.md,
documentation/plans/PLAN-product-discontinued-brand-scope.md
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, NamedTuple, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.product import Product
from app.models.user import User, UserProductDiscontinuedScope
from app.services.notification_service import NotificationService
from app.services.sla_service import MALAYSIA_TZ

logger = logging.getLogger(__name__)


def _frontend_base() -> str:
    return (getattr(settings, "frontend_base_url", None) or "").strip().rstrip("/")


def batch_link(param: str, batch_id: str, brand_ids: Optional[list[str]] = None) -> str:
    """Staff deep link to the product list filtered to one notify batch (``?<param>=``).

    With ``brand_ids`` the link also carries the recipient's brands, so it opens on exactly
    the subset their message counted.
    """
    link = f"{_frontend_base()}/master-data-management/products?{param}={batch_id}"
    if brand_ids:
        link += f"&brand_id={','.join(brand_ids)}"
    return link


def _plural(n: int) -> str:
    return "" if n == 1 else "s"


class Recipient(NamedTuple):
    """A candidate recipient as plain values, deliberately NOT an ORM ``User``.

    Every company batch commits the stamp before it sends, and every send commits again
    inside ``create_with_channel_preferences``; a commit expires every instance in the
    session, so an attribute read on a ``User`` held across one is a fresh SELECT, once per
    recipient. Reading the three columns we need at load time keeps the fan-out free of
    per-recipient reloads.
    """

    id: str
    name: Optional[str]
    email: Optional[str]


@dataclass(frozen=True)
class MessageContext:
    """Everything a spec's message builder may read, for one recipient's slice."""

    items: list  # the spec's snapshots, already narrowed to this recipient's scopes
    batch_id: str
    link: str
    company_name: Optional[str]
    prefix: str  # "<Company>: " when the run spans companies, else ""
    scope_label: str  # " for <Company>" likewise
    today_date: str  # Malaysia local date, DD/MM/YYYY


@dataclass(frozen=True)
class Message:
    title: str
    body: str
    whatsapp_text: str
    context_vars: dict  # WhatsApp template vars, before contact_name is merged on
    data: dict  # extra notification ``data`` keys (whatsapp_* are added by the runner)


@dataclass(frozen=True)
class WatchedField:
    notify_type: str  # notification type AND WhatsApp use case
    source_entity_type: str
    event_type: str
    email_pref: str
    whatsapp_pref: str
    link_param: str
    pending: Callable[[Session], list]
    snapshot: Callable[[Session, list], list]  # ORM rows -> plain values with ``brand_id``
    # (row, its snapshot, now, batch_id). Stamp from the SNAPSHOT, never from a live column:
    # after the first company's commit every row is expired, and a re-read would pick up a
    # change made since the message was composed and mark it reported unseen.
    stamp: Callable[[Any, Any, datetime, str], None]
    build_message: Callable[[MessageContext], Message]
    prepare: Optional[Callable[[Session], None]] = None


def _load_recipient_scopes(db: Session, spec: WatchedField) -> tuple[list[Recipient], dict[str, list]]:
    """Candidate recipients (either toggle on, not trashed) and their scope rows.

    Loaded ONCE per run and shared by every company batch. Scopes are raw
    ``(company_id, brand_id)`` pairs matched against values already held: no Brand query,
    which matters because brands are company-scoped and this runs under whatever scope the
    scheduled task carries.
    """
    users = [
        Recipient(str(row[0]), row[1], row[2])
        for row in db.query(User.id, User.name, User.email)
        .filter(
            User.is_trashed.is_(False),
            or_(
                getattr(User, spec.email_pref).is_(True),
                getattr(User, spec.whatsapp_pref).is_(True),
            ),
        )
        .all()
    ]
    scopes: dict[str, list] = {}
    if users:
        rows = (
            db.query(
                UserProductDiscontinuedScope.user_id,
                UserProductDiscontinuedScope.company_id,
                UserProductDiscontinuedScope.brand_id,
            )
            .filter(UserProductDiscontinuedScope.user_id.in_([u.id for u in users]))
            .all()
        )
        for user_id, company_id, brand_id in rows:
            scopes.setdefault(str(user_id), []).append(
                (
                    str(company_id) if company_id is not None else None,
                    str(brand_id) if brand_id is not None else None,
                )
            )
    return users, scopes


def subset_for_scopes(
    scopes: list, company_id: Optional[str], pending: list
) -> tuple[list, list[str]]:
    """The products of one company's batch this recipient is responsible for.

    Returns ``(products, brand_ids_for_link)``. An all-brands scope for the company (or an
    all-companies scope) takes the whole batch with no brand filter on the link. Otherwise
    the subset is the products whose brand the recipient named.

    The link only ever carries the brands actually PRESENT in that subset, and none at all
    when the subset is the whole batch: naming brands the batch does not contain would make
    a longer link that filters nothing, and a recipient who ticked every brand of a big
    catalogue could push the WhatsApp body past its 4096-character limit.

    A product with no brand reaches only all-brands scopes: an unbranded product is not
    brand X. ``pending`` is plain snapshots (anything with ``brand_id``), never ORM rows.
    """
    relevant = [s for s in scopes if s[0] is None or s[0] == company_id]
    if not relevant:
        return [], []
    if any(brand_id is None for _, brand_id in relevant):
        return list(pending), []

    wanted = {brand_id for _, brand_id in relevant if brand_id}
    subset = [p for p in pending if getattr(p, "brand_id", None) and str(p.brand_id) in wanted]
    if len(subset) == len(pending):
        return subset, []
    return subset, sorted({str(p.brand_id) for p in subset})


def run_watched_field_check(db: Session, spec: WatchedField, task: Any = None) -> dict:
    """Scheduled-task entry point for one watched field.

    WHICH companies this reports on is decided by the scheduler (the task's
    ``metadata.company_ids`` scope is applied to the session). What IS decided here is the
    batching: one batch per company.
    """
    from app.models.company import Company

    if spec.prepare is not None:
        spec.prepare(db)

    pending = spec.pending(db)
    by_company: dict[Optional[str], list] = {}
    for p in pending:
        by_company.setdefault(getattr(p, "company_id", None), []).append(p)
    # Snapshot taken here, before ANY commit: the first company's stamp commit expires
    # every instance in the session, including the other companies' rows.
    snapshot_by_company = {cid: spec.snapshot(db, rows) for cid, rows in by_company.items()}

    names = {}
    ids = [c for c in by_company if c]
    if ids:
        names = {c.id: c.name for c in db.query(Company).filter(Company.id.in_(ids)).all()}
    # Name the company in the copy only when this run actually spans more than one.
    label_with_company = len(by_company) > 1

    candidates, scopes_by_user = _load_recipient_scopes(db, spec) if by_company else ([], {})

    runs = [
        _run_for_company(
            db,
            spec,
            cid,
            names.get(cid),
            label_with_company,
            rows,
            snapshot_by_company[cid],
            candidates,
            scopes_by_user,
        )
        for cid, rows in by_company.items()
    ]
    if not runs:
        return {"pending": 0, "subscribers": 0, "notified_users": 0, "batch_id": None, "companies": []}
    return {
        "pending": sum(r["pending"] for r in runs),
        "subscribers": max((r["subscribers"] for r in runs), default=0),
        "notified_users": sum(r["notified_users"] for r in runs),
        "batch_id": runs[0]["batch_id"] if len(runs) == 1 else None,
        "companies": runs,
    }


def _run_for_company(
    db: Session,
    spec: WatchedField,
    company_id: Optional[str],
    company_name: Optional[str],
    label_with_company: bool,
    pending: list,
    pending_snapshot: list,
    candidates: list[Recipient],
    scopes_by_user: dict[str, list],
) -> dict:
    now = datetime.utcnow()
    batch_id = str(uuid.uuid4())
    count = len(pending)
    # Stamp FIRST and commit before any send. ``pending_snapshot`` is parallel to
    # ``pending`` (built from it, in order).
    for p, snap in zip(pending, pending_snapshot):
        spec.stamp(p, snap, now, batch_id)
    db.commit()

    prefix = f"{company_name}: " if (label_with_company and company_name) else ""
    scope_label = f" for {company_name}" if (label_with_company and company_name) else ""
    today_date = datetime.now(MALAYSIA_TZ).strftime("%d/%m/%Y")

    notified_users = 0
    subscribers = 0
    notifier = NotificationService(db)
    for user in candidates:
        subset, brand_ids = subset_for_scopes(
            scopes_by_user.get(user.id, []), company_id, pending_snapshot
        )
        # Nothing of theirs in this batch: no in-app row, no delivery, no noise.
        if not subset:
            continue
        subscribers += 1

        msg = spec.build_message(
            MessageContext(
                items=subset,
                batch_id=batch_id,
                link=batch_link(spec.link_param, batch_id, brand_ids),
                company_name=company_name,
                prefix=prefix,
                scope_label=scope_label,
                today_date=today_date,
            )
        )

        # Best-effort per recipient: one failure must never abort the rest, and the batch
        # is already stamped. (create_with_channel_preferences commits internally, so the
        # except rollback only discards the failing iteration's own partial flush.)
        try:
            # contact_name is the RECIPIENT (staff), so it varies per subscriber.
            recipient_name = (user.name or user.email or "there").strip() or "there"
            notifier.create_with_channel_preferences(
                user_id=user.id,
                type=spec.notify_type,
                title=msg.title,
                body=msg.body,
                data={
                    **msg.data,
                    "whatsapp_use_case": spec.notify_type,
                    "whatsapp_text": msg.whatsapp_text,
                    "whatsapp_context_vars": {**msg.context_vars, "contact_name": recipient_name},
                },
                source_entity_type=spec.source_entity_type,
                source_entity_id=batch_id,
                event_type=spec.event_type,
                send_in_app=True,
                send_email=True,
                send_whatsapp=True,
                email_pref_attr=spec.email_pref,
                whatsapp_pref_attr=spec.whatsapp_pref,
            )
            notified_users += 1
        except Exception as e:  # noqa: BLE001 - best-effort fan-out
            db.rollback()
            logger.warning(
                "%s notify failed for user %s (batch %s): %s",
                spec.notify_type,
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


# --------------------------------------------------------------------------- discontinued


class PendingProduct(NamedTuple):
    """A discontinued product as plain values. The brand is the only column the matching
    needs: the company is the batch's own and the message carries a count."""

    brand_id: Optional[str]


def _discontinued_pending(db: Session) -> list:
    # Level-triggered: a product discontinued then reverted before this tick has
    # is_discontinued=False and drops out on its own.
    return (
        db.query(Product)
        .filter(Product.is_discontinued.is_(True), Product.discontinued_notified_at.is_(None))
        .all()
    )


def _discontinued_snapshot(db: Session, rows: list) -> list:
    return [
        PendingProduct(str(p.brand_id) if getattr(p, "brand_id", None) is not None else None)
        for p in rows
    ]


def _discontinued_stamp(p: Any, snap: Any, now: datetime, batch_id: str) -> None:
    p.discontinued_notified_at = now
    p.discontinued_notify_batch_id = batch_id


def _discontinued_message(ctx: MessageContext) -> Message:
    n = len(ctx.items)
    title = f"{ctx.prefix}{n} product{_plural(n)} discontinued"
    body = (
        f"{n} product{_plural(n)}{ctx.scope_label} "
        f"{'was' if n == 1 else 'were'} newly "
        f"marked as discontinued. View the list: {ctx.link}"
    )
    wa_text = f"{ctx.prefix}{n} product{_plural(n)} discontinued. View the list: {ctx.link}"
    return Message(
        title=title,
        body=body,
        whatsapp_text=wa_text,
        context_vars={
            "discontinued_count": str(n),
            "discontinued_link": ctx.link,
            "company_name": ctx.company_name or "",
            "today_date": ctx.today_date,
            "system_url": _frontend_base(),
            # Aliased onto portal_url so templates can reuse the existing link slot.
            "portal_url": ctx.link,
            "message": wa_text,
        },
        data={
            "discontinued_count": n,
            "discontinued_batch_id": ctx.batch_id,
            "discontinued_link": ctx.link,
        },
    )


DISCONTINUED = WatchedField(
    notify_type="product_discontinued",
    source_entity_type="product_discontinued_batch",
    event_type="discontinued",
    email_pref="notify_email_on_product_discontinued",
    whatsapp_pref="notify_whatsapp_on_product_discontinued",
    link_param="discontinued_batch_id",
    pending=_discontinued_pending,
    snapshot=_discontinued_snapshot,
    stamp=_discontinued_stamp,
    build_message=_discontinued_message,
)


# --------------------------------------------------------------------------- list price

#: Lines listed in one in-app / email digest; the rest read "...and N more" + the link.
LIST_PRICE_MAX_LINES = 50


class ListPriceChange(NamedTuple):
    brand_id: Optional[str]
    code: str
    name: str
    old: Decimal
    new: Decimal
    currency: str
    changed_by: Optional[str]  # "AutoCount sync" / staff name from the audit trail, else None


#: What a list-price change made by an integration (the AutoCount push) is credited to.
SYNC_SOURCE_LABEL = "AutoCount sync"


def _list_price_sources(db: Session, rows: list) -> dict[str, str]:
    """Who changed each product's list price to the value being reported, from the audit
    trail (owner decision on #2228). Never from ``products.updated_by``: the ordinary
    AutoCount push leaves that column untouched, so it would name a stale UI editor.

    Per product, the latest ``product`` UPDATE audit row whose ``new_values`` carries
    ``list_price``. It counts only when it set the price being reported AND is newer than the
    last report; anything else (no row, e.g. a bulk Excel import that writes one coarse job
    row, or a row that predates the change) leaves the source out rather than guess.
    Integration -> ``SYNC_SOURCE_LABEL``; a staff user -> their name; other actors -> none.
    Raw SQL on purpose: filtered by the product ids already loaded, one round trip.
    """
    from sqlalchemy import bindparam, text

    if not rows:
        return {}
    by_id = {str(p.id): p for p in rows}
    audit_rows = db.execute(
        text(
            "SELECT DISTINCT ON (entity_id) entity_id, actor_type, user_id, "
            "new_values ->> 'list_price' AS new_price, changed_at "
            "FROM audit_logs "
            "WHERE entity_type = 'product' AND action = 'UPDATE' "
            "AND entity_id IN :ids AND new_values ->> 'list_price' IS NOT NULL "
            "ORDER BY entity_id, changed_at DESC"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": list(by_id)},
    ).all()

    actors: dict[str, tuple] = {}
    for entity_id, actor_type, user_id, new_price, changed_at in audit_rows:
        p = by_id.get(str(entity_id))
        if p is None:
            continue
        try:
            if Decimal(str(new_price)) != Decimal(p.list_price):
                continue
        except Exception:  # noqa: BLE001 - an unparsable audit value is no source
            continue
        notified_at = getattr(p, "list_price_notified_at", None)
        if notified_at is not None and changed_at is not None and changed_at <= notified_at:
            continue
        actors[str(entity_id)] = (actor_type, user_id)
    return audit_source_labels(db, actors)


def audit_source_labels(db: Session, actors: dict) -> dict:
    """``{key: (actor_type, user_id)}`` -> ``{key: label}`` for the keys that get one.

    The one "by <source>" rule, shared by the #2228 digest and the products list's
    list-price history lightbox: an integration -> ``SYNC_SOURCE_LABEL``; a staff user ->
    their name (else email); any other actor (scheduler, worker, legacy) -> no label."""
    sources: dict = {}
    staff: dict = {}
    for key, (actor_type, user_id) in actors.items():
        if actor_type == "integration":
            sources[key] = SYNC_SOURCE_LABEL
        elif actor_type == "user" and user_id:
            staff[key] = str(user_id)

    if staff:
        names = {
            str(uid): (name or email)
            for uid, name, email in db.query(User.id, User.name, User.email)
            .filter(User.id.in_(set(staff.values())))
            .all()
        }
        for key, uid in staff.items():
            if names.get(uid):
                sources[key] = names[uid]
    return sources


def _list_price_prepare(db: Session) -> None:
    """A product with no baseline yet (a new insert) adopts its current price silently:
    a new product is not a price change.

    Loaded through an ORM SELECT rather than a bulk UPDATE on purpose: the company scope
    the scheduler applies to the session filters SELECTs only, so a bulk UPDATE would
    write to every company's products whatever the task's ``company_ids`` say."""
    rows = db.query(Product).filter(Product.list_price_notified.is_(None)).all()
    for p in rows:
        p.list_price_notified = p.list_price
    if rows:
        db.commit()


def _list_price_pending(db: Session) -> list:
    # A change reverted before the tick (A -> B -> A) equals its watermark and drops out.
    return (
        db.query(Product)
        .filter(
            Product.list_price_notified.isnot(None),
            Product.list_price != Product.list_price_notified,
        )
        .order_by(Product.product_code)
        .all()
    )


def _list_price_snapshot(db: Session, rows: list) -> list:
    sources = _list_price_sources(db, rows)
    return [
        ListPriceChange(
            brand_id=str(p.brand_id) if getattr(p, "brand_id", None) is not None else None,
            code=p.product_code,
            name=p.product_name or "",
            old=Decimal(p.list_price_notified),
            new=Decimal(p.list_price),
            currency=p.currency or "MYR",
            changed_by=sources.get(str(p.id)),
        )
        for p in rows
    ]


def _list_price_stamp(p: Any, snap: ListPriceChange, now: datetime, batch_id: str) -> None:
    # The price the message reports, not ``p.list_price``: see ``WatchedField.stamp``.
    p.list_price_notified = snap.new
    p.list_price_notified_at = now
    p.list_price_notify_batch_id = batch_id


def _money(currency: str, amount: Decimal) -> str:
    label = "RM" if currency == "MYR" else currency
    return f"{label} {amount:,.2f}"


def _pct(old: Decimal, new: Decimal) -> str:
    if old == 0:
        return "new price"
    pct = (new - old) / old * 100
    return f"{pct:+.1f}%"


def list_price_line(c: ListPriceChange) -> str:
    line = (
        f"{c.code} {c.name}: {_money(c.currency, c.old)} -> {_money(c.currency, c.new)} "
        f"({_pct(c.old, c.new)})"
    )
    if c.changed_by:
        line += f", by {c.changed_by}"
    return line


def _list_price_message(ctx: MessageContext) -> Message:
    n = len(ctx.items)
    headline = f"List price changed for {n} product{_plural(n)}"
    lines = [f"- {list_price_line(c)}" for c in ctx.items[:LIST_PRICE_MAX_LINES]]
    if n > LIST_PRICE_MAX_LINES:
        lines.append(f"...and {n - LIST_PRICE_MAX_LINES} more")
    body = (
        f"{headline}{ctx.scope_label} ({ctx.today_date}):\n"
        + "\n".join(lines)
        + f"\nView the list: {ctx.link}"
    )
    # WhatsApp carries the count and the link only (template length).
    wa_text = f"{ctx.prefix}{headline} ({ctx.today_date}). View the list: {ctx.link}"
    return Message(
        title=f"{ctx.prefix}{headline}",
        body=body,
        whatsapp_text=wa_text,
        context_vars={
            "list_price_count": str(n),
            "list_price_link": ctx.link,
            "company_name": ctx.company_name or "",
            "today_date": ctx.today_date,
            "system_url": _frontend_base(),
            "portal_url": ctx.link,
            "message": wa_text,
        },
        data={
            "list_price_count": n,
            "list_price_batch_id": ctx.batch_id,
            "list_price_link": ctx.link,
            # The generic email template renders data["link"] as its button.
            "link": ctx.link,
        },
    )


LIST_PRICE = WatchedField(
    notify_type="product_list_price_changed",
    source_entity_type="product_list_price_batch",
    event_type="list_price_changed",
    email_pref="notify_email_on_product_list_price",
    whatsapp_pref="notify_whatsapp_on_product_list_price",
    link_param="list_price_batch_id",
    pending=_list_price_pending,
    snapshot=_list_price_snapshot,
    stamp=_list_price_stamp,
    build_message=_list_price_message,
    prepare=_list_price_prepare,
)
