"""SO-LINE-OI-STATUS-UNIFY owner hand test (5 Nov 2026), item 5: a PO chip's line label printed
the raw AutoCount key ("LAED_SORENTO:45836908:45884936") - `_line_label` prefixed `L` to
`purchase_order_lines.source_ref`, which is `"{database}:{DocKey}:{DtlKey}"`, not a line
number. A label is `L<n>` for a real line number and nothing otherwise; never a raw key."""
from __future__ import annotations

from app.services.project_order_inquiry_service import ProjectOrderInquiryService

label = ProjectOrderInquiryService._line_label


def test_a_raw_autocount_key_is_never_a_line_label():
    assert label("AED_SORENTO:45836908:45884936") is None
    assert label("LAED_SORENTO:45836908:45884936") is None


def test_a_line_number_reads_l_n():
    assert label(3) == "L3"
    assert label("12") == "L12"
    assert label(" 7 ") == "L7"


def test_nothing_reads_nothing():
    assert label(None) is None
    assert label("") is None
