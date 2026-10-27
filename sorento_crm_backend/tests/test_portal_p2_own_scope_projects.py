"""PORTAL-P2-ONLY-THEIRS: projects, server side (UAC 1, 2, 3, 4, 6, 7).

A user holding `projects.projects.view_own` and not `projects.projects.view` sees only
the projects they own, collaborate on, or registered from the portal through their own
contact, and everything under them. Anything else is a 404, reads and writes alike, on
every route under the project-sales router.
"""
from __future__ import annotations

import re
import uuid
from datetime import date

import pytest
from fastapi.routing import APIRoute

from app.models.base import company_scope
from app.models.projects import (
    Project,
    ProjectCollaborator,
    ProjectPurchaseOrder,
    ProjectQuotation,
    ProjectQuotationDocument,
    ProjectQuotationVersion,
    ProjectSalesProfile,
    ProjectSample,
)
from app.models.project_so import (
    DeliverySchedule,
    DeliveryScheduleVersion,
    ProjectDeliveryPhase,
    ProjectPOVersion,
    ProjectSalesOrder,
)

from ._own_scope_support import MARKER, acting, uid, user, world
from ._pg_fixture import blank_session

BASE = "/api/v1/project-sales"
VIEW = "projects.projects.view"
VIEW_OWN = "projects.projects.view_own"
EDIT = "projects.projects.edit"
DELETE = "projects.projects.delete"
LIMITED = {VIEW_OWN, EDIT, DELETE}


def _project(db, company_id: str, owner: str | None, *, approval_state=None) -> Project:
    tag = uuid.uuid4().hex[:6]
    row = Project(
        id=uid(),
        company_id=company_id,
        project_code=f"{MARKER}-{tag}",
        title=f"{MARKER} Project {tag}",
        normalised_title=f"{MARKER} project {tag}",
        owner_user_id=owner,
        approval_state=approval_state,
    )
    db.add(row)
    db.flush()
    return row


def _children(db, company_id: str, project: Project) -> dict:
    """One row per guard anchor under `project`, with only the columns each requires."""
    document = ProjectQuotationDocument(
        id=uid(), company_id=company_id, project_id=project.id, document_no=f"{MARKER}-{uid()[:6]}"
    )
    db.add(document)
    db.flush()
    quotation = ProjectQuotation(
        id=uid(), company_id=company_id, project_id=project.id, document_id=document.id,
        scope_label="Scope",
    )
    db.add(quotation)
    db.flush()
    version = ProjectQuotationVersion(
        id=uid(), company_id=company_id, quotation_id=quotation.id, version_no=1
    )
    db.add(version)
    db.flush()
    sample = ProjectSample(
        id=uid(), company_id=company_id, project_id=project.id, quotation_version_id=version.id
    )
    po = ProjectPurchaseOrder(
        id=uid(), company_id=company_id, project_id=project.id, po_number=f"{MARKER}-{uid()[:6]}"
    )
    db.add_all([sample, po])
    db.flush()
    po_version = ProjectPOVersion(id=uid(), company_id=company_id, purchase_order_id=po.id, version_no=1)
    schedule = DeliverySchedule(
        id=uid(), company_id=company_id, project_id=project.id, purchase_order_id=po.id
    )
    db.add_all([po_version, schedule])
    db.flush()
    schedule_version = DeliveryScheduleVersion(
        id=uid(), company_id=company_id, delivery_schedule_id=schedule.id, version_no=1
    )
    phase = ProjectDeliveryPhase(
        id=uid(), company_id=company_id, project_id=project.id, area_group="A", sequence=1
    )
    order = ProjectSalesOrder(
        id=uid(), company_id=company_id, project_id=project.id,
        provisional_ref=f"{MARKER}-PSO-{uid()[:8]}",
    )
    db.add_all([schedule_version, phase, order])
    db.flush()
    return {
        "document": document.id,
        "quotation": quotation.id,
        "version": version.id,
        "sample": sample.id,
        "po": po.id,
        "po_version": po_version.id,
        "schedule": schedule.id,
        "schedule_version": schedule_version.id,
        "phase": phase.id,
        "order": order.id,
    }


@pytest.fixture()
def scene():
    """A owns P1 and P2 and collaborates on P3 (B's); B owns P4; P5 is a pending portal
    registration by A's own contact; P6 is a portal draft by A's contact (never visible)."""
    with blank_session() as db:
        w = world(db)
        with company_scope(db, frozenset({w.company_id})):
            p1 = _project(db, w.company_id, w.a)
            p2 = _project(db, w.company_id, w.a)
            p3 = _project(db, w.company_id, w.b)
            p4 = _project(db, w.company_id, w.b)
            p5 = _project(db, w.company_id, None, approval_state="pending")
            p6 = _project(db, w.company_id, None, approval_state="draft")
            db.add(ProjectCollaborator(project_id=p3.id, user_id=w.a))
            db.add(ProjectSalesProfile(project_id=p5.id, contact_id=w.ca.id))
            db.add(ProjectSalesProfile(project_id=p6.id, contact_id=w.ca.id))
            db.flush()
            yield db, w, {"p1": p1.id, "p2": p2.id, "p3": p3.id, "p4": p4.id, "p5": p5.id, "p6": p6.id}


def _listed(client) -> set:
    response = client.get(f"{BASE}/projects/", params={"limit": 200})
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()["data"]}


# ------------------------------------------------------------------ UAC 1, 7: the list


def test_a_limited_list_holds_only_their_projects(scene):
    db, w, p = scene
    with acting(db, w.a, LIMITED) as client:
        assert _listed(client) == {p["p1"], p["p2"], p["p3"], p["p5"]}


def test_a_limited_user_with_no_contact_sees_only_rows_keyed_on_their_user_id(scene):
    db, w, p = scene
    loner = user(db, "No contact")
    mine = _project(db, w.company_id, loner)
    db.add(ProjectCollaborator(project_id=p["p4"], user_id=loner))
    db.flush()
    with acting(db, loner, LIMITED) as client:
        assert _listed(client) == {mine.id, p["p4"]}


# ------------------------------------------------------------------ UAC 4: unchanged for view


def test_a_view_holder_still_reads_every_project(scene):
    db, w, p = scene
    with acting(db, w.a, {VIEW}) as client:
        assert {p["p1"], p["p3"], p["p4"], p["p5"]} <= _listed(client)
        assert client.get(f"{BASE}/projects/{p['p4']}").status_code == 200


def test_view_and_view_own_together_behave_as_view(scene):
    db, w, p = scene
    with acting(db, w.a, {VIEW, VIEW_OWN}) as client:
        assert p["p4"] in _listed(client)
        assert client.get(f"{BASE}/projects/{p['p4']}").status_code == 200


def test_admin_and_superadmin_are_never_limited(scene):
    """The real permission service, no stub: admin and superadmin get every slug from
    `get_user_permission_slugs`, `view` included, so `view_own` never narrows them."""
    from sqlalchemy import text as sql

    from app.models.user import UserPermission, UserRole, UserRoleAssignment
    from app.services import own_scope

    db, w, _p = scene
    for slug in (VIEW, VIEW_OWN):  # the blank schema seeds no permissions
        if not db.query(UserPermission).filter(UserPermission.slug == slug).first():
            db.add(UserPermission(id=uid(), slug=slug, name=slug))
    for slug in ("admin", "superadmin"):
        role_id = db.execute(sql("select id from user_roles where slug = :s"), {"s": slug}).scalar()
        if role_id is None:
            role_id = uid()
            db.add(UserRole(id=role_id, slug=slug, name=f"{MARKER} {slug}"))
            db.flush()
        holder = user(db, f"Role {slug}")
        db.add(UserRoleAssignment(id=uid(), user_id=holder, role_id=role_id))
        db.flush()
        assert not own_scope.user_is_limited(db, holder, VIEW, VIEW_OWN), slug


# ------------------------------------------------------------------ UAC 2, 3: detail and children


def test_own_collaborated_and_portal_registered_projects_open(scene):
    db, w, p = scene
    with acting(db, w.a, LIMITED) as client:
        for key in ("p1", "p3", "p5"):
            assert client.get(f"{BASE}/projects/{p[key]}").status_code == 200, key


def test_a_portal_draft_stays_not_found_even_to_its_contact(scene):
    db, w, p = scene
    with acting(db, w.a, LIMITED) as client:
        assert client.get(f"{BASE}/projects/{p['p6']}").status_code == 404


def _project_id_routes():
    from app.main import app

    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(BASE) and "{project_id}" in route.path:
            for method in sorted(route.methods):
                yield method, route.path


def _fill(path: str, project_id: str) -> str:
    path = path.replace("{project_id}", project_id)
    return re.sub(r"{(\w+)(?::\w+)?}", lambda m: "0" if m.group(1).endswith("index") else uid(), path)


def test_every_project_id_route_is_404_for_a_foreign_project(scene):
    """UAC 2 + 3: enumerated, so a child route added later is covered without editing this."""
    db, w, p = scene
    routes = list(_project_id_routes())
    assert len(routes) > 40  # the enumeration itself is not silently empty
    with acting(db, w.a, LIMITED | {"projects.registrations.approve", "projects.quotations.approve"}) as client:
        for method, path in routes:
            response = client.request(method, _fill(path, p["p4"]), json={})
            assert response.status_code == 404, (method, path, response.status_code, response.text)


def test_writes_on_a_foreign_project_are_404(scene):
    db, w, p = scene
    with acting(db, w.a, LIMITED) as client:
        assert client.put(f"{BASE}/projects/{p['p4']}", json={"title": "x"}).status_code == 404
        assert client.delete(f"{BASE}/projects/{p['p4']}").status_code == 404
        assert client.post(f"{BASE}/projects/{p['p4']}/tasks", json={"name": "x"}).status_code == 404


# One read (or a harmless write) per guard anchor, addressed by the child's own id.
_CHILD_ROUTES = (
    ("GET", "/quotations/{quotation}/versions"),
    ("GET", "/quotation-versions/{version}/lines"),
    ("PUT", "/samples/{sample}"),
    ("GET", "/purchase-orders/{po}/lines"),
    ("GET", "/purchase-order-versions/{po_version}"),
    ("GET", "/delivery-schedules/{schedule}/versions"),
    ("GET", "/delivery-schedule-versions/{schedule_version}"),
    ("PUT", "/delivery-phases/{phase}/date"),
    ("GET", "/sales-orders/{order}"),
)


def test_a_child_of_a_foreign_project_is_404_by_its_own_id(scene):
    db, w, p = scene
    foreign = _children(db, w.company_id, db.get(Project, p["p4"]))
    with acting(db, w.a, LIMITED) as client:
        for method, template in _CHILD_ROUTES:
            path = BASE + template.format(**foreign)
            response = client.request(method, path, json={})
            assert response.status_code == 404, (method, template, response.text)


def test_a_child_of_their_own_project_passes_the_guard(scene):
    db, w, p = scene
    own = _children(db, w.company_id, db.get(Project, p["p1"]))
    with acting(db, w.a, LIMITED) as client:
        for method, template in _CHILD_ROUTES:
            response = client.request(method, BASE + template.format(**own), json={})
            assert response.status_code not in (403, 404), (method, template, response.text)


def test_a_removed_collaborator_loses_the_project_on_the_next_request(scene):
    db, w, p = scene
    with acting(db, w.a, LIMITED) as client:
        assert client.get(f"{BASE}/projects/{p['p3']}").status_code == 200
        db.query(ProjectCollaborator).filter(
            ProjectCollaborator.project_id == p["p3"], ProjectCollaborator.user_id == w.a
        ).delete()
        db.flush()
        assert client.get(f"{BASE}/projects/{p['p3']}").status_code == 404
        assert p["p3"] not in _listed(client)


# ------------------------------------------------------------------ fail closed (Q1a)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/my-tasks"),
        ("POST", "/sales-orders/bulk-delete"),
        ("GET", "/amendments/{x}"),
        ("GET", "/parties/{x}"),
    ],
)
def test_routes_outside_the_map_are_refused_to_a_limited_user(scene, method, path):
    db, w, _p = scene
    with acting(db, w.a, LIMITED | {"projects.parties.view"}) as client:
        response = client.request(method, BASE + path.replace("{x}", uid()), json={})
        assert response.status_code == 403, response.text


def test_the_guard_map_names_only_routes_that_exist():
    """Kill test for the map itself: every anchor and id-less entry matches a live route, so a
    renamed route cannot leave a stale entry behind that silently stops matching."""
    from app.api.v1.projects import _own_scope
    from app.main import app

    paths = {
        (method, route.path[len(BASE):])
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith(BASE)
        for method in route.methods
    }
    for segment, param in _own_scope._ANCHORS:
        assert any(f"/{segment}/{{{param}}}" in path for _m, path in paths), (segment, param)
    for entry in _own_scope._ID_LESS:
        assert entry in paths, entry


# ------------------------------------------------------------------ UAC 6: the activity panel


def test_the_project_activity_panel_is_404_for_a_foreign_project(scene):
    db, w, p = scene
    with acting(db, w.a, LIMITED) as client:
        assert client.get(f"/api/v1/activities/project/{p['p4']}/activities").status_code == 404
        assert client.get(f"/api/v1/activities/project/{p['p1']}/activities").status_code == 200


def test_the_project_activity_panel_is_unchanged_for_a_view_holder(scene):
    db, w, p = scene
    with acting(db, w.a, {VIEW}) as client:
        assert client.get(f"/api/v1/activities/project/{p['p4']}/activities").status_code == 200


# ------------------------------------------------------------------ UAC 6: the assistant's project lookup


def _probe(db, w, user_id, perms, tokens):
    from app.audit_context import AuditActor, stamp_actor
    from app.services.entity_resolver import _probe_project

    stamp_actor(AuditActor(actor_type="user", user_id=user_id, real_user_id=user_id), db=db)
    with acting(db, user_id, perms):
        found = _probe_project(db, tokens)
    return {m.uuid for matches in found.values() for m in matches}


def test_the_assistant_does_not_name_a_foreign_project_to_a_limited_user(scene):
    db, w, p = scene
    codes = [db.get(Project, p[k]).project_code for k in ("p1", "p4")]
    assert _probe(db, w, w.a, LIMITED, codes) == {p["p1"]}
    assert _probe(db, w, w.a, {VIEW}, codes) == {p["p1"], p["p4"]}


def test_every_route_a_limited_user_reaches_is_pinned():
    """Security review L5: a route that becomes reachable to a limited user (a new child under
    an anchor, a new reference path) changes this list, so it is reviewed rather than trusted.
    Regenerate the file from the failure message after checking the new route scopes its ids."""
    from pathlib import Path

    from app.api.v1.projects import _own_scope
    from app.main import app

    reached = sorted(
        f"{method} {route.path_format[len(BASE):]}"
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith(BASE)
        for method in route.methods
        if _own_scope.classify(method, route.path_format) is not None
    )
    pinned = (Path(__file__).parent / "portal_p2_allowed_routes.txt").read_text().split("\n")
    assert reached == [line for line in pinned if line], "\n".join(
        sorted(set(reached) ^ {line for line in pinned if line})
    )


# ------------------------------------------------------------------ security review M1, M2, L1


def test_a_clash_does_not_name_a_foreign_project_to_a_limited_user(scene):
    from app.services import project_seed_service

    db, w, p = scene
    project_seed_service.run(db, company_id=w.company_id)
    foreign = db.get(Project, p["p4"])
    with acting(db, w.a, LIMITED) as client:
        response = client.post(f"{BASE}/projects/", json={"title": foreign.title})
        assert response.status_code == 409, (response.status_code, response.text)
        assert foreign.project_code not in response.text
        assert foreign.title not in response.text
    with acting(db, w.a, {VIEW, EDIT}) as client:
        response = client.post(f"{BASE}/projects/", json={"title": foreign.title})
        assert response.status_code == 409, response.text
        assert foreign.project_code in response.text


def test_possible_duplicates_name_only_their_own_projects(scene, monkeypatch):
    from app.services import project_registration_service as registrations

    db, w, p = scene
    listed = [{"project_id": p[k], "project_code": "x", "title": "x"} for k in ("p1", "p4")]
    monkeypatch.setattr(registrations, "duplicates_for_project", lambda db_, project: list(listed))
    with acting(db, w.a, LIMITED) as client:
        body = client.get(f"{BASE}/projects/{p['p5']}").json()
        assert [d["project_id"] for d in body["possible_duplicates"]] == [p["p1"]]
    with acting(db, w.a, {VIEW}) as client:
        body = client.get(f"{BASE}/projects/{p['p5']}").json()
        assert [d["project_id"] for d in body["possible_duplicates"]] == [p["p1"], p["p4"]]


def test_a_schedule_cell_refuses_another_projects_phase(scene):
    from app.services.error_handler import AppException
    from app.services.project_schedule_service import ProjectScheduleService

    db, w, p = scene
    own = _children(db, w.company_id, db.get(Project, p["p1"]))
    foreign = _children(db, w.company_id, db.get(Project, p["p4"]))
    with pytest.raises(AppException) as exc:
        ProjectScheduleService(db).update_cells(
            own["schedule_version"],
            [{"phase_id": foreign["phase"], "product_id": uid(), "qty": 1}],
        )
    assert exc.value.status_code == 404


def test_a_second_id_not_trusted_under_its_anchor_is_refused():
    """The `_NESTED` refusal no live route reaches today (reviewer kill test M23)."""
    from app.api.v1.projects import _own_scope

    assert _own_scope.classify("GET", BASE + "/projects/{project_id}/x/{other_id}") is None
    assert _own_scope.classify("GET", BASE + "/samples/{sample_id}/lines/{line_id}") is None
    assert _own_scope.classify("GET", BASE + "/projects/{project_id}/tasks/{task_id}") is not None


def _gate_slugs(route) -> set:
    slugs: set = set()

    def walk(dependant):
        for cell in getattr(dependant.call, "__closure__", None) or ():
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if isinstance(value, str):
                slugs.add(value)
            elif isinstance(value, (list, tuple)):
                slugs.update(v for v in value if isinstance(v, str))
        for sub in dependant.dependencies:
            walk(sub)

    walk(route.dependant)
    return slugs


def test_no_route_takes_view_own_that_the_guard_then_refuses():
    """Reviewer S2: a read opened to `view_own` but refused by the guard is a dead change
    that reads as a grant. Every route gated on `view_own` must be one the guard lets through."""
    from app.api.v1.projects import _own_scope
    from app.main import app

    dead = [
        f"{method} {route.path}"
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith(BASE)
        and VIEW_OWN in _gate_slugs(route)
        for method in route.methods
        if _own_scope.classify(method, route.path_format) is None
    ]
    assert dead == []



# ------------------------------------------------------------------ owner ruling Q2 (27 Oct 17:50)

GUARD_REFUSAL = "Not available with access to your own records only."

#: One route per cross-project screen the owner named: each follows its own permission slug.
_CROSS_PROJECT = (
    ("GET", "/reports/forecast", VIEW),
    ("GET", "/stock-debt", "projects.stock_debt.view"),
    ("GET", "/order-inquiries", VIEW),
    ("GET", "/leads", VIEW),
    ("GET", "/allocation-claims", VIEW),
    ("GET", "/fulfilment-planning/queue", VIEW),
    ("GET", "/divergences", VIEW),
)


@pytest.mark.parametrize("method,path,own_slug", _CROSS_PROJECT)
def test_view_own_neither_opens_nor_closes_a_cross_project_screen(scene, method, path, own_slug):
    """Q2: "depends on the permission we give to their role". Holding view_own on projects
    must not by itself open the screen (its own slug still answers 403) nor close it (with
    its own slug granted, the guard does not refuse)."""
    db, w, _p = scene
    with acting(db, w.a, LIMITED) as client:
        response = client.request(method, BASE + path)
        if own_slug != VIEW:
            assert response.status_code == 403, response.text
        assert GUARD_REFUSAL not in response.text
    if own_slug != VIEW:
        with acting(db, w.a, LIMITED | {own_slug}) as client:
            response = client.request(method, BASE + path)
            assert response.status_code != 403, response.text


def test_a_cross_project_write_follows_its_own_slug_for_a_limited_user(scene):
    """Q2: POST /leads takes projects.projects.edit; the guard does not refuse it."""
    db, w, _p = scene
    with acting(db, w.a, LIMITED) as client:
        response = client.post(BASE + "/leads", json={"title": f"{MARKER} lead"})
        assert GUARD_REFUSAL not in response.text
