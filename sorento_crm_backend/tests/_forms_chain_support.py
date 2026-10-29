"""Shared world for the forms lifecycle regression chains (tests/test_forms_chain_*.py).

Plan: documentation/plans/forms/PLAN-forms-lifecycle-regression-29oct.md (FORMS-REGRESSION).

One TestClient over the REAL routes on the blank Postgres scratch schema
(tests/_pg_fixture.py), so every chain seeds its own rows and runs in CI's empty database.
What is real and what is stubbed, on purpose:

* Real: every route, its permission dependency (users hold slugs through a real role, see
  `grant`), the form-action dispatcher (grace window, cancel, undo), the handling lock, the
  SLA orchestrator (stage start, resolve, next stage, escalation, the overdue sweep), the
  revision fence, the portal services, in-app notifications, and the outbox writer itself
  (`integration_log` rows, written by the app's own code).
* Stubbed at the network edge only: `respond_messaging_service.send_text_or_template`
  (the one choke point every Respond.io send goes through) records the send and answers
  like a delivered in-window text, so the app writes a `success` outbox row.
* RQ: `queue_service.enqueue_job` records the job instead of pushing to Redis. Complaint
  and stock inquiry sends go through the `respond_io` queue, so `World.drain()` runs those
  jobs inline on this test's connection, exactly as the worker would, and their outbox
  rows land in the scratch schema too. Other queues (notification deliveries) stay recorded.
* The idempotency middleware is off: it is a 10 second duplicate-submit backstop keyed on
  (session, path, body), and a chain legitimately repeats e.g. a bodyless
  `set-pending-approval` on the same form after a reject and resubmit.

Test support only: no implementation lives here. All names are invented.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from ._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"
MARKER = "zzt-fchain"
PORTAL = "/api/v1/public/portal"
SUB = f"{PORTAL}/submissions"
PR_BASE = "/api/v1/procurement/purchase-requests"
SI_BASE = "/api/v1/procurement/stock-inquiries"
CX_BASE = "/api/v1/complaints-management/complaints"
PT_BASE = "/api/v1/dealer-kit/price-tag-requests"
SR_BASE = "/api/v1/project-sales/sample-requests"
FORM_ACTIONS = "/api/v1/sla-management/form-actions"
FORM_SLA = "/api/v1/sla-management/form-sla-tracking"
CONV_SLA = "/api/v1/sla-management/conversation-sla-tracking"
SPACE = "zzt-space"

UNDO = "sla_management.form_sla.undo_action"
ESCALATE = "sla.form.escalate"
EXTEND = "sla_management.conversation_sla_tracking.extend"


def uid() -> str:
    return str(uuid.uuid4())


# ------------------------------------------------------------------ users and RBAC


def user(db, name: str) -> str:
    """An ACTIVE user linked to Sorento, with no email or WhatsApp prefs that would fan out."""
    from app.models.company import UserCompany
    from app.models.user import User

    user_id = uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} {name}", status="ACTIVE"))
    db.flush()
    db.add(UserCompany(id=uid(), user_id=user_id, company_id=SORENTO))
    db.flush()
    return user_id


def grant(db, user_id: str, *slugs: str) -> None:
    """Give `user_id` the slugs through one real role, the way RBAC resolves them."""
    from app.models.user import UserPermission, UserRole, UserRoleAssignment, UserRolePermission

    role = UserRole(id=uid(), slug=f"{MARKER}-{uid()[:10]}", name=f"{MARKER} {uid()[:10]}")
    db.add(role)
    db.flush()
    for slug in slugs:
        permission = db.query(UserPermission).filter(UserPermission.slug == slug).first()
        if permission is None:
            permission = UserPermission(id=uid(), slug=slug, name=slug)
            db.add(permission)
            db.flush()
        db.add(UserRolePermission(id=uid(), role_id=role.id, permission_id=permission.id))
    db.add(UserRoleAssignment(id=uid(), user_id=user_id, role_id=role.id))
    db.flush()


# ------------------------------------------------------------------ portal contact


def contact(db, *, kinds=(), name: str = "salesperson") -> str:
    """A Respond.io contact with a resolvable respond_io_id (so the inbox URL, and with it
    every contact send, resolves), linked to Sorento, granted `kinds` on the portal."""
    from app.models.access import RespondContact

    from ._portal_grant import grant_portal_forms, link_contact_company

    rid = str(900_000_000 + uuid.uuid4().int % 99_999_999)
    row = RespondContact(
        id=uid(),
        phone_number=f"+60{uid().replace('-', '')[:9]}",
        name=f"{MARKER} {name}",
        respond_io_id=rid,
    )
    db.add(row)
    db.flush()
    link_contact_company(db, row.id, SORENTO)
    if kinds:
        grant_portal_forms(db, row.id, list(kinds))
    return row.id


# ------------------------------------------------------------------ settings and SLA chain


def settings_row(db, **over):
    """The single system_settings row (created on first call)."""
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting(id=uid(), name=f"{MARKER} co")
        db.add(row)
    for key, value in over.items():
        setattr(row, key, value)
    db.commit()
    return row


def revision_config(db, kind: str, *, allowed_statuses, max_revisions: Optional[int] = None):
    from app.models.portal import PortalRevisionConfig

    row = PortalRevisionConfig(
        id=uid(),
        source_entity_type=kind,
        is_enabled=True,
        max_revisions=max_revisions,
        allowed_statuses=list(allowed_statuses),
    )
    db.add(row)
    db.commit()
    return row


def sla_chain(db, kind: str, stages: list[dict], *, tiers=(1, 2, 3)) -> SimpleNamespace:
    """A working SLA chain for `kind`: one policy (4h response / 24h resolution per tier),
    one agent, and per stage a team set with a tier-1 and a tier-2 team, each with its own
    member. `stages` are FormSLAConfig kwargs (start_event, resolve_event, advance_on_event,
    grace_seconds, ...) in chain order; consecutive stages are linked by next_config_id.

    Returns the policy, the agent and per stage `{config, team_set, tier1, tier2}` where
    tier1 / tier2 are the member user ids (round robin over one member is deterministic).
    """
    from app.models.access import AccessAgent, AgentTeam, Team, TeamMember
    from app.models.sla import FormSLAConfig, SLAPolicy, SLAPolicyTier

    policy_id = uid()
    db.add(SLAPolicy(id=policy_id, code=unique_code("POL"), name=f"{MARKER} policy"))
    for level in tiers:
        db.add(SLAPolicyTier(id=uid(), policy_id=policy_id, tier_level=level,
                             tier_name=f"Tier {level}", response_hours=4, resolution_hours=24))
    agent_id = uid()
    agent_code = unique_code(f"agent-{kind}")
    db.add(AccessAgent(id=agent_id, code=agent_code, name=f"{MARKER} {kind} agent"))
    db.flush()

    out = []
    for i, stage in enumerate(stages):
        team_set = stage.pop("team_set_code", None) or unique_code(f"ts{i}")
        members = {}
        for tier in (1, 2):
            team_id = uid()
            db.add(Team(id=team_id, name=unique_code(f"team{tier}"), company_id=SORENTO))
            db.add(AgentTeam(id=uid(), agent_id=agent_id, code=team_set, team_id=team_id,
                             tier=tier, company_id=SORENTO))
            db.flush()
            member = user(db, f"{kind} s{i} tier{tier}")
            db.add(TeamMember(id=uid(), team_id=team_id, user_id=member, sort_order=0))
            members[tier] = member
        cfg = FormSLAConfig(
            id=uid(), source_entity_type=kind, stage_code=unique_code(f"stage{i}"),
            policy_id=policy_id, agent_code=agent_code, team_set_code=team_set,
            is_active=True, notify_assignee=True, **stage,
        )
        db.add(cfg)
        db.flush()
        out.append(SimpleNamespace(config=cfg, team_set=team_set, tier1=members[1], tier2=members[2]))
    for here, nxt in zip(out, out[1:]):
        here.config.next_config_id = nxt.config.id
    db.commit()
    return SimpleNamespace(policy_id=policy_id, agent_id=agent_id, stages=out)


# ------------------------------------------------------------------ reads


def trackers(db, kind: str, entity_id: str, *, open_only: bool = False):
    from app.models.sla import ConversationSLATracking as T

    db.expire_all()
    q = db.query(T).filter(T.source_entity_type == kind, T.source_entity_id == str(entity_id))
    if open_only:
        q = q.filter(T.is_resolved.is_(False), T.voided_at.is_(None))
    return q.order_by(T.initiated_at, T.id).all()


def open_tracker(db, kind: str, entity_id: str):
    rows = trackers(db, kind, entity_id, open_only=True)
    assert len(rows) == 1, f"expected one open {kind} stage, found {len(rows)}"
    return rows[0]


def event_types(db, tracking_id: str) -> list[str]:
    from app.models.sla import ConversationSLAEventLog as L

    db.expire_all()
    rows = db.query(L).filter(L.sla_tracking_id == tracking_id).order_by(L.event_at, L.id).all()
    return [r.event_type for r in rows]


def outbox(db, business_table: str, business_id: str):
    """The Respond outbox rows (`integration_log`, channel respond_io) for one form."""
    from app.models.integration import IntegrationLog

    db.expire_all()
    return (
        db.query(IntegrationLog)
        .filter(
            IntegrationLog.integration_channel == "respond_io",
            IntegrationLog.business_table == business_table,
            IntegrationLog.business_id == str(business_id),
        )
        .order_by(IntegrationLog.created_at, IntegrationLog.id)
        .all()
    )


def notifications(db, user_id: str, *, event_type: Optional[str] = None):
    from app.models.notification import Notification

    db.expire_all()
    q = db.query(Notification).filter(Notification.user_id == user_id)
    if event_type is not None:
        q = q.filter(Notification.event_type == event_type)
    return q.all()


def make_due(db, action_id: str) -> None:
    """Move a parked form action's commit_at into the past (the grace window lapsed)."""
    from app.models.sla import SlaFormAction

    row = db.query(SlaFormAction).filter(SlaFormAction.id == action_id).one()
    row.commit_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()


def form_action(db, action_id: str):
    from app.models.sla import SlaFormAction

    db.expire_all()
    return db.query(SlaFormAction).filter(SlaFormAction.id == action_id).one()


# ------------------------------------------------------------------ the world


class _Unclosable:
    """The test session handed to a worker body: its commits are this session's commits
    (so they share the request writes' savepoint semantics), and its close() is a no-op."""

    def __init__(self, db):
        self._db = db

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._db, name)


class World(SimpleNamespace):
    """db, client, the acting principal (`as_user` / `as_contact`), the recorded sends and
    jobs, and the respond_io drain."""

    def as_user(self, user_id: str):
        self.state["user"] = user_id
        return self.client

    def as_contact(self, contact_id: str):
        self.state["contact"] = contact_id
        return self.client

    def drain(self) -> int:
        """Run the queued respond_io jobs inline, on this test's connection, the way the
        worker would. Returns how many ran. A job that raises is the worker's FAILED job:
        its own `failed` outbox row is already written, so the error is kept, not raised."""
        from app import database

        ran = 0
        pending = [j for j in self.jobs if j["queue"] == "respond_io" and not j.get("ran")]
        for job in pending:
            job["ran"] = True
            original = database.SessionLocal
            database.SessionLocal = lambda: _Unclosable(self.db)  # type: ignore[assignment]
            try:
                job["fn"](*job["args"], **job["kwargs"])
            except Exception as exc:  # noqa: BLE001 - see docstring
                job["error"] = exc
            finally:
                database.SessionLocal = original
            ran += 1
        return ran

    def sends_for(self, identifier_suffix: str) -> list[dict]:
        return [s for s in self.sends if str(s["identifier"]).endswith(identifier_suffix)]


def _fake_send(sends: list):
    def send_text_or_template(db, *, identifier, text, use_case, context_vars=None, **kw):
        sends.append({"identifier": identifier, "text": text, "use_case": use_case,
                      "context_vars": dict(context_vars or {})})
        return {
            "sent_as": "text",
            "window_state": "open",
            "response": {"messageId": len(sends), "contactId": identifier},
            "request_payload": {"message": {"type": "text", "text": text}, "use_case": use_case},
        }

    return send_text_or_template


@pytest.fixture
def world(monkeypatch):
    """The chain world. `w.as_user(uid)` / `w.as_contact(cid)` pick the principal of the next
    calls on `w.client`; the staff and portal routes share the one client."""
    from fastapi.testclient import TestClient

    from app.main import app  # noqa: F401  MUST be the first app import (circular import)
    from app.api.v1.public.portal import get_portal_token
    from app.config import settings
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.models.base import set_company_scope
    from app.models.portal import PortalToken
    from app.services import queue_service, respond_messaging_service
    from app.services.company_scope_resolver import apply_company_scope

    sends: list[dict] = []
    jobs: list[dict] = []

    def fake_enqueue(fn, *args, queue_name="imports", job_timeout=3600, **kwargs):
        kwargs.pop("meta", None)
        jobs.append({"fn": fn, "name": getattr(fn, "__name__", str(fn)), "args": args,
                     "kwargs": kwargs, "queue": queue_name})
        return SimpleNamespace(id=f"zzt-job-{len(jobs)}")

    monkeypatch.setattr(queue_service, "enqueue_job", fake_enqueue)
    monkeypatch.setattr(respond_messaging_service, "send_text_or_template", _fake_send(sends))
    monkeypatch.setattr(settings, "idempotency_enabled", False, raising=False)
    monkeypatch.setattr(settings, "respond_app_base_url", "https://app.respond.io", raising=False)

    with blank_session() as db:
        state: dict[str, Any] = {"user": None, "contact": None}

        def actor():
            return {"id": state["user"], "email": f"{state['user']}@zzt.test", "role": "staff"}

        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = actor
        app.dependency_overrides[get_current_user_or_api_key] = actor
        app.dependency_overrides[apply_company_scope] = lambda: set_company_scope(
            db, frozenset({SORENTO})
        )
        app.dependency_overrides[get_portal_token] = lambda: PortalToken(
            id=uid(), contact_id=state["contact"], space_id=SPACE
        )
        try:
            client = TestClient(app, headers={"X-Portal-Token": "zzt-token"})
            yield World(db=db, client=client, state=state, sends=sends, jobs=jobs)
        finally:
            app.dependency_overrides.clear()
