"""S3 - one send, one channel, named recipients, and an open that is recorded.

`PLAN-scm-fulfilment-feedback-p4.md` section 3 (R9-R11), AC-C2 to AC-C9. What is under test
is the part a person cannot see afterwards: which row a send left behind, who the email
actually went to, what a chat send does when the workspace cannot carry it, and whether the
supplier opening their link is recorded without ever being able to break the page.

Render and storage are stubbed the same way S8's own suite stubs them; the Respond client is
stubbed at the composer's own send function, because a test that reaches api.respond.io is a
test that fails on somebody else's outage.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.models.email_outbox import EmailOutbox
from app.models.supplier_notice import SupplierNotice
from app.services.error_handler import AppException
from app.services.scm import supplier_notice_service as svc
from tests._pg_fixture import pg_session
from tests.scm.test_loading_plan import World

MARKER = "ZZSC"


@pytest.fixture(autouse=True)
def _no_pdf_no_storage(monkeypatch):
    monkeypatch.setattr(svc, "render_document", lambda html: b"%PDF-1.4 stub")
    monkeypatch.setattr(svc, "_store", lambda data, filename: ("s3", f"exports/t/{filename}"))


def _world(db, *, email=None, phone=None) -> World:
    w = World(db)
    if email is not None:
        w.supplier.email = email
    if phone is not None:
        w.supplier.phone_number = phone
    w.stock("A", packed=120, unfinished=340)
    db.flush()
    return w


def _send(db, w, **kwargs) -> dict:
    return svc.request_and_notify(
        db,
        supplier_id=str(w.supplier.id),
        lines=[{"product_id": str(w.product("A").id), "qty": 500}],
        **kwargs,
    )


def _contact(db, *, phone: str, name: str = "Factory Wang") -> str:
    """A Respond contact to send to, with the respond_io_id a send resolves through."""
    from app.models.access import RespondContact

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=phone,
        name=name,
        respond_io_id=f"9{uuid.uuid4().int % 10_000_000}",
    )
    db.add(contact)
    db.flush()
    return str(contact.id)


def _wechat_channel(db):
    """A WeChat channel on an active workspace, which is what makes a chat send possible."""
    from app.models.respond_template import RespondChannel
    from app.models.respond_workspace import RespondWorkspace

    ws = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=f"{MARKER}-{uuid.uuid4().hex[:8]}",
        name=f"{MARKER} workspace",
        is_active=True,
        api_key_ciphertext="x",
    )
    db.add(ws)
    db.flush()
    channel = RespondChannel(
        id=str(uuid.uuid4()),
        workspace_id=str(ws.id),
        respond_channel_id=int(uuid.uuid4().int % 1_000_000),
        name=f"{MARKER} WeChat OA",
        source="wechat",
        is_active=True,
    )
    db.add(channel)
    db.flush()
    return channel


# --------------------------------------------------------------------------- #
# one send, one row (AC-C6)
# --------------------------------------------------------------------------- #


def test_a_send_writes_one_notice_for_the_chosen_channel_only():
    # AC-C6 / R9. The chat row was `skipped` on every send since 343 - a row that always
    # says "not done" is noise, and the send now goes on the channel the user picked.
    with pg_session() as db:
        w = _world(db, email=f"{MARKER}@example.test")

        out = _send(db, w, channel="email")

        assert [n["channel"] for n in out["notices"]] == ["email"]
        rows = db.query(SupplierNotice).filter(
            SupplierNotice.supplier_id == str(w.supplier.id)
        ).all()
        assert len(rows) == 1
        assert not [r for r in rows if r.status == "skipped"]


def test_an_unknown_channel_is_refused():
    with pg_session() as db:
        w = _world(db, email=f"{MARKER}@example.test")

        with pytest.raises(AppException) as raised:
            _send(db, w, channel="carrier-pigeon")

        assert raised.value.status_code == 422


# --------------------------------------------------------------------------- #
# email recipients (AC-C2)
# --------------------------------------------------------------------------- #


def test_every_named_recipient_is_enqueued_and_recorded_on_the_notice():
    # AC-C2. The supplier's own address is a default, not a limit: the person who packs and
    # the person who quotes are rarely the same mailbox.
    with pg_session() as db:
        w = _world(db, email=f"{MARKER}-default@example.test")
        addresses = [f"{MARKER}-a@example.test", f"{MARKER}-b@example.test"]

        out = _send(db, w, channel="email", recipients=addresses)

        queued = {
            r.recipient_email
            for r in db.query(EmailOutbox).filter(
                EmailOutbox.event_key == svc.EVENT_KEY,
                EmailOutbox.recipient_email.in_(addresses),
            )
        }
        assert queued == set(addresses)
        assert out["notices"][0]["recipients"] == addresses
        assert out["notices"][0]["status"] == "sent"


def test_with_no_recipients_named_the_supplier_address_is_used():
    with pg_session() as db:
        address = f"{MARKER}-{uuid.uuid4().hex[:6]}@example.test"
        w = _world(db, email=address)

        out = _send(db, w, channel="email")

        assert out["notices"][0]["recipients"] == [address]
        assert db.query(EmailOutbox).filter(
            EmailOutbox.recipient_email == address
        ).count() == 1


def test_a_send_with_no_address_anywhere_is_refused_rather_than_silently_dropped():
    # AC-C2. Zero recipients means nobody hears about the container; a 422 says so.
    with pg_session() as db:
        w = _world(db, email=None)

        with pytest.raises(AppException) as raised:
            _send(db, w, channel="email", recipients=[])

        assert raised.value.status_code == 422
        assert raised.value.detail["code"] == "no_recipients"
        assert db.query(SupplierNotice).filter(
            SupplierNotice.supplier_id == str(w.supplier.id)
        ).count() == 0


def test_an_address_that_is_not_an_address_is_refused():
    with pg_session() as db:
        w = _world(db, email=f"{MARKER}@example.test")

        with pytest.raises(AppException) as raised:
            _send(db, w, channel="email", recipients=["not-an-address"])

        assert raised.value.status_code == 422


def test_the_note_is_prepended_to_the_bilingual_body():
    # R9: the optional note line is the one thing the sender adds in their own words.
    with pg_session() as db:
        address = f"{MARKER}-{uuid.uuid4().hex[:6]}@example.test"
        w = _world(db, email=address)

        _send(db, w, channel="email", note="Ship before CNY please.")

        row = db.query(EmailOutbox).filter(EmailOutbox.recipient_email == address).one()
        assert row.body_text.startswith("Ship before CNY please.")
        assert "配柜要求" in row.body_text or "请查收附件配柜要求" in row.body_text


# --------------------------------------------------------------------------- #
# chat = WeChat, through the composer (AC-C3 / C4 / C5)
# --------------------------------------------------------------------------- #


def test_a_chat_send_with_no_wechat_channel_connected_is_refused_with_the_reason():
    # AC-C3. The workspace carries one WhatsApp channel today; until a WeChat one is
    # connected there is nothing to send a supplier request on, and saying so is the whole
    # answer (connecting it is a Respond.io task with its own go, R10).
    with pg_session() as db:
        w = _world(db, phone="+8613800000000")
        contact_id = _contact(db, phone="+8613800000000")

        with pytest.raises(AppException) as raised:
            _send(db, w, channel="chat", chat_contact_id=contact_id)

        assert raised.value.status_code == 422
        assert raised.value.detail["code"] == "wechat_channel_missing"
        assert db.query(SupplierNotice).filter(
            SupplierNotice.supplier_id == str(w.supplier.id)
        ).count() == 0


def test_a_chat_send_inside_the_window_goes_as_text_through_the_composer(monkeypatch):
    # AC-C4. Not a second Respond send path: the composer's own function owns the window
    # branch, the template and the outbox row, and this send is one of its callers.
    with pg_session() as db:
        _wechat_channel(db)
        w = _world(db, phone="+8613800000001")
        contact_id = _contact(db, phone="+8613800000001")
        seen = {}

        def _fake_send(db_, **kwargs):
            seen.update(kwargs)
            return {
                "sent_as": "text",
                "rendered_text": kwargs["text"],
                "flattened": False,
                "window_state": {"open": True},
                "response": {"messageId": "1"},
            }

        monkeypatch.setattr(svc, "_chat_send", _fake_send)
        monkeypatch.setattr(svc, "_chat_window_open", lambda *a, **k: True)
        monkeypatch.setattr(svc, "_public_base_url", lambda: "https://crm.example.test")

        out = _send(db, w, channel="chat", chat_contact_id=contact_id, note="Hi Wang")

        notice = out["notices"][0]
        assert notice["channel"] == "chat"
        assert notice["status"] == "sent"
        assert notice["sent_at"] is not None
        assert seen["business_table"] == "supplier_notices"
        assert seen["business_id"] == notice["id"]
        assert seen["chat_use_case"] == svc.CHAT_USE_CASE
        assert seen["text"].startswith("Hi Wang")
        assert "/supplier-request/" in seen["text"]
        assert notice["recipients"][0]["respond_contact_id"] == contact_id
        assert notice["recipients"][0]["channel"] == "wechat"


def test_a_chat_send_outside_the_window_goes_as_the_approved_template(monkeypatch):
    # AC-C4. The composer decides text vs template; what this suite owns is that the
    # outcome lands on the notice either way.
    with pg_session() as db:
        _wechat_channel(db)
        w = _world(db, phone="+8613800000002")
        contact_id = _contact(db, phone="+8613800000002")

        monkeypatch.setattr(
            svc,
            "_chat_send",
            lambda db_, **kw: {
                "sent_as": "template",
                "rendered_text": kw["text"],
                "flattened": True,
                "window_state": {"open": False},
                "response": {"messageId": "2"},
            },
        )
        monkeypatch.setattr(svc, "_chat_window_open", lambda *a, **k: False)
        monkeypatch.setattr(svc, "_chat_template_ready", lambda db_: True)

        out = _send(db, w, channel="chat", chat_contact_id=contact_id)

        assert out["notices"][0]["status"] == "sent"


def test_a_chat_send_respond_refuses_leaves_the_notice_failed_with_the_reason(monkeypatch):
    # AC-C4. Respond.io refusing the send is a fact about this send, and the row carries it:
    # the Requests sent card says what happened without anybody opening the outbox.
    with pg_session() as db:
        _wechat_channel(db)
        w = _world(db, phone="+8613800000003")
        contact_id = _contact(db, phone="+8613800000003")

        def _boom(db_, **kw):
            raise AppException(
                status_code=502,
                message="Failed to send the message. Please try again.",
                code="respond_send_failed",
            )

        monkeypatch.setattr(svc, "_chat_window_open", lambda *a, **k: True)
        monkeypatch.setattr(svc, "_chat_send", _boom)

        out = _send(db, w, channel="chat", chat_contact_id=contact_id)

        notice = out["notices"][0]
        assert notice["status"] == "failed"
        assert "failed to send" in (notice["last_error"] or "").lower()
        assert notice["sent_at"] is None


def test_out_of_window_with_no_approved_template_the_send_is_refused_and_nothing_changes(
    monkeypatch,
):
    # AC-C5. A template is the only deliverable message outside the window, so with none
    # approved there is nothing to send - and refusing BEFORE anything is written is what
    # keeps the supplier's live link alive (a retired link with no replacement is worse than
    # a refused send).
    with pg_session() as db:
        _wechat_channel(db)
        w = _world(db, phone="+8613800000006")
        contact_id = _contact(db, phone="+8613800000006")
        svc.request_and_notify(
            db,
            supplier_id=str(w.supplier.id),
            lines=[{"product_id": str(w.product("A").id), "qty": 500}],
            channel="email",
            recipients=[f"{MARKER}-live@example.test"],
        )
        live_before = db.query(SupplierNotice).filter(
            SupplierNotice.supplier_id == str(w.supplier.id)
        ).one().public_token_expires_at

        monkeypatch.setattr(svc, "_chat_window_open", lambda *a, **k: False)
        monkeypatch.setattr(svc, "_chat_template_ready", lambda db_: False)
        monkeypatch.setattr(
            svc, "_chat_send", lambda *a, **k: pytest.fail("nothing may be sent")
        )

        with pytest.raises(AppException) as raised:
            _send(db, w, channel="chat", chat_contact_id=contact_id)

        assert raised.value.status_code == 422
        assert raised.value.detail["code"] == "template_missing"
        rows = db.query(SupplierNotice).filter(
            SupplierNotice.supplier_id == str(w.supplier.id)
        ).all()
        assert len(rows) == 1, "the refused send wrote a row"
        assert rows[0].public_token_expires_at == live_before, "it retired the live link"


def test_a_chat_send_without_a_contact_is_refused():
    with pg_session() as db:
        _wechat_channel(db)
        w = _world(db, phone="+8613800000004")

        with pytest.raises(AppException) as raised:
            _send(db, w, channel="chat")

        assert raised.value.status_code == 422
        assert raised.value.detail["code"] == "chat_contact_required"


def test_a_chat_send_to_an_unknown_contact_is_refused():
    with pg_session() as db:
        _wechat_channel(db)
        w = _world(db, phone="+8613800000005")

        with pytest.raises(AppException) as raised:
            _send(db, w, channel="chat", chat_contact_id=str(uuid.uuid4()))

        assert raised.value.status_code == 422
        assert raised.value.detail["code"] == "chat_contact_not_found"


# --------------------------------------------------------------------------- #
# the contact picker (AC-C3)
# --------------------------------------------------------------------------- #


def test_the_contact_picker_puts_the_suppliers_own_number_first():
    # AC-C3. The prefilled contact is the one whose phone is the supplier's; everybody else
    # is searchable behind it, because a factory often answers on a colleague's account.
    with pg_session() as db:
        _wechat_channel(db)
        phone = f"+86138{uuid.uuid4().int % 100000000:08d}"
        w = _world(db, phone=phone)
        _contact(db, phone=f"+86139{uuid.uuid4().int % 100000000:08d}", name=f"{MARKER} Aaa")
        mine = _contact(db, phone=phone, name=f"{MARKER} Zzz")

        out = svc.chat_contacts(db, supplier_id=str(w.supplier.id), query=MARKER)

        assert out["wechat_connected"] is True
        assert out["data"][0]["id"] == mine
        assert out["data"][0]["suggested"] is True
        assert all(c["suggested"] is False for c in out["data"][1:])


def test_the_contact_picker_says_when_no_wechat_channel_is_connected():
    with pg_session() as db:
        w = _world(db)

        out = svc.chat_contacts(db, supplier_id=str(w.supplier.id), query=None)

        assert out["wechat_connected"] is False
        assert "wechat" in (out["unavailable_reason"] or "").lower()


# --------------------------------------------------------------------------- #
# opens (AC-C7)
# --------------------------------------------------------------------------- #


def test_opening_the_link_stamps_the_first_open_and_counts_every_one():
    # AC-C7 / R11. A write on a GET by design - it IS the tracking.
    with pg_session() as db:
        w = _world(db, email=f"{MARKER}@example.test")
        out = _send(db, w, channel="email")
        notice_id = out["notices"][0]["id"]
        token = db.query(SupplierNotice).filter(
            SupplierNotice.id == notice_id
        ).one().public_token

        svc.public_request_page(db, token)
        first = db.query(SupplierNotice).filter(SupplierNotice.id == notice_id).one()
        db.refresh(first)
        opened_at = first.opened_at
        assert opened_at is not None
        assert first.open_count == 1

        svc.public_request_page(db, token)
        db.refresh(first)
        assert first.open_count == 2
        assert first.opened_at == opened_at, "the first open never moves"
        assert first.last_opened_at >= opened_at


def test_downloading_a_document_off_the_link_counts_as_an_open(monkeypatch):
    with pg_session() as db:
        w = _world(db, email=f"{MARKER}@example.test")
        out = _send(db, w, channel="email")
        notice = db.query(SupplierNotice).filter(
            SupplierNotice.id == out["notices"][0]["id"]
        ).one()

        class _Backend:
            def get_signed_url(self, key, expires_in=3600):
                return f"https://example.test/{key}"

        monkeypatch.setattr("app.services.storage_router.get_backend", lambda p: _Backend())

        svc.public_document_url(db, notice.public_token, "pdf")

        db.refresh(notice)
        assert notice.open_count == 1


def test_a_stamp_that_fails_never_stops_the_supplier_reading_the_page(monkeypatch):
    # AC-C7. The tracking is the least important thing on that page.
    with pg_session() as db:
        w = _world(db, email=f"{MARKER}@example.test")
        out = _send(db, w, channel="email")
        notice = db.query(SupplierNotice).filter(
            SupplierNotice.id == out["notices"][0]["id"]
        ).one()

        def _boom(db_, token):
            raise RuntimeError("the open counter is on fire")

        monkeypatch.setattr(svc, "_stamp_open", _boom)

        page = svc.public_request_page(db, notice.public_token)

        assert page["line_count"] == 1


def test_the_notice_payload_carries_what_the_screen_shows_about_opens():
    # AC-C8: the list column and the Requests sent card read off these four fields.
    with pg_session() as db:
        w = _world(db, email=f"{MARKER}@example.test")
        out = _send(db, w, channel="email")

        payload = out["notices"][0]

        assert payload["open_count"] == 0
        assert payload["opened_at"] is None
        assert payload["last_opened_at"] is None
        assert payload["recipients"] == [f"{MARKER}@example.test"]
        assert payload["channel"] == "email"


# --------------------------------------------------------------------------- #
# the loading-plan list (S1 reads this)
# --------------------------------------------------------------------------- #


def test_the_latest_notice_per_plan_answers_the_list_columns():
    # The Sent / Opened columns of the loading-plan list (S1) read one row per plan, and it
    # has to be the LATEST send: a resent plan whose first notice answered would report an
    # opened count that belongs to a link nobody can open any more.
    from app.services.scm import loading_plan_service

    with pg_session() as db:
        w = _world(db, email=f"{MARKER}@example.test")
        w.po("1", [("A", 10, 0)])
        plan = loading_plan_service.build(
            db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10
        )

        first = _send(db, w, channel="email")
        second = _send(db, w, channel="email")
        rows = {}
        for key, out in (("first", first), ("second", second)):
            rows[key] = db.query(SupplierNotice).filter(
                SupplierNotice.id == out["notices"][0]["id"]
            ).one()
            rows[key].loading_plan_id = str(plan.id)
        # `now()` is fixed for the whole transaction, so both rows carry the same
        # `created_at` and "newest" cannot be read off it here. Age the first one.
        rows["first"].created_at = rows["first"].created_at - timedelta(days=1)
        rows["second"].open_count = 3
        db.flush()

        assert svc.latest_notice_for_plans(db, []) == {}
        found = svc.latest_notice_for_plans(db, [str(plan.id)])
        assert set(found) == {str(plan.id)}
        assert found[str(plan.id)]["channel"] == "email"
        assert found[str(plan.id)]["open_count"] == 3
        assert found[str(plan.id)]["sent_at"] is not None


def test_a_link_issued_before_the_migration_still_renders_and_starts_counting():
    # AC-H2. A token minted before 442 is open in somebody's inbox: its row has no
    # recipients, no opens and no chat contact, and the page must still answer - then count
    # the open like any other.
    with pg_session() as db:
        w = _world(db, email=f"{MARKER}@example.test")
        out = _send(db, w, channel="email")
        notice = db.query(SupplierNotice).filter(
            SupplierNotice.id == out["notices"][0]["id"]
        ).one()
        # Roll the row back to its pre-442 shape.
        notice.recipients = None
        notice.opened_at = None
        notice.last_opened_at = None
        notice.open_count = 0
        db.flush()

        page = svc.public_request_page(db, notice.public_token)

        assert page["line_count"] == 1
        assert page["sheet"]["columns"], "the no-file sheet still renders"
        db.refresh(notice)
        assert notice.open_count == 1
        assert svc.serialize(db, notice)["recipients"] is None
