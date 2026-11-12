"""AFTER-SALES-P1 red tests: Site on the complaint (A1), raising a job (B1-B8), resolution flag (G1),
guards (H1, H2). UAC: documentation/plans/after-sales/service-jobs-p1-acceptance-criteria.md
"""
from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime

import pytest

from ._service_jobs_p1_support import (
    ALL_PERMS,
    COMPLAINTS,
    DISPATCH,
    JOBS,
    MANAGE,
    RESOLUTIONS,
    VIEW,
    api,
    env,  # noqa: F401  (fixture)
    live_jobs,
    make_complaint,
    make_job,
    reload_job,
    seeded_env,
)

SITE = {
    "site_address_line1": "12 Jalan Damai",
    "site_address_line2": "Taman Seri",
    "site_postcode": "47500",
    "site_city": "Subang Jaya",
    "site_state": "Selangor",
    "site_country": "Malaysia",
    "site_contact_name": "Ms Lim",
    "site_contact_phone": "+60127770099",
    "site_latitude": 3.0567,
    "site_longitude": 101.5851,
}


def raise_url(complaint_id):
    return f"{COMPLAINTS}/{complaint_id}/service-jobs"


# ------------------------------------------------------------------ permissions registered

def test_new_permissions_are_registered():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {e["slug"] for e in PERMISSION_REGISTRY}
    assert {VIEW, DISPATCH, MANAGE} <= slugs


# ------------------------------------------------------------------ A1

def test_a1_site_fields_save_through_complaint_update_and_come_back_on_get(env):
    c = make_complaint(env, "A1")
    with api(env) as client:
        put = client.put(f"{COMPLAINTS}/{c.id}", json=SITE)
        assert put.status_code == 200, put.text
        got = client.get(f"{COMPLAINTS}/{c.id}")
        assert got.status_code == 200, got.text
        body = got.json()
        for key, value in SITE.items():
            assert key in body, f"complaint GET dropped {key} (response_model drops undeclared fields)"
            assert body[key] == value, key


# ------------------------------------------------------------------ B1, B2, B4, B5

def test_b1_raise_creates_a_proposed_numbered_job(env):
    c = make_complaint(env, "B1")
    with api(env) as client:
        r = client.post(raise_url(c.id))
        assert r.status_code == 201, r.text
        body = r.json()
        yy_mm = datetime.now().strftime("%y/%m")
        assert re.fullmatch(rf"SV{yy_mm}-\d{{4}}", body["job_number"]), body["job_number"]
        assert body["status"] == "proposed"
        assert body["complaint_id"] == c.id
    job = reload_job(env, body["id"])
    assert job.company_id == c.company_id


def test_b2_raise_again_returns_the_live_job_with_200(env):
    c = make_complaint(env, "B2")
    with api(env) as client:
        first = client.post(raise_url(c.id))
        second = client.post(raise_url(c.id))
    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    assert len(live_jobs(env, c.id)) == 1


@pytest.mark.parametrize("dead", ["cancelled", "verified"])
def test_b4_a_dead_job_does_not_block_a_new_one(env, dead):
    c = make_complaint(env, "B4")
    old = make_job(env, c, dead)
    with api(env) as client:
        r = client.post(raise_url(c.id))
    assert r.status_code == 201, r.text
    assert r.json()["id"] != old.id
    assert len(live_jobs(env, c.id)) == 1


@pytest.mark.parametrize("complaint_status", ["new", "resolved", "closed", "voided", "rejected"])
def test_b5_raise_works_on_a_complaint_in_any_status(env, complaint_status):
    c = make_complaint(env, "B5", status=complaint_status)
    with api(env) as client:
        r = client.post(raise_url(c.id))
    assert r.status_code == 201, r.text


def test_raise_on_unknown_complaint_is_404(env):
    with api(env) as client:
        assert client.post(raise_url(uuid.uuid4())).status_code == 404


# ------------------------------------------------------------------ B8

def test_b8_raise_needs_dispatch_permission(env):
    c = make_complaint(env, "B8")
    with api(env, {VIEW}) as client:
        assert client.post(raise_url(c.id)).status_code == 403
    with api(env, set()) as client:
        assert client.post(raise_url(c.id)).status_code == 403
    assert live_jobs(env, c.id) == []


# ------------------------------------------------------------------ G1, B6, B7

def _resolution(client, name, flag):
    r = client.post(f"{RESOLUTIONS}/", json={"name": name, "requires_service_job": flag})
    assert r.status_code == 201, r.text
    return r.json()


def test_g1_resolution_flag_defaults_off_saves_lists_and_updates(env):
    with api(env) as client:
        plain = client.post(f"{RESOLUTIONS}/", json={"name": f"ZZT plain {uuid.uuid4().hex[:6]}"})
        assert plain.status_code == 201, plain.text
        assert plain.json()["requires_service_job"] is False
        flagged = _resolution(client, f"ZZT flagged {uuid.uuid4().hex[:6]}", True)
        assert flagged["requires_service_job"] is True
        rows = client.get(f"{RESOLUTIONS}/", params={"limit": 200, "query": "ZZT"}).json()["data"]
        by_id = {r["id"]: r for r in rows}
        assert by_id[flagged["id"]]["requires_service_job"] is True
        assert by_id[plain.json()["id"]]["requires_service_job"] is False
        up = client.put(f"{RESOLUTIONS}/{flagged['id']}", json={"requires_service_job": False})
        assert up.status_code == 200, up.text
        assert up.json()["requires_service_job"] is False


def test_b6_resolution_with_flag_raises_a_job_and_is_idempotent(env):
    c = make_complaint(env, "B6")
    with api(env) as client:
        res = _resolution(client, f"ZZT flag {uuid.uuid4().hex[:6]}", True)
        r = client.put(f"{COMPLAINTS}/{c.id}", json={"resolution_id": res["id"]})
        assert r.status_code == 200, r.text
        assert len(live_jobs(env, c.id)) == 1
        again = client.put(f"{COMPLAINTS}/{c.id}", json={"resolution_id": res["id"], "customer_name": "ZZT Again"})
        assert again.status_code == 200, again.text
    assert len(live_jobs(env, c.id)) == 1


def test_b6_complaint_save_never_fails_when_the_job_cannot_be_raised():
    """No graph and no numbering rule seeded: the raise cannot succeed, the save still must."""
    from ._pg_fixture import blank_session
    from ._own_scope_support import sorento, user
    from app.models.base import company_scope
    from ._service_jobs_p1_support import Env

    with blank_session() as db:
        company_id = sorento(db)
        e = Env(db, company_id, user(db, "P1 Unseeded"))
        with company_scope(db, frozenset({company_id})):
            c = make_complaint(e, "B6x")
            with api(e) as client:
                res = _resolution(client, f"ZZT flag {uuid.uuid4().hex[:6]}", True)
                r = client.put(f"{COMPLAINTS}/{c.id}", json={"resolution_id": res["id"]})
                assert r.status_code == 200, r.text
            assert db.execute(__import__("sqlalchemy").text("select count(*) from service_jobs")).scalar() == 0


def test_b7_unflagged_or_cleared_resolution_never_creates_or_deletes_a_job(env):
    c = make_complaint(env, "B7")
    with api(env) as client:
        plain = _resolution(client, f"ZZT plain {uuid.uuid4().hex[:6]}", False)
        assert client.put(f"{COMPLAINTS}/{c.id}", json={"resolution_id": plain["id"]}).status_code == 200
        assert live_jobs(env, c.id) == []
        job = make_job(env, c, "proposed")
        flagged = _resolution(client, f"ZZT flag {uuid.uuid4().hex[:6]}", True)
        assert client.put(f"{COMPLAINTS}/{c.id}", json={"resolution_id": flagged["id"]}).status_code == 200
        assert [j.id for j in live_jobs(env, c.id)] == [job.id]
        cleared = client.put(f"{COMPLAINTS}/{c.id}", json={"resolution_id": None})
        assert cleared.status_code == 200, cleared.text
    assert [j.id for j in live_jobs(env, c.id)] == [job.id]


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
            out.append(c.post(raise_url(complaint_id)))

        try:
            threads = [threading.Thread(target=worker) for _ in range(2)]
            [t.start() for t in threads]
            [t.join(60) for t in threads]
        finally:
            (UserPermissionService.check_user_has_permission, UserPermissionService.get_user_permission_slugs, UserPermissionService.get_user_role_slugs) = originals
            app.dependency_overrides.clear()

        assert len(out) == 2
        assert all(r.status_code in (200, 201) for r in out), [(r.status_code, r.text) for r in out]
        assert len({r.json()["id"] for r in out}) == 1
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

def test_h2_fresh_bootstrap_seeds_can_raise_and_confirm():
    """Graph and numbering come from the seeders `scripts/bootstrap_env.py` runs, not migration data."""
    import inspect

    from scripts import bootstrap_env

    src = inspect.getsource(bootstrap_env)
    assert "service_job_status_graph" in src, "bootstrap_env must run the service job graph seeder"
    assert "seed_service_job_rule" in src, "bootstrap_env must seed the service_job numbering rule"

    with seeded_env() as e:
        c = make_complaint(e, "H2")
        with api(e) as client:
            job = client.post(raise_url(c.id))
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
