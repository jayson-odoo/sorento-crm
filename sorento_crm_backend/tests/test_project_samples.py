"""S4 sample submissions (UAC Group F, AC-F1 and AC-F2).

The interesting rule is AC-F2: a sample may not be submitted against a SUPERSEDED
version. That enforces the client's "update the quotation first" rule -- sending a
sample against a price the developer is no longer looking at is how a project ends up
delivered at last month's number.

The corollary the AC does not spell out, and which these tests pin: a sample already
recorded against a version that LATER gets superseded stays, and stays editable.
Developer feedback usually arrives after the revise, and refusing to record it would
throw away the one thing the sample exists to capture.
"""
from __future__ import annotations

import itertools
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import User
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-sample"


def _uid() -> str:
    return str(uuid.uuid4())


_TITLE_SEQ = itertools.count(1)


def _title_suffix() -> str:
    """A deterministic, always-digit-bearing per-call project-title suffix.

    Replaces a `_uid()[:6]`-style random hex slice, which lands with no digit
    about (6/16)**6 = ~0.3% of the time. `phase_designators`
    (`app.services.project_clash_service`) tokenizes a title on a required
    `\\d`, so a digit-free suffix leaves BOTH titles' designator sets empty,
    the sibling-development exemption falls through, and the shared "zzt-
    sample tower" prefix then clears the trigram-similarity block before the
    test's own assertion runs (BL-038). A plain counter is always
    digit-bearing, and since it only ever increases, two projects created in
    the same test always get distinct designators too.
    """
    return str(next(_TITLE_SEQ))


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _project(db, company_id: str, owner: str):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Tower {_title_suffix()}",
    )


def _quotation(db, project, owner: str):
    from app.services import project_quotation_service as quotes

    return quotes.create_quotation(
        db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
    )


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)
        quotation = _quotation(db, project, owner)
        yield db, company_id, owner, project, quotation


# ------------------------------------------------------------------ recording


def test_a_sample_binds_to_a_version_not_to_the_quotation(seeded):
    """AC-F1. "Which price was the developer looking at when they approved this" is
    only answerable if the binding is to the version."""
    from app.services import project_quotation_service as quotes
    from app.services import project_sample_service as samples

    db, _company_id, owner, project, quotation = seeded
    version = quotes.current_version(db, quotation.id)

    sample = samples.create_sample(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "submitted_on": date(2026, 7, 20),
            "salesperson_notes": "Left two finishes with the architect",
        },
    )

    assert sample.quotation_version_id == version.id
    assert sample.project_id == project.id


def test_many_samples_may_hang_off_one_version(seeded):
    from app.services import project_quotation_service as quotes
    from app.services import project_sample_service as samples

    db, _company_id, owner, project, quotation = seeded
    version = quotes.current_version(db, quotation.id)

    for label in ("first round", "second round after feedback"):
        samples.create_sample(
            db,
            project=project,
            actor_user_id=owner,
            payload={"quotation_version_id": version.id, "salesperson_notes": label},
        )

    assert len(samples.list_samples(db, project_id=project.id)) == 2


def test_submitting_against_a_superseded_version_is_refused(seeded):
    """AC-F2, and the message has to name the version to go to -- "not allowed" without
    a next step just makes the user try again."""
    from app.services import project_quotation_service as quotes
    from app.services import project_sample_service as samples

    db, _company_id, owner, project, quotation = seeded
    old_version = quotes.current_version(db, quotation.id)
    quotes.revise(db, quotation=quotation, actor_user_id=owner)

    with pytest.raises(AppException) as excinfo:
        samples.create_sample(
            db,
            project=project,
            actor_user_id=owner,
            payload={"quotation_version_id": old_version.id},
        )

    assert excinfo.value.status_code == 409
    assert "v2" in str(excinfo.value.detail or excinfo.value.message)


def test_a_sample_recorded_before_a_revise_survives_it_and_stays_editable(seeded):
    """The feedback the sample exists to capture usually arrives AFTER the revise."""
    from app.services import project_quotation_service as quotes
    from app.services import project_sample_service as samples

    db, _company_id, owner, project, quotation = seeded
    version = quotes.current_version(db, quotation.id)
    sample = samples.create_sample(
        db,
        project=project,
        actor_user_id=owner,
        payload={"quotation_version_id": version.id},
    )

    quotes.revise(db, quotation=quotation, actor_user_id=owner)

    updated = samples.update_sample(
        db,
        sample=sample,
        payload={"developer_feedback": "Wants the matte finish, price to be revisited"},
    )
    assert updated.developer_feedback.startswith("Wants the matte finish")
    assert samples.list_samples(db, project_id=project.id)[0].id == sample.id


def test_a_version_from_another_project_is_refused(seeded):
    """A sample on project A bound to project B's version would corrupt every rollup
    that reads it, and the mistake is one mis-click away in an API client."""
    from app.services import project_quotation_service as quotes
    from app.services import project_sample_service as samples

    db, company_id, owner, project, _own_quotation = seeded
    other_project = _project(db, company_id, owner)
    other_quotation = _quotation(db, other_project, owner)
    other_version = quotes.current_version(db, other_quotation.id)

    with pytest.raises(AppException) as excinfo:
        samples.create_sample(
            db,
            project=project,
            actor_user_id=owner,
            payload={"quotation_version_id": other_version.id},
        )

    assert excinfo.value.status_code == 422


def test_serialisation_carries_the_scope_and_version_a_human_can_read(seeded):
    """No UUIDs in the UI: the panel has to be able to say "House Units v1"."""
    from app.services import project_quotation_service as quotes
    from app.services import project_sample_service as samples

    db, _company_id, owner, project, quotation = seeded
    version = quotes.current_version(db, quotation.id)
    samples.create_sample(
        db,
        project=project,
        actor_user_id=owner,
        payload={"quotation_version_id": version.id, "submitted_on": date(2026, 7, 20)},
    )

    rows = samples.serialize_samples(db, samples.list_samples(db, project_id=project.id))
    assert rows[0]["scope_label"] == "House Units"
    assert rows[0]["version_no"] == 1
    assert rows[0]["is_version_current"] is True
    assert rows[0]["submitted_by_name"] == f"{MARKER} Ali"


def test_a_superseded_binding_is_reported_so_the_panel_can_say_so(seeded):
    from app.services import project_quotation_service as quotes
    from app.services import project_sample_service as samples

    db, _company_id, owner, project, quotation = seeded
    version = quotes.current_version(db, quotation.id)
    samples.create_sample(
        db, project=project, actor_user_id=owner, payload={"quotation_version_id": version.id}
    )
    quotes.revise(db, quotation=quotation, actor_user_id=owner)

    rows = samples.serialize_samples(db, samples.list_samples(db, project_id=project.id))
    assert rows[0]["is_version_current"] is False
    assert rows[0]["version_no"] == 1


def test_deleting_a_sample_is_a_hard_delete(seeded):
    from app.services import project_quotation_service as quotes
    from app.services import project_sample_service as samples

    db, _company_id, owner, project, quotation = seeded
    version = quotes.current_version(db, quotation.id)
    sample = samples.create_sample(
        db, project=project, actor_user_id=owner, payload={"quotation_version_id": version.id}
    )

    samples.delete_sample(db, sample=sample)

    assert samples.list_samples(db, project_id=project.id) == []


def test_the_sample_count_per_version_is_available_for_the_quotation_panel(seeded):
    """The quotations tab needs "2 samples out" without loading the sample list."""
    from app.services import project_quotation_service as quotes
    from app.services import project_sample_service as samples

    db, _company_id, owner, project, quotation = seeded
    version = quotes.current_version(db, quotation.id)
    for _ in range(2):
        samples.create_sample(
            db, project=project, actor_user_id=owner, payload={"quotation_version_id": version.id}
        )

    counts = samples.sample_counts_by_version(db, version_ids=[version.id])
    assert counts[version.id] == 2
