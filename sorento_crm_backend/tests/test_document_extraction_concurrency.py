"""Page concurrency, per-page error isolation, per-page progress and the page_text
turn (19 Aug follow-up B1-B3; PLAN-demo-followups-19aug-ladder-v2.md workstream B,
"make the PO / delivery-schedule read absolutely the fastest").

These drive `extract_document` directly against a stub provider and a monkeypatched
page renderer, so nothing here touches a real model, a real PDF or a real DB write
beyond the usage-log flush `extract_document` already does. `PageResult.page_no` is
recovered from the rendered prompt text itself (`{{page_no}}` substituted in), which
is how a test can tell which page a given `chat()` call was actually for once several
are in flight at once.
"""
from __future__ import annotations

import re
import threading
import time

import pytest

from app.config import settings as app_settings
from app.services import ai_prompt_registry, document_extraction
from app.services.document_extraction import RenderedPage, extract_document
from app.services.llm_provider import ChatResult

from ._pg_fixture import blank_session

_PAGE_NO_RE = re.compile(r"page (\d+) of (\d+)")


def _rendered_pages(count: int, *, texts: dict[int, str] | None = None) -> list[RenderedPage]:
    texts = texts or {}
    return [
        RenderedPage(image_b64=f"ZZT-img-{i}", image_mime="image/jpeg", text=texts.get(i))
        for i in range(1, count + 1)
    ]


class _StubProvider:
    """Records every call and answers deterministically from the page number it can
    read out of the prompt - the same one the real prompts substitute in."""

    name = "stub"

    def __init__(self, *, fail_pages: set[int] | None = None, reverse_delay: bool = False):
        self.fail_pages = fail_pages or set()
        self.reverse_delay = reverse_delay
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def chat(self, messages, *, images=None, **kwargs):
        prompt = messages[0]["content"]
        match = _PAGE_NO_RE.search(prompt)
        assert match, f"page marker missing from prompt: {prompt!r}"
        page_no = int(match.group(1))
        with self._lock:
            self.calls.append(
                {
                    "page_no": page_no,
                    "prompt": prompt,
                    "thread": threading.current_thread().ident,
                }
            )
        if self.reverse_delay:
            # Page 1 sleeps longest, the last page barely at all - completion order is
            # the REVERSE of page order, so an ordering assertion cannot pass by luck.
            time.sleep(0.02 * (6 - page_no))
        if page_no in self.fail_pages:
            raise RuntimeError(f"ZZT page {page_no} exploded")
        return ChatResult(
            content=f'{{"page_seen": {page_no}}}',
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
        )


@pytest.fixture(autouse=True)
def _has_a_key(monkeypatch):
    monkeypatch.setattr(app_settings, "document_ai_provider", "gemini", raising=False)
    monkeypatch.setattr(app_settings, "gemini_api_key", "ZZT-key", raising=False)


def _run(db, monkeypatch, provider, *, page_count=5, texts=None, on_page=None, concurrency=None):
    monkeypatch.setattr(
        document_extraction, "_render_pages_rich",
        lambda *a, **k: _rendered_pages(page_count, texts=texts),
    )
    monkeypatch.setattr(document_extraction, "get_provider", lambda *a, **k: provider)
    if concurrency is not None:
        monkeypatch.setattr(app_settings, "document_ai_page_concurrency", concurrency, raising=False)
    return extract_document(db, b"ZZT", "application/pdf", prompt_key="po_extractor", on_page=on_page)


# ------------------------------------------------------------------------ concurrency


def test_pages_run_concurrently_and_the_wall_time_beats_running_them_one_by_one(monkeypatch):
    provider = _StubProvider(reverse_delay=True)
    with blank_session() as db:
        result = _run(db, monkeypatch, provider, page_count=5, concurrency=5)

    # Five pages, longest single delay 0.08s (page 1). Serial would be roughly
    # 0.02*(5+4+3+2+1) = 0.30s; concurrent is bounded by the slowest one page.
    assert result.elapsed_ms < 250
    assert len(provider.calls) == 5


def test_results_stay_in_page_order_even_though_completion_order_is_reversed(monkeypatch):
    provider = _StubProvider(reverse_delay=True)
    with blank_session() as db:
        result = _run(db, monkeypatch, provider, page_count=5, concurrency=5)

    # The stub is built so page 5 answers first and page 1 last; the result must still
    # read 1..5 - `extract_document` reassembles by page_no, not by arrival.
    assert [p.page_no for p in result.pages] == [1, 2, 3, 4, 5]
    assert [p.data for p in result.pages] == [{"page_seen": n} for n in range(1, 6)]


def test_a_bad_page_does_not_fail_the_others(monkeypatch):
    provider = _StubProvider(fail_pages={3})
    with blank_session() as db:
        result = _run(db, monkeypatch, provider, page_count=5, concurrency=5)

    assert result.failed_pages == [3]
    bad = next(p for p in result.pages if p.page_no == 3)
    assert bad.data is None
    assert "exploded" in (bad.error or "")
    assert [p.page_no for p in result.ok_pages] == [1, 2, 4, 5]
    for page in result.ok_pages:
        assert page.data == {"page_seen": page.page_no}


# --------------------------------------------------------------- on_page / progress


def test_on_page_fires_once_per_page_from_the_callers_own_thread(monkeypatch):
    provider = _StubProvider(reverse_delay=True)
    seen: list[dict] = []
    main_thread = threading.current_thread().ident

    def on_page(page):
        seen.append({"page_no": page.page_no, "thread": threading.current_thread().ident})

    with blank_session() as db:
        result = _run(db, monkeypatch, provider, page_count=4, on_page=on_page, concurrency=4)

    assert len(seen) == 4
    assert {s["page_no"] for s in seen} == {1, 2, 3, 4}
    # Every callback ran on the thread that called extract_document, never on one of
    # the pool's worker threads - the whole point of keeping DB writes off the pool.
    assert {s["thread"] for s in seen} == {main_thread}
    assert len(result.pages) == 4


def test_an_on_page_that_raises_does_not_lose_the_page(monkeypatch):
    provider = _StubProvider()

    def on_page(page):
        if page.page_no == 2:
            raise RuntimeError("ZZT progress write failed")

    with blank_session() as db:
        result = _run(db, monkeypatch, provider, page_count=3, on_page=on_page, concurrency=3)

    assert [p.page_no for p in result.ok_pages] == [1, 2, 3]


# ------------------------------------------------------------------------ page_text


def test_the_page_text_layer_rides_in_the_same_turn_as_the_image(monkeypatch):
    provider = _StubProvider()
    with blank_session() as db:
        _run(
            db, monkeypatch, provider, page_count=2,
            texts={1: "STOCK CODE  QTY\nSRTWC8613-RL  927"},
            concurrency=2,
        )

    page_one = next(c for c in provider.calls if c["page_no"] == 1)
    page_two = next(c for c in provider.calls if c["page_no"] == 2)
    assert "SRTWC8613-RL" in page_one["prompt"]
    assert "authoritative" in page_one["prompt"].lower()
    # No text layer on page 2 (e.g. a scanned image) still gets the same turn shape,
    # just with an empty block - never an error, never a missing variable.
    assert "---\n\n---" in page_two["prompt"]


def test_a_page_text_layer_past_the_cap_carries_a_truncation_marker():
    """The prompt calls the text layer authoritative for codes/numbers; a page cut
    mid-token with no marker would have the model trust an incomplete reading as if
    it were the whole one."""
    raw = "A" * (document_extraction.PAGE_TEXT_CHAR_LIMIT + 500)

    capped = document_extraction._cap_page_text(raw)

    assert capped is not None
    assert capped.endswith(document_extraction._PAGE_TEXT_TRUNCATED_MARKER)
    assert len(capped) <= document_extraction.PAGE_TEXT_CHAR_LIMIT


def test_a_page_text_layer_under_the_cap_is_untouched():
    raw = "STOCK CODE  QTY\nSRTWC8613-RL  927"

    assert document_extraction._cap_page_text(raw) == raw


def test_an_empty_page_text_layer_stays_none():
    assert document_extraction._cap_page_text("") is None


def test_the_prompt_template_is_resolved_once_for_the_whole_document(monkeypatch):
    provider = _StubProvider()
    calls = {"n": 0}
    original = ai_prompt_registry.get_prompt

    def counting(db, name, *a, **k):
        calls["n"] += 1
        return original(db, name, *a, **k)

    monkeypatch.setattr(ai_prompt_registry, "get_prompt", counting)
    with blank_session() as db:
        _run(db, monkeypatch, provider, page_count=6, concurrency=6)

    assert calls["n"] == 1
