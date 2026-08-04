"""The quotation DOCUMENT: one letterhead carrying several priced scopes.

Sits above ``project_quotation_service``, which keeps owning a scope and its version chain. The
split matters: outcome is per scope and is not a property of a revision, so this module never
touches outcome, and the project's derived outcome keeps working untouched.

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

import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.numbering import DocumentNumberingRule
from app.models.projects import (
    QUOTATION_OUTCOME_LOST,
    QUOTATION_OUTCOME_WON,
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
from app.services import project_quotation_service as scope_service
from app.services.error_handler import AppException
from app.services.numbering_service import NumberingService

QUOTATION_DOC_TYPE = "project_quotation"

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


# ------------------------------------------------------------------ create


def _next_document_no(db: Session, company_id: Optional[str]) -> str:
    """From the running-number feature, so an admin can change the format without a deploy.

    Scoped to the company: a customer-facing series that two companies share is not a series.
    Falls back to a derived number only when no rule exists at all, because refusing to create a
    quotation because nobody configured a prefix would be a worse failure than an ugly reference.
    """
    number = NumberingService(db).get_next_number(
        QUOTATION_DOC_TYPE, company_id=company_id, commit_rule=False
    )
    if number:
        return number

    highest = (
        db.query(func.count(ProjectQuotationDocument.id))
        .filter(ProjectQuotationDocument.company_id == company_id)
        .scalar()
        or 0
    )
    return f"Q-{date.today().year}-{highest + 1:04d}"


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


def create_document(
    db: Session,
    *,
    project: Project,
    actor_user_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> ProjectQuotationDocument:
    payload = payload or {}
    document = ProjectQuotationDocument(
        company_id=project.company_id,
        project_id=project.id,
        document_no=payload.get("document_no") or _next_document_no(db, project.company_id),
        your_ref=payload.get("your_ref"),
        doc_date=payload.get("doc_date") or date.today(),
        attn_name=payload.get("attn_name"),
        subject_title=payload.get("subject_title") or project.title,
        cover_letter_html=payload.get("cover_letter_html"),
        terms_html=payload.get("terms_html"),
        signatory_name=payload.get("signatory_name"),
        signatory_phone=payload.get("signatory_phone"),
        created_by=actor_user_id,
        **_recipient_from_project(db, project),
    )
    db.add(document)
    db.flush()
    return document


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

    highest = (
        db.query(func.max(ProjectQuotationIssue.issue_no))
        .filter(ProjectQuotationIssue.document_id == document.id)
        .scalar()
    )
    issue_no = 1 if highest is None else int(highest) + 1

    record = ProjectQuotationIssue(
        company_id=document.company_id,
        document_id=document.id,
        issue_no=issue_no,
        our_ref_text=f"{document.document_no} (R{issue_no})",
        issued_at=datetime.utcnow(),
        issued_by=actor_user_id,
        cover_letter_rendered=document.cover_letter_html,
        terms_rendered=document.terms_html,
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
    return record


# ------------------------------------------------------------------ delete


def delete_document(db: Session, document: ProjectQuotationDocument) -> None:
    """Hard delete, and refused outright once anything has been issued.

    An issued quotation is a thing the customer holds. Deleting the record of it would leave a
    reference in their inbox that this system cannot explain, so the exit is an explicit
    withdrawal on the status graph, never a delete.
    """
    if current_issue(db, document) is not None:
        raise AppException(
            status_code=422,
            message=(
                "This quotation has been issued to the customer and cannot be deleted. "
                "Withdraw it instead."
            ),
            code="quotation_document_issued",
        )
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
        "outcome": scope.outcome,
        "current_version_id": str(version.id) if version is not None else None,
        "current_version_no": version.version_no if version is not None else None,
        "line_count": int(line_count),
        "scope_total": version_total(db, version) if version is not None else ZERO,
    }


def serialize_document(db: Session, document: ProjectQuotationDocument) -> Dict[str, Any]:
    """One document, with its tabs and its money.

    `grand_total` is summed HERE rather than by the caller, so the header, the tabs and the PDF
    cannot disagree about what a rate-only line contributes (nothing).
    """
    scopes = list_scopes(db, document)
    summaries = [_scope_summary(db, scope) for scope in scopes]
    latest = current_issue(db, document)
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
            f"{document.document_no} (R{latest.issue_no})"
            if latest is not None
            else document.document_no
        ),
        "your_ref": document.your_ref,
        "doc_date": document.doc_date,
        "recipient_party_id": (
            str(document.recipient_party_id) if document.recipient_party_id else None
        ),
        "recipient_name_snapshot": document.recipient_name_snapshot,
        "recipient_address_snapshot": document.recipient_address_snapshot,
        "recipient_phone_snapshot": document.recipient_phone_snapshot,
        "attn_name": document.attn_name,
        "subject_title": document.subject_title,
        "cover_letter_html": document.cover_letter_html,
        "terms_html": document.terms_html,
        "signatory_name": document.signatory_name,
        "signatory_phone": document.signatory_phone,
        "scopes": summaries,
        "grand_total": sum((row["scope_total"] for row in summaries), ZERO),
        "issue_count": int(issue_count),
        "current_issue_no": latest.issue_no if latest is not None else None,
        "is_issued": latest is not None,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def serialize_documents(
    db: Session, documents: List[ProjectQuotationDocument]
) -> List[Dict[str, Any]]:
    return [serialize_document(db, document) for document in documents]


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
        "our_ref_text": record.our_ref_text,
        "issued_at": record.issued_at,
        "issued_by": record.issued_by,
        "issued_by_name": name,
        "grand_total": Decimal(record.grand_total or 0),
        "scope_count": int(scope_count),
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
    """Header edits only. `document_no` is deliberately not editable: the customer has it."""
    for field in (
        "your_ref",
        "doc_date",
        "attn_name",
        "subject_title",
        "cover_letter_html",
        "terms_html",
        "signatory_name",
        "signatory_phone",
    ):
        if field in payload:
            setattr(document, field, payload[field])
    db.flush()
    return document


def update_scope(
    db: Session, *, scope: ProjectQuotation, payload: Dict[str, Any]
) -> ProjectQuotation:
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
    signature = record_signature(
        db,
        company_id=document.company_id,
        owner_kind="user",
        signer_name=payload.get("signer_name") or document.signatory_name,
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


def get_issue_by_sign_token(db: Session, token: str) -> ProjectQuotationIssue:
    """Resolve a counter-sign link, refusing anything expired or unknown with the SAME message.

    Deliberately one message for both: telling a caller that a token exists but has expired
    confirms the token, and this endpoint is public.
    """
    record = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.sign_token == token)
        .first()
    )
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
    """
    if record.accepted_at is not None:
        return record

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

    _win_the_scopes_on(db, record)
    return record


def _win_the_scopes_on(db: Session, record: ProjectQuotationIssue) -> List[ProjectQuotation]:
    """Mark every scope this issue carried as won, skipping any already lost.

    Goes through `scope_service.set_outcome` rather than setting the column, so the project's
    derived outcome is recomputed by the one function that owns that rule.
    """
    scopes = (
        db.query(ProjectQuotation)
        .join(
            ProjectQuotationIssueScope,
            ProjectQuotationIssueScope.quotation_id == ProjectQuotation.id,
        )
        .filter(ProjectQuotationIssueScope.issue_id == record.id)
        .all()
    )
    won: List[ProjectQuotation] = []
    for scope in scopes:
        if scope.outcome == QUOTATION_OUTCOME_LOST:
            continue
        if scope.outcome == QUOTATION_OUTCOME_WON:
            won.append(scope)
            continue
        scope_service.set_outcome(db, quotation=scope, outcome=QUOTATION_OUTCOME_WON)
        won.append(scope)
    db.flush()
    return won


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


def serialize_sign_page(db: Session, record: ProjectQuotationIssue) -> Dict[str, Any]:
    """The quotation as ISSUED, for the customer's read-only counter-sign page.

    Every line comes from the `version_id` the issue recorded, never from the scope's current
    version. If it read live rows, the page could show the customer something different from the
    PDF in their inbox, which is the one thing a signing surface must never do.
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
            .order_by(ProjectQuotationLine.sort_order, ProjectQuotationLine.created_at)
            .all()
        )
        scopes.append(
            {
                # The label is read live, and that is a deliberate, small exception: renaming a tab
                # does not change what was priced, and a stale label helps nobody.
                "scope_label": scope.scope_label if scope else "",
                "scope_total": Decimal(pair.scope_total or 0),
                "lines": [
                    {
                        "item_label": line.item_label,
                        "description": line.description_snapshot,
                        "technical_spec": line.technical_spec,
                        "brand": line.brand_snapshot,
                        "product_code": line.product_code_snapshot,
                        "quantity": Decimal(line.quantity or 0),
                        "unit_price": Decimal(line.unit_price or 0),
                        "complete_set": line.complete_set,
                        "band_label": line.band_label,
                        "is_rate_only": bool(line.is_rate_only),
                        # None, not zero: the page prints "rate only" and a zero would read as free.
                        "amount": None if line.is_rate_only else Decimal(line.line_total or 0),
                    }
                    for line in lines
                ],
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

    company_name = None
    if document is not None and document.company_id:
        from app.models.company import Company

        company = (
            db.query(Company).filter(Company.id == document.company_id).first()
        )
        company_name = company.name if company else None

    return {
        "our_ref": record.our_ref_text,
        "issue_no": record.issue_no,
        "doc_date": document.doc_date if document else None,
        "subject_title": document.subject_title if document else None,
        "sender_name": company_name,
        "recipient_name": document.recipient_name_snapshot if document else None,
        "recipient_address": document.recipient_address_snapshot if document else None,
        "attn_name": document.attn_name if document else None,
        "cover_letter": record.cover_letter_rendered,
        "terms": record.terms_rendered,
        "signatory_name": document.signatory_name if document else None,
        "scopes": scopes,
        "grand_total": Decimal(record.grand_total or 0),
        "sorento_signature": _serialize_signature(sorento),
        "customer_signature": _serialize_signature(customer),
        "accepted_at": record.accepted_at,
        "is_accepted": record.accepted_at is not None,
    }
