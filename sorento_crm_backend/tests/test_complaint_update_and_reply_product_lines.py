"""Update & Reply must accept `product_lines`, like a plain update does.

`ComplaintUpdate.model_dump()` returns `product_lines` as a list of plain dicts.
`update_complaint` pops that key and routes it through
`_apply_explicit_product_lines`; `update_complaint_and_reply` did not, so its
`setattr(complaint, key, value)` loop assigned a list of dicts straight onto the
ORM relationship and the request died with

    'dict' object has no attribute '_sa_instance_state'

The complaint EDIT page sends the full payload, product lines included, so its
"Update & Reply" button 500'd for every complaint that has a product row - while
the same button in the detail-page response modal worked, because that payload
carries no lines. Found in a browser run on CMP2026-0031.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.complaints import Complaint
from app.schemas.complaints import ComplaintUpdate
from app.services.complaints_service import ComplaintService

MARKER = "CMPUARPL"


@pytest.fixture(autouse=True)
def _clean_state():
    """Delete only this test's own rows - the dev DB is a copy of production."""
    def _purge():
        with engine.connect() as conn:
            try:
                conn.execute(
                    text(
                        "DELETE FROM complaint_product_lines WHERE complaint_id IN "
                        "(SELECT id FROM complaints WHERE complaint_number LIKE :p)"
                    ),
                    {"p": f"{MARKER}-%"},
                )
                conn.execute(
                    text("DELETE FROM complaints WHERE complaint_number LIKE :p"),
                    {"p": f"{MARKER}-%"},
                )
                conn.commit()
            except Exception:
                conn.rollback()

    _purge()
    yield
    _purge()


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def complaint(db: Session) -> Complaint:
    row = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        customer_name=f"{MARKER} customer",
        status="submitted",
        technical_team_response=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_update_and_reply_accepts_product_lines(db: Session, complaint: Complaint):
    """The payload the edit page actually sends - lines included - must succeed and
    persist the lines, not raise on the relationship assignment."""
    svc = ComplaintService(db)

    updated = svc.update_complaint_and_reply(
        str(complaint.id),
        ComplaintUpdate(
            technical_team_response="ZZT reply body",
            product_lines=[{"product_code": "ZZT-A", "quantity": "2", "product_type": "WC"}],
        ),
        respond_user_id="zzt-user",
    )

    assert updated.status == "responded"
    assert updated.technical_team_response == "ZZT reply body"
    lines = [(l.product_code, l.quantity) for l in updated.product_lines]
    assert lines == [("ZZT-A", "2")]
