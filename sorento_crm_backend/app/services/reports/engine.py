"""Run a report definition against the database and return what the screen renders.

Two layouts over one row set:

- **Detail** - the requested catalog columns, in the requested order, plus a total for
  every measure among them.
- **Pivot** - GROUP BY row dimension, column dimension in SQL; the matrix, the row and
  column totals and the grand total assembled here from Decimals.

Every total in the result is computed HERE, so the screen and the exported workbook cannot
disagree (the workbook writes values, never formulas - AC-D4). Money is a decimal string
with two places, or absent: a form with no lines has no sample price, and the workbook
prints "-" there rather than 0.00.

The sync path is capped (5,000 detail rows / 5,000 pivot cells) and answers 422 with
``capped: true``; the export path passes ``cap=False`` and has no cap.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import status
from sqlalchemy import and_, func
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.schemas.report import (
    ReportColumn,
    ReportColumnGroup,
    ReportDetailLayout,
    ReportLayouts,
    ReportPivotColumnDimension,
    ReportPivotDimension,
    ReportPivotLayout,
    ReportResult,
    ReportViewConfig,
)
from app.services.error_handler import AppException
from app.services.reports import registry as reg

# The sync caps. A run over either is refused and the user is pointed at the uncapped
# export - the refusal IS the answer, not a failure.
DETAIL_ROW_CAP = 5000
PIVOT_CELL_CAP = 5000

_MONTH_ABBR = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

_TWO_PLACES = Decimal("0.01")


class ReportCapped(AppException):
    """A 422 the frontend can tell apart from a failure: the body carries `capped: true`.

    AppException's envelope is `message`/`detail`/`code` and the global handler serialises it
    FLAT (app/main.py), so the flag sits alongside the message. Without it a capped run reads
    as "something went wrong" instead of "narrow this, or export instead".
    """

    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message=message,
            code="REPORT_CAPPED",
        )
        self.detail = {**self.detail, "capped": True}


def _invalid(message: str) -> AppException:
    return AppException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message=message,
        code="REPORT_INVALID_PARAMS",
    )


# ---------------------------------------------------------------------- the period


@dataclass(frozen=True)
class Period:
    kind: str
    start: date
    end_exclusive: date
    label: str
    months: Tuple[str, ...]


def _month_key(value: date) -> str:
    return f"{value.year}-{value.month:02d}"


def _month_label(value: date) -> str:
    return f"{_MONTH_ABBR[value.month - 1]}'{str(value.year)[2:]}"


def _add_month(value: date) -> date:
    return date(value.year + 1, 1, 1) if value.month == 12 else date(value.year, value.month + 1, 1)


def _months_between(start: date, end_exclusive: date) -> Tuple[str, ...]:
    keys: List[str] = []
    cursor = date(start.year, start.month, 1)
    while cursor < end_exclusive:
        keys.append(_month_key(cursor))
        cursor = _add_month(cursor)
    return tuple(keys)


def _parse_date(value: Any, field_name: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise _invalid(f"Invalid date '{value}' for '{field_name}'")


def resolve_period(raw: Any) -> Period:
    if not isinstance(raw, dict):
        raise _invalid("Invalid period: expected an object with a 'kind'")
    kind = raw.get("kind")

    if kind == "year":
        try:
            year = int(raw["year"])
        except (KeyError, TypeError, ValueError):
            raise _invalid("Invalid period: 'year' is required for a yearly period")
        start, end = date(year, 1, 1), date(year + 1, 1, 1)
        suffix = str(year)[2:]
        return Period(kind, start, end, f"Jan'{suffix} to Dec'{suffix}", _months_between(start, end))

    if kind == "month_range":
        try:
            year = int(raw["year"])
            from_month = int(raw["from_month"])
            to_month = int(raw["to_month"])
        except (KeyError, TypeError, ValueError):
            raise _invalid(
                "Invalid period: 'year', 'from_month' and 'to_month' are required for a month range"
            )
        if not 1 <= from_month <= 12 or not 1 <= to_month <= 12 or from_month > to_month:
            raise _invalid(f"Invalid period: months {from_month} to {to_month}")
        start = date(year, from_month, 1)
        end = _add_month(date(year, to_month, 1))
        suffix = str(year)[2:]
        label = f"{_MONTH_ABBR[from_month - 1]}'{suffix} to {_MONTH_ABBR[to_month - 1]}'{suffix}"
        return Period(kind, start, end, label, _months_between(start, end))

    if kind == "custom":
        start = _parse_date(raw.get("from"), "period.from")
        last = _parse_date(raw.get("to"), "period.to")
        if last < start:
            raise _invalid("Invalid period: 'to' is before 'from'")
        end = last + timedelta(days=1)
        return Period(
            kind, start, end, f"{start.isoformat()} to {last.isoformat()}", _months_between(start, end)
        )

    raise _invalid(f"Unknown period kind '{kind}'")


# --------------------------------------------------------------------- the context


@dataclass
class QueryContext:
    """What every expression in a dataset is a function of."""

    db: Session
    definition: reg.ReportDefinition
    date_basis_key: str
    date_basis: ColumnElement
    period: Period
    values: Dict[str, Any] = field(default_factory=dict)

    @property
    def dataset(self) -> reg.Dataset:
        return self.definition.dataset


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def resolve(db: Session, definition: reg.ReportDefinition, params: Dict[str, Any]) -> QueryContext:
    """Validate the incoming params against the definition and bind them (AC-A3)."""
    params = dict(params or {})
    known = {p.key for p in definition.params}
    for key in params:
        if key not in known:
            raise _invalid(f"Unknown param '{key}'")

    basis_key: Optional[str] = None
    period: Optional[Period] = None
    values: Dict[str, Any] = {}

    for param in definition.params:
        given = params.get(param.key, None)
        if isinstance(param, reg.DateBasisParam):
            basis_key = str(given) if given not in (None, "") else param.default
            if definition.dataset.basis(basis_key) is None:
                raise _invalid(f"Unknown date basis '{basis_key}' for '{param.key}'")
            values[param.key] = basis_key
        elif isinstance(param, reg.PeriodParam):
            period = resolve_period(given if given is not None else param.default)
            values[param.key] = period
        elif isinstance(param, reg.SelectParam):
            chosen = _as_list(given) if given is not None else list(param.default)
            values[param.key] = chosen
        else:  # pragma: no cover - a param type nobody has declared
            raise _invalid(f"Unsupported param type for '{param.key}'")

    if basis_key is None or period is None:
        raise _invalid(f"Report '{definition.key}' declares no date basis or no period param")

    return QueryContext(
        db=db,
        definition=definition,
        date_basis_key=basis_key,
        date_basis=definition.dataset.basis(basis_key).expr,
        period=period,
        values=values,
    )


def _predicates(ctx: QueryContext) -> List[ColumnElement]:
    """Period + every select filter + the company scope, in one list."""
    preds: List[ColumnElement] = [
        ctx.date_basis >= ctx.period.start,
        ctx.date_basis < ctx.period.end_exclusive,
    ]
    for param in ctx.definition.params:
        if not isinstance(param, reg.SelectParam):
            continue
        chosen = ctx.values.get(param.key) or []
        if not chosen:  # an empty multi-select means "no filter", as the screen shows
            continue
        condition = param.condition(ctx, chosen)
        if condition is not None:
            preds.append(condition)

    dataset = ctx.dataset
    if dataset.scope == "company":
        from app.services.company_scope import admin_listing_company_filter

        company = admin_listing_company_filter(ctx.db, dataset.company_column)
        if company is not None:
            preds.append(company)
    return preds


# -------------------------------------------------------------------- value shapes


def _money(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(Decimal(str(value)).quantize(_TWO_PLACES))


def _cell_value(column: reg.Column, value: Any) -> Any:
    if value is None:
        return None
    if column.type == "money":
        return _money(value)
    if column.type == "date":
        return value.date().isoformat() if isinstance(value, datetime) else str(value)
    if column.type == "integer":
        return int(value)
    if column.type == "bool":
        return bool(value)
    return str(value)


def _dimension_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


def _totals(sums: Dict[str, Optional[Decimal]]) -> Dict[str, str]:
    return {key: str(total.quantize(_TWO_PLACES)) for key, total in sums.items() if total is not None}


# -------------------------------------------------------------------------- detail


def _detail(ctx: QueryContext, view: ReportViewConfig, cap: bool) -> ReportDetailLayout:
    definition = ctx.definition
    dataset = ctx.dataset
    requested = list(view.detail.columns) or [c.key for c in dataset.columns]

    columns: List[reg.Column] = []
    for key in requested:
        column = dataset.column(key)
        if column is None:
            raise _invalid(f"Unknown detail column '{key}'")
        columns.append(column)

    stmt = dataset.base(ctx).add_columns(*[c.expr(ctx).label(c.key) for c in columns])
    stmt = stmt.where(and_(*_predicates(ctx)))
    order_by = list(definition.detail.order_by(ctx))
    if order_by:
        stmt = stmt.order_by(*order_by)
    if cap:
        stmt = stmt.limit(DETAIL_ROW_CAP + 1)

    fetched = ctx.db.execute(stmt).mappings().all()
    if cap and len(fetched) > DETAIL_ROW_CAP:
        raise ReportCapped(
            f"This run returns more than {DETAIL_ROW_CAP:,} rows. "
            "Narrow the period or export to Excel instead."
        )

    groups_by_source = {g.source: g for g in definition.detail.groups}
    tick_values: Dict[str, List[str]] = {}
    for source in groups_by_source:
        if any(c.key == source for c in columns):
            present = {_dimension_value(row[source]) for row in fetched}
            tick_values[source] = sorted(v for v in present if v)

    out_columns: List[ReportColumn] = []
    out_groups: List[ReportColumnGroup] = []
    for column in columns:
        if column.key in groups_by_source:
            values = tick_values.get(column.key) or []
            if not values:
                continue
            keys = [f"{column.key}__{value}" for value in values]
            out_columns.extend(
                ReportColumn(key=key, label=value, type="bool", size=80)
                for key, value in zip(keys, values)
            )
            out_groups.append(
                ReportColumnGroup(
                    label=groups_by_source[column.key].label, source=column.key, keys=keys
                )
            )
            continue
        out_columns.append(
            ReportColumn(key=column.key, label=column.label, type=column.type, size=column.size)
        )

    measures = [c for c in columns if c.tag == "measure"]
    sums: Dict[str, Optional[Decimal]] = {c.key: None for c in measures}

    rows: List[Dict[str, Any]] = []
    for fetched_row in fetched:
        row: Dict[str, Any] = {}
        for column in columns:
            value = fetched_row[column.key]
            if column.key in groups_by_source:
                rendered = _dimension_value(value)
                for tick in tick_values.get(column.key) or []:
                    row[f"{column.key}__{tick}"] = rendered == tick
                continue
            row[column.key] = _cell_value(column, value)
            if column.tag == "measure" and value is not None:
                sums[column.key] = (sums[column.key] or Decimal(0)) + Decimal(str(value))
        rows.append(row)

    return ReportDetailLayout(
        key=definition.detail.key,
        title=definition.detail.title,
        columns=out_columns,
        column_groups=out_groups,
        rows=rows,
        totals=_totals(sums),
    )


# --------------------------------------------------------------------------- pivot


def _dimension(ctx: QueryContext, key: str, role: str) -> reg.Column:
    column = ctx.dataset.column(key)
    if column is None or column.tag != "dimension":
        raise _invalid(f"'{key}' is not a dimension this report can group {role} by")
    return column


def _pivot(ctx: QueryContext, view: ReportViewConfig, cap: bool) -> ReportPivotLayout:
    definition = ctx.definition
    dataset = ctx.dataset
    config = view.pivot

    if config.rows == config.cols:
        raise _invalid("Rows and Columns cannot be the same dimension")
    row_column = _dimension(ctx, config.rows, "rows")
    col_column = _dimension(ctx, config.cols, "columns")

    measures: List[reg.Column] = []
    for key in config.measures:
        column = dataset.column(key)
        if column is None or column.tag != "measure":
            raise _invalid(f"'{key}' is not a measure this report can total")
        measures.append(column)

    row_expr = row_column.expr(ctx)
    col_expr = col_column.expr(ctx)
    stmt = dataset.base(ctx).add_columns(
        row_expr.label("__row"),
        col_expr.label("__col"),
        *[func.sum(m.expr(ctx)).label(f"__m{i}") for i, m in enumerate(measures)],
    )
    stmt = stmt.where(and_(*_predicates(ctx))).group_by(row_expr, col_expr)
    grouped = ctx.db.execute(stmt).mappings().all()

    cells: Dict[str, Dict[str, Dict[str, str]]] = {}
    row_sums: Dict[str, Dict[str, Decimal]] = {}
    col_sums: Dict[str, Dict[str, Decimal]] = {}
    grand: Dict[str, Decimal] = {}
    row_values: List[str] = []
    present_cols: List[str] = []

    for group in grouped:
        row_value = _dimension_value(group["__row"])
        col_value = _dimension_value(group["__col"])
        if not row_value or not col_value:
            continue
        if row_value not in row_values:
            row_values.append(row_value)
        if col_value not in present_cols:
            present_cols.append(col_value)
        for index, measure in enumerate(measures):
            total = group[f"__m{index}"]
            if total is None:  # every row in this cell was blank; the cell stays blank
                continue
            amount = Decimal(str(total))
            cells.setdefault(row_value, {}).setdefault(col_value, {})[measure.key] = _money(amount)
            row_sums.setdefault(row_value, {})
            row_sums[row_value][measure.key] = row_sums[row_value].get(measure.key, Decimal(0)) + amount
            col_sums.setdefault(col_value, {})
            col_sums[col_value][measure.key] = col_sums[col_value].get(measure.key, Decimal(0)) + amount
            grand[measure.key] = grand.get(measure.key, Decimal(0)) + amount

    row_values.sort()
    if col_column.period_months:
        # Every month of the period, empty ones included - the workbook has twelve sheets
        # whether or not December had a form.
        col_values = list(ctx.period.months)
    else:
        col_values = sorted(present_cols)

    value_labels = (
        {value: col_column.value_label(value) for value in col_values}
        if col_column.value_label
        else None
    )

    if cap and len(row_values) * len(col_values) > PIVOT_CELL_CAP:
        raise ReportCapped(
            f"This summary is more than {PIVOT_CELL_CAP:,} cells. "
            "Group by something coarser or export to Excel instead."
        )

    return ReportPivotLayout(
        key=definition.pivot.key,
        title=definition.pivot.title,
        row_dim=ReportPivotDimension(key=row_column.key, label=row_column.label),
        col_dim=ReportPivotColumnDimension(
            key=col_column.key,
            label=col_column.label,
            values=col_values,
            value_labels=value_labels,
        ),
        measures=[
            ReportColumn(key=m.key, label=m.label, type=m.type, size=m.size) for m in measures
        ],
        row_values=row_values,
        cells=cells,
        row_totals={k: _totals(v) for k, v in row_sums.items()},
        col_totals={k: _totals(v) for k, v in col_sums.items()},
        grand_total=_totals(grand),
    )


# ----------------------------------------------------------------------------- run


def view_config(definition: reg.ReportDefinition) -> ReportViewConfig:
    """The definition's own default view, as the wire shape."""
    return ReportViewConfig.model_validate(definition.default_view)


def run(
    db: Session,
    definition: reg.ReportDefinition,
    params: Dict[str, Any],
    view: Optional[ReportViewConfig] = None,
    *,
    cap: bool = True,
) -> ReportResult:
    """Both layouts over one row set. ``cap=False`` is the export path (AC-A7)."""
    ctx = resolve(db, definition, params)
    effective = view or view_config(definition)

    detail = _detail(ctx, effective, cap)
    summary = _pivot(ctx, effective, cap)

    return ReportResult(
        key=definition.key,
        period_label=ctx.period.label,
        row_count=len(detail.rows),
        capped=False,
        layouts=ReportLayouts(detail=detail, summary=summary),
    )
