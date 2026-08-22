"""The company's cover letter and terms templates, and the merge fields they may use (S4, AC-E1..E4).

Three rules live here rather than being left to callers, because each one is a customer-facing
text bug rather than a visible failure:

1. **One active template per (company, kind).** "The active template" has to identify exactly one
   row. Activating deactivates the incumbent in the same transaction, and a partial unique index
   backs it up, because two concurrent activations can interleave two ordered writes.
2. **An unknown merge token is refused on SAVE, not silently rendered.** A token nobody declared
   can only become a hole in the letter or a raw ``{{token}}`` on Sorento letterhead. Save time is
   the last moment a human is looking at it, so the refusal happens there and names the tokens.
3. **Rendering is plain token substitution over stored HTML, never a template engine.** The body is
   admin-authored text destined for a customer-facing document; a general-purpose engine would
   hand whoever edits a template the ability to execute code and to reach objects the letter has
   no business seeing. The registry below is the entire vocabulary.

Rendering happens ONCE, at document create, into the document's own editable column (AC-E2). The
template is never read at print time: an admin rewriting the company letter in March must not
rewrite a quotation drafted in February, and must never touch one already issued (AC-B4 / AC-E3).
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.projects import (
    QUOTATION_TEMPLATE_KINDS,
    TEMPLATE_KIND_COVER_LETTER,
    TEMPLATE_KIND_TERMS,
    Project,
    ProjectParty,
    ProjectQuotationDocument,
    QuotationTemplate,
)
from app.services.error_handler import AppException

# ------------------------------------------------------------------ merge fields

# THE registry. Declared server-side and served to the FE picker (`GET .../merge-fields`) so the
# picker and the renderer cannot drift: a token the picker offered but the renderer did not know
# would put a hole in a letter, and it would look like a frontend bug.
#
# Every entry carries a human label and an EXAMPLE value, because "{{our_ref}}" on its own tells
# an admin nothing about what will appear in its place. Examples are read off the real artifact
# (Cabana Elmina - nadi cergas R2) rather than invented.
MERGE_FIELDS: tuple[Dict[str, str], ...] = (
    {
        "token": "project_title",
        "label": "Project title",
        "example": "Cabana Elmina Phase 2",
    },
    {
        "token": "developer_name",
        "label": "Developer",
        "example": "Nadi Cergas Sdn Bhd",
    },
    {
        "token": "recipient_name",
        "label": "Recipient (who the letter is addressed to)",
        "example": "Nadi Cergas Sdn Bhd",
    },
    {
        "token": "attn_name",
        "label": "Attention",
        "example": "Kelly",
    },
    {
        "token": "our_ref",
        "label": "Our reference",
        "example": "SRT/Q/2026/0141",
    },
    {
        "token": "doc_date",
        "label": "Quotation date",
        "example": "26 February 2026",
    },
    {
        "token": "subject_title",
        "label": "Subject line",
        "example": "CADANGAN MEMBINA PANGSAPURI RUMAH IDAMAN",
    },
    {
        "token": "grand_total",
        "label": "Grand total (no currency prefix)",
        "example": "696,923.00",
    },
    {
        "token": "salesperson_name",
        "label": "Salesperson",
        "example": "Baser Ramli",
    },
    {
        "token": "company_name",
        "label": "Our company",
        "example": "Sorento Sdn Bhd",
    },
)

MERGE_FIELD_TOKENS = tuple(field["token"] for field in MERGE_FIELDS)

# Whitespace inside the braces is tolerated ({{ our_ref }}) because an admin typing by hand will
# produce it, and refusing that would read as the feature being broken.
_TOKEN_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


def serialize_merge_fields() -> List[Dict[str, str]]:
    """The registry as the picker consumes it, placeholder included.

    The placeholder is built here rather than in the FE so there is one definition of the token
    syntax. A picker that assembled "{{" + token itself would be a second definition.
    """
    return [
        {
            "token": field["token"],
            "placeholder": "{{" + field["token"] + "}}",
            "label": field["label"],
            "example": field["example"],
        }
        for field in MERGE_FIELDS
    ]


def find_unknown_tokens(body_html: Optional[str]) -> List[str]:
    """Every ``{{token}}`` in the body that the registry does not declare, de-duplicated."""
    if not body_html:
        return []
    seen: List[str] = []
    for token in _TOKEN_PATTERN.findall(body_html):
        if token not in MERGE_FIELD_TOKENS and token not in seen:
            seen.append(token)
    return seen


def assert_tokens_known(body_html: Optional[str]) -> None:
    """Refuse a body carrying a token nothing can fill, NAMING the offenders.

    An admin cannot find a mistyped ``{{grand_totals}}`` in a page of HTML, so the message has to
    carry it. Same shape as the AI prompt registry's unknown-token block: a hard refusal at save
    time, not a warning that gets scrolled past.
    """
    unknown = find_unknown_tokens(body_html)
    if not unknown:
        return
    names = ", ".join("{{" + token + "}}" for token in unknown)
    raise AppException(
        status_code=422,
        message=(
            f"This template uses merge fields that do not exist: {names}. "
            "Pick fields from the list instead of typing them."
        ),
        code="quotation_template_unknown_merge_field",
    )


def render(body_html: Optional[str], context: Dict[str, Any]) -> Optional[str]:
    """Substitute the declared tokens, and nothing else.

    An UNKNOWN token is left verbatim rather than blanked: it can only get here through a body
    saved before its token was withdrawn from the registry, and a visible ``{{token}}`` is a
    problem somebody fixes, where a silent gap in a letter is one nobody notices.
    """
    if not body_html:
        return body_html

    def _replace(match: "re.Match[str]") -> str:
        token = match.group(1)
        if token not in MERGE_FIELD_TOKENS:
            return match.group(0)
        return _as_text(context.get(token))

    return _TOKEN_PATTERN.sub(_replace, body_html)


def _as_text(value: Any) -> str:
    """An absent fact renders as nothing at all.

    Not "-" and not "N/A": this text is prose a person will read and edit before it goes out, and
    a gap where the Attn line should be reads as unfinished, which it is. A placeholder dash would
    read as deliberate.
    """
    if value is None:
        return ""
    return str(value)


def _money(amount: Optional[Decimal]) -> str:
    """The grand total as a letter states it. `Decimal('261500.00')` reaching a page is the
    failure mode when a total is interpolated without formatting, and RM 261500.00 is not what
    Sorento sends. No currency prefix: the template author writes "RM {{grand_total}}"."""
    return f"{Decimal(amount or 0):,.2f}"


def _long_date(value: Optional[date]) -> str:
    """"26 February 2026", the way the sample workbook writes it. No leading zero on the day."""
    if value is None:
        return ""
    return f"{value.day} {value.strftime('%B')} {value.year}"


def build_document_context(
    db: Session, *, document: ProjectQuotationDocument
) -> Dict[str, Any]:
    """Everything the letter can say about this document, taken from what is already known.

    The journey's rule (Phase 0): a fact derivable from something the system already holds is
    derived, never asked. The recipient block comes off the DOCUMENT's snapshot rather than the
    party, so a letter rendered today and a letter rendered next year read the same.
    """
    from app.models.company import Company
    from app.models.user import User
    from app.services import project_quotation_document_service as documents

    project = (
        db.query(Project).filter(Project.id == document.project_id).first()
        if document.project_id
        else None
    )

    developer_name = None
    if project is not None and project.developer_party_id:
        party = (
            db.query(ProjectParty)
            .filter(ProjectParty.id == project.developer_party_id)
            .first()
        )
        developer_name = party.name if party else None

    salesperson_name = None
    owner_id = (project.owner_user_id if project is not None else None) or document.created_by
    if owner_id:
        owner = db.query(User).filter(User.id == owner_id).first()
        salesperson_name = owner.name if owner else None

    company_name = None
    if document.company_id:
        company = db.query(Company).filter(Company.id == document.company_id).first()
        company_name = company.name if company else None

    return {
        "project_title": project.title if project is not None else None,
        "developer_name": developer_name,
        "recipient_name": document.recipient_name_snapshot,
        "attn_name": document.attn_name,
        "our_ref": document.document_no,
        "doc_date": _long_date(document.doc_date),
        "subject_title": document.subject_title,
        "grand_total": _money(documents.document_total(db, document)),
        "salesperson_name": salesperson_name,
        "company_name": company_name,
    }


def render_for_document(
    db: Session, *, document: ProjectQuotationDocument, kind: str
) -> Optional[str]:
    """The active template for this document's company, rendered against this document.

    Returns None when the company has no active template of that kind: an unconfigured letter is
    an empty section with an empty state on the screen, not an error that blocks a quotation.
    """
    template = active_template(db, company_id=document.company_id, kind=kind)
    if template is None:
        return None
    return render(template.body_html, build_document_context(db, document=document))


# ------------------------------------------------------------------------- CRUD


def _assert_kind(kind: Optional[str]) -> str:
    value = (kind or "").strip()
    if value not in QUOTATION_TEMPLATE_KINDS:
        raise AppException(
            status_code=422,
            message=(
                f"Unknown template kind '{kind}'. A quotation template is either a "
                "cover_letter or terms."
            ),
            code="quotation_template_kind_invalid",
        )
    return value


def active_template(
    db: Session, *, company_id: Optional[str], kind: str
) -> Optional[QuotationTemplate]:
    """The one active template for a company and kind.

    Filtered on ``company_id`` explicitly rather than relying on the ambient request scope: this
    is also called from the create-document path and from workers, where the scope may be wider,
    and a company reading another's letterhead is a leak no screen would show.
    """
    return (
        db.query(QuotationTemplate)
        .filter(
            QuotationTemplate.company_id == company_id,
            QuotationTemplate.kind == kind,
            QuotationTemplate.is_active.is_(True),
        )
        .first()
    )


def list_templates(
    db: Session,
    *,
    company_id: Optional[str],
    kind: Optional[str] = None,
) -> List[QuotationTemplate]:
    query = db.query(QuotationTemplate).filter(QuotationTemplate.company_id == company_id)
    if kind:
        query = query.filter(QuotationTemplate.kind == _assert_kind(kind))
    return query.order_by(
        QuotationTemplate.kind.asc(),
        QuotationTemplate.is_active.desc(),
        QuotationTemplate.name.asc(),
    ).all()


def get_template_or_404(db: Session, template_id: str) -> QuotationTemplate:
    row = db.query(QuotationTemplate).filter(QuotationTemplate.id == template_id).first()
    if row is None:
        raise AppException(
            status_code=404,
            message="Quotation template not found.",
            code="quotation_template_not_found",
        )
    return row


def _deactivate_others(
    db: Session, *, company_id: Optional[str], kind: str, keep_id: Optional[str]
) -> None:
    """Clear the flag on every sibling BEFORE the new one claims it.

    Ordering matters: the partial unique index rejects two active rows, so activating first and
    clearing afterwards would fail on a company that already has one.
    """
    query = db.query(QuotationTemplate).filter(
        QuotationTemplate.company_id == company_id,
        QuotationTemplate.kind == kind,
        QuotationTemplate.is_active.is_(True),
    )
    if keep_id:
        query = query.filter(QuotationTemplate.id != keep_id)
    for row in query.all():
        row.is_active = False
    db.flush()


def create_template(
    db: Session, *, company_id: Optional[str], payload: Dict[str, Any], actor_user_id=None
) -> QuotationTemplate:
    """A new letter or terms set.

    The FIRST template of a kind is active on arrival, whatever the caller asked for: a company
    holding a template with nothing active renders an empty letter, which reads as the feature
    being broken rather than as a configuration choice.
    """
    kind = _assert_kind(payload.get("kind"))
    name = " ".join(str(payload.get("name") or "").split())
    body_html = payload.get("body_html")
    if not name:
        raise AppException(
            status_code=422,
            message="Give the template a name, e.g. Standard cover letter 2026.",
            code="quotation_template_name_required",
        )
    if not (body_html or "").strip():
        raise AppException(
            status_code=422,
            message="A template with no text renders an empty letter. Write the letter first.",
            code="quotation_template_body_required",
        )
    assert_tokens_known(body_html)

    incumbent = active_template(db, company_id=company_id, kind=kind)
    wants_active = bool(payload.get("is_active")) or incumbent is None
    if wants_active and incumbent is not None:
        _deactivate_others(db, company_id=company_id, kind=kind, keep_id=None)

    template = QuotationTemplate(
        company_id=company_id,
        kind=kind,
        name=name,
        body_html=body_html,
        is_active=wants_active,
        created_by=actor_user_id,
    )
    db.add(template)
    db.flush()
    return template


def update_template(
    db: Session, *, template: QuotationTemplate, payload: Dict[str, Any]
) -> QuotationTemplate:
    """Edit the name and the wording.

    ``is_active`` is deliberately NOT settable here: switching the active template is its own act
    with its own route, so there is one code path that deactivates the incumbent and one thing to
    read when asking how a company ended up with the letter it has. ``kind`` is not editable
    either - a letter that became terms would silently disappear from the section it was written
    for.
    """
    if "name" in payload and payload["name"] is not None:
        name = " ".join(str(payload["name"]).split())
        if not name:
            raise AppException(
                status_code=422,
                message="Give the template a name, e.g. Standard cover letter 2026.",
                code="quotation_template_name_required",
            )
        template.name = name
    if "body_html" in payload and payload["body_html"] is not None:
        body_html = payload["body_html"]
        if not str(body_html).strip():
            raise AppException(
                status_code=422,
                message="A template with no text renders an empty letter. Write the letter first.",
                code="quotation_template_body_required",
            )
        assert_tokens_known(body_html)
        template.body_html = body_html
    db.flush()
    return template


def activate_template(db: Session, *, template: QuotationTemplate) -> QuotationTemplate:
    """Make this the letter every future document carries.

    Idempotent: activating the active one is a no-op rather than a refusal, because an admin
    double-clicking has not asked for anything different.
    """
    _deactivate_others(
        db, company_id=template.company_id, kind=template.kind, keep_id=template.id
    )
    template.is_active = True
    db.flush()
    return template


def delete_template(db: Session, *, template: QuotationTemplate) -> None:
    """Hard delete, and refused for the row the company actually depends on.

    Deleting the ACTIVE template leaves the company with no letter, and nothing errors: the next
    document simply carries an empty section, so the failure surfaces as a salesperson emailing a
    blank page. The refusal names the fix instead. A superseded template is history and deletes
    cleanly - documents already rendered from it are untouched, because they hold their own copy.
    """
    if template.is_active:
        raise AppException(
            status_code=422,
            message=(
                f'"{template.name}" is the active template, and deleting it would leave this '
                "company with none. Activate another one first."
            ),
            code="quotation_template_active",
        )
    db.delete(template)
    db.flush()


# -------------------------------------------------------------------- serialize


def serialize_template(template: QuotationTemplate) -> Dict[str, Any]:
    return {
        "id": str(template.id),
        "kind": template.kind,
        "name": template.name,
        "body_html": template.body_html,
        "is_active": bool(template.is_active),
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def serialize_templates(templates: List[QuotationTemplate]) -> List[Dict[str, Any]]:
    return [serialize_template(template) for template in templates]


def count_templates(db: Session, *, company_id: Optional[str], kind: str) -> int:
    return (
        db.query(func.count(QuotationTemplate.id))
        .filter(
            QuotationTemplate.company_id == company_id,
            QuotationTemplate.kind == kind,
        )
        .scalar()
        or 0
    )


__all__ = [
    "MERGE_FIELDS",
    "MERGE_FIELD_TOKENS",
    "TEMPLATE_KIND_COVER_LETTER",
    "TEMPLATE_KIND_TERMS",
    "activate_template",
    "active_template",
    "assert_tokens_known",
    "build_document_context",
    "count_templates",
    "create_template",
    "delete_template",
    "find_unknown_tokens",
    "get_template_or_404",
    "list_templates",
    "render",
    "render_for_document",
    "serialize_merge_fields",
    "serialize_template",
    "serialize_templates",
    "update_template",
]
