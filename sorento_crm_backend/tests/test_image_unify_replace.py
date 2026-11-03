"""IMAGE-UNIFY P1: Replace never reuses a storage key (crew ruling (b) on #2133).

Renditions are cached for a year as immutable, so an original must never be overwritten under
the key it had: Files "Replace" writes the new bytes, and their thumb and medium, under NEW keys
and points the attachment row at them. The old objects stay (a cleanup job removes unreferenced
keys later; nothing is deleted in the request).

Real app and route on a blank schema; storage is an in-memory fake.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

import app.database as app_database
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.main import app
from tests._pg_fixture import blank_session
from tests.test_list_api_perms import _user

ATT = "/api/v1/resource-management/attachments"


class MemoryStore:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.cache_control: dict[str, str] = {}

    def upload_file(self, file_content, file_path, content_type=None, signed_url_expires_in=3600, cache_control=None):
        self.objects[file_path] = file_content
        if cache_control:
            self.cache_control[file_path] = cache_control
        return file_path, f"https://signed.test/{file_path}"

    def get_signed_url(self, key, expires_in=3600):
        return f"https://signed.test/{key}"

    def file_exists(self, key):
        return key in self.objects

    def download_file(self, key):
        return self.objects[key]

    def delete_file(self, key):
        self.objects.pop(key, None)
        return True


def _png(colour) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (1500, 1000), colour).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def env(monkeypatch):
    from app.services import storage_router

    store = MemoryStore()
    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: store)
    monkeypatch.setattr(storage_router, "default_provider", lambda: "r2")
    monkeypatch.setattr(storage_router, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}")
    with blank_session() as db:
        import uuid

        from app.models.resources import AttachmentType

        user = _user(db, "uploader", "zz_uploader", ["resource.attachments.upload", "resource.attachments.view"])
        kind = AttachmentType(
            id=str(uuid.uuid4()),
            type_name=f"zz-photo-{uuid.uuid4().hex[:6]}",
            allowed_extensions=".png,.jpg",
            max_file_size_mb=10,
            triggers_n8n_webhook=False,
        )
        db.add(kind)
        db.commit()
        client = TestClient(app)
        client.attachment_type_id = kind.id

        def _override_db():
            yield db

        app.dependency_overrides[app_database.get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_user_or_api_key] = lambda: user
        try:
            yield client, store
        finally:
            app.dependency_overrides.clear()


def _upload(client, content: bytes, **form):
    return client.post(
        f"{ATT}/",
        files={"file": ("zz-replace.png", content, "image/png")},
        data={"attachment_type_id": client.attachment_type_id, **form},
    )


def _key(url: str) -> str:
    return url.split("https://cdn.test/", 1)[-1].split("https://signed.test/", 1)[-1]


def test_replace_writes_new_keys_and_the_new_bytes_are_served_on_a_different_url(env):
    client, store = env
    old_bytes, new_bytes = _png((200, 0, 0)), _png((0, 0, 200))

    first = _upload(client, old_bytes)
    assert first.status_code == 201, first.text
    first_body = first.json()
    old_key = _key(first_body["file_path"])
    assert store.objects[old_key] == old_bytes

    second = _upload(client, new_bytes, on_conflict="replace")
    assert second.status_code == 201, second.text
    body = second.json()
    assert body["id"] == first_body["id"]  # same row, every link kept
    new_key = _key(body["file_path"])

    # A different key, and so a different URL, for the original ...
    assert new_key != old_key
    assert body["file_path"] != first_body["file_path"]
    assert store.objects[new_key] == new_bytes
    # ... and for both renditions, each immutable under its own key.
    for suffix in (".thumb.jpg", ".medium.jpg"):
        assert old_key + suffix in store.objects
        assert new_key + suffix in store.objects
        assert store.objects[old_key + suffix] != store.objects[new_key + suffix]
        assert store.cache_control[new_key + suffix] == "public, max-age=31536000, immutable"
    # Nothing is deleted in the request.
    assert store.objects[old_key] == old_bytes

    # Fetching the attachment now signs the new key.
    fetched = client.get(f"{ATT}/{body['id']}")
    assert fetched.status_code == 200, fetched.text
    assert _key(fetched.json()["file_path"]) == new_key


def test_replacing_with_the_same_bytes_again_is_idempotent(env):
    client, store = env
    content = _png((0, 150, 0))
    _upload(client, _png((9, 9, 9)))
    first = _upload(client, content, on_conflict="replace").json()
    again = _upload(client, content, on_conflict="replace").json()
    # Same bytes, same key: the key is derived from the content, so nothing stale can be served.
    assert again["file_path"] == first["file_path"]


def test_replace_storage_key_shape():
    from app.services.storage_router import replace_storage_key

    key = replace_storage_key("general", "A1", "x.png", "ab" * 32)
    assert key == "general/A1/v-abababababababab/x.png"


def test_cmyk_fix_script_writes_a_new_key_and_fresh_renditions(monkeypatch):
    """The CMYK -> RGB script used to overwrite originals in place; now it never does."""
    import importlib.util
    import os
    from types import SimpleNamespace

    from PIL import Image

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts", "backfill_cmyk_attachments_to_rgb.py")
    spec = importlib.util.spec_from_file_location("cmyk_fix", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    buffer = io.BytesIO()
    Image.new("CMYK", (900, 600), (0, 200, 200, 0)).save(buffer, format="JPEG")
    old_key = "general/A1/photo.jpg"
    store = MemoryStore()
    store.objects[old_key] = buffer.getvalue()
    monkeypatch.setattr(script, "get_backend", lambda provider: store)
    monkeypatch.setattr(script, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}")
    from app.services import storage_router

    monkeypatch.setattr(storage_router, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}")

    class Db:
        def add(self, row):
            pass

        def commit(self):
            pass

    row = SimpleNamespace(
        id="A1", storage_provider="r2", file_path=f"https://cdn.test/{old_key}",
        original_filename="photo.jpg", mime_type="image/jpeg", entity_type="general",
        thumbnail_path=None, file_hash=None, file_size_bytes=None,
    )
    assert script._process_one(Db(), row, dry_run=False) == "converted"

    new_key = _key(row.file_path)
    assert new_key != old_key and new_key.startswith("general/A1/v-")
    assert store.objects[old_key] == buffer.getvalue()  # the CMYK original is kept
    with Image.open(io.BytesIO(store.objects[new_key])) as im:
        assert im.mode == "RGB"
    assert _key(row.thumbnail_path) == new_key + ".thumb.jpg"
    assert new_key + ".medium.jpg" in store.objects
