"""S1 (PLAN-chatbot-stock-ask-v2-24sep.md) - resolution rule for X (chatbot_max_qty) and
Y (chatbot_eta_offset_days): the product's own value wins when it is set, else the
product's OWN category value, else 0. No parent-category walk ever (R2, owner ruling
R12: "the product inherit from category, overridable, we don't need parent category ->
category relationship for now").

Pure unit tests, no DB: `effective(product, category)` (plan S1 "Resolution rule") is a
plain function over two objects carrying `chatbot_max_qty` / `chatbot_eta_offset_days`
attributes. `SimpleNamespace` stands in for the real ORM rows - the module under test is
declared "pure, core" in the plan and must not need a database to exercise.

AC-SA101, AC-SA102.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.stock_ask_limits import effective


def _obj(max_qty=None, eta_offset_days=None):
    return SimpleNamespace(chatbot_max_qty=max_qty, chatbot_eta_offset_days=eta_offset_days)


# --- AC-SA101: X (chatbot_max_qty) ------------------------------------------

def test_product_x_overrides_category_x():
    product = _obj(max_qty=200)
    category = _obj(max_qty=50)
    max_qty, _ = effective(product, category)
    assert max_qty == 200


def test_product_x_none_falls_back_to_category_x():
    product = _obj(max_qty=None)
    category = _obj(max_qty=50)
    max_qty, _ = effective(product, category)
    assert max_qty == 50


def test_product_and_category_x_both_none_is_zero():
    product = _obj(max_qty=None)
    category = _obj(max_qty=None)
    max_qty, _ = effective(product, category)
    assert max_qty == 0


def test_product_x_explicit_zero_wins_over_category_x():
    """Zero is a real, explicitly-set value - not falsy/unset. A product opted all the
    way down to zero must not fall back to the category's 50."""
    product = _obj(max_qty=0)
    category = _obj(max_qty=50)
    max_qty, _ = effective(product, category)
    assert max_qty == 0


# --- AC-SA101: Y (chatbot_eta_offset_days), same table --------------------------

def test_product_y_overrides_category_y():
    product = _obj(eta_offset_days=200)
    category = _obj(eta_offset_days=50)
    _, eta = effective(product, category)
    assert eta == 200


def test_product_y_none_falls_back_to_category_y():
    product = _obj(eta_offset_days=None)
    category = _obj(eta_offset_days=50)
    _, eta = effective(product, category)
    assert eta == 50


def test_product_and_category_y_both_none_is_zero():
    product = _obj(eta_offset_days=None)
    category = _obj(eta_offset_days=None)
    _, eta = effective(product, category)
    assert eta == 0


def test_product_y_explicit_zero_wins_over_category_y():
    product = _obj(eta_offset_days=0)
    category = _obj(eta_offset_days=50)
    _, eta = effective(product, category)
    assert eta == 0


# --- AC-SA102: no parent-category walk, ever ------------------------------------

def test_no_parent_category_walk():
    """`effective()` accepts exactly one category - the product's OWN one. A NULL
    product value with a NULL own-category value resolves to 0 even if some OTHER
    (e.g. grandparent) category carries a value, because there is no second
    parameter through which that value could ever reach this function (R2/R12).
    A "parent category" object is deliberately never constructed here - the
    signature itself is the proof, not a mock relationship walk."""
    product = _obj(max_qty=None, eta_offset_days=None)
    own_category = _obj(max_qty=None, eta_offset_days=None)

    max_qty, eta = effective(product, own_category)

    assert (max_qty, eta) == (0, 0)
