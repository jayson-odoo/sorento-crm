"""Shared seeds and fakes for the panel attachment tests (not a test module).

Used by test_panel_upload.py, test_panel_send_files.py and test_panel_purge.py. Postgres only, on the
blank schema of `session_factory`; every row is seeded by the test.

Assumption the coder must honour: storage is reached through `app.services.storage_router.get_backend`
and `default_provider`, looked up at CALL time (as `create_response_attachment` does), because that is
the seam these fakes replace.
"""
from __future__ import annotations

import io
import uuid
import zipfile
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  isort:skip
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app

UPLOAD_URL = "/api/v1/system/ai-assistant/attachments"
CHAT_URL = "/api/v1/system/ai-assistant/chat"
GREETING_URL = "/api/v1/system/ai-assistant/greeting"
DRAFT = "ai_assistant_draft"
CONVERSATION = "ai_assistant_conversation"


class MemoryStore:
    """A storage backend in a dict that records what was written and deleted."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def upload_file(self, file_content, file_path, content_type=None, signed_url_expires_in=3600, cache_control=None):
        self.objects[file_path] = file_content
        return file_path, f"https://signed.test/{file_path}"

    def get_signed_url(self, key, expires_in=3600):
        return f"https://signed.test/{key}"

    def file_exists(self, key):
        return key in self.objects

    def download_file(self, key):
        return self.objects[key]

    def delete_file(self, key):
        self.deleted.append(key)
        self.objects.pop(key, None)
        return True


@pytest.fixture()
def store(monkeypatch) -> MemoryStore:
    from app.services import storage_router

    fake = MemoryStore()
    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: fake)
    monkeypatch.setattr(storage_router, "default_provider", lambda: "s3")
    monkeypatch.setattr(storage_router, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}")
    monkeypatch.setattr(
        storage_router, "resolve_signed_url", lambda file_path, provider=None, **kw: f"https://signed.test/{file_path}"
    )
    return fake


def seed_type(session_factory):
    """The `ai_assistant_attachment` type, as the migration seeds it (the blank schema runs no migration)."""
    from app.services.chatbot.panel_files import ensure_attachment_type

    db = session_factory()
    row = ensure_attachment_type(db)
    db.commit()
    return row


def make_client(session_factory, who) -> TestClient:
    def _db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    act_as(who)
    return TestClient(app, raise_server_exceptions=False)


def act_as(who) -> None:
    user = {"id": who.user_id, "name": "ZZT Panel Staff"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user


@pytest.fixture()
def panel(session_factory, staff, grants, store):
    """`(client, staff)` with the attachment type seeded, storage faked and the caller allowed to chat."""
    seed_type(session_factory)
    client = make_client(session_factory, staff)
    try:
        yield SimpleNamespace(client=client, staff=staff, grants=grants, store=store, factory=session_factory)
    finally:
        app.dependency_overrides.clear()


def upload(client, name: str, data: bytes, content_type: str = "application/octet-stream"):
    return client.post(UPLOAD_URL, files={"file": (name, data, content_type)})


def message_of(resp) -> str:
    """All the text of an error body, whatever its envelope."""
    return resp.text


# --------------------------------------------------------------------------- #
# Byte builders
# --------------------------------------------------------------------------- #


def png_bytes(size=(1500, 1000)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def jpeg_bytes(size=(64, 64)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, (30, 30, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def pdf_bytes(pages: int = 1, text: str = "Hello from the PDF") -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} page {i + 1}")
    data = doc.tobytes()
    doc.close()
    return data


def xlsx_bytes(sheets: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    first = True
    for title, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet()
        first = False
        ws.title = title
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


DEALERS = [["Phone", "Name", "Role"], ["60123456789", "Person A", "owner"], ["60100000002", "Person B", "staff"]]


def csv_bytes(rows: int = 2) -> bytes:
    return ("Phone,Name\n" + "".join(f"601{i:05d},Person {i}\n" for i in range(rows))).encode()


def zip_with(members: dict[str, bytes], *, compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()
