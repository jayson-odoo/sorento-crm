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

from app.models.notification import Notification
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import User, UserProductDiscontinuedScope
from app.schemas.product import ProductUpdate
from app.services.product_service import ProductService
import app.services.product_discontinued_notify_service as svc
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    """A blank Postgres schema, rolled back after the test.

    Was in-memory sqlite with a JSONB->JSON compile shim and a hand-listed
    subset of tables that had to be extended whenever a global listener started
    touching a new one. The real schema has all 199.
    """
    with blank_session() as session:
        yield session


def _parent_refs(db):
    """The category + UOM rows Product's NOT NULL FKs point at.

    sqlite let each product carry a random unmatched UUID in these columns;
    Postgres enforces them, so one real parent pair is shared by the products a
    test creates.
    """
    if not hasattr(db, "_refs"):
        category_id = str(uuid.uuid4())
        uom_id = str(uuid.uuid4())
        db.add(ProductCategory(id=category_id, category_code="CAT1", category_name="Category One"))
        db.add(UnitOfMeasure(id=uom_id, uom_code="EA", uom_name="Each"))
        db.flush()
        db._refs = (category_id, uom_id)
    return db._refs


def _product(db, *, code: str, discontinued: bool, notified_at=None, batch_id=None):
    category_id, uom_id = _parent_refs(db)
    p = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description="**** EOL" if discontinued else "active",
        category_id=category_id,
        base_uom_id=uom_id,
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
    if email_pref or wa_pref:
        # The all-companies / all-brands scope every pre-existing subscriber is
        # given by migration 375. Without a scope a user hears nothing, so this is
        # what "subscribed to everything" now looks like.
        db.add(UserProductDiscontinuedScope(id=str(uuid.uuid4()), user_id=u.id))
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

    # Compared key-by-key rather than whole-dict: the result now also carries a
    # per-company breakdown under "companies", and pinning the exact dict shape
    # makes an additive field look like a behaviour change.
    assert out["pending"] == 0
    assert out["subscribers"] == 0
    assert out["notified_users"] == 0
    assert out["batch_id"] is None
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

    ProductService(db).update_product(p.id, ProductUpdate(description="now active"), updated_by="90fbc7bc-61d3-57e0-8328-af7cf485afdf")

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

    ProductService(db).update_product(p.id, ProductUpdate(description="**** still EOL"), updated_by="90fbc7bc-61d3-57e0-8328-af7cf485afdf")

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
