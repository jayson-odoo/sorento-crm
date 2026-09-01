"""Saved views (segments) routes + service (AC-4.3, G9).

Mirrors `tests/test_report_routes.py`'s "AC-C3 views" / "AC-C4 publish/default" sections -
`saved_views` generalises `report_views` for S4, PLAN-scm-reorder-oi-feedback-1sep.md - with
one structural difference: `saved_views` is keyed by an arbitrary `listing_key`
(`_can_view_listing_key`, the SAME gate `column-config` already uses) rather than a report
registry key, and DELETE runs through the deferred-action registry
(`saved_view.delete`, `app/services/record_actions.py`) instead of a direct route - covered
in `tests/test_record_actions_s6b.py`'s parametrised sweep plus the dedicated end-to-end
test at the bottom of this file, and at the SERVICE level here (`SavedViewsService.delete`
is the one line the record action calls).

Postgres only, on the blank scratch schema, seeding its own chain - CI's database is empty.

Run: pytest tests/test_saved_views_routes.py -q
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models.user import User, UserPermission
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session

BASE = "/api/v1/list-query/saved-views"
LISTING_KEY = "zzt.saved_views.view::demo-list"
VIEW_PERMISSION = "zzt.saved_views.view"
PUBLISH_PERMISSION = "list_query.saved_views.publish"

_ME = {"id": str(uuid.uuid4()), "email": "views-caller@zzt.test", "name": "Views Caller"}
_OTHER_ID = str(uuid.uuid4())


def _seed_user(db, user_id: str, email: str, name: str) -> None:
    db.add(User(id=user_id, email=email, name=name, status="ACTIVE"))
    db.flush()


@pytest.fixture
def db():
    with blank_session() as session:
        session.add(UserPermission(id=str(uuid.uuid4()), slug=VIEW_PERMISSION, name="t", description=""))
        _seed_user(session, _ME["id"], _ME["email"], _ME["name"])
        _seed_user(session, _OTHER_ID, "other@zzt.test", "Other Person")
        session.commit()
        yield session


@pytest.fixture
def api(db, monkeypatch):
    allow = {VIEW_PERMISSION}

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _ME
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client, allow
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def _config(**overrides) -> dict:
    view = {
        "filters": {"op": "and", "children": [{"field_key": "supplier", "op": "eq", "value": "Acme"}]},
        "sort": [{"id": "suggested_qty", "desc": True}],
        "columns": ["sku", "supplier", "suggested_qty"],
        "column_order": ["sku", "supplier", "suggested_qty"],
    }
    view.update(overrides)
    return view


def _create_view(client, name="Mine", view=None):
    return client.post(f"{BASE}/{LISTING_KEY}", json={"name": name, "view": view or _config()})


def _seed_other_view(db, *, name: str, is_shared: bool, owner=_OTHER_ID, listing_key=LISTING_KEY, view=None):
    from app.models.saved_view import SavedView as SavedViewRow

    row = SavedViewRow(
        listing_key=listing_key,
        owner_user_id=owner,
        name=name,
        view=view or _config(),
        is_shared=is_shared,
    )
    db.add(row)
    db.flush()
    return str(row.id)


# ---------------------------------------------------------------- _can_view_listing_key


def test_listing_key_denial_is_403_for_a_permission_the_caller_lacks(api):
    """The same gate `column-config` already uses (`_can_view_listing_key`): the
    permission slug prefixing the listing key exists in the RBAC catalog, but the caller
    was not granted it."""
    client, allow = api
    allow.clear()
    assert client.get(f"{BASE}/{LISTING_KEY}").status_code == 403
    assert _create_view(client, "Nope").status_code == 403


def test_listing_key_with_an_unknown_permission_slug_is_module_auth_only(api):
    """A slug that does not exist in the RBAC catalog at all reads as a listing gated
    by a module guard rather than fine-grained RBAC, and is allowed through - the same
    behaviour `test_list_column_config_allows_when_permission_slug_unknown` pins for
    column-config."""
    client, _allow = api
    key = "zzt.nonexistent.permission.slug::x"
    resp = client.get(f"{BASE}/{key}")
    assert resp.status_code == 200
    assert resp.json() == {"mine": [], "shared": []}


# --------------------------------------------------------------------- list scoping


def test_a_saved_view_comes_back_under_mine(api):
    client, _allow = api
    created = _create_view(client, "My segment")
    assert created.status_code == 200, created.text
    view = created.json()
    assert view["is_shared"] is False
    assert view["is_default"] is False
    assert view["owner_name"] == "Views Caller"
    assert view["view"]["columns"] == ["sku", "supplier", "suggested_qty"]
    assert view["view"]["column_order"] == ["sku", "supplier", "suggested_qty"]
    assert view["view"]["sort"] == [{"id": "suggested_qty", "desc": True}]
    assert view["view"]["filters"]["children"][0]["field_key"] == "supplier"

    listed = client.get(f"{BASE}/{LISTING_KEY}").json()
    assert [v["name"] for v in listed["mine"]] == ["My segment"]
    assert listed["shared"] == []


def test_a_second_view_with_the_same_name_is_refused(api):
    client, _allow = api
    _create_view(client, "Same name")
    again = _create_view(client, "Same name")
    assert again.status_code == 409
    assert "Same name" in again.json()["message"]


def test_a_blank_name_is_refused_at_the_button(api):
    client, _allow = api
    resp = _create_view(client, "   ")
    assert resp.status_code == 422, resp.text


def test_another_users_personal_view_is_invisible(api, db):
    client, _allow = api
    _seed_other_view(db, name="Private to them", is_shared=False)
    listed = client.get(f"{BASE}/{LISTING_KEY}").json()
    assert listed["mine"] == []
    assert listed["shared"] == []


def test_another_users_published_view_is_shared_not_mine(api, db):
    client, _allow = api
    _seed_other_view(db, name="Management default", is_shared=True)
    listed = client.get(f"{BASE}/{LISTING_KEY}").json()
    assert listed["mine"] == []
    assert [v["name"] for v in listed["shared"]] == ["Management default"]
    assert listed["shared"][0]["owner_name"] == "Other Person"


def test_my_own_published_view_stays_under_mine(api):
    """Publishing must not take a view out of its author's own list."""
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    view_id = _create_view(client, "Shared by me").json()["id"]

    published = client.post(f"{BASE}/{view_id}/publish", json={"is_shared": True})
    assert published.status_code == 200, published.text
    assert published.json()["is_shared"] is True

    listed = client.get(f"{BASE}/{LISTING_KEY}").json()
    assert [v["name"] for v in listed["mine"]] == ["Shared by me"]
    assert listed["mine"][0]["is_shared"] is True
    assert listed["shared"] == []


def test_a_view_under_a_different_listing_key_never_appears(api, db):
    client, _allow = api
    _create_view(client, "Mine here")
    _seed_other_view(db, name="Elsewhere", is_shared=True, owner=_ME["id"], listing_key="zzt.other.listing")
    listed = client.get(f"{BASE}/{LISTING_KEY}").json()
    assert [v["name"] for v in listed["mine"]] == ["Mine here"]


# -------------------------------------------------------------- publish permission


def test_publish_is_403_without_the_publish_permission(api):
    client, _allow = api
    view_id = _create_view(client, "Not shareable").json()["id"]
    resp = client.post(f"{BASE}/{view_id}/publish", json={"is_shared": True})
    assert resp.status_code == 403
    assert PUBLISH_PERMISSION in resp.json()["message"]


def test_set_default_is_403_without_the_publish_permission(api):
    client, _allow = api
    view_id = _create_view(client, "Not defaultable").json()["id"]
    assert client.post(f"{BASE}/{view_id}/set-default").status_code == 403


def test_publish_and_set_default_still_gate_on_can_view_listing_key_first(api):
    """The listing-key gate runs BEFORE the publish permission, so a caller who cannot
    even see the listing gets the listing-key's own denial rather than a hint that a
    view exists."""
    client, allow = api
    view_id = _create_view(client, "Gated").json()["id"]
    allow.clear()  # loses VIEW_PERMISSION too, so _can_view_listing_key now fails
    resp = client.post(f"{BASE}/{view_id}/publish", json={"is_shared": True})
    assert resp.status_code == 404, resp.text


# ------------------------------------------------------------------- one default


def test_at_most_one_view_is_the_default_for_a_listing_key(api):
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    first = _create_view(client, "First").json()["id"]
    second = _create_view(client, "Second").json()["id"]

    client.post(f"{BASE}/{first}/set-default")
    resp = client.post(f"{BASE}/{second}/set-default")
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_default"] is True
    assert resp.json()["is_shared"] is True  # the default is shared by definition

    listed = client.get(f"{BASE}/{LISTING_KEY}").json()
    defaults = [v["name"] for v in listed["mine"] + listed["shared"] if v["is_default"]]
    assert defaults == ["Second"]


def test_another_users_private_view_cannot_be_made_the_default(api, db):
    """Used to publish whatever id it was handed, so a holder of the publish grant could
    expose somebody else's PRIVATE view to everyone by id alone."""
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    other = _seed_other_view(db, name="Private to them", is_shared=False)

    resp = client.post(f"{BASE}/{other}/set-default")
    assert resp.status_code == 409, resp.text
    assert "shared" in resp.json()["message"].lower()

    listed = client.get(f"{BASE}/{LISTING_KEY}").json()
    assert listed["mine"] == []
    assert listed["shared"] == []


def test_another_users_shared_view_can_be_made_the_default(api, db):
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    other = _seed_other_view(db, name="Theirs, published", is_shared=True)

    resp = client.post(f"{BASE}/{other}/set-default")
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_default"] is True


def test_the_owner_may_publish_and_default_a_view_in_one_step(api):
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    view_id = _create_view(client, "Mine to share").json()["id"]

    resp = client.post(f"{BASE}/{view_id}/set-default")
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_shared"] is True
    assert resp.json()["is_default"] is True


def test_unpublishing_the_default_clears_the_default(api):
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    view_id = _create_view(client, "House view").json()["id"]
    client.post(f"{BASE}/{view_id}/set-default")

    resp = client.post(f"{BASE}/{view_id}/publish", json={"is_shared": False})
    assert resp.json()["is_default"] is False


def test_two_set_defaults_at_once_answer_409_rather_than_500(api, db, monkeypatch):
    """The partial unique index is the arbiter, and the loser of a race used to get a
    500 - the one-default RACE GUARD `SavedViewsService.set_default` clear-then-set
    documents."""
    from sqlalchemy.exc import IntegrityError

    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    view_id = _create_view(client, "House view").json()["id"]

    def _collide(*args, **kwargs):
        raise IntegrityError("set default", None, Exception("uq_saved_views_one_default"))

    monkeypatch.setattr(db, "commit", _collide)
    resp = client.post(f"{BASE}/{view_id}/set-default")
    assert resp.status_code == 409, resp.text


def test_set_default_on_an_unknown_view_id_is_404(api):
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    assert client.post(f"{BASE}/{uuid.uuid4()}/set-default").status_code == 404


def test_publishing_someone_elses_private_view_is_404_not_403(api, db):
    """A view id in another person's hand is not a licence to learn that it exists."""
    client, allow = api
    allow.add(PUBLISH_PERMISSION)
    other = _seed_other_view(db, name="Private and stale", is_shared=False)
    assert client.post(f"{BASE}/{other}/publish", json={"is_shared": True}).status_code == 404


# ------------------------------------------------------------------ delete (SERVICE)
#
# There is no direct DELETE route: `saved_view.delete` runs through the deferred-action
# registry (see `test_saved_view_delete_record_action` below, plus the parametrised sweep
# in `tests/test_record_actions_s6b.py`). `SavedViewsService.delete` is the one line the
# record action calls, so ownership is proven at THAT layer.


def test_delete_only_removes_the_owners_own_view(db):
    from app.services.saved_views_service import SavedViewsService

    from app.schemas.saved_view import SavedViewConfig

    svc = SavedViewsService(db)
    created = svc.create(LISTING_KEY, _ME["id"], "Mine to delete", SavedViewConfig(**_config()))
    svc.delete(created.id, _ME["id"])

    listed = svc.list_for(LISTING_KEY, _ME["id"])
    assert listed.mine == []


def test_delete_refuses_someone_elses_view(db):
    from app.schemas.saved_view import SavedViewConfig
    from app.services.error_handler import AppException
    from app.services.saved_views_service import SavedViewsService

    svc = SavedViewsService(db)
    theirs = svc.create(LISTING_KEY, _OTHER_ID, "Theirs", SavedViewConfig(**_config()))

    with pytest.raises(AppException) as exc_info:
        svc.delete(theirs.id, _ME["id"])
    assert exc_info.value.status_code == 404

    listed = svc.list_for(LISTING_KEY, _OTHER_ID)
    assert [v.name for v in listed.mine] == ["Theirs"]


# --------------------------------------------------------- delete (RECORD ACTION, D7)


def test_saved_view_delete_record_action_end_to_end(db):
    """`saved_view.delete` (OWN_RECORD, WINDOW_DESTRUCTIVE) end to end: parked, untouched
    until the window lapses, then gone - and never reachable for a view the requester
    does not own. `tests/test_record_actions_s6b.py` covers the registration contract for
    every record action; this is the shape-specific end-to-end proof, mirroring its own
    `test_a_notification_is_deleted_only_for_the_reader_who_owns_it`."""
    from datetime import datetime, timedelta

    from fastapi import Depends
    from app.models.base import set_company_scope
    from app.models.sla import FORM_ACTION_COMMITTED, SlaFormAction
    from app.schemas.saved_view import SavedViewConfig
    from app.services import record_actions  # noqa: F401  registers the record actions
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.form_action_grace import WINDOW_DESTRUCTIVE, window_class_for
    from app.services.form_action_registry import REGISTRY
    from app.services.saved_views_service import SavedViewsService

    action = REGISTRY["saved_view.delete"]
    assert action.permission == record_actions.OWN_RECORD
    assert window_class_for(action) == WINDOW_DESTRUCTIVE

    svc = SavedViewsService(db)
    mine = svc.create(LISTING_KEY, _ME["id"], "Mine, parked", SavedViewConfig(**_config()))
    theirs = svc.create(LISTING_KEY, _OTHER_ID, "Theirs, untouchable", SavedViewConfig(**_config()))

    def _override_db():
        yield db

    def _override_scope(_db=Depends(get_db)):
        set_company_scope(_db, None)
        return None

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[apply_company_scope] = _override_scope
    app.dependency_overrides[get_current_user] = lambda: _ME
    try:
        with TestClient(app) as c:
            base = "/api/v1/pending-actions"

            def _start(entity_id):
                return c.post(
                    base,
                    json={
                        "action_key": "saved_view.delete",
                        "entity_type": "saved_view",
                        "entity_id": str(entity_id),
                        "payload": {},
                    },
                )

            def _lapse_and_poll(entity_id, action_id):
                db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
                    {"commit_at": datetime.utcnow() - timedelta(seconds=1)},
                    synchronize_session=False,
                )
                db.commit()
                return c.get(
                    f"{base}/current",
                    params={"entity_type": "saved_view", "entity_id": str(entity_id)},
                )

            parked_mine = _start(mine.id)
            assert parked_mine.status_code == 202, parked_mine.text
            assert parked_mine.json()["window_seconds"] == 10  # destructive, not the short window
            body = _lapse_and_poll(mine.id, parked_mine.json()["id"]).json()
            assert body["last_outcome"]["status"] == "committed", body["last_outcome"]

            parked_theirs = _start(theirs.id)
            assert parked_theirs.status_code == 202, parked_theirs.text
            body = _lapse_and_poll(theirs.id, parked_theirs.json()["id"]).json()
            assert body["last_outcome"]["status"] == "failed", body["last_outcome"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(apply_company_scope, None)
        app.dependency_overrides.pop(get_current_user, None)

    db.expire_all()
    listed_mine = SavedViewsService(db).list_for(LISTING_KEY, _ME["id"])
    assert listed_mine.mine == []
    listed_theirs = SavedViewsService(db).list_for(LISTING_KEY, _OTHER_ID)
    assert [v.name for v in listed_theirs.mine] == ["Theirs, untouchable"]
