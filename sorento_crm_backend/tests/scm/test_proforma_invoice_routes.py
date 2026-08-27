"""AC-P4 - the proforma-invoice upload channel: preview/apply/list/detail/delete + RBAC.

TEST-FIRST: `app/api/v1/scm/proforma_invoices.py` does not exist yet at the time this file
is written, so every test is expected to be red (404 - the route is not mounted) until it
lands, then green against the exact contract in AC-P4.1 / AC-P4.2 / AC-P4.3 / AC-P4.4.

Permissions are granted through a role this suite creates and owns, never a borrowed one -
CI's database carries no role->permission grants until migration 375's sweep has actually
run, and even then "whatever roles hold scm.reorder.run" is an assertion about the
environment this suite must not depend on (see test_coverage_routes.py, same pattern).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.procurement import Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import (
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from tests._pg_fixture import unique_code
from tests.scm.conftest import requires_pg
from tests.scm.fixtures.proforma_shapes import kailu_proforma_workbook
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

URL = "/api/v1/scm/proforma-invoices"
UPLOAD_PERMISSION = "scm.proforma_invoice.upload"
VIEW_PERMISSION = "scm.dashboard.view"

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MARKER = "ZZPIR"


def _u() -> str:
    return str(uuid.uuid4())


def _grant(db, uid: str, slug: str) -> None:
    """Give `uid` `slug` through a role this test owns (get-or-create the permission row)."""
    role = UserRole(id=_u(), slug=unique_code("scmrole"), name=unique_code("SCM role"))
    db.add(role)
    db.flush()

    perm = db.query(UserPermission).filter(UserPermission.slug == slug).one_or_none()
    if perm is None:
        perm = UserPermission(id=_u(), slug=slug, name=slug)
        db.add(perm)
        db.flush()

    db.add(UserRolePermission(id=_u(), role_id=role.id, permission_id=perm.id))
    db.add(UserRoleAssignment(id=_u(), user_id=uid, role_id=role.id))
    db.flush()


def _seed_packing_list_numbering(db) -> None:
    """The `inbound_shipment_draft` series for THIS suite's own company.

    `as_company_user` creates the company from nothing, and migration 440 seeded the rule
    only for the companies that existed when it ran - so a convert here would have no
    series to draw from and be refused (R16, `numbering_rule_missing`).
    """
    from app.models.numbering import DocumentNumberingRule
    from app.services.company_scope import get_company_scope

    company_id = next(iter(get_company_scope(db) or []), None)
    db.add(
        DocumentNumberingRule(
            id=_u(),
            company_id=company_id,
            doc_type="inbound_shipment_draft",
            enabled=True,
            prefix_template="PL-{yy}{month:02d}-",
            number_digits=3,
            next_value=1,
            start_value=1,
            reset_policy="monthly",
        )
    )
    db.flush()


def _client(scm_app, *, upload: bool = False, view: bool = False) -> tuple:
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    _seed_packing_list_numbering(db)
    uid = app.dependency_overrides[gcu]()["id"]
    if upload:
        _grant(db, uid, UPLOAD_PERMISSION)
    if view:
        _grant(db, uid, VIEW_PERMISSION)
    return TestClient(app), db


def _seed_supplier_and_product(db):
    tag = uuid.uuid4().hex[:8].upper()
    cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}-CAT-{tag}", category_name=f"{MARKER} category"
    )
    uom = UnitOfMeasure(id=_u(), uom_code=f"{MARKER}-U-{tag}"[:20], uom_name="pcs")
    db.add_all([cat, uom])
    db.flush()
    supplier = Supplier(
        id=_u(), supplier_code=f"{MARKER}-S-{tag}", supplier_name=f"{MARKER} supplier",
        is_active=True,
    )
    product = Product(
        id=_u(), product_code=f"{MARKER}-A-{tag}", product_name="A",
        category_id=cat.id, base_uom_id=uom.id, list_price=0, is_active=True,
        is_discontinued=False,
    )
    db.add_all([supplier, product])
    db.flush()
    return supplier, product


def _upload(data: bytes, name: str = "kailu.xlsx"):
    return {"file": (name, data, _XLSX)}


# --------------------------------------------------------------------------- #
# AC-P4.3 - RBAC
# --------------------------------------------------------------------------- #


def test_preview_without_the_upload_permission_is_403(scm_app):
    client, db = _client(scm_app, upload=False, view=False)
    supplier, _ = _seed_supplier_and_product(db)

    r = client.post(
        f"{URL}/preview",
        files=_upload(kailu_proforma_workbook()),
        data={"supplier_id": str(supplier.id)},
    )

    assert r.status_code == 403, r.text


def test_apply_without_the_upload_permission_is_403(scm_app):
    client, db = _client(scm_app, upload=False, view=False)
    supplier, _ = _seed_supplier_and_product(db)

    r = client.post(
        f"{URL}/apply",
        files=_upload(kailu_proforma_workbook()),
        data={"supplier_id": str(supplier.id)},
    )

    assert r.status_code == 403, r.text


def test_list_without_the_view_permission_is_403(scm_app):
    client, db = _client(scm_app, upload=False, view=False)

    r = client.get(URL)

    assert r.status_code == 403, r.text


def test_delete_without_the_upload_permission_is_403(scm_app):
    client, db = _client(scm_app, upload=False, view=False)

    r = client.delete(f"{URL}/{uuid.uuid4()}")

    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# AC-P4.1 - preview / apply happy path
# --------------------------------------------------------------------------- #


def test_preview_returns_a_summary_and_writes_nothing(scm_app):
    client, db = _client(scm_app, upload=True)
    supplier, product = _seed_supplier_and_product(db)
    data = kailu_proforma_workbook({"SRTWT7443": product.product_code})

    r = client.post(
        f"{URL}/preview",
        files=_upload(data),
        data={"supplier_id": str(supplier.id)},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert "summary" in body or "documents" in body

    # Not granted the view permission in this test - the read side is gated separately.
    listed = client.get(URL, params={"supplier_id": str(supplier.id)})
    assert listed.status_code == 403


def test_apply_with_validate_only_returns_the_standard_verdict_and_writes_nothing(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    supplier, product = _seed_supplier_and_product(db)
    data = kailu_proforma_workbook({"SRTWT7443": product.product_code})

    r = client.post(
        f"{URL}/apply?validate_only=true",
        files=_upload(data),
        data={"supplier_id": str(supplier.id)},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) >= {"valid", "errors", "warnings", "summary"}
    assert body["valid"] is True

    listed = client.get(URL, params={"supplier_id": str(supplier.id)}).json()
    assert listed["data"] == []


def test_apply_writes_and_the_document_is_then_listed_and_fetchable(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    supplier, product = _seed_supplier_and_product(db)
    data = kailu_proforma_workbook({"SRTWT7443": product.product_code})

    r = client.post(
        f"{URL}/apply",
        files=_upload(data),
        data={"supplier_id": str(supplier.id)},
    )
    assert r.status_code == 200, r.text

    listed = client.get(URL, params={"supplier_id": str(supplier.id)})
    assert listed.status_code == 200, listed.text
    rows = listed.json()["data"]
    assert len(rows) == 1
    assert rows[0]["pi_number"] == "KL20260717"
    # AC-P4.4: a human-readable supplier identifier, not just a raw id.
    assert rows[0].get("supplier_code") == supplier.supplier_code

    detail = client.get(f"{URL}/{rows[0]['id']}")
    assert detail.status_code == 200, detail.text
    d = detail.json()
    assert d["pi_number"] == "KL20260717"
    assert len(d["lines"]) == 19
    # AC-P4.4: no raw uuid as the only identifier - the matched line names the product
    # by its code, not `product_id`.
    matched = [ln for ln in d["lines"] if ln.get("product_code") == product.product_code]
    assert matched, "the mapped line should carry the matched product's code"
    assert matched[0].get("matched") is True


def test_delete_hard_deletes_header_and_lines(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    supplier, product = _seed_supplier_and_product(db)
    data = kailu_proforma_workbook({"SRTWT7443": product.product_code})

    client.post(f"{URL}/apply", files=_upload(data), data={"supplier_id": str(supplier.id)})
    rows = client.get(URL, params={"supplier_id": str(supplier.id)}).json()["data"]
    inv_id = rows[0]["id"]

    r = client.delete(f"{URL}/{inv_id}")
    assert r.status_code in (200, 204), r.text

    after = client.get(URL, params={"supplier_id": str(supplier.id)}).json()["data"]
    assert after == []

    gone = client.get(f"{URL}/{inv_id}")
    assert gone.status_code == 404


# --------------------------------------------------------------------------- #
# Form and query validation - a bad value is a 422, never a 500
# --------------------------------------------------------------------------- #


def test_an_unknown_supplier_is_a_422_naming_the_field(scm_app):
    client, db = _client(scm_app, upload=True)

    r = client.post(
        f"{URL}/apply",
        files=_upload(kailu_proforma_workbook()),
        data={"supplier_id": str(uuid.uuid4())},
    )

    assert r.status_code == 422, r.text


def test_a_supplier_id_that_is_not_an_id_is_a_422_not_a_500(scm_app):
    client, db = _client(scm_app, upload=True)

    r = client.post(
        f"{URL}/preview",
        files=_upload(kailu_proforma_workbook()),
        data={"supplier_id": "the one from last week"},
    )

    assert r.status_code == 422, r.text


def test_a_currency_nobody_recognises_is_a_422_naming_the_value(scm_app):
    client, db = _client(scm_app, upload=True)
    supplier, product = _seed_supplier_and_product(db)

    r = client.post(
        f"{URL}/apply",
        files=_upload(kailu_proforma_workbook({"SRTWT7443": product.product_code})),
        data={"supplier_id": str(supplier.id), "currency": "dollars"},
    )

    assert r.status_code == 422, r.text
    assert "dollars" in r.text


def test_listing_with_a_supplier_id_that_is_not_an_id_is_a_422(scm_app):
    client, db = _client(scm_app, view=True)

    r = client.get(URL, params={"supplier_id": "not-an-id"})

    assert r.status_code == 422, r.text


def test_fetching_an_invoice_id_that_is_not_an_id_is_a_404(scm_app):
    client, db = _client(scm_app, view=True)

    r = client.get(f"{URL}/not-an-id")

    assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
# F5 - adjusting the invoice to fit the container (AC-E1, AC-E2, AC-D4, AC-E4)
# --------------------------------------------------------------------------- #


def _applied_invoice(client, db) -> tuple[dict, str]:
    """One Kailu invoice on file, and the id of its first line."""
    supplier, product = _seed_supplier_and_product(db)
    client.post(
        f"{URL}/apply",
        files=_upload(kailu_proforma_workbook({"SRTWT7443": product.product_code})),
        data={"supplier_id": str(supplier.id)},
    )
    listed = client.get(URL, params={"supplier_id": str(supplier.id)}).json()
    invoice_id = listed["data"][0]["id"]
    detail = client.get(f"{URL}/{invoice_id}").json()
    return detail, detail["lines"][0]["id"]


def test_adjusting_a_line_without_the_upload_permission_is_403(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    detail, line_id = _applied_invoice(client, db)
    # Same app, a principal that holds only the read side: drop the upload override.
    reader, _ = _client(scm_app, upload=False, view=True)

    r = reader.patch(f"{URL}/{detail['id']}/lines/{line_id}", json={"qty": 5})

    assert r.status_code == 403, r.text


def test_adjusting_a_line_returns_the_whole_invoice_with_the_supplier_figure_kept(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    detail, line_id = _applied_invoice(client, db)
    before = detail["lines"][0]["qty"]

    r = client.patch(f"{URL}/{detail['id']}/lines/{line_id}", json={"qty": before - 1})

    assert r.status_code == 200, r.text
    body = r.json()
    line = next(ln for ln in body["lines"] if ln["id"] == line_id)
    assert line["qty"] == before - 1
    assert line["supplier_qty"] == before
    assert body["is_adjusted"] is True
    assert body["adjusted_by"]


def test_a_negative_quantity_is_refused_by_the_route_as_a_422(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    detail, line_id = _applied_invoice(client, db)

    r = client.patch(f"{URL}/{detail['id']}/lines/{line_id}", json={"qty": -1})

    assert r.status_code == 422, r.text


def test_removing_a_line_drops_it_from_the_returned_invoice(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    detail, line_id = _applied_invoice(client, db)
    before = detail["line_count"]

    r = client.delete(f"{URL}/{detail['id']}/lines/{line_id}")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["line_count"] == before - 1
    assert all(ln["id"] != line_id for ln in body["lines"])


def test_the_container_size_is_settable_and_clearable_on_the_route(scm_app):
    from app.models.scm import ContainerSize

    client, db = _client(scm_app, upload=True, view=True)
    detail, _ = _applied_invoice(client, db)
    size = ContainerSize(
        id=_u(), code=unique_code("BOX")[:30], label="test box", cbm=30, is_active=True
    )
    db.add(size)
    db.flush()

    r = client.patch(f"{URL}/{detail['id']}", json={"container_size_id": str(size.id)})
    assert r.status_code == 200, r.text
    assert r.json()["container_cbm"] == 30

    cleared = client.patch(f"{URL}/{detail['id']}", json={"container_size_id": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["container_size_id"] != str(size.id)


def test_the_export_route_returns_a_workbook_named_after_the_invoice(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    detail, _ = _applied_invoice(client, db)

    r = client.get(f"{URL}/{detail['id']}/export")

    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == _XLSX
    assert ".xlsx" in r.headers["content-disposition"]
    assert detail["id"] not in r.headers["content-disposition"]
    assert r.content[:2] == b"PK"


# --------------------------------------------------------------------------- #
# F5b - revisions (AC-E6, AC-E7, AC-E11)
# --------------------------------------------------------------------------- #


def test_the_preview_offers_the_invoice_on_file_as_a_revision_target(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    supplier, product = _seed_supplier_and_product(db)
    data = kailu_proforma_workbook({"SRTWT7443": product.product_code})
    client.post(f"{URL}/apply", files=_upload(data), data={"supplier_id": str(supplier.id)})

    r = client.post(
        f"{URL}/preview", files=_upload(data, "kailu-2.xlsx"),
        data={"supplier_id": str(supplier.id)},
    )

    assert r.status_code == 200, r.text
    candidate = r.json()["documents"][0]["revision_candidate"]
    assert candidate is not None
    assert candidate["overlap_pct"] == 100


def test_applying_with_a_revision_map_supersedes_the_named_invoice(scm_app):
    import json

    client, db = _client(scm_app, upload=True, view=True)
    supplier, product = _seed_supplier_and_product(db)
    data = kailu_proforma_workbook({"SRTWT7443": product.product_code})
    client.post(f"{URL}/apply", files=_upload(data), data={"supplier_id": str(supplier.id)})
    first = client.get(URL, params={"supplier_id": str(supplier.id)}).json()["data"][0]

    r = client.post(
        f"{URL}/apply",
        files=_upload(data, "kailu-2.xlsx"),
        data={
            "supplier_id": str(supplier.id),
            "revision_of": json.dumps({"1": first["id"]}),
        },
    )

    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["revision_no"] == 2
    superseded = client.get(f"{URL}/{first['id']}").json()
    assert superseded["status"] == "superseded"
    assert superseded["revision_count"] == 2


def test_a_revision_map_that_is_not_json_is_a_422_not_a_500(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    supplier, product = _seed_supplier_and_product(db)
    data = kailu_proforma_workbook({"SRTWT7443": product.product_code})

    r = client.post(
        f"{URL}/apply",
        files=_upload(data),
        data={"supplier_id": str(supplier.id), "revision_of": "not-json"},
    )

    assert r.status_code == 422, r.text


def test_mark_as_revision_of_links_two_invoices_after_the_fact(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    supplier, product = _seed_supplier_and_product(db)
    client.post(
        f"{URL}/apply",
        files=_upload(kailu_proforma_workbook({"SRTWT7443": product.product_code})),
        data={"supplier_id": str(supplier.id)},
    )
    first = client.get(URL, params={"supplier_id": str(supplier.id)}).json()["data"][0]
    # A second, genuinely different document for the same supplier.
    client.post(
        f"{URL}/apply",
        files=_upload(kailu_proforma_workbook({"SRTWT7443": product.product_code}), "b.xlsx"),
        data={"supplier_id": str(supplier.id)},
    )

    r = client.post(
        f"{URL}/{first['id']}/mark-as-revision-of", json={"previous_id": first["id"]}
    )

    # Itself is refused; the route is reachable and validating rather than 404ing.
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# F10 - the PI and the packing list see each other (AC-F6, AC-F9, AC-F10)
# --------------------------------------------------------------------------- #


def test_the_list_filters_on_where_the_goods_went(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    detail, _ = _applied_invoice(client, db)

    not_converted = client.get(
        URL, params={"supplier_id": detail["supplier_id"], "placement": "not_converted"}
    )
    assert not_converted.status_code == 200, not_converted.text
    assert [r["id"] for r in not_converted.json()["data"]] == [detail["id"]]

    converted = client.get(
        URL, params={"supplier_id": detail["supplier_id"], "placement": "converted"}
    )
    assert converted.json()["data"] == []


def test_a_placement_nobody_recognises_is_a_422(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    _applied_invoice(client, db)

    r = client.get(URL, params={"placement": "somewhere"})

    assert r.status_code == 422, r.text


def test_the_draft_shipments_route_is_gone(scm_app):
    """It served the dropped "add to an existing draft" select and nothing else (Q6)."""
    client, db = _client(scm_app, upload=True, view=True)
    _applied_invoice(client, db)

    r = client.get(f"{URL}/draft-shipments")

    assert r.status_code == 404, r.text


def test_converting_part_of_a_line_and_then_the_rest(scm_app):
    # The convert is a SHIPMENT write, so it sits behind `scm.reorder.run` rather than the
    # proforma upload permission.
    client, db = _client(scm_app, upload=True, view=True)
    _grant(db, client.app.dependency_overrides[scm_app[2]]()["id"], "scm.reorder.run")
    detail, line_id = _applied_invoice(client, db)
    matched = [ln["id"] for ln in detail["lines"] if ln["matched"]]

    first = client.post(
        f"{URL}/convert-to-draft-shipment",
        json={
            "proforma_invoice_ids": [detail["id"]],
            "line_quantities": {lid: 1 for lid in matched},
        },
    )
    assert first.status_code == 201, first.text

    after = client.get(f"{URL}/{detail['id']}").json()
    assert after["placement"] == "split"
    assert after["remaining_qty"] > 0

    second = client.post(
        f"{URL}/convert-to-draft-shipment",
        json={"proforma_invoice_ids": [detail["id"]]},
    )
    assert second.status_code == 201, second.text
    # A NEW packing list for the rest: a convert never adds to an existing draft (Q6).
    assert second.json()["shipment_id"] != first.json()["shipment_id"]

    finished = client.get(f"{URL}/{detail['id']}").json()
    assert finished["placement"] == "converted"
    assert finished["remaining_qty"] == 0


def test_a_body_still_naming_a_target_packing_list_gets_a_new_one(scm_app):
    """A stale bundle sending `target_shipment_id` must not silently land its goods in
    somebody else's box: the field is not part of the request any more, and the convert
    does what every convert does (Q6)."""
    client, db = _client(scm_app, upload=True, view=True)
    _grant(db, client.app.dependency_overrides[scm_app[2]]()["id"], "scm.reorder.run")
    detail, _ = _applied_invoice(client, db)
    matched = [ln["id"] for ln in detail["lines"] if ln["matched"]]
    first = client.post(
        f"{URL}/convert-to-draft-shipment",
        json={
            "proforma_invoice_ids": [detail["id"]],
            "line_quantities": {lid: 1 for lid in matched},
        },
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"{URL}/convert-to-draft-shipment",
        json={
            "proforma_invoice_ids": [detail["id"]],
            "target_shipment_id": first.json()["shipment_id"],
        },
    )

    assert second.status_code == 201, second.text
    assert second.json()["shipment_id"] != first.json()["shipment_id"]


def test_the_packing_list_route_names_the_invoices_behind_it(scm_app):
    client, db = _client(scm_app, upload=True, view=True)
    _grant(db, client.app.dependency_overrides[scm_app[2]]()["id"], "scm.reorder.run")
    detail, _ = _applied_invoice(client, db)
    converted = client.post(
        f"{URL}/convert-to-draft-shipment", json={"proforma_invoice_ids": [detail["id"]]}
    ).json()

    r = client.get(
        f"/api/v1/scm/inbound-shipments/{converted['shipment_id']}/source-proforma-invoices"
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert [i["pi_number"] for i in body["invoices"]] == [detail["pi_number"]]
    assert body["by_shipment_line"]
