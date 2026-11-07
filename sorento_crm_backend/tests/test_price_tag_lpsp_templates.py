"""PRICETAG-LPSP S3: a default tag template per product, and template links on combos.

UAC: documentation/plans/dealer-kit/pricetag-lpsp-acceptance-criteria.md, AC-8 to AC-11.

Written test-FIRST (PRINCIPLES.md Phase 2). `is_default`, `default_template_id`, `ComboTagTemplate`
and the `/dealer-kit/combos/{id}/tag-templates` routes do not exist yet; every case is red as an
unknown field / 404 / missing import, not as a harness error.

Same harness as `tests/test_product_tag_templates.py` (staff manager + viewer, portal contact,
Postgres scratch schema); its seed helpers are reused rather than copied.

Pick order under test (plan S3): sent pick if allowed -> the default -> the only link ->
(preview only) the first link.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.company import Company
from tests import _ptag_combo_seed as combo_seed
from tests._pg_fixture import unique_code
from tests.test_product_tag_templates import (  # noqa: F401  (env is a fixture)
    DK,
    MANAGER_ID,
    PORTAL,
    PTAG,
    SORENTO,
    VIEWER_ID,
    _draft,
    _link,
    _product,
    _reference,
    _template,
    env,
)

MOCHA = "00000000-0000-0000-0000-000000000002"


# --------------------------------------------------------------------------- helpers
def _link_default(db, product_id: str, default_id: str, *other_ids: str) -> None:
    from app.models.dealer_kit import ProductTagTemplate

    db.add(ProductTagTemplate(
            product_id=product_id, template_id=default_id, default_list=True, default_selling=True
        ))
    for template_id in other_ids:
        db.add(ProductTagTemplate(product_id=product_id, template_id=template_id))
    db.flush()


def _combo(db, host_id: str, name: str = "ZZT combo"):
    from app.models.product import Product

    host = host_id if isinstance(host_id, Product) else db.get(Product, host_id)
    return combo_seed.combo(db, host, unique_code(name))


def _combo_link(db, combo_id: str, *template_ids: str, default: str | None = None) -> None:
    from app.models.dealer_kit import ComboTagTemplate

    for template_id in template_ids:
        db.add(
            ComboTagTemplate(
                combo_id=combo_id,
                template_id=template_id,
                default_list=(template_id == default),
                default_selling=(template_id == default),
            )
        )
    db.flush()


def _defaults(items: list[dict]) -> list[str]:
    return [row["id"] for row in items if row["is_default"]]


def _foreign_combo(db):
    """A combo whose host product belongs to another company."""
    from app.models.product import Product

    if db.get(Company, MOCHA) is None:
        db.add(Company(id=MOCHA, name="ZZT Mocha", code=unique_code("MCH")[:20], is_active=True))
        db.flush()
    host_id = _product(db, _reference(db))
    host = db.get(Product, host_id)
    host.company_id = MOCHA
    db.flush()
    return host_id, _combo(db, host, "ZZT foreign")


# --------------------------------------------------------------------------- AC-8
class TestProductDefault:
    def test_put_with_a_default_stores_exactly_one_and_get_reports_it(self, env):
        from app.models.dealer_kit import ProductTagTemplate

        db, c, _ = env
        product = _product(db, _reference(db))
        a, b, x = _template(db, "A"), _template(db, "B"), _template(db, "X")

        res = c.put(
            f"{DK}/products/{product}/tag-templates",
            json={"template_ids": [a, b, x], "default_template_id": b},
        )
        assert res.status_code == 200, res.text
        assert _defaults(res.json()) == [b]
        assert db.query(ProductTagTemplate).filter_by(product_id=product, default_list=True, default_selling=True).count() == 1

        listed = c.get(f"{DK}/products/{product}/tag-templates").json()
        assert _defaults(listed) == [b]
        assert {row["id"] for row in listed} == {a, b, x}

    def test_moving_the_default_leaves_one(self, env):
        from app.models.dealer_kit import ProductTagTemplate

        db, c, _ = env
        product = _product(db, _reference(db))
        a, b = _template(db, "A"), _template(db, "B")
        url = f"{DK}/products/{product}/tag-templates"
        c.put(url, json={"template_ids": [a, b], "default_template_id": a})
        res = c.put(url, json={"template_ids": [a, b], "default_template_id": b})
        assert res.status_code == 200, res.text
        assert _defaults(res.json()) == [b]
        assert db.query(ProductTagTemplate).filter_by(product_id=product, default_list=True, default_selling=True).count() == 1

    def test_a_default_that_is_not_among_the_ids_is_422_and_writes_nothing(self, env):
        from app.models.dealer_kit import ProductTagTemplate

        db, c, _ = env
        product = _product(db, _reference(db))
        a, b, outside = _template(db, "A"), _template(db, "B"), _template(db, "Out")
        url = f"{DK}/products/{product}/tag-templates"
        c.put(url, json={"template_ids": [a, b], "default_template_id": a})

        res = c.put(url, json={"template_ids": [a, b], "default_template_id": outside})
        assert res.status_code == 422, res.text
        assert {row["id"] for row in c.get(url).json()} == {a, b}
        assert _defaults(c.get(url).json()) == [a]
        assert db.query(ProductTagTemplate).filter_by(product_id=product).count() == 2

    def test_a_malformed_default_is_422(self, env):
        db, c, _ = env
        product = _product(db, _reference(db))
        a = _template(db, "A")
        res = c.put(
            f"{DK}/products/{product}/tag-templates",
            json={"template_ids": [a], "default_template_id": "not-a-uuid"},
        )
        assert res.status_code == 422, res.text

    def test_many_links_without_a_default_report_none(self, env):
        db, c, _ = env
        product = _product(db, _reference(db))
        a, b = _template(db, "A"), _template(db, "B")
        res = c.put(f"{DK}/products/{product}/tag-templates", json={"template_ids": [a, b]})
        assert res.status_code == 200, res.text
        assert all("is_default" in row for row in res.json())
        assert _defaults(res.json()) == []

    def test_a_single_link_reports_as_the_default(self, env):
        db, c, _ = env
        product = _product(db, _reference(db))
        a = _template(db, "A")
        res = c.put(f"{DK}/products/{product}/tag-templates", json={"template_ids": [a]})
        assert _defaults(res.json()) == [a]
        assert _defaults(c.get(f"{DK}/products/{product}/tag-templates").json()) == [a]

    def test_the_default_is_dropped_when_its_link_is_removed(self, env):
        db, c, _ = env
        product = _product(db, _reference(db))
        a, b, x = _template(db, "A"), _template(db, "B"), _template(db, "X")
        url = f"{DK}/products/{product}/tag-templates"
        c.put(url, json={"template_ids": [a, b, x], "default_template_id": a})
        res = c.put(url, json={"template_ids": [b, x]})
        assert res.status_code == 200, res.text
        assert _defaults(res.json()) == []

    def test_the_default_needs_the_manage_gate(self, env):
        db, c, as_ = env
        product = _product(db, _reference(db))
        a, b = _template(db, "A"), _template(db, "B")
        as_(VIEWER_ID)
        res = c.put(
            f"{DK}/products/{product}/tag-templates",
            json={"template_ids": [a, b], "default_template_id": a},
        )
        assert res.status_code == 403

    def test_service_signature_takes_default_template_id(self, env):
        from app.models.base import company_scope
        from app.services.dealer_kit import product_tag_template_service as svc

        db, _c, _ = env
        product = _product(db, _reference(db))
        a, b = _template(db, "A"), _template(db, "B")
        with company_scope(db, frozenset({SORENTO})):
            svc.set_product_templates(
                db, product, [a, b], user_id=MANAGER_ID, default_template_id=b
            )
            assert [t.id for t in svc.linked_templates(db, product)] == [a, b]


# --------------------------------------------------------------------------- AC-9
class TestLineUsesTheDefault:
    def test_no_pick_stores_the_default_and_submit_passes(self, env):
        db, c, _ = env
        product = _product(db, _reference(db))
        a, b = _template(db, "A"), _template(db, "B")
        _link_default(db, product, b, a)

        body = _draft(c, [{"line_type": "product", "product_id": product}])
        assert body["lines"][0]["tag_template_id"] == b
        assert c.post(f"{PTAG}/{body['id']}/submit").status_code == 200

    def test_an_allowed_pick_beats_the_default(self, env):
        db, c, _ = env
        product = _product(db, _reference(db))
        a, b = _template(db, "A"), _template(db, "B")
        _link_default(db, product, b, a)

        body = _draft(c, [{"line_type": "product", "product_id": product, "tag_template_id": a}])
        assert body["lines"][0]["tag_template_id"] == a

    def test_a_pick_outside_the_links_falls_to_the_default(self, env):
        db, c, _ = env
        product = _product(db, _reference(db))
        a, b, stranger = _template(db, "A"), _template(db, "B"), _template(db, "S")
        _link_default(db, product, b, a)

        body = _draft(
            c, [{"line_type": "product", "product_id": product, "tag_template_id": stranger}]
        )
        assert body["lines"][0]["tag_template_id"] == b

    def test_two_links_and_no_default_still_need_a_pick_at_submit(self, env):
        db, c, _ = env
        product = _product(db, _reference(db))
        a, b = _template(db, "A"), _template(db, "B")
        _link(db, product, a, b)

        body = _draft(c, [{"line_type": "product", "product_id": product}])
        assert body["lines"][0]["tag_template_id"] is None
        res = c.post(f"{PTAG}/{body['id']}/submit")
        assert res.status_code == 422, res.text
        assert res.json().get("code") == "TAG_TEMPLATE_REQUIRED"

    def test_replacing_the_lines_keeps_the_default_pick_rule(self, env):
        db, c, _ = env
        product = _product(db, _reference(db))
        a, b = _template(db, "A"), _template(db, "B")
        _link_default(db, product, b, a)
        body = _draft(c, [{"line_type": "product", "product_id": product, "tag_template_id": a}])

        res = c.put(
            f"{PTAG}/{body['id']}",
            json={"lines": [{"line_type": "product", "product_id": product}]},
        )
        assert res.status_code == 200, res.text
        assert res.json()["lines"][0]["tag_template_id"] == b

    def test_preview_with_no_pick_draws_the_default_not_the_first_link(self, env):
        db, c, _ = env
        product = _product(db, _reference(db))
        first, default = _template(db, "AAA"), _template(db, "BBB")
        _link_default(db, product, default, first)

        out = c.post(
            f"{PORTAL}/lookups/tag-preview",
            json={"lines": [{"key": "k", "line_type": "product", "product_id": product}]},
        ).json()
        assert out["templates"]["k"]["id"] == default

    def test_the_portal_lookup_carries_is_default(self, env):
        db, c, _ = env
        product = _product(db, _reference(db))
        a, b = _template(db, "A"), _template(db, "B")
        _link_default(db, product, a, b)

        res = c.get(f"{PORTAL}/lookups/product-tag-templates/{product}")
        assert res.status_code == 200, res.text
        assert _defaults(res.json()) == [a]


# --------------------------------------------------------------------------- AC-10
class TestComboLinks:
    def test_put_replaces_the_set_and_get_lists_it_with_the_default(self, env):
        from app.models.dealer_kit import ComboTagTemplate

        db, c, _ = env
        host = _product(db, _reference(db))
        combo = _combo(db, host)
        a, b, x = _template(db, "A"), _template(db, "B"), _template(db, "X", published=False)
        url = f"{DK}/combos/{combo.id}/tag-templates"

        res = c.put(url, json={"template_ids": [a, b, x], "default_template_id": b})
        assert res.status_code == 200, res.text
        assert {row["id"] for row in res.json()} == {a, b, x}
        assert _defaults(res.json()) == [b]
        assert {row["id"]: row["published"] for row in res.json()}[x] is False
        assert db.query(ComboTagTemplate).filter_by(combo_id=combo.id, default_list=True, default_selling=True).count() == 1

        listed = c.get(url)
        assert listed.status_code == 200
        assert _defaults(listed.json()) == [b]
        assert listed.json()[0]["width_mm"] == 80

        res = c.put(url, json={"template_ids": [a]})
        assert [row["id"] for row in res.json()] == [a]
        assert _defaults(res.json()) == [a], "a single link is the default"

    def test_a_default_outside_the_ids_is_422(self, env):
        db, c, _ = env
        combo = _combo(db, _product(db, _reference(db)))
        a, outside = _template(db, "A"), _template(db, "Out")
        res = c.put(
            f"{DK}/combos/{combo.id}/tag-templates",
            json={"template_ids": [a], "default_template_id": outside},
        )
        assert res.status_code == 422, res.text

    def test_viewer_can_read_but_not_write(self, env):
        db, c, as_ = env
        combo = _combo(db, _product(db, _reference(db)))
        a = _template(db, "A")
        as_(VIEWER_ID)
        assert c.get(f"{DK}/combos/{combo.id}/tag-templates").status_code == 200
        res = c.put(f"{DK}/combos/{combo.id}/tag-templates", json={"template_ids": [a]})
        assert res.status_code == 403

    def test_no_permission_at_all_is_refused(self, env):
        db, c, as_ = env
        combo = _combo(db, _product(db, _reference(db)))
        as_(str(uuid.uuid4()))
        assert c.get(f"{DK}/combos/{combo.id}/tag-templates").status_code in (401, 403)

    def test_unknown_template_or_combo_is_404_and_writes_nothing(self, env):
        from app.models.dealer_kit import ComboTagTemplate

        db, c, _ = env
        combo = _combo(db, _product(db, _reference(db)))
        a = _template(db, "A")

        res = c.put(
            f"{DK}/combos/{combo.id}/tag-templates",
            json={"template_ids": [a, str(uuid.uuid4())]},
        )
        assert res.status_code == 404
        assert db.query(ComboTagTemplate).filter_by(combo_id=combo.id).count() == 0
        assert c.put(
            f"{DK}/combos/{uuid.uuid4()}/tag-templates", json={"template_ids": [a]}
        ).status_code == 404
        assert c.get(f"{DK}/combos/{uuid.uuid4()}/tag-templates").status_code == 404
        assert c.get(f"{DK}/combos/not-a-uuid/tag-templates").status_code == 404

    def test_a_combo_whose_host_is_in_another_company_is_404(self, env):
        from app.models.dealer_kit import ComboTagTemplate

        db, c, _ = env
        _host, combo = _foreign_combo(db)
        a = _template(db, "A")
        assert c.get(f"{DK}/combos/{combo.id}/tag-templates").status_code == 404
        res = c.put(f"{DK}/combos/{combo.id}/tag-templates", json={"template_ids": [a]})
        assert res.status_code == 404
        assert db.query(ComboTagTemplate).filter_by(combo_id=combo.id).count() == 0

    def test_spec_sheet_family_cannot_be_linked(self, env):
        db, c, _ = env
        combo = _combo(db, _product(db, _reference(db)))
        spec = _template(db, "Spec", family="spec_page")
        res = c.put(f"{DK}/combos/{combo.id}/tag-templates", json={"template_ids": [spec]})
        assert res.status_code == 422, res.text

    def test_deleting_the_combo_removes_its_links(self, env):
        from app.models.dealer_kit import ComboTagTemplate
        from app.models.product_combo import ProductCombo

        db, c, _ = env
        combo = _combo(db, _product(db, _reference(db)))
        a = _template(db, "A")
        c.put(f"{DK}/combos/{combo.id}/tag-templates", json={"template_ids": [a]})
        assert db.query(ComboTagTemplate).filter_by(combo_id=combo.id).count() == 1
        db.query(ProductCombo).filter(ProductCombo.id == combo.id).delete(synchronize_session=False)
        db.flush()
        assert db.query(ComboTagTemplate).filter_by(combo_id=combo.id).count() == 0

    def test_service_functions(self, env):
        from app.models.base import company_scope
        from app.services.dealer_kit import product_tag_template_service as svc

        db, _c, _ = env
        combo = _combo(db, _product(db, _reference(db)))
        a, b = _template(db, "A"), _template(db, "B")
        with company_scope(db, frozenset({SORENTO})):
            rows = svc.set_combo_templates(
                db, combo.id, [a, b], user_id=MANAGER_ID, default_template_id=a
            )
            assert {t.id for t in rows} == {a, b}
            assert [t.id for t in svc.linked_combo_templates(db, combo.id)] == [a, b]


# --------------------------------------------------------------------------- AC-11
class TestComboLineTemplate:
    def _world(self, db, *, combo_default: bool = True):
        """Host linked to one template H; its combo linked to C1 and C2."""
        host = _product(db, _reference(db))
        h = _template(db, "H")
        c1, c2 = _template(db, "C1"), _template(db, "C2")
        _link(db, host, h)
        combo = _combo(db, host)
        _combo_link(db, combo.id, c1, c2, default=c2 if combo_default else None)
        return host, combo, h, c1, c2

    def test_save_uses_the_combos_default_template(self, env):
        db, c, _ = env
        host, combo, _h, _c1, c2 = self._world(db)
        body = _draft(
            c, [{"line_type": "product", "product_id": host, "combo_id": combo.id}]
        )
        assert body["lines"][0]["tag_template_id"] == c2

    def test_a_pick_among_the_combos_links_is_kept(self, env):
        db, c, _ = env
        host, combo, _h, c1, _c2 = self._world(db)
        body = _draft(
            c,
            [{"line_type": "product", "product_id": host, "combo_id": combo.id,
              "tag_template_id": c1}],
        )
        assert body["lines"][0]["tag_template_id"] == c1

    def test_the_hosts_own_template_is_not_allowed_on_a_combo_that_has_links(self, env):
        db, c, _ = env
        host, combo, h, _c1, c2 = self._world(db)
        body = _draft(
            c,
            [{"line_type": "product", "product_id": host, "combo_id": combo.id,
              "tag_template_id": h}],
        )
        assert body["lines"][0]["tag_template_id"] == c2

    def test_a_combo_without_links_falls_back_to_the_hosts_templates(self, env):
        db, c, _ = env
        host = _product(db, _reference(db))
        h = _template(db, "H")
        _link(db, host, h)
        bare = _combo(db, host)
        body = _draft(c, [{"line_type": "product", "product_id": host, "combo_id": bare.id}])
        assert body["lines"][0]["tag_template_id"] == h

    def test_the_same_host_without_a_combo_still_uses_its_own_template(self, env):
        db, c, _ = env
        host, _combo_row, h, _c1, _c2 = self._world(db)
        body = _draft(c, [{"line_type": "product", "product_id": host}])
        assert body["lines"][0]["tag_template_id"] == h

    def test_two_combo_links_and_no_default_still_need_a_pick_at_submit(self, env):
        db, c, _ = env
        host, combo, _h, c1, _c2 = self._world(db, combo_default=False)
        body = _draft(c, [{"line_type": "product", "product_id": host, "combo_id": combo.id}])
        assert body["lines"][0]["tag_template_id"] is None
        res = c.post(f"{PTAG}/{body['id']}/submit")
        assert res.status_code == 422, res.text
        assert res.json().get("code") == "TAG_TEMPLATE_REQUIRED"

        res = c.put(
            f"{PTAG}/{body['id']}",
            json={"lines": [{"line_type": "product", "product_id": host,
                             "combo_id": combo.id, "tag_template_id": c1}]},
        )
        assert res.status_code == 200, res.text
        assert c.post(f"{PTAG}/{body['id']}/submit").status_code == 200

    def test_a_combo_line_with_a_default_submits_without_a_pick(self, env):
        db, c, _ = env
        host, combo, *_ = self._world(db)
        body = _draft(c, [{"line_type": "product", "product_id": host, "combo_id": combo.id}])
        assert c.post(f"{PTAG}/{body['id']}/submit").status_code == 200

    def test_preview_of_an_unsaved_combo_line_draws_the_combos_template(self, env):
        db, c, _ = env
        host, combo, h, _c1, c2 = self._world(db)
        bare = _combo(db, host, "ZZT bare")
        out = c.post(
            f"{PORTAL}/lookups/tag-preview",
            json={"lines": [
                {"key": "with", "line_type": "product", "product_id": host, "combo_id": combo.id},
                {"key": "bare", "line_type": "product", "product_id": host, "combo_id": bare.id},
                {"key": "none", "line_type": "product", "product_id": host},
            ]},
        )
        assert out.status_code == 200, out.text
        templates = out.json()["templates"]
        assert templates["with"]["id"] == c2
        assert templates["bare"]["id"] == h
        assert templates["none"]["id"] == h

    def test_preview_of_a_saved_request_draws_the_combos_template(self, env):
        from app.models.price_tag import PriceTagRequestLine

        db, c, _ = env
        host, combo, _h, _c1, c2 = self._world(db)
        body = _draft(c, [{"line_type": "product", "product_id": host, "combo_id": combo.id}])
        line = db.query(PriceTagRequestLine).filter_by(request_id=body["id"]).one()
        out = c.post(f"{PORTAL}/lookups/tag-preview", json={"request_id": body["id"]}).json()
        assert out["templates"][line.id]["id"] == c2

    def test_the_portal_lookup_answers_the_combos_links(self, env):
        db, c, _ = env
        host, combo, h, c1, c2 = self._world(db)
        _unpublished = _template(db, "Draft", published=False)
        _combo_link(db, combo.id, _unpublished)

        res = c.get(f"{PORTAL}/lookups/product-tag-templates/{host}?combo_id={combo.id}")
        assert res.status_code == 200, res.text
        assert {row["id"] for row in res.json()} == {c1, c2}
        assert _defaults(res.json()) == [c2]

        plain = c.get(f"{PORTAL}/lookups/product-tag-templates/{host}")
        assert [row["id"] for row in plain.json()] == [h]

    def test_the_lookup_falls_back_to_the_product_for_a_combo_without_links(self, env):
        db, c, _ = env
        host = _product(db, _reference(db))
        h = _template(db, "H")
        _link(db, host, h)
        bare = _combo(db, host)
        res = c.get(f"{PORTAL}/lookups/product-tag-templates/{host}?combo_id={bare.id}")
        assert [row["id"] for row in res.json()] == [h]

    def test_a_combo_of_another_product_does_not_change_the_answer(self, env):
        db, c, _ = env
        host, _combo_row, h, _c1, _c2 = self._world(db)
        other = _product(db, _reference(db))
        other_combo = _combo(db, other, "ZZT other")
        _combo_link(db, other_combo.id, _template(db, "O1"), _template(db, "O2"))
        res = c.get(f"{PORTAL}/lookups/product-tag-templates/{host}?combo_id={other_combo.id}")
        assert [row["id"] for row in res.json()] == [h]

    def test_a_foreign_companys_combo_is_not_answered(self, env):
        db, c, _ = env
        foreign_host, foreign_combo = _foreign_combo(db)
        mine = _product(db, _reference(db))
        h = _template(db, "H")
        _link(db, mine, h)
        _combo_link(db, foreign_combo.id, _template(db, "F1"))
        res = c.get(f"{PORTAL}/lookups/product-tag-templates/{mine}?combo_id={foreign_combo.id}")
        assert [row["id"] for row in res.json()] == [h]
        assert foreign_host


# --------------------------------------------------------------------------- deferred unlink
class TestDeferredComboUnlink:
    """`combo.unlink_tag_templates`: unticking a template on an existing combo parks, like the
    product's `product.unlink_tag_templates`."""

    def test_the_action_is_registered_and_removes_only_the_named_links(self, env):
        from app.models.base import set_company_scope
        from app.models.dealer_kit import ComboTagTemplate
        import app.services.record_actions  # noqa: F401  (registers the actions)
        from app.services.form_action_registry import get_action

        db, _c, _ = env
        combo = _combo(db, _product(db, _reference(db)))
        a, b = _template(db, "A"), _template(db, "B")
        _combo_link(db, combo.id, a, b, default=b)

        action = get_action("combo.unlink_tag_templates")
        assert action is not None, "record_actions did not register the key"
        assert action.permission == "dealer_kit.tag_templates.manage"
        set_company_scope(db, frozenset({SORENTO}))
        result = action.execute(db, {"entity_id": combo.id, "template_ids": [a]})
        assert result == {"changed": 1}, result
        assert {r.template_id for r in db.query(ComboTagTemplate).filter_by(combo_id=combo.id)} == {b}

    def test_a_combo_of_another_company_is_404_and_untouched(self, env):
        from app.models.base import set_company_scope
        from app.models.dealer_kit import ComboTagTemplate
        from app.services.dealer_kit import product_tag_template_service as svc
        from app.services.error_handler import AppException

        db, _c, _ = env
        _host, combo = _foreign_combo(db)
        a = _template(db, "A")
        _combo_link(db, combo.id, a)
        set_company_scope(db, frozenset({SORENTO}))
        with pytest.raises(AppException) as exc:
            svc.unlink_combo_templates(db, combo.id, [a])
        assert exc.value.status_code == 404
        assert db.query(ComboTagTemplate).filter_by(combo_id=combo.id).count() == 1

    def test_the_park_check_refuses_a_foreign_combo(self, env):
        from app.api.v1.system.pending_actions import _assert_entity_visible
        from app.models.base import company_scope
        from app.services.error_handler import AppException

        db, _c, _ = env
        _host, combo = _foreign_combo(db)
        with company_scope(db, frozenset({SORENTO})):
            with pytest.raises(AppException) as exc:
                _assert_entity_visible(db, "combo.unlink_tag_templates", combo.id, MANAGER_ID)
        assert exc.value.status_code == 404


class TestDefaultSurvivesOneToTwo:
    """Crew pass on bb5954ce: unlink a combo down to one template (countdown completed), add a
    second one back, and the saved default was gone (both is_default false). A 1 -> 2 link change
    must never drop the default: the lone remaining link becomes the default on unlink, and a
    lone link stays the default when another is added. Clearing the default on purpose, with 2+
    links, still works."""

    @staticmethod
    def _combo_defaults(db, combo_id):
        from app.models.dealer_kit import ComboTagTemplate

        return {
            r.template_id
            for r in db.query(ComboTagTemplate).filter_by(combo_id=combo_id, default_list=True, default_selling=True)
        }

    @staticmethod
    def _product_defaults(db, product_id):
        from app.models.dealer_kit import ProductTagTemplate

        return {
            r.template_id
            for r in db.query(ProductTagTemplate).filter_by(product_id=product_id, default_list=True, default_selling=True)
        }

    def test_combo_unlink_to_one_then_add_a_second_keeps_a_default(self, env):
        from app.models.base import set_company_scope
        from app.services.dealer_kit import product_tag_template_service as svc

        db, _c, _ = env
        combo = _combo(db, _product(db, _reference(db)))
        a, b, c = _template(db, "A"), _template(db, "B"), _template(db, "C")
        _combo_link(db, combo.id, a, b, default=a)
        set_company_scope(db, frozenset({SORENTO}))

        svc.unlink_combo_templates(db, combo.id, [a])
        assert self._combo_defaults(db, combo.id) == {b}

        # The form sends no default when it showed a single link (the crew repro).
        svc.set_combo_templates(db, combo.id, [b, c], user_id=None, default_template_id=None)
        assert self._combo_defaults(db, combo.id) == {b}

    def test_combo_unlinking_the_non_default_keeps_the_default(self, env):
        from app.models.base import set_company_scope
        from app.services.dealer_kit import product_tag_template_service as svc

        db, _c, _ = env
        combo = _combo(db, _product(db, _reference(db)))
        a, b, c = _template(db, "A"), _template(db, "B"), _template(db, "C")
        _combo_link(db, combo.id, a, b, default=a)
        set_company_scope(db, frozenset({SORENTO}))

        svc.unlink_combo_templates(db, combo.id, [b])
        svc.set_combo_templates(db, combo.id, [a, c], user_id=None, default_template_id=None)
        assert self._combo_defaults(db, combo.id) == {a}

    def test_product_lone_link_without_a_stored_default_becomes_it_when_a_second_is_added(self, env):
        from app.models.base import set_company_scope
        from app.services.dealer_kit import product_tag_template_service as svc

        db, _c, _ = env
        product = _product(db, _reference(db))
        a, b = _template(db, "A"), _template(db, "B")
        _link(db, product, a)  # a link saved before defaults existed: is_default false
        set_company_scope(db, frozenset({SORENTO}))

        svc.set_product_templates(db, product, [a, b], user_id=None, default_template_id=None)
        assert self._product_defaults(db, product) == {a}

    def test_product_unlink_to_one_makes_the_remaining_link_the_default(self, env):
        from app.models.base import set_company_scope
        from app.services.dealer_kit import product_tag_template_service as svc

        db, _c, _ = env
        product = _product(db, _reference(db))
        a, b = _template(db, "A"), _template(db, "B")
        _link_default(db, product, a, b)
        set_company_scope(db, frozenset({SORENTO}))

        svc.unlink_product_templates(db, product, [a])
        assert self._product_defaults(db, product) == {b}

    def test_bulk_add_to_a_product_with_one_link_keeps_that_link_the_default(self, env):
        from app.models.base import set_company_scope
        from app.services.dealer_kit import product_tag_template_service as svc

        db, _c, _ = env
        ref = _reference(db)
        product = _product(db, ref, family_code=unique_code("FAM"))
        a, b = _template(db, "A"), _template(db, "B")
        _link(db, product, a)  # legacy lone link, is_default false
        set_company_scope(db, frozenset({SORENTO}))
        from app.models.product import Product

        family = db.get(Product, product).family_code
        svc.bulk_assign(db, b, {"family_codes": [family]}, "add", user_id=None)
        assert self._product_defaults(db, product) == {a}

    def test_clearing_the_default_with_two_links_still_clears_it(self, env):
        from app.models.base import set_company_scope
        from app.services.dealer_kit import product_tag_template_service as svc

        db, _c, _ = env
        product = _product(db, _reference(db))
        a, b = _template(db, "A"), _template(db, "B")
        _link_default(db, product, a, b)
        set_company_scope(db, frozenset({SORENTO}))

        svc.set_product_templates(db, product, [a, b], user_id=None, default_template_id=None)
        assert self._product_defaults(db, product) == set()
