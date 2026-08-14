"""Edition transitions are audited (AC-L11).

Reuses the permission-split fixture from ``test_dealer_kit_edition_routes.py``
(one user per right, so a leaked permission would also leak into who an audit
row blames) with one addition: the ``get_current_user`` override here also
calls ``set_audit_context``, because in production that happens inside the
REAL (``async def``) dependency and the test replaces it wholesale. Without
this, every auto-written audit row in this suite would attribute to nobody,
which is not what production does - see ``app.dependencies.get_current_user``.

Three things are pinned:

* A transition (draft -> pending_approval) writes one audit row naming the
  Edition, with the status move in old/new values, blamed on the acting
  Designer.
* An approve (pending_approval -> approved) writes its OWN row, blamed on the
  Approver - a different actor from the one above.
* A no-op write (same value re-assigned) writes NOTHING. The audit listener's
  own history-based diffing already guarantees this for every tracked model;
  pinned here so a future ``__audit_columns__`` change on Edition can't
  silently defeat it.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.audit import AuditLog
from app.models.dealer_kit import Edition, Page, PageVersion
from tests._pg_fixture import blank_session, unique_code

_SORENTO = "00000000-0000-0000-0000-000000000001"

_DESIGNER_ID = "2f7c4a19-8e35-5d62-b401-7a9c3e5f1d84"
_DESIGNER_ROLE = "3a8d5b27-9f16-5c74-8e20-1b6d4a9c2e35"
_APPROVER_ID = "5c9e2d38-4a71-5b06-9f13-8e2a7c4b1d69"
_APPROVER_ROLE = "8b1f6c94-2d57-5a83-b619-4c7e2a9d5f30"

_MIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "318_dealer_kit_edition.py"
)
_spec = importlib.util.spec_from_file_location("mig_318_edition_audit", _MIG_PATH)
mig318 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mig318)

_ROLES = (
    (_DESIGNER_ROLE, "zzt_ed_audit_designer", _DESIGNER_ID, ("dealer_kit.page.view", "dealer_kit.page.edit")),
    (_APPROVER_ROLE, "zzt_ed_audit_approver", _APPROVER_ID, ("dealer_kit.page.view", "dealer_kit.edition.approve")),
)

_ALL_SLUGS = (
    "dealer_kit.page.view",
    "dealer_kit.page.edit",
    "dealer_kit.edition.approve",
)


def _seed_roles(db) -> None:
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
    from app.audit_context import set_audit_context
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

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}

            # Mirrors the REAL get_current_user (app/dependencies.py): it is an
            # `async def`, so `set_audit_context` set inside it is visible to
            # later code in this same request (no threadpool hop for async
            # dependencies) - see the module docstring above. The plain-lambda
            # override the route-permission tests use skips this entirely,
            # which is fine there (they don't assert on audit rows) and wrong
            # here.
            async def _override():
                set_audit_context(user_id, "127.0.0.1")
                return principal

            app.dependency_overrides[get_current_user] = _override
            app.dependency_overrides[get_current_user_or_api_key] = _override

        _as(_DESIGNER_ID)
        yield db, _as

        app.dependency_overrides.clear()


def _page(db) -> Page:
    page = Page(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Ed Audit Page"),
        slug=unique_code("zzt-eda").lower(),
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


def _rows_for(db, edition_id: str) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == edition_id)
        .order_by(AuditLog.changed_at.asc())
        .all()
    )


class TestSubmitIsAudited:
    def test_draft_to_pending_approval_writes_a_row_naming_the_status_move(self, api) -> None:
        db, _as = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]
            submitted = client.post(f"/api/v1/dealer-kit/editions/{edition_id}/submit")

        assert submitted.status_code == 200, submitted.text

        # The CREATE row from `create_edition` plus the UPDATE row from `submit`.
        rows = _rows_for(db, edition_id)
        update_rows = [r for r in rows if r.action == "UPDATE"]
        assert len(update_rows) == 1, [r.action for r in rows]
        row = update_rows[0]

        assert row.entity_type == "dealer_kit_edition"
        assert row.old_values["status_key"] == "draft"
        assert row.new_values["status_key"] == "pending_approval"
        assert row.user_id == _DESIGNER_ID


class TestApproveIsAuditedSeparately:
    def test_approve_writes_its_own_row_blamed_on_the_approver(self, api) -> None:
        db, _as = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]
            client.post(f"/api/v1/dealer-kit/editions/{edition_id}/submit")
            _as(_APPROVER_ID)
            approved = client.post(f"/api/v1/dealer-kit/editions/{edition_id}/approve")

        assert approved.status_code == 200, approved.text

        rows = _rows_for(db, edition_id)
        update_rows = [r for r in rows if r.action == "UPDATE"]
        assert len(update_rows) == 2, [r.action for r in rows]

        submit_row, approve_row = update_rows
        assert submit_row.user_id == _DESIGNER_ID
        assert approve_row.user_id == _APPROVER_ID
        assert approve_row.old_values["status_key"] == "pending_approval"
        assert approve_row.new_values["status_key"] == "approved"
        # What was approved, not just that something was.
        assert approve_row.new_values["approved_by"] == _APPROVER_ID
        assert approve_row.new_values["approved_version_id"]


class TestNoOpWritesNothing:
    def test_reassigning_the_same_value_writes_no_audit_row(self, api) -> None:
        db, _as = api
        page = _page(db)

        with TestClient(app) as client:
            edition_id = _create(client, page).json()["id"]

        before = len(_rows_for(db, edition_id))

        edition = db.query(Edition).filter(Edition.id == edition_id).one()
        edition.name = edition.name  # identical value, no real change
        db.commit()

        after = _rows_for(db, edition_id)
        assert len(after) == before, [(r.action, r.old_values, r.new_values) for r in after]
