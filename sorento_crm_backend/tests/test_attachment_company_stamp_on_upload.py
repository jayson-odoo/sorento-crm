"""An owned attachment must carry the company the uploader was switched INTO.

Real production report: a packing list uploaded while switched to Mocha came back
belonging to nobody. ``Attachment`` is ``__company_shared__``, so
``_stamp_company_id`` (company_scope.py) short-circuits on ``_is_shared`` BEFORE it
ever reads the session scope - every upload in every company landed with
``company_id`` NULL.

For attachments NULL is not neutral, it means SHARED: the predicate is
``company_id IS NULL OR company_id IN (scope)``, so the Mocha file was visible from
Sorento too. Worse, ``scope_to_attachment_company`` pins the n8n binding scope off
this exact column - a NULL left the X-API-Key scope at None, so the inbound shipment
n8n then created stamped ``DEFAULT_COMPANY_ID`` (Sorento) while holding Mocha
products.

The rule is the other way around: anything uploaded while exactly one company is
active belongs to that company, folder or not, EXCEPT the shared form entity types
(complaint, purchase_request, stock_inquiry) which stay NULL so they remain readable
from every company (AC-G3). An ambiguous scope (UNSET, all-companies, or several
companies) still stamps nothing - a wrong guess is worse than shared.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import UNSET, set_company_scope
from app.models.company import Company
from app.models.resources import AttachmentDirectory, AttachmentType
from app.schemas.resources import AttachmentCreate
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.resources_service import AttachmentService

from ._pg_fixture import blank_session, unique_code

MOCHA_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        session.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        session.flush()
        yield session


def _att_type(db) -> str:
    # type_name carries a UNIQUE constraint, so every call needs its own.
    row = AttachmentType(
        id=str(uuid.uuid4()), type_name=unique_code("Packing List")[:50],
        allowed_extensions="xlsx", max_file_size_mb=10,
    )
    db.add(row)
    db.flush()
    return row.id


def _directory(db) -> str:
    """A folder under whatever single company is active, else shared (None).

    `AttachmentDirectory` is `__company_shared__` (PLAN-shared-brand-
    attachments R17), so the before_insert auto-stamp never fills this in -
    this mirrors what `AttachmentDirectoryService.create_directory` now does
    for a root folder, so a raw ORM build here still lands owned the same way
    a real create call would.
    """
    from app.models.base import get_company_scope

    scope = get_company_scope(db)
    company_id = next(iter(scope)) if isinstance(scope, frozenset) and len(scope) == 1 else None
    row = AttachmentDirectory(id=str(uuid.uuid4()), name="Testing", company_id=company_id)
    db.add(row)
    db.flush()
    return row.id


def _payload(db, **overrides) -> AttachmentCreate:
    data = dict(
        id=str(uuid.uuid4()),
        attachment_type_id=_att_type(db),
        original_filename="TGHU6295708 - WH M.xlsx",
        stored_filename="TGHU6295708 - WH (M).xlsx",
        file_path="https://cdn.test/packing_list/x/TGHU6295708.xlsx",
        file_size_bytes=17007,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_hash=uuid.uuid4().hex,
        storage_provider="r2",
    )
    data.update(overrides)
    return AttachmentCreate(**data)


def _upload(db, payload) -> object:
    return AttachmentService(db).create_attachment(payload, str(uuid.uuid4()))


# --- the defect ------------------------------------------------------------- #

def test_folder_upload_while_switched_to_mocha_belongs_to_mocha(db):
    """The reported case: a file uploaded into a folder from the Mocha workspace."""
    set_company_scope(db, frozenset({MOCHA_ID}))

    attachment = _upload(db, _payload(db, directory_id=_directory(db)))

    assert attachment.company_id == MOCHA_ID, (
        "an owned upload was left company-less, so it is shared across every "
        "company and n8n binds anything derived from it to the incumbent company"
    )


def test_the_same_upload_under_sorento_belongs_to_sorento(db):
    """Not hardcoded to one company - it follows whichever company is active."""
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    attachment = _upload(db, _payload(db, directory_id=_directory(db)))

    assert attachment.company_id == DEFAULT_COMPANY_ID


def test_root_upload_without_a_folder_belongs_to_the_active_company(db):
    """The 17 Aug packing list: ``CMAU4318062 - WH.xlsx`` was dropped at the root of
    All files (no folder, no entity) while switched into a company, and the folder
    gate short-circuited before the scope was ever read, so it landed shared."""
    set_company_scope(db, frozenset({MOCHA_ID}))

    attachment = _upload(db, _payload(db))

    assert attachment.company_id == MOCHA_ID, (
        "a root upload was left company-less, so it is shared across every company"
    )


def test_root_upload_under_sorento_belongs_to_sorento(db):
    """Again, it follows whichever company is active, not a hardcoded one."""
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    attachment = _upload(db, _payload(db))

    assert attachment.company_id == DEFAULT_COMPANY_ID


def test_promotion_attachment_is_owned_too(db):
    set_company_scope(db, frozenset({MOCHA_ID}))

    attachment = _upload(
        db, _payload(db, entity_type="promotion", entity_id=str(uuid.uuid4()))
    )

    assert attachment.company_id == MOCHA_ID


# --- what must NOT change --------------------------------------------------- #

def test_a_form_attachment_stays_shared(db):
    """Complaint / PR / stock-inquiry attachments are deliberately company-less so
    they stay readable from every company (AC-G3). Stamping them would hide them."""
    set_company_scope(db, frozenset({MOCHA_ID}))

    for entity_type in ("complaint", "purchase_request", "stock_inquiry", "Complaint"):
        attachment = _upload(
            db, _payload(db, entity_type=entity_type, entity_id=str(uuid.uuid4()))
        )
        assert attachment.company_id is None, (
            f"a {entity_type!r} attachment was stamped, so it is now invisible from "
            "every other company"
        )


def test_an_ambiguous_scope_is_never_guessed(db):
    """All-companies (n8n X-API-Key with no contact identity) and UNSET must leave
    NULL rather than pick a company - a wrong guess is worse than shared."""
    # Build the folder under a valid scope first: AttachmentDirectory is strictly
    # owned (not shared), so creating one under an ambiguous scope is itself a 400.
    set_company_scope(db, frozenset({MOCHA_ID}))
    directory_id = _directory(db)

    for scope in (None, UNSET, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID})):
        set_company_scope(db, scope)
        attachment = _upload(db, _payload(db, directory_id=directory_id))
        assert attachment.company_id is None, f"scope {scope!r} was guessed at"

        at_root = _upload(db, _payload(db))
        assert at_root.company_id is None, f"scope {scope!r} was guessed at, at root"
