"""PROJECT-REG-PORTAL: what an unapproved project (draft / pending / rejected) is kept out of
(RW4, RW8, RW10), red-first.

REWORK R3 / R4: a registration is a `projects.projects` row, so every INTERNAL path that reads
or writes projects must treat it as "not a project yet" until Approve:

- the registration lock and the clash check ignore it (RW4);
- every write on it is 409 `project_not_approved`, status moves included (RW8);
- the pickers, their server validators, the entity resolver, the reports, the embeddings, the
  possible-duplicate candidates and the staleness sweep skip it (RW8);
- no message names "None" for its missing code (RW10).

Each write surface is its own parametrised case, paired with the same call on an approved
project that must NOT answer `project_not_approved` (so a pass is the guard, not a bad request).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._pg_fixture import blank_session
from ._project_registration_support import (
    PORTAL,
    STAFF,
    approve,
    as_contact,
    as_user,
    developer,
    funnel,
    pending,
    project,
    second_company,
    sorento,
    uid,
    world,  # noqa: F401  (fixture)
)

ROOT = "/api/v1/project-sales"
UNAPPROVED = ("draft", "pending", "rejected")


# ------------------------------------------------------------------ RW4 the registration lock


def test_rw4_two_unapproved_projects_with_the_same_title_and_no_developer_both_exist(world):
    for state in UNAPPROVED:
        project(world.db, world.company_id, f"Twin Tower {state}", approval_state=state)
        project(world.db, world.company_id, f"Twin Tower {state}", approval_state=state)
    world.db.flush()  # no unique violation


def test_rw4_two_unapproved_projects_with_the_same_developer_and_title_both_exist(world):
    dev = developer(world.db, world.company_id, "Setia Example Group")
    project(world.db, world.company_id, "Tower Epsilon", developer_party=dev, approval_state="pending")
    project(world.db, world.company_id, "Tower Epsilon", developer_party=dev, approval_state="pending")
    project(world.db, world.company_id, "Tower Epsilon", developer_party=dev, approval_state="rejected")
    project(world.db, world.company_id, "Tower Epsilon", developer_party=dev, approval_state="draft")
    world.db.flush()


def test_rw4_an_unapproved_project_never_blocks_a_staff_project_with_the_same_developer_and_title(world):
    dev = developer(world.db, world.company_id, "Setia Example Group")
    project(world.db, world.company_id, "Tower Zeta", developer_party=dev, approval_state="pending")
    project(world.db, world.company_id, "Tower Zeta", developer_party=dev)  # staff: approval_state NULL
    world.db.flush()  # no unique violation: the pending row is outside the lock
    project(world.db, world.company_id, "Tower Eta", developer_party=dev, approval_state="approved", code="PPF2601098")
    project(world.db, world.company_id, "Tower Eta", developer_party=dev, approval_state="rejected")
    world.db.flush()


def test_rw4_the_identity_index_is_partial_over_staff_and_approved_rows(world):
    from app.models.projects import Project

    index = next(i for i in Project.__table__.indexes if i.name == "uq_projects_company_developer_title")
    assert index.unique
    where = str(index.dialect_options["postgresql"]["where"])
    assert "approval_state IS NULL" in where
    assert "approval_state = 'approved'" in where


def test_rw4_a_pending_project_never_blocks_a_staff_registration_of_the_same_title_and_developer(world):
    dev = developer(world.db, world.company_id, "Setia Example Group")
    project(world.db, world.company_id, "Setia Alam Phase 3B", developer_party=dev, approval_state="pending")
    project(world.db, world.company_id, "Setia Alam Phase 3C", developer_party=dev, approval_state="rejected")
    c = as_user(world, world.staff)
    same = c.post(f"{STAFF}/", json={"title": "Setia Alam Phase 3B", "developer_party_id": dev.id})
    assert same.status_code == 201, same.text
    near = c.post(f"{STAFF}/", json={"title": "setia alam ph 3c", "developer_party_id": dev.id})
    assert near.status_code == 201, near.text


def test_rw4_the_clash_check_and_the_clash_preview_skip_unapproved_projects(world):
    from app.services.project_clash_service import find_clashes

    dev = developer(world.db, world.company_id, "Setia Example Group")
    pend = project(world.db, world.company_id, "Setia Alam Phase 3B", developer_party=dev, approval_state="pending")
    rej = project(world.db, world.company_id, "Setia Alam Phase 3B", developer_party=dev, approval_state="rejected")
    staff_project = project(world.db, world.company_id, "Setia Alam Phase 3B Block A", developer_party=dev, code="PRJ-ZZT-C1")

    found = {
        c.project_id
        for c in find_clashes(world.db, company_id=world.company_id, developer_party_id=dev.id, title="Setia Alam Phase 3B")
    }
    assert staff_project.id in found
    assert pend.id not in found and rej.id not in found

    res = as_user(world, world.staff).post(
        f"{STAFF}/clash-preview", json={"title": "Setia Alam Phase 3B", "developer_party_id": dev.id}
    )
    assert res.status_code == 200, res.text
    ids = {c["project_id"] for c in res.json()["candidates"]}
    assert staff_project.id in ids
    assert pend.id not in ids and rej.id not in ids


# ------------------------------------------------------------------ the helpers (R2, R4)


def test_approved_projects_keeps_staff_and_approved_rows_only(world):
    from app.models.projects import Project
    from app.services.project_service import approved_projects

    staff_project = project(world.db, world.company_id, "Helper Staff", code="PRJ-ZZT-H1")
    ok = project(world.db, world.company_id, "Helper Approved", approval_state="approved", code="PPF2601011")
    others = [project(world.db, world.company_id, f"Helper {s}", approval_state=s) for s in UNAPPROVED]
    ids = {r.id for r in approved_projects(world.db.query(Project).filter(Project.company_id == world.company_id)).all()}
    assert {staff_project.id, ok.id} <= ids
    assert not ids & {o.id for o in others}


def test_project_label_is_the_code_or_awaiting_approval_never_none(world):
    from app.services.project_service import project_label

    assert project_label(SimpleNamespace(project_code="PPF2601001")) == "PPF2601001"
    assert project_label(SimpleNamespace(project_code=None)) == "Awaiting approval"
    assert project_label(SimpleNamespace(project_code="")) == "Awaiting approval"
    assert "None" not in project_label(SimpleNamespace(project_code=None))


# ------------------------------------------------------------------ RW8 writes: one case per surface


def _seed_children(w, p) -> SimpleNamespace:
    """A PO, a sales order and a task hung straight on the project (the rows an approved
    project would have), so the routes that address them by their own id can be exercised."""
    from app.models.project_so import ProjectSalesOrder
    from app.models.projects import ProjectPurchaseOrder, ProjectTask

    po = ProjectPurchaseOrder(id=uid(), company_id=w.company_id, project_id=p.id, po_number=f"PO-ZZT-{uid()[:6]}")
    so = ProjectSalesOrder(id=uid(), company_id=w.company_id, project_id=p.id, provisional_ref=f"SO-ZZT-{uid()[:6]}")
    task = ProjectTask(id=uid(), company_id=w.company_id, project_id=p.id, name="Existing task")
    w.db.add_all([po, so, task])
    w.db.flush()
    return SimpleNamespace(pid=p.id, po=po.id, so=so.id, task=task.id, stages=funnel(w.db))


PDF = ("po.pdf", b"%PDF-1.4 zzt", "application/pdf")

#: name -> callable(client, ctx) -> response. Each is a WRITE the plan names (R4).
SURFACES = {
    "quotation_create": lambda c, x: c.post(f"{STAFF}/{x.pid}/quotations", json={"scope_label": "House Units"}),
    "sample_create": lambda c, x: c.post(f"{STAFF}/{x.pid}/samples", json={"quotation_version_id": uid()}),
    "customer_po_create": lambda c, x: c.post(f"{STAFF}/{x.pid}/purchase-orders", json={"po_number": "PO-ZZT-NEW", "po_source": "contractor_direct"}),
    "customer_po_update": lambda c, x: c.put(f"{ROOT}/purchase-orders/{x.po}", json={"notes": "edited"}),
    "po_intake_upload": lambda c, x: c.post(f"{STAFF}/{x.pid}/purchase-orders/upload", files={"file": PDF}),
    "task_create": lambda c, x: c.post(f"{STAFF}/{x.pid}/tasks", json={"name": "Call the QS"}),
    "task_update": lambda c, x: c.put(f"{STAFF}/{x.pid}/tasks/{x.task}", json={"name": "Renamed"}),
    "task_delete": lambda c, x: c.delete(f"{STAFF}/{x.pid}/tasks/{x.task}"),
    "schedule_upload": lambda c, x: c.post(
        f"{ROOT}/purchase-orders/{x.po}/delivery-schedules/upload", files={"file": PDF}
    ),
    "sales_order_build": lambda c, x: c.post(
        f"{ROOT}/purchase-orders/{x.po}/build-sales-orders", json={"schedule_version_id": uid()}
    ),
    "sales_order_delete": lambda c, x: c.delete(f"{ROOT}/sales-orders/{x.so}"),
    "stakeholder_add": lambda c, x: c.post(f"{STAFF}/{x.pid}/stakeholders", json={"person_name": "Lim QS"}),
    "status_move": lambda c, x: c.post(f"{STAFF}/{x.pid}/status", json={"to_status_id": x.stages["registered"].id}),
}


@pytest.fixture
def stubbed_storage(monkeypatch):
    """The approved-project control reaches the storage layer on the two uploads; stub it so
    the control stays offline and answers a code that is not the guard's."""
    from app.api.v1.projects import po_intake, schedules
    from app.services.error_handler import AppException

    def teapot(*args, **kwargs):
        raise AppException(status_code=418, message="stubbed storage", code="zzt_stubbed")

    monkeypatch.setattr(po_intake.ProjectPOExtractionService, "create_version_from_upload", teapot)
    monkeypatch.setattr(schedules, "_service", lambda db: SimpleNamespace(create_version=teapot))


@pytest.mark.parametrize("surface", sorted(SURFACES))
@pytest.mark.parametrize("state", UNAPPROVED)
def test_rw8_a_write_on_an_unapproved_project_is_409_project_not_approved(world, stubbed_storage, surface, state):
    p = project(world.db, world.company_id, f"Guarded {state} {surface}", approval_state=state, owner=world.root)
    ctx = _seed_children(world, p)
    res = SURFACES[surface](as_user(world, world.root), ctx)
    assert res.status_code == 409, (surface, state, res.status_code, res.text)
    assert res.json()["code"] == "project_not_approved"
    assert "None" not in res.json()["message"]


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_rw8_the_same_write_on_an_approved_project_is_not_refused_for_approval(world, stubbed_storage, surface):
    p = project(world.db, world.company_id, f"Control {surface}", approval_state="approved", code=f"PPF26010{uid()[:2]}", owner=world.root)
    ctx = _seed_children(world, p)
    res = SURFACES[surface](as_user(world, world.root), ctx)
    body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
    assert body.get("code") != "project_not_approved", (surface, res.status_code, res.text)


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_rw8_the_same_write_on_a_staff_project_is_not_refused_for_approval(world, stubbed_storage, surface):
    p = project(world.db, world.company_id, f"Staff control {surface}", code=f"PRJ-ZZT-{uid()[:6]}", owner=world.root)
    ctx = _seed_children(world, p)
    res = SURFACES[surface](as_user(world, world.root), ctx)
    body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
    assert body.get("code") != "project_not_approved", (surface, res.status_code, res.text)


def test_rw8_the_guard_names_the_reason_for_each_state(world):
    p = project(world.db, world.company_id, "Reason tower", approval_state="pending", owner=world.root)
    res = as_user(world, world.root).post(f"{STAFF}/{p.id}/tasks", json={"name": "x"})
    assert res.status_code == 409
    assert "approv" in res.json()["message"].lower()


def test_rw8_reads_of_an_unapproved_project_still_work(world):
    p = project(world.db, world.company_id, "Readable tower", approval_state="pending", owner=world.root)
    c = as_user(world, world.root)
    for suffix in ("", "/quotations", "/tasks", "/stakeholders", "/samples"):
        res = c.get(f"{STAFF}/{p.id}{suffix}")
        assert res.status_code == 200, (suffix, res.status_code, res.text)


def test_rw8_a_status_move_on_a_pending_project_leaves_it_without_a_stage(world):
    stages = funnel(world.db)
    rid = pending(world)
    res = as_user(world, world.root).post(f"{STAFF}/{rid}/status", json={"to_status_id": stages["registered"].id})
    assert res.status_code == 409
    assert res.json()["code"] == "project_not_approved"
    world.db.expire_all()
    from app.models.projects import Project

    assert world.db.get(Project, rid).status_id is None


def test_rw8_once_approved_it_moves_through_the_funnel_like_any_project(world):
    stages = funnel(world.db)
    rid = pending(world)
    assert approve(world, rid).status_code == 200
    res = as_user(world, world.root).post(f"{STAFF}/{rid}/status", json={"to_status_id": stages["specified"].id})
    assert res.status_code != 409 or res.json()["code"] != "project_not_approved", res.text


def test_rw8_a_lead_cannot_be_linked_to_an_unapproved_project(world):
    from app.models.projects import ProjectLead
    from app.services.error_handler import AppException
    from app.services.project_lead_service import set_project_lead

    pend = project(world.db, world.company_id, "Lead target", approval_state="pending", owner=world.root)
    lead = ProjectLead(
        id=uid(), company_id=world.company_id, lead_code=f"LD-ZZT-{uid()[:6]}", title="A sighting",
        normalised_title="a sighting", outcome="open", owner_user_id=world.root,
    )
    world.db.add(lead)
    world.db.flush()
    with pytest.raises(AppException) as exc:
        set_project_lead(world.db, pend, lead.id, actor_user_id=world.root, permissions={"projects.projects.manage"})
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "project_not_approved"
    world.db.refresh(lead)
    assert lead.outcome == "open"


def test_rw8_the_project_form_cannot_link_a_lead_to_an_unapproved_project_over_http(world):
    from app.models.projects import ProjectLead

    pend = project(world.db, world.company_id, "Lead target http", approval_state="pending", owner=world.root)
    lead = ProjectLead(
        id=uid(), company_id=world.company_id, lead_code=f"LD-ZZT-{uid()[:6]}", title="Another sighting",
        normalised_title="another sighting", outcome="open", owner_user_id=world.root,
    )
    world.db.add(lead)
    world.db.flush()
    res = as_user(world, world.root).put(f"{STAFF}/{pend.id}", json={"lead_id": lead.id})
    assert res.status_code == 409, res.text
    assert res.json()["code"] == "project_not_approved"


def test_rw8_qualifying_a_lead_is_not_blocked_by_an_unapproved_project_of_the_same_title(world):
    """Qualify runs the staff registration lock: a pending portal project must not be the
    incumbent it is refused for (RW4 on the qualify path)."""
    from app.models.projects import ProjectLead
    from app.services.project_lead_service import qualify_lead

    dev = developer(world.db, world.company_id, "Setia Example Group")
    project(world.db, world.company_id, "Setia Alam Phase 3B", developer_party=dev, approval_state="pending")
    lead = ProjectLead(
        id=uid(), company_id=world.company_id, lead_code=f"LD-ZZT-{uid()[:6]}", title="Setia Alam Phase 3B",
        normalised_title="setia alam phase 3b", outcome="open", owner_user_id=world.root,
        developer_party_id=dev.id,
    )
    world.db.add(lead)
    world.db.flush()
    made = qualify_lead(world.db, lead=lead, actor_user_id=world.root, company_id=world.company_id)
    assert made.project_code
    assert made.approval_state in (None, "approved")


# ------------------------------------------------------------------ RW8 pickers and validators


def test_rw8_the_portal_project_picker_offers_approved_and_staff_projects_only(world):
    ok = project(world.db, world.company_id, "Picker approved", approval_state="approved", code="PPF2601021")
    staff_project = project(world.db, world.company_id, "Picker staff", code="PRJ-ZZT-K1")
    hidden = [project(world.db, world.company_id, f"Picker {s}", approval_state=s) for s in UNAPPROVED]
    res = as_contact(world, world.a).get(f"{PORTAL}/lookups/projects", params={"q": "Picker", "limit": 50})
    assert res.status_code == 200, res.text
    ids = {row["id"] for row in res.json()}
    assert {ok.id, staff_project.id} <= ids
    assert not ids & {h.id for h in hidden}


def test_rw8_projects_for_contact_skips_unapproved_projects(world):
    from app.models.access import RespondContact
    from app.services import sponsorship_link_service as links

    ok = project(world.db, world.company_id, "Linked approved", approval_state="approved", code="PPF2601022")
    hidden = [project(world.db, world.company_id, f"Linked {s}", approval_state=s) for s in UNAPPROVED]
    contact = world.db.get(RespondContact, world.a)
    ids = {r["id"] for r in links.projects_for_contact(world.db, contact=contact, limit=100)}
    assert ok.id in ids
    assert not ids & {h.id for h in hidden}
    assert all(r["project_code"] for r in links.projects_for_contact(world.db, contact=contact, limit=100))


def test_rw8_the_sponsorship_validator_refuses_an_unapproved_project(world):
    from app.models.access import RespondContact
    from app.services.error_handler import AppException
    from app.services.sponsorship_link_service import assert_project_requirement

    contact = world.db.get(RespondContact, world.a)
    ok = project(world.db, world.company_id, "Sponsor approved", approval_state="approved", code="PPF2601023")
    assert_project_requirement(world.db, contact=contact, project_id=ok.id)
    for state in UNAPPROVED:
        hidden = project(world.db, world.company_id, f"Sponsor {state}", approval_state=state)
        with pytest.raises(AppException) as exc:
            assert_project_requirement(world.db, contact=contact, project_id=hidden.id)
        assert exc.value.detail["code"] == "sponsorship_project_not_permitted", state


def test_rw8_the_portal_sample_request_validator_refuses_an_unapproved_project(world):
    from app.models.access import RespondContact
    from app.services.error_handler import AppException
    from app.services.sample_request_service import assert_portal_project_allowed

    contact = world.db.get(RespondContact, world.a)
    ok = project(world.db, world.company_id, "Sample approved", approval_state="approved", code="PPF2601024")
    assert_portal_project_allowed(world.db, contact=contact, project_id=ok.id)
    for state in UNAPPROVED:
        hidden = project(world.db, world.company_id, f"Sample {state}", approval_state=state)
        with pytest.raises(AppException) as exc:
            assert_portal_project_allowed(world.db, contact=contact, project_id=hidden.id)
        assert exc.value.detail["code"] == "SAMPLE_REQUEST_PROJECT_NOT_ALLOWED", state


def test_rw8_the_staff_sample_request_validator_refuses_an_unapproved_project(world):
    from app.services.error_handler import AppException
    from app.services.sample_request_service import _check_refs

    ok = project(world.db, world.company_id, "Staff sample approved", approval_state="approved", code="PPF2601025")
    _check_refs(world.db, {"project_id": ok.id})
    for state in UNAPPROVED:
        hidden = project(world.db, world.company_id, f"Staff sample {state}", approval_state=state)
        with pytest.raises(AppException) as exc:
            _check_refs(world.db, {"project_id": hidden.id})
        assert exc.value.detail["code"] == "SAMPLE_REQUEST_PROJECT_INVALID", state


# ------------------------------------------------------------------ RW8 entity resolver, reports


def test_rw8_the_entity_resolver_does_not_resolve_an_unapproved_project(world):
    from app.services.entity_resolver import _probe_project

    ok = project(world.db, world.company_id, "Resolver approved tower", approval_state="approved", code="PPF2601031")
    project(world.db, world.company_id, "Resolver pending tower", approval_state="pending")
    project(world.db, world.company_id, "Resolver rejected tower", approval_state="rejected")
    project(world.db, world.company_id, "Resolver draft tower", approval_state="draft")
    tokens = [
        "Resolver approved tower",
        "Resolver pending tower",
        "Resolver rejected tower",
        "Resolver draft tower",
    ]
    out = _probe_project(world.db, tokens)
    assert len(out["Resolver approved tower"]) == 1
    for token in tokens[1:]:
        assert out[token] == [], token
    assert [e.canonical_code for e in out["Resolver approved tower"]] == ["PPF2601031"]


def _estimate(db, row, value):
    from decimal import Decimal

    from app.models.projects import ProjectSalesProfile

    profile = db.get(ProjectSalesProfile, row.id)
    if profile is None:
        profile = ProjectSalesProfile(project_id=row.id)
        db.add(profile)
    profile.estimated_sales_value = Decimal(value)
    db.flush()


def test_rw8_the_forecast_skips_unapproved_projects(world):
    from decimal import Decimal

    from app.services import project_forecast_service as fc

    base = fc.forecast(world.db, company_id=world.company_id)
    for state in UNAPPROVED:
        _estimate(world.db, project(world.db, world.company_id, f"Forecast {state}", approval_state=state, owner=world.root), "1000000.00")
    after = fc.forecast(world.db, company_id=world.company_id)
    assert after["pipeline"] == base["pipeline"]
    assert after["project_count"] == base["project_count"]

    _estimate(world.db, project(world.db, world.company_id, "Forecast staff", code="PRJ-ZZT-FC1", owner=world.root), "500000.00")
    counted = fc.forecast(world.db, company_id=world.company_id)
    assert Decimal(str(counted["pipeline"])) == Decimal(str(base["pipeline"])) + Decimal("500000.00")
    assert counted["project_count"] == base["project_count"] + 1


def test_rw8_conversion_and_by_salesperson_skip_unapproved_projects(world):
    from app.services import project_forecast_service as fc

    base_conv = fc.conversion(world.db, company_id=world.company_id)
    base_people = fc.by_salesperson(world.db, company_id=world.company_id)
    for state in UNAPPROVED:
        project(world.db, world.company_id, f"Report {state}", approval_state=state, owner=world.root)
    assert fc.conversion(world.db, company_id=world.company_id) == base_conv
    assert fc.by_salesperson(world.db, company_id=world.company_id) == base_people

    project(world.db, world.company_id, "Report staff", code="PRJ-ZZT-RP1", owner=world.root)
    assert fc.conversion(world.db, company_id=world.company_id)["open"] == base_conv["open"] + 1
    mine = next(r for r in fc.by_salesperson(world.db, company_id=world.company_id) if r["owner_user_id"] == world.root)
    assert mine["project_count"] == 1


def test_rw8_the_forecast_route_skips_them_too(world):
    base = as_user(world, world.root).get(f"{ROOT}/reports/forecast").json()
    _estimate(world.db, project(world.db, world.company_id, "Route pending", approval_state="pending"), "750000.00")
    after = as_user(world, world.root).get(f"{ROOT}/reports/forecast").json()
    assert after["pipeline"] == base["pipeline"]


# ------------------------------------------------------------------ RW8 possible duplicates, embeddings, staleness


def test_rw8_find_possible_duplicates_skips_unapproved_candidates(world):
    from app.services.project_registration_service import find_possible_duplicates

    ok = project(world.db, world.company_id, "Menara Zeta Office Tower", approval_state="approved", code="PPF2601041")
    staff_project = project(world.db, world.company_id, "Menara Eta Office Tower", code="PRJ-ZZT-DU1")
    hidden = [project(world.db, world.company_id, f"Menara {s} Tower", approval_state=s) for s in UNAPPROVED]
    world.semantic[:] = [(h.id, 0.99) for h in hidden] + [(ok.id, 0.90), (staff_project.id, 0.85)]
    rows = find_possible_duplicates(world.db, company_id=world.company_id, title="Blok Pejabat Baru")
    assert [r["project_id"] for r in rows] == [ok.id, staff_project.id]


def _queued(session, source_id):
    from app.models.embeddings import EmbeddingQueue

    session.flush()
    return (
        session.query(EmbeddingQueue)
        .filter(EmbeddingQueue.source_type == "project", EmbeddingQueue.source_id == source_id)
        .count()
    )


def test_rw8_an_unapproved_project_queues_no_embedding_until_it_is_approved():
    from app.services.embedding_change_listener import register_embedding_change_listeners

    register_embedding_change_listeners()
    with blank_session() as session:
        company_id = sorento(session)
        staff_project = project(session, company_id, "EMBED STAFF TOWER", code="PRJ-ZZT-EM1")
        assert _queued(session, staff_project.id) >= 1  # the unchanged staff path

        rows = {s: project(session, company_id, f"EMBED {s.upper()} TOWER", approval_state=s) for s in UNAPPROVED}
        for state, row in rows.items():
            assert _queued(session, row.id) == 0, state
        # a title edit while pending is still nothing to embed
        rows["pending"].title = "EMBED PENDING TOWER PHASE 2"
        assert _queued(session, rows["pending"].id) == 0

        rows["pending"].approval_state = "approved"
        rows["pending"].project_code = "PPF2601042"
        assert _queued(session, rows["pending"].id) >= 1  # now it is a project: embedded


def test_rw8_the_embedding_worker_has_no_text_for_an_unapproved_project():
    from app.services.embedding_worker import _canonical_for_source

    with blank_session() as session:
        company_id = sorento(session)
        ok = project(session, company_id, "WORKER APPROVED TOWER", approval_state="approved", code="PPF2601043")
        assert _canonical_for_source(session, "project", ok.id)["title"] == "WORKER APPROVED TOWER"
        for state in UNAPPROVED:
            row = project(session, company_id, f"WORKER {state.upper()} TOWER", approval_state=state)
            with pytest.raises(ValueError):
                _canonical_for_source(session, "project", row.id)


def test_rw8_the_staleness_sweep_does_not_scan_unapproved_projects():
    from app.services.project_staleness_service import sweep

    long_ago = datetime.utcnow() - timedelta(days=120)
    with blank_session() as session:
        company_id = sorento(session)
        project(session, company_id, "SWEEP STAFF TOWER", code="PRJ-ZZT-SW1")
        hidden = []
        for state in UNAPPROVED:
            row = project(session, company_id, f"SWEEP {state.upper()} TOWER", approval_state=state)
            row.last_meaningful_activity_at = long_ago
            row.stale_level = 2  # even one that carries a rung is not the sweep's business
            hidden.append(row)
        session.flush()
        summary = sweep(session, notify=False)
        assert summary["scanned"] == 1
        session.expire_all()
        for row in hidden:
            assert row.stale_level == 2 and row.stale_since is None


# ------------------------------------------------------------------ RW10 no "None" for a missing code


def test_rw10_the_not_editable_refusal_names_the_awaiting_label(world):
    from app.services.error_handler import AppException
    from app.services.project_service import assert_can_edit_project

    p = project(world.db, world.company_id, "Message tower", approval_state="pending", owner=world.owner)
    with pytest.raises(AppException) as exc:
        assert_can_edit_project(world.db, p, world.staff, set())
    message = exc.value.detail["message"]
    assert "None" not in message
    assert "Awaiting approval" in message


def test_rw10_the_not_editable_refusal_over_http(world):
    rid = pending(world)
    res = as_user(world, world.staff).put(f"{STAFF}/{rid}", json={"mukim": "x"})
    assert res.status_code == 403
    assert "None" not in res.json()["message"]
    assert "Awaiting approval" in res.json()["message"]


def test_rw10_a_staff_project_still_quotes_its_code_in_that_refusal(world):
    from app.services.error_handler import AppException
    from app.services.project_service import assert_can_edit_project

    p = project(world.db, world.company_id, "Coded tower", code="PRJ-ZZT-MSG", owner=world.owner)
    with pytest.raises(AppException) as exc:
        assert_can_edit_project(world.db, p, world.staff, set())
    assert "PRJ-ZZT-MSG" in exc.value.detail["message"]


def test_rw10_the_self_takeover_and_open_request_messages(world):
    from app.services.error_handler import AppException
    from app.services.project_service import create_takeover_request

    p = project(world.db, world.company_id, "Takeover tower", approval_state="pending", owner=world.owner)
    with pytest.raises(AppException) as exc:
        create_takeover_request(world.db, project=p, requester_user_id=world.owner, kind="join", reason="mine")
    assert "None" not in exc.value.detail["message"]
    assert "Awaiting approval" in exc.value.detail["message"]


def test_rw10_the_staleness_messages_never_say_none():
    from app.models.projects import Project
    from app.services.project_staleness_service import _message

    shell = Project(title="Message tower", project_code=None)
    for level in (1, 2, 3):
        out = _message(shell, level, {"days": 12, "reason": "no_activity"})
        assert "None" not in out["title"] and "None" not in out["body"], level
        assert "Awaiting approval" in out["title"], level


def test_rw10_the_floor_breach_notice_never_says_none(world, monkeypatch):
    from app.services import project_notify_service as notify

    sent = []
    monkeypatch.setattr(notify, "_send", lambda db, **kw: sent.append(kw) or 0)
    p = project(world.db, world.company_id, "Notice tower", approval_state="pending", owner=world.owner)
    notify.notify_floor_breach(
        world.db, project=p,
        event={"floor_value": "10", "unit_price": "9", "floor_level": "series", "quotation_id": uid(), "line_id": uid()},
    )
    assert sent
    assert "None" not in sent[0]["title"] and "None" not in sent[0]["body"]
    assert "Awaiting approval" in sent[0]["title"]


def test_rw10_the_task_refusal_names_the_label(world):
    from app.models.projects import ProjectTask
    from app.services.error_handler import AppException
    from app.services.project_task_service import assert_can_edit_task

    p = project(world.db, world.company_id, "Task message tower", approval_state="pending", owner=world.owner)
    task = ProjectTask(id=uid(), company_id=world.company_id, project_id=p.id, name="t")
    world.db.add(task)
    world.db.flush()
    with pytest.raises(AppException) as exc:
        assert_can_edit_task(world.db, task, p, world.staff, set())
    assert "None" not in exc.value.detail["message"]
    assert "Awaiting approval" in exc.value.detail["message"]
