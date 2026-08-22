"""S2 project edit, funnel movement, critical flag and delete (Groups C, G).

Each test here pins a rule that a plausible implementation gets wrong: renaming past
the lock, dragging a card along an edge that does not exist, resetting the negotiation
clock on an unrelated save, and deleting commercial history.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.projects import Project
from app.models.status import Status, StatusTransition
from app.models.user import User
from app.services import project_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-life"
MANAGE = "projects.projects.manage"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _numbering(db) -> None:
    db.execute(
        text(
            "insert into document_numbering_rules "
            "(id, doc_type, enabled, prefix_template, number_digits, next_value, "
            " start_value, reset_policy) "
            "values (:id, 'project', true, 'PRJ-', 6, 1, 1, 'none')"
        ),
        {"id": _uid()},
    )
    db.flush()


def _developer(db, company_id: str, name: str):
    from app.models.projects import ProjectParty

    party = ProjectParty(
        id=_uid(), company_id=company_id, party_type="developer", name=name
    )
    db.add(party)
    db.flush()
    return party


def _funnel(db):
    """A two-rung graph with exactly one legal edge forwards."""
    identified = Status(
        id=_uid(),
        entity_type="project",
        key="identified",
        label="Identified",
        is_initial=True,
        sort_order=0,
    )
    quoted = Status(
        id=_uid(),
        entity_type="project",
        key="quoted",
        label="Quoted",
        sort_order=1,
    )
    po = Status(
        id=_uid(),
        entity_type="project",
        key="po_received",
        label="PO Received",
        is_terminal=True,
        sort_order=2,
    )
    db.add_all([identified, quoted, po])
    db.flush()
    db.add(
        StatusTransition(
            id=_uid(),
            entity_type="project",
            from_status_id=identified.id,
            to_status_id=quoted.id,
            label="Send quotation",
            trigger_mode="manual",
        )
    )
    db.flush()
    return identified, quoted, po


def _register(db, company_id, owner, developer, title, **kwargs):
    return project_service.register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=developer.id,
        title=title,
        **kwargs,
    )


def test_a_new_project_lands_on_the_graphs_first_rung():
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering(db)
        identified, _quoted, _po = _funnel(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")

        project = _register(db, company_id, owner, developer, "Setia Alam Phase 3B")

        assert project.status_id == identified.id


def test_a_project_registered_before_its_funnel_exists_is_still_created():
    """The registration is the valuable act; the funnel can be configured after.

    Refusing here would mean a fresh install cannot record a single project until an
    admin has finished building a status graph.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")

        project = _register(db, company_id, owner, developer, "Setia Alam Phase 3B")

        assert project.project_code == "PRJ-000001"
        assert project.status_id is None


def test_renaming_a_project_onto_a_colleagues_title_is_refused():
    """The rename bypass: register something innocuous, then rename it.

    The database unique index catches an exact key collision, but a near-duplicate
    ("Setia Alam Ph 3B") would slide straight past it, so the matcher has to run on
    edit and not only on create.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering(db)
        owner = _user(db, f"{MARKER} Ali")
        squatter = _user(db, f"{MARKER} Siti")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")

        _register(db, company_id, owner, developer, "Setia Alam Phase 3B")
        mine = _register(db, company_id, squatter, developer, "Bukit Jalil Clubhouse")

        with pytest.raises(AppException) as exc:
            project_service.update_project(
                db,
                mine,
                {"title": "Setia Alam Ph 3B"},
                actor_user_id=squatter,
                permissions=set(),
            )

        assert exc.value.status_code == 409
        assert mine.title == "Bukit Jalil Clubhouse"


def test_renaming_a_project_to_a_tidier_version_of_its_own_title_is_allowed():
    """A project must never block itself, which a naive clash check on edit does."""
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")
        project = _register(db, company_id, owner, developer, "setia alam ph 3b")

        project_service.update_project(
            db,
            project,
            {"title": "Setia Alam Phase 3B"},
            actor_user_id=owner,
            permissions=set(),
        )

        assert project.title == "Setia Alam Phase 3B"
        assert project.normalised_title == "setia alam phase 3b"


def test_an_edge_that_does_not_exist_is_rejected_server_side():
    """AC-B4: dragging a card to an illegal column fails on the server.

    Trusting the board's own column list would make the rule cosmetic -- anything
    posting straight to the API could put a project anywhere.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering(db)
        _identified, _quoted, po = _funnel(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")
        project = _register(db, company_id, owner, developer, "Setia Alam Phase 3B")

        with pytest.raises(AppException) as exc:
            project_service.change_status(
                db,
                project,
                to_status_id=po.id,
                actor_user_id=owner,
                permissions=set(),
            )

        assert exc.value.status_code == 422


def test_a_configured_edge_is_accepted():
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering(db)
        _identified, quoted, _po = _funnel(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")
        project = _register(db, company_id, owner, developer, "Setia Alam Phase 3B")

        project_service.change_status(
            db, project, to_status_id=quoted.id, actor_user_id=owner, permissions=set()
        )

        assert project.status_id == quoted.id


def test_another_salesperson_cannot_move_a_card_they_do_not_own():
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering(db)
        _identified, quoted, _po = _funnel(db)
        owner = _user(db, f"{MARKER} Ali")
        outsider = _user(db, f"{MARKER} Siti")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")
        project = _register(db, company_id, owner, developer, "Setia Alam Phase 3B")

        with pytest.raises(AppException) as exc:
            project_service.change_status(
                db,
                project,
                to_status_id=quoted.id,
                actor_user_id=outsider,
                permissions=set(),
            )
        assert exc.value.status_code == 403


def test_the_critical_clock_starts_once_and_is_not_reset_by_later_saves():
    """"Days in final negotiation" is what management acts on.

    Re-stamping on every save of an already-critical project would make that number
    always read zero, and the resulting reports would look fine.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")
        project = _register(db, company_id, owner, developer, "Setia Alam Phase 3B")

        project_service.update_project(
            db,
            project,
            {"is_critical": True, "management_support": "Price approval to 18%"},
            actor_user_id=owner,
            permissions=set(),
        )
        stamped_at = project.critical_at
        assert stamped_at is not None

        project_service.update_project(
            db,
            project,
            {"is_critical": True, "management_notes": "Met the QS on Tuesday"},
            actor_user_id=owner,
            permissions=set(),
        )
        assert project.critical_at == stamped_at

        # Standing down clears the clock, so a second escalation is timed afresh.
        project_service.update_project(
            db, project, {"is_critical": False}, actor_user_id=owner, permissions=set()
        )
        assert project.critical_at is None


def test_only_a_manager_can_reassign_the_owner():
    """A quiet self-handoff is how accountability for a stalling pursuit disappears."""
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering(db)
        owner = _user(db, f"{MARKER} Ali")
        other = _user(db, f"{MARKER} Siti")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")
        project = _register(db, company_id, owner, developer, "Setia Alam Phase 3B")

        with pytest.raises(AppException) as exc:
            project_service.update_project(
                db,
                project,
                {"owner_user_id": other},
                actor_user_id=owner,
                permissions=set(),
            )
        assert exc.value.status_code == 403
        assert project.owner_user_id == owner

        project_service.update_project(
            db,
            project,
            {"owner_user_id": other},
            actor_user_id=owner,
            permissions={MANAGE},
        )
        assert project.owner_user_id == other


def test_a_project_is_hard_deleted():
    """AC-G10: delete means delete, not a hidden flag."""
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")
        project = _register(db, company_id, owner, developer, "Setia Alam Phase 3B")
        project_id = project.id

        project_service.delete_project(
            db, project, actor_user_id=owner, permissions=set()
        )

        assert db.query(Project).filter(Project.id == project_id).first() is None
