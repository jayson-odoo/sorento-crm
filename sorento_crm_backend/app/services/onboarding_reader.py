"""Read a staff phone list into people plus complaints.

The file this exists for is not a report export - it is the list a department
head already keeps. The observed shape (verified against a real one):

* a title line above the table, so the header is not row 1,
* four department sections, each introduced by a lone label cell in column A,
* the header row repeated under every one of them,
* Malaysian mobile numbers in several formats, mostly `01X-XXXXXXX`,
* half the email addresses carrying trailing whitespace,
* rows with no email at all.

Every one of those is normal input, not an error. The contract is the customer
importer's: **warnings, not errors**. A row the reader could not fully
understand comes back WITH a `RowProblem` attached rather than being dropped,
because the person who uploaded it is the only one who can fix it and she can
only fix what she is told about. The single hard failure is a header carrying no
name column at all - that is a different document.

Like every reader here, this one touches no database beyond building its alias
resolver, so it is testable against a file alone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.import_alias_service import AliasResolver, normalize_header

# The footer/rule-line filter, imported rather than re-implemented: a second
# copy is how the two readers start disagreeing about whether "GRAND TOTAL" is a
# person.
from app.services.customer_import_reader import _is_report_furniture

# One workbook entry point for the whole system, so the route that accepts an
# upload and the reader that parses it cannot disagree about what is supported.
from app.services.scm.outstanding_reader import RowProblem, sheet_rows
from app.services.phone_utils import normalize_msisdn

DOC_TYPE = "onboarding_person"

#: Only the name is required. A phone list with names and no emails is still a
#: usable list of people; a file with no name column is a different document.
REQUIRED_COLUMNS = ("full_name",)

READABLE_FIELDS = ("full_name", "nick_name", "phone", "email")

#: Enough consecutive digits to be a phone number rather than a room number.
#: Used only to keep a stray "0123456789" in column A from being mistaken for a
#: section label.
_LOOKS_LIKE_PHONE = re.compile(r"\d{7,}")

#: A Malaysian MSISDN is `60` plus a 9- or 10-digit subscriber number, so the
#: normalised form is 11 or 12 digits.
#:
#: `normalize_msisdn` is deliberately permissive - it is also the matcher that
#: links an existing user to an existing contact, where refusing an odd-looking
#: stored number would break a real link. Intake is the opposite situation: the
#: number has never been dialled, and `01x-34567` normalising to `60134567`
#: would be written to `users.contact_number` as though it were a phone number.
#: So the plausibility judgement lives HERE, where a bad number is a warning the
#: requester can act on, rather than in the shared normaliser.
_MSISDN_MIN_LEN = 11
_MSISDN_MAX_LEN = 12


def _plausible_msisdn(raw: Optional[str]) -> Optional[str]:
    """The MSISDN for a raw cell, or None when it is not a phone number.

    Returns the same bare-digits form the rest of the system stores
    (``60123456781``, no leading ``+``) so a value written here compares
    directly against ``users.contact_number`` and
    ``respond_contacts.phone_number``.
    """
    if not raw:
        return None
    normalised = normalize_msisdn(raw)
    if not normalised or not normalised.isdigit():
        return None
    if not (_MSISDN_MIN_LEN <= len(normalised) <= _MSISDN_MAX_LEN):
        return None
    return normalised


@dataclass
class OnboardingPersonRow:
    row_number: int
    full_name: str
    nick_name: Optional[str] = None
    #: Exactly as typed. What the requester is shown back.
    phone_raw: Optional[str] = None
    #: MSISDN, or None when the raw value could not be read.
    phone: Optional[str] = None
    email_raw: Optional[str] = None
    #: `lower(strip())`, or None when no email was supplied.
    email: Optional[str] = None
    section_label: Optional[str] = None
    #: Non-fatal complaints about THIS row, e.g. "phone not recognised".
    problems: list[str] = field(default_factory=list)


@dataclass
class OnboardingReadResult:
    rows: list[OnboardingPersonRow] = field(default_factory=list)
    #: Complaints that cost a row entirely (no name), plus any file-level one.
    problems: list[RowProblem] = field(default_factory=list)
    unmapped_headers: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    total_rows: int = 0
    #: Section labels in the order they appeared. Lets the intake page offer
    #: "apply this template to the whole section".
    sections: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """A file is readable when its header carries a name column.

        Individual bad rows do NOT make a file unusable: 18 people with two
        unreadable phone numbers is 18 people and two warnings.
        """
        return not self.missing_columns


def _text(value: Any) -> Optional[str]:
    """A cell as text, or None when it is blank.

    Whole floats lose the trailing `.0`, because Excel reads a numeric-looking
    phone number as a float and `60123456789.0` is not a phone number.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value)
    return s if s.strip() else None


def _map_header(raw: Any, resolver: AliasResolver) -> dict[int, str]:
    """Column index -> canonical field, for the cells of one row."""
    mapped: dict[int, str] = {}
    for pos, cell in enumerate(raw):
        resolved = resolver.field_for_header(cell)
        # First column wins for a field named twice, matching the resolver's own
        # first-alias-wins rule rather than depending on column order.
        if resolved in READABLE_FIELDS and resolved not in mapped.values():
            mapped[pos] = resolved
    return mapped


def _is_section_label(raw: tuple, col_field: dict[int, str]) -> Optional[str]:
    """The row's section label, or None if it is not one.

    A section label is a row with EXACTLY one non-empty cell that resolves to no
    field and does not look like contact details. Requiring exactly one cell is
    what keeps a real person from being eaten: a person row always carries at
    least a name and something else, and a person with only a name still fails
    the "resolves to no field" test only if their name happens to BE a column
    heading - which the repeated-header branch has already taken.
    """
    non_empty = [(pos, _text(cell)) for pos, cell in enumerate(raw) if _text(cell) is not None]
    if len(non_empty) != 1:
        return None
    pos, value = non_empty[0]
    assert value is not None
    text = value.strip()
    if not text:
        return None
    if "@" in text or _LOOKS_LIKE_PHONE.search(text):
        return None
    if _is_report_furniture(text):
        return None
    # A lone cell in a mapped column could be a person with only a name. Treat it
    # as a section label only when it sits where no field was mapped, or in the
    # name column while being written like a heading (no lowercase letters).
    if pos in col_field and col_field[pos] != "full_name":
        return None
    if pos in col_field and any(ch.islower() for ch in text):
        return None
    return text


def read_workbook(
    file_data: bytes,
    resolver: Optional[AliasResolver] = None,
    *,
    db: Optional[Session] = None,
) -> OnboardingReadResult:
    """Parse the first sheet of a staff phone list."""
    if resolver is None:
        if db is None:
            raise ValueError("read_workbook needs either a resolver or a session")
        resolver = AliasResolver.for_doc_type(db, DOC_TYPE)

    result = OnboardingReadResult()
    try:
        rows = list(sheet_rows(file_data))
    except Exception as exc:  # noqa: BLE001 - the message is for whoever uploaded it
        result.problems.append(RowProblem(0, f"could not read the workbook: {exc}"))
        result.missing_columns = list(REQUIRED_COLUMNS)
        return result

    # The header is the FIRST row that resolves a name column, not row 1: these
    # sheets carry a title line, and sometimes a blank one, above the table.
    header_idx: Optional[int] = None
    col_field: dict[int, str] = {}
    for idx, raw in enumerate(rows):
        mapped = _map_header(raw, resolver)
        if "full_name" in mapped.values():
            header_idx = idx
            col_field = mapped
            result.unmapped_headers = [
                str(cell).strip()
                for pos, cell in enumerate(raw)
                if pos not in mapped and normalize_header(cell)
            ]
            break

    if header_idx is None:
        result.missing_columns = list(REQUIRED_COLUMNS)
        return result

    # The section a sheet opens with sits ABOVE its first header row - the file
    # reads "SALES PERSON / STAFF NAME | ... / <people>". Without this the first
    # section's people carry no label at all, which is the one signal a phone
    # list gives us about their access. The LAST label-shaped row before the
    # header wins, so a company name on line 1 loses to the section on line 3.
    current_section: Optional[str] = None
    for raw in rows[:header_idx]:
        candidate = _is_section_label(raw, col_field)
        if candidate is not None:
            current_section = candidate
    if current_section is not None:
        result.sections.append(current_section)

    for offset, raw in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        # 1. The header again. It repeats under every section in the real file
        #    and must never be reported as a person.
        repeat = _map_header(raw, resolver)
        if "full_name" in repeat.values() and len(repeat) >= 2:
            continue

        # 2. A section label. Its text rides on every person under it - the only
        #    access signal a phone list carries.
        section = _is_section_label(raw, col_field)
        if section is not None:
            current_section = section
            if section not in result.sections:
                result.sections.append(section)
            continue

        values: dict[str, str] = {}
        for pos, canonical in col_field.items():
            if pos < len(raw):
                text = _text(raw[pos])
                if text is not None:
                    values[canonical] = text

        if not values:
            # A spacer. Nothing was meant by it, so it is not counted either.
            continue

        # 3. Report furniture under the table: a rule line, `*** END OF REPORT
        #    ***`, a page number. Skipped when EVERY cell the row filled in is
        #    furniture - matched on the whole cell, so a person genuinely called
        #    "Total Chin Wei" is a person and only a row that is nothing but
        #    decoration disappears.
        name = (values.get("full_name") or "").strip()
        if all(_is_report_furniture(v) for v in values.values()):
            continue

        # Every row that named something is a data row, whether or not it
        # survives: "18 people, 17 usable, 1 skipped" only adds up if the
        # skipped one is counted.
        result.total_rows += 1
        if not name:
            result.problems.append(
                RowProblem(offset, "no staff name", values.get("email") or values.get("phone") or "")
            )
            continue

        phone_raw = values.get("phone")
        phone = _plausible_msisdn(phone_raw)
        email_raw = values.get("email")
        email = email_raw.strip().lower() if email_raw and email_raw.strip() else None

        problems: list[str] = []
        if not email:
            problems.append("no email")
        if phone_raw and not phone:
            problems.append("phone not recognised")
        if not phone_raw:
            problems.append("no phone")

        result.rows.append(
            OnboardingPersonRow(
                row_number=offset,
                full_name=name,
                nick_name=(values.get("nick_name") or "").strip() or None,
                phone_raw=phone_raw,
                phone=phone,
                email_raw=email_raw,
                email=email,
                section_label=current_section,
                problems=problems,
            )
        )

    return result
