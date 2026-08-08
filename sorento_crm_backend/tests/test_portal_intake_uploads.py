"""The receipt a consumer photographed has to survive the extractor's opinion of it.

`/ai-extract` read the uploaded bytes, posted them to a model and dropped them. Nothing
persisted the file. So the journey that opens with "take a photo of your receipt" produced
a complaint with no receipt on it, and when extraction misread the printed date - which is
the ordinary case, not the edge case - CS had nothing to check it against.

The rule these tests pin: the upload is EVIDENCE first and model input second. What the
extractor made of a file is a judgement about the file; it is never the reason to keep or
lose it. The files it reads worst are exactly the ones a human most needs to open.

Run: venv/bin/python -m pytest tests/test_portal_intake_uploads.py -q -p no:randomly
"""
from __future__ import annotations

import pytest

from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import Attachment
from app.services.consumer_lodge_service import _proof_attachment_id
from app.services.portal_intake_uploads import link_uploads_to_entity
from tests._pg_fixture import pg_session, unique_code


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


def _attachment(db) -> Attachment:
    """An already-stored upload, as `/ai-extract` would have left it: no link yet."""
    from app.services.entity_attachment_service import EntityAttachmentService
    from app.services.portal_service import PORTAL_ATTACHMENT_TYPE_CODE

    row = Attachment(
        attachment_type_id=EntityAttachmentService(db)
        .get_attachment_type_by_code(PORTAL_ATTACHMENT_TYPE_CODE)
        .id,
        original_filename=f"{unique_code('receipt')}.jpg",
        stored_filename=f"{unique_code('receipt')}.jpg",
        file_path=f"portal/test/{unique_code('key')}.jpg",
        uploader_kind="contact",
    )
    db.add(row)
    db.flush()
    return row


class TestLinkingUploadsToTheComplaint:
    def test_an_uploaded_file_ends_up_on_the_record(self, db):
        complaint_id = unique_code("cmp")
        attachment = _attachment(db)

        linked = link_uploads_to_entity(
            db,
            entity_type="complaint",
            entity_id=complaint_id,
            attachment_ids=[str(attachment.id)],
        )

        assert linked == [str(attachment.id)]
        assert (
            db.query(EntityAttachmentLink)
            .filter(
                EntityAttachmentLink.entity_type == "complaint",
                EntityAttachmentLink.entity_id == complaint_id,
            )
            .count()
            == 1
        )

    def test_every_file_is_linked_not_just_the_one_that_looked_like_a_receipt(self, db):
        # The shot of the cracked basin is the evidence a technician needs, and the
        # receipt the extractor could not read is the one CS has to open by hand.
        complaint_id = unique_code("cmp")
        ids = [str(_attachment(db).id) for _ in range(3)]

        assert len(link_uploads_to_entity(
            db, entity_type="complaint", entity_id=complaint_id, attachment_ids=ids
        )) == 3

    def test_a_resubmit_does_not_fail_on_its_own_earlier_success(self, db):
        """Linking is idempotent from the caller's point of view.

        `link_existing_attachment` raises conflict on a duplicate. A client retrying a
        submit would otherwise get a 500 for work that already succeeded - and the
        complaint is the thing that must not be lost.
        """
        complaint_id = unique_code("cmp")
        attachment_id = str(_attachment(db).id)
        link_uploads_to_entity(
            db, entity_type="complaint", entity_id=complaint_id, attachment_ids=[attachment_id]
        )

        again = link_uploads_to_entity(
            db, entity_type="complaint", entity_id=complaint_id, attachment_ids=[attachment_id]
        )

        assert again == []  # skipped, not raised
        assert (
            db.query(EntityAttachmentLink)
            .filter(EntityAttachmentLink.entity_id == complaint_id)
            .count()
            == 1
        )

    def test_a_missing_attachment_does_not_sink_the_submission(self, db):
        # An id that no longer resolves is a nuisance. Refusing the complaint over it
        # loses the report AND the file.
        complaint_id = unique_code("cmp")
        good = str(_attachment(db).id)

        linked = link_uploads_to_entity(
            db,
            entity_type="complaint",
            entity_id=complaint_id,
            attachment_ids=["00000000-0000-0000-0000-000000000000", good],
        )

        assert linked == [good]

    def test_nothing_uploaded_is_not_an_error(self, db):
        assert link_uploads_to_entity(
            db, entity_type="complaint", entity_id=unique_code("cmp"), attachment_ids=[]
        ) == []


class TestWhichFileIsTheProof:
    def test_an_explicit_choice_wins(self):
        assert (
            _proof_attachment_id(
                {"proof_attachment_id": "chosen", "attachment_ids": ["a", "b"]}
            )
            == "chosen"
        )

    def test_one_upload_is_unambiguous(self):
        # There is nothing else it could be, so the purchase points at the receipt its
        # date was read from and CS can open it.
        assert _proof_attachment_id({"attachment_ids": ["only"]}) == "only"

    def test_two_uploads_name_no_proof(self):
        """A consumer photographs the receipt AND the crack. Nothing here can tell which.

        `proof_attachment_id` is read as evidence, so a guess files a photo of a bathroom
        floor as proof of purchase. Null means "CS attaches it", which is a task somebody
        does. A wrong one is a wrong record nobody knows to check.
        """
        assert _proof_attachment_id({"attachment_ids": ["a", "b"]}) is None

    def test_no_uploads_names_no_proof(self):
        assert _proof_attachment_id({}) is None
        assert _proof_attachment_id({"attachment_ids": [], "proof_attachment_id": ""}) is None

    def test_blank_entries_are_not_counted_as_a_file(self):
        # Otherwise a payload carrying one real id and one empty string reads as
        # "ambiguous" and silently drops the proof.
        assert _proof_attachment_id({"attachment_ids": ["real", "  "]}) == "real"


class TestTheAcknowledgement:
    """The "All done" screen is not an acknowledgement.

    A consumer closes the tab and an hour later has nothing: no number, no thread, no way
    back in. The receipt they photographed is on our side of a form they can no longer
    see. A message carrying the reference is the thing they keep.
    """

    def test_it_quotes_the_reference_the_consumer_will_be_asked_for(self):
        from app.models.complaints import Complaint
        from app.services.consumer_lodge_service import acknowledgement_text

        text = acknowledgement_text(Complaint(complaint_number="CMP2026-0027"))
        assert "CMP2026-0027" in text

    def test_it_still_says_something_when_numbering_failed(self):
        # Numbering is best-effort (an unconfigured rule must not block a lodgement), so a
        # complaint can genuinely have no number. "Reference None" would be worse than a
        # message with no reference at all.
        from app.models.complaints import Complaint
        from app.services.consumer_lodge_service import acknowledgement_text

        text = acknowledgement_text(Complaint(complaint_number=None))
        assert "None" not in text
        assert "your report" in text

    def test_it_states_no_warranty_verdict(self):
        """Cover is assessed from a purchase date that is often unreadable at this moment.

        A verdict delivered by message reads as a decision rather than a first guess CS
        may correct, and taking one back is worse than never sending it.
        """
        from app.models.complaints import Complaint
        from app.services.consumer_lodge_service import acknowledgement_text

        text = acknowledgement_text(Complaint(complaint_number="CMP2026-0027")).lower()
        for word in ("covered", "not covered", "expired", "warranty is"):
            assert word not in text

    def test_a_complaint_with_no_contact_is_not_an_error(self, db):
        # Portal lodgements always have a contact; the WhatsApp track may not. Neither is
        # a reason to fail a complaint that is already committed.
        from app.models.complaints import Complaint
        from app.services.consumer_lodge_service import _acknowledge

        _acknowledge(db, Complaint(id="x", complaint_number="ZZT-1", contact_id=None))
