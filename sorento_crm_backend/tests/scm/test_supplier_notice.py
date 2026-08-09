"""S8 - approving a loading plan tells the supplier, and says what it told them.

The document itself is rendered by WeasyPrint, whose native libraries are a deployment fact
rather than a property of this code, so every test here stubs the render and the object store.
What is under test is the part that can be wrong in a way a person would not notice: what the
notice froze, what it claims about a send, and whether a supplier we cannot reach reads as a
failure or as an outcome.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.email_outbox import EmailOutbox
from app.models.supplier_notice import SupplierNotice, SupplierNoticeLine
from app.services.error_handler import AppException
from app.services.scm import loading_plan_service
from app.services.scm import supplier_notice_service as svc
from tests._pg_fixture import pg_session
from tests.scm.test_loading_plan import World

MARKER = "ZZSN"


@pytest.fixture(autouse=True)
def _no_pdf_no_storage(monkeypatch):
    """Render and storage stubbed: this suite is about the record, not about WeasyPrint."""
    monkeypatch.setattr(svc, "render_document", lambda html: b"%PDF-1.4 stub")
    monkeypatch.setattr(svc, "_store", lambda data, filename: ("s3", f"exports/test/{filename}"))


def _plan_with_stock(db, *, packed=10, cbm=1.0, capacity=10, unfinished=0):
    w = World(db)
    w.po("1", [("A", 10, 0)], issue_date=date(2026, 1, 1))
    w.stock("A", packed=packed, unfinished=unfinished, cbm=cbm)
    plan = loading_plan_service.build(
        db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=capacity
    )
    return w, plan


def _lines(db, notice_id):
    return (
        db.query(SupplierNoticeLine)
        .filter(SupplierNoticeLine.notice_id == notice_id)
        .order_by(SupplierNoticeLine.sort_order)
        .all()
    )


def test_approving_produces_one_notice_per_channel():
    # AC-F1 plus AC-F4: email sends, chat is declared. One row each, because an email that
    # sent and a chat that did not are two facts and a single row would have to pick one.
    with pg_session() as db:
        w, plan = _plan_with_stock(db)
        w.supplier.email = f"{MARKER}@example.test"
        db.flush()

        out = svc.approve_and_notify(db, str(plan.id), actor="Ms Tee")

        by_channel = {n["channel"]: n for n in out["notices"]}
        assert set(by_channel) == {"email", "chat"}
        assert by_channel["email"]["status"] == "sent"
        assert by_channel["chat"]["status"] == "skipped"


def test_the_chat_channel_says_why_it_is_dark_rather_than_reading_as_a_failure():
    # Nobody can act on a "failure" whose cause is that the feature does not exist yet.
    with pg_session() as db:
        w, plan = _plan_with_stock(db)
        w.supplier.email = f"{MARKER}@example.test"
        db.flush()

        out = svc.approve_and_notify(db, str(plan.id))

        chat = next(n for n in out["notices"] if n["channel"] == "chat")
        assert chat["status"] == "skipped"
        assert "chat channel" in (chat["status_reason"] or "").lower()
        assert chat["last_error"] is None


def test_a_supplier_with_no_address_still_gets_a_notice_and_a_document():
    # AC-F3: the document is the point. A missing address is an outcome, not an error, or Ms
    # Tee loses the file she was going to send by hand.
    with pg_session() as db:
        w, plan = _plan_with_stock(db)
        w.supplier.email = None
        db.flush()

        out = svc.approve_and_notify(db, str(plan.id))

        email = next(n for n in out["notices"] if n["channel"] == "email")
        assert email["status"] == "skipped"
        assert "email address" in (email["status_reason"] or "").lower()
        assert email["has_document"] is True
        assert email["document_filename"].endswith(".pdf")


def test_the_email_is_queued_to_the_outbox_with_the_document_attached():
    # One producer of SMTP traffic keeps owning the send; the outbox carries a reference to
    # the stored document rather than its bytes.
    with pg_session() as db:
        w, plan = _plan_with_stock(db)
        w.supplier.email = f"{MARKER}-to@example.test"
        db.flush()

        svc.approve_and_notify(db, str(plan.id))

        row = (
            db.query(EmailOutbox)
            .filter(EmailOutbox.recipient_email == f"{MARKER}-to@example.test")
            .one()
        )
        assert row.event_key == "supplier_loading_notice"
        assert row.attachment_storage_key
        assert row.attachment_filename.endswith(".pdf")
        assert row.status == "pending"


def test_the_notice_copies_the_lines_so_a_re_run_cannot_rewrite_what_was_sent():
    # The plan re-runs in place on every container-count change (AC-E6). A notice reading
    # through to it would silently restate itself, and "what did we ask for" would have no
    # answer. The copy is the whole reason the table exists.
    with pg_session() as db:
        w, plan = _plan_with_stock(db, packed=10, cbm=1.0, capacity=10)
        w.supplier.email = f"{MARKER}@example.test"
        db.flush()

        out = svc.approve_and_notify(db, str(plan.id))
        notice_id = out["notices"][0]["id"]
        before = [(ln.item_code, float(ln.qty)) for ln in _lines(db, notice_id)]
        assert before and before[0][1] == 10

        # Half the containers: the plan now asks for 5 of the same item.
        loading_plan_service.build(
            db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=5, plan=plan
        )

        after = [(ln.item_code, float(ln.qty)) for ln in _lines(db, notice_id)]
        assert after == before


def test_deferred_lines_are_not_asked_for():
    # Telling a supplier to pack something the plan then leaves behind is how a container goes
    # out wrong. Only what was allocated volume is in the notice.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 10, 0)], issue_date=date(2026, 1, 1))
        w.po("2", [("B", 10, 0)], issue_date=date(2026, 6, 1))
        w.stock("A", packed=10, cbm=1.0)
        w.stock("B", packed=10, cbm=1.0)
        w.supplier.email = f"{MARKER}@example.test"
        plan = loading_plan_service.build(
            db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10
        )

        out = svc.approve_and_notify(db, str(plan.id))

        codes = {ln.item_code for ln in _lines(db, out["notices"][0]["id"])}
        assert w.product("A").product_code in codes
        assert w.product("B").product_code not in codes


def test_production_items_are_a_separate_kind_not_a_line_to_load():
    # AC-F2. "Load this" and "make this" are two different asks, and merging them is how
    # somebody loads a container with things that do not exist.
    with pg_session() as db:
        w, plan = _plan_with_stock(db, packed=10, cbm=1.0, capacity=10, unfinished=4)
        w.supplier.email = f"{MARKER}@example.test"
        db.flush()

        out = svc.approve_and_notify(db, str(plan.id))

        kinds = {ln.kind: ln for ln in _lines(db, out["notices"][0]["id"])}
        assert "produce" in kinds and float(kinds["produce"].qty) == 4
        assert out["notices"][0]["production_line_count"] == 1
        assert out["notices"][0]["line_count"] == 1


def test_nothing_to_pack_and_nothing_in_production_is_refused():
    # An empty notice is worse than no notice: the supplier reads it as an instruction.
    with pg_session() as db:
        w = World(db)
        w.po("1", [("A", 10, 0)])
        # No supplier inventory at all, so nothing is packed and nothing is unfinished.
        plan = loading_plan_service.build(
            db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10
        )
        w.supplier.email = f"{MARKER}@example.test"
        db.flush()

        with pytest.raises(AppException) as e:
            svc.approve_and_notify(db, str(plan.id))
        assert "nothing to pack" in str(e.value.detail).lower()


def test_every_attempt_writes_an_integration_log_including_the_ones_that_did_not_send():
    # AC-F5. A send nobody logged is a send nobody can answer questions about later.
    with pg_session() as db:
        w, plan = _plan_with_stock(db)
        w.supplier.email = None
        db.flush()

        out = svc.approve_and_notify(db, str(plan.id))
        notice_id = next(n["id"] for n in out["notices"] if n["channel"] == "email")

        rows = _integration_logs(db, notice_id)
        assert rows, "the skipped email attempt left no trace"
        assert rows[0]["business_table"] == "supplier_notices"

        # And the chat channel too. The screen shows both, so an outbox holding one of them
        # reads as a log that dropped a row.
        chat_id = next(n["id"] for n in out["notices"] if n["channel"] == "chat")
        assert _integration_logs(db, chat_id), "the chat channel left no trace"


def _integration_logs(db, business_id):
    from sqlalchemy import text

    # `integration_log`, singular: the table name and the model name disagree here, and the
    # plural reads so naturally that it is worth a comment rather than another 20 minutes.
    return db.execute(
        text(
            "SELECT status, business_table FROM integration_log "
            " WHERE business_id = CAST(:b AS uuid)"
        ),
        {"b": business_id},
    ).mappings().all()


def test_an_unknown_plan_is_a_404():
    with pg_session() as db:
        with pytest.raises(AppException) as e:
            svc.approve_and_notify(db, str(uuid.uuid4()))
        assert e.value.status_code == 404


def test_the_notice_reads_back_against_its_plan():
    # AC-F6: what was sent, to whom, on which channel, and when.
    with pg_session() as db:
        w, plan = _plan_with_stock(db)
        w.supplier.email = f"{MARKER}-read@example.test"
        db.flush()

        svc.approve_and_notify(db, str(plan.id), actor="Ms Tee")
        rows = svc.list_for_plan(db, str(plan.id))

        email = next(r for r in rows if r["channel"] == "email")
        assert email["recipient"] == f"{MARKER}-read@example.test"
        assert email["sent_at"] is not None
        assert email["created_by"] == "Ms Tee"
        assert email["supplier_name"] == w.supplier.supplier_name


def test_a_notice_with_no_document_refuses_to_hand_out_a_link():
    with pg_session() as db:
        w, plan = _plan_with_stock(db)
        db.flush()
        notice = SupplierNotice(
            supplier_id=str(w.supplier.id), channel="email", status="skipped"
        )
        db.add(notice)
        db.flush()

        with pytest.raises(AppException) as e:
            svc.document_url(db, str(notice.id))
        assert e.value.status_code == 409
