"""PRICETAG-COMBO-FORMAT fix round 1 (backend rulings R1, R5, R8, R12).

Contract: pricetag-combo-format-contract.md, section "Fix round 1". Written test-FIRST, tests only.
R2 / R3 / R4 live beside the sanitiser and the description API tests.

Harness reused from `tests/test_product_tag_templates.py` (`env`) and the earlier suites of this lane.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.test_price_tag_line_template_price_type import (  # noqa: F401  (_quiet is autouse)
    PTAG,
    _line,
    _quiet,
    _set_type,
    _submit,
    _typed,
)
from tests.test_price_tag_lpsp_templates import _combo  # noqa: F401
from tests.test_product_tag_templates import (  # noqa: F401  (env is a fixture)
    DK,
    _draft,
    _link,
    _product,
    _reference,
    _template,
    env,
)


def _ids(items, flag):
    return [row["id"] for row in items if row[flag]]


# --------------------------------------------------------------------------- R1
def test_r1_a_saved_flag_counts_only_while_the_template_fits(env):
    """R1: A is the legacy default (both flags). Setting A to LP-only: GET reports default_list
    only, and a later PUT adding a link with no defaults sent is 200 (no stale SP flag)."""
    db, c, _ = env
    product = _product(db, _reference(db))
    a, b = _template(db, "A"), _template(db, "B")
    url = f"{DK}/products/{product}/tag-templates"

    res = c.put(url, json={"template_ids": [a, b], "default_template_id": a})
    assert res.status_code == 200, res.text
    assert _ids(res.json(), "default_list") == [a] and _ids(res.json(), "default_selling") == [a]

    assert c.put(f"{DK}/tag-templates/{a}", json={"price_type": "list"}).status_code == 200

    items = c.get(url).json()
    by_id = {row["id"]: row for row in items}
    assert by_id[a]["default_list"] is True
    assert by_id[a]["default_selling"] is False

    assert by_id[a]["price_type"] == "list"


def test_r1_adding_a_link_after_a_type_change_is_200_with_no_defaults_sent(env):
    """R1: the stale SP flag on A (now LP-only) must not make the next link edit a 422."""
    db, c, _ = env
    product = _product(db, _reference(db))
    a, b, extra = _template(db, "A"), _template(db, "B"), _template(db, "C")
    url = f"{DK}/products/{product}/tag-templates"
    assert c.put(url, json={"template_ids": [a, b], "default_template_id": a}).status_code == 200
    assert c.put(f"{DK}/tag-templates/{a}", json={"price_type": "list"}).status_code == 200

    res = c.put(url, json={"template_ids": [a, b, extra]})
    assert res.status_code == 200, res.text
    assert _ids(res.json(), "default_selling") != [a]


def test_r1_a_template_price_type_change_clears_flags_it_no_longer_fits_in_the_db(env):
    """R1: the template PUT clears non-fitting flags on EVERY link (product and combo)."""
    from app.models.dealer_kit import ComboTagTemplate, ProductTagTemplate

    db, c, _ = env
    product = _product(db, _reference(db))
    combo = _combo(db, _product(db, _reference(db)), "ZZT r1 combo")
    a, b = _template(db, "A"), _template(db, "B")
    for url in (f"{DK}/products/{product}/tag-templates", f"{DK}/combos/{combo.id}/tag-templates"):
        res = c.put(url, json={"template_ids": [a, b], "default_template_id": a})
        assert res.status_code == 200, res.text

    assert c.put(f"{DK}/tag-templates/{a}", json={"price_type": "selling"}).status_code == 200

    db.expire_all()
    for model, owner in ((ProductTagTemplate, {"product_id": product}), (ComboTagTemplate, {"combo_id": combo.id})):
        row = db.query(model).filter_by(template_id=a, **owner).one()
        assert row.default_selling is True
        assert row.default_list is False, f"{model.__name__}: the LP flag must go when A becomes SP"

    assert c.put(f"{DK}/tag-templates/{a}", json={"price_type": None}).status_code == 200
    db.expire_all()
    row = db.query(ProductTagTemplate).filter_by(template_id=a, product_id=product).one()
    assert (row.default_list, row.default_selling) == (False, True), "an unset type clears nothing"


# --------------------------------------------------------------------------- R5
def test_r5_a_kept_pick_passes_submit_even_when_it_no_longer_fits(env):
    """R5: SP line kept on T (unchanged pick); T later set to LP; nothing SP linked -> 200."""
    db, c, _ = env
    product = _product(db, _reference(db))
    t = _typed(db, "T", "both")
    _link(db, product, t)
    body = _draft(c, [_line(product, "selling", tag_template_id=t)])
    assert body["lines"][0]["tag_template_id"] == t

    _set_type(db, t, "list")

    res = _submit(c, body["id"])
    assert res.status_code == 200, res.text


def test_r5_a_line_without_a_kept_pick_is_still_refused(env):
    """R5: NO_TEMPLATE_FOR_PRICE_TYPE still applies to a line with no kept pick."""
    db, c, _ = env
    product = _product(db, _reference(db))
    _link(db, product, _typed(db, "LPONLY", "list"))
    body = _draft(c, [_line(product, "selling")])
    res = _submit(c, body["id"])
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "NO_TEMPLATE_FOR_PRICE_TYPE"


def test_r5_the_approve_path_shares_the_gate(env):
    """R5: submit-approve runs the same `require_line_templates` before it approves."""
    from tests.test_price_tag_self_approval import _placed_tag_ids, _sheet

    db, c, _ = env
    product = _product(db, _reference(db))
    t = _typed(db, "T", "both")
    _link(db, product, t)
    body = _draft(c, [_line(product, "selling", tag_template_id=t)])
    _set_type(db, t, "list")

    res = c.post(
        f"{PTAG}/{body['id']}/submit-approve", json={"doc": _sheet(_placed_tag_ids(db, body["id"]))}
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"


# --------------------------------------------------------------------------- R8 (backend part)
def test_r8_the_product_data_changed_review_shows_plain_text():
    """R8: `diff_pin_against_live` values for the price tag description, the combo description and
    a part's description are plain text (no markup). The tag payload itself stays rich."""
    from app.services.dealer_kit.tag_data_service import diff_pin_against_live

    pinned = {
        "price_tag_description": "<p><strong>SRTBF11416</strong> (CABINET)</p><p>L400</p>",
        "combo": {"name": "3 in 1", "description": "<ul><li>a</li><li>b</li></ul>"},
        "parts": [{"product_id": "p1", "code": "SRTWB248", "price_tag_description": "<p><em>old</em> &amp; co</p>"}],
    }
    live = {
        "price_tag_description": "<p><strong>SRTBF11416</strong> (CABINET)</p><p>L450</p>",
        "combo": {"name": "3 in 1", "description": "<ol><li>a</li><li>c</li></ol>"},
        "parts": [{"product_id": "p1", "code": "SRTWB248", "price_tag_description": "<p><em>new</em></p>"}],
    }
    changes = {c["field"]: c for c in diff_pin_against_live(None, None, pinned, live, None, promotion_live=False)}

    host = changes["price_tag_description"]
    assert (host["old"], host["new"]) == ("SRTBF11416 (CABINET)\nL400", "SRTBF11416 (CABINET)\nL450")
    combo = changes["combo:description"]
    assert (combo["old"], combo["new"]) == ("• a\n• b", "1. a\n2. c")
    part = changes["part:SRTWB248:price_tag_description"]
    assert (part["old"], part["new"]) == ("old & co", "new")
    for entry in changes.values():
        for side in ("old", "new"):
            assert "<" not in str(entry.get(side) or ""), entry


def test_r8_a_formatting_only_change_is_not_reported():
    """R8: two descriptions that differ only in markup read the same to a person."""
    from app.services.dealer_kit.tag_data_service import diff_pin_against_live

    pinned = {"price_tag_description": "<p><strong>A</strong> b</p>"}
    live = {"price_tag_description": "<p>A b</p>"}
    changes = diff_pin_against_live(None, None, pinned, live, None, promotion_live=False)
    assert [c for c in changes if c["field"] == "price_tag_description"] == []


# --------------------------------------------------------------------------- R12
def test_r12_the_legacy_default_sets_only_the_types_it_fits(env):
    """R12: `default_template_id` naming an LP-only template -> 200 (no 422); only default_list
    is stored, whatever the SP need of the other link."""
    from app.models.dealer_kit import ProductTagTemplate

    db, c, _ = env
    product = _product(db, _reference(db))
    lp, sp = _typed(db, "LPONLY", "list"), _typed(db, "SPONLY", "selling")
    url = f"{DK}/products/{product}/tag-templates"

    res = c.put(url, json={"template_ids": [lp, sp], "default_template_id": lp})
    assert res.status_code == 200, res.text

    db.expire_all()
    rows = {r.template_id: r for r in db.query(ProductTagTemplate).filter_by(product_id=product).all()}
    assert (rows[lp].default_list, rows[lp].default_selling) == (True, False)
    assert (rows[sp].default_list, rows[sp].default_selling) == (False, False)
    assert _ids(res.json(), "default_list") == [lp]


def test_r12_the_legacy_default_on_an_sp_only_template_sets_default_selling_only(env):
    db, c, _ = env
    combo = _combo(db, _product(db, _reference(db)), "ZZT r12 combo")
    lp, sp = _typed(db, "LPONLY", "list"), _typed(db, "SPONLY", "selling")
    res = c.put(f"{DK}/combos/{combo.id}/tag-templates", json={"template_ids": [lp, sp], "default_template_id": sp})
    assert res.status_code == 200, res.text
    assert _ids(res.json(), "default_selling") == [sp]


# --------------------------------------------------------------------------- R1 read-side guard
def test_r1_the_read_side_ignores_a_stale_flag_even_without_the_put_clearing_it(env):
    """R1 guard for `_defaults_for`: the type is changed with RAW SQL, so the link keeps
    default_selling = true. GET must still report it false, and an SP line with no pick must not
    pick the template."""
    from app.models.dealer_kit import ProductTagTemplate

    db, c, _ = env
    product = _product(db, _reference(db))
    a, b = _template(db, "A"), _template(db, "B")
    url = f"{DK}/products/{product}/tag-templates"
    assert c.put(url, json={"template_ids": [a, b], "default_template_id": a}).status_code == 200
    _set_type(db, b, "selling")
    _set_type(db, a, "list")  # raw: nothing clears the flags

    db.expire_all()
    assert db.query(ProductTagTemplate).filter_by(product_id=product, template_id=a).one().default_selling is True

    items = {row["id"]: row for row in c.get(url).json()}
    assert items[a]["default_list"] is True
    assert items[a]["default_selling"] is False, "a stale flag is not reported"

    body = _draft(c, [_line(product, "selling")])
    assert body["lines"][0]["tag_template_id"] == b, "the LP-only template is not picked for an SP line"
