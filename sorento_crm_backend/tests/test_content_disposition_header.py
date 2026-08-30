"""The download header must survive a non-ASCII filename.

``GET /resource-management/attachments/{id}/download`` used to build
``Content-Disposition: attachment; filename="<raw name>"``. HTTP header values
are latin-1, so a Chinese filename such as ``2026-7-27 库存明细.xlsx`` raised
``'latin-1' codec can't encode characters in position 33-36`` inside the ASGI
layer and the user saw a 500 on a file that had uploaded perfectly well.

RFC 6266 / RFC 5987 answer this with two parameters on one header: a plain
``filename`` an old client can read, and a ``filename*=UTF-8''...`` a modern one
prefers. One helper emits both, and every download route in the backend goes
through it, so no export can be crashed by the name of its own file.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves circular-import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.resources import Attachment
from app.utils.http import content_disposition
from tests._pg_fixture import blank_session


# --------------------------------------------------------------------------
# The helper
# --------------------------------------------------------------------------


def test_an_ascii_name_is_carried_through_unchanged():
    header = content_disposition("stock-report.xlsx")
    assert header == (
        "attachment; filename=\"stock-report.xlsx\"; "
        "filename*=UTF-8''stock-report.xlsx"
    )


def test_a_non_ascii_name_yields_both_parameters():
    header = content_disposition("2026-7-27 库存明细.xlsx")
    assert 'filename="2026-7-27 ____.xlsx"' in header
    assert "filename*=UTF-8''2026-7-27%20%E5%BA%93%E5%AD%98%E6%98%8E%E7%BB%86.xlsx" in header


def test_a_non_ascii_name_encodes_as_a_latin_1_header_value():
    """The exact failure this exists to prevent - the ASGI server encodes header
    values as latin-1, and the raw name cannot."""
    content_disposition("2026-7-27 库存明细.xlsx").encode("latin-1")


def test_a_quote_in_the_name_is_escaped_not_left_to_close_the_value():
    header = content_disposition('say "hi".pdf')
    assert 'filename="say \\"hi\\".pdf"' in header
    assert "filename*=UTF-8''say%20%22hi%22.pdf" in header


def test_a_backslash_in_the_name_is_escaped():
    header = content_disposition("a\\b.pdf")
    assert 'filename="a\\\\b.pdf"' in header


def test_a_newline_in_the_name_cannot_inject_a_second_header():
    header = content_disposition("evil\r\nX-Bad: 1.pdf")
    assert "\r" not in header and "\n" not in header


def test_an_empty_name_falls_back_to_a_usable_one():
    assert content_disposition("") == (
        "attachment; filename=\"download\"; filename*=UTF-8''download"
    )


def test_inline_asks_the_browser_to_render_rather_than_save():
    assert content_disposition("preview.pdf", inline=True).startswith("inline; ")


# --------------------------------------------------------------------------
# The route the bug was reported against
# --------------------------------------------------------------------------

FILE_BYTES = b"attachment-bytes"
_USER_ID = "130c548f-048f-53b2-97a6-3a54676bea77"
_ROLE_ID = "7c50d6db-8dce-555a-85a2-86cf7756f33f"


class _FakeStorageBackend:
    def download_file(self, key: str) -> bytes:
        return FILE_BYTES


def _seed_user(db: Session) -> None:
    from app.models.user import User, UserRole, UserRoleAssignment

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
    db.flush()
    db.add(User(id=_USER_ID, email="u1@test.com", name="U1", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_USER_ID, role_id=_ROLE_ID))
    db.commit()


@pytest.fixture
def client(monkeypatch):
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    import app.services.storage_router as storage_router

    with blank_session() as db:
        _seed_user(db)
        monkeypatch.setattr(
            storage_router, "get_backend", lambda provider=None: _FakeStorageBackend()
        )

        def _override_get_db():
            yield db

        def _override_current_user():
            return {"id": _USER_ID, "email": "u1@test.com"}

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_current_user_or_api_key] = _override_current_user
        try:
            with TestClient(app) as c:
                yield c, db
        finally:
            app.dependency_overrides.clear()


def _attachment(db: Session, filename: str) -> Attachment:
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"https://cdn.test/resource/{uuid.uuid4().hex}/{filename}",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_size_bytes=len(FILE_BYTES),
    )
    db.add(att)
    db.commit()
    return att


def test_downloading_a_chinese_filename_is_200_and_names_the_file(client):
    c, db = client
    att = _attachment(db, "库存明细.xlsx")

    res = c.get(f"/api/v1/resource-management/attachments/{att.id}/download")

    assert res.status_code == 200, res.text
    assert res.content == FILE_BYTES
    disposition = res.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="____.xlsx"')
    assert "filename*=UTF-8''%E5%BA%93%E5%AD%98%E6%98%8E%E7%BB%86.xlsx" in disposition
