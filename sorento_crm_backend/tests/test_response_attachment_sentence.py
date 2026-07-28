"""Table-driven coverage for the response-attachment sentence + staff count
(UAC-response-attachments.md D1/D3, item 8 of the test brief).

Per the orchestrator's mid-task note: the current wording is

    count 0 -> ""
    count 1 -> singular ("1 attachment")
    count N -> plural ("N attachments")

Assertions favour structure (contains the count, correct singular/plural,
never both) over the full literal sentence, except for the 0 -> "" case,
which is asserted exactly since that IS the hard behavioural contract
(never say "0 attachments").
"""
from __future__ import annotations

import uuid

import pytest

from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import Attachment, AttachmentType
from app.services.entity_attachment_service import (
    RESPONSE_ATTACHMENT_TYPE_CODE,
    compose_response_attachment_sentence,
    count_staff_attachments,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# ---------------------------------------------------------------------------
# compose_response_attachment_sentence - pure function, table-driven
# ---------------------------------------------------------------------------


def test_zero_is_exactly_empty_string():
    assert compose_response_attachment_sentence(0) == ""


@pytest.mark.parametrize("count", [-5, -1, 0])
def test_non_positive_counts_are_empty_string(count):
    assert compose_response_attachment_sentence(count) == ""


def test_one_is_singular():
    sentence = compose_response_attachment_sentence(1)
    assert sentence != ""
    assert "1 attachment" in sentence
    assert "1 attachments" not in sentence


@pytest.mark.parametrize("count", [2, 3, 9, 25])
def test_n_greater_than_one_is_plural_and_names_the_count(count):
    sentence = compose_response_attachment_sentence(count)
    assert sentence != ""
    assert f"{count} attachments" in sentence
    # The plural word never regresses to the singular for N > 1 (e.g. never
    # emits a bare "N attachment" without the trailing "s").
    assert f"{count} attachment " not in sentence


def test_never_says_image_generic_attachment_wording_only():
    # A staff reply may include a PDF/spreadsheet, not just an image - the
    # sentence must not say "image(s)".
    for count in (1, 2, 5):
        sentence = compose_response_attachment_sentence(count)
        assert "image" not in sentence.lower()


# ---------------------------------------------------------------------------
# count_staff_attachments - scoped to uploader_kind='user' AND the
# response_attachment type (a manually linked internal file must never be
# announced to the customer)
# ---------------------------------------------------------------------------


@pytest.fixture
def response_type_id(db) -> str:
    row = AttachmentType(
        id=str(uuid.uuid4()),
        code=RESPONSE_ATTACHMENT_TYPE_CODE,
        type_name="Response Attachment",
        allowed_extensions="jpg,png,pdf",
        max_file_size_mb=10,
    )
    db.add(row)
    db.flush()
    return row.id


@pytest.fixture
def other_type_id(db) -> str:
    """Any non-response type - stands in for the manual Linked Attachments panel."""
    row = AttachmentType(
        id=str(uuid.uuid4()),
        code="internal_doc",
        type_name="Internal Document",
        allowed_extensions="jpg,png,pdf",
        max_file_size_mb=10,
    )
    db.add(row)
    db.flush()
    return row.id


def _attachment(
    db,
    *,
    uploader_kind,
    uploaded_by=None,
    uploaded_by_contact_id=None,
    attachment_type_id=None,
) -> str:
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename="f.jpg",
        stored_filename="f.jpg",
        file_path="https://cdn.test/f.jpg",
        uploaded_by=uploaded_by,
        uploaded_by_contact_id=uploaded_by_contact_id,
        uploader_kind=uploader_kind,
        attachment_type_id=attachment_type_id,
    )
    db.add(att)
    db.flush()
    return att.id


def _link(db, entity_type: str, entity_id: str, attachment_id: str) -> None:
    db.add(
        EntityAttachmentLink(
            entity_type=entity_type,
            entity_id=entity_id,
            attachment_id=attachment_id,
        )
    )
    db.commit()


def test_count_staff_attachments_zero_when_none_linked(db):
    assert count_staff_attachments(db, "stock_inquiry", str(uuid.uuid4())) == 0


def test_count_staff_attachments_counts_only_uploader_kind_user(db, response_type_id):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number=f"+6011{uuid.uuid4().hex[:8]}", name="Contact"
    )
    db.add(contact)
    db.flush()

    entity_id = str(uuid.uuid4())
    staff_1 = _attachment(
        db, uploader_kind="user", uploaded_by=str(uuid.uuid4()), attachment_type_id=response_type_id
    )
    staff_2 = _attachment(
        db, uploader_kind="user", uploaded_by=str(uuid.uuid4()), attachment_type_id=response_type_id
    )
    contact_att = _attachment(
        db,
        uploader_kind="contact",
        uploaded_by_contact_id=contact.id,
        attachment_type_id=response_type_id,
    )
    system_att = _attachment(db, uploader_kind="system", attachment_type_id=response_type_id)
    legacy_null = _attachment(db, uploader_kind=None, attachment_type_id=response_type_id)

    for att_id in (staff_1, staff_2, contact_att, system_att, legacy_null):
        _link(db, "stock_inquiry", entity_id, att_id)

    # Only the two uploader_kind='user' rows count - the contact's own
    # uploads, system uploads, and legacy NULL rows never inflate the sentence.
    assert count_staff_attachments(db, "stock_inquiry", entity_id) == 2


def test_count_staff_attachments_ignores_manually_linked_staff_files(
    db, response_type_id, other_type_id
):
    """A staff member linking an internal spec sheet through the Linked
    Attachments panel is ALSO uploader_kind='user' (the uploader backfill stamps
    every historical staff upload that way). Announcing it to the customer would
    send them an internal document nobody chose to share."""
    entity_id = str(uuid.uuid4())
    manual = _attachment(
        db, uploader_kind="user", uploaded_by=str(uuid.uuid4()), attachment_type_id=other_type_id
    )
    _link(db, "complaint", entity_id, manual)
    assert count_staff_attachments(db, "complaint", entity_id) == 0

    reply_file = _attachment(
        db, uploader_kind="user", uploaded_by=str(uuid.uuid4()), attachment_type_id=response_type_id
    )
    _link(db, "complaint", entity_id, reply_file)
    assert count_staff_attachments(db, "complaint", entity_id) == 1


def test_count_staff_attachments_scoped_to_entity_type_and_id(db, response_type_id):
    entity_id = str(uuid.uuid4())
    other_entity_id = str(uuid.uuid4())
    staff_att = _attachment(
        db, uploader_kind="user", uploaded_by=str(uuid.uuid4()), attachment_type_id=response_type_id
    )
    _link(db, "stock_inquiry", entity_id, staff_att)

    # Same attachment type, different entity id -> not counted.
    assert count_staff_attachments(db, "stock_inquiry", other_entity_id) == 0
    # Same entity id, different entity_type (complaint vs stock_inquiry) -> not counted.
    assert count_staff_attachments(db, "complaint", entity_id) == 0
    assert count_staff_attachments(db, "stock_inquiry", entity_id) == 1


def test_count_staff_attachments_empty_ids_return_zero_never_raise(db):
    assert count_staff_attachments(db, "", "") == 0
    assert count_staff_attachments(db, "stock_inquiry", "") == 0
    assert count_staff_attachments(db, "", str(uuid.uuid4())) == 0
