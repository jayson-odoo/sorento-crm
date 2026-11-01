"""SUPPLIER-ASK: `supplier_ids` narrows the open-PO book to that supplier's lines.

`documentation/plans/chatbot/PLAN-supplier-ask-01nov.md` AC-3. Postgres only, blank schema,
every row seeded here (CI's database has none). Reuses the seeders of
`tests/test_purchase_orders_placed.py`.
"""
from __future__ import annotations

from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.purchase_order_service import (
    purchase_orders_placed_rows,
    purchase_orders_placed_summary,
)

from tests._mc_lookup_seed import product
from tests.test_purchase_orders_placed import (  # noqa: F401 - fixtures
    BASE,
    _po_line,
    _spo,
    _supplier,
    client,
    db,
)


def _numbers(rows):
    return sorted(r["po_number"] for r in rows)


def _two_suppliers(db):
    ours = _supplier(db, name="ZZ Sunrise Technology Co Ltd")
    other = _supplier(db, name="ZZ Other Sanitary Co Ltd")
    a = product(db, company_id=DEFAULT_COMPANY_ID)
    b = product(db, company_id=DEFAULT_COMPANY_ID)
    _po_line(db, supplier_id=ours.id, product_id=a.id, ordered=10, received=4, po_number="PO-OURS-A")
    _po_line(db, supplier_id=ours.id, product_id=b.id, ordered=3, received=0, po_number="PO-OURS-B")
    _po_line(db, supplier_id=ours.id, product_id=b.id, ordered=3, received=3, po_number="PO-OURS-DONE")
    _po_line(db, supplier_id=other.id, product_id=a.id, ordered=9, received=0, po_number="PO-OTHER")
    _spo(db, product_id=a.id, allocated=5, number="SPO-OURS", supplier_id=ours.id)
    _spo(db, product_id=a.id, allocated=7, number="SPO-OTHER", supplier_id=other.id)
    db.commit()
    return ours, other


def test_supplier_filter_keeps_only_that_suppliers_open_po_and_spo_lines(db):
    ours, _other = _two_suppliers(db)
    rows = purchase_orders_placed_rows(db, supplier_ids=[ours.id])
    assert _numbers(rows) == ["PO-OURS-A", "PO-OURS-B", "SPO-OURS"]
    assert {r["supplier"] for r in rows} == {"ZZ Sunrise Technology Co Ltd"}


def test_supplier_filter_summary_counts_exactly_the_filtered_rows(db):
    ours, _other = _two_suppliers(db)
    summary = purchase_orders_placed_summary(db, supplier_ids=[ours.id])
    assert summary == {"po_placed_qty": 6 + 3 + 5, "po_placed_count": 3}


def test_supplier_filter_route_passes_supplier_ids_through(client, db):
    ours, _other = _two_suppliers(db)
    resp = client.get(
        f"{BASE}/placed", params={"supplier_ids": ours.id, "include_summary": "true"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert _numbers(body["data"]) == ["PO-OURS-A", "PO-OURS-B", "SPO-OURS"]
    assert body["summary"]["po_placed_count"] == 3


def test_supplier_filter_route_rejects_a_malformed_id(client, db):
    resp = client.get(f"{BASE}/placed", params={"supplier_ids": "not-a-uuid"})
    assert resp.status_code == 400, resp.text



def test_supplier_filter_under_a_contact_without_the_reveal_is_403(client, db, monkeypatch):
    from app.services import contact_field_reveal_service, field_access

    ours, _other = _two_suppliers(db)
    monkeypatch.setattr(field_access, "resolve_contact_with_null_workspace_fallback", lambda db, **kw: "pk-1")
    monkeypatch.setattr(contact_field_reveal_service, "granted_keys", lambda db, pk: ["purchase_orders.placed"])
    resp = client.get(f"{BASE}/placed", params={"supplier_ids": ours.id, "contact_id": "900000001"})
    assert resp.status_code == 403, resp.text
    assert resp.json().get("code") == "supplier_not_revealed" or "supplier" in resp.text


def test_supplier_filter_under_an_unknown_contact_is_403(client, db):
    ours, _other = _two_suppliers(db)
    resp = client.get(f"{BASE}/placed", params={"supplier_ids": ours.id, "contact_id": "ZZT-no-such-contact"})
    assert resp.status_code == 403, resp.text


def test_supplier_filter_under_a_contact_with_the_reveal_filters(client, db, monkeypatch):
    from app.services import contact_field_reveal_service, field_access

    ours, _other = _two_suppliers(db)
    monkeypatch.setattr(field_access, "resolve_contact_with_null_workspace_fallback", lambda db, **kw: "pk-1")
    monkeypatch.setattr(contact_field_reveal_service, "granted_keys", lambda db, pk: ["purchase_orders.supplier"])
    import types

    # A contact whose stock policy shows every location (`scope_warehouse_ids` None = no narrowing).
    monkeypatch.setattr("app.services.stock_visibility.resolve_policy", lambda db, c, s: types.SimpleNamespace(mode="full"))
    monkeypatch.setattr("app.services.stock_visibility.scope_warehouse_ids", lambda db, policy: None)
    resp = client.get(f"{BASE}/placed", params={"supplier_ids": ours.id, "contact_id": "900000001"})
    assert resp.status_code == 200, resp.text
    assert _numbers(resp.json()["data"]) == ["PO-OURS-A", "PO-OURS-B", "SPO-OURS"]
