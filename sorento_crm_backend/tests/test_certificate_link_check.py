"""CERT-LINK-CLEANUP red tests: the per-link verdict rule (card R2, owner answer Q1 8 Nov).

A link is FOUND when its printed code is a whole token on the certificate (the #2245 matcher's
normalisation: spaces, hyphens, case dropped, symbol font decoded, a run of 1-4 words) AND that code is
CONTAINED in the product code as a contiguous run of 3+ characters with a digit. A digits-only code is
`check`. A code a person typed skips the containment rule. No text layer = `scanned`.
"""
from __future__ import annotations

import pymupdf
import pytest


def text_pdf(lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    y = 100
    for line in lines:
        page.insert_text((60, y), line, fontsize=11)
        y += 20
    out = doc.tobytes()
    doc.close()
    return out


def blank_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)
    out = doc.tobytes()
    doc.close()
    return out


SPAN = ["Model 14A stop valve DN20", "Model 114A pedestal", "WB 1515 wash basin", "Model 120"]


@pytest.fixture(scope="module")
def span_text():
    from app.services.certificate_pdf_service import printed_runs

    return printed_runs(text_pdf(SPAN))


def _verdict(text, code, product_code, source="ai"):
    from app.services.certificate_link_check import verdict

    return verdict(text, model_code=code, model_code_source=source, product_code=product_code)


def test_printed_runs_reports_text_and_whole_tokens(span_text):
    assert span_text["has_text"] is True
    assert "14a" in span_text["runs"]
    assert "wb1515" in span_text["runs"]  # a run crosses the space
    assert "4a" not in span_text["runs"]  # never a fragment of a word


def test_printed_runs_of_a_scan_has_no_text():
    from app.services.certificate_pdf_service import printed_runs

    assert printed_runs(blank_pdf())["has_text"] is False
    assert printed_runs(b"not a pdf")["has_text"] is False


def test_symbol_font_text_is_decoded(monkeypatch):
    """Real SPAN/WELPS PDFs report each character as U+F020..U+F0FF; shifted the way #2245's test does."""
    from app.services.certificate_pdf_service import printed_runs

    original = pymupdf.Page.get_text

    def shifted(self, option="text", *args, **kwargs):
        result = original(self, option, *args, **kwargs)
        if option != "words":
            return result
        return [(*w[:4], "".join(chr(ord(c) + 0xF000) if 0x20 <= ord(c) <= 0xFF else c for c in w[4]), *w[5:]) for w in result]

    monkeypatch.setattr(pymupdf.Page, "get_text", shifted)
    text = printed_runs(text_pdf(["Model 14A"]))
    assert "14a" in text["runs"] and text["runs"]["14a"] == "14A"


@pytest.mark.parametrize(
    "product_code",
    ["SV-14A-CP", "CSK14A-BL", "14A"],
)
def test_found_when_printed_and_contained(span_text, product_code):
    assert _verdict(span_text, "14A", product_code) == ("found", "14A")


@pytest.mark.parametrize("product_code", ["BRD7711CP", "BRHSD213C", "FUR-A11C"])
def test_not_found_when_printed_but_not_contained(span_text, product_code):
    """The towel rail, hand shower and chair on the 14A stop-valve certificate."""
    assert _verdict(span_text, "14A", product_code)[0] == "not_found"


def test_not_found_when_not_printed(span_text):
    assert _verdict(span_text, "15A", "SV-15A-CP")[0] == "not_found"


def test_whole_token_only(span_text):
    """`4A` is inside `14A` on the page but is not a printed token."""
    assert _verdict(span_text, "4A", "SV-4A-CP")[0] == "not_found"


def test_spaces_and_case_are_ignored(span_text):
    assert _verdict(span_text, "wb1515", "SRTWB1515")[0] == "found"
    assert _verdict(span_text, "WB 1515", "SRTWB1515")[0] == "found"


def test_too_short_or_no_digit_is_not_found(span_text):
    """Containment needs 3+ characters with a digit."""
    assert _verdict(span_text, "WB", "SRTWB1515")[0] == "not_found"
    assert _verdict(span_text, "Model", "MODEL-X1")[0] == "not_found"


def test_digits_only_code_is_check(span_text):
    assert _verdict(span_text, "120", "SRT120-CP") == ("check", "120")


def test_a_typed_code_skips_containment(span_text):
    assert _verdict(span_text, "14A", "BRD7711CP", source="manual") == ("found", "14A")
    assert _verdict(span_text, "15A", "BRD7711CP", source="manual")[0] == "not_found"


def test_no_code_finds_the_longest_printed_run_inside_the_product_code(span_text):
    assert _verdict(span_text, None, "SRTWB1515-W") == ("found", "WB 1515")
    assert _verdict(span_text, None, "BRD7711CP")[0] == "not_found"


def test_no_code_digits_only_hit_is_check(span_text):
    assert _verdict(span_text, None, "XX120") == ("check", "120")


def test_scanned_and_no_file():
    from app.services.certificate_link_check import verdict

    assert verdict({"has_text": False, "runs": set()}, model_code="14A", model_code_source="ai", product_code="SV-14A")[0] == "scanned"
    assert verdict(None, model_code="14A", model_code_source="ai", product_code="SV-14A")[0] == "no_file"


@pytest.mark.parametrize(
    "code,via,expect",
    [
        ("14A", "substring", True),
        ("SV-14A-CP", "exact", True),
        ("120", "substring", False),  # digits-only never fans out
        ("120", "exact", True),
        ("A1", "substring", False),  # too short
        ("ABCD", "substring", False),  # no digit
        ("SRTBV - BRASS", "prefix", False),  # family prefix is off for certificates
        ("SET-1", "product_set", True),
        ("A1 + B2", "plus_split", True),
    ],
)
def test_ingest_link_rule(code, via, expect):
    from app.services.certificate_link_check import ingest_match_allowed

    assert ingest_match_allowed(code, via) is expect


def test_ingest_printed_rule(span_text):
    from app.services.certificate_link_check import printed_on

    assert printed_on(span_text, "14A") is True
    assert printed_on(span_text, "BRD7711CP") is False
    # A scan or a missing file cannot be checked: the string is let through.
    assert printed_on({"has_text": False, "runs": set()}, "BRD7711CP") is True
    assert printed_on(None, "BRD7711CP") is True
