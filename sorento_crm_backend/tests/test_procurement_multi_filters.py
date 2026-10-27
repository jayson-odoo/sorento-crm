"""FILTER-MULTISELECT PR4b: GRN Status, New product applications (Status, Applicant), Packing lists
Region, Purchase requests (Type, Status, Assigned to), SPO documents (Product, Warehouse), Cost price
uploads (Supplier, Status guard) take several values (OR within a filter, AND across); comma-joined,
repeated and single all read. Order statuses "Final" stays yes / no but is answered by the server, so
pagination reflects it. Red first; Postgres only; rows seeded here into a blank schema.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.cost_price import CostPriceChangeSet
from app.models.inventory import Warehouse
from app.models.new_product_application import NewProductApplication
from app.models.order import OrderStatus
from app.models.procurement import (
    InboundShipment,
    PickingHeader,
    PurchaseRequestHeader,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.sla import ConversationSLATracking, SLAPolicy, SLAPolicyTier
from app.models.user import User
from tests._multi_filter_client import SORENTO, get, ok_ids, open_client
from tests._pg_fixture import blank_session, unique_code

P = "/api/v1/procurement"
GRN = f"{P}/grn/"
NPA = f"{P}/new-product-applications"
PACKING = f"{P}/packing-lists/"
PR = f"{P}/purchase-requests/"
SPO_DOCS = f"{P}/spo-allocations/documents"
COST = f"{P}/cost-price-changes"
ORDER_STATUSES = "/api/v1/order-management/order-statuses/"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _user(db, key):
    u = User(id=_uid(), email=f"zzt-{key}-{uuid.uuid4().hex[:6]}@test.com", name=f"ZZT {key}")
    db.add(u)
    db.flush()
    return u


# ---- GRN: Status -----------------------------------------------------------------------------------------

@pytest.fixture
def grns(db):
    tag = unique_code("GRN", alpha=True)
    rows = {}
    for key, status in (("a", "draft"), ("b", "approved"), ("c", "cancelled"), ("d", "approved")):
        h = PickingHeader(id=_uid(), picking_number=f"{tag}-{key}", picking_type="goods_received", picking_status=status)
        db.add(h)
        db.flush()
        rows[key] = h
    return rows


def _grns(client, pairs):
    return ok_ids(get(client, GRN, [("limit", 200), *pairs]))


def test_grn_status_single_and_union(client, grns):
    s = grns
    assert _grns(client, [("picking_status", "approved")]) == {s["b"].id, s["d"].id}
    assert _grns(client, [("picking_status", "draft,cancelled")]) == {s["a"].id, s["c"].id}
    assert _grns(client, [("picking_status", "draft"), ("picking_status", "approved")]) == {s["a"].id, s["b"].id, s["d"].id}


def test_grn_status_sentinel_all_is_not_a_filter(client, grns):
    assert len(_grns(client, [("picking_status", "all")])) == 4


# ---- New product applications: Status (guard) and Applicant ------------------------------------------------

@pytest.fixture
def npas(db, monkeypatch):
    from app.services import new_product_application_service as svc

    monkeypatch.setattr(
        "app.api.v1.procurement.new_product_applications.permission_slugs", lambda _db, _uid: [svc.VIEW]
    )
    u1, u2, u3 = _user(db, "u1"), _user(db, "u2"), _user(db, "u3")
    rows = {}
    for key, status, who in (("a", "draft", u1), ("b", "submitted", u2), ("c", "approved", u3), ("d", "submitted", u1)):
        n = NewProductApplication(
            id=_uid(), company_id=SORENTO, application_no=unique_code(f"NPA{key}"), status=status, applicant_id=who.id,
        )
        db.add(n)
        db.flush()
        rows[key] = n
    return dict(users=(u1, u2, u3), **rows)


def _npas(client, pairs):
    resp = get(client, NPA, [("limit", 100), *pairs])
    assert resp.status_code == 200, resp.text
    return {row["id"] for row in resp.json()["items"]}


def test_npa_status_guard_forms(client, npas):
    s = npas
    assert _npas(client, [("status", "submitted,approved")]) == {s["b"].id, s["c"].id, s["d"].id}
    assert _npas(client, [("status", "draft")]) == {s["a"].id}


def test_npa_status_repeated(client, npas):
    s = npas
    assert _npas(client, [("status", "draft"), ("status", "approved")]) == {s["a"].id, s["c"].id}


def test_npa_applicant_union_single_repeated(client, npas):
    s = npas
    u1, u2, u3 = (u.id for u in s["users"])
    assert _npas(client, [("applicant_id", u1)]) == {s["a"].id, s["d"].id}
    assert _npas(client, [("applicant_id", f"{u2},{u3}")]) == {s["b"].id, s["c"].id}
    assert _npas(client, [("applicant_id", u2), ("applicant_id", u3)]) == {s["b"].id, s["c"].id}


def test_npa_status_and_applicant_are_and_ed(client, npas):
    s = npas
    u1, u2, _u3 = (u.id for u in s["users"])
    assert _npas(client, [("status", "draft,submitted"), ("applicant_id", f"{u1},{u2}")]) == {s["a"].id, s["b"].id, s["d"].id}
    assert _npas(client, [("status", "submitted"), ("applicant_id", f"{u1},{u2}")]) == {s["b"].id, s["d"].id}


# ---- Packing lists: Region (west / east) -----------------------------------------------------------------

@pytest.fixture
def packing(db):
    rows = {}
    for key, regions in (("a", ["west"]), ("b", ["east"]), ("c", ["west", "east"])):
        sh = InboundShipment(id=_uid(), shipment_date=date(2026, 1, 1), regions=regions)
        db.add(sh)
        db.flush()
        rows[key] = sh
    return rows


def _packing(client, pairs):
    return ok_ids(get(client, PACKING, [("limit", 200), *pairs]))


def test_packing_region_single(client, packing):
    s = packing
    assert _packing(client, [("region", "west")]) == {s["a"].id, s["c"].id}
    assert _packing(client, [("region", "east")]) == {s["b"].id, s["c"].id}


def test_packing_region_both_is_either(client, packing):
    s = packing
    assert _packing(client, [("region", "west,east")]) == {s["a"].id, s["b"].id, s["c"].id}
    assert _packing(client, [("region", "west"), ("region", "east")]) == {s["a"].id, s["b"].id, s["c"].id}


def test_packing_region_unknown_is_refused(client, packing):
    assert get(client, PACKING, [("region", "west,north")]).status_code == 422


# ---- Purchase requests: Type, Status, Assigned to --------------------------------------------------------

@pytest.fixture
def prs(db):
    u1, u2 = _user(db, "pr1"), _user(db, "pr2")
    pol = SLAPolicy(id=_uid(), code=unique_code("pol"), name="ZZT policy")
    db.add(pol)
    db.add(SLAPolicyTier(id=_uid(), policy_id=pol.id, tier_level=1, tier_name="T1", response_hours=4, resolution_hours=24))
    db.flush()
    spec = {
        "a": ("purchase_request", "pending", u1),
        "b": ("sponsorship_form", "approved", u2),
        "c": ("purchase_request", "rejected", None),
        "d": ("sponsorship_form", "pending", None),
        "e": ("purchase_request", None, None),
    }
    tag = unique_code("PR", alpha=True)
    rows = {}
    for key, (rtype, appr, who) in spec.items():
        h = PurchaseRequestHeader(id=_uid(), request_type=rtype, approval_status=appr, request_number=f"{tag}-{key}")
        db.add(h)
        db.flush()
        rows[key] = h
        if who is not None:
            now = datetime.utcnow()
            db.add(ConversationSLATracking(
                id=_uid(), policy_id=pol.id, current_tier=1, due_at=now + timedelta(days=1),
                is_responded=False, is_resolved=False, source_entity_type=rtype, source_entity_id=h.id,
                assigned_to_id=who.id,
            ))
            db.flush()
    return dict(users=(u1, u2), **rows)


def _prs(client, pairs):
    return ok_ids(get(client, PR, [("limit", 200), *pairs]))


def test_pr_type_single_and_repeated(client, prs):
    s = prs
    assert _prs(client, [("request_type", "sponsorship_form")]) == {s["b"].id, s["d"].id}
    got = _prs(client, [("request_type", "purchase_request"), ("request_type", "sponsorship_form")])
    assert got == {s[k].id for k in "abcde"}


def test_pr_status_union_with_draft(client, prs):
    s = prs
    assert _prs(client, [("approval_status", "pending")]) == {s["a"].id, s["d"].id}
    assert _prs(client, [("approval_status", "pending,approved")]) == {s["a"].id, s["b"].id, s["d"].id}
    assert _prs(client, [("approval_status", "draft,rejected")]) == {s["c"].id, s["e"].id}
    assert _prs(client, [("approval_status", "draft"), ("approval_status", "approved")]) == {s["b"].id, s["e"].id}


def test_pr_assigned_to_union_and_unassigned_pseudo_value(client, prs):
    s = prs
    u1, u2 = (u.id for u in s["users"])
    assert _prs(client, [("assigned_to", u1)]) == {s["a"].id}
    assert _prs(client, [("assigned_to", f"{u1},{u2}")]) == {s["a"].id, s["b"].id}
    assert _prs(client, [("assigned_to", u1), ("assigned_to", u2)]) == {s["a"].id, s["b"].id}
    assert _prs(client, [("assigned_to", f"__unassigned__,{u1}")]) == {s["a"].id, s["c"].id, s["d"].id, s["e"].id}
    assert _prs(client, [("assigned_to", "__unassigned__")]) == {s["c"].id, s["d"].id, s["e"].id}


def test_pr_filters_and_across(client, prs):
    s = prs
    u1, u2 = (u.id for u in s["users"])
    got = _prs(client, [("request_type", "purchase_request"), ("approval_status", "pending,rejected"),
                        ("assigned_to", f"__unassigned__,{u2}")])
    assert got == {s["c"].id}
    got = _prs(client, [("approval_status", "pending,approved"), ("assigned_to", f"{u1},{u2}")])
    assert got == {s["a"].id, s["b"].id}


# ---- SPO documents: Product, Warehouse -------------------------------------------------------------------

@pytest.fixture
def spos(db):
    cat = ProductCategory(id=_uid(), category_code=unique_code("c"), category_name="ZZT cat")
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("u"), uom_name="ZZT uom")
    db.add_all([cat, uom])
    db.flush()
    prods = []
    for i in range(3):
        p = Product(id=_uid(), product_code=unique_code(f"p{i}"), product_name=f"ZZT p{i}", category_id=cat.id,
                    base_uom_id=uom.id, list_price=Decimal("1.00"))
        db.add(p)
        prods.append(p)
    whs = []
    for i in range(3):
        w = Warehouse(id=_uid(), warehouse_code=unique_code(f"w{i}"), warehouse_name=f"ZZT w{i}", is_active=True)
        db.add(w)
        whs.append(w)
    db.flush()
    tag = unique_code("SPO", alpha=True)
    nums = {}
    for key, (pi, wi) in {"a": (0, 0), "b": (1, 1), "c": (2, 2), "d": (0, 2)}.items():
        nums[key] = f"{tag}-{key}"
        db.add(SPOAllocation(
            id=_uid(), spo_number=nums[key], product_id=prods[pi].id, warehouse_id=whs[wi].id, allocated_quantity=5,
        ))
        db.flush()
    return dict(prods=prods, whs=whs, nums=nums)


def _spos(client, pairs):
    resp = get(client, SPO_DOCS, [("limit", 200), *pairs])
    assert resp.status_code == 200, resp.text
    return {row["spo_number"] for row in resp.json()["data"]}


def test_spo_seed_is_visible(client, spos):
    assert _spos(client, []) == set(spos["nums"].values())


def test_spo_product_single_union_repeated(client, spos):
    s, n = spos, spos["nums"]
    p0, p1, p2 = (p.id for p in s["prods"])
    assert _spos(client, [("product_id", p0)]) == {n["a"], n["d"]}
    assert _spos(client, [("product_id", f"{p1},{p2}")]) == {n["b"], n["c"]}
    assert _spos(client, [("product_id", p1), ("product_id", p2)]) == {n["b"], n["c"]}


def test_spo_warehouse_single_union_repeated(client, spos):
    s, n = spos, spos["nums"]
    w0, w1, w2 = (w.id for w in s["whs"])
    assert _spos(client, [("warehouse_id", w2)]) == {n["c"], n["d"]}
    assert _spos(client, [("warehouse_id", f"{w0},{w1}")]) == {n["a"], n["b"]}
    assert _spos(client, [("warehouse_id", w0), ("warehouse_id", w1)]) == {n["a"], n["b"]}


def test_spo_product_and_warehouse_are_and_ed(client, spos):
    s, n = spos, spos["nums"]
    p0, _p1, p2 = (p.id for p in s["prods"])
    _w0, _w1, w2 = (w.id for w in s["whs"])
    assert _spos(client, [("product_id", f"{p0},{p2}"), ("warehouse_id", w2)]) == {n["c"], n["d"]}


def test_spo_malformed_ids_are_refused(client, spos):
    for key in ("product_id", "warehouse_id"):
        resp = get(client, SPO_DOCS, [(key, f"{_uid()},not-a-uuid")])
        assert resp.status_code == 422, (key, resp.text)


# ---- Cost price uploads: Supplier (multi) and Status (guard) ---------------------------------------------

@pytest.fixture
def costs(db):
    sups = []
    for i in range(3):
        s = Supplier(id=_uid(), supplier_code=unique_code(f"s{i}"), supplier_name=f"ZZT supplier {i}")
        db.add(s)
        sups.append(s)
    db.flush()
    rows = {}
    for key, (si, status) in {"a": (0, "draft"), "b": (1, "applied"), "c": (2, "draft"), "d": (0, "applied")}.items():
        cs = CostPriceChangeSet(
            id=_uid(), code=unique_code(f"CP{key}"), supplier_id=sups[si].id, currency="MYR", status=status,
        )
        db.add(cs)
        db.flush()
        rows[key] = cs
    return dict(sups=sups, **rows)


def _costs(client, pairs):
    resp = get(client, COST, [("limit", 200), *pairs])
    assert resp.status_code == 200, resp.text
    return {row["id"] for row in resp.json()["data"]}


def test_cost_status_guard_forms(client, costs):
    s = costs
    assert _costs(client, [("status", "draft,applied")]) == {s[k].id for k in "abcd"}
    assert _costs(client, [("status", "applied")]) == {s["b"].id, s["d"].id}


def test_cost_supplier_single_union_repeated(client, costs):
    s = costs
    s0, s1, s2 = (x.id for x in s["sups"])
    assert _costs(client, [("supplier_id", s0)]) == {s["a"].id, s["d"].id}
    assert _costs(client, [("supplier_id", f"{s1},{s2}")]) == {s["b"].id, s["c"].id}
    assert _costs(client, [("supplier_id", s1), ("supplier_id", s2)]) == {s["b"].id, s["c"].id}


def test_cost_supplier_and_status_are_and_ed(client, costs):
    s = costs
    s0, s1, _s2 = (x.id for x in s["sups"])
    assert _costs(client, [("supplier_id", f"{s0},{s1}"), ("status", "applied")]) == {s["b"].id, s["d"].id}


def test_cost_malformed_supplier_is_refused(client, costs):
    assert get(client, COST, [("supplier_id", f"{_uid()},not-a-uuid")]).status_code == 422


# ---- Order statuses: Final is answered by the server -----------------------------------------------------

@pytest.fixture
def order_statuses(db):
    final, other = [], []
    for i in range(3):
        for flag, bucket in ((True, final), (False, other)):
            row = OrderStatus(
                id=_uid(), status_code=unique_code(f"os{i}{'f' if flag else 'n'}"), status_name=f"ZZT {i}{flag}",
                sequence=i * 2 + (0 if flag else 1), is_final_status=flag,
            )
            db.add(row)
            db.flush()
            bucket.append(row)
    return dict(final=final, other=other)


def _statuses(client, pairs):
    resp = get(client, ORDER_STATUSES, pairs)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return {r["id"] for r in body["data"]}, body["pagination"]["total"]


def test_order_statuses_final_true_counts_the_whole_table(client, order_statuses):
    s = order_statuses
    ids, total = _statuses(client, [("is_final_status", "true"), ("limit", 2)])
    assert total == 3
    assert len(ids) == 2 and ids <= {r.id for r in s["final"]}


def test_order_statuses_final_true_page_two_is_reachable(client, order_statuses):
    s = order_statuses
    page1, _ = _statuses(client, [("is_final_status", "true"), ("limit", 2), ("page", 1)])
    page2, _ = _statuses(client, [("is_final_status", "true"), ("limit", 2), ("page", 2)])
    assert page1 | page2 == {r.id for r in s["final"]}
    assert len(page2) == 1


def test_order_statuses_final_false_and_absent(client, order_statuses):
    s = order_statuses
    ids, total = _statuses(client, [("is_final_status", "false"), ("limit", 50)])
    assert total == 3 and ids == {r.id for r in s["other"]}
    ids, total = _statuses(client, [("limit", 50)])
    assert total == 6 and ids == {r.id for r in s["final"]} | {r.id for r in s["other"]}
