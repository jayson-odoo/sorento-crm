"""Resource-specific list-query filter compilers."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Union

from sqlalchemy import ColumnElement, Numeric, and_, cast, exists, func, or_, select

from app.models.inventory import Warehouse
from app.models.list_query_metadata import ListQueryField
from app.models.marketing import Promotion
from app.models.order import Order, OrderLine
from app.models.procurement import Supplier
from app.models.product import Product
from app.models.workflow_forms import WorkflowFormDefinition, WorkflowSubmission, WorkflowSubmissionLine
from app.schemas.list_query import FilterCondition, FilterGroup


def _meta_flag(meta: Any, attr: str, default: bool = False) -> bool:
    return bool(getattr(meta, attr, default))


def _meta_str(meta: Any, attr: str, default: str = "") -> str:
    val = getattr(meta, attr, default)
    return str(val) if val is not None else default


def _meta_allowed_ops(meta: Any) -> list[str]:
    raw = getattr(meta, "allowed_operators", None)
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


def _coerce_value(value: Any, data_type: str) -> Any:
    if value is None:
        return None
    if data_type == "number":
        return Decimal(str(value))
    if data_type == "boolean":
        if isinstance(value, bool):
            return value
        if str(value).lower() in ("1", "true", "yes"):
            return True
        if str(value).lower() in ("0", "false", "no"):
            return False
        raise ValueError("invalid boolean")
    if data_type == "uuid":
        return str(value)
    if data_type == "date":
        return value
    return value


def _apply_scalar(column: Any, op: str, value: Any, data_type: str) -> ColumnElement:
    if op == "is_null":
        want_null = value is True or str(value).lower() in ("true", "1", "yes")
        return column.is_(None) if want_null else column.isnot(None)

    v = _coerce_value(value, data_type)

    if op == "eq":
        return column == v
    if op == "ne":
        return column != v
    if op == "contains":
        return column.ilike(f"%{v}%")
    if op == "starts_with":
        return column.ilike(f"{v}%")
    if op == "in":
        if not isinstance(v, (list, tuple)) or not v:
            raise ValueError("in operator requires non-empty list value")
        return column.in_(list(v))
    if op == "gt":
        return column > v
    if op == "gte":
        return column >= v
    if op == "lt":
        return column < v
    if op == "lte":
        return column <= v
    raise ValueError(f"unsupported op {op}")


def _order_root_column(compile_key: str) -> Any:
    _, name = compile_key.split(".", 1)
    return getattr(Order, name)


def _order_line_inner(compile_key: str, op: str, value: Any, data_type: str) -> ColumnElement:
    _, name = compile_key.split(".", 1)
    col = getattr(OrderLine, name)
    return _apply_scalar(col, op, value, data_type)


def _compile_order_line_predicate(compile_key: str, op: str, value: Any, data_type: str) -> ColumnElement:
    inner = _order_line_inner(compile_key, op, value, data_type)
    return exists().where(and_(OrderLine.order_id == Order.id, inner))


def _compile_order_line_joined_predicate(compile_key: str, op: str, value: Any, data_type: str) -> ColumnElement:
    parts = compile_key.split(".")
    if len(parts) != 3 or parts[0] != "line":
        raise ValueError(f"invalid nested line compile_key: {compile_key}")
    _, rel, attr = parts
    if rel == "product":
        join_model = Product
        join_cond = OrderLine.product_id == Product.id
    elif rel == "warehouse":
        join_model = Warehouse
        join_cond = OrderLine.warehouse_id == Warehouse.id
    else:
        raise ValueError(f"unsupported line relation: {rel}")
    col = getattr(join_model, attr)
    pred = _apply_scalar(col, op, value, data_type)
    subq = (
        select(1)
        .select_from(OrderLine)
        .join(join_model, join_cond)
        .where(and_(OrderLine.order_id == Order.id, pred))
    )
    return exists(subq)


def _product_column(compile_key: str) -> Any:
    _, name = compile_key.split(".", 1)
    return getattr(Product, name)


def _supplier_column(compile_key: str) -> Any:
    _, name = compile_key.split(".", 1)
    return getattr(Supplier, name)


def _promotion_column(compile_key: str) -> Any:
    _, name = compile_key.split(".", 1)
    return getattr(Promotion, name)


def _workflow_def_column(compile_key: str) -> Any:
    _, name = compile_key.split(".", 1)
    return getattr(WorkflowFormDefinition, name)


def _workflow_sub_column(compile_key: str) -> Any:
    _, name = compile_key.split(".", 1)
    return getattr(WorkflowSubmission, name)


def _wf_hdr_text_expr(field_id: str) -> Any:
    return func.jsonb_extract_path_text(WorkflowSubmission.header_data, field_id)


def _wf_line_text_expr(field_id: str) -> Any:
    return func.jsonb_extract_path_text(WorkflowSubmissionLine.row_data, field_id)


def _apply_json_text_scalar(column_expr: Any, op: str, value: Any, data_type: str) -> ColumnElement:
    if op == "is_null":
        want_null = value is True or str(value).lower() in ("true", "1", "yes")
        return column_expr.is_(None) if want_null else column_expr.isnot(None)
    if data_type == "number":
        return _apply_scalar(cast(column_expr, Numeric), op, value, "number")
    if data_type == "boolean":
        if op != "eq":
            raise ValueError(f"unsupported op {op} for boolean JSON field")
        v = _coerce_value(value, "boolean")
        return column_expr == ("true" if v else "false")
    if data_type == "date":
        return _apply_scalar(column_expr, op, value, "string")
    return _apply_scalar(column_expr, op, value, "string")


def _compile_wf_sub_leaf(meta: Any, node: FilterCondition) -> ColumnElement:
    ck = _meta_str(meta, "compile_key")
    data_type = _meta_str(meta, "data_type", "string")
    allowed = _meta_allowed_ops(meta)
    if node.op not in allowed:
        raise ValueError(f"operator {node.op} not allowed for field {node.field_key}")
    if ck.startswith("wf_hdr:"):
        field_id = ck.split(":", 1)[1]
        if not field_id:
            raise ValueError("invalid wf_hdr compile_key")
        return _apply_json_text_scalar(_wf_hdr_text_expr(field_id), node.op, node.value, data_type)
    if ck.startswith("wf_ln:"):
        parts = ck.split(":", 2)
        if len(parts) != 3 or parts[0] != "wf_ln":
            raise ValueError("invalid wf_ln compile_key")
        _, line_group_id, field_id = parts
        if not line_group_id or not field_id:
            raise ValueError("invalid wf_ln path")
        pred = _apply_json_text_scalar(_wf_line_text_expr(field_id), node.op, node.value, data_type)
        return exists().where(
            and_(
                WorkflowSubmissionLine.submission_id == WorkflowSubmission.id,
                WorkflowSubmissionLine.line_group_id == line_group_id,
                pred,
            )
        )
    if ck.startswith("sub."):
        return _apply_scalar(_workflow_sub_column(ck), node.op, node.value, data_type)
    raise ValueError(f"unsupported workflow submission compile_key: {ck}")


def _compile_orders(node: Union[FilterGroup, FilterCondition], field_by_key: Dict[str, ListQueryField]) -> ColumnElement:
    if isinstance(node, FilterGroup):
        parts = [_compile_orders(c, field_by_key) for c in node.children]
        return and_(*parts) if node.op == "and" else or_(*parts)
    meta = field_by_key.get(node.field_key)
    if meta is None or not _meta_flag(meta, "filterable", False):
        raise ValueError(f"unknown or non-filterable field: {node.field_key}")
    allowed = _meta_allowed_ops(meta)
    if node.op not in allowed:
        raise ValueError(f"operator {node.op} not allowed for field {node.field_key}")
    ck = _meta_str(meta, "compile_key")
    data_type = _meta_str(meta, "data_type", "string")
    if ck.startswith("line.") and ck.count(".") >= 2:
        parts = ck.split(".")
        if len(parts) == 3 and parts[1] in ("product", "warehouse"):
            return _compile_order_line_joined_predicate(ck, node.op, node.value, data_type)
    if ck.startswith("line."):
        return _compile_order_line_predicate(ck, node.op, node.value, data_type)
    return _apply_scalar(_order_root_column(ck), node.op, node.value, data_type)


def _compile_products(node: Union[FilterGroup, FilterCondition], field_by_key: Dict[str, ListQueryField]) -> ColumnElement:
    if isinstance(node, FilterGroup):
        parts = [_compile_products(c, field_by_key) for c in node.children]
        return and_(*parts) if node.op == "and" else or_(*parts)
    meta = field_by_key.get(node.field_key)
    if meta is None or not _meta_flag(meta, "filterable", False):
        raise ValueError(f"unknown or non-filterable field: {node.field_key}")
    if node.op not in _meta_allowed_ops(meta):
        raise ValueError(f"operator {node.op} not allowed for field {node.field_key}")
    return _apply_scalar(
        _product_column(_meta_str(meta, "compile_key")),
        node.op,
        node.value,
        _meta_str(meta, "data_type", "string"),
    )


def _compile_suppliers(node: Union[FilterGroup, FilterCondition], field_by_key: Dict[str, ListQueryField]) -> ColumnElement:
    if isinstance(node, FilterGroup):
        parts = [_compile_suppliers(c, field_by_key) for c in node.children]
        return and_(*parts) if node.op == "and" else or_(*parts)
    meta = field_by_key.get(node.field_key)
    if meta is None or not _meta_flag(meta, "filterable", False):
        raise ValueError(f"unknown or non-filterable field: {node.field_key}")
    if node.op not in _meta_allowed_ops(meta):
        raise ValueError(f"operator {node.op} not allowed for field {node.field_key}")
    return _apply_scalar(
        _supplier_column(_meta_str(meta, "compile_key")),
        node.op,
        node.value,
        _meta_str(meta, "data_type", "string"),
    )


def _compile_promotions(node: Union[FilterGroup, FilterCondition], field_by_key: Dict[str, ListQueryField]) -> ColumnElement:
    if isinstance(node, FilterGroup):
        parts = [_compile_promotions(c, field_by_key) for c in node.children]
        return and_(*parts) if node.op == "and" else or_(*parts)
    meta = field_by_key.get(node.field_key)
    if meta is None or not _meta_flag(meta, "filterable", False):
        raise ValueError(f"unknown or non-filterable field: {node.field_key}")
    if node.op not in _meta_allowed_ops(meta):
        raise ValueError(f"operator {node.op} not allowed for field {node.field_key}")
    return _apply_scalar(
        _promotion_column(_meta_str(meta, "compile_key")),
        node.op,
        node.value,
        _meta_str(meta, "data_type", "string"),
    )


def _compile_workflow_form_definitions(
    node: Union[FilterGroup, FilterCondition], field_by_key: Dict[str, ListQueryField]
) -> ColumnElement:
    if isinstance(node, FilterGroup):
        parts = [_compile_workflow_form_definitions(c, field_by_key) for c in node.children]
        return and_(*parts) if node.op == "and" else or_(*parts)
    meta = field_by_key.get(node.field_key)
    if meta is None or not _meta_flag(meta, "filterable", False):
        raise ValueError(f"unknown or non-filterable field: {node.field_key}")
    if node.op not in _meta_allowed_ops(meta):
        raise ValueError(f"operator {node.op} not allowed for field {node.field_key}")
    return _apply_scalar(
        _workflow_def_column(_meta_str(meta, "compile_key")),
        node.op,
        node.value,
        _meta_str(meta, "data_type", "string"),
    )


def _compile_workflow_form_submissions(
    node: Union[FilterGroup, FilterCondition], field_by_key: Dict[str, Any]
) -> ColumnElement:
    if isinstance(node, FilterGroup):
        parts = [_compile_workflow_form_submissions(c, field_by_key) for c in node.children]
        return and_(*parts) if node.op == "and" else or_(*parts)
    meta = field_by_key.get(node.field_key)
    if meta is None or not _meta_flag(meta, "filterable", False):
        raise ValueError(f"unknown or non-filterable field: {node.field_key}")
    ck = _meta_str(meta, "compile_key")
    if ck.startswith("rel."):
        raise ValueError(f"field {node.field_key} is not filterable")
    if ck.startswith("wf_hdr:") or ck.startswith("wf_ln:") or ck.startswith("sub."):
        return _compile_wf_sub_leaf(meta, node)
    raise ValueError(f"unsupported workflow submission compile_key: {ck}")


RESOURCE_COMPILERS = {
    "orders": _compile_orders,
    "products": _compile_products,
    "suppliers": _compile_suppliers,
    "promotions": _compile_promotions,
    "workflow_form_definitions": _compile_workflow_form_definitions,
    "workflow_form_submissions": _compile_workflow_form_submissions,
}

