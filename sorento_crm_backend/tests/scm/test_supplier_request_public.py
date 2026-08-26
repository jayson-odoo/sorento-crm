"""F8 - the supplier opens a link instead of hunting for the attachment.

`PLAN-scm-fulfilment-feedback.md` section 3 (F8), AC-C1 / C6 / C7. The reader is a factory
with no session and no API key, so everything here is about what the token does and does not
buy: one request's lines, no price, no other supplier, and the same answer for a token that
never existed as for one that has run out.

The render and the object store are stubbed the same way S8's own suite stubs them - this
file is about the link, not about WeasyPrint.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models.email_outbox import EmailOutbox
from app.models.supplier_notice import SupplierNotice
from app.services.error_handler import AppException
from app.services.scm import supplier_notice_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_loading_plan import World

pytestmark = requires_pg

MARKER = "ZZSR"

URL = "/api/v1/public/supplier-request"


@pytest.fixture(autouse=True)
def _no_pdf_no_storage(monkeypatch):
    monkeypatch.setattr(svc, "render_document", lambda html: b"%PDF-1.4 stub")
    monkeypatch.setattr(svc, "_store", lambda data, filename: ("s3", f"exports/t/{filename}"))


def _sent(db, *, email: str | None = None, qty: float = 500) -> tuple[World, str]:
    """One container request, sent. Returns the world and the email notice's token."""
    w = World(db)
    if email:
        w.supplier.email = email
        db.flush()
    w.stock("A", packed=120, unfinished=340)
    svc.request_and_notify(
        db,
        supplier_id=str(w.supplier.id),
        lines=[{"product_id": str(w.product("A").id), "qty": qty}],
    )
    notice = (
        db.query(SupplierNotice)
        .filter(
            SupplierNotice.supplier_id == str(w.supplier.id),
            SupplierNotice.channel == "email",
        )
        .one()
    )
    return w, notice.public_token


# --------------------------------------------------------------------------- #
# the token
# --------------------------------------------------------------------------- #


def test_sending_stamps_a_token_that_expires_in_thirty_days(scm_app):
    # AC-C7. Thirty days is the whole of the link's life; nothing renews it.
    app, db, *_ = scm_app
    w, token = _sent(db)

    assert token
    notice = (
        db.query(SupplierNotice).filter(SupplierNotice.public_token == token).one()
    )
    life = notice.public_token_expires_at - datetime.utcnow()
    assert timedelta(days=29) < life <= timedelta(days=30)


def test_resending_issues_a_new_token_and_retires_the_old_one(scm_app):
    # AC-C7. The second request is the current ask; the first link must stop answering, or
    # a supplier working off an old email packs last month's quantities.
    app, db, *_ = scm_app
    w, first = _sent(db)

    svc.request_and_notify(
        db,
        supplier_id=str(w.supplier.id),
        lines=[{"product_id": str(w.product("A").id), "qty": 900}],
    )

    # Both notices carry the SAME `created_at`: `now()` is fixed for the whole transaction,
    # so "newest" cannot be read off the timestamp here. The live one is the one whose
    # expiry is still in the future, which is the property under test anyway.
    live = [
        n.public_token
        for n in db.query(SupplierNotice).filter(
            SupplierNotice.supplier_id == str(w.supplier.id),
            SupplierNotice.channel == "email",
            SupplierNotice.public_token_expires_at > datetime.utcnow(),
        )
    ]
    assert len(live) == 1
    assert live[0] != first
    with pytest.raises(AppException) as raised:
        svc.request_by_public_token(db, first)
    assert raised.value.status_code == 404


def test_an_expired_token_and_an_unknown_token_give_the_same_answer(scm_app):
    # AC-C7. Two different messages would confirm to anybody guessing that a token exists.
    app, db, *_ = scm_app
    w, token = _sent(db)
    notice = db.query(SupplierNotice).filter(SupplierNotice.public_token == token).one()
    notice.public_token_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.flush()

    with pytest.raises(AppException) as expired:
        svc.request_by_public_token(db, token)
    with pytest.raises(AppException) as unknown:
        svc.request_by_public_token(db, "no-such-token")

    assert expired.value.status_code == unknown.value.status_code == 404
    assert expired.value.detail == unknown.value.detail


# --------------------------------------------------------------------------- #
# the page
# --------------------------------------------------------------------------- #


def test_the_public_page_reads_without_a_login(scm_app):
    # AC-C6. No session, no API key: the token is the whole credential.
    app, db, *_ = scm_app
    w, token = _sent(db)

    body = TestClient(app).get(f"{URL}/{token}").json()

    assert body["supplier_name"] == w.supplier.supplier_name
    assert body["line_count"] == 1
    assert body["lines"][0]["item_code"] == w.product("A").product_code
    assert body["lines"][0]["qty"] == 500


def test_the_page_carries_their_own_stock_figures(scm_app):
    # AC-C6: "their packed / unfinished" beside our ask, so they can see what we counted on.
    app, db, *_ = scm_app
    w, token = _sent(db)

    line = TestClient(app).get(f"{URL}/{token}").json()["lines"][0]

    assert line["qty_packed"] == 120
    assert line["qty_unfinished"] == 340


def test_the_page_states_no_price_and_no_cost(scm_app):
    # AC-C6. The one thing a supplier must never read off our side of the conversation.
    app, db, *_ = scm_app
    _w, token = _sent(db)

    body = TestClient(app).get(f"{URL}/{token}").json()

    flat = str(body).lower()
    assert "price" not in flat
    assert "cost" not in flat
    assert "supplier_id" not in body
    assert "notice_id" not in body


def test_the_page_shows_this_request_only_and_no_other_suppliers_rows(scm_app):
    # AC-C6. One token, one document - the property that makes a leaked URL survivable.
    app, db, *_ = scm_app
    _other, _other_token = _sent(db)
    w, token = _sent(db)

    body = TestClient(app).get(f"{URL}/{token}").json()

    assert [ln["item_code"] for ln in body["lines"]] == [w.product("A").product_code]


def test_an_unknown_token_is_a_404_on_the_route_too(scm_app):
    app, db, *_ = scm_app

    response = TestClient(app).get(f"{URL}/no-such-token")

    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# the files
# --------------------------------------------------------------------------- #


def test_the_page_offers_both_files(scm_app, monkeypatch):
    # AC-C6: PDF and XLSX download, off the same token.
    app, db, *_ = scm_app
    _w, token = _sent(db)

    class _Backend:
        def get_signed_url(self, key, expires_in=3600):
            return f"https://example.test/{key}"

    monkeypatch.setattr("app.services.storage_router.get_backend", lambda p: _Backend())
    client = TestClient(app)

    body = client.get(f"{URL}/{token}").json()
    assert body["has_pdf"] is True
    assert body["has_xlsx"] is True

    pdf = client.get(f"{URL}/{token}/document/pdf").json()
    xlsx = client.get(f"{URL}/{token}/document/xlsx").json()
    assert pdf["filename"].endswith(".pdf")
    assert xlsx["filename"].endswith(".xlsx")


def test_a_document_on_an_unknown_token_is_a_404(scm_app):
    app, db, *_ = scm_app

    assert TestClient(app).get(f"{URL}/no-such-token/document/pdf").status_code == 404


def test_an_unknown_file_kind_is_refused(scm_app):
    app, db, *_ = scm_app
    _w, token = _sent(db)

    assert TestClient(app).get(f"{URL}/{token}/document/exe").status_code in (404, 422)


# --------------------------------------------------------------------------- #
# the email
# --------------------------------------------------------------------------- #


def test_the_email_body_carries_the_link(scm_app, monkeypatch):
    # AC-C1: three things in one email - the PDF, the sheet, and a link to the same request.
    app, db, *_ = scm_app
    monkeypatch.setattr(svc, "_public_base_url", lambda: "https://crm.example.test")
    address = f"{MARKER}-{uuid.uuid4().hex[:6]}@example.test"
    _w, token = _sent(db, email=address)

    row = db.query(EmailOutbox).filter(EmailOutbox.recipient_email == address).one()

    assert token in row.body_text
    assert "https://crm.example.test/c/" in row.body_text
    assert "/supplier-request/" in row.body_text


def test_with_no_base_url_configured_the_email_simply_has_no_link(scm_app, monkeypatch):
    # A missing FRONTEND_BASE_URL must not put "None/c/.../token" in front of a supplier.
    app, db, *_ = scm_app
    monkeypatch.setattr(svc, "_public_base_url", lambda: None)
    address = f"{MARKER}-{uuid.uuid4().hex[:6]}@example.test"
    _w, token = _sent(db, email=address)

    row = db.query(EmailOutbox).filter(EmailOutbox.recipient_email == address).one()

    assert token not in row.body_text
    assert "None" not in row.body_text


def test_the_notice_payload_carries_the_link_and_drops_it_once_retired(scm_app, monkeypatch):
    # AC-C4: the Requests sent card offers "Copy link", and it must not offer one that has
    # been retired by a resend - a copied dead link is worse than no button.
    app, db, *_ = scm_app
    monkeypatch.setattr(svc, "_public_base_url", lambda: "https://crm.example.test")
    w, token = _sent(db)

    rows = svc.list_for_supplier(db, str(w.supplier.id))
    live = next(n for n in rows if n["channel"] == "email")
    assert live["public_url"].endswith(f"/supplier-request/{token}")
    assert "/c/" in live["public_url"]
    # One token per send, on the channel that carries the link. The chat row is dark, so a
    # second live link to the same request would be one nobody ever receives.
    assert next(n for n in rows if n["channel"] == "chat")["public_url"] is None

    svc.request_and_notify(
        db,
        supplier_id=str(w.supplier.id),
        lines=[{"product_id": str(w.product("A").id), "qty": 900}],
    )
    retired = next(
        n
        for n in svc.list_for_supplier(db, str(w.supplier.id))
        if n["id"]
        == str(
            db.query(SupplierNotice)
            .filter(SupplierNotice.public_token == token)
            .one()
            .id
        )
    )
    assert retired["public_url"] is None
