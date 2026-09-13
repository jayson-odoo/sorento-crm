"""Review round 2 (r8): a file with no extension AND an unrecognized content
type must be refused by ``ai_extract``'s file-type check, not slip through.

``_ext()`` (``app/api/v1/public/ai_extract.py``) falls back to "" when the
filename has no dot AND the content type has no "/", and the guard
``if ext and ext not in _ALLOWED_EXTS`` is falsy for an empty string - so a
file with neither signal reaches ``AIExtractService.extract`` unchecked
instead of being refused.

Fixture pattern: ``tests/test_ai_extract_route_off_the_loop.py``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session

EXTRACT_URL = "/api/v1/public/portal/ai-extract"


@pytest.fixture
def api():
    """A portal-token-authenticated client on a blank Postgres schema."""
    from app.database import get_db

    with blank_session() as db:

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        try:
            yield db
        finally:
            app.dependency_overrides.clear()


def _contact(db):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{uuid.uuid4().hex[:8]}",
        name="ZZT-no-ext-contact",
    )
    db.add(contact)
    db.flush()
    return contact


def _token(db, contact):
    from app.models.portal import PortalToken

    token = PortalToken(
        id=str(uuid.uuid4()),
        token=f"ZZT-tok-{uuid.uuid4().hex}",
        contact_id=contact.id,
        space_id="ZZT-no-ext-space",
        expires_at=datetime.utcnow() + timedelta(days=30),
        verified_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(token)
    db.commit()
    return token


class TestNoExtensionUnsupportedContentTypeRejected:
    def test_ai_extract_rejects_file_with_no_extension(self, api, monkeypatch):
        from app.api.v1.public import ai_extract as route_module

        db = api
        contact = _contact(db)
        token = _token(db, contact)

        called = {"n": 0}

        def _spy(self, form_key, files, *, user_id=None, portal_contact_id=None):
            called["n"] += 1
            from app.services.ai_extract.extract_service import ExtractResult

            return ExtractResult(values={})

        monkeypatch.setattr(route_module.AIExtractService, "extract", _spy)

        with TestClient(app) as c:
            res = c.post(
                EXTRACT_URL,
                data={"form_key": "portal.complaint"},
                # No dot in the filename, and a content type with no "/" -
                # `_ext()` returns "" for both signals, and the guard's
                # `if ext and ...` never fires for an empty string.
                files={"files": ("attachment", b"unrecognized bytes", "notarealtype")},
                headers={"X-Portal-Token": token.token},
            )

        assert res.status_code in (400, 422), res.text
        assert called["n"] == 0, (
            "AIExtractService.extract ran on a file with no validated "
            "extension - the type guard let it through"
        )
