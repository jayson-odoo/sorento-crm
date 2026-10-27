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


def test_admin_still_reads_every_project(scene):
    """Admin gets every slug from `get_user_permission_slugs`, `view` included."""
    db, w, p = scene
    with acting(db, w.a, {VIEW, VIEW_OWN, EDIT}, roles={"admin"}) as client:
        assert p["p4"] in _listed(client)
        assert client.get(f"{BASE}/projects/{p['p4']}").status_code == 200


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
        ("GET", "/reports/forecast"),
        ("GET", "/my-tasks"),
        ("POST", "/leads"),
        ("GET", "/leads/{x}"),
        ("GET", "/order-inquiries"),
        ("POST", "/sales-orders/bulk-delete"),
        ("GET", "/amendments/{x}"),
        ("GET", "/divergences/{x}"),
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
