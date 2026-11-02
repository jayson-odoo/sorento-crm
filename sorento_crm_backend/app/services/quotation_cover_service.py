"""The quotation cover page content, shared by the PDF and the customer countersign page.

One list (``cover_rows``) feeds both surfaces so the order, labels and terms structure cannot
drift between them. The layout of an issue is one integer on the issue row
(``layout_version``): rows issued before the cover page stay 1 and keep today's layout.
"""
from __future__ import annotations

from datetime import date, datetime
from html import escape
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.projects import Project

COVER_LAYOUT = 2

_ALLOWED = {"p", "strong", "em", "u", "ul", "ol", "li"}
_RENAMED = {"b": "strong", "i": "em"}
_DROPPED = {"script", "style", "iframe", "object", "embed"}


def layout_of(issue: Any) -> int:
    return int(getattr(issue, "layout_version", None) or 1)


def cover_reference(document: Any, issue: Any, project: Optional[Project]) -> str:
    from app.services.project_quotation_document_service import quotation_no

    number = quotation_no(document.document_no, issue.issue_no)
    title = (project.title or "").strip() if project is not None else ""
    return f"{number} {title}" if title else number


class _TermsCleaner(HTMLParser):
    """Allow-list reducer for the terms editor HTML. No attribute survives."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.stack: List[str] = []
        self.skip = 0
        # Index into ``out`` of the open <p> and whether anything was written since.
        self.p_start: List[int] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        tag = _RENAMED.get(tag, tag)
        if tag in _DROPPED:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "br":
            self.out.append("<br>")
            return
        if tag not in _ALLOWED:
            return
        self.stack.append(tag)
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
        if tag in _DROPPED:
            if self.skip:
                self.skip -= 1
            return
        if self.skip or tag not in _ALLOWED or tag not in self.stack:
            return
        while self.stack:
            top = self.stack.pop()
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


def cover_rows(db: Session, document: Any, issue: Any) -> List[Dict[str, Any]]:
    """Ordered ``{key, label, text}`` rows (terms carries ``html``), empty rows dropped."""
    from app.services.project_quotation_template_service import salesperson_of

    project = (
        db.query(Project).filter(Project.id == document.project_id).first()
        if document.project_id
        else None
    )

    def clean(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    plain = [
        ("reference", "Reference No.", cover_reference(document, issue, project)),
        ("date", "Date", _date_text(document.doc_date or issue.issued_at)),
        ("attn", "Attn", clean(document.attn_name)),
        ("company", "Company", clean(document.recipient_name_snapshot)),
        ("contact", "Contact", clean(document.recipient_phone_snapshot)),
        ("address", "Add", clean(document.recipient_address_snapshot)),
        ("email", "Email", clean(document.recipient_email_snapshot)),
        ("purpose", "Quotation Purpose", clean(document.quotation_purpose)),
    ]
    tail = [
        ("payment_terms", "Payment Terms", clean(document.payment_terms)),
        ("validity", "Validity", clean(document.validity)),
        ("prepared_by", "Prepared By", clean(salesperson_of(db, project, document))),
    ]
    rows: List[Dict[str, Any]] = [
        {"key": k, "label": label, "text": text} for k, label, text in plain if text
    ]
    terms = clean_terms_html(issue.terms_rendered)
    if terms:
        rows.append({"key": "terms", "label": "Terms & Conditions", "html": terms})
    rows += [{"key": k, "label": label, "text": text} for k, label, text in tail if text]
    return rows
