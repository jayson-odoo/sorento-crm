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


# --------------------------------------------------------------------------- cleanup (crew ruling (a))
# After a Replace commits, the old key's original + thumb + medium are deleted by the existing
# delete_storage_files worker job (never in the request); a hard delete removes every rendition
# key too. A failing delete is retried and logged and never blocks the Replace.


@pytest.fixture
def inline_jobs(monkeypatch):
    """enqueue_job runs the job at once and records it, as the worker would."""
    from app.services import queue_service

    jobs = []

    def run(func, *args, **kwargs):
        jobs.append((func.__name__, args))
        return func(*args)

    monkeypatch.setattr(queue_service, "enqueue_job", run)
    return jobs


def test_replace_deletes_the_old_original_and_its_renditions_in_the_worker(env, inline_jobs):
    client, store = env
    old = _upload(client, _png((200, 0, 0))).json()
    old_key = _key(old["file_path"])
    assert inline_jobs == []  # a first upload deletes nothing

    new = _upload(client, _png((0, 0, 200)), on_conflict="replace").json()
    new_key = _key(new["file_path"])

    assert [name for name, _ in inline_jobs] == ["delete_storage_files"]
    for suffix in ("", ".thumb.jpg", ".medium.jpg"):
        assert old_key + suffix not in store.objects
        assert new_key + suffix in store.objects


def test_replacing_with_the_same_bytes_deletes_nothing_it_still_points_at(env, inline_jobs):
    client, store = env
    content = _png((0, 150, 0))
    _upload(client, _png((9, 9, 9)))
    first = _upload(client, content, on_conflict="replace").json()
    inline_jobs.clear()
    again = _upload(client, content, on_conflict="replace").json()
    key = _key(again["file_path"])
    assert key == _key(first["file_path"])
    assert inline_jobs == []
    for suffix in ("", ".thumb.jpg", ".medium.jpg"):
        assert key + suffix in store.objects


def test_a_cleanup_that_cannot_be_queued_never_blocks_the_replace(env, monkeypatch, caplog):
    from app.services import queue_service

    def refuse(*_a, **_k):
        raise ConnectionError("redis down")

    monkeypatch.setattr(queue_service, "enqueue_job", refuse)
    client, store = env
    old_key = _key(_upload(client, _png((1, 2, 3))).json()["file_path"])
    with caplog.at_level("WARNING"):
        replaced = _upload(client, _png((3, 2, 1)), on_conflict="replace")
    assert replaced.status_code == 201, replaced.text
    assert old_key in store.objects  # left for later, and said so
    assert any(old_key in record.getMessage() for record in caplog.records)


def test_delete_storage_files_removes_every_rendition_of_an_original(monkeypatch):
    from app.services import storage_router
    from app.tasks.s3_tasks import delete_storage_files

    store = MemoryStore()
    for key in ("p/a.png", "p/a.png.thumb.jpg", "p/a.png.medium.jpg", "p/b.png.thumb.jpg"):
        store.objects[key] = b"x"
    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: store)

    delete_storage_files([("r2", "https://cdn.test/p/a.png"), ("r2", "p/b.png.thumb.jpg")])
    assert store.objects == {}


def test_a_failing_delete_is_retried_then_logged_and_the_rest_still_go(monkeypatch, caplog):
    from app.services import storage_router
    from app.tasks import s3_tasks

    class Flaky(MemoryStore):
        def __init__(self):
            super().__init__()
            self.attempts = {}

        def delete_file(self, key):
            self.attempts[key] = self.attempts.get(key, 0) + 1
            if key.startswith("p/stuck") or (key == "p/flaky.png" and self.attempts[key] < 3):
                raise RuntimeError("bucket busy")
            return super().delete_file(key)

    store = Flaky()
    for key in ("p/flaky.png", "p/stuck.png", "p/ok.png"):
        store.objects[key] = b"x"
    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: store)
    monkeypatch.setattr(s3_tasks, "_RETRY_SLEEP_SECONDS", 0)

    with caplog.at_level("WARNING"):
        result = s3_tasks.delete_storage_files([("r2", "p/flaky.png"), ("r2", "p/stuck.png"), ("r2", "p/ok.png")])

    assert "p/flaky.png" not in store.objects and "p/ok.png" not in store.objects  # retried, deleted
    assert store.attempts["p/stuck.png"] == s3_tasks._DELETE_ATTEMPTS
    assert result["failed"] >= 1
    assert any("p/stuck.png" in record.getMessage() for record in caplog.records)


def test_hard_delete_of_an_attachment_removes_its_renditions(monkeypatch, inline_jobs):
    import uuid

    from app.models.resources import Attachment
    from app.services import storage_router
    from app.services.resources_service import AttachmentService

    store = MemoryStore()
    key = f"general/{uuid.uuid4()}/zz.png"
    for suffix in ("", ".thumb.jpg", ".medium.jpg"):
        store.objects[key + suffix] = b"x"
    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: store)
    with blank_session() as db:
        row = Attachment(
            id=str(uuid.uuid4()), original_filename="zz.png", stored_filename="zz.png",
            file_path=f"https://cdn.test/{key}", thumbnail_path=f"https://cdn.test/{key}.thumb.jpg",
            mime_type="image/png", storage_provider="r2",
        )
        db.add(row)
        db.commit()
        AttachmentService(db).delete_attachment(row.id, deleted_by=None)
    assert store.objects == {}
