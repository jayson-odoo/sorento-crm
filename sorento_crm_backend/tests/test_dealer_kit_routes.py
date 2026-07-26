"""Route-level tests for /api/v1/dealer-kit/pages.

``test_dealer_kit_pages.py`` covers the service: versioning, labels, the public
resolve. This file covers the thing a service test structurally cannot - the
permission split declared on the routes.

The split is the whole point of the design (see the docstring on
``app/api/v1/dealer_kit/pages.py``): ``page.edit`` drafts, ``page.publish`` puts
a document in front of every dealer. A holder of ``page.edit`` alone must be
able to save a version and move ``staging``, and must be REFUSED on
``published`` - including the rollback path, which moves the same label and so
carries the same blast radius.

Auth-override pattern from test_record_context_route.py.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session

_ADMIN_ID = "2f1a7d64-8c3e-5b21-9d47-1a0e5c9b3f22"
_ADMIN_ROLE = "6b9c2e18-4d75-5a03-8e16-7c4f2b8d1a90"
_EDITOR_ID = "8d4e1c05-2b96-5f84-a3d1-9e6b0c2f7a45"
_EDITOR_ROLE = "3c7f9a21-5e48-5d16-b072-4a8d1f6e3b59"
_NOPERM_ID = "5a2b8e73-9c14-5027-8fb6-2d3e7a1c94f8"


def _seed(db: Session) -> None:
    """Two roles: a superadmin, and an editor holding view+edit but NOT publish."""
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_ADMIN_ROLE,
            slug="superadmin",
            name="Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
    )
    db.add(
        UserRole(
            id=_EDITOR_ROLE,
            slug="zzt_dk_editor",
            name="ZZT Dealer Kit Editor",
            description="Drafts catalogues, cannot publish them",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(User(id=_ADMIN_ID, email="zzt-dk-admin@test.com", name="DK Admin", status="ACTIVE"))
    db.add(User(id=_EDITOR_ID, email="zzt-dk-editor@test.com", name="DK Editor", status="ACTIVE"))
    db.add(User(id=_NOPERM_ID, email="zzt-dk-noperm@test.com", name="DK Outsider", status="ACTIVE"))
    db.flush()

    db.add(UserRoleAssignment(user_id=_ADMIN_ID, role_id=_ADMIN_ROLE))
    db.add(UserRoleAssignment(user_id=_EDITOR_ID, role_id=_EDITOR_ROLE))

    # blank_session builds an empty schema, so the permission rows the migration
    # seeds in a real database have to be created here.
    granted = ("dealer_kit.page.view", "dealer_kit.page.edit")
    for slug in granted + ("dealer_kit.page.publish",):
        perm_id = str(uuid.uuid4())
        db.add(
            UserPermission(id=perm_id, slug=slug, name=slug, description="")
        )
        db.flush()
        if slug in granted:
            db.add(
                UserRolePermission(
                    id=str(uuid.uuid4()), role_id=_EDITOR_ROLE, permission_id=perm_id
                )
            )
    db.commit()


@pytest.fixture
def api():
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db,
    )
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    # The real resolver reads the bearer token, which these tests do not send
    # (they override the principal dependencies instead). Left alone it returns
    # UNSET and every owned INSERT is refused before any route logic runs. Pin
    # it to the incumbent company - what a logged-in Sorento user resolves to -
    # so what is under test here is the permission split, not scope resolution
    # (which tests/test_company_scope.py owns).
    _SORENTO = "00000000-0000-0000-0000-000000000001"

    with blank_session() as db:
        _seed(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            # The router sits behind a module guard resolving
            # get_current_user_or_api_key, while the routes themselves resolve
            # get_current_user. Both need a principal, or every call is a 401
            # before any permission check is reached. The permission service
            # itself is NOT stubbed - it is the thing under test.
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db, _as

        app.dependency_overrides.clear()


def _create_page(client: TestClient, slug: str = "zzt-catalogue-2026") -> str:
    res = client.post(
        "/api/v1/dealer-kit/pages", json={"name": "ZZT Catalogue", "slug": slug}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _save_version(client: TestClient, page_id: str, message: str) -> str:
    res = client.post(
        f"/api/v1/dealer-kit/pages/{page_id}/versions",
        json={"doc": {"sections": []}, "commitMessage": message},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# --------------------------------------------------------------------------
# The permission split
# --------------------------------------------------------------------------


def test_editor_can_draft_but_not_publish(api):
    """The gate item: page.edit without page.publish is 403 on the published label."""
    _db, _as = api
    _as(_EDITOR_ID)

    with TestClient(app) as c:
        page_id = _create_page(c)
        version_id = _save_version(c, page_id, "first draft")

        staged = c.put(
            f"/api/v1/dealer-kit/pages/{page_id}/labels/staging",
            json={"versionId": version_id},
        )
        assert staged.status_code == 200, staged.text
        assert "staging" in staged.json()["labels"]

        published = c.put(
            f"/api/v1/dealer-kit/pages/{page_id}/labels/published",
            json={"versionId": version_id},
        )
        assert published.status_code == 403, published.text
        assert "dealer_kit.page.publish" in published.text


def test_rollback_needs_publish_too(api):
    """Rollback moves the same label at the same readers, so it is gated the same."""
    db, _as = api

    _as(_ADMIN_ID)
    with TestClient(app) as c:
        page_id = _create_page(c, "zzt-rollback-perm")
        v1 = _save_version(c, page_id, "v1")
        v2 = _save_version(c, page_id, "v2")
        assert (
            c.put(
                f"/api/v1/dealer-kit/pages/{page_id}/labels/published",
                json={"versionId": v2},
            ).status_code
            == 200
        )

    # Same page, now as the editor: rolling back to v1 is refused.
    _as(_EDITOR_ID)
    with TestClient(app) as c:
        res = c.put(
            f"/api/v1/dealer-kit/pages/{page_id}/labels/published",
            json={"versionId": v1},
        )
    assert res.status_code == 403, res.text

    # And the live version did not move.
    from app.services.dealer_kit import page_service as svc

    assert svc.labels_for(db, page_id)[v2] == ["published"]


def test_a_user_with_no_dealer_kit_permission_is_refused(api):
    _db, _as = api
    _as(_NOPERM_ID)

    with TestClient(app) as c:
        assert c.get("/api/v1/dealer-kit/pages").status_code == 403
        assert (
            c.post(
                "/api/v1/dealer-kit/pages",
                json={"name": "Sneaky", "slug": "zzt-sneaky"},
            ).status_code
            == 403
        )


def test_superadmin_publishes(api):
    _db, _as = api
    _as(_ADMIN_ID)

    with TestClient(app) as c:
        page_id = _create_page(c, "zzt-admin-publish")
        version_id = _save_version(c, page_id, "ship it")
        res = c.put(
            f"/api/v1/dealer-kit/pages/{page_id}/labels/published",
            json={"versionId": version_id},
        )
        assert res.status_code == 200, res.text
        assert "published" in res.json()["labels"]

        listed = c.get("/api/v1/dealer-kit/pages")
        row = next(r for r in listed.json() if r["id"] == page_id)
        assert row["publishedVersion"] == 1


# --------------------------------------------------------------------------
# Happy path, validation, absence
# --------------------------------------------------------------------------


def test_create_read_delete_round_trip(api):
    _db, _as = api
    _as(_ADMIN_ID)

    with TestClient(app) as c:
        page_id = _create_page(c, "zzt-round-trip")

        got = c.get(f"/api/v1/dealer-kit/pages/{page_id}")
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["slug"] == "zzt-round-trip"
        # A page created through the API is immediately usable in paper mode:
        # a print profile is seeded rather than left null for the FE to guess.
        assert body["doc"]["printProfile"]["pageSize"] == "A4"

        assert c.delete(f"/api/v1/dealer-kit/pages/{page_id}").status_code == 204
        assert c.get(f"/api/v1/dealer-kit/pages/{page_id}").status_code == 404


@pytest.mark.parametrize(
    "slug",
    ["Catalogue 2026", "zzt--double", "-leading", "trailing-", "zzt_underscore", ""],
)
def test_a_bad_address_is_rejected_before_it_reaches_a_url(api, slug):
    _db, _as = api
    _as(_ADMIN_ID)

    with TestClient(app) as c:
        res = c.post("/api/v1/dealer-kit/pages", json={"name": "X", "slug": slug})
    assert res.status_code == 422, res.text


def test_unknown_page_is_404_on_every_route(api):
    _db, _as = api
    _as(_ADMIN_ID)
    missing = str(uuid.uuid4())

    with TestClient(app) as c:
        assert c.get(f"/api/v1/dealer-kit/pages/{missing}").status_code == 404
        assert c.get(f"/api/v1/dealer-kit/pages/{missing}/versions").status_code == 404
        assert (
            c.post(
                f"/api/v1/dealer-kit/pages/{missing}/versions",
                json={"doc": {}, "commitMessage": None},
            ).status_code
            == 404
        )
        assert c.delete(f"/api/v1/dealer-kit/pages/{missing}").status_code == 404
