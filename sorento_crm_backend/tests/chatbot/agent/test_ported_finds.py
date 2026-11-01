"""AGENTIC-UNIFY PR 4: `crm_complaints_find` and `crm_projects_find` (AC-5, AC-8).

Panel only (AC-0, crew ruling 2 Nov): every run below is inside `panel_turn`. The console operator `combine` and
the brand refusal are gone with that ruling; their tests were removed.

Two in-process `UserRead`s in `writes.USER_READS`, run through `writes.run_user_read` as the user, on the real
route functions and real role rows (blank Postgres schema, nothing patched). The catalog keeps its UUID-first rule,
so a complaint number or project code is found here. Arg: `query`. Slug: the domain's `.view` or `.view_own`.

The row shape is pinned by content, not by key names: the number or code, the status, the customer or title and
the id must all be in the result, and the id must join `seen_ids`.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.models.company import UserCompany
from app.models.complaints import Complaint
from app.models.projects import Project
from app.services.chatbot.agent import tools as agent_tools
from app.services.chatbot.agent import writes
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from tests._own_scope_support import contact as mk_contact
from tests._pg_fixture import blank_session
from tests.chatbot.agent._ported_reads_support import make_ctx, panel_turn
from tests.chatbot.agent._seed import seed_user

COMPLAINTS = "crm_complaints_find"
PROJECTS = "crm_projects_find"
C_VIEW = "complaint_management.complaints.view"
C_OWN = "complaint_management.complaints.view_own"
P_VIEW = "projects.projects.view"
P_OWN = "projects.projects.view_own"
UNRELATED = "inventory.stock.view"
SORENTO = DEFAULT_COMPANY_ID
FAMILIES = [
    pytest.param(COMPLAINTS, C_VIEW, C_OWN, id="complaints"),
    pytest.param(PROJECTS, P_VIEW, P_OWN, id="projects"),
]


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    yield


@pytest.fixture(scope="module")
def db():
    with blank_session() as session:
        yield session


# ------------------------------------------------------------------ seeding


def mk_user(db, *slugs, contact=None) -> str:
    user_id = seed_user(db, contact_pk=contact.id if contact is not None else None, slugs=slugs)
    db.add(UserCompany(user_id=user_id, company_id=SORENTO))
    db.flush()
    return user_id


def mk_contact_row(db):
    return mk_contact(db, "FIND")


def mk_complaint(db, tag: str, n: int, *, owner_contact) -> Complaint:
    row = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"ZZT-CMP-{tag}-{n}",
        customer_name=f"ZZT Customer {tag} {n}",
        status="processed_by_cs",
        complaint_date=date(2026, 6, 2),
        contact_id=str(owner_contact.id),
    )
    db.add(row)
    db.flush()
    return row


def mk_project(db, tag: str, n: int, *, owner: str) -> Project:
    code = f"ZZT-PRJ-{tag}-{n}"
    row = Project(
        id=str(uuid.uuid4()),
        company_id=SORENTO,
        project_code=code,
        title=f"ZZT Project Title {tag} {n}",
        normalised_title=f"zzt project title {tag} {n}",
        owner_user_id=owner,
    )
    db.add(row)
    db.flush()
    return row


class Scene:
    """Two records of one search tag, one per owner, for either family."""

    def __init__(self, db, name: str, view: str, own: str):
        self.name = name
        self.tag = uuid.uuid4().hex[:8]
        self.contact_a, self.contact_b = mk_contact_row(db), mk_contact_row(db)
        self.owner_a = mk_user(db, own, contact=self.contact_a)
        self.owner_b = mk_user(db, own, contact=self.contact_b)
        self.viewer = mk_user(db, view)
        if name == COMPLAINTS:
            self.row_a = mk_complaint(db, self.tag, 1, owner_contact=self.contact_a)
            self.row_b = mk_complaint(db, self.tag, 2, owner_contact=self.contact_b)
            self.key_a, self.key_b = self.row_a.complaint_number, self.row_b.complaint_number
            self.detail_a = self.row_a.customer_name
        else:
            self.row_a = mk_project(db, self.tag, 1, owner=self.owner_a)
            self.row_b = mk_project(db, self.tag, 2, owner=self.owner_b)
            self.key_a, self.key_b = self.row_a.project_code, self.row_b.project_code
            self.detail_a = self.row_a.title
        db.commit()


def find(db, ctx, name: str, query: str, seen: set[str] | None = None):
    assert name in writes.USER_READS, f"{name} is not in writes.USER_READS"
    seen = seen if seen is not None else set()
    with panel_turn(ctx.user_id):
        return writes.run_user_read(db, ctx, name, {"query": query}, seen)


def blob(out) -> str:
    return json.dumps(out.data, default=str)


# ------------------------------------------------------------------ registered, finds its row


@pytest.mark.parametrize("name,view,own", FAMILIES)
def test_AC5_the_find_is_a_user_read_that_takes_query(name, view, own):
    assert name in writes.USER_READS, f"{name} is not in writes.USER_READS"
    read = writes.USER_READS[name]
    assert "query" in read.schema["function"]["parameters"]["properties"]
    assert set(read.user_permission) == {view, own}, read.user_permission


@pytest.mark.parametrize("name,view,own", FAMILIES)
def test_AC5_a_number_or_code_finds_its_row_and_the_id_joins_seen_ids(db, name, view, own):
    s = Scene(db, name, view, own)
    seen: set[str] = set()
    out = find(db, make_ctx(s.viewer), name, s.key_a, seen)
    assert out.status == "ok", (out.status, out.message)
    text = blob(out)
    assert s.key_a in text
    assert s.detail_a in text, "the customer (complaint) or title (project) is missing from the row"
    if name == COMPLAINTS:
        assert "processed_by_cs" in text, "the status is missing from the row"
    assert s.key_b not in text, "a search for one number returned the other row"
    assert str(s.row_a.id).lower() in seen, "the row's id did not join the turn's seen ids"
    assert str(s.row_b.id).lower() not in seen


@pytest.mark.parametrize("name,view,own", FAMILIES)
def test_AC5_an_unknown_number_is_empty(db, name, view, own):
    s = Scene(db, name, view, own)
    out = find(db, make_ctx(s.viewer), name, f"ZZT-NOPE-{uuid.uuid4().hex}")
    assert out.status == "empty", (out.status, out.message)


# ------------------------------------------------------------------ view, view_own, no slug


@pytest.mark.parametrize("name,view,own", FAMILIES)
def test_AC5_a_view_holder_sees_every_row(db, name, view, own):
    s = Scene(db, name, view, own)
    out = find(db, make_ctx(s.viewer), name, s.tag)
    assert out.status == "ok", (out.status, out.message)
    assert s.key_a in blob(out) and s.key_b in blob(out)


@pytest.mark.parametrize("name,view,own", FAMILIES)
def test_AC5_a_view_own_holder_sees_only_their_own_rows_on_the_panel(db, name, view, own):
    """The finds run in process as the user, so the screen's own scope holds."""
    s = Scene(db, name, view, own)
    ctx = make_ctx(s.owner_a)
    out = find(db, ctx, name, s.tag)
    assert out.status == "ok", (out.status, out.message)
    text = blob(out)
    assert s.key_a in text
    assert s.key_b not in text, "a view_own holder read another user's row"


@pytest.mark.parametrize("name,view,own", FAMILIES)
def test_AC5_a_view_own_holder_searching_anothers_exact_number_finds_nothing(db, name, view, own):
    s = Scene(db, name, view, own)
    out = find(db, make_ctx(s.owner_a), name, s.key_b)
    assert out.status == "empty", (out.status, out.message)


@pytest.mark.parametrize("name,view,own", FAMILIES)
def test_AC5_no_slug_means_not_offered_and_refused(db, name, view, own):
    s = Scene(db, name, view, own)
    nobody = mk_user(db, UNRELATED)
    ctx = make_ctx(nobody)
    assert name in writes.USER_READS, f"{name} is not in writes.USER_READS"
    with panel_turn(nobody):
        assert name not in [r.name for r in writes.permitted_user_reads(db, ctx)]
    out = find(db, ctx, name, s.key_a)
    assert out.status == "denied", (out.status, out.message)
    assert s.key_a not in blob(out)


@pytest.mark.parametrize("name,view,own", FAMILIES)
def test_AC5_each_slug_alone_is_offered_on_the_panel(db, name, view, own):
    s = Scene(db, name, view, own)
    assert name in writes.USER_READS, f"{name} is not in writes.USER_READS"
    for user_id in (s.viewer, s.owner_a):
        with panel_turn(user_id):
            assert name in [r.name for r in writes.permitted_user_reads(db, make_ctx(user_id))]


# ------------------------------------------------------------------ approved projects only


def mk_registration(db, tag: str, n: int, *, owner: str, state: str) -> Project:
    """A portal registration waiting for approval (or rejected): `approval_state` set, not yet a project."""
    row = mk_project(db, tag, n, owner=owner)
    row.approval_state = state
    db.commit()
    return row


@pytest.mark.parametrize("state", ["pending", "rejected"])
def test_AC5_projects_find_returns_no_unapproved_registration(db, state):
    s = Scene(db, PROJECTS, P_VIEW, P_OWN)
    reg = mk_registration(db, s.tag, 9, owner=s.owner_a, state=state)
    out = find(db, make_ctx(s.viewer), PROJECTS, s.tag)
    assert out.status == "ok", (out.status, out.message)
    text = blob(out)
    assert s.key_a in text, "the approved project is missing"
    assert reg.project_code not in text, f"a {state} registration was returned"


def test_AC5_projects_find_for_an_unapproved_registrations_exact_code_is_empty(db):
    s = Scene(db, PROJECTS, P_VIEW, P_OWN)
    reg = mk_registration(db, s.tag, 8, owner=s.owner_a, state="pending")
    out = find(db, make_ctx(s.viewer), PROJECTS, reg.project_code)
    assert out.status == "empty", (out.status, out.message)


def test_AC5_projects_list_is_called_with_no_approval_argument_it_is_unchanged(db):
    """The catalog's list already leaves registrations out on a machine read; the agent adds nothing to it."""
    from tests.chatbot.agent._ported_reads_support import Recorder, dispatch

    viewer = mk_user(db, P_VIEW)
    rec = Recorder()
    with panel_turn(viewer):
        out = dispatch(db, make_ctx(viewer), "crm_projects_list", {}, rec=rec)
    assert out.status == "ok", (out.status, out.message)
    sent = rec.calls[0][1]
    assert not ({"approved_only", "approval_state"} & set(sent)), sent


# ------------------------------------------------------------------ the not-found verifier


def _ledger(name: str, status: str, query: str) -> dict:
    return {"f1": {"name": name, "status": status, "args": {"query": query}, "data": None}}


@pytest.mark.parametrize("name", [COMPLAINTS, PROJECTS])
@pytest.mark.parametrize("what", ["CMP-0042", "complaint CMP-0042", "cmp-0042"])
def test_AC5_an_empty_find_backs_a_not_found_claim_for_the_term_it_searched(name, what):
    from app.services.chatbot.agent import loop

    args = {"text": "I could not find it.", "not_found": [{"what": what, "call_id": "f1"}]}
    bad_numbers, bad_not_found = loop.verify_answer(args, _ledger(name, "empty", "CMP-0042"), "is CMP-0042 there")
    assert bad_not_found == [], f"an empty {name} for the same term did not back the claim: {bad_not_found}"


@pytest.mark.parametrize("name", [COMPLAINTS, PROJECTS])
def test_AC5_an_empty_find_does_not_back_a_not_found_claim_for_a_different_term(name):
    from app.services.chatbot.agent import loop

    args = {"text": "No.", "not_found": [{"what": "CMP-0099", "call_id": "f1"}]}
    _, bad_not_found = loop.verify_answer(args, _ledger(name, "empty", "CMP-0042"), "is CMP-0099 there")
    assert bad_not_found == ["CMP-0099"]


@pytest.mark.parametrize("name", [COMPLAINTS, PROJECTS])
def test_AC5_a_find_that_returned_rows_does_not_back_a_not_found_claim(name):
    from app.services.chatbot.agent import loop

    args = {"text": "No.", "not_found": [{"what": "CMP-0042", "call_id": "f1"}]}
    _, bad_not_found = loop.verify_answer(args, _ledger(name, "ok", "CMP-0042"), "is CMP-0042 there")
    assert bad_not_found == ["CMP-0042"]


# ------------------------------------------------------------------ labels


@pytest.mark.parametrize("name", [COMPLAINTS, PROJECTS])
def test_AC8_each_find_has_a_plain_label_that_reaches_jev(name):
    from app.services.chatbot import router

    label = agent_tools.TOOL_LABELS.get(name)
    assert label and label.strip(), f"{name} has no entry in TOOL_LABELS"
    assert "crm_" not in label
    assert label in router.agent_tool_labels(), f"{name} is not told to Jev"


def test_AC8_the_two_find_labels_differ_from_each_other_and_from_the_list_labels():
    labels = [agent_tools.TOOL_LABELS.get(n) for n in (COMPLAINTS, PROJECTS)]
    assert all(labels), labels
    assert len(set(labels)) == 2
    for other in ("crm_complaints_list", "crm_projects_list"):
        assert agent_tools.TOOL_LABELS.get(other) not in labels
