"""Tag template publish/unpublish/versions/restore routes (PLAN D7, S5).

Publish snapshots the draft into an immutable version and moves the live
pointer; the request designer's template source (AC-S5-2) must see ONLY that
pointer's doc, never the draft that keeps changing underneath it. Restore is
the reverse motion - it copies a version's doc back into the draft and
deliberately never touches the pointer, so restoring an old design is not the
same act as publishing it.

Auth-override pattern from test_dealer_kit_edition_routes.py /
test_dealer_kit_routes.py.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session, unique_code

_SORENTO = "00000000-0000-0000-0000-000000000001"

_EDITOR_ID = "1a2b3c4d-5e6f-5a1b-8c2d-3e4f5a6b7c81"
_EDITOR_ROLE = "2b3c4d5e-6f7a-5b2c-9d3e-4f5a6b7c8d92"
_VIEWER_ID = "3c4d5e6f-7a8b-5c3d-0e4f-5a6b7c8d9ea3"
_VIEWER_ROLE = "4d5e6f7a-8b9c-5d4e-1f5a-6b7c8d9eafb4"
_NOPERM_ID = "5e6f7a8b-9c0d-5e5f-2a6b-7c8d9eafb0c5"


def _seed_roles(db: Session) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    slugs = ("dealer_kit.tag_templates.view", "dealer_kit.tag_templates.manage")
    perm_ids: dict[str, str] = {}
    for slug in slugs:
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        perm_ids[slug] = perm_id
    db.flush()

    roles = (
        (_EDITOR_ROLE, "zzt_tt_editor", _EDITOR_ID, slugs),
        (_VIEWER_ROLE, "zzt_tt_viewer", _VIEWER_ID, (slugs[0],)),
    )
    for role_id, slug, user_id, granted in roles:
        db.add(
            UserRole(
                id=role_id, slug=slug, name=slug, description="",
                is_protected=False, is_default=False,
            )
        )
        db.add(User(id=user_id, email=f"{slug}@test.com", name=slug, status="ACTIVE"))
        db.flush()
        db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
        for granted_slug in granted:
            db.add(
                UserRolePermission(
                    id=str(uuid.uuid4()), role_id=role_id, permission_id=perm_ids[granted_slug]
                )
            )
    db.add(User(id=_NOPERM_ID, email="zzt-tt-noperm@test.com", name="Outsider", status="ACTIVE"))
    db.commit()


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)
        here = {"company": _SORENTO}

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({here["company"]})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def _in_company(company_id: str):
            here["company"] = company_id
            set_company_scope(db, frozenset({company_id}))

        _as(_EDITOR_ID)
        yield db, _as, _in_company

        app.dependency_overrides.clear()


def _doc(width=85, height=58):
    return {"layers": [], "width_mm": width, "height_mm": height}


def _create_template(client: TestClient, name: str | None = None) -> str:
    res = client.post(
        "/api/v1/dealer-kit/tag-templates",
        json={
            "name": name or unique_code("Tmpl"),
            "family": "toilet",
            "doc": _doc(),
            "print_size": {"width_mm": 85, "height_mm": 58},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ---------------------------------------------------------------------------
# AC-S5-1: publish snapshots + moves the pointer
# ---------------------------------------------------------------------------


def test_publish_creates_v1_and_moves_the_pointer(api):
    _db, _as, _scope = api

    with TestClient(app) as client:
        template_id = _create_template(client)

        published = client.post(
            f"/api/v1/dealer-kit/tag-templates/{template_id}/publish",
            json={"note": "first release"},
        )
        assert published.status_code == 200, published.text
        body = published.json()
        assert body["published_version_id"]
        assert body["published_version_no"] == 1

        versions = client.get(f"/api/v1/dealer-kit/tag-templates/{template_id}/versions")

    assert versions.status_code == 200, versions.text
    rows = versions.json()
    assert len(rows) == 1
    assert rows[0]["version_no"] == 1
    assert rows[0]["note"] == "first release"
    assert rows[0]["created_by_name"]


def test_a_draft_edit_after_publish_does_not_move_the_live_version(api):
    _db, _as, _scope = api

    with TestClient(app) as client:
        template_id = _create_template(client)
        client.post(f"/api/v1/dealer-kit/tag-templates/{template_id}/publish")

        client.put(
            f"/api/v1/dealer-kit/tag-templates/{template_id}",
            json={"doc": _doc(width=90, height=60)},
        )

        published_list = client.get(
            "/api/v1/dealer-kit/tag-templates", params={"published": "1"}
        )

    assert published_list.status_code == 200, published_list.text
    row = next(r for r in published_list.json() if r["id"] == template_id)
    # The published branch answers the v1 SNAPSHOT, not the edited draft.
    assert row["doc"]["width_mm"] == 85


def test_a_concurrent_publish_is_a_409_not_a_500(api, monkeypatch):
    """Two publishes racing both compute ``next_version_no`` before either
    commits, so the second's INSERT collides on
    ``uq_dealer_kit_tag_template_version`` and Postgres raises IntegrityError
    at flush. Forced here by making the flush that carries the pending
    ``TagTemplateVersion`` raise it once - an incidental autoflush earlier in
    the same request (``_get_template_or_404``'s SELECT) must NOT trip it,
    or this would fail before the route's own try/except is even reached."""
    from sqlalchemy.exc import IntegrityError
    from app.models.dealer_kit import TagTemplateVersion

    db, _as, _scope = api

    with TestClient(app) as client:
        template_id = _create_template(client)

        original_flush = db.flush

        def _flush_maybe_conflicting(*args, **kwargs):
            if any(isinstance(obj, TagTemplateVersion) for obj in db.new):
                monkeypatch.setattr(db, "flush", original_flush)
                raise IntegrityError(
                    "INSERT INTO dealer_kit.tag_template_version ...",
                    {},
                    Exception(
                        'duplicate key value violates unique constraint '
                        '"uq_dealer_kit_tag_template_version"'
                    ),
                )
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(db, "flush", _flush_maybe_conflicting)

        published = client.post(f"/api/v1/dealer-kit/tag-templates/{template_id}/publish")

        # The session survived the rollback and still works for the next
        # request - a real race leaves the template publishable again.
        retried = client.post(f"/api/v1/dealer-kit/tag-templates/{template_id}/publish")

    assert published.status_code == 409, published.text
    assert published.json()["code"] == "tag_template_publish_conflict"
    assert retried.status_code == 200, retried.text


def test_publishing_again_creates_v2_and_moves_the_pointer_forward(api):
    _db, _as, _scope = api

    with TestClient(app) as client:
        template_id = _create_template(client)
        client.post(f"/api/v1/dealer-kit/tag-templates/{template_id}/publish")
        client.put(
            f"/api/v1/dealer-kit/tag-templates/{template_id}",
            json={"doc": _doc(width=90, height=60)},
        )
        second = client.post(
            f"/api/v1/dealer-kit/tag-templates/{template_id}/publish",
            json={"note": "v2"},
        )

    assert second.status_code == 200, second.text
    assert second.json()["published_version_no"] == 2


# ---------------------------------------------------------------------------
# AC-S5-2: published-only resolution
# ---------------------------------------------------------------------------


def test_the_published_list_substitutes_the_versions_print_size_too(api):
    """AC-S5-2 covers ``doc``; the same drift can happen to ``print_size`` the
    moment a draft edit changes the tag's dimensions after a publish."""
    _db, _as, _scope = api

    with TestClient(app) as client:
        template_id = _create_template(client)
        client.post(f"/api/v1/dealer-kit/tag-templates/{template_id}/publish")

        client.put(
            f"/api/v1/dealer-kit/tag-templates/{template_id}",
            json={"print_size": {"width_mm": 100, "height_mm": 70}},
        )

        published_list = client.get(
            "/api/v1/dealer-kit/tag-templates", params={"published": "1"}
        )
        unfiltered = client.get(f"/api/v1/dealer-kit/tag-templates/{template_id}")

    row = next(r for r in published_list.json() if r["id"] == template_id)
    assert row["print_size"] == {"width_mm": 85, "height_mm": 58}
    # The draft (unfiltered) branch shows the edited size - proves the two
    # really did diverge rather than the assertion above being a no-op.
    assert unfiltered.json()["print_size"] == {"width_mm": 100, "height_mm": 70}


def test_a_never_published_template_is_absent_from_the_published_list(api):
    _db, _as, _scope = api

    with TestClient(app) as client:
        _create_template(client)
        published_list = client.get(
            "/api/v1/dealer-kit/tag-templates", params={"published": "1"}
        )

    assert published_list.status_code == 200, published_list.text
    assert published_list.json() == []


def test_the_unfiltered_list_still_shows_drafts(api):
    _db, _as, _scope = api

    with TestClient(app) as client:
        template_id = _create_template(client)
        everything = client.get("/api/v1/dealer-kit/tag-templates")

    assert everything.status_code == 200, everything.text
    row = next(r for r in everything.json() if r["id"] == template_id)
    assert row["published_version_id"] is None


# ---------------------------------------------------------------------------
# AC-S5-3: unpublish
# ---------------------------------------------------------------------------


def test_unpublish_removes_it_from_the_published_list_but_keeps_draft_and_versions(api):
    _db, _as, _scope = api

    with TestClient(app) as client:
        template_id = _create_template(client)
        client.post(f"/api/v1/dealer-kit/tag-templates/{template_id}/publish")

        unpublished = client.post(
            f"/api/v1/dealer-kit/tag-templates/{template_id}/unpublish"
        )
        assert unpublished.status_code == 200, unpublished.text
        assert unpublished.json()["published_version_id"] is None

        published_list = client.get(
            "/api/v1/dealer-kit/tag-templates", params={"published": "1"}
        )
        still_there = client.get(f"/api/v1/dealer-kit/tag-templates/{template_id}")
        versions = client.get(f"/api/v1/dealer-kit/tag-templates/{template_id}/versions")

    assert template_id not in {r["id"] for r in published_list.json()}
    assert still_there.status_code == 200
    assert len(versions.json()) == 1


# ---------------------------------------------------------------------------
# AC-S5-8 / D16: view a past version's full doc
# ---------------------------------------------------------------------------


def test_a_past_versions_full_doc_is_readable(api):
    _db, _as, _scope = api

    with TestClient(app) as client:
        template_id = _create_template(client)
        v1 = client.post(f"/api/v1/dealer-kit/tag-templates/{template_id}/publish").json()
        version_id = v1["published_version_id"]

        detail = client.get(
            f"/api/v1/dealer-kit/tag-templates/{template_id}/versions/{version_id}"
        )

    assert detail.status_code == 200, detail.text
    assert detail.json()["doc"]["width_mm"] == 85


# ---------------------------------------------------------------------------
# AC-S5-6 / D15: restore copies a version's doc into the draft, pointer untouched
# ---------------------------------------------------------------------------


def test_restore_copies_the_version_into_the_draft_without_moving_the_pointer(api):
    _db, _as, _scope = api

    with TestClient(app) as client:
        template_id = _create_template(client)
        v1 = client.post(f"/api/v1/dealer-kit/tag-templates/{template_id}/publish").json()
        v1_version_id = v1["published_version_id"]

        # Draft drifts away from v1, then gets published as v2.
        client.put(
            f"/api/v1/dealer-kit/tag-templates/{template_id}",
            json={"doc": _doc(width=90, height=60)},
        )
        client.post(f"/api/v1/dealer-kit/tag-templates/{template_id}/publish")

        restored = client.post(
            f"/api/v1/dealer-kit/tag-templates/{template_id}/versions/{v1_version_id}/restore"
        )
        assert restored.status_code == 200, restored.text
        body = restored.json()

        # The draft now reads like v1 again...
        assert body["doc"]["width_mm"] == 85
        # ...but the live pointer is still v2 - restore is not a publish.
        assert body["published_version_no"] == 2


# ---------------------------------------------------------------------------
# Company scope: no cross-company version access (CompanyScopedMixin)
# ---------------------------------------------------------------------------


class TestScope:
    def test_another_companys_template_versions_is_404(self, api):
        db, _as, _scope = api

        with TestClient(app) as client:
            template_id = _create_template(client)
            client.post(f"/api/v1/dealer-kit/tag-templates/{template_id}/publish")

        _scope(str(uuid.uuid4()))

        with TestClient(app) as client:
            got = client.get(f"/api/v1/dealer-kit/tag-templates/{template_id}/versions")
            detail = client.get(f"/api/v1/dealer-kit/tag-templates/{template_id}")
            publish = client.post(
                f"/api/v1/dealer-kit/tag-templates/{template_id}/publish"
            )

        assert got.status_code == 404, got.text
        assert detail.status_code == 404, detail.text
        assert publish.status_code == 404, publish.text

    def test_another_companys_version_detail_is_404(self, api):
        db, _as, _scope = api

        with TestClient(app) as client:
            template_id = _create_template(client)
            published = client.post(
                f"/api/v1/dealer-kit/tag-templates/{template_id}/publish"
            ).json()
            version_id = published["published_version_id"]

        _scope(str(uuid.uuid4()))

        with TestClient(app) as client:
            got = client.get(
                f"/api/v1/dealer-kit/tag-templates/{template_id}/versions/{version_id}"
            )

        assert got.status_code == 404, got.text

    def test_another_companys_restore_is_404(self, api):
        db, _as, _scope = api

        with TestClient(app) as client:
            template_id = _create_template(client)
            published = client.post(
                f"/api/v1/dealer-kit/tag-templates/{template_id}/publish"
            ).json()
            version_id = published["published_version_id"]

        _scope(str(uuid.uuid4()))

        with TestClient(app) as client:
            restored = client.post(
                f"/api/v1/dealer-kit/tag-templates/{template_id}/versions/{version_id}/restore"
            )

        assert restored.status_code == 404, restored.text


# ---------------------------------------------------------------------------
# Permission split: view cannot publish/unpublish/restore
# ---------------------------------------------------------------------------


class TestPermissionSplit:
    def test_a_viewer_can_read_versions_but_not_publish(self, api):
        db, _as, _scope = api

        with TestClient(app) as client:
            template_id = _create_template(client)

        _as(_VIEWER_ID)
        with TestClient(app) as client:
            listed = client.get(f"/api/v1/dealer-kit/tag-templates/{template_id}/versions")
            denied = client.post(f"/api/v1/dealer-kit/tag-templates/{template_id}/publish")

        assert listed.status_code == 200, listed.text
        assert denied.status_code == 403, denied.text

    def test_a_user_with_no_permission_is_refused(self, api):
        db, _as, _scope = api

        with TestClient(app) as client:
            template_id = _create_template(client)

        _as(_NOPERM_ID)
        with TestClient(app) as client:
            denied = client.get(f"/api/v1/dealer-kit/tag-templates/{template_id}/versions")

        assert denied.status_code == 403, denied.text
