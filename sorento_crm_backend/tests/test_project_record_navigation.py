"""Prev/next neighbours for the three project-sales detail screens.

The detail pages (a sales order, a customer PO, a delivery schedule version) each carry the
shared `RecordNavigation` pager, and the pager walks the SAME set, in the SAME order, that
the list the user came from shows:

* sales orders  -> the project's own orders, newest first (the sales-orders tab's order).
* purchase orders -> the project's own POs, newest PO date first (the POs tab's order).
* schedule versions -> the revision history of THIS schedule, newest version first (the
  versions grid's order).

What is pinned here is that ordering, the circular wrap at both ends (a Next on the last
record reaches the first), the 404 an id that names nothing gets, and the auth the endpoints
refuse without.

Cleanup is by rollback (``blank_session``) and every row is created by the test: the shared
database is a copy of production.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.models.project_so import DeliverySchedule, DeliveryScheduleVersion, ProjectSalesOrder
from app.models.projects import ProjectParty, ProjectPurchaseOrder
from app.models.user import User
from app.services import project_record_navigation as nav
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-nav"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} owner"))
    db.flush()
    return user_id


def _project(db, company_id: str, owner: str):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} {_uid()[:12]}",
    )


def _party(db, company_id: str) -> ProjectParty:
    row = ProjectParty(
        id=_uid(),
        company_id=company_id,
        party_type="trading_house",
        name=f"{MARKER} {_uid()[:6]}",
    )
    db.add(row)
    db.flush()
    return row


def _po(db, project, party, *, po_date: date, po_number: str) -> ProjectPurchaseOrder:
    row = ProjectPurchaseOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        po_source="trading_house",
        issuing_party_id=party.id,
        po_number=po_number,
        po_date=po_date,
        status="approved",
    )
    db.add(row)
    db.flush()
    return row


def _sales_order(db, project, *, ref: str, created_at: datetime) -> ProjectSalesOrder:
    row = ProjectSalesOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        provisional_ref=ref,
        status="draft",
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def _schedule(db, project, po) -> DeliverySchedule:
    row = DeliverySchedule(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        purchase_order_id=po.id,
        label=f"{MARKER} schedule",
    )
    db.add(row)
    db.flush()
    return row


def _version(db, schedule, *, version_no: int) -> DeliveryScheduleVersion:
    row = DeliveryScheduleVersion(
        id=_uid(),
        company_id=schedule.company_id,
        delivery_schedule_id=schedule.id,
        version_no=version_no,
        extraction_state="done",
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        yield db, company_id, owner


# ------------------------------------------------------------------ sales orders


def _three_orders(db, project):
    """Newest first is PSO-3, PSO-2, PSO-1 - the order the sales-orders tab lists."""
    return [
        _sales_order(db, project, ref="PSO-1", created_at=datetime(2026, 4, 1, 9, 0)),
        _sales_order(db, project, ref="PSO-2", created_at=datetime(2026, 4, 2, 9, 0)),
        _sales_order(db, project, ref="PSO-3", created_at=datetime(2026, 4, 3, 9, 0)),
    ]


def test_sales_order_neighbours_walk_the_tab_order(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    first, middle, last = _three_orders(db, project)

    out = nav.sales_order_neighbours(db, project_id=project.id, pso_id=middle.id)

    # Newest first: [PSO-3, PSO-2, PSO-1]. PSO-2 sits second.
    assert out["total"] == 3
    assert out["index"] == 2
    assert out["prev_id"] == last.id
    assert out["next_id"] == first.id


def test_sales_order_neighbours_wrap_at_both_ends(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    oldest, _middle, newest = _three_orders(db, project)

    top = nav.sales_order_neighbours(db, project_id=project.id, pso_id=newest.id)
    bottom = nav.sales_order_neighbours(db, project_id=project.id, pso_id=oldest.id)

    assert top["index"] == 1 and top["prev_id"] == oldest.id
    assert bottom["index"] == 3 and bottom["next_id"] == newest.id


def test_sales_order_neighbours_are_scoped_to_the_project(seeded):
    # Another project's orders are a different sequence, not extra rows in this one.
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    other = _project(db, company_id, owner)
    mine = _sales_order(db, project, ref="PSO-9", created_at=datetime(2026, 4, 1, 9, 0))
    _sales_order(db, other, ref="PSO-10", created_at=datetime(2026, 4, 2, 9, 0))

    out = nav.sales_order_neighbours(db, project_id=project.id, pso_id=mine.id)

    assert out["total"] == 1
    assert out["index"] == 1
    assert out["prev_id"] is None and out["next_id"] is None


def test_sales_order_neighbours_unknown_id_is_404(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)

    with pytest.raises(AppException) as raised:
        nav.sales_order_neighbours(db, project_id=project.id, pso_id=_uid())

    assert raised.value.status_code == 404


def test_sales_order_neighbours_from_another_project_is_404(seeded):
    # The id exists, but not in the project the pager is walking: naming it would put a
    # record from somewhere else into this sequence.
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    other = _project(db, company_id, owner)
    elsewhere = _sales_order(db, other, ref="PSO-11", created_at=datetime(2026, 4, 1, 9, 0))

    with pytest.raises(AppException) as raised:
        nav.sales_order_neighbours(db, project_id=project.id, pso_id=elsewhere.id)

    assert raised.value.status_code == 404


# --------------------------------------------------------------- purchase orders


def _three_pos(db, project, party):
    """Newest PO date first is PO-3, PO-2, PO-1 - the order the POs tab lists."""
    return [
        _po(db, project, party, po_date=date(2026, 1, 5), po_number=f"{MARKER}/PO-1"),
        _po(db, project, party, po_date=date(2026, 2, 5), po_number=f"{MARKER}/PO-2"),
        _po(db, project, party, po_date=date(2026, 3, 5), po_number=f"{MARKER}/PO-3"),
    ]


def test_purchase_order_neighbours_walk_the_tab_order(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    party = _party(db, company_id)
    first, middle, last = _three_pos(db, project, party)

    out = nav.purchase_order_neighbours(db, project_id=project.id, po_id=middle.id)

    assert out["total"] == 3
    assert out["index"] == 2
    assert out["prev_id"] == last.id
    assert out["next_id"] == first.id


def test_purchase_order_neighbours_wrap_at_both_ends(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    party = _party(db, company_id)
    oldest, _middle, newest = _three_pos(db, project, party)

    top = nav.purchase_order_neighbours(db, project_id=project.id, po_id=newest.id)
    bottom = nav.purchase_order_neighbours(db, project_id=project.id, po_id=oldest.id)

    assert top["index"] == 1 and top["prev_id"] == oldest.id
    assert bottom["index"] == 3 and bottom["next_id"] == newest.id


def test_purchase_order_neighbours_unknown_id_is_404(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)

    with pytest.raises(AppException) as raised:
        nav.purchase_order_neighbours(db, project_id=project.id, po_id=_uid())

    assert raised.value.status_code == 404


def test_purchase_order_neighbours_from_another_project_is_404(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    other = _project(db, company_id, owner)
    party = _party(db, company_id)
    elsewhere = _po(db, other, party, po_date=date(2026, 1, 5), po_number=f"{MARKER}/PO-X")

    with pytest.raises(AppException) as raised:
        nav.purchase_order_neighbours(db, project_id=project.id, po_id=elsewhere.id)

    assert raised.value.status_code == 404


# ------------------------------------------------------- delivery schedule versions


def test_schedule_version_neighbours_walk_the_revision_history(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    party = _party(db, company_id)
    po = _po(db, project, party, po_date=date(2026, 1, 5), po_number=f"{MARKER}/PO-S")
    schedule = _schedule(db, project, po)
    v1 = _version(db, schedule, version_no=1)
    v2 = _version(db, schedule, version_no=2)
    v3 = _version(db, schedule, version_no=3)
    # Another schedule on the same project: a different history, not more of this one.
    other_schedule = _schedule(db, project, po)
    _version(db, other_schedule, version_no=1)

    out = nav.schedule_version_neighbours(db, version_id=v2.id)

    # Newest first: [v3, v2, v1].
    assert out["total"] == 3
    assert out["index"] == 2
    assert out["prev_id"] == v3.id
    assert out["next_id"] == v1.id


def test_schedule_version_neighbours_wrap_at_both_ends(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    party = _party(db, company_id)
    po = _po(db, project, party, po_date=date(2026, 1, 5), po_number=f"{MARKER}/PO-W")
    schedule = _schedule(db, project, po)
    v1 = _version(db, schedule, version_no=1)
    _v2 = _version(db, schedule, version_no=2)
    v3 = _version(db, schedule, version_no=3)

    top = nav.schedule_version_neighbours(db, version_id=v3.id)
    bottom = nav.schedule_version_neighbours(db, version_id=v1.id)

    assert top["index"] == 1 and top["prev_id"] == v1.id
    assert bottom["index"] == 3 and bottom["next_id"] == v3.id


def test_schedule_version_neighbours_single_version_has_no_neighbours(seeded):
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    party = _party(db, company_id)
    po = _po(db, project, party, po_date=date(2026, 1, 5), po_number=f"{MARKER}/PO-1V")
    schedule = _schedule(db, project, po)
    only = _version(db, schedule, version_no=1)

    out = nav.schedule_version_neighbours(db, version_id=only.id)

    assert out["total"] == 1 and out["index"] == 1
    assert out["prev_id"] is None and out["next_id"] is None


def test_schedule_version_neighbours_unknown_id_is_404(seeded):
    db, _company_id, _owner = seeded

    with pytest.raises(AppException) as raised:
        nav.schedule_version_neighbours(db, version_id=_uid())

    assert raised.value.status_code == 404


# ------------------------------------------------------------------ endpoint auth

# A FIXED id, not uuid4(): parametrize ids are part of the collected test id, and
# pytest-xdist refuses to run when workers collect different ids ("Different tests
# were collected between gw4 and gw3"). The value is never looked up.
PROJECT_ID = "00000000-0000-4000-8000-0000000000a1"
NEIGHBOUR_PATHS = [
    f"/api/v1/project-sales/projects/{PROJECT_ID}/sales-orders/neighbours",
    f"/api/v1/project-sales/projects/{PROJECT_ID}/purchase-orders/neighbours",
    "/api/v1/project-sales/delivery-schedule-versions/neighbours",
]


@pytest.mark.parametrize("path", NEIGHBOUR_PATHS)
def test_neighbours_endpoints_require_auth(path: str) -> None:
    with TestClient(app) as client:
        res = client.get(path, params={"id": str(uuid.uuid4())})
    assert res.status_code in (401, 403), res.text


@pytest.mark.parametrize("path", NEIGHBOUR_PATHS)
def test_neighbours_endpoints_require_an_id(path: str) -> None:
    # `id` is required. Auth may reject before validation does; what must not happen is a
    # 200 or a 500.
    with TestClient(app) as client:
        res = client.get(path)
    assert res.status_code in (401, 403, 422), res.text
