"""PRICETAG-COMBO-FORMAT S7: a request line is offered only the templates that fit its LP / SP.

UAC: documentation/plans/dealer-kit/pricetag-combo-format-acceptance-criteria.md, AC-33 to AC-39.
Contract: pricetag-combo-format-contract.md "Request lines".

Written test-FIRST (PRINCIPLES.md Phase 2). `tag_template.price_type`, the link flags
(`default_list` / `default_selling`), the `price_type` lookup filter and the two new error codes
do not exist yet. Tests that only assert behaviour that must NOT change (AC-39 with every
template unset) are expected to pass already; they are the release-day compatibility net.

Harness reused from `tests/test_product_tag_templates.py` (staff manager + portal contact on a
Postgres scratch schema). Every product, combo, template and link is seeded here.

What "offered" means here: the portal lookup answer
(`GET /lookups/product-tag-templates/{product}?combo_id=&price_type=`), and what a SAVED line
stores in `tag_template_id`. The contract keeps `line_links` unfiltered and filters in
`line_template_id` / `published_items`, so the lookup is the observable surface.

KILL: remove the price-type filter in the lookup/line pick -> test 1 and test 2 go red;
make NULL count as `list` only -> the AC-39 tests go red.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.models.price_tag import PriceTagRequestLine
from tests._pg_fixture import unique_code
from tests.test_price_tag_lpsp_templates import _combo  # noqa: F401
from tests.test_product_tag_templates import (  # noqa: F401  (env is a fixture)
    PORTAL,
    PTAG,
    _draft,
    _link,
    _product,
    _reference,
    _template,
    env,
)

LOOKUP = f"{PORTAL}/lookups/product-tag-templates"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    """Submit rings the salesperson on Respond.io; nothing here is about that."""
    from tests import _ptag_r9_seed as r9

    r9.block_respond(monkeypatch)


# --------------------------------------------------------------------------- seeds
def _typed(db, name, price_type):
    """Raw SQL on purpose: a missing column must fail loudly, not vanish on an ORM attribute."""
    template_id = _template(db, name)
    if price_type is not None:
        db.execute(
            text("UPDATE tag_template SET price_type = :p WHERE id = :i"),
            {"p": price_type, "i": template_id},
        )
        db.flush()
    return template_id


def _set_type(db, template_id, price_type):
    db.execute(
        text("UPDATE tag_template SET price_type = :p WHERE id = :i"),
        {"p": price_type, "i": template_id},
    )
    db.flush()


def _link_with(db, product_id, template_id, *, list_=False, selling=False):
    from app.models.dealer_kit import ProductTagTemplate

    flags = {"default_list": True} if list_ else {}
    flags.update({"default_selling": True} if selling else {})
    db.add(ProductTagTemplate(product_id=product_id, template_id=template_id, **flags))
    db.flush()


def _combo_link(db, combo_id, template_id, *, list_=False, selling=False):
    from app.models.dealer_kit import ComboTagTemplate

    flags = {"default_list": True} if list_ else {}
    flags.update({"default_selling": True} if selling else {})
    db.add(ComboTagTemplate(combo_id=combo_id, template_id=template_id, **flags))
    db.flush()


def _offered(c, product, combo=None, price_type=None) -> set[str]:
    params = {}
    if combo is not None:
        params["combo_id"] = combo.id
    if price_type is not None:
        params["price_type"] = price_type
    res = c.get(f"{LOOKUP}/{product}", params=params)
    assert res.status_code == 200, res.text
    return {row["id"] for row in res.json()}


def _line(product, price_type, combo=None, **extra):
    row = {"line_type": "product", "product_id": product, "price_type": price_type, **extra}
    if combo is not None:
        row["combo_id"] = combo.id
    return row


def _stored(c, product, price_type, combo=None, **extra):
    return _draft(c, [_line(product, price_type, combo, **extra)])["lines"][0]["tag_template_id"]


# --------------------------------------------------------------------------- AC-33
def test_the_lookup_offers_only_templates_that_fit_the_lines_type(env):
    """AC-33: LP -> {list, both, unset}; SP -> {selling, both, unset}; no type = unfiltered."""
    db, c, _ = env
    product = _product(db, _reference(db))
    lp, sp, both, unset = (_typed(db, n, t) for n, t in
                           (("LP", "list"), ("SP", "selling"), ("BOTH", "both"), ("UNSET", None)))
    _link(db, product, lp, sp, both, unset)

    assert _offered(c, product, price_type="list") == {lp, both, unset}
    assert _offered(c, product, price_type="selling") == {sp, both, unset}
    assert _offered(c, product) == {lp, sp, both, unset}, "absent price_type = unfiltered (compat)"


def test_the_combo_lookup_filters_the_combos_own_links_the_same_way(env):
    db, c, _ = env
    host = _product(db, _reference(db))
    host_template = _typed(db, "HOST", "both")
    _link(db, host, host_template)
    combo = _combo(db, host, "ZZT filter combo")
    lp, sp, both, unset = (_typed(db, n, t) for n, t in
                           (("CLP", "list"), ("CSP", "selling"), ("CBOTH", "both"), ("CUNSET", None)))
    for template_id in (lp, sp, both, unset):
        _combo_link(db, combo.id, template_id)

    assert _offered(c, host, combo, "list") == {lp, both, unset}
    assert _offered(c, host, combo, "selling") == {sp, both, unset}
    assert _offered(c, host, combo) == {lp, sp, both, unset}


def test_an_unknown_price_type_filter_is_refused(env):
    db, c, _ = env
    product = _product(db, _reference(db))
    _link(db, product, _typed(db, "A", "both"))
    assert c.get(f"{LOOKUP}/{product}", params={"price_type": "bogus"}).status_code == 422


# --------------------------------------------------------------------------- AC-34
def test_an_sp_line_with_no_pick_stores_the_sp_default(env):
    db, c, _ = env
    product = _product(db, _reference(db))
    lp, sp, other_sp = _typed(db, "LP", "list"), _typed(db, "SP", "selling"), _typed(db, "SP2", "selling")
    _link_with(db, product, lp, list_=True)
    _link_with(db, product, sp, selling=True)
    _link_with(db, product, other_sp)

    assert _stored(c, product, "selling") == sp
    assert _stored(c, product, "list") == lp


def test_with_no_default_the_lone_fitting_link_is_stored(env):
    """Pick order: sent pick -> that type's default -> the lone link that FITS."""
    db, c, _ = env
    product = _product(db, _reference(db))
    lp, sp = _typed(db, "LP", "list"), _typed(db, "SP", "selling")
    _link(db, product, lp, sp)

    assert _stored(c, product, "selling") == sp
    assert _stored(c, product, "list") == lp


def test_a_sent_pick_that_does_not_fit_is_422_and_one_that_fits_is_kept(env):
    db, c, _ = env
    product = _product(db, _reference(db))
    lp, sp, both = _typed(db, "LP", "list"), _typed(db, "SP", "selling"), _typed(db, "BOTH", "both")
    _link_with(db, product, sp, selling=True)
    _link(db, product, lp, both)

    res = c.post(
        PTAG,
        json={"debtor_name": "ZZT Dealer", "debtor_code": "ZZT-D", "print_by": "office",
              "lines": [_line(product, "selling", tag_template_id=lp)]},
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "TEMPLATE_PRICE_TYPE_MISMATCH"

    assert _stored(c, product, "selling", tag_template_id=both) == both
    assert _stored(c, product, "list", tag_template_id=lp) == lp


def test_a_combo_sp_line_uses_the_combos_sp_default(env):
    db, c, _ = env
    host = _product(db, _reference(db))
    combo = _combo(db, host, "ZZT default combo")
    lp, sp = _typed(db, "CLP", "list"), _typed(db, "CSP", "selling")
    _combo_link(db, combo.id, lp, list_=True)
    _combo_link(db, combo.id, sp, selling=True)

    assert _stored(c, host, "selling", combo) == sp
    assert _stored(c, host, "list", combo) == lp


# --------------------------------------------------------------------------- AC-36
def _submit(c, body_id):
    return c.post(f"{PTAG}/{body_id}/submit")


@pytest.mark.parametrize("line_type, only_linked, label", [("selling", "list", "SP"), ("list", "selling", "LP")])
def test_submit_refuses_a_combo_line_with_no_template_for_its_type(env, line_type, only_linked, label):
    db, c, _ = env
    host = _product(db, _reference(db))
    combo = _combo(db, host, "ZZT lonely combo")
    _combo_link(db, combo.id, _typed(db, "ONLY", only_linked))

    body = _draft(c, [_line(host, line_type, combo)])
    res = _submit(c, body["id"])
    assert res.status_code == 422, res.text
    payload = res.json()
    assert payload["code"] == "NO_TEMPLATE_FOR_PRICE_TYPE"
    assert payload["detail"] == "line:0"
    assert payload["message"] == f"{combo.name}: No {label} template linked"


def test_submit_names_the_product_code_and_the_offending_line(env):
    db, c, _ = env
    ref = _reference(db)
    good = _product(db, ref)
    code = unique_code("SRTBF11416")
    bad = _product(db, ref, code=code)
    both = _typed(db, "BOTH", "both")
    _link(db, good, both)
    _link(db, bad, _typed(db, "LPONLY", "list"))

    body = _draft(c, [_line(good, "selling"), _line(bad, "selling")])
    res = _submit(c, body["id"])
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "NO_TEMPLATE_FOR_PRICE_TYPE"
    assert res.json()["detail"] == "line:1"
    assert res.json()["message"] == f"{code}: No SP template linked"


def test_an_item_with_no_links_at_all_keeps_todays_behaviour(env):
    """Unchanged: no link = the family rule applies later; submit does not refuse it."""
    db, c, _ = env
    product = _product(db, _reference(db))
    body = _draft(c, [_line(product, "selling")])
    res = _submit(c, body["id"])
    assert res.status_code == 200, res.text


def test_a_line_that_has_a_fitting_template_submits(env):
    db, c, _ = env
    product = _product(db, _reference(db))
    _link(db, product, _typed(db, "LP", "list"), _typed(db, "SP", "selling"))
    body = _draft(c, [_line(product, "selling"), _line(product, "list")])
    assert _submit(c, body["id"]).status_code == 200


# --------------------------------------------------------------------------- AC-37
def _line_row(db, request_id):
    db.expire_all()
    return db.query(PriceTagRequestLine).filter_by(request_id=request_id).one()


def _previewed_template(c, request_id, line_id):
    res = c.post(f"{PORTAL}/lookups/tag-preview", json={"request_id": request_id})
    assert res.status_code == 200, res.text
    return res.json()["templates"].get(line_id, {}).get("id")


def test_a_saved_line_is_not_rewritten_when_its_template_type_changes(env):
    """AC-37: the stored pick keeps printing; only an edit of that line re-filters."""
    db, c, _ = env
    product = _product(db, _reference(db))
    t, u = _typed(db, "T", "list"), _typed(db, "U", "selling")
    _link(db, product, t)
    _link_with(db, product, u, selling=True)
    body = _draft(c, [_line(product, "list")])
    assert body["lines"][0]["tag_template_id"] == t
    line_id = _line_row(db, body["id"]).id

    _set_type(db, t, "selling")  # the owner sets T to SP afterwards

    assert _line_row(db, body["id"]).tag_template_id == t, "not rewritten"
    assert _previewed_template(c, body["id"], line_id) == t, "still prints with T"

    # editing the line's price type re-filters: no pick -> the SP default
    res = c.put(f"{PTAG}/{body['id']}", json={"lines": [_line(product, "selling")]})
    assert res.status_code == 200, res.text
    assert res.json()["lines"][0]["tag_template_id"] == u


def test_an_approved_tag_keeps_its_template_and_pinned_data_after_the_type_change(env):
    """AC-37: submit pins the tag's data; approval freezes the request; a later type change on
    the template moves neither the stored template nor the pin."""
    from app.models.base import company_scope
    from app.services.price_tag_request_service import STATUS_APPROVED, PriceTagRequestService
    from tests.test_product_tag_templates import SORENTO

    db, c, _ = env
    product = _product(db, _reference(db))
    t = _typed(db, "T", "list")
    _link(db, product, t)
    body = _draft(c, [_line(product, "list")])
    assert body["lines"][0]["tag_template_id"] == t
    assert _submit(c, body["id"]).status_code == 200

    def pins():
        db.expire_all()
        with company_scope(db, frozenset({SORENTO})):
            request = PriceTagRequestService.get_request(db, body["id"])
            return {tag.id: tag.pinned_tag_data for line in request.lines for tag in line.tags}

    with company_scope(db, frozenset({SORENTO})):
        request = PriceTagRequestService.get_request(db, body["id"])
        request.status = STATUS_APPROVED
        db.flush()
    before = pins()
    assert before and all(before.values()), "submit pins the tag's data"
    line_id = _line_row(db, body["id"]).id

    _set_type(db, t, "selling")

    assert pins() == before
    assert _line_row(db, body["id"]).tag_template_id == t
    assert _previewed_template(c, body["id"], line_id) == t


# --------------------------------------------------------------------------- AC-38
def test_a_no_selling_price_brand_sp_line_is_offered_sp_templates(env):
    """AC-38: Cabana (no promo selling price) with a typed SP is offered SP templates."""
    db, c, _ = env
    ref = _reference(db)
    ref[1].no_promo_selling_price = True  # the brand
    db.flush()
    product = _product(db, ref)
    lp, sp = _typed(db, "LP", "list"), _typed(db, "SP", "selling")
    _link(db, product, lp, sp)

    assert _offered(c, product, price_type="selling") == {sp}
    assert _stored(c, product, "selling", manual_sell_price="399.00") == sp


# --------------------------------------------------------------------------- AC-39
@pytest.mark.parametrize("price_type", [None, "list", "selling"])
def test_release_day_a_product_with_one_unset_link_offers_it_to_every_line(env, price_type):
    """AC-39 shape 1: every template NULL -> exactly what main offers today."""
    db, c, _ = env
    product = _product(db, _reference(db))
    a = _template(db, "A")
    _link(db, product, a)
    assert _offered(c, product, price_type=price_type) == {a}
    for line_type in ("list", "selling"):
        assert _stored(c, product, line_type) == a


@pytest.mark.parametrize("price_type", [None, "list", "selling"])
def test_release_day_a_product_with_two_unset_links_offers_both_and_needs_a_pick(env, price_type):
    """AC-39 shape 2."""
    db, c, _ = env
    product = _product(db, _reference(db))
    a, b = _template(db, "A"), _template(db, "B")
    _link(db, product, a, b)
    assert _offered(c, product, price_type=price_type) == {a, b}
    for line_type in ("list", "selling"):
        body = _draft(c, [_line(product, line_type)])
        assert body["lines"][0]["tag_template_id"] is None
        res = _submit(c, body["id"])
        assert res.status_code == 422 and res.json()["code"] == "TAG_TEMPLATE_REQUIRED"


@pytest.mark.parametrize("price_type", [None, "list", "selling"])
def test_release_day_a_combo_with_unset_links_offers_its_own_links(env, price_type):
    """AC-39 shape 3: the combo's links, not the host's."""
    db, c, _ = env
    host = _product(db, _reference(db))
    h = _template(db, "H")
    _link(db, host, h)
    combo = _combo(db, host, "ZZT release combo")
    c1, c2 = _template(db, "C1"), _template(db, "C2")
    _combo_link(db, combo.id, c1)
    _combo_link(db, combo.id, c2)
    assert _offered(c, host, combo, price_type) == {c1, c2}


@pytest.mark.parametrize("price_type", [None, "list", "selling"])
def test_release_day_a_combo_without_links_offers_the_hosts(env, price_type):
    """AC-39 shape 4."""
    db, c, _ = env
    host = _product(db, _reference(db))
    h1 = _template(db, "H1")
    _link(db, host, h1)
    bare = _combo(db, host, "ZZT bare release combo")
    assert _offered(c, host, bare, price_type) == {h1}
    for line_type in ("list", "selling"):
        assert _stored(c, host, line_type, bare) == h1
