"""`crm_project_quotation_lines`: a project's quotation documents with their lines, compact, for comparing.

Local and in process as the user (company scope and the project route's own 404 apply). The list tool answers
"what did we quote" per scope; this one answers "what is on it": each document's scopes at their CURRENT version,
or at the versions an issued revision pinned (`refs`). Photos and signed URLs are not read. Each document carries
its Prepared By and per-document facts; two or more carry a computed `comparison` (AGENT-PROPOSAL-INSIGHTS).
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.services import project_quotation_service as svc
from app.services import project_service as projects
from app.services.project_quotation_document_service import quotation_no
from app.services.project_quotation_template_service import prepared_by_names

#: The most entries each comparison list holds; the rest are counted in `<name>_not_shown`.
COMPARE_CAP = 20


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def vs_list(listed: Any, unit: Any) -> str | None:
    """The unit price against the list price, as words the model can quote as is: "74.52% below list",
    "12% above list", "at list", "no charge" (unit price 0). None without a list price. A bare percent in an
    answer left the reader guessing what it measured (owner, 11 Nov), so the tool never hands one out."""
    if not listed:
        return None
    listed = Decimal(listed)
    unit = Decimal(unit or 0)
    if not unit:  # "100% below list" read as a discount; a line at 0 is given away (owner, 14 Nov)
        return "no charge"
    pct = round(abs(listed - unit) / listed * 100, 2)
    if not pct:  # equal, or a difference that rounds to 0.00
        return "at list"
    shown = f"{pct:.2f}".rstrip("0").rstrip(".")  # 74.52, 10, 12.5
    return f"{shown}% {'below' if unit < listed else 'above'} list"


def _line(row: Any) -> dict[str, Any]:
    listed = row.list_price_snapshot
    unit = Decimal(row.unit_price or 0)
    return {
        "code": row.product_code_snapshot,
        "description": svc.line_text(row),  # plain text, never the stored rich-text markup
        "qty": _num(row.quantity),
        "uom": row.uom,
        "list_price": _num(listed),
        "unit_price": _num(unit),
        "vs_list": vs_list(listed, unit),
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
    prepared_by = prepared_by_names(db, documents)  # the document's creator, never the project owner
    out: list[dict] = []
    matched: set[str] = set()

    def current_doc(doc: Any) -> dict:
        rows = [current[s.id] for s in scopes if s.document_id == doc.id]
        built = [_scope(r["scope_label"], r["current_version_no"], r["current_version_id"], r["current_total"]) for r in rows]
        return {
            "ref": doc.document_no, "document_no": doc.document_no, "revision": None,
            "prepared_by": prepared_by[doc.id], "total": round(sum(s["total"] for s in built), 2), "scopes": built,
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
            "prepared_by": prepared_by[doc.id], "total": _num(issue.grand_total) or 0.0, "scopes": built,
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
    for doc in out:
        _facts(doc)
    data: dict[str, Any] = {"documents": out, "not_found": not_found, "total_lines": sum(d["line_count"] for d in out)}
    if len(out) > 1:
        data["comparison"] = _compare(out)  # from every line, before `_fit` cuts any
    return data, _fit(data, cap)


def _doc_lines(doc: dict) -> list[dict]:
    return [ln for s in doc["scopes"] for ln in s["lines"]]


def _facts(doc: dict) -> None:
    """What a reader checks first in one document, computed so the model never counts."""
    lines = _doc_lines(doc)
    codes = [ln["code"] for ln in lines if ln["code"]]
    doc["line_count"] = len(lines)
    doc["no_charge_lines"] = list(dict.fromkeys(
        ln["code"] for ln in lines
        if ln["code"] and not ln["unit_price"] and (ln["qty"] or 0) > 0 and not ln["rate_only"]
    ))
    doc["repeated_codes"] = [
        {"code": c, "times": codes.count(c)} for c in dict.fromkeys(codes) if codes.count(c) > 1
    ]
    doc["rate_only_lines"] = sum(1 for ln in lines if ln["rate_only"])
    doc["empty"] = not doc["scopes"]


def _capped(block: dict, name: str, entries: list) -> None:
    block[name] = entries[:COMPARE_CAP]
    if len(entries) > COMPARE_CAP:
        block[f"{name}_not_shown"] = len(entries) - COMPARE_CAP


def _compare(docs: list[dict]) -> dict:
    """The differences between two or more documents (UAC C1 to C6): every figure the answer needs is here,
    so the model compares without arithmetic."""
    refs = [d["ref"] for d in docs]
    ranked = sorted(docs, key=lambda d: d["total"])  # stable: a tie keeps document order
    low = ranked[0]["total"]
    block: dict[str, Any] = {
        "totals": [{"ref": d["ref"], "total": d["total"], "gap_to_lowest": round(d["total"] - low, 2)} for d in ranked],
        "lowest": ranked[0]["ref"],
        "highest": ranked[-1]["ref"],
    }

    by_code: dict[str, dict[str, list[dict]]] = {}  # code -> ref -> its lines, both in first-seen order
    by_scope: dict[str, dict[str, float]] = {}  # scope label -> ref -> total
    for d in docs:
        for s in d["scopes"]:
            totals = by_scope.setdefault(s["scope"], {})
            totals[d["ref"]] = round(totals.get(d["ref"], 0.0) + s["total"], 2)
        for ln in _doc_lines(d):
            if ln["code"]:
                by_code.setdefault(ln["code"], {}).setdefault(d["ref"], []).append(ln)

    def only_in(groups: dict[str, dict], key: str) -> list[dict]:
        return [{key: k, "refs": [r for r in refs if r in v]} for k, v in groups.items() if len(v) < len(refs)]

    shared = []
    for code, per_ref in by_code.items():
        if len(per_ref) < 2:
            continue
        rows = [{
            "ref": ref,
            "qty": round(sum(ln["qty"] or 0 for ln in lines), 4),
            "unit_prices": sorted({ln["unit_price"] for ln in lines}),
            "line_total": round(sum(ln["line_total"] or 0 for ln in lines), 2),
        } for ref, lines in ((r, per_ref[r]) for r in refs if r in per_ref)]
        same_uom = len({(ln["uom"] or "").strip().lower() for lines in per_ref.values() for ln in lines}) == 1
        mins = [row["unit_prices"][0] for row in rows]
        cheapest = rows[mins.index(min(mins))]["ref"] if same_uom and len(set(mins)) > 1 else None
        totals = [row["line_total"] for row in rows]
        shared.append({
            "code": code, "docs": rows, "cheapest": cheapest,
            "unit_price_gap": round(max(mins) - min(mins), 2) if same_uom else None,
            "line_total_gap": round(max(totals) - min(totals), 2), "same_uom": same_uom,
        })
    shared.sort(key=lambda e: -e["line_total_gap"])  # stable: a tie keeps first-seen order

    _capped(block, "only_in", only_in(by_code, "code"))
    _capped(block, "shared", shared)
    _capped(block, "scopes_only_in", only_in(by_scope, "scope"))
    _capped(block, "scope_totals", [
        {"scope": label, "totals": [{"ref": r, "total": v[r]} for r in refs if r in v]}
        for label, v in by_scope.items() if len(v) > 1
    ])
    return block


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
