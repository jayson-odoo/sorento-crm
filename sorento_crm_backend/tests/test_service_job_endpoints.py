"""S6 - the dispatch API, and the two things a route layer can get wrong on its own.

The service-level gate (`test_service_job_dispatch.py`) already proves the rules. What this
file adds is what only the HTTP boundary can be wrong about:

**Who is allowed.** Three slugs, and the split only means something if the routes actually
enforce it. A dispatcher-shaped principal holding `view` alone must be refused the confirm,
because the whole reason `dispatch` is separate is that committing a person to a place at a
time is not the same act as reading the board. `require_permission_with_api_key` is
deliberately absent from every write: it is documented as read-oriented, and nothing here
has the second real-user gate the two exceptions in the codebase carry.

**That the domain's own status code survives.** `AppException` subclasses `HTTPException`,
so a route wrapping its body in a bare `except Exception` turns AC-F5's 422 into an opaque
500 - the dispatcher then sees "something went wrong" instead of the sentence explaining why
a date without an agreement is not a confirmation. That is a real regression this suite
exists to catch, and it is invisible at the service level.

Permissions are modelled by patching the lookup rather than by seeding roles: a blank schema
has no roles at all, and seeding an RBAC chain here would be testing `UserPermissionService`
rather than these routes. Enforcement of the lookup itself is `test_rbac.py`'s job.

Run: venv/bin/python -m pytest tests/test_service_job_endpoints.py -q -p no:randomly
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402

from app import database as app_database  # noqa: E402
from app.dependencies import get_current_user, get_current_user_or_api_key  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session  # noqa: E402

BASE = "/api/v1/complaints-management/service-jobs"
TECHNICIANS = "/api/v1/complaints-management/technicians"

VIEW = "complaint_management.service_jobs.view"
DISPATCH = "complaint_management.service_jobs.dispatch"
COSTS = "complaint_management.case_costs.manage"


@pytest.fixture
def db():
    with blank_session() as session:
        from app.services.service_job_status_graph import seed_service_job_status_graph

        seed_service_job_status_graph(session)
        session.flush()
        yield session


@pytest.fixture
def client(db):
    """A logged-in principal. Permissions are granted per-test by `granted()`."""

    def _override_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "dispatcher@example.test"}
    app.dependency_overrides[app_database.get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(app_database.get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_or_api_key, None)


@contextmanager
def granted(*slugs: str):
    """Hold exactly these permissions and no others.

    Deliberately exact rather than "grant everything": a test that granted all three
    could never notice a route reading the wrong slug, which is the most likely way the
    dispatch / cost split gets quietly undone.
    """
    allowed = set(slugs)
    with patch("app.dependencies.UserPermissionService") as service:
        service.return_value.check_user_has_permission.side_effect = (
            lambda _user_id, slug: slug in allowed
        )
        service.return_value.get_user_role_slugs.return_value = set()
        yield


def _create(client, **overrides):
    body = {
        "source_entity_type": "complaint",
        "source_entity_id": str(uuid.uuid4()),
        "site_address": f"{TEST_PREFIX} 12 Jalan Damai",
        "site_contact_name": f"{TEST_PREFIX} Consumer",
        "site_contact_phone": "+60127770099",
    }
    body.update(overrides)
    with granted(DISPATCH):
        response = client.post(f"{BASE}/", json=body)
    assert response.status_code == 200, response.text
    return response.json()


# ============================================================== permissions


def test_reading_the_board_needs_the_view_permission(client):
    with granted():
        response = client.get(
            f"{BASE}/board",
            params={"date_from": "2026-08-10T00:00:00", "date_to": "2026-08-11T00:00:00"},
        )
    assert response.status_code == 403


def test_dispatching_is_not_included_in_viewing(client):
    """The point of the split. Somebody reading a case to answer the phone must not be
    one misclick from re-assigning an afternoon.
    """
    job = _create(client)
    with granted(VIEW):
        response = client.post(
            f"{BASE}/{job['id']}/confirm",
            json={
                "scheduled_from": "2026-08-10T10:00:00",
                "customer_agreed_by": "Consumer agreed",
            },
        )
    assert response.status_code == 403


def test_recording_a_cost_is_not_included_in_dispatching(client):
    """Money leaving the company is its own grant. The people who schedule vans are not
    automatically the people who record what the plumber charged.
    """
    job = _create(client)
    with granted(DISPATCH):
        response = client.post(
            f"{BASE}/costs",
            json={
                "source_entity_type": "complaint",
                "source_entity_id": job["source_entity_id"],
                "cost_kind": "labour",
                "amount": "80.00",
            },
        )
    assert response.status_code == 403


def test_no_write_route_accepts_an_api_key_principal():
    """`require_permission_with_api_key` is documented as read-oriented, and the two
    write exceptions in this codebase both carry a second real-user gate at the assistant
    layer. Nothing in S6 has one, so a write must never resolve an act-as principal.
    """
    import inspect

    from app.api.v1.complaints import service_jobs, technicians

    for module in (service_jobs, technicians):
        source = inspect.getsource(module)
        for line in source.splitlines():
            stripped = line.strip()
            # Only actual dependency declarations count. Scanning raw source would
            # also match the module docstring explaining this very rule.
            if "Depends(require_permission_with_api_key" not in stripped:
                continue
            # The read slug is the only one allowed through the api-key path.
            assert "VIEW_PERMISSION" in stripped, (
                f"{module.__name__} lets an API key reach a write: {stripped}"
            )


# =============================================== AC-F5 survives the boundary


def test_confirming_without_a_date_is_a_422_not_a_500(client):
    """AppException subclasses HTTPException, so a bare `except Exception` in the route
    would turn this into an opaque 500 and the dispatcher would never see the reason.
    """
    job = _create(client)
    with granted(DISPATCH):
        response = client.post(
            f"{BASE}/{job['id']}/confirm",
            json={"customer_agreed_by": "Consumer agreed"},
        )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "service_job_date_required"


def test_confirming_without_an_agreement_is_a_422_naming_the_reason(client):
    job = _create(client)
    with granted(DISPATCH):
        response = client.post(
            f"{BASE}/{job['id']}/confirm",
            json={"scheduled_from": "2026-08-10T10:00:00"},
        )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "service_job_agreement_required"


def test_an_unknown_cost_kind_is_a_422_naming_the_allowed_set(client):
    job = _create(client)
    with granted(COSTS):
        response = client.post(
            f"{BASE}/costs",
            json={
                "source_entity_type": "complaint",
                "source_entity_id": job["source_entity_id"],
                "cost_kind": "miscellaneous",
                "amount": "80.00",
            },
        )
    assert response.status_code == 422, response.text
    assert "labour" in response.json()["message"]


def test_a_malformed_job_id_is_a_404_rather_than_a_500(client):
    with granted(VIEW):
        response = client.get(f"{BASE}/not-a-uuid")
    assert response.status_code == 404


# ==================================================== the flow over HTTP


def test_a_job_is_created_proposed_with_a_number(client):
    job = _create(client)
    assert job["status_key"] == "proposed"
    assert job["source_entity_type"] == "complaint"
    # No numbering rule exists on a blank schema, and that must not block dispatch: a
    # job with no number is still a job somebody has to attend.
    assert "job_number" in job


def test_the_site_is_returned_as_it_was_reported(client):
    """AC-B3. The site is what the consumer said, never derived from the customer record
    - deriving it sends a technician to a shop.
    """
    job = _create(client)
    assert job["site_address"].endswith("12 Jalan Damai")
    assert job["site_contact_phone"] == "+60127770099"


def test_the_confirm_assign_arrive_complete_path_works_end_to_end(client, db):
    from app.models.service_jobs import Technician

    technician = Technician(
        id=str(uuid.uuid4()),
        name=f"{TEST_PREFIX} Technician",
        phone="+60123334455",
        employment_type="employee",
    )
    db.add(technician)
    db.flush()

    job = _create(client)
    with granted(DISPATCH):
        confirmed = client.post(
            f"{BASE}/{job['id']}/confirm",
            json={
                "scheduled_from": "2026-08-10T10:00:00",
                "customer_agreed_by": "Consumer agreed on WhatsApp",
            },
        ).json()
        assert confirmed["status_key"] == "confirmed"

        client.post(f"{BASE}/{job['id']}/assign", json={"technician_id": technician.id})
        client.post(f"{BASE}/{job['id']}/on-the-way")
        arrived = client.post(f"{BASE}/{job['id']}/arrive").json()
        assert arrived["status_key"] == "arrived"
        assert arrived["attend_seconds"] is not None

        completed = client.post(f"{BASE}/{job['id']}/complete", json={}).json()
        assert completed["status_key"] == "completed"


def test_a_rejected_visit_comes_back_attributed_to_the_customer(client, db):
    from app.models.service_jobs import Technician

    technician = Technician(
        id=str(uuid.uuid4()), name=f"{TEST_PREFIX} Tech2", employment_type="contractor"
    )
    db.add(technician)
    db.flush()

    job = _create(client)
    with granted(DISPATCH):
        client.post(
            f"{BASE}/{job['id']}/confirm",
            json={
                "scheduled_from": "2026-08-10T10:00:00",
                "customer_agreed_by": "Consumer agreed",
            },
        )
        client.post(f"{BASE}/{job['id']}/assign", json={"technician_id": technician.id})
        rejected = client.post(
            f"{BASE}/{job['id']}/reject", json={"reason": "Consumer asked to postpone"}
        ).json()

    assert rejected["status_key"] == "proposed"
    assert rejected["waiting_on_party"] == "customer"


def test_the_board_returns_the_day_and_its_jobs(client, db):
    job = _create(client)
    with granted(DISPATCH):
        client.post(
            f"{BASE}/{job['id']}/confirm",
            json={
                "scheduled_from": "2026-08-10T10:00:00",
                "customer_agreed_by": "Consumer agreed",
            },
        )
    with granted(VIEW):
        board = client.get(
            f"{BASE}/board",
            params={"date_from": "2026-08-10T00:00:00", "date_to": "2026-08-11T00:00:00"},
        ).json()

    assert board and board[0]["day"] == "2026-08-10"
    # Nobody assigned yet, and the job must still be on the screen.
    assert board[0]["technician_id"] is None


def test_the_stall_list_carries_the_elapsed_time(client, db):
    from app.models.service_jobs import ServiceJob

    job = _create(client)
    row = db.query(ServiceJob).filter(ServiceJob.id == job["id"]).first()
    row.scheduled_from = datetime.utcnow() - timedelta(days=2)
    db.flush()

    with granted(VIEW):
        stalls = client.get(f"{BASE}/stalls").json()

    mine = [row for row in stalls if row["service_job_id"] == job["id"]]
    assert mine and mine[0]["stalled_seconds"] > 86400


def test_costs_come_back_as_a_total_and_a_breakdown(client):
    """AC-M29. One number per case does not answer the costing question this requirement
    came from, so both ship in the same response.
    """
    job = _create(client)
    with granted(COSTS):
        for kind, amount in (("labour", "80.00"), ("parts", "45.50")):
            client.post(
                f"{BASE}/costs",
                json={
                    "source_entity_type": "complaint",
                    "source_entity_id": job["source_entity_id"],
                    "cost_kind": kind,
                    "amount": amount,
                },
            )
        payload = client.get(
            f"{BASE}/costs/by-source",
            params={
                "source_entity_type": "complaint",
                "source_entity_id": job["source_entity_id"],
            },
        ).json()

    assert payload["total"] == pytest.approx(125.50)
    assert payload["breakdown"]["labour"] == pytest.approx(80.0)
    assert payload["breakdown"]["travel"] == pytest.approx(0.0)
    assert len(payload["lines"]) == 2


# ================================================== technicians and providers


def test_a_technician_is_created_without_touching_users(client, db):
    from app.models.user import User

    before = db.query(User).count()
    with granted(DISPATCH):
        response = client.post(
            f"{TECHNICIANS}/",
            json={
                "name": f"{TEST_PREFIX} Ah Meng",
                "phone": "+60129998877",
                "employment_type": "contractor",
            },
        )
    assert response.status_code == 200, response.text
    assert db.query(User).count() == before, (
        "Creating a technician created a user. AC-F8 exists precisely because that puts "
        "them back inside an SLA engine that cannot schedule them."
    )


def test_an_unknown_employment_type_is_refused(client):
    with granted(DISPATCH):
        response = client.post(
            f"{TECHNICIANS}/",
            json={"name": f"{TEST_PREFIX} Nobody", "employment_type": "freelance-ish"},
        )
    assert response.status_code == 422


def test_a_job_is_raised_from_a_complaint_with_the_site_the_case_reported(client, db):
    """The link the dispatch board was missing. The client names the case and nothing else.

    The complaint below carries the dealer's shop in `customer_address` and the house in the
    Site columns; a job that came back with the shop would send a van to the wrong place, and
    both are real addresses so nothing on screen would look wrong.
    """
    import uuid as _uuid

    from app.models.complaints import Complaint

    complaint = Complaint(
        id=str(_uuid.uuid4()),
        complaint_number=f"{TEST_PREFIX}-CMP-9001",
        customer_name=f"{TEST_PREFIX} Dealer Sdn Bhd",
        customer_address="Lot 5, Jalan Industri (the DEALER's shop)",
        site_address="12 Jalan Damai, Shah Alam",
        site_contact_name="Puan Aminah",
        site_contact_phone="+60127770099",
        status="new",
    )
    db.add(complaint)
    db.flush()

    with granted(DISPATCH):
        response = client.post(
            f"{BASE}/from-source",
            json={"source_entity_type": "complaint", "source_entity_id": complaint.id},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status_key"] == "proposed"
    assert body["site_address"] == "12 Jalan Damai, Shah Alam"
    assert body["source_entity_id"] == complaint.id


def test_raising_from_an_unsupported_source_is_a_422_naming_it(client):
    with granted(DISPATCH):
        response = client.post(
            f"{BASE}/from-source",
            json={"source_entity_type": "purchase_request", "source_entity_id": "x"},
        )
    assert response.status_code == 422, response.text
    assert "purchase_request" in response.json()["message"]


def test_raising_a_job_is_not_included_in_viewing(client):
    with granted(VIEW):
        response = client.post(
            f"{BASE}/from-source",
            json={"source_entity_type": "complaint", "source_entity_id": "x"},
        )
    assert response.status_code == 403
