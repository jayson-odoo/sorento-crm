"""S2 registration service (ADR-0004, UAC Group A/C).

The registration step is where a salesperson claims a development. It is the one
write in the module that must never be permissive: a duplicate that gets through
puts two people on one tender, which is the failure the module exists to prevent.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.projects import ProjectParty
from app.models.user import User
from app.services.error_handler import AppException
from app.services.project_service import register_project

from ._pg_fixture import blank_session

MARKER = "zzt-reg"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    """Via the ORM, so every column default is applied.

    Hand-written INSERTs against ``users`` break on each new NOT NULL column the
    table gains, and there are already more than twenty.
    """
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _numbering_rule(db, *, prefix: str = "PRJ-", digits: int = 6) -> None:
    """The project code is numbering-driven, not hardcoded (user decision)."""
    db.execute(
        text(
            "insert into document_numbering_rules "
            "(id, doc_type, enabled, prefix_template, number_digits, next_value, "
            " start_value, reset_policy) "
            "values (:id, 'project', true, :prefix, :digits, 123, 1, 'none')"
        ),
        {"id": _uid(), "prefix": prefix, "digits": digits},
    )
    db.flush()


def _developer(db, company_id: str, name: str) -> ProjectParty:
    party = ProjectParty(
        id=_uid(), company_id=company_id, party_type="developer", name=name
    )
    db.add(party)
    db.flush()
    return party


def test_registering_a_project_stamps_code_owner_and_comparison_key():
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering_rule(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")

        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=developer.id,
            title="  Setia Alam   Phase 3B ",
        )

        assert project.project_code == "PRJ-000123"
        assert project.owner_user_id == owner
        assert project.outcome == "open"
        # Whitespace is tidied but casing is NOT: the display title keeps the
        # capitalisation the user typed, and only the comparison key is casefolded.
        # Collapsing runs of spaces is deliberate -- the live data already contains
        # "KSL Setia Alam Project  (733 units service apartment)" with a doubled
        # space, and two identical titles that differ only in spacing would
        # otherwise render as two different strings while sharing one identity.
        assert project.title == "Setia Alam Phase 3B"
        assert project.normalised_title == "setia alam phase 3b"


def test_a_blocking_clash_refuses_the_registration_and_writes_nothing():
    """ADR-0004 is a hard block: the second person is told who holds it.

    The message has to name the incumbent's code and owner, because "already
    registered" with no detail leaves the user with nowhere to go, and the whole
    point is to send them to that person (or to the request-to-join path).
    """
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering_rule(db)
        incumbent_owner = _user(db, f"{MARKER} Ali")
        challenger = _user(db, f"{MARKER} Siti")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")

        first = register_project(
            db,
            company_id=company_id,
            actor_user_id=incumbent_owner,
            developer_party_id=developer.id,
            title="Setia Alam Phase 3B",
        )

        with pytest.raises(AppException) as exc:
            register_project(
                db,
                company_id=company_id,
                actor_user_id=challenger,
                developer_party_id=developer.id,
                title="setia alam ph 3b",
            )

        assert exc.value.status_code == 409
        assert first.project_code in exc.value.detail["message"]
        assert f"{MARKER} Ali" in exc.value.detail["message"]

        # Nothing partial left behind: no second project, and the numbering
        # sequence was not consumed by the rejected attempt.
        codes = db.execute(
            text("select project_code from projects where company_id = :c"),
            {"c": company_id},
        ).scalars().all()
        assert codes == ["PRJ-000123"]


def test_a_context_only_clash_still_registers():
    """Between the surfacing and blocking bars, the user is informed, not stopped.

    "IKI Hotel" against "The Jerai Hotel" scores 0.600: worth showing, not worth
    refusing. Refusing here would block ordinary unrelated work, since the pipeline
    is full of similarly-named hotels and residences.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering_rule(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _developer(db, company_id, f"{MARKER} Jerai Group")

        register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=developer.id,
            title="The Jerai Hotel",
        )
        second = register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=developer.id,
            title="IKI Hotel",
        )

        assert second.project_code == "PRJ-000124"


def test_registering_without_a_numbering_rule_is_refused_not_silently_uncoded():
    """A project with no code is unusable: every screen and message quotes it.

    ``NumberingService`` returns None when no rule is configured, and letting that
    None reach the column would either violate NOT NULL at flush time (an opaque
    500) or, worse, store an empty string.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _developer(db, company_id, f"{MARKER} SP Setia")

        with pytest.raises(AppException) as exc:
            register_project(
                db,
                company_id=company_id,
                actor_user_id=owner,
                developer_party_id=developer.id,
                title="Setia Alam Phase 3B",
            )

        assert exc.value.status_code == 422
        assert "numbering" in exc.value.detail["message"].lower()


def test_leaving_the_developer_blank_does_not_buy_a_free_duplicate():
    """The exclusivity lock must not be opt-out, and the opt-out must not be a blank field.

    Developer is optional on the form. The clash search used to be filtered on
    ``developer_party_id == <the value given>``, so registering with it blank compared the
    title against other developer-less projects only - in practice against nothing. Two
    salespeople could each claim the same development simply by not saying whose it was,
    which is the one outcome this module exists to prevent.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering_rule(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _developer(db, company_id, f"{MARKER} Mah Sing")

        register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=developer.id,
            title="Kepong Metropolitan Serviced Apartments",
        )

        with pytest.raises(AppException) as exc:
            register_project(
                db,
                company_id=company_id,
                actor_user_id=owner,
                developer_party_id=None,
                title="Kepong Metropolitan Serviced Apartments",
            )

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "project_already_registered"


def test_a_blank_developer_blocks_on_a_partial_name_too():
    """Same rule as the named-developer path: containment is sameness.

    Typing a shorter form of a claimed title with no developer chosen is the exact case
    the user hit - the candidate was listed as similar but nothing stopped the save.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering_rule(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _developer(db, company_id, f"{MARKER} Mah Sing")

        register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=developer.id,
            title="Kepong Metropolitan Serviced Apartments",
        )

        with pytest.raises(AppException) as exc:
            register_project(
                db,
                company_id=company_id,
                actor_user_id=owner,
                developer_party_id=None,
                title="Kepong Metropolitan",
            )

        assert exc.value.status_code == 409


def test_naming_a_different_developer_clears_the_blank_developer_block():
    """The block corrects itself as the form is filled in, so it cannot become a dead end.

    Blocking an unknown developer is a "cannot rule it out" verdict, not a claim of
    sameness. The moment the user names a developer who is demonstrably someone else, the
    two projects are different developments and the registration must go through.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering_rule(db)
        owner = _user(db, f"{MARKER} Ali")
        mah_sing = _developer(db, company_id, f"{MARKER} Mah Sing")
        sp_setia = _developer(db, company_id, f"{MARKER} SP Setia")

        register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=mah_sing.id,
            title="Kepong Metropolitan Serviced Apartments",
        )
        second = register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=sp_setia.id,
            title="Kepong Metropolitan Serviced Apartments",
        )

        assert second.developer_party_id == sp_setia.id


def test_two_developer_less_projects_with_unrelated_titles_both_register():
    """Widening the search must not turn every blank-developer save into a clash.

    Only a title that scores at or above the blocking bar (or contains one) blocks; an
    ordinary second project with its own name is unaffected.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        _numbering_rule(db)
        owner = _user(db, f"{MARKER} Ali")

        register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=None,
            title="Bukit Jalil Corporate Tower",
        )
        second = register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=None,
            title="Penang Waterfront Convention Centre",
        )

        assert second.project_code == "PRJ-000124"
