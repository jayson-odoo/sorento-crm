"""Draft (proforma-created) shipments must never reach the salesperson MCP tools.

`proforma_invoice_service` creates a draft `InboundShipment` (`shipment_status = "draft"`,
numbered `SHIP-DRAFT-...`) while an SPO Planner session is still in progress. Nothing about it
is a real container yet, so it must be invisible to `IncomingStockService` - the service behind
`/api/v1/incoming-stock/*`, which is what the MCP tools (`crm_incoming_stock_list`,
`crm_incoming_stock_by_product`, `crm_incoming_stock_shipments`) expose to salespeople. It must
also be unresolvable by container/BOL/invoice number in `entity_resolver`'s inbound-shipment
probes, or the assistant can still name a draft container and then get told "nothing incoming
for it" instead of never hearing of it in the first place.

The INTERNAL screen (`/scm/incoming`, and the packing-list detail page's own tabs including SPO
Planner) reads a *different* backend surface - `GET /api/v1/scm/inbound-shipments` in
`app/api/v1/scm/fulfilment.py` - which this change does not touch and must keep showing drafts:
the captain navigates to a draft's packing list and SPO Planner from that very list. The last
test in this file proves that path is untouched.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest

from app.models.procurement import InboundShipment, InboundShipmentLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.entity_resolver import (
    _prefix_probe_inbound_shipment,
    _probe_inbound_shipment,
)
from app.services.incoming_stock_service import IncomingStockService
from tests._pg_fixture import blank_session

MARKER = "ZZDRAFT"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _product(db, code: str) -> str:
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=f"CAT-{code}", category_name=f"Category {code}"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"UOM-{code}", uom_name="Each")
    db.add_all([category, uom])
    db.flush()

    pid = str(uuid.uuid4())
    db.add(
        Product(
            id=pid,
            product_code=code,
            product_name=code,
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=0,
            is_active=True,
        )
    )
    db.flush()
    return pid


def _shipment(db, *, number: str, status: str) -> str:
    sid = str(uuid.uuid4())
    db.add(
        InboundShipment(
            id=sid,
            shipment_number=number,
            shipment_date=date(2026, 1, 1),
            estimated_arrival_date=date(2026, 2, 1),
            shipment_status=status,
        )
    )
    db.flush()
    return sid


def _line(db, shipment_id: str, product_id: str, *, shipped: int) -> None:
    db.add(
        InboundShipmentLine(
            id=str(uuid.uuid4()),
            shipment_id=shipment_id,
            product_id=product_id,
            quantity_shipped=shipped,
            quantity_received=0,
            line_status="in_transit",
        )
    )
    db.flush()


# --------------------------------------------------------------------------- #
# MCP-facing path: IncomingStockService excludes drafts
# --------------------------------------------------------------------------- #


def test_incoming_list_excludes_draft_shipment_but_keeps_a_real_one(db):
    p = _product(db, f"{MARKER}-SKU-1")
    draft = _shipment(db, number=f"{MARKER}-SHIP-DRAFT-1", status="draft")
    real = _shipment(db, number=f"{MARKER}-SHIP-REAL-1", status="in_transit")
    _line(db, draft, p, shipped=10)
    _line(db, real, p, shipped=7)
    db.commit()

    res = IncomingStockService(db).incoming_list(product_ids=[p])

    assert res["empty"] is False
    numbers = [row["shipment_number"] for row in res["data"]]
    assert numbers == [f"{MARKER}-SHIP-REAL-1"]


def test_incoming_list_all_draft_reads_empty_not_a_leak(db):
    p = _product(db, f"{MARKER}-SKU-2")
    draft = _shipment(db, number=f"{MARKER}-SHIP-DRAFT-2", status="draft")
    _line(db, draft, p, shipped=10)
    db.commit()

    res = IncomingStockService(db).incoming_list(product_ids=[p])

    assert res["empty"] is True
    assert res["data"] == []


def test_incoming_for_product_excludes_draft_shipment_but_keeps_a_real_one(db):
    p = _product(db, f"{MARKER}-SKU-3")
    draft = _shipment(db, number=f"{MARKER}-SHIP-DRAFT-3", status="draft")
    real = _shipment(db, number=f"{MARKER}-SHIP-REAL-3", status="in_transit")
    _line(db, draft, p, shipped=10)
    _line(db, real, p, shipped=4)
    db.commit()

    res = IncomingStockService(db).incoming_for_product(product_ids=[p])

    assert res["empty"] is False
    bucket = next(b for b in res["data"] if b["product_code"] == f"{MARKER}-SKU-3")
    ship_numbers = [s["shipment_number"] for s in bucket["shipments"]]
    assert ship_numbers == [f"{MARKER}-SHIP-REAL-3"]
    # And the remaining quantity is the REAL shipment's own, never the draft's.
    assert bucket["shipments"][0]["remaining_incoming_quantity"] == 4


def test_shipment_incoming_products_returns_nothing_for_a_draft_shipment(db):
    p = _product(db, f"{MARKER}-SKU-4")
    draft = _shipment(db, number=f"{MARKER}-SHIP-DRAFT-4", status="draft")
    _line(db, draft, p, shipped=10)
    db.commit()

    res = IncomingStockService(db).shipment_incoming_products(draft)

    assert res["empty"] is True
    assert res["data"] is None


def test_incoming_shipments_excludes_draft_shipment_but_keeps_a_real_one(db):
    p = _product(db, f"{MARKER}-SKU-5")
    draft = _shipment(db, number=f"{MARKER}-SHIP-DRAFT-5", status="draft")
    real = _shipment(db, number=f"{MARKER}-SHIP-REAL-5", status="in_transit")
    _line(db, draft, p, shipped=10)
    _line(db, real, p, shipped=6)
    db.commit()

    res = IncomingStockService(db).incoming_shipments(
        eta_from=date(2026, 1, 1), eta_to=date(2026, 12, 31)
    )

    numbers = [row["shipment_number"] for row in res["data"]]
    assert f"{MARKER}-SHIP-DRAFT-5" not in numbers
    assert f"{MARKER}-SHIP-REAL-5" in numbers


def test_shipment_attachment_returns_none_for_a_draft_shipment(db):
    draft = _shipment(db, number=f"{MARKER}-SHIP-DRAFT-6", status="draft")
    db.commit()

    res = IncomingStockService(db).shipment_attachment(draft)

    assert res is None


def test_shipment_attachment_still_returns_for_a_real_shipment(db):
    real = _shipment(db, number=f"{MARKER}-SHIP-REAL-6", status="in_transit")
    db.commit()

    res = IncomingStockService(db).shipment_attachment(real)

    assert res is not None
    assert res["shipment_number"] == f"{MARKER}-SHIP-REAL-6"
    assert res["attachment"] is None  # no attachment linked, but the shipment itself resolves


def test_incoming_entity_alternatives_has_incoming_excludes_draft_only_neighbour(db, monkeypatch):
    """`_has_incoming` (the batch predicate `_incoming_entity_alternatives` hands to
    `find_entity_neighbours_with_data`) must not call a neighbour "data-bearing" on the
    strength of a draft-only shipment line.

    The full neighbour walk needs pg_trgm, which is not on the search_path of the scratch
    schema `blank_session` builds - so `find_entity_neighbours_with_data` itself is stubbed
    here to capture the `has_data` callback `_incoming_entity_alternatives` constructs, and
    that callback is exercised directly against a draft-only candidate and a real-incoming
    one. This is what changed; the ranking/gating logic downstream of it is untouched.
    """
    target = _product(db, f"{MARKER}-SKU-7")
    draft_only = _product(db, f"{MARKER}-SKU-7B")
    real_incoming = _product(db, f"{MARKER}-SKU-7C")
    draft = _shipment(db, number=f"{MARKER}-SHIP-DRAFT-7", status="draft")
    real = _shipment(db, number=f"{MARKER}-SHIP-REAL-7", status="in_transit")
    _line(db, draft, draft_only, shipped=5)
    _line(db, real, real_incoming, shipped=5)
    db.commit()

    captured: dict[str, Any] = {}

    def fake_find_neighbours(db_, code, *, has_data, **kwargs):
        captured["has_data"] = has_data
        return []

    monkeypatch.setattr(
        "app.services.entity_resolver.find_entity_neighbours_with_data",
        fake_find_neighbours,
    )

    IncomingStockService(db)._incoming_entity_alternatives([target])

    assert "has_data" in captured
    with_data = captured["has_data"]([draft_only, real_incoming])
    assert with_data == {real_incoming}


# --------------------------------------------------------------------------- #
# entity_resolver: the same draft must not be NAMEABLE by container/BOL/invoice
# --------------------------------------------------------------------------- #


def test_probe_inbound_shipment_excludes_draft_but_keeps_a_real_one(db):
    draft_number = f"{MARKER}-SHIP-DRAFT-8"
    real_number = f"{MARKER}-SHIP-REAL-8"
    _shipment(db, number=draft_number, status="draft")
    _shipment(db, number=real_number, status="in_transit")
    db.commit()

    res = _probe_inbound_shipment(db, [draft_number, real_number])

    assert res[draft_number] == []
    assert [m.canonical_code for m in res[real_number]] == [real_number]


def test_prefix_probe_inbound_shipment_excludes_draft_but_keeps_a_real_one(db):
    prefix = f"{MARKER}-SHIP-PFX8"
    _shipment(db, number=f"{prefix}-DRAFT", status="draft")
    _shipment(db, number=f"{prefix}-REAL", status="in_transit")
    db.commit()

    res = _prefix_probe_inbound_shipment(db, prefix)

    codes = [m.canonical_code for m in res]
    assert f"{prefix}-DRAFT" not in codes
    assert f"{prefix}-REAL" in codes


# --------------------------------------------------------------------------- #
# Internal path: /api/v1/scm/inbound-shipments must keep showing drafts -
# the captain opens a draft's packing list / SPO Planner from this very list.
# --------------------------------------------------------------------------- #


try:
    from fastapi.testclient import TestClient

    from tests.scm.conftest import requires_pg, scm_app  # noqa: F401
    from tests.scm.test_outstanding_import_routes import as_company_user

    _HAS_SCM_FIXTURES = True
except Exception:  # pragma: no cover - defensive, mirrors other scm test files
    _HAS_SCM_FIXTURES = False


if _HAS_SCM_FIXTURES:

    @requires_pg
    def test_internal_inbound_shipments_list_still_shows_a_draft_shipment(scm_app):
        # Scoped to a test-owned supplier (rather than the unfiltered list, newest-25) so the
        # assertion cannot be sunk by whatever real, unrelated shipments already exist on the
        # shared local database this fixture runs against.
        from app.models.procurement import Supplier

        app, db, gcu, gcuk = scm_app
        as_company_user(app, db, gcu, gcuk)

        supplier = Supplier(
            id=str(uuid.uuid4()),
            supplier_code=f"{MARKER}-SUP-{uuid.uuid4().hex[:6]}".upper(),
            supplier_name=f"{MARKER} supplier",
            is_active=True,
        )
        db.add(supplier)
        db.flush()

        draft = InboundShipment(
            id=str(uuid.uuid4()),
            shipment_number=f"{MARKER}-SHIP-DRAFT-INTERNAL",
            supplier_id=supplier.id,
            shipment_date=date(2026, 1, 1),
            shipping_container_number=f"{MARKER}U0000001",
            shipment_status="draft",
        )
        db.add(draft)
        db.flush()

        r = TestClient(app).get(
            "/api/v1/scm/inbound-shipments", params={"supplier_id": supplier.id}
        )

        assert r.status_code == 200, r.text
        ids = [row["shipment_id"] for row in r.json()["data"]]
        assert str(draft.id) in ids
        row = next(x for x in r.json()["data"] if x["shipment_id"] == str(draft.id))
        assert row["shipment_number"] == f"{MARKER}-SHIP-DRAFT-INTERNAL"
        assert row["status"] == "draft"
