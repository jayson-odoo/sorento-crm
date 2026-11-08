"""CERT-LINK-CLEANUP red tests: the certificate ingest links only what the certificate prints (R8, Q2 (a)).

A string the reader returns links a product only when (1) it is printed as a whole token on the PDF,
when the PDF has text, and (2) it resolves through exact, product set or `+` split, or as a contained
run of 3+ characters with a digit (never digits only). The family-prefix tier stays as the last\nresort (owner 8 Nov, ruling #440 R7), its family head printed on the PDF.
A string that fails is reported in the revision's unmatched list, never dropped silently.
Reuses the ingest harness of tests/test_certificate_api.py.
"""
from __future__ import annotations

import pymupdf
import pytest

from app.models.certificate import Certificate, CertificateProduct, CertificateRevision

from .test_certificate_api import EXTERNAL, _cert_payload, env  # noqa: F401  (fixture + helper)


def _pdf(lines):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for i, line in enumerate(lines):
        page.insert_text((60, 100 + 20 * i), line, fontsize=11)
    out = doc.tobytes()
    doc.close()
    return out


@pytest.fixture
def pdf_bytes(monkeypatch):
    holder = {"data": None}

    def fake(self, attachment):
        if holder["data"] is None:
            raise Exception("no file")
        return holder["data"]

    from app.services.resources_service import AttachmentService

    monkeypatch.setattr(AttachmentService, "get_file_content_for", fake)
    return holder


def _covered_codes(env, number) -> set[str]:
    cert = env.db.query(Certificate).filter(Certificate.certificate_number == number).one()
    env.db.expire_all()
    rows = env.db.query(CertificateProduct).filter(CertificateProduct.certificate_id == cert.id).all()
    return {row.product.product_code for row in rows}


def _unmatched(env, number) -> list[str]:
    cert = env.db.query(Certificate).filter(Certificate.certificate_number == number).one()
    rev = env.db.query(CertificateRevision).filter(CertificateRevision.certificate_id == cert.id).one()
    return list(rev.unmatched_products or [])


def _post(env, number, codes):
    attachment = env.attachment(env.attachment_type(is_certificate=True, name="Certification"), number)
    payload = _cert_payload(attachment, [], certificate_number=number)
    payload["products"] = codes
    r = env.client.post(EXTERNAL, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_printed_short_code_links_only_products_that_contain_it(env, pdf_bytes):
    pdf_bytes["data"] = _pdf(["SPAN stop valve", "Model 14A DN20"])
    for code in ("SV-14A-CP", "CSK14A-BL", "BRD7711CP", "BRHSD213C", "FUR-A11C"):
        env.product("T", code=code)
    _post(env, "TIGHT-1", ["14A"])
    assert _covered_codes(env, "TIGHT-1") == {"SV-14A-CP", "CSK14A-BL"}


def test_a_string_not_printed_on_the_pdf_links_nothing_and_is_reported(env, pdf_bytes):
    pdf_bytes["data"] = _pdf(["Model 14A DN20"])
    env.product("T", code="SV-14A-CP")
    env.product("T", code="BRD7711CP")
    body = _post(env, "TIGHT-2", ["14A", "BRD7711CP"])
    assert _covered_codes(env, "TIGHT-2") == {"SV-14A-CP"}
    assert "BRD7711CP" in _unmatched(env, "TIGHT-2")
    assert "BRD7711CP" in body["skipped_product_codes"]


def test_a_family_prefix_links_its_family_as_the_last_resort(env, pdf_bytes):
    """Owner 8 Nov 21:00, applying ruling #440 R7: the family-prefix tier stays ON for certificates
    as the LAST resort. A certificate printing "SRTBV - BRASS BALL VALVE", with no exact or substring
    hit, still links the SRTBV family."""
    pdf_bytes["data"] = _pdf(["SRTBV - BRASS BALL VALVE"])
    for code in ("SRTBV10", "SRTBV20-CP", "XSRTBV30"):
        env.product("T", code=code)
    _post(env, "TIGHT-3", ["SRTBV - BRASS BALL VALVE"])
    assert _covered_codes(env, "TIGHT-3") == {"SRTBV10", "SRTBV20-CP"}
    assert _unmatched(env, "TIGHT-3") == []


def test_a_family_prefix_not_printed_links_nothing(env, pdf_bytes):
    """The prefix tier keeps the printed check: the family head must be on the PDF."""
    pdf_bytes["data"] = _pdf(["Model WB 1515 wash basin"])
    env.product("T", code="SRTBV10")
    _post(env, "TIGHT-3B", ["SRTBV - BRASS BALL VALVE"])
    assert _covered_codes(env, "TIGHT-3B") == set()
    assert _unmatched(env, "TIGHT-3B") == ["SRTBV - BRASS BALL VALVE"]


def test_a_digits_only_string_never_fans_out(env, pdf_bytes):
    pdf_bytes["data"] = _pdf(["Size 120 mm"])
    env.product("T", code="SRT120-CP")
    _post(env, "TIGHT-4", ["120"])
    assert _covered_codes(env, "TIGHT-4") == set()
    assert _unmatched(env, "TIGHT-4") == ["120"]


def test_a_short_letter_run_never_fans_out(env, pdf_bytes):
    pdf_bytes["data"] = _pdf(["Model A1"])
    env.product("T", code="SRTA1-CP")
    _post(env, "TIGHT-5", ["A1"])
    assert _covered_codes(env, "TIGHT-5") == set()


def test_an_exact_code_still_links(env, pdf_bytes):
    pdf_bytes["data"] = _pdf(["Model SRTWC8355-RL"])
    env.product("T", code="SRTWC8355-RL")
    _post(env, "TIGHT-6", ["SRTWC8355-RL"])
    assert _covered_codes(env, "TIGHT-6") == {"SRTWC8355-RL"}


def test_a_scan_skips_the_printed_check_but_not_the_tier_rule(env, pdf_bytes):
    """No text layer: the PDF cannot say no, so the printed check is skipped; the prefix and
    digits-only rules still hold."""
    doc = pymupdf.open()
    doc.new_page()
    pdf_bytes["data"] = doc.tobytes()
    doc.close()
    env.product("T", code="SV-14A-CP")
    env.product("T", code="SRT120-CP")
    _post(env, "TIGHT-7", ["14A", "120"])
    assert _covered_codes(env, "TIGHT-7") == {"SV-14A-CP"}


def test_a_renewal_adds_only_printed_links(env, pdf_bytes):
    pdf_bytes["data"] = _pdf(["Model 14A"])
    env.product("T", code="SV-14A-CP")
    env.product("T", code="BRD7711CP")
    _post(env, "TIGHT-8", ["14A"])
    _post(env, "TIGHT-8", ["14A", "BRD7711CP"])
    assert _covered_codes(env, "TIGHT-8") == {"SV-14A-CP"}


def test_a_plus_code_links_each_printed_part_even_in_separate_cells(env, pdf_bytes):
    """Reviewer round 1: parts printed apart (table cells) still link; an unprinted part does not."""
    pdf_bytes["data"] = _pdf(["Model SRTP100", "Model SRTP200"])
    env.product("T", code="SRTP100")
    env.product("T", code="SRTP200")
    env.product("T", code="SRTP300")
    _post(env, "TIGHT-9", ["SRTP100 + SRTP200 + SRTP300"])
    assert _covered_codes(env, "TIGHT-9") == {"SRTP100", "SRTP200"}
