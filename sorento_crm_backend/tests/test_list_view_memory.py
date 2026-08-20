"""Listing view memory: sticky sort + sticky filter on the column-config row.

Contract: documentation/plans/listings/listing-view-memory-acceptance-criteria.md
(AC-A1 .. AC-A6). Design: documentation/plans/listings/PLAN-listing-view-memory.md.

The load-bearing behaviour is the MERGE. Two independent writers share one
`(user_id, listing_key)` row: DataGrid's column hook writes the three column keys
from inside the grid, and the page's view hook writes `sorting` / `filters` /
`filtersVersion` from above it. A whole-blob replace makes each writer wipe the
other's keys, which reads as flaky persistence rather than as a bug - so the merge
is pinned from BOTH write directions here.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.user import (
    User,
    UserListColumnConfig,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from tests._pg_fixture import TEST_PREFIX, blank_session, unique_code

# Every row this module creates carries the marker, so nothing is borrowed from an
# existing table and nothing asserts against a production row.
PERM_SLUG = f"{TEST_PREFIX.lower()}.view_memory.view"
LISTING_KEY = f"{PERM_SLUG}::stock-inquiries"


def _seed_rbac_and_user(db: Session, *, user_id: str, permission_slug: str, role_id: str) -> None:
    """Seed the whole chain: permission -> role -> grant -> user -> assignment."""
    perm = db.query(UserPermission).filter(UserPermission.slug == permission_slug).first()
    if perm is None:
        perm = UserPermission(
            id=f"perm_{permission_slug}",
            slug=permission_slug,
            name=f"{TEST_PREFIX} perm",
            description="",
        )
        db.add(perm)
        db.flush()

    role = db.query(UserRole).filter(UserRole.id == role_id).first()
    if role is None:
        role = UserRole(
            id=role_id,
            slug=f"role_{role_id}",
            name=f"{TEST_PREFIX} role {role_id}",
            description="",
            is_trashed=False,
            is_protected=False,
            is_default=False,
        )
        db.add(role)
        db.flush()

    if (
        db.query(UserRolePermission)
        .filter(UserRolePermission.role_id == role.id, UserRolePermission.permission_id == perm.id)
        .first()
        is None
    ):
        db.add(UserRolePermission(role_id=role.id, permission_id=perm.id))

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        user = User(
            id=user_id,
            email=f"{unique_code('viewmem')}@test.com",
            status="ACTIVE",
            name=f"{TEST_PREFIX} user",
        )
        db.add(user)
        db.flush()

    if (
        db.query(UserRoleAssignment)
        .filter(UserRoleAssignment.user_id == user.id, UserRoleAssignment.role_id == role.id)
        .first()
        is None
    ):
        db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))

    db.commit()


@pytest.fixture
def api_client():
    with blank_session() as db:
        current_user = {"id": str(uuid.uuid4())}

        def _override_current_user():
            return {"id": current_user["id"]}

        def _override_get_db():
            yield db

        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_db] = _override_get_db

        with TestClient(app) as client:
            _seed_rbac_and_user(
                db,
                user_id=current_user["id"],
                permission_slug=PERM_SLUG,
                role_id=f"{TEST_PREFIX}-role-granted",
            )
            yield client, current_user, db

        app.dependency_overrides.clear()


def _url(listing_key: str = LISTING_KEY) -> str:
    return f"/api/v1/list-query/column-config/{listing_key}"


def _stored_config(db: Session, user_id: str, listing_key: str = LISTING_KEY):
    db.expire_all()
    row = (
        db.query(UserListColumnConfig)
        .filter(
            UserListColumnConfig.user_id == user_id,
            UserListColumnConfig.listing_key == listing_key,
        )
        .first()
    )
    return getattr(row, "config", None) if row else None


COLUMN_KEYS = {
    "columnOrder": ["status", "created_at"],
    "columnVisibility": {"status": True, "remark": False},
    "columnSizing": {"status": 110.0},
}
VIEW_KEYS = {
    "sorting": [{"id": "status", "desc": False}],
    "filters": {"statuses": ["pending_purchasing"]},
    "filtersVersion": 1,
}


# --- AC-A1 -----------------------------------------------------------------


def test_stored_config_accepts_sort_and_filter(api_client):
    """AC-A1: sorting and filters survive the write and the next read."""
    client, current_user, _ = api_client

    r = client.put(_url(), json={"version": 1, **VIEW_KEYS})
    assert r.status_code == 200
    cfg = r.json()["config"]
    assert cfg["sorting"] == [{"id": "status", "desc": False}]
    assert cfg["filters"] == {"statuses": ["pending_purchasing"]}
    assert cfg["filtersVersion"] == 1

    r2 = client.get(_url())
    assert r2.status_code == 200
    assert r2.json()["config"]["sorting"] == [{"id": "status", "desc": False}]
    assert r2.json()["config"]["filters"] == {"statuses": ["pending_purchasing"]}
    assert r2.json()["config"]["filtersVersion"] == 1


def test_filters_blob_is_opaque(api_client):
    """The page owns the filter shape; the backend never interprets it."""
    client, _, _ = api_client

    blob = {
        "logic": "and",
        "conditions": [{"field": "status", "op": "in", "value": ["a", "b"]}],
        "nested": {"depth": {"deeper": [1, 2, 3]}},
    }
    r = client.put(_url(), json={"version": 1, "filters": blob, "filtersVersion": 7})
    assert r.status_code == 200
    assert r.json()["config"]["filters"] == blob
    assert client.get(_url()).json()["config"]["filters"] == blob


# --- AC-A2 -----------------------------------------------------------------


def test_column_only_write_preserves_sort_and_filter(api_client):
    """AC-A2, direction 1: the column writer must not wipe the view keys."""
    client, current_user, db = api_client

    client.put(_url(), json={"version": 1, **COLUMN_KEYS, **VIEW_KEYS})

    r = client.put(_url(), json={"version": 1, **COLUMN_KEYS})
    assert r.status_code == 200
    cfg = r.json()["config"]
    assert cfg["sorting"] == VIEW_KEYS["sorting"]
    assert cfg["filters"] == VIEW_KEYS["filters"]
    assert cfg["filtersVersion"] == VIEW_KEYS["filtersVersion"]
    assert _stored_config(db, current_user["id"])["filters"] == VIEW_KEYS["filters"]


def test_view_only_write_preserves_column_keys(api_client):
    """AC-A2, direction 2: the view writer must not wipe the column keys."""
    client, current_user, db = api_client

    client.put(_url(), json={"version": 1, **COLUMN_KEYS, **VIEW_KEYS})

    r = client.put(
        _url(),
        json={
            "version": 1,
            "sorting": [{"id": "inquiry_number", "desc": True}],
            "filters": {"statuses": ["responded"]},
            "filtersVersion": 1,
        },
    )
    assert r.status_code == 200
    cfg = r.json()["config"]
    assert cfg["columnOrder"] == COLUMN_KEYS["columnOrder"]
    assert cfg["columnVisibility"] == COLUMN_KEYS["columnVisibility"]
    assert cfg["columnSizing"] == COLUMN_KEYS["columnSizing"]
    assert cfg["sorting"] == [{"id": "inquiry_number", "desc": True}]
    stored = _stored_config(db, current_user["id"])
    assert stored["columnOrder"] == COLUMN_KEYS["columnOrder"]


def test_put_response_is_the_full_merged_config(api_client):
    """The frontend seeds its query cache from this body, so a partial echo would
    drop the other writer's keys at the client layer even though the row is fine."""
    client, _, _ = api_client

    client.put(_url(), json={"version": 1, **COLUMN_KEYS, **VIEW_KEYS})

    r = client.put(_url(), json={"version": 1, "sorting": [{"id": "status", "desc": True}]})
    assert r.status_code == 200
    cfg = r.json()["config"]
    assert set(cfg) >= {
        "columnOrder",
        "columnVisibility",
        "columnSizing",
        "sorting",
        "filters",
        "filtersVersion",
    }
    assert cfg == client.get(_url()).json()["config"]


def test_absent_key_is_not_a_clear(api_client):
    """`exclude_unset`: omitting a key means "not writing it", never "clear it"."""
    client, _, _ = api_client

    client.put(_url(), json={"version": 1, **VIEW_KEYS})
    r = client.put(_url(), json={"version": 1, "sorting": [{"id": "created_at", "desc": True}]})
    assert r.status_code == 200
    assert r.json()["config"]["filters"] == VIEW_KEYS["filters"]
    assert r.json()["config"]["filtersVersion"] == 1


# --- AC-A3 -----------------------------------------------------------------


def test_explicit_null_clears_the_key(api_client):
    """AC-A3: `filters: null` present in the body is the Clear affordance."""
    client, current_user, db = api_client

    client.put(_url(), json={"version": 1, **COLUMN_KEYS, **VIEW_KEYS})

    r = client.put(_url(), json={"version": 1, "filters": None, "filtersVersion": None})
    assert r.status_code == 200
    cfg = r.json()["config"]
    assert "filters" not in cfg
    assert "filtersVersion" not in cfg
    # Everything else is untouched.
    assert cfg["columnOrder"] == COLUMN_KEYS["columnOrder"]
    assert cfg["sorting"] == VIEW_KEYS["sorting"]

    stored = _stored_config(db, current_user["id"])
    assert "filters" not in stored
    assert stored["columnOrder"] == COLUMN_KEYS["columnOrder"]


def test_explicit_null_clears_sorting_only(api_client):
    """A listing back on its shipped default sort clears the key, keeping the rest."""
    client, _, _ = api_client

    client.put(_url(), json={"version": 1, **COLUMN_KEYS, **VIEW_KEYS})

    r = client.put(_url(), json={"version": 1, "sorting": None})
    assert r.status_code == 200
    cfg = r.json()["config"]
    assert "sorting" not in cfg
    assert cfg["filters"] == VIEW_KEYS["filters"]
    assert cfg["columnSizing"] == COLUMN_KEYS["columnSizing"]


# --- AC-A4 -----------------------------------------------------------------


def test_reset_clears_everything(api_client):
    """AC-A4: DELETE is "reset this listing for me", columns and view alike."""
    client, current_user, db = api_client

    client.put(_url(), json={"version": 1, **COLUMN_KEYS, **VIEW_KEYS})

    r = client.delete(_url())
    assert r.status_code == 204
    assert client.get(_url()).json()["config"] is None
    assert _stored_config(db, current_user["id"]) is None


# --- AC-A5 -----------------------------------------------------------------


def test_put_with_view_keys_denied_without_permission(api_client):
    """AC-A5: the gate is unchanged by the new keys, and nothing is stored."""
    client, _, db = api_client

    other_slug = f"{TEST_PREFIX.lower()}.view_memory_denied.view"
    db.add(
        UserPermission(
            id=f"perm_{other_slug}",
            slug=other_slug,
            name=f"{TEST_PREFIX} perm",
            description="",
        )
    )
    db.commit()

    denied_key = f"{other_slug}::stock-inquiries"
    r = client.put(_url(denied_key), json={"version": 1, **VIEW_KEYS})
    assert r.status_code == 403

    row = (
        db.query(UserListColumnConfig)
        .filter(UserListColumnConfig.listing_key == denied_key)
        .first()
    )
    assert row is None


# --- AC-A6 -----------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_sorting",
    [
        "created_at",
        ["created_at"],
        [{"desc": True}],
        [{"id": "created_at", "desc": "yesplease"}],
        [{"id": 5, "desc": True}],
        {"id": "created_at", "desc": True},
    ],
)
def test_malformed_sorting_is_rejected(api_client, bad_sorting):
    """AC-A6: sorting drives an ORDER BY on the next request, so it is validated."""
    client, current_user, db = api_client

    r = client.put(_url(), json={"version": 1, "sorting": bad_sorting})
    assert r.status_code == 422
    assert _stored_config(db, current_user["id"]) is None


def test_malformed_sorting_leaves_an_existing_config_untouched(api_client):
    client, current_user, db = api_client

    client.put(_url(), json={"version": 1, **COLUMN_KEYS, **VIEW_KEYS})

    r = client.put(_url(), json={"version": 1, "sorting": ["created_at"]})
    assert r.status_code == 422

    stored = _stored_config(db, current_user["id"])
    assert stored["sorting"] == VIEW_KEYS["sorting"]
    assert stored["columnOrder"] == COLUMN_KEYS["columnOrder"]
