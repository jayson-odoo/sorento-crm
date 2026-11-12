"""DATE-FORMAT-UNIFY: the one way the backend writes a date a person reads.

Owner, 4 Nov 2026: "all the dates need to use dd/mm/yyyy format like a standardized format
across the system". Emails, PDFs, xlsx cells written as text, chatbot replies, notifications and
remark/audit text all go through ``app.utils.date_format``; the guard at the bottom fails on a new
month-name or 12-hour strftime anywhere else in ``app/``.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import pytest

from app.utils.date_format import fmt_date, fmt_date_range, fmt_datetime, fmt_datetime_24h, fmt_maybe_date

MYT = timezone(timedelta(hours=8))


# --- fmt_date -------------------------------------------------------------------------------

def test_fmt_date_zero_pads_a_calendar_day():
    assert fmt_date(date(2026, 1, 1)) == "01/01/2026"


def test_fmt_date_reads_a_naive_datetime_as_utc_and_shows_malaysia():
    # 16:30 UTC on 31 Mar is 00:30 on 1 Apr in Malaysia.
    assert fmt_date(datetime(2026, 3, 31, 16, 30)) == "01/04/2026"


def test_fmt_date_naive_wall_clock_is_not_shifted_when_told():
    assert fmt_date(datetime(2026, 3, 31, 16, 30), naive_is_utc=False) == "31/03/2026"


def test_fmt_date_converts_an_aware_datetime():
    assert fmt_date(datetime(2026, 3, 31, 23, 0, tzinfo=MYT)) == "31/03/2026"


def test_fmt_date_parses_iso_strings():
    assert fmt_date("2026-10-01") == "01/10/2026"
    assert fmt_date("2026-03-31T16:30:00") == "01/04/2026"
    assert fmt_date("2026-03-31T16:30:00Z") == "01/04/2026"


def test_fmt_date_fallback_for_missing_or_unparseable():
    assert fmt_date(None) == ""
    assert fmt_date(None, fallback="-") == "-"
    assert fmt_date("", fallback="-") == "-"
    assert fmt_date("ASAP") == "ASAP"


# --- fmt_datetime ---------------------------------------------------------------------------

def test_fmt_datetime_is_dd_mm_yyyy_comma_h_mm_lower_am_pm():
    assert fmt_datetime(datetime(2026, 9, 30, 4, 23)) == "30/09/2026, 12:23 pm"
    assert fmt_datetime(datetime(2026, 9, 30, 16, 5)) == "01/10/2026, 12:05 am"
    assert fmt_datetime(datetime(2026, 8, 17, 1, 0)) == "17/08/2026, 9:00 am"


def test_fmt_datetime_wall_clock():
    assert fmt_datetime(datetime(2026, 8, 18, 10, 0), naive_is_utc=False) == "18/08/2026, 10:00 am"


def test_fmt_datetime_of_a_plain_date_is_the_date():
    assert fmt_datetime(date(2026, 8, 18)) == "18/08/2026"


def test_fmt_datetime_fallback():
    assert fmt_datetime(None, fallback="-") == "-"


# --- fmt_datetime_24h (crm_query answers, owner ruling 5 Nov: dd/mm/yyyy HH:MM) ---------------

def test_fmt_datetime_24h_is_dd_mm_yyyy_space_zero_padded_24_hour():
    # Naive is UTC: 17:30 UTC on 1 Oct is 01:30 on 2 Oct in Malaysia.
    assert fmt_datetime_24h(datetime(2026, 10, 1, 17, 30)) == "02/10/2026 01:30"
    assert fmt_datetime_24h(datetime(2026, 9, 30, 6, 5)) == "30/09/2026 14:05"


def test_fmt_datetime_24h_converts_an_aware_datetime():
    assert fmt_datetime_24h(datetime(2026, 9, 30, 23, 59, tzinfo=MYT)) == "30/09/2026 23:59"
    assert fmt_datetime_24h(datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc)) == "01/10/2026 00:00"


def test_fmt_datetime_24h_wall_clock_plain_date_and_fallback():
    assert fmt_datetime_24h(datetime(2026, 8, 18, 10, 0), naive_is_utc=False) == "18/08/2026 10:00"
    assert fmt_datetime_24h(date(2026, 8, 18)) == "18/08/2026"
    assert fmt_datetime_24h(None, fallback="-") == "-"


# --- fmt_date_range -------------------------------------------------------------------------

def test_fmt_date_range_joins_with_a_plain_hyphen():
    assert fmt_date_range(date(2026, 1, 1), date(2026, 3, 31)) == "01/01/2026 - 31/03/2026"


def test_fmt_date_range_one_end_or_none():
    assert fmt_date_range(date(2026, 1, 1), None) == "01/01/2026"
    assert fmt_date_range(None, "2026-03-31") == "31/03/2026"
    assert fmt_date_range(None, None, fallback="-") == "-"


# --- fmt_maybe_date: a stored value that may be a date (audit summaries) --------------------

def test_fmt_maybe_date_formats_iso_days_and_instants_and_leaves_the_rest():
    assert fmt_maybe_date("2027-06-20") == "20/06/2027"
    # Audit snapshots store naive UTC with microseconds: shown in Malaysia, the chips' shape.
    assert fmt_maybe_date("2026-11-04T11:11:55.686071") == "04/11/2026, 7:11 pm"
    assert fmt_maybe_date("2026-11-04T11:11:55+00:00") == "04/11/2026, 7:11 pm"
    assert fmt_maybe_date("Open") == "Open"
    assert fmt_maybe_date("12") == "12"
    assert fmt_maybe_date(None) is None


def test_activity_summary_line_shows_dates_in_the_one_shape():
    """Crew re-check on 094acba9 (item 4): the grey summary line read
    'Data checked at: 2026-11-04T11:11:55.686071 -> 2026-11-04T11:11:55.796621'."""
    from app.services.activity_service import _summary

    changes = [
        {"field": "Data checked at", "from": "2026-11-04T11:11:55.686071", "to": "2026-11-04T11:11:55.796621"},
        {"field": "Status", "from": "Open", "to": "Closed"},
    ]
    assert _summary("UPDATE", None, changes) == (
        "Data checked at: 04/11/2026, 7:11 pm → 04/11/2026, 7:11 pm (+1 more)"
    )
    assert _summary("UPDATE", None, [{"field": "Due", "from": None, "to": "2026-12-01"}]) == (
        "Due: - → 01/12/2026"
    )


def test_fmt_day_label_is_weekday_day_month():
    """The short day label a chip carries (the Town snapshot's last-week compare): no year."""
    from app.utils.date_format import fmt_day_label

    assert fmt_day_label(date(2026, 10, 27)) == "Tue 27 Oct"
    assert fmt_day_label(date(2026, 12, 2)) == "Wed 2 Dec"
    assert fmt_day_label("2027-01-03") == "Sun 3 Jan"
    assert fmt_day_label(None, "-") == "-"


# --- guard ----------------------------------------------------------------------------------

APP = Path(__file__).resolve().parents[1] / "app"
HELPER = APP / "utils" / "date_format.py"

# A strftime / format spec that spells a month or weekday name, or a 12-hour clock: a private
# date style. `%Y-%m-%d`, `%Y%m%d` and `%Y-%m` stay legal (keys, filenames, wire values).
_PRIVATE_STYLE = re.compile(r"""['"][^'"\n]*%[-#]?[bBaAIp][^'"\n]*['"]""")

_FSTRING_SPEC = re.compile(r"\{[^{}]*:%")


def _offenders() -> list[str]:
    out: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        if path == HELPER:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
            if "date-format-ok:" in line:
                continue
            if _PRIVATE_STYLE.search(code) and ("strftime" in code or _FSTRING_SPEC.search(code)):
                out.append(f"{path.relative_to(APP.parent)}:{n}")
    return out


_MONTH_TABLE = re.compile(r"""['"]Jan(uary)?['"],\s*['"]Feb(ruary)?['"]""")


def test_no_hand_rolled_month_name_table_outside_the_helper():
    """`f"{d.day} {_MONTHS[d.month - 1]} {d.year}"` is the same private style without strftime.
    A table that labels a MONTH bucket (or feeds the LLM prompt) carries `date-format-ok:`."""
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for m in _MONTH_TABLE.finditer(text):
            n = text.count("\n", 0, m.start())  # 0-based line of the table's first entry
            # The reason sits on that line or the two above it: a marker elsewhere in the file
            # must not silence a second table.
            if not any("date-format-ok:" in line for line in lines[max(0, n - 2): n + 1]):
                offenders.append(f"{path.relative_to(APP.parent)}:{n + 1}")
    assert offenders == []


# A dd/mm/yyyy format with a 24-hour clock (`04/11/2026 19:26`), or two dd/mm/yyyy dates joined by
# " to ": both are the right date in the wrong shape; fmt_datetime / fmt_date_range write them.
_DMY_24H = re.compile(r"""%d/%m/%Y[^'"\n]*%H""")
_DMY_TO_RANGE = re.compile(r"""%d/%m/%Y[^\n]*\bto\b[^\n]*%d/%m/%Y""")


def test_no_24_hour_dd_mm_yyyy_stamp_or_to_range_outside_the_helper():
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        if path == HELPER:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "date-format-ok:" in line or line.lstrip().startswith("#"):
                continue
            writes = "strftime" in line or _FSTRING_SPEC.search(line)  # parse lists (strptime) are input
            if writes and (_DMY_24H.search(line) or _DMY_TO_RANGE.search(line)):
                offenders.append(f"{path.relative_to(APP.parent)}:{n}")
    assert offenders == []


# A change chip's from / to is whatever the audit snapshot stored (ISO for any date column):
# text built from it goes through fmt_maybe_date, never `{c['from']}` raw.
_RAW_CHANGE_VALUE = re.compile(r"""\{\s*\w+\[['"](from|to)['"]\]""")


def test_no_raw_change_value_in_built_text():
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "date-format-ok:" in line or line.lstrip().startswith("#"):
                continue
            if _RAW_CHANGE_VALUE.search(line):
                offenders.append(f"{path.relative_to(APP.parent)}:{n}")
    assert offenders == []


def test_no_month_name_or_12_hour_date_style_outside_the_helper():
    """Mark a genuine exception (month bucket, LLM prompt) with `# date-format-ok: <reason>`."""
    assert _offenders() == []
