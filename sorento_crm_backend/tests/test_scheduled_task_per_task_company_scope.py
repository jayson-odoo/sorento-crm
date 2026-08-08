"""Per-task company scope (``metadata.company_ids``), and its regression guard.

Sibling of ``test_scheduled_task_company_scope.py``, which pins the #69 fix: every
handler must run system-scoped rather than UNSET. This file pins the narrowing built
on top of it.

The property that matters most here is the NEGATIVE one. There are ~25 registered
tasks and exactly one wanted this, so "a task that does not set the key behaves
exactly as before" is what makes the change safe to ship at all.

The second guard is blast radius. Narrowing restricts the 35 ``CompanyScopedMixin``
business tables; it must NOT reach users, notifications or the scheduler's own
tables, or a narrowed job would quietly stop notifying anyone and look dead.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.base import get_company_scope, set_company_scope
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
    """The filter is an ORM event registered by app.main at import time; without it
    the scope is never applied and these tests would prove nothing. Idempotent."""
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        yield session


def _task(db, *, key: str, metadata=None, due: bool = False) -> ScheduledTask:
    row = ScheduledTask(
        key=key,
        name=f"probe {key}",
        enabled=True,
        interval_unit="hours",
        interval_value=1,
        timezone="UTC",
        metadata_=metadata,
    )
    if due:
        row.next_run_at = datetime.utcnow() - timedelta(days=1)
    db.add(row)
    db.flush()
    return row


# --- resolution ------------------------------------------------------------- #

def test_no_metadata_means_every_company(db):
    """The state of all ~25 existing tasks. None == no predicate == today's behaviour."""
    assert sts.task_company_scope(_task(db, key="anything")) is None


def test_metadata_without_company_ids_means_every_company(db):
    """Several tasks already carry unrelated metadata keys (send_email, grace_percent)."""
    task = _task(db, key="user_sla_daily_summary", metadata={"send_email": True})
    assert sts.task_company_scope(task) is None


def test_explicit_null_means_every_company(db):
    """null is the admin UI's "clear this key" sentinel, not "no companies"."""
    assert sts.task_company_scope(_task(db, key="x", metadata={"company_ids": None})) is None


def test_empty_list_means_every_company_not_none(db):
    """An empty frozenset would fail-closed to zero rows and read as a broken job."""
    assert sts.task_company_scope(_task(db, key="x", metadata={"company_ids": []})) is None


def test_a_configured_list_narrows(db):
    task = _task(db, key="x", metadata={"company_ids": [DEFAULT_COMPANY_ID, MOCHA_ID]})
    assert sts.task_company_scope(task) == frozenset({DEFAULT_COMPANY_ID, MOCHA_ID})


def test_a_comma_string_is_accepted(db):
    task = _task(db, key="x", metadata={"company_ids": f" {DEFAULT_COMPANY_ID} , {MOCHA_ID} "})
    assert sts.task_company_scope(task) == frozenset({DEFAULT_COMPANY_ID, MOCHA_ID})


# --- blast radius ----------------------------------------------------------- #

def _refs(db):
    if not hasattr(db, "_refs"):
        cat, uom = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(ProductCategory(id=cat, category_code="CAT1", category_name="C"))
        db.add(UnitOfMeasure(id=uom, uom_code="EA", uom_name="Each"))
        db.flush()
        db._refs = (cat, uom)
    return db._refs


def _product(db, *, code: str, company_id: str):
    cat, uom = _refs(db)
    db.add(
        Product(
            id=str(uuid.uuid4()), product_code=code, product_name=code,
            category_id=cat, base_uom_id=uom, list_price=10,
            is_active=True, is_discontinued=True, company_id=company_id,
        )
    )


def test_narrowing_filters_business_rows(db):
    db.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
    _product(db, code="SRT-1", company_id=DEFAULT_COMPANY_ID)
    _product(db, code="MCH-1", company_id=MOCHA_ID)
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    assert {p.product_code for p in db.query(Product).all()} == {"SRT-1"}


def test_narrowing_does_not_hide_users_or_notifications(db):
    """If narrowing reached these, a scoped job would stop notifying anyone."""
    user = User(
        id=str(uuid.uuid4()), email=f"u-{uuid.uuid4().hex[:6]}@x.com",
        name="U", status="ACTIVE",
    )
    db.add(user)
    db.flush()
    db.add(Notification(id=str(uuid.uuid4()), user_id=user.id, type="t", title="t", body="b"))
    db.commit()

    set_company_scope(db, frozenset({MOCHA_ID}))
    assert db.query(User).filter(User.id == user.id).first() is not None, "users must stay visible"
    assert db.query(Notification).count() >= 1, "notifications must stay visible"


# --- the sweep -------------------------------------------------------------- #

def test_each_task_runs_under_its_own_scope_and_does_not_leak_it(db):
    """Two due tasks in one sweep: the narrowed one must not affect the open one.

    Ordering is not asserted - only that both scopes were observed, so this does not
    depend on which task get_due_tasks returns first.
    """
    scoped_key = f"zzt_scoped_{uuid.uuid4().hex[:8]}"
    open_key = f"zzt_open_{uuid.uuid4().hex[:8]}"
    seen: dict[str, object] = {}

    def make_probe(name):
        def probe(session, task):
            seen[name] = get_company_scope(session)
            return {"ok": True}
        return probe

    sts.register_handler(scoped_key, make_probe("scoped"))
    sts.register_handler(open_key, make_probe("open"))
    try:
        _task(db, key=scoped_key, metadata={"company_ids": [MOCHA_ID]}, due=True)
        _task(db, key=open_key, due=True)
        db.commit()

        sts.run_due_tasks(db)

        assert seen.get("scoped") == frozenset({MOCHA_ID}), (
            f"narrowed task did not run narrowed: {seen.get('scoped')!r}"
        )
        assert seen.get("open") is None, (
            f"unconfigured task must stay wide open, got {seen.get('open')!r} "
            "- a leaked scope here would silently shrink 24 other jobs"
        )
    finally:
        sts.TASK_HANDLERS.pop(scoped_key, None)
        sts.TASK_HANDLERS.pop(open_key, None)


def test_the_scope_is_reset_after_the_sweep(db):
    """The finally block must restore None even for the last task in the sweep."""
    key = f"zzt_last_{uuid.uuid4().hex[:8]}"
    sts.register_handler(key, lambda session, task: {"ok": True})
    try:
        _task(db, key=key, metadata={"company_ids": [MOCHA_ID]}, due=True)
        db.commit()
        sts.run_due_tasks(db)
        assert get_company_scope(db) is None
    finally:
        sts.TASK_HANDLERS.pop(key, None)


def test_a_failing_narrowed_task_still_restores_the_scope(db):
    """A raise inside the handler must not leave the session narrowed for the next task."""
    key = f"zzt_boom_{uuid.uuid4().hex[:8]}"

    def boom(session, task):
        raise RuntimeError("boom")

    sts.register_handler(key, boom)
    try:
        _task(db, key=key, metadata={"company_ids": [MOCHA_ID]}, due=True)
        db.commit()
        sts.run_due_tasks(db)  # the sweep swallows handler errors into a failed run
        assert get_company_scope(db) is None
    finally:
        sts.TASK_HANDLERS.pop(key, None)
