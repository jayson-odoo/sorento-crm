"""AC-QTSO-CRM round 6/6b (B5, F7): a refusal must not make every retry replay the refusal.

Crew's decision (6 Nov, round 6b): #2223's shared helper (`autocount_idempotency`), not a body hash.
SS replays a stored refusal for the same key and body, so a refusal made every retry impossible. Attempt
0 is the plain base key; a DEFINITE refusal (outcome refused, errorCode not IDEMPOTENCY_*) moves the next
press of the same intent to `attempt_key(base, n)`. A timeout, a 202, `needs_attention` or an
IDEMPOTENCY_* answer keeps the key. With no store every press uses the base key.
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


# --------------------------------------------------------------------------- attempts (round 6b)
#
# Crew's decision: #2223's `autocount_idempotency` helper, not a body hash. Attempt 0 is the plain
# base key; a DEFINITE refusal (outcome refused, errorCode not IDEMPOTENCY_*) moves the next press of
# the same intent to `attempt_key(base, n)`. Anything else keeps the key so a retry can only replay.


class DictStore:
    """A Redis-like store: `get`, `set(ex=)`."""

    def __init__(self):
        self.data = {}

    def get(self, name):
        return self.data.get(name)

    def set(self, name, value, ex=None):
        self.data[name] = value


@pytest.fixture
def store(monkeypatch):
    from app.services import project_autocount_write_service as svc

    s = DictStore()
    monkeypatch.setattr(svc, "attempt_store", lambda: s)
    return s


def _no_store(monkeypatch):
    from app.services import project_autocount_write_service as svc

    monkeypatch.setattr(svc, "attempt_store", lambda: None)


def _refused(code="ITEM_NOT_FOUND"):
    return (422, refused_body(code, "no"))


def _so_url(world):
    return f"{BASE}/sales-orders/{world.order.id}/autocount"


# ---- each of the seven sites goes through the helper, at attempt 0 with the plain base key


def test_so_create_uses_the_base_key_at_attempt_zero(so_api, fake_ss, store):
    client, _db, world = so_api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, done_body())

    client.post(_so_url(world))

    [request] = fake_ss.to("POST", SO_CREATE_PATH)
    assert _key(request) == f"crm-pso-{world.order.id}-create"


def test_so_update_uses_the_base_key_at_attempt_zero(so_api, fake_ss, store):
    client, db, world = so_api
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [delay_row(world, world.line2, "2027-01-07")])
    db.commit()
    fake_ss.answers[("PATCH", SO_DOC)] = (200, done_body())

    client.post(f"{BASE}/sales-orders/amendments/{amendment.id}/autocount")

    [request] = fake_ss.to("PATCH", SO_DOC)
    assert _key(request) == f"crm-amd-{amendment.id}-update-edit"


def test_so_cancel_uses_the_base_key_at_attempt_zero(so_api, fake_ss, store):
    client, db, world = so_api
    put_in_autocount(db, world)
    db.commit()
    fake_ss.answers[("GET", CAPS_PATH)] = (200, {"book": BOOK, "capabilities": caps_with(cancel_doc=(True, None))})
    fake_ss.answers[("POST", f"{SO_DOC}/cancel")] = (200, done_body())

    client.post(f"{BASE}/sales-orders/{world.order.id}/autocount/cancel")

    [request] = fake_ss.to("POST", f"{SO_DOC}/cancel")
    assert _key(request) == f"crm-pso-{world.order.id}-cancel"


def test_qt_create_uses_the_base_key_at_attempt_zero(qt_api, fake_ss, store):
    client, _db, world = qt_api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, done_body(doc_no="QT000777", doc_key=QT_KEY))

    client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount")

    [request] = fake_ss.to("POST", QT_CREATE_PATH)
    assert _key(request) == f"crm-qt-{world.document.id}-{world.issue.id}-create"


def test_qt_update_steps_use_their_base_keys_at_attempt_zero(qt_api, fake_ss, store):
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
    assert _key(patch) == f"{base}-edit" and _key(lines) == f"{base}-lines-3", "one add-line call per new row, keyed by its place"


def test_qt_cancel_uses_the_base_key_at_attempt_zero(qt_api, fake_ss, store):
    client, db, world = qt_api
    _qt_in_autocount(db, world)
    fake_ss.answers[("GET", CAPS_PATH)] = (200, {"book": BOOK, "capabilities": caps_with(cancel_doc=(True, None))})
    fake_ss.answers[("POST", f"{QT_DOC}/cancel")] = (200, done_body(doc_no="QT000777", doc_key=QT_KEY))

    client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount/cancel")

    [request] = fake_ss.to("POST", f"{QT_DOC}/cancel")
    assert _key(request) == f"crm-qt-{world.document.id}-cancel"


# ---- a definite refusal moves the next press on and it goes through


def test_so_create_after_a_refusal_goes_under_the_next_attempt_key(so_api, fake_ss, store):
    from app.services.autocount_idempotency import attempt_key

    client, _db, world = so_api
    base = f"crm-pso-{world.order.id}-create"
    fake_ss.answers[("POST", SO_CREATE_PATH)] = _refused()
    assert client.post(_so_url(world)).json()["outcome"] == "refused"
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, done_body())

    assert client.post(_so_url(world)).json()["outcome"] == "done"

    first, second = fake_ss.to("POST", SO_CREATE_PATH)
    assert _key(first) == base and _key(second) == attempt_key(base, 1)


def test_qt_create_after_a_refusal_goes_under_the_next_attempt_key(qt_api, fake_ss, store):
    from app.services.autocount_idempotency import attempt_key

    client, _db, world = qt_api
    base = f"crm-qt-{world.document.id}-{world.issue.id}-create"
    url = f"{BASE}/quotation-documents/{world.document.id}/autocount"
    fake_ss.answers[("POST", QT_CREATE_PATH)] = _refused()
    client.post(url)
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, done_body(doc_no="QT000777", doc_key=QT_KEY))

    assert client.post(url).json()["outcome"] == "done"

    first, second = fake_ss.to("POST", QT_CREATE_PATH)
    assert _key(first) == base and _key(second) == attempt_key(base, 1)


def test_so_cancel_after_a_refusal_goes_under_the_next_attempt_key(so_api, fake_ss, store):
    from app.services.autocount_idempotency import attempt_key

    client, db, world = so_api
    put_in_autocount(db, world)
    db.commit()
    base = f"crm-pso-{world.order.id}-cancel"
    url = f"{BASE}/sales-orders/{world.order.id}/autocount/cancel"
    fake_ss.answers[("GET", CAPS_PATH)] = (200, {"book": BOOK, "capabilities": caps_with(cancel_doc=(True, None))})
    fake_ss.answers[("POST", f"{SO_DOC}/cancel")] = _refused("HAS_DELIVERIES")
    client.post(url)
    fake_ss.answers[("POST", f"{SO_DOC}/cancel")] = (200, done_body())

    assert client.post(url).json()["outcome"] == "done"

    first, second = fake_ss.to("POST", f"{SO_DOC}/cancel")
    assert _key(first) == base and _key(second) == attempt_key(base, 1)


def test_a_corrected_body_after_a_refusal_goes_under_the_new_attempt_key(so_api, fake_ss, store):
    from app.services.autocount_idempotency import attempt_key

    client, db, world = so_api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = _refused()
    client.post(_so_url(world))
    world.line1.qty = world.line1.qty + 1
    db.commit()
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, done_body())

    assert client.post(_so_url(world)).json()["outcome"] == "done"

    first, second = fake_ss.to("POST", SO_CREATE_PATH)
    assert _body(first) != _body(second)
    assert _key(second) == attempt_key(f"crm-pso-{world.order.id}-create", 1)


# ---- anything that is not a definite refusal keeps the key


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param((202, {**done_body(), "outcome": "pending_verification"}), id="pending-202"),
        pytest.param((200, {**done_body(), "outcome": "needs_attention"}), id="needs-attention"),
        pytest.param((422, refused_body("IDEMPOTENCY_CONFLICT", "key used")), id="idempotency-conflict"),
        pytest.param((409, refused_body("IDEMPOTENCY_CONFLICT", "key used", outcome="refused")), id="conflict-409"),
    ],
)
def test_a_retry_keeps_the_same_key_unless_the_refusal_was_definite(so_api, fake_ss, store, answer):
    client, _db, world = so_api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = answer

    client.post(_so_url(world))
    client.post(_so_url(world))

    first, second = fake_ss.to("POST", SO_CREATE_PATH)
    assert _key(first) == _key(second) == f"crm-pso-{world.order.id}-create"


def test_a_timeout_keeps_the_same_key(so_api, fake_ss, store):
    import httpx

    client, _db, world = so_api

    def slow(request):
        raise httpx.ReadTimeout("slow")

    # Only the write times out; the capability read (which names the book) answers.
    fake_ss.answers[("POST", SO_CREATE_PATH)] = slow

    client.post(_so_url(world))
    client.post(_so_url(world))

    posts = [r for r in fake_ss.calls if r.method == "POST"]
    assert len(posts) == 2 and _key(posts[0]) == _key(posts[1]) == f"crm-pso-{world.order.id}-create"


def test_with_no_store_every_press_uses_the_base_key(so_api, fake_ss, monkeypatch):
    _no_store(monkeypatch)
    client, _db, world = so_api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = _refused()

    client.post(_so_url(world))
    client.post(_so_url(world))

    first, second = fake_ss.to("POST", SO_CREATE_PATH)
    assert _key(first) == _key(second) == f"crm-pso-{world.order.id}-create"


def test_the_step_marker_still_stops_a_resend_after_done(so_api, fake_ss, store):
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
