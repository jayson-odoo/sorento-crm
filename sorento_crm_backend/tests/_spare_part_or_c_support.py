"""Shared helpers for the SPARE-PART-OR-B C red tests (tests/test_spare_part_or_c_*.py).

Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md (C1-C5 +
Migration). Builds on `_spare_part_request_support` (the OR-B world: Form SLA stages,
requester, approver team, purchasing, products, all seeded on a `blank_session` scratch
schema). Test support only, no implementation.

NAMED CONTRACT CHOICES shared by every C file (the UAC leaves them open):

1. `spare_part_request_service.is_final_approver(db, user_id, company_id) -> bool` (C1.1).
2. A line in the request body carries `delivery_date` ("YYYY-MM-DD" or None); the header field
   stays `needed_by` on the API (C5.1 "API field name unchanged"). The OR detail line carries
   `delivery_date` too.
3. During an open revision `spare_part_request_service.update(db, inquiry, data, actor)` (the
   edit form's save) is the revision-mode save (C4.1): an existing line (by `id`) writes
   `revised_qty`, `revised_product_id`, `revised_delivery_date`; a line with no `id` is a new
   draft row; an existing live row the form no longer lists is marked to cancel (the row stays
   live for purchasing until the re-approval). `edit_line(qty=...)` keeps working for qty.
4. The `staged` world of OR-B puts the requester on stage 1's tier-2 team. With one stage that
   team IS the final level's, so under C1.1 that requester is an approver. `plain` below takes
   the requester off every team, so it is the non-approver requester of C1.4.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from ._forms_chain_support import trackers
from ._spare_part_request_support import (  # noqa: F401  (fixtures re-exported)
    KIND,
    ONE_STAGE,
    TWO_STAGES,
    add_stages,
    as_inquiry,
    body,
    line,
    make_product,
    reload,
    row_for,
    rows_of,
    sent,
    svc,
    world,
)


def drop_requester_from_teams(w) -> None:
    from app.models.access import TeamMember

    w.db.query(TeamMember).filter(TeamMember.user_id == w.requester).delete()
    w.db.commit()


@pytest.fixture
def plain(world):
    """One approval level; the requester sits on no team (a non-approver requester)."""
    add_stages(world, ONE_STAGE)
    drop_requester_from_teams(world)
    return world


@pytest.fixture
def plain_two(world):
    """Two approval levels; the requester sits on no team."""
    add_stages(world, TWO_STAGES)
    drop_requester_from_teams(world)
    return world


@pytest.fixture
def handovers(monkeypatch):
    """Every handover email item queued: (row_id, kind, was)."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    calls: list = []
    real = ProjectOrderInquiryService._record_handover

    def spy(self, row, *, kind, was=None, **kw):
        calls.append((str(row.id), kind, dict(was) if was else None))
        return real(self, row, kind=kind, was=was, **kw)

    monkeypatch.setattr(ProjectOrderInquiryService, "_record_handover", spy)
    return calls


def dated_line(product, location, qty="10", unit_price="25.00", delivery_date=None) -> dict:
    data = line(product, location, qty=qty, unit_price=unit_price)
    data["delivery_date"] = delivery_date
    return data


def create_as(w, actor, **over):
    result = svc().create(w.db, body(w, **over), actor)
    w.db.commit()
    return as_inquiry(w.db, result)


def submit_as(w, inquiry, actor):
    svc().submit(w.db, reload(w.db, inquiry), actor)
    w.db.commit()
    return reload(w.db, inquiry)


def approve_as(w, inquiry, actor):
    svc().approve(w.db, reload(w.db, inquiry), actor)
    w.db.commit()
    return reload(w.db, inquiry)


def raised_by(w, requester, approver, **over):
    inquiry = submit_as(w, create_as(w, requester, **over), requester)
    if inquiry.state != "raised":
        inquiry = approve_as(w, inquiry, approver)
    return inquiry


def revise_as(w, inquiry, actor):
    svc().revise(w.db, reload(w.db, inquiry), actor)
    w.db.commit()
    return reload(w.db, inquiry)


def change_qty(w, inquiry, product, qty, actor):
    row = row_for(w.db, inquiry, product)
    svc().edit_line(w.db, reload(w.db, inquiry), row.id, actor, qty=qty)
    w.db.commit()
    return row_for(w.db, inquiry, product)


def form_lines(w, inquiry) -> list:
    """The edit form's lines as it would send them back unchanged (ids kept)."""
    out = []
    for row in rows_of(w.db, inquiry):
        if row.state == "cancelled":
            continue
        out.append(
            {
                "id": str(row.id),
                "product_id": str(row.product_id),
                "stock_location": row.stock_location,
                "qty": str(row.qty),
                "unit_price": str(row.unit_price) if row.unit_price is not None else None,
                "delivery_date": row.delivery_date.isoformat() if row.delivery_date else None,
            }
        )
    return out


def save_form(w, inquiry, actor, lines, **header):
    inquiry = reload(w.db, inquiry)
    data = {
        "currency": inquiry.currency,
        "needed_by": inquiry.needed_by.isoformat() if inquiry.needed_by else None,
        "default_location": inquiry.default_location,
        "reason": inquiry.reason,
        "lines": lines,
    }
    data.update(header)
    svc().update(w.db, inquiry, data, actor)
    w.db.commit()
    return reload(w.db, inquiry)


def open_trackers(w, inquiry) -> list:
    return trackers(w.db, KIND, inquiry.id, open_only=True)


def audit_texts(w, inquiry) -> list:
    from app.models.audit import AuditLog

    w.db.expire_all()
    return [
        (a.event, a.description or "")
        for a in w.db.query(AuditLog).filter(
            AuditLog.entity_type == "project_order_inquiries",
            AuditLog.entity_id == str(inquiry.id),
        )
    ]


def worklist_rows(w, inquiry, user=None) -> dict:
    from ._spare_part_request_support import WORKLIST

    res = w.as_user(user or w.buyer).get(
        WORKLIST, params={"inquiry_id": str(inquiry.id), "limit": 100}
    )
    assert res.status_code == 200, res.text
    return {r["id"]: r for r in res.json()["data"]}


def header_row(w, inquiry, user=None) -> dict:
    from ._spare_part_request_support import HEADERS

    res = w.as_user(user or w.buyer).get(HEADERS, params={"state": "all", "limit": 100})
    assert res.status_code == 200, res.text
    found = [r for r in res.json()["data"] if r["id"] == str(inquiry.id)]
    assert len(found) == 1, f"the header is listed once: {found}"
    return found[0]


def dec(value) -> Decimal:
    return Decimal(str(value))
