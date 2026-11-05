"""PROJECT-CLASH-LOST (owner, 5 Nov).

1. The register Check must see a project in EVERY outcome: registering "test" said
   "No clash" although PPF2611001 "test" existed with outcome Won.
2. A project moved onto the Lost rung must read outcome Lost everywhere: the list showed
   Stage "Lost" next to Outcome "Won" because outcome followed the quotations only.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.models.projects import (
    Project,
    ProjectParty,
    ProjectQuotation,
    ProjectQuotationDocument,
)
from app.models.status import Status, StatusTransition
from app.models.user import User
from app.services import project_service
from app.services.project_clash_service import find_clashes, normalise_project_title
from app.services.project_quotation_service import derive_project_outcome

from ._pg_fixture import blank_session

MARKER = "zzt-clashlost"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} Owner"))
    db.flush()
    return user_id


def _developer(db, company_id: str) -> ProjectParty:
    party = ProjectParty(
        id=_uid(), company_id=company_id, party_type="developer", name=f"{MARKER} Airmas"
    )
    db.add(party)
    db.flush()
    return party


def _project(db, company_id, *, title="test", outcome="open", developer=None, owner=None, status_id=None):
    project = Project(
        id=_uid(),
        company_id=company_id,
        project_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        title=title,
        normalised_title=normalise_project_title(title),
        developer_party_id=developer.id if developer else None,
        owner_user_id=owner,
        outcome=outcome,
        status_id=status_id,
    )
    db.add(project)
    db.flush()
    return project


def _won_quotation(db, company_id, project) -> ProjectQuotation:
    document = ProjectQuotationDocument(
        id=_uid(), company_id=company_id, project_id=project.id, document_no=f"{MARKER}-{_uid()[:6]}"
    )
    db.add(document)
    db.flush()
    quotation = ProjectQuotation(
        id=_uid(),
        company_id=company_id,
        project_id=project.id,
        document_id=document.id,
        scope_label="Scope",
        outcome="won",
    )
    db.add(quotation)
    db.flush()
    return quotation


def _funnel(db):
    """Sponsorship Form -> Lost, and Lost -> Sponsorship Form (a reopened pursuit)."""
    live = Status(
        id=_uid(), entity_type="project", key="sponsorship_form", label="Sponsorship Form",
        is_initial=True, sort_order=0,
    )
    lost = Status(
        id=_uid(), entity_type="project", key="lost", label="Lost", is_terminal=True, sort_order=9
    )
    db.add_all([live, lost])
    db.flush()
    db.add_all(
        [
            StatusTransition(
                id=_uid(), entity_type="project", from_status_id=live.id,
                to_status_id=lost.id, label="Mark lost", trigger_mode="manual",
            ),
            StatusTransition(
                id=_uid(), entity_type="project", from_status_id=lost.id,
                to_status_id=live.id, label="Reopen", trigger_mode="manual",
            ),
        ]
    )
    db.flush()
    return live, lost


# ------------------------------------------------------------------ clash check


def test_a_won_and_a_lost_project_of_the_same_title_are_both_returned_with_no_developer():
    """The owner's case: title "test", Developer empty, PPF2611001 "test" is Won."""
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _developer(db, company_id)
        won = _project(db, company_id, outcome="won", developer=developer)
        lost = _project(db, company_id, outcome="lost", developer=developer)
        dormant = _project(db, company_id, outcome="dormant", developer=developer)

        clashes = find_clashes(
            db,
            company_id=company_id,
            developer_party_id=None,
            title="test",
            include_other_developers=True,
        )

        by_id = {c.project_id: c for c in clashes}
        assert {won.id, lost.id, dormant.id} <= set(by_id)
        assert by_id[won.id].outcome == "won"
        assert by_id[lost.id].outcome == "lost"
        # Only an open pursuit locks the development; a closed one is shown, not blocking.
        assert not any(by_id[pid].blocks for pid in (won.id, lost.id, dormant.id))


def test_the_preview_serialiser_carries_stage_outcome_and_owner_for_a_closed_match():
    with blank_session() as db:
        company_id = _sorento(db)
        live, lost_rung = _funnel(db)
        owner = _user(db)
        project = _project(db, company_id, outcome="lost", owner=owner, status_id=lost_rung.id)

        clashes = find_clashes(
            db, company_id=company_id, developer_party_id=None, title="test",
            include_other_developers=True,
        )
        rows = project_service.serialize_clash_candidates(db, clashes)

        row = next(r for r in rows if r["project_id"] == project.id)
        assert row["project_code"] == project.project_code
        assert row["outcome"] == "lost"
        assert row["status_label"] == "Lost"
        assert row["owner_name"] == f"{MARKER} Owner"


# ------------------------------------------------------------------ stage drives outcome


def test_moving_a_won_project_to_lost_makes_its_outcome_lost():
    with blank_session() as db:
        company_id = _sorento(db)
        live, lost_rung = _funnel(db)
        owner = _user(db)
        project = _project(db, company_id, outcome="won", owner=owner, status_id=live.id)
        _won_quotation(db, company_id, project)

        project_service.change_status(
            db, project, to_status_id=lost_rung.id, actor_user_id=owner, permissions=set()
        )

        db.refresh(project)
        assert project.status_id == lost_rung.id
        assert project.outcome == "lost"


def test_reopening_a_lost_project_re_derives_its_outcome_from_the_quotations():
    with blank_session() as db:
        company_id = _sorento(db)
        live, lost_rung = _funnel(db)
        owner = _user(db)
        project = _project(db, company_id, outcome="won", owner=owner, status_id=live.id)
        _won_quotation(db, company_id, project)
        project_service.change_status(
            db, project, to_status_id=lost_rung.id, actor_user_id=owner, permissions=set()
        )

        project_service.change_status(
            db, project, to_status_id=live.id, actor_user_id=owner, permissions=set()
        )

        db.refresh(project)
        assert project.outcome == "won"


def test_a_won_quotation_does_not_turn_a_lost_stage_back_into_won():
    """A project cannot be Lost and Won at once: the decided stage wins the derivation."""
    with blank_session() as db:
        company_id = _sorento(db)
        _live, lost_rung = _funnel(db)
        project = _project(db, company_id, outcome="open", status_id=lost_rung.id)
        _won_quotation(db, company_id, project)

        assert derive_project_outcome(db, project) == "lost"


def test_a_live_stage_still_derives_outcome_from_quotations():
    with blank_session() as db:
        company_id = _sorento(db)
        live, _lost = _funnel(db)
        project = _project(db, company_id, outcome="open", status_id=live.id)
        _won_quotation(db, company_id, project)

        assert derive_project_outcome(db, project) == "won"
