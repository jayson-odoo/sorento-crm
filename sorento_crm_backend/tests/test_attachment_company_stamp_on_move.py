"""A move never re-stamps a file's company (PLAN-shared-brand-attachments R10).

This file used to test the OPPOSITE rule: that filing a company-less (shared)
root file into an owned folder gave it that folder's company, the same way an
upload does. R10 retires that inheritance - "Company is decided ONCE at
upload... and afterwards only by the `Set company…` action. A move never
re-stamps a company." - because a shared/company-less attachment is now a
DELIBERATE state (R11: an `is_shared` attachment TYPE writes it on purpose),
not just a legacy hole to fill in on the first folder that comes along.

What a move does instead when the file being moved is shared and the
destination folder is owned: pull that folder's ANCESTOR CHAIN to shared
(R19), so the folder tree the file lives under still resolves from every
company (`AttachmentCompanyService.share_ancestor_chain`, AC-D3/AC-D4 -
UAC coverage for that lands separately). This file only pins the FILE's own
`company_id` never changing on a move, plus the pre-existing "an existing
company is never overwritten" / "a move to root stamps nothing" / "shared
form attachments stay shared" invariants, none of which R10 touches.
"""
from __future__ import annotations

import uuid

from app.models.base import set_company_scope
from app.models.resources import Attachment, AttachmentDirectory
from app.schemas.resources import AttachmentUpdate
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.resources_service import AttachmentService

from .test_attachment_company_stamp_on_upload import (  # noqa: F401
    MOCHA_ID,
    _att_type,
    _directory,
    _payload,
    _scope_listeners,
    _upload,
    db,
)

BOTH = frozenset({DEFAULT_COMPANY_ID, MOCHA_ID})


def _company_id(db, attachment_id: str) -> str | None:
    """Read the stored company under a scope wide enough to see either company."""
    set_company_scope(db, BOTH)
    db.expire_all()
    row = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    assert row is not None, "the attachment vanished from a two-company scope"
    return row.company_id


def _mocha_folder(db) -> str:
    # AttachmentDirectory is owned, so it must be created under exactly one
    # company; the folder then carries that company.
    set_company_scope(db, frozenset({MOCHA_ID}))
    return _directory(db)


def _company_less_folder(db) -> str:
    """A legacy folder that never got a company of its own."""
    folder_id = _mocha_folder(db)
    folder = db.query(AttachmentDirectory).filter(AttachmentDirectory.id == folder_id).first()
    folder.company_id = None
    db.flush()
    return folder_id


# --- R10: a move never re-stamps a file's own company ----------------------- #

def test_bulk_move_into_a_folder_no_longer_stamps_a_shared_file(db):
    """A shared root file dragged into an owned folder STAYS shared (R10) - the
    old inheritance this file used to pin is retired."""
    set_company_scope(db, None)  # ambiguous at upload time -> lands NULL
    attachment = _upload(db, _payload(db))
    assert attachment.company_id is None, "fixture precondition: the file is shared"

    folder_id = _mocha_folder(db)

    set_company_scope(db, frozenset({MOCHA_ID}))
    moved = AttachmentService(db).bulk_move([attachment.id], folder_id)

    assert moved == 1
    assert _company_id(db, attachment.id) is None, (
        "a move re-stamped a shared file's own company, which R10 retires - "
        "only `Set company…` may do that now"
    )


def test_update_attachment_directory_no_longer_stamps_a_shared_file(db):
    """Same rule down the single-row edit path, not just bulk move."""
    set_company_scope(db, None)
    attachment = _upload(db, _payload(db))
    assert attachment.company_id is None

    folder_id = _mocha_folder(db)

    set_company_scope(db, frozenset({MOCHA_ID}))
    AttachmentService(db).update_attachment(
        attachment.id, AttachmentUpdate(directory_id=folder_id)
    )

    assert _company_id(db, attachment.id) is None, (
        "editing directory_id re-stamped a shared file's own company (R10)"
    )


# --- what must NOT change --------------------------------------------------- #

def test_move_never_overwrites_an_existing_company(db):
    """Inheritance fills a hole; it never re-homes a file that already belongs."""
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    attachment = _upload(db, _payload(db))
    assert attachment.company_id == DEFAULT_COMPANY_ID

    folder_id = _mocha_folder(db)

    set_company_scope(db, BOTH)
    AttachmentService(db).bulk_move([attachment.id], folder_id)

    assert _company_id(db, attachment.id) == DEFAULT_COMPANY_ID, (
        "a Sorento file was re-homed to Mocha by a move, which hides it from its "
        "own company"
    )


def test_move_to_root_leaves_company_alone(db):
    """Root is not a folder, so there is nothing to inherit from."""
    set_company_scope(db, None)
    attachment = _upload(db, _payload(db, directory_id=None))
    assert attachment.company_id is None

    set_company_scope(db, frozenset({MOCHA_ID}))
    AttachmentService(db).bulk_move([attachment.id], None)

    assert _company_id(db, attachment.id) is None, (
        "a move to root guessed a company off the active scope"
    )


def test_form_attachment_stays_shared_after_a_move(db):
    """Complaint / PR / stock-inquiry attachments stay readable from every
    company (AC-G3); filing one away must not hide it."""
    set_company_scope(db, None)
    attachment = _upload(
        db, _payload(db, entity_type="complaint", entity_id=str(uuid.uuid4()))
    )
    assert attachment.company_id is None

    folder_id = _mocha_folder(db)

    set_company_scope(db, frozenset({MOCHA_ID}))
    AttachmentService(db).bulk_move([attachment.id], folder_id)

    assert _company_id(db, attachment.id) is None, (
        "a complaint attachment was stamped by a move, so it is now invisible "
        "from every other company"
    )


# --- a company-less folder no longer answers anything (R10) ----------------- #

def test_a_company_less_folder_no_longer_stamps_a_file_moved_into_it(db):
    """R10: a move never consults the destination folder for a company to
    copy, company-less or not - the file stays exactly as shared as it was."""
    set_company_scope(db, None)
    attachment = _upload(db, _payload(db))
    assert attachment.company_id is None

    folder_id = _company_less_folder(db)

    set_company_scope(db, frozenset({MOCHA_ID}))
    AttachmentService(db).bulk_move([attachment.id], folder_id)

    assert _company_id(db, attachment.id) is None, (
        "a move re-stamped a file off a company-less folder, which R10 retires"
    )


def test_a_company_less_folder_under_an_ambiguous_scope_stamps_nothing(db):
    """Same outcome under an ambiguous (all-companies) scope: still nothing to
    guess, since a move stamps nothing regardless (R10)."""
    set_company_scope(db, None)
    attachment = _upload(db, _payload(db))
    assert attachment.company_id is None

    folder_id = _company_less_folder(db)

    set_company_scope(db, None)
    AttachmentService(db).bulk_move([attachment.id], folder_id)

    assert _company_id(db, attachment.id) is None, (
        "an all-companies move guessed a company off nothing"
    )
