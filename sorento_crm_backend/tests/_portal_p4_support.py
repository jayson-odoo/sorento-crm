"""Shared world + flows for the PORTAL-P4-REQUESTS write-path tests (slice S0-B).

Contract under test (PLAN-portal-p4-requests-28oct.md "Architecture" item 4): a salesperson with
a linked contact writes stock inquiries, complaints, purchase requests and sponsorship forms from
the CRM through `/api/v1/my-requests/...` -- the SAME paths, bodies and responses as the portal
router (`app/api/v1/public/portal.py`), authenticated by the normal CRM Bearer session, running the
portal's own service functions. So every flow here is written once, against an `Api` handle, and a
control switch re-points the handle at the portal route with a real PortalToken:

    P4_CONTROL=1 pytest tests/test_portal_p4_my_requests_*.py

proves the staff-side steps (approve / reject / process) are correct against code that exists today,
so a red run can only mean "the my-requests surface is missing or wrong". Without the switch the
`me` handle is `/api/v1/my-requests` with a Bearer session.

Postgres only (`blank_session`), every row seeded here. Nothing is sent: `enqueue_job` is replaced
by a recorder, and the assertions read DB rows (notifications, deliveries, trackers, audit logs).
"""
from __future__ import annotations

import os
import re
import uuid
from types import SimpleNamespace
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.database import get_db
from app.models.access import (
    AccessAgent,
    AgentTeam,
    RespondContact,
    Team,
    TeamMember,
)
from app.models.audit import AuditLog
from app.models.company import UserCompany
from app.models.complaints import Complaint
from app.models.impersonation import ImpersonationSession
from app.models.notification import Notification, NotificationDelivery
from app.models.portal import PortalFormRevision, PortalRevisionConfig, PortalToken
from app.models.procurement import PurchaseRequestHeader, StockInquiry
from app.models.respond_workspace import RespondWorkspace
from app.models.sla import ConversationSLATracking, FormSLAConfig, SLAPolicy, SLAPolicyTier
from app.models.user import (
    SystemSetting,
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from app.services.company_scope import DEFAULT_COMPANY_ID as SORENTO
from app.services.user_session_service import mint_session
from tests._pg_fixture import blank_session, unique_code

MY = "/api/v1/my-requests"
PORTAL = "/api/v1/public/portal"
CONTROL = os.environ.get("P4_CONTROL") == "1"
IMPERSONATE_HEADER = "X-Impersonate-User-Id"
NOT_FOUND_BODY = {"detail": "Not Found"}  # FastAPI's answer for a path that is not mounted

KINDS = ("stock_inquiry", "complaint", "purchase_request", "sponsorship_form")


def uid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# Per-form spec                                                               #
# --------------------------------------------------------------------------- #


@dataclass
class Spec:
    kind: str
    model: type
    slug_prefix: str  # procurement.stock_inquiries etc.
    submit_status: str
    final_status: str
    number_attr: Optional[str]
    revisable: bool
    restart_status: Optional[str]
    frozen: tuple  # (label field, contact-id field)
    notify_created: str
    notify_resub: str
    revise_field: str  # a non-frozen header field a revision changes
    notify_agent: str  # access agent code whose tier-1 team is notified on submit
    notify_set: str
    staff_perms: list = field(default_factory=list)

    @property
    def view_own(self) -> str:
        return f"{self.slug_prefix}.view_own"

    @property
    def view(self) -> str:
        return f"{self.slug_prefix}.view"

    @property
    def add(self) -> str:
        return f"{self.slug_prefix}.add"

    def body(self, sc: "Scene", *, contact=None, **over) -> dict:
        who = (contact or sc.contact).id
        """`{"fields": ..., "products": ...}` for a create, requestor = the caller's own contact."""
        tag = unique_code(self.kind[:3])
        if self.kind == "stock_inquiry":
            fields = {
                "salesperson_contact_id": who,
                "product_code": tag,
                "item_description": "ZZT bath mixer",
                "quantity": "4",
                "project_name": "ZZT project",
                "remark": "ZZT remark",
            }
            products = None
        elif self.kind == "complaint":
            fields = {
                "customer_name": f"ZZT customer {tag}",
                "defect_description": "ZZT leaking tap",
                "product_code": tag,
                "quantity": "2",
                "project_title": "ZZT project",
            }
            products = None
        else:
            fields = {
                "requested_by_contact_id": who,
                "customer_name": f"ZZT customer {tag}",
                "project_title": f"ZZT project {tag}",
                "purpose": "ZZT purpose",
                "delivery_address": "1 ZZT Road",
            }
            products = [{"item_code": "ITEM-A", "quantity": 2, "unit_price": 10}]
        fields.update(over)
        out: dict = {"fields": fields}
        if products is not None:
            out["products"] = products
        return out


SPECS: dict[str, Spec] = {
    "stock_inquiry": Spec(
        kind="stock_inquiry", model=StockInquiry, slug_prefix="procurement.stock_inquiries",
        submit_status="pending_project_sales", final_status="responded", number_attr="inquiry_number",
        revisable=True, restart_status="pending_project_sales",
        frozen=("salesperson", "salesperson_contact_id"),
        notify_created="portal_submitted", notify_resub="portal_resubmitted",
        revise_field="quantity", notify_agent="lead_time_enquiries", notify_set="project_sales",
    ),
    "complaint": Spec(
        kind="complaint", model=Complaint, slug_prefix="complaint_management.complaints",
        submit_status="submitted", final_status="processed_by_cs", number_attr=None,
        revisable=False, restart_status=None, frozen=(),
        notify_created="external_created", notify_resub="external_resubmitted",
        revise_field="quantity", notify_agent="complaint", notify_set="complaint",
    ),
    "purchase_request": Spec(
        kind="purchase_request", model=PurchaseRequestHeader, slug_prefix="procurement.purchase_requests",
        submit_status="submitted", final_status="processed_by_cs", number_attr="request_number",
        revisable=True, restart_status="submitted",
        frozen=("requested_by", "requested_by_contact_id"),
        notify_created="external_created", notify_resub="external_resubmitted",
        revise_field="purpose", notify_agent="purchase_request", notify_set="project_sales",
    ),
    "sponsorship_form": Spec(
        kind="sponsorship_form", model=PurchaseRequestHeader, slug_prefix="procurement.sponsorship_forms",
        submit_status="submitted", final_status="processed_by_cs", number_attr="request_number",
        revisable=True, restart_status="submitted",
        frozen=("requested_by", "requested_by_contact_id"),
        notify_created="external_created", notify_resub="external_resubmitted",
        revise_field="purpose", notify_agent="purchase_request", notify_set="project_sales",
    ),
}


# --------------------------------------------------------------------------- #
# HTTP handle                                                                 #
# --------------------------------------------------------------------------- #


class Api:
    """One caller on one base path. `me` and `portal` expose the same method set."""

    def __init__(self, client: TestClient, base: str, headers: dict):
        self.client, self.base, self.headers = client, base, headers

    def call(self, method: str, path: str, **kw):
        headers = {**self.headers, **kw.pop("headers", {})}
        return self.client.request(method, f"{self.base}{path}", headers=headers, **kw)

    def create(self, kind, body):
        return self.call("POST", f"/submissions/{kind}", json=body)

    def save(self, kind, sid, body):
        return self.call("PUT", f"/submissions/{kind}/{sid}", json=body)

    def submit(self, kind, sid, body=None):
        return self.call("POST", f"/submissions/{kind}/{sid}/submit", json=body)

    def get(self, kind, sid):
        return self.call("GET", f"/submissions/{kind}/{sid}")

    def delete(self, kind, sid):
        return self.call("DELETE", f"/submissions/{kind}/{sid}")

    def revise(self, kind, sid, *, reason="ZZT customer changed the order", expected=0, fields=None):
        return self.call(
            "POST", f"/submissions/{kind}/{sid}/revise",
            json={"reason": reason, "expected_revision_no": expected, "fields": fields or {}},
        )

    def revisions(self, kind, sid):
        return self.call("GET", f"/submissions/{kind}/{sid}/revisions")

    def comments(self, kind, sid):
        return self.call("GET", f"/submissions/{kind}/{sid}/comments")

    def comment(self, kind, sid, text="ZZT hello"):
        return self.call("POST", f"/submissions/{kind}/{sid}/comments", data={"body": text})

    def requestor_options(self, q=None):
        return self.call("GET", "/requestor-options", params={"q": q} if q else None)


# --------------------------------------------------------------------------- #
# Scene                                                                       #
# --------------------------------------------------------------------------- #


@dataclass
class Actor:
    user: User
    token: str

    @property
    def id(self) -> str:
        return self.user.id

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass
class Scene:
    db: object
    client: TestClient
    contact: RespondContact
    space_id: str
    workspace: RespondWorkspace
    sp: Actor  # the salesperson, linked to `contact`
    staff: Actor  # an admin approver
    me: Api  # the surface under test (my-requests, or the portal in control mode)
    portal: Api  # the portal, real PortalToken of `contact`
    enqueued: list
    handler: User  # member of every seeded team
    other_contact: RespondContact
    other_portal: Api  # the portal, real PortalToken of `other_contact`

    # ----- DB reads
    def row(self, spec: Spec, sid: str):
        self.db.expire_all()
        return self.db.query(spec.model).filter(spec.model.id == sid).one()

    def staff_call(self, method: str, path: str, **kw):
        return self.client.request(method, path, headers=self.staff.headers, **kw)

    def revisions(self, kind: str, sid: str) -> list:
        self.db.expire_all()
        return (
            self.db.query(PortalFormRevision)
            .filter(PortalFormRevision.source_entity_type == kind, PortalFormRevision.source_entity_id == sid)
            .order_by(PortalFormRevision.version_no)
            .all()
        )

    def notifications(self, sid: str) -> list:
        self.db.expire_all()
        return self.db.query(Notification).filter(Notification.source_entity_id == sid).all()

    def deliveries(self, sid: str) -> list:
        ids = [n.id for n in self.notifications(sid)]
        if not ids:
            return []
        return self.db.query(NotificationDelivery).filter(NotificationDelivery.notification_id.in_(ids)).all()

    def trackers(self, kind: str, sid: str) -> list:
        self.db.expire_all()
        return (
            self.db.query(ConversationSLATracking)
            .filter(ConversationSLATracking.source_entity_type == kind,
                    ConversationSLATracking.source_entity_id == sid)
            .all()
        )

    def audit(self, sid: str) -> list:
        self.db.expire_all()
        return self.db.query(AuditLog).filter(AuditLog.entity_id == sid).order_by(AuditLog.changed_at).all()


def _contact(db, name, workspace) -> RespondContact:
    row = RespondContact(
        id=uid(), phone_number=f"+6019{uuid.uuid4().int % 10**8:08d}", name=name,
        respond_io_id=unique_code("rio"), workspace_id=workspace.id,
    )
    db.add(row)
    db.flush()
    return row


def make_user(db, *, perms=(), roles=(), contact=None, name="ZZT User") -> Actor:
    """A real user with a real Bearer session. `perms` become a private role's permissions."""
    user = User(
        id=uid(), email=f"{unique_code('p4')}@example.test".lower(), name=name, status="ACTIVE",
        respond_contact_id=contact.id if contact else None, last_active_company_id=SORENTO,
    )
    db.add(user)
    db.flush()
    db.add(UserCompany(user_id=user.id, company_id=SORENTO))
    for slug in roles:
        role = db.query(UserRole).filter(UserRole.slug == slug).first()
        if role is None:
            role = UserRole(id=uid(), slug=slug, name=slug, is_protected=False, is_default=False)
            db.add(role)
            db.flush()
        db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    if perms:
        role = UserRole(id=uid(), slug=unique_code("p4role").lower(), name="ZZT p4", is_protected=False, is_default=False)
        db.add(role)
        db.flush()
        for slug in perms:
            perm = db.query(UserPermission).filter(UserPermission.slug == slug).first()
            if perm is None:
                perm = UserPermission(id=uid(), slug=slug, name=slug)
                db.add(perm)
                db.flush()
            db.add(UserRolePermission(role_id=role.id, permission_id=perm.id))
        db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    db.flush()
    token = mint_session(db, user.id).token
    db.commit()
    return Actor(user=user, token=token)


def sp_perms(*specs: Spec) -> list:
    out: list = []
    for s in specs:
        out += [s.view_own, s.add]
    return out


def _portal_token(db, contact, space_id) -> str:
    row = PortalToken(
        id=uid(), token=f"tok-{uuid.uuid4().hex}", contact_id=contact.id, space_id=space_id,
        expires_at=datetime.utcnow() + timedelta(days=30), verified_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(row)
    db.commit()
    return row.token


def _agent_team(db, agent_code, set_code, members, tier=1):
    agent = db.query(AccessAgent).filter(AccessAgent.code == agent_code).first()
    if agent is None:
        agent = AccessAgent(id=uid(), code=agent_code, name=f"ZZT {agent_code}")
        db.add(agent)
        db.flush()
    team = Team(id=uid(), name=unique_code("Team"), company_id=SORENTO)
    db.add(team)
    db.flush()
    db.add(AgentTeam(id=uid(), agent_id=agent.id, code=set_code, team_id=team.id, tier=tier, company_id=SORENTO))
    db.flush()
    for i, m in enumerate(members):
        db.add(TeamMember(id=uid(), team_id=team.id, user_id=m.id, sort_order=i, include_in_round_robin=True))
    db.flush()


@pytest.fixture
def scene(monkeypatch):
    enqueued: list = []

    def _record(func, *args, **kwargs):
        enqueued.append((getattr(func, "__name__", str(func)), args, kwargs))
        return SimpleNamespace(id=f"zzt-job-{len(enqueued)}")

    monkeypatch.setattr("app.services.queue_service.enqueue_job", _record)

    with blank_session() as db:

        def _override_db():
            yield db

        app.dependency_overrides[get_db] = _override_db
        try:
            ws = RespondWorkspace(id=uid(), space_id=f"sp_{uuid.uuid4().hex[:8]}", name="ZZT WS", api_key_ciphertext="x")
            db.add(ws)
            db.flush()
            contact = _contact(db, unique_code("ZZT Salesperson"), ws)
            other = _contact(db, unique_code("ZZT Other"), ws)
            handler = make_user(db, name="ZZT Handler").user
            sp = make_user(db, perms=sp_perms(*SPECS.values()), contact=contact, name="ZZT Salesperson")
            staff = make_user(db, roles=["admin"], name="ZZT Approver")
            # Teams that the submit notification and the form SLA resolve; one handler in each.
            for spec in {s.notify_agent: s for s in SPECS.values()}.values():
                _agent_team(db, spec.notify_agent, spec.notify_set, [handler])
            db.commit()

            with TestClient(app) as client:
                portal = Api(client, PORTAL, {"X-Portal-Token": _portal_token(db, contact, ws.space_id)})
                other_portal = Api(client, PORTAL, {"X-Portal-Token": _portal_token(db, other, ws.space_id)})
                me = portal if CONTROL else Api(client, MY, sp.headers)
                yield Scene(
                    db=db, client=client, contact=contact, space_id=ws.space_id, workspace=ws, sp=sp,
                    staff=staff, me=me, portal=portal, enqueued=enqueued, handler=handler,
                    other_contact=other, other_portal=other_portal,
                )
        finally:
            app.dependency_overrides.clear()


def my_api(sc: Scene, actor: Actor, **extra_headers) -> Api:
    return Api(sc.client, MY, {**actor.headers, **extra_headers})


# --------------------------------------------------------------------------- #
# Seeding helpers                                                             #
# --------------------------------------------------------------------------- #


def seed_sla(sc: Scene, spec: Spec) -> FormSLAConfig:
    """A form_sla_configs row with a `submit` start rule for this form, wired to a real
    agent -> tier-1 team -> handler so the tracker can resolve an assignee."""
    policy = SLAPolicy(id=uid(), code=unique_code("POL"), name="ZZT policy")
    sc.db.add(policy)
    sc.db.flush()
    sc.db.add(SLAPolicyTier(id=uid(), policy_id=policy.id, tier_level=1, tier_name="T1",
                            response_hours=4, resolution_hours=24))
    agent_code = unique_code("sla").lower()
    set_code = unique_code("set").lower()
    _agent_team(sc.db, agent_code, set_code, [sc.handler])
    cfg = FormSLAConfig(
        id=uid(), source_entity_type=spec.kind, stage_code=unique_code("stage"), policy_id=policy.id,
        agent_code=agent_code, team_set_code=set_code, start_event="submit", resolve_event="resolved",
        is_active=True,
    )
    sc.db.add(cfg)
    sc.db.commit()
    return cfg


def seed_revisions(sc: Scene, spec: Spec, *, enabled: bool, cap: int = 3, allowed=None) -> None:
    """The per-form switch (portal_revision_configs) plus the global one (system_settings)."""
    sc.db.add(SystemSetting(id=uid(), portal_revisions_enabled=True, portal_max_revisions=cap))
    sc.db.add(PortalRevisionConfig(
        id=uid(), source_entity_type=spec.kind, is_enabled=enabled, max_revisions=None,
        allowed_statuses=allowed if allowed is not None else [spec.final_status], restart_stage_code=None,
    ))
    sc.db.commit()


def not_a_missing_route(resp) -> None:
    """A refusal must come from the app, not from the route being absent."""
    assert resp.json() != NOT_FOUND_BODY, f"route not mounted: {resp.request.method} {resp.request.url}"


def ok(resp, code=None):
    expected = (code,) if code else (200, 201, 204)
    assert resp.status_code in expected, f"{resp.request.method} {resp.request.url.path} -> {resp.status_code} {resp.text}"
    return resp


def shape(value: Optional[str]) -> Optional[str]:
    """A document number with every digit blanked, to compare number RULES across two rows."""
    return re.sub(r"\d", "9", value) if value else value


# --------------------------------------------------------------------------- #
# Staff approver drivers (the real staff routes)                              #
# --------------------------------------------------------------------------- #

SI = "/api/v1/procurement/stock-inquiries"
PR = "/api/v1/procurement/purchase-requests"
CX = "/api/v1/complaints-management/complaints"


def staff_reject(sc: Scene, spec: Spec, sid: str) -> None:
    reason = "ZZT rejected: please fix the details"
    if spec.kind == "stock_inquiry":
        ok(sc.staff_call("POST", f"{SI}/{sid}/project-sales-reject", json={"reason": reason}))
    elif spec.kind == "complaint":
        ok(sc.staff_call("POST", f"{CX}/{sid}/update-and-reply", json={"technical_team_response": "ZZT answer"}))
        ok(sc.staff_call("POST", f"{CX}/{sid}/reject", json={"rejection_reason": reason}))
    else:
        ok(sc.staff_call("POST", f"{PR}/{sid}/reject-submitted", json={"rejection_reason": reason}))
    assert sc.row(spec, sid).status == "rejected"


def staff_to_final(sc: Scene, spec: Spec, sid: str) -> None:
    """From the review stage (submitted / resubmitted) to the form's final status."""
    if spec.kind == "stock_inquiry":
        ok(sc.staff_call("POST", f"{SI}/{sid}/project-sales-approve"))
        assert sc.row(spec, sid).status == "pending_purchasing"
        ok(sc.staff_call("POST", f"{SI}/{sid}/update-and-reply", json={"purchasing_response": "ZZT in stock"}))
    elif spec.kind == "complaint":
        ok(sc.staff_call("POST", f"{CX}/{sid}/update-and-reply", json={"technical_team_response": "ZZT answer"}))
        assert sc.row(spec, sid).status == "responded"
        ok(sc.staff_call("POST", f"{CX}/{sid}/approve"))
        assert sc.row(spec, sid).status == "approved"
        ok(sc.staff_call("POST", f"{CX}/{sid}/process", json={"note": "ZZT done"}))
    else:
        ok(sc.staff_call("POST", f"{PR}/{sid}/set-pending-approval"))
        ok(sc.staff_call("POST", f"{PR}/{sid}/approval-decision", json={"action": "approved", "comments": "ZZT ok"}))
        assert sc.row(spec, sid).status == "approved"
        ok(sc.staff_call("POST", f"{PR}/{sid}/process", json={"note": "ZZT done"}))
    assert sc.row(spec, sid).status == spec.final_status


# --------------------------------------------------------------------------- #
# Flows (each is one test body; the per-form files call them)                 #
# --------------------------------------------------------------------------- #


def _id(resp) -> str:
    return ok(resp).json()["id"]


def flow_parity(sc: Scene, spec: Spec) -> None:
    """P4-10: the same payload through my-requests and through the portal gives the same row."""
    body = spec.body(sc)
    mine_id = _id(sc.me.create(spec.kind, body))
    portal_id = _id(sc.portal.create(spec.kind, body))
    assert mine_id != portal_id
    a, b = sc.row(spec, mine_id), sc.row(spec, portal_id)
    for col in ("status", "contact_id", "space_id", "source"):
        assert getattr(a, col, None) == getattr(b, col, None), col
    assert a.status == "draft"
    assert a.portal_draft_at is not None
    assert a.contact_id == sc.contact.id
    assert a.space_id == sc.space_id
    if spec.kind != "complaint":
        assert getattr(a, "source", None) == "portal"
    # The submit runs the same rules: status, number shape, history row.
    ok(sc.me.submit(spec.kind, mine_id))
    ok(sc.portal.submit(spec.kind, portal_id))
    a, b = sc.row(spec, mine_id), sc.row(spec, portal_id)
    assert a.status == b.status == spec.submit_status
    assert a.portal_draft_at is None and b.portal_draft_at is None
    if spec.number_attr:
        mine_no, portal_no = getattr(a, spec.number_attr), getattr(b, spec.number_attr)
        assert mine_no and portal_no
        assert shape(mine_no) == shape(portal_no)
    assert [r.kind for r in sc.revisions(spec.kind, mine_id)] == [r.kind for r in sc.revisions(spec.kind, portal_id)]


def flow_happy(sc: Scene, spec: Spec) -> None:
    """P4-11, P4-12: create -> save -> submit, then a staff approver to the final state."""
    cfg = seed_sla(sc, spec)
    sid = _id(sc.me.create(spec.kind, spec.body(sc)))
    saved = ok(sc.me.save(spec.kind, sid, spec.body(sc, **{"project_title" if spec.kind != "stock_inquiry" else "remark": "ZZT edited"}))).json()
    assert saved["id"] == sid
    assert sc.row(spec, sid).status == "draft"

    ok(sc.me.submit(spec.kind, sid))
    row = sc.row(spec, sid)
    assert row.status == spec.submit_status
    assert row.portal_draft_at is None
    if spec.number_attr:
        assert getattr(row, spec.number_attr)
    revs = sc.revisions(spec.kind, sid)
    if spec.kind == "complaint":
        assert revs == []  # no revision adapter (portal_service.py:1305)
    else:
        assert [r.kind for r in revs] == ["original"]
    trackers = sc.trackers(spec.kind, sid)
    assert len(trackers) == 1 and str(trackers[0].policy_id) == str(cfg.policy_id)
    notifs = sc.notifications(sid)
    assert any((n.event_type or "").startswith(spec.notify_created) for n in notifs), [n.event_type for n in notifs]
    assert sc.deliveries(sid), "notification_deliveries rows expected"

    staff_to_final(sc, spec, sid)


def flow_reject_resubmit(sc: Scene, spec: Spec) -> None:
    """P4-13: staff rejects; the salesperson edits and resubmits from the CRM -> `resubmitted`."""
    sid = _id(sc.me.create(spec.kind, spec.body(sc)))
    ok(sc.me.submit(spec.kind, sid))
    staff_reject(sc, spec, sid)
    before = len(sc.audit(sid))

    # A rejected row cannot be parked back in a draft save: the portal refuses a PUT, exactly so here.
    refused = sc.me.save(spec.kind, sid, spec.body(sc))
    assert refused.status_code >= 400 and "draft saves are disabled" in refused.text, refused.text
    not_a_missing_route(refused)

    # The edit travels WITH the submit, as the portal's own form sends it.
    edited = spec.body(sc, **{"project_title" if spec.kind != "stock_inquiry" else "remark": "ZZT fixed"})
    ok(sc.me.submit(spec.kind, sid, edited))
    row = sc.row(spec, sid)
    assert row.status == "resubmitted"
    assert (getattr(row, "project_title", None) or getattr(row, "remark", None)) == "ZZT fixed" or spec.kind == "complaint"

    audit = sc.audit(sid)
    assert len(audit) > before, "the resubmit wrote no audit_logs rows"
    assert any(a.user_id == sc.sp.id for a in audit[before:]), "audit actor is not the salesperson"

    revs = sc.revisions(spec.kind, sid)
    if spec.kind == "complaint":
        assert revs == []
    else:
        assert [r.kind for r in revs] == ["original", "resubmission"]
    events = [(n.event_type or "") for n in sc.notifications(sid)]
    assert any(e.startswith(spec.notify_resub) for e in events), events

    staff_to_final(sc, spec, sid)


def flow_revision_enabled(sc: Scene, spec: Spec) -> None:
    """P4-14: with the type enabled a responded/processed row can be revised from the CRM."""
    assert spec.revisable
    seed_revisions(sc, spec, enabled=True)
    sid = _id(sc.me.create(spec.kind, spec.body(sc)))
    ok(sc.me.submit(spec.kind, sid))
    staff_to_final(sc, spec, sid)
    before = sc.row(spec, sid)
    frozen_before = {f: getattr(before, f) for f in spec.frozen}
    assert getattr(before, "revision_no", 0) == 0

    other = sc.other_contact.id
    fields = {spec.revise_field: "9" if spec.revise_field == "quantity" else "ZZT revised purpose"}
    for f in spec.frozen:
        fields[f] = other if f.endswith("contact_id") else "ZZT someone else"
    resp = ok(sc.me.revise(spec.kind, sid, fields=fields, expected=0), 200)
    body = resp.json()
    assert body["revision_no"] == 1
    assert body["submission"]["status"] == spec.restart_status

    after = sc.row(spec, sid)
    assert after.revision_no == 1
    assert after.status == spec.restart_status
    for f, v in frozen_before.items():
        assert getattr(after, f) == v, f"{f} changed on revise"
    assert str(getattr(after, spec.revise_field)) in ("9", "ZZT revised purpose")
    kinds = [r.kind for r in sc.revisions(spec.kind, sid)]
    assert kinds == ["original", "revision"], kinds


def flow_revision_refused(sc: Scene, spec: Spec) -> None:
    """P4-14: type disabled (or complaint, which has no adapter) -> refused exactly as the portal refuses."""
    if spec.revisable:
        seed_revisions(sc, spec, enabled=False)
    pid = _id(sc.portal.create(spec.kind, spec.body(sc)))
    ok(sc.portal.submit(spec.kind, pid))
    staff_to_final(sc, spec, pid)
    sid = _id(sc.me.create(spec.kind, spec.body(sc)))
    ok(sc.me.submit(spec.kind, sid))
    staff_to_final(sc, spec, sid)

    mine = sc.me.revise(spec.kind, sid, fields={})
    theirs = sc.portal.revise(spec.kind, pid, fields={})
    assert theirs.status_code != 200, theirs.text
    not_a_missing_route(mine)
    assert mine.status_code == theirs.status_code, (mine.status_code, mine.text, theirs.text)
    assert mine.json() == theirs.json()
    assert sc.row(spec, sid).status == spec.final_status
    assert (getattr(sc.row(spec, sid), "revision_no", 0) or 0) == 0
    assert sc.revisions(spec.kind, sid)[-1:] == [] or sc.revisions(spec.kind, sid)[-1].kind == "original"


def flow_delete_and_edit_rules(sc: Scene, spec: Spec) -> None:
    """P4-11: a draft deletes (204); a submitted row can be neither deleted nor edited."""
    draft = _id(sc.me.create(spec.kind, spec.body(sc)))
    resp = sc.me.delete(spec.kind, draft)
    assert resp.status_code == 204, resp.text
    sc.db.expire_all()
    assert sc.db.query(spec.model).filter(spec.model.id == draft).first() is None

    sid = _id(sc.me.create(spec.kind, spec.body(sc)))
    pid = _id(sc.portal.create(spec.kind, spec.body(sc)))
    ok(sc.me.submit(spec.kind, sid))
    ok(sc.portal.submit(spec.kind, pid))
    for mine, theirs in (
        (sc.me.delete(spec.kind, sid), sc.portal.delete(spec.kind, pid)),
        (sc.me.save(spec.kind, sid, spec.body(sc)), sc.portal.save(spec.kind, pid, spec.body(sc))),
        (sc.me.submit(spec.kind, sid), sc.portal.submit(spec.kind, pid)),
    ):
        assert theirs.status_code >= 400
        not_a_missing_route(mine)
        assert mine.status_code == theirs.status_code, (mine.request.method, mine.text, theirs.text)
        assert mine.json() == theirs.json()
    assert sc.row(spec, sid).status == spec.submit_status


def flow_ownership(sc: Scene, spec: Spec) -> None:
    """P4-11 / security: another contact's row answers exactly what the portal answers for it."""
    foreign = _id(sc.other_portal.create(spec.kind, spec.body(sc, contact=sc.other_contact)))
    assert sc.row(spec, foreign).contact_id == sc.other_contact.id
    # the salesperson's own row, so the route is known to be mounted
    ok(sc.me.get(spec.kind, _id(sc.me.create(spec.kind, spec.body(sc)))))

    pairs = {
        "get": (sc.me.get(spec.kind, foreign), sc.portal.get(spec.kind, foreign)),
        "put": (sc.me.save(spec.kind, foreign, spec.body(sc)), sc.portal.save(spec.kind, foreign, spec.body(sc))),
        "delete": (sc.me.delete(spec.kind, foreign), sc.portal.delete(spec.kind, foreign)),
        "submit": (sc.me.submit(spec.kind, foreign), sc.portal.submit(spec.kind, foreign)),
        "revise": (sc.me.revise(spec.kind, foreign), sc.portal.revise(spec.kind, foreign)),
        "revisions": (sc.me.revisions(spec.kind, foreign), sc.portal.revisions(spec.kind, foreign)),
        "comments": (sc.me.comments(spec.kind, foreign), sc.portal.comments(spec.kind, foreign)),
        "comment_post": (sc.me.comment(spec.kind, foreign), sc.portal.comment(spec.kind, foreign)),
    }
    for name, (mine, theirs) in pairs.items():
        assert theirs.status_code >= 400, (name, theirs.status_code)
        not_a_missing_route(mine)
        assert mine.status_code == theirs.status_code, (name, mine.status_code, mine.text, theirs.status_code, theirs.text)
        assert mine.json() == theirs.json(), name
    assert sc.row(spec, foreign).status == "draft"
    assert sc.db.query(spec.model).filter(spec.model.id == foreign).count() == 1


def flow_comments(sc: Scene, spec: Spec) -> None:
    """Comments on an own, submitted row work through my-requests."""
    sid = _id(sc.me.create(spec.kind, spec.body(sc)))
    ok(sc.me.submit(spec.kind, sid))
    posted = ok(sc.me.comment(spec.kind, sid, "ZZT question about my order"), 201).json()
    assert posted["comment"]["body"] == "ZZT question about my order"
    items = ok(sc.me.comments(spec.kind, sid)).json()["items"]
    assert [i["body"] for i in items] == ["ZZT question about my order"]
    assert items == ok(sc.portal.comments(spec.kind, sid)).json()["items"]


def flow_requestor_options(sc: Scene, spec: Spec) -> None:
    """P4-15: the requestor picker equals the portal's for the same contact."""
    mine, theirs = ok(sc.me.requestor_options()), ok(sc.portal.requestor_options())
    assert mine.json() == theirs.json()
    assert sc.contact.id in [i["id"] for i in mine.json()["items"]]
    assert ok(sc.me.requestor_options("ZZT")).json() == ok(sc.portal.requestor_options("ZZT")).json()


def flow_impersonation(sc: Scene, spec: Spec) -> None:
    """P4-17: admin viewing as the salesperson creates AS that salesperson; the audit names the admin."""
    admin = make_user(sc.db, roles=["admin"], name="ZZT Impersonating Admin")
    sc.db.add(ImpersonationSession(id=uid(), admin_user_id=admin.id, target_user_id=sc.sp.id))
    sc.db.commit()
    api = my_api(sc, admin, **{IMPERSONATE_HEADER: sc.sp.id})
    sid = _id(api.create(spec.kind, spec.body(sc)))
    row = sc.row(spec, sid)
    assert row.contact_id == sc.contact.id
    assert row.space_id == sc.space_id
    rows = sc.audit(sid)
    assert rows, "no audit_logs rows for the create"
    assert all(a.user_id == sc.sp.id for a in rows if a.user_id), [a.user_id for a in rows]
    assert any(a.real_user_id == admin.id for a in rows), [a.real_user_id for a in rows]
    assert any(a.auth_method == "impersonation" for a in rows)
    # and the whole write path works as that salesperson
    ok(api.submit(spec.kind, sid))
    assert sc.row(spec, sid).status == spec.submit_status
