"""QUOTE-AUTOSAVE: a proposal / quotation form's draft and its History.

The tag designer's split (``api/v1/dealer_kit/price_tag_requests.py:1359`` / ``:1395``), applied to
the quotation form:

- **Autosave** overwrites the document's draft in place (``save_draft``). It never touches the
  record, so nothing a Save fires (the floor-breach alert to management, guardrails, audit of every
  rewritten line) runs per keystroke burst.
- **Save** is today's POST / PATCH. When it carries the form's state, ``record_save`` writes a
  ``saved`` History entry from it and clears the draft, in the same commit.
- **History** is insert-only (``QuotationDocumentSnapshot``). Restore loads an entry into the
  draft and keeps the draft it replaced as a ``before_restore`` entry, so it never destroys work.

The draft's shape is the form's own (``QuotationFormClient.tsx``); this module reads only the few
keys it must reconcile against the record (``scopes[].id``, ``staged[key].versionId`` and the
staged lines' ``id`` / ``line``) and stores everything else as given.

Concurrency: every write names the draft revision it was built on (``base_rev``). A stale one is
refused with 409 ``quotation_draft_stale``, and its document is kept as a ``conflict`` History
entry first, so the refused tab's typing survives (owner card Q4).
"""
from __future__ import annotations

import copy
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.projects import (
    ProjectQuotation,
    ProjectQuotationDocument,
    ProjectQuotationLine,
    QuotationDocumentDraft,
    QuotationDocumentSnapshot,
)
from app.services.error_handler import AppException

#: A draft is the form's state as JSON. The biggest real proposal measured is far under this; the
#: cap only stops a runaway client filling a row (and every History entry copied from it).
MAX_DRAFT_BYTES = 2_000_000

KIND_SAVED = "saved"
KIND_BEFORE_RESTORE = "before_restore"
KIND_CONFLICT = "conflict"


def _now() -> datetime:
    return datetime.utcnow()


def _check_size(doc: Dict[str, Any]) -> None:
    if not isinstance(doc, dict):
        raise AppException(
            status_code=422, message="The draft must be an object.", code="quotation_draft_invalid"
        )
    if len(json.dumps(doc, default=str)) > MAX_DRAFT_BYTES:
        raise AppException(
            status_code=413,
            message="This draft is too large to save.",
            code="quotation_draft_too_large",
        )


def _row(db: Session, document: ProjectQuotationDocument, *, lock: bool = False):
    query = db.query(QuotationDocumentDraft).filter(
        QuotationDocumentDraft.document_id == document.id
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def _row_or_new(db: Session, document: ProjectQuotationDocument) -> QuotationDocumentDraft:
    row = _row(db, document, lock=True)
    if row is None:
        row = QuotationDocumentDraft(document_id=document.id, rev=0, doc=None)
        db.add(row)
        db.flush()
    return row


def user_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    from app.models.user import User

    user = db.query(User).filter(User.id == user_id).first()
    return user.name if user else None


def _assert_writable(db: Session, document: ProjectQuotationDocument) -> None:
    """A document an approval holds refuses its draft too (card rule 6).

    The same 422 the record's own edits answer (``assert_unlocked``), so a stale tab on a locked
    document cannot keep a draft growing behind the lock.
    """
    from app.services import project_quotation_approval_service as approvals

    approvals.assert_unlocked(db, document)


def _stale(db: Session, document, row, doc, user_id) -> AppException:
    """Keep the refused tab's state as History, then refuse it (card Q4)."""
    if isinstance(doc, dict):
        db.add(
            QuotationDocumentSnapshot(
                document_id=document.id,
                kind=KIND_CONFLICT,
                doc=doc,
                grand_total=draft_total(doc),
                created_by=user_id,
            )
        )
        db.flush()
    return AppException(
        status_code=409,
        message="This draft was changed in another tab or by someone else. Reload to continue.",
        code="quotation_draft_stale",
        details={
            "rev": row.rev if row is not None else 0,
            "updated_at": row.updated_at.isoformat() if row is not None and row.updated_at else None,
            "updated_by_name": user_name(db, row.updated_by) if row is not None else None,
        },
    )


# ------------------------------------------------------------------ reading


def draft_state(db: Session, document: ProjectQuotationDocument) -> Dict[str, Any]:
    """The draft as the form opens it: reconciled against the record, plus who and when."""
    row = _row(db, document)
    doc = row.doc if row is not None else None
    return {
        "doc": reconcile(db, document, doc) if doc is not None else None,
        "rev": row.rev if row is not None else 0,
        "updated_at": row.updated_at if row is not None and doc is not None else None,
        "updated_by_name": (
            user_name(db, row.updated_by) if row is not None and doc is not None else None
        ),
    }


def draft_summary(db: Session, document: ProjectQuotationDocument) -> Dict[str, Any]:
    """The three fields the document response carries for the read page's draft strip."""
    row = _row(db, document)
    has = row is not None and row.doc is not None
    return {
        "has_form_draft": has,
        "form_draft_at": row.updated_at if has else None,
        "form_draft_by_name": user_name(db, row.updated_by) if has else None,
    }


def has_pending_draft(db: Session, document: ProjectQuotationDocument) -> bool:
    row = _row(db, document)
    return row is not None and row.doc is not None


def assert_no_pending_draft(db: Session, document: ProjectQuotationDocument) -> None:
    """Issue and Request approval refuse while a draft is unsaved (card rule 7).

    Otherwise the customer, or the approver, would get a revision missing edits that are sitting
    in the draft.
    """
    if has_pending_draft(db, document):
        raise AppException(
            status_code=409,
            message="Save or discard the draft first.",
            code="quotation_draft_pending",
        )


# ------------------------------------------------------------------ writing


def save_draft(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    doc: Dict[str, Any],
    base_rev: int,
    user_id: str,
) -> Dict[str, Any]:
    """Autosave: overwrite the draft in place. Never writes History, never touches the record."""
    _check_size(doc)
    _assert_writable(db, document)
    row = _row_or_new(db, document)
    if int(base_rev) != int(row.rev or 0):
        raise _stale(db, document, row, doc, user_id)
    row.doc = doc
    row.rev = int(row.rev or 0) + 1
    row.updated_by = user_id
    row.updated_at = _now()
    db.flush()
    return {"rev": row.rev, "updated_at": row.updated_at}


def discard_draft(
    db: Session, *, document: ProjectQuotationDocument, base_rev: Optional[int], user_id: str
) -> Dict[str, Any]:
    """Discard draft (card Q5): the form goes back to the last Save. Nothing is written to History
    because nothing is lost that was ever Saved; the countdown on the button is the way back."""
    row = _row_or_new(db, document)
    if base_rev is not None and int(base_rev) != int(row.rev or 0):
        raise _stale(db, document, row, None, user_id)
    row.doc = None
    row.rev = int(row.rev or 0) + 1
    row.updated_by = user_id
    row.updated_at = _now()
    db.flush()
    return {"rev": row.rev}


def record_save(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    form_state: Dict[str, Any],
    user_id: str,
    grand_total: Optional[Decimal] = None,
) -> QuotationDocumentSnapshot:
    """Save: a ``saved`` History entry from the form's state, and the draft cleared.

    Called by the POST / PATCH routes inside their own transaction, after the record write, so a
    Save the server refuses (an issued line, a locked document) writes no History and keeps the
    draft.
    """
    _check_size(form_state)
    entry = QuotationDocumentSnapshot(
        document_id=document.id,
        kind=KIND_SAVED,
        doc=form_state,
        grand_total=grand_total if grand_total is not None else draft_total(form_state),
        created_by=user_id,
    )
    db.add(entry)
    row = _row_or_new(db, document)
    row.doc = None
    row.rev = int(row.rev or 0) + 1
    row.updated_by = user_id
    row.updated_at = _now()
    db.flush()
    return entry


def seed_draft(
    db: Session, *, document: ProjectQuotationDocument, doc: Dict[str, Any], user_id: str
) -> Dict[str, Any]:
    """A new proposal's first real edit (card Q2): the record is created and its draft written in
    the same commit, so the number and the typing land together."""
    _check_size(doc)
    row = _row_or_new(db, document)
    row.doc = doc
    row.rev = int(row.rev or 0) + 1
    row.updated_by = user_id
    row.updated_at = _now()
    db.flush()
    return {"rev": row.rev, "updated_at": row.updated_at}


# ------------------------------------------------------------------ history


def list_history(db: Session, document: ProjectQuotationDocument) -> List[Dict[str, Any]]:
    rows = (
        db.query(QuotationDocumentSnapshot)
        .filter(QuotationDocumentSnapshot.document_id == document.id)
        .order_by(QuotationDocumentSnapshot.created_at.desc(), QuotationDocumentSnapshot.id.desc())
        .all()
    )
    names: Dict[str, Optional[str]] = {}
    out = []
    for row in rows:
        if row.created_by and row.created_by not in names:
            names[row.created_by] = user_name(db, row.created_by)
        out.append(
            {
                "id": str(row.id),
                "kind": row.kind,
                "grand_total": row.grand_total,
                "created_at": row.created_at,
                "created_by_name": names.get(row.created_by) if row.created_by else None,
            }
        )
    return out


def _entry_or_404(db: Session, document, entry_id: str) -> QuotationDocumentSnapshot:
    row = (
        db.query(QuotationDocumentSnapshot)
        .filter(
            QuotationDocumentSnapshot.id == entry_id,
            # Checked against THIS document, so a known entry id cannot be read through any
            # other document the caller can open.
            QuotationDocumentSnapshot.document_id == document.id,
        )
        .first()
    )
    if row is None:
        raise AppException(
            status_code=404, message="History entry not found.", code="quotation_history_not_found"
        )
    return row


def get_history_entry(db: Session, document, entry_id: str) -> Dict[str, Any]:
    row = _entry_or_404(db, document, entry_id)
    return {
        "id": str(row.id),
        "kind": row.kind,
        "grand_total": row.grand_total,
        "created_at": row.created_at,
        "created_by_name": user_name(db, row.created_by),
        "doc": row.doc,
    }


def restore_entry(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    entry_id: str,
    base_rev: int,
    user_id: str,
) -> Dict[str, Any]:
    """Restore: the entry becomes the draft; the draft it replaces becomes ``before_restore``.

    No confirm (the History sheet's rule): nothing is destroyed. The record changes only on the
    next Save, which fires everything a Save fires.
    """
    entry = _entry_or_404(db, document, entry_id)
    _assert_writable(db, document)
    row = _row_or_new(db, document)
    if int(base_rev) != int(row.rev or 0):
        raise _stale(db, document, row, None, user_id)
    if row.doc is not None:
        db.add(
            QuotationDocumentSnapshot(
                document_id=document.id,
                kind=KIND_BEFORE_RESTORE,
                doc=row.doc,
                grand_total=draft_total(row.doc),
                created_by=user_id,
            )
        )
    restored = reconcile(db, document, copy.deepcopy(entry.doc))
    row.doc = restored
    row.rev = int(row.rev or 0) + 1
    row.updated_by = user_id
    row.updated_at = _now()
    db.flush()
    return {"doc": restored, "rev": row.rev, "updated_at": row.updated_at}


# ------------------------------------------------------------------ the draft's figures


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def draft_total(doc: Any) -> Optional[Decimal]:
    """What the History list shows beside an entry that is not a Save: the form's own live total
    (``total``, the figure its header shows), or None when it carried none. A display figure only;
    a ``saved`` entry takes the record's real grand total instead (``record_save``)."""
    if not isinstance(doc, dict):
        return None
    value = _decimal(doc.get("total"))
    return value.quantize(Decimal("0.01")) if value is not None else None


# ------------------------------------------------------------------ reconcile


def reconcile(db: Session, document: ProjectQuotationDocument, doc: Any) -> Any:
    """Make a stored draft or History entry safe to Save against the record AS IT IS NOW.

    A draft can be older than the record: someone Saved, revised or removed a scope since. The
    form's Save sends a saved scope's lines by id, and an id the scope's current version does not
    hold is refused (``replace_lines``, 404 ``quotation_line_not_found``), so without this a
    restored entry could never be saved. Rules:

    - a scope whose id no longer belongs to this document becomes a NEW scope (id null), its lines
      all new;
    - a scope whose current version moved since the draft was staged takes the current version id,
      and keeps line ids only where that version still holds the line; the others become new lines;
    - a reconciled scope's ``seeded`` set is emptied, so the form treats its lines as changed and
      Save sends them.

    Everything else in the draft is returned untouched.
    """
    if not isinstance(doc, dict):
        return doc
    scopes = doc.get("scopes")
    staged = doc.get("staged")
    if not isinstance(scopes, list):
        return doc

    live_scope_ids = {
        str(row.id)
        for row in db.query(ProjectQuotation.id)
        .filter(ProjectQuotation.document_id == document.id)
        .all()
    }
    from app.services import project_quotation_service as quotes

    current_version: Dict[str, Optional[str]] = {}
    for scope_id in live_scope_ids:
        try:
            current_version[scope_id] = str(quotes.current_version(db, scope_id).id)
        except AppException:
            current_version[scope_id] = None

    def line_ids(version_id: Optional[str]) -> set:
        if not version_id:
            return set()
        return {
            str(row.id)
            for row in db.query(ProjectQuotationLine.id)
            .filter(ProjectQuotationLine.version_id == version_id)
            .all()
        }

    def as_new(held: Dict[str, Any], keep: set, version_id: Optional[str]) -> Dict[str, Any]:
        lines = []
        for line in held.get("lines") or []:
            if not isinstance(line, dict):
                continue
            line = dict(line)
            if not line.get("id") or str(line["id"]) not in keep:
                line["id"] = None
                line["line"] = None
            lines.append(line)
        return {**held, "versionId": version_id or "", "seeded": [], "lines": lines}

    removed = set(str(x) for x in (doc.get("removedIds") or []))
    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        scope_id = str(scope["id"]) if scope.get("id") else None
        key = scope.get("key")
        held = staged.get(key) if isinstance(staged, dict) and key else None
        if scope_id and scope_id not in live_scope_ids:
            scope["id"] = None
            if isinstance(held, dict):
                staged[key] = as_new(held, set(), None)
            continue
        if scope_id and isinstance(held, dict):
            version_id = current_version.get(scope_id)
            if held.get("versionId") != version_id:
                staged[key] = as_new(held, line_ids(version_id), version_id)
    # A removal of a scope that is already gone is no removal.
    if removed:
        doc["removedIds"] = [x for x in doc.get("removedIds") or [] if str(x) in live_scope_ids]
    return doc
