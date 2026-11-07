"""PRICETAG-COMBO-FORMAT S6: one default LP and one default SP template per product / combo.

UAC: documentation/plans/dealer-kit/pricetag-combo-format-acceptance-criteria.md, AC-31.

Written test-FIRST (PRINCIPLES.md Phase 2). `default_list` / `default_selling` / `price_type`
do not exist on the links yet, so the PUT keys are ignored, the items lack the fields, and the
ORM constructor refuses the new column names.

Harness reused from `tests/test_product_tag_templates.py` and `tests/test_price_tag_lpsp_templates.py`.

KILL: drop the type-fit check (`TEMPLATE_PRICE_TYPE_MISMATCH`) -> the two mismatch tests go red.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests.test_price_tag_lpsp_templates import _combo, _foreign_combo  # noqa: F401
from tests.test_product_tag_templates import (  # noqa: F401  (env is a fixture)
    DK,
    VIEWER_ID,
    _product,
    _reference,
    _template,
    env,
)


def _typed(db, name: str, price_type: str | None, *, published: bool = True) -> str:
    """A template of a given price type. Raw SQL on purpose: an unknown column must fail here,
    not be swallowed as a plain attribute on a model that has no such column."""
    template_id = _template(db, name, published=published)
    if price_type is not None:
        db.execute(
            text("UPDATE tag_template SET price_type = :p WHERE id = :i"),
            {"p": price_type, "i": template_id},
        )
        db.flush()
    return template_id


def _flag_ids(items: list[dict], flag: str) -> list[str]:
    return [row["id"] for row in items if row[flag]]


def _owners(db):
    """(label, url, setter-url-builder) for a product and a combo, each its own chain."""
    product = _product(db, _reference(db))
    combo = _combo(db, _product(db, _reference(db)))
    return [
        ("product", f"{DK}/products/{product}/tag-templates"),
        ("combo", f"{DK}/combos/{combo.id}/tag-templates"),
    ]


# --------------------------------------------------------------------------- AC-31
@pytest.mark.parametrize("owner", [0, 1], ids=["product", "combo"])
def test_put_stores_a_default_per_type_and_get_reports_both(env, owner):
    db, c, _ = env
    _label, url = _owners(db)[owner]
    lp, sp, other = _typed(db, "LP", "list"), _typed(db, "SP", "selling"), _typed(db, "BOTH", "both")

    res = c.put(
        url,
        json={
            "template_ids": [lp, sp, other],
            "default_list_template_id": lp,
            "default_selling_template_id": sp,
        },
    )
    assert res.status_code == 200, res.text
    for items in (res.json(), c.get(url).json()):
        assert _flag_ids(items, "default_list") == [lp]
        assert _flag_ids(items, "default_selling") == [sp]
        by_id = {row["id"]: row for row in items}
        assert by_id[lp]["price_type"] == "list"
        assert by_id[sp]["price_type"] == "selling"
        assert by_id[other]["price_type"] == "both"
        # compat key: a default of either kind
        assert set(_flag_ids(items, "is_default")) == {lp, sp}


@pytest.mark.parametrize("owner", [0, 1], ids=["product", "combo"])
def test_the_two_defaults_can_be_one_template_and_move_independently(env, owner):
    db, c, _ = env
    _label, url = _owners(db)[owner]
    a, b = _typed(db, "A", "both"), _typed(db, "B", "both")

    res = c.put(
        url,
        json={"template_ids": [a, b], "default_list_template_id": a, "default_selling_template_id": a},
    )
    assert res.status_code == 200, res.text
    assert _flag_ids(res.json(), "default_list") == [a]
    assert _flag_ids(res.json(), "default_selling") == [a]

    res = c.put(
        url,
        json={"template_ids": [a, b], "default_list_template_id": a, "default_selling_template_id": b},
    )
    assert _flag_ids(res.json(), "default_list") == [a]
    assert _flag_ids(res.json(), "default_selling") == [b]


@pytest.mark.parametrize("owner", [0, 1], ids=["product", "combo"])
def test_the_legacy_default_template_id_sets_both(env, owner):
    """Contract: with neither new key sent, `default_template_id` sets BOTH defaults."""
    db, c, _ = env
    _label, url = _owners(db)[owner]
    a, b = _typed(db, "A", "both"), _typed(db, "B", "both")
    res = c.put(url, json={"template_ids": [a, b], "default_template_id": b})
    assert res.status_code == 200, res.text
    assert _flag_ids(res.json(), "default_list") == [b]
    assert _flag_ids(res.json(), "default_selling") == [b]


@pytest.mark.parametrize("owner", [0, 1], ids=["product", "combo"])
@pytest.mark.parametrize(
    "key, wrong_type",
    [("default_selling_template_id", "list"), ("default_list_template_id", "selling")],
)
def test_a_default_that_does_not_fit_its_type_is_422_and_writes_nothing(env, owner, key, wrong_type):
    """KILL: drop the type-fit check."""
    db, c, _ = env
    _label, url = _owners(db)[owner]
    keep = _typed(db, "Keep", "both")
    assert c.put(url, json={"template_ids": [keep]}).status_code == 200
    wrong = _typed(db, "Wrong", wrong_type)

    res = c.put(url, json={"template_ids": [keep, wrong], key: wrong})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "TEMPLATE_PRICE_TYPE_MISMATCH"
    assert {row["id"] for row in c.get(url).json()} == {keep}


@pytest.mark.parametrize("owner", [0, 1], ids=["product", "combo"])
def test_an_unset_template_may_be_either_default(env, owner):
    db, c, _ = env
    _label, url = _owners(db)[owner]
    unset, other = _typed(db, "Unset", None), _typed(db, "Other", "both")
    res = c.put(
        url,
        json={"template_ids": [unset, other], "default_list_template_id": unset,
              "default_selling_template_id": unset},
    )
    assert res.status_code == 200, res.text
    assert _flag_ids(res.json(), "default_list") == [unset]
    assert _flag_ids(res.json(), "default_selling") == [unset]
    assert {row["id"]: row["price_type"] for row in res.json()}[unset] is None


@pytest.mark.parametrize("owner", [0, 1], ids=["product", "combo"])
@pytest.mark.parametrize("key", ["default_list_template_id", "default_selling_template_id"])
def test_a_default_outside_the_linked_ids_is_422_with_the_unchanged_code(env, owner, key):
    db, c, _ = env
    _label, url = _owners(db)[owner]
    a, outside = _template(db, "A"), _template(db, "Out")
    res = c.put(url, json={"template_ids": [a], key: outside})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "INVALID_DEFAULT_TEMPLATE"


@pytest.mark.parametrize("owner", [0, 1], ids=["product", "combo"])
def test_a_malformed_new_default_is_422(env, owner):
    db, c, _ = env
    _label, url = _owners(db)[owner]
    a = _template(db, "A")
    for key in ("default_list_template_id", "default_selling_template_id"):
        assert c.put(url, json={"template_ids": [a], key: "not-a-uuid"}).status_code == 422


@pytest.mark.parametrize("owner", [0, 1], ids=["product", "combo"])
def test_the_new_defaults_need_the_manage_gate(env, owner):
    db, c, as_ = env
    _label, url = _owners(db)[owner]
    a = _template(db, "A")
    as_(VIEWER_ID)
    res = c.put(url, json={"template_ids": [a], "default_list_template_id": a})
    assert res.status_code == 403


@pytest.mark.parametrize(
    "price_type, list_default, selling_default",
    [
        ("both", True, True),
        ("list", True, False),
        ("selling", False, True),
        (None, True, True),
    ],
)
@pytest.mark.parametrize("owner", [0, 1], ids=["product", "combo"])
def test_a_lone_link_is_the_default_for_the_types_it_fits(
    env, owner, price_type, list_default, selling_default
):
    db, c, _ = env
    _label, url = _owners(db)[owner]
    only = _typed(db, "Only", price_type)
    for items in (c.put(url, json={"template_ids": [only]}).json(), c.get(url).json()):
        assert (_flag_ids(items, "default_list") == [only]) is list_default, price_type
        assert (_flag_ids(items, "default_selling") == [only]) is selling_default, price_type


def test_a_combo_whose_host_is_in_another_company_is_404(env):
    db, c, _ = env
    _host, combo = _foreign_combo(db)
    a = _template(db, "A")
    url = f"{DK}/combos/{combo.id}/tag-templates"
    assert c.get(url).status_code == 404
    res = c.put(url, json={"template_ids": [a], "default_list_template_id": a})
    assert res.status_code == 404


def test_unknown_combo_is_404(env):
    db, c, _ = env
    a = _template(db, "A")
    res = c.put(
        f"{DK}/combos/{uuid.uuid4()}/tag-templates",
        json={"template_ids": [a], "default_list_template_id": a},
    )
    assert res.status_code == 404
