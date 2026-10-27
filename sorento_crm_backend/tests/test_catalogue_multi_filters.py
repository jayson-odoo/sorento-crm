"""FILTER-MULTISELECT PR4: Products (Category, Brand), Certificates (Validity, Scheme, Status), the
Spec verification worklist (State, Class) and a spec's "Seen in products" list (Value, Class, Source)
take several values (OR within a filter, AND across). Comma-joined, repeated and single all read.
Red first; Postgres only; rows seeded here into a blank schema.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.certificate import Certificate, CertificateRevision
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from tests._multi_filter_client import get, ok_ids, open_client
from tests._pg_fixture import blank_session, unique_code

PRODUCTS = "/api/v1/master-data/products/"
CERTS = "/api/v1/master-data/certificates/"
WORKLIST = "/api/v1/master-data/product-specifications/verification/worklist"
SPEC_REGISTRY = "/api/v1/master-data/spec-registry"


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


# ---- Products: Category and Brand -------------------------------------------------------------------------

@pytest.fixture
def products(db):
    tag = unique_code("PRD", alpha=True)
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("uom"), uom_name="ZZT uom")
    cats = [ProductCategory(id=_uid(), category_code=unique_code(f"c{i}"), category_name=f"ZZT cat {i}") for i in range(3)]
    brands = [Brand(id=_uid(), brand_code=unique_code(f"b{i}"), brand_name=f"ZZT brand {i}") for i in range(3)]
    db.add(uom)
    db.add_all(cats + brands)
    db.flush()
    rows = {}
    # (category index, brand index)
    for key, (ci, bi) in {"a": (0, 0), "b": (1, 1), "c": (2, 2), "d": (0, 1)}.items():
        row = Product(
            id=_uid(), product_code=f"{tag}-{key}", product_name=f"{tag} {key}", category_id=cats[ci].id,
            brand_id=brands[bi].id, base_uom_id=uom.id, list_price=Decimal("1.00"),
        )
        db.add(row)
        db.flush()
        rows[key] = row
    return dict(tag=tag, cats=cats, brands=brands, **rows)


def _products(client, s, pairs):
    return ok_ids(get(client, PRODUCTS, [("limit", 200), ("query", s["tag"]), *pairs]))


def test_products_category_union_and_single(client, products):
    s = products
    c0, c1, c2 = (c.id for c in s["cats"])
    assert _products(client, s, [("category_id", c0)]) == {s["a"].id, s["d"].id}
    assert _products(client, s, [("category_id", f"{c1},{c2}")]) == {s["b"].id, s["c"].id}
    assert _products(client, s, [("category_id", c1), ("category_id", c2)]) == {s["b"].id, s["c"].id}


def test_products_category_sentinel_all_is_not_a_filter(client, products):
    s = products
    assert _products(client, s, [("category_id", "all")]) == {s[k].id for k in "abcd"}


def test_products_brand_guard_union(client, products):
    s = products
    b0, b1, b2 = (b.id for b in s["brands"])
    assert _products(client, s, [("brand_id", f"{b0},{b2}")]) == {s["a"].id, s["c"].id}
    assert _products(client, s, [("brand_id", b1)]) == {s["b"].id, s["d"].id}


def test_products_category_and_brand_are_and_ed(client, products):
    s = products
    c0, c1, _c2 = (c.id for c in s["cats"])
    b0, b1, _b2 = (b.id for b in s["brands"])
    assert _products(client, s, [("category_id", f"{c0},{c1}"), ("brand_id", b1)]) == {s["b"].id, s["d"].id}
    assert _products(client, s, [("category_id", f"{c0},{c1}"), ("brand_id", b0)]) == {s["a"].id}


# ---- Certificates: Validity (guard), Scheme, Status ------------------------------------------------------

def _cert(db, key, scheme, status, valid_until):
    row = Certificate(
        id=_uid(), scheme=scheme, certificate_number=unique_code(key), status=status, title=f"ZZT {key}",
    )
    db.add(row)
    db.flush()
    if valid_until is not None:
        rev = CertificateRevision(
            id=_uid(), certificate_id=row.id, revision_no=1, is_current=True, valid_until=valid_until,
        )
        db.add(rev)
        db.flush()
        row.current_revision_id = rev.id
        db.flush()
    return row


@pytest.fixture
def certs(db):
    today = date.today()
    return {
        "a": _cert(db, "a", "PPS", "active", today + timedelta(days=400)),   # valid
        "b": _cert(db, "b", "SPAN", "active", today - timedelta(days=100)),  # expired
        "c": _cert(db, "c", "PPS", "archived", None),                        # unknown
        "d": _cert(db, "d", "ZZX", "active", today + timedelta(days=400)),   # valid
    }


def _certs(client, pairs):
    return ok_ids(get(client, CERTS, [("limit", 200), *pairs]))


def test_certificates_validity_guard_forms(client, certs):
    s = certs
    assert _certs(client, [("validity_state", "expired,unknown")]) == {s["b"].id, s["c"].id}
    assert _certs(client, [("validity_state", "valid")]) == {s["a"].id, s["d"].id}


def test_certificates_validity_repeated(client, certs):
    s = certs
    assert _certs(client, [("validity_state", "expired"), ("validity_state", "unknown")]) == {s["b"].id, s["c"].id}


def test_certificates_validity_unknown_state_refused(client, certs):
    resp = get(client, CERTS, [("validity_state", "valid,nonsense")])
    assert resp.status_code in (400, 422), resp.text


def test_certificates_scheme_union_and_single(client, certs):
    s = certs
    assert _certs(client, [("scheme", "PPS")]) == {s["a"].id, s["c"].id}
    assert _certs(client, [("scheme", "SPAN,ZZX")]) == {s["b"].id, s["d"].id}
    assert _certs(client, [("scheme", "pps"), ("scheme", "span")]) == {s["a"].id, s["b"].id, s["c"].id}


def test_certificates_status_union_single_and_unknown(client, certs):
    s = certs
    assert _certs(client, [("status", "archived")]) == {s["c"].id}
    assert _certs(client, [("status", "active,archived")]) == {s["a"].id, s["b"].id, s["c"].id, s["d"].id}
    assert _certs(client, [("status", "archived"), ("status", "active")]) == {s["a"].id, s["b"].id, s["c"].id, s["d"].id}
    resp = get(client, CERTS, [("status", "active,deleted")])
    assert resp.status_code in (400, 422), resp.text


def test_certificates_filters_and_across(client, certs):
    s = certs
    got = _certs(client, [("scheme", "PPS,SPAN"), ("status", "active"), ("validity_state", "valid,expired")])
    assert got == {s["a"].id, s["b"].id}


# ---- Spec verification worklist: State and Class ---------------------------------------------------------

@pytest.fixture
def worklist(db):
    from app.services.product_spec_derivation import derive_for_code
    from app.services.product_spec_write import apply_spec_values
    from app.services import product_spec_verification as psv

    tag = unique_code("SPV", alpha=True)
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("uom"), uom_name="ZZT uom")
    db.add(uom)
    out = dict(tag=tag, classes={})
    codes = {}
    for key in ("u", "v", "r"):
        label = f"{tag} class {key}"
        cat = ProductCategory(id=_uid(), category_code=unique_code(key), category_name=f"ZZT {key}", class_label=label)
        db.add(cat)
        db.flush()
        code = f"{tag}-{key}"
        db.add(Product(
            id=_uid(), product_code=code, product_name=code, description="ZZT item", category_id=cat.id,
            base_uom_id=uom.id, list_price=Decimal("1.00"),
        ))
        db.flush()
        codes[key] = code
        out["classes"][key] = label
    db.commit()
    user = {"id": _uid(), "email": "zzt-verifier@zzt.test", "name": "ZZT Verifier"}
    for key in ("v", "r"):
        derive_for_code(db, codes[key], commit=True)
        h = psv.current_values_hash(db, codes[key])
        res = psv.verify_codes_bulk(db, [{"product_code": codes[key], "values_hash": h}], actor=user)
        assert res[0]["outcome"] == "verified", res
    apply_spec_values(db, codes["r"], [{"spec_key": "material", "op": "set", "value": "brass"}], actor=user)
    db.commit()
    out["codes"] = codes
    return out


def _wl(client, s, pairs):
    resp = get(client, WORKLIST, [("limit", 100), ("query", s["tag"]), ("include_discontinued", "true"), *pairs])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _wl_codes(body):
    return {row["product_code"] for row in body["data"]}


def test_worklist_seed_is_in_three_states(client, worklist):
    s = worklist
    body = _wl(client, s, [])
    assert body["summary"]["unverified"] == 1 and body["summary"]["verified"] == 1
    assert body["summary"]["needs_reverify"] == 1


def test_worklist_state_single_still_works(client, worklist):
    s = worklist
    assert _wl_codes(_wl(client, s, [("state", "verified")])) == {s["codes"]["v"]}


def test_worklist_state_union_total_and_unchanged_summary(client, worklist):
    s = worklist
    body = _wl(client, s, [("state", "verified,needs_reverify")])
    assert _wl_codes(body) == {s["codes"]["v"], s["codes"]["r"]}
    assert body["pagination"]["total"] == 2
    # the summary counts the set minus the state filter, so it still reads all three
    assert body["summary"] == {"total": 3, "verified": 1, "needs_reverify": 1, "unverified": 1}


def test_worklist_state_repeated(client, worklist):
    s = worklist
    body = _wl(client, s, [("state", "unverified"), ("state", "needs_reverify")])
    assert _wl_codes(body) == {s["codes"]["u"], s["codes"]["r"]}
    assert body["pagination"]["total"] == 2


def test_worklist_unknown_state_refused(client, worklist):
    resp = get(client, WORKLIST, [("state", "verified,sideways")])
    assert resp.status_code == 422, resp.text


def test_worklist_class_union_and_summary_counts_both_classes(client, worklist):
    s = worklist
    body = _wl(client, s, [("class_label", f"{s['classes']['u']},{s['classes']['v']}")])
    assert _wl_codes(body) == {s["codes"]["u"], s["codes"]["v"]}
    assert body["pagination"]["total"] == 2
    assert body["summary"] == {"total": 2, "verified": 1, "needs_reverify": 0, "unverified": 1}


def test_worklist_class_single_and_repeated(client, worklist):
    s = worklist
    assert _wl_codes(_wl(client, s, [("class_label", s["classes"]["r"])])) == {s["codes"]["r"]}
    body = _wl(client, s, [("class_label", s["classes"]["u"]), ("class_label", s["classes"]["r"])])
    assert _wl_codes(body) == {s["codes"]["u"], s["codes"]["r"]}


def test_worklist_state_and_class_are_and_ed(client, worklist):
    s = worklist
    body = _wl(client, s, [
        ("state", "verified,needs_reverify"),
        ("class_label", f"{s['classes']['u']},{s['classes']['r']}"),
    ])
    assert _wl_codes(body) == {s["codes"]["r"]}
    assert body["pagination"]["total"] == 1


# ---- Spec "Seen in products": Value, Class, Source -------------------------------------------------------

@pytest.fixture
def seen(db, monkeypatch):
    from app.services.user_service import UserPermissionService

    # this route reads the caller's permission slugs directly (any-of), not check_user_has_permission
    monkeypatch.setattr(
        UserPermissionService, "get_user_permission_slugs", lambda self, uid: ["master_data.spec_registry.view"]
    )
    tag = unique_code("SEN", alpha=True)
    key = "zzt_finish"
    db.add(ProductSpecRegistry(
        spec_key=key, label="ZZT finish", data_type="text", allowed_values=[], synonyms={}, user_synonyms={},
        user_values=[], applies_when={}, is_active=True, source="user",
    ))
    cat = ProductCategory(id=_uid(), category_code=unique_code("c"), category_name="ZZT cat")
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("uom"), uom_name="ZZT uom")
    db.add_all([cat, uom])
    db.flush()
    rows = {}
    spec = {
        "a": ("matte", "Sink", "derived"),
        "b": ("gloss", "Basin", "human"),
        "c": ("satin", "Tap", "derived"),
        "d": ("matte", "Basin", "human"),
    }
    for k, (value, klass, source) in spec.items():
        p = Product(
            id=_uid(), product_code=f"{tag}-{k}", product_name=f"{tag} {k}", category_id=cat.id,
            base_uom_id=uom.id, list_price=Decimal("1.00"),
        )
        db.add(p)
        db.flush()
        db.add(ProductSpecifications(
            id=_uid(), product_id=p.id,
            values={key: {"value": value}, "class": {"value": klass}},
            provenance={key: {"source": source}},
        ))
        db.flush()
        rows[k] = p
    return dict(key=key, tag=tag, **rows)


def _seen(client, s, pairs):
    resp = get(client, f"{SPEC_REGISTRY}/{s['key']}/products", [("limit", 100), *pairs])
    assert resp.status_code == 200, resp.text
    return {row["product_code"] for row in resp.json()["products"]}, resp.json()


def _codes(s, *keys):
    return {f"{s['tag']}-{k}" for k in keys}


def test_seen_value_single_union_repeated(client, seen):
    s = seen
    assert _seen(client, s, [("value", "gloss")])[0] == _codes(s, "b")
    assert _seen(client, s, [("value", "gloss,satin")])[0] == _codes(s, "b", "c")
    assert _seen(client, s, [("value", "gloss"), ("value", "satin")])[0] == _codes(s, "b", "c")


def test_seen_class_single_union_repeated(client, seen):
    s = seen
    assert _seen(client, s, [("class_label", "Sink")])[0] == _codes(s, "a")
    assert _seen(client, s, [("class_label", "Sink,Tap")])[0] == _codes(s, "a", "c")
    assert _seen(client, s, [("class_label", "Sink"), ("class_label", "Basin")])[0] == _codes(s, "a", "b", "d")


def test_seen_source_single_union_repeated(client, seen):
    s = seen
    assert _seen(client, s, [("source", "human")])[0] == _codes(s, "b", "d")
    assert _seen(client, s, [("source", "derived,human")])[0] == _codes(s, "a", "b", "c", "d")
    assert _seen(client, s, [("source", "derived"), ("source", "human")])[0] == _codes(s, "a", "b", "c", "d")


def test_seen_filters_and_across_and_total(client, seen):
    s = seen
    codes, body = _seen(client, s, [("value", "matte,gloss"), ("class_label", "Sink,Basin"), ("source", "human")])
    assert codes == _codes(s, "b", "d")
    assert body["total"] == 2
