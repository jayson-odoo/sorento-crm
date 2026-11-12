"""AFTER-SALES-P1 tests: creating a service job (standalone module, owner ruling 12 Nov).

A job carries its own customer, contact, site and problem; the related complaint is optional.
Visibility is the after_sales permissions and the company filter only.
"""
from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime

import pytest

from ._service_jobs_p1_support import (
    ALL_PERMS,
    DISPATCH,
    JOBS,
    MANAGE,
    VIEW,
    api,
    env,  # noqa: F401  (fixture)
    live_jobs,
    make_complaint,
    make_job,
    reload_job,
    seeded_env,
)

BODY = {
    "customer_name": "Ms Lim Trading",
    "contact_name": "Ms Lim",
    "contact_phone": "012-345 6789",
    "site_address_line1": "12 Jalan Damai",
    "site_address_line2": "Taman Seri",
    "site_postcode": "47500",
    "site_city": "Subang Jaya",
    "site_state": "Selangor",
    "site_country": "Malaysia",
    "problem": "Basin leaks at the trap",
}


def create(client, **over):
    return client.post(JOBS, json={**BODY, **over})


def test_new_permissions_are_registered():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {e["slug"] for e in PERMISSION_REGISTRY}
    assert {VIEW, DISPATCH, MANAGE} <= slugs
    assert not any(s.startswith("complaint_management.service_jobs") for s in slugs)


def test_the_module_is_registered_with_its_permission_prefix():
    from app.modules.runtime.module_manifest import MODULE_MANIFEST
    from app.modules.runtime.permission_module_map import module_for_permission

    assert "after_sales" in MODULE_MANIFEST
    assert module_for_permission(VIEW) == "after_sales"


# ------------------------------------------------------------------ create


def test_create_makes_a_proposed_numbered_job_with_its_own_details(env):
    with api(env) as client:
        r = create(client)
        assert r.status_code == 201, r.text
        body = r.json()
    yy_mm = datetime.now().strftime("%y/%m")
    assert re.fullmatch(rf"SV{yy_mm}-\d{{4}}", body["job_number"]), body["job_number"]
    assert body["status"] == "proposed"
    assert body["customer_name"] == "Ms Lim Trading"
    assert body["city"] == "Subang Jaya"
    assert body["site_country"] == "Malaysia"
    assert body["problem"] == "Basin leaks at the trap"
    assert body["complaint_id"] is None and body["complaint_number"] is None
    assert reload_job(env, body["id"]).company_id == str(env.company_id)


def test_customer_name_is_required(env):
    with api(env) as client:
        for bad in ("", "   "):
            assert create(client, customer_name=bad).status_code == 422
        assert client.post(JOBS, json={"problem": "x"}).status_code == 422


def test_a_related_complaint_is_optional_and_shown_by_number(env):
    c = make_complaint(env, "rel")
    with api(env) as client:
        r = create(client, complaint_id=c.id)
        assert r.status_code == 201, r.text
        assert r.json()["complaint_number"] == c.complaint_number
        assert create(client, complaint_id=str(uuid.uuid4())).status_code == 422


def test_a_second_live_job_for_the_same_complaint_is_409(env):
    c = make_complaint(env, "two")
    with api(env) as client:
        assert create(client, complaint_id=c.id).status_code == 201
        again = create(client, complaint_id=c.id)
        assert again.status_code == 409, again.text
        assert "already has a live service job" in again.text
        assert create(client).status_code == 201  # no complaint: no limit
    assert len(live_jobs(env, c.id)) == 1


@pytest.mark.parametrize("dead", ["cancelled", "verified"])
def test_a_dead_job_does_not_block_a_new_one(env, dead):
    c = make_complaint(env, "dead")
    make_job(env, c, dead)
    with api(env) as client:
        assert create(client, complaint_id=c.id).status_code == 201


@pytest.mark.parametrize("complaint_status", ["new", "resolved", "closed", "voided", "rejected"])
def test_any_complaint_status_can_be_related(env, complaint_status):
    c = make_complaint(env, "st", status=complaint_status)
    with api(env) as client:
        assert create(client, complaint_id=c.id).status_code == 201


def test_create_needs_dispatch(env):
    with api(env, {VIEW}) as client:
        assert create(client).status_code == 403
    with api(env, set()) as client:
        assert create(client).status_code == 403


def test_visibility_is_the_module_permission_only(env):
    """No coupling to complaint permissions: view alone sees every job, a related complaint included."""
    c = make_complaint(env, "vis")
    job = make_job(env, c, "proposed")
    with api(env, {VIEW}) as client:
        ids = [r["id"] for r in client.get(JOBS, params={"limit": 200}).json()["data"]]
        assert job.id in ids
        got = client.get(f"{JOBS}/{job.id}")
        assert got.status_code == 200 and got.json()["complaint_number"] == c.complaint_number
    with api(env, set()) as client:
        assert client.get(JOBS).status_code == 403


def test_edit_changes_the_details_in_the_same_shape(env):
    with api(env) as client:
        job = create(client).json()
        r = client.put(f"{JOBS}/{job['id']}", json={"customer_name": "Mr Tan", "site_city": "Ipoh", "problem": None})
        assert r.status_code == 200, r.text
        assert r.json()["customer_name"] == "Mr Tan" and r.json()["city"] == "Ipoh" and r.json()["problem"] is None
        assert client.put(f"{JOBS}/{job['id']}", json={"customer_name": "  "}).status_code == 422
    with api(env, {VIEW}) as client:
        assert client.put(f"{JOBS}/{job['id']}", json={"site_city": "x"}).status_code == 403


def test_edit_cannot_relate_a_complaint_that_already_has_a_live_job(env):
    c = make_complaint(env, "edit")
    make_job(env, c, "proposed")
    with api(env) as client:
        other = create(client).json()
        assert client.put(f"{JOBS}/{other['id']}", json={"complaint_id": c.id}).status_code == 409


# ------------------------------------------------------------------ phone


@pytest.mark.parametrize("bad", ["abc", "123", "01"])
def test_a_bad_contact_phone_is_422(env, bad):
    with api(env) as client:
        r = create(client, contact_phone=bad)
        assert r.status_code == 422, r.text
        assert "Enter a valid phone number" in r.text


def test_a_good_contact_phone_is_stored_e164_and_shown_local(env):
    with api(env) as client:
        body = create(client, contact_phone="012-345 6789").json()
    assert body["contact_phone"] == "+60123456789"
    assert body["contact_phone_display"] == "012-345 6789"


def test_a_blank_contact_phone_stays_blank(env):
    with api(env) as client:
        assert create(client, contact_phone="").json()["contact_phone"] is None


# ------------------------------------------------------------------ B3 (real concurrency)

def test_b3_two_concurrent_raises_leave_exactly_one_live_job():
    """Committed data on a private-pool engine over the blank schema, two threads, one barrier."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import NullPool

    from app.database import engine as app_engine, get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.models.base import set_company_scope
    from app.services import numbering_defaults
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.service_job_status_graph import seed_service_job_status_graph
    from app.services.user_service import UserPermissionService
    from . import _pg_fixture
    from ._own_scope_support import sorento

    _pg_fixture.blank_schema_engine()
    name = _pg_fixture._BLANK["name"]
    path = ",".join(f'"{name}{s}"' for s in ("", "_scm", "_dealer_kit", "_chatbot", "_sales", "_finance", "_projects"))
    eng = create_engine(
        app_engine.url.render_as_string(hide_password=False),
        poolclass=NullPool,
        connect_args={"options": f"-csearch_path={path.replace(chr(34), '')},public"},
    ).execution_options(
        schema_translate_map={
            None: name,
            "scm": f"{name}_scm",
            "dealer_kit": f"{name}_dealer_kit",
            "projects": f"{name}_projects",
            "chatbot": f"{name}_chatbot",
            "sales": f"{name}_sales",
            "finance": f"{name}_finance",
        }
    )
    from app.models.complaints import Complaint

    setup = Session(eng)
    company_id = sorento(setup)
    complaint_id = str(uuid.uuid4())
    actor = str(uuid.uuid4())
    scope = frozenset({company_id})
    try:
        from app.models.user import User

        setup.add(User(id=actor, email=f"{actor}@zzt.test", name="ZZT race"))
        seed_service_job_status_graph(setup)
        numbering_defaults.seed_service_job_rule(setup, company_id=company_id)
        setup.add(Complaint(id=complaint_id, complaint_number=f"ZZT-RACE-{complaint_id[:6]}", status="new"))
        setup.commit()

        def _db():
            s = Session(eng)
            set_company_scope(s, scope)
            try:
                yield s
            finally:
                s.close()

        principal = {"id": actor, "email": f"{actor}@zzt.test"}
        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
        app.dependency_overrides[apply_company_scope] = lambda: None
        originals = (UserPermissionService.check_user_has_permission, UserPermissionService.get_user_permission_slugs, UserPermissionService.get_user_role_slugs)
        UserPermissionService.check_user_has_permission = lambda self, u, s: True
        UserPermissionService.get_user_permission_slugs = lambda self, u: list(ALL_PERMS)
        UserPermissionService.get_user_role_slugs = lambda self, u: {"admin"}
        barrier = threading.Barrier(2)
        out = []

        def worker():
            c = TestClient(app)
            barrier.wait()
            out.append(c.post(JOBS, json={**BODY, 'complaint_id': complaint_id}))

        try:
            threads = [threading.Thread(target=worker) for _ in range(2)]
            [t.start() for t in threads]
            [t.join(60) for t in threads]
        finally:
            (UserPermissionService.check_user_has_permission, UserPermissionService.get_user_permission_slugs, UserPermissionService.get_user_role_slugs) = originals
            app.dependency_overrides.clear()

        assert len(out) == 2
        assert sorted(r.status_code for r in out) == [201, 409], [(r.status_code, r.text) for r in out]
        live = setup.execute(
            text(
                "select count(*) from service_jobs j join statuses s on s.id = j.status_id "
                "where j.complaint_id = :c and s.key not in ('cancelled','verified')"
            ),
            {"c": complaint_id},
        ).scalar()
        assert live == 1
    finally:
        setup.rollback()
        for sql in (
            "delete from audit_logs where entity_type = 'service_jobs' and entity_id in (select id::text from service_jobs where complaint_id = :c)",
            "delete from service_jobs where complaint_id = :c",
            "delete from complaints where id = :c",
            "delete from users where id = :u",
            "delete from document_numbering_rules where doc_type = 'service_job'",
            "delete from status_transitions where entity_type = 'service_job'",
            "delete from statuses where entity_type = 'service_job'",
        ):
            try:
                setup.execute(text(sql), {"c": complaint_id, "u": actor})
            except Exception:
                setup.rollback()
        setup.commit()
        setup.close()
        eng.dispose()


# ------------------------------------------------------------------ H1

def test_h1_new_tables_use_uuid_ids():
    from sqlalchemy.dialects.postgresql import UUID

    from app.database import Base
    import app.models.service_jobs  # noqa: F401

    for table in ("technicians", "service_jobs"):
        assert isinstance(Base.metadata.tables[table].c.id.type, UUID), table


@pytest.mark.parametrize("path", [JOBS, f"{JOBS}/", ])
def test_h1_job_list_respects_the_limit_cap(env, path):
    with api(env) as client:
        assert client.get(path, params={"limit": 1000000}).status_code == 422


# ------------------------------------------------------------------ H2

def test_h2_fresh_bootstrap_seeds_can_create_and_confirm():
    """Graph and numbering come from the seeders `scripts/bootstrap_env.py` runs, not migration data."""
    import inspect

    from scripts import bootstrap_env

    src = inspect.getsource(bootstrap_env)
    assert "service_job_status_graph" in src, "bootstrap_env must run the service job graph seeder"
    assert "seed_service_job_rule" in src, "bootstrap_env must seed the service_job numbering rule"

    with seeded_env() as e:
        with api(e) as client:
            job = client.post(JOBS, json=BODY)
            assert job.status_code == 201, job.text
            ok = client.post(
                f"{JOBS}/{job.json()['id']}/confirm",
                json={"scheduled_from": "2026-11-20T10:00:00+08:00", "customer_agreed_by": "Ms Lim"},
            )
            assert ok.status_code == 200, ok.text
            assert ok.json()["status"] == "confirmed"


def test_h2_graph_has_seven_statuses_and_twelve_transitions(env):
    from app.models.status import Status, StatusTransition

    assert env.db.query(Status).filter(Status.entity_type == "service_job").count() == 7
    assert env.db.query(StatusTransition).filter(StatusTransition.entity_type == "service_job").count() == 12
