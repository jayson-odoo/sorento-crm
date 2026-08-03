"""Edition routes, and the permission split that is the point of them (S2.5.2).

The real subject here is WHO may do what. Three rights, deliberately separate:

* ``page.edit``        - Designer: start, submit, reopen
* ``edition.approve``  - Approver: approve, reject
* ``page.publish``     - move the published label, i.e. mark it done

A Designer holding only ``page.edit`` must get a 403 on approve, including on
their own Edition (AC-L3), and the fixture below gives each user exactly one of
the three so a widened dependency shows up as a test that suddenly passes for
the wrong person.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.dealer_kit import Page, PageVersion
from tests._pg_fixture import blank_session, unique_code

_SORENTO = "00000000-0000-0000-0000-000000000001"

_DESIGNER_ID = "2f7c4a19-8e35-5d62-b401-7a9c3e5f1d84"
_DESIGNER_ROLE = "3a8d5b27-9f16-5c74-8e20-1b6d4a9c2e35"
_APPROVER_ID = "5c9e2d38-4a71-5b06-9f13-8e2a7c4b1d69"
_APPROVER_ROLE = "8b1f6c94-2d57-5a83-b619-4c7e2a9d5f30"
_PUBLISHER_ID = "7d2a8e51-6b34-5f92-a075-3c8b1e6d4a27"
_PUBLISHER_ROLE = "9e4c1a76-5d28-5b31-8f60-2a7d9c3e5b18"

_MIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "318_dealer_kit_edition.py"
)
_spec = importlib.util.spec_from_file_location("mig_318_edition_routes", _MIG_PATH)
mig318 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mig318)

_ROLES = (
    (_DESIGNER_ROLE, "zzt_ed_designer", _DESIGNER_ID, ("dealer_kit.page.view", "dealer_kit.page.edit")),
    (_APPROVER_ROLE, "zzt_ed_approver", _APPROVER_ID, ("dealer_kit.page.view", "dealer_kit.edition.approve")),
    (_PUBLISHER_ROLE, "zzt_ed_publisher", _PUBLISHER_ID, ("dealer_kit.page.view", "dealer_kit.page.publish")),
)

_ALL_SLUGS = (
    "dealer_kit.page.view",
    "dealer_kit.page.edit",
    "dealer_kit.page.publish",
    "dealer_kit.edition.approve",
)


def _seed_roles(db) -> None:
    """One user per right. Nobody holds two, so a leak is visible."""
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    perm_ids: dict[str, str] = {}
    for slug in _ALL_SLUGS:
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        perm_ids[slug] = perm_id
    db.flush()

    for role_id, slug, user_id, granted in _ROLES:
        db.add(
            UserRole(
                id=role_id,
                slug=slug,
                name=slug,
                description="",
                is_protected=False,
                is_default=False,
            )
        )
        db.add(
            User(id=user_id, email=f"{slug}@test.com", name=slug, status="ACTIVE")
        )
        db.flush()
        db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
        for granted_slug in granted:
            db.add(
                UserRolePermission(
                    id=str(uuid.uuid4()),
                    role_id=role_id,
                    permission_id=perm_ids[granted_slug],
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

    with blank_session() as db:
        mig318._seed_graph(db.connection())
        db.flush()
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

        _as(_DESIGNER_ID)
        yield db, _as, _in_company

        app.dependency_overrides.clear()


def _page(db) -> Page:
    page = Page(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Ed Page"),
        slug=unique_code("zzt-edr").lower(),
    )
    db.add(page)
    db.flush()
    db.add(
        PageVersion(
            id=str(uuid.uuid4()),
            page_id=page.id,
            version=1,
            doc={"sections": []},
            created_by=_DESIGNER_ID,
        )
    )
    db.commit()
    return page


def _create(client: TestClient, page: Page):
    return client.post(
        "/api/v1/dealer-kit/editions",
        json={"pageId": page.id, "name": unique_code("ZZT Edition")},
    )


class TestTheDesignersHalf:
    def test_starting_an_edition_returns_it_at_draft(self, api) -> None:
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            created = _create(client, page)

        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "draft"
        assert body["statusLabel"] == "Draft"
        assert body["pageName"] == page.name

    def test_a_second_open_edition_is_a_409_that_says_what_to_do(self, api) -> None:
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            _create(client, page)
            again = _create(client, page)

        assert again.status_code == 409, again.text
        assert "already has an Edition in progress" in again.text

    def test_the_designer_can_submit(self, api) -> None:
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]
            submitted = client.post(f"/api/v1/dealer-kit/editions/{edition_id}/submit")

        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["status"] == "pending_approval"


class TestADesignerCannotApproveTheirOwn:
    """AC-L3. The permission is not implied by page.edit, so the answer is 403
    even when the Designer is the person who submitted it."""

    def test_approving_is_403_for_the_designer(self, api) -> None:
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]
            client.post(f"/api/v1/dealer-kit/editions/{edition_id}/submit")
            denied = client.post(f"/api/v1/dealer-kit/editions/{edition_id}/approve")

        assert denied.status_code == 403, denied.text

    def test_rejecting_is_403_for_the_designer(self, api) -> None:
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]
            client.post(f"/api/v1/dealer-kit/editions/{edition_id}/submit")
            denied = client.post(
                f"/api/v1/dealer-kit/editions/{edition_id}/reject",
                json={"reason": "I changed my mind about my own work"},
            )

        assert denied.status_code == 403, denied.text

    def test_publishing_is_403_for_the_designer(self, api) -> None:
        """page.edit does not carry the right to move the published label."""
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]
            denied = client.post(f"/api/v1/dealer-kit/editions/{edition_id}/publish")

        assert denied.status_code == 403, denied.text


class TestTheApproversHalf:
    def test_the_approver_approves_and_publishes_nothing(self, api) -> None:
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]
            client.post(f"/api/v1/dealer-kit/editions/{edition_id}/submit")
            _as(_APPROVER_ID)
            approved = client.post(f"/api/v1/dealer-kit/editions/{edition_id}/approve")

        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["status"] == "approved"
        assert body["approvedVersionId"]
        assert body["doneVersionId"] is None

    def test_a_rejection_needs_a_reason(self, api) -> None:
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]
            client.post(f"/api/v1/dealer-kit/editions/{edition_id}/submit")
            _as(_APPROVER_ID)
            blank = client.post(
                f"/api/v1/dealer-kit/editions/{edition_id}/reject", json={"reason": ""}
            )

        assert blank.status_code == 422, blank.text

    def test_the_reason_reaches_the_designer(self, api) -> None:
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]
            client.post(f"/api/v1/dealer-kit/editions/{edition_id}/submit")
            _as(_APPROVER_ID)
            client.post(
                f"/api/v1/dealer-kit/editions/{edition_id}/reject",
                json={"reason": "The bathtub prices are last season."},
            )
            _as(_DESIGNER_ID)
            read_back = client.get(f"/api/v1/dealer-kit/editions/{edition_id}")

        assert read_back.json()["rejectionReason"] == "The bathtub prices are last season."

    def test_the_approver_cannot_submit(self, api) -> None:
        """The split runs both ways: approving is not editing."""
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]
            _as(_APPROVER_ID)
            denied = client.post(f"/api/v1/dealer-kit/editions/{edition_id}/submit")

        assert denied.status_code == 403, denied.text


class TestPublishing:
    def test_only_the_publisher_finishes_it(self, api) -> None:
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]
            client.post(f"/api/v1/dealer-kit/editions/{edition_id}/submit")
            _as(_APPROVER_ID)
            client.post(f"/api/v1/dealer-kit/editions/{edition_id}/approve")
            _as(_PUBLISHER_ID)
            published = client.post(f"/api/v1/dealer-kit/editions/{edition_id}/publish")

        assert published.status_code == 200, published.text
        body = published.json()
        assert body["status"] == "done"
        assert body["doneVersionId"]


class TestScope:
    def test_another_companys_edition_is_a_404_never_a_403(self, api) -> None:
        """403 confirms the id exists, which turns a guess into an enumeration."""
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]

        _scope(str(uuid.uuid4()))

        with TestClient(app) as client:
            got = client.get(f"/api/v1/dealer-kit/editions/{edition_id}")

        assert got.status_code == 404, got.text

    def test_no_uuid_reaches_the_client_as_a_status(self, api) -> None:
        """The status travels as its KEY. A status id is a uuid and no uuid
        belongs in the UI."""
        db, _as, _scope = api
        page = _page(db)

        with TestClient(app) as client:
            body = _create(client, page).json()

        assert body["status"] == "draft"
        assert "statusId" not in body
