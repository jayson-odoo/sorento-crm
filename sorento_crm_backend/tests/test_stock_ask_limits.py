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
    product value with a NULL own-category value resolves to 0 even when the own
    category HAS a parent that carries a value, because `effective()` takes no
    second category through which that value could ever reach it (R2/R12).

    Blocking 3 (reviewer pass, PR #1221, 85c2e9e7): the previous fixture never gave
    the own category a `parent` attribute at all, so a kill mutation that added
    `getattr(category, "parent", None)` fallback code inside `effective()` stayed
    green - `getattr` just returned `None` for an attribute the fixture never set,
    which proves nothing about whether a walk would be followed if one existed. The
    own category here carries a real `parent` (and `parent_category`, the other
    plausible ORM relationship name) with X = 30 / Y = 5, so a parent-walk mutation
    resolves to (30, 5) and this test catches it; the un-mutated `effective()`
    still resolves to (0, 0)."""
    product = _obj(max_qty=None, eta_offset_days=None)
    parent_with_values = _obj(max_qty=30, eta_offset_days=5)
    own_category = SimpleNamespace(
        chatbot_max_qty=None,
        chatbot_eta_offset_days=None,
        parent=parent_with_values,
        parent_category=parent_with_values,
    )

    max_qty, eta = effective(product, own_category)

    assert (max_qty, eta) == (0, 0)
