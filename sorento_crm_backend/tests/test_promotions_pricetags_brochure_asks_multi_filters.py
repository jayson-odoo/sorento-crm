"""FILTER-MULTISELECT PR3: Promotions (Access level already a list, Attachment state), Price tag requests
Status, Brochure images Promotion and the Top asks report's Products (role) filter take several values
(OR within a filter). Red first; Postgres only; rows seeded here into a blank schema.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.access import ContactAccessType, RespondContact
from app.models.marketing import Promotion, PromotionAttachment, PromotionGroup, PromotionProduct
from app.models.price_tag import PriceTagRequest
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment
from app.services.user_service import UserPermissionService
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

PROMOTIONS = "/api/v1/marketing/promotions/"
PRICE_TAGS = "/api/v1/dealer-kit/price-tag-requests"
BROCHURE = "/api/v1/master-data/product-attachments/brochure-images"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    # the promotions list authorises an any-of slug set through the role lookup
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"})
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


# ---- Promotions ---------------------------------------------------------------------------------------

def _promo(db, label, levels=("dealer",)):
    row = Promotion(id=str(uuid.uuid4()), description=f"ZZT {label}", start_date=date(2026, 1, 1),
                    end_date=date(2030, 12, 31), is_active=True, access_levels=list(levels))
    db.add(row)
    db.flush()
    return row


def _attachment(db, deleted):
    row = Attachment(id=str(uuid.uuid4()), original_filename="f.pdf", stored_filename=unique_code("f"),
                     file_path="x/f.pdf", is_deleted=deleted)
    db.add(row)
    db.flush()
    return row


def _link(db, promo, att):
    db.add(PromotionAttachment(id=str(uuid.uuid4()), promotion_id=promo.id, attachment_id=att.id))
    db.flush()


@pytest.fixture
def promos(db):
    unlinked, trashed, clean = _promo(db, "unlinked"), _promo(db, "trashed"), _promo(db, "clean")
    _link(db, trashed, _attachment(db, True))
    _link(db, clean, _attachment(db, False))
    return dict(unlinked=unlinked, trashed=trashed, clean=clean)


def _promo_ids(client, pairs):
    resp = get(client, PROMOTIONS, [("limit", 200), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def test_attachment_state_union_is_the_set_of_either(client, promos):
    s = promos
    got = _promo_ids(client, [("attachment_state", "unlinked,linked_to_trashed")])
    assert got == {s["unlinked"].id, s["trashed"].id}


def test_attachment_state_single_value_and_repeated(client, promos):
    s = promos
    assert _promo_ids(client, [("attachment_state", "unlinked")]) == {s["unlinked"].id}
    assert _promo_ids(client, [("attachment_state", "linked_to_trashed")]) == {s["trashed"].id}
    got = _promo_ids(client, [("attachment_state", "unlinked"), ("attachment_state", "linked_to_trashed")])
    assert got == {s["unlinked"].id, s["trashed"].id}


def test_attachment_state_unknown_value_is_422(client, promos):
    assert get(client, PROMOTIONS, [("attachment_state", "bogus")]).status_code == 422
    assert get(client, PROMOTIONS, [("attachment_state", "unlinked,bogus")]).status_code == 422


def test_access_levels_already_take_several_names(client, db):
    codes = [unique_code("lvl").lower() for _ in range(3)]
    for code in codes:
        db.add(ContactAccessType(code=code, name=f"ZZT {code}", is_active=True, sort_order=1))
    db.flush()
    p0, p1, p2 = (_promo(db, f"p{i}", (codes[i],)) for i in range(3))
    got = _promo_ids(client, [("access_levels", f"ZZT {codes[0]},ZZT {codes[1]}")])
    assert {p0.id, p1.id} <= got and p2.id not in got


# ---- Price tag requests -------------------------------------------------------------------------------

def _ptr(db, contact, tag, label, status):
    row = PriceTagRequest(id=str(uuid.uuid4()), contact_id=contact.id, doc_number=f"{tag}-{label}"[:30], status=status,
                          debtor_name=f"ZZT {tag}")
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def ptrs(db):
    contact = RespondContact(id=str(uuid.uuid4()), phone_number=f"60{uuid.uuid4().int % 10**8 + 10**8}", name="ZZT contact")
    db.add(contact)
    db.flush()
    tag = unique_code("PT", alpha=True)
    return dict(tag=tag, r1=_ptr(db, contact, tag, "1", "new"), r2=_ptr(db, contact, tag, "2", "designing"),
                r3=_ptr(db, contact, tag, "3", "approved"), r4=_ptr(db, contact, tag, "4", "new"))


def _pt(client, s, pairs):
    resp = get(client, PRICE_TAGS, [("limit", 200), ("query", s["tag"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def test_price_tag_status_union_single_and_repeated(client, ptrs):
    s = ptrs
    assert _pt(client, s, [("status", "designing,approved")]) == {s["r2"].id, s["r3"].id}
    assert _pt(client, s, [("status", "new")]) == {s["r1"].id, s["r4"].id}
    assert _pt(client, s, [("status", "designing"), ("status", "approved")]) == {s["r2"].id, s["r3"].id}


# ---- Brochure images: Promotion -----------------------------------------------------------------------

@pytest.fixture
def brochure(db):
    stem = unique_code("BI", alpha=True)
    cat = ProductCategory(category_code=stem, category_name="ZZT cat")
    uom = UnitOfMeasure(uom_code=stem[:20], uom_name="ZZT uom")
    db.add_all([cat, uom])
    db.flush()
    promos, prods = [], []
    for i in range(3):
        promo = _promo(db, f"b{i}")
        prod = Product(product_code=f"{stem}-{i}", product_name=f"ZZT {stem} {i}", category_id=cat.id,
                       base_uom_id=uom.id, list_price=10)
        db.add(prod)
        db.flush()
        group = PromotionGroup(id=uuid.uuid4(), promotion_id=promo.id, group_name="ZZT group")
        db.add(group)
        db.flush()
        db.add(PromotionProduct(id=str(uuid.uuid4()), promotion_id=promo.id, promotion_group_id=group.id,
                                product_id=prod.id))
        db.flush()
        promos.append(promo)
        prods.append(prod)
    return dict(stem=stem, promos=promos, prods=prods)


def _bi(client, s, pairs):
    resp = get(client, BROCHURE, [("limit", 200), ("query", s["stem"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["productId"] for r in resp.json()["items"]}


def test_brochure_promotion_union_single_and_repeated(client, brochure):
    s = brochure
    p, q = s["promos"], s["prods"]
    assert _bi(client, s, [("promotion_id", f"{p[0].id},{p[2].id}")]) == {q[0].id, q[2].id}
    assert _bi(client, s, [("promotion_id", p[1].id)]) == {q[1].id}
    assert _bi(client, s, [("promotion_id", p[0].id), ("promotion_id", p[2].id)]) == {q[0].id, q[2].id}


def test_brochure_malformed_promotion_id_is_422(client, brochure):
    s = brochure
    assert get(client, BROCHURE, [("promotion_id", "not-a-uuid")]).status_code == 422
    assert get(client, BROCHURE, [("promotion_id", f"{s['promos'][0].id},not-a-uuid")]).status_code == 422


# ---- Top asks report: Products (role) ----------------------------------------------------------------

def test_top_asks_products_role_declares_several_values():
    from app.services.reports import registry as reg
    import app.services.reports  # noqa: F401

    definition = reg.get("chat_top_asks")
    by_key = {p.key: p for p in definition.params}
    assert by_key["products"].multi is True


def test_top_asks_both_roles_count_the_rows_of_either():
    from tests.test_report_chat_top_asks import PRODUCT_VIEW, _row_asks, _run, _seed_items
    from tests._pg_fixture import blank_session as _blank
    from app.models.base import set_company_scope

    with _blank() as session:
        set_company_scope(session, None)
        _seed_items(session)
        asked = _row_asks(_run(session, {"count_by": ["products"], "products": ["asked"]}, PRODUCT_VIEW).layouts.summary)
        shown = _row_asks(_run(session, {"count_by": ["products"], "products": ["shown"]}, PRODUCT_VIEW).layouts.summary)
        both = _row_asks(_run(session, {"count_by": ["products"], "products": ["asked", "shown"]},
                              PRODUCT_VIEW).layouts.summary)
    assert asked == {"ZZTTA-A": 2, "ZZTTA-B": 1}
    assert shown == {"ZZTTA-A": 1, "ZZTTA-B": 2}
    assert both == {"ZZTTA-A": 3, "ZZTTA-B": 3}


def test_access_level_user_type_param_takes_several_codes(client, db):
    # the Promotions list's Access level control sends `user_type` (one level code today)
    codes = [unique_code("ut").lower() for _ in range(3)]
    p0, p1, p2 = (_promo(db, f"u{i}", (codes[i],)) for i in range(3))
    assert _promo_ids(client, [("user_type", codes[2])]) >= {p2.id}
    got = _promo_ids(client, [("user_type", f"{codes[0]},{codes[1]}")])
    assert {p0.id, p1.id} <= got and p2.id not in got
    got = _promo_ids(client, [("user_type", codes[0]), ("user_type", codes[1])])
    assert {p0.id, p1.id} <= got and p2.id not in got
