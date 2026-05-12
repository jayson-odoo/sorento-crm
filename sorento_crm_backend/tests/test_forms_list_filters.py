"""FormService.list_forms filter/search behavior.

Postgres-only filters (``?|`` against JSONB ``access_levels``) are exercised
elsewhere — here we cover SQL paths that translate cleanly to SQLite:

  * ``form_type`` exact match (lowercased)
  * search query matches form code/name AND linked attachment filename
  * ``contact_access_codes=[]`` short-circuits to no results (the
    ``text("false")`` branch — no JSONB op invoked)
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.audit import AuditLog
from app.models.forms import Form
from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.models.resources import (
    Attachment,
    AttachmentDirectory,
    AttachmentType,
)
from app.services.forms_service import FormService


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(_element, _compiler, **_kw):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AttachmentDirectory.__table__,
            AttachmentType.__table__,
            Attachment.__table__,
            Form.__table__,
            LookupSet.__table__,
            LookupOption.__table__,
            LookupBinding.__table__,
            AuditLog.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_attachment(db, filename: str) -> str:
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"/tmp/{filename}",
        access_levels=["dealer"],
    )
    db.add(att)
    db.flush()
    return att.id


def _seed_form(
    db,
    *,
    code: str,
    name: str,
    form_type: str = "marketing",
    attachment_id: str | None = None,
    access_levels: list[str] | None = None,
) -> str:
    form = Form(
        id=str(uuid.uuid4()),
        code=code,
        name=name,
        form_type=form_type,
        language="en",
        version=1,
        is_active=True,
        attachment_id=attachment_id,
        access_levels=access_levels or ["dealer"],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(form)
    db.flush()
    return form.id


def test_form_type_filter_returns_only_matching_type(db):
    marketing_id = _seed_form(db, code="M1", name="Marketing 1", form_type="marketing")
    _seed_form(db, code="S1", name="Service 1", form_type="service")
    db.commit()

    result = FormService(db).list_forms(form_type="marketing")
    ids = [f.id for f in result["data"]]
    assert ids == [marketing_id]


def test_form_type_all_value_returns_all_rows(db):
    a = _seed_form(db, code="M1", name="Marketing 1", form_type="marketing")
    b = _seed_form(db, code="S1", name="Service 1", form_type="service")
    db.commit()

    result = FormService(db).list_forms(form_type="all")
    ids = {f.id for f in result["data"]}
    assert ids == {a, b}


def test_search_matches_linked_attachment_filename(db):
    att_id = _seed_attachment(db, "warranty-claim-template.pdf")
    matching_id = _seed_form(db, code="WC1", name="Warranty Claim", attachment_id=att_id)
    _seed_form(db, code="OTHER", name="Other form")
    db.commit()

    result = FormService(db).list_forms(query="warranty-claim-template")
    ids = [f.id for f in result["data"]]
    assert matching_id in ids


def test_search_matches_form_code(db):
    target = _seed_form(db, code="FEEDBACK_2026", name="Feedback Q1")
    _seed_form(db, code="MARKETING_2026", name="Marketing form")
    db.commit()

    result = FormService(db).list_forms(query="feedback_2026")
    ids = [f.id for f in result["data"]]
    assert ids == [target]


def test_empty_contact_access_codes_returns_no_forms(db):
    _seed_form(db, code="F1", name="Form 1")
    _seed_form(db, code="F2", name="Form 2")
    db.commit()

    result = FormService(db).list_forms(contact_access_codes=[])
    assert result["data"] == []
    assert result["empty"] is True
