"""QUOTE-AUTOSAVE: a proposal / quotation form's draft and its History.

The tag designer's split (``api/v1/dealer_kit/price_tag_requests.py:1359`` / ``:1395``), applied to
the quotation form, with the owner's answers of 10 Nov 2026 (plan
``documentation/plans/project-sales/PLAN-quote-autosave-10nov.md``):

- **Autosave** overwrites the draft in place (``save_draft``). It never touches the record, so
  nothing a Save fires (the floor-breach alert to management, guardrails, audit of every rewritten
  line) runs per keystroke burst.
- **A new proposal** (card Q2) has a PRIVATE draft, one per person per project, and no number: the
  record is created by its first Save, which adopts the draft (``adopt_new_draft``).
- **Save** is today's POST / PATCH. With the form's state it writes a ``saved`` History entry and
  clears the draft in the record's own commit (``record_save``).
- **History** follows the tag designer exactly (card Q3): an entry per Save; Restore first keeps
  the state being left as "Before restore to version N" (the draft, else the latest Save), then
  puts the entry into the draft (``restore_entry``, cf. ``price_tag_requests.py:941-997``).
- **One writer** (card Q4): every open of the form claims the draft with a fresh token
  (``open_draft``). Only the holder may write; a write from the tab opened earlier is refused with
  409 ``quotation_draft_not_holder``, and what it carried is kept as a ``conflict`` entry first,
  so the older tab's typing is never lost while it goes view-only.
- **Discard draft** (card Q5) is a 5 s server-deferred record action (``record_actions``), which
  clears the draft; nothing reaches History.

The draft's shape is the form's own (``QuotationFormClient.tsx``); this module reads only the keys
it must reconcile against the record and stores everything else as given.
"""
from __future__ import annotations

import copy
import json
import secrets
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

#: The cap only stops a runaway client filling a row (and every History entry copied from it).
MAX_DRAFT_BYTES = 2_000_000

KIND_SAVED = "saved"
KIND_BEFORE_RESTORE = "before_restore"
KIND_CONFLICT = "conflict"


def _now() -> datetime:
    return datetime.utcnow()


def _check_size(doc: Any) -> None:
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


def user_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    from app.models.user import User

    user = db.query(User).filter(User.id == user_id).first()
    return user.name if user else None


# ------------------------------------------------------------------ rows


def document_draft(
    db: Session, document: ProjectQuotationDocument, *, create: bool = False, lock: bool = False
) -> Optional[QuotationDocumentDraft]:
    query = db.query(QuotationDocumentDraft).filter(
        QuotationDocumentDraft.document_id == document.id
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None and create:
        row = QuotationDocumentDraft(project_id=document.project_id, document_id=document.id)
        db.add(row)
        db.flush()
    return row


def new_draft(
    db: Session, project_id: str, user_id: str, *, create: bool = False, lock: bool = False
) -> Optional[QuotationDocumentDraft]:
    """The caller's OWN new-proposal draft on this project (card Q2). Never anyone else's."""
    query = db.query(QuotationDocumentDraft).filter(
        QuotationDocumentDraft.project_id == project_id,
        QuotationDocumentDraft.document_id.is_(None),
        QuotationDocumentDraft.owner_user_id == str(user_id),
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None and create:
        row = QuotationDocumentDraft(project_id=project_id, owner_user_id=str(user_id))
        db.add(row)
        db.flush()
    return row


def _document_of(db: Session, row: QuotationDocumentDraft) -> Optional[ProjectQuotationDocument]:
    if not row.document_id:
        return None
    return (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.id == row.document_id)
        .first()
    )


def _assert_writable(db: Session, row: QuotationDocumentDraft) -> None:
    """A document an approval holds refuses its draft too (card rule 6): the same 422 its own edits
    answer, so a stale tab cannot keep a draft growing behind the lock."""
    document = _document_of(db, row)
    if document is not None:
        from app.services import project_quotation_approval_service as approvals

        approvals.assert_unlocked(db, document)


def _not_holder(db: Session, row: QuotationDocumentDraft, doc: Any, user_id: str) -> AppException:
    """Keep the refused tab's state as History, then refuse it (card Q4)."""
    if isinstance(doc, dict):
        db.add(
            QuotationDocumentSnapshot(
                document_id=row.document_id,
                draft_id=row.id,
                kind=KIND_CONFLICT,
                note="Not saved: opened in another tab",
                doc=doc,
                grand_total=draft_total(doc),
                created_by=user_id,
            )
        )
        db.flush()
    return AppException(
        status_code=409,
        message="This draft was opened in another tab. This one is view only now; reload to edit.",
        code="quotation_draft_not_holder",
        details=_holder(db, row),
    )


def _holder(db: Session, row: QuotationDocumentDraft) -> Dict[str, Any]:
    return {
        "holder_name": user_name(db, row.holder_by),
        "holder_at": row.holder_at.isoformat() if row.holder_at else None,
    }


def assert_holder(
    db: Session, row: Optional[QuotationDocumentDraft], token: Optional[str], user_id: str,
    doc: Any = None,
) -> None:
    """Only the tab holding the draft writes. A row nobody has claimed yet accepts any writer."""
    if row is None or not row.holder_token:
        return
    if not token or not secrets.compare_digest(str(token), str(row.holder_token)):
        raise _not_holder(db, row, doc, user_id)


# ------------------------------------------------------------------ reading


def open_draft(db: Session, row: QuotationDocumentDraft, user_id: str) -> Dict[str, Any]:
    """Open the form: claim the draft for this tab (card Q4) and hand back what to open on."""
    row.holder_token = secrets.token_urlsafe(24)
    row.holder_by = str(user_id)
    row.holder_at = _now()
    db.flush()
    document = _document_of(db, row)
    doc = row.doc
    if doc is not None and document is not None:
        doc = reconcile(db, document, copy.deepcopy(doc))
    return {
        "draft_id": str(row.id),
        "token": row.holder_token,
        "doc": doc,
        "updated_at": row.updated_at if row.doc is not None else None,
        "updated_by_name": user_name(db, row.updated_by) if row.doc is not None else None,
    }


def holder_state(db: Session, row: Optional[QuotationDocumentDraft], token: str) -> Dict[str, Any]:
    """Whether this tab still holds the draft, and if not, who took it and when."""
    is_holder = row is None or not row.holder_token or (
        bool(token) and secrets.compare_digest(str(token), str(row.holder_token))
    )
    return {"is_holder": is_holder, **(_holder(db, row) if row is not None else {})}


def draft_summary(db: Session, document: ProjectQuotationDocument) -> Dict[str, Any]:
    """The three fields the document response carries for the read page's draft strip."""
    row = document_draft(db, document)
    has = row is not None and row.doc is not None
    return {
        "has_form_draft": has,
        "form_draft_at": row.updated_at if has else None,
        "form_draft_by_name": user_name(db, row.updated_by) if has else None,
    }


def assert_no_pending_draft(db: Session, document: ProjectQuotationDocument) -> None:
    """Issue and Request approval refuse while a draft is unsaved (card rule 7): otherwise the
    customer, or the approver, gets a revision missing edits that are sitting in the draft."""
    row = document_draft(db, document)
    if row is not None and row.doc is not None:
        raise AppException(
            status_code=409,
            message="Save or discard the draft first.",
            code="quotation_draft_pending",
        )


# ------------------------------------------------------------------ writing


def save_draft(
    db: Session, *, row: QuotationDocumentDraft, doc: Dict[str, Any], token: str, user_id: str
) -> Dict[str, Any]:
    """Autosave: overwrite the draft in place. Never History, never the record."""
    _check_size(doc)
    _assert_writable(db, row)
    assert_holder(db, row, token, user_id, doc)
    row.doc = doc
    row.updated_by = str(user_id)
    row.updated_at = _now()
    db.flush()
    return {"updated_at": row.updated_at}


def discard_draft(db: Session, row: QuotationDocumentDraft) -> None:
    """Discard draft (card Q5), committed by the 5 s pending action: the form goes back to the
    last Save. The countdown is the way back, as for every reversible record action."""
    row.doc = None
    row.updated_at = _now()
    db.flush()


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
    Save the server refuses writes no History and keeps the draft.
    """
    _check_size(form_state)
    row = document_draft(db, document, create=True)
    entry = QuotationDocumentSnapshot(
        document_id=document.id,
        draft_id=row.id,
        kind=KIND_SAVED,
        doc=form_state,
        grand_total=grand_total if grand_total is not None else draft_total(form_state),
        created_by=str(user_id),
    )
    db.add(entry)
    row.doc = None
    row.updated_by = str(user_id)
    row.updated_at = _now()
    db.flush()
    return entry


def adopt_new_draft(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    user_id: str,
    token: Optional[str],
) -> None:
    """A new proposal's first Save (card Q2): its private draft becomes the new document's draft,
    and any History made while it had no number moves onto the document."""
    row = new_draft(db, document.project_id, user_id, lock=True)
    if row is None:
        return
    assert_holder(db, row, token, user_id)
    db.query(QuotationDocumentSnapshot).filter(
        QuotationDocumentSnapshot.draft_id == row.id,
        QuotationDocumentSnapshot.document_id.is_(None),
    ).update({QuotationDocumentSnapshot.document_id: document.id}, synchronize_session=False)
    row.document_id = document.id
    row.owner_user_id = None
    db.flush()


# ------------------------------------------------------------------ history


def _entries(db: Session, document: ProjectQuotationDocument) -> List[QuotationDocumentSnapshot]:
    return (
        db.query(QuotationDocumentSnapshot)
        .filter(QuotationDocumentSnapshot.document_id == document.id)
        .order_by(QuotationDocumentSnapshot.created_at.asc(), QuotationDocumentSnapshot.id.asc())
        .all()
    )


def _serialize_entry(db: Session, row, version: int, names: Dict[str, Optional[str]]) -> Dict[str, Any]:
    if row.created_by and row.created_by not in names:
        names[row.created_by] = user_name(db, row.created_by)
    return {
        "id": str(row.id),
        "version": version,
        "kind": row.kind,
        "note": row.note,
        "grand_total": row.grand_total,
        "created_at": row.created_at,
        "created_by_name": names.get(row.created_by) if row.created_by else None,
    }


def list_history(db: Session, document: ProjectQuotationDocument) -> List[Dict[str, Any]]:
    """Newest first, numbered oldest = 1, the tag designer's "Version N"."""
    names: Dict[str, Optional[str]] = {}
    rows = _entries(db, document)
    out = [_serialize_entry(db, row, index + 1, names) for index, row in enumerate(rows)]
    return list(reversed(out))


def _entry_or_404(db: Session, document, entry_id: str):
    rows = _entries(db, document)
    for index, row in enumerate(rows):
        # Checked against THIS document, so a known entry id cannot be read through another one.
        if str(row.id) == str(entry_id):
            return row, index + 1, rows
    raise AppException(
        status_code=404, message="History entry not found.", code="quotation_history_not_found"
    )


def get_history_entry(db: Session, document, entry_id: str) -> Dict[str, Any]:
    row, version, _ = _entry_or_404(db, document, entry_id)
    return {**_serialize_entry(db, row, version, {}), "doc": row.doc}


def restore_entry(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    entry_id: str,
    token: str,
    user_id: str,
) -> Dict[str, Any]:
    """Restore, the tag designer's way (``price_tag_requests.py:941-997``): the state being LEFT is
    kept first ("Before restore to version N": the draft, else the latest Save), then the entry
    becomes the draft. No confirm: nothing is destroyed. The record changes only on the next Save.
    """
    entry, version, rows = _entry_or_404(db, document, entry_id)
    row = document_draft(db, document, create=True, lock=True)
    _assert_writable(db, row)
    assert_holder(db, row, token, user_id)
    leaving = row.doc
    if leaving is None:
        saved = [r for r in rows if r.kind == KIND_SAVED]
        leaving = saved[-1].doc if saved else None
    if leaving is not None:
        db.add(
            QuotationDocumentSnapshot(
                document_id=document.id,
                draft_id=row.id,
                kind=KIND_BEFORE_RESTORE,
                note=f"Before restore to version {version}",
                doc=leaving,
                grand_total=draft_total(leaving),
                created_by=str(user_id),
            )
        )
    restored = reconcile(db, document, copy.deepcopy(entry.doc))
    row.doc = restored
    row.updated_by = str(user_id)
    row.updated_at = _now()
    db.flush()
    return {
        "draft_id": str(row.id),
        "token": row.holder_token,
        "doc": restored,
        "updated_at": row.updated_at,
        "updated_by_name": user_name(db, user_id),
    }


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
