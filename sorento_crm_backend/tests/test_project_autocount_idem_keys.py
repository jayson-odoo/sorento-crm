"""AC-QTSO-CRM: the Idempotency-Key of each write (B5, then the owner's ruling of 11 Nov) and F7.

Owner, 11 Nov: "We want to make things retryable in an error situation for recovery." Every write
but a create takes a fresh key each press; a create holds its key on the record until AutoCount
confirms or refuses it (`tests/test_project_autocount_retry.py`). The round 6b attempt counter in
Redis is retired for this service.
"""
from __future__ import annotations

import json

import pytest

from tests._ac_write_support import (
    BASE,
    CAPS_PATH,
    DOC_KEY,
    EDIT,
    QT_CREATE_PATH,
    SO_CREATE_PATH,
    VIEW,
    WRITE,
    add_amendment,
    add_issue,
    api_fixture,
    caps_with,
    delay_row,
    detail,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    put_in_autocount,
    refused_body,
    BOOK,
)

QT_KEY = 5001
QT_DOC = f"{QT_CREATE_PATH}/{QT_KEY}"
SO_DOC = f"{SO_CREATE_PATH}/{DOC_KEY}"


@pytest.fixture
def so_api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def qt_api(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)


def _body(request) -> dict:
    return json.loads(request.content)


def _key(request) -> str:
    return request.headers["Idempotency-Key"]


def _qt_in_autocount(db, world, *, newer_issue=False):
    world.document.autocount_doc_no = "QT000777"
    world.document.autocount_doc_key = str(QT_KEY)
    world.document.autocount_last_modified = "2026-10-21T08:00:00"
    world.document.autocount_issue_id = world.issue.id
    world.document.autocount_book = BOOK
    issue2 = None
    if newer_issue:
        issue2 = add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()
    return issue2


# --------------------------------------------------------------------------- keys (owner ruling 11 Nov)
#
# "We want to make things retryable in an error situation for recovery." Every write but a create
# takes a fresh key each press (`{base}-{8 hex}`), so a refusal never blocks the retry. A create
# holds its key on the record until AutoCount confirms or refuses it
# (`tests/test_project_autocount_retry.py`). No Redis is involved.


def _refused(code="ITEM_NOT_FOUND"):
    return (422, refused_body(code, "no"))


def _so_url(world):
    return f"{BASE}/sales-orders/{world.order.id}/autocount"


def _fresh(key: str, base: str) -> bool:
    suffix = key[len(base) + 1:]
    return key.startswith(f"{base}-") and len(suffix) == 8 and all(c in "0123456789abcdef" for c in suffix)


def test_so_cancel_takes_a_fresh_key_each_press(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    db.commit()
    fake_ss.answers[("GET", CAPS_PATH)] = (200, {"book": BOOK, "capabilities": caps_with(cancel_doc=(True, None))})
    fake_ss.answers[("POST", f"{SO_DOC}/cancel")] = _refused("DOC_HAS_TRANSFERS")
    url = f"{BASE}/sales-orders/{world.order.id}/autocount/cancel"
    client.post(url)
    fake_ss.answers[("POST", f"{SO_DOC}/cancel")] = (200, done_body())

    assert client.post(url).json()["outcome"] == "done"

    first, second = fake_ss.to("POST", f"{SO_DOC}/cancel")
    base = f"crm-pso-{world.order.id}-cancel"
    assert _fresh(_key(first), base) and _fresh(_key(second), base)
    assert _key(first) != _key(second)


def test_qt_update_steps_take_fresh_keys_under_their_step_names(qt_api, fake_ss):
    client, db, world = qt_api
    issue2 = _qt_in_autocount(db, world, newer_issue=True)
    from app.models.projects import ProjectQuotationLine
    import uuid
    from decimal import Decimal
    from tests.test_project_so_draft import _product, _uid

    new = _product(db, f"ZZT-NEW-{_uid()[:6]}")
    db.add(ProjectQuotationLine(
        id=str(uuid.uuid4()), company_id=world.company_id, version_id=world.version.id, product_id=new.id,
        product_code_snapshot=new.product_code, description_snapshot="New", unit_price=Decimal("75.00"),
        quantity=Decimal("3"), uom="UNIT", line_total=Decimal("225.00"), sort_order=9,
    ))
    db.commit()
    held = [detail(1, world.p1.product_code, "10", "180.00", "BRW-BB", None, 1),
            detail(2, world.p_wc.product_code, "2", "950.00", "BRW-BB", None, 2),
            detail(3, world.p_av.product_code, "4", "0.00", "BRW-BB", None, 3)]
    fake_ss.answers[("GET", QT_DOC)] = (200, done_body(doc_key=QT_KEY, details=held))
    fake_ss.answers[("PATCH", QT_DOC)] = (200, done_body(doc_key=QT_KEY, details=held, last_modified="2026-11-06T09:00:00"))
    fake_ss.answers[("POST", f"{QT_DOC}/lines")] = (200, done_body(doc_key=QT_KEY, details=held))

    client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount")

    [patch] = fake_ss.to("PATCH", QT_DOC)
    [lines] = fake_ss.to("POST", f"{QT_DOC}/lines")
    base = f"crm-qt-{world.document.id}-{issue2.id}-update"
    assert _fresh(_key(patch), f"{base}-edit")
    assert _fresh(_key(lines), f"{base}-lines-3"), "one add-line call per new row, keyed by its place"


def test_a_timed_out_edit_goes_again_under_a_fresh_key(so_api, fake_ss):
    """An edit is absolute values under the stamp check, so it never needs its old key back."""
    import httpx

    client, db, world = so_api
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [delay_row(world, world.line2, "2027-01-07")])
    db.commit()

    def down(_request):
        raise httpx.ReadTimeout("lost")

    fake_ss.answers[("PATCH", SO_DOC)] = down
    url = f"{BASE}/sales-orders/amendments/{amendment.id}/autocount"
    client.post(url)
    fake_ss.answers[("PATCH", SO_DOC)] = (200, done_body())

    assert client.post(url).json()["outcome"] == "done"
    first, second = fake_ss.to("PATCH", SO_DOC)
    assert _key(first) != _key(second)


def test_the_step_marker_still_stops_a_resend_after_done(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [delay_row(world, world.line2, "2027-01-07")])
    db.commit()
    fake_ss.answers[("PATCH", SO_DOC)] = (200, done_body())
    url = f"{BASE}/sales-orders/amendments/{amendment.id}/autocount"
    client.post(url)

    second = client.post(url)

    assert len(fake_ss.to("PATCH", SO_DOC)) == 1
    assert second.json()["message"] == "Already in AutoCount."


# --------------------------------------------------------------------------- F7


def test_a_quotation_whose_recipient_has_no_customer_is_422_ac_missing_recipient(qt_api, fake_ss):
    from app.models.projects import ProjectParty

    client, db, world = qt_api
    party_id = world.document.recipient_party_id
    party = db.query(ProjectParty).filter(ProjectParty.id == party_id).one()
    party.customer_id = None
    db.commit()

    response = client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount")

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "ac_missing_recipient"
    assert response.json()["message"] == "This quotation has no recipient customer."
    assert fake_ss.calls == []


def test_a_quotation_with_no_recipient_party_at_all_is_the_same_422(qt_api, fake_ss):
    client, db, world = qt_api
    world.document.recipient_party_id = None
    db.commit()

    response = client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount")

    assert response.status_code == 422 and response.json()["code"] == "ac_missing_recipient"
    assert fake_ss.calls == []
