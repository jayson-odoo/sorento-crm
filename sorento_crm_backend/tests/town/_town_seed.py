"""Shared seeds for the SORENTO-TOWN Phase 0 red tests (not a test module).

Contract: `documentation/plans/dashboard/PLAN-sorento-town-08nov.md` section "Phase 0 contract".
Every row is seeded by the caller (CI's database is empty); codes carry the `ZZT` prefix.
"""
from __future__ import annotations

import copy
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa

from app.main import app  # noqa: F401  (import order: resolves the guards cycle)
from app.models.finance import BillingDocument, BillingDocumentLine
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.sales import invoiced_sales as inv
from tests._sales_unified_seed import cust, doc, line, so

D = Decimal
MYT = timezone(timedelta(hours=8))
DAY = date(2026, 11, 3)
NOW = datetime(2026, 11, 3, 15, 42, tzinfo=MYT)

AMOUNT_KEYS = {"amount", "today_amount", "ninety_day_amount"}


def myt(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=MYT)


def dealer_doc(db, customer, net: str, when: date, kind: str = "invoice", company_id: str = DEFAULT_COMPANY_ID):
    """A posted document whose line transfers from a retail sales order, so its sales type is
    Dealer (`invoiced_sales.sales_type()`)."""
    header, _ = so(db, demand_class="retail", customer=customer, company_id=company_id)
    return doc(
        db, kind, net, when, customer=customer, company_id=company_id,
        lines=[line(net=net, from_type="SO", from_no=header.so_number)],
    )


def project_doc(db, customer, net: str, when: date, company_id: str = DEFAULT_COMPANY_ID):
    header, _ = so(db, demand_class="project", customer=customer, company_id=company_id)
    return doc(
        db, "invoice", net, when, customer=customer, company_id=company_id,
        lines=[line(net=net, from_type="SO", from_no=header.so_number)],
    )


# ----------------------------------------------------------- independent expectations


def report_total(db, day: date, company_id: str = DEFAULT_COMPANY_ID) -> Decimal:
    """The Invoiced report's figure for one day: the shared header expression, not the town's code."""
    value = db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(inv.signed_amount()), 0)).where(
            inv.posted(), BillingDocument.doc_date == day, BillingDocument.company_id == company_id
        )
    ).scalar_one()
    return D(value).quantize(D("0.01"))


def line_total(db, day: date, company_id: str = DEFAULT_COMPANY_ID) -> Decimal:
    """The same day from the LINES, subtotal lines excluded (`counted_line()`)."""
    value = db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(inv.signed_line_amount()), 0))
        .select_from(BillingDocumentLine)
        .join(BillingDocument, BillingDocument.id == BillingDocumentLine.document_id)
        .where(
            inv.posted(), inv.counted_line(), BillingDocument.doc_date == day,
            BillingDocument.company_id == company_id,
        )
    ).scalar_one()
    return D(value).quantize(D("0.01"))


# ------------------------------------------------------------------ a stored snapshot


def fake_full(day: date = DAY, company_id: str = DEFAULT_COMPANY_ID, *, phase: str = "day") -> dict:
    """A well-formed full snapshot (schema 1) with RM figures a leak test can search for."""
    return {
        "schema": 1,
        "company_id": company_id,
        "day": day.isoformat(),
        "as_of": "2026-11-03T15:42:00+08:00",
        "data_as_of": None,
        "phase": phase,
        "today": {"amount": "671985.50", "invoice_count": 237, "credit_note_count": 1, "customer_count": 110},
        "shops": [
            {"key": str(uuid.uuid4()), "code": "ZZT-S001", "name": "ZZT Tiling One SDN BHD [A/C III]",
             "account_label": "A/C III", "kind": "shop", "rank": 1,
             "ninety_day_amount": "148214.94", "today_amount": "27028.40", "today_docs": 3},
            {"key": str(uuid.uuid4()), "code": "ZZT-S002", "name": "ZZT Tiling Two SDN BHD",
             "account_label": None, "kind": "shop", "rank": 2,
             "ninety_day_amount": "90111.11", "today_amount": "0.00", "today_docs": 0},
            {"key": str(uuid.uuid4()), "code": "ZZT-S099", "name": "ZZT Stall Three",
             "account_label": None, "kind": "stall", "rank": None,
             "ninety_day_amount": "512.25", "today_amount": "333.33", "today_docs": 1},
        ],
        "warehouses": [{"pool": "ZZT-BRW", "on_hand": 901681, "available": 900000, "locations": 24}],
        "reorder": {"below_count": 1749, "set_count": 11307},
        "approvals": {"total": 1, "purchase_requests": 1, "quotation_documents": 0},
    }


#: RM figures in `fake_full` that must never reach a redacted body.
FAKE_RM_FIGURES = ("671985.50", "148214.94", "27028.40", "90111.11", "512.25", "333.33")


def all_keys(node) -> set:
    found: set = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            found |= all_keys(value)
    elif isinstance(node, list):
        for item in node:
            found |= all_keys(item)
    return found


def deep(node):
    return copy.deepcopy(node)
