"""The quotation cover page content, shared by the PDF and the customer countersign page.

One list (``cover_rows``) feeds both surfaces so the order, labels and terms structure cannot
drift between them. The layout of an issue is one integer on the issue row
(``layout_version``): rows issued before the cover page stay 1 and keep today's layout, 2 is the
fixed cover page, 3 prints the design copied onto the issue at send (QUOTE-COVER-DESIGN).
"""
from __future__ import annotations

import copy
from datetime import date, datetime
from html import escape
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.projects import Project
from app.services.error_handler import AppException

COVER_LAYOUT = 2
COVER_LAYOUT_DESIGNED = 3

ROW_KEYS = (
    "reference",
    "date",
    "attn",
    "company",
    "contact",
    "address",
    "email",
    "purpose",
    "terms",
    "payment_terms",
    "validity",
    "prepared_by",
)
ROW_LABELS = {
    "reference": "Reference No.",
    "date": "Date",
    "attn": "Attn",
    "company": "Company",
    "contact": "Contact",
    "address": "Add",
    "email": "Email",
    "purpose": "Quotation Purpose",
    "terms": "Terms & Conditions",
    "payment_terms": "Payment Terms",
    "validity": "Validity",
    "prepared_by": "Prepared By",
}
MAX_LABEL = 60
MAX_HTML = 50000

#: The #2088 cover: every row, the #2088 labels, no intro or closing text.
DEFAULT_DESIGN: Dict[str, Any] = {
    "show_letterhead": True,
    "title": "QUOTATION",
    "rows": [{"key": k, "shown": True, "label": ROW_LABELS[k]} for k in ROW_KEYS],
    "closing_html": "",
}


def default_design() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULT_DESIGN)


def _invalid(message: str) -> AppException:
    return AppException(status_code=422, message=message, code="quotation_cover_design_invalid")


def validate_design(raw: Any) -> Dict[str, Any]:
    """The design as stored: exactly the 12 known rows once each, short label and title, and only
    merge fields the system knows in the closing text. Anything else is a 422, never trimmed."""
    from app.services import project_quotation_template_service as templates

    if not isinstance(raw, dict):
        raise _invalid("The cover page design is missing.")
    show_letterhead = raw.get("show_letterhead", True)
    title = raw.get("title", "")
    closing = raw.get("closing_html") or ""
    rows = raw.get("rows")
    if not isinstance(show_letterhead, bool):
        raise _invalid("Show company letterhead must be on or off.")
    if not isinstance(title, str) or len(title) > MAX_LABEL:
        raise _invalid(f"The title can hold at most {MAX_LABEL} characters.")
    if not isinstance(closing, str):
        raise _invalid("The closing text must be text.")
    if not isinstance(rows, list):
        raise _invalid("The design needs its rows.")
    seen: List[str] = []
    clean_rows: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise _invalid("Each row needs a key, a tick and a label.")
        key = row.get("key")
        label = row.get("label", "")
        shown = row.get("shown")
        if key not in ROW_KEYS:
            raise _invalid(f"Unknown row '{key}'. Custom rows cannot be added.")
        if key in seen:
            raise _invalid(f"The row '{ROW_LABELS[key]}' appears twice.")
        if not isinstance(shown, bool):
            raise _invalid("Each row needs a tick.")
        if not isinstance(label, str) or len(label) > MAX_LABEL:
            raise _invalid(f"A label can hold at most {MAX_LABEL} characters.")
        seen.append(key)
        clean_rows.append({"key": key, "shown": shown, "label": label})
    if sorted(seen) != sorted(ROW_KEYS):
        raise _invalid("The design must list all 12 rows once each.")
    if len(closing) > MAX_HTML:
        raise _invalid(f"The closing text can hold at most {MAX_HTML} characters.")
    templates.assert_tokens_known(closing)
    return {
        "show_letterhead": show_letterhead,
        "title": title,
        "rows": clean_rows,
        "closing_html": closing,
    }


_ALLOWED = {"p", "strong", "em", "u", "ul", "ol", "li"}
_RENAMED = {"b": "strong", "i": "em"}
_DROPPED = {"script", "style", "iframe", "object", "embed"}
_VOID_DROPPED = {"embed"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def layout_of(issue: Any) -> int:
    return int(getattr(issue, "layout_version", None) or 1)


def cover_reference(document: Any, issue: Any, project: Optional[Project]) -> str:
    from app.services.project_quotation_document_service import quotation_no

    number = quotation_no(document.document_no, issue.issue_no, issue.revision_label)
    title = (project.title or "").strip() if project is not None else ""
    return f"{number} {title}" if title else number


class _TermsCleaner(HTMLParser):
    """Allow-list reducer for the terms editor HTML. No attribute survives."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.stack: List[str] = []
        # How many of each tag are open, so "is this tag open" is O(1) rather than a stack scan.
        self.open: Dict[str, int] = {}
        self.skip = 0
        # Index into ``out`` of the open <p> and whether anything was written since.
        self.p_start: List[int] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        tag = _RENAMED.get(tag, tag)
        if tag in _VOID_DROPPED:
            return
        if tag in _DROPPED:
            self.skip += 1
            return
        if tag in _HEADINGS:
            if self.skip:
                return
            self.handle_starttag("p", attrs)
            self.handle_starttag("strong", attrs)
            return
        if self.skip:
            return
        if tag == "br":
            self.out.append("<br>")
            return
        if tag not in _ALLOWED:
            return
        self.stack.append(tag)
        self.open[tag] = self.open.get(tag, 0) + 1
        self.out.append(f"<{tag}>")
        if tag == "p":
            self.p_start.append(len(self.out))

    def handle_startendtag(self, tag: str, attrs: Any) -> None:
        if tag in _DROPPED:
            return
        self.handle_starttag(tag, attrs)
        if tag != "br":
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = _RENAMED.get(tag, tag)
        if tag in _HEADINGS:
            self.handle_endtag("strong")
            self.handle_endtag("p")
            return
        if tag in _VOID_DROPPED:
            return
        if tag in _DROPPED:
            if self.skip:
                self.skip -= 1
            return
        if self.skip or tag not in _ALLOWED or not self.open.get(tag):
            return
        while self.stack:
            top = self.stack.pop()
            self.open[top] -= 1
            self._close(top)
            if top == tag:
                break

    def _close(self, tag: str) -> None:
        if tag == "p":
            start = self.p_start.pop()
            if len(self.out) == start:
                self.out.append("&nbsp;")
        self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self.skip or not data:
            return
        self.out.append(escape(data, quote=False))

    def result(self) -> str:
        while self.stack:
            self._close(self.stack.pop())
        return "".join(self.out)


def clean_terms_html(raw: Optional[str]) -> str:
    """The terms as typed: p, br, strong, em, u, ul, ol, li only, escaped, balanced."""
    if not raw or not str(raw).strip():
        return ""
    parser = _TermsCleaner()
    parser.feed(str(raw))
    parser.close()
    return parser.result()


def _date_text(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    return ""


def issue_values(
    db: Session, document: Any, issue: Any, project: Optional[Project] = None
) -> Dict[str, str]:
    """Key -> value for the twelve rows (terms as cleaned html, the rest as text).

    Terms, payment terms and validity come off the issue (frozen at issue); the rest is live.
    """
    from app.services.project_quotation_template_service import salesperson_of

    if project is None and document.project_id:
        project = db.query(Project).filter(Project.id == document.project_id).first()

    def clean(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    return {
        "reference": cover_reference(document, issue, project),
        "date": _date_text(document.doc_date or issue.issued_at),
        "attn": clean(document.attn_name),
        "company": clean(document.recipient_name_snapshot),
        "contact": clean(document.recipient_phone_snapshot),
        "address": clean(document.recipient_address_snapshot),
        "email": clean(document.recipient_email_snapshot),
        "purpose": clean(document.quotation_purpose),
        "terms": clean_terms_html(issue.terms_rendered),
        "payment_terms": clean(issue.payment_terms),
        "validity": clean(issue.validity),
        "prepared_by": clean(salesperson_of(db, project, document)),
    }


def rows_for_design(
    values: Dict[str, str], design: Optional[Dict[str, Any]] = None, noun: str = "Quotation"
) -> List[Dict[str, Any]]:
    """Ordered ``{key, label, text}`` rows (terms carries ``html``): the design's shown rows in its
    order with its labels, empty rows dropped. No design = the #2088 cover. An unchanged default
    Purpose label follows the document's noun (Proposal / Quotation, PS-PROPOSAL-QUOTATION)."""
    design = design or DEFAULT_DESIGN
    rows: List[Dict[str, Any]] = []
    for item in design["rows"]:
        key = item["key"]
        value = values.get(key) or ""
        if not item.get("shown", True) or not value:
            continue
        label = (item.get("label") or "").strip() or ROW_LABELS[key]
        if key == "purpose" and label == ROW_LABELS["purpose"]:
            label = f"{noun} Purpose"
        if key == "terms":
            rows.append({"key": key, "label": label, "html": value})
        else:
            rows.append({"key": key, "label": label, "text": value})
    return rows


def cover_rows(
    db: Session,
    document: Any,
    issue: Any,
    project: Optional[Project] = None,
    design: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """The rows of one issue (or of a draft shaped like one) under ``design``."""
    from app.services.project_quotation_document_service import document_noun

    return rows_for_design(
        issue_values(db, document, issue, project), design, document_noun(document)
    )


def cover_title(design: Dict[str, Any], noun: str = "Quotation") -> str:
    """The title a design prints: as the admin wrote it, except the unchanged default, which
    follows the document's noun (PROPOSAL / QUOTATION), as the #2088 cover does."""
    title = (design.get("title") or "").strip()
    if title.upper() == str(DEFAULT_DESIGN["title"]).upper():
        return noun.upper()
    return title


def design_of(issue: Any) -> Dict[str, Any]:
    """The design copied onto a layout 3 issue at send."""
    return getattr(issue, "cover_design", None) or DEFAULT_DESIGN


def cover_payload(
    rows: List[Dict[str, Any]],
    design: Dict[str, Any],
    *,
    intro: Optional[str],
    closing: Optional[str],
    sender_name: Optional[str],
    sender_logo_url: Optional[str],
    noun: str = "Quotation",
) -> Dict[str, Any]:
    """The cover as the sign page, the Cover letter tab and the designer preview all read it."""
    return {
        "cover_rows": rows,
        "cover_title": cover_title(design, noun),
        "cover_show_letterhead": bool(design.get("show_letterhead", True)),
        "cover_intro_html": clean_terms_html(intro),
        "cover_closing_html": clean_terms_html(closing),
        "sender_name": sender_name,
        "sender_logo_url": sender_logo_url,
    }


# ------------------------------------------------------------------ previews (store nothing)

#: Fixed fake values for the designer preview (agreed fake phone and example.com address).
SAMPLE_VALUES: Dict[str, str] = {
    "reference": "PRJQ-2026-0042-R1 SERI MUTIARA RESIDENCES",
    "date": "02/11/2026",
    "attn": "Ms Farah Iskandar",
    "company": "TERAS JAYA BUILDERS SDN BHD",
    "contact": "012-345 6789",
    "address": "No. 21, Jalan Cempaka 7, 43000 Kajang, Selangor",
    "email": "farah@example.com",
    "purpose": "Tender submission for Block B show units",
    "terms": "<p>1. Prices are in Ringgit Malaysia.</p><p>2. Delivery within 6 weeks of order.</p>",
    "payment_terms": "30 days from invoice date",
    "validity": "30 days from quotation date",
    "prepared_by": "Aina Rahman",
}


def sender_of(db: Session, company_id: Optional[str]) -> Dict[str, Optional[str]]:
    from app.models.company import Company

    company = db.query(Company).filter(Company.id == company_id).first() if company_id else None
    return {
        "sender_name": company.name if company else None,
        "sender_logo_url": company.logo_url if company else None,
    }


def preview_design(
    db: Session, *, company_id: Optional[str], design: Any, body_html: Optional[str]
) -> Dict[str, Any]:
    """An unsaved design filled with the sample values; merge fields show their examples."""
    from app.services import project_quotation_template_service as templates

    clean = validate_design(design)
    templates.assert_tokens_known(body_html)
    context = {f["token"]: f["example"] for f in templates.MERGE_FIELDS}
    return cover_payload(
        rows_for_design(SAMPLE_VALUES, clean),
        clean,
        intro=templates.render(body_html, context),
        closing=templates.render(clean["closing_html"], context),
        **sender_of(db, company_id),
    )
