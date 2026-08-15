"""The outbox learned to carry a document. Every email that does not want one must not notice.

The change was made so SMTP keeps ONE producer: the drainer owns the backoff, the rate limiter
and the per-event kill switch, and forking a second sender to gain an attachment would have
duplicated all three. The risk of that shape is entirely on the other side - that every
existing email quietly changes - so that is what these tests hold down.
"""
from __future__ import annotations

from app.models.email_outbox import EmailOutbox
from app.tasks import email_outbox_tasks as tasks


def _row(**over) -> EmailOutbox:
    row = EmailOutbox(
        event_key="password_reset",
        recipient_email="someone@example.test",
        subject="Subject",
        body_text="Body",
    )
    for k, v in over.items():
        setattr(row, k, v)
    return row


def test_a_row_with_no_attachment_sends_exactly_what_it_used_to():
    # The regression guard. `attachments=None` is what `send_mime_email` received before this
    # change existed, so an existing email's payload is byte-identical.
    captured = {}

    def fake_send(**kwargs):
        captured.update(kwargs)
        return None

    original = tasks.send_mime_email
    tasks.send_mime_email = fake_send  # type: ignore[assignment]
    try:
        assert tasks._attempt_send(_row(), None) is None
    finally:
        tasks.send_mime_email = original  # type: ignore[assignment]

    assert captured["attachments"] is None
    assert captured["subject"] == "Subject"
    assert captured["to_list"] == ["someone@example.test"]


def test_a_row_that_declares_a_document_carries_it():
    captured = {}

    class FakeBackend:
        def download_file(self, key):
            assert key == "exports/supplier-notice/x/notice.pdf"
            return b"%PDF-1.4 bytes"

    def fake_send(**kwargs):
        captured.update(kwargs)
        return None

    import app.services.storage_router as router

    original_send, original_backend = tasks.send_mime_email, router.get_backend
    tasks.send_mime_email = fake_send  # type: ignore[assignment]
    router.get_backend = lambda provider: FakeBackend()  # type: ignore[assignment]
    try:
        row = _row(
            attachment_filename="notice.pdf",
            attachment_storage_provider="s3",
            attachment_storage_key="exports/supplier-notice/x/notice.pdf",
        )
        assert tasks._attempt_send(row, None) is None
    finally:
        tasks.send_mime_email = original_send  # type: ignore[assignment]
        router.get_backend = original_backend  # type: ignore[assignment]

    assert captured["attachments"] == [("notice.pdf", "application/pdf", b"%PDF-1.4 bytes")]


def test_a_document_that_cannot_be_read_fails_the_send_rather_than_arriving_empty():
    # An email that was supposed to carry a document and silently arrives without one is worse
    # than one that retries: the recipient has no way to tell it is incomplete. Reporting it as
    # a send failure puts it back through the outbox's existing backoff.
    class BrokenBackend:
        def download_file(self, key):
            raise RuntimeError("object missing")

    import app.services.storage_router as router

    original_send, original_backend = tasks.send_mime_email, router.get_backend
    tasks.send_mime_email = lambda **kwargs: None  # type: ignore[assignment]
    router.get_backend = lambda provider: BrokenBackend()  # type: ignore[assignment]
    try:
        row = _row(
            attachment_filename="notice.pdf",
            attachment_storage_provider="s3",
            attachment_storage_key="gone.pdf",
        )
        error = tasks._attempt_send(row, None)
    finally:
        tasks.send_mime_email = original_send  # type: ignore[assignment]
        router.get_backend = original_backend  # type: ignore[assignment]

    assert error is not None
    assert "attachment unavailable" in error


def test_a_filename_is_derived_from_the_key_when_none_was_stored():
    class FakeBackend:
        def download_file(self, key):
            return b"data"

    import app.services.storage_router as router

    original = router.get_backend
    router.get_backend = lambda provider: FakeBackend()  # type: ignore[assignment]
    try:
        out = tasks._attachments_for(_row(attachment_storage_key="a/b/c/notice.pdf"))
    finally:
        router.get_backend = original  # type: ignore[assignment]

    assert out == [("notice.pdf", "application/pdf", b"data")]
