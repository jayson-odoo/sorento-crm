"""AFTER-SALES-P2 red tests: who may do what (UAC P1, P2). P3 lives in test_warranty_p2_job_products.py.

Admin is recognised by role slug (`admin` or `superadmin`, as `get_user_role_slugs`), NOT by a permission slug:
the admin cases hold NO permission at all. There is no warranty permission (no slug starting with
`after_sales.warranty`). Configuration writes: admin only (403 for everyone else). Configuration reads and the
job `warranty` field / list `warranty_summary`: `after_sales.service_jobs.view` (or admin).
"""
from __future__ import annotations

from datetime import date

import pytest

from app.rbac.permission_registry import PERMISSION_REGISTRY

from ._warranty_p2_support import (
    DISPATCH,
    JOBS,
    KINDS,
    POLICIES,
    RULES,
    TERMS,
    VIEW,
    WC,
    add_line,
    api,
    env,  # noqa: F401
    make_job,
    make_kind,
    make_policy,
    make_product,
    make_rule,
    make_term,
)

MANAGE_TECH = "after_sales.technicians.manage"
NON_ADMIN_FULL = {VIEW, DISPATCH, MANAGE_TECH}


def test_p1_no_warranty_permission_slug_exists():
    assert [e["slug"] for e in PERMISSION_REGISTRY if e["slug"].startswith("after_sales.warranty")] == []


def world(env):
    policy = make_policy(env, "ZPA", date(2000, 1, 1), date(2000, 12, 31))
    kind = make_kind(env)
    spare = make_kind(env)
    third = make_kind(env)
    rule = make_rule(env, kind, "category", "SRT-WC")
    term = make_term(env, policy, kind, "Body", months=12)
    return dict(policy=policy, kind=kind, spare=spare, third=third, rule=rule, term=term)


def ops(env, w):
    """(name, method, url, json) for every configuration write."""
    from datetime import date

    open_pol = make_policy(env, "ZPOPEN", date(2010, 1, 1), None)
    t2 = make_term(env, w["policy"], w["kind"], "Seat", months=6)
    p, k, r, t = w["policy"], w["kind"], w["rule"], w["term"]
    return [
        ("policy_create", "post", POLICIES, {"version": "ZPNEW", "effective_from": "1990-01-01", "effective_to": "1990-12-31"}),
        ("policy_edit", "patch", f"{POLICIES}/{p.id}", {"policy_text": "x"}),
        ("policy_supersede", "post", f"{POLICIES}/{open_pol.id}/supersede", {"version": "ZPSUP", "effective_from": "2026-12-01"}),
        ("term_create", "post", TERMS, {"policy_id": p.id, "kind_id": w["third"].id, "part_name": "New", "duration_months": 12}),
        ("term_edit", "patch", f"{TERMS}/{t.id}", {"duration_months": 18}),
        ("term_delete", "delete", f"{TERMS}/{t2.id}", None),
        ("kind_create", "post", KINDS, {"code": "zp_new_kind", "name": "ZZT new"}),
        ("kind_archive", "patch", f"{KINDS}/{k.id}", {"is_active": False}),
        ("kind_delete", "delete", f"{KINDS}/{w['spare'].id}", None),
        ("rule_create", "post", RULES, {"kind_id": k.id, "match_type": "category", "match_value": "ZP1"}),
        ("rule_edit", "patch", f"{RULES}/{r.id}", {"match_value": "ZP2"}),
        ("rule_delete", "delete", f"{RULES}/{r.id}", None),
        ("policy_delete", "delete", f"{POLICIES}/{p.id}", None),
    ]


def send(client, method, url, body):
    return getattr(client, method)(url, json=body) if body is not None else getattr(client, method)(url)


OP_NAMES = [
    "policy_create", "policy_edit", "policy_supersede", "term_create", "term_edit", "term_delete", "kind_create",
    "kind_archive", "kind_delete", "rule_create", "rule_edit", "rule_delete", "policy_delete",
]


@pytest.mark.parametrize("role", ["admin", "superadmin"])
def test_p1_admins_can_do_every_configuration_write_holding_no_permission(env, role):
    w = world(env)
    with api(env, set(), roles={role}) as c:
        for name, method, url, body in ops(env, w):
            r = send(c, method, url, body)
            assert r.status_code in (200, 201), (role, name, r.status_code, r.text)


@pytest.mark.parametrize("name", OP_NAMES)
def test_p1_a_non_admin_with_every_after_sales_permission_gets_403_on_each_write(env, name):
    w = world(env)
    (op,) = [o for o in ops(env, w) if o[0] == name]
    with api(env, NON_ADMIN_FULL) as c:
        r = send(c, op[1], op[2], op[3])
    assert r.status_code == 403, (name, r.status_code, r.text)


def read_ops(w):
    return [
        ("get", POLICIES, None),
        ("get", f"{POLICIES}/{w['policy'].id}", None),
        ("get", TERMS + f"?policy_id={w['policy'].id}", None),
        ("get", KINDS, None),
        ("get", RULES, None),
        ("post", f"{RULES}/test", {"product_id": "PRODUCT"}),
    ]


def test_p1_configuration_reads_work_for_a_view_holder(env):
    w = world(env)
    product = make_product(env, *WC)
    with api(env, {VIEW}) as c:
        for method, url, body in read_ops(w):
            body = {"product_id": product.id} if body else None
            r = send(c, method, url, body)
            assert r.status_code == 200, (url, r.status_code, r.text)


@pytest.mark.parametrize("idx", range(6))
def test_p1_configuration_reads_are_403_without_service_jobs_view(env, idx):
    w = world(env)
    product = make_product(env, *WC)
    method, url, body = read_ops(w)[idx]
    body = {"product_id": product.id} if body else None
    with api(env, {DISPATCH, MANAGE_TECH}) as c:
        assert send(c, method, url, body).status_code == 403


def test_p2_a_view_only_user_sees_warranty_on_the_job_and_the_summary_on_the_list(env):
    job = make_job(env)
    product = make_product(env, *WC)
    with api(env) as full:
        add_line(full, job.id, product.id)
    with api(env, {VIEW}) as c:
        got = c.get(f"{JOBS}/{job.id}")
        assert got.status_code == 200 and "warranty" in got.json() and len(got.json()["warranty"]) == 1
        rows = c.get(JOBS, params={"query": job.customer_name}).json()["data"]
        assert "warranty_summary" in rows[0]
