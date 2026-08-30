"""The S6b sweep's record actions - the handlers that replaced a confirmation dialog.

`tests/test_pending_actions.py` owns the ENGINE: parking, cancelling, the two windows,
the lazy commit, `last_outcome`. Nothing here re-tests any of that. What this file owns
is the thirty-odd handlers S6b added, and it asks two different questions of them:

1. **Per registration, of all of them.** Every record action names a permission slug the
   route can enforce, declares a window class the verb agrees with, and has an `execute`
   whose lazy import actually resolves. Those three are the whole contract between a
   handler and `/pending-actions`, and each of them fails SILENTLY in a way the reader
   only meets ten seconds after clicking: an unknown slug refuses every click, a
   mis-declared window gives a hard delete five seconds, and a bad import raises inside
   the commit where the countdown has already gone.

2. **End to end, of a representative one per shape.** A uuid-keyed row (a brand), a
   CODE-keyed row (a market segment), a link row (a product's supplier), and a singleton
   setting (the sign-in background). Those are the four ways an `entity_id` is formed,
   and each of them proves the same three things: parking applies nothing, the window
   lapsing applies exactly what the immediate route applies, and Cancel leaves the record
   where it was.

Postgres only, on the blank scratch schema, seeding its own chain - CI's database is
empty, so nothing may be borrowed from an existing table.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.access import MarketSegment, Team
from app.models.notification import Notification
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.models.procurement import ProductSupplier, Supplier
from app.models.sla import FORM_ACTION_CANCELLED, FORM_ACTION_COMMITTED, SlaFormAction
from app.models.user import SystemSetting, User
from app.rbac.permission_registry import PERMISSION_REGISTRY
from app.services.form_action_grace import (
    WINDOW_DESTRUCTIVE,
    WINDOW_REVERSIBLE,
    window_class_for,
)
from app.services.form_action_registry import REGISTRY
from tests._pg_fixture import blank_session

# `from ... import`, never `import app.services.record_actions`: the latter rebinds the
# name `app` to the PACKAGE and shadows the FastAPI instance imported above, so every
# `app.dependency_overrides` in the fixture raises AttributeError.
from app.services import record_actions  # noqa: F401  (registers the record actions)

BASE = "/api/v1/pending-actions"
MARKER = "ZZT-S6B"

#: Every RECORD action, i.e. everything the generic route can park. A form-SLA action
#: leaves `permission` unset and is dispatched from inside its own domain route.
RECORD_ACTIONS = {key: action for key, action in REGISTRY.items() if action.permission}
KNOWN_SLUGS = {row["slug"] for row in PERMISSION_REGISTRY}


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

        actor_row = User(
            id=_uid(), email=f"zzt-s6b-{_uid()[:8]}@example.test", name="Ada Actor"
        )
        db.add(actor_row)
        db.commit()
        actor = {"id": actor_row.id, "email": actor_row.email, "name": actor_row.name}
        #: Mutable, so one test can withdraw a single slug and keep the rest.
        denied: set[str] = set()

        def _override_scope(_db=Depends(get_db)):
            # The resolver reads an Authorization header this client does not send and
            # would fail closed, hiding the test's own seeded rows for the rest of the
            # test. Company scope is not what S6b is about.
            set_company_scope(_db, None)
            return None

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: actor
        monkeypatch.setattr(
            UserPermissionService,
            "check_user_has_permission",
            lambda self, uid, slug: slug not in denied,
        )
        try:
            with TestClient(app) as c:
                yield c, db, actor, denied
        finally:
            app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Seeds
# --------------------------------------------------------------------------- #


def _brand(db) -> Brand:
    row = Brand(
        id=_uid(), brand_code=f"{MARKER}-{_uid()[:8]}", brand_name=f"{MARKER} brand"
    )
    db.add(row)
    db.commit()
    return row


def _segment(db) -> MarketSegment:
    row = MarketSegment(
        id=_uid(), code=f"{MARKER}-{_uid()[:8]}", name=f"{MARKER} segment"
    )
    db.add(row)
    db.commit()
    return row


def _team(db) -> Team:
    row = Team(id=_uid(), name=f"{MARKER} team")
    db.add(row)
    db.commit()
    return row


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


def _product_supplier(db) -> ProductSupplier:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"{MARKER}-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    supplier = Supplier(
        id=_uid(),
        supplier_code=f"{MARKER}-{_uid()[:8]}",
        supplier_name=f"{MARKER} supplier",
    )
    db.add_all([uom, category, supplier])
    db.flush()
    product = Product(
        id=_uid(),
        product_code=f"{MARKER}-{_uid()[:8]}",
        product_name=f"{MARKER} chair",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(product)
    db.flush()
    link = ProductSupplier(
        id=_uid(),
        product_id=product.id,
        supplier_id=supplier.id,
        standard_lead_time_days=45,
    )
    db.add(link)
    db.commit()
    return link


def _settings_with_background(db) -> SystemSetting:
    row = SystemSetting(
        id=_uid(),
        name=f"{MARKER} co",
        signin_background="branding/signin-background/abc.jpg",
        signin_background_storage_provider="s3",
    )
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


def _lapse(db, action_id: str) -> None:
    """Move the window into the past without waiting out ten real seconds."""
    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)},
        synchronize_session=False,
    )
    db.commit()


def _commit_now(c, db, entity_type: str, entity_id: str, action_id: str):
    """Lapse the window and let the lazy commit on GET apply it, as a poll would."""
    _lapse(db, action_id)
    return c.get(
        f"{BASE}/current",
        params={"entity_type": entity_type, "entity_id": str(entity_id)},
    )


# --------------------------------------------------------------------------- #
# The registration contract, over EVERY record action (S6-01, S6-04)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("key", sorted(RECORD_ACTIONS))
def test_every_record_action_names_a_permission_the_registry_knows(key):
    """A slug the registry has never heard of is a slug no role can be granted, so the
    action refuses every click - and it refuses it at the click, where the reader will
    read the refusal as the feature being broken rather than as a missing grant."""
    slug = RECORD_ACTIONS[key].permission
    if slug == record_actions.OWN_RECORD:
        # The one grant that is not a slug: the handler is scoped to the requester, so
        # the row it can reach is the reader's own (see `record_actions.OWN_RECORD`).
        return
    assert slug in KNOWN_SLUGS, f"{key} requires {slug!r}, which is in no role's reach"


#: `.delete` keys that deliberately take the SHORT window, each with its reason. An
#: allowlist rather than a softer rule, so the next delete registered still has to take
#: the long window or come here and say why.
SHORT_WINDOW_DELETES = {
    # A notification is a copy of something that happened elsewhere, and deleting one
    # destroys no record. Its own panel offers Clear beside it with no window at all,
    # so ten seconds here would be the heaviest gesture guarding the lightest action.
    "notification.delete",
}


@pytest.mark.parametrize("key", sorted(RECORD_ACTIONS))
def test_every_record_action_declares_a_window_its_verb_agrees_with(key):
    """A `.delete` on the five-second window is the one mistake this model cannot
    afford: the reader gets half the time to catch a mistake that cannot be undone."""
    action = RECORD_ACTIONS[key]
    assert action.window in {WINDOW_DESTRUCTIVE, WINDOW_REVERSIBLE}, key
    if key.endswith(".delete") and key not in SHORT_WINDOW_DELETES:
        assert window_class_for(action) == WINDOW_DESTRUCTIVE, key


@pytest.mark.parametrize("key", sorted(RECORD_ACTIONS))
def test_every_record_action_declares_its_entity_type_and_a_callable(key):
    action = RECORD_ACTIONS[key]
    assert action.entity_types, key
    assert callable(action.execute), key
    # The key's prefix IS the entity type on every one of them, which is what lets a
    # frontend name both from one string without a second lookup.
    assert key.split(".", 1)[0] in action.entity_types, key


@pytest.mark.parametrize("key", sorted(RECORD_ACTIONS))
def test_every_handler_resolves_its_service_import(key):
    """The imports inside a handler are LAZY, so a renamed service module is invisible
    until the window lapses - by which time the countdown is gone and the failure lands
    in `last_outcome` instead of on the button.

    Run each handler against a session that raises on ANY attribute. What is asserted is
    only that it got that far: an ImportError or an AttributeError on the service would
    be raised first and is what this catches.
    """

    class _Refuses:
        def __getattr__(self, _name):
            raise RuntimeError("session refused")

    action = RECORD_ACTIONS[key]
    #: A composite address for the one handler that takes one - it refuses half of a
    #: `<product id>:<spec key>` before reaching any service, which is its whole job.
    entity_ids = {"product_spec_value.clear": f"{_uid()}:width"}
    payload = {
        "entity_id": entity_ids.get(key, _uid()),
        # The route always puts the actor here, and a handler scoped to the requester
        # (a notification) refuses outright without one, before it reaches a service.
        "requested_by_id": _uid(),
        # Whatever the handlers that need a second key read; unused by the rest.
        "promotion_id": _uid(),
        "integration_id": _uid(),
        "product_id": _uid(),
        "order_status_id": _uid(),
        "scope_kind": "contact",
        "mode": "revert",
    }
    with pytest.raises(RuntimeError, match="session refused"):
        action.execute(_Refuses(), payload)


# --------------------------------------------------------------------------- #
# RBAC, over EVERY record action - the slug is enforced at the CLICK (S6-01)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("key", sorted(RECORD_ACTIONS))
def test_each_action_is_refused_without_its_own_slug(client, key):
    c, db, _actor, denied = client
    action = RECORD_ACTIONS[key]
    if action.permission == record_actions.OWN_RECORD:
        # Nothing to withdraw: the grant is ownership, enforced by the handler's own
        # query rather than by a slug (see `record_actions.OWN_RECORD`).
        return
    denied.add(action.permission)

    response = _start(c, key, action.entity_types[0], _uid())

    assert response.status_code == 403, response.text
    assert action.permission in response.json()["message"]
    # Refused BEFORE anything is parked: a row that exists but may never commit is a
    # countdown with no outcome.
    assert db.query(SlaFormAction).count() == 0


# --------------------------------------------------------------------------- #
# End to end, one per shape of `entity_id`
# --------------------------------------------------------------------------- #


def test_a_uuid_keyed_row_is_untouched_until_the_window_lapses(client):
    """Brand: the ordinary case, and the one every list-row delete follows."""
    c, db, _actor, _denied = client
    brand = _brand(db)

    parked = _start(c, "brand.delete", "brand", brand.id)

    assert parked.status_code == 202, parked.text
    assert parked.json()["window_seconds"] == 10
    assert db.query(Brand).filter(Brand.id == brand.id).first() is not None

    body = _commit_now(c, db, "brand", brand.id, parked.json()["id"]).json()

    assert body["pending"] is None
    assert body["last_outcome"]["status"] == "committed"
    assert db.query(Brand).filter(Brand.id == brand.id).first() is None


def test_a_code_keyed_row_commits_against_its_code(client):
    """Market segment: its primary key is a CODE, which is what the DELETE route takes
    and therefore what the frontend parks. A handler that assumed a uuid would 404 ten
    seconds after a click that looked fine."""
    c, db, _actor, _denied = client
    segment = _segment(db)

    parked = _start(c, "market_segment.delete", "market_segment", segment.code)

    assert parked.status_code == 202, parked.text
    assert db.query(MarketSegment).filter(MarketSegment.code == segment.code).first()

    body = _commit_now(c, db, "market_segment", segment.code, parked.json()["id"]).json()

    assert body["last_outcome"]["status"] == "committed", body["last_outcome"]
    db.expire_all()
    assert (
        db.query(MarketSegment).filter(MarketSegment.code == segment.code).first()
        is None
    )


def test_market_segment_delete_refuses_view_only_and_accepts_manage(client, monkeypatch):
    """Issue #402: a view grant authorising a hard delete was wrong in principle,
    even though the immediate route it replaced had no slug at all. `.view` alone
    must now refuse the click, and only `.manage` may start it."""
    from app.services.user_service import UserPermissionService

    c, db, _actor, _denied = client
    segment = _segment(db)

    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug == "user_management.reference_data.view",
    )
    refused = _start(c, "market_segment.delete", "market_segment", segment.code)
    assert refused.status_code == 403, refused.text
    assert db.query(SlaFormAction).count() == 0

    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug == "user_management.reference_data.manage",
    )
    parked = _start(c, "market_segment.delete", "market_segment", segment.code)
    assert parked.status_code == 202, parked.text


def test_two_products_clear_the_same_spec_key_without_colliding(client):
    """A specification value is one product's answer for one key, so it is parked as
    `<product id>:<spec key>`.

    Addressed by the bare key it was a GLOBALLY shared id: the engine holds one pending
    action per record, so the second person to clear `width` - on a different product -
    was refused with a 409 about a record they had never touched, and each of them then
    read the other's outcome as their own."""
    c, db, _actor, _denied = client
    first, second = _product(db), _product(db)

    parked_first = _start(
        c,
        "product_spec_value.clear",
        "product_spec_value",
        f"{first.id}:width",
        {"mode": "revert"},
    )
    parked_second = _start(
        c,
        "product_spec_value.clear",
        "product_spec_value",
        f"{second.id}:width",
        {"mode": "revert"},
    )

    assert parked_first.status_code == 202, parked_first.text
    assert parked_second.status_code == 202, parked_second.text
    assert parked_first.json()["id"] != parked_second.json()["id"]

    parked_ids = {
        row.source_entity_id
        for row in db.query(SlaFormAction)
        .filter(SlaFormAction.action_key == "product_spec_value.clear")
        .all()
    }
    assert parked_ids == {f"{first.id}:width", f"{second.id}:width"}


def test_a_delete_blocked_by_a_foreign_key_says_so_without_showing_the_sql(client):
    """`error_text` is rendered straight into the reader's toast.

    A psycopg2 IntegrityError stringifies to the failing statement, the constraint name
    and the bound parameters, so before this the answer to "why did that not delete" was
    a DELETE FROM with the row's own values in it. The reason has to be a sentence, and
    the exception belongs in the log."""
    c, db, _actor, _denied = client
    product = _product(db)
    # RESTRICT on the member's product: a set must never hold a dangling member, so the
    # database refuses the delete and the service does not pre-check it.
    product_set = ProductSet(id=_uid(), set_code=f"{MARKER}-{_uid()[:8]}", name=f"{MARKER} set")
    db.add(product_set)
    db.flush()
    db.add(
        ProductSetMember(
            id=_uid(), product_set_id=product_set.id, product_id=product.id, quantity=1
        )
    )
    db.commit()

    parked = _start(c, "product.delete", "product", product.id)
    assert parked.status_code == 202, parked.text

    body = _commit_now(c, db, "product", product.id, parked.json()["id"]).json()

    assert body["last_outcome"]["status"] == "failed", body["last_outcome"]
    said = body["last_outcome"]["error_text"]
    assert said == "Cannot delete this product: other records still reference it."
    lowered = said.lower()
    for leak in ("delete from", "insert into", "select ", "psycopg2", "violates", "constraint", "sqlalchemy"):
        assert leak not in lowered, f"error_text leaks {leak!r}: {said}"
    # And the record is still standing - a failed commit changes nothing.
    db.expire_all()
    assert db.query(Product).filter(Product.id == product.id).first() is not None


def test_a_spec_value_parked_without_its_product_does_not_apply(client):
    """The composite is the address, so half of it is not one. A bare spec key would
    otherwise reach `apply_spec_values` as a product code and clear whatever it hit."""
    c, db, _actor, _denied = client

    parked = _start(
        c, "product_spec_value.clear", "product_spec_value", "width", {"mode": "revert"}
    )
    assert parked.status_code == 202, parked.text

    body = _commit_now(
        c, db, "product_spec_value", "width", parked.json()["id"]
    ).json()

    assert body["pending"] is None
    assert body["last_outcome"]["status"] == "failed", body["last_outcome"]


def test_a_link_row_is_detached_and_leaves_both_ends_standing(client):
    """The product-supplier detach (S6b item 1). It takes the REVERSIBLE window because
    the link can be made again, and it must not take the product or the supplier with
    it - a detach that deleted either would be a data loss nobody asked for."""
    c, db, _actor, _denied = client
    link = _product_supplier(db)
    product_id, supplier_id = link.product_id, link.supplier_id

    parked = _start(c, "product_supplier.unlink", "product_supplier", link.id)

    assert parked.status_code == 202, parked.text
    assert parked.json()["window_seconds"] == 5
    assert db.query(ProductSupplier).filter(ProductSupplier.id == link.id).first()

    _commit_now(c, db, "product_supplier", link.id, parked.json()["id"])

    assert db.query(ProductSupplier).filter(ProductSupplier.id == link.id).first() is None
    assert db.query(Product).filter(Product.id == product_id).first() is not None
    assert db.query(Supplier).filter(Supplier.id == supplier_id).first() is not None


def test_a_singleton_setting_is_parked_against_its_constant(client):
    """The sign-in background is one of a kind, so the frontend parks it against the
    constant `signin-background` rather than an id nobody ever sees. Both columns go,
    because a `signin_background_storage_provider` with no image is a setting for a
    picture that is not there."""
    c, db, _actor, _denied = client
    settings = _settings_with_background(db)

    parked = _start(
        c, "signin_background.remove", "signin_background", "signin-background"
    )

    assert parked.status_code == 202, parked.text
    assert parked.json()["window_seconds"] == 5
    db.refresh(settings)
    assert settings.signin_background is not None

    _commit_now(c, db, "signin_background", "signin-background", parked.json()["id"])

    db.refresh(settings)
    assert settings.signin_background is None
    assert settings.signin_background_storage_provider is None


def test_a_notification_is_deleted_only_for_the_reader_who_owns_it(client):
    """The one action whose grant is OWNERSHIP, not a slug (`record_actions.OWN_RECORD`).

    The bell is in the topbar for every signed-in user and its route checks no
    permission, so what stops one reader clearing another's inbox is that the handler is
    scoped to the requester. Parking is allowed either way - the id is not proof of
    anything at the click - and the commit is where the wrong owner comes to nothing."""
    c, db, actor, _denied = client
    mine = Notification(
        id=_uid(), user_id=actor["id"], type="import_job_finished", title=f"{MARKER} mine"
    )
    theirs = Notification(
        id=_uid(), user_id=_uid(), type="import_job_finished", title=f"{MARKER} theirs"
    )
    db.add_all([mine, theirs])
    db.commit()

    parked_mine = _start(c, "notification.delete", "notification", mine.id)
    assert parked_mine.status_code == 202, parked_mine.text
    assert parked_mine.json()["window_seconds"] == 5
    _commit_now(c, db, "notification", mine.id, parked_mine.json()["id"])

    parked_theirs = _start(c, "notification.delete", "notification", theirs.id)
    assert parked_theirs.status_code == 202, parked_theirs.text
    body = _commit_now(
        c, db, "notification", theirs.id, parked_theirs.json()["id"]
    ).json()

    db.expire_all()
    assert db.query(Notification).filter(Notification.id == mine.id).first() is None
    assert db.query(Notification).filter(Notification.id == theirs.id).first() is not None
    assert body["last_outcome"]["status"] == "failed", body["last_outcome"]


def test_cancel_inside_the_window_leaves_the_record_exactly_where_it_was(client):
    """Cancel is the whole way back now that no dialog asks first, so it is asserted on
    a handler S6b added rather than assumed from the engine's own tests."""
    c, db, _actor, _denied = client
    team = _team(db)
    parked = _start(c, "team.delete", "team", team.id).json()

    response = c.post(f"{BASE}/{parked['id']}/cancel")

    assert response.status_code == 200, response.text
    row = db.query(SlaFormAction).filter(SlaFormAction.id == parked["id"]).one()
    assert row.status == FORM_ACTION_CANCELLED
    assert db.query(Team).filter(Team.id == team.id).first() is not None


def test_a_second_action_on_the_same_record_is_refused_while_one_is_parked(client):
    """One record holds ONE pending action: `current` answers per record, so a second
    key would leave both countdowns draining the other one's window."""
    c, db, _actor, _denied = client
    brand = _brand(db)

    assert _start(c, "brand.delete", "brand", brand.id).status_code == 202
    assert _start(c, "brand.delete", "brand", brand.id).status_code == 202
    assert (
        db.query(SlaFormAction)
        .filter(SlaFormAction.source_entity_id == str(brand.id))
        .count()
        == 1
    )


def test_a_failing_handler_marks_the_row_failed_and_leaves_the_record_alone(client):
    """S6-03, on an S6b handler: a brand that no longer exists when the window lapses
    must read as a failure with a reason, because a countdown that simply disappears
    reads exactly like success."""
    c, db, _actor, _denied = client
    brand = _brand(db)
    parked = _start(c, "brand.delete", "brand", brand.id).json()

    db.delete(db.query(Brand).filter(Brand.id == brand.id).one())
    db.commit()

    body = _commit_now(c, db, "brand", brand.id, parked["id"]).json()

    assert body["pending"] is None
    assert body["last_outcome"]["status"] == "failed"
    assert body["last_outcome"]["action_key"] == "brand.delete"
    row = db.query(SlaFormAction).filter(SlaFormAction.id == parked["id"]).one()
    assert row.status != FORM_ACTION_COMMITTED
