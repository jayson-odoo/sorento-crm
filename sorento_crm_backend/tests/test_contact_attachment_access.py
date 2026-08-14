"""Per-contact attachment-type grants.

`is_direct_access` is one global boolean: a document type is dealer-downloadable
or it is unreachable. The Container Status workbook fits neither - the office
needs it and dealers must not have it.

The whole design rests on the visible set being a UNION, so these tests are
mostly about what must NOT change:

1. **The baseline is a floor.** A contact with no grants sees exactly the
   direct-access types, byte for byte what it saw before this table existed. If
   this feature can subtract, it is a regression dressed as a security fix.
2. **A grant is per-contact.** Granting Container Status to one contact must not
   widen anyone else's view, or the feature is just `is_direct_access` with extra
   rows.
3. **Failure resolves to the baseline, never to everything.** An unknown contact,
   a contact in the wrong workspace, or a lookup that raises all fall back - a
   fail-open here hands sensitive documents to whoever mistypes an id.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.access import ContactAttachmentType, RespondContact
from app.models.resources import Attachment, AttachmentType
from app.services.contact_attachment_access import (
    granted_type_ids,
    list_grants,
    set_grants,
    visible_type_ids,
)
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _contact(db, *, respond_io_id=None) -> RespondContact:
    contact = RespondContact(
        id=unique_code("CONTACT"),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name="ZZT Contact",
        respond_io_id=respond_io_id,
    )
    db.add(contact)
    db.flush()
    return contact


def _type(db, name, *, direct=False) -> AttachmentType:
    row = AttachmentType(
        id=str(uuid.uuid4()),
        type_name=unique_code(name),
        allowed_extensions="pdf,xlsx",
        is_direct_access=direct,
    )
    db.add(row)
    db.flush()
    return row


def _grant(db, contact, att_type) -> ContactAttachmentType:
    row = ContactAttachmentType(
        id=str(uuid.uuid4()),
        contact_id=contact.id,
        attachment_type_id=str(att_type.id),
    )
    db.add(row)
    db.flush()
    return row


# --- the union ------------------------------------------------------------


def test_no_grants_leaves_the_filter_alone(db):
    """None means "do not widen" - the caller keeps its direct-access filter."""
    contact = _contact(db)
    _type(db, "Direct", direct=True)
    assert visible_type_ids(db, contact.id) is None


def test_grant_widens_the_baseline_rather_than_replacing_it(db):
    """The granted type is ADDED. The baseline must survive the widening."""
    contact = _contact(db)
    baseline = _type(db, "Direct", direct=True)
    container = _type(db, "Container Status")
    _grant(db, contact, container)

    visible = visible_type_ids(db, contact.id)

    assert visible is not None
    assert str(baseline.id) in visible, "granting a type must not cost the baseline"
    assert str(container.id) in visible


def test_a_grant_does_not_widen_another_contact(db):
    """Otherwise this is `is_direct_access` again, just with more rows."""
    granted_contact = _contact(db)
    other = _contact(db)
    _type(db, "Direct", direct=True)
    container = _type(db, "Container Status")
    _grant(db, granted_contact, container)

    assert visible_type_ids(db, other.id) is None


def test_ungranted_type_stays_out(db):
    contact = _contact(db)
    _type(db, "Direct", direct=True)
    granted = _type(db, "Container Status")
    ungranted = _type(db, "Product Photos")
    _grant(db, contact, granted)

    visible = visible_type_ids(db, contact.id)

    assert str(ungranted.id) not in visible


# --- failing closed -------------------------------------------------------


def test_unknown_contact_falls_back_to_the_baseline(db):
    """Not to everything. A mistyped id must not become a skeleton key."""
    _type(db, "Direct", direct=True)
    _type(db, "Container Status")
    assert visible_type_ids(db, "no-such-contact") is None


def test_no_contact_supplied_leaves_the_filter_alone(db):
    _type(db, "Container Status")
    assert visible_type_ids(db, None) is None
    assert visible_type_ids(db, "") is None


def test_respond_io_id_resolves_to_the_internal_contact(db):
    """n8n passes the Respond.io id; grants key on the internal one."""
    contact = _contact(db, respond_io_id=unique_code("rio"))
    _type(db, "Direct", direct=True)
    container = _type(db, "Container Status")
    _grant(db, contact, container)

    visible = visible_type_ids(db, contact.respond_io_id)

    assert visible is not None and str(container.id) in visible


def test_granted_type_ids_swallows_a_broken_lookup(db, monkeypatch):
    """The inner read is the one that must never propagate - it returns empty."""
    contact = _contact(db)

    class Boom:
        def query(self, *_a, **_k):
            raise RuntimeError("db exploded")

    assert granted_type_ids(Boom(), contact.id) == set()


# --- the grant surface ----------------------------------------------------


def test_list_grants_returns_the_whole_catalog_not_just_grants(db):
    """An admin needs to see what CAN be granted, not only what is."""
    contact = _contact(db)
    baseline = _type(db, "Direct", direct=True)
    container = _type(db, "Container Status")
    _grant(db, contact, container)

    result = list_grants(db, contact.id)
    by_id = {row["id"]: row for row in result["data"]}

    assert by_id[str(container.id)]["granted"] is True
    assert by_id[str(baseline.id)]["granted"] is False
    assert by_id[str(baseline.id)]["is_direct_access"] is True
    assert result["granted_ids"] == [str(container.id)]


def test_set_grants_replaces_the_set(db):
    contact = _contact(db)
    first = _type(db, "Container Status")
    second = _type(db, "Project Document")
    _grant(db, contact, first)

    set_grants(db, contact.id, [str(second.id)], actor="tester")

    assert granted_type_ids(db, contact.id) == {str(second.id)}


def test_set_grants_is_idempotent(db):
    """Re-saving the same set must not raise on the unique constraint."""
    contact = _contact(db)
    container = _type(db, "Container Status")

    set_grants(db, contact.id, [str(container.id)])
    set_grants(db, contact.id, [str(container.id)])

    assert granted_type_ids(db, contact.id) == {str(container.id)}


def test_set_grants_empty_clears(db):
    contact = _contact(db)
    container = _type(db, "Container Status")
    _grant(db, contact, container)

    set_grants(db, contact.id, [])

    assert granted_type_ids(db, contact.id) == set()


def test_set_grants_stamps_the_actor(db):
    contact = _contact(db)
    container = _type(db, "Container Status")

    set_grants(db, contact.id, [str(container.id)], actor="admin-1")

    row = (
        db.query(ContactAttachmentType)
        .filter(ContactAttachmentType.contact_id == contact.id)
        .one()
    )
    assert row.created_by == "admin-1"


def test_set_grants_rejects_an_unknown_contact(db):
    from app.services.error_handler import AppException

    container = _type(db, "Container Status")
    with pytest.raises(AppException):
        set_grants(db, "no-such-contact", [str(container.id)])


def test_deleting_a_contact_takes_its_grants(db):
    """ON DELETE CASCADE - a stale grant keyed to a dead contact is a landmine."""
    contact = _contact(db)
    container = _type(db, "Container Status")
    _grant(db, contact, container)

    db.delete(contact)
    db.flush()

    assert (
        db.query(ContactAttachmentType)
        .filter(ContactAttachmentType.contact_id == contact.id)
        .count()
        == 0
    )


# --- what the endpoint actually serves ------------------------------------


def _attachment(db, att_type) -> Attachment:
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=unique_code("file") + ".xlsx",
        stored_filename=unique_code("file") + ".xlsx",
        file_path="zzt/" + unique_code("key"),
        attachment_type_id=str(att_type.id),
        is_deleted=False,
    )
    db.add(row)
    db.flush()
    return row


def test_query_serves_baseline_plus_grant_and_nothing_else(db):
    """End to end through the query builder, which is what the MCP tool hits."""
    from app.services.resources_service import AttachmentService

    contact = _contact(db)
    baseline = _type(db, "Direct", direct=True)
    container = _type(db, "Container Status")
    hidden = _type(db, "Product Photos")
    baseline_file = _attachment(db, baseline)
    container_file = _attachment(db, container)
    _attachment(db, hidden)
    _grant(db, contact, container)

    service = AttachmentService(db)
    result = service.list_attachments(
        direct_access_only=True,
        visible_attachment_type_ids=visible_type_ids(db, contact.id),
    )
    ids = {str(a.id) for a in result["data"]}

    assert ids == {str(baseline_file.id), str(container_file.id)}


def test_query_without_grants_is_unchanged(db):
    """The regression that would matter most: today's callers keep today's rows."""
    from app.services.resources_service import AttachmentService

    contact = _contact(db)
    baseline = _type(db, "Direct", direct=True)
    container = _type(db, "Container Status")
    baseline_file = _attachment(db, baseline)
    _attachment(db, container)

    service = AttachmentService(db)
    result = service.list_attachments(
        direct_access_only=True,
        visible_attachment_type_ids=visible_type_ids(db, contact.id),
    )

    assert {str(a.id) for a in result["data"]} == {str(baseline_file.id)}
