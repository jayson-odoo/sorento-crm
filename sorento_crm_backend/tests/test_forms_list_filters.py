"""FormService.list_forms filter/search behavior.

Covers:

  * ``form_type`` exact match (lowercased)
  * search query matches form code/name AND linked attachment filename
  * ``contact_access_codes=[]`` short-circuits to no results (the
    ``text("false")`` branch — no JSONB op invoked)

Runs on Postgres, so ``access_levels`` is real JSONB rather than the sqlite
stand-in the file used to register a global ``@compiles`` hook for.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.models.forms import Form
from app.models.resources import Attachment
from app.services.forms_service import FormService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


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
