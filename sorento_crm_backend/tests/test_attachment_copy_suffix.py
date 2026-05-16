"""Tests for the Google-Drive dup-name suffix helper used by the attachment
upload collision flow (TCK-2026-000020).

The helper is pure-function — it does not touch the DB, only chooses the next
candidate filename. The DB-aware ``_next_copy_name`` loop is exercised via
manual verification (see the ticket's curl block) because it would otherwise
require standing up the full attachments / directories schema in a test DB.
"""
from __future__ import annotations

from app.api.v1.resources.attachments import _suffix_copy_name


def test_suffix_copy_first_collision_appends_dash_copy():
    assert _suffix_copy_name("x.pdf") == "x - copy.pdf"


def test_suffix_copy_bumps_existing_copy_marker():
    assert _suffix_copy_name("x - copy.pdf") == "x - copy (2).pdf"


def test_suffix_copy_bumps_numbered_copy_marker():
    assert _suffix_copy_name("x - copy (2).pdf") == "x - copy (3).pdf"
    assert _suffix_copy_name("x - copy (9).pdf") == "x - copy (10).pdf"


def test_suffix_copy_handles_files_without_extension():
    assert _suffix_copy_name("README") == "README - copy"
    assert _suffix_copy_name("README - copy") == "README - copy (2)"


def test_suffix_copy_preserves_multi_dot_basenames():
    """Last segment after the rightmost dot is treated as the extension."""
    assert _suffix_copy_name("archive.tar.gz") == "archive.tar - copy.gz"


def test_suffix_copy_handles_uppercase_extension():
    assert _suffix_copy_name("INVOICE.PDF") == "INVOICE - copy.PDF"
