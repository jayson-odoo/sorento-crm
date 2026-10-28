"""RESUBMITTED-STATUS for dealer-kit Editions (status graph: resubmitted stands in for
pending_approval). A Designer who reopens a rejected Edition and sends it again lands on
`resubmitted`; the Approver decides it exactly as a pending one, and it keeps the page's one
open slot. Plan: documentation/plans/forms/PLAN-resubmitted-status-27oct.md.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from app.models.dealer_kit import Page, PageVersion
from app.services.dealer_kit import edition_service, page_service
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session, unique_code

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"mig_{name}", _VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mig318 = _load("318_dealer_kit_edition")
resub = _load("resub_0001_resubmitted_status")

USER = str(uuid.uuid4())
APPROVER = str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as session:
        mig318._seed_graph(session.connection())
        resub.seed_resubmitted_rungs(session.connection())
        session.flush()
        yield session


def _page(db) -> Page:
    page = Page(id=str(uuid.uuid4()), name=unique_code("ZZT Edition Page"), slug=unique_code("zzt-ed").lower())
    db.add(page)
    db.flush()
    db.add(PageVersion(id=str(uuid.uuid4()), page_id=page.id, version=1, doc={"sections": []}, created_by=USER))
    db.flush()
    return page


def _resubmitted(db, page=None):
    page = page or _page(db)
    edition = edition_service.create_edition(db, page_id=page.id, name=unique_code("ZZT Edition"), user_id=USER)
    edition_service.submit(db, edition.id, user_id=USER)
    edition_service.reject(db, edition.id, reason="Prices on page 4 are wrong", user_id=APPROVER)
    edition_service.reopen(db, edition.id, user_id=USER)
    return edition_service.submit(db, edition.id, user_id=USER)


def test_a_first_submit_is_pending_approval(db):
    edition = edition_service.create_edition(db, page_id=_page(db).id, name=unique_code("ZZT"), user_id=USER)
    assert edition_service.submit(db, edition.id, user_id=USER).status_key == "pending_approval"


def test_sending_a_rejected_edition_again_is_resubmitted(db):
    edition = _resubmitted(db)
    assert edition.status_key == "resubmitted"
    assert edition.rejection_reason is None


def test_a_resubmitted_edition_is_approved_like_a_pending_one(db):
    edition = _resubmitted(db)
    assert edition_service.approve(db, edition.id, user_id=APPROVER).status_key == "approved"


def test_a_resubmitted_edition_can_be_rejected_again(db):
    edition = _resubmitted(db)
    assert edition_service.reject(db, edition.id, reason="Still wrong", user_id=APPROVER).status_key == "rejected"


def test_a_resubmitted_edition_keeps_the_pages_one_open_slot(db):
    page = _page(db)
    _resubmitted(db, page)
    with pytest.raises(AppException) as caught:
        edition_service.create_edition(db, page_id=page.id, name=unique_code("ZZT"), user_id=USER)
    assert caught.value.status_code == 409


def test_publishing_around_a_resubmitted_edition_says_it_waits_for_approval(db):
    edition = _resubmitted(db)
    assert "waiting for approval" in page_service._bypass_message(edition)
