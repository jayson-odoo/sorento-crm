"""Shared world for the AFTER-SALES-P1 (service jobs) red tests.

Contract the coder must satisfy (from PLAN-service-jobs-p1-12nov.md, Data + API):

* models   `app.models.service_jobs.ServiceJob`, `app.models.service_jobs.Technician`
* seeds    `app.services.service_job_status_graph.seed_service_job_status_graph(db)` (7 statuses,
           12 transitions, entity_type "service_job") and
           `app.services.numbering_defaults.seed_service_job_rule(connection, *, company_id=None)`
           (doc_type `numbering_defaults.SERVICE_JOB_DOC_TYPE == "service_job"`)
* routes   under `/api/v1/complaints-management`
* wire     a job serialises `id, job_number, complaint_id, complaint_number, customer_name, city,
           status` (the status KEY, e.g. "on_the_way"), `status_label, technician_id, technician_name,
           scheduled_from, scheduled_to, customer_agreed_by, arrived_at, completed_at, verified_at`.
           Lists are `{"data": [...], "pagination": {"total", "page", "limit"}}`.
* errors   missing/blank confirm field -> 422 naming the field; illegal move -> 409.

Models are imported lazily inside helpers so that, while the slice is red, each test fails on
its own `ModuleNotFoundError` instead of one collection error hiding all of them.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pytest

from app.models.base import company_scope
from app.models.complaints import Complaint
from app.rbac.permission_registry import PERMISSION_REGISTRY

from ._own_scope_support import acting, sorento, user
from ._pg_fixture import blank_session, unique_code

BASE = "/api/v1/complaints-management"
JOBS = f"{BASE}/service-jobs"
TECHS = f"{BASE}/technicians"
COMPLAINTS = f"{BASE}/complaints"
RESOLUTIONS = f"{BASE}/complaint-resolutions"

VIEW = "complaint_management.service_jobs.view"
DISPATCH = "complaint_management.service_jobs.dispatch"
MANAGE = "complaint_management.technicians.manage"
NEW_SLUGS = {VIEW, DISPATCH, MANAGE}
ALL_PERMS = {e["slug"] for e in PERMISSION_REGISTRY} | NEW_SLUGS


@dataclass
class Env:
    db: object
    company_id: str
    actor_id: str


@contextmanager
def seeded_env():
    """Blank schema + the P1 seeds (graph and numbering rule) + an actor user, company scoped."""
    from app.services import numbering_defaults
    from app.services.service_job_status_graph import seed_service_job_status_graph

    with blank_session() as db:
        company_id = sorento(db)
        seed_service_job_status_graph(db)
        numbering_defaults.seed_service_job_rule(db, company_id=company_id)
        db.flush()
        actor_id = user(db, "P1 Dispatcher")
        with company_scope(db, frozenset({company_id})):
            yield Env(db, company_id, actor_id)


@pytest.fixture
def env():
    with seeded_env() as e:
        yield e


def api(env: Env, perms=ALL_PERMS, *, user_id: Optional[str] = None, roles=()):
    """A TestClient context acting with exactly ``perms`` (default: everything incl. the new slugs)."""
    return acting(env.db, user_id or env.actor_id, perms, roles=roles)


def make_complaint(env: Env, tag: str = "", *, status: str = "new", **fields) -> Complaint:
    row = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=fields.pop("complaint_number", unique_code(f"SJ{tag}", alpha=True)),
        status=status,
        customer_name=fields.pop("customer_name", f"ZZT Customer {tag}".strip()),
        **fields,
    )
    env.db.add(row)
    env.db.flush()
    return row


def status_id(env: Env, key: str) -> str:
    from app.models.status import Status

    return (
        env.db.query(Status.id)
        .filter(Status.entity_type == "service_job", Status.key == key, Status.scope_id.is_(None))
        .scalar()
    )


def make_tech(env: Env, name: Optional[str] = None, *, active: bool = True, kind: str = "employee"):
    from app.models.service_jobs import Technician

    row = Technician(
        id=str(uuid.uuid4()),
        name=name or unique_code("Tech"),
        phone="+60123456789",
        employment_type=kind,
        is_active=active,
        company_id=env.company_id,
    )
    env.db.add(row)
    env.db.flush()
    return row


_seq = [0]


def make_job(
    env: Env,
    complaint: Complaint,
    key: str = "proposed",
    *,
    technician=None,
    scheduled_from: Optional[datetime] = None,
    scheduled_to: Optional[datetime] = None,
    agreed_by: Optional[str] = None,
    job_number: Optional[str] = None,
):
    """Insert a job row directly, in any status (the API path to a state is tested elsewhere)."""
    from app.models.service_jobs import ServiceJob

    _seq[0] += 1
    row = ServiceJob(
        id=str(uuid.uuid4()),
        job_number=job_number or f"SVT{uuid.uuid4().hex[:6]}-{_seq[0]:04d}",
        complaint_id=complaint.id,
        status_id=status_id(env, key),
        technician_id=technician.id if technician is not None else None,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
        customer_agreed_by=agreed_by,
        company_id=env.company_id,
        created_by=env.actor_id,
    )
    env.db.add(row)
    env.db.flush()
    return row


def reload_job(env: Env, job_id: str):
    from app.models.service_jobs import ServiceJob

    env.db.expire_all()
    return env.db.query(ServiceJob).filter(ServiceJob.id == job_id).one()


def live_jobs(env: Env, complaint_id: str) -> list:
    from app.models.service_jobs import ServiceJob
    from app.models.status import Status

    env.db.expire_all()
    rows = (
        env.db.query(ServiceJob, Status.key)
        .join(Status, Status.id == ServiceJob.status_id)
        .filter(ServiceJob.complaint_id == complaint_id)
        .all()
    )
    return [j for j, k in rows if k not in ("cancelled", "verified")]


def audit_rows(env: Env, job_id: str) -> list:
    from app.models.audit import AuditLog
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    env.db.flush()
    return (
        env.db.query(AuditLog)
        .filter(AuditLog.entity_type == "service_jobs", AuditLog.entity_id == job_id)
        .order_by(AuditLog.changed_at)
        .all()
    )
