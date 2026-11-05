"""AI-QUERY-CORE (phase 1 of the AI tools standard): the registry query compiler, `crm_query`, `crm_describe`.

Written test-first against `documentation/plans/chatbot/PLAN-ai-query-core-5nov.md` ("Measured facts" and
"Contract"). The core is `app.services.assistant_registry` (`ENTITIES`, `query.run_query`, `query.describe`,
`query.QueryRefused`); the tools are `writes.USER_READS["crm_query" | "crm_describe"]`.

Postgres only (blank schema). Every row is seeded here and every assertion is filtered by this test's own tag, so
nothing leans on existing data. Core calls run through `writes.run_as_user` so the real company scope is stamped.

Imports of the unwritten package happen inside functions, so a missing module fails the test that needs it.
"""
from __future__ import annotations

import dataclasses
import json
from contextlib import contextmanager
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

import app.main  # noqa: F401  register every model and the app's listeners
from app.models.company import Company, UserCompany
from app.models.complaints import Complaint
from app.models.order import Order
from app.models.procurement import PurchaseOrder, Supplier
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.chatbot.agent import writes
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from tests._own_scope_support import contact as mk_contact
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._ported_reads_support import make_ctx, panel_turn
from tests.chatbot.agent._seed import seed_user

SORENTO = DEFAULT_COMPANY_ID
ORDERS_VIEW = "order_management.orders.view"
ORDERS_VIEW_OWN = "order_management.orders.view_own"
PRODUCTS_VIEW = "master_data.products.view"
COST_SLUG = "procurement.cost_price_changes.view"
SCM_VIEW = "scm.dashboard.view"
C_VIEW = "complaint_management.complaints.view"
C_OWN = "complaint_management.complaints.view_own"


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    yield


@pytest.fixture(scope="module")
def db():
    with blank_session() as session:
        yield session


# ------------------------------------------------------------------ seeding


def tag() -> str:
    return "ZZT" + uuid.uuid4().hex[:8].upper()


def mk_user(db, *slugs, contact=None, companies=(SORENTO,)) -> str:
    user_id = seed_user(db, contact_pk=contact.id if contact is not None else None, slugs=slugs)
    for company_id in companies:
        db.add(UserCompany(user_id=user_id, company_id=company_id))
    db.flush()
    return user_id


def mk_company_b(db) -> str:
    row = Company(id=str(uuid.uuid4()), name=f"ZZT Co {uuid.uuid4().hex[:6]}", code=unique_code("ZB")[:20])
    db.add(row)
    db.flush()
    return row.id


def mk_order(db, t: str, n: int, *, company_id: str = SORENTO, **kw) -> Order:
    row = Order(
        id=str(uuid.uuid4()),
        company_id=company_id,
        order_number=f"{t}-{n}",
        debtor_code=t,
        debtor_name=f"Debtor {t}",
        **kw,
    )
    db.add(row)
    return row


def mk_orders(db, t: str, count: int, **kw) -> list[Order]:
    rows = [mk_order(db, t, i, **kw) for i in range(count)]
    db.flush()
    return rows


def mk_product_chain(db, company_id: str = SORENTO) -> tuple[str, str, str]:
    cat = ProductCategory(
        id=str(uuid.uuid4()), company_id=company_id, category_code=unique_code("ZC"), category_name="ZZT Category"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), company_id=company_id, uom_code=unique_code("ZU"), uom_name="ZZT Unit")
    brand = Brand(id=str(uuid.uuid4()), company_id=company_id, brand_code=unique_code("ZB"), brand_name="ZZT Brand")
    db.add_all([cat, uom, brand])
    db.flush()
    return cat.id, uom.id, brand.id


def mk_product(db, code: str, chain, *, cost=Decimal("12.50")) -> Product:
    cat, uom, brand = chain
    row = Product(
        id=str(uuid.uuid4()), company_id=SORENTO, product_code=code, product_name=f"ZZT {code}",
        category_id=cat, base_uom_id=uom, brand_id=brand, list_price=Decimal("20.00"), cost_price=cost,
    )
    db.add(row)
    db.flush()
    return row


def mk_supplier(db, name: str) -> Supplier:
    row = Supplier(id=str(uuid.uuid4()), company_id=SORENTO, supplier_code=unique_code("ZS"), supplier_name=name)
    db.add(row)
    db.flush()
    return row


def mk_po(db, number: str, supplier: Supplier) -> PurchaseOrder:
    row = PurchaseOrder(id=str(uuid.uuid4()), company_id=SORENTO, po_number=number, supplier_id=supplier.id)
    db.add(row)
    db.flush()
    return row


def mk_complaint(db, t: str, n: int, *, owner_contact) -> Complaint:
    row = Complaint(
        id=str(uuid.uuid4()), complaint_number=f"{t}-{n}", customer_name=f"ZZT Customer {t} {n}",
        status="processed_by_cs", complaint_date=date(2026, 6, 2), contact_id=str(owner_contact.id),
    )
    db.add(row)
    db.flush()
    return row


# ------------------------------------------------------------------ running


def core(db, user_id: str, spec: dict):
    """`run_query` inside the user's real company scope, as the tool would run it."""
    from app.services.assistant_registry.query import run_query

    ctx = make_ctx(user_id)
    return writes.run_as_user(db, ctx, lambda user: run_query(db, user["id"], spec))


def refusal(db, user_id: str, spec: dict):
    from app.services.assistant_registry.query import QueryRefused

    with pytest.raises(QueryRefused) as info:
        core(db, user_id, spec)
    return info.value


def tool(db, ctx, args: dict, *, name: str = "crm_query", panel: bool = True):
    assert name in writes.USER_READS, f"{name} is not in writes.USER_READS"
    if panel:
        with panel_turn(ctx.user_id):
            return writes.run_user_read(db, ctx, name, args, set())
    return writes.run_user_read(db, ctx, name, args, set())


def code(row: dict) -> str:
    """A row's number or code: the part of its `label` ("CODE: Name") before the colon."""
    return row["label"].split(": ", 1)[0]


def order_spec(t: str, **extra) -> dict:
    return {"entity": "order", "filters": [{"field": "debtor_code", "op": "eq", "value": t}], **extra}


# ------------------------------------------------------------------ Q1 allowlist, filter, sort, limit


def test_Q1_filter_sort_limit_and_only_allowlisted_fields(db):
    t = tag()
    for i, total in enumerate([5, 30, 10, 20, 40]):
        mk_order(db, t, i, total_amount=Decimal(total), is_cancelled=False)
    db.flush()
    user = mk_user(db, ORDERS_VIEW)
    out = core(db, user, order_spec(
        t, fields=["order_number", "total_amount"], sort=[{"field": "total_amount", "dir": "desc"}], limit=3,
    ))
    assert out["entity"] == "order"
    rows = out["rows"]
    assert [float(r["total_amount"]) for r in rows] == [40, 30, 20]
    from app.services.assistant_registry import ENTITIES

    for row in rows:
        # what was asked; the number and debtor the record is named by come as one label
        assert set(row) <= {"total_amount", "id", "link", "label"}
        assert not set(row) & set(ENTITIES["order"].name_by)
        assert "deliver_phone" not in row
        assert row["id"] and row["link"]
    assert out["total"] == 5
    assert out["truncated"] is True and out["restricted"] == []


def test_Q1_a_column_outside_the_allowlist_is_refused_unknown_field(db):
    t = tag()
    mk_order(db, t, 1, deliver_phone="+6012345")
    db.flush()
    user = mk_user(db, ORDERS_VIEW)
    err = refusal(db, user, order_spec(t, fields=["order_number", "deliver_phone"]))
    assert err.code == "unknown_field"
    assert refusal(db, user, order_spec(t, filters=[{"field": "deliver_phone", "op": "eq", "value": "x"}])).code == "unknown_field"


# ------------------------------------------------------------------ Q2 field permission


def test_Q2_a_restricted_field_is_dropped_named_and_refused_in_a_filter(db):
    chain = mk_product_chain(db)
    code = unique_code("ZP")
    mk_product(db, code, chain)
    plain = mk_user(db, PRODUCTS_VIEW)
    spec = {
        "entity": "product", "fields": ["product_code", "cost_price"],
        "filters": [{"field": "product_code", "op": "eq", "value": code}],
    }
    out = core(db, plain, spec)
    assert len(out["rows"]) == 1
    assert out["rows"][0]["label"].split(": ", 1)[0] == code
    assert "cost_price" not in out["rows"][0]
    assert out["restricted"] == ["cost_price"]

    err = refusal(db, plain, {**spec, "filters": [{"field": "cost_price", "op": "gt", "value": 1}]})
    assert err.code == "restricted"

    holder = mk_user(db, PRODUCTS_VIEW, COST_SLUG)
    full = core(db, holder, spec)
    assert float(full["rows"][0]["cost_price"]) == 12.5
    assert not full.get("restricted")


# ------------------------------------------------------------------ Q3 company scope


def _two_company_world(db):
    t = tag()
    company_b = mk_company_b(db)
    mk_orders(db, t, 2)  # company A
    for i in range(3):
        mk_order(db, t, 100 + i, company_id=company_b)
    db.flush()
    return t, mk_user(db, ORDERS_VIEW, companies=(SORENTO,))


@pytest.mark.parametrize("panel", [True, False], ids=["panel", "whatsapp_linked_user"])
def test_Q3_a_user_never_sees_another_companys_orders(db, panel):
    t, user = _two_company_world(db)
    ctx = make_ctx(user)
    out = tool(db, ctx, order_spec(t, fields=["order_number"], limit=50), panel=panel)
    assert out.status == "ok", out
    numbers = {code(r) for r in out.data["rows"]}
    assert numbers == {f"{t}-0", f"{t}-1"}
    assert out.data["total"] == 2


def test_Q3_a_group_count_only_counts_the_users_company(db):
    t, user = _two_company_world(db)
    out = core(db, user, order_spec(t, group_by=["debtor_code"], aggregates=[{"fn": "count"}]))
    assert [(g["debtor_code"], g["count"]) for g in out["groups"]] == [(t, 2)]


# ------------------------------------------------------------------ Q4 own scope


def test_Q4_view_own_sees_only_their_contacts_complaints_and_view_sees_both(db):
    t = tag()
    ca, cb = mk_contact(db, "QA"), mk_contact(db, "QB")
    a = mk_complaint(db, t, 1, owner_contact=ca)
    b = mk_complaint(db, t, 2, owner_contact=cb)
    owner = mk_user(db, C_OWN, contact=ca)
    viewer = mk_user(db, C_VIEW)
    spec = {
        "entity": "complaint", "fields": ["complaint_number"],
        "filters": [{"field": "complaint_number", "op": "starts_with", "value": t}],
    }
    mine = core(db, owner, spec)
    assert [code(r) for r in mine["rows"]] == [a.complaint_number]
    both = core(db, viewer, spec)
    assert {code(r) for r in both["rows"]} == {a.complaint_number, b.complaint_number}


def test_Q4_own_only_holder_on_an_entity_without_an_own_clause_is_refused(db, monkeypatch):
    from app.services.assistant_registry import ENTITIES

    monkeypatch.setitem(
        ENTITIES, "order",
        dataclasses.replace(ENTITIES["order"], own_permission=ORDERS_VIEW_OWN, own_clause=None),
    )
    t = tag()
    mk_order(db, t, 1)
    db.flush()
    user = mk_user(db, ORDERS_VIEW_OWN)
    assert refusal(db, user, order_spec(t)).code == "own_only_unsupported"


# ------------------------------------------------------------------ Q5 aggregation equals hand SQL


def test_Q5_group_by_with_a_month_bucket_matches_hand_written_sql(db):
    t = tag()
    plan = [
        ("AG1", "WH1", date(2026, 1, 5), 10), ("AG1", "WH1", date(2026, 1, 28), 15),
        ("AG1", "WH1", date(2026, 2, 3), 7), ("AG1", "WH2", date(2026, 1, 9), 3),
        ("AG2", "WH1", date(2026, 2, 14), 100), ("AG2", "WH1", date(2026, 2, 20), 50),
    ]
    for i, (agent, wh, d, total) in enumerate(plan):
        mk_order(db, t, i, agent=agent, warehouse=wh, order_date=d, total_amount=Decimal(total))
    db.flush()
    user = mk_user(db, ORDERS_VIEW)
    out = core(db, user, order_spec(
        t,
        group_by=["agent", "warehouse", {"field": "order_date", "bucket": "month"}],
        aggregates=[{"fn": "sum", "field": "total_amount"}, {"fn": "count"}],
    ))
    def bucket(g: dict) -> str:
        # the contract does not name the bucket's key; it is the one that carries the date field's name
        (key,) = [k for k in g if k.startswith("order_date")]
        return str(g[key])[:10]

    got = {
        (g["agent"], g["warehouse"], bucket(g)): (float(g["sum_total_amount"]), int(g["count"]))
        for g in out["groups"]
    }
    rows = db.execute(
        text(
            "SELECT agent, warehouse, date_trunc('month', order_date)::date AS m, SUM(total_amount), COUNT(*) "
            "FROM orders WHERE debtor_code = :t AND company_id = :c AND deleted_at IS NULL "
            "GROUP BY agent, warehouse, m"
        ),
        {"t": t, "c": SORENTO},
    ).all()
    # the answer's date form, dd/mm/yyyy (owner ruling, 5 Nov)
    want = {(r[0], r[1], r[2].strftime("%d/%m/%Y")): (float(r[3]), int(r[4])) for r in rows}
    assert want and got == want
    assert out["total_groups"] == len(want)
    assert out["truncated"] is False


# ------------------------------------------------------------------ Q6 relation paths


def test_Q6_a_relation_path_filters_and_a_third_hop_is_too_deep(db):
    t = tag()
    mine, other = mk_supplier(db, f"Supplier {t} Mine"), mk_supplier(db, f"Supplier {t} Other")
    keep = mk_po(db, f"{t}-PO1", mine)
    mk_po(db, f"{t}-PO2", other)
    user = mk_user(db, SCM_VIEW)
    out = core(db, user, {
        "entity": "purchase_order", "fields": ["po_number"],
        "filters": [{"field": "supplier.name", "op": "contains", "value": f"{t} Mine"}],
    })
    assert [code(r) for r in out["rows"]] == [keep.po_number]
    err = refusal(db, user, {
        "entity": "purchase_order", "fields": ["po_number"],
        "filters": [{"field": "supplier.a.b.c", "op": "eq", "value": "x"}],
    })
    assert err.code == "too_deep"


# ------------------------------------------------------------------ Q7 caps


def test_Q7_rows_are_capped_at_50_and_say_so(db):
    from app.services.assistant_registry.query import MAX_GROUPS, MAX_ROWS

    assert (MAX_ROWS, MAX_GROUPS) == (50, 200)
    t = tag()
    mk_orders(db, t, 51)
    user = mk_user(db, ORDERS_VIEW)
    out = core(db, user, order_spec(t, fields=["order_number"], limit=60))
    assert len(out["rows"]) == 50
    assert out["truncated"] is True
    assert out["total"] == 51


def test_Q7_groups_are_capped_at_200_and_say_so(db):
    t = tag()
    mk_orders(db, t, 201)
    user = mk_user(db, ORDERS_VIEW)
    out = core(db, user, order_spec(t, group_by=["order_number"], aggregates=[{"fn": "count"}]))
    assert len(out["groups"]) == 200
    assert out["truncated"] is True
    assert out["total_groups"] == 201


# ------------------------------------------------------------------ Q8 timeout


def test_Q8_a_statement_timeout_is_a_refusal_and_the_session_survives(db, monkeypatch):
    from app.services.assistant_registry import query

    t = tag()
    mk_order(db, t, 1)
    db.flush()
    user = mk_user(db, ORDERS_VIEW)
    real = query._execute

    def slow(session, stmt):
        session.execute(text("SELECT pg_sleep(0.2)"))
        return real(session, stmt)

    monkeypatch.setattr(query, "STATEMENT_TIMEOUT_MS", 1)
    monkeypatch.setattr(query, "_execute", slow)

    assert refusal(db, user, order_spec(t)).code == "timeout"
    out = tool(db, make_ctx(user), order_spec(t))
    assert out.status == "timeout", out
    assert db.execute(text("SELECT 1")).scalar() == 1


# ------------------------------------------------------------------ Q9 module switch


def test_Q9_a_disabled_module_refuses_the_query(db, monkeypatch):
    import app.modules.runtime.guards as guards

    def blocked(*args, **kwargs):
        return "order" in args or "order" in kwargs.values()

    monkeypatch.setattr(guards, "module_blocked", blocked)
    t = tag()
    mk_order(db, t, 1)
    db.flush()
    user = mk_user(db, ORDERS_VIEW)
    assert refusal(db, user, order_spec(t)).code == "module_disabled"


# ------------------------------------------------------------------ Q10 contact principal


def test_Q10_a_contact_principal_is_offered_neither_tool_and_cannot_run_them(db):
    user = mk_user(db, ORDERS_VIEW)
    contact_ctx = dataclasses.replace(make_ctx(user), principal="contact", user_id="")
    assert "crm_query" in writes.USER_READS and "crm_describe" in writes.USER_READS
    offered = {r.name for r in writes.permitted_user_reads(db, contact_ctx)}
    assert not offered & {"crm_query", "crm_describe"}
    assert tool(db, contact_ctx, {"entity": "order"}, panel=False).status != "ok"
    assert tool(db, contact_ctx, {}, name="crm_describe", panel=False).status != "ok"
    # the same user as a linked user is offered both
    names = {r.name for r in writes.permitted_user_reads(db, make_ctx(user))}
    assert {"crm_query", "crm_describe"} <= names


def test_Q10_a_user_who_may_read_no_registered_entity_is_not_offered_the_tools(db):
    """Holding a slug of no registered entity, the tools would answer nothing: they are not offered, and the
    console operator case (another person acting) is not offered either (linked-only)."""
    nobody = mk_user(db, "inventory.stock.view")
    names = {r.name for r in writes.permitted_user_reads(db, make_ctx(nobody))}
    assert not names & {"crm_query", "crm_describe"}
    assert tool(db, make_ctx(nobody), {"entity": "order"}).status == "denied"
    viewer, operator = mk_user(db, ORDERS_VIEW), mk_user(db, ORDERS_VIEW)
    acting = {r.name for r in writes.permitted_user_reads(db, make_ctx(viewer, operator=operator))}
    assert not acting & {"crm_query", "crm_describe"}


# ------------------------------------------------------------------ Q11 describe


def _listed(out: dict) -> set[str]:
    return {(e.get("key") or e.get("entity")) if isinstance(e, dict) else e for e in out["entities"]}


def test_Q11_describe_lists_exactly_the_entities_the_user_may_view(db):
    from app.services.assistant_registry.query import describe

    user = mk_user(db, ORDERS_VIEW)
    out = writes.run_as_user(db, make_ctx(user), lambda u: describe(db, u["id"]))
    listed = _listed(out)
    assert "order" in listed
    assert not listed & {"product", "purchase_order", "complaint"}
    # lookup entities (no view slug) are never listed
    from app.services.assistant_registry import ENTITIES

    lookups = {k for k, e in ENTITIES.items() if e.view_permission is None}
    assert not listed & lookups


def test_Q11_describe_of_an_entity_the_user_may_not_view_is_no_access(db):
    from app.services.assistant_registry.query import QueryRefused, describe

    user = mk_user(db, ORDERS_VIEW)
    with pytest.raises(QueryRefused) as info:
        writes.run_as_user(db, make_ctx(user), lambda u: describe(db, u["id"], "product"))
    assert info.value.code == "no_access"
    shown = writes.run_as_user(db, make_ctx(user), lambda u: describe(db, u["id"], "order"))
    assert "order_number" in json.dumps(shown, default=str)
    assert "deliver_phone" not in json.dumps(shown, default=str)


def test_Q11_the_describe_tool_answers_ok_for_a_viewable_entity(db):
    user = mk_user(db, ORDERS_VIEW)
    out = tool(db, make_ctx(user), {"entity": "order"}, name="crm_describe")
    assert out.status == "ok", out


# ------------------------------------------------------------------ Q12 registry self-check


def test_Q12_the_registry_is_consistent_with_the_models_and_the_permission_registry():
    from app.rbac.permission_registry import PERMISSION_REGISTRY
    from app.services.assistant_registry import ENTITIES

    slugs = {p["slug"] for p in PERMISSION_REGISTRY}
    from app.services.contact_field_reveal_service import FIELD_REVEAL_KEYS

    # AI-TOOLS-WAVE2: a field may name a reveal key (`reveal:<key>`) the sales report gates on.
    known = slugs | {f"reveal:{k}" for k, _label in FIELD_REVEAL_KEYS}
    assert {"order", "product", "purchase_order", "complaint"} <= set(ENTITIES)
    for key, ent in ENTITIES.items():
        assert ent.key == key
        columns = {c.key for c in sa_inspect(ent.model).columns}
        for name, field in ent.fields.items():
            col = field.column or name
            if ent.compute is not None:
                # AI-TOOLS-WAVE2: a computed entity's field has no column; its kind says its type.
                assert field.kind in ("text", "number", "date", "boolean"), f"{key}.{name}: computed field needs a kind"
            elif field.expr is None:
                assert col in columns, f"{key}.{name}: no column {col} on {ent.model.__name__}"
            if field.permission:
                assert field.permission in known, f"{key}.{name}: unknown slug {field.permission}"
        if ent.aggregate_permission:
            assert ent.aggregate_permission in known, f"{key}: unknown aggregate slug {ent.aggregate_permission}"
        for slug in (ent.view_permission, ent.own_permission):
            if slug:
                assert slug in slugs, f"{key}: unknown slug {slug}"
        for rel, (target, fk) in ent.relations.items():
            assert target in ENTITIES, f"{key}.{rel}: unknown target entity {target}"
            assert fk in columns, f"{key}.{rel}: no fk column {fk}"
        for name in ent.name_by:
            # a naming field is always returned, so it must be allowlisted and need no slug of its own
            assert name in ent.fields, f"{key}: name_by field {name} is not an allowlisted field"
            assert not ent.fields[name].permission and not ent.fields[name].whole_document, f"{key}.{name}"
        if ent.view_permission:
            assert ent.name_by, f"{key}: a queryable entity names its rows"


# ------------------------------------------------------------------ review round 1 (reviewer + security reviewer)


@contextmanager
def brand_scoped(db, brand_ids):
    """A WhatsApp linked-user turn keeps the contact's brand scope on the session (`access.build_context`)."""
    from app.models.base import get_brand_scope, set_brand_scope

    before = get_brand_scope(db)
    set_brand_scope(db, frozenset(brand_ids))
    try:
        yield
    finally:
        set_brand_scope(db, before)


def mk_warehouse(db) -> str:
    from app.models.inventory import Warehouse

    row = Warehouse(id=str(uuid.uuid4()), company_id=SORENTO, warehouse_code=unique_code("ZW"), warehouse_name="ZZT WH")
    db.add(row)
    db.flush()
    return row.id


def mk_line(db, order: Order, product: Product, warehouse_id: str, total: str) -> None:
    from app.models.order import OrderLine

    db.add(OrderLine(
        id=str(uuid.uuid4()), company_id=SORENTO, order_id=order.id, product_id=product.id,
        warehouse_id=warehouse_id, quantity=Decimal("1"), total=Decimal(total),
    ))
    db.flush()


def test_R1_a_company_b_only_user_reads_company_b_through_the_tool(db):
    """The tool stamps the reading user's own company (`run_as_user`), not whatever the session held before."""
    t = tag()
    company_b = mk_company_b(db)
    mk_orders(db, t, 2)
    for i in range(3):
        mk_order(db, t, 100 + i, company_id=company_b)
    db.flush()
    user = mk_user(db, ORDERS_VIEW, companies=(company_b,))
    out = tool(db, make_ctx(user), order_spec(t, fields=["order_number"]))
    assert out.status == "ok", out.message
    assert sorted(code(r) for r in out.data["rows"]) == [f"{t}-{100 + i}" for i in range(3)]


def test_R1_relation_fields_project_group_and_sort_and_stay_in_the_users_company(db):
    t = tag()
    company_b = mk_company_b(db)
    kohler, grohe = mk_supplier(db, f"{t} Kohler"), mk_supplier(db, f"{t} Grohe")
    for i, supplier in enumerate([kohler, kohler, grohe]):
        mk_po(db, f"{t}-PO-{i}", supplier)
    other = Supplier(id=str(uuid.uuid4()), company_id=company_b, supplier_code=unique_code("ZS"), supplier_name=f"{t} Kohler")
    db.add(other)
    db.flush()
    db.add(PurchaseOrder(id=str(uuid.uuid4()), company_id=company_b, po_number=f"{t}-PO-B", supplier_id=other.id))
    db.flush()
    user = mk_user(db, SCM_VIEW)
    mine = [{"field": "po_number", "op": "starts_with", "value": t}]
    rows = core(db, user, {
        "entity": "purchase_order", "fields": ["po_number", "supplier.name"], "filters": mine,
        "sort": [{"field": "supplier.code", "dir": "asc"}, {"field": "po_number", "dir": "asc"}],
    })
    assert rows["total"] == 3
    assert {r["supplier.name"] for r in rows["rows"]} == {f"{t} Kohler", f"{t} Grohe"}
    groups = core(db, user, {"entity": "purchase_order", "filters": mine, "group_by": ["supplier.name"]})
    assert {g["supplier.name"]: g["count"] for g in groups["groups"]} == {f"{t} Kohler": 2, f"{t} Grohe": 1}
    # a group on a relation field only still carries the root's company: company B's PO is not counted
    everything = core(db, user, {"entity": "purchase_order", "group_by": ["supplier.name"]})
    assert sum(g["count"] for g in everything["groups"] if g["supplier.name"] == f"{t} Kohler") == 2


def test_R1_a_deleted_order_is_not_counted(db):
    from datetime import datetime

    t = tag()
    mk_orders(db, t, 2)
    mk_order(db, t, 9, deleted_at=datetime(2026, 10, 1))
    db.flush()
    user = mk_user(db, ORDERS_VIEW)
    assert core(db, user, order_spec(t))["total"] == 2
    assert core(db, user, order_spec(t, aggregates=[{"fn": "count"}]))["groups"][0]["count"] == 2


def test_R1_a_brand_scoped_contact_sees_only_orders_with_its_brands_and_no_whole_order_totals(db):
    t = tag()
    chain_in, chain_out = mk_product_chain(db), mk_product_chain(db)
    product_in, product_out = mk_product(db, unique_code("ZIN"), chain_in), mk_product(db, unique_code("ZOUT"), chain_out)
    warehouse = mk_warehouse(db)
    shown, hidden = mk_order(db, t, 1, total_amount=Decimal("100")), mk_order(db, t, 2, total_amount=Decimal("500"))
    db.flush()
    mk_line(db, shown, product_in, warehouse, "100")
    mk_line(db, hidden, product_out, warehouse, "500")
    user = mk_user(db, ORDERS_VIEW)
    ctx = make_ctx(user)  # a WhatsApp linked-user turn: no panel principal
    with brand_scoped(db, {chain_in[2]}):
        rows = tool(db, ctx, order_spec(t, fields=["order_number"]), panel=False)
        assert rows.status == "ok", rows.message
        assert [code(r) for r in rows.data["rows"]] == [f"{t}-1"]
        totals = tool(db, ctx, order_spec(t, aggregates=[{"fn": "sum", "field": "total_amount"}]), panel=False)
        assert totals.status == "denied"
        listed = tool(db, ctx, order_spec(t, fields=["order_number", "total_amount"]), panel=False)
        assert listed.data["restricted"] == ["total_amount"]
    # unscoped, both orders and their totals
    out = core(db, user, order_spec(t, aggregates=[{"fn": "sum", "field": "total_amount"}]))
    assert out["groups"][0]["sum_total_amount"] == 600


def test_R1_a_brand_scoped_contact_sees_only_complaints_of_its_brands(db):
    from app.models.complaints import ComplaintProductLine

    t = tag()
    chain_in, chain_out = mk_product_chain(db), mk_product_chain(db)
    product_in, product_out = mk_product(db, unique_code("ZIN"), chain_in), mk_product(db, unique_code("ZOUT"), chain_out)
    owner = mk_contact(db, "QC")
    shown, hidden = mk_complaint(db, t, 1, owner_contact=owner), mk_complaint(db, t, 2, owner_contact=owner)
    db.add_all([
        ComplaintProductLine(id=str(uuid.uuid4()), complaint_id=shown.id, product_code=product_in.product_code),
        ComplaintProductLine(id=str(uuid.uuid4()), complaint_id=hidden.id, product_code=product_out.product_code),
    ])
    db.flush()
    user = mk_user(db, C_VIEW)
    spec = {"entity": "complaint", "fields": ["complaint_number"],
            "filters": [{"field": "complaint_number", "op": "starts_with", "value": t}]}
    with brand_scoped(db, {chain_in[2]}):
        out = tool(db, make_ctx(user), spec, panel=False)
    assert [code(r) for r in out.data["rows"]] == [f"{t}-1"]
    assert core(db, user, spec)["total"] == 2


def test_R1_timestamps_are_malaysian_days_in_filters_and_buckets(db):
    from datetime import datetime

    t = tag()
    # 17:00 UTC on 1 Oct is 01:00 on 2 Oct in Malaysia; 15:00 UTC on 1 Oct is 23:00 on 1 Oct.
    mk_order(db, t, 1, created_at=datetime(2026, 10, 1, 17, 0))
    mk_order(db, t, 2, created_at=datetime(2026, 10, 1, 15, 0))
    db.flush()
    user = mk_user(db, ORDERS_VIEW)
    days = core(db, user, order_spec(t, group_by=[{"field": "created_at", "bucket": "day"}]))
    assert {g["created_at_day"]: g["count"] for g in days["groups"]} == {"01/10/2026": 1, "02/10/2026": 1}
    def numbers(op, value):
        spec = order_spec(t, fields=["order_number"])
        spec["filters"].append({"field": "created_at", "op": op, "value": value})
        return sorted(code(r) for r in core(db, user, spec)["rows"])
    assert numbers("lte", "2026-10-01") == [f"{t}-2"]
    assert numbers("eq", "2026-10-02") == [f"{t}-1"]
    assert numbers("between", ["2026-10-01", "2026-10-01"]) == [f"{t}-2"]
    assert numbers("in", ["2026-10-02"]) == [f"{t}-1"]


def test_R1_the_statement_timeout_is_restored_after_a_query(db):
    before = db.execute(text("SHOW statement_timeout")).scalar()
    user = mk_user(db, ORDERS_VIEW)
    core(db, user, order_spec(tag()))
    assert db.execute(text("SHOW statement_timeout")).scalar() == before


def test_R1_a_value_that_does_not_fit_its_field_is_invalid_not_a_tool_failure(db):
    user = mk_user(db, ORDERS_VIEW)
    for field, value in (("order_date", "notadate"), ("total_amount", "abc")):
        spec = order_spec(tag())
        spec["filters"].append({"field": field, "op": "gt", "value": value})
        out = tool(db, make_ctx(user), spec)
        assert out.status == "invalid", (field, out.status, out.message)
    assert db.execute(text("SELECT 1")).scalar() == 1


def test_R1_contains_text_is_capped(db):
    user = mk_user(db, ORDERS_VIEW)
    out = refusal(db, user, {"entity": "order", "filters": [{"field": "debtor_name", "op": "contains", "value": "x" * 201}]})
    assert out.code == "invalid"


def test_R1_a_customer_scoped_whatsapp_contact_is_not_offered_the_tools(db):
    """Today every WhatsApp read of such a contact is narrowed to its linked customers; these tools cannot be."""
    from app.models.access import RespondContactCustomer
    from app.models.order import Customer

    contact = mk_contact(db, "QCS")
    customer = Customer(id=str(uuid.uuid4()), company_id=SORENTO, customer_code=unique_code("ZK"), customer_name="ZZT Cust")
    db.add(customer)
    db.flush()
    db.add(RespondContactCustomer(contact_id=str(contact.id), customer_id=customer.id))
    db.flush()
    user = mk_user(db, ORDERS_VIEW, contact=contact)
    ctx = dataclasses.replace(make_ctx(user), contact_pk=str(contact.id))
    names = {r.name for r in writes.permitted_user_reads(db, ctx)}
    assert not names & {"crm_query", "crm_describe"}
    assert tool(db, ctx, {"entity": "order"}, panel=False).status == "denied"
    # the same person on the panel answers as their screen does
    with panel_turn(user):
        assert {"crm_query", "crm_describe"} <= {r.name for r in writes.permitted_user_reads(db, ctx)}


def test_R1_a_lookup_row_of_another_company_is_not_read_through_a_relation(db):
    """A relation join carries the lookup's own company predicate: a PO pointing at another company's supplier
    (bad data, but the join must not trust it) shows no supplier name."""
    t = tag()
    company_b = mk_company_b(db)
    foreign = Supplier(id=str(uuid.uuid4()), company_id=company_b, supplier_code=unique_code("ZS"), supplier_name=f"{t} Foreign")
    db.add(foreign)
    db.flush()
    mk_po(db, f"{t}-PO-X", foreign)
    user = mk_user(db, SCM_VIEW)
    out = core(db, user, {
        "entity": "purchase_order", "fields": ["po_number", "supplier.name"],
        "filters": [{"field": "po_number", "op": "eq", "value": f"{t}-PO-X"}],
    })
    assert [r["supplier.name"] for r in out["rows"]] == [None]


def test_R2_a_brand_scoped_contact_cannot_read_a_complaints_full_product_code_list(db):
    """The header lists every line's code; the screen cuts it to the contact's brands, so here it is refused,
    in fields, filters and groups alike, and describe says so."""
    from app.models.complaints import ComplaintProductLine
    from app.services.assistant_registry.query import describe

    t = tag()
    chain_in, chain_out = mk_product_chain(db), mk_product_chain(db)
    product_in, product_out = mk_product(db, unique_code("ZIN"), chain_in), mk_product(db, unique_code("ZOUT"), chain_out)
    owner = mk_contact(db, "QC2")
    row = mk_complaint(db, t, 1, owner_contact=owner)
    row.product_code = f"{product_in.product_code},{product_out.product_code}"
    db.add_all([
        ComplaintProductLine(id=str(uuid.uuid4()), complaint_id=row.id, product_code=product_in.product_code),
        ComplaintProductLine(id=str(uuid.uuid4()), complaint_id=row.id, product_code=product_out.product_code),
    ])
    db.flush()
    user = mk_user(db, C_VIEW)
    ctx = make_ctx(user)
    mine = [{"field": "complaint_number", "op": "eq", "value": f"{t}-1"}]
    with brand_scoped(db, {chain_in[2]}):
        rows = tool(db, ctx, {"entity": "complaint", "fields": ["complaint_number", "product_code"], "filters": mine}, panel=False)
        assert rows.status == "ok" and rows.data["restricted"] == ["product_code"]
        assert "product_code" not in rows.data["rows"][0]
        oracle = mine + [{"field": "product_code", "op": "contains", "value": product_out.product_code}]
        assert tool(db, ctx, {"entity": "complaint", "filters": oracle}, panel=False).status == "denied"
        assert tool(db, ctx, {"entity": "complaint", "group_by": ["product_code"]}, panel=False).status == "denied"
        fields = writes.run_as_user(db, ctx, lambda u: describe(db, u["id"], "complaint"))["fields"]
        assert {f["field"]: f.get("restricted", False) for f in fields}["product_code"] is True
    full = core(db, user, {"entity": "complaint", "fields": ["product_code"], "filters": mine})
    assert full["rows"][0]["product_code"] == row.product_code


def test_R2_a_failed_customer_scope_lookup_refuses_and_leaves_the_session_usable(db, monkeypatch):
    import app.services.contact_customer_scope as ccs

    def broken(session, contact_id):
        session.execute(text("SELECT 1/0"))

    monkeypatch.setattr(ccs, "contact_customer_scope", broken)
    user = mk_user(db, ORDERS_VIEW)
    names = {r.name for r in writes.permitted_user_reads(db, make_ctx(user))}
    assert not names & {"crm_query", "crm_describe"}
    assert db.execute(text("SELECT 1")).scalar() == 1


def test_R2_describe_leaves_out_a_relation_whose_module_is_off(db, monkeypatch):
    from app.modules.runtime import guards
    from app.services.assistant_registry.query import describe

    real = guards.module_blocked
    monkeypatch.setattr(guards, "module_blocked", lambda d, u, key: key == "procurement" or real(d, u, key))
    monkeypatch.setitem(
        __import__("app.services.assistant_registry", fromlist=["ENTITIES"]).ENTITIES, "supplier",
        dataclasses.replace(__import__("app.services.assistant_registry", fromlist=["ENTITIES"]).ENTITIES["supplier"], module="procurement"),
    )
    user = mk_user(db, SCM_VIEW)
    out = writes.run_as_user(db, make_ctx(user), lambda u: describe(db, u["id"], "purchase_order"))
    assert "supplier" not in out["relations"]


# ------------------------------------------------------------------ crew browser pass on 826964f2 (5 Nov)


def test_R3_describe_says_which_order_field_is_the_lists_agent_and_its_date(db):
    """'Per agent' was grouped by salesman while the Delivery Orders list's Agent column is `agent`; describe must
    say which field is which, and which date the list filters on."""
    from app.services.assistant_registry.query import describe

    user = mk_user(db, ORDERS_VIEW)
    fields = {f["field"]: f for f in writes.run_as_user(db, make_ctx(user), lambda u: describe(db, u["id"], "order"))["fields"]}
    assert "Agent column" in fields["agent"].get("note", "")
    assert "per agent" in fields["agent"]["note"]
    assert "not the list's Agent" in fields["salesman"].get("note", "")
    assert "Order date" in fields["order_date"].get("note", "")
    assert "not the order date" in fields["created_at"].get("note", "")


def test_R3_per_agent_counts_equal_the_delivery_orders_lists_own_filter(db):
    """Step 7: the list filtered on Agent + Order date 1 to 31 Oct + not cancelled. Each per-agent count from
    crm_query must equal what the list's own search (`ListQuerySearchService`, the Filters dialog's path) returns
    for that agent, over rows that differ on every axis that could split them."""
    from datetime import datetime

    from app.schemas.list_query import FilterCondition, FilterGroup, ListSearchRequest
    from app.services.list_query_metadata_sync_service import ListQueryMetadataSyncService
    from app.services.list_query_registry import ADAPTERS
    from app.services.list_query_search_service import ListQuerySearchService

    ListQueryMetadataSyncService(db).sync_resource(ADAPTERS["orders"])
    t = tag()
    a, b = f"{t}A", f"{t}B"
    rows = [
        # (agent, salesman, order_date, created_at, cancelled, deleted)
        (a, a, date(2026, 10, 1), datetime(2026, 10, 1, 2), False, False),
        (a, b, date(2026, 10, 31), datetime(2026, 10, 31, 20), False, False),  # created 1 Nov in Malaysia
        (a, a, date(2026, 11, 1), datetime(2026, 10, 30, 2), False, False),  # created in Oct, dated Nov
        (a, a, date(2026, 10, 15), datetime(2026, 10, 15, 2), True, False),  # cancelled
        (a, a, date(2026, 10, 16), datetime(2026, 10, 16, 2), False, True),  # deleted
        (b, a, date(2026, 10, 20), datetime(2026, 10, 20, 2), False, False),
        (b, a, date(2026, 9, 30), datetime(2026, 10, 2, 2), False, False),  # dated Sep, created in Oct
    ]
    for i, (agent, salesman, day, created, cancelled, deleted) in enumerate(rows):
        mk_order(
            db, t, i, agent=agent, salesman=salesman, order_date=day, created_at=created, is_cancelled=cancelled,
            deleted_at=datetime(2026, 10, 17) if deleted else None,
        )
    db.flush()
    user = mk_user(db, ORDERS_VIEW)
    october = [
        {"field": "debtor_code", "op": "eq", "value": t},
        {"field": "order_date", "op": "between", "value": ["2026-10-01", "2026-10-31"]},
        {"field": "is_cancelled", "op": "eq", "value": False},
    ]
    groups = core(db, user, {"entity": "order", "filters": october, "group_by": ["agent"]})["groups"]
    bot = {g["agent"]: g["count"] for g in groups}
    assert bot == {a: 2, b: 1}

    def listed(agent: str) -> int:
        conditions = [
            FilterCondition(field_key="debtor_code", op="eq", value=t),
            FilterCondition(field_key="agent", op="eq", value=agent),
            FilterCondition(field_key="order_date", op="gte", value="2026-10-01"),
            FilterCondition(field_key="order_date", op="lte", value="2026-10-31"),
            FilterCondition(field_key="is_cancelled", op="eq", value=False),
        ]
        req = ListSearchRequest(resource="orders", filter=FilterGroup(op="and", children=conditions), page=1, limit=100)
        out = writes.run_as_user(db, make_ctx(user), lambda u: ListQuerySearchService(db).search(req))
        return int(out["pagination"]["total"])

    assert {agent: listed(agent) for agent in (a, b)} == bot


# ------------------------------------------------------------------ crew browser pass on faf6f91b + owner rulings (5 Nov)


def test_R4_the_query_tool_says_delivery_order_counts_are_its_job_not_the_sales_reports():
    """Step 3 went to the sales report in 2 of 3 runs: the description must claim DO counts per agent."""
    text = writes.USER_READS["crm_query"].schema["function"]["description"].lower()
    assert "delivery order" in text and "per agent" in text
    assert "not the sales report" in text


def test_R4_the_reply_is_unchanged_without_a_query_result():
    from app.services.chatbot.agent import loop

    reply, _ = loop.final_reply({"text": "CB600-NL is in stock."}, [], [], ledger={})
    assert reply == "CB600-NL is in stock."


def test_R4_dates_come_back_as_dd_mm_yyyy_and_timestamps_in_malaysian_time(db):
    from datetime import datetime

    t = tag()
    mk_order(db, t, 1, order_date=date(2026, 10, 5), created_at=datetime(2026, 10, 1, 17, 30))
    db.flush()
    user = mk_user(db, ORDERS_VIEW)
    row = core(db, user, order_spec(t, fields=["order_date", "created_at"]))["rows"][0]
    assert row["order_date"] == "05/10/2026"
    assert row["created_at"] == "02/10/2026 01:30"
    months = core(db, user, order_spec(t, group_by=[{"field": "order_date", "bucket": "month"}]))["groups"]
    assert months[0]["order_date_month"] == "01/10/2026"
    # a filter value written the same way is read as a date
    spec = order_spec(t, fields=["order_number"])
    spec["filters"].append({"field": "order_date", "op": "eq", "value": "05/10/2026"})
    assert core(db, user, spec)["total"] == 1




# ------------------------------------------------------------------ crew pass on f54a8859: decided in the tool output (5 Nov)

_ISO = __import__("re").compile(r"(?<![\w-])\d{4}-\d{2}-\d{2}(?![\w-])")


def _no_iso(value) -> list[str]:
    return _ISO.findall(json.dumps(value, default=str))


def test_R5_a_row_carries_one_label_code_colon_name_and_no_separate_code_or_name(db):
    chain = mk_product_chain(db)
    t = tag()
    for i, price in enumerate(("100.00", "300.00", "200.00")):
        row = mk_product(db, f"{t}-{i}", chain)
        row.list_price = Decimal(price)
    db.flush()
    user = mk_user(db, PRODUCTS_VIEW)
    out = core(db, user, {
        "entity": "product", "fields": ["product_code", "product_name", "list_price"],
        "filters": [{"field": "product_code", "op": "starts_with", "value": t}],
        "sort": [{"field": "list_price", "dir": "desc"}], "limit": 2,
    })
    assert [(r["label"], r["list_price"]) for r in out["rows"]] == [(f"{t}-1: ZZT {t}-1", 300.0), (f"{t}-2: ZZT {t}-2", 200.0)]
    for row in out["rows"]:
        assert "product_code" not in row and "product_name" not in row
    # an entity named by one field: the label is that value
    supplier = mk_supplier(db, f"{t} Sup")
    mk_po(db, f"{t}-PO", supplier)
    po = core(db, mk_user(db, SCM_VIEW), {"entity": "purchase_order", "fields": ["status"],
                                           "filters": [{"field": "po_number", "op": "eq", "value": f"{t}-PO"}]})
    assert po["rows"][0]["label"] == f"{t}-PO"


def test_R5_an_order_result_carries_its_period_and_scope_note_in_display_form(db):
    t = tag()
    mk_order(db, t, 1, order_date=date(2026, 10, 3), agent="A")
    mk_order(db, t, 2, order_date=date(2026, 10, 9), agent="A", is_cancelled=True)
    db.flush()
    user = mk_user(db, ORDERS_VIEW)
    spec = order_spec(t, group_by=["agent"], aggregates=[{"fn": "count"}])
    spec["filters"].append({"field": "order_date", "op": "between", "value": ["2026-10-01", "2026-10-31"]})
    out = core(db, user, spec)
    assert out["groups"] == [{"agent": "A", "count": 1}]
    assert out["period_display"] == "Order date 01/10/2026 to 31/10/2026"
    assert out["scope_note"] == "Cancelled orders excluded."
    assert _no_iso(out) == []
    # asked for cancelled ones: no exclusion note
    asked = order_spec(t, fields=["order_number"])
    asked["filters"].append({"field": "is_cancelled", "op": "eq", "value": True})
    out = core(db, user, asked)
    assert out["total"] == 1 and out.get("scope_note") is None and out.get("period_display") is None


def test_R5_no_result_carries_a_raw_iso_date_anywhere(db):
    from datetime import datetime

    t = tag()
    mk_order(db, t, 1, order_date=date(2026, 10, 3), created_at=datetime(2026, 10, 3, 5))
    db.flush()
    user = mk_user(db, ORDERS_VIEW)
    for spec in (
        order_spec(t),
        order_spec(t, fields=["order_date", "created_at", "estimated_delivery_date"]),
        order_spec(t, group_by=["order_date", {"field": "created_at", "bucket": "week"}]),
        {**order_spec(t), "filters": order_spec(t)["filters"] + [{"field": "created_at", "op": "gte", "value": "2026-10-01"}]},
    ):
        assert _no_iso(core(db, user, spec)) == [], spec
