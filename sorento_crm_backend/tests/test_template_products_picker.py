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

import pytest

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
        ref = _reference(db)
        _product(db, ref)
        t = _template(db, "Pick")
        ids = [str(uuid.uuid4()) for _ in range(501)]
        # With a brand that matches, so only the id cap can refuse it.
        res = c.post(f"{DK}/tag-templates/{t}/assign",
                     json={"product_ids": ids, "brand_ids": [ref[1].id], "action": "add"})
        assert res.status_code == 422
        assert _links(db, t) == set()

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
        _product(db, ref)  # same brand, not picked
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


# ---------------------------------------------------------------------------
# Review round 1 (reviewer B1 / S5, security nits 1 and 3)
# ---------------------------------------------------------------------------


class TestJunkAndForeign:
    def test_only_junk_ids_match_nothing_never_everything(self, env):
        import app.services.record_actions  # noqa: F401  (registers the actions)
        from app.models.base import set_company_scope
        from app.services.form_action_registry import get_action

        db, c, _ = env
        ref = _reference(db)
        p1, p2 = _product(db, ref), _product(db, ref)
        t = _template(db, "Pick")
        _link(db, p1, t)
        junk = {"product_ids": ["not-a-uuid", "also-junk"]}

        preview = c.post(f"{DK}/tag-templates/{t}/assign/preview", json=junk)
        assert preview.status_code == 200, preview.text
        assert preview.json() == {"matched": 0, "already_linked": 0}
        added = c.post(f"{DK}/tag-templates/{t}/assign", json={**junk, "action": "add"})
        assert added.json() == {"changed": 0}
        assert _links(db, t) == {p1}

        set_company_scope(db, frozenset({SORENTO}))
        result = get_action("tag_template.unassign_products").execute(
            db, {"entity_id": t, **junk, "requested_by_id": MANAGER_ID}
        )
        assert result == {"changed": 0}
        assert _links(db, t) == {p1}
        assert p2 not in _links(db, t)

    def test_deferred_unassign_never_touches_a_foreign_product(self, env):
        import app.services.record_actions  # noqa: F401
        from app.models.base import set_company_scope
        from app.services.form_action_registry import get_action

        db, _c, _ = env
        foreign = _foreign_product(db)
        t = _template(db, "Pick")
        _link(db, foreign, t)  # not reachable through the API; must survive
        set_company_scope(db, frozenset({SORENTO}))
        result = get_action("tag_template.unassign_products").execute(
            db, {"entity_id": t, "product_ids": [foreign], "requested_by_id": MANAGER_ID}
        )
        assert result == {"changed": 0}
        assert _links(db, t) == {foreign}

    def test_parking_an_unassign_with_more_than_500_ids_is_refused(self, env):
        db, c, _ = env
        t = _template(db, "Pick")
        res = c.post(
            "/api/v1/pending-actions",
            json={
                "action_key": "tag_template.unassign_products",
                "entity_type": "tag_template",
                "entity_id": t,
                "payload": {"product_ids": [str(uuid.uuid4()) for _ in range(501)]},
            },
        )
        assert res.status_code == 400, res.text
        assert res.json()["code"] == "VALIDATION_ERROR"

    def test_products_list_rejects_a_non_uuid_template_id(self, env):
        _db, c, _ = env
        res = c.get("/api/v1/master-data/products/", params={"tag_template_id": "nope"})
        assert res.status_code == 400

    def test_products_list_ignores_a_template_outside_the_scope(self, env):
        from app.models.company import Company
        from app.models.dealer_kit import TagTemplate

        db, c, _ = env
        ref = _reference(db)
        mine = _product(db, ref)
        other_company = str(uuid.uuid4())
        db.add(Company(id=other_company, name=unique_code("ZZT Other"), code=unique_code("OC")[:20]))
        db.flush()
        theirs = TagTemplate(id=str(uuid.uuid4()), name=unique_code("Theirs"), family="ala_carte",
                             doc={"layers": [], "width_mm": 80, "height_mm": 50},
                             print_size={}, company_id=other_company)
        db.add(theirs)
        db.flush()
        _link(db, mine, theirs.id)  # not reachable through the API

        res = c.get("/api/v1/master-data/products/", params={"tag_template_id": theirs.id})
        assert res.status_code == 200, res.text
        assert res.json()["data"] == []


# ---------------------------------------------------------------------------
# Crew pass on c6e3e014 (AC-7): what the product card SHOWS as Default LP / SP never moves
# ---------------------------------------------------------------------------


def _typed(db, name: str, price_type):
    """A published template with a price type (None fits LP and SP lines)."""
    from app.models.dealer_kit import TagTemplate

    tid = _template(db, name)
    db.get(TagTemplate, tid).price_type = price_type
    db.flush()
    return tid


def _card(c, product_id: str) -> dict[str, tuple[bool, bool]]:
    """The product page card: template id -> (Default LP, Default SP), as the card shows it."""
    res = c.get(f"{DK}/products/{product_id}/tag-templates")
    assert res.status_code == 200, res.text
    return {row["id"]: (row["default_list"], row["default_selling"]) for row in res.json()}


class TestShownDefaultsNeverMove:
    @pytest.mark.parametrize("new_type", ["selling", "list", None])
    def test_an_implicit_default_survives_a_bulk_link(self, env, new_type):
        """Crew repro: CB2151-DIY has DIY Tag (LP + SP) and Small Price Tag LP. The card shows
        Default SP = DIY Tag (the only SP fit, never saved). Linking an SP template in bulk
        emptied it."""
        db, c, _ = env
        ref = _reference(db)
        p = _product(db, ref)
        diy = _typed(db, "DIY", None)
        small_lp = _typed(db, "SmallLP", "list")
        _link(db, p, diy, small_lp)  # no saved flags at all
        before = _card(c, p)
        assert before == {diy: (False, True), small_lp: (False, False)}

        new = _typed(db, "SmallSP", new_type)
        res = c.post(f"{DK}/tag-templates/{new}/assign", json={"product_ids": [p], "action": "add"})
        assert res.json() == {"changed": 1}
        after = _card(c, p)
        assert after[diy] == before[diy]
        assert after[small_lp] == before[small_lp]
        assert after[new] == (False, False)

    def test_an_implicit_lp_default_survives_too(self, env):
        db, c, _ = env
        ref = _reference(db)
        p = _product(db, ref)
        lp = _typed(db, "LP", "list")
        sp = _typed(db, "SP", "selling")
        _link(db, p, lp, sp)
        assert _card(c, p) == {lp: (True, False), sp: (False, True)}
        new = _typed(db, "Both", None)
        c.post(f"{DK}/tag-templates/{new}/assign", json={"product_ids": [p], "action": "add"})
        assert _card(c, p) == {lp: (True, False), sp: (False, True), new: (False, False)}

    def test_unlinking_the_default_clears_only_that_default(self, env):
        """Matches the product page: the removed template's default goes; a lone remaining fit
        for that type becomes the saved default; the other type is untouched."""
        import app.services.record_actions  # noqa: F401
        from app.models.base import set_company_scope
        from app.models.dealer_kit import ProductTagTemplate
        from app.services.form_action_registry import get_action

        db, c, _ = env
        ref = _reference(db)
        p = _product(db, ref)
        diy = _typed(db, "DIY", None)
        small_lp = _typed(db, "SmallLP", "list")
        db.add(ProductTagTemplate(product_id=p, template_id=diy, default_selling=True))
        db.add(ProductTagTemplate(product_id=p, template_id=small_lp, default_list=True))
        db.flush()
        assert _card(c, p) == {diy: (False, True), small_lp: (True, False)}

        set_company_scope(db, frozenset({SORENTO}))
        get_action("tag_template.unassign_products").execute(
            db, {"entity_id": diy, "product_ids": [p], "requested_by_id": MANAGER_ID}
        )
        assert _card(c, p) == {small_lp: (True, False)}
        assert _flags(db, p) == {small_lp: (True, False)}


# ---------------------------------------------------------------------------
# Owner hand test 11 Nov: "it should be able to link to combos also" (reverses card Q1)
# Same rows as the combo page: dealer_kit.combo_tag_template.
# ---------------------------------------------------------------------------


def _host_combo(db, ref, code: str | None = None, name: str = "ZZT combo"):
    """(host product id, combo id) for a combo with no parts."""
    from app.models.product import Product
    from tests import _ptag_combo_seed as combo_seed

    host_id = _product(db, ref, code=code)
    combo = combo_seed.combo(db, db.get(Product, host_id), unique_code(name))
    return host_id, combo.id


def _foreign_host_combo(db):
    """A combo on another company's product (built by id: the scoped session cannot load it)."""
    from app.models.product_combo import ProductCombo

    combo = ProductCombo(id=str(uuid.uuid4()), host_product_id=_foreign_product(db),
                         name=unique_code("ZZT foreign combo"), sort_order=0)
    db.add(combo)
    db.flush()
    return combo.id


def _combo_links(db, template_id: str) -> set[str]:
    from app.models.dealer_kit import ComboTagTemplate

    return {r.combo_id for r in db.query(ComboTagTemplate).filter_by(template_id=template_id)}


def _fixed_parts_template(db, name: str, fixed: int) -> str:
    """A published template whose doc prints `fixed` fixed combo parts (needs them)."""
    from app.models.dealer_kit import TagTemplate

    tid = _template(db, name)
    layers = [
        {"id": f"f{i}", "type": "text", "x_mm": 0, "y_mm": 0, "width_mm": 10, "height_mm": 5,
         "rotation": 0, "z_index": 1,
         "props": {"kind": "text", "subjectSlot": {"kind": "fixed", "index": i}}}
        for i in range(fixed)
    ]
    template = db.get(TagTemplate, tid)
    template.published_version.doc = {"layers": layers, "width_mm": 80, "height_mm": 50}
    db.flush()
    return tid


class TestCombos:
    def test_combo_ids_seed_lists_this_companys_linked_combos(self, env):
        from app.models.dealer_kit import ComboTagTemplate

        db, c, as_ = env
        ref = _reference(db)
        _h1, linked = _host_combo(db, ref)
        _h2, unlinked = _host_combo(db, ref)
        foreign = _foreign_host_combo(db)
        t = _template(db, "Pick")
        db.add(ComboTagTemplate(combo_id=linked, template_id=t))
        db.add(ComboTagTemplate(combo_id=foreign, template_id=t))
        db.flush()
        res = c.get(f"{DK}/tag-templates/{t}/combo-ids")
        assert res.status_code == 200, res.text
        assert res.json() == [linked]
        assert unlinked not in res.json()
        as_(VIEWER_ID)
        assert c.get(f"{DK}/tag-templates/{t}/combo-ids").status_code == 403

    def test_combo_list_searches_host_code_or_name_and_says_why_one_cannot_print(self, env):
        db, c, _ = env
        ref = _reference(db)
        code = unique_code("SRTKS", alpha=True)
        _host, combo = _host_combo(db, ref, code=code, name="Sink set")
        _host_combo(db, ref)  # another host, not matched
        _foreign_host_combo(db)
        plain = _template(db, "Plain")
        three_fixed = _fixed_parts_template(db, "ThreeFixed", 3)

        res = c.get(f"{DK}/tag-templates/{plain}/combos", params={"query": code})
        assert res.status_code == 200, res.text
        body = res.json()
        assert [row["id"] for row in body["data"]] == [combo]
        row = body["data"][0]
        assert row["host_code"] == code
        assert row["fit_reason"] is None  # a plain template prints every combo as one product
        assert body["pagination"]["total"] == 1

        res = c.get(f"{DK}/tag-templates/{three_fixed}/combos", params={"query": code})
        assert res.json()["data"][0]["fit_reason"] == "Needs 3 fixed parts; this combo has 0"

    def test_combo_list_can_show_only_the_linked_combos(self, env):
        from app.models.dealer_kit import ComboTagTemplate

        db, c, _ = env
        ref = _reference(db)
        _h1, linked = _host_combo(db, ref)
        _h2, _unlinked = _host_combo(db, ref)
        t = _template(db, "Pick")
        db.add(ComboTagTemplate(combo_id=linked, template_id=t))
        db.flush()
        res = c.get(f"{DK}/tag-templates/{t}/combos", params={"linked": "true", "limit": 50})
        assert [row["id"] for row in res.json()["data"]] == [linked]

    def test_assign_links_picked_combos_and_skips_foreign_junk_and_misfits(self, env):
        db, c, _ = env
        ref = _reference(db)
        _h1, combo = _host_combo(db, ref)
        foreign = _foreign_host_combo(db)
        plain = _template(db, "Plain")
        res = c.post(f"{DK}/tag-templates/{plain}/assign",
                     json={"combo_ids": [combo, foreign, "junk"], "action": "add"})
        assert res.status_code == 200, res.text
        assert res.json()["changed"] == 1
        assert _combo_links(db, plain) == {combo}

        three_fixed = _fixed_parts_template(db, "ThreeFixed", 3)
        res = c.post(f"{DK}/tag-templates/{three_fixed}/assign",
                     json={"combo_ids": [combo], "action": "add"})
        assert res.json() == {"changed": 0, "skipped": 1}
        assert _combo_links(db, three_fixed) == set()

    def test_products_and_combos_in_one_save(self, env):
        db, c, _ = env
        ref = _reference(db)
        p = _product(db, ref)
        _h, combo = _host_combo(db, ref)
        t = _template(db, "Pick")
        res = c.post(f"{DK}/tag-templates/{t}/assign",
                     json={"product_ids": [p], "combo_ids": [combo], "action": "add"})
        assert res.json()["changed"] == 2
        assert _links(db, t) == {p}
        assert _combo_links(db, t) == {combo}

    def test_the_combo_page_reads_the_same_rows_and_shown_defaults_never_move(self, env):
        from app.models.dealer_kit import ComboTagTemplate

        db, c, _ = env
        ref = _reference(db)
        _h, combo = _host_combo(db, ref)
        diy = _typed(db, "DIY", None)
        small_lp = _typed(db, "SmallLP", "list")
        db.add(ComboTagTemplate(combo_id=combo, template_id=diy))
        db.add(ComboTagTemplate(combo_id=combo, template_id=small_lp))
        db.flush()

        def card():
            res = c.get(f"{DK}/combos/{combo}/tag-templates")
            assert res.status_code == 200, res.text
            return {r["id"]: (r["default_list"], r["default_selling"]) for r in res.json()}

        before = card()
        assert before == {diy: (False, True), small_lp: (False, False)}
        small_sp = _typed(db, "SmallSP", "selling")
        c.post(f"{DK}/tag-templates/{small_sp}/assign", json={"combo_ids": [combo], "action": "add"})
        after = card()
        assert after[diy] == before[diy]
        assert after[small_lp] == before[small_lp]
        assert after[small_sp] == (False, False)

    def test_a_first_template_becomes_the_combos_default(self, env):
        db, c, _ = env
        ref = _reference(db)
        _h, combo = _host_combo(db, ref)
        t = _template(db, "Pick")
        c.post(f"{DK}/tag-templates/{t}/assign", json={"combo_ids": [combo], "action": "add"})
        res = c.get(f"{DK}/combos/{combo}/tag-templates").json()
        assert [(r["id"], r["default_list"], r["default_selling"]) for r in res] == [(t, True, True)]

    def test_deferred_unassign_by_combo_ids(self, env):
        import app.services.record_actions  # noqa: F401
        from app.models.base import set_company_scope
        from app.models.dealer_kit import ComboTagTemplate
        from app.services.form_action_registry import get_action

        db, _c, _ = env
        ref = _reference(db)
        _h1, gone = _host_combo(db, ref)
        _h2, kept = _host_combo(db, ref)
        foreign = _foreign_host_combo(db)
        t = _template(db, "Pick")
        for cid in (gone, kept, foreign):
            db.add(ComboTagTemplate(combo_id=cid, template_id=t))
        db.flush()
        set_company_scope(db, frozenset({SORENTO}))
        result = get_action("tag_template.unassign_products").execute(
            db, {"entity_id": t, "combo_ids": [gone, foreign], "requested_by_id": MANAGER_ID}
        )
        assert result == {"changed": 1}
        assert _combo_links(db, t) == {kept, foreign}

    def test_parking_more_than_500_combo_ids_is_refused(self, env):
        db, c, _ = env
        t = _template(db, "Pick")
        res = c.post(
            "/api/v1/pending-actions",
            json={"action_key": "tag_template.unassign_products", "entity_type": "tag_template",
                  "entity_id": t,
                  "payload": {"combo_ids": [str(uuid.uuid4()) for _ in range(501)]}},
        )
        assert res.status_code == 400, res.text
