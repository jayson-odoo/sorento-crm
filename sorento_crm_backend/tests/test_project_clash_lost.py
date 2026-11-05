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
    """Sponsorship Form -> Lost. Lost is terminal: the engine refuses any move off it."""
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
        ]
    )
    db.flush()
    return live, lost


# ------------------------------------------------------------------ clash check


def test_a_won_and_a_lost_project_of_the_same_title_are_both_returned_with_no_developer():
    """The owner's case: title "test", Developer empty, PPF2611001 "test" is Won.

    Owner hand test (5 Nov): "if got match then should follow the same clash path", so a
    Won, Lost or Dormant match blocks exactly like an Open one.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        # One developer each: (company, developer, title) is unique.
        won = _project(db, company_id, outcome="won", developer=_developer(db, company_id))
        lost = _project(db, company_id, outcome="lost", developer=_developer(db, company_id))
        dormant = _project(db, company_id, outcome="dormant")

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
        assert all(by_id[pid].blocks for pid in (won.id, lost.id, dormant.id))


def test_registering_the_title_of_a_won_project_is_refused_server_side():
    """The form is not the guard: a direct register call must hit the same clash path."""
    from app.services.error_handler import AppException

    with blank_session() as db:
        company_id = _sorento(db)
        developer = _developer(db, company_id)
        _project(db, company_id, title="Menara Won Test", outcome="won", developer=developer)
        owner = _user(db)

        try:
            project_service.register_project(
                db,
                company_id=company_id,
                actor_user_id=owner,
                developer_party_id=developer.id,
                title="Menara Won Test",
            )
        except AppException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("a Won match must block a new registration")


def test_a_weak_lookalike_of_a_won_project_stays_context():
    """Only a match that would block if Open blocks: generic-noun lookalikes stay context."""
    with blank_session() as db:
        company_id = _sorento(db)
        developer = _developer(db, company_id)
        other = _project(
            db, company_id, title="The Wyn Residence", outcome="won", developer=developer
        )

        clashes = find_clashes(
            db, company_id=company_id, developer_party_id=developer.id, title="Taiga Residence"
        )

        match = next((c for c in clashes if c.project_id == other.id), None)
        assert match is not None and match.blocks is False


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


def _loss_reason(db, value="price") -> str:
    """The configurable loss-reason set a Lost move validates against (PROJECT-OUTCOME-SINGLE)."""
    from app.models.lookup import LookupOption, LookupSet
    from app.models.projects import QUOTATION_LOSS_REASON_SET_KEY

    lookup_set = db.query(LookupSet).filter(LookupSet.set_key == QUOTATION_LOSS_REASON_SET_KEY).first()
    if lookup_set is None:
        lookup_set = LookupSet(id=_uid(), set_key=QUOTATION_LOSS_REASON_SET_KEY, name="Loss reasons")
        db.add(lookup_set)
        db.flush()
    db.add(LookupOption(id=_uid(), set_id=lookup_set.id, value=value, label=value.title()))
    db.flush()
    return value


def test_moving_a_won_project_to_lost_makes_its_outcome_lost():
    with blank_session() as db:
        company_id = _sorento(db)
        live, lost_rung = _funnel(db)
        owner = _user(db)
        project = _project(db, company_id, outcome="won", owner=owner, status_id=live.id)
        _won_quotation(db, company_id, project)

        project_service.change_status(
            db,
            project,
            to_status_id=lost_rung.id,
            actor_user_id=owner,
            permissions=set(),
            loss_reason=_loss_reason(db),
        )

        db.refresh(project)
        assert project.status_id == lost_rung.id
        assert project.outcome == "lost"
        assert project.loss_reason == "price"


def test_a_project_on_the_lost_stage_reads_lost_whatever_its_areas_say():
    """A project cannot be Lost and Won at once: the stage decides, an area carries no outcome."""
    with blank_session() as db:
        company_id = _sorento(db)
        _live, lost_rung = _funnel(db)
        project = _project(db, company_id, outcome="open", status_id=lost_rung.id)
        _won_quotation(db, company_id, project)

        project_service.outcome_follows_stage(db, project)

        assert project.outcome == "lost"


def test_a_live_stage_leaves_the_project_outcome_alone():
    """No derivation from areas any more: Mark won on a live stage stays Won."""
    with blank_session() as db:
        company_id = _sorento(db)
        live, _lost = _funnel(db)
        project = _project(db, company_id, outcome="won", status_id=live.id)

        project_service.outcome_follows_stage(db, project)

        assert project.outcome == "won"


def test_an_admin_bulk_migration_onto_lost_syncs_outcome_too():
    """The status editor's 'move records off this status' writes status_id in bulk; it must
    leave outcome agreeing with the stage just like a single move does."""
    from app.modules.projects.status_entities import _migrate_projects

    with blank_session() as db:
        company_id = _sorento(db)
        live, lost_rung = _funnel(db)
        project = _project(db, company_id, outcome="won", status_id=live.id)
        _won_quotation(db, company_id, project)

        _migrate_projects(db, live.id, lost_rung.id)

        db.refresh(project)
        assert project.status_id == lost_rung.id
        assert project.outcome == "lost"
