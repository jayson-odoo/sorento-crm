"""Build `onboarding_phone_list.xlsx`, the reader's fixture.

The real PHONE LIST.xlsx cannot be committed - it is 18 real people's phone
numbers and corporate email addresses. This script reproduces its *shape*
exactly, which is what the reader is tested against:

* four department sections, each introduced by a lone label cell in column A,
* the header row (`STAFF NAME | NICK NAME | PHONE | EMAIL`) repeated under
  every one of them,
* Malaysian mobile numbers written with a dash, in more than one format,
* half the email addresses carrying trailing whitespace,
* one row with no email and one whose phone cannot be read,
* a `*** END OF REPORT ***` footer and a rule line, so the furniture filter is
  exercised,
* and a person legitimately called "Total Chin Wei", which the furniture filter
  must NOT swallow.

Re-run with:

    venv/bin/python tests/fixtures/make_onboarding_phone_list.py
"""
from __future__ import annotations

from pathlib import Path

import openpyxl

HEADER = ("STAFF NAME", "NICK NAME", "PHONE", "EMAIL")

SECTIONS: list[tuple[str, list[tuple[str, str, str, str | None]]]] = [
    (
        "SALES PERSON",
        [
            ("Nurul Aisyah binti Rahman", "Aisyah", "012-3456781", "aisyah@mocha.com.my "),
            ("Tan Wei Ming", "Wei", "012-3456782", "weiming@mocha.com.my"),
            ("Kavitha Subramaniam", "Kavi", "013-3456783", "kavitha@mocha.com.my  "),
            ("Mohd Faizal bin Osman", "Faizal", "011-23456784", "faizal@mocha.com.my"),
            ("Lim Siew Peng", "Siew", "016-3456785", "siewpeng@mocha.com.my "),
            # No email at all: a warning, never a dropped row.
            ("Ahmad Zulkifli bin Hashim", "Zul", "017-3456786", None),
            ("Priya Devi Ramasamy", "Priya", "+60193456787", "priya@mocha.com.my "),
            # A real person whose name starts with a furniture word. Must survive.
            ("Total Chin Wei", "Chin", "012-3456788", "chinwei@mocha.com.my"),
        ],
    ),
    (
        "SALES ADMIN",
        [
            ("Siti Nurhaliza binti Yusof", "Siti", "012-3456789", "siti@mocha.com.my"),
            ("Ng Mei Ling", "Mei", "013 345 6790", "meiling@mocha.com.my "),
            # Unreadable phone: a warning on the row, not a rejected file.
            ("Rajesh Kumar Nair", "Raj", "01x-34567", "rajesh@mocha.com.my"),
            ("Farah Nabila binti Idris", "Farah", "016-3456792", "farah@mocha.com.my"),
            ("Wong Chee Keong", "CK", "017-3456793", "cheekeong@mocha.com.my "),
            ("Nur Amirah binti Salleh", "Amirah", "019-3456794", "amirah@mocha.com.my"),
        ],
    ),
    (
        "WAREHOUSE",
        [
            ("Hassan bin Ibrahim", "Hassan", "012-3456795", "hassan@mocha.com.my"),
            ("Goh Beng Huat", "Beng", "013-3456796", "benghuat@mocha.com.my "),
        ],
    ),
    (
        "SERVICES/REPLACEMENT",
        [
            ("Suresh Manickam", "Suresh", "016-3456797", "suresh@mocha.com.my"),
            ("Azlan bin Mokhtar", "Azlan", "017-3456798", "azlan@mocha.com.my"),
        ],
    ),
]

#: How many real people the fixture holds. Asserted by the reader test, so a
#: change to the data above cannot silently weaken the assertion.
EXPECTED_PEOPLE = sum(len(rows) for _, rows in SECTIONS)


def build(path: Path) -> None:
    wb = openpyxl.Workbook()
    sheet = wb.active
    assert sheet is not None
    sheet.title = "PHONE LIST"

    # A title line above the table: the header is NOT row 1.
    sheet.append(("MOCHA SDN BHD - STAFF PHONE LIST",))
    sheet.append(())

    for label, rows in SECTIONS:
        sheet.append((label,))
        sheet.append(HEADER)
        for name, nick, phone, email in rows:
            sheet.append((name, nick, phone, email))
        sheet.append(())

    sheet.append(("-----",))
    sheet.append(("*** END OF REPORT ***",))
    sheet.append(("Page 1 of 1",))

    wb.save(path)


if __name__ == "__main__":
    target = Path(__file__).with_name("onboarding_phone_list.xlsx")
    build(target)
    print(f"wrote {target} ({EXPECTED_PEOPLE} people)")
