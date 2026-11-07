"""Shared "watched product field changed" notifier (PRODUCT-FIELD-CHANGE-NOTIFY).

Two halves:

* A golden lock on the discontinued message (title, body, WhatsApp text, context vars),
  written against the pre-refactor service so the shared runner cannot drift its copy.
* List price as the second watched field: level-triggered on
  ``list_price <> list_price_notified`` (a NULL baseline is adopted first), own per-user toggles, the same
  company/brand scope rows, one digest per company per run listing each product as
  ``code name: RM old -> RM new (+x.x%)``.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.notification import Notification
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import User, UserProductDiscontinuedScope
import app.services.product_discontinued_notify_service as disc_svc
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _frontend(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "frontend_base_url", "https://crm.example", raising=False)


def _refs(db):
    if not hasattr(db, "_refs"):
        category_id, uom_id = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(ProductCategory(id=category_id, category_code="CAT1", category_name="Category One"))
        db.add(UnitOfMeasure(id=uom_id, uom_code="EA", uom_name="Each"))
        db.flush()
        db._refs = (category_id, uom_id)
    return db._refs


def _product(db, *, code, price="100.00", notified="100.00", discontinued=False, updated_by=None):
    category_id, uom_id = _refs(db)
    p = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=f"Name {code}",
        description="**** EOL" if discontinued else "active",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=Decimal(price),
        list_price_notified=Decimal(notified) if notified is not None else None,
        is_active=True,
        is_discontinued=discontinued,
        updated_by=updated_by,
    )
    db.add(p)
    return p


def _user(db, *, email, disc_email=False, lp_email=False, lp_wa=False, scope=True):
    u = User(
        id=str(uuid.uuid4()),
        email=email,
        name=email.split("@")[0],
        status="ACTIVE",
        notify_email_on_product_discontinued=disc_email,
        notify_email_on_product_list_price=lp_email,
        notify_whatsapp_on_product_list_price=lp_wa,
    )
    db.add(u)
    if scope:
        db.add(UserProductDiscontinuedScope(id=str(uuid.uuid4()), user_id=u.id))
    return u


def _lp_run(db):
    from app.services.product_watched_field_notify_service import (
        LIST_PRICE,
        run_watched_field_check,
    )

    return run_watched_field_check(db, LIST_PRICE)


# --------------------------------------------------------------------------- discontinued


def test_discontinued_message_golden(db):
    """Byte-for-byte lock of today's discontinued copy (single company, one product)."""
    _product(db, code="D1", discontinued=True)
    sub = _user(db, email="sub@x.com", disc_email=True)
    db.commit()

    out = disc_svc.run_product_discontinued_check(db)
    batch = out["batch_id"]
    link = f"https://crm.example/master-data-management/products?discontinued_batch_id={batch}"

    n = db.query(Notification).one()
    assert n.user_id == sub.id
    assert n.type == "product_discontinued"
    assert n.event_type == "discontinued"
    assert n.source_entity_type == "product_discontinued_batch"
    assert n.title == "1 product discontinued"
    assert n.body == f"1 product was newly marked as discontinued. View the list: {link}"
    data = n.data
    assert data["discontinued_count"] == 1
    assert data["discontinued_batch_id"] == batch
    assert data["discontinued_link"] == link
    assert data["whatsapp_use_case"] == "product_discontinued"
    assert data["whatsapp_text"] == f"1 product discontinued. View the list: {link}"
    ctx = data["whatsapp_context_vars"]
    assert ctx["discontinued_count"] == "1"
    assert ctx["discontinued_link"] == link
    assert ctx["portal_url"] == link
    assert ctx["system_url"] == "https://crm.example"
    assert ctx["contact_name"] == "sub"
    assert ctx["message"] == data["whatsapp_text"]
    assert set(ctx) == {
        "discontinued_count", "discontinued_link", "company_name", "today_date",
        "system_url", "portal_url", "message", "contact_name",
    }


def test_discontinued_ignores_list_price_subscribers(db):
    _product(db, code="D1", discontinued=True)
    _user(db, email="lp@x.com", lp_email=True)
    db.commit()
    out = disc_svc.run_product_discontinued_check(db)
    assert out["notified_users"] == 0
    assert db.query(Notification).count() == 0


# --------------------------------------------------------------------------- list price


def test_list_price_change_notifies_digest(db):
    editor = _user(db, email="editor@x.com", scope=False)
    _product(db, code="P1", price="110.00", notified="100.00", updated_by=editor.id)
    _product(db, code="P2", price="80.00", notified="100.00")
    _product(db, code="SAME", price="50.00", notified="50.00")
    sub = _user(db, email="sub@x.com", lp_email=True)
    _user(db, email="disc@x.com", disc_email=True)  # discontinued-only: not a recipient
    db.commit()

    out = _lp_run(db)

    assert out["pending"] == 2
    assert out["notified_users"] == 1
    batch = out["batch_id"]
    n = db.query(Notification).one()
    assert n.user_id == sub.id
    assert n.type == "product_list_price_changed"
    assert n.source_entity_type == "product_list_price_batch"
    assert n.source_entity_id == batch
    assert n.title == "List price changed for 2 products"
    assert "P1 Name P1: RM 100.00 -> RM 110.00 (+10.0%)" in n.body
    # No "by <editor>": updated_by is stale after an AutoCount push (owner ask on #2228).
    assert "by editor" not in n.body
    assert "P2 Name P2: RM 100.00 -> RM 80.00 (-20.0%)" in n.body
    assert "SAME" not in n.body
    link = f"https://crm.example/master-data-management/products?list_price_batch_id={batch}"
    assert link in n.body
    assert n.data["whatsapp_use_case"] == "product_list_price_changed"
    assert n.data["list_price_link"] == link
    ctx = n.data["whatsapp_context_vars"]
    assert ctx["list_price_count"] == "2"
    assert ctx["list_price_link"] == link
    assert ctx["contact_name"] == "sub"
    assert n.data["link"] == link
    # WhatsApp: count + date + link only, no product lines.
    assert n.data["whatsapp_text"] == (
        f"List price changed for 2 products ({ctx['today_date']}). View the list: {link}"
    )
    assert ctx["message"] == n.data["whatsapp_text"]
    # dd/mm/yyyy
    import re

    assert re.fullmatch(r"\d{2}/\d{2}/\d{4}", ctx["today_date"])
    assert ctx["today_date"] in n.body


def test_list_price_stamps_baseline_and_is_reported_once(db):
    _product(db, code="P1", price="120.00", notified="100.00")
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()

    first = _lp_run(db)
    p = db.query(Product).filter(Product.product_code == "P1").one()
    assert p.list_price_notified == Decimal("120.00")
    assert p.list_price_notified_at is not None
    assert p.list_price_notify_batch_id == first["batch_id"]

    second = _lp_run(db)
    assert second["pending"] == 0
    assert db.query(Notification).count() == 1


def test_list_price_revert_before_tick_not_reported(db):
    _product(db, code="P1", price="100.00", notified="100.00")
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()
    assert _lp_run(db)["pending"] == 0
    assert db.query(Notification).count() == 0


def test_new_product_adopts_baseline_silently(db):
    """A product with no baseline yet (new insert) is not a price change."""
    _product(db, code="NEW", price="99.00", notified=None)
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()
    out = _lp_run(db)
    assert out["pending"] == 0
    assert db.query(Notification).count() == 0
    p = db.query(Product).filter(Product.product_code == "NEW").one()
    assert p.list_price_notified == Decimal("99.00")
    # A later change IS reported.
    p.list_price = Decimal("109.00")
    db.commit()
    assert _lp_run(db)["pending"] == 1


def test_list_price_from_zero_has_no_percentage(db):
    _product(db, code="Z", price="10.00", notified="0.00")
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()
    _lp_run(db)
    n = db.query(Notification).one()
    assert "Z Name Z: RM 0.00 -> RM 10.00 (new price)" in n.body


def test_list_price_digest_caps_lines(db):
    for i in range(55):
        _product(db, code=f"C{i:02d}", price="101.00", notified="100.00")
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()
    _lp_run(db)
    n = db.query(Notification).one()
    assert n.title == "List price changed for 55 products"
    assert n.body.count("RM 100.00 -> RM 101.00") == 50
    assert "and 5 more" in n.body


def test_list_price_respects_brand_scope(db):
    from app.models.product import Brand

    b1, b2 = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(Brand(id=b1, brand_code="B1", brand_name="Brand 1"))
    db.add(Brand(id=b2, brand_code="B2", brand_name="Brand 2"))
    db.flush()
    p1 = _product(db, code="IN", price="110.00", notified="100.00")
    p1.brand_id = b1
    p2 = _product(db, code="OUT", price="110.00", notified="100.00")
    p2.brand_id = b2
    u = _user(db, email="sub@x.com", lp_email=True, scope=False)
    db.add(UserProductDiscontinuedScope(id=str(uuid.uuid4()), user_id=u.id, brand_id=b1))
    db.commit()

    _lp_run(db)
    n = db.query(Notification).one()
    assert "IN Name IN" in n.body
    assert "OUT Name OUT" not in n.body
    assert n.title == "List price changed for 1 product"


def test_list_price_batch_filter_on_product_list(db):
    from app.services.product_service import ProductService

    _product(db, code="P1", price="110.00", notified="100.00")
    _product(db, code="P2", price="100.00", notified="100.00")
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()
    batch = _lp_run(db)["batch_id"]

    q = ProductService(db)._build_list_query(list_price_batch_id=batch)
    assert {p.product_code for p in q.all()} == {"P1"}


def test_list_price_scheduler_handler_registered():
    from app.scheduler.task_scheduler import register_task_handlers
    from app.services.scheduled_task_service import TASK_HANDLERS

    register_task_handlers()
    assert "product_list_price_check" in TASK_HANDLERS


def test_list_price_whatsapp_use_case_registered():
    from app.models import respond_template

    src = open(respond_template.__file__).read()
    assert '"product_list_price_changed"' in src


# --------------------------------------------------------------------------- multi-company

MOCHA_ID = "00000000-0000-0000-0000-000000000002"


def _mocha(db):
    from app.models.company import Company
    from tests._pg_fixture import unique_code

    db.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
    db.flush()
    return MOCHA_ID


def test_list_price_stamps_reported_price_not_a_later_edit(db, monkeypatch):
    """Reviewer blocker: a two-company run where company 2's price moves while company 1
    is being notified. The stored watermark must be the price the message reported, so
    the later move is reported by the NEXT run instead of being swallowed."""
    from app.models.base import set_company_scope
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from app.services.notification_service import NotificationService
    from sqlalchemy import text

    set_company_scope(db, None)  # as the scheduler runs it: all companies
    mocha = _mocha(db)
    a = _product(db, code="A-SRT", price="110.00", notified="100.00")
    a.company_id = DEFAULT_COMPANY_ID
    b = _product(db, code="B-MCH", price="110.00", notified="100.00")
    b.company_id = mocha
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()

    orig = NotificationService.create_with_channel_preferences
    fired = {"done": False}

    def send_then_concurrent_edit(self, *args, **kwargs):
        if not fired["done"]:
            fired["done"] = True
            db.execute(text("UPDATE products SET list_price = 130 WHERE product_code = 'B-MCH'"))
        return orig(self, *args, **kwargs)

    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", send_then_concurrent_edit)

    first = _lp_run(db)
    assert first["pending"] == 2
    assert len(first["companies"]) == 2
    mocha_note = (
        db.query(Notification)
        .filter(Notification.title.like("Mocha:%"))
        .one()
    )
    assert "B-MCH Name B-MCH: RM 100.00 -> RM 110.00 (+10.0%)" in mocha_note.body
    db.expire_all()
    assert (
        db.query(Product).filter(Product.product_code == "B-MCH").one().list_price_notified
        == Decimal("110.00")
    )

    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", orig)
    second = _lp_run(db)
    assert second["pending"] == 1
    latest = db.query(Notification).filter(Notification.source_entity_id == second["batch_id"]).one()
    assert "B-MCH Name B-MCH: RM 110.00 -> RM 130.00 (+18.2%)" in latest.body


def test_list_price_baseline_respects_task_company_scope(db):
    """The new-product baseline step must not write outside the task's company scope."""
    from app.models.base import set_company_scope
    from app.services.company_scope import DEFAULT_COMPANY_ID

    set_company_scope(db, None)
    mocha = _mocha(db)
    s1 = _product(db, code="NEW-SRT", price="10.00", notified=None)
    s1.company_id = DEFAULT_COMPANY_ID
    m1 = _product(db, code="NEW-MCH", price="10.00", notified=None)
    m1.company_id = mocha
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    _lp_run(db)

    set_company_scope(db, None)
    db.expire_all()
    rows = {p.product_code: p.list_price_notified for p in db.query(Product).all()}
    assert rows["NEW-SRT"] == Decimal("10.00")
    assert rows["NEW-MCH"] is None


# --------------------------------------------------------------------------- source (audit trail)


def _audit(db, product, *, new_price, actor_type, user_id=None, changed_at=None):
    from app.models.audit import AuditLog

    row = AuditLog(
        id=str(uuid.uuid4()),
        entity_type="product",
        entity_id=str(product.id),
        action="UPDATE",
        old_values={"list_price": "100.00"},
        new_values={"list_price": new_price},
        actor_type=actor_type,
        user_id=user_id,
    )
    if changed_at is not None:
        row.changed_at = changed_at
    db.add(row)
    return row


def _line_for(db, code):
    n = db.query(Notification).one()
    return next(l for l in n.body.splitlines() if l.startswith(f"- {code} "))


def test_source_sync_change_credits_autocount_not_stale_ui_editor(db):
    """Crew decision on #2228: a price changed by the AutoCount push must never be credited
    to whoever last edited the product in the UI (``updated_by`` is stale after a push)."""
    stale_editor = _user(db, email="stale.editor@x.com", scope=False)
    db.flush()
    p = _product(db, code="SYNC", price="110.00", notified="100.00", updated_by=stale_editor.id)
    db.flush()
    _audit(db, p, new_price="110.00", actor_type="integration", user_id=stale_editor.id)
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()

    _lp_run(db)
    line = _line_for(db, "SYNC")
    assert line.endswith(", by AutoCount sync")
    assert "stale.editor" not in line


def test_source_staff_change_credits_the_staff_name(db):
    staff = _user(db, email="pricer@x.com", scope=False)
    db.flush()
    p = _product(db, code="UI", price="110.00", notified="100.00")
    db.flush()
    _audit(db, p, new_price="110.00", actor_type="user", user_id=staff.id)
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()

    _lp_run(db)
    assert _line_for(db, "UI").endswith(", by pricer")


def test_source_omitted_without_an_audit_row_even_with_updated_by(db):
    editor = _user(db, email="editor@x.com", scope=False)
    db.flush()
    _product(db, code="NOAUD", price="110.00", notified="100.00", updated_by=editor.id)
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()

    _lp_run(db)
    line = _line_for(db, "NOAUD")
    assert line == "- NOAUD Name NOAUD: RM 100.00 -> RM 110.00 (+10.0%)"


def test_source_omitted_when_audit_row_set_a_different_price(db):
    """The latest audited change is not the one being reported (a later unaudited bulk
    import moved the price again): no source rather than a wrong one."""
    staff = _user(db, email="pricer@x.com", scope=False)
    db.flush()
    p = _product(db, code="MOVED", price="120.00", notified="100.00")
    db.flush()
    _audit(db, p, new_price="110.00", actor_type="user", user_id=staff.id)
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()

    _lp_run(db)
    assert "by" not in _line_for(db, "MOVED")


def test_source_omitted_when_audit_row_predates_last_report(db):
    from datetime import datetime, timedelta

    staff = _user(db, email="pricer@x.com", scope=False)
    db.flush()
    p = _product(db, code="OLD", price="110.00", notified="100.00")
    p.list_price_notified_at = datetime.utcnow()
    db.flush()
    _audit(
        db, p, new_price="110.00", actor_type="user", user_id=staff.id,
        changed_at=datetime.utcnow() - timedelta(days=30),
    )
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()

    _lp_run(db)
    assert "by" not in _line_for(db, "OLD")


def test_source_through_the_real_audit_listener(db):
    """End to end: a real ORM price edit by a staff actor writes the audit row the source
    reads, so a rename of the audit entity type cannot silently turn every "by" off."""
    from app.audit_context import AuditActor, actor_scope
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    staff = _user(db, email="real.staff@x.com", scope=False)
    p = _product(db, code="REAL", price="100.00", notified="100.00")
    _user(db, email="sub@x.com", lp_email=True)
    db.commit()

    with actor_scope(AuditActor(actor_type="user", user_id=staff.id, real_user_id=staff.id), db=db):
        p.list_price = Decimal("125.00")
        db.commit()

    _lp_run(db)
    assert _line_for(db, "REAL") == "- REAL Name REAL: RM 100.00 -> RM 125.00 (+25.0%), by real.staff"
