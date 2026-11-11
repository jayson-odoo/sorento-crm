"""Owner ruling 11 Nov ~21:35: "Why when AutoCount block the salesperson cannot retry? We want to
make things retryable in an error situation for recovery."

1. Only a CONFIRMED success uses up a key.
2. A refusal from AutoCount releases it: the user fixes the cause and presses again; it goes.
3. An unknown outcome (timeout, lost reply, 5xx, 202) never blocks: the next press first asks SS
   for the earlier press by re-sending that exact key and body (SS answers with what it stored for
   our reference); done -> link it, no duplicate; a refusal -> the corrected body goes under a
   fresh key in the same press.
4. A second press after a success is a no-op that shows the existing document.

None of this depends on Redis: `fake_ss` runs with no attempt store.
"""
from __future__ import annotations

import json

import httpx
import pytest

from tests._ac_write_support import (
    BASE,
    EDIT,
    SO_CREATE_PATH,
    VIEW,
    WRITE,
    add_issue,
    api_fixture,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    refused_body,
)
from tests.test_project_autocount_qt_send import QT_CREATE_PATH, QT_DOC_PATH, QT_KEY, _mark_sent, _read_back

QT_PATH = QT_CREATE_PATH


@pytest.fixture
def qt_api(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def so_api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


def _qt_url(world) -> str:
    return f"{BASE}/quotation-documents/{world.document.id}/autocount"


def _so_url(world) -> str:
    return f"{BASE}/sales-orders/{world.order.id}/autocount"


def _created(world):
    return (200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=_read_back(world)))


def _keys(fake_ss, method, path):
    return [r.headers["Idempotency-Key"] for r in fake_ss.to(method, path)]


# =========================================================================== 2. refuse -> fix -> retry


@pytest.mark.parametrize(
    "refusal",
    [
        (422, refused_body("FIELD_REQUIRED", "uom is required")),
        (502, refused_body("VENDOR_REFUSED", "itemCode and uom do not exist in its master file", outcome="vendor_error")),
        (409, refused_body("DOC_STALE", "")),
    ],
)
def test_a_refused_quotation_create_goes_through_once_the_cause_is_fixed(qt_api, fake_ss, refusal):
    client, db, world = qt_api
    fake_ss.answers[("POST", QT_PATH)] = refusal

    first = client.post(_qt_url(world)).json()
    assert first["outcome"] == "refused", first

    fake_ss.answers[("POST", QT_PATH)] = _created(world)
    second = client.post(_qt_url(world)).json()

    assert second["outcome"] == "done", second
    first_key, second_key = _keys(fake_ss, "POST", QT_PATH)
    assert first_key != second_key, "a refusal releases the key"
    base = f"crm-qt-{world.document.id}-{world.issue.id}-create"
    assert first_key.startswith(base) and second_key.startswith(base)
    db.refresh(world.document)
    assert world.document.autocount_doc_key == str(QT_KEY)
    assert world.document.autocount_pending_create is None


def test_a_refused_sales_order_create_goes_through_once_the_cause_is_fixed(so_api, fake_ss):
    client, db, world = so_api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (422, refused_body("FIELD_REQUIRED", "location is required"))
    assert client.post(_so_url(world)).json()["outcome"] == "refused"

    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, done_body())
    second = client.post(_so_url(world)).json()

    assert second["outcome"] == "done", second
    first_key, second_key = _keys(fake_ss, "POST", SO_CREATE_PATH)
    assert first_key != second_key
    db.refresh(world.order)
    assert world.order.autocount_doc_no == "SO412345"
    assert world.order.autocount_pending_create is None


def test_a_refused_edit_goes_through_on_the_next_press_without_redis(qt_api, fake_ss):
    """Every write but a create takes a fresh key each press: no held key can block it."""
    client, db, world = qt_api
    _mark_sent(db, world)
    add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()
    fake_ss.answers[("GET", QT_DOC_PATH)] = _created(world)
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = (422, refused_body("FIELD_NOT_EDITABLE", "ref is not editable"))
    assert client.post(_qt_url(world)).json()["outcome"] == "refused"

    fake_ss.answers[("PATCH", QT_DOC_PATH)] = _created(world)
    assert client.post(_qt_url(world)).json()["outcome"] == "done"

    first, second = _keys(fake_ss, "PATCH", QT_DOC_PATH)
    assert first != second


# =========================================================================== 4. success -> no-op


def test_a_second_press_after_a_quotation_create_shows_the_existing_document(qt_api, fake_ss):
    client, _db, world = qt_api
    fake_ss.answers[("POST", QT_PATH)] = _created(world)
    assert client.post(_qt_url(world)).json()["outcome"] == "done"
    calls = len(fake_ss.calls)

    again = client.post(_qt_url(world))

    assert again.status_code == 200, again.text
    assert again.json()["outcome"] == "done"
    assert again.json()["doc_no"] == "QT000777"
    assert again.json()["message"] == "QT000777 is already in AutoCount."
    assert len(fake_ss.calls) == calls, "no call to SS"


def test_a_second_press_after_a_sales_order_create_shows_the_existing_document(so_api, fake_ss):
    client, _db, world = so_api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, done_body())
    assert client.post(_so_url(world)).json()["outcome"] == "done"
    calls = len(fake_ss.calls)

    again = client.post(_so_url(world))

    assert again.status_code == 200, again.text
    assert again.json()["outcome"] == "done"
    assert again.json()["message"] == "SO412345 is already in AutoCount."
    assert len(fake_ss.calls) == calls


# =========================================================================== 3. unknown outcome


def _lost_then(answer_after):
    """The first create reaches SS and lands, but its answer is lost; SS then answers whatever it
    stored for that key, and anything for another key."""
    state: dict = {}

    def answer(request):
        key = request.headers["Idempotency-Key"]
        if "key" not in state:
            state["key"], state["body"] = key, request.content
            raise httpx.ReadTimeout("answer lost")
        if key == state["key"]:
            assert request.content == state["body"], "the same key always carries the same body"
            return answer_after
        return (500, {"code": "UNEXPECTED", "message": "a second create was sent"})

    return answer


def test_a_lost_reply_on_a_quotation_create_is_looked_up_and_linked_with_no_duplicate(qt_api, fake_ss):
    from app.models.projects import ProjectQuotationLine

    client, db, world = qt_api
    fake_ss.answers[("POST", QT_PATH)] = _lost_then(_created(world))

    first = client.post(_qt_url(world)).json()
    assert first["outcome"] == "unreachable", first
    db.refresh(world.document)
    assert world.document.autocount_pending_create, "the earlier press is remembered"

    # The salesperson edits the quotation meanwhile: the earlier press is still asked for as sent.
    line = db.query(ProjectQuotationLine).filter(ProjectQuotationLine.version_id == world.version.id).first()
    line.quantity = line.quantity + 1
    db.commit()

    second = client.post(_qt_url(world)).json()

    assert second["outcome"] == "done", second
    posts = fake_ss.to("POST", QT_PATH)
    assert len(posts) == 2
    assert posts[0].headers["Idempotency-Key"] == posts[1].headers["Idempotency-Key"]
    assert posts[0].content == posts[1].content
    db.refresh(world.document)
    assert world.document.autocount_doc_key == str(QT_KEY)
    assert world.document.autocount_pending_create is None
    assert client.post(_qt_url(world)).json()["message"] == "QT000777 is already in AutoCount."
    assert len(fake_ss.to("POST", QT_PATH)) == 2


def test_a_lost_reply_on_a_sales_order_create_is_looked_up_and_linked_with_no_duplicate(so_api, fake_ss):
    client, db, world = so_api
    fake_ss.answers[("POST", SO_CREATE_PATH)] = _lost_then((200, done_body()))

    assert client.post(_so_url(world)).json()["outcome"] == "unreachable"
    second = client.post(_so_url(world)).json()

    assert second["outcome"] == "done", second
    first_post, second_post = fake_ss.to("POST", SO_CREATE_PATH)
    assert first_post.headers["Idempotency-Key"] == second_post.headers["Idempotency-Key"]
    assert first_post.content == second_post.content
    db.refresh(world.order)
    assert world.order.autocount_doc_no == "SO412345"


def test_an_earlier_press_that_never_landed_sends_the_corrected_body_in_the_same_press(qt_api, fake_ss):
    """The asked-for earlier press turns out refused: it is released and the current body goes
    under a fresh key at once, so one press recovers."""
    client, db, world = qt_api
    def down(_request):
        raise httpx.ConnectError("down")

    fake_ss.answers[("POST", QT_PATH)] = down
    assert client.post(_qt_url(world)).json()["outcome"] == "unreachable"
    db.refresh(world.document)
    held_key = world.document.autocount_pending_create["key"]

    def answer(request):
        if request.headers["Idempotency-Key"] == held_key:
            return (422, refused_body("FIELD_REQUIRED", "uom is required"))
        return _created(world)

    fake_ss.answers[("POST", QT_PATH)] = answer

    body = client.post(_qt_url(world)).json()

    assert body["outcome"] == "done", body
    keys = [r.headers["Idempotency-Key"] for r in fake_ss.to("POST", QT_PATH)]
    assert keys[-2] == held_key and keys[-1] != held_key


def test_an_earlier_press_still_unconfirmed_never_sends_a_second_create(qt_api, fake_ss):
    client, db, world = qt_api
    fake_ss.answers[("POST", QT_PATH)] = (202, {**done_body(doc_key=None, doc_no=None), "outcome": "pending_verification"})
    assert client.post(_qt_url(world)).json()["outcome"] == "pending_verification"

    again = client.post(_qt_url(world)).json()

    assert again["outcome"] == "pending_verification"
    first, second = fake_ss.to("POST", QT_PATH)
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"]
    assert json.loads(first.content) == json.loads(second.content)


def test_the_pending_create_is_written_before_the_call(qt_api, fake_ss, monkeypatch):
    """Write-ahead: the key and body are committed before the call, so a press that dies during it
    is still asked for next time. (The fixture wraps every test in one outer transaction, so a
    second connection cannot see a commit; the commit itself is what is checked.)"""
    client, db, world = qt_api
    commits = []
    original = db.commit
    monkeypatch.setattr(db, "commit", lambda: (commits.append(1), original())[1])
    seen = {}

    def answer(request):
        seen["pending"] = world.document.autocount_pending_create
        seen["commits"] = len(commits)
        seen["key"] = request.headers["Idempotency-Key"]
        return _created(world)

    fake_ss.answers[("POST", QT_PATH)] = answer

    client.post(_qt_url(world))

    assert seen["commits"] >= 1, "committed before the call"
    assert seen["pending"] == {"key": seen["key"], "body": seen["pending"]["body"]}
    assert seen["key"].startswith(f"crm-qt-{world.document.id}")
