"""GET /api/v1/public/dealer-kit/fonts/{asset_id} - font bytes, same-origin.

Written BEFORE the route (price-tag-r4 S1). A signed CDN URL answers 200 with
no CORS header on some hosts, so `FontFace.load()` in the browser rejects it
and both the editor and the print page silently fall back to the system sans
(measured on origin/main dbba826bf, see PLAN-price-tag-r4.md). Proxying the
bytes through this same-origin route sidesteps the CORS gap entirely.

No auth: an asset id is a UUID nobody can enumerate, and a font is brand
artwork the page already renders unauthenticated. The route answers a
``kind='font'`` row only - any other kind, or an id that does not exist, is a
404 - so it cannot be used to read a brand's other artwork.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.base import company_scope
from tests._fake_storage import FakeStorage
from tests._pg_fixture import pg_session, unique_code

_SORENTO = "00000000-0000-0000-0000-000000000001"


def _seed_asset(db, *, kind: str, filename: str, mime: str, content: bytes) -> tuple[str, str]:
    """A dealer_kit.asset row plus its attachment, stored bytes in a fake backend."""
    from app.models.dealer_kit import Asset
    from app.models.resources import Attachment

    attachment_id = str(uuid.uuid4())
    key = f"dealer_kit_asset/{attachment_id}/{filename}"

    with company_scope(db, frozenset({_SORENTO})):
        attachment = Attachment(
            id=attachment_id,
            original_filename=filename,
            stored_filename=filename,
            file_path=f"https://cdn.test/{key}",
            file_size_bytes=len(content),
            mime_type=mime,
            entity_type="dealer_kit_asset",
            uploader_kind="system",
            storage_provider="s3",
            company_id=_SORENTO,
        )
        db.add(attachment)
        db.flush()

        asset = Asset(
            id=str(uuid.uuid4()),
            attachment_id=attachment.id,
            name=unique_code("font"),
            kind=kind,
        )
        db.add(asset)
        db.flush()

    db.commit()
    return asset.id, key


@pytest.fixture
def client_and_db(monkeypatch):
    from app.api.v1.public import dealer_kit_fonts
    from app.database import get_db

    with pg_session() as db:
        storage = FakeStorage()
        monkeypatch.setattr(dealer_kit_fonts, "get_backend", lambda provider: storage)

        def _override():
            yield db

        app.dependency_overrides[get_db] = _override
        yield TestClient(app), db, storage
        app.dependency_overrides.clear()


def test_a_font_asset_returns_its_bytes_and_content_type(client_and_db):
    client, db, storage = client_and_db
    asset_id, key = _seed_asset(
        db, kind="font", filename="ZZTBrand.ttf", mime="font/ttf", content=b"zzt ttf bytes"
    )
    storage.objects[key] = (b"zzt ttf bytes", "font/ttf")

    response = client.get(f"/api/v1/public/dealer-kit/fonts/{asset_id}")

    assert response.status_code == 200, response.text
    assert response.content == b"zzt ttf bytes"
    assert response.headers["content-type"].startswith("font/ttf")
    assert response.headers["cache-control"] == "public, max-age=86400"
    # The route hands back bytes an anonymous caller uploaded and named. Without
    # this, a browser is free to sniff a font file as something executable.
    assert response.headers["x-content-type-options"] == "nosniff"


def test_a_woff2_font_keeps_its_own_content_type(client_and_db):
    client, db, storage = client_and_db
    asset_id, key = _seed_asset(
        db, kind="font", filename="ZZTBrand.woff2", mime="font/woff2", content=b"zzt woff2 bytes"
    )
    storage.objects[key] = (b"zzt woff2 bytes", "font/woff2")

    response = client.get(f"/api/v1/public/dealer-kit/fonts/{asset_id}")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("font/woff2")


def test_a_non_font_asset_is_refused(client_and_db):
    client, db, storage = client_and_db
    asset_id, key = _seed_asset(
        db, kind="badge", filename="zzt-badge.png", mime="image/png", content=b"zzt png bytes"
    )
    storage.objects[key] = (b"zzt png bytes", "image/png")

    response = client.get(f"/api/v1/public/dealer-kit/fonts/{asset_id}")

    assert response.status_code == 404, response.text


def test_an_unknown_asset_id_is_refused(client_and_db):
    client, _db, _storage = client_and_db

    response = client.get(f"/api/v1/public/dealer-kit/fonts/{uuid.uuid4()}")

    assert response.status_code == 404, response.text


def test_a_malformed_asset_id_is_refused_not_a_500(client_and_db):
    client, _db, _storage = client_and_db

    response = client.get("/api/v1/public/dealer-kit/fonts/not-a-uuid")

    assert response.status_code == 404, response.text


def test_a_storage_outage_answers_502_not_a_relabeled_404(client_and_db):
    client, db, storage = client_and_db
    asset_id, _key = _seed_asset(
        db, kind="font", filename="ZZTBrand.ttf", mime="font/ttf", content=b"zzt ttf bytes"
    )
    storage.downloading_fails = True

    response = client.get(f"/api/v1/public/dealer-kit/fonts/{asset_id}")

    assert response.status_code == 502, response.text
