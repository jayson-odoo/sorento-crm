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
from app.models.lookup import LookupOption, LookupOptionKeyword, LookupSet
from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
from app.models.procurement import InboundShipment, InboundShipmentLine
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
    # "wall hung" is a registry mounting value: not a class, but recognized - 
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
    # filtered by the number - it merely ranks below the 1000mm one.
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


# --------------------------------------------------------------------------- #
# Attribute-first asks S1 (PLAN-attribute-first-asks.md)                       #
# --------------------------------------------------------------------------- #


def test_resolve_product_set_never_returns_a_silent_zero(db):
    """AC-1302: "water tap" names no class/product_type/brand (AC-1301), and
    `resolve_product_set` must carry that honesty through rather than answering a
    silent, indistinguishable-from-real zero.
    """
    out = _totals(db, {"certificate": True}, ["water tap"])
    assert out["qualifying_total"] == 0
    assert "water tap" in out["unrecognized_terms"]


def test_filter_specs_membership_accepts_product_type_and_brand(db):
    """AC-1307: `filter_specs` membership widens beside `class` to `product_type` and
    `brand` - today only a `class` spec entry defines membership, so a `product_type` /
    `brand` entry is silently dropped and the clause stays `None`.
    """
    from sqlalchemy import func

    from app.models.product_spec import ProductSpecifications

    bidet = _product(db, "ZZT-PT-BIDET", "SORENTO BIDET SPRAY")
    shower = _product(db, "ZZT-PT-SHOWER", "SORENTO SHOWER SET")

    def _set_values(product, **extra):
        row = (
            db.query(ProductSpecifications)
            .filter(ProductSpecifications.product_id == product.id)
            .first()
        )
        values = dict(row.values or {}) if row is not None else {}
        for key, value in extra.items():
            values[key] = {"value": value}
        if row is None:
            row = ProductSpecifications(product_id=product.id, values=values, provenance={})
            db.add(row)
        else:
            row.values = values
        db.flush()

    _set_values(bidet, product_type="bidet", brand="SORENTO")
    _set_values(shower, product_type="shower_set", brand="SORENTO")

    def _count(clause):
        return (
            db.query(func.count(ProductSpecifications.product_id))
            .filter(clause)
            .scalar()
        )

    by_type = filter_specs(db, specs=[{"key": "product_type", "value": "bidet"}])
    assert by_type["clause"] is not None
    assert _count(by_type["clause"]) == 1

    by_brand = filter_specs(db, specs=[{"key": "brand", "value": "SORENTO"}])
    assert by_brand["clause"] is not None
    assert _count(by_brand["clause"]) == 2


def test_resolve_product_set_intersects_given_product_ids_with_legs(db):
    """AC-1308 (ids only): the LOOKUP-matched ids are the described set, intersected
    with the legs like any other described set."""
    a = _product(db, "ZZT-PID-A", "PRODUCT A")
    b = _product(db, "ZZT-PID-B", "PRODUCT B")
    c = _product(db, "ZZT-PID-C", "PRODUCT C")
    _certificate(db, a)
    out = resolve_product_set(db, require={"certificate": True}, product_ids=[a.id, b.id, c.id])
    assert out["qualifying_total"] == 1
    codes = [cand["product_code"] for cand in out["candidates"]]
    assert codes == ["ZZT-PID-A"]


def test_resolve_product_set_unions_product_ids_with_bindings(db):
    """AC-1308 (both): product A is matched ONLY through the given `product_ids`;
    product B is matched ONLY through the class binding; product C is certified but in
    neither and must stay excluded - the described set is a UNION of the two, then
    intersected with the legs."""
    a = _product(db, "ZZT-UN-A", "SORENTO WIDGET A")
    b = _product(db, "ZZT-UN-B", "SORENTO S/STEEL KITCHEN SINK (900X500X200MM)")
    c = _product(db, "ZZT-UN-C", "SORENTO WIDGET C")
    for p in (a, b, c):
        _certificate(db, p)

    out = resolve_product_set(
        db,
        require={"certificate": True},
        product_ids=[a.id],
        specs=[{"key": "class", "value": "kitchen sink"}],
    )
    assert out["qualifying_total"] == 2
    codes = {cand["product_code"] for cand in out["candidates"]}
    assert codes == {"ZZT-UN-A", "ZZT-UN-B"}


def test_resolve_product_set_brand_scopes_the_set(db):
    """AC-1306 / D3: a `brand` filter scopes the whole set, applied on top of the
    described set and the legs - two certified kitchen sinks, one Sorento and one
    Cabana, and only the Sorento one qualifies once `brand="SORENTO"` is asked."""
    from app.models.product import Brand

    sorento = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SRT", brand_name="SORENTO")
    cabana = Brand(id=str(uuid.uuid4()), brand_code="ZZT-CAB", brand_name="CABANA")
    db.add_all([sorento, cabana])
    db.flush()

    a = _product(db, "ZZT-BR-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    b = _product(db, "ZZT-BR-B", "CABANA S/STEEL KITCHEN SINK (1000X500X220MM)")
    a.brand_id = sorento.id
    b.brand_id = cabana.id
    db.flush()
    _certificate(db, a)
    _certificate(db, b)

    out = resolve_product_set(
        db,
        require={"certificate": True},
        specs=[{"key": "class", "value": "kitchen sink"}],
        brand="SORENTO",
    )
    assert out["qualifying_total"] == 1
    codes = [cand["product_code"] for cand in out["candidates"]]
    assert codes == ["ZZT-BR-A"]


def test_product_ids_path_does_not_bleed_across_companies(db):
    """AC-1310: the new `product_ids` leg is fail-closed per company exactly like the
    other four - two companies share a product CODE, both certified, and a
    `product_ids` list naming both uuids must still qualify only the caller's own
    company's row."""
    other = Company(id=str(uuid.uuid4()), code="ZZT-MC2", name="ZZT Mocha 2")
    db.add(other)
    db.flush()

    ours = _product(db, "ZZT-DUP", "SORENTO WIDGET")
    _certificate(db, ours)

    with company_scope(db, frozenset({other.id})):
        theirs = _product(db, "ZZT-DUP", "MOCHA WIDGET")
        _certificate(db, theirs)

    # Session scope is Sorento (conftest default): `theirs.id` must not qualify even
    # though it was explicitly named in `product_ids`.
    out = resolve_product_set(db, require={"certificate": True}, product_ids=[ours.id, theirs.id])
    assert out["qualifying_total"] == 1
    codes = [cand["product_code"] for cand in out["candidates"]]
    assert codes == ["ZZT-DUP"]


# --------------------------------------------------------------------------- #
# Attribute-first asks S2 (PLAN-attribute-first-asks.md, D1/D2/D3)             #
# --------------------------------------------------------------------------- #


def _shipment(db, *, arrived: bool):
    row = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=f"ZZT-{uuid.uuid4().hex[:8]}",
        shipment_date=_utc_today(),
        actual_arrival_date=_utc_today() if arrived else None,
    )
    db.add(row)
    db.flush()
    return row


def _shipment_line(db, shipment, product, *, shipped, received):
    row = InboundShipmentLine(
        id=str(uuid.uuid4()),
        shipment_id=shipment.id,
        product_id=product.id,
        quantity_shipped=shipped,
        quantity_received=received,
    )
    db.add(row)
    db.flush()
    return row


def test_incoming_leg_counts_open_lines_on_unarrived_shipments(db):
    """AC-1311: EXISTS inbound_shipment_lines JOIN inbound_shipments (scoped) WHERE
    shipped minus received > 0 AND the shipment has not yet actually arrived. Today
    `REQUIRE_LEGS` has no "incoming" entry at all, so this 422s ("Unknown require
    key(s): incoming") rather than returning a dict - the right red reason for a leg
    that does not exist yet.
    """
    p1 = _product(db, "ZZT-INC-P1", "SORENTO ITEM P1")
    p2 = _product(db, "ZZT-INC-P2", "SORENTO ITEM P2")
    p3 = _product(db, "ZZT-INC-P3", "SORENTO ITEM P3")

    shipment_a = _shipment(db, arrived=False)
    _shipment_line(db, shipment_a, p1, shipped=10, received=0)
    _shipment_line(db, shipment_a, p2, shipped=5, received=5)

    shipment_b = _shipment(db, arrived=True)
    _shipment_line(db, shipment_b, p3, shipped=8, received=0)

    out = resolve_product_set(db, require={"incoming": True})
    assert out["qualifying_total"] == 1
    codes = [cand["product_code"] for cand in out["candidates"]]
    assert codes == ["ZZT-INC-P1"]


def test_incoming_leg_does_not_bleed_across_companies(db):
    """AC-1310: the new `incoming` leg is fail-closed per company exactly like the
    other four (`test_no_leg_bleeds_across_companies`, extended per
    PLAN-attribute-first-asks.md). `InboundShipment`/`InboundShipmentLine` are
    ordinary `CompanyScopedMixin` models (not `__company_shared__`), so the
    before_insert auto-stamp scopes them to `other.id` for free inside the context
    manager."""
    other = Company(id=str(uuid.uuid4()), code="ZZT-MC3", name="ZZT Mocha 3")
    db.add(other)
    db.flush()

    with company_scope(db, frozenset({other.id})):
        theirs = _product(db, "ZZT-SINK-INC", "MOCHA S/STEEL KITCHEN SINK (900X500X200MM)")
        shipment = _shipment(db, arrived=False)
        _shipment_line(db, shipment, theirs, shipped=10, received=0)

    out = _totals(db, {"incoming": True}, ["kitchen sink"])
    assert out["qualifying_total"] == 0
    assert out["candidates"] == []


def test_attachment_type_label_resolves_through_the_alias_lookup_set(db):
    """AC-1312: `attachment_type` resolution falls through to the
    `attachment_type_alias` lookup set (keyword "photo" -> option "Product Photos")
    when the raw does not exact-match a code or type_name directly. Today
    `_leg_attachment_type` never reads a lookup set at all, so "photo" is reported
    unrecognized and qualifying_total is 0, not 1 - the wrong VALUE, the right red
    reason."""
    lookup_set = LookupSet(
        id=str(uuid.uuid4()), tenant_id=None, set_key="attachment_type_alias",
        name="Attachment Type Alias", is_active=True,
    )
    db.add(lookup_set)
    db.flush()
    option = LookupOption(
        id=str(uuid.uuid4()), set_id=lookup_set.id, value="Product Photos",
        label="Product Photos", is_active=True,
    )
    db.add(option)
    db.flush()
    db.add(LookupOptionKeyword(id=str(uuid.uuid4()), option_id=option.id, keyword="photo", locale=None))
    db.flush()

    at = _attachment_type(db, "Product Photos")
    with_photo = _product(db, "ZZT-PHOTO-A", "SORENTO ITEM WITH PHOTO")
    _product(db, "ZZT-PHOTO-B", "SORENTO ITEM WITHOUT PHOTO")
    _attach(db, with_photo, at)

    out = resolve_product_set(db, require={"attachment_type": "photo"})
    assert out["qualifying_total"] == 1
    codes = [cand["product_code"] for cand in out["candidates"]]
    assert codes == ["ZZT-PHOTO-A"]
    assert out["require"]["attachment_type"] == "Product Photos"


def test_attachment_type_unknown_word_is_unrecognized_with_empty_or_missing_set(db):
    """AC-1312 / AC-1314: an alias word that resolves through NEITHER an empty
    `attachment_type_alias` set NOR a missing one is reported unrecognized, never a
    500, in either state."""
    lookup_set = LookupSet(
        id=str(uuid.uuid4()), tenant_id=None, set_key="attachment_type_alias",
        name="Attachment Type Alias", is_active=True,
    )
    db.add(lookup_set)
    db.flush()

    out_empty_set = resolve_product_set(db, require={"attachment_type": "gambar2"})
    assert out_empty_set["qualifying_total"] == 0
    assert out_empty_set["unrecognized_terms"] == ["gambar2"]

    db.query(LookupSet).filter(LookupSet.set_key == "attachment_type_alias").delete()
    db.flush()

    out_missing_set = resolve_product_set(db, require={"attachment_type": "gambar2"})
    assert out_missing_set["qualifying_total"] == 0
    assert out_missing_set["unrecognized_terms"] == ["gambar2"]


def _scheme_seed(db):
    """Two certified products, schemes PPS and SPAN, plus a `certificate_scheme`
    lookup set carrying only the PPS option/keyword - SPAN stays reachable only by
    its own exact spelling, matching the register (owner enters options by hand)."""
    pps_product = _product(db, "ZZT-SCHEME-PPS", "SORENTO CERTIFIED ITEM PPS")
    span_product = _product(db, "ZZT-SCHEME-SPAN", "SORENTO CERTIFIED ITEM SPAN")
    _certificate(db, pps_product, scheme="PPS")
    _certificate(db, span_product, scheme="SPAN")

    lookup_set = LookupSet(
        id=str(uuid.uuid4()), tenant_id=None, set_key="certificate_scheme",
        name="Certificate Scheme", is_active=True,
    )
    db.add(lookup_set)
    db.flush()
    option = LookupOption(
        id=str(uuid.uuid4()), set_id=lookup_set.id, value="PPS", label="PPS", is_active=True,
    )
    db.add(option)
    db.flush()
    db.add(LookupOptionKeyword(id=str(uuid.uuid4()), option_id=option.id, keyword="pps scheme", locale=None))
    db.flush()
    return pps_product, span_product


def test_certificate_scheme_normalises_through_the_lookup_set(db):
    """AC-1313: "pps scheme" normalises through the `certificate_scheme` lookup set
    to the register's own spelling "PPS" before equality. Today `_leg_certificate`
    lower-cases and compares the RAW value verbatim against `Certificate.scheme`, so
    "pps scheme" != "pps" and qualifying_total is 0, not 1 - the wrong value."""
    _scheme_seed(db)

    out = resolve_product_set(db, require={"certificate": {"scheme": "pps scheme"}})
    assert out["qualifying_total"] == 1
    codes = [cand["product_code"] for cand in out["candidates"]]
    assert codes == ["ZZT-SCHEME-PPS"]
    assert out["require"]["certificate"]["scheme"] == "PPS"


def test_certificate_unknown_scheme_returns_schemes_on_file(db):
    """AC-1313: a scheme word with no matching option (or keyword) qualifies
    nothing, reports itself unrecognized, and lists the register's distinct
    schemes so the reply can name them. Today `_leg_certificate` neither reports
    "watermark" as unrecognized (it silently filters to zero via a plain SQL
    comparison) nor emits a `schemes_on_file` key at all - both assertions below
    fail on the un-implemented leg."""
    _scheme_seed(db)

    out = resolve_product_set(db, require={"certificate": {"scheme": "watermark"}})
    assert out["qualifying_total"] == 0
    assert "watermark" in out["unrecognized_terms"]
    assert out["schemes_on_file"] == ["PPS", "SPAN"]


def test_schemes_on_file_is_company_scoped(db):
    """AC-1313 / AC-1310: a certificate scheme belonging to a DIFFERENT company must
    never appear in `schemes_on_file`. `Certificate` is `__company_shared__` (a NULL
    `company_id` is a deliberately SHARED row, visible under every scope, per the
    model's own docstring) so the other company's WCM certificate is stamped with an
    EXPLICIT `company_id` - leaving it unset would leak it into Sorento's list
    regardless of `company_scope`."""
    _scheme_seed(db)

    other = Company(id=str(uuid.uuid4()), code="ZZT-SCHCO", name="ZZT Scheme Co")
    db.add(other)
    db.flush()

    with company_scope(db, frozenset({other.id})):
        theirs = _product(db, "ZZT-SCHEME-WCM", "MOCHA CERTIFIED ITEM WCM")
        cert = Certificate(
            id=str(uuid.uuid4()),
            scheme="WCM",
            certificate_number=f"ZZT-{uuid.uuid4().hex[:8]}",
            status="active",
            company_id=other.id,
        )
        db.add(cert)
        db.flush()
        db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=theirs.id))
        db.flush()

    out = resolve_product_set(db, require={"certificate": {"scheme": "watermark"}})
    assert out["qualifying_total"] == 0
    assert "WCM" not in out["schemes_on_file"]
    assert out["schemes_on_file"] == ["PPS", "SPAN"]


# --------------------------------------------------------------------------- #
# Security review (11 Sep 2026, PLAN-attribute-first-asks.md SEC-S1/S2,       #
# AC-1334/AC-1335)                                                             #
# --------------------------------------------------------------------------- #


def test_promotion_leg_respects_access_levels(db):
    """AC-1334/SEC-S1: the promotion leg must intersect `Promotion.access_levels`
    with the caller's OWN tier(s), the same name -> code translation
    `references.py`'s `_apply_promotion_access_levels_filter` already uses
    (`ContactAccessType.name` case-insensitive -> `.code`) - a promotion the
    contact's tier cannot see must never count toward `qualifying_total` nor
    name its product.

    World: two class-Tap products, each in its own active promotion - product A's
    promotion open to access code X, product B's restricted to code Y.

    RED: `resolve_product_set` has no `access_levels` parameter at all today, so
    `resolve_product_set(require={"promotion": True}, access_levels=[...])`
    raises `TypeError` before any filtering logic runs - `_leg_promotion` reads
    only `PromotionProduct` / `Promotion.is_active` / the date window, never the
    caller's tier.
    """
    from app.models.access import ContactAccessType

    db.add(ContactAccessType(code="zzt_code_x", name="ZZT Level X"))
    db.add(ContactAccessType(code="zzt_code_y", name="ZZT Level Y"))
    db.flush()

    product_a = _product(db, "ZZT-PROMO-A", "SORENTO CHROME TAP A")
    product_b = _product(db, "ZZT-PROMO-B", "SORENTO CHROME TAP B")

    promo_a = Promotion(
        id=str(uuid.uuid4()), description="ZZT promo A", is_active=True, access_levels=["zzt_code_x"]
    )
    db.add(promo_a)
    db.flush()
    group_a = PromotionGroup(id=uuid.uuid4(), promotion_id=promo_a.id, group_name="G")
    db.add(group_a)
    db.flush()
    db.add(
        PromotionProduct(
            id=str(uuid.uuid4()), promotion_id=promo_a.id, promotion_group_id=group_a.id, product_id=product_a.id
        )
    )

    promo_b = Promotion(
        id=str(uuid.uuid4()), description="ZZT promo B", is_active=True, access_levels=["zzt_code_y"]
    )
    db.add(promo_b)
    db.flush()
    group_b = PromotionGroup(id=uuid.uuid4(), promotion_id=promo_b.id, group_name="G")
    db.add(group_b)
    db.flush()
    db.add(
        PromotionProduct(
            id=str(uuid.uuid4()), promotion_id=promo_b.id, promotion_group_id=group_b.id, product_id=product_b.id
        )
    )
    db.flush()

    out = resolve_product_set(db, require={"promotion": True}, access_levels=["ZZT Level X"])
    assert out["qualifying_total"] == 1
    codes = [cand["product_code"] for cand in out["candidates"]]
    assert codes == ["ZZT-PROMO-A"]

    out_no_tier = resolve_product_set(db, require={"promotion": True}, access_levels=None)
    assert out_no_tier["qualifying_total"] == 2


def test_common_and_nearest_class_labels_are_company_scoped(db):
    """AC-1335/SEC-S2: `_common_class_labels` and `_nearest_class_labels` must
    read only the CALLER's own catalogue - a class label that exists solely in
    another company must never reach a company A reply.

    World: company B (Mocha, via `tests/_mc_lookup_seed.seed_mocha`) owns a
    product whose derived spec class is the nonsense label "Zzqsecretclass" -
    unique enough that its presence can only be explained by a cross-company
    leak, never a coincidence.

    RED: `ProductSpecifications` carries no `company_id` at all (not a
    `CompanyScopedMixin` model) and neither helper joins `Product` (the scoped
    side) to filter by it - `_common_class_labels` groups the whole table
    unconditionally, and `_nearest_class_labels`'s own `stored_class_labels` runs
    raw `text()` SQL with no company filter whatsoever - so under company A's
    scope both still see company B's secret class label.
    """
    from tests._mc_lookup_seed import seed_mocha
    from app.models.base import set_company_scope
    from app.models.product_spec import ProductSpecifications
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from app.services.product_predicate_service import _common_class_labels, _nearest_class_labels

    mocha = seed_mocha(db)
    with company_scope(db, frozenset({mocha.id})):
        secret_product = _product(db, "ZZT-MCH-SECRET", "MOCHA SECRET ITEM")
        # `_product` already ran `derive_for_code`, which inserted the row (the
        # description names no known class, so it derived nothing) - UPDATE the
        # existing row rather than inserting a second one under the same
        # `product_id` (a real UNIQUE constraint), which is exactly how a
        # deterministic class derivation would have written it in production.
        spec_row = (
            db.query(ProductSpecifications)
            .filter(ProductSpecifications.product_id == secret_product.id)
            .one()
        )
        spec_row.values = {"class": {"value": "Zzqsecretclass"}}
        db.flush()
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    common = _common_class_labels(db, limit=50)
    assert "Zzqsecretclass" not in common, common

    nearest = _nearest_class_labels(db, "zzqsecretclas")
    assert nearest == [], nearest
