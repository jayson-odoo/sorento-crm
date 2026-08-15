"""The token gate on the print payload route.

`test_dealer_kit_render_token.py` proves the token primitive. This proves the
ROUTE actually uses it, which is a different claim and the one that matters:
`/api/v1/public/print/{download_id}` is unauthenticated by necessity - headless
Chromium has no CRM session - and it renders a page carrying whatever prices the
snapshot says the audience may see.

So the only thing standing between a stranger and a priced catalogue is this
gate, and until now nothing tested it end to end. Every rejection answers 404,
never 401 or 403: whether a download id exists is not something an anonymous
caller gets to probe.
"""
from __future__ import annotations

import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.services.dealer_kit import render_token
from tests._pg_fixture import blank_session

_USER_ID = "6e1c8a35-2f74-5b09-a416-8d3f7b2e5c40"
_ROLE_ID = "8b4d6f92-1a37-5c85-9207-5e2c4a8f1d63"
_SORENTO = "00000000-0000-0000-0000-000000000001"


def _seed(db: Session) -> None:
    from app.models.company import Company
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    if db.query(Company).filter(Company.id == _SORENTO).first() is None:
        db.add(Company(id=_SORENTO, code="SRT", name="Sorento", is_active=True))

    db.add(
        UserRole(
            id=_ROLE_ID,
            slug="superadmin",
            name="Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
    )
    db.add(User(id=_USER_ID, email="zzt-print@test.com", name="Print", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_USER_ID, role_id=_ROLE_ID))
    for slug in ("dealer_kit.page.view", "dealer_kit.page.edit", "dealer_kit.page.publish"):
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        db.add(
            UserRolePermission(id=str(uuid.uuid4()), role_id=_ROLE_ID, permission_id=perm_id)
        )
    db.commit()


def _published_page(db: Session) -> str:
    """A page with one published version. Returns its id."""
    from app.services.dealer_kit import page_service

    stem = uuid.uuid4().hex[:6]
    page = page_service.create_page(
        db, name=f"ZZT print {stem}", slug=f"zzt-print-{stem}", user_id=_USER_ID
    )
    db.flush()
    version = page_service.save_version(
        db,
        page.id,
        doc={"sections": [{"id": "s1", "blocks": []}]},
        commit_message="ZZT print fixture",
        user_id=_USER_ID,
    )
    db.flush()
    page_service.move_label(
        db, page.id, "published", version_id=version.id, user_id=_USER_ID
    )
    db.commit()
    return page.id


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

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

        principal = {"id": _USER_ID, "email": "zzt-print@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db

        app.dependency_overrides.clear()


def _download_id(db: Session, audience: str = "staff") -> str:
    from app.services.dealer_kit import export_service

    download = export_service.request_export(
        db, page_id=_published_page(db), audience=audience, user_id=_USER_ID
    )
    db.commit()
    return download.id


def test_a_valid_token_returns_the_payload(api):
    db = api
    download_id = _download_id(db)
    client = TestClient(app)

    response = client.get(
        f"/api/v1/public/print/{download_id}",
        params={"token": render_token.issue(download_id)},
    )
    assert response.status_code == 200, response.text
    assert "doc" in response.json()


def test_no_token_is_refused(api):
    db = api
    download_id = _download_id(db)
    client = TestClient(app)

    # The token is a required query parameter, so its absence is a 422 from
    # validation - the point is that the payload is not served either way.
    response = client.get(f"/api/v1/public/print/{download_id}")
    assert response.status_code in (404, 422)
    assert "doc" not in response.text


def test_a_forged_token_is_refused(api):
    db = api
    download_id = _download_id(db)
    client = TestClient(app)

    expires_at = int(time.time()) + 600
    forged = f"{expires_at}.{'0' * 64}"
    response = client.get(
        f"/api/v1/public/print/{download_id}", params={"token": forged}
    )
    assert response.status_code == 404


def test_a_token_for_a_different_download_is_refused(api):
    """The token is bound to ONE download id. Reusing a legitimately obtained
    token against another render is the interesting attack, not forgery."""
    db = api
    mine = _download_id(db)
    someone_elses = _download_id(db)
    client = TestClient(app)

    response = client.get(
        f"/api/v1/public/print/{someone_elses}",
        params={"token": render_token.issue(mine)},
    )
    assert response.status_code == 404


def test_an_expired_token_is_refused(api):
    db = api
    download_id = _download_id(db)
    client = TestClient(app)

    stale = render_token.issue(download_id, ttl_seconds=1, now=int(time.time()) - 60)
    response = client.get(
        f"/api/v1/public/print/{download_id}", params={"token": stale}
    )
    assert response.status_code == 404


def test_an_unknown_download_looks_the_same_as_a_forged_token(api):
    """Both 404. A different answer would let a caller enumerate which download
    ids exist by watching the status code."""
    db = api
    client = TestClient(app)
    unknown = str(uuid.uuid4())

    response = client.get(
        f"/api/v1/public/print/{unknown}", params={"token": render_token.issue(unknown)}
    )
    assert response.status_code == 404
