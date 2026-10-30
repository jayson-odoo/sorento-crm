"""PS-REGISTER-CHECK-FIRST UAC S1-S4: a salesperson (submit slug only) is held to the same
clash block as staff when SUBMITTING; drafts stay free.

Red-first. Titles: an approved incumbent "ZZT 100 units DSTH Taman Contoh" under developer D. A new
title that contains it (same single designator "100") blocks under D; the same words under another
developer never block. Every row is seeded here.
"""
from __future__ import annotations

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_register_v2_support import (  # noqa: F401
    LIST,
    STAFF,
    approved_project,
    as_user,
    developer,
    register_body,
    seed_lead,
    v2,
)

INCUMBENT = "ZZT 100 units DSTH Taman Contoh"
BLOCKING = "ZZT 100 units DSTH Taman Contoh Residensi"
SUBMIT_ONLY = {"projects.registrations.submit"}


def _world(w):
    dev = developer(w.db, w.company_id, "ZZT Developer D Sdn Bhd")
    incumbent = approved_project(w, ttl=INCUMBENT, dev=dev)
    return dev, incumbent


def _count(w, ttl: str) -> int:
    from app.models.projects import Project

    w.db.expire_all()
    return w.db.query(Project).filter(Project.company_id == w.company_id, Project.title == ttl).count()


def _payload(w, ttl: str, dev):
    lead = seed_lead(w, w.sub_b)
    return {
        "title": ttl,
        "developer_party_id": dev.id,
        "customer_id": w.customer.id,
        "lead_id": lead.id,
    }


def _register(w, ttl: str, dev, *, submit: bool):
    from app.services import project_registration_service as svc

    return svc.crm_register(
        w.db, company_id=w.company_id, user_id=w.sub_b, payload=_payload(w, ttl, dev), submit=submit
    )


def _draft(w, ttl: str, dev):
    row = _register(w, ttl, dev, submit=False)
    w.db.flush()
    return row


# ------------------------------------------------------------------ S1


def test_ac_s1_submitting_a_blocking_title_is_refused_with_409_and_no_row(v2):
    from app.services.error_handler import AppException

    dev, incumbent = _world(v2)
    with pytest.raises(AppException) as exc:
        _register(v2, BLOCKING, dev, submit=True)
    assert exc.value.status_code == 409
    assert exc.value.code == "project_already_registered"
    assert _count(v2, BLOCKING) == 0


def test_ac_s1_the_refusal_message_is_the_one_staff_get(v2):
    from app.services.error_handler import AppException

    dev, _incumbent = _world(v2)
    with pytest.raises(AppException) as exc:
        _register(v2, BLOCKING, dev, submit=True)
    assert "already registered" in exc.value.message


def test_ac_s1_over_http_a_submit_only_user_gets_409_and_no_project(v2):
    dev, incumbent = _world(v2)
    res = as_user(v2, v2.sub_b).post(
        LIST,
        json={**register_body(v2, user=v2.sub_b, title=BLOCKING, developer_party_id=dev.id), "submit": True},
    )
    assert res.status_code == 409, res.text
    assert res.json()["code"] == "project_already_registered"
    assert _count(v2, BLOCKING) == 0


# ------------------------------------------------------------------ S2


def test_ac_s2_submitting_a_draft_with_a_blocking_title_is_refused_and_stays_a_draft(v2):
    from app.models.projects import Project
    from app.services import project_registration_service as svc
    from app.services.error_handler import AppException

    dev, _incumbent = _world(v2)
    draft = _draft(v2, BLOCKING, dev)
    before = draft.approval_state
    with pytest.raises(AppException) as exc:
        svc.crm_submit(v2.db, draft, user_id=v2.sub_b, payload={}, permissions=SUBMIT_ONLY)
    assert exc.value.status_code == 409
    assert exc.value.code == "project_already_registered"
    v2.db.expire_all()
    assert v2.db.get(Project, draft.id).approval_state == before == "draft"


# ------------------------------------------------------------------ S3 drafts are free (regression guard)


def test_ac_s3_saving_a_draft_with_a_blocking_title_still_saves(v2):
    dev, _incumbent = _world(v2)
    row = _register(v2, BLOCKING, dev, submit=False)
    v2.db.flush()
    assert row.approval_state == "draft"
    assert _count(v2, BLOCKING) == 1


def test_ac_s3_over_http_a_blocking_draft_saves(v2):
    dev, _incumbent = _world(v2)
    res = as_user(v2, v2.sub_b).post(
        LIST,
        json={**register_body(v2, user=v2.sub_b, title=BLOCKING, developer_party_id=dev.id), "submit": False},
    )
    assert res.status_code == 201, res.text


# ------------------------------------------------------------------ S4 non-blocking near match (regression guard)


def test_ac_s4_the_same_words_under_another_developer_do_not_block_submit(v2):
    _dev, _incumbent = _world(v2)
    other = developer(v2.db, v2.company_id, "ZZT Developer E Sdn Bhd")
    row = _register(v2, BLOCKING, other, submit=True)
    v2.db.flush()
    assert row.approval_state == "pending"


def test_ac_s4_a_draft_for_another_developer_submits(v2):
    from app.services import project_registration_service as svc

    _dev, _incumbent = _world(v2)
    other = developer(v2.db, v2.company_id, "ZZT Developer E Sdn Bhd")
    draft = _draft(v2, BLOCKING, other)
    svc.crm_submit(v2.db, draft, user_id=v2.sub_b, payload={}, permissions=SUBMIT_ONLY)
    assert draft.approval_state == "pending"


# ------------------------------------------------------------------ S5 no holder name for a user without view


def _bare_submitter(w):
    """A user whose ONLY permission is projects.registrations.submit (no view, no view_own)."""
    from ._project_registration_support import MARKER, active_user, grant

    uid_ = active_user(w.db, f"{MARKER} Bare Submitter")
    grant(w.db, uid_, "projects.registrations.submit", w.company_id)
    w.perms[uid_] = {"projects.registrations.submit"}
    return uid_


def _owner_name(w) -> str:
    from app.models.user import User

    return w.db.get(User, w.owner).name


def _bare_payload(w, user, ttl, dev):
    return {
        "title": ttl,
        "developer_party_id": dev.id,
        "customer_id": w.customer.id,
        "lead_id": seed_lead(w, user).id,
    }


def _assert_no_holder(w, message: str, incumbent):
    assert _owner_name(w) not in message, message
    assert incumbent.project_code in message, message


def test_ac_s5_crm_register_409_hides_the_holder_name_from_a_user_without_view(v2):
    from app.services import project_registration_service as svc
    from app.services.error_handler import AppException

    dev, incumbent = _world(v2)
    user = _bare_submitter(v2)
    with pytest.raises(AppException) as exc:
        svc.crm_register(
            v2.db, company_id=v2.company_id, user_id=user,
            payload=_bare_payload(v2, user, BLOCKING, dev), submit=True,
        )
    assert exc.value.status_code == 409
    assert exc.value.code == "project_already_registered"
    _assert_no_holder(v2, exc.value.message, incumbent)


def test_ac_s5_crm_submit_409_hides_the_holder_name_from_a_user_without_view(v2):
    from app.services import project_registration_service as svc
    from app.services.error_handler import AppException

    dev, incumbent = _world(v2)
    user = _bare_submitter(v2)
    draft = svc.crm_register(
        v2.db, company_id=v2.company_id, user_id=user,
        payload=_bare_payload(v2, user, BLOCKING, dev), submit=False,
    )
    v2.db.flush()
    with pytest.raises(AppException) as exc:
        svc.crm_submit(v2.db, draft, user_id=user, payload={}, permissions=SUBMIT_ONLY)
    assert exc.value.code == "project_already_registered"
    _assert_no_holder(v2, exc.value.message, incumbent)


def test_ac_s5_http_409_hides_the_holder_name_from_a_user_without_view(v2):
    dev, incumbent = _world(v2)
    user = _bare_submitter(v2)
    res = as_user(v2, user).post(LIST, json={**_bare_payload(v2, user, BLOCKING, dev), "submit": True})
    assert res.status_code == 409, res.text
    body = res.json()
    assert body["code"] == "project_already_registered"
    _assert_no_holder(v2, res.text, incumbent)


def test_ac_s5_staff_with_view_still_sees_the_holder_name(v2):
    """Regression guard: staff keep today's message."""
    dev, incumbent = _world(v2)
    res = as_user(v2, v2.sales_b).post(
        LIST, json=register_body(v2, user=v2.sales_b, title=BLOCKING, developer_party_id=dev.id)
    )
    assert res.status_code == 409, res.text
    assert _owner_name(v2) in res.text
