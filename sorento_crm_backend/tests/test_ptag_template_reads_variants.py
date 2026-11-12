"""PRICETAG-UPGRADE-VARIANTS crew re-pass (1): the request line shows "Variants on this tag" (and the
"Variants price differently" warning) only when the line's template reads "All variants". The
template row the line reads (`template_item`) says so as `reads_variants`, from the PUBLISHED doc.
Pure: no database.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.dealer_kit.template_needs import doc_reads_variants


def _layer(kind: str, slot=None) -> dict:
    props = {"kind": kind}
    if slot is not None:
        props["subjectSlot"] = slot
    return {"id": "l1", "type": kind, "props": props}


def test_a_feature_icons_layer_on_all_variants_reads_variants():
    assert doc_reads_variants({"layers": [_layer("feature_icons", {"kind": "variants"})]}) is True


def test_a_layer_on_the_main_product_does_not():
    assert doc_reads_variants({"layers": [_layer("feature_icons", {"kind": "main"}), _layer("text")]}) is False


def test_an_empty_or_damaged_doc_does_not():
    assert doc_reads_variants(None) is False
    assert doc_reads_variants({}) is False
    assert doc_reads_variants({"layers": "nope"}) is False
    assert doc_reads_variants({"layers": [None, {"props": "x"}]}) is False


def _template(doc):
    version = SimpleNamespace(doc=doc, print_size={"width_mm": 148, "height_mm": 105}) if doc is not None else None
    return SimpleNamespace(
        id="t1", name="WC FAMILY TEST", family=None, published_version=version,
        published_version_id="v1" if version is not None else None, print_size={}, price_type=None,
    )


def test_the_template_row_carries_reads_variants():
    from app.services.dealer_kit.product_tag_template_service import template_item

    on = template_item(_template({"layers": [_layer("feature_icons", {"kind": "variants"})]}))
    off = template_item(_template({"layers": [_layer("text")]}))
    unpublished = template_item(_template(None))
    assert on["reads_variants"] is True
    assert off["reads_variants"] is False
    assert unpublished["reads_variants"] is False


def test_the_response_schema_declares_it():
    from app.schemas.price_tag import ProductTagTemplateItem

    assert ProductTagTemplateItem(id="t1", name="x", family="WC", published=True, reads_variants=True).reads_variants is True
    assert ProductTagTemplateItem(id="t1", name="x", family="WC", published=True).reads_variants is False
