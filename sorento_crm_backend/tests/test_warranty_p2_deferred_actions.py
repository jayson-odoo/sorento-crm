"""AFTER-SALES-P2 coverage: the six deferred (countdown) actions and the defect-types read.

Actions (POST /api/v1/pending-actions, then the window lapses and the server commits):
service_job_product.delete (needs after_sales.service_jobs.dispatch), warranty_policy.delete,
warranty_term.delete, warranty_kind.delete, warranty_kind_rule.delete, warranty_kind.archive (admin only,
owner Q1: role admin or superadmin). A kind in use is refused 409 at park time, like the direct route (C4).
GET /api/v1/after-sales/warranty/defect-types -> [{id, label}] of the after_sales_defect_type set, for a
service_jobs.view holder.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from contextlib import contextmanager

from app.models.base import set_company_scope
from app.models.sla import SlaFormAction

from ._warranty_p2_support import (
    DISPATCH,
    VIEW,
    WARRANTY,
    WC,
    api as _api,
    defect,
    env,  # noqa: F401
    foreign_defect,
    make_job,
    make_kind,
    make_policy,
    make_product,
    make_rule,
    make_term,
)

PENDING = "/api/v1/pending-actions"


@contextmanager
def api(env, *args, **kwargs):
    """As P1's `api`, but the session reads every company: `/current` hides an outcome parked under another
    scope, and this suite is about the actions, not company visibility (as test_pending_actions.py does)."""
    with _api(env, *args, **kwargs) as client:
        set_company_scope(env.db, None)
        yield client
MANAGE_TECH = "after_sales.technicians.manage"
NON_ADMIN_FULL = {VIEW, DISPATCH, MANAGE_TECH}


def seed(env, what: str):
    """(action_key, entity_type, entity_id, checker) for a fresh record of that kind."""
    from app.models.service_jobs import ServiceJobProduct
    from app.models.warranty import WarrantyKindRule, WarrantyPolicy, WarrantyProductKind, WarrantyTerm

    def gone(model):
        def check():
            env.db.expire_all()
            return env.db.query(model).filter(model.id == rid).count() == 0
        return check

    if what == "line":
        product, job = make_product(env, *WC), make_job(env)
        row = ServiceJobProduct(id=str(uuid.uuid4()), service_job_id=job.id, product_id=product.id, company_id=env.company_id)
        env.db.add(row)
        env.db.flush()
        rid = row.id
        return "service_job_product.delete", "service_job_product", rid, gone(ServiceJobProduct)
    if what == "policy":
        rid = make_policy(env).id
        return "warranty_policy.delete", "warranty_policy", rid, gone(WarrantyPolicy)
    if what == "term":
        rid = make_term(env, make_policy(env), make_kind(env), "Body", months=12).id
        return "warranty_term.delete", "warranty_term", rid, gone(WarrantyTerm)
    if what == "kind":
        rid = make_kind(env).id
        return "warranty_kind.delete", "warranty_kind", rid, gone(WarrantyProductKind)
    if what == "rule":
        rid = make_rule(env, make_kind(env), "category", "SRT-WC").id
        return "warranty_kind_rule.delete", "warranty_kind_rule", rid, gone(WarrantyKindRule)
    if what == "archive":
        rid = make_kind(env).id

        def archived():
            env.db.expire_all()
            row = env.db.get(WarrantyProductKind, rid)
            return row is not None and row.is_active is False
        return "warranty_kind.archive", "warranty_kind", rid, archived
    raise AssertionError(what)


def park(client, key, entity_type, entity_id):
    return client.post(PENDING, json={"action_key": key, "entity_type": entity_type, "entity_id": entity_id, "payload": {}})


def lapse(env, action_id):
    env.db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)}, synchronize_session=False
    )
    env.db.commit()


def current(client, entity_type, entity_id):
    return client.get(f"{PENDING}/current", params={"entity_type": entity_type, "entity_id": entity_id})


WARRANTY_KINDS = ["policy", "term", "kind", "rule", "archive"]
ALL_KINDS = ["line", *WARRANTY_KINDS]


@pytest.mark.parametrize("what", ALL_KINDS)
def test_parked_action_applies_nothing_then_the_server_commits_when_the_window_lapses(env, what):
    key, etype, rid, done = seed(env, what)
    with api(env, {VIEW, DISPATCH}, roles={"admin"}) as c:
        r = park(c, key, etype, rid)
        assert r.status_code == 202, r.text
        assert not done()
        lapse(env, r.json()["id"])
        body = current(c, etype, rid).json()
    assert body["last_outcome"]["action_key"] == key
    assert body["last_outcome"]["status"] == "committed", body
    assert done()


@pytest.mark.parametrize("what", WARRANTY_KINDS)
def test_warranty_actions_are_refused_for_a_non_admin_holding_every_after_sales_permission(env, what):
    key, etype, rid, done = seed(env, what)
    with api(env, NON_ADMIN_FULL) as c:
        r = park(c, key, etype, rid)
        assert r.status_code == 403, r.text
        assert current(c, etype, rid).json()["pending"] is None
    assert not done()


@pytest.mark.parametrize("role", ["admin", "superadmin"])
@pytest.mark.parametrize("what", WARRANTY_KINDS)
def test_warranty_actions_are_allowed_for_admin_and_superadmin(env, what, role):
    key, etype, rid, _ = seed(env, what)
    with api(env, {VIEW}, roles={role}) as c:
        assert park(c, key, etype, rid).status_code == 202


def test_removing_a_job_product_needs_dispatch_and_view_alone_is_refused(env):
    key, etype, rid, done = seed(env, "line")
    with api(env, {VIEW}) as c:
        assert park(c, key, etype, rid).status_code == 403
    assert not done()
    with api(env, {DISPATCH}) as c:
        assert park(c, key, etype, rid).status_code == 202


@pytest.mark.parametrize("use", ["term", "rule"])
def test_a_kind_in_use_is_refused_409_on_the_deferred_delete_like_the_direct_route(env, use):
    from app.models.warranty import WarrantyProductKind

    kind = make_kind(env)
    if use == "term":
        make_term(env, make_policy(env), kind, "Body", months=12)
    else:
        make_rule(env, kind, "category", "SRT-WC")
    with api(env, {VIEW}, roles={"admin"}) as c:
        r = park(c, "warranty_kind.delete", "warranty_kind", kind.id)
        assert r.status_code == 409, r.text
        assert use in r.text.lower()
        assert current(c, "warranty_kind", kind.id).json()["pending"] is None
    env.db.expire_all()
    assert env.db.get(WarrantyProductKind, kind.id) is not None


def test_a_kind_used_by_a_job_line_is_refused_409_on_the_deferred_delete(env):
    from app.models.service_jobs import ServiceJobProduct

    kind, product, job = make_kind(env), make_product(env, *WC), make_job(env)
    env.db.add(ServiceJobProduct(id=str(uuid.uuid4()), service_job_id=job.id, product_id=product.id, kind_id=kind.id, company_id=env.company_id))
    env.db.flush()
    with api(env, {VIEW}, roles={"admin"}) as c:
        r = park(c, "warranty_kind.delete", "warranty_kind", kind.id)
    assert r.status_code == 409 and "job" in r.text.lower()


def test_defect_types_returns_the_set_options_with_id_and_label_for_a_view_holder(env):
    ids = {label: defect(env, label) for label in ("Crack line", "Leakage", "Rust")}
    foreign_defect(env)
    with api(env, {VIEW}) as c:
        r = c.get(f"{WARRANTY}/defect-types")
    assert r.status_code == 200, r.text
    got = {row["id"]: row["label"] for row in r.json()}
    assert got == {v: k for k, v in ids.items()}
    assert all(set(row) >= {"id", "label"} for row in r.json())


def test_defect_types_is_refused_without_service_jobs_view(env):
    defect(env, "Leakage")
    with api(env, {DISPATCH, MANAGE_TECH}) as c:
        assert c.get(f"{WARRANTY}/defect-types").status_code == 403
