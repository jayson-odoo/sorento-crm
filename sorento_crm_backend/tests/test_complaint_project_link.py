"""S6b - linking a complaint to a registered project (UAC AC-L3).

Same shape as the sponsorship link in S4, and for the same reason: complaints already carry a
free-text `project_title` that nobody can report on. The nullable FK adds the reportable link
WITHOUT taking the text away, because ~every historical row has only the text and a fuzzy
backfill would invent links nobody checked.

Three properties are pinned:

* the link is optional and stays optional (a complaint about a retail delivery has no project);
* deleting a project does not delete its complaints, it just unlinks them;
* the UI gets a project CODE, never a UUID -- the FE rule is absolute, and the serializer is
  where it is either honoured or lost.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-s6b"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _complaint(db, **kwargs):
    from app.models.complaints import Complaint

    row = Complaint(
        id=_uid(),
        complaint_number=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        complaint_date=date.today(),
        defect_description=f"{MARKER} cracked basin",
        status="submitted",
        **kwargs,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def linked():
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=None,
            title=f"{MARKER} Residensi Linked",
            owner_user_id=owner,
        )
        db.flush()
        yield db, project, owner


def test_a_complaint_can_carry_a_project_link(linked):
    db, project, _owner = linked
    complaint = _complaint(db, project_id=str(project.id))
    db.flush()
    db.refresh(complaint)
    assert str(complaint.project_id) == str(project.id)


def test_the_link_is_optional(linked):
    """A complaint about a retail delivery has no project, and never will. Making the column
    required would force somebody to invent one."""
    db, _project, _owner = linked
    complaint = _complaint(db)
    db.flush()
    assert complaint.project_id is None


def test_the_free_text_project_title_survives_alongside_the_link(linked):
    """AC-F6's rule, applied here: the text is what every historical row has, and it stays as
    the display fallback. Dropping it during this migration would erase the only project
    information on thousands of complaints."""
    db, project, _owner = linked
    complaint = _complaint(
        db, project_id=str(project.id), project_title="RESIDENSI LINKED PHASE 2"
    )
    db.flush()
    assert complaint.project_title == "RESIDENSI LINKED PHASE 2"
    assert complaint.project_id is not None


def test_deleting_a_project_unlinks_the_complaint_rather_than_deleting_it(linked):
    """ON DELETE SET NULL, deliberately. A complaint is a customer's problem and a legal
    record: it must outlive the pursuit it happened to be attached to."""
    from app.models.complaints import Complaint

    db, project, _owner = linked
    complaint = _complaint(db, project_id=str(project.id), project_title="KEEP ME")
    db.flush()
    complaint_id = complaint.id

    db.delete(project)
    db.flush()
    # The SET NULL happens in the DATABASE, so the identity-mapped complaint has to be
    # expired before reading it -- otherwise this asserts against a stale in-session copy.
    db.expire_all()

    survivor = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    assert survivor is not None, "the complaint was deleted with its project"
    assert survivor.project_id is None
    assert survivor.project_title == "KEEP ME"


def test_the_serializer_sends_a_project_code_never_a_bare_uuid(linked):
    """The no-UUIDs-in-the-UI rule is enforced here or nowhere: the FE renders what this
    dict contains, and `project_id` alone would put a UUID on screen."""
    from app.services.complaints_service import ComplaintService

    db, project, _owner = linked
    complaint = _complaint(db, project_id=str(project.id))
    db.flush()

    data = ComplaintService(db)._serialize_complaint(complaint)
    assert data["project_id"] == str(project.id)
    assert data["project_code"] == project.project_code
    assert data["project_name"] == project.title


def test_an_unlinked_complaint_serializes_without_pretending(linked):
    from app.services.complaints_service import ComplaintService

    db, _project, _owner = linked
    complaint = _complaint(db, project_title="SOME DEVELOPMENT")
    db.flush()

    data = ComplaintService(db)._serialize_complaint(complaint)
    assert data["project_id"] is None
    assert data["project_code"] is None
    assert data["project_name"] is None
    # The typed text is still there, so the FE can show what it has.
    assert data["project_title"] == "SOME DEVELOPMENT"


def test_a_purchase_request_read_carries_the_project_code(linked):
    """AC-L3's other half. The portal already resolved the code for contacts; the office-side
    read did not, so the same link rendered as a code in one place and as nothing in the
    other -- which reads as a broken link rather than as two code paths."""
    from app.models.procurement import PurchaseRequestHeader
    from app.services.procurement_service import PurchaseRequestService

    db, project, _owner = linked
    header = PurchaseRequestHeader(
        id=_uid(),
        request_type="sponsorship_form",
        request_number=f"{MARKER}-SF-1",
        project_title="BANDAR MUTIARA TOWER",
        project_id=str(project.id),
        status="submitted",
    )
    db.add(header)
    db.flush()

    fetched = PurchaseRequestService(db).get_request(str(header.id))
    assert fetched.project_code == project.project_code
    assert fetched.project_title == "BANDAR MUTIARA TOWER"


def test_an_unlinked_purchase_request_reports_no_code(linked):
    from app.models.procurement import PurchaseRequestHeader
    from app.services.procurement_service import PurchaseRequestService

    db, _project, _owner = linked
    header = PurchaseRequestHeader(
        id=_uid(),
        request_type="purchase_request",
        request_number=f"{MARKER}-PR-1",
        project_title="SOME DEVELOPMENT",
        status="submitted",
    )
    db.add(header)
    db.flush()

    fetched = PurchaseRequestService(db).get_request(str(header.id))
    assert fetched.project_code is None


def test_the_complaints_list_resolves_every_project_in_one_query(linked):
    """This serializer's override convention exists because a 50-row page used to fire per-row
    view-token, user and SLA queries. The S6b project resolve was added straight into the
    serializer and re-introduced exactly that: one SELECT per linked complaint.

    Pinned as a RATIO -- more linked rows must not mean more queries -- so a legitimate new
    query elsewhere does not fail the test.
    """
    from sqlalchemy import event

    from app.services.complaints_service import ComplaintService

    db, project, _owner = linked
    service = ComplaintService(db)
    engine = db.get_bind()

    def _count_after_adding(rows: int) -> int:
        for _ in range(rows):
            _complaint(db, project_id=str(project.id))
        db.flush()
        seen: list[str] = []

        def _tap(_conn, _cur, statement, *_a, **_k):
            seen.append(statement)

        event.listen(engine, "before_cursor_execute", _tap)
        try:
            service.list_complaints(page=1, limit=50)
        finally:
            event.remove(engine, "before_cursor_execute", _tap)
        return len(seen)

    two_rows = _count_after_adding(2)
    six_rows = _count_after_adding(4)
    assert six_rows <= two_rows, (
        f"query count grew with the number of linked complaints ({two_rows} -> {six_rows})"
    )


def test_a_listed_complaint_still_carries_its_project_code(linked):
    """The batch must produce the same answer the per-row lookup did, including for a row with
    no link at all -- otherwise the list and the detail page disagree about the same complaint.
    """
    from app.services.complaints_service import ComplaintService

    db, project, _owner = linked
    linked_row = _complaint(db, project_id=str(project.id))
    plain_row = _complaint(db, project_title="NO LINK HERE")
    db.flush()

    result = ComplaintService(db).list_complaints(page=1, limit=50)
    rows = {str(r["system_id"]): r for r in result["data"]}

    assert rows[str(linked_row.id)]["project_code"] == project.project_code
    assert rows[str(linked_row.id)]["project_name"] == project.title
    assert rows[str(plain_row.id)]["project_code"] is None
    assert rows[str(plain_row.id)]["project_title"] == "NO LINK HERE"
