"""Pick a template's products inside the designer (PRICETAG-TEMPLATE-PRODUCTS).

Plan: documentation/plans/dealer-kit/PLAN-pricetag-template-products-10nov.md (Design v3).
One view, the shared product picker, tick = uses this template. The backend contract it rests on:

- ``GET /dealer-kit/tag-templates/{id}/product-ids``: the company's products linked to the template
  (seeds the ticks).
- ``GET /master-data/products?tag_template_id=``: the "Show: Uses this template" filter.
- ``POST /dealer-kit/tag-templates/{id}/assign`` and ``/assign/preview`` accept ``product_ids``.
- ``tag_template.unassign_products`` (the Save's countdown) accepts ``product_ids``.
- Bulk link never changes an existing default (owner, 10 Nov).

Postgres only, rows rolled back; seeds and the ``env`` fixture come from test_product_tag_templates.
"""
from __future__ import annotations

import uuid

from tests._pg_fixture import unique_code
from tests.test_product_tag_templates import (  # noqa: F401  (env is a fixture)
    DK,
    MANAGER_ID,
    SORENTO,
    VIEWER_ID,
    _link,
    _product,
    _reference,
    _template,
    env,
)


def _links(db, template_id: str) -> set[str]:
    from app.models.dealer_kit import ProductTagTemplate

    return {r.product_id for r in db.query(ProductTagTemplate).filter_by(template_id=template_id)}


def _flags(db, product_id: str) -> dict[str, tuple[bool, bool]]:
    from app.models.dealer_kit import ProductTagTemplate

    db.expire_all()
    return {
        r.template_id: (r.default_list, r.default_selling)
        for r in db.query(ProductTagTemplate).filter_by(product_id=product_id)
    }


def _foreign_product(db) -> str:
    """A product in another company, with its own reference rows."""
    from app.models.company import Company
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    company_id = str(uuid.uuid4())
    db.add(Company(id=company_id, name=unique_code("ZZT Other"), code=unique_code("OC")[:20]))
    db.flush()
    category = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("cat"),
                               category_name=unique_code("Cat"), company_id=company_id)
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("uom"), uom_name="Each",
                        company_id=company_id)
    db.add_all([category, uom])
    db.flush()
    product = Product(id=str(uuid.uuid4()), product_code=unique_code("frn"),
                      product_name=unique_code("Foreign"), category_id=category.id,
                      base_uom_id=uom.id, list_price=10, company_id=company_id)
    db.add(product)
    db.flush()
    return product.id


# ---------------------------------------------------------------------------
# Assign by picked ids
# ---------------------------------------------------------------------------


class TestAssignByIds:
    def test_add_links_only_the_picked_products(self, env):
        db, c, _ = env
        ref = _reference(db)
        p1, p2, untouched = _product(db, ref), _product(db, ref), _product(db, ref)
        t = _template(db, "Pick")
        _link(db, p1, t)

        preview = c.post(f"{DK}/tag-templates/{t}/assign/preview",
                         json={"product_ids": [p1, p2]})
        assert preview.status_code == 200, preview.text
        assert preview.json() == {"matched": 2, "already_linked": 1}

        res = c.post(f"{DK}/tag-templates/{t}/assign",
                     json={"product_ids": [p1, p2], "action": "add"})
        assert res.status_code == 200, res.text
        assert res.json() == {"changed": 1}
        assert _links(db, t) == {p1, p2}
        assert untouched not in _links(db, t)

    def test_ids_alone_are_enough_but_none_at_all_is_refused(self, env):
        db, c, _ = env
        t = _template(db, "Pick")
        res = c.post(f"{DK}/tag-templates/{t}/assign", json={"product_ids": [], "action": "add"})
        assert res.status_code == 422

    def test_foreign_or_junk_ids_are_never_linked(self, env):
        db, c, _ = env
        ref = _reference(db)
        mine = _product(db, ref)
        foreign = _foreign_product(db)
        t = _template(db, "Pick")

        res = c.post(f"{DK}/tag-templates/{t}/assign",
                     json={"product_ids": [mine, foreign, "not-a-uuid", str(uuid.uuid4())],
                           "action": "add"})
        assert res.status_code == 200, res.text
        assert res.json() == {"changed": 1}
        assert _links(db, t) == {mine}

    def test_more_than_500_ids_is_refused(self, env):
        db, c, _ = env
        t = _template(db, "Pick")
        ids = [str(uuid.uuid4()) for _ in range(501)]
        res = c.post(f"{DK}/tag-templates/{t}/assign", json={"product_ids": ids, "action": "add"})
        assert res.status_code == 422

    def test_ids_narrow_a_filter_rather_than_widen_it(self, env):
        """AND across kinds, as the filter already is: ids plus a brand = those ids of that brand."""
        from app.models.product import Brand

        db, c, _ = env
        ref = _reference(db)
        other = Brand(id=str(uuid.uuid4()), brand_code=unique_code("br"),
                      brand_name=unique_code("Other"), company_id=SORENTO)
        db.add(other)
        db.flush()
        same_brand = _product(db, ref)
        other_brand = _product(db, ref, brand=other)
        t = _template(db, "Pick")
        res = c.post(f"{DK}/tag-templates/{t}/assign/preview",
                     json={"product_ids": [same_brand, other_brand], "brand_ids": [ref[1].id]})
        assert res.json()["matched"] == 1

    def test_viewer_cannot_assign_by_ids(self, env):
        db, c, as_ = env
        ref = _reference(db)
        p = _product(db, ref)
        t = _template(db, "Pick")
        as_(VIEWER_ID)
        res = c.post(f"{DK}/tag-templates/{t}/assign", json={"product_ids": [p], "action": "add"})
        assert res.status_code == 403
        assert _links(db, t) == set()


# ---------------------------------------------------------------------------
# Defaults: bulk link never changes an existing default
# ---------------------------------------------------------------------------


class TestDefaultsOnBulkLink:
    def test_a_first_template_becomes_the_default(self, env):
        db, c, _ = env
        ref = _reference(db)
        p = _product(db, ref)
        t = _template(db, "Pick")
        c.post(f"{DK}/tag-templates/{t}/assign", json={"product_ids": [p], "action": "add"})
        assert _flags(db, p) == {t: (True, True)}

    def test_a_single_existing_template_stays_the_default(self, env):
        db, c, _ = env
        ref = _reference(db)
        p = _product(db, ref)
        old = _template(db, "Old")
        _link(db, p, old)  # stored flags False: a lone link is the default implicitly
        t = _template(db, "Pick")
        c.post(f"{DK}/tag-templates/{t}/assign", json={"product_ids": [p], "action": "add"})
        assert _flags(db, p) == {old: (True, True), t: (False, False)}

    def test_stored_defaults_are_never_moved_or_filled(self, env):
        from app.models.dealer_kit import ProductTagTemplate

        db, c, _ = env
        ref = _reference(db)
        p = _product(db, ref)
        a, b = _template(db, "A"), _template(db, "B")
        db.add(ProductTagTemplate(product_id=p, template_id=a, default_list=True))
        db.add(ProductTagTemplate(product_id=p, template_id=b))
        db.flush()
        t = _template(db, "Pick")
        c.post(f"{DK}/tag-templates/{t}/assign", json={"product_ids": [p], "action": "add"})
        # a keeps LP, nobody gains SP (2+ links with no SP default stays without one).
        assert _flags(db, p) == {a: (True, False), b: (False, False), t: (False, False)}


# ---------------------------------------------------------------------------
# Remove by picked ids (the Save's countdown)
# ---------------------------------------------------------------------------


def test_deferred_unassign_by_ids_unlinks_only_those(env):
    from app.models.base import set_company_scope
    import app.services.record_actions  # noqa: F401  (registers the actions)
    from app.services.form_action_registry import get_action

    db, _c, _ = env
    ref = _reference(db)
    gone, kept = _product(db, ref), _product(db, ref)
    t = _template(db, "Pick")
    other = _template(db, "Other")
    _link(db, gone, t, other)
    _link(db, kept, t)

    action = get_action("tag_template.unassign_products")
    set_company_scope(db, frozenset({SORENTO}))
    result = action.execute(
        db, {"entity_id": t, "product_ids": [gone], "requested_by_id": MANAGER_ID}
    )
    assert result == {"changed": 1}, result
    assert _links(db, t) == {kept}
    # The product left with one template has it as its default.
    assert _flags(db, gone) == {other: (True, True)}


# ---------------------------------------------------------------------------
# Seed: which products use this template
# ---------------------------------------------------------------------------


class TestProductIds:
    def test_lists_the_linked_products_of_this_company_only(self, env):
        db, c, _ = env
        ref = _reference(db)
        p1, p2, unlinked = _product(db, ref), _product(db, ref), _product(db, ref)
        foreign = _foreign_product(db)
        t = _template(db, "Pick")
        _link(db, p1, t)
        _link(db, p2, t)
        _link(db, foreign, t)  # not reachable through the API; must still never be listed

        res = c.get(f"{DK}/tag-templates/{t}/product-ids")
        assert res.status_code == 200, res.text
        assert sorted(res.json()) == sorted([p1, p2])
        assert unlinked not in res.json()

    def test_unknown_template_is_404_and_viewer_is_403(self, env):
        db, c, as_ = env
        assert c.get(f"{DK}/tag-templates/{uuid.uuid4()}/product-ids").status_code == 404
        t = _template(db, "Pick")
        as_(VIEWER_ID)
        assert c.get(f"{DK}/tag-templates/{t}/product-ids").status_code == 403


# ---------------------------------------------------------------------------
# Products list filter: "Show: Uses this template"
# ---------------------------------------------------------------------------


def test_products_list_filters_by_tag_template(env):
    db, c, _ = env
    ref = _reference(db)
    p1, p2 = _product(db, ref), _product(db, ref)
    _product(db, ref)
    t = _template(db, "Pick")
    _link(db, p1, t)
    _link(db, p2, t)

    res = c.get("/api/v1/master-data/products/", params={"tag_template_id": t, "limit": 50})
    assert res.status_code == 200, res.text
    body = res.json()
    assert {row["id"] for row in body["data"]} == {p1, p2}
    assert body["pagination"]["total"] == 2
