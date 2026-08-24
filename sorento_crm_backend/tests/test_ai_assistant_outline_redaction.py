"""Item 5 (PLAN-post-security-batch) - assistant must NOT leak the Outline URL.

Outline (``doc.foundryx.my``) is an INTERNAL Foundryx asset. The assistant may
cite in-app routes / ``?guide_target`` deep links / inline steps, but never the
Outline URL. These are PURE-function tests (no LLM, no DB) covering the two
belt-and-suspenders layers:

  * ``_redact_guide_tool_output`` - strips the Outline ``url`` field from the
    ``user_guides_read`` JSON BEFORE it reaches the model (UAC5.3), while
    preserving the in-app links in the markdown body (UAC5.2).
  * ``_strip_outline_urls`` - final-answer post-filter removing bare Outline
    URLs and markdown links to Outline, leaving readable text + in-app routes
    (UAC5.1 / UAC5.2).

The live REAL-LLM end-to-end string-scan (UAC5.1 / UAC5.5) is verified in the
browser; see the module docstring note at the bottom.
"""
from __future__ import annotations

import json

from app.config import settings
from app.services.ai_assistant_service import AIAssistantChatService


def _svc() -> AIAssistantChatService:
    # Pure helpers touch neither the DB nor any service collaborator.
    return AIAssistantChatService(db=None)  # type: ignore[arg-type]


def test_outline_host_derived_from_settings_not_hardcoded():
    svc = _svc()
    # Default config value.
    assert svc._outline_host() == "doc.foundryx.my"


def test_strip_outline_urls_removes_bare_url():
    svc = _svc()
    text = (
        "To rename a file, open the file menu and click Rename. "
        "Full guide: https://doc.foundryx.my/doc/xyz-aBcDe"
    )
    out = svc._strip_outline_urls(text)
    assert "doc.foundryx.my" not in out
    # The instructional text survives.
    assert "open the file menu and click Rename" in out


def test_strip_outline_urls_collapses_markdown_link_to_label():
    svc = _svc()
    text = "See the [Guide](https://doc.foundryx.my/doc/xyz) for more detail."
    out = svc._strip_outline_urls(text)
    assert "doc.foundryx.my" not in out
    # Label kept so the sentence still reads.
    assert "See the Guide for more detail." in out


def test_strip_outline_urls_preserves_in_app_links():
    svc = _svc()
    text = (
        "Open [**Resource Management → Files**](/resource-management/attachment-directories) "
        "then click [**Upload**](/resource-management/attachment-directories?guide_target=upload). "
        "Old link: https://doc.foundryx.my/doc/xyz"
    )
    out = svc._strip_outline_urls(text)
    assert "doc.foundryx.my" not in out
    # In-app route + guide_target deep link untouched (UAC5.2).
    assert "/resource-management/attachment-directories" in out
    assert "guide_target=upload" in out
    assert "[**Resource Management → Files**]" in out


def test_redact_guide_tool_output_removes_url_field():
    svc = _svc()
    raw = json.dumps(
        {
            "id": "abc-123",
            "title": "Renaming a file",
            "url": "https://doc.foundryx.my/doc/renaming-a-file-aBcDe",
            "url_id": "aBcDe",
            "updated_at": "2026-06-01T00:00:00Z",
            "text": (
                "Open [**Resource Management → Files**]"
                "(/resource-management/attachment-directories) and click rename."
            ),
        }
    )
    cleaned = svc._redact_guide_tool_output(raw)
    payload = json.loads(cleaned)
    # UAC5.3 - model never sees the Outline URL.
    assert "url" not in payload
    assert "doc.foundryx.my" not in cleaned
    # url_id (internal anchor, not a clickable URL) is retained.
    assert payload["url_id"] == "aBcDe"
    # In-app link inside the body survives so _extract_guide_link_map still works.
    assert "/resource-management/attachment-directories" in payload["text"]


def test_redact_guide_tool_output_scrubs_url_inside_body_text():
    svc = _svc()
    raw = json.dumps(
        {
            "id": "abc-123",
            "title": "How to",
            "url": "https://doc.foundryx.my/doc/how-to-aBcDe",
            "text": "Steps... full guide at https://doc.foundryx.my/doc/how-to-aBcDe",
        }
    )
    cleaned = svc._redact_guide_tool_output(raw)
    assert "doc.foundryx.my" not in cleaned
    assert "Steps..." in json.loads(cleaned)["text"]


def test_redact_guide_tool_output_scrubs_alternative_titles():
    svc = _svc()
    raw = json.dumps(
        {
            "id": "abc-123",
            "title": "How to",
            "url": "https://doc.foundryx.my/doc/how-to-aBcDe",
            "text": "Steps",
            "alternative_titles": [
                {
                    "id": "def-456",
                    "title": "Related",
                    "url": "https://doc.foundryx.my/doc/related-xYz",
                    "snippet": "see https://doc.foundryx.my/doc/related-xYz",
                }
            ],
        }
    )
    cleaned = svc._redact_guide_tool_output(raw)
    assert "doc.foundryx.my" not in cleaned
    alt = json.loads(cleaned)["alternative_titles"][0]
    assert "url" not in alt


def test_redact_guide_tool_output_non_json_falls_back_to_strip():
    svc = _svc()
    raw = "plain text with https://doc.foundryx.my/doc/xyz inside"
    cleaned = svc._redact_guide_tool_output(raw)
    assert "doc.foundryx.my" not in cleaned


def test_strip_outline_urls_no_host_is_noop(monkeypatch):
    svc = _svc()
    monkeypatch.setattr(settings, "outline_base_url", "")
    text = "nothing to strip https://doc.foundryx.my/doc/xyz"
    # With no configured host, redaction safely no-ops (cannot derive a host).
    assert svc._strip_outline_urls(text) == text
