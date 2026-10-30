"""OI-AUTO-CONFIRM slice 2: Confirm / Unconfirm stay as MANUAL OVERRIDES (AC-AC-15..17c).

Contract (fixed names): nullable `order_inquiry_rows.ack_override` ('confirmed' |
'unconfirmed' | NULL), `ack_override_by` (users.id), `ack_override_at`. The presses are the
existing `POST /order-inquiries/acknowledge` and `/unacknowledge`. Worklist rows carry
`ack_override`, `ack_override_at`, `ack_override_by_name`.

Every test reads `ack_override*` off the row, and the columns do not exist yet, so each of
these is red at the first attribute read (AttributeError), except where noted in the report.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.project_so import ACK_ACKNOWLEDGED, ACK_AWAITING, ACK_CHANGED, ACK_REJECTED
from app.models.user import User
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from .test_oi_auto_confirm import (  # noqa: F401
    HEADERS_URL,
    _header_state_of,
    _reload,
)
from .test_order_inquiry_handshake import (  # noqa: F401  (fixtures + helpers)
    LIST,
    _as_purchasing,
    _open_po_line,
    _raise_one_row,
    _settle,
    api,
    world,
)

ACK = f"{LIST}/acknowledge"
UNACK = f"{LIST}/unacknowledge"


def _press(w, url: str, row) -> object:
    with _as_purchasing(w) as buyer:
        response = buyer.post(url, json={"row_ids": [str(row.id)]})
    w.db.commit()
    return response


def _place(w, row, line, qty):
    ProjectOrderInquiryService(w.db).place_on_po_allocations(
        str(row.id), [{"po_line_id": str(line.id), "qty": str(qty)}], actor_user_id=None
    )
    w.db.commit()


def test_ac_ac_15_confirm_with_no_link_is_done_and_sticks_through_link_changes(api):
    _c, w = api
    row = _raise_one_row(api, qty="10")["row"]
    _po, line = _open_po_line(w, qty=50)

    response = _press(w, ACK, row)
    assert response.status_code == 200, response.text

    _reload(w.db, row)
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert row.ack_override == "confirmed"
    assert row.ack_override_by == w.buyer
    assert row.ack_override_at is not None

    _place(w, row, line, 10)
    ProjectOrderInquiryService(w.db).unplace(str(row.id), actor_user_id=w.buyer)
    w.db.commit()
    _reload(w.db, row)
    assert row.ack_state == ACK_ACKNOWLEDGED, "a manual Confirm sticks when the links go"
    assert row.ack_override == "confirmed"


def test_ac_ac_16_unconfirm_a_covered_row_sticks_until_a_new_link_arrives(api):
    _c, w = api
    row = _raise_one_row(api, qty="10")["row"]
    _po_a, line_a = _open_po_line(w, qty=50)
    _po_b, line_b = _open_po_line(w, qty=50)
    svc = ProjectOrderInquiryService(w.db)
    _place(w, row, line_a, 6)
    _place(w, row, line_b, 4)
    assert _reload(w.db, row).ack_state == ACK_ACKNOWLEDGED, "auto Done first"

    response = _press(w, UNACK, row)
    assert response.status_code == 200, response.text
    _reload(w.db, row)
    assert row.ack_state == ACK_AWAITING
    assert row.ack_override == "unconfirmed"

    svc.refresh_link_state([row])
    w.db.commit()
    _reload(w.db, row)
    assert row.ack_state == ACK_AWAITING, "same links: the Unconfirm holds"
    assert row.ack_override == "unconfirmed"

    # a NEW link made after the Unconfirm hands the decision back to the automatic rule
    link_b = [l for l in svc._links_of(str(row.id)) if str(l.po_line_id) == str(line_b.id)][0]
    svc.unplace(str(row.id), actor_user_id=w.buyer, link_id=str(link_b.id))
    w.db.commit()
    assert _reload(w.db, row).ack_state == ACK_AWAITING
    _po_c, line_c = _open_po_line(w, qty=50)
    _place(w, row, line_c, 4)
    _reload(w.db, row)
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert row.ack_override is None


def test_ac_ac_16_confirm_after_unconfirm_is_a_manual_confirm(api):
    _c, w = api
    row = _raise_one_row(api, qty="10")["row"]
    _po, line = _open_po_line(w, qty=50)
    _place(w, row, line, 10)
    assert _press(w, UNACK, row).status_code == 200
    assert _press(w, ACK, row).status_code == 200

    _reload(w.db, row)
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert row.ack_override == "confirmed"


def test_ac_ac_17_a_cs_amendment_clears_a_manual_override(api):
    _c, w = api
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    assert _press(w, ACK, row).status_code == 200
    assert _reload(w.db, row).ack_override == "confirmed"

    _settle(w, fixture, qty="14")

    _reload(w.db, row)
    assert row.ack_override is None
    assert row.ack_override_by is None
    assert row.ack_state == ACK_CHANGED, "not covered: the automatic rule says To order (changed)"


def test_ac_ac_17a_rejecting_clears_the_override_and_a_rejected_row_cannot_be_confirmed(api):
    _c, w = api
    row = _raise_one_row(api, qty="10")["row"]
    assert _press(w, ACK, row).status_code == 200
    assert _reload(w.db, row).ack_override == "confirmed"

    ProjectOrderInquiryService(w.db).reject_row(
        str(row.id), reason="Factory closed", actor_user_id=w.buyer
    )
    w.db.commit()
    _reload(w.db, row)
    assert row.ack_state == ACK_REJECTED
    assert row.ack_override is None

    refused = _press(w, ACK, row)
    assert refused.status_code == 422, refused.text


def test_ac_ac_17b_the_worklist_row_carries_the_manual_decision_with_a_name(api):
    c, w = api
    row = _raise_one_row(api, qty="10")["row"]
    assert _press(w, ACK, row).status_code == 200
    presser = w.db.query(User).filter(User.id == w.buyer).one()

    with _as_purchasing(w) as buyer:
        listing = buyer.get(LIST, params={"limit": 200})
    assert listing.status_code == 200, listing.text
    item = next(i for i in listing.json()["data"] if i["id"] == str(row.id))
    assert item["ack_override"] == "confirmed"
    assert item["ack_override_at"]
    assert item["ack_override_by_name"] == presser.name
    assert str(w.buyer) not in str(item["ack_override_by_name"])


def test_ac_ac_11_the_header_follows_a_manual_override(api):
    c, w = api
    uncovered = _raise_one_row(api, qty="10")
    covered = _raise_one_row(api, qty="10")
    _po, line = _open_po_line(w, qty=50)
    _place(w, covered["row"], line, 10)

    assert _press(w, ACK, uncovered["row"]).status_code == 200
    assert _press(w, UNACK, covered["row"]).status_code == 200

    assert _header_state_of(c, uncovered["core_so"].so_number) == "completed"
    assert _header_state_of(c, covered["core_so"].so_number) == "outstanding"
