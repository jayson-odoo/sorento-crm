"""Tests for dynamic list filter compiler."""
from unittest.mock import MagicMock

import pytest

from app.schemas.list_query import FilterCondition, FilterGroup
from app.services.query.filter_compiler import compile_filter


def _field(field_key: str, compile_key: str, data_type: str, ops: list):
    m = MagicMock()
    m.field_key = field_key
    m.compile_key = compile_key
    m.data_type = data_type
    m.filterable = True
    m.allowed_operators = ops
    return m


def test_compile_orders_and_contains():
    fg = FilterGroup(
        op="and",
        children=[
            FilterCondition(field_key="order_number", op="contains", value="ABC"),
            FilterCondition(field_key="is_cancelled", op="eq", value=False),
        ],
    )
    meta = {
        "order_number": _field("order_number", "order.order_number", "string", ["contains", "eq"]),
        "is_cancelled": _field("is_cancelled", "order.is_cancelled", "boolean", ["eq"]),
    }
    expr = compile_filter("orders", fg, meta)
    assert expr is not None


def test_compile_order_line_nested_product_contains():
    fg = FilterGroup(
        op="and",
        children=[
            FilterCondition(field_key="line_product_code", op="contains", value="SKU"),
        ],
    )
    meta = {
        "line_product_code": _field(
            "line_product_code",
            "line.product.product_code",
            "string",
            ["contains", "eq"],
        ),
    }
    expr = compile_filter("orders", fg, meta)
    assert expr is not None


def test_compile_order_line_product_eq():
    fg = FilterGroup(
        op="and",
        children=[
            FilterCondition(field_key="line_product_id", op="eq", value="550e8400-e29b-41d4-a716-446655440000"),
        ],
    )
    meta = {
        "line_product_id": _field(
            "line_product_id",
            "line.product_id",
            "uuid",
            ["eq", "ne", "in"],
        ),
    }
    expr = compile_filter("orders", fg, meta)
    assert expr is not None


def test_rejects_unknown_field():
    fg = FilterGroup(op="and", children=[FilterCondition(field_key="nope", op="eq", value="x")])
    with pytest.raises(ValueError, match="unknown"):
        compile_filter("orders", fg, {})


def test_rejects_disallowed_operator():
    meta = {
        "order_number": _field("order_number", "order.order_number", "string", ["eq"]),
    }
    fg = FilterGroup(
        op="and",
        children=[FilterCondition(field_key="order_number", op="contains", value="x")],
    )
    with pytest.raises(ValueError, match="not allowed"):
        compile_filter("orders", fg, meta)
