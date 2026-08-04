"""Preview an outstanding-orders upload, and apply it once someone confirms.

Two entry points sharing one code path, which is the point: `preview()` and `apply()` build
the SAME diff from the SAME resolution, and apply simply writes what preview showed. A
preview computed differently from the commit is a preview that lies.

Resolution failures are surfaced, never guessed. An unknown item code is reported with its
row number and the line is skipped; it is not invented as a new product, because a typo
would otherwise silently become a SKU that gets planned and purchased.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.inventory import Warehouse
from app.models.product import Product
from app.services.import_alias_service import AliasResolver
from app.services.scm.outstanding_diff import (
    ADDED,
    CLOSED,
    Change,
    Diff,
    Line,
    diff_lines,
)
from app.services.scm.outstanding_reader import SO, ReadResult, RowProblem, read_workbook

# Demand class drives fulfilment priority. Anything that is not recognisably a project is
# treated as retail: under-prioritising a project order is visible and complained about,
# while over-prioritising every retail order quietly starves the projects.
_PROJECT_SEGMENTS = {"project", "projects", "contract"}
DEFAULT_DEMAND_CLASS = "retail"


@dataclass
class ResolutionIssue:
    row_number: int
    field: str
    value: str
    reason: str


@dataclass
class PreviewResult:
    doc_type: str
    scope_documents: tuple[str, ...]
    counts: dict
    total_rows: int
    unmapped_headers: list[str]
    missing_columns: list[str]
    row_problems: list[RowProblem] = field(default_factory=list)
    resolution_issues: list[ResolutionIssue] = field(default_factory=list)
    samples: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.missing_columns

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "ok": self.ok,
            "scope_documents": list(self.scope_documents),
            "counts": self.counts,
            "total_rows": self.total_rows,
            "unmapped_headers": self.unmapped_headers,
            "missing_columns": self.missing_columns,
            "row_problems": [asdict(p) for p in self.row_problems],
            "resolution_issues": [asdict(i) for i in self.resolution_issues],
            "samples": self.samples,
        }


@dataclass
class _Resolved:
    lines: list[Line]
    issues: list[ResolutionIssue]
    product_by_code: dict
    warehouse_by_code: dict
    customer_by_code: dict
    header_by_doc: dict


def _norm(code: str) -> str:
    return (code or "").strip().upper()


def _resolve(db: Session, read: ReadResult) -> _Resolved:
    """Map codes in the file onto real rows, reporting whatever cannot be resolved.

    Deliberately ORM queries, not raw SQL. `products`, `warehouses` and `sales_orders` are
    all company-scoped, and the isolation filter runs on ORM execution only - a raw
    `SELECT ... FROM products` sees EVERY company. That matters here rather than in theory:
    each company carries its own copy of the catalogue, so 11,390 product codes exist twice
    in this database. A raw lookup keyed by code would resolve to whichever row came back
    last and could attach an imported order line to another company's product.
    """
    issues: list[ResolutionIssue] = []

    item_codes = {_norm(l.item_code) for l in read.lines if l.item_code}
    loc_codes = {_norm(l.location) for l in read.lines if l.location}

    products: dict[str, str] = {}
    if item_codes:
        for pid, code in (
            db.query(Product.id, Product.product_code)
            .filter(func.upper(Product.product_code).in_(list(item_codes)))
            .all()
        ):
            products[_norm(code)] = str(pid)

    warehouses: dict[str, str] = {}
    if loc_codes:
        for wid, code in (
            db.query(Warehouse.id, Warehouse.warehouse_code)
            .filter(func.upper(Warehouse.warehouse_code).in_(list(loc_codes)))
            .all()
        ):
            warehouses[_norm(code)] = str(wid)

    kept: list[Line] = []
    for l in read.lines:
        row = int(l.row_ref) if (l.row_ref or "").isdigit() else 0
        pid = products.get(_norm(l.item_code))
        if not pid:
            # Never auto-create: a typo would become a SKU that gets planned and bought.
            issues.append(ResolutionIssue(row, "item_code", l.item_code,
                                          "no product with this code"))
            continue
        if l.location and _norm(l.location) not in warehouses:
            issues.append(ResolutionIssue(row, "stock_location", l.location,
                                          "no warehouse with this code"))
            continue
        kept.append(l)

    return _Resolved(lines=kept, issues=issues, product_by_code=products,
                     warehouse_by_code=warehouses, customer_by_code={},
                     header_by_doc={})


def _existing_lines(db: Session, docs: set[str]) -> list[Line]:
    """Current outstanding lines for the documents named in the file, as diff Lines.

    `row_ref` carries the DB line id so apply() can update in place rather than matching
    twice by content.
    """
    if not docs:
        return []
    # ORM, so the company-isolation filter applies. See `_resolve`: another company's order
    # carrying the same SO number must never be diffed against this upload, let alone closed
    # by it.
    rows = (
        db.query(
            SalesOrderLine.id,
            SalesOrder.so_number,
            Product.product_code,
            Warehouse.warehouse_code,
            (SalesOrderLine.qty_ordered - SalesOrderLine.qty_delivered).label("outstanding"),
            SalesOrderLine.required_date,
        )
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .join(Product, Product.id == SalesOrderLine.product_id)
        .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
        .filter(
            SalesOrder.so_number.in_(list(docs)),
            SalesOrder.status == "open",
            SalesOrderLine.line_status == "open",
            SalesOrderLine.qty_ordered > SalesOrderLine.qty_delivered,
        )
        .all()
    )
    return [
        Line(doc_number=r[1], item_code=r[2], location=r[3] or "",
             qty=float(r[4] or 0), required_date=r[5], row_ref=str(r[0]))
        for r in rows
    ]


def _samples(diff: Diff, limit: int = 8) -> dict:
    """A few real rows per change kind, so the confirm screen shows evidence not just counts."""
    out: dict = {}
    for c in diff.changes:
        if c.kind == "unchanged":
            continue
        bucket = out.setdefault(c.kind, [])
        if len(bucket) >= limit:
            continue
        bucket.append({
            "doc_number": c.doc_number,
            "item_code": c.item_code,
            "location": c.location,
            "qty_before": c.before.qty if c.before else None,
            "qty_after": c.after.qty if c.after else None,
            "date_before": c.before.required_date.isoformat()
                           if c.before and c.before.required_date else None,
            "date_after": c.after.required_date.isoformat()
                          if c.after and c.after.required_date else None,
            "days_moved": c.days_moved,
            "label": (c.after or c.before).label,
        })
    return out


def _build(db: Session, file_data: bytes, doc_type: str):
    resolver = AliasResolver.for_doc_type(db, doc_type)
    read = read_workbook(file_data, doc_type, resolver)
    if not read.ok:
        return read, None, None
    resolved = _resolve(db, read)
    existing = _existing_lines(db, {l.doc_number for l in resolved.lines})
    return read, resolved, diff_lines(existing, resolved.lines)


def preview(db: Session, file_data: bytes, doc_type: str = SO) -> PreviewResult:
    """What this upload would change. Writes nothing."""
    read, resolved, diff = _build(db, file_data, doc_type)
    if diff is None:
        return PreviewResult(
            doc_type=doc_type, scope_documents=(), counts={}, total_rows=read.total_rows,
            unmapped_headers=read.unmapped_headers, missing_columns=read.missing_columns,
            row_problems=read.problems,
        )
    return PreviewResult(
        doc_type=doc_type,
        scope_documents=diff.scope_documents,
        counts=diff.counts,
        total_rows=read.total_rows,
        unmapped_headers=read.unmapped_headers,
        missing_columns=read.missing_columns,
        row_problems=read.problems,
        resolution_issues=resolved.issues,
        samples=_samples(diff),
    )


def _demand_class_for(db: Session, debtor_code: str) -> str:
    if not debtor_code:
        return DEFAULT_DEMAND_CLASS
    # ORM again: customers are company-scoped too, and reading another company's customer
    # would decide this order's fulfilment priority from the wrong row.
    row = (
        db.query(func.lower(func.coalesce(Customer.market_segment_code, "")))
        .filter(func.upper(Customer.customer_code) == _norm(debtor_code))
        .limit(1)
        .scalar()
    )
    if row and any(seg in row for seg in _PROJECT_SEGMENTS):
        return "project"
    return DEFAULT_DEMAND_CLASS


def apply(db: Session, file_data: bytes, doc_type: str = SO,
          actor: Optional[str] = None) -> dict:
    """Write the upload. Returns the same counts the preview showed.

    Closing is `line_status = 'closed'`, not a delete. The line existed and was planned
    against; erasing it would make last week's plan unexplainable, and `scm.committed_v`
    already excludes non-open lines (migration 311).
    """
    read, resolved, diff = _build(db, file_data, doc_type)
    if diff is None:
        return {"ok": False, "missing_columns": read.missing_columns, "counts": {}}

    by_id = {str(l.row_ref): l for l in _existing_lines(db, set(diff.scope_documents))}
    order_ids: dict[str, str] = {}
    for so_number in diff.scope_documents:
        so = db.query(SalesOrder).filter(SalesOrder.so_number == so_number).one_or_none()
        if so is None:
            so = SalesOrder(so_number=so_number, status="open",
                            source_system="scm_upload", source_ref=doc_type)
            db.add(so)
            db.flush()
        order_ids[so_number] = so.id

    applied = {"added": 0, "updated": 0, "closed": 0, "unchanged": 0}
    for c in diff.changes:
        if c.kind == CLOSED:
            line = db.query(SalesOrderLine).filter(
                SalesOrderLine.id == c.before.row_ref).one_or_none()
            if line is not None:
                line.line_status = "closed"
                applied["closed"] += 1
            continue

        if c.kind == ADDED:
            pid = resolved.product_by_code.get(_norm(c.item_code))
            wid = resolved.warehouse_by_code.get(_norm(c.location)) if c.location else None
            db.add(SalesOrderLine(
                sales_order_id=order_ids[c.doc_number],
                product_id=pid,
                warehouse_id=wid,
                qty_ordered=c.after.qty,
                qty_delivered=0,
                required_date=c.after.required_date,
                line_status="open",
            ))
            applied["added"] += 1
            continue

        if c.kind == "unchanged":
            applied["unchanged"] += 1
            continue

        # qty and/or date changed: update the row the diff paired, in place.
        line = db.query(SalesOrderLine).filter(
            SalesOrderLine.id == c.before.row_ref).one_or_none()
        if line is None:
            continue
        # The extract states what is OUTSTANDING; qty_ordered is outstanding plus whatever
        # has already gone out, so a part-delivered line is not silently un-delivered.
        line.qty_ordered = float(line.qty_delivered or 0) + c.after.qty
        line.required_date = c.after.required_date
        applied["updated"] += 1

    db.flush()
    return {
        "ok": True,
        "counts": diff.counts,
        "applied": applied,
        "scope_documents": list(diff.scope_documents),
        "resolution_issues": [asdict(i) for i in resolved.issues],
        "row_problems": [asdict(p) for p in read.problems],
    }
