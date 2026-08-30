"""Deferred record actions - the grace window behind the product's delete (S6).

    POST /api/v1/pending-actions
    POST /api/v1/pending-actions/{id}/cancel
    GET  /api/v1/pending-actions/current?entity_type&entity_id

Written test-first, against the contract the Phase-1 frontend already consumes
(`services/pendingActionService.ts`). Two things it exists to pin:

1. **Nothing is applied until the window lapses**, and when it does, the SERVER
   applies it - the browser is not in the loop, so closing the tab still commits
   (S6-08). A commit that fails says so in `last_outcome`, because a countdown
   that simply disappears reads exactly like success (S6-03).
2. **The response fields.** The countdown drains against `commit_at` and sizes its
   bar with `window_seconds`; the hook tells a commit from a failure with
   `last_outcome.status`, and tells two actions on one record apart with
   `last_outcome.action_key`. Any of those missing is a silent UI defect, so each
   is asserted on the wire.

Postgres only, on the blank scratch schema, seeding its own chain - CI's database
is empty, so nothing may be borrowed from an existing table.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.order import Order, OrderStatus
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.sla import (
    FORM_ACTION_CANCELLED,
    FORM_ACTION_COMMITTED,
    FORM_ACTION_FAILED,
    FORM_ACTION_PENDING,
    SlaFormAction,
)
from app.models.user import SystemSetting, User
from tests._pg_fixture import blank_session

BASE = "/api/v1/pending-actions"
MARKER = "ZZT-PENDING"

PRODUCT_DELETE = "master_data.products.delete"
ORDER_DELETE = "order_management.orders.delete"
ORDER_EDIT = "order_management.orders.edit"
USER_DELETE = "user_management.users.delete"
ALL_SLUGS = {PRODUCT_DELETE, ORDER_DELETE, ORDER_EDIT, USER_DELETE}


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def client(monkeypatch):
    from fastapi import Depends

    from app.database import get_db
    from app.dependencies import get_current_user
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    with blank_session() as db:

        def _override_get_db():
            yield db

        # A real row, not just a dict: `sla_form_actions.requested_by_id` is a FK to
        # users, and `current` resolves the requester's NAME for the second browser.
        actor_row = User(id=_uid(), email=f"zzt-actor-{_uid()[:8]}@example.test", name="Ada Actor")
        db.add(actor_row)
        db.commit()
        actor = {"id": actor_row.id, "email": actor_row.email, "name": actor_row.name}
        allowed: set[str] = set(ALL_SLUGS)

        def _override_scope(_db=Depends(get_db)):
            # The resolver reads an Authorization header this client does not send and
            # would fail closed, which then hides the test's own seeded rows from the
            # SESSION for the rest of the test. Scope is not what S6 is about.
            set_company_scope(_db, None)
            return None

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: actor
        # The repo's convention for a per-slug grant in a route test: the allow-set is
        # mutable, so one test can withdraw a single slug and keep the rest.
        monkeypatch.setattr(
            UserPermissionService,
            "check_user_has_permission",
            lambda self, uid, slug: slug in allowed,
        )
        try:
            with TestClient(app) as c:
                yield c, db, actor, allowed
        finally:
            app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Seeds
# --------------------------------------------------------------------------- #


def _product(db) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"{MARKER}-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=f"{MARKER}-{_uid()[:8]}",
        product_name=f"{MARKER} chair",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.commit()
    return row


def _order_status(db, code: str, name: str) -> OrderStatus:
    row = OrderStatus(
        id=_uid(), status_code=f"{MARKER}-{code}-{_uid()[:6]}", status_name=name
    )
    db.add(row)
    db.commit()
    return row


def _order(db, status: OrderStatus) -> Order:
    row = Order(
        id=_uid(),
        order_number=f"{MARKER}-{_uid()[:8]}",
        order_status_id=status.id,
    )
    db.add(row)
    db.commit()
    return row


def _user(db) -> User:
    row = User(
        id=_uid(),
        email=f"zzt-{_uid()[:8]}@example.test",
        name=f"{MARKER} target",
    )
    db.add(row)
    db.commit()
    return row


def _settings(db, **columns) -> SystemSetting:
    row = SystemSetting(id=_uid(), name=f"{MARKER} co", **columns)
    db.add(row)
    db.commit()
    return row


def _start(c, action_key: str, entity_type: str, entity_id: str, payload=None):
    return c.post(
        BASE,
        json={
            "action_key": action_key,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "payload": payload or {},
        },
    )


def _current(c, entity_type: str, entity_id: str):
    return c.get(
        f"{BASE}/current",
        params={"entity_type": entity_type, "entity_id": str(entity_id)},
    )


def _lapse(db, action_id: str) -> None:
    """Move the window into the past without waiting ten real seconds."""
    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)},
        synchronize_session=False,
    )
    db.commit()


# --------------------------------------------------------------------------- #
# S6-01 - park it, apply nothing
# --------------------------------------------------------------------------- #


def test_post_parks_the_action_and_applies_nothing(client):
    c, db, _actor, _allowed = client
    product = _product(db)

    response = _start(c, "product.delete", "product", product.id)

    assert response.status_code == 202, response.text
    body = response.json()
    assert set(body) >= {"id", "commit_at", "window_seconds"}
    assert body["window_seconds"] == 10
    # The countdown parses this as naive UTC; an offset would make the bar drain
    # eight hours early in Malaysia.
    assert "+" not in body["commit_at"] and not body["commit_at"].endswith("Z")

    assert db.query(Product).filter(Product.id == product.id).first() is not None


def test_second_post_for_the_same_entity_and_action_returns_the_same_row(client):
    """A double click must not park two deletes, and must not error either - the
    reader clicked the same thing twice and the answer is the same countdown."""
    c, db, _actor, _allowed = client
    product = _product(db)

    first = _start(c, "product.delete", "product", product.id)
    second = _start(c, "product.delete", "product", product.id)

    assert first.status_code == 202
    assert second.status_code == 202, second.text
    assert second.json()["id"] == first.json()["id"]
    assert (
        db.query(SlaFormAction)
        .filter(SlaFormAction.source_entity_id == str(product.id))
        .count()
        == 1
    )


def test_a_different_action_on_a_record_that_is_already_counting_down_is_refused(client):
    """One record holds ONE pending action: `current` answers per record and the
    screen shows one countdown, so a second key would have both of them draining
    the other one's window under the wrong verb."""
    c, db, _actor, _allowed = client
    status_row = _order_status(db, "new", "New")
    order = _order(db, status_row)
    delivered = _order_status(db, "delivered", "Delivered")

    assert _start(c, "order.delete", "order", order.id).status_code == 202
    clash = _start(
        c, "order.set_status", "order", order.id, {"order_status_id": delivered.id}
    )

    assert clash.status_code == 409, clash.text


def test_an_unknown_action_key_is_refused_before_anything_is_parked(client):
    c, db, _actor, _allowed = client
    product = _product(db)

    response = _start(c, "product.incinerate", "product", product.id)

    assert response.status_code == 400, response.text
    assert db.query(SlaFormAction).count() == 0


def test_an_entity_type_the_action_does_not_cover_is_refused(client):
    c, db, _actor, _allowed = client
    product = _product(db)

    response = _start(c, "user.delete", "product", product.id)

    assert response.status_code == 400, response.text


# --------------------------------------------------------------------------- #
# S6-01 RBAC - the slug is enforced when the action is PARKED, not when it runs
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "action_key,entity_type,slug",
    [
        ("product.delete", "product", PRODUCT_DELETE),
        ("order.delete", "order", ORDER_DELETE),
        ("order.set_status", "order", ORDER_EDIT),
        ("user.delete", "user", USER_DELETE),
    ],
)
def test_each_action_enforces_its_own_permission_slug(
    client, action_key, entity_type, slug
):
    c, db, _actor, allowed = client
    allowed.discard(slug)

    response = _start(c, action_key, entity_type, _uid(), {"order_status_id": _uid()})

    assert response.status_code == 403, response.text
    assert slug in response.json()["message"]
    assert db.query(SlaFormAction).count() == 0


def test_a_neighbouring_slug_does_not_unlock_an_action(client):
    """Deleting a delivery order and re-statusing one are different grants; holding
    the edit grant must not let the holder delete."""
    c, db, _actor, allowed = client
    allowed.discard(ORDER_DELETE)
    status_row = _order_status(db, "new", "New")
    order = _order(db, status_row)

    assert _start(c, "order.delete", "order", order.id).status_code == 403
    assert (
        _start(c, "order.set_status", "order", order.id, {"order_status_id": status_row.id}).status_code
        == 202
    )


# --------------------------------------------------------------------------- #
# S6-04 - the two windows, and where they are read from
# --------------------------------------------------------------------------- #


def test_the_windows_default_to_ten_and_five_seconds_by_the_verb(client):
    c, db, _actor, _allowed = client
    product = _product(db)
    status_row = _order_status(db, "new", "New")
    order = _order(db, status_row)

    destructive = _start(c, "product.delete", "product", product.id)
    reversible = _start(
        c, "order.set_status", "order", order.id, {"order_status_id": status_row.id}
    )

    assert destructive.json()["window_seconds"] == 10
    assert reversible.json()["window_seconds"] == 5


def test_the_windows_come_from_system_settings(client):
    """D16: the two windows are tuned in System Settings > General, without a deploy."""
    c, db, _actor, _allowed = client
    _settings(db, deferred_delete_seconds=30, deferred_action_seconds=3)
    product = _product(db)
    status_row = _order_status(db, "new", "New")
    order = _order(db, status_row)

    destructive = _start(c, "product.delete", "product", product.id)
    reversible = _start(
        c, "order.set_status", "order", order.id, {"order_status_id": status_row.id}
    )

    assert destructive.json()["window_seconds"] == 30
    assert reversible.json()["window_seconds"] == 3
    # commit_at is the server's clock plus that window, so a refresh cannot
    # restart it and a slow client cannot shorten it.
    parked = (
        db.query(SlaFormAction)
        .filter(SlaFormAction.id == destructive.json()["id"])
        .one()
    )
    assert 25 <= (parked.commit_at - parked.created_at).total_seconds() <= 35


# --------------------------------------------------------------------------- #
# S6-02 - cancel
# --------------------------------------------------------------------------- #


def test_cancel_before_the_window_lapses_leaves_the_record_alone(client):
    c, db, _actor, _allowed = client
    product = _product(db)
    parked = _start(c, "product.delete", "product", product.id).json()

    response = c.post(f"{BASE}/{parked['id']}/cancel")

    assert response.status_code == 200, response.text
    row = db.query(SlaFormAction).filter(SlaFormAction.id == parked["id"]).one()
    assert row.status == FORM_ACTION_CANCELLED
    assert db.query(Product).filter(Product.id == product.id).first() is not None
    assert _current(c, "product", product.id).json()["pending"] is None


def test_cancel_after_the_window_has_lapsed_is_refused(client):
    """The window is the whole promise: once it closes the answer is the server's,
    and a Cancel that arrives late must say so rather than silently no-op."""
    c, db, _actor, _allowed = client
    product = _product(db)
    parked = _start(c, "product.delete", "product", product.id).json()
    _lapse(db, parked["id"])

    response = c.post(f"{BASE}/{parked['id']}/cancel")

    assert response.status_code == 409, response.text
    assert db.query(Product).filter(Product.id == product.id).first() is None


def test_cancelling_the_same_action_twice_is_refused(client):
    c, db, _actor, _allowed = client
    product = _product(db)
    parked = _start(c, "product.delete", "product", product.id).json()

    assert c.post(f"{BASE}/{parked['id']}/cancel").status_code == 200
    assert c.post(f"{BASE}/{parked['id']}/cancel").status_code == 409


# --------------------------------------------------------------------------- #
# S6-05 - GET current, before and after
# --------------------------------------------------------------------------- #


def test_current_answers_null_for_a_record_with_nothing_parked(client):
    c, db, _actor, _allowed = client
    product = _product(db)

    body = _current(c, "product", product.id).json()

    assert body == {"pending": None, "last_outcome": None}


def test_current_carries_every_field_the_countdown_needs(client):
    """A second browser has to show the SAME countdown, so it needs the whole row -
    including who started it, because the reader there did not."""
    c, db, actor, _allowed = client
    product = _product(db)
    parked = _start(c, "product.delete", "product", product.id).json()

    pending = _current(c, "product", product.id).json()["pending"]

    assert pending["id"] == parked["id"]
    assert pending["action_key"] == "product.delete"
    assert pending["entity_type"] == "product"
    assert pending["entity_id"] == str(product.id)
    assert pending["commit_at"] == parked["commit_at"]
    assert pending["window_seconds"] == parked["window_seconds"]
    assert pending["requested_by_id"] == actor["id"]
    assert "requested_by_name" in pending


def test_current_commits_an_overdue_action_and_reports_the_outcome(client):
    """The lazy commit: a stopped scheduler may DELAY an action, never lose it."""
    c, db, _actor, _allowed = client
    product = _product(db)
    parked = _start(c, "product.delete", "product", product.id).json()
    _lapse(db, parked["id"])

    body = _current(c, "product", product.id).json()

    assert body["pending"] is None
    outcome = body["last_outcome"]
    assert outcome["id"] == parked["id"]
    assert outcome["action_key"] == "product.delete"
    assert outcome["status"] == "committed"
    assert outcome["ended_at"]
    assert db.query(Product).filter(Product.id == product.id).first() is None


def test_a_cancelled_action_is_reported_as_cancelled_not_committed(client):
    c, db, _actor, _allowed = client
    product = _product(db)
    parked = _start(c, "product.delete", "product", product.id).json()
    c.post(f"{BASE}/{parked['id']}/cancel")

    outcome = _current(c, "product", product.id).json()["last_outcome"]

    assert outcome["status"] == "cancelled"
    assert outcome["action_key"] == "product.delete"


def test_current_names_the_action_that_ended_so_two_keys_do_not_cross_show(client):
    """A delivery order carries both a status change and a delete. The hook shows
    the outcome only when `action_key` matches the one it was watching."""
    c, db, _actor, _allowed = client
    status_row = _order_status(db, "new", "New")
    delivered = _order_status(db, "delivered", "Delivered")
    order = _order(db, status_row)
    parked = _start(
        c, "order.set_status", "order", order.id, {"order_status_id": delivered.id}
    ).json()
    _lapse(db, parked["id"])

    outcome = _current(c, "order", order.id).json()["last_outcome"]

    assert outcome["action_key"] == "order.set_status"
    assert outcome["status"] == "committed"


# --------------------------------------------------------------------------- #
# S6-03 - the handlers, and what happens when one fails
# --------------------------------------------------------------------------- #


def test_the_commit_runs_the_real_delete_for_an_order(client):
    c, db, _actor, _allowed = client
    status_row = _order_status(db, "new", "New")
    order = _order(db, status_row)
    parked = _start(c, "order.delete", "order", order.id).json()
    _lapse(db, parked["id"])

    _current(c, "order", order.id)

    assert db.query(Order).filter(Order.id == order.id).first() is None


def test_the_commit_applies_the_payload_for_a_status_change(client):
    c, db, _actor, _allowed = client
    status_row = _order_status(db, "new", "New")
    delivered = _order_status(db, "delivered", "Delivered")
    order = _order(db, status_row)
    parked = _start(
        c, "order.set_status", "order", order.id, {"order_status_id": delivered.id}
    ).json()
    _lapse(db, parked["id"])

    _current(c, "order", order.id)

    db.expire_all()
    assert db.query(Order).filter(Order.id == order.id).one().order_status_id == delivered.id


def test_the_commit_trashes_a_user(client):
    """`user.delete` is the trash the Users list restores from, which is what the
    route it wraps has always done - the pending action changed WHEN it runs, not
    what it does."""
    c, db, _actor, _allowed = client
    target = _user(db)
    parked = _start(c, "user.delete", "user", target.id).json()
    _lapse(db, parked["id"])

    _current(c, "user", target.id)

    db.expire_all()
    assert db.query(User).filter(User.id == target.id).one().is_trashed is True


def test_a_handler_failure_is_captured_and_leaves_the_record_alone(client):
    """A countdown that simply vanishes reads as success. A failure has to be
    readable afterwards, and the record has to be untouched (S6-03)."""
    c, db, _actor, _allowed = client
    from app.services import form_action_registry as reg

    product = _product(db)
    parked = _start(c, "product.delete", "product", product.id).json()

    def _boom(_db, _payload):
        raise RuntimeError("the warehouse still holds stock for it")

    original = reg.REGISTRY["product.delete"]
    reg.REGISTRY["product.delete"] = reg.FormAction(
        key=original.key,
        entity_types=original.entity_types,
        execute=_boom,
        capture=original.capture,
        invert=None,
        resolve_event=original.resolve_event,
        window=original.window,
        permission=original.permission,
    )
    try:
        _lapse(db, parked["id"])
        body = _current(c, "product", product.id).json()
    finally:
        reg.REGISTRY["product.delete"] = original

    assert body["pending"] is None
    outcome = body["last_outcome"]
    assert outcome["status"] == "failed"
    # The reader is told the delete did not happen, in a sentence. NOT the exception:
    # `error_text` goes straight into a toast, and an exception that escaped a handler
    # is a defect whose message may be a SQL statement and its parameters.
    said = outcome["error_text"] or ""
    assert said == "This product could not be deleted. Nothing was changed."
    assert "warehouse" not in said
    assert db.query(Product).filter(Product.id == product.id).first() is not None
    assert (
        db.query(SlaFormAction).filter(SlaFormAction.id == parked["id"]).one().status
        == FORM_ACTION_FAILED
    )


def test_a_failed_action_does_not_block_the_next_one(client):
    """The one-pending-per-record rule counts PENDING rows only, or a failure would
    lock the record out of ever being acted on again."""
    c, db, _actor, _allowed = client
    from app.services import form_action_registry as reg

    product = _product(db)
    parked = _start(c, "product.delete", "product", product.id).json()
    original = reg.REGISTRY["product.delete"]
    reg.REGISTRY["product.delete"] = reg.FormAction(
        key=original.key,
        entity_types=original.entity_types,
        execute=lambda _db, _p: (_ for _ in ()).throw(RuntimeError("nope")),
        capture=original.capture,
        invert=None,
        resolve_event=original.resolve_event,
        window=original.window,
        permission=original.permission,
    )
    try:
        _lapse(db, parked["id"])
        _current(c, "product", product.id)
    finally:
        reg.REGISTRY["product.delete"] = original

    retry = _start(c, "product.delete", "product", product.id)

    assert retry.status_code == 202, retry.text
    assert retry.json()["id"] != parked["id"]


# --------------------------------------------------------------------------- #
# S6-08 - the browser is not in the loop
# --------------------------------------------------------------------------- #


def test_the_sweeper_commits_an_action_nobody_is_looking_at(client):
    """Closing the tab still commits: the sweep is what covers a record whose page
    is gone, and the lazy commit only ever covers whoever is watching."""
    c, db, _actor, _allowed = client
    from app.services.form_action_service import FormActionService

    product = _product(db)
    parked = _start(c, "product.delete", "product", product.id).json()
    _lapse(db, parked["id"])

    outcome = FormActionService(db).commit_due()

    assert outcome["committed"] >= 1
    assert db.query(Product).filter(Product.id == product.id).first() is None
    assert (
        db.query(SlaFormAction).filter(SlaFormAction.id == parked["id"]).one().status
        == FORM_ACTION_COMMITTED
    )


def test_a_parked_action_stays_pending_until_its_window_closes(client):
    c, db, _actor, _allowed = client
    from app.services.form_action_service import FormActionService

    product = _product(db)
    _start(c, "product.delete", "product", product.id)

    FormActionService(db).commit_due()

    assert db.query(Product).filter(Product.id == product.id).first() is not None
    row = (
        db.query(SlaFormAction)
        .filter(SlaFormAction.source_entity_id == str(product.id))
        .one()
    )
    assert row.status == FORM_ACTION_PENDING


# --------------------------------------------------------------------------- #
# S6-04 (D16) - the two windows are settings, and they reach the frontend
# --------------------------------------------------------------------------- #

SETTINGS = "/api/v1/user-management/settings/"
SETTINGS_GENERAL = "/api/v1/user-management/settings/general"


def test_settings_get_carries_both_windows_with_their_defaults(client):
    """A response_model drops what it does not declare and the GET builds a manual
    dict - a column missing from either never reaches the settings form."""
    c, db, _actor, allowed = client
    allowed.add("user_management.settings.view")
    _settings(db)

    body = c.get(SETTINGS).json()["settings"]

    assert body["deferred_delete_seconds"] == 10
    assert body["deferred_action_seconds"] == 5


def test_saving_the_windows_changes_the_next_pending_action(client):
    c, db, _actor, allowed = client
    allowed.add("user_management.settings.view")
    _settings(db)
    product = _product(db)

    saved = c.post(
        SETTINGS_GENERAL,
        json={"deferred_delete_seconds": 20, "deferred_action_seconds": 8},
    )
    assert saved.status_code == 200, saved.text

    assert c.get(SETTINGS).json()["settings"]["deferred_delete_seconds"] == 20
    assert _start(c, "product.delete", "product", product.id).json()["window_seconds"] == 20


def test_a_window_of_zero_is_refused(client):
    """Zero would apply the action with no way back, which is the confirmation
    dialog's failure mode wearing the new model's clothes."""
    c, db, _actor, allowed = client
    allowed.add("user_management.settings.view")
    _settings(db)

    response = c.post(SETTINGS_GENERAL, json={"deferred_delete_seconds": 0})

    assert response.status_code == 422, response.text
