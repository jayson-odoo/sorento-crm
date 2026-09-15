"""AC-S11-1..S11-3 (PLAN-price-tag-ai-extract-resolver.md D16): the PDF
render worker finds the frontend from `FRONTEND_BASE_URL` when
`DEALER_KIT_PRINT_BASE_URL` is unset, so a deploy does not need a second
setting pointed at the same place `portal_service.submission_link` already
reads.

No DB needed: `render_token.issue` is mocked so these run as pure unit tests
of the base-url resolution in `_print_url` / `_tag_sheet_print_url`.
"""
from __future__ import annotations

import pytest

from app.tasks import dealer_kit_export_tasks as tasks


@pytest.fixture(autouse=True)
def _fixed_token(monkeypatch):
    monkeypatch.setattr(
        tasks.render_token, "issue", lambda download_id, *a, **k: "tok-123"
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Neither setting exists in the ambient test environment by default.
    monkeypatch.delenv(tasks.PRINT_BASE_ENV, raising=False)


def test_ac_s11_1_falls_back_to_frontend_base_url_when_print_base_unset(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "frontend_base_url", "https://fe.example", raising=False)

    url = tasks._tag_sheet_print_url("dl-1")
    assert url.startswith("https://fe.example/c/print/tag-sheet/"), url

    url2 = tasks._print_url("dl-1")
    assert url2.startswith("https://fe.example/c/print/"), url2


def test_ac_s11_2_dealer_kit_print_base_url_wins_when_both_are_set(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "frontend_base_url", "https://fe.example", raising=False)
    monkeypatch.setenv(tasks.PRINT_BASE_ENV, "https://print.internal")

    url = tasks._tag_sheet_print_url("dl-1")
    assert url.startswith("https://print.internal/c/print/tag-sheet/"), url

    url2 = tasks._print_url("dl-1")
    assert url2.startswith("https://print.internal/c/print/"), url2


def test_ac_s11_3_falls_back_to_localhost_3000_when_neither_is_set(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "frontend_base_url", None, raising=False)

    url = tasks._tag_sheet_print_url("dl-1")
    assert url.startswith("http://localhost:3000/c/print/tag-sheet/"), url

    url2 = tasks._print_url("dl-1")
    assert url2.startswith("http://localhost:3000/c/print/"), url2
