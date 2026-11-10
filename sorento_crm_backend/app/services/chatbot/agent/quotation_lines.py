"""`crm_project_quotation_lines`: a project's quotation documents with their lines, compact, for comparing.

Local and in process as the user (company scope and the project route's own 404 apply). The list tool answers
"what did we quote" per scope; this one answers "what is on it": each document's scopes at their CURRENT version,
or at the versions an issued revision pinned (`refs`). Photos and signed URLs are not read.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.services import project_quotation_service as svc
from app.services import project_service as projects
from app.services.project_quotation_document_service import quotation_no


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def _line(row: Any) -> dict[str, Any]:
    listed = row.list_price_snapshot
    unit = Decimal(row.unit_price or 0)
    # Below list only: a line priced above list is not a discount (a negative one cannot be verified in an answer).
    discount = round(float((listed - unit) / listed * 100), 2) if listed and unit <= listed else None
    above = round(float((unit - listed) / listed * 100), 2) if listed and unit > listed else None
    return {
        "code": row.product_code_snapshot,
        "description": svc.line_text(row),  # plain text, never the stored rich-text markup
        "qty": _num(row.quantity),
        "uom": row.uom,
        "list_price": _num(listed),
        "unit_price": _num(unit),
        "discount_pct": discount,
        "above_list_pct": above,
        "line_total": _num(row.line_total),
        "rate_only": bool(row.is_rate_only),
    }


def _scope(label: str | None, version_no: int | None, version_id: str | None, total: Any) -> dict:
    """A scope with its version id kept aside (`_vid`) until `_fill` reads every version's lines in one query."""
    return {"scope": label, "version": version_no, "total": _num(total) or 0.0, "lines": [], "_vid": version_id}


def _fill(db: Session, scopes: list[dict]) -> None:
    from app.models.projects import ProjectQuotationLine as Line

    ids = {s["_vid"] for s in scopes if s["_vid"]}
    by_version: dict[str, list[dict]] = {}
    if ids:
        rows = (
            db.query(Line)
            .filter(Line.version_id.in_(ids))
            .order_by(Line.sort_order.asc(), Line.created_at.asc(), Line.id.asc())  # the order `list_lines` gives
            .all()
        )
        for row in rows:
            by_version.setdefault(row.version_id, []).append(_line(row))
    for scope in scopes:
        scope["lines"] = list(by_version.get(scope.pop("_vid"), []))


def project_quotation_lines(db: Session, project_id: str, refs: list[str], cap: int) -> tuple[dict, int]:
    """`(data, items_not_shown)`. Raises the project route's 404 for an unknown project."""
    from app.models.projects import (
        ProjectQuotation,
        ProjectQuotationDocument,
        ProjectQuotationIssue,
        ProjectQuotationIssueScope,
        ProjectQuotationVersion,
    )

    projects.get_project_or_404(db, project_id)
    documents = (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.project_id == project_id)
        .order_by(ProjectQuotationDocument.created_at.asc(), ProjectQuotationDocument.id.asc())
        .all()
    )
    scopes = (
        db.query(ProjectQuotation)
        .filter(ProjectQuotation.project_id == project_id)
        .order_by(ProjectQuotation.sort_order.asc(), ProjectQuotation.created_at.asc(), ProjectQuotation.id.asc())
        .all()
    )
    current = {row["id"]: row for row in svc.serialize_quotations(db, scopes)}
    wanted = [r.strip() for r in refs if isinstance(r, str) and r.strip()]
    issues = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.document_id.in_([d.id for d in documents]))
        .order_by(ProjectQuotationIssue.issue_no.asc())
        .all()
        if documents and wanted
        else []
    )
    out: list[dict] = []
    matched: set[str] = set()

    def current_doc(doc: Any) -> dict:
        rows = [current[s.id] for s in scopes if s.document_id == doc.id]
        built = [_scope(r["scope_label"], r["current_version_no"], r["current_version_id"], r["current_total"]) for r in rows]
        return {
            "ref": doc.document_no, "document_no": doc.document_no, "revision": None,
            "total": round(sum(s["total"] for s in built), 2), "scopes": built,
        }

    def issued_doc(doc: Any, issue: Any) -> dict:
        pinned = (
            db.query(ProjectQuotationIssueScope, ProjectQuotation, ProjectQuotationVersion)
            .join(ProjectQuotation, ProjectQuotation.id == ProjectQuotationIssueScope.quotation_id)
            .join(ProjectQuotationVersion, ProjectQuotationVersion.id == ProjectQuotationIssueScope.version_id)
            .filter(ProjectQuotationIssueScope.issue_id == issue.id)
            .order_by(ProjectQuotationIssueScope.sort_order.asc())
            .all()
        )
        built = [_scope(q.scope_label, v.version_no, v.id, p.scope_total) for p, q, v in pinned]
        ref = quotation_no(doc.document_no, issue.issue_no, issue.revision_label)
        return {
            "ref": ref, "document_no": doc.document_no, "revision": issue.revision_label or f"R{issue.issue_no}",
            "total": _num(issue.grand_total) or 0.0, "scopes": built,
        }

    if not wanted:
        out = [current_doc(d) for d in documents]
    else:
        lowered = {r.lower(): r for r in wanted}
        for doc in documents:
            if doc.document_no.lower() in lowered:
                matched.add(doc.document_no.lower())
                out.append(current_doc(doc))
            for issue in (i for i in issues if i.document_id == doc.id):
                ref = quotation_no(doc.document_no, issue.issue_no, issue.revision_label)
                if ref.lower() in lowered:
                    matched.add(ref.lower())
                    out.append(issued_doc(doc, issue))
    _fill(db, [sc for d in out for sc in d["scopes"]])
    not_found = [r for r in wanted if r.lower() not in matched]
    data: dict[str, Any] = {"documents": out, "not_found": not_found}
    return data, _fit(data, cap)


def _fit(data: dict, cap: int) -> int:
    """Cut lines, from the scope with most, until the JSON is under `cap` characters; each cut scope says how many
    it left out. With no lines left, whole documents go (`documents_not_shown`). Returns the count cut. What is
    left (an empty `documents` and at most ten `not_found` refs) is far under any cap."""
    cut = 0
    scope_rows = [s for d in data["documents"] for s in d["scopes"]]
    while len(json.dumps(data, default=str)) > cap:
        biggest = max(scope_rows, key=lambda s: len(s["lines"]), default=None)
        if biggest is None or not biggest["lines"]:
            # No lines left to cut: whole documents go, last first, and are counted.
            if not data["documents"]:
                break
            data["documents"].pop()
            data["documents_not_shown"] = data.get("documents_not_shown", 0) + 1
            cut += 1
            scope_rows = [s for d in data["documents"] for s in d["scopes"]]
            continue
        drop = max(1, len(biggest["lines"]) // 4)
        del biggest["lines"][-drop:]
        biggest["lines_not_shown"] = biggest.get("lines_not_shown", 0) + drop
        cut += drop
    return cut
