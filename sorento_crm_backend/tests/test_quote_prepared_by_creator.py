"""QUOTE-ATTN-PICKER owner ruling (11 Nov 2026): "prepared by should always be the one who create,
this is compliance". Prepared By is the document's creator (``created_by``), never the project
owner, on the document response, the cover page (legacy row and the Prepared by name/phone
sources) and the spec sheet. The Salesperson sources keep the project owner.

Seed: a project owned by one salesperson, a quotation created by ANOTHER. Postgres only via
``blank_session``; every row carries the shared ``zzt-`` markers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from ._pg_fixture import blank_session
from .test_project_quotation_cover_page import MARKER, _full_document
from .test_project_quotation_pdf import _issue, _setup, _user


def _creator(db, env, document):
    """Hand the document to a second salesperson, its creator; the project owner stays."""
    from app.models.user import User

    creator_id = _user(db, f"{MARKER} Creator Chan")
    creator = db.query(User).filter(User.id == creator_id).first()
    creator.contact_number = "012-000 0777"
    document.created_by = creator_id
    db.flush()
    return creator


def test_document_prepared_by_is_the_creator_not_the_project_owner():
    from app.services.project_quotation_document_service import _prepared_by

    with blank_session() as db:
        env = _setup(db)
        document = _full_document(db, env)
        creator = _creator(db, env, document)
        assert _prepared_by(db, document) == creator.name


def test_cover_prepared_by_row_and_sources_are_the_creator():
    from app.models.user import User
    from app.services.quotation_cover_service import issue_values, source_values

    with blank_session() as db:
        env = _setup(db)
        document = _full_document(db, env)
        record = _issue(db, document, env["owner"])
        creator = _creator(db, env, document)
        owner = db.query(User).filter(User.id == env["owner"]).first()

        assert issue_values(db, document, record)["prepared_by"] == creator.name
        values = source_values(db, document, record)
        assert values["prepared_by_name"] == creator.name
        assert values["prepared_by_phone"] == "012-000 0777"
        # The salesperson is still the project's owner.
        assert values["salesperson_name"] == owner.name


def test_a_legacy_prepared_by_row_prints_the_creator():
    from app.services.quotation_cover_service import _LEGACY_SOURCE

    assert _LEGACY_SOURCE["prepared_by"] == "prepared_by_name"


def test_a_document_without_a_known_creator_prints_no_prepared_by():
    from app.services.project_quotation_document_service import _prepared_by

    with blank_session() as db:
        env = _setup(db)
        document = _full_document(db, env)
        document.created_by = None
        db.flush()
        assert _prepared_by(db, document) is None


def test_spec_sheet_prepared_by_is_the_creator():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        env = _setup(db)
        document = _full_document(db, env)
        creator = _creator(db, env, document)
        # A draft sheet: no issue yet, items taken now.
        sheet = SimpleNamespace(issue_id=None, items_taken_at=datetime.now(timezone.utc))
        fields = spec._doc_fields(db, document, sheet)
        assert fields["prepared_by"] == creator.name
        assert fields["prepared_by_phone"] == "012-000 0777"
