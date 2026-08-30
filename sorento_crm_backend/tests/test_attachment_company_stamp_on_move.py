"""Filing an old root file into a folder must give it that folder's company.

The upload-side fix (test_attachment_company_stamp_on_upload.py) is create-only:
it stamps the active company at the moment the file is written. Every file that
already sat at the root of All files from before that fix still carries
``company_id`` NULL, and for attachments NULL is not neutral, it means SHARED
(the predicate is ``company_id IS NULL OR company_id IN (scope)``). Dragging one
of those into Purchasing used to touch ``directory_id`` and
``full_directory_path`` only, so the file looked filed but stayed readable from
every company, and ``scope_to_attachment_company`` still resolved None off it.

``AttachmentDirectory`` is strictly owned - its ``company_id`` is always set - so
the folder the user picked is an exact source for the missing company, no scope
guessing needed. The rule: on a move INTO a folder, a NULL attachment inherits
the folder's company, unless it is one of the shared form entity types
(complaint, purchase_request, stock_inquiry) which stay NULL on purpose (AC-G3).
An existing company is never overwritten, and a move to root stamps nothing.

The one folder that cannot answer the question is a folder whose own company_id
is NULL (it reads as invisible under a single-company scope, since owned rows are
filtered ``company_id IN (ids)``). There the move falls back to the active scope
exactly as an upload does: a single active company, or nothing.
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


# --- the defect ------------------------------------------------------------- #

def test_bulk_move_into_a_folder_stamps_a_company_less_file(db):
    """The reported case: an old root file dragged into a Purchasing folder."""
    set_company_scope(db, None)  # ambiguous at upload time -> lands NULL
    attachment = _upload(db, _payload(db))
    assert attachment.company_id is None, "fixture precondition: the file is shared"

    folder_id = _mocha_folder(db)

    set_company_scope(db, frozenset({MOCHA_ID}))
    moved = AttachmentService(db).bulk_move([attachment.id], folder_id)

    assert moved == 1
    assert _company_id(db, attachment.id) == MOCHA_ID, (
        "a file filed into an owned folder stayed company-less, so it is still "
        "shared across every company"
    )


def test_update_attachment_directory_stamps_a_company_less_file(db):
    """Same rule down the single-row edit path, not just bulk move."""
    set_company_scope(db, None)
    attachment = _upload(db, _payload(db))
    assert attachment.company_id is None

    folder_id = _mocha_folder(db)

    set_company_scope(db, frozenset({MOCHA_ID}))
    AttachmentService(db).update_attachment(
        attachment.id, AttachmentUpdate(directory_id=folder_id)
    )

    assert _company_id(db, attachment.id) == MOCHA_ID, (
        "editing directory_id filed the file without giving it the folder's company"
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


# --- the folder that cannot answer ------------------------------------------ #

def test_a_company_less_folder_falls_back_to_the_active_company(db):
    """No company to copy off the folder, so the move stamps the one company the
    user is actually working in - the same rule an upload uses."""
    set_company_scope(db, None)
    attachment = _upload(db, _payload(db))
    assert attachment.company_id is None

    folder_id = _company_less_folder(db)

    set_company_scope(db, frozenset({MOCHA_ID}))
    AttachmentService(db).bulk_move([attachment.id], folder_id)

    assert _company_id(db, attachment.id) == MOCHA_ID, (
        "a file filed into a company-less folder stayed shared even though exactly "
        "one company was active"
    )


def test_a_company_less_folder_under_an_ambiguous_scope_stamps_nothing(db):
    """Nothing exact to copy AND no single active company: a wrong guess is worse
    than shared, so the file stays NULL."""
    set_company_scope(db, None)
    attachment = _upload(db, _payload(db))
    assert attachment.company_id is None

    folder_id = _company_less_folder(db)

    set_company_scope(db, None)
    AttachmentService(db).bulk_move([attachment.id], folder_id)

    assert _company_id(db, attachment.id) is None, (
        "an all-companies move guessed a company off nothing"
    )
