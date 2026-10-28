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


def test_compile_workflow_submission_header_json_contains():
    fg = FilterGroup(
        op="and",
        children=[FilterCondition(field_key="hdr:f1", op="contains", value="abc")],
    )
    meta = {
        "hdr:f1": _field("hdr:f1", "wf_hdr:f1", "string", ["contains", "eq"]),
    }
    expr = compile_filter("workflow_form_submissions", fg, meta)
    assert expr is not None


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


def test_rejects_unsupported_resource():
    meta = {
        "order_number": _field("order_number", "order.order_number", "string", ["eq"]),
    }
    fg = FilterGroup(op="and", children=[FilterCondition(field_key="order_number", op="eq", value="x")])
    with pytest.raises(ValueError, match="Unsupported resource"):
        compile_filter("unknown_resource", fg, meta)


# FILTER-MULTISELECT PR7 browser pass: the Advanced filter's multi pick list sends a LIST for
# "In list"; on a uuid field (Delivery Orders Order status, Products Category) the value adapter
# turned that list into one string and the compiler refused it ("in operator requires non-empty
# list value"). Each element is coerced on its own.
def test_compile_uuid_in_takes_a_list_of_ids():
    ids = ["550e8400-e29b-41d4-a716-446655440000", "650e8400-e29b-41d4-a716-446655440001"]
    fg = FilterGroup(
        op="and",
        children=[FilterCondition(field_key="line_product_id", op="in", value=ids)],
    )
    meta = {
        "line_product_id": _field("line_product_id", "line.product_id", "uuid", ["eq", "ne", "in"]),
    }
    expr = compile_filter("orders", fg, meta)
    assert expr is not None
    assert " IN " in str(expr).upper()


def test_in_coerces_each_element_of_the_list():
    from sqlalchemy import Numeric, column

    from app.services.query.filter_compiler_adapters import _apply_scalar

    expr = _apply_scalar(column("qty", Numeric), "in", ["1", "2.5"], "number")
    assert " IN " in str(expr).upper()


# Review round: a list is only meaningful for "In list". On any other operator it is refused
# (400) rather than coerced: a JSON boolean `eq [False]` would otherwise match "true", and a
# uuid / number `eq [..]` would reach the database as a 500.
def test_eq_with_a_list_is_refused():
    fg = FilterGroup(
        op="and",
        children=[
            FilterCondition(
                field_key="line_product_id", op="eq", value=["550e8400-e29b-41d4-a716-446655440000"]
            )
        ],
    )
    meta = {
        "line_product_id": _field("line_product_id", "line.product_id", "uuid", ["eq", "ne", "in"]),
    }
    with pytest.raises(ValueError, match="single value"):
        compile_filter("orders", fg, meta)


def test_workflow_boolean_eq_with_a_list_is_refused():
    fg = FilterGroup(
        op="and",
        children=[FilterCondition(field_key="hdr:f1", op="eq", value=[False])],
    )
    meta = {
        "hdr:f1": _field("hdr:f1", "wf_hdr:f1", "boolean", ["eq"]),
    }
    with pytest.raises(ValueError, match="single value"):
        compile_filter("workflow_form_submissions", fg, meta)
