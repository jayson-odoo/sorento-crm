"""S2 seeding (AC-C1, AC-C8, Group B).

The seeder runs on every boot, so the property that matters is not "it creates the
defaults" but "it never touches anything afterwards". A seeder that re-asserts its
defaults silently reverts the team's configuration on restart, and nobody connects the
two events.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.models.numbering import DocumentNumberingRule
from app.models.projects import ProjectTemplate, ProjectTemplateRole, ProjectType
from app.models.status import Status, StatusTransition
from app.services import project_seed_service, status_service

from ._pg_fixture import blank_session

MARKER = "zzt-seed"


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def test_seeding_produces_a_valid_usable_funnel():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)

        statuses = (
            db.query(Status)
            .filter(Status.entity_type == "project", Status.scope_id.is_(None))
            .all()
        )
        keys = {s.key for s in statuses}
        assert "identified" in keys
        # The terminal rung says what happened, not that the pursuit ended (G1).
        assert "po_received" in keys
        assert "won" not in keys

        # Exactly one starting state, and the engine's own validator agrees the graph
        # is coherent -- a seeded graph that fails validation would block every
        # transition with a confusing error.
        assert len([s for s in statuses if s.is_initial]) == 1
        status_service.validate_graph(db, "project")

        assert status_service.initial_status(db, "project").key == "identified"


def test_every_live_rung_can_be_lost():
    """Losing at the identified stage is as real as losing at tender.

    A funnel where only the last rung can be lost forces people to fake a stage
    advance before recording the loss, which corrupts every stage-duration number.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)

        by_key = {
            s.key: s
            for s in db.query(Status)
            .filter(Status.entity_type == "project", Status.scope_id.is_(None))
            .all()
        }
        lost_id = by_key["lost"].id
        for key in ("identified", "registered", "specified", "quoted", "tendering"):
            edges = status_service.available_transitions(
                db, "project", by_key[key].id
            )
            assert lost_id in {e.to_status_id for e in edges}, f"{key} cannot be lost"


def test_the_funnel_is_not_fully_connected():
    """A configurable funnel where every move is legal is decorative.

    Registering straight to PO Received would mean nothing was ever specified or
    quoted, and the pipeline report would be fiction.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)

        by_key = {
            s.key: s
            for s in db.query(Status)
            .filter(Status.entity_type == "project", Status.scope_id.is_(None))
            .all()
        }
        from_identified = {
            e.to_status_id
            for e in status_service.available_transitions(
                db, "project", by_key["identified"].id
            )
        }
        assert by_key["po_received"].id not in from_identified


def test_seeding_twice_changes_nothing():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)

        counts = lambda: (  # noqa: E731
            db.query(Status).filter(Status.entity_type == "project").count(),
            db.query(StatusTransition)
            .filter(StatusTransition.entity_type == "project")
            .count(),
            db.query(ProjectType).count(),
            db.query(ProjectTemplate).count(),
            db.query(ProjectTemplateRole).count(),
            db.query(DocumentNumberingRule).count(),
        )
        before = counts()

        project_seed_service.run(db, company_id=company_id)
        project_seed_service.run(db, company_id=company_id)

        assert counts() == before


def test_a_renamed_status_survives_reseeding():
    """The team owns their vocabulary once it ships."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)

        identified = (
            db.query(Status)
            .filter(Status.entity_type == "project", Status.key == "identified")
            .first()
        )
        identified.label = "Sighted"
        db.flush()

        project_seed_service.run(db, company_id=company_id)
        db.refresh(identified)

        assert identified.label == "Sighted"


def test_a_deleted_project_type_is_not_resurrected():
    """Re-adding "Institutional" every restart, after someone deliberately removed
    it, is the seeder fighting the user."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)

        institutional = (
            db.query(ProjectType)
            .filter(
                ProjectType.company_id == company_id,
                ProjectType.code == "institutional",
            )
            .first()
        )
        assert institutional is not None
        db.query(ProjectTemplateRole).filter(
            ProjectTemplateRole.template_id.in_(
                db.query(ProjectTemplate.id).filter(
                    ProjectTemplate.type_id == institutional.id
                )
            )
        ).delete(synchronize_session=False)
        db.query(ProjectTemplate).filter(
            ProjectTemplate.type_id == institutional.id
        ).delete(synchronize_session=False)
        db.delete(institutional)
        db.flush()

        # A per-status/per-type "create if missing" seeder would bring it straight
        # back. The status graph guard is the same shape: skip once any row exists.
        project_seed_service.run(db, company_id=company_id)

        assert (
            db.query(ProjectType)
            .filter(
                ProjectType.company_id == company_id,
                ProjectType.code == "institutional",
            )
            .first()
            is None
        )


def test_every_seeded_template_offers_the_four_client_named_roles():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)

        templates = db.query(ProjectTemplate).all()
        assert templates
        for template in templates:
            roles = {
                r.name
                for r in db.query(ProjectTemplateRole)
                .filter(ProjectTemplateRole.template_id == template.id)
                .all()
            }
            assert {
                "Decision Maker",
                "Influencer",
                "Info Provider",
                "Architect",
            } <= roles


def test_the_project_numbering_rule_yields_the_agreed_shape():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)

        from app.services.numbering_service import NumberingService

        assert (
            NumberingService(db).get_next_number("project", commit_rule=False)
            == "PRJ-000001"
        )


def test_only_property_development_derives_delivery_from_launch():
    """AC-C4. A hotel refurbishment has no launch date to count months from, so
    inferring a delivery year for it would invent demand that does not exist."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)

        derives = {
            t.code
            for t in db.query(ProjectType)
            .filter(
                ProjectType.company_id == company_id,
                ProjectType.derives_delivery_from_launch.is_(True),
            )
            .all()
        }
        assert derives == {"property_development"}
