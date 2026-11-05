"""PROJECT-OUTCOME-SINGLE: one Won/Lost outcome per project, none per area.

Written BEFORE the implementation (Phase 2, test-first). Every test here is red until the lane
lands. Contract: documentation/plans/projects/PLAN-project-outcome-single-05nov.md, "Build
contract" BE1-BE9 (each docstring names its id).

Postgres only, via ``blank_session`` or the ``v2`` route world. Every test seeds its own chain.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.main import app  # noqa: F401  MUST be first app import (circular import)
from app.models.activities import ActivityEvent
from app.models.projects import Project
from app.models.user import User
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session
from ._project_register_v2_support import (  # noqa: F401
    STAFF,
    approved_project,
    as_user,
    v2,
)

MARKER = "zzt-pos"
PERMS = {"projects.projects.view", "projects.projects.edit", "projects.projects.manage"}


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return str(db.execute(text("select id from companies where code = 'SRT'")).scalar())


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _status_id(db, key: str) -> str:
    return str(
        db.execute(
            text(
                "select id from statuses where entity_type = 'project' and key = :k "
                "and scope_id is null"
            ),
            {"k": key},
        ).scalar()
    )


def _status_key(db, status_id) -> str:
    return db.execute(
        text("select key from statuses where id = :i"), {"i": str(status_id)}
    ).scalar()


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        yield db, company_id, owner


def _project(db, company_id: str, owner: str, *, status_key: str | None = None) -> Project:
    from app.services.project_service import register_project

    project = register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Tower {_uid()[:8]}",
    )
    if status_key:
        project.status_id = _status_id(db, status_key)
        db.flush()
    return project


def _move(db, project, owner, key: str, **extra):
    from app.services import project_service

    return project_service.change_status(
        db,
        project,
        to_status_id=_status_id(db, key),
        actor_user_id=owner,
        permissions=PERMS,
        **extra,
    )


def _set_outcome(db, project, owner, outcome: str):
    from app.services import project_service

    return project_service.set_project_outcome(
        db, project, outcome=outcome, actor_user_id=owner, permissions=PERMS
    )


_clock = {"n": 0}


def _stage_event_ids(db, project) -> set:
    return {
        str(e.id)
        for e in db.query(ActivityEvent).filter(
            ActivityEvent.entity_type == "project",
            ActivityEvent.entity_id == str(project.id),
            ActivityEvent.system_template == "stage_changed",
        )
    }


def _spaced(db, project, action):
    """Run ``action`` and give every stage_changed row it wrote its own created_at.

    Postgres now() is the transaction start, so every event in one test would share a
    timestamp and 'older than' would be a coin flip. Spacing them makes the ordering real.
    """
    before = _stage_event_ids(db, project)
    result = action()
    db.flush()
    for event in db.query(ActivityEvent).filter(
        ActivityEvent.entity_type == "project",
        ActivityEvent.entity_id == str(project.id),
        ActivityEvent.system_template == "stage_changed",
    ):
        if str(event.id) not in before:
            _clock["n"] += 1
            event.created_at = datetime(2026, 1, 1, 12, 0, 0) + timedelta(minutes=_clock["n"])
    db.flush()
    return result


def _walk(db, project, owner, key: str, **extra):
    _spaced(db, project, lambda: _move(db, project, owner, key, **extra))


def _reopen(db, project, owner):
    _spaced(db, project, lambda: _set_outcome(db, project, owner, "open"))


def _events(db, project, template: str):
    db.expire_all()
    return (
        db.query(ActivityEvent)
        .filter(
            ActivityEvent.entity_type == "project",
            ActivityEvent.entity_id == str(project.id),
            ActivityEvent.system_template == template,
        )
        .all()
    )


# ------------------------------------------------------------------------------ BE1 Mark lost


def test_be1_marking_lost_with_a_valid_reason_sets_outcome_and_reason(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="quoted")

    _move(db, project, owner, "lost", loss_reason="price")

    db.refresh(project)
    assert project.status_id == _status_id(db, "lost")
    assert project.outcome == "lost"
    assert project.loss_reason == "price"


@pytest.mark.parametrize(
    "reason,code",
    [
        (None, "quotation_loss_reason_required"),
        ("", "quotation_loss_reason_required"),
        ("they hated us", "quotation_loss_reason_invalid"),
    ],
)
def test_be1_a_refused_loss_writes_no_status(seeded, reason, code):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="quoted")
    before = project.status_id

    with pytest.raises(AppException) as refused:
        _move(db, project, owner, "lost", loss_reason=reason)

    assert refused.value.status_code == 422
    assert refused.value.code == code
    db.refresh(project)
    assert project.status_id == before
    assert project.outcome == "open"
    assert project.loss_reason is None
    assert all(
        e.system_payload.get("to_status_id") != _status_id(db, "lost")
        for e in _events(db, project, "stage_changed")
    )


def test_be1_the_po_received_move_sets_won_and_clears_any_reason(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="quoted")
    project.loss_reason = "price"
    db.flush()

    _move(db, project, owner, "po_received")

    db.refresh(project)
    assert project.outcome == "won"
    assert project.loss_reason is None


def test_be1_other_moves_leave_outcome_and_reason_alone(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="specified")
    project.outcome = "won"
    project.loss_reason = None
    db.flush()

    _move(db, project, owner, "quoted")

    db.refresh(project)
    assert project.outcome == "won"

    other = _project(db, company_id, owner, status_key="specified")
    _move(db, other, owner, "quoted")
    db.refresh(other)
    assert other.outcome == "open"

    parked = _project(db, company_id, owner, status_key="quoted")
    _move(db, parked, owner, "dormant")
    db.refresh(parked)
    assert parked.outcome == "open"


def test_be1_the_status_route_takes_loss_reason(v2):
    w = v2
    project = approved_project(w)
    project.status_id = _status_id(w.db, "quoted")
    w.db.flush()
    lost_id = _status_id(w.db, "lost")

    refused = as_user(w, w.owner).post(
        f"{STAFF}/{project.id}/status", json={"to_status_id": lost_id}
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "quotation_loss_reason_required"
    w.db.expire_all()
    assert w.db.get(Project, project.id).status_id == _status_id(w.db, "quoted")

    moved = as_user(w, w.owner).post(
        f"{STAFF}/{project.id}/status", json={"to_status_id": lost_id, "loss_reason": "price"}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["outcome"] == "lost"
    w.db.expire_all()
    assert w.db.get(Project, project.id).loss_reason == "price"


# ------------------------------------------------------------------------------ BE2 first PO


def test_be2_the_first_po_sets_won(seeded):
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="quoted")
    project.loss_reason = "price"
    db.flush()

    pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={"po_source": "contractor_direct", "po_number": f"PO-{_uid()[:6]}"},
    )

    db.refresh(project)
    assert project.status_id == _status_id(db, "po_received")
    assert project.outcome == "won"
    assert project.loss_reason is None


def test_be2_a_po_that_does_not_move_the_status_leaves_outcome_alone(seeded):
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="quoted")
    db.execute(
        text(
            "delete from status_transitions where entity_type = 'project' "
            "and to_status_id = :t"
        ),
        {"t": _status_id(db, "po_received")},
    )

    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={"po_source": "contractor_direct", "po_number": f"PO-{_uid()[:6]}"},
    )

    db.refresh(project)
    assert getattr(po, "_status_moved", None) is False
    assert project.outcome == "open"


# ------------------------------------------------------------------------------ BE3 outcome


def test_be3_mark_won_from_open_leaves_the_status_alone(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="specified")

    _set_outcome(db, project, owner, "won")

    db.refresh(project)
    assert project.outcome == "won"
    assert project.loss_reason is None
    assert project.status_id == _status_id(db, "specified")


def test_be3_mark_won_from_lost_is_refused_with_project_lost(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="quoted")
    _move(db, project, owner, "lost", loss_reason="price")

    with pytest.raises(AppException) as refused:
        _set_outcome(db, project, owner, "won")

    assert refused.value.status_code == 409
    assert refused.value.code == "project_lost"
    assert "Re-open the project first" in refused.value.message
    db.refresh(project)
    assert project.outcome == "lost"


def test_be3_mark_won_on_a_won_project_is_a_no_op(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="specified")
    _set_outcome(db, project, owner, "won")
    first = len(_events(db, project, "outcome_changed"))

    _set_outcome(db, project, owner, "won")

    db.refresh(project)
    assert project.outcome == "won"
    assert len(_events(db, project, "outcome_changed")) == first


def test_be3_reopen_from_won_clears_the_reason_and_keeps_the_status(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="quoted")
    _move(db, project, owner, "po_received")
    assert project.outcome == "won"

    _set_outcome(db, project, owner, "open")

    db.refresh(project)
    assert project.outcome == "open"
    assert project.loss_reason is None
    assert project.status_id == _status_id(db, "po_received")


def test_be3_reopen_on_an_open_project_is_a_no_op(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="quoted")

    _set_outcome(db, project, owner, "open")

    db.refresh(project)
    assert project.outcome == "open"
    assert _events(db, project, "outcome_changed") == []


def test_be3_reopen_from_the_lost_rung_restores_the_previous_rung(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="registered")
    _walk(db, project, owner, "specified")
    _walk(db, project, owner, "quoted")
    _walk(db, project, owner, "lost", loss_reason="price")
    assert project.outcome == "lost"

    _reopen(db, project, owner)

    db.refresh(project)
    assert project.outcome == "open"
    assert project.loss_reason is None
    assert _status_key(db, project.status_id) == "quoted"
    # The direct write is recorded as a stage change too.
    targets = [e.system_payload.get("to_status_id") for e in _events(db, project, "stage_changed")]
    assert targets.count(_status_id(db, "quoted")) >= 2


def test_be3_a_second_loss_and_reopen_returns_to_the_rung_before_the_newest_loss(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="registered")
    _walk(db, project, owner, "specified")
    _walk(db, project, owner, "lost", loss_reason="price")
    _reopen(db, project, owner)
    assert _status_key(db, project.status_id) == "specified"
    _walk(db, project, owner, "quoted")
    _walk(db, project, owner, "lost", loss_reason="lead_time")

    _reopen(db, project, owner)

    db.refresh(project)
    assert _status_key(db, project.status_id) == "quoted"


def test_be3_reopen_with_no_history_falls_back_to_the_initial_status(seeded):
    from app.services import status_service

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="lost")
    project.outcome = "lost"
    project.loss_reason = "price"
    db.flush()
    initial = status_service.initial_status(db, "project", None)

    _set_outcome(db, project, owner, "open")

    db.refresh(project)
    assert project.outcome == "open"
    assert project.status_id == initial.id


def test_be3_a_real_change_records_an_outcome_changed_event(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="specified")

    _set_outcome(db, project, owner, "won")
    _set_outcome(db, project, owner, "open")

    payloads = [e.system_payload for e in _events(db, project, "outcome_changed")]
    assert {"outcome": "won"} in payloads
    assert {"outcome": "open"} in payloads
    assert len(payloads) == 2


def test_be3_an_unknown_outcome_is_refused(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)

    with pytest.raises(AppException) as refused:
        _set_outcome(db, project, owner, "lost")  # lost goes through the stage move
    assert refused.value.status_code == 422
    assert refused.value.code == "project_outcome_invalid"

    with pytest.raises(AppException) as nonsense:
        _set_outcome(db, project, owner, "maybe")
    assert nonsense.value.code == "project_outcome_invalid"


def test_be3_the_outcome_route_marks_won_and_reopens(v2):
    w = v2
    project = approved_project(w)
    project.status_id = _status_id(w.db, "specified")
    w.db.flush()

    won = as_user(w, w.owner).post(f"{STAFF}/{project.id}/outcome", json={"outcome": "won"})
    assert won.status_code == 200, won.text
    assert won.json()["outcome"] == "won"
    assert won.json()["status_id"] == _status_id(w.db, "specified")

    reopened = as_user(w, w.owner).post(
        f"{STAFF}/{project.id}/outcome", json={"outcome": "open"}
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["outcome"] == "open"


def test_be3_the_outcome_route_refuses_won_on_a_lost_project(v2):
    w = v2
    project = approved_project(w)
    project.status_id = _status_id(w.db, "quoted")
    w.db.flush()
    moved = as_user(w, w.owner).post(
        f"{STAFF}/{project.id}/status",
        json={"to_status_id": _status_id(w.db, "lost"), "loss_reason": "price"},
    )
    assert moved.status_code == 200, moved.text

    refused = as_user(w, w.owner).post(f"{STAFF}/{project.id}/outcome", json={"outcome": "won"})
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "project_lost"

    reopened = as_user(w, w.owner).post(
        f"{STAFF}/{project.id}/outcome", json={"outcome": "open"}
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["outcome"] == "open"
    assert reopened.json()["status_id"] == _status_id(w.db, "quoted")


def test_be3_the_outcome_route_validates_the_body(v2):
    w = v2
    project = approved_project(w)

    for body in ({"outcome": "maybe"}, {"outcome": "lost"}, {}):
        res = as_user(w, w.owner).post(f"{STAFF}/{project.id}/outcome", json=body)
        assert res.status_code == 422, (body, res.text)


def test_be3_the_outcome_route_needs_the_edit_permission(v2):
    w = v2
    project = approved_project(w)

    denied = as_user(w, w.nobody).post(f"{STAFF}/{project.id}/outcome", json={"outcome": "won"})
    assert denied.status_code == 403, denied.text
    w.db.expire_all()
    assert w.db.get(Project, project.id).outcome == "open"


# ------------------------------------------------------------------------------ BE4 / BE5

# The proposal flow helpers live with the proposal-quotation suite; importing them keeps one
# definition of "a priced, signed, issued proposal".


def test_be4_accept_wins_an_open_project_and_writes_no_area_outcome():
    from app.services import project_quotation_document_service as qdocs

    from .test_project_proposal_quotation import _issue, _price, _setup

    with blank_session() as db:
        _company, owner, product, project, document, scope = _setup(db)
        _price(db, scope, product, owner, "100.00")
        record = _issue(db, document, owner)
        assert project.outcome == "open"

        qdocs.accept_issue(
            db,
            terms_accepted=True,
            record=record,
            signer_name=f"{MARKER} Kelly",
            mode="type",
            image_data_uri="data:image/png;base64,zzt",
        )

        db.refresh(project)
        db.refresh(scope)
        assert record.accepted_at is not None
        assert project.outcome == "won"
        assert scope.outcome == "open"
        assert scope.decided_at is None
        assert not hasattr(qdocs, "_win_the_scopes_on")


def test_be4_accept_on_a_lost_project_is_recorded_and_stays_lost():
    from app.services import project_quotation_document_service as qdocs

    from .test_project_proposal_quotation import _issue, _price, _setup

    with blank_session() as db:
        _company, owner, product, project, document, scope = _setup(db)
        _price(db, scope, product, owner, "100.00")
        record = _issue(db, document, owner)
        project.outcome = "lost"
        project.loss_reason = "price"
        db.flush()

        qdocs.accept_issue(
            db,
            terms_accepted=True,
            record=record,
            signer_name=f"{MARKER} Kelly",
            mode="type",
            image_data_uri="data:image/png;base64,zzt",
        )

        db.refresh(project)
        assert record.accepted_at is not None
        assert project.outcome == "lost"
        assert project.loss_reason == "price"


def test_be5_make_quotation_is_allowed_on_open_and_won_and_copies_every_area():
    from app.services import project_quotation_document_service as qdocs

    from .test_project_proposal_quotation import _issue, _make, _price, _setup

    for outcome in ("open", "won"):
        with blank_session() as db:
            _company, owner, product, project, proposal, first = _setup(db)
            second = qdocs.add_scope(
                db, document=proposal, scope_label=f"{MARKER} Common", actor_user_id=owner
            )
            _price(db, first, product, owner, "100.00", 4)
            _price(db, second, product, owner, "55.00", 1)
            record = _issue(db, proposal, owner)
            project.outcome = outcome
            db.flush()

            quotation = _make(db, proposal, record, owner)

            assert quotation.kind == "quotation"
            assert len(qdocs.list_scopes(db, quotation)) == 2


def test_be5_make_quotation_is_refused_on_a_lost_project():
    from .test_project_proposal_quotation import _issue, _make, _price, _setup

    with blank_session() as db:
        _company, owner, product, project, proposal, scope = _setup(db)
        _price(db, scope, product, owner, "100.00")
        record = _issue(db, proposal, owner)
        project.outcome = "lost"
        project.loss_reason = "price"
        db.flush()

        with pytest.raises(AppException) as refused:
            _make(db, proposal, record, owner)

        assert refused.value.status_code == 409
        assert refused.value.code == "project_lost"
        assert "Re-open it before making its quotation" in refused.value.message


# ------------------------------------------------------------------------------ BE6 pipeline


def _quote(db, project, owner, *, unit_price: str, quantity=1, scope="House Units"):
    from .test_project_forecast import _quote as quote

    return quote(db, project, owner, unit_price=unit_price, quantity=quantity, scope=scope)


def test_be6_an_open_project_counts_all_its_areas(seeded):
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    _quote(db, project, owner, unit_price="1000.00", quantity=10, scope="House Units")
    _quote(db, project, owner, unit_price="500.00", quantity=4, scope="Common Area")

    assert fc.forecast(db, company_id=company_id)["pipeline"] == Decimal("12000.00")


def test_be6_won_and_lost_projects_count_zero_pipeline_but_won_stays_committed(seeded):
    from app.services import project_forecast_service as fc
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    won = _project(db, company_id, owner)
    lost = _project(db, company_id, owner)
    _quote(db, won, owner, unit_price="1000.00", quantity=10)
    _quote(db, lost, owner, unit_price="1000.00", quantity=10)
    won.outcome = "won"
    lost.outcome = "lost"
    lost.loss_reason = "price"
    db.flush()
    pos.create_po(
        db,
        project=lost,
        actor_user_id=owner,
        payload={
            "po_source": "contractor_direct",
            "po_number": f"PO-{_uid()[:6]}",
            "po_amount": Decimal("700.00"),
        },
    )

    numbers = fc.forecast(db, company_id=company_id)
    assert numbers["pipeline"] == Decimal("0.00")
    # Committed counts POs, lost projects included.
    assert numbers["committed"] == Decimal("700.00")


def test_be6_a_project_holding_a_quotation_counts_only_its_areas():
    """The proposal's own areas are superseded by the quotation document's copies, so the
    same money is not counted twice."""
    from app.services import project_forecast_service as fc
    from app.services import project_quotation_document_service as qdocs

    from .test_project_proposal_quotation import _issue, _make, _price, _setup

    with blank_session() as db:
        company_id, owner, product, project, proposal, scope = _setup(db)
        _price(db, scope, product, owner, "100.00", 2)
        record = _issue(db, proposal, owner)
        quotation = _make(db, proposal, record, owner)
        assert project.outcome == "open"
        assert qdocs.project_quotation(db, project.id).id == quotation.id

        assert fc.forecast(db, company_id=company_id)["pipeline"] == Decimal("200.00")


# ------------------------------------------------------------------------------ BE7 loss report


def test_be7_loss_reasons_count_lost_projects_by_project_reason(seeded):
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    for reason in ("price", "price", "lead_time"):
        project = _project(db, company_id, owner)
        project.outcome = "lost"
        project.loss_reason = reason
    stray = _project(db, company_id, owner)
    stray.loss_reason = "price"  # not lost: not counted
    area, _v = _quote(db, stray, owner, unit_price="10.00")
    area.loss_reason = "price"  # per-area column is ignored
    db.flush()

    rows = {r["reason"]: r for r in fc.loss_reason_counts(db, company_id=company_id)}
    assert rows["price"]["count"] == 2
    assert rows["price"]["label"] == "Price"
    assert rows["lead_time"]["count"] == 1
    assert set(rows[next(iter(rows))]) == {"reason", "label", "count"}


# ------------------------------------------------------------------------------ BE8 PO intake


def test_be8_the_outcome_rank_is_gone_from_po_intake():
    from app.services import project_po_confirm, project_po_reading

    assert not hasattr(project_po_reading, "_OUTCOME_RANK")
    assert not hasattr(project_po_confirm, "_OUTCOME_RANK")
    # Behaviour (one area binds, two stay unbound) lives in test_project_po_intake.py.


# ------------------------------------------------------------------------------ BE9 removals


def test_be9_the_area_outcome_service_functions_are_gone():
    from app.services import project_quotation_service as quotes

    for name in ("set_outcome", "derive_project_outcome", "sync_project_outcome"):
        assert not hasattr(quotes, name), name


def test_be9_the_area_outcome_route_is_gone(v2):
    w = v2
    project = approved_project(w)
    res = as_user(w, w.owner).post(
        f"/api/v1/project-sales/quotations/{_uid()}/outcome",
        json={"outcome": "won"},
    )
    assert res.status_code in (404, 405), res.text
    del project


def test_be9_area_responses_carry_no_outcome_fields():
    from app.schemas import projects as schemas

    for name, model in vars(schemas).items():
        fields = getattr(model, "model_fields", None)
        if not fields or "Quotation" not in name or "Version" in name or "Line" in name:
            continue
        for gone in ("outcome", "loss_reason", "decided_at", "loss_reason_label"):
            assert gone not in fields, f"{name}.{gone}"
