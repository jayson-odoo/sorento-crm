"""SORENTO-TOWN snapshot: the figures, the Redis store, and the scheduler tick.

Plan: documentation/plans/dashboard/PLAN-sorento-town-08nov.md ("Phase 0 contract").
The tick builds one FULL snapshot per active company every few minutes and stores it (and its
amount-free twin) in Redis; the route serves those bytes and reads no business table. Sales
figures come from `services/sales/invoiced_sales.py` only: the sign, the posted rule and the
sales type are never re-derived here.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.finance import CREDIT_NOTE, BillingDocument
from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseRequestHeader
from app.models.product import Product
from app.models.projects import ProjectQuotationDocument
from app.models.scm import ReorderLevel
from app.models.status import Status
from app.models.town import TownDay
from app.scheduler.task_scheduler import scheduler_session
from app.services.sales import invoiced_sales as inv

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
MYT = timezone(timedelta(hours=8))
TTL_SECONDS = 36 * 3600
SHOP_LIMIT = 30
WINDOW_DAYS = 90
LOCK_KEY = "town:lock"
LOCK_SECONDS = 240
# Compare-and-delete: only the run that took the lock may drop it.
_RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0"
STATEMENT_TIMEOUT_MS = 5000
RANKING_TIMEOUT_MS = 30000
FAILED_RANKING_TTL_SECONDS = 30 * 60
OPEN_MINUTE = 7 * 60
NIGHT_MINUTE = 22 * 60
CLOSE_MINUTE = 22 * 60 + 5

_LABEL_RE = re.compile(r"\[(A/C[^\]]*)\]\s*$")
_QUOTATION_PENDING_KEYS = ("pending_approval", "resubmitted")


def _money(value: Any) -> str:
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


# ------------------------------------------------------------------------------ the figures


def _account_label(name: Optional[str]) -> Optional[str]:
    match = _LABEL_RE.search(name or "")
    return match.group(1).strip() if match else None


_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _today_and_compare(db: Session, company_id: str, day: date) -> tuple:
    """Today's figures and the same weekday last week, from one query over the two days. Last week is
    the whole day by document date, with the same expressions as today: AutoCount gives no document
    time, and `created_at` is when the CRM received the document, so it cannot cut the day."""
    week_ago = day - timedelta(days=7)
    sales_type = inv.document_sales_type()
    today = BillingDocument.doc_date == day
    last = BillingDocument.doc_date == week_ago
    not_credit = BillingDocument.document_type != CREDIT_NOTE
    row = db.execute(
        sa.select(
            sa.func.coalesce(sa.func.sum(inv.signed_amount()).filter(today), 0),
            sa.func.count().filter(today, not_credit),
            sa.func.count().filter(today, BillingDocument.document_type == CREDIT_NOTE),
            sa.func.count(sa.distinct(BillingDocument.customer_id)).filter(today),
            sa.func.count(sa.distinct(BillingDocument.customer_id)).filter(today, sales_type.c.value == inv.DEALER),
            sa.func.coalesce(sa.func.sum(inv.signed_amount()).filter(last), 0),
            sa.func.count().filter(last, not_credit),
        )
        .select_from(BillingDocument)
        .join(sales_type, sa.true(), isouter=True)
        .where(
            inv.posted(), BillingDocument.company_id == company_id,
            BillingDocument.doc_date.in_([day, week_ago]),
        )
    ).one()
    figures = {
        "amount": _money(row[0]),
        "invoice_count": int(row[1]),
        "credit_note_count": int(row[2]),
        "customer_count": int(row[3]),
        "dealer_customer_count": int(row[4]),
    }
    compare = {
        "label": f"{_WEEKDAYS[week_ago.weekday()]} {week_ago.day} {_MONTHS[week_ago.month - 1]}",
        "last_week_amount": _money(row[5]),
        "last_week_invoice_count": int(row[6]),
    }
    return figures, compare


def _deliveries(db: Session, company_id: str, day: date) -> dict:
    """Sales orders still owing goods that are due today or overdue (a count only)."""
    due = sa.func.coalesce(SalesOrderLine.required_date, SalesOrder.requested_delivery_date)
    count = db.execute(
        sa.select(sa.func.count(sa.distinct(SalesOrderLine.sales_order_id)))
        .select_from(SalesOrderLine)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .where(
            SalesOrder.company_id == company_id,
            SalesOrderLine.line_status == "open",
            SalesOrderLine.qty_ordered - SalesOrderLine.qty_delivered > 0,
            due <= day,
        )
    ).scalar_one()
    return {"to_deliver": int(count)}


def _dealer_rows(db: Session, company_id: str, since: date, until: date, *, today: Optional[date]) -> list:
    """Dealer-type customers (one row per AutoCount account) over `since..until`: id, code, name,
    signed amount, and, when `today` is given, that day's amount and document count. The sales
    type is computed once per document (`document_sales_type()`), then aggregated."""
    sales_type = inv.document_sales_type()
    on_day = BillingDocument.doc_date == today
    return db.execute(
        sa.select(
            Customer.id,
            Customer.customer_code,
            sa.func.coalesce(Customer.customer_name, sa.func.max(BillingDocument.customer_name)),
            sa.func.sum(inv.signed_amount()),
            sa.func.coalesce(sa.func.sum(inv.signed_amount()).filter(on_day), 0),
            sa.func.count().filter(on_day),
        )
        .select_from(BillingDocument)
        .join(Customer, Customer.id == BillingDocument.customer_id)
        .join(sales_type, sa.true(), isouter=True)
        .where(
            inv.posted(),
            BillingDocument.company_id == company_id,
            BillingDocument.doc_date >= since,
            BillingDocument.doc_date <= until,
            sales_type.c.value == inv.DEALER,
        )
        .group_by(Customer.id, Customer.customer_code, Customer.customer_name)
    ).all()


def compute_ranking(db: Session, company_id: str, day: date) -> list:
    """The top 30 Dealer-type accounts by invoiced sales over the 90 days ending `day`, ties by
    code. The heavy query: it runs once per company per day (`ranking_for`), with 30 s allowed."""
    previous = db.execute(sa.text("SHOW statement_timeout")).scalar() or "0"
    db.execute(sa.text(f"SET LOCAL statement_timeout = {RANKING_TIMEOUT_MS}"))
    rows = _dealer_rows(db, company_id, day - timedelta(days=WINDOW_DAYS - 1), day, today=None)
    # RELEASE of the caller's savepoint keeps a SET LOCAL, so the success path restores it itself;
    # a failure rolls the savepoint back, which undoes it.
    db.execute(sa.text("SELECT set_config('statement_timeout', :v, true)"), {"v": str(previous)})
    ranked = sorted(rows, key=lambda r: (-Decimal(r[3] or 0), r[1] or ""))[:SHOP_LIMIT]
    return [
        {
            "key": str(key), "code": code, "name": name, "account_label": _account_label(name),
            "rank": index + 1, "ninety_day_amount": _money(ninety),
        }
        for index, (key, code, name, ninety, _a, _d) in enumerate(ranked)
    ]


def store_ranking(redis: Any, company_id: str, day: date, ranking: list, ttl: int = TTL_SECONDS) -> None:
    redis.set(_key(company_id, day, "ranking"), _gzip_json(ranking), ex=ttl)


def load_ranking(redis: Any, company_id: str, day: date) -> Optional[list]:
    raw = redis.get(_key(company_id, day, "ranking"))
    return None if raw is None else json.loads(gzip.decompress(raw))


def ranking_for(db: Session, company_id: str, day: date) -> list:
    """The day's ranking from Redis, computed and cached when the day's first build finds none.
    A failed ranking (the 30 s query timing out) leaves the town with today's figures and stalls
    only, and an empty ranking is cached for 30 minutes so the next ticks do not rerun it."""
    from app.services.queue_service import redis_conn

    ranking = load_ranking(redis_conn, company_id, day)
    if ranking is not None:
        return ranking
    try:
        with db.begin_nested():
            ranking = compute_ranking(db, company_id, day)
    except Exception:  # noqa: BLE001 - the town still shows today without a ranking
        logger.exception("town ranking failed for company %s", company_id)
        store_ranking(redis_conn, company_id, day, [], ttl=FAILED_RANKING_TTL_SECONDS)
        return []
    store_ranking(redis_conn, company_id, day, ranking)
    return ranking


def _shops(db: Session, company_id: str, day: date) -> list:
    """The cached top 30 (shops) carrying today's figures, then a stall for every other Dealer-type
    account invoiced today. Only today's documents pay for the sales type here."""
    ranking = ranking_for(db, company_id, day)
    today = {
        str(key): (code, name, amount, docs)
        for key, code, name, _ninety, amount, docs in _dealer_rows(db, company_id, day, day, today=day)
    }
    out = []
    for entry in ranking:
        _code, _name, amount, docs = today.get(entry["key"], (None, None, 0, 0))
        out.append({**entry, "kind": "shop", "today_amount": _money(amount), "today_docs": int(docs)})
    ranked_keys = {e["key"] for e in ranking}
    stalls = {k: v for k, v in today.items() if k not in ranked_keys}
    for key, (code, name, amount, docs) in sorted(stalls.items(), key=lambda kv: kv[1][0] or ""):
        out.append({
            "key": key, "code": code, "name": name, "account_label": _account_label(name),
            "kind": "stall", "rank": None, "ninety_day_amount": None,
            "today_amount": _money(amount), "today_docs": int(docs),
        })
    return out


def _warehouses(db: Session, company_id: str) -> list:
    pool = aliased(Warehouse)
    pool_id = sa.func.coalesce(Warehouse.pool_warehouse_id, Warehouse.id)
    pool_code = sa.func.coalesce(sa.func.max(pool.warehouse_code), sa.func.max(Warehouse.warehouse_code))
    rows = db.execute(
        sa.select(
            pool_code,
            sa.func.coalesce(sa.func.sum(Stock.quantity_on_hand), 0),
            sa.func.coalesce(sa.func.sum(Stock.quantity_available), 0),
            sa.func.count(sa.distinct(Warehouse.id)),
        )
        .select_from(Warehouse)
        .join(pool, pool.id == Warehouse.pool_warehouse_id, isouter=True)
        .join(Stock, Stock.warehouse_id == Warehouse.id, isouter=True)
        .where(Warehouse.company_id == company_id, Warehouse.is_active.is_(True))
        .group_by(pool_id)
    ).all()
    return sorted(
        ({"pool": code, "on_hand": int(on_hand), "available": int(avail), "locations": int(n)}
         for code, on_hand, avail, n in rows),
        key=lambda w: w["pool"] or "",
    )


def _reorder(db: Session, company_id: str) -> dict:
    stock = aliased(Stock)
    wh = aliased(Warehouse)
    available = (
        sa.select(sa.func.coalesce(sa.func.sum(stock.quantity_available), 0))
        .select_from(stock)
        .join(wh, wh.id == stock.warehouse_id)
        .where(
            stock.product_id == ReorderLevel.product_id,
            wh.company_id == company_id,
            wh.is_active.is_(True),
            wh.counts_as_available.is_(True),
        )
        .correlate(ReorderLevel)
        .scalar_subquery()
    )
    set_count, below = db.execute(
        sa.select(sa.func.count(), sa.func.count().filter(available < ReorderLevel.level))
        .select_from(ReorderLevel)
        .join(Product, Product.id == ReorderLevel.product_id)
        .where(
            ReorderLevel.company_id == company_id,
            ReorderLevel.warehouse_id.is_(None),
            ReorderLevel.level > 0,
            Product.is_active.is_(True),
        )
    ).one()
    return {"below_count": int(below), "set_count": int(set_count)}


def _approvals(db: Session, company_id: str) -> dict:
    prs = db.execute(
        sa.select(sa.func.count()).select_from(PurchaseRequestHeader).where(
            PurchaseRequestHeader.approval_status == "pending", PurchaseRequestHeader.voided_at.is_(None)
        )
    ).scalar_one()
    quotations = db.execute(
        sa.select(sa.func.count())
        .select_from(ProjectQuotationDocument)
        .join(Status, Status.id == ProjectQuotationDocument.approval_status_id)
        .where(ProjectQuotationDocument.company_id == company_id, Status.key.in_(_QUOTATION_PENDING_KEYS))
    ).scalar_one()
    return {"total": int(prs) + int(quotations), "purchase_requests": int(prs), "quotation_documents": int(quotations)}


def build_snapshot(db: Session, company_id: str, day: date, *, now: datetime) -> dict:
    """The FULL variant (schema 1) for one company and one MYT day."""
    now_myt = now.astimezone(MYT)
    data_as_of = db.execute(
        sa.select(sa.func.max(BillingDocument.last_synced_at)).where(
            BillingDocument.company_id == company_id, BillingDocument.doc_date >= day - timedelta(days=7)
        )
    ).scalar_one()
    today, compare = _today_and_compare(db, company_id, day)
    return {
        "schema": SCHEMA_VERSION,
        "company_id": company_id,
        "day": day.isoformat(),
        "as_of": now_myt.isoformat(timespec="seconds"),
        "data_as_of": data_as_of.replace(tzinfo=timezone.utc).isoformat() if data_as_of else None,
        "phase": "night" if now_myt.hour * 60 + now_myt.minute >= NIGHT_MINUTE else "day",
        "today": today,
        "compare": compare,
        "shops": _shops(db, company_id, day),
        "warehouses": _warehouses(db, company_id),
        "reorder": _reorder(db, company_id),
        "approvals": _approvals(db, company_id),
        "deliveries": _deliveries(db, company_id, day),
    }


def day_events(db: Session, company_id: str, day: date, shop_keys: set) -> list:
    """The day's posted documents in creation order, for the replay (phase 2)."""
    rows = db.execute(
        sa.select(
            BillingDocument.created_at, BillingDocument.customer_id,
            BillingDocument.document_type, inv.signed_amount(),
        )
        .where(inv.posted(), BillingDocument.company_id == company_id, BillingDocument.doc_date == day)
        .order_by(BillingDocument.created_at, BillingDocument.id)
    ).all()
    events = []
    for created_at, customer_id, document_type, amount in rows:
        # `created_at` is a naive UTC timestamp.
        at = created_at.replace(tzinfo=timezone.utc).astimezone(MYT).strftime("%H:%M")
        key = str(customer_id) if customer_id else None
        events.append({
            "at": at,
            "shop_key": key if key in shop_keys else None,
            "kind": "credit_note" if document_type == CREDIT_NOTE else "invoice",
            "amount": _money(amount),
        })
    return events


# ---------------------------------------------------------------------- redaction and wallboard

def _opaque_keys(out: dict) -> None:
    """Replace each shop's customer id with its position, so a viewer cannot correlate customers."""
    for index, shop in enumerate(out.get("shops", []), start=1):
        shop["key"] = f"s{index}"


def redact(snapshot: dict) -> dict:
    """The variant for a user without the sales reports permission: no amount, and no dealer
    identity or ranking either (name, code, rank, customer id). Counts and kinds stay."""
    out = copy.deepcopy(snapshot)
    out.get("today", {}).pop("amount", None)
    out.get("compare", {}).pop("last_week_amount", None)
    # Not in revenue order: by kind, then today's documents, then a hash of the key. The hash is
    # the same for the same counts, so the buildings are stable between refreshes, and it is not the ranking.
    out["shops"] = sorted(
        out.get("shops", []),
        key=lambda s: (s["kind"], -s["today_docs"], hashlib.sha1(str(s["key"]).encode()).hexdigest()),
    )
    for shop in out["shops"]:
        for key in ("today_amount", "ninety_day_amount", "name", "code", "rank"):
            shop.pop(key, None)
    _opaque_keys(out)
    return out


def strip_names(snapshot: dict) -> dict:
    """Wallboard (rank numbers and the total only): no shop name, code, per-shop amount or customer
    id. Rank, label, kind and counts stay; `today.amount` follows the viewer's variant."""
    out = copy.deepcopy(snapshot)
    for shop in out.get("shops", []):
        for key in ("name", "code", "today_amount", "ninety_day_amount"):
            shop.pop(key, None)
    _opaque_keys(out)
    return out


# ------------------------------------------------------------------------------ the Redis store


def _key(company_id: str, day: date, suffix: str) -> str:
    return f"town:{company_id}:{day.isoformat()}:{suffix}"


def _gzip_json(value: dict) -> bytes:
    return gzip.compress(json.dumps(value).encode(), mtime=0)


def store(redis: Any, company_id: str, day: date, full: dict) -> str:
    """Write both variants and the version (sha1 of the full JSON, sorted keys); returns the version."""
    version = hashlib.sha1(json.dumps(full, sort_keys=True).encode()).hexdigest()
    pipe = redis.pipeline()
    pipe.set(_key(company_id, day, "full"), _gzip_json(full), ex=TTL_SECONDS)
    pipe.set(_key(company_id, day, "redacted"), _gzip_json(redact(full)), ex=TTL_SECONDS)
    pipe.set(_key(company_id, day, "version"), version, ex=TTL_SECONDS)
    pipe.execute()
    return version


def load(redis: Any, company_id: str, day: date, variant: str) -> Optional[tuple]:
    """`(gzip bytes, version)` for `variant` (`full` or `redacted`), or None when nothing is stored."""
    pipe = redis.pipeline()
    pipe.get(_key(company_id, day, variant))
    pipe.get(_key(company_id, day, "version"))
    body, version = pipe.execute()
    if body is None or version is None:
        return None
    return body, version.decode() if isinstance(version, bytes) else version


# --------------------------------------------------------------------------------- the tick

_replica_engines: dict = {}


def _replica_session() -> Session:
    url = settings.town_replica_database_url
    engine = _replica_engines.get(url)
    if engine is None:
        engine = _replica_engines[url] = sa.create_engine(url, pool_pre_ping=True)
    db = Session(bind=engine, autoflush=False)
    set_company_scope(db, None)  # explicit company filters in every query
    return db


def _replica_reachable() -> bool:
    """One cheap check per tick: a configured replica that cannot answer means this tick builds on
    the primary (one warning), instead of every company failing on the replica."""
    db = None
    try:
        db = _replica_session()
        db.execute(sa.text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - any failure to reach the replica means fall back
        logger.warning("town replica unreachable; building this tick on the primary", exc_info=True)
        return False
    finally:
        if db is not None:
            db.close()


class _build_session:
    """The session a build runs on: the read replica when configured (and `use_replica`), else the
    primary. 5 s limit."""

    def __init__(self, use_replica: bool = True) -> None:
        self._use_replica = use_replica

    def __enter__(self) -> Session:
        if self._use_replica and settings.town_replica_database_url:
            self._db, self._ctx = _replica_session(), None
        else:
            self._ctx = scheduler_session("town_snapshot")
            self._db = self._ctx.__enter__()
        self._db.execute(sa.text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
        return self._db

    def __exit__(self, *exc) -> None:
        if self._ctx is not None:
            self._ctx.__exit__(*exc)
        else:
            self._db.close()


def _freeze_day(company_id: str, day: date, snapshot: dict, events: list) -> None:
    with scheduler_session("town_day") as db:
        row = db.query(TownDay).filter(TownDay.company_id == company_id, TownDay.day == day).first()
        if row is None:
            db.add(TownDay(company_id=company_id, day=day, snapshot=snapshot, events=events))
        else:
            row.snapshot = snapshot
            row.events = events
            row.updated_at = sa.func.now()
        db.commit()


def _run_company(
    redis: Any, company_id: str, day: date, now: datetime, night: bool, use_replica: bool = True
) -> None:
    with _build_session(use_replica) as db:
        full = build_snapshot(db, company_id, day, now=now)
        events = None
        if night:
            keys = {s["key"] for s in full["shops"]}
            events = day_events(db, company_id, day, keys)
    store(redis, company_id, day, full)
    if events is not None:
        _freeze_day(company_id, day, full, events)


def run_town_snapshot_tick(now: Optional[datetime] = None) -> None:
    """Scheduler job: 07:00-22:05 MYT only; one run at a time (`town:lock`); a company that
    fails is logged and the next one still runs. From 22:00 MYT the day is also frozen."""
    from app.services.queue_service import redis_conn

    now = (now or datetime.now(MYT)).astimezone(MYT)
    minute = now.hour * 60 + now.minute
    if not OPEN_MINUTE <= minute <= CLOSE_MINUTE:
        return
    token = uuid.uuid4().hex
    if not redis_conn.set(LOCK_KEY, token, nx=True, ex=LOCK_SECONDS):
        return
    try:
        with scheduler_session("town_companies") as db:
            company_ids = [str(c) for (c,) in db.query(Company.id).filter(Company.is_active.is_(True)).all()]
        use_replica = bool(settings.town_replica_database_url) and _replica_reachable()
        for company_id in company_ids:
            try:
                _run_company(redis_conn, company_id, now.date(), now, minute >= NIGHT_MINUTE, use_replica)
            except Exception:  # noqa: BLE001 - one company must not stop the next
                logger.error("town snapshot failed for company %s", company_id, exc_info=True)
    finally:
        redis_conn.eval(_RELEASE, 1, LOCK_KEY, token)
