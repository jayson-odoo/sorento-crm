"""S2 project edit rights (UAC Group J, AC-C7).

The read/write split is deliberately asymmetric. Every salesperson reads every
project, because hiding colleagues' projects recreates the blindness the module
exists to remove. Writing is confined to the owner, approved collaborators, and
managers -- otherwise "one development, one owner" means nothing.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.projects import Project
from app.models.user import User
from app.services.error_handler import AppException
from app.services import project_service

from ._pg_fixture import blank_session

MARKER = "zzt-acc"
MANAGE_PERMISSION = "projects.projects.manage"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _project(db, company_id: str, owner: str) -> Project:
    project = Project(
        id=_uid(),
        company_id=company_id,
        project_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        title="Setia Alam Phase 3B",
        normalised_title="setia alam phase 3b",
        owner_user_id=owner,
    )
    db.add(project)
    db.flush()
    return project


def test_the_owner_may_edit():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)

        assert project_service.can_edit_project(db, project, owner, set()) is True


def test_another_salesperson_may_not_edit():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        outsider = _user(db, f"{MARKER} Siti")
        project = _project(db, company_id, owner)

        assert project_service.can_edit_project(db, project, outsider, set()) is False

        with pytest.raises(AppException) as exc:
            project_service.assert_can_edit_project(db, project, outsider, set())
        assert exc.value.status_code == 403
        # The refusal has to point somewhere. A dead-end 403 is what drives people
        # back to WhatsApp to sort it out, which is the pain being removed.
        assert "join" in exc.value.detail["message"].lower()


def test_an_approved_collaborator_may_edit():
    """AC-C7: approving a join request is what grants edit rights.

    Two people legitimately share a project when one holds the developer
    relationship and the other the specifying architect, and the answer to that is a
    recorded collaborator, not a silent second registration.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        helper = _user(db, f"{MARKER} Siti")
        project = _project(db, company_id, owner)

        request = project_service.create_takeover_request(
            db,
            project=project,
            requester_user_id=helper,
            kind="join",
            reason="I hold the architect relationship on this tender.",
        )
        assert project_service.can_edit_project(db, project, helper, set()) is False

        project_service.decide_takeover_request(
            db,
            request=request,
            decider_user_id=owner,
            decider_permissions=set(),
            approve=True,
        )

        assert project_service.can_edit_project(db, project, helper, set()) is True


def test_a_manager_may_edit_any_project():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        manager = _user(db, f"{MARKER} Manager")
        project = _project(db, company_id, owner)

        assert (
            project_service.can_edit_project(
                db, project, manager, {MANAGE_PERMISSION}
            )
            is True
        )


def test_only_the_owner_or_a_manager_decides_a_join_request():
    """A third salesperson approving someone else onto a project they do not hold
    would route around the owner entirely."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        helper = _user(db, f"{MARKER} Siti")
        bystander = _user(db, f"{MARKER} Bystander")
        project = _project(db, company_id, owner)

        request = project_service.create_takeover_request(
            db,
            project=project,
            requester_user_id=helper,
            kind="join",
            reason="Please add me.",
        )

        with pytest.raises(AppException) as exc:
            project_service.decide_takeover_request(
                db,
                request=request,
                decider_user_id=bystander,
                decider_permissions=set(),
                approve=True,
            )
        assert exc.value.status_code == 403
        assert project_service.can_edit_project(db, project, helper, set()) is False


def test_an_approved_dispute_transfers_ownership_rather_than_adding_a_collaborator():
    """The two request kinds resolve differently, which is the whole point.

    "Join" says the project is yours and I want in; "dispute" says the project should
    be mine. Resolving both as a collaborator grant would leave the disputed project
    still owned by the person the manager just ruled against.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        challenger = _user(db, f"{MARKER} Siti")
        manager = _user(db, f"{MARKER} Manager")
        project = _project(db, company_id, owner)

        request = project_service.create_takeover_request(
            db,
            project=project,
            requester_user_id=challenger,
            kind="dispute",
            reason="I registered this with the developer three months ago.",
        )
        project_service.decide_takeover_request(
            db,
            request=request,
            decider_user_id=manager,
            decider_permissions={MANAGE_PERMISSION},
            approve=True,
        )

        assert project.owner_user_id == challenger
        # The previous owner keeps access rather than being locked out of work they
        # did: they stay a collaborator, and the record of the decision survives.
        assert project_service.can_edit_project(db, project, owner, set()) is True
        assert request.status == "approved"
        assert request.decided_by == manager


def test_a_rejected_request_grants_nothing_and_records_the_decision():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        helper = _user(db, f"{MARKER} Siti")
        project = _project(db, company_id, owner)

        request = project_service.create_takeover_request(
            db,
            project=project,
            requester_user_id=helper,
            kind="join",
            reason="Please add me.",
        )
        project_service.decide_takeover_request(
            db,
            request=request,
            decider_user_id=owner,
            decider_permissions=set(),
            approve=False,
            decision_note="Different phase, register your own.",
        )

        assert request.status == "rejected"
        assert request.decision_note == "Different phase, register your own."
        assert project_service.can_edit_project(db, project, helper, set()) is False


def test_a_request_cannot_be_decided_twice():
    """Without this, a rejected request can be re-approved later by anyone who can
    decide, silently granting access the owner already refused."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        helper = _user(db, f"{MARKER} Siti")
        project = _project(db, company_id, owner)

        request = project_service.create_takeover_request(
            db,
            project=project,
            requester_user_id=helper,
            kind="join",
            reason="Please add me.",
        )
        project_service.decide_takeover_request(
            db,
            request=request,
            decider_user_id=owner,
            decider_permissions=set(),
            approve=False,
        )

        with pytest.raises(AppException) as exc:
            project_service.decide_takeover_request(
                db,
                request=request,
                decider_user_id=owner,
                decider_permissions=set(),
                approve=True,
            )
        assert exc.value.status_code == 409
        assert project_service.can_edit_project(db, project, helper, set()) is False


def test_a_duplicate_open_request_is_refused():
    """Otherwise a spurned requester can spam the owner's notifications."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        helper = _user(db, f"{MARKER} Siti")
        project = _project(db, company_id, owner)

        project_service.create_takeover_request(
            db,
            project=project,
            requester_user_id=helper,
            kind="join",
            reason="Please add me.",
        )

        with pytest.raises(AppException) as exc:
            project_service.create_takeover_request(
                db,
                project=project,
                requester_user_id=helper,
                kind="join",
                reason="Please add me again.",
            )
        assert exc.value.status_code == 409


def test_the_owner_cannot_request_to_join_their_own_project():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)

        with pytest.raises(AppException) as exc:
            project_service.create_takeover_request(
                db,
                project=project,
                requester_user_id=owner,
                kind="join",
                reason="Adding myself.",
            )
        assert exc.value.status_code == 422
