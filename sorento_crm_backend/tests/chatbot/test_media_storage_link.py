"""S4 (PLAN-chatbot-media-into-turn.md): store the media bytes and expose them on the
turn projection.

AC-1833 to AC-1841 (UAC section D). None of `app.tasks.media_tasks.process_media_
extraction` uploading to storage, the `attachments` row, the `entity_attachment_links`
row, the `chatbot_media` attachment type seed, or the `media` block on
`GET /system/chatbot/turns[/{id}]` exist yet - every test here is expected to fail for
exactly one of those absences, never an import error.

Storage is mocked at `app.services.storage_router.get_backend` (never a real S3/R2 call),
the same seam `app/api/v1/resources/attachments.py`'s own upload route is built on.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import text

from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import Attachment, AttachmentType

from tests.chatbot.test_engine import CONTACT_ID, seeded  # noqa: F401
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_media_intake_turn import (
    IMAGE_RESULT,
    _contact_uuid,
    _image_envelope,
    _seed_media_limit,
    _seed_settings,
    _voice_envelope,
    media_pipeline,  # noqa: F401
)


def _seed_chatbot_media_attachment_type(session_factory) -> None:
    """The blank schema (`Base.metadata.create_all`) carries no migration DATA, only
    the tables - migration 526's `chatbot_media` seed row lives only on a REAL,
    migrated database (see `TestAttachmentTypeSeed` below, which reads that one
    directly). `EntityAttachmentService.create_attachment_and_link` 404s without a row
    to resolve the code against, so every test here that expects a real attachment
    row seeds one by hand first."""
    db = session_factory()
    if db.query(AttachmentType).filter(AttachmentType.code == "chatbot_media").first() is None:
        db.add(
            AttachmentType(
                code="chatbot_media",
                type_name="Chatbot media (test seed)",
                allowed_extensions="jpg,jpeg,png,ogg,mp3",
                max_file_size_mb=25,
            )
        )
        db.commit()


class _FakeBackend:
    def __init__(self, *, raise_on_upload: bool = False) -> None:
        self.raise_on_upload = raise_on_upload
        self.uploads: list[dict[str, Any]] = []

    def upload_file(self, *, file_content: bytes, file_path: str, content_type: str):
        if self.raise_on_upload:
            raise RuntimeError("storage backend unreachable")
        self.uploads.append({"file_path": file_path, "content_type": content_type, "size": len(file_content)})
        return file_path, "https://cdn.example/" + file_path


@pytest.fixture()
def fake_storage(monkeypatch):
    backend = _FakeBackend()

    import app.services.storage_router as storage_router

    monkeypatch.setattr(storage_router, "get_backend", lambda provider: backend)
    monkeypatch.setattr(storage_router, "default_provider", lambda: "s3")
    monkeypatch.setattr(storage_router, "cdn_base_url", lambda provider, key: f"https://cdn.example/{key}")
    monkeypatch.setattr(
        storage_router, "resolve_signed_url", lambda path, *, provider, expires_in=900: f"{path}?sig=zzt"
    )
    return backend


def _attachment_rows_for_contact(session_factory, contact_uuid: str) -> list[Attachment]:
    return (
        session_factory()
        .query(Attachment)
        .filter(Attachment.uploaded_by_contact_id == contact_uuid)
        .all()
    )


def _links_for(session_factory, entity_type: str, entity_id: str) -> list[EntityAttachmentLink]:
    return (
        session_factory()
        .query(EntityAttachmentLink)
        .filter(EntityAttachmentLink.entity_type == entity_type, EntityAttachmentLink.entity_id == entity_id)
        .all()
    )


class TestImageAttachmentRowCreated:
    """AC-1833/AC-1834."""

    def test_completed_image_job_creates_an_attachment_and_a_link(
        self, session_factory, seeded, stub_parser, stub_access, media_pipeline, fake_storage, monkeypatch
    ):
        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        _seed_chatbot_media_attachment_type(session_factory)
        # `_store_media_bytes` (S4, `app/tasks/media_tasks.py`) stores the SAME bytes
        # the extraction itself fetched (security review item 1: never a second
        # `fetch_media_bytes` call) - handed to the canned result the same shape
        # `media_extract.service._result_with_bytes` produces for real.
        media_pipeline.set_result(
            IMAGE_RESULT, media_bytes=b"fake-image-bytes", media_content_type="image/jpeg"
        )
        stub_parser()
        stub_access()

        result = engine_run(session_factory, _image_envelope(caption="Check stock"))

        contact_uuid = _contact_uuid(session_factory)
        rows = _attachment_rows_for_contact(session_factory, contact_uuid)
        assert rows, "no attachments row was created for the completed image job"
        row = rows[0]
        assert row.uploader_kind == "contact"
        assert row.mime_type == "image/jpeg"
        assert row.file_size_bytes
        assert row.storage_provider == "s3"
        assert row.attachment_type is not None and row.attachment_type.code == "chatbot_media"

        links = _links_for(session_factory, "chatbot_turn", str(result.turn_id))
        assert len(links) == 1
        assert links[0].attachment_id == row.id

        # Hot fix (browser pass): the transient `_media_bytes`/`_media_content_type`
        # keys must never reach the persisted job row - raw bytes in a JSONB column
        # fail json.dumps, which turned a genuinely successful extraction into a
        # failed job.
        from app.models.media import ContactMediaUsage, MediaExtractionJob

        db = session_factory()
        usage = db.query(ContactMediaUsage).filter(ContactMediaUsage.contact_id == contact_uuid).first()
        assert usage is not None
        job = db.query(MediaExtractionJob).filter(MediaExtractionJob.usage_id == usage.id).first()
        assert job is not None and job.result is not None
        assert "_media_bytes" not in job.result
        assert "_media_content_type" not in job.result


class TestVoiceAttachmentRowCreated:
    """AC-1835."""

    def test_completed_voice_job_creates_an_attachment_with_the_audio_mime(
        self, session_factory, seeded, stub_parser, stub_access, media_pipeline, fake_storage, monkeypatch
    ):
        _seed_media_limit(session_factory, modality="voice")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        _seed_chatbot_media_attachment_type(session_factory)
        media_pipeline.set_result(
            {"transcript": "stock for SRTWB1455"},
            media_bytes=b"fake-voice-bytes", media_content_type="audio/ogg",
        )
        stub_parser()
        stub_access()

        engine_run(session_factory, _voice_envelope())

        contact_uuid = _contact_uuid(session_factory)
        rows = _attachment_rows_for_contact(session_factory, contact_uuid)
        assert rows, "no attachments row was created for the completed voice job"
        assert rows[0].mime_type == "audio/ogg"


class TestStorageFailureDoesNotFailTheExtraction:
    """AC-1836."""

    def test_upload_failure_still_completes_with_no_attachment_row(
        self, session_factory, seeded, stub_parser, stub_access, media_pipeline, monkeypatch
    ):
        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        _seed_chatbot_media_attachment_type(session_factory)
        media_pipeline.set_result(
            IMAGE_RESULT, media_bytes=b"fake-image-bytes", media_content_type="image/jpeg"
        )
        stub_parser()
        stub_access()

        import app.services.storage_router as storage_router

        failing_backend = _FakeBackend(raise_on_upload=True)
        monkeypatch.setattr(storage_router, "get_backend", lambda provider: failing_backend)
        monkeypatch.setattr(storage_router, "default_provider", lambda: "s3")

        result = engine_run(session_factory, _image_envelope(caption="Check stock"))

        contact_uuid = _contact_uuid(session_factory)
        assert not _attachment_rows_for_contact(session_factory, contact_uuid)

        from tests.chatbot.test_media_intake_turn import _trace_of

        trace = _trace_of(session_factory, result.turn_id)
        stage = next((r for r in trace if r.get("stage") == "media_intake"), None)
        assert stage is not None, "media_intake stage not implemented yet"
        assert (stage.get("facts") or {}).get("attachment_error"), (
            "a storage upload failure must be noted on the trace, not silently dropped"
        )


class TestDeniedJobCreatesNoAttachment:
    """AC-1837.

    NOTE FOR THE CAPTAIN: vacuously true today - no media feature exists at all yet, so
    naturally no attachment row is created. Kept as the regression guard S4 needs once
    upload-on-completion lands; not an independently red test today."""

    def test_denied_gate_creates_no_attachment(
        self, session_factory, seeded, stub_access, fake_storage
    ):
        import app.services.chatbot.head.parser as parser_mod
        from unittest.mock import patch as _patch

        _seed_settings(session_factory, media_sync_wait_seconds=5)
        stub_access()
        with _patch.object(parser_mod, "parse", lambda *a, **k: {}):
            engine_run(session_factory, _image_envelope(caption="Check stock"))

        contact_uuid = _contact_uuid(session_factory)
        assert not _attachment_rows_for_contact(session_factory, contact_uuid)
        assert not fake_storage.uploads


class TestAttachmentTypeSeed:
    """AC-1838: `attachment_types.code == 'chatbot_media'` exists exactly once. Read
    against the REAL (non-blank-schema) database this lane's tests run on - it is
    already migrated to head, and this migration is not on it yet, so this is a direct
    read of live migration state rather than the create_all blank schema (which has no
    seed data at all)."""

    def test_chatbot_media_attachment_type_seeded(self) -> None:
        from app.database import engine

        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT id FROM attachment_types WHERE code = 'chatbot_media'")
            ).fetchall()
        assert len(rows) == 1, (
            f"expected exactly one attachment_types row with code='chatbot_media', "
            f"found {len(rows)} - the S4 seed migration has not landed on this DB yet"
        )


def engine_run(session_factory, envelope):
    from app.services.chatbot import engine as engine_mod

    return engine_mod.run_turn(envelope, session_factory=session_factory)


# --------------------------------------------------------------------------- #
# Turn projection - `media` block on GET /turns and /turns/{id}
# --------------------------------------------------------------------------- #


class TestTurnDetailCarriesMediaBlock:
    """AC-1839/AC-1840/AC-1841."""

    def _seed_media_turn(self, db, *, contact: str) -> tuple[str, str]:
        """A turn whose trace already carries a completed `media_intake` stage, plus a
        real attachment + link - built by hand rather than through `run_turn`, so this
        test is independent of section A/D's own wiring and only proves the PROJECTION."""
        from app.models.chatbot_turn import ChatbotTurn

        turn_id = str(uuid.uuid4())
        db.execute(
            text(
                "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
                "VALUES (gen_random_uuid()::text, :cid, :phone, CAST('{}' AS jsonb)) "
                "ON CONFLICT DO NOTHING"
            ),
            {"cid": contact, "phone": "+60000000009"},
        )
        contact_uuid = db.execute(
            text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": contact}
        ).scalar()

        att_type = db.query(AttachmentType).filter(AttachmentType.code == "chatbot_media").first()
        if att_type is None:
            att_type = AttachmentType(
                code="chatbot_media", type_name="Chatbot media (test seed)",
                allowed_extensions="jpg,jpeg,png,ogg,mp3", max_file_size_mb=25,
            )
            db.add(att_type)
            db.flush()

        attachment = Attachment(
            attachment_type_id=att_type.id,
            original_filename="photo.jpg",
            stored_filename="photo.jpg",
            file_path="chatbot-media/x.jpg",
            mime_type="image/jpeg",
            file_size_bytes=98641,
            uploaded_by_contact_id=contact_uuid,
            uploader_kind="contact",
            storage_provider="s3",
        )
        db.add(attachment)
        db.flush()
        db.add(EntityAttachmentLink(entity_type="chatbot_turn", entity_id=turn_id, attachment_id=attachment.id))

        trace = [
            {
                "stage": "media_intake",
                "status": "ok",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ms": 900,
                "summary": "Read the photo.",
                "why": "media",
                "facts": {
                    "modality": "image",
                    "decision": "accepted",
                    "status": "completed",
                    "job_id": str(uuid.uuid4()),
                    "elapsed_ms": 900,
                    "attachment_id": attachment.id,
                    "result": {
                        "entities": ["A", "B"],
                        "attributes": [],
                        "truncated": False,
                        "notes": None,
                        "rendered_text": "A, B",
                    },
                },
                "error": None,
                "raw": {},
            }
        ]
        turn = ChatbotTurn(
            id=turn_id,
            contact_respond_id=contact,
            message_id=f"ZZT-media-turn-{uuid.uuid4().hex[:8]}",
            ingress="webhook",
            envelope={"message": {}, "contact": {"id": contact}},
            status="done",
            stage="sent",
            branch_kind="business_query",
            attempt=1,
            trace=trace,
        )
        db.add(turn)
        db.commit()
        return turn_id, attachment.id

    def test_detail_endpoint_carries_the_media_block(self, session_factory, monkeypatch):
        from tests.chatbot.test_turns_admin_api import BASE, client, db, _permissions  # noqa: F401

        # `_media_block` now signs `strict=True` (review round note (b)): a broken
        # signer must surface as no url, never an unsigned one - so this test, which
        # has no real CloudFront key configured, mocks the signer the same way
        # `fake_storage` does elsewhere in this file, rather than relying on the
        # OLD fail-open behaviour this note retired.
        import app.services.storage_router as storage_router

        monkeypatch.setattr(
            storage_router, "resolve_signed_url",
            lambda path, *, provider, expires_in=900, strict=False: f"{path}?sig=zzt",
        )

        db_session = session_factory()
        turn_id, attachment_id = self._seed_media_turn(db_session, contact=f"ZZT-media-{uuid.uuid4().hex[:8]}")

        def _override_db():
            try:
                yield db_session
            finally:
                pass

        from app.main import app
        from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
        from app.services.user_service import UserPermissionService
        from fastapi.testclient import TestClient

        grants = {"system.chat_history.view"}

        import unittest.mock as mock

        with mock.patch.object(
            UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in grants
        ), mock.patch.object(UserPermissionService, "get_user_role_slugs", lambda self, uid: set()):
            app.dependency_overrides[get_db] = _override_db
            app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4()), "name": "ZZT"}
            app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": str(uuid.uuid4()), "name": "ZZT"}
            try:
                test_client = TestClient(app, raise_server_exceptions=False)
                resp = test_client.get(f"{BASE}/{turn_id}")
                assert resp.status_code == 200, resp.text
                body = resp.json()
                assert "media" in body, (
                    "ChatbotTurnResponse does not declare a 'media' field yet - "
                    "response_model silently dropped it"
                )
                media = body["media"]
                assert media is not None
                for key in (
                    "modality", "mime_type", "attachment_id", "url",
                    "transcript_or_rendered_text", "entities", "attributes", "notes",
                    "truncated", "decision",
                ):
                    assert key in media, f"media block missing {key!r}: {media}"
                assert media["attachment_id"] == attachment_id
                assert media["url"], "expected a signed url"

                grants.clear()
                resp2 = test_client.get(f"{BASE}/{turn_id}")
                assert resp2.status_code == 403, resp2.text
            finally:
                app.dependency_overrides.clear()

    def test_text_turn_has_null_media(self, session_factory):
        from app.models.chatbot_turn import ChatbotTurn
        from tests.chatbot.test_turns_admin_api import BASE, _seed_turn

        db_session = session_factory()
        contact = f"ZZT-text-{uuid.uuid4().hex[:8]}"
        row = _seed_turn(db_session, contact_respond_id=contact, trace=[])

        from app.main import app
        from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
        from app.services.user_service import UserPermissionService
        from fastapi.testclient import TestClient
        import unittest.mock as mock

        with mock.patch.object(
            UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
        ), mock.patch.object(UserPermissionService, "get_user_role_slugs", lambda self, uid: set()):
            def _override_db():
                try:
                    yield db_session
                finally:
                    pass

            app.dependency_overrides[get_db] = _override_db
            app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4()), "name": "ZZT"}
            app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": str(uuid.uuid4()), "name": "ZZT"}
            try:
                test_client = TestClient(app, raise_server_exceptions=False)
                resp = test_client.get(f"{BASE}/{row.id}")
                assert resp.status_code == 200, resp.text
                body = resp.json()
                assert "media" in body
                assert body["media"] is None
            finally:
                app.dependency_overrides.clear()
