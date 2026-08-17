"""S10: one atomic write for a whole version's line set.

The editor used to write per row, so a ten-line scope was ten requests and a half-failed
sequence left a quotation in a state nobody typed. These tests pin the property that makes
the new endpoint worth having: either the whole desired set lands, or none of it does.

Route-level rather than service-level, because the transaction boundary being asserted IS
the route's (`db.commit()` on the way out, `db.rollback()` on any refusal). A service test
would leave the interesting half untested.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-qbulk"
BASE = "/api/v1/project-sales"
EDIT = "projects.projects.edit"

ALL_SLUGS = [
    "projects.projects.view",
    "projects.projects.create",
    "projects.projects.edit",
    "projects.projects.delete",
    "projects.projects.manage",
    "projects.types.view",
    "projects.types.edit",
]


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _uom(db) -> str:
    row = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Piece")
    db.add(row)
    db.flush()
    return row.id


def _category(db, name: str) -> ProductCategory:
    row = ProductCategory(
        id=_uid(),
        category_code=f"ZZT-{_uid()[:8]}",
        category_name=f"{MARKER} {name}",
    )
    db.add(row)
    db.flush()
    return row


def _product(db, category_id: str, uom_id: str, list_price: str) -> Product:
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} Basin",
        description="Wall-hung basin",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=Decimal(list_price),
    )
    db.add(row)
    db.flush()
    return row


def _client(db, user_id: str):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "superadmin"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(ALL_SLUGS)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


class _without_permission:
    """Run the block as a user holding every project permission EXCEPT ``slug``."""

    def __init__(self, slug: str) -> None:
        self.slug = slug

    def __enter__(self):
        from app.services.user_service import UserPermissionService

        self._originals = (
            UserPermissionService.check_user_has_permission,
            UserPermissionService.get_user_permission_slugs,
        )
        granted = [s for s in ALL_SLUGS if s != self.slug]
        UserPermissionService.check_user_has_permission = (
            lambda self_, uid, wanted, _denied=self.slug: wanted != _denied
        )
        UserPermissionService.get_user_permission_slugs = lambda self_, uid: list(granted)
        return self

    def __exit__(self, *exc):
        from app.services.user_service import UserPermissionService

        UserPermissionService.check_user_has_permission = self._originals[0]
        UserPermissionService.get_user_permission_slugs = self._originals[1]
        return False


@pytest.fixture()
def api():
    from app.models.base import company_scope
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user_id = _user(db, f"{MARKER} Ali")
        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=user_id,
            developer_party_id=None,
            title=f"{MARKER} Tower",
        )
        db.commit()
        client, originals = _client(db, user_id)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, user_id, project
        finally:
            _restore(originals)


def _quotation(client, project_id: str, **body) -> dict:
    payload = {"scope_label": f"{MARKER} House Units", **body}
    response = client.post(f"{BASE}/projects/{project_id}/quotations", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _bulk(client, version_id: str, lines: list) -> "object":
    return client.put(
        f"{BASE}/quotation-versions/{version_id}/lines", json={"lines": lines}
    )


def _stored(client, version_id: str) -> list:
    response = client.get(f"{BASE}/quotation-versions/{version_id}/lines")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _off_catalog(description: str, price: str, quantity: str = "1", **extra) -> dict:
    return {
        "description_snapshot": f"{MARKER} {description}",
        "unit_price": price,
        "quantity": quantity,
        **extra,
    }


# ------------------------------------------------------------------ the diff


def test_one_call_inserts_updates_and_deletes_the_whole_set(api):
    """The reason the endpoint exists: a Save is one request, not one per row."""
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]

    seeded = _bulk(
        client,
        version_id,
        [_off_catalog("Basin", "100.00"), _off_catalog("Tap", "200.00")],
    )
    assert seeded.status_code == 200, seeded.text
    basin, tap = seeded.json()["data"]

    # Keep the basin at a new price, drop the tap entirely, add a mirror.
    saved = _bulk(
        client,
        version_id,
        [
            {"id": basin["id"], "unit_price": "150.00", "quantity": "2"},
            _off_catalog("Mirror", "300.00"),
        ],
    )
    assert saved.status_code == 200, saved.text
    rows = saved.json()["data"]

    assert [row["description"] for row in rows] == [
        f"{MARKER} Basin",
        f"{MARKER} Mirror",
    ]
    assert rows[0]["id"] == basin["id"], "an update must keep the row it updated"
    assert rows[0]["line_total"] == "300.00"
    assert tap["id"] not in {row["id"] for row in rows}

    # The envelope the GET already answers with, so the client reads one shape.
    body = saved.json()
    assert body["empty"] is False
    assert body["pagination"]["total"] == 2
    assert _stored(client, version_id) == rows


def test_a_line_left_out_of_the_body_is_deleted(api):
    """The whole-set contract, stated on its own because it is the sharp edge: a client
    that sends only the rows it touched wipes the rest."""
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]

    _bulk(
        client,
        version_id,
        [_off_catalog("Basin", "100.00"), _off_catalog("Tap", "200.00")],
    )
    kept = _stored(client, version_id)[0]

    saved = _bulk(client, version_id, [{"id": kept["id"]}])
    assert saved.status_code == 200, saved.text
    assert [row["id"] for row in saved.json()["data"]] == [kept["id"]]
    assert len(_stored(client, version_id)) == 1


def test_an_empty_set_clears_the_version(api):
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]
    _bulk(client, version_id, [_off_catalog("Basin", "100.00")])

    cleared = _bulk(client, version_id, [])
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"] == []
    assert cleared.json()["empty"] is True
    assert _stored(client, version_id) == []

    listed = client.get(f"{BASE}/projects/{project.id}/quotations").json()["data"]
    assert listed[0]["current_total"] == "0.00"


# ----------------------------------------------------------------- ordering


def test_the_order_of_the_array_is_the_order_of_the_lines(api):
    """Reordering is sending a different order, so the client never computes sort_order."""
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]

    saved = _bulk(
        client,
        version_id,
        [
            _off_catalog("Basin", "100.00"),
            _off_catalog("Tap", "200.00"),
            _off_catalog("Mirror", "300.00"),
        ],
    )
    assert saved.status_code == 200, saved.text
    rows = saved.json()["data"]
    assert [row["sort_order"] for row in rows] == [0, 1, 2]

    reordered = _bulk(
        client,
        version_id,
        [{"id": rows[2]["id"]}, {"id": rows[0]["id"]}, {"id": rows[1]["id"]}],
    )
    assert reordered.status_code == 200, reordered.text
    assert [row["description"] for row in reordered.json()["data"]] == [
        f"{MARKER} Mirror",
        f"{MARKER} Basin",
        f"{MARKER} Tap",
    ]
    assert [row["sort_order"] for row in _stored(client, version_id)] == [0, 1, 2]
    assert [row["description"] for row in _stored(client, version_id)] == [
        f"{MARKER} Mirror",
        f"{MARKER} Basin",
        f"{MARKER} Tap",
    ]


def test_a_sort_order_sent_by_the_client_does_not_override_the_position(api):
    """Position is the single source of order, so a stale sort_order in the payload
    cannot make the saved list disagree with the list the user arranged."""
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]

    saved = _bulk(
        client,
        version_id,
        [
            _off_catalog("Basin", "100.00", sort_order=99),
            _off_catalog("Tap", "200.00", sort_order=5),
        ],
    )
    assert saved.status_code == 200, saved.text
    assert [row["sort_order"] for row in saved.json()["data"]] == [0, 1]


# -------------------------------------------------------------------- total


def test_the_total_is_recomputed_once_and_excludes_rate_only_lines(api, monkeypatch):
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]

    from app.services import project_quotation_service as service

    original = service._recalculate_total
    calls: list = []

    def spy(db, version):
        calls.append(version.id)
        return original(db, version)

    monkeypatch.setattr(service, "_recalculate_total", spy)

    saved = _bulk(
        client,
        version_id,
        [
            _off_catalog("Basin", "100.00", quantity="2"),
            _off_catalog("Tap", "200.00"),
            _off_catalog("Spare valve", "500.00", is_rate_only=True),
        ],
    )
    assert saved.status_code == 200, saved.text

    assert calls == [version_id], "one write, one total"

    listed = client.get(f"{BASE}/projects/{project.id}/quotations").json()["data"]
    # 200 + 200, with the rate-only alternate printed but counted as nothing.
    assert listed[0]["current_total"] == "400.00"


# ------------------------------------------------------------------ refusals


def test_a_frozen_version_is_refused_and_nothing_is_applied(api):
    """The freeze is the whole point of the version model, so the new endpoint has to
    honour it too - and honour it BEFORE writing anything."""
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    frozen_version = quotation["current_version_id"]
    _bulk(client, frozen_version, [_off_catalog("Basin", "100.00")])
    before = _stored(client, frozen_version)

    revised = client.post(f"{BASE}/quotations/{quotation['id']}/revise")
    assert revised.status_code == 201, revised.text

    refused = _bulk(
        client,
        frozen_version,
        [
            {"id": before[0]["id"], "unit_price": "1.00"},
            _off_catalog("Sneaked in", "999.00"),
        ],
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "quotation_version_frozen"

    assert _stored(client, frozen_version) == before


def test_an_issued_version_is_refused_with_the_issued_code(api):
    """The code the editor branches on to offer a revision.

    The issue rows are written directly rather than through ``qdocs.issue``: a real issue
    needs a signatory signature and a numbering rule, none of which this assertion is about.
    What freezes the version is the issue SCOPE pointing at it, and that is what is seeded.
    """
    client, db, company_id, user_id, project = api
    from datetime import datetime

    from app.models.projects import (
        ProjectQuotation,
        ProjectQuotationIssue,
        ProjectQuotationIssueScope,
    )

    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]
    _bulk(client, version_id, [_off_catalog("Basin", "100.00")])
    before = _stored(client, version_id)

    row = db.query(ProjectQuotation).filter(ProjectQuotation.id == quotation["id"]).first()
    issue = ProjectQuotationIssue(
        company_id=company_id,
        document_id=row.document_id,
        issue_no=1,
        our_ref_text=f"{MARKER}/R1",
        issued_at=datetime.utcnow(),
        issued_by=user_id,
        grand_total=Decimal("100.00"),
    )
    db.add(issue)
    db.flush()
    db.add(
        ProjectQuotationIssueScope(
            company_id=company_id,
            issue_id=issue.id,
            quotation_id=row.id,
            version_id=version_id,
            scope_total=Decimal("100.00"),
        )
    )
    db.commit()

    refused = _bulk(client, version_id, [_off_catalog("Sneaked in", "999.00")])
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "quotation_version_issued"
    assert _stored(client, version_id) == before


def test_a_malformed_line_rejects_every_other_line_in_the_batch(api):
    """Atomicity is the property most worth pinning: a batch that half-lands is exactly
    the failure the per-row editor had."""
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]
    _bulk(client, version_id, [_off_catalog("Basin", "100.00")])
    before = _stored(client, version_id)

    refused = _bulk(
        client,
        version_id,
        [
            {"id": before[0]["id"], "unit_price": "111.00"},
            _off_catalog("Tap", "200.00"),
            # Off-catalog with no description: valid to Pydantic, refused by the service
            # AFTER the two good lines above have already been flushed.
            {"unit_price": "300.00", "quantity": "1"},
        ],
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "quotation_line_description_required"

    assert _stored(client, version_id) == before, "a refused batch writes nothing at all"


def test_a_line_id_from_another_version_is_refused(api):
    """An id the caller did not get from this version is a client bug, and silently
    treating it as a new line would duplicate the row it meant to move."""
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]
    other = _quotation(client, project.id, scope_label=f"{MARKER} Common Area")
    other_version = other["current_version_id"]
    _bulk(client, other_version, [_off_catalog("Basin", "100.00")])
    stranger = _stored(client, other_version)[0]

    refused = _bulk(client, version_id, [{"id": stranger["id"], "unit_price": "1.00"}])
    assert refused.status_code == 404, refused.text
    assert refused.json()["code"] == "quotation_line_not_found"
    assert _stored(client, other_version)[0] == stranger


def test_the_same_line_twice_is_refused(api):
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]
    _bulk(client, version_id, [_off_catalog("Basin", "100.00")])
    line = _stored(client, version_id)[0]

    refused = _bulk(
        client, version_id, [{"id": line["id"]}, {"id": line["id"], "unit_price": "9.00"}]
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "quotation_line_duplicate"
    assert _stored(client, version_id) == [line]


def test_a_reader_who_may_not_edit_the_project_cannot_save_its_lines(api):
    """The bulk route is a write, so it needs the same grant every other line write does."""
    client, _db, _company_id, _user_id, project = api
    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]
    _bulk(client, version_id, [_off_catalog("Basin", "100.00")])
    before = _stored(client, version_id)

    with _without_permission(EDIT):
        denied = _bulk(client, version_id, [_off_catalog("Sneaked in", "999.00")])

    assert denied.status_code == 403, denied.text
    assert _stored(client, version_id) == before


def test_an_unknown_version_is_a_404_not_a_silent_no_op(api):
    client, _db, _company_id, _user_id, _project = api
    missing = _bulk(client, _uid(), [_off_catalog("Basin", "100.00")])
    assert missing.status_code == 404, missing.text


# -------------------------------------------------------------- catalogue lines


def test_a_product_line_is_snapshotted_and_guarded_exactly_as_the_per_row_route(api):
    """Same service path, so the snapshot and both alerts cannot drift between the two
    ways of saving a line."""
    client, db, _company_id, _user_id, project = api
    uom = _uom(db)
    category = _category(db, "Basins")
    product = _product(db, category.id, uom, "1000.00")
    floor = client.post(
        f"{BASE}/config/price-floors",
        json={"mode": "percent", "value": "90", "category_id": category.id},
    )
    assert floor.status_code == 201, floor.text
    db.commit()

    quotation = _quotation(client, project.id)
    version_id = quotation["current_version_id"]

    saved = _bulk(
        client,
        version_id,
        [{"product_id": product.id, "unit_price": "800.00", "quantity": "1"}],
    )
    assert saved.status_code == 200, saved.text
    row = saved.json()["data"][0]
    assert row["product_code"] == product.product_code
    assert row["list_price"] == "1000.00"
    assert row["is_below_floor"] is True
    assert row["floor_value_applied"] == "900.00"
    # NOT non-standard: this project nominated no series, and a project with no allowlist has
    # nothing to breach (project_pricing_service.is_in_series). Asserted rather than skipped
    # because the alert firing here would put an off-catalog warning on every line of every
    # project that never picked a series.
    assert row["is_non_standard"] is False

    # The claim in this test's name, actually checked: the same input through the per-row route
    # lands on the same flags. Two write paths that compute an alert differently is how a line
    # changes meaning depending on which button saved it.
    second = _quotation(client, project.id, scope_label=f"{MARKER} Per row")
    per_row = client.post(
        f"{BASE}/quotation-versions/{second['current_version_id']}/lines",
        json={"product_id": product.id, "unit_price": "800.00", "quantity": "1"},
    )
    assert per_row.status_code == 201, per_row.text
    single = per_row.json()
    for field in ("list_price", "floor_value_applied", "is_below_floor", "is_non_standard"):
        assert single[field] == row[field], field
