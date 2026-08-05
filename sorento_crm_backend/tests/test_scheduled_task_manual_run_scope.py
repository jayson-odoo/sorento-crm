"""Manual "Run now" must see the same rows the scheduled run sees.

This is a real defect that shipped, not a hypothetical. ``_execute_task_run`` opens
its own bare ``SessionLocal()`` for the background thread. A bare session has no
``company_scope`` key, absent reads as ``UNSET``, and ``UNSET`` compiles to
``false()`` - so EVERY company-scoped table returned zero rows while the run logged
``status=success``. #69 fixed exactly this for the cron path (``run_due_tasks``) and
never touched this one.

Observed live on the dev database: three products discontinued and pending, and four
consecutive manual runs of ``product_discontinued_check`` all reported
``{"pending": 0}`` and success. Nothing in the UI suggested a problem - a silent zero
is indistinguishable from "nothing to do".

So the guard here is not "the scope equals X", it is "the handler can actually SEE
its rows when run manually", which is the property that was broken.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.models.base import UNSET, get_company_scope, set_company_scope
from app.models.company import Company
from app.models.notification import Notification
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scheduled_task import ScheduledTask
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services import scheduled_task_service as sts

from ._pg_fixture import blank_session, unique_code

MOCHA_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        yield session


@pytest.fixture
def as_background_session(db, monkeypatch):
    """Make ``_execute_task_run``'s own ``SessionLocal()`` hand back the scratch session.

    The function deliberately opens a FRESH session (it runs in a background thread),
    which is the whole reason the scope was missing. To exercise it against the
    scratch schema, hand it this session and neuter close() so the fixture keeps
    ownership of the rollback.

    Crucially the scope key is DELETED first, reproducing what a real bare
    SessionLocal() arrives with. Leaving the fixture's None in place would mask the
    bug completely.
    """
    db.info.pop("company_scope", None)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(sts, "SessionLocal", lambda: db)
    return db


def _task(db, *, key: str, metadata=None) -> ScheduledTask:
    row = ScheduledTask(
        key=key, name=f"probe {key}", enabled=True,
        interval_unit="hours", interval_value=1, timezone="UTC",
        metadata_=metadata,
    )
    db.add(row)
    db.flush()
    return row


def _refs(db):
    if not hasattr(db, "_refs"):
        cat, uom = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(ProductCategory(id=cat, category_code="CAT1", category_name="C"))
        db.add(UnitOfMeasure(id=uom, uom_code="EA", uom_name="Each"))
        db.flush()
        db._refs = (cat, uom)
    return db._refs


def _discontinued(db, *, code: str, company_id: str):
    cat, uom = _refs(db)
    db.add(
        Product(
            id=str(uuid.uuid4()), product_code=code, product_name=code,
            category_id=cat, base_uom_id=uom, list_price=10,
            is_active=True, is_discontinued=True, company_id=company_id,
        )
    )


def _subscriber(db):
    db.add(
        User(
            id=str(uuid.uuid4()), email=f"sub-{uuid.uuid4().hex[:6]}@x.com",
            name="Sub", status="ACTIVE",
            notify_email_on_product_discontinued=True,
        )
    )


def _run_manually(db, task) -> None:
    run = sts.create_run(db, sts._task_id(task), status="started")
    sts._execute_task_run(
        sts._task_id(task), sts._run_id(run), sts._task_key(task), None
    )


# --- the defect ------------------------------------------------------------- #

def test_a_manual_run_does_not_hand_the_handler_an_unset_scope(as_background_session):
    """The bug in one assertion: UNSET means every company-scoped query returns zero."""
    db = as_background_session
    key = f"zzt_manual_{uuid.uuid4().hex[:8]}"
    seen: dict = {}

    sts.register_handler(key, lambda session, task: seen.setdefault("scope", get_company_scope(session)) or {})
    try:
        task = _task(db, key=key)
        db.commit()
        _run_manually(db, task)

        assert "scope" in seen, "handler never ran"
        assert seen["scope"] is not UNSET, (
            "manual run handed the handler an UNSET scope - every company-scoped "
            "query it makes silently returns zero rows while the run logs success"
        )
        assert seen["scope"] is None
    finally:
        sts.TASK_HANDLERS.pop(key, None)


def test_a_manual_run_honours_the_tasks_company_scope(as_background_session):
    """Manual and scheduled runs must not disagree about which companies are in play."""
    db = as_background_session
    key = f"zzt_manual_scoped_{uuid.uuid4().hex[:8]}"
    seen: dict = {}

    sts.register_handler(key, lambda session, task: seen.setdefault("scope", get_company_scope(session)) or {})
    try:
        task = _task(db, key=key, metadata={"company_ids": [MOCHA_ID]})
        db.commit()
        _run_manually(db, task)

        assert seen.get("scope") == frozenset({MOCHA_ID})
    finally:
        sts.TASK_HANDLERS.pop(key, None)


# --- the symptom the user actually saw -------------------------------------- #

def test_run_now_on_the_discontinued_check_finds_its_pending_products(as_background_session):
    """Reproduces the live report: pending products present, every manual run said 0.

    Two companies with pending rows, so this also pins that a manual run batches per
    company exactly like the scheduled one.
    """
    db = as_background_session
    from app.scheduler.task_scheduler import register_task_handlers

    register_task_handlers()
    db.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
    _discontinued(db, code="SRT-A", company_id=DEFAULT_COMPANY_ID)
    _discontinued(db, code="SRT-B", company_id=DEFAULT_COMPANY_ID)
    _discontinued(db, code="MCH-A", company_id=MOCHA_ID)
    _subscriber(db)
    task = _task(db, key="product_discontinued_check")
    db.commit()

    _run_manually(db, task)

    set_company_scope(db, None)
    remaining = (
        db.query(Product)
        .filter(Product.is_discontinued.is_(True), Product.discontinued_notified_at.is_(None))
        .count()
    )
    assert remaining == 0, (
        f"{remaining} pending product(s) went unreported by a manual run - this is the "
        "silent zero that looked like success"
    )
    titles = sorted(n.title for n in db.query(Notification).all())
    assert len(titles) == 2, f"expected one notification per company, got {titles}"
    assert any(t.startswith("Sorento: 2 products") for t in titles), titles
    assert any(t.startswith("Mocha: 1 product") for t in titles), titles


def test_a_scoped_manual_run_uses_the_tasks_companies_not_the_ambient_scope(
    as_background_session,
):
    """Narrowing must hold on the manual path, and must come from the TASK.

    Deliberately scopes the task to MOCHA, which is the opposite of the ambient
    default. `tests/conftest.py` re-applies a Sorento scope on every transaction
    begin (`session.info.setdefault`), so it comes back after any commit - an
    earlier version of this test scoped the task to Sorento and passed even with
    the fix reverted, because conftest was doing the scoping, not the code.

    Scoping to Mocha makes the two explanations disagree: only the real fix stamps
    Mocha and leaves Sorento pending.
    """
    db = as_background_session
    from app.scheduler.task_scheduler import register_task_handlers

    register_task_handlers()
    db.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
    _discontinued(db, code="SRT-A", company_id=DEFAULT_COMPANY_ID)
    _discontinued(db, code="MCH-A", company_id=MOCHA_ID)
    _subscriber(db)
    task = _task(db, key="product_discontinued_check", metadata={"company_ids": [MOCHA_ID]})
    db.commit()

    _run_manually(db, task)

    set_company_scope(db, None)
    mocha = db.query(Product).filter(Product.product_code == "MCH-A").one()
    sorento = db.query(Product).filter(Product.product_code == "SRT-A").one()
    assert mocha.discontinued_notified_at is not None, (
        "the task's own company was not reported - the manual run is not honouring "
        "metadata.company_ids"
    )
    assert sorento.discontinued_notified_at is None, (
        "a company outside the task scope was stamped - its genuine first report "
        "would be silenced on the day someone widens the scope"
    )
    assert db.query(Notification).count() == 1
