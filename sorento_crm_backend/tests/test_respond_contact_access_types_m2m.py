"""
Unit tests for the respond_contacts ↔ contact_access_types many-to-many access control.

Pure-Python coverage of ``PromotionService._filter_attachments_by_codes`` overlap helper.

The pivot CRUD (``set_contact_access_codes`` / ``get_contact_access_codes`` / ``resolve_contact_access_codes``)
and the SQL-level JSONB ``?|`` overlap filter are covered by the live integration test against the
running backend (Postgres) - they cannot be exercised in the SQLite test setup because the existing
models depend on PostgreSQL ``JSONB`` columns and PostgreSQL-only ``::jsonb`` cast defaults.

Run with: pytest tests/test_respond_contact_access_types_m2m.py -v
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.marketing_service import PromotionService


# ----------------------------- inline-attachment helper -----------------------------


def _make_attachment(levels):
    return SimpleNamespace(attachment=SimpleNamespace(access_levels=levels))


def test_filter_attachments_by_codes_none_keeps_everything():
    """codes=None means no contact context was supplied - keep everything."""
    atts = [_make_attachment(["dealer"]), _make_attachment([])]
    assert PromotionService._filter_attachments_by_codes(atts, None) == atts


def test_filter_attachments_by_codes_empty_codes_drops_everything():
    """codes=[] means contact has no assigned access types - overlap impossible."""
    atts = [_make_attachment(["dealer"]), _make_attachment(["end_user"])]
    assert PromotionService._filter_attachments_by_codes(atts, []) == []


def test_filter_attachments_by_codes_overlap_keeps_matches():
    atts = [
        _make_attachment(["dealer"]),
        _make_attachment(["end_user"]),
        _make_attachment(["vip", "dealer"]),
        _make_attachment([]),
        _make_attachment(None),
    ]
    kept = PromotionService._filter_attachments_by_codes(atts, ["dealer"])
    # First and third overlap with "dealer"; empty / None levels are excluded
    # (empty access_levels = visible to nobody, per chosen semantics).
    assert kept == [atts[0], atts[2]]


def test_filter_attachments_by_codes_no_overlap_returns_nothing():
    atts = [_make_attachment(["dealer"]), _make_attachment(["end_user"])]
    assert PromotionService._filter_attachments_by_codes(atts, ["vip"]) == []


def test_filter_attachments_by_codes_multi_code_overlap():
    """Contact with multiple access types - kept if ANY overlaps."""
    atts = [
        _make_attachment(["dealer"]),         # overlaps via dealer
        _make_attachment(["end_user"]),       # overlaps via end_user
        _make_attachment(["vip"]),            # overlaps via vip
        _make_attachment(["other_only"]),     # no overlap
    ]
    kept = PromotionService._filter_attachments_by_codes(atts, ["dealer", "end_user", "vip"])
    assert kept == atts[:3]
