"""Revision-history attachments carry a resolvable url (UAC I2a / G6).

The snapshot stores ``{attachment_id, link_id, filename, size, mime}`` and NO url -
a signed url expires, so a stored one would be dead by the time anybody read the
history. The url is resolved at READ time, per attachment row, through
``storage_router`` (the provider is a per-row column: s3 or r2).

The case this exists for is the one with no live link at all. A file dropped by a
later revision is unlinked, not destroyed (G6), so its ``EntityAttachmentLink`` is
gone while the snapshot still names it. Without a url on the snapshot entry the
preview modal falls through to its "cannot preview" card - on exactly the historical
files revision history exists to show.

Postgres only, blank scratch schema, every row seeded here under a marker.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.models.entity_attachment import EntityAttachmentLink
from app.models.portal import PortalFormRevision
from app.models.resources import Attachment
from app.services.portal_revision_service import PortalRevisionService
from tests._pg_fixture import blank_session

MARKER = "ZZT-REVURL"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _attachment(db, *, provider="s3", file_path=None) -> Attachment:
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=f"{MARKER}-quote.pdf",
        stored_filename=f"{MARKER}-quote.pdf",
        file_path=file_path or f"{MARKER}/{uuid.uuid4().hex}/quote.pdf",
        file_size_bytes=2048,
        mime_type="application/pdf",
        uploader_kind="contact",
        storage_provider=provider,
    )
    db.add(row)
    db.commit()
    return row


def _revision(db, entity_id: str, attachments: list[dict], *, version_no=0) -> PortalFormRevision:
    row = PortalFormRevision(
        id=str(uuid.uuid4()),
        source_entity_type="stock_inquiry",
        source_entity_id=entity_id,
        version_no=version_no,
        revision_no=version_no,
        kind="original" if version_no == 0 else "revision",
        reason=None if version_no == 0 else f"{MARKER} reason",
        snapshot_json={},
        attachments_json=attachments,
    )
    db.add(row)
    db.commit()
    return row


def _entry(att: Attachment, *, link_id=None) -> dict:
    return {
        "attachment_id": str(att.id),
        "link_id": link_id,
        "filename": att.original_filename,
        "size": att.file_size_bytes,
        "mime": att.mime_type,
    }


def test_an_unlinked_file_still_resolves_to_a_url(db):
    """The whole point of I2a: no EntityAttachmentLink, still previewable."""
    entity_id = str(uuid.uuid4())
    att = _attachment(db)
    _revision(db, entity_id, [_entry(att)])

    assert (
        db.query(EntityAttachmentLink)
        .filter(EntityAttachmentLink.attachment_id == str(att.id))
        .count()
        == 0
    ), "the shape under test is a file with no live link left"

    items = PortalRevisionService(db).list_revisions("stock_inquiry", entity_id)
    attachment = items[0]["attachments"][0]
    assert attachment["url"], "an unlinked snapshot file must still carry a url"


def test_the_url_is_signed_against_the_rows_own_provider(db):
    """Provider is per row. One global signer would break every migrated file, and
    the breakage is a broken preview, not an error anybody sees."""
    entity_id = str(uuid.uuid4())
    s3_file = _attachment(db, provider="s3")
    r2_file = _attachment(db, provider="r2")
    _revision(db, entity_id, [_entry(s3_file), _entry(r2_file)])

    seen: dict[str, str] = {}

    def _fake_sign(file_path, *, provider=None, **_kwargs):
        seen[str(file_path)] = provider
        return f"https://signed.test/{provider}/{file_path}"

    with patch("app.services.storage_router.resolve_signed_url", side_effect=_fake_sign):
        items = PortalRevisionService(db).list_revisions("stock_inquiry", entity_id)

    by_id = {a["attachment_id"]: a for a in items[0]["attachments"]}
    assert seen[s3_file.file_path] == "s3"
    assert seen[r2_file.file_path] == "r2"
    assert by_id[str(s3_file.id)]["url"] == f"https://signed.test/s3/{s3_file.file_path}"
    assert by_id[str(r2_file.id)]["url"] == f"https://signed.test/r2/{r2_file.file_path}"


def test_the_stored_snapshot_never_gains_a_url(db):
    """Resolved at read time, so it cannot go stale. If this ever fails, history is
    serving expired links."""
    entity_id = str(uuid.uuid4())
    att = _attachment(db)
    revision = _revision(db, entity_id, [_entry(att)])

    PortalRevisionService(db).list_revisions("stock_inquiry", entity_id)
    db.expire_all()

    stored = db.query(PortalFormRevision).filter(PortalFormRevision.id == revision.id).one()
    assert "url" not in (stored.attachments_json or [{}])[0]


def test_the_original_snapshot_keys_survive(db):
    """The url is an addition. Dropping filename or size would blank the history row."""
    entity_id = str(uuid.uuid4())
    att = _attachment(db)
    _revision(db, entity_id, [_entry(att, link_id=str(uuid.uuid4()))])

    attachment = PortalRevisionService(db).list_revisions("stock_inquiry", entity_id)[0][
        "attachments"
    ][0]
    assert set(attachment) == {
        "attachment_id",
        "link_id",
        "filename",
        "size",
        "mime",
        "url",
    }
    assert attachment["filename"] == att.original_filename
    assert attachment["size"] == 2048


def test_a_deleted_attachment_row_degrades_to_no_url(db):
    """Hard-deleted bytes cannot be signed. The entry still renders (filename, size)
    and the preview falls back - it must not take the whole history down."""
    entity_id = str(uuid.uuid4())
    _revision(
        db,
        entity_id,
        [
            {
                "attachment_id": str(uuid.uuid4()),
                "link_id": None,
                "filename": f"{MARKER}-gone.pdf",
                "size": 10,
                "mime": "application/pdf",
            }
        ],
    )

    attachment = PortalRevisionService(db).list_revisions("stock_inquiry", entity_id)[0][
        "attachments"
    ][0]
    assert attachment["url"] is None
    assert attachment["filename"] == f"{MARKER}-gone.pdf"


def test_every_version_in_the_lineage_gets_urls(db):
    """Not just the newest: the older versions are the ones holding removed files."""
    entity_id = str(uuid.uuid4())
    dropped = _attachment(db)
    kept = _attachment(db)
    _revision(db, entity_id, [_entry(dropped), _entry(kept)], version_no=0)
    _revision(db, entity_id, [_entry(kept)], version_no=1)

    items = PortalRevisionService(db).list_revisions("stock_inquiry", entity_id)
    assert len(items) == 2
    for item in items:
        for attachment in item["attachments"]:
            assert attachment["url"], f"{item['label']} has an unresolvable attachment"
