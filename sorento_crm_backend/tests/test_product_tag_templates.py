"""Price tag templates per product (PRICETAG-TEMPLATE-PER-PRODUCT).

UAC: documentation/plans/dealer-kit/pricetag-template-per-product-acceptance-criteria.md.

Through ``TestClient`` (route mounting, permissions, response_model all matter),
Postgres only (``tests/_pg_fixture.py``). Every row this file makes carries the
``ZZT`` prefix and is rolled back.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app  # noqa: E402  (first app import, see test_portal_price_tag_routes)
from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"
PORTAL = "/api/v1/public/portal"
PTAG = f"{PORTAL}/submissions/price_tag_request"
DK = "/api/v1/dealer-kit"

MANAGER_ID = "6a7b8c9d-0e1f-5a6b-8c7d-9e0f1a2b3c01"
MANAGER_ROLE = "6a7b8c9d-0e1f-5a6b-8c7d-9e0f1a2b3c02"
VIEWER_ID = "6a7b8c9d-0e1f-5a6b-8c7d-9e0f1a2b3c03"
VIEWER_ROLE = "6a7b8c9d-0e1f-5a6b-8c7d-9e0f1a2b3c04"


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------


def _reference(db: Session):
    from app.models.product import Brand, ItemClass, ProductCategory, UnitOfMeasure

    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("cat"),
        category_name=unique_code("Category"),
        company_id=SORENTO,
    )
    brand = Brand(
        id=str(uuid.uuid4()),
        brand_code=unique_code("br"),
        brand_name=unique_code("Brand"),
        company_id=SORENTO,
    )
    item_class = ItemClass(
        id=str(uuid.uuid4()),
        item_class_code=unique_code("cls"),
        item_class_name=unique_code("Class"),
        company_id=SORENTO,
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()), uom_code=unique_code("uom"), uom_name="Each", company_id=SORENTO
    )
    db.add_all([category, brand, item_class, uom])
    db.flush()
    return category, brand, item_class, uom


def _product(db: Session, ref, *, code: str | None = None, family_code: str | None = None,
             brand=None, category=None, item_class=None) -> str:
    from app.models.product import Product

    category_, brand_, item_class_, uom = ref
    product = Product(
        id=str(uuid.uuid4()),
        product_code=code or unique_code("prod"),
        product_name=unique_code("Product"),
        category_id=(category or category_).id,
        brand_id=(brand or brand_).id if (brand or brand_) is not None else None,
        item_class_id=item_class.id if item_class is not None else None,
        base_uom_id=uom.id,
        list_price=100.00,
        company_id=SORENTO,
    )
    if family_code is not None:
        product.family_code = family_code
        product.family_code_manual = True
    db.add(product)
    db.flush()
    return product.id


def _doc(width=80, height=50, marker="x"):
    return {
        "layers": [
            {
                "id": f"layer-{marker}",
                "type": "text",
                "x_mm": 0,
                "y_mm": 0,
                "width_mm": 10,
                "height_mm": 5,
                "rotation": 0,
                "z_index": 0,
                "props": {"text": marker},
            }
        ],
        "width_mm": width,
        "height_mm": height,
    }


def _template(db: Session, name: str, *, family: str = "ala_carte", published: bool = True,
              width: int = 80, height: int = 50) -> str:
    from app.models.dealer_kit import TagTemplate, TagTemplateVersion

    template = TagTemplate(
        id=str(uuid.uuid4()),
        name=unique_code(name),
        family=family,
        doc=_doc(width, height, marker=f"draft-{name}"),
        print_size={"width_mm": width, "height_mm": height},
        company_id=SORENTO,
    )
    db.add(template)
    db.flush()
    if published:
        version = TagTemplateVersion(
            id=str(uuid.uuid4()),
            template_id=template.id,
            version_no=1,
            doc=_doc(width, height, marker=f"published-{name}"),
            print_size={"width_mm": width, "height_mm": height},
        )
        db.add(version)
        db.flush()
        template.published_version_id = version.id
        db.flush()
    return template.id


def _link(db: Session, product_id: str, *template_ids: str) -> None:
    from app.models.dealer_kit import ProductTagTemplate

    for template_id in template_ids:
        db.add(ProductTagTemplate(product_id=product_id, template_id=template_id))
    db.flush()


def _seed_roles(db: Session) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    slugs = ("dealer_kit.tag_templates.view", "dealer_kit.tag_templates.manage")
    perm_ids: dict[str, str] = {}
    for slug in slugs:
        existing = db.query(UserPermission).filter(UserPermission.slug == slug).first()
        if existing is None:
            existing = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
            db.add(existing)
            db.flush()
        perm_ids[slug] = existing.id
    for role_id, slug, user_id, granted in (
        (MANAGER_ROLE, "zzt_ptpt_manager", MANAGER_ID, slugs),
        (VIEWER_ROLE, "zzt_ptpt_viewer", VIEWER_ID, slugs[:1]),
    ):
        db.add(UserRole(id=role_id, slug=slug, name=slug, description="",
                        is_protected=False, is_default=False))
        db.add(User(id=user_id, email=f"{slug}@test.com", name=slug, status="ACTIVE"))
        db.flush()
        db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
        for granted_slug in granted:
            db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role_id,
                                      permission_id=perm_ids[granted_slug]))
    db.flush()


def _seed_contact(db: Session) -> str:
    from app.models.access import RespondContact
    from tests._portal_grant import link_contact_company, link_contact_segment, seed_segment

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(contact)
    db.flush()
    segment = seed_segment(db, kinds=["price_tag_request"])
    link_contact_segment(db, contact.id, segment.code)
    link_contact_company(db, contact.id)
    return contact.id


@pytest.fixture
def env():
    """(db, staff client acting as `as_(user)`, portal client)."""
    from app.api.v1.public.portal import get_portal_token
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.models.portal import PortalToken
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)
        contact_id = _seed_contact(db)

        def _db():
            yield db

        async def _scope():
            scope = frozenset({SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[apply_company_scope] = _scope
        app.dependency_overrides[get_portal_token] = lambda: PortalToken(
            id=str(uuid.uuid4()), contact_id=contact_id, space_id="zzt-space"
        )

        def as_(user_id: str) -> None:
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        as_(MANAGER_ID)
        set_company_scope(db, frozenset({SORENTO}))
        try:
            with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as client:
                yield db, client, as_
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# AC-2 / AC-3: product links
# ---------------------------------------------------------------------------


class TestProductLinks:
    def test_put_replaces_the_set_and_get_lists_it(self, env):
        db, c, _ = env
        ref = _reference(db)
        product = _product(db, ref)
        a = _template(db, "A")
        b = _template(db, "B", published=False)

        res = c.put(f"{DK}/products/{product}/tag-templates", json={"template_ids": [a, b, a]})
        assert res.status_code == 200, res.text
        assert {row["id"] for row in res.json()} == {a, b}
        assert {row["id"]: row["published"] for row in res.json()} == {a: True, b: False}

        res = c.put(f"{DK}/products/{product}/tag-templates", json={"template_ids": [b]})
        assert [row["id"] for row in res.json()] == [b]

        listed = c.get(f"{DK}/products/{product}/tag-templates")
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()] == [b]
        assert listed.json()[0]["width_mm"] == 80

    def test_viewer_can_read_but_not_write(self, env):
        db, c, as_ = env
        ref = _reference(db)
        product = _product(db, ref)
        a = _template(db, "A")
        as_(VIEWER_ID)

        assert c.get(f"{DK}/products/{product}/tag-templates").status_code == 200
        assert (
            c.put(f"{DK}/products/{product}/tag-templates", json={"template_ids": [a]}).status_code
            == 403
        )

    def test_unknown_template_or_product_is_404_and_writes_nothing(self, env):
        from app.models.dealer_kit import ProductTagTemplate

        db, c, _ = env
        ref = _reference(db)
        product = _product(db, ref)
        a = _template(db, "A")

        res = c.put(
            f"{DK}/products/{product}/tag-templates",
            json={"template_ids": [a, str(uuid.uuid4())]},
        )
        assert res.status_code == 404
        assert db.query(ProductTagTemplate).filter_by(product_id=product).count() == 0
        res = c.put(f"{DK}/products/{uuid.uuid4()}/tag-templates", json={"template_ids": [a]})
        assert res.status_code == 404

    def test_spec_sheet_family_cannot_be_linked(self, env):
        db, c, _ = env
        ref = _reference(db)
        product = _product(db, ref)
        spec = _template(db, "Spec", family="spec_page")

        res = c.put(f"{DK}/products/{product}/tag-templates", json={"template_ids": [spec]})
        assert res.status_code == 422
        assert res.json().get("code") == "NOT_A_PRICE_TAG_TEMPLATE" or "price tag" in res.text


# ---------------------------------------------------------------------------
# AC-5 / AC-6: bulk assignment
# ---------------------------------------------------------------------------


class TestBulkAssign:
    def test_empty_filter_is_refused(self, env):
        db, c, _ = env
        t = _template(db, "Bulk")
        assert c.post(f"{DK}/tag-templates/{t}/assign/preview", json={}).status_code == 422
        assert (
            c.post(f"{DK}/tag-templates/{t}/assign", json={"action": "add"}).status_code == 422
        )

    def test_add_then_remove_by_brand_and_category(self, env):
        from app.models.dealer_kit import ProductTagTemplate
        from app.models.product import Brand

        db, c, _ = env
        ref = _reference(db)
        category, brand, _cls, _uom = ref
        other_brand = Brand(id=str(uuid.uuid4()), brand_code=unique_code("br"),
                            brand_name=unique_code("Other"), company_id=SORENTO)
        db.add(other_brand)
        db.flush()
        p1 = _product(db, ref)
        p2 = _product(db, ref)
        outsider = _product(db, ref, brand=other_brand)
        t = _template(db, "Bulk")
        _link(db, p1, t)
        body = {"brand_ids": [brand.id], "category_ids": [category.id]}

        preview = c.post(f"{DK}/tag-templates/{t}/assign/preview", json=body)
        assert preview.status_code == 200, preview.text
        assert preview.json() == {"matched": 2, "already_linked": 1}

        added = c.post(f"{DK}/tag-templates/{t}/assign", json={**body, "action": "add"})
        assert added.json() == {"changed": 1}
        linked = {r.product_id for r in db.query(ProductTagTemplate).filter_by(template_id=t)}
        assert linked == {p1, p2}
        assert outsider not in linked

        removed = c.post(f"{DK}/tag-templates/{t}/assign", json={**body, "action": "remove"})
        assert removed.json() == {"changed": 2}
        assert db.query(ProductTagTemplate).filter_by(template_id=t).count() == 0

    def test_item_class_and_model_family_filters(self, env):
        db, c, _ = env
        ref = _reference(db)
        _cat, _brand, item_class, _uom = ref
        family = unique_code("FAM")
        p_class = _product(db, ref, item_class=item_class)
        p_family = _product(db, ref, family_code=family)
        _product(db, ref)
        t = _template(db, "Bulk")

        res = c.post(f"{DK}/tag-templates/{t}/assign/preview",
                     json={"item_class_ids": [item_class.id]})
        assert res.json()["matched"] == 1
        res = c.post(f"{DK}/tag-templates/{t}/assign/preview", json={"family_codes": [family]})
        assert res.json()["matched"] == 1
        # AND across kinds: no product has both.
        res = c.post(f"{DK}/tag-templates/{t}/assign/preview",
                     json={"item_class_ids": [item_class.id], "family_codes": [family]})
        assert res.json()["matched"] == 0
        assert p_class != p_family

    def test_viewer_cannot_bulk_assign(self, env):
        db, c, as_ = env
        ref = _reference(db)
        t = _template(db, "Bulk")
        as_(VIEWER_ID)
        res = c.post(f"{DK}/tag-templates/{t}/assign",
                     json={"brand_ids": [ref[1].id], "action": "add"})
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# AC-8 .. AC-13: request lines
# ---------------------------------------------------------------------------


def _draft(c: TestClient, lines: list[dict]) -> dict:
    res = c.post(
        PTAG,
        json={"debtor_name": "ZZT Dealer", "debtor_code": "ZZT-D", "print_by": "office",
              "lines": lines},
    )
    assert res.status_code == 201, res.text
    return res.json()


class TestRequestLines:
    def test_lookup_lists_only_published_price_tag_links(self, env):
        db, c, _ = env
        ref = _reference(db)
        product = _product(db, ref)
        live = _template(db, "Live")
        draft = _template(db, "Draft", published=False)
        _link(db, product, live, draft)

        res = c.get(f"{PORTAL}/lookups/product-tag-templates/{product}")
        assert res.status_code == 200, res.text
        assert [row["id"] for row in res.json()] == [live]

    def test_single_link_is_filled_in_on_save(self, env):
        db, c, _ = env
        ref = _reference(db)
        product = _product(db, ref)
        only = _template(db, "Only")
        _link(db, product, only)

        body = _draft(c, [{"line_type": "product", "product_id": product}])
        assert body["lines"][0]["tag_template_id"] == only
        detail = c.get(f"{PTAG}/{body['id']}").json()
        assert detail["lines"][0]["tag_template_name"].startswith("ZZT-Only")

    def test_many_links_need_a_pick_at_submit(self, env):
        db, c, _ = env
        ref = _reference(db)
        plain = _product(db, ref)
        product = _product(db, ref)
        a = _template(db, "A")
        b = _template(db, "B")
        _link(db, product, a, b)

        body = _draft(
            c,
            [
                {"line_type": "product", "product_id": plain},
                {"line_type": "product", "product_id": product},
            ],
        )
        assert body["lines"][1]["tag_template_id"] is None

        res = c.post(f"{PTAG}/{body['id']}/submit")
        assert res.status_code == 422, res.text
        payload = res.json()
        assert payload.get("code") == "TAG_TEMPLATE_REQUIRED"
        assert "line:1" in res.text
        assert "Pick a tag template for this line." in res.text

        res = c.put(
            f"{PTAG}/{body['id']}",
            json={
                "lines": [
                    {"line_type": "product", "product_id": plain},
                    {"line_type": "product", "product_id": product, "tag_template_id": b},
                ]
            },
        )
        assert res.status_code == 200, res.text
        assert res.json()["lines"][1]["tag_template_id"] == b
        assert c.post(f"{PTAG}/{body['id']}/submit").status_code == 200

    def test_a_pick_outside_the_links_is_dropped_not_stored(self, env):
        db, c, _ = env
        ref = _reference(db)
        product = _product(db, ref)
        a = _template(db, "A")
        b = _template(db, "B")
        stranger = _template(db, "Stranger")
        _link(db, product, a, b)

        body = _draft(
            c,
            [{"line_type": "product", "product_id": product, "tag_template_id": stranger}],
        )
        assert body["lines"][0]["tag_template_id"] is None
        junk = _draft(
            c, [{"line_type": "product", "product_id": product, "tag_template_id": "not-a-uuid"}]
        )
        assert junk["lines"][0]["tag_template_id"] is None

    def test_no_links_means_no_field_and_no_refusal(self, env):
        db, c, _ = env
        ref = _reference(db)
        product = _product(db, ref)

        body = _draft(c, [{"line_type": "product", "product_id": product}])
        assert body["lines"][0]["tag_template_id"] is None
        assert c.post(f"{PTAG}/{body['id']}/submit").status_code == 200

    def test_deleting_a_template_clears_the_line_pick(self, env):
        from app.models.dealer_kit import TagTemplate
        from app.models.price_tag import PriceTagRequestLine

        db, c, _ = env
        ref = _reference(db)
        product = _product(db, ref)
        only = _template(db, "Only")
        _link(db, product, only)
        body = _draft(c, [{"line_type": "product", "product_id": product}])

        db.query(TagTemplate).filter(TagTemplate.id == only).delete(synchronize_session=False)
        db.flush()
        db.expire_all()
        line = db.query(PriceTagRequestLine).filter_by(request_id=body["id"]).one()
        assert line.tag_template_id is None


# ---------------------------------------------------------------------------
# AC-15: live preview
# ---------------------------------------------------------------------------


class TestPreview:
    def test_preview_picks_the_template_and_writes_nothing(self, env):
        from app.models.price_tag import PriceTagRequest

        db, c, _ = env
        ref = _reference(db)
        single = _product(db, ref)
        many = _product(db, ref)
        unlinked = _product(db, ref, code="SRTMR" + uuid.uuid4().hex[:6])
        one = _template(db, "One")
        a = _template(db, "A", width=100, height=70)
        b = _template(db, "B", width=120, height=90)
        mirror = _template(db, "Mirror", family="mirror")
        _template(db, "Spec", family="spec_page")
        _link(db, single, one)
        _link(db, many, a, b)
        before = db.query(PriceTagRequest).count()

        res = c.post(
            f"{PORTAL}/lookups/tag-preview",
            json={
                "price_mode": "list",
                "lines": [
                    {"key": "k1", "line_type": "product", "product_id": single},
                    {"key": "k2", "line_type": "product", "product_id": many,
                     "tag_template_id": b},
                    {"key": "k3", "line_type": "product", "product_id": unlinked},
                    {"key": "k4", "line_type": "product", "product_id": "junk"},
                ],
            },
        )
        assert res.status_code == 200, res.text
        out = res.json()
        assert out["templates"]["k1"]["id"] == one
        assert out["templates"]["k2"]["id"] == b
        # The PUBLISHED version's doc, never the draft.
        assert out["templates"]["k2"]["doc"]["layers"][0]["props"]["text"] == "published-B"
        assert out["templates"]["k3"]["id"] == mirror
        assert "k4" not in out["templates"]
        assert {row["line_id"] for row in out["lines"]} == {"k1", "k2", "k3"}
        assert all(row["code"] for row in out["lines"])
        assert {"assets", "images", "fonts"} <= set(out)
        assert db.query(PriceTagRequest).count() == before

    def test_preview_with_many_and_no_pick_draws_the_first_link(self, env):
        db, c, _ = env
        ref = _reference(db)
        many = _product(db, ref)
        a = _template(db, "AAA")
        b = _template(db, "BBB")
        _link(db, many, b, a)

        out = c.post(
            f"{PORTAL}/lookups/tag-preview",
            json={"lines": [{"key": "k", "line_type": "product", "product_id": many}]},
        ).json()
        assert out["templates"]["k"]["id"] == a  # by name: ZZT-AAA-... before ZZT-BBB-...


class TestPreviewForASavedRequest:
    def test_request_mode_answers_real_line_and_tag_ids(self, env):
        from app.models.price_tag import PriceTagRequestLine, PriceTagRequestTag

        db, c, _ = env
        ref = _reference(db)
        product = _product(db, ref)
        a = _template(db, "A")
        b = _template(db, "B")
        _link(db, product, a, b)
        body = _draft(
            c, [{"line_type": "product", "product_id": product, "tag_template_id": b}]
        )
        line = db.query(PriceTagRequestLine).filter_by(request_id=body["id"]).one()
        tag = db.query(PriceTagRequestTag).filter_by(line_id=line.id).one()

        res = c.post(f"{PORTAL}/lookups/tag-preview", json={"request_id": body["id"]})
        assert res.status_code == 200, res.text
        out = res.json()
        assert out["templates"][line.id]["id"] == b
        assert [(r["line_id"], r["tag_id"]) for r in out["lines"]] == [(line.id, tag.id)]

    def test_another_contacts_request_is_404(self, env):
        from app.services.price_tag_request_service import PriceTagRequestService

        db, c, _ = env
        other = _seed_contact(db)
        theirs = PriceTagRequestService.create_request(
            db, contact_id=other, company_id=SORENTO, data={"debtor_name": "ZZT Theirs"}
        )
        db.flush()
        res = c.post(f"{PORTAL}/lookups/tag-preview", json={"request_id": theirs.id})
        assert res.status_code == 404
        res = c.post(f"{PORTAL}/lookups/tag-preview", json={"request_id": "junk"})
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# The family table is kept in step with the frontend's
# ---------------------------------------------------------------------------


def test_family_for_matches_frontend_table():
    from app.services.dealer_kit.product_tag_template_service import _FAMILY_PREFIXES

    ts = (
        Path(__file__).resolve().parents[2]
        / "sorento_crm_frontend" / "lib" / "dealer-kit" / "line-family.ts"
    ).read_text()
    pairs = tuple(re.findall(r"\['(\w+)', '(\w+)'\]", ts))
    assert pairs == _FAMILY_PREFIXES


def test_family_codes_lists_distinct_families(env):
    db, c, as_ = env
    ref = _reference(db)
    family = unique_code("FAMLIST")
    _product(db, ref, family_code=family)
    _product(db, ref, family_code=family)
    res = c.get(f"{DK}/tag-templates/family-codes", params={"q": family})
    assert res.status_code == 200, res.text
    assert res.json() == [family]
    as_(VIEWER_ID)
    assert c.get(f"{DK}/tag-templates/family-codes").status_code == 403


def test_deferred_remove_unlinks_the_matching_products(env):
    """`tag_template.unassign_products` (the dialog's Remove, a parked unlink)."""
    from app.models.dealer_kit import ProductTagTemplate
    import app.services.record_actions  # noqa: F401  (registers the actions)
    from app.services.form_action_registry import get_action

    db, _c, _ = env
    ref = _reference(db)
    p1 = _product(db, ref)
    t = _template(db, "Bulk")
    keep = _template(db, "Keep")
    _link(db, p1, t, keep)

    action = get_action("tag_template.unassign_products")
    assert action.permission == "dealer_kit.tag_templates.manage"
    result = action.execute(
        db, {"entity_id": t, "brand_ids": [ref[1].id], "requested_by_id": MANAGER_ID}
    )
    assert result == {"changed": 1}
    assert {r.template_id for r in db.query(ProductTagTemplate).filter_by(product_id=p1)} == {keep}


@pytest.mark.parametrize("price_mode", ["list", "selling"])
def test_preview_never_prices_a_promotion_outside_the_contacts_audience(env, price_mode):
    """Security review: the resolver prices with the staff viewer, so a promotion
    the contact may not see must be dropped before it, in BOTH modes."""
    from app.models.product import Product
    from tests.test_price_tag_line_pricing import _promotion

    db, c, _ = env
    ref = _reference(db)
    product_id = _product(db, ref)
    _template(db, "Any")
    product = db.query(Product).filter(Product.id == product_id).one()
    hidden = _promotion(db, [(product, "40.00")], access_levels=["zzt_nobody"])

    out = c.post(
        f"{PORTAL}/lookups/tag-preview",
        json={
            "price_mode": price_mode,
            "lines": [
                {"key": "k", "line_type": "product", "product_id": product_id,
                 "promotion_id": hidden.id}
            ],
        },
    ).json()
    assert out["lines"], out
    assert float(out["lines"][0]["sell_price"] or 100) != 40.0
    assert "40" not in str(out["lines"][0].get("sell_price"))


def test_deferred_product_unlink_removes_only_the_named_links(env):
    """`product.unlink_tag_templates` (the product card's untick, a parked unlink)."""
    from app.models.dealer_kit import ProductTagTemplate
    import app.services.record_actions  # noqa: F401  (registers the actions)
    from app.services.form_action_registry import get_action

    db, c, _ = env
    ref = _reference(db)
    product = _product(db, ref)
    a = _template(db, "A")
    b = _template(db, "B")
    _link(db, product, a, b)

    action = get_action("product.unlink_tag_templates")
    assert action.permission == "dealer_kit.tag_templates.manage"
    assert action.execute(db, {"entity_id": product, "template_ids": [a]}) == {"changed": 1}
    assert {r.template_id for r in db.query(ProductTagTemplate).filter_by(product_id=product)} == {b}


def test_product_lookup_is_scoped(env):
    from app.models.base import set_company_scope

    db, c, _ = env
    ref = _reference(db)
    product = _product(db, ref)
    assert c.get(f"{DK}/products/{product}/tag-templates").status_code == 200
    from app.services.dealer_kit import product_tag_template_service

    set_company_scope(db, frozenset({"11111111-1111-1111-1111-111111111111"}))
    assert product_tag_template_service.product_exists(db, product) is False
    set_company_scope(db, frozenset({SORENTO}))
