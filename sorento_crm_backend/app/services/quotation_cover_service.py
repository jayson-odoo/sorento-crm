"""The quotation cover page content, shared by the PDF and the customer countersign page.

One list (``cover_rows``) feeds both surfaces so the order, labels and terms structure cannot
drift between them. The layout of an issue is one integer on the issue row
(``layout_version``): rows issued before the cover page stay 1 and keep today's layout, 2 is the
fixed cover page, 3 prints the 12-row design copied onto the issue at send (QUOTE-COVER-DESIGN),
4 prints a sections design whose rows pick a source field (QUOTE-COVER-FIELDS). Every revision
keeps printing the way it went out.
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
#: QUOTE-COVER-FIELDS: rows pick a source and sit in sections with any number of columns.
COVER_LAYOUT_SECTIONS = 4

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
    """The design a new cover page starts from: today's rows (minus Quotation Purpose, owner
    10 Nov) in one single-column section, then the Project Title band."""
    return normalize_design(DEFAULT_DESIGN)


# ------------------------------------------------------------------ sources (QUOTE-COVER-FIELDS)

#: Every field a cover row can print: key -> (caption in the picker, group, default label).
#: The resolver for each key is ``source_values``. Owner 10 Nov: Quotation Purpose is gone, and
#: Sale admin / project short name are not offered until their data exists.
SOURCES: Dict[str, tuple] = {
    "document_no": ("Document number", "Document", "Reference No."),
    "date": ("Date", "Document", "Date"),
    "project_title": ("Project title", "Document", "Project Title"),
    "total_pages": ("Total pages (PDF only)", "Document", "Total Pages"),
    "to_name": ("To: company name", "To", "Company"),
    "to_address": ("To: address", "To", "Address"),
    "to_tel": ("To: tel", "To", "Tel"),
    "to_fax": ("To: fax", "To", "Fax"),
    "to_email": ("To: email", "To", "Email"),
    "attn": ("Attn", "To", "Attn"),
    "salesperson_name": ("Salesperson: name", "Salesperson", "Sales"),
    "salesperson_email": ("Salesperson: email", "Salesperson", "Email"),
    "salesperson_mobile": ("Salesperson: mobile", "Salesperson", "Mobile"),
    "prepared_by_name": ("Prepared by: name", "Prepared by", "Name"),
    "prepared_by_phone": ("Prepared by: phone", "Prepared by", "Phone No"),
    "terms": ("Terms text", "Terms", "Terms & Conditions"),
    "payment_terms": ("Payment terms", "Terms", "Payment Terms"),
    "validity": ("Validity", "Terms", "Validity"),
    "company_name": ("Company: name", "Our company", ""),
    "company_address": ("Company: address", "Our company", ""),
    "company_tel": ("Company: tel", "Our company", "Tel"),
    "company_fax": ("Company: fax", "Our company", "Fax"),
}
SECTION_STYLES = ("fields", "title", "numbered", "signature", "footer")
MAX_COLUMNS = 6
MAX_SECTIONS = 12
MAX_ROWS = 80

#: A design saved before sources existed: its row key -> the source it prints.
_LEGACY_SOURCE = {
    "reference": "document_no",
    "date": "date",
    "attn": "attn",
    "company": "to_name",
    "contact": "to_tel",
    "address": "to_address",
    "email": "to_email",
    "terms": "terms",
    "payment_terms": "payment_terms",
    "validity": "validity",
    "prepared_by": "salesperson_name",
}


def serialize_sources() -> List[Dict[str, str]]:
    return [
        {"key": key, "caption": caption, "group": group, "default_label": label}
        for key, (caption, group, label) in SOURCES.items()
    ]


def normalize_design(raw: Dict[str, Any]) -> Dict[str, Any]:
    """A design in the sections shape. One saved before this lane (``rows`` of fixed keys) becomes
    one single-column ``fields`` section (Quotation Purpose dropped) and a Project Title band.
    Already sectioned: a copy."""
    if "sections" in raw or not isinstance(raw.get("rows"), list):
        return copy.deepcopy(raw)
    rows = [
        {
            "source": _LEGACY_SOURCE[item["key"]],
            # The old cover printed the default label for a blank one; keep that on the page.
            "label": (item.get("label") or "").strip() or ROW_LABELS[item["key"]],
            "shown": item.get("shown", True),
            "column": 0,
        }
        for item in raw["rows"]
        if isinstance(item, dict) and item.get("key") in _LEGACY_SOURCE
    ]
    return {
        "show_letterhead": raw.get("show_letterhead", True),
        "title": raw.get("title", ""),
        "closing_html": raw.get("closing_html") or "",
        "sections": [
            {"style": "fields", "label": "", "columns": 1, "rows": rows},
            # The title used to ride on Reference No.; it now prints in its own band (owner
            # 10 Nov), so a design saved before keeps printing it.
            {
                "style": "title",
                "label": "Project Title:",
                "columns": 1,
                "rows": [{"source": "project_title", "label": "", "shown": True, "column": 0}],
            },
        ],
    }


def _invalid(message: str) -> AppException:
    return AppException(status_code=422, message=message, code="quotation_cover_design_invalid")


def validate_design(raw: Any) -> Dict[str, Any]:
    """The design as stored, in the sections shape: known sources only, a column inside its
    section's column count, short labels and title, and only merge fields the system knows in the
    closing text. A design in the old 12-row shape is normalized first. Anything else is a 422,
    never trimmed."""
    from app.services import project_quotation_template_service as templates

    if not isinstance(raw, dict):
        raise _invalid("The cover page design is missing.")
    raw = normalize_design(raw)
    show_letterhead = raw.get("show_letterhead", True)
    title = raw.get("title", "")
    closing = raw.get("closing_html") or ""
    sections = raw.get("sections")
    if not isinstance(show_letterhead, bool):
        raise _invalid("Show company letterhead must be on or off.")
    if not isinstance(title, str) or len(title) > MAX_LABEL:
        raise _invalid(f"The title can hold at most {MAX_LABEL} characters.")
    if not isinstance(closing, str):
        raise _invalid("The closing text must be text.")
    if not isinstance(sections, list) or not sections:
        raise _invalid("The design needs at least one section.")
    if len(sections) > MAX_SECTIONS:
        raise _invalid(f"A design can hold at most {MAX_SECTIONS} sections.")
    clean_sections: List[Dict[str, Any]] = []
    total_rows = 0
    for section in sections:
        if not isinstance(section, dict):
            raise _invalid("Each section needs a style, a label, columns and rows.")
        style = section.get("style")
        label = section.get("label", "")
        columns = section.get("columns", 1)
        rows = section.get("rows")
        if style not in SECTION_STYLES:
            raise _invalid(f"Unknown section style '{style}'.")
        if not isinstance(label, str) or len(label) > MAX_LABEL:
            raise _invalid(f"A section label can hold at most {MAX_LABEL} characters.")
        if isinstance(columns, bool) or not isinstance(columns, int) or not 1 <= columns <= MAX_COLUMNS:
            raise _invalid(f"A section has 1 to {MAX_COLUMNS} columns.")
        if not isinstance(rows, list):
            raise _invalid("Each section needs its rows.")
        total_rows += len(rows)
        if total_rows > MAX_ROWS:
            raise _invalid(f"A design can hold at most {MAX_ROWS} rows.")
        clean_rows: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise _invalid("Each row needs a source, a tick, a label and a column.")
            source = row.get("source")
            row_label = row.get("label", "")
            shown = row.get("shown")
            column = row.get("column", 0)
            if source not in SOURCES:
                raise _invalid(f"Unknown source field '{source}'.")
            if not isinstance(shown, bool):
                raise _invalid("Each row needs a tick.")
            if not isinstance(row_label, str) or len(row_label) > MAX_LABEL:
                raise _invalid(f"A label can hold at most {MAX_LABEL} characters.")
            if isinstance(column, bool) or not isinstance(column, int) or not 0 <= column < columns:
                raise _invalid("A row sits in a column its section does not have.")
            clean_rows.append(
                {"source": source, "label": row_label, "shown": shown, "column": column}
            )
        clean_sections.append(
            {"style": style, "label": label, "columns": columns, "rows": clean_rows}
        )
    if len(closing) > MAX_HTML:
        raise _invalid(f"The closing text can hold at most {MAX_HTML} characters.")
    templates.assert_tokens_known(closing)
    return {
        "show_letterhead": show_letterhead,
        "title": title,
        "closing_html": closing,
        "sections": clean_sections,
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
    if layout_of(issue) >= COVER_LAYOUT_SECTIONS:
        # Owner 10 Nov: Reference No. is the number; the title prints in its own section.
        return number
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
        # Only layout 2 / 3 revisions reach here, and they reprint as they went out, Purpose row
        # included. A new revision is layout 4, whose sources carry no Purpose (PFC-5, QCF D1).
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


def _salesperson(db: Session, project: Any, document: Any) -> Any:
    """The project's salesperson user (owner, else the quotation's creator), as
    ``salesperson_of`` resolves the name."""
    from app.models.user import User

    owner_id = (getattr(project, "owner_user_id", None) if project is not None else None) or getattr(
        document, "created_by", None
    )
    if not owner_id:
        return None
    return db.query(User).filter(User.id == owner_id).first()


def _company_values(db: Session, company_id: Optional[str]) -> Dict[str, str]:
    """The issuing company as the PDF letterhead prints it (``_sender`` in the PDF service): the
    name off ``companies``, address / Tel / Fax off the one ``system_settings`` row."""
    from app.models.company import Company
    from app.models.user import SystemSetting

    company = (
        db.query(Company).filter(Company.id == str(company_id)).first() if company_id else None
    )
    settings = db.query(SystemSetting).order_by(SystemSetting.id).first()
    name = company.name if company is not None else None
    if not name and settings is not None:
        name = settings.name

    def text_of(value: Any) -> str:
        return str(value).strip() if value else ""

    return {
        "company_name": text_of(name),
        "company_address": text_of(getattr(settings, "address", None)),
        "company_tel": text_of(getattr(settings, "support_phone", None)),
        "company_fax": text_of(getattr(settings, "fax", None)),
    }


def source_values(
    db: Session, document: Any, issue: Any, project: Optional[Project] = None
) -> Dict[str, str]:
    """Source key -> value for one issue (or a draft shaped like one). Terms as cleaned html, the
    rest as text. Terms, payment terms and validity come off the issue (frozen at issue); the rest
    is live. Total pages is empty here: only the PDF knows its page count."""
    from app.services.project_quotation_document_service import quotation_no

    if project is None and getattr(document, "project_id", None):
        project = db.query(Project).filter(Project.id == document.project_id).first()

    def clean(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    person = _salesperson(db, project, document)
    title = clean(getattr(document, "subject_title", None)) or clean(
        getattr(project, "title", None) if project is not None else None
    )
    values = {
        "document_no": quotation_no(document.document_no, issue.issue_no, issue.revision_label),
        "date": _date_text(getattr(document, "doc_date", None) or issue.issued_at),
        "project_title": title,
        "total_pages": "",
        "to_name": clean(getattr(document, "recipient_name_snapshot", None)),
        "to_address": clean(getattr(document, "recipient_address_snapshot", None)),
        "to_tel": clean(getattr(document, "recipient_phone_snapshot", None)),
        "to_fax": clean(getattr(document, "recipient_fax_snapshot", None)),
        "to_email": clean(getattr(document, "recipient_email_snapshot", None)),
        "attn": clean(getattr(document, "attn_name", None)),
        "salesperson_name": clean(person.name if person is not None else None),
        "salesperson_email": clean(person.email if person is not None else None),
        "salesperson_mobile": clean(person.contact_number if person is not None else None),
        "prepared_by_name": clean(getattr(document, "signatory_name", None)),
        "prepared_by_phone": clean(getattr(document, "signatory_phone", None)),
        "terms": clean_terms_html(issue.terms_rendered),
        "payment_terms": clean(issue.payment_terms),
        "validity": clean(issue.validity),
    }
    values.update(_company_values(db, getattr(document, "company_id", None)))
    return values


def sections_for_design(
    values: Dict[str, str], design: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """The design's sections with their values: ``{style, label, columns, cells}``, ``cells`` one
    list per column of ``{source, label, text}`` (terms carries ``html``). Unticked and empty rows
    drop; a section left with no rows drops; an empty column keeps its place."""
    out: List[Dict[str, Any]] = []
    for section in design.get("sections") or []:
        columns = int(section.get("columns") or 1)
        cells: List[List[Dict[str, Any]]] = [[] for _ in range(columns)]
        for item in section.get("rows") or []:
            source = item["source"]
            value = values.get(source) or ""
            if not item.get("shown", True) or not value:
                continue
            column = min(max(int(item.get("column") or 0), 0), columns - 1)
            cell: Dict[str, Any] = {"source": source, "label": (item.get("label") or "").strip()}
            cell["html" if source == "terms" else "text"] = value
            cells[column].append(cell)
        if any(cells):
            out.append(
                {
                    "style": section["style"],
                    "label": (section.get("label") or "").strip(),
                    "columns": columns,
                    "cells": cells,
                }
            )
    return out


def flat_rows(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The sections as the old ``cover_rows`` list (section order, column by column), so a reader
    asking "is there a cover" or "do the terms print on it" keeps working."""
    rows: List[Dict[str, Any]] = []
    for section in sections:
        for column in section["cells"]:
            for cell in column:
                row = {"key": cell["source"], "label": cell["label"]}
                if "html" in cell:
                    row["html"] = cell["html"]
                else:
                    row["text"] = cell["text"]
                rows.append(row)
    return rows


def cover_sections(
    db: Session,
    document: Any,
    issue: Any,
    project: Optional[Project] = None,
    design: Optional[Dict[str, Any]] = None,
    total_pages: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """The sections of one layout 4 issue (or a draft shaped like one)."""
    values = source_values(db, document, issue, project)
    if total_pages:
        values["total_pages"] = total_pages
    return sections_for_design(values, normalize_design(design or default_design()))


def cover_title(design: Dict[str, Any], noun: str = "Quotation") -> str:
    """The title a design prints: as the admin wrote it, except the unchanged default, which
    follows the document's noun (PROPOSAL / QUOTATION), as the #2088 cover does."""
    title = (design.get("title") or "").strip()
    if title.upper() == str(DEFAULT_DESIGN["title"]).upper():
        return noun.upper()
    return title


def design_of(issue: Any) -> Dict[str, Any]:
    """The design copied onto a layout 3 or 4 issue at send."""
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
    sections: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """The cover as the sign page, the Cover letter tab and the designer preview all read it.
    ``sections`` is set for a layout 4 cover; ``rows`` is then its flattened list."""
    return {
        "cover_sections": sections,
        "cover_rows": rows,
        "cover_title": cover_title(design, noun),
        "cover_show_letterhead": bool(design.get("show_letterhead", True)),
        "cover_intro_html": clean_terms_html(intro),
        "cover_closing_html": clean_terms_html(closing),
        "sender_name": sender_name,
        "sender_logo_url": sender_logo_url,
    }


# ------------------------------------------------------------------ previews (store nothing)

#: Fixed fake values for the designer preview (agreed fake phones and example.com addresses).
SAMPLE_VALUES: Dict[str, str] = {
    "document_no": "PRJQ-2026-0042-R1",
    "date": "02/11/2026",
    "project_title": "PROPOSED SUPPLY OF SANITARY WARES FOR SERI MUTIARA RESIDENCES, KAJANG",
    "total_pages": "1+3",
    "to_name": "TERAS JAYA BUILDERS SDN BHD",
    "to_address": "No. 21, Jalan Cempaka 7, 43000 Kajang, Selangor",
    "to_tel": "03-0000 0000",
    "to_fax": "03-0000 0001",
    "to_email": "buyer@example.com",
    "attn": "Ms A. Example / Mr B. Example",
    "salesperson_name": "Sales Person C",
    "salesperson_email": "sales.c@example.com",
    "salesperson_mobile": "012-000 0000",
    "prepared_by_name": "Prepared Person D",
    "prepared_by_phone": "012-000 0001",
    "terms": "<p>1. Prices are in Ringgit Malaysia.</p><p>2. Delivery within 6 weeks of order.</p>",
    "payment_terms": "30 days from invoice date",
    "validity": "30 days from quotation date",
    "company_name": "Your company",
    "company_address": "Company address line 1, line 2",
    "company_tel": "03-0000 0002",
    "company_fax": "03-0000 0003",
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
    """An unsaved design filled with the sample values (the company's own name, address, Tel and
    Fax where set); merge fields show their examples."""
    from app.services import project_quotation_template_service as templates

    clean = validate_design(design)
    templates.assert_tokens_known(body_html)
    context = {f["token"]: f["example"] for f in templates.MERGE_FIELDS}
    values = dict(SAMPLE_VALUES)
    values.update({k: v for k, v in _company_values(db, company_id).items() if v})
    sections = sections_for_design(values, clean)
    return cover_payload(
        flat_rows(sections),
        clean,
        intro=templates.render(body_html, context),
        closing=templates.render(clean["closing_html"], context),
        sections=sections,
        **sender_of(db, company_id),
    )
