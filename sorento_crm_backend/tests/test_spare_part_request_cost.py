"""SPARE-PART-ORDER-REQUEST fix round 1, G8 (crew ruling (b), price visibility), red-first.

A spare part request's unit price and totals are the EXPECTED SUPPLIER COST. Visible to the
request's requester and to anyone who can decide on it, always; to everyone else only with
`products.cost.view` (`app/services/cost_access.py`, no new permission). Masked = null in
payloads; "hidden" in History.

Fields: SPR detail `lines[].unit_price / total / requested_unit_price` and `total`; worklist
(Lines tab) rows `unit_price / line_total / submitted_unit_price`; the header detail carries no
price (any price key it grows must mask too); the Lines export (`GET /order-inquiries/export`).

History NAMED CHOICE: the approver's unit price change is audited under the COST key
`unit_cost` (in `COST_AUDIT_KEYS`), so the shared `/audit-logs` masking and the OI History
reader both hide it; the global `unit_price` key is NOT masked (quotations use it for the
selling price).

Harness: the world's actor override is replaced with an ASYNC one that stamps cost visibility
exactly like `app.dependencies._stamped` (a sync override never stamps, so every reader would
see cost and the test would prove nothing).
"""
from __future__ import annotations

import io
from decimal import Decimal

import pytest

from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    HEADERS,
    SPR,
    VIEW,
    WORKLIST,
    approve,
    create,
    dec,
    raised,
    reload,
    role_grant,
    row_for,
    sent,
    staged,
    submitted,
    svc,
    user,
    world,
)

COST = "products.cost.view"
PRICES = {Decimal("25"), Decimal("12.5"), Decimal("250"), Decimal("50"), Decimal("300"), Decimal("27.5")}


@pytest.fixture
def costed(staged):
    """Staged world + a cost-viewing purchasing user and a plain viewer; auth stamps cost."""
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.cost_access import stamp_cost_visibility

    w = staged
    w.cost_buyer = user(w.db, "spr purchasing with cost")
    role_grant(
        w.db, w.cost_buyer, VIEW, "projects.order_inquiry.action", "projects.order_inquiries.acknowledge", COST,
        role_slug=f"purchasing-zzt-cost-{w.cost_buyer[:6]}",
    )
    w.viewer = user(w.db, "spr viewer without cost")
    role_grant(w.db, w.viewer, VIEW)
    w.db.commit()

    async def actor():
        current = {"id": w.state["user"], "email": f"{w.state['user']}@zzt.test", "role": "staff"}
        stamp_cost_visibility(w.db, current)
        return current

    app.dependency_overrides[get_current_user] = actor
    app.dependency_overrides[get_current_user_or_api_key] = actor
    return w


def _detail(w, user_id, inquiry) -> dict:
    res = w.as_user(user_id).get(f"{SPR}/{inquiry.id}")
    assert res.status_code == 200, res.text
    return res.json()


def _worklist(w, user_id, inquiry) -> list:
    res = w.as_user(user_id).get(WORKLIST, params={"inquiry_id": str(inquiry.id), "limit": 100})
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _line(lines, product) -> dict:
    return next(item for item in lines if item["product_id"] == str(product.id))


def _assert_prices_shown(detail, rows, product) -> None:
    line = _line(detail["lines"], product)
    assert dec(line["unit_price"]) == Decimal("25")
    assert dec(line["total"]) == Decimal("250")
    assert dec(detail["total"]) == Decimal("300")
    row = _line(rows, product)
    assert dec(row["unit_price"]) == Decimal("25")
    assert dec(row["line_total"]) == Decimal("250")


# (1) -------------------------------------------------------------------------


def test_G8_purchasing_with_cost_view_sees_unit_price_and_total(costed):
    w = costed
    done = raised(w)
    _assert_prices_shown(_detail(w, w.cost_buyer, done), _worklist(w, w.cost_buyer, done), w.product_a)


# (2) -------------------------------------------------------------------------


def test_G8_a_viewer_without_cost_view_gets_null_prices_everywhere(costed):
    w = costed
    done = raised(w)

    detail = _detail(w, w.viewer, done)
    assert detail["total"] is None
    for line in detail["lines"]:
        assert line["unit_price"] is None
        assert line["total"] is None
        assert line["requested_unit_price"] is None
        assert line["qty"] is not None, "only the money is masked"

    for row in _worklist(w, w.viewer, done):
        assert row["unit_price"] is None
        assert row["line_total"] is None
        assert row["submitted_unit_price"] is None

    res = w.as_user(w.viewer).get(f"{HEADERS}/{done.id}")
    assert res.status_code == 200, res.text
    for key in ("total", "request_total", "unit_price", "line_total"):
        if key in res.json():
            assert res.json()[key] is None, key


def test_G8_the_lines_export_carries_no_price_for_a_viewer_without_cost_view(costed):
    from openpyxl import load_workbook

    w = costed
    done = raised(w)
    res = w.as_user(w.viewer).get(f"{WORKLIST}/export", params={"inquiry_id": str(done.id)})
    assert res.status_code == 200, res.text
    book = load_workbook(io.BytesIO(res.content), read_only=True)
    cells = [c for sheet in book.worksheets for r in sheet.iter_rows(values_only=True) for c in r]
    leaked = [c for c in cells if isinstance(c, (int, float, Decimal)) and Decimal(str(c)) in PRICES]
    assert w.product_a.product_code in {str(c) for c in cells}, "the export holds the rows"
    assert leaked == []


# (3) -------------------------------------------------------------------------


def test_G8_the_requester_without_cost_view_sees_their_own_prices(costed):
    w = costed
    draft = create(w)
    line = _line(_detail(w, w.requester, draft)["lines"], w.product_a)
    assert dec(line["unit_price"]) == Decimal("25") and dec(line["total"]) == Decimal("250")
    done = raised(w)
    detail = _detail(w, w.requester, done)
    assert dec(_line(detail["lines"], w.product_a)["unit_price"]) == Decimal("25")
    assert dec(detail["total"]) == Decimal("300")


# (4) -------------------------------------------------------------------------


def test_G8_the_stage_approver_without_cost_view_sees_prices_while_deciding(costed):
    w = costed
    pending = submitted(w)
    _assert_prices_shown(
        _detail(w, w.stage1.tier1, pending), _worklist(w, w.stage1.tier1, pending), w.product_a
    )
    row = _line(_worklist(w, w.stage1.tier1, pending), w.product_a)
    assert dec(row["submitted_unit_price"]) == Decimal("25")


# (5) -------------------------------------------------------------------------


def _price_change(w):
    pending = submitted(w)
    row = row_for(w.db, pending, w.product_a)
    svc().edit_line(w.db, pending, row.id, w.stage1.tier1, unit_price="27.50")
    w.db.commit()
    return approve(w, reload(w.db, pending), w.stage1.tier1)


def test_G8_the_price_change_is_audited_under_a_cost_key(costed):
    from app.models.audit import AuditLog
    from app.services.cost_access import COST_AUDIT_KEYS

    w = costed
    done = _price_change(w)
    w.db.expire_all()
    audits = [
        a for a in w.db.query(AuditLog).filter(AuditLog.entity_id == str(done.id)).all()
        if a.event == "SPR_LINE_CHANGED"
    ]
    assert audits, "the approver's price change is on History"
    assert "unit_cost" in COST_AUDIT_KEYS
    assert any("unit_cost" in (a.new_values or {}) for a in audits), [a.new_values for a in audits]
    assert not any("unit_price" in (a.new_values or {}) for a in audits), "never the selling-price key"


def test_G8_history_shows_the_price_change_to_a_cost_viewer_and_hidden_to_others(costed):
    w = costed
    done = _price_change(w)

    shown = w.as_user(w.cost_buyer).get(f"{HEADERS}/{done.id}/history")
    assert shown.status_code == 200, shown.text
    assert "27.5" in shown.text and "25" in shown.text

    masked = w.as_user(w.viewer).get(f"{HEADERS}/{done.id}/history")
    assert masked.status_code == 200, masked.text
    assert "27.5" not in masked.text
    assert "hidden" in masked.text


def test_G8_the_shared_audit_log_reader_masks_it_too(costed):
    w = costed
    done = _price_change(w)
    params = {"entity_type": "project_order_inquiries", "entity_id": str(done.id)}
    control = w.as_user(w.admin).get("/api/v1/audit/logs/", params=params)
    assert control.status_code == 200, control.text
    assert "27.5" in control.text, "positive control: the reader returns this change at all"
    res = w.as_user(w.viewer).get("/api/v1/audit/logs/", params=params)
    if res.status_code == 403:
        pytest.skip("the viewer cannot read /audit-logs at all, so nothing leaks there")
    assert "27.5" not in res.text
