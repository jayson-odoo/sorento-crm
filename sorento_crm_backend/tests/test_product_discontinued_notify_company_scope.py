"""The discontinued-product check batches per company, within the task scope.

The failure this guards against is not subtle: the job reads `products` with the
scheduler's company scope set to all companies, so before this change a second
company's entire discontinued catalogue would arrive as one notification - counted
together with Sorento's, behind one deep link - aimed at staff who do not handle that
catalogue.

Two properties matter and they pull in opposite directions:
  - a company that was never opted in must be left COMPLETELY alone, including its
    `discontinued_notified_at` (stamping it would silence its real first report later)
  - a company that IS opted in must get its own batch, never a shared one
"""
from __future__ import annotations

import uuid

import pytest

from app.models.company import Company
from app.models.notification import Notification
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import User, UserProductDiscontinuedScope
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
import app.services.product_discontinued_notify_service as svc
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as session:
        # Mirror the scheduler, which sets scope=None (all companies). The shared
        # conftest defaults sessions to Sorento, which would hide every Mocha row
        # behind the ORM filter and make these tests pass for the wrong reason -
        # "no Mocha notification" because Mocha was invisible, not because it was
        # correctly skipped.
        set_company_scope(session, None)
        yield session


MOCHA_ID = "00000000-0000-0000-0000-000000000002"


def _second_company(db) -> str:
    """Sorento is auto-seeded by the fixture; a second company is not."""
    db.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
    db.flush()
    return MOCHA_ID


def _refs(db):
    if not hasattr(db, "_refs"):
        cat, uom = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(ProductCategory(id=cat, category_code="CAT1", category_name="Category One"))
        db.add(UnitOfMeasure(id=uom, uom_code="EA", uom_name="Each"))
        db.flush()
        db._refs = (cat, uom)
    return db._refs


def _product(db, *, code: str, company_id: str):
    cat, uom = _refs(db)
    p = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        category_id=cat,
        base_uom_id=uom,
        list_price=10,
        is_active=True,
        is_discontinued=True,
        company_id=company_id,
    )
    db.add(p)
    return p


def _subscriber(db):
    u = User(
        id=str(uuid.uuid4()),
        email=f"sub-{uuid.uuid4().hex[:6]}@x.com",
        name="Sub",
        status="ACTIVE",
        notify_email_on_product_discontinued=True,
    )
    db.add(u)
    # The all-companies / all-brands scope every pre-existing subscriber is given
    # by migration 375. Without a scope a user hears nothing, so this is what
    # "subscribed to everything" now looks like.
    db.add(UserProductDiscontinuedScope(id=str(uuid.uuid4()), user_id=u.id))
    return u


def _scope(db, company_ids):
    """Apply the scope the scheduler would apply for a task carrying these ids.

    The job no longer reads any configuration of its own - the scheduler narrows the
    session from the task's ``metadata.company_ids`` before calling it - so the tests
    set the same thing the scheduler would.
    """
    set_company_scope(db, frozenset(company_ids) if company_ids else None)


def _by_code(db, code: str) -> Product:
    return db.query(Product).filter(Product.product_code == code).one()


# --- reporting -------------------------------------------------------------- #

def test_a_company_outside_the_task_scope_is_left_completely_alone(db):
    """The narrowing case: task metadata.company_ids = [Sorento]."""
    mocha = _second_company(db)
    _product(db, code="SRT-1", company_id=DEFAULT_COMPANY_ID)
    _product(db, code="MCH-1", company_id=mocha)
    _subscriber(db)
    db.commit()
    _scope(db, [DEFAULT_COMPANY_ID])

    out = svc.run_product_discontinued_check(db)

    assert out["pending"] == 1, "only Sorento's product should have been reported"
    # Mocha keeps its NULL stamp. Stamping a company the task cannot see would
    # silence its genuine first report on the day someone widens the scope.
    _scope(db, None)
    assert _by_code(db, "MCH-1").discontinued_notified_at is None
    assert _by_code(db, "SRT-1").discontinued_notified_at is not None


def test_each_company_gets_its_own_batch(db):
    mocha = _second_company(db)
    _product(db, code="SRT-1", company_id=DEFAULT_COMPANY_ID)
    _product(db, code="MCH-1", company_id=mocha)
    _product(db, code="MCH-2", company_id=mocha)
    _subscriber(db)
    db.commit()
    _scope(db, None)  # task unconfigured = every company

    out = svc.run_product_discontinued_check(db)

    assert out["pending"] == 3
    srt_batch = _by_code(db, "SRT-1").discontinued_notify_batch_id
    mch_batch = _by_code(db, "MCH-1").discontinued_notify_batch_id
    assert srt_batch and mch_batch
    assert srt_batch != mch_batch, "a batch must never span two companies"
    assert _by_code(db, "MCH-2").discontinued_notify_batch_id == mch_batch
    # Aggregate batch_id is only meaningful for a single reporting company.
    assert out["batch_id"] is None
    assert {c["company_id"] for c in out["companies"]} == {DEFAULT_COMPANY_ID, mocha}


def test_counts_are_per_company_not_summed_in_the_message(db):
    """The count is the whole message; 3 products across 2 catalogues is not "3"."""
    mocha = _second_company(db)
    _product(db, code="SRT-1", company_id=DEFAULT_COMPANY_ID)
    _product(db, code="MCH-1", company_id=mocha)
    _product(db, code="MCH-2", company_id=mocha)
    _subscriber(db)
    db.commit()
    _scope(db, None)  # task unconfigured = every company

    svc.run_product_discontinued_check(db)

    titles = sorted(n.title for n in db.query(Notification).all())
    assert len(titles) == 2
    assert any("1 product" in t for t in titles)
    assert any("2 products" in t for t in titles)


def test_the_company_is_named_when_the_run_spans_more_than_one(db):
    """Both companies need pending rows: the label exists to disambiguate two
    notifications arriving together, so a run covering one company never earns it."""
    mocha = _second_company(db)
    _product(db, code="SRT-1", company_id=DEFAULT_COMPANY_ID)
    _product(db, code="MCH-1", company_id=mocha)
    _subscriber(db)
    db.commit()
    _scope(db, None)  # task unconfigured = every company

    svc.run_product_discontinued_check(db)

    titles = sorted(n.title for n in db.query(Notification).all())
    assert len(titles) == 2, titles
    assert any(t.startswith("Mocha: ") for t in titles), titles
    assert any(t.startswith("Sorento: ") for t in titles), titles


def test_the_single_company_install_keeps_its_existing_copy(db):
    """Sorento-only production must not suddenly gain a company prefix."""
    _product(db, code="SRT-1", company_id=DEFAULT_COMPANY_ID)
    _subscriber(db)
    db.commit()
    _scope(db, None)

    svc.run_product_discontinued_check(db)

    note = db.query(Notification).one()
    assert note.title == "1 product discontinued", note.title


def test_nothing_pending_anywhere_is_a_quiet_no_op(db):
    mocha = _second_company(db)
    _subscriber(db)
    db.commit()
    _scope(db, None)  # task unconfigured = every company

    out = svc.run_product_discontinued_check(db)

    assert out["pending"] == 0
    assert out["notified_users"] == 0
    assert db.query(Notification).count() == 0


def test_one_company_pending_still_reports_its_batch_id(db):
    """A run that reports a single company keeps the flat batch_id the log always had."""
    mocha = _second_company(db)
    _product(db, code="MCH-1", company_id=mocha)
    _subscriber(db)
    db.commit()
    _scope(db, None)  # task unconfigured = every company

    out = svc.run_product_discontinued_check(db)

    assert out["pending"] == 1
    assert out["batch_id"] == _by_code(db, "MCH-1").discontinued_notify_batch_id
