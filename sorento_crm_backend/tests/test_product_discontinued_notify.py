"""Product-discontinued batch notification cron (product_discontinued_notify_service).

Covers the level-triggered batcher: pending = currently discontinued AND not yet
reported; revert-before-tick excluded; empty = no-op; already-notified skipped;
only subscribers notified; stamp-first; best-effort fan-out (one failure does not
abort the rest). Email-only subscribers keep the WhatsApp gate (and its respond
lookup) out of these tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.audit import AuditLog
from app.models.embeddings import EmbeddingQueue
from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.models.notification import Notification, NotificationDelivery, PushSubscription
from app.models.attachment_field_link import AttachmentFieldLink
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentDirectory, AttachmentType
from app.models.user import User
from app.schemas.product import ProductUpdate
from app.services.product_service import ProductService
import app.services.product_discontinued_notify_service as svc


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(_element, _compiler, **_kw):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Product.__table__,
            ProductCategory.__table__,
            Brand.__table__,
            UnitOfMeasure.__table__,
            AttachmentDirectory.__table__,
            AttachmentType.__table__,
            Attachment.__table__,
            AttachmentFieldLink.__table__,
            User.__table__,
            Notification.__table__,
            NotificationDelivery.__table__,
            PushSubscription.__table__,
            LookupSet.__table__,
            LookupOption.__table__,
            LookupBinding.__table__,
            AuditLog.__table__,
            EmbeddingQueue.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _product(db, *, code: str, discontinued: bool, notified_at=None, batch_id=None):
    p = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description="**** EOL" if discontinued else "active",
        category_id=str(uuid.uuid4()),
        base_uom_id=str(uuid.uuid4()),
        list_price=10,
        is_active=True,
        is_discontinued=discontinued,
        discontinued_notified_at=notified_at,
        discontinued_notify_batch_id=batch_id,
    )
    db.add(p)
    return p


def _user(db, *, email: str, email_pref=False, wa_pref=False):
    u = User(
        id=str(uuid.uuid4()),
        email=email,
        name=email.split("@")[0],
        status="ACTIVE",
        notify_email_on_product_discontinued=email_pref,
        notify_whatsapp_on_product_discontinued=wa_pref,
    )
    db.add(u)
    return u


def test_pending_picked_stamped_and_notified(db):
    _product(db, code="A", discontinued=True)
    _product(db, code="B", discontinued=True)
    sub = _user(db, email="sub@x.com", email_pref=True)
    _user(db, email="nobody@x.com")  # not a subscriber
    db.commit()

    out = svc.run_product_discontinued_check(db)

    assert out["pending"] == 2
    assert out["subscribers"] == 1
    assert out["notified_users"] == 1
    batch_id = out["batch_id"]
    assert batch_id

    # Both products stamped with the same run time + batch id.
    for code in ("A", "B"):
        p = db.query(Product).filter(Product.product_code == code).one()
        assert p.discontinued_notified_at is not None
        assert p.discontinued_notify_batch_id == batch_id

    # Exactly one notification, to the subscriber, count + link in the body.
    notes = db.query(Notification).all()
    assert len(notes) == 1
    n = notes[0]
    assert n.user_id == sub.id
    assert n.type == "product_discontinued"
    assert n.source_entity_type == "product_discontinued_batch"
    assert n.source_entity_id == batch_id
    assert "2 products" in n.title
    assert batch_id in (n.data or {}).get("discontinued_link", "")


def test_revert_before_tick_excluded(db):
    # Discontinued then reverted before the cron => is_discontinued False => excluded.
    _product(db, code="REVERTED", discontinued=False)
    _product(db, code="STILL", discontinued=True)
    _user(db, email="sub@x.com", email_pref=True)
    db.commit()

    out = svc.run_product_discontinued_check(db)

    assert out["pending"] == 1
    still = db.query(Product).filter(Product.product_code == "STILL").one()
    reverted = db.query(Product).filter(Product.product_code == "REVERTED").one()
    assert still.discontinued_notify_batch_id == out["batch_id"]
    assert reverted.discontinued_notify_batch_id is None


def test_empty_batch_is_noop(db):
    _user(db, email="sub@x.com", email_pref=True)
    db.commit()

    out = svc.run_product_discontinued_check(db)

    assert out == {"pending": 0, "subscribers": 0, "notified_users": 0, "batch_id": None}
    assert db.query(Notification).count() == 0


def test_already_notified_not_repicked(db):
    # notified_at already set (prior batch) => not pending, not re-reported.
    old_batch = str(uuid.uuid4())
    _product(db, code="DONE", discontinued=True, notified_at=datetime.utcnow(), batch_id=old_batch)
    _user(db, email="sub@x.com", email_pref=True)
    db.commit()

    out = svc.run_product_discontinued_check(db)

    assert out["pending"] == 0
    assert db.query(Notification).count() == 0
    done = db.query(Product).filter(Product.product_code == "DONE").one()
    assert done.discontinued_notify_batch_id == old_batch  # untouched


def test_only_subscribers_notified_multiple(db):
    _product(db, code="A", discontinued=True)
    s1 = _user(db, email="s1@x.com", email_pref=True)
    s2 = _user(db, email="s2@x.com", email_pref=True)
    _user(db, email="off@x.com", email_pref=False, wa_pref=False)
    db.commit()

    out = svc.run_product_discontinued_check(db)

    assert out["subscribers"] == 2
    assert out["notified_users"] == 2
    recipients = {n.user_id for n in db.query(Notification).all()}
    assert recipients == {s1.id, s2.id}


def test_update_to_active_clears_marker(db):
    # Discontinued + already reported, then description edited to drop the ****
    # => is_discontinued False AND notify watermark reset (so a later re-discontinue
    # is reported again).
    p = _product(
        db, code="X", discontinued=True,
        notified_at=datetime.utcnow(), batch_id=str(uuid.uuid4()),
    )
    db.commit()

    ProductService(db).update_product(p.id, ProductUpdate(description="now active"), updated_by="t")

    db.refresh(p)
    assert p.is_discontinued is False
    assert p.discontinued_notified_at is None
    assert p.discontinued_notify_batch_id is None


def test_update_still_discontinued_keeps_marker(db):
    # Re-saving a still-discontinued product (description stays ****) must NOT clear
    # the watermark, so the cron does not re-report it.
    batch = str(uuid.uuid4())
    when = datetime.utcnow()
    p = _product(db, code="Y", discontinued=True, notified_at=when, batch_id=batch)
    db.commit()

    ProductService(db).update_product(p.id, ProductUpdate(description="**** still EOL"), updated_by="t")

    db.refresh(p)
    assert p.is_discontinued is True
    assert p.discontinued_notified_at is not None
    assert p.discontinued_notify_batch_id == batch


def test_best_effort_one_failure_does_not_abort(db, monkeypatch):
    _product(db, code="A", discontinued=True)
    bad = _user(db, email="bad@x.com", email_pref=True)
    good = _user(db, email="good@x.com", email_pref=True)
    db.commit()

    real = svc.NotificationService.create_with_channel_preferences

    def flaky(self, *args, **kwargs):
        if kwargs.get("user_id") == bad.id:
            raise RuntimeError("simulated send failure")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(svc.NotificationService, "create_with_channel_preferences", flaky)

    out = svc.run_product_discontinued_check(db)

    # Batch still stamped; the good user is still notified despite the bad one failing.
    assert out["subscribers"] == 2
    assert out["notified_users"] == 1
    recipients = {n.user_id for n in db.query(Notification).all()}
    assert recipients == {good.id}
    p = db.query(Product).filter(Product.product_code == "A").one()
    assert p.discontinued_notify_batch_id == out["batch_id"]
