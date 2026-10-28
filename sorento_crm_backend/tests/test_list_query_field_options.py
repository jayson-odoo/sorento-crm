"""FILTER-MULTISELECT PR7 (design 4.1): the advanced filter dialog's pick lists.

`GET /api/v1/list-query/{resource}/fields/{field_key}/options?query=&page=&limit=` answers
`{data: [{value, label}], pagination}`: the DISTINCT values of the field over the resource's own
company-scoped base query, labelled through the field's relation. The metadata route marks those
fields `option_source == {"kind": "distinct"}`. Also: Import jobs Type / Status, Import logs Entity type
and Workflow submissions State code take several values. Red first; Postgres only; every row seeded here.
`limit` on the options route is an assumption of this file (the design names `query` and `page`).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.company import Company
from app.models.import_log import ImportLog
from app.models.job import ImportJob
from app.models.list_query_metadata import ListQueryField, ListQueryResource
from app.models.order import Customer, Order, OrderStatus
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.workflow_forms import WorkflowFormDefinition, WorkflowFormVersion, WorkflowSubmission
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.user_service import UserPermissionService
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

SORENTO = DEFAULT_COMPANY_ID
MOCHA = "00000000-0000-0000-0000-000000000002"
LQ = "/api/v1/list-query"


def _uid() -> str:
    return str(uuid.uuid4())


def _opts(client, resource, field, **params):
    return client.get(f"{LQ}/{resource}/fields/{field}/options", params=params)


def _pairs(resp):
    assert resp.status_code == 200, resp.text
    return {(o["value"], o["label"]) for o in resp.json()["data"]}


@pytest.fixture
def db():
    with blank_session() as session:
        session.add(Company(id=MOCHA, name="Mocha", code=unique_code("MCH")[:20]))
        session.flush()
        yield session


def _field(db, resource, key, compile_key, dtype="uuid"):
    res = db.query(ListQueryResource).filter_by(resource_key=resource).first()
    if res is None:
        res = ListQueryResource(id=_uid(), resource_key=resource, display_name=resource)
        db.add(res)
        db.flush()
    db.add(ListQueryField(
        id=_uid(), resource_id=res.id, field_key=key, label=key, data_type=dtype, compile_key=compile_key,
        allowed_operators=["eq", "in"], filterable=True, exportable=True,
    ))
    db.flush()


@pytest.fixture
def orders(db):
    for key, ck, dt in (
        ("order_status_id", "order.order_status_id", "uuid"), ("customer_id", "order.customer_id", "uuid"),
        ("order_type", "order.order_type", "string"), ("agent", "order.agent", "string"),
        ("remarks", "order.remarks", "string"),
    ):
        _field(db, "orders", key, ck, dt)
    st = {}
    for k, company in (("a", SORENTO), ("b", SORENTO), ("unused", SORENTO), ("mocha", MOCHA)):
        row = OrderStatus(id=_uid(), status_code=unique_code("ST")[:50], status_name=f"ZZT Status {k}")
        db.add(row)
        st[k] = row
    cu = {}
    for k, company in (("a", SORENTO), ("b", SORENTO), ("mocha", MOCHA)):
        row = Customer(id=_uid(), company_id=company, customer_code=unique_code("C")[:50], customer_name=f"ZZT Cust {k}")
        db.add(row)
        cu[k] = row
    db.flush()
    spec = [
        ("a", "a", "ZZT-TYPE-1", "ZZT Agent One", SORENTO), ("a", "b", "ZZT-TYPE-2", "ZZT Agent Two", SORENTO),
        ("b", "a", "ZZT-TYPE-3", "ZZT Agent One", SORENTO),
        ("mocha", "mocha", "ZZT-TYPE-MOCHA", "ZZT Agent Mocha", MOCHA),
    ]
    for s, c, t, ag, company in spec:
        db.add(Order(id=_uid(), company_id=company, order_number=unique_code("SO")[:50], order_status_id=st[s].id,
                     customer_id=cu[c].id, order_type=t, agent=ag, remarks="x"))
    db.commit()
    return dict(st=st, cu=cu)


@pytest.fixture
def allow(monkeypatch):
    state = {"view": True}
    return state


@pytest.fixture
def client(db, monkeypatch, allow):
    with open_client(db, monkeypatch, scope=frozenset({SORENTO})) as (c, _a):
        monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: allow["view"])
        yield c


# ---- 1. distinct options ---------------------------------------------------------------------------

def test_order_status_options_are_distinct_and_labelled_by_name(client, orders):
    st = orders["st"]
    got = _pairs(_opts(client, "orders", "order_status_id"))
    assert got == {(st["a"].id, "ZZT Status a"), (st["b"].id, "ZZT Status b")}


def test_customer_options_label_is_the_customer_name(client, orders):
    cu = orders["cu"]
    assert _pairs(_opts(client, "orders", "customer_id")) == {(cu["a"].id, "ZZT Cust a"), (cu["b"].id, "ZZT Cust b")}


def test_string_fields_use_the_value_as_the_label(client, orders):
    assert _pairs(_opts(client, "orders", "agent")) == {("ZZT Agent One", "ZZT Agent One"), ("ZZT Agent Two", "ZZT Agent Two")}
    assert _pairs(_opts(client, "orders", "order_type")) == {(t, t) for t in ("ZZT-TYPE-1", "ZZT-TYPE-2", "ZZT-TYPE-3")}


def test_query_narrows_by_label_and_page_pages(client, orders):
    assert _pairs(_opts(client, "orders", "order_type", query="TYPE-2")) == {("ZZT-TYPE-2", "ZZT-TYPE-2")}
    first = _opts(client, "orders", "order_type", limit=2, page=1)
    second = _opts(client, "orders", "order_type", limit=2, page=2)
    assert first.status_code == 200 and second.status_code == 200, first.text
    assert len(first.json()["data"]) == 2 and len(second.json()["data"]) == 1
    assert first.json()["pagination"]["total"] == 3
    assert {o["value"] for o in first.json()["data"]} | {o["value"] for o in second.json()["data"]} == {
        "ZZT-TYPE-1", "ZZT-TYPE-2", "ZZT-TYPE-3"
    }


def test_products_category_and_brand_options(db, client):
    _field(db, "products", "category_id", "product.category_id")
    _field(db, "products", "brand_id", "product.brand_id")
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("U")[:20], uom_name="Unit")
    cat = ProductCategory(id=_uid(), category_code=unique_code("CAT")[:50], category_name="ZZT Category", company_id=SORENTO)
    brand = Brand(id=_uid(), brand_code=unique_code("B")[:50], brand_name="ZZT Brand", company_id=SORENTO)
    db.add_all([uom, cat, brand])
    db.flush()
    for i in range(2):
        db.add(Product(id=_uid(), company_id=SORENTO, product_code=unique_code(f"P{i}")[:50], product_name=f"ZZT P{i}",
                       category_id=cat.id, brand_id=brand.id, base_uom_id=uom.id, list_price=1))
    db.commit()
    assert _pairs(_opts(client, "products", "category_id")) == {(cat.id, "ZZT Category")}
    assert _pairs(_opts(client, "products", "brand_id")) == {(brand.id, "ZZT Brand")}


def test_workflow_submission_definition_options_use_the_definition_name(db, client):
    _field(db, "workflow_form_submissions", "definition_id", "sub.definition_id")
    d1 = WorkflowFormDefinition(id=_uid(), code=unique_code("D")[:50], name="ZZT Definition One")
    d2 = WorkflowFormDefinition(id=_uid(), code=unique_code("D")[:50], name="ZZT Definition Two")
    db.add_all([d1, d2])
    db.flush()
    versions = {}
    for d in (d1, d2):
        versions[d.id] = WorkflowFormVersion(id=_uid(), definition_id=d.id, version_number=1, schema={})
        db.add(versions[d.id])
    db.flush()
    for d in (d1, d1, d2):
        db.add(WorkflowSubmission(id=_uid(), definition_id=d.id, version_id=versions[d.id].id, current_state_code="draft"))
    db.commit()
    assert _pairs(_opts(client, "workflow_form_submissions", "definition_id")) == {
        (d1.id, "ZZT Definition One"), (d2.id, "ZZT Definition Two")
    }


# ---- 2. scope and permission -----------------------------------------------------------------------

def test_another_companys_values_never_appear(client, orders):
    st, cu = orders["st"], orders["cu"]
    assert st["mocha"].id not in {v for v, _ in _pairs(_opts(client, "orders", "order_status_id"))}
    assert cu["mocha"].id not in {v for v, _ in _pairs(_opts(client, "orders", "customer_id"))}
    assert "ZZT-TYPE-MOCHA" not in {v for v, _ in _pairs(_opts(client, "orders", "order_type"))}
    assert "ZZT Agent Mocha" not in {v for v, _ in _pairs(_opts(client, "orders", "agent"))}
    assert _opts(client, "orders", "order_type", query="MOCHA").json()["data"] == []


def test_a_caller_without_view_permission_gets_403(client, orders, allow):
    allow["view"] = False
    assert _opts(client, "orders", "order_status_id").status_code == 403


# ---- 3. no options / unknown -------------------------------------------------------------------------

def test_a_field_without_options_and_unknown_things_are_404(client, orders):
    assert _opts(client, "orders", "order_status_id").status_code == 200  # the route exists; the 404s below are its own
    assert _opts(client, "orders", "remarks").status_code == 404
    assert _opts(client, "orders", "no_such_field").status_code == 404
    assert _opts(client, "no_such_resource", "order_status_id").status_code == 404


# ---- 4. metadata ---------------------------------------------------------------------------------------

def test_metadata_marks_the_pick_list_fields(client, orders):
    resp = client.get(f"{LQ}/resources/orders/fields")
    assert resp.status_code == 200, resp.text
    by_key = {f["field_key"]: f for f in resp.json()}
    assert by_key["order_status_id"]["option_source"] == {"kind": "distinct"}
    assert by_key["remarks"]["option_source"] is None


# ---- 5. text boxes turned into multi: Import jobs, Import logs, Workflow submissions -------------------------

def test_import_jobs_type_and_status_take_several(db, client):
    from app.models.user import User

    actor_id = db.query(User).filter(User.name == "ZZT Actor").one().id
    tags = {}
    for key, jtype, status in (("a", "ZZT_TYPE_A", "finished"), ("b", "ZZT_TYPE_B", "failed"), ("c", "ZZT_TYPE_C", "finished")):
        job = ImportJob(id=uuid.uuid4(), job_id=f"zzt-{key}-{_uid()[:6]}", job_type=jtype, user_id=actor_id, status=status,
                        company_id=uuid.UUID(SORENTO))
        db.add(job)
        tags[key] = str(job.id)
    db.commit()

    def ids(*pairs):
        resp = get(client, "/api/v1/system/jobs", [("limit", 100), *pairs])
        assert resp.status_code == 200, resp.text
        return {j["id"] for j in resp.json()["data"]} & set(tags.values())

    assert ids(("job_type", "ZZT_TYPE_A")) == {tags["a"]}
    assert ids(("job_type", "ZZT_TYPE_A,ZZT_TYPE_B")) == {tags["a"], tags["b"]}
    assert ids(("job_type", "ZZT_TYPE_A"), ("job_type", "ZZT_TYPE_C")) == {tags["a"], tags["c"]}
    assert ids(("status", "finished,failed")) == set(tags.values())
    assert ids(("status", "failed")) == {tags["b"]}
    assert ids(("status", "failed,finished"), ("job_type", "ZZT_TYPE_A,ZZT_TYPE_B")) == {tags["a"], tags["b"]}
    assert get(client, "/api/v1/system/jobs", [("status", "finished,bogus")]).status_code in (400, 422)


def test_import_logs_entity_type_takes_several(db, client):
    ids = {}
    for key in "abc":
        log = ImportLog(import_session_id=f"zzt-{key}-{_uid()[:6]}", entity_type=f"zzt_entity_{key}", entity_table="zzt",
                        import_type="create", company_id=SORENTO)
        db.add(log)
        db.flush()
        ids[key] = str(log.id)
    db.commit()

    def got(*pairs):
        resp = get(client, "/api/v1/system/import-logs", [("limit", 100), *pairs])
        assert resp.status_code == 200, resp.text
        return {r["id"] for r in resp.json()["data"]} & set(ids.values())

    assert got(("entity_type", "zzt_entity_a")) == {ids["a"]}
    assert got(("entity_type", "zzt_entity_a,zzt_entity_c")) == {ids["a"], ids["c"]}
    assert got(("entity_type", "zzt_entity_b"), ("entity_type", "zzt_entity_c")) == {ids["b"], ids["c"]}


def test_workflow_submissions_state_code_takes_several(db, client):
    d = WorkflowFormDefinition(id=_uid(), code=unique_code("D")[:50], name="ZZT Def")
    db.add(d)
    db.flush()
    v = WorkflowFormVersion(id=_uid(), definition_id=d.id, version_number=1, schema={})
    db.add(v)
    db.flush()
    ids = {}
    for code in ("zzt_draft", "zzt_review", "zzt_done"):
        s = WorkflowSubmission(id=_uid(), definition_id=d.id, version_id=v.id, current_state_code=code)
        db.add(s)
        ids[code] = s.id
    db.commit()

    def got(*pairs):
        resp = get(client, "/api/v1/workflow-forms/submissions", [("limit", 100), ("definition_id", d.id), *pairs])
        assert resp.status_code == 200, resp.text
        return {r["id"] for r in resp.json()["data"]}

    assert got(("state_code", "zzt_draft")) == {ids["zzt_draft"]}
    assert got(("state_code", "zzt_draft,zzt_done")) == {ids["zzt_draft"], ids["zzt_done"]}
    assert got(("state_code", "zzt_review"), ("state_code", "zzt_done")) == {ids["zzt_review"], ids["zzt_done"]}
