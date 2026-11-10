"""The quotation DOCUMENT: one letterhead carrying several priced scopes.

Sits above ``project_quotation_service``, which keeps owning a scope and its version chain. The
split matters: a scope carries no outcome (the project has the one Won/Lost outcome), and the
only outcome this module writes is a customer acceptance winning an open project.

Three rules are enforced here rather than left to callers, because each has already been got
wrong once somewhere in this codebase:

1. **Rate-only lines contribute zero to every total.** Scope total, grand total and the issue's
   snapshotted total all come from ONE function. Three call sites computing the same sum is how
   a quotation ends up disagreeing with its own PDF.
2. **The recipient block is snapshotted at create.** Read live, a party address edited next year
   silently rewrites what was sent last year.
3. **Issuing freezes.** An issue records the exact version each scope contributed, and
   ``project_quotation_service.is_frozen`` treats "an issue points at this version" as freezing
   it, so the rows an issue claims to hold cannot be rewritten under it.
"""
from __future__ import annotations

import copy
import logging
import re
import secrets
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.base import company_scope, set_company_scope
from app.models.numbering import DocumentNumberingRule
from app.models.projects import (
    Project,
    ProjectParty,
    ProjectQuotation,
    ProjectQuotationDocument,
    ProjectQuotationIssue,
    ProjectQuotationIssueScope,
    ProjectQuotationLine,
    ProjectQuotationVersion,
    QuotationSignature,
)
from app.services import quotation_form_draft_service as _form_drafts
from app.services import project_quotation_approval_service as approvals
from app.services import project_quotation_image_service as quotation_images
from app.services import project_quotation_service as scope_service
from app.services import quotation_view_service as _views
from app.services.error_handler import AppException
from app.services.quotation_cover_service import (
    COVER_LAYOUT,
    COVER_LAYOUT_DESIGNED,
    cover_payload,
    cover_reference,
    cover_rows,
    sender_of,
    default_design,
    design_of,
    layout_of,
)
from app.services.numbering_service import NumberingService

logger = logging.getLogger(__name__)

QUOTATION_DOC_TYPE = "project_quotation"
# PS-PROPOSAL-QUOTATION: the quotation a won project converts one proposal revision into has its
# own running number, so a customer can tell the two apart from the reference alone.
SALES_QUOTATION_DOC_TYPE = "project_sales_quotation"
KIND_PROPOSAL = "proposal"
KIND_QUOTATION = "quotation"

ZERO = Decimal("0.00")


# ------------------------------------------------------------------ money


def line_amount(line: ProjectQuotationLine) -> Decimal:
    """What a line adds to its scope. A rate-only line adds NOTHING.

    The sample quotation carries five rate-only alternates; adding them would have overstated it
    by more than RM 235,000. `line_total` is still stored and still printed, because the customer
    is being shown a rate - it just does not count.
    """
    if line.is_rate_only:
        return ZERO
    return Decimal(line.line_total or 0)


def scope_total(db: Session, quotation: ProjectQuotation) -> Decimal:
    """The current version's priced total for one scope."""
    version = (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.quotation_id == quotation.id)
        .order_by(ProjectQuotationVersion.version_no.desc())
        .first()
    )
    if version is None:
        return ZERO
    return version_total(db, version)


def version_total(db: Session, version: ProjectQuotationVersion) -> Decimal:
    lines = (
        db.query(ProjectQuotationLine)
        .filter(ProjectQuotationLine.version_id == version.id)
        .all()
    )
    return sum((line_amount(line) for line in lines), ZERO)


def list_scopes(db: Session, document: ProjectQuotationDocument) -> List[ProjectQuotation]:
    return (
        db.query(ProjectQuotation)
        .filter(ProjectQuotation.document_id == document.id)
        .order_by(ProjectQuotation.sort_order, ProjectQuotation.created_at)
        .all()
    )


def document_total(db: Session, document: ProjectQuotationDocument) -> Decimal:
    """The sample workbook's TOTAL AMOUNT: every scope's current version, added up."""
    return sum((scope_total(db, scope) for scope in list_scopes(db, document)), ZERO)


def _item_number(line: ProjectQuotationLine, position: int) -> str:
    """The ITEM cell, defined once for every surface that prints a quotation."""
    from app.services.project_quotation_pdf_service import item_number

    return item_number(line, position)


def quotation_no(document_no: Optional[str], issue_no: int, label: Optional[str] = None) -> str:
    """The number every surface prints: `<document_no>-<label>`, e.g. PRJQ-2026-0003-B.

    Built, never read back from `our_ref_text`, so an issue stored with the old `(R1)` text still
    shows the same number on the sign page, the PDF, the workbook and the download name. With no
    stored label (a row the backfill has not reached) it is the legacy `R<issue_no>`.
    """
    return f"{document_no}-{label or f'R{issue_no}'}"


def issue_no_text(document_no: Optional[str], record: ProjectQuotationIssue) -> str:
    """`quotation_no` for a stored issue, reading its own label."""
    return quotation_no(document_no, record.issue_no, record.revision_label)


def revision_letter(n: int) -> str:
    """1 -> A ... 26 -> Z, 27 -> AA: the proposal revision letters (PS-PROPOSAL-QUOTATION)."""
    letters = ""
    while n > 0:
        n, rest = divmod(n - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def document_noun(document: Optional[ProjectQuotationDocument]) -> str:
    """"Proposal" or "Quotation": the word every surface prints for this document."""
    return "Quotation" if getattr(document, "kind", None) == KIND_QUOTATION else "Proposal"


_LEGACY_LABEL = re.compile(r"^R\d+$")


def _next_label(db: Session, document: ProjectQuotationDocument, issue_no: int) -> str:
    """A quotation counts R1, R2. A proposal counts A, B, C - unless it already went out as R1
    before this lane, in which case it keeps counting R so the customer's paper stays in order."""
    if document.kind == KIND_QUOTATION:
        return f"R{issue_no}"
    earlier = [
        row[0] or ""
        for row in db.query(ProjectQuotationIssue.revision_label)
        .filter(ProjectQuotationIssue.document_id == document.id)
        .all()
    ]
    if any(_LEGACY_LABEL.match(label) for label in earlier):
        return f"R{issue_no}"
    return revision_letter(issue_no)


# ------------------------------------------------------------------ create


def _next_document_no(
    db: Session, company_id: Optional[str], doc_type: str = QUOTATION_DOC_TYPE
) -> str:
    """From the running-number feature, so an admin can change the format without a deploy.

    Scoped to the company: a customer-facing series that two companies share is not a series.
    Falls back to a derived number only when no rule exists at all, because refusing to create a
    quotation because nobody configured a prefix would be a worse failure than an ugly reference.
    """
    number = NumberingService(db).get_next_number(
        doc_type, company_id=company_id, commit_rule=False
    )
    if number:
        return number

    kind = KIND_QUOTATION if doc_type == SALES_QUOTATION_DOC_TYPE else KIND_PROPOSAL
    highest = (
        db.query(func.count(ProjectQuotationDocument.id))
        .filter(
            ProjectQuotationDocument.company_id == company_id,
            ProjectQuotationDocument.kind == kind,
        )
        .scalar()
        or 0
    )
    prefix = "QT" if kind == KIND_QUOTATION else "Q"
    return f"{prefix}-{date.today().year}-{highest + 1:04d}"


def _recipient_from_project(db: Session, project: Project) -> Dict[str, Any]:
    """Everything knowable about who this goes to, taken once and kept.

    The journey's rule: a field derivable from something we already hold is derived, never asked.
    """
    party = None
    if project.developer_party_id:
        party = (
            db.query(ProjectParty).filter(ProjectParty.id == project.developer_party_id).first()
        )
    if party is None:
        return {
            "recipient_party_id": None,
            "recipient_name_snapshot": None,
            "recipient_address_snapshot": None,
            "recipient_phone_snapshot": None,
        }
    return {
        "recipient_party_id": party.id,
        "recipient_name_snapshot": party.name,
        "recipient_address_snapshot": party.address,
        "recipient_phone_snapshot": party.phone,
    }


#: The text fields whose {{merge fields}} are filled on every save.
TOKEN_FIELDS = ("cover_letter_html", "cover_closing_html", "terms_html")


def create_document(
    db: Session,
    *,
    project: Project,
    actor_user_id: str,
    payload: Optional[Dict[str, Any]] = None,
    render_templates: bool = True,
) -> ProjectQuotationDocument:
    """``render_templates=False`` leaves the letter to the caller, which renders it once the
    quotation's lines exist (the form's create, #1341), so ``{{grand_total}}`` is the real one."""
    payload = payload or {}
    document = ProjectQuotationDocument(
        company_id=project.company_id,
        project_id=project.id,
        document_no=payload.get("document_no") or _next_document_no(db, project.company_id),
        your_ref=payload.get("your_ref"),
        doc_date=payload.get("doc_date") or date.today(),
        attn_name=payload.get("attn_name"),
        recipient_email_snapshot=payload.get("recipient_email_snapshot"),
        quotation_purpose=payload.get("quotation_purpose"),
        payment_terms=payload.get("payment_terms"),
        validity=payload.get("validity"),
        subject_title=payload.get("subject_title") or project.title,
        cover_letter_html=payload.get("cover_letter_html"),
        cover_closing_html=payload.get("cover_closing_html"),
        terms_html=payload.get("terms_html"),
        signatory_name=payload.get("signatory_name"),
        signatory_phone=payload.get("signatory_phone"),
        created_by=actor_user_id,
        **_recipient_from_project(db, project),
    )
    db.add(document)
    db.flush()
    if render_templates:
        _render_templates_onto(db, document, payload)
    return document


def _render_templates_onto(
    db: Session, document: ProjectQuotationDocument, payload: Dict[str, Any]
) -> None:
    """Journey step 5: the letter is already written when the salesperson gets there (AC-E2).

    Rendered ONCE, into the document's own columns, AFTER the flush - the merge fields quote the
    document's own reference, date and recipient snapshot, so the row has to exist first.

    Never re-read at print time: an admin rewriting the company letter must not rewrite a
    quotation drafted last month, and must never touch one already issued (AC-B4 / AC-E3). A
    caller that supplied its own text has already decided, and rendering over it would discard
    what a person typed.
    """
    from app.services import project_quotation_template_service as templates

    # The active cover page design supplies the intro (into the letter column) and the closing;
    # with none active the old cover letter template stays the intro.
    design = templates.active_template(
        db, company_id=document.company_id, kind=templates.TEMPLATE_KIND_COVER_PAGE
    )
    context = templates.build_document_context(db, document=document) if design else None
    if design is not None:
        if not (payload.get("cover_closing_html") or "").strip():
            closing = (design.design or {}).get("closing_html")
            document.cover_closing_html = templates.render(closing, context) or None
        if not (payload.get("cover_letter_html") or "").strip():
            document.cover_letter_html = templates.render(design.body_html, context) or None
    for field, kind in (
        ("cover_letter_html", templates.TEMPLATE_KIND_COVER_LETTER),
        ("terms_html", templates.TEMPLATE_KIND_TERMS),
    ):
        if (payload.get(field) or "").strip():
            continue
        if field == "cover_letter_html" and design is not None:
            continue
        rendered = templates.render_for_document(db, document=document, kind=kind)
        if rendered is not None:
            setattr(document, field, rendered)
    db.flush()


def get_document(db: Session, document_id: str) -> Optional[ProjectQuotationDocument]:
    """By id alone, for callers that already know which document they hold."""
    return (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.id == document_id)
        .first()
    )


def get_document_or_404(
    db: Session, project_id: str, document_id: str
) -> ProjectQuotationDocument:
    document = (
        db.query(ProjectQuotationDocument)
        .filter(
            ProjectQuotationDocument.id == document_id,
            ProjectQuotationDocument.project_id == project_id,
        )
        .first()
    )
    if not document:
        raise AppException(
            status_code=404,
            message="Quotation not found.",
            code="quotation_document_not_found",
        )
    return document


def add_scope(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    scope_label: str,
    actor_user_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> ProjectQuotation:
    """A tab on the document, with its version 1 opened immediately.

    Delegates to the existing scope service so there is one definition of "a scope and its first
    version", then binds it to this document and puts it last in tab order.
    """
    approvals.assert_unlocked(db, document)
    project = db.query(Project).filter(Project.id == document.project_id).first()
    if project is None:
        raise AppException(
            status_code=404, message="Project not found.", code="project_not_found"
        )

    body = dict(payload or {})
    body["scope_label"] = scope_label

    # Tab order is decided BEFORE the insert, because `document_id` is NOT NULL and the row
    # cannot be written unattached and fixed up afterwards.
    highest = (
        db.query(func.max(ProjectQuotation.sort_order))
        .filter(ProjectQuotation.document_id == document.id)
        .scalar()
    )
    quotation = scope_service.create_quotation(
        db,
        project=project,
        actor_user_id=actor_user_id,
        payload=body,
        document_id=document.id,
    )
    quotation.sort_order = 0 if highest is None else int(highest) + 1
    db.flush()
    return quotation


# ------------------------------------------------------------------ the form's save (#1341)

_RECIPIENT_FIELDS = (
    "recipient_name_snapshot",
    "recipient_address_snapshot",
    "recipient_phone_snapshot",
)
_SCOPE_FIELDS = ("scope_label", "series_id", "notes")


def create_document_with_scopes(
    db: Session,
    *,
    project: Project,
    actor_user_id: str,
    payload: Dict[str, Any],
) -> Tuple[ProjectQuotationDocument, List[ProjectQuotationLine]]:
    """The quotation form's Save in create mode: letterhead, scopes and lines in one go.

    The owner's words: "I should be able to add product straight away and save when I am
    satisfied". So nothing exists until this runs, and it writes everything the page holds in the
    caller's ONE transaction: a line the server refuses raises before the route commits, and the
    rollback takes the document and every scope with it. No half quotation is ever left behind.

    Everything is written through the paths the rest of the module already uses - ``add_scope``
    for a scope and its version 1, ``replace_lines`` for the lines - so the snapshotting, the
    guardrails and the rate-only totals are the same rules, not a copy of them. A scope sent with
    no lines is saved with none: there is no placeholder line anywhere on this path.

    Returns the lines written so the route can raise below-floor notifications for them, exactly
    as the bulk line route does.
    """
    from app.services import project_quotation_template_service as _templates

    for field in TOKEN_FIELDS:
        _templates.assert_tokens_known(payload.get(field))
    body = dict(payload)
    scopes = body.pop("scopes", None) or []
    corrections = {field: body.pop(field, None) for field in _RECIPIENT_FIELDS}
    # The letter typed in the create form's own tabs (#1341, "show them on create as well"). Held
    # back from ``create_document`` so the company template renders there as it always did, and
    # the typed text replaces it once the scopes exist: its merge fields then quote the real
    # number and total, not the ones a half-made quotation would give.
    letter = {
        field: body.pop(field)
        for field in TOKEN_FIELDS
        if (body.get(field) or "").strip()
    }

    document = create_document(
        db, project=project, actor_user_id=actor_user_id, payload=body, render_templates=False
    )
    # A typed recipient CORRECTS the party snapshot (the result create-then-edit gave before); a
    # blank one keeps what the developer party says rather than blanking the letterhead.
    for field, value in corrections.items():
        if value is not None and str(value).strip():
            setattr(document, field, value)
    db.flush()

    written: List[ProjectQuotationLine] = []
    for item in scopes:
        written.extend(
            _add_form_scope(db, document=document, actor_user_id=actor_user_id, item=item)
        )
    # The letter, once the lines exist: typed text has its merge fields filled, and a blank tab
    # takes the company template, both against the real total rather than 0.00.
    db.flush()
    if letter:
        from app.services import project_quotation_template_service as templates

        context = templates.build_document_context(db, document=document)
        for field, text in letter.items():
            setattr(document, field, templates.render(text, context))
    _render_templates_onto(db, document, letter)
    return document, written


def letter_templates(db: Session, *, project: Project) -> Dict[str, Optional[str]]:
    """The company's active cover letter and terms, as written, for the create form (#1341).

    Unrendered on purpose: before Save there is no quotation number and no total, so a merge
    field rendered now would bake in a blank. The tokens are filled when the quotation is saved.
    """
    from app.services import project_quotation_template_service as templates

    out: Dict[str, Optional[str]] = {}
    design = templates.active_template(
        db, company_id=project.company_id, kind=templates.TEMPLATE_KIND_COVER_PAGE
    )
    out["cover_closing_html"] = (design.design or {}).get("closing_html") or None if design else None
    for field, kind in (
        ("cover_letter_html", templates.TEMPLATE_KIND_COVER_LETTER),
        ("terms_html", templates.TEMPLATE_KIND_TERMS),
    ):
        # An active cover page design supplies the intro in place of the old cover letter.
        template = templates.active_template(
            db,
            company_id=project.company_id,
            kind=templates.TEMPLATE_KIND_COVER_PAGE if field == "cover_letter_html" and design else kind,
        )
        out[field] = (template.body_html or None) if template is not None else None
        if kind == templates.TEMPLATE_KIND_TERMS:
            out["payment_terms"] = template.payment_terms if template is not None else None
            out["validity"] = template.validity if template is not None else None
    return out


def remove_form_scopes(
    db: Session, *, document: ProjectQuotationDocument, scope_ids: List[str]
) -> None:
    """Edit quotation deletes saved scopes (#1341, owner on Q2: "yes can").

    Only while nothing in the scope has been issued: ANY version of it in any issue, not only the
    open one, because the customer holds that paper and a revision opened since does not change
    that. Refused before anything is deleted, so one issued scope in the list stops them all.
    """
    approvals.assert_unlocked(db, document)
    scopes = [get_scope_or_404(db, document, str(scope_id)) for scope_id in scope_ids]
    for scope in scopes:
        issued = (
            db.query(ProjectQuotationIssueScope.id)
            .filter(ProjectQuotationIssueScope.quotation_id == scope.id)
            .first()
        )
        if issued is not None:
            raise AppException(
                status_code=422,
                message=(
                    f"{scope.scope_label} has been sent to the customer and cannot be removed "
                    "from this quotation."
                ),
                code="quotation_scope_issued",
            )
    for scope in scopes:
        scope_service.delete_quotation(db, scope)


def apply_form_scopes(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    actor_user_id: str,
    scopes: List[Dict[str, Any]],
) -> List[ProjectQuotationLine]:
    """The quotation form's Save in edit mode, for the scopes (#1341).

    Each item with an ``id`` is a scope already on THIS document (another document's scope 404s):
    its name, series and notes are applied when present, and ``lines`` when present is the FULL
    line set of its current version. That goes through ``replace_lines``, so a version the
    customer holds or that was superseded refuses with the existing 422 before anything moves -
    the status rules are the bulk line route's, unchanged. An item without an ``id`` is a new
    scope. A saved scope the payload leaves out is not touched.
    """
    approvals.assert_unlocked(db, document)
    written: List[ProjectQuotationLine] = []
    for item in scopes:
        scope_id = item.get("id")
        if not scope_id:
            written.extend(
                _add_form_scope(db, document=document, actor_user_id=actor_user_id, item=item)
            )
            continue
        scope = get_scope_or_404(db, document, str(scope_id))
        if item.get("matrix_columns") is not None:
            # A saved scope's columns move its quantities (set_columns); the form is not a
            # second way in that would skip that move.
            raise AppException(
                status_code=422,
                message="Change a saved scope's columns in its table header.",
                code="quotation_columns_invalid",
            )
        fields = {key: item[key] for key in _SCOPE_FIELDS if key in item}
        if fields:
            scope_service.update_quotation(db, quotation=scope, payload=fields)
        if item.get("lines") is not None:
            written.extend(
                scope_service.replace_lines(
                    db,
                    version=scope_service.current_version(db, scope.id),
                    actor_user_id=actor_user_id,
                    lines=item["lines"],
                )
            )
    return written


def _add_form_scope(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    actor_user_id: str,
    item: Dict[str, Any],
) -> List[ProjectQuotationLine]:
    lines = item.get("lines") or []
    scope = add_scope(
        db,
        document=document,
        scope_label=item.get("scope_label") or "",
        actor_user_id=actor_user_id,
        payload={key: item[key] for key in ("series_id", "notes") if key in item},
    )
    # PS-QUOTE-MATRIX: a scope added on the form brings its column headers. Set before the lines
    # (it has none yet, so nothing moves), so each line's cells are validated against them and
    # its quantity derived from them, all in this one transaction.
    if item.get("matrix_columns"):
        scope_service.set_columns(
            db,
            version=scope_service.current_version(db, scope.id),
            columns=item["matrix_columns"],
        )
    if not lines:
        return []
    return scope_service.replace_lines(
        db,
        version=scope_service.current_version(db, scope.id),
        actor_user_id=actor_user_id,
        lines=lines,
    )


# ------------------------------------------------------------------ issue


def list_issues(db: Session, document: ProjectQuotationDocument) -> List[ProjectQuotationIssue]:
    """Newest first. Current is MAX(issue_no); everything below it is what was sent before."""
    return (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.document_id == document.id)
        .order_by(ProjectQuotationIssue.issue_no.desc())
        .all()
    )


def current_issue(
    db: Session, document: ProjectQuotationDocument
) -> Optional[ProjectQuotationIssue]:
    return (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.document_id == document.id)
        .order_by(ProjectQuotationIssue.issue_no.desc())
        .first()
    )


def next_issue_no(db: Session, document_id: str) -> int:
    """The revision number the next send of this document takes (R1 for a first send)."""
    highest = (
        db.query(func.max(ProjectQuotationIssue.issue_no))
        .filter(ProjectQuotationIssue.document_id == document_id)
        .scalar()
    )
    return 1 if highest is None else int(highest) + 1


def issue(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    actor_user_id: str,
) -> ProjectQuotationIssue:
    """Stamp R{n} and record exactly what went out.

    Two things are frozen, for the same reason: the rendered letter and terms (the template will be
    rewritten) and the ``(scope, version)`` pairs (the versions would otherwise keep taking edits).

    A revision does NOT force every scope to move: an untouched scope contributes the same version
    it contributed last time, which is why the pairs are recorded rather than inferred from version
    numbers that advanced at different moments.
    """
    scopes = list_scopes(db, document)
    if not scopes:
        raise AppException(
            status_code=422,
            message="Add at least one scope before issuing this quotation.",
            code="quotation_document_no_scopes",
        )
    # AC-H1. No signature, no issue: an unsigned quotation in a customer's inbox is a thing
    # nobody can explain later, so the refusal happens here rather than being left to a reviewer.
    if not document.signatory_signature_id:
        raise AppException(
            status_code=422,
            message="Sign this quotation before issuing it.",
            code="quotation_document_unsigned",
        )
    # S15. Below-floor pricing needs a manager before it reaches the customer. Deliberately at
    # ISSUE and not at Sign: the internal signature is readiness, not dispatch. A quotation with
    # nothing below its floor - the overwhelming majority - is not touched by this at all.
    approvals.assert_issuable(db, document)

    issue_no = next_issue_no(db, document.id)
    label = _next_label(db, document, issue_no)
    previous = current_issue(db, document)

    from app.services import project_quotation_template_service as templates

    # The active cover page design, copied: editing or activating another one later never
    # touches this revision (QUOTE-COVER-DESIGN, UAC C4).
    active_design = templates.active_template(
        db, company_id=document.company_id, kind=templates.TEMPLATE_KIND_COVER_PAGE
    )
    record = ProjectQuotationIssue(
        company_id=document.company_id,
        document_id=document.id,
        issue_no=issue_no,
        revision_label=label,
        our_ref_text=quotation_no(document.document_no, issue_no, label),
        issued_at=datetime.utcnow(),
        issued_by=actor_user_id,
        cover_letter_rendered=document.cover_letter_html,
        cover_closing_rendered=document.cover_closing_html,
        cover_design=(
            copy.deepcopy(active_design.design)
            if active_design is not None and active_design.design
            else default_design()
        ),
        terms_rendered=document.terms_html,
        layout_version=COVER_LAYOUT_DESIGNED,
        payment_terms=document.payment_terms,
        validity=document.validity,
        grand_total=ZERO,
        # Copied, not referenced: re-signing the draft later must not change the signature this
        # revision went out with.
        sorento_signature_id=document.signatory_signature_id,
    )
    db.add(record)
    db.flush()

    grand = ZERO
    for scope in scopes:
        version = scope_service.current_version(db, scope.id)
        # S21. The photograph each line goes out with, written down at the moment it goes out.
        # A draft resolves its picture live off `product_attachments.is_primary`, because almost
        # every product is priced before anybody has chosen one; issuing is what turns today's
        # answer into the record of what was sent. A FILL only, so a scope carried unchanged into
        # R2 keeps exactly the pictures R1 showed.
        quotation_images.freeze_version_images(db, version.id)
        total = version_total(db, version)
        grand += total
        db.add(
            ProjectQuotationIssueScope(
                company_id=document.company_id,
                issue_id=record.id,
                quotation_id=scope.id,
                version_id=version.id,
                sort_order=scope.sort_order,
                scope_total=total,
            )
        )
    record.grand_total = grand
    db.flush()
    # QUOTE-CERT-TAB (CERT-11): the certificates that go out with this revision, frozen.
    from app.services import quotation_certificate_service

    record.certificates = quotation_certificate_service.snapshot(db, document)
    db.flush()
    # Issuing SPENDS an approval: a manager approved those prices, so the document moves off
    # `approved` and the next revision that dips below the floor has to be approved on its own
    # merits. A no-op on a quotation that was never on the graph.
    approvals.mark_issued(db, document)
    # Rule 3. Worked out here, SENT by the route after its commit: the notification service
    # commits per recipient, so sending inside this transaction would commit the issue early and
    # leave every recipient after the first unsent (and no email queued at all).
    record.price_changes = (
        price_changes(db, previous, record)
        if document.kind != KIND_QUOTATION and previous is not None
        else []
    )
    return record


# ------------------------------------------------- PS-PROPOSAL-QUOTATION


def line_key(line: ProjectQuotationLine) -> Optional[str]:
    """What makes two lines "the same product" across revisions and documents: the product, else
    the set, else the code the line printed."""
    if line.product_id:
        return str(line.product_id)
    if line.product_set_id:
        return f"set:{line.product_set_id}"
    code = (line.product_code_snapshot or "").strip().upper()
    return f"code:{code}" if code else None


def issue_lines(db: Session, record: ProjectQuotationIssue) -> List[ProjectQuotationLine]:
    """Every line of every version this issue froze."""
    return (
        db.query(ProjectQuotationLine)
        .join(
            ProjectQuotationIssueScope,
            ProjectQuotationIssueScope.version_id == ProjectQuotationLine.version_id,
        )
        .filter(ProjectQuotationIssueScope.issue_id == record.id)
        .order_by(ProjectQuotationIssueScope.sort_order, ProjectQuotationLine.sort_order)
        .all()
    )


def issue_price_map(db: Session, record: ProjectQuotationIssue) -> Dict[str, Decimal]:
    """`line_key -> unit price` of one issue; the lowest when a product appears twice."""
    prices: Dict[str, Decimal] = {}
    for line in issue_lines(db, record):
        key = line_key(line)
        if key is None or line.is_rate_only:
            continue
        price = Decimal(line.unit_price or 0)
        if key not in prices or price < prices[key]:
            prices[key] = price
    return prices


def price_changes(
    db: Session, previous: ProjectQuotationIssue, record: ProjectQuotationIssue
) -> List[Dict[str, Any]]:
    """Products in both revisions whose unit price moved. Added or removed lines are not price
    changes, and a quantity-only change is nothing at all."""
    before = issue_price_map(db, previous)
    changes: List[Dict[str, Any]] = []
    seen: set = set()
    for line in issue_lines(db, record):
        key = line_key(line)
        if key is None or key in seen or key not in before or line.is_rate_only:
            continue
        seen.add(key)
        new_price = Decimal(line.unit_price or 0)
        if new_price != before[key]:
            changes.append(
                {
                    "product_code": line.product_code_snapshot,
                    "description": line.description_snapshot,
                    "old_price": before[key],
                    "new_price": new_price,
                }
            )
    return changes


def alert_price_changes(
    db: Session, document: ProjectQuotationDocument, record: ProjectQuotationIssue
) -> None:
    """Rule 3: a PRICE change between two revisions of one proposal tells management.

    Called by the route AFTER the issue is committed, with the changes `issue()` worked out.
    Best-effort: the revision has already gone out and an alert that fails must not take it back.
    """
    changes = getattr(record, "price_changes", None) or []
    if not changes:
        return
    try:
        project = db.query(Project).filter(Project.id == document.project_id).first()
        if project is None:
            return
        from app.services import project_notify_service as notify

        notify.notify_proposal_price_changed(
            db, project=project, document=document, record=record, changes=changes
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("proposal price alert not sent: document=%s (%s)", document.id, exc)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


def alert_price_changes_job(
    db: Session, document_id: str, issue_id: str, changes: List[Dict[str, Any]]
) -> None:
    """``alert_price_changes`` for an after-response job: re-reads the rows on its own session."""
    if not changes:
        return
    document = db.query(ProjectQuotationDocument).filter(
        ProjectQuotationDocument.id == document_id
    ).first()
    record = db.query(ProjectQuotationIssue).filter(ProjectQuotationIssue.id == issue_id).first()
    if document is None or record is None:
        return
    record.price_changes = changes
    alert_price_changes(db, document, record)


def project_quotation(db: Session, project_id: str) -> Optional[ProjectQuotationDocument]:
    """The project's quotation (one at most, held by a partial unique index)."""
    return (
        db.query(ProjectQuotationDocument)
        .filter(
            ProjectQuotationDocument.project_id == project_id,
            ProjectQuotationDocument.kind == KIND_QUOTATION,
        )
        .first()
    )


def _stage_label(db: Session, project: Project) -> Optional[str]:
    """The label the user sees on the project's current stage (an admin may rename it)."""
    from app.models.status import Status

    return db.query(Status.label).filter(Status.id == project.status_id).scalar()


def make_quotation(
    db: Session,
    *,
    proposal: ProjectQuotationDocument,
    issue_id: str,
    actor_user_id: str,
) -> ProjectQuotationDocument:
    """The project's salesperson turns ONE issued proposal revision into the QUOTATION (any
    project not Lost or Dormant; #2197 dropped the won-only gate).

    A copy, not a re-pointing: the proposal and its issues stay exactly what the customer was
    sent, and the quotation gets its own number, its own scopes and versions (so a PO, a sample
    or an SO draft binds to it like to any version) and its own Sorento signature. The letter,
    terms, payment terms and validity come from the ISSUE's frozen copies, because that is what
    the customer agreed to, not whatever the proposal's draft says since.
    """
    if proposal.kind != KIND_PROPOSAL:
        raise AppException(
            status_code=422,
            message="Pick a proposal revision to make the quotation from.",
            code="quotation_source_not_proposal",
        )
    record = next(
        (row for row in list_issues(db, proposal) if str(row.id) == str(issue_id)), None
    )
    if record is None:
        raise AppException(
            status_code=404, message="Revision not found.", code="quotation_issue_not_found"
        )
    project = db.query(Project).filter(Project.id == proposal.project_id).first()
    if project is None:
        raise AppException(
            status_code=404, message="Project not found.", code="project_not_found"
        )
    if project.outcome == "dormant":
        # A Dormant stage makes the outcome dormant (PROJECT-CLASH-LOST): say which stage
        # stops it, as the admin may have renamed it.
        raise AppException(
            status_code=409,
            message=(
                f"This project is on the {_stage_label(db, project) or 'Dormant'}"
                " stage, so it cannot get a quotation."
            ),
            code="project_dormant",
        )
    if project.outcome == "lost":
        raise AppException(
            status_code=409,
            message="This project is lost. Re-open it before making its quotation.",
            code="project_lost",
        )
    if project_quotation(db, project.id) is not None:
        raise AppException(
            status_code=409,
            message="This project already has a quotation.",
            code="project_has_quotation",
        )

    quotation = ProjectQuotationDocument(
        company_id=proposal.company_id,
        project_id=proposal.project_id,
        kind=KIND_QUOTATION,
        source_issue_id=record.id,
        document_no=_next_document_no(db, proposal.company_id, SALES_QUOTATION_DOC_TYPE),
        your_ref=proposal.your_ref,
        doc_date=date.today(),
        recipient_party_id=proposal.recipient_party_id,
        recipient_name_snapshot=proposal.recipient_name_snapshot,
        recipient_address_snapshot=proposal.recipient_address_snapshot,
        recipient_phone_snapshot=proposal.recipient_phone_snapshot,
        recipient_email_snapshot=proposal.recipient_email_snapshot,
        attn_name=proposal.attn_name,
        quotation_purpose=proposal.quotation_purpose,
        subject_title=proposal.subject_title,
        cover_letter_html=record.cover_letter_rendered,
        terms_html=record.terms_rendered,
        payment_terms=record.payment_terms,
        validity=record.validity,
        signatory_name=proposal.signatory_name,
        signatory_phone=proposal.signatory_phone,
        # PS-SPEC-SHEET (#2103): the spec sheet settings travel with the lines they describe.
        spec_sheet=proposal.spec_sheet,
        created_by=actor_user_id,
    )
    db.add(quotation)
    db.flush()

    pairs = (
        db.query(ProjectQuotationIssueScope, ProjectQuotation)
        .join(ProjectQuotation, ProjectQuotation.id == ProjectQuotationIssueScope.quotation_id)
        .filter(ProjectQuotationIssueScope.issue_id == record.id)
        .order_by(ProjectQuotationIssueScope.sort_order)
        .all()
    )
    for pair, scope in pairs:
        copy = ProjectQuotation(
            company_id=quotation.company_id,
            project_id=quotation.project_id,
            document_id=quotation.id,
            sort_order=scope.sort_order,
            scope_label=scope.scope_label,
            series_id=scope.series_id,
            notes=scope.notes,
            created_by=actor_user_id,
        )
        db.add(copy)
        db.flush()
        source_version = (
            db.query(ProjectQuotationVersion)
            .filter(ProjectQuotationVersion.id == pair.version_id)
            .first()
        )
        version = ProjectQuotationVersion(
            company_id=quotation.company_id,
            quotation_id=copy.id,
            version_no=1,
            issued_by=actor_user_id,
            total_amount=ZERO,
            matrix_columns=source_version.matrix_columns if source_version else None,
        )
        db.add(version)
        db.flush()
        for line in scope_service.list_lines(db, pair.version_id):
            db.add(scope_service.copy_line(line, version_id=version.id, company_id=quotation.company_id))
        db.flush()
        scope_service.recalculate_total(db, version)

    from app.services import project_activity_service as activity

    activity.record_project_event(
        db,
        project=project,
        template="quotation_created",
        payload={
            "document_id": str(quotation.id),
            "document_no": quotation.document_no,
            "from": issue_no_text(proposal.document_no, record),
        },
        actor_id=actor_user_id,
    )
    db.flush()
    return quotation


# ------------------------------------------------------------------ delete


def assert_deletable(db: Session, document: ProjectQuotationDocument) -> None:
    if current_issue(db, document) is not None:
        raise AppException(
            status_code=422,
            message=(
                "This quotation has been issued to the customer and cannot be deleted. "
                "Withdraw it instead."
            ),
            code="quotation_document_issued",
        )


def delete_document(db: Session, document: ProjectQuotationDocument) -> None:
    """Hard delete, and refused outright once anything has been issued.

    An issued quotation is a thing the customer holds. Deleting the record of it would leave a
    reference in their inbox that this system cannot explain, so the exit is an explicit
    withdrawal on the status graph, never a delete.
    """
    assert_deletable(db, document)
    db.delete(document)
    db.flush()


# ------------------------------------------------------------------ serialize


def _scope_summary(db: Session, scope: ProjectQuotation) -> Dict[str, Any]:
    version = (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.quotation_id == scope.id)
        .order_by(ProjectQuotationVersion.version_no.desc())
        .first()
    )
    line_count = 0
    if version is not None:
        line_count = (
            db.query(func.count(ProjectQuotationLine.id))
            .filter(ProjectQuotationLine.version_id == version.id)
            .scalar()
            or 0
        )
    return {
        "id": str(scope.id),
        "scope_label": scope.scope_label,
        "sort_order": int(scope.sort_order or 0),
        "current_version_id": str(version.id) if version is not None else None,
        "current_version_no": version.version_no if version is not None else None,
        "line_count": int(line_count),
        "scope_total": version_total(db, version) if version is not None else ZERO,
    }


def _customer_decision(latest: Optional[ProjectQuotationIssue]) -> Optional[str]:
    """What the customer did with the revision they hold: accepted, asked, or nothing yet.

    Acceptance is checked FIRST and that ordering is the rule, not a coincidence: a customer who
    asked for changes and then signed has accepted, the request stays on the row as history, and
    a screen reporting "changes requested" on a quotation that is already won would be wrong on
    every one of them.
    """
    if latest is None:
        return None
    if latest.accepted_at is not None:
        return "accepted"
    if latest.changes_requested_at is not None:
        return "changes_requested"
    return None


def _prepared_by(db: Session, document: ProjectQuotationDocument) -> Optional[str]:
    """The project's salesperson, the same name the cover page prints."""
    from app.services.project_quotation_template_service import salesperson_of

    project = db.query(Project).filter(Project.id == document.project_id).first()
    return salesperson_of(db, project, document)


def _kind_fields(db: Session, document: ProjectQuotationDocument) -> Dict[str, Any]:
    """Proposal or quotation, and the link between the two (PS-PROPOSAL-QUOTATION)."""
    source = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.id == document.source_issue_id)
        .first()
        if document.source_issue_id
        else None
    )
    source_document = (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.id == source.document_id)
        .first()
        if source is not None
        else None
    )
    made = None
    if document.kind != KIND_QUOTATION:
        made = (
            db.query(ProjectQuotationDocument.id)
            .join(
                ProjectQuotationIssue,
                ProjectQuotationIssue.id == ProjectQuotationDocument.source_issue_id,
            )
            .filter(ProjectQuotationIssue.document_id == document.id)
            .scalar()
        )
    party_type = (
        db.query(ProjectParty.party_type)
        .filter(ProjectParty.id == document.recipient_party_id)
        .scalar()
        if document.recipient_party_id
        else None
    )
    return {
        "kind": document.kind or KIND_PROPOSAL,
        "source_issue_id": str(source.id) if source is not None else None,
        "source_document_id": str(source_document.id) if source_document is not None else None,
        "source_label": (
            issue_no_text(source_document.document_no, source)
            if source is not None and source_document is not None
            else None
        ),
        "quotation_document_id": str(made) if made else None,
        "recipient_party_type": party_type,
    }


def serialize_document(
    db: Session, document: ProjectQuotationDocument, viewer_id: Optional[str] = None
) -> Dict[str, Any]:
    """One document, with its tabs and its money.

    `grand_total` is summed HERE rather than by the caller, so the header, the tabs and the PDF
    cannot disagree about what a rate-only line contributes (nothing).
    """
    scopes = list_scopes(db, document)
    summaries = [_scope_summary(db, scope) for scope in scopes]
    latest = current_issue(db, document)
    # AC-H1 gates issuing on this, so the client has to be able to read it after a refresh and
    # not only in the response to its own sign call. "It is issued, so it must be signed" is not
    # a safe substitute: it is wrong on documents issued before the gate existed.
    signature = (
        db.query(QuotationSignature)
        .filter(QuotationSignature.id == document.signatory_signature_id)
        .first()
        if document.signatory_signature_id
        else None
    )
    issue_count = (
        db.query(func.count(ProjectQuotationIssue.id))
        .filter(ProjectQuotationIssue.document_id == document.id)
        .scalar()
        or 0
    )
    return {
        "id": str(document.id),
        "project_id": str(document.project_id),
        "document_no": document.document_no,
        "our_ref": (
            issue_no_text(document.document_no, latest)
            if latest is not None
            else document.document_no
        ),
        "current_revision_label": latest.revision_label if latest is not None else None,
        # What the next Send will print, by the same rule issue() stamps it with.
        "next_revision_label": _next_label(
            db, document, (latest.issue_no if latest is not None else 0) + 1
        ),
        **_kind_fields(db, document),
        "your_ref": document.your_ref,
        "doc_date": document.doc_date,
        "recipient_party_id": (
            str(document.recipient_party_id) if document.recipient_party_id else None
        ),
        "recipient_name_snapshot": document.recipient_name_snapshot,
        "recipient_address_snapshot": document.recipient_address_snapshot,
        "recipient_phone_snapshot": document.recipient_phone_snapshot,
        "recipient_email_snapshot": document.recipient_email_snapshot,
        "quotation_purpose": document.quotation_purpose,
        "payment_terms": document.payment_terms,
        "validity": document.validity,
        "prepared_by": _prepared_by(db, document),
        "attn_name": document.attn_name,
        "subject_title": document.subject_title,
        "cover_letter_html": document.cover_letter_html,
        "cover_closing_html": document.cover_closing_html,
        "terms_html": document.terms_html,
        "signatory_name": document.signatory_name,
        "signatory_phone": document.signatory_phone,
        "signatory_signature": _serialize_signature(signature),
        "is_signed": signature is not None,
        "scopes": summaries,
        "grand_total": sum((row["scope_total"] for row in summaries), ZERO),
        "issue_count": int(issue_count),
        "current_issue_no": latest.issue_no if latest is not None else None,
        "is_issued": latest is not None,
        # Where the CUSTOMER left the revision they are currently holding, so the salesperson's
        # own screens can say it without reading the issue history. The client went looking for a
        # change request and could not find it ("when i request changes, how can i see it from
        # the system?"), and the answer cannot be a tab: the banner on the document and the badge
        # on the project's quotation list both need this, and neither fetches issues.
        #
        # Read off the LATEST issue alone. Read across the whole history it would keep telling
        # somebody to revise a quotation they have already revised and re-issued.
        "accepted_at": latest.accepted_at if latest is not None else None,
        "changes_requested_at": (
            latest.changes_requested_at if latest is not None else None
        ),
        "changes_requested_note": (
            latest.changes_requested_note if latest is not None else None
        ),
        "changes_requested_by_name": (
            latest.changes_requested_by_name if latest is not None else None
        ),
        # The one place the "acceptance wins" rule is decided. Both fields can be set - somebody
        # who asked for changes may still sign - and every surface has to reach the same answer,
        # so it is resolved once here rather than re-expressed on the counter-sign page, the
        # Signatures badge, the document banner and the list column.
        "customer_decision": _customer_decision(latest),
        # PS-QUOTE-VIEWS: the customer's counted opens of the revision they hold now. Older
        # revisions' opens are in the view log, not here.
        **_views.summary_for_issue(db, latest),
        # S15. The screen reads all six of these to decide whether to show the price-floor
        # block at all, so they are present on EVERY document rather than only on a gated one:
        # absent would be as bad as wrong. Spread from one function so this manual dict and the
        # approval service cannot drift - this repo has been bitten by a manual builder silently
        # dropping a new column more than once (`get_user`, `system_settings`).
        **approvals.serialize_approval(db, document, viewer_id=viewer_id),
        # QUOTE-AUTOSAVE: whether a form draft is waiting, for the read page's strip.
        **_form_drafts.draft_summary(db, document),
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def serialize_documents(
    db: Session, documents: List[ProjectQuotationDocument], viewer_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    return [serialize_document(db, document, viewer_id=viewer_id) for document in documents]


def serialize_issue(db: Session, record: ProjectQuotationIssue) -> Dict[str, Any]:
    from app.models.user import User

    name = None
    if record.issued_by:
        user = db.query(User).filter(User.id == record.issued_by).first()
        name = user.name if user else None
    scope_count = (
        db.query(func.count(ProjectQuotationIssueScope.id))
        .filter(ProjectQuotationIssueScope.issue_id == record.id)
        .scalar()
        or 0
    )
    return {
        "id": str(record.id),
        "document_id": str(record.document_id),
        "issue_no": record.issue_no,
        "revision_label": record.revision_label,
        "our_ref_text": record.our_ref_text,
        "issued_at": record.issued_at,
        "issued_by": record.issued_by,
        "issued_by_name": name,
        "grand_total": Decimal(record.grand_total or 0),
        "scope_count": int(scope_count),
        # QUOTE-CERT-TAB: how many certificates went out with this revision (frozen at issue).
        # None = issued before certificates were frozen (never frozen), not "none went out".
        "certificates_count": (
            None
            if record.certificates is None
            else len([c for c in record.certificates if c.get("attachment_id")])
        ),
        # The acceptance lands HERE, on the thing the customer actually held and signed, while the
        # screen watching for it is the document. Without these the document panel says "not
        # counter-signed yet" forever on a quotation that is already won.
        "customer_signature": _serialize_signature(
            db.query(QuotationSignature)
            .filter(QuotationSignature.id == record.customer_signature_id)
            .first()
            if record.customer_signature_id
            else None
        ),
        "accepted_at": record.accepted_at,
        "is_accepted": record.accepted_at is not None,
        # The other decision, on the same row and needed on the same screen: the salesperson
        # reads the feedback here and presses Revise. A notification alone would mean the words
        # only ever exist in an inbox.
        "changes_requested_at": record.changes_requested_at,
        "changes_requested_note": record.changes_requested_note,
        "changes_requested_by_name": record.changes_requested_by_name,
        "is_changes_requested": record.changes_requested_at is not None,
    }


def list_documents(db: Session, project_id: str) -> List[ProjectQuotationDocument]:
    return (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.project_id == project_id)
        .order_by(ProjectQuotationDocument.created_at.desc())
        .all()
    )


def update_document(
    db: Session, *, document: ProjectQuotationDocument, payload: Dict[str, Any]
) -> ProjectQuotationDocument:
    """Header edits only. `document_no` is deliberately not editable: the customer has it.

    The recipient snapshot IS editable, and it is still a snapshot. What a correction changes is
    this document's copy of who it is addressed to, never the developer party behind it, so a
    quotation can go to the customer's finance department without moving the master record - and
    the party changing later still cannot rewrite a quotation already in the customer's hands.

    Applied by allow-list and keyed on PRESENCE, because the route hands down an `exclude_unset`
    payload: a save correcting only Your Ref arrives with no recipient key at all, and reading
    absent as null would blank the letterhead as a side effect. Null is a separate, deliberate
    answer, and it clears.
    """
    approvals.assert_unlocked(db, document)
    from app.services import project_quotation_template_service as templates

    # One rule for every save: an unknown merge field is refused before anything is written.
    for field in TOKEN_FIELDS:
        templates.assert_tokens_known(payload.get(field))
    for field in (
        "your_ref",
        "doc_date",
        "attn_name",
        "subject_title",
        "cover_letter_html",
        "cover_closing_html",
        "terms_html",
        "signatory_name",
        "signatory_phone",
        "recipient_name_snapshot",
        "recipient_address_snapshot",
        "recipient_phone_snapshot",
        "recipient_email_snapshot",
        "quotation_purpose",
        "payment_terms",
        "validity",
    ):
        if field in payload:
            setattr(document, field, payload[field])
    db.flush()
    # ...and the known ones are filled in from this document, on every save.
    context = None
    for field in TOKEN_FIELDS:
        if payload.get(field):
            context = context or templates.build_document_context(db, document=document)
            setattr(document, field, templates.render(payload[field], context))
    db.flush()
    return document


def update_scope(
    db: Session, *, scope: ProjectQuotation, payload: Dict[str, Any]
) -> ProjectQuotation:
    scope_service.assert_scope_unlocked(db, scope)
    if "scope_label" in payload and payload["scope_label"] is not None:
        label = " ".join(str(payload["scope_label"]).split())
        if not label:
            raise AppException(
                status_code=422,
                message="A scope needs a name, e.g. Townhouse or Guard House.",
                code="quotation_scope_required",
            )
        scope.scope_label = label
    if payload.get("sort_order") is not None:
        scope.sort_order = int(payload["sort_order"])
    if "notes" in payload:
        scope.notes = payload["notes"]
    db.flush()
    return scope


def get_scope_or_404(
    db: Session, document: ProjectQuotationDocument, quotation_id: str
) -> ProjectQuotation:
    scope = (
        db.query(ProjectQuotation)
        .filter(
            ProjectQuotation.id == quotation_id,
            ProjectQuotation.document_id == document.id,
        )
        .first()
    )
    if not scope:
        raise AppException(
            status_code=404, message="Scope not found.", code="quotation_scope_not_found"
        )
    return scope


# ------------------------------------------------------------------ signing

SIGN_TOKEN_TTL_DAYS = 30


def record_signature(
    db: Session,
    *,
    company_id: Optional[str],
    owner_kind: str,
    signer_name: Optional[str],
    mode: str,
    image_data_uri: Optional[str],
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    gps_lat: Optional[str] = None,
    gps_lng: Optional[str] = None,
) -> QuotationSignature:
    """Store one signature exactly as captured.

    Always a NEW row, never a reference to a reusable one: a signature applied to a document has to
    stay what it was on the day, so re-drawing your signature next year cannot rewrite what you
    already signed. Same snapshot rule as the lines and the rendered letter.
    """
    if mode not in ("draw", "type", "initials"):
        raise AppException(
            status_code=422,
            message=f"Unknown signature mode '{mode}'.",
            code="signature_mode_invalid",
        )
    if not image_data_uri:
        raise AppException(
            status_code=422,
            message="A signature needs to be drawn, typed or initialled before it can be saved.",
            code="signature_empty",
        )

    signature = QuotationSignature(
        company_id=company_id,
        owner_kind=owner_kind,
        user_id=user_id,
        signer_name=(signer_name or "").strip() or None,
        mode=mode,
        image_data_uri=image_data_uri,
        ip_address=ip_address,
        user_agent=user_agent,
        gps_lat=gps_lat,
        gps_lng=gps_lng,
        signed_at=datetime.utcnow(),
    )
    db.add(signature)
    db.flush()
    return signature


def sign_as_sorento(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    actor_user_id: str,
    payload: Dict[str, Any],
) -> QuotationSignature:
    """The internal signature, held on the DOCUMENT until an issue carries it.

    Kept on the document rather than demanded at issue time so the signing and the issuing are
    separate acts: a person signs once and can then issue, which is the order the journey has.
    """
    from app.models.user import User

    signer_name = (payload.get("signer_name") or "").strip() or (document.signatory_name or "").strip()
    if not signer_name:
        user = db.query(User).filter(User.id == actor_user_id).first()
        signer_name = ((user.name if user else None) or "").strip()
    signature = record_signature(
        db,
        company_id=document.company_id,
        owner_kind="user",
        signer_name=signer_name or None,
        mode=payload.get("mode") or "draw",
        image_data_uri=payload.get("image_data_uri"),
        user_id=actor_user_id,
        ip_address=payload.get("ip_address"),
        user_agent=payload.get("user_agent"),
        gps_lat=payload.get("gps_lat"),
        gps_lng=payload.get("gps_lng"),
    )
    document.signatory_signature_id = signature.id
    db.flush()
    return signature


def issue_sign_link(
    db: Session, *, record: ProjectQuotationIssue, ttl_days: int = SIGN_TOKEN_TTL_DAYS
) -> str:
    """Mint (or reuse) the tokenised counter-sign link for an issue.

    Reused while it is still valid so re-sending the same quotation does not invalidate the link
    the customer already has sitting in their inbox. Rotated once it has expired.
    """
    now = datetime.utcnow()
    if (
        record.sign_token
        and record.sign_token_expires_at
        and record.sign_token_expires_at > now
    ):
        return record.sign_token
    record.sign_token = secrets.token_urlsafe(32)
    record.sign_token_expires_at = now + timedelta(days=ttl_days)
    db.flush()
    return record.sign_token


def record_whatsapp_opened(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    record: ProjectQuotationIssue,
    actor_id: str,
) -> None:
    """Note on the project feed that the salesperson opened the quotation link in WhatsApp.

    Deliberately NOT on `MEANINGFUL_TEMPLATES`: opening a chat is not the customer answering, and
    must not clear the project's unattended clock.
    """
    from app.models.user import User
    from app.services import project_activity_service as activity

    project = db.query(Project).filter(Project.id == document.project_id).first()
    if project is None:
        return
    user = db.query(User).filter(User.id == actor_id).first()
    who = (user.name or user.email) if user is not None else "a colleague"
    reference = record.our_ref_text or issue_no_text(document.document_no, record)
    activity.record_project_event(
        db,
        project=project,
        template=WHATSAPP_OPENED_TEMPLATE,
        payload={
            "document_id": str(document.id),
            "issue_id": str(record.id),
            "issue_no": record.issue_no,
            "our_ref": reference,
        },
        actor_id=actor_id,
        body_text=f"Quotation {reference} link opened in WhatsApp by {who}",
    )
    db.flush()


def get_issue_by_sign_token(db: Session, token: str) -> ProjectQuotationIssue:
    """Resolve a counter-sign link, refusing anything expired or unknown with the SAME message.

    Deliberately one message for both: telling a caller that a token exists but has expired
    confirms the token, and this endpoint is public.

    Resolved with the company scope OPEN, then pinned shut to the issue's own company. The signer
    is a stranger with no session and no API key, so the scope resolver leaves this request at
    UNSET, which is fail-closed and reads zero rows from every owned table: without the open
    window a live link answers "no longer valid" and the customer is told to ask for a resend of
    something that was never broken. The token is what makes opening it safe, being globally
    unique and the whole credential. Pinning afterwards is not optional: everything the handler
    reads next (scopes, lines, signatures) must stay inside the company the token belongs to, or
    one leaked link becomes a reader for every company's data.
    """
    with company_scope(db, None):
        record = (
            db.query(ProjectQuotationIssue)
            .filter(ProjectQuotationIssue.sign_token == token)
            .first()
        )
    if record is not None and record.company_id:
        set_company_scope(db, frozenset({str(record.company_id)}))
    if (
        record is None
        or record.sign_token_expires_at is None
        or record.sign_token_expires_at <= datetime.utcnow()
    ):
        raise AppException(
            status_code=404,
            message="This link is no longer valid. Ask your contact at Sorento to resend it.",
            code="quotation_sign_link_invalid",
        )
    return record


def later_issue(
    db: Session, record: ProjectQuotationIssue
) -> Optional[ProjectQuotationIssue]:
    """The newest issue of the same document after this one, or None when this is the latest."""
    return (
        db.query(ProjectQuotationIssue)
        .filter(
            ProjectQuotationIssue.document_id == record.document_id,
            ProjectQuotationIssue.issue_no > record.issue_no,
        )
        .order_by(ProjectQuotationIssue.issue_no.desc())
        .first()
    )


def assert_not_superseded(db: Session, record: ProjectQuotationIssue) -> None:
    """A replaced revision is neither signed nor amended: the customer is pointed at the new one."""
    newer = later_issue(db, record)
    if newer is not None:
        raise AppException(
            status_code=409,
            message=f"This has been replaced by {newer.our_ref_text}.",
            code="quotation_superseded",
        )


def accept_issue(
    db: Session,
    *,
    record: ProjectQuotationIssue,
    signer_name: Optional[str],
    mode: str,
    image_data_uri: Optional[str],
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    gps_lat: Optional[str] = None,
    gps_lng: Optional[str] = None,
    terms_accepted: bool = False,
) -> ProjectQuotationIssue:
    """The customer counter-signs, and that WINS the quotation.

    Client decision (2026-08-04), overruling the evidence-only reading the UAC first proposed: a
    counter-signature is the commitment, so every scope the issue carried is marked won and the
    project's outcome derives to won through the rule that already exists.

    A scope already marked LOST is left alone. Somebody decided that deliberately, and a signature
    on a document that still lists the scope must not silently overrule a person. It stays lost,
    and the acceptance is still recorded.

    Idempotent: signing twice keeps the FIRST signature and the first accepted_at. A customer who
    double-taps has not signed two different things, and overwriting would lose the timestamp that
    matters.

    An issue that carries terms needs `terms_accepted`; the public route passes what the customer
    ticked (false when missing), so the box is enforced server-side and not only by the page.
    """
    # Locked and re-read BEFORE any check, as `request_changes` and a suggestion submit do: a
    # signature and a suggestion racing from two tabs serialise on this row, and the second
    # sees what the first wrote.
    record = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.id == record.id)
        .with_for_update()
        .populate_existing()
        .first()
    ) or record
    if record.accepted_at is not None:
        return record
    assert_not_superseded(db, record)
    if (record.terms_rendered or "").strip() and terms_accepted is not True:
        raise AppException(
            status_code=422,
            message="Tick the box to agree to the terms before you accept.",
            code="quotation_terms_not_accepted",
        )

    signature = record_signature(
        db,
        company_id=record.company_id,
        owner_kind="customer",
        signer_name=signer_name,
        mode=mode,
        image_data_uri=image_data_uri,
        ip_address=ip_address,
        user_agent=user_agent,
        gps_lat=gps_lat,
        gps_lng=gps_lng,
    )
    record.customer_signature_id = signature.id
    record.accepted_at = datetime.utcnow()
    db.flush()

    _win_the_project_on(db, record)
    return record


def _win_the_project_on(db: Session, record: ProjectQuotationIssue) -> None:
    """An accepted proposal wins an OPEN project. Won is left as it is, and Lost too: a person
    decided that, and a signature does not overrule them."""
    document = (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.id == record.document_id)
        .first()
    )
    project = (
        db.query(Project).filter(Project.id == document.project_id).first()
        if document is not None
        else None
    )
    if project is not None and project.outcome == "open":
        project.outcome = "won"
        project.loss_reason = None
        db.flush()


# --------------------------------------------------------- the other answer


CHANGES_REQUESTED_TEMPLATE = "quotation_changes_requested"
WHATSAPP_OPENED_TEMPLATE = "quotation_whatsapp_opened"


def request_changes(
    db: Session,
    *,
    record: ProjectQuotationIssue,
    note: Optional[str],
    requester_name: Optional[str] = None,
) -> ProjectQuotationIssue:
    """The customer will not sign this as it stands, and says why.

    Client decision (2026-08-05): the feedback is CAPTURED and the salesperson revises by hand.
    Nothing here opens a revision, re-prices a line or moves an outcome - a customer asking for a
    lower price has not been given one, and a system that auto-revised would put words in the
    salesperson's mouth. What this owes them is the message, the moment, and a notification.

    Three refusals and one silence, each mirroring the care `accept_issue` already takes:

    * **An empty request is refused** (422). A stamped time with no words behind it renders on the
      customer's page as a settled outcome that nobody can act on.
    * **An accepted quotation is refused** (409). The counter-signature won every scope on the
      issue and moved the project's outcome; a request for changes sitting beside it would be a
      record that says both. The page stops offering the form once accepted, so this is only
      reachable from a stale tab, and it is answered rather than silently dropped.
    * **The same words twice do nothing** - no new stamp, no second activity row, no second
      notification. A double-tap is one request, exactly as a double-tap on Accept is one
      signature. Genuinely NEW words DO get through, which is the property
      ``floor_breach_dedup_key`` exists for: deduplicating the repeat must not silence somebody
      who came back with something else to say.

    The read is taken ``FOR UPDATE`` so two submissions from the same thumb serialise instead of
    racing: without the lock both see a null note and both notify.

    The reverse order is ALLOWED: somebody who asked for changes can still decide to sign, and
    feedback notes (``quotation_amendment_service``) never block signing either.
    """
    text_note = (note or "").strip()
    if not text_note:
        raise AppException(
            status_code=422,
            message="Tell us what to change before sending this back.",
            code="quotation_changes_note_required",
        )

    locked = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.id == record.id)
        .with_for_update()
        .first()
    ) or record

    if locked.accepted_at is not None:
        raise AppException(
            status_code=409,
            message=(
                "This quotation has already been accepted. "
                "Contact Sorento if something needs to change."
            ),
            code="quotation_already_accepted",
        )

    if locked.changes_requested_at is not None and locked.changes_requested_note == text_note:
        return locked

    name = (requester_name or "").strip() or None
    locked.changes_requested_at = datetime.utcnow()
    locked.changes_requested_note = text_note
    locked.changes_requested_by_name = name
    db.flush()

    _record_changes_requested(db, record=locked, note=text_note, requester_name=name)
    return locked


def _record_changes_requested(
    db: Session,
    *,
    record: ProjectQuotationIssue,
    note: str,
    requester_name: Optional[str],
) -> None:
    """Tell the feed and tell the salesperson. Best-effort, both of them.

    The row is already written by the time this runs, so a notification backend that is down must
    not turn a captured request into a 500 the customer would retry - and the retry would take the
    identical-note path, which writes nothing at all.
    """
    document = (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.id == record.document_id)
        .first()
    )
    project = (
        db.query(Project).filter(Project.id == document.project_id).first()
        if document is not None
        else None
    )
    if project is None:
        return

    who = requester_name or "The customer"
    reference = record.our_ref_text or (document.document_no if document else "")
    try:
        from app.services import project_activity_service as activity

        # Deliberately NOT on `MEANINGFUL_TEMPLATES`: a request nobody has answered is exactly
        # when a project should look unattended, and advancing the staleness clock here would
        # clear the badge the moment the customer complains.
        activity.record_project_event(
            db,
            project=project,
            template=CHANGES_REQUESTED_TEMPLATE,
            payload={
                "document_id": str(record.document_id),
                "issue_id": str(record.id),
                "issue_no": record.issue_no,
                "our_ref": reference,
                "requested_by": requester_name,
            },
            body_text=f"{who} asked for changes to {reference}: {note}",
        )
        db.flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "quotation changes-requested activity not written: issue=%s (%s)", record.id, exc
        )

    try:
        from app.services import project_notify_service as notify

        notify.notify_quotation_changes_requested(
            db,
            project=project,
            document=document,
            record=record,
            note=note,
            requester_name=requester_name,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "quotation changes-requested notification not sent: issue=%s (%s)", record.id, exc
        )


# ------------------------------------------------------- the public sign page


def _serialize_signature(signature: Optional[QuotationSignature]) -> Optional[Dict[str, Any]]:
    if signature is None:
        return None
    return {
        "id": str(signature.id),
        "signer_name": signature.signer_name,
        "mode": signature.mode,
        "image_data_uri": signature.image_data_uri,
        "signed_at": signature.signed_at,
        "ip_address": signature.ip_address,
        "gps_lat": signature.gps_lat,
        "gps_lng": signature.gps_lng,
    }


#: Rendered sign-page pictures by attachment id, across requests: ``(data uri, deadline)``. A
#: rendered picture never goes stale (the ids are stamped at issue), so it keeps for good; a miss
#: (storage down, a file Pillow will not open) keeps for ``_SIGN_MISS_SECONDS`` so a page that is
#: refetched does not refetch a broken picture each time, yet a hiccup is not a permanent blank.
#: Bounded: ~15 KB each, so the cap holds a few MB; evicting the lot costs one re-render each.
_SIGN_PICTURES_MAX = 512
_SIGN_PICTURES: Dict[str, Tuple[Optional[str], float]] = {}
_SIGN_MISS_SECONDS = 10 * 60
#: Most pictures one sign page inlines, in page order (QUOTE-PERF-HOTFIX, 3 Nov): each is an
#: image decode inside the request, and a page of hundreds of lines made one GET do hundreds.
SIGN_PICTURES_PER_PAGE = 60


def _sign_clock() -> float:
    return time.monotonic()


def _sign_cached(attachment_id: str) -> Tuple[bool, Optional[str]]:
    hit = _SIGN_PICTURES.get(attachment_id)
    if hit is None or hit[1] <= _sign_clock():
        return False, None
    return True, hit[0]


def _sign_remember(attachment_id: str, uri: Optional[str]) -> None:
    if len(_SIGN_PICTURES) >= _SIGN_PICTURES_MAX:
        _SIGN_PICTURES.clear()
    deadline = float("inf") if uri is not None else _sign_clock() + _SIGN_MISS_SECONDS
    _SIGN_PICTURES[attachment_id] = (uri, deadline)


def _save_thumbnails(
    made: Dict[str, str], company_id: Optional[str], db: Optional[Session] = None
) -> None:
    """Record thumbnails the sign page made, so the original is never read for them again.

    Through ``db`` when the caller still holds it, else a short session of its own: by now the
    request's connection has been handed back.
    """
    if not made:
        return
    from app.database import SessionLocal
    from app.models.base import company_scope
    from app.models.resources import Attachment

    own = db is None
    session = SessionLocal() if own else db
    try:
        # Pinned to the issue's company: the ids came from a read scoped to it.
        scope = frozenset({company_id}) if company_id else None
        with company_scope(session, scope):
            for attachment_id, url in made.items():
                session.query(Attachment).filter(
                    Attachment.id == attachment_id, Attachment.thumbnail_path.is_(None)
                ).update({Attachment.thumbnail_path: url}, synchronize_session=False)
        if own:
            session.commit()
        else:
            session.flush()
    except Exception:  # noqa: BLE001 - the picture is already on the page; this is a saving
        logger.warning("sign page: could not save made thumbnails", exc_info=True)
        if own:
            session.rollback()
    finally:
        if own:
            session.close()


def _sign_pictures(
    db: Session,
    wanted: List[str],
    release: Optional[Callable[[], None]],
    company_id: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Every picture the page inlines, as data URIs. A data URI rather than a link: the customer
    has no login, and a signed URL would carry the storage key into their browser.

    Where each file lives is read first; then ``release`` hands the DB connection back before any
    byte is fetched or decoded, so a slow bucket never pins a pool connection.
    """
    from app.services import product_image_service as product_images

    out: Dict[str, Optional[str]] = {}
    missing: List[str] = []
    for key in wanted:
        known, uri = _sign_cached(key)
        if known:
            out[key] = uri
        else:
            missing.append(key)
    sources = product_images.picture_sources(db, missing) if missing else {}
    if release is not None:
        release()
    made: Dict[str, str] = {}
    for key in missing:
        source = sources.get(key)
        rendered, thumb = (
            product_images.render_source(source) if source is not None else (None, None)
        )
        uri = product_images.as_data_uri(rendered)
        if thumb:
            made[key] = thumb
        _sign_remember(key, uri)
        out[key] = uri
    _save_thumbnails(made, company_id, None if release is not None else db)
    return out


def serialize_sign_page(
    db: Session,
    record: ProjectQuotationIssue,
    *,
    release: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    """The quotation as ISSUED, for the customer's read-only counter-sign page.

    Every line comes from the `version_id` the issue recorded, never from the scope's current
    version. If it read live rows, the page could show the customer something different from the
    PDF in their inbox, which is the one thing a signing surface must never do.

    ``release`` (the route's ``db.close``) is called once every row has been read and before any
    picture is fetched; the session must not be used by the caller afterwards.
    """
    document = (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.id == record.document_id)
        .first()
    )
    pairs = (
        db.query(ProjectQuotationIssueScope)
        .filter(ProjectQuotationIssueScope.issue_id == record.id)
        .order_by(ProjectQuotationIssueScope.sort_order)
        .all()
    )

    version_columns = {
        str(v.id): v.matrix_columns
        for v in db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.id.in_([p.version_id for p in pairs]))
        .all()
    } if pairs else {}
    from app.services import quotation_columns

    # Pictures are collected in page order and filled in at the very end (see `_sign_pictures`).
    wanted: List[str] = []
    slots: List[Tuple[Dict[str, Any], str, str]] = []

    def _want(row: Dict[str, Any], field: str, attachment_id: Optional[str], shown: bool) -> None:
        row[field] = None
        if not attachment_id or not shown:
            return
        key = str(attachment_id)
        if key not in wanted:
            if len(wanted) >= SIGN_PICTURES_PER_PAGE:
                return
            wanted.append(key)
        slots.append((row, field, key))

    scopes: List[Dict[str, Any]] = []
    for pair in pairs:
        scope = (
            db.query(ProjectQuotation)
            .filter(ProjectQuotation.id == pair.quotation_id)
            .first()
        )
        lines = (
            db.query(ProjectQuotationLine)
            .filter(ProjectQuotationLine.version_id == pair.version_id)
            .order_by(
                ProjectQuotationLine.sort_order,
                ProjectQuotationLine.created_at,
                ProjectQuotationLine.id,
            )
            .all()
        )
        columns = quotation_columns.for_lines(lines)
        shown = {key for key, _label in columns}
        rows: List[Dict[str, Any]] = []
        for position, line in enumerate(lines, start=1):
            row: Dict[str, Any] = {
                # The handle a suggested change names. Only lines of this issue are
                # accepted back, so the id gives nothing beyond the page itself.
                "id": str(line.id),
                # Same definition the PDF and the workbook use. The customer signing this
                # page and the customer reading the PDF must see the same item numbers.
                # Same definition the PDF and the workbook use, imported INSIDE the
                # function on purpose: the pdf module pulls in WeasyPrint's neighbours and
                # storage, and importing that at module scope changes what is loaded before
                # the test fixtures build their schema.
                "item_label": _item_number(line, position),
                "description": line.description_snapshot,
                "technical_spec": line.technical_spec,
                "image_url": None,
                "drawing_url": None,
                "brand": line.brand_snapshot,
                "product_code": line.product_code_snapshot,
                "quantity": Decimal(line.quantity or 0),
                # Printed after the quantity, as the PDF's QTY cell does ("2 pcs").
                "uom": line.uom,
                "unit_price": Decimal(line.unit_price or 0),
                "complete_set": line.complete_set,
                "band_label": line.band_label,
                "is_rate_only": bool(line.is_rate_only),
                # None, not zero: the page prints "rate only" and a zero would read as free.
                "amount": None if line.is_rate_only else Decimal(line.line_total or 0),
                "qty_cells": dict(line.qty_cells or {}),
            }
            # Inline only what the page draws: the photo sits in PRODUCT IMAGE, the drawing in
            # TECHNICAL SPEC.
            _want(row, "image_url", line.image_attachment_id, quotation_columns.IMAGE in shown)
            _want(row, "drawing_url", line.drawing_attachment_id, "spec" in shown)
            rows.append(row)
        scopes.append(
            {
                # The label is read live, and that is a deliberate, small exception: renaming a tab
                # does not change what was priced, and a stale label helps nobody.
                "scope_label": scope.scope_label if scope else "",
                "scope_total": Decimal(pair.scope_total or 0),
                "matrix_columns": list(version_columns.get(str(pair.version_id)) or []),
                # The PDF's column set for this scope, from the one shared definition
                # (QUOTE-SIGN-COLUMNS): the page renders these, it keeps no list of its own.
                "columns": [{"key": key, "label": label} for key, label in columns],
                "lines": rows,
            }
        )

    sorento = (
        db.query(QuotationSignature)
        .filter(QuotationSignature.id == record.sorento_signature_id)
        .first()
        if record.sorento_signature_id
        else None
    )
    customer = (
        db.query(QuotationSignature)
        .filter(QuotationSignature.id == record.customer_signature_id)
        .first()
        if record.customer_signature_id
        else None
    )

    sender = sender_of(db, document.company_id if document is not None else None)

    from app.services import quotation_amendment_service as amendments

    newer = later_issue(db, record)
    # One reason, the first that applies, so the page never prints two.
    if record.accepted_at is not None:
        blocked = "accepted"
    elif newer is not None:
        blocked = "superseded"
    else:
        blocked = None

    cover = None
    designed: Dict[str, Any] = {}
    our_ref = (
        issue_no_text(document.document_no, record)
        if document is not None
        else record.our_ref_text
    )
    if document is not None and layout_of(record) >= COVER_LAYOUT:
        project = (
            db.query(Project).filter(Project.id == document.project_id).first()
            if document.project_id
            else None
        )
        layout3 = layout_of(record) >= COVER_LAYOUT_DESIGNED
        cover = cover_rows(db, document, record, project, design_of(record) if layout3 else None)
        our_ref = cover_reference(document, record, project)
        if layout3:
            designed = cover_payload(
                cover,
                design_of(record),
                intro=record.cover_letter_rendered,
                closing=record.cover_closing_rendered,
                sender_name=None,
                sender_logo_url=None,
                noun=document_noun(document),
            )
    page = {
        "our_ref": our_ref,
        "document_kind": (document.kind if document is not None else None) or KIND_PROPOSAL,
        "cover_rows": cover,
        "cover_title": designed.get("cover_title"),
        "cover_show_letterhead": designed.get("cover_show_letterhead"),
        "cover_intro_html": designed.get("cover_intro_html"),
        "cover_closing_html": designed.get("cover_closing_html"),
        "issue_no": record.issue_no,
        "doc_date": document.doc_date if document else None,
        "subject_title": document.subject_title if document else None,
        "sender_name": sender["sender_name"],
        "sender_logo_url": sender["sender_logo_url"],
        "recipient_name": document.recipient_name_snapshot if document else None,
        "recipient_address": document.recipient_address_snapshot if document else None,
        "attn_name": document.attn_name if document else None,
        "cover_letter": record.cover_letter_rendered,
        "terms": record.terms_rendered,
        "signatory_name": document.signatory_name if document else None,
        "signatory_phone": document.signatory_phone if document else None,
        "scopes": scopes,
        "grand_total": Decimal(record.grand_total or 0),
        "sorento_signature": _serialize_signature(sorento),
        "customer_signature": _serialize_signature(customer),
        "accepted_at": record.accepted_at,
        "is_accepted": record.accepted_at is not None,
        # So the page can settle on either decision without a reload, and quote the customer's
        # own words back to them rather than making them wonder whether it sent.
        "changes_requested_at": record.changes_requested_at,
        "changes_requested_note": record.changes_requested_note,
        "changes_requested_by_name": record.changes_requested_by_name,
        "is_changes_requested": record.changes_requested_at is not None,
        "amendment_request": amendments.sign_page_feedback(db, record.id),
        "superseded_by_ref": newer.our_ref_text if newer is not None else None,
        "can_sign": blocked is None,
        "sign_blocked_reason": blocked,
    }
    # Last, once every row has been read: the connection goes back before any picture work.
    company_id = str(document.company_id) if document is not None and document.company_id else None
    pictures = _sign_pictures(db, wanted, release, company_id)
    for row, field, key in slots:
        row[field] = pictures.get(key)
    return page


# ------------------------------------------------------------------ cover preview (stores nothing)

#: The quotation fields a preview body may stage over the saved document.
_PREVIEW_FIELDS = (
    "doc_date",
    "attn_name",
    "recipient_name_snapshot",
    "recipient_address_snapshot",
    "recipient_phone_snapshot",
    "recipient_email_snapshot",
    "quotation_purpose",
    "payment_terms",
    "validity",
    "cover_letter_html",
    "cover_closing_html",
    "terms_html",
)


def preview_cover(
    db: Session, *, project: Project, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """The cover as it would print now, from the form's unsaved values.

    Works on plain namespaces, never an ORM row, so nothing is added to the session: no number is
    drawn from the numbering rule and no row is written. A saved quotation (``document_id``) shows
    its own number; an unsaved one shows a placeholder. Merge fields are filled from the same
    context a save uses, and an unknown one is refused with the same 422.
    """
    from types import SimpleNamespace

    from app.services import project_quotation_template_service as templates

    for field in TOKEN_FIELDS:
        templates.assert_tokens_known(payload.get(field))
    document_id = payload.get("document_id")
    if document_id:
        saved = get_document_or_404(db, str(project.id), str(document_id))
        base = {field: getattr(saved, field) for field in _PREVIEW_FIELDS}
        base.update(
            document_no=saved.document_no,
            subject_title=saved.subject_title,
            created_by=saved.created_by,
            company_id=saved.company_id,
            kind=saved.kind,
        )
        issue_no = next_issue_no(db, saved.id)
        next_label = _next_label(db, saved, issue_no)
        total = document_total(db, saved)
    else:
        base = {field: None for field in _PREVIEW_FIELDS}
        base.update(_recipient_from_project(db, project))
        base.update(
            doc_date=date.today(),
            document_no="NEW",
            subject_title=project.title,
            created_by=None,
            company_id=project.company_id,
            kind=KIND_PROPOSAL,
        )
        issue_no = 1
        next_label = revision_letter(1)
        total = ZERO
    for field in _PREVIEW_FIELDS:
        if field in payload:
            base[field] = payload[field]
    document = SimpleNamespace(project_id=project.id, **base)
    context = templates.build_document_context(db, document=document, grand_total=total)
    for field in TOKEN_FIELDS:
        setattr(document, field, templates.render(getattr(document, field), context))
    draft = SimpleNamespace(
        issue_no=issue_no,
        revision_label=next_label,
        issued_at=None,
        payment_terms=document.payment_terms,
        validity=document.validity,
        terms_rendered=document.terms_html,
    )
    active = templates.active_template(
        db, company_id=document.company_id, kind=templates.TEMPLATE_KIND_COVER_PAGE
    )
    design = active.design if active is not None and active.design else default_design()
    sender = sender_of(db, document.company_id)
    return cover_payload(
        cover_rows(db, document, draft, project, design),
        design,
        intro=document.cover_letter_html,
        closing=document.cover_closing_html,
        noun=document_noun(document),
        **sender,
    )
