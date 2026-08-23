"""Shape B: a described set intersected with a domain predicate, inside the CRM.

Membership and the count are SQL over the full company-scoped catalogue; the ranker
only orders the products that already qualify. The count is honest by construction:
it counts distinct variant FAMILIES (what a customer calls "a product"), never rows,
and an unrecognized word is reported as unrecognized rather than silently answering
"none" from the wrong set.

Contract: sorento_crm_n8n/n8n-workflows-init/plans/crm-ask-spec-backward-search.md.
Plan: documentation/plans/PLAN-spec-backward-search.md.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.certificate import Certificate, CertificateProduct, CertificateRevision
from app.models.inventory import Stock, Warehouse
from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services.company_scope import company_scope
from app.services.error_handler import AppException
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from app.services.product_spec_search import filter_specs, search_specs
from app.services.product_predicate_service import resolve_product_set
from tests._pg_fixture import blank_session

_REFS: dict = {}


def _utc_today() -> date:
    """The service compares validity against `func.current_date()` on a
    session pinned to UTC (`app/database.py` sets `options=-c timezone=utc`).
    Seed fixtures against that same clock, not the local wall clock, or a
    test run between 00:00 and 08:00 Malaysia time seeds a date the service
    still reads as 'today'."""
    return datetime.now(timezone.utc).date()


@pytest.fixture
def db():
    with blank_session() as s:
        ks = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS")
        wc = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-WC", category_name="SRT-WC")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
        s.add_all([ks, wc, uom])
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        _REFS.update({"ks": ks.id, "wc": wc.id, "uom": uom.id})
        yield s


def _product(db, code, description, *, category="ks", variant_of=None):
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS[category],
        base_uom_id=_REFS["uom"],
        list_price=Decimal("1.00"),
        variant_of_id=variant_of,
    )
    db.add(row)
    db.flush()
    derive_for_code(db, code)
    return row


def _warehouse(db):
    wh = Warehouse(id=str(uuid.uuid4()), warehouse_code=f"ZZT-{uuid.uuid4().hex[:6]}", warehouse_name="ZZT WH")
    db.add(wh)
    db.flush()
    return wh


def _stock(db, product, qty, warehouse=None):
    wh = warehouse or _warehouse(db)
    db.add(
        Stock(
            id=str(uuid.uuid4()),
            product_id=product.id,
            warehouse_id=wh.id,
            quantity_on_hand=qty,
            quantity_reserved=0,
            quantity_damaged=0,
        )
    )
    db.flush()


def _certificate(db, product, *, status="active", scheme="ZZT-SIRIM", valid_until=None):
    cert = Certificate(
        id=str(uuid.uuid4()),
        scheme=scheme,
        certificate_number=f"ZZT-{uuid.uuid4().hex[:8]}",
        status=status,
    )
    db.add(cert)
    db.flush()
    if valid_until is not None:
        rev = CertificateRevision(
            id=str(uuid.uuid4()),
            certificate_id=cert.id,
            revision_no=1,
            valid_until=valid_until,
        )
        db.add(rev)
        db.flush()
        cert.current_revision_id = rev.id
    db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=product.id))
    db.flush()
    return cert


def _promotion(db, product, *, is_active=True, end_date=None):
    promo = Promotion(id=str(uuid.uuid4()), description=f"ZZT promo {uuid.uuid4().hex[:6]}", is_active=is_active, end_date=end_date)
    db.add(promo)
    db.flush()
    group = PromotionGroup(id=uuid.uuid4(), promotion_id=promo.id, group_name="G")
    db.add(group)
    db.flush()
    db.add(PromotionProduct(id=str(uuid.uuid4()), promotion_id=promo.id, promotion_group_id=group.id, product_id=product.id))
    db.flush()
    return promo


def _attachment_type(db, type_name):
    at = AttachmentType(
        id=str(uuid.uuid4()),
        code=type_name.upper().replace(" ", "_"),
        type_name=type_name,
        allowed_extensions="pdf",
    )
    db.add(at)
    db.flush()
    return at


def _attach(db, product, attachment_type):
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename="zzt.pdf",
        stored_filename="zzt.pdf",
        file_path="https://cdn/zzt.pdf",
        attachment_type_id=attachment_type.id,
    )
    db.add(att)
    db.flush()
    db.add(ProductAttachment(id=str(uuid.uuid4()), product_id=product.id, attachment_id=att.id))
    db.flush()
    return att


def _totals(db, require, terms=None, **kw):
    return resolve_product_set(db, require=require, free_terms=terms, **kw)


# --------------------------------------------------------------------------- #
# filter_specs: the class-only membership vocabulary                            #
# --------------------------------------------------------------------------- #
def test_filter_specs_resolves_a_class_term(db):
    _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    verdict = filter_specs(db, free_terms=["kitchen sink"])
    assert verdict["class_labels"]
    assert verdict["clause"] is not None
    assert verdict["unrecognized_terms"] == []


def test_filter_specs_drops_known_spec_words_without_flagging_them(db):
    # "wall hung" is a registry mounting value: not a class, but recognized —
    # it must neither define membership nor be reported as unrecognized.
    verdict = filter_specs(db, free_terms=["wall hung"])
    assert verdict["class_labels"] == []
    assert verdict["unrecognized_terms"] == []


def test_filter_specs_reports_nonsense_as_unrecognized(db):
    verdict = filter_specs(db, free_terms=["flurbish"])
    assert verdict["unrecognized_terms"] == ["flurbish"]
    assert verdict["clause"] is None


# --------------------------------------------------------------------------- #
# the four legs                                                                 #
# --------------------------------------------------------------------------- #
def test_stock_leg_requires_on_hand_above_zero(db):
    with_stock = _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    without = _product(db, "ZZT-SINK-B", "SORENTO S/STEEL KITCHEN SINK (800X450X200MM)")
    _stock(db, with_stock, 3)
    _stock(db, without, 0)
    out = _totals(db, {"stock": True}, ["kitchen sink"])
    codes = [c["product_code"] for c in out["candidates"]]
    assert codes == ["ZZT-SINK-A"]
    assert out["qualifying_total"] == 1


def test_certificate_leg_bare_true_means_any_active_register_cert(db):
    certified = _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    archived = _product(db, "ZZT-SINK-B", "SORENTO S/STEEL KITCHEN SINK (800X450X200MM)")
    _certificate(db, certified, status="active")
    _certificate(db, archived, status="archived")
    out = _totals(db, {"certificate": True}, ["kitchen sink"])
    codes = [c["product_code"] for c in out["candidates"]]
    assert codes == ["ZZT-SINK-A"]


def test_certificate_object_form_filters_on_validity(db):
    valid = _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    expired = _product(db, "ZZT-SINK-B", "SORENTO S/STEEL KITCHEN SINK (800X450X200MM)")
    _certificate(db, valid, valid_until=_utc_today() + timedelta(days=30))
    _certificate(db, expired, valid_until=_utc_today() - timedelta(days=1))
    out = _totals(db, {"certificate": {"validity_state": "valid"}}, ["kitchen sink"])
    codes = [c["product_code"] for c in out["candidates"]]
    assert codes == ["ZZT-SINK-A"]


def test_promotion_leg_requires_an_active_unexpired_promotion(db):
    promoted = _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    lapsed = _product(db, "ZZT-SINK-B", "SORENTO S/STEEL KITCHEN SINK (800X450X200MM)")
    switched_off = _product(db, "ZZT-SINK-C", "CABANA CERAMIC KITCHEN SINK (1000X500X140MM)")
    _promotion(db, promoted)
    _promotion(db, lapsed, end_date=_utc_today() - timedelta(days=1))
    _promotion(db, switched_off, is_active=False)
    out = _totals(db, {"promotion": True}, ["kitchen sink"])
    codes = [c["product_code"] for c in out["candidates"]]
    assert codes == ["ZZT-SINK-A"]


def test_attachment_type_leg_resolves_the_customers_label(db):
    drawn = _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    bare = _product(db, "ZZT-SINK-B", "SORENTO S/STEEL KITCHEN SINK (800X450X200MM)")
    at = _attachment_type(db, "Technical Drawing")
    _attach(db, drawn, at)
    out = _totals(db, {"attachment_type": "technical drawing"}, ["kitchen sink"])
    codes = [c["product_code"] for c in out["candidates"]]
    assert codes == ["ZZT-SINK-A"]
    assert out["require"]["attachment_type"] == "Technical Drawing"


def test_an_unresolvable_attachment_label_is_unrecognized_not_none(db):
    p = _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    _attach(db, p, _attachment_type(db, "Technical Drawing"))
    out = _totals(db, {"attachment_type": "blorp sheet"}, ["kitchen sink"])
    assert out["qualifying_total"] == 0
    assert "blorp sheet" in out["unrecognized_terms"]


def test_multiple_require_keys_are_an_and(db):
    both = _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    stock_only = _product(db, "ZZT-SINK-B", "SORENTO S/STEEL KITCHEN SINK (800X450X200MM)")
    wh = _warehouse(db)
    _stock(db, both, 5, wh)
    _stock(db, stock_only, 5, wh)
    _certificate(db, both)
    out = _totals(db, {"stock": True, "certificate": True}, ["kitchen sink"])
    codes = [c["product_code"] for c in out["candidates"]]
    assert codes == ["ZZT-SINK-A"]


def test_an_unknown_require_key_is_a_422(db):
    with pytest.raises(AppException):
        _totals(db, {"blessing": True}, ["kitchen sink"])


# --------------------------------------------------------------------------- #
# the honest count                                                              #
# --------------------------------------------------------------------------- #
def test_qualifying_total_counts_variant_families_not_rows(db):
    parent = _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    v1 = _product(db, "ZZT-SINK-A-BK", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM) BLACK", variant_of=parent.id)
    v2 = _product(db, "ZZT-SINK-A-GD", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM) GOLD", variant_of=parent.id)
    wh = _warehouse(db)
    for p in (parent, v1, v2):
        _stock(db, p, 2, wh)
    out = _totals(db, {"stock": True}, ["kitchen sink"])
    assert out["qualifying_total"] == 1
    assert out["truncated"] is False


def test_truncated_when_more_qualify_than_are_shown(db):
    wh = _warehouse(db)
    for i in range(4):
        p = _product(db, f"ZZT-SINK-{i}", f"SORENTO S/STEEL KITCHEN SINK ({900 + i}X500X200MM)")
        _stock(db, p, 1, wh)
    out = _totals(db, {"stock": True}, ["kitchen sink"], limit=2)
    assert out["qualifying_total"] == 4
    assert len(out["candidates"]) == 2
    assert out["truncated"] is True


def test_class_membership_is_a_filter_but_numbers_stay_boosts(db):
    wh = _warehouse(db)
    big = _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    small = _product(db, "ZZT-SINK-B", "SORENTO S/STEEL KITCHEN SINK (800X450X200MM)")
    other_class = _product(db, "ZZT-WC-A", "SORENTO CERAMIC WALL HUNG WATER CLOSET", category="wc")
    for p in (big, small, other_class):
        _stock(db, p, 1, wh)
    out = _totals(
        db,
        {"stock": True},
        ["kitchen sink"],
        specs=[{"key": "length", "value": 1000, "op": "at_least"}],
    )
    codes = [c["product_code"] for c in out["candidates"]]
    # The water closet is filtered out (wrong class); the 800mm sink is NOT
    # filtered by the number — it merely ranks below the 1000mm one.
    assert "ZZT-WC-A" not in codes
    assert set(codes) == {"ZZT-SINK-A", "ZZT-SINK-B"}
    assert codes[0] == "ZZT-SINK-A"
    assert out["qualifying_total"] == 2


def test_unrecognized_terms_do_not_silently_mean_none(db):
    p = _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    _stock(db, p, 1)
    out = _totals(db, {"stock": True}, ["flurbish"])
    assert out["unrecognized_terms"] == ["flurbish"]
    assert out["qualifying_total"] == 0
    assert out["candidates"] == []


# --------------------------------------------------------------------------- #
# company isolation: every leg fail-closed across companies                     #
# --------------------------------------------------------------------------- #
def test_no_leg_bleeds_across_companies(db):
    other = Company(id=str(uuid.uuid4()), code="ZZT-MC", name="ZZT Mocha")
    db.add(other)
    db.flush()

    with company_scope(db, frozenset({other.id})):
        theirs = _product(db, "ZZT-SINK-X", "MOCHA S/STEEL KITCHEN SINK (900X500X200MM)")
        _stock(db, theirs, 9)
        _certificate(db, theirs)
        _promotion(db, theirs)
        _attach(db, theirs, _attachment_type(db, "Technical Drawing"))

    # Session scope is Sorento (conftest default): the other company's fully
    # qualifying product must be invisible through EVERY leg.
    for require in (
        {"stock": True},
        {"certificate": True},
        {"promotion": True},
        {"attachment_type": "technical drawing"},
    ):
        out = _totals(db, require, ["kitchen sink"])
        assert out["qualifying_total"] == 0, require
        assert out["candidates"] == [], require


# --------------------------------------------------------------------------- #
# stage-2: the ranker restricted to the qualifying set                          #
# --------------------------------------------------------------------------- #
def test_search_specs_product_ids_whitelist_restricts_candidates(db):
    a = _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    _product(db, "ZZT-SINK-B", "SORENTO S/STEEL KITCHEN SINK (800X450X200MM)")
    found = search_specs(db, free_terms=["kitchen sink"], product_ids=[a.id])
    codes = [c["product_code"] for c in found["candidates"]]
    assert codes == ["ZZT-SINK-A"]
