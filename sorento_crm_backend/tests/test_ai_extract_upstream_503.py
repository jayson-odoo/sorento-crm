"""AI-EXTRACT-502: an upstream failure inside the AI extract answers 503 with the app's own
JSON message, and the provider call stops at 45 s with no SDK retries.

Owner, 2 Nov on production: the Price Tag Request "Extract" dialog showed "Bad gateway (502).
The API server is not responding ..." - the frontend's text for an HTML body
(`lib/api-client.ts`). The extract answered 502 with JSON on every provider failure, and
Cloudflare answers an origin 502 with its own branded HTML page, so the reason never reached
the dialog. Cloudflare's Error Pages do not apply to 503.

PLAN: documentation/plans/portal/PLAN-ai-extract-502-02nov.md
UAC: documentation/plans/portal/ai-extract-502-02nov-acceptance-criteria.md
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: F401  MUST be first app import (circular import)
from app.services.ai_extract import extract_service
from app.services.ai_extract.extract_service import AIExtractService, ExtractFile
from app.services.error_handler import AppException
from app.services.llm_provider import ChatResult, GeminiProvider, OpenAIProvider, ResponseTruncated
from tests._pg_fixture import blank_session, unique_code
from tests._portal_grant import grant_portal_forms

FORM = "portal.price_tag_request"
_EXTRACT = "/api/v1/public/portal/ai-extract"
_SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _text_file() -> list[ExtractFile]:
    return [ExtractFile(filename="zzt.txt", mime="text/plain", data=b"ZZT-CODE-1 x 2")]


class _Raises:
    """A provider whose call fails the way a dead key or an exhausted quota does."""

    name = "openai"

    def __init__(self, exc: BaseException):
        self.exc = exc
        self.calls: list[dict] = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        raise self.exc


class _Answers:
    name = "gemini"

    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict] = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return ChatResult(content=self.content, prompt_tokens=1, completion_tokens=1, total_tokens=2)


def _use(monkeypatch, provider, name="openai", model="zzt-model"):
    monkeypatch.setattr(
        AIExtractService, "_resolve_provider", lambda self, *a, **k: (provider, name, model)
    )


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


# ---------------------------------------------------------------------------
# AC-1 / AC-2: provider failure -> 503 with a plain message; the provider's own text
# (account details, billing hints) stays in the server log. Owner ruling, 2 Nov.
# ---------------------------------------------------------------------------

PLAIN_FAILED = "Could not read the file just now, please try again."
PLAIN_TOO_LONG = "This file is too long to read in one go; try fewer pages."
RAW = "zzt-raw Error code: 401 - incorrect API key sk-zzt1234; top up credits in Google AI Studio"


def test_provider_failure_is_503_with_a_plain_message_and_the_raw_text_in_the_log(
    db, monkeypatch, caplog
):
    _use(monkeypatch, _Raises(RuntimeError(RAW)))

    with caplog.at_level("WARNING"), pytest.raises(AppException) as caught:
        AIExtractService(db).extract(FORM, _text_file())

    assert caught.value.status_code == 503
    assert caught.value.code == "ai_extract_provider_failed"
    assert caught.value.message == PLAIN_FAILED
    assert RAW not in str(caught.value.detail)
    assert RAW in caplog.text


def _portal_post(monkeypatch, provider):
    """POST the portal Extract button's route as a real portal contact; the provider is faked."""
    from app.database import get_db
    from app.models.access import RespondContact
    from app.models.company import RespondContactCompany
    from app.models.portal import PortalToken

    _use(monkeypatch, provider)

    with blank_session() as s:

        def _override_get_db():
            yield s

        app.dependency_overrides[get_db] = _override_get_db
        try:
            contact = RespondContact(
                id=str(uuid.uuid4()),
                phone_number=f"+6011{uuid.uuid4().hex[:8]}",
                name=unique_code("extract-503"),
            )
            s.add(contact)
            s.flush()
            s.add(RespondContactCompany(respond_contact_id=contact.id, company_id=_SORENTO_COMPANY_ID))
            s.flush()
            grant_portal_forms(s, contact.id, ["price_tag_request"])
            token = PortalToken(
                id=str(uuid.uuid4()),
                token=f"ZZT-tok-{uuid.uuid4().hex}",
                contact_id=contact.id,
                space_id="ZZT-extract-503-space",
                expires_at=datetime.utcnow() + timedelta(days=30),
                verified_at=datetime.utcnow() - timedelta(minutes=5),
            )
            s.add(token)
            s.commit()

            with TestClient(app) as c:
                res = c.post(
                    _EXTRACT,
                    data={"form_key": FORM},
                    files=[("files", ("zzt.png", _TINY_PNG, "image/png"))],
                    headers={"X-Portal-Token": token.token},
                )
        finally:
            app.dependency_overrides.clear()
    return res


@pytest.mark.parametrize(
    "exc, code, message",
    [
        (RuntimeError(RAW), "ai_extract_provider_failed", PLAIN_FAILED),
        (
            ResponseTruncated(f"Gemini stopped early: MAX_TOKENS ({RAW})"),
            "ai_extract_too_long",
            PLAIN_TOO_LONG,
        ),
    ],
)
def test_portal_extract_route_answers_503_plain_json_never_the_raw_error(
    monkeypatch, exc, code, message
):
    """The owner's surface: the portal Extract button. A 502 is what Cloudflare swaps for HTML,
    and a dealer must never read the provider's own error text."""
    res = _portal_post(monkeypatch, _Raises(exc))

    assert res.status_code == 503, res.text
    assert res.headers["content-type"].startswith("application/json")
    assert res.json()["code"] == code
    assert res.json()["message"] == message
    assert "zzt-raw" not in res.text
    assert "sk-zzt1234" not in res.text


def test_portal_extract_route_never_echoes_an_unusable_answer(monkeypatch):
    """A non-JSON answer is the model's own text (it can quote the document): plain message."""
    res = _portal_post(monkeypatch, _Answers(f"not json {RAW}"))

    assert res.status_code == 503, res.text
    assert res.json()["code"] == "ai_extract_bad_json"
    assert res.json()["message"] == PLAIN_FAILED
    assert "zzt-raw" not in res.text


# ---------------------------------------------------------------------------
# AC-3: 45 s, no SDK retries, a clear message when it runs out
# ---------------------------------------------------------------------------


def test_the_provider_call_is_given_a_45_second_timeout(db, monkeypatch):
    provider = _Answers("{}")
    _use(monkeypatch, provider)

    AIExtractService(db).extract(FORM, _text_file())

    assert provider.calls[0]["timeout"] == 45


def test_openai_is_built_with_the_timeout_and_no_retries(db, monkeypatch):
    """The real OpenAI provider class: a caller-set timeout turns the SDK's 2 retries off."""
    built: list[dict] = []

    def _client(self, **overrides):
        built.append(overrides)
        raise RuntimeError("zzt-stop-before-network")

    monkeypatch.setattr(OpenAIProvider, "_client", _client)
    _use(monkeypatch, OpenAIProvider(api_key="ZZT-key", default_model="zzt-model"))

    with pytest.raises(AppException) as caught:
        AIExtractService(db).extract(FORM, _text_file())

    assert built == [{"timeout": 45, "max_retries": 0}]
    assert caught.value.status_code == 503


def test_gemini_http_call_is_capped_at_45_seconds(db, monkeypatch):
    seen: list = []

    def _request(self, method, path, *, json_body=None, params=None, timeout=None):
        seen.append(timeout)
        raise RuntimeError("zzt-stop-before-network")

    monkeypatch.setattr(GeminiProvider, "_request", _request)
    _use(monkeypatch, GeminiProvider(api_key="ZZT-key"), name="gemini", model="gemini-3.5-flash")

    with pytest.raises(AppException):
        AIExtractService(db).extract(FORM, _text_file())

    assert seen and all(t is not None and 44 < t <= 45 for t in seen), seen


def test_a_timed_out_call_is_503_saying_45_seconds(db, monkeypatch):
    _use(monkeypatch, _Raises(httpx.ReadTimeout("zzt read timed out")))

    with pytest.raises(AppException) as caught:
        AIExtractService(db).extract(FORM, _text_file())

    assert caught.value.status_code == 503
    assert caught.value.code == "ai_extract_provider_timeout"
    assert "45 seconds" in caught.value.message


def test_a_slow_provider_ends_at_the_timeout_not_the_sdk_default(db, monkeypatch):
    """Real Gemini code path, a server that answers in 3 s, the cap lowered to 0.5 s:
    the extract ends at the cap with the timeout message (in production: near 45 s). Gemini
    never waits less than 1 s per request (`llm_provider.py` `remaining()`), so "at the cap"
    here is about 1 s, still well short of the 3 s the server would take."""
    answer_after = 3.0

    def _slow_server(method, url, *, timeout=None, **kwargs):
        wait = answer_after if timeout is None else min(timeout, answer_after)
        time.sleep(wait)
        if timeout is not None and timeout < answer_after:
            raise httpx.ReadTimeout("zzt read timed out")
        raise RuntimeError("zzt the call outlived the cap")

    monkeypatch.setattr(extract_service, "EXTRACT_PROVIDER_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(httpx, "request", _slow_server)
    _use(monkeypatch, GeminiProvider(api_key="ZZT-key"), name="gemini", model="gemini-3.5-flash")

    started = time.monotonic()
    with pytest.raises(AppException) as caught:
        AIExtractService(db).extract(FORM, _text_file())
    elapsed = time.monotonic() - started

    assert caught.value.status_code == 503
    assert caught.value.code == "ai_extract_provider_timeout"
    assert "did not answer within" in caught.value.message
    assert 0.5 <= elapsed < 2.0, elapsed


# ---------------------------------------------------------------------------
# AC-4: a provider that answers with nothing usable is upstream too
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content, code",
    [
        ("", "ai_extract_empty_response"),
        ("no json here", "ai_extract_bad_json"),
        ("[1, 2]", "ai_extract_bad_json"),
        # Reviewer: an answer cut off mid-object reaches the brace-extraction branch.
        ('{"values": {"a": 1}, "products": [', "ai_extract_bad_json"),
    ],
)
def test_an_unusable_answer_is_503(db, monkeypatch, content, code):
    _use(monkeypatch, _Answers(content))

    with pytest.raises(AppException) as caught:
        AIExtractService(db).extract(FORM, _text_file())

    assert caught.value.status_code == 503
    assert caught.value.code == code
    assert caught.value.message == PLAIN_FAILED


def test_a_failed_storage_read_on_the_field_extract_is_503(db, monkeypatch):
    """The master-data field extract reads the attachment first; a storage miss is upstream too."""
    from app.models.resources import Attachment
    from app.services import storage_router

    attachment_id = str(uuid.uuid4())
    db.add(
        Attachment(
            id=attachment_id,
            original_filename="zzt-spec.pdf",
            stored_filename="zzt-spec.pdf",
            file_path="https://cdn/zzt-spec.pdf",
        )
    )
    db.commit()

    class _Bucket:
        def download_file(self, key):
            raise RuntimeError("zzt bucket unreachable")

    monkeypatch.setattr(storage_router, "extract_key", lambda path: "zzt-key")
    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: _Bucket())

    with pytest.raises(AppException) as caught:
        AIExtractService(db).extract_against_attachment("master.product_fields", attachment_id)

    assert caught.value.status_code == 503
    assert caught.value.code == "ai_extract_attachment_download_failed"


# ---------------------------------------------------------------------------
# AC-5: no configured provider never silently means OpenAI
# ---------------------------------------------------------------------------


def test_no_config_row_and_no_label_is_a_clear_400_not_openai(db, monkeypatch):
    from app.config import settings as app_settings
    from app.models.ai_assistant import AIAssistantConfig

    monkeypatch.setattr(app_settings, "openai_api_key", "ZZT-openai-env-key", raising=False)
    built: list = []
    monkeypatch.setattr(
        extract_service, "get_provider", lambda *a, **k: built.append((a, k)) or object()
    )
    assert db.query(AIAssistantConfig).count() == 0, "precondition: no AI assistant config row"

    with pytest.raises(AppException) as caught:
        AIExtractService(db)._resolve_provider(FORM)

    assert caught.value.status_code == 400
    assert caught.value.code == "ai_extract_no_provider"
    assert built == []


# ---------------------------------------------------------------------------
# AC-7 / AC-8. Production logs, 2 Nov: five portal price tag extracts answered 502 after
# 13-14 s with "Gemini stopped early: MAX_TOKENS (response truncated; thinking 0, answer
# 6138 tokens)". The extract asked for 4096 answer tokens; on gemini-3.x the call's
# maxOutputTokens is that plus 2049 thinking room, 6145, which a big promo PDF overruns.
# ---------------------------------------------------------------------------


def _gemini_needing(answer_tokens: int, seen: list):
    """A Gemini whose JSON answer needs `answer_tokens` output tokens. Under that cap it stops
    on MAX_TOKENS with half an answer, as production did on a big file."""

    def _request(self, method, path, *, json_body=None, params=None, timeout=None):
        cap = json_body["generationConfig"]["maxOutputTokens"]
        seen.append(cap)
        if cap < answer_tokens:
            return {
                "candidates": [
                    {
                        "content": {"parts": [{"text": '{"products": [{"product_code": "ZZT-1"'}]},
                        "finishReason": "MAX_TOKENS",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 900,
                    "candidatesTokenCount": cap - 7,
                    "thoughtsTokenCount": 0,
                    "totalTokenCount": 900 + cap - 7,
                },
            }
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": '{"products": [{"product_code": "ZZT-1", "product_name": "ZZT one"}]}'}]
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 900,
                "candidatesTokenCount": answer_tokens,
                "thoughtsTokenCount": 0,
                "totalTokenCount": 900 + answer_tokens,
            },
        }

    return _request


def test_the_extract_asks_for_16384_answer_tokens(db, monkeypatch):
    provider = _Answers("{}")
    _use(monkeypatch, provider)

    AIExtractService(db).extract(FORM, _text_file())

    assert provider.calls[0]["max_tokens"] == 16384


def test_a_file_that_overran_the_old_cap_now_reads(db, monkeypatch):
    """Production's case: an answer of about 6138 tokens (9000 here, past the old 6145 cap)."""
    seen: list = []
    monkeypatch.setattr(GeminiProvider, "_request", _gemini_needing(9000, seen))
    _use(monkeypatch, GeminiProvider(api_key="ZZT-key"), name="gemini", model="gemini-3.5-flash")

    result = AIExtractService(db).extract(FORM, _text_file())

    assert [p.product_code for p in result.products] == ["ZZT-1"]
    assert seen and seen[0] >= 16384, seen


def test_an_answer_too_long_even_now_is_503_saying_so(db, monkeypatch):
    """Real Gemini path, an answer no cap holds: MAX_TOKENS answers 503 with the plain words."""
    seen: list = []
    monkeypatch.setattr(GeminiProvider, "_request", _gemini_needing(10**6, seen))
    _use(monkeypatch, GeminiProvider(api_key="ZZT-key"), name="gemini", model="gemini-3.5-flash")

    with pytest.raises(AppException) as caught:
        AIExtractService(db).extract(FORM, _text_file())

    assert caught.value.status_code == 503
    assert caught.value.code == "ai_extract_too_long"
    assert caught.value.message == PLAIN_TOO_LONG


def test_a_truncated_answer_from_any_provider_is_503_too_long(db, monkeypatch):
    """A fake provider raising the shared truncation error, whatever the vendor."""
    _use(
        monkeypatch,
        _Raises(
            ResponseTruncated(
                "Gemini stopped early: MAX_TOKENS (response truncated; thinking 0, answer 6138 tokens)."
            )
        ),
    )

    with pytest.raises(AppException) as caught:
        AIExtractService(db).extract(FORM, _text_file())

    assert caught.value.status_code == 503
    assert caught.value.code == "ai_extract_too_long"
    assert caught.value.message == PLAIN_TOO_LONG


# ---------------------------------------------------------------------------
# AC-9..AC-12. Crew browser pass, 2 Nov: a 12-page / 336-row price list does not fit one call
# inside the 45 s cap (6 pages / 168 rows read in 34 s in one call). A line-item upload of MORE
# than 6 pages is read as at most 4 page groups at once (one wave, so the whole read still ends
# inside one call's cap), rows merged in page order, an exact duplicate row from a later group
# dropped, and pages that fail named in a plain note. Anything smaller stays one call (review:
# a 2-photo complaint split in two lost its second DO number).
# ---------------------------------------------------------------------------

import threading  # noqa: E402

from app.services.llm_provider import ImagePart  # noqa: E402


def _pages(monkeypatch, n: int) -> None:
    """The upload renders to `n` pages; page k's image data is "p<k>" so a fake provider can
    say which pages it was handed."""
    monkeypatch.setattr(
        AIExtractService,
        "_render_files",
        lambda self, files: [ImagePart("image/png", f"p{k}") for k in range(1, n + 1)],
    )


def _pdf() -> list[ExtractFile]:
    return [ExtractFile(filename="zzt-promo.pdf", mime="application/pdf", data=b"%PDF-zzt")]


class _PagesProvider:
    """Answers one product row per page it is handed (code ZZT-<page>), after `delay(pages)`
    seconds, or raises `fail(pages)` when that returns an exception. Records the most calls
    that were in flight at once."""

    name = "gemini"

    def __init__(self, delay=lambda pages: 0.0, fail=lambda pages: None, extra=lambda pages: []):
        self.delay, self.fail, self.extra = delay, fail, extra
        self.calls: list[list[str]] = []
        self.in_flight = 0
        self.most_in_flight = 0
        self._lock = threading.Lock()

    def chat(self, **kwargs):
        pages = [img.data_b64 for img in kwargs.get("images") or []]
        with self._lock:
            self.calls.append(pages)
            self.in_flight += 1
            self.most_in_flight = max(self.most_in_flight, self.in_flight)
        try:
            time.sleep(self.delay(pages))
            exc = self.fail(pages)
            if exc is not None:
                raise exc
            rows = [{"product_code": f"ZZT-{p}"} for p in pages] + self.extra(pages)
            import json as _json

            return ChatResult(
                content=_json.dumps({"products": rows}), prompt_tokens=10, completion_tokens=5, total_tokens=15
            )
        finally:
            with self._lock:
                self.in_flight -= 1


def _codes(result) -> list[str]:
    return [p.product_code for p in result.products]


def test_a_12_page_file_is_read_as_4_parallel_groups_merged_in_page_order(db, monkeypatch):
    """The first group is the slowest, so finish order is not page order; the rows still are."""
    _pages(monkeypatch, 12)
    provider = _PagesProvider(delay=lambda pages: 0.4 if "p1" in pages else 0.15)
    _use(monkeypatch, provider)

    started = time.monotonic()
    result = AIExtractService(db).extract(FORM, _pdf())
    elapsed = time.monotonic() - started

    assert sorted(provider.calls) == sorted(
        [["p1", "p2", "p3"], ["p4", "p5", "p6"], ["p7", "p8", "p9"], ["p10", "p11", "p12"]]
    )
    assert _codes(result) == [f"ZZT-p{k}" for k in range(1, 13)]
    assert provider.most_in_flight == 4
    assert elapsed < 1.0, elapsed  # one wave: the slow group's 0.4 s, not the sum
    assert result.note is None


def test_each_group_gets_its_own_45_second_cap_and_the_answer_budget(db, monkeypatch):
    """7 pages, just past the line: 4 groups (2, 2, 2, 1), each with the cap and the budget."""
    _pages(monkeypatch, 7)
    seen: list[dict] = []

    class _Records(_PagesProvider):
        def chat(self, **kwargs):
            seen.append({"timeout": kwargs.get("timeout"), "max_tokens": kwargs.get("max_tokens")})
            return super().chat(**kwargs)

    _use(monkeypatch, _Records())

    AIExtractService(db).extract(FORM, _pdf())

    assert seen == [{"timeout": 45, "max_tokens": 16384}] * 4


def test_a_failing_group_keeps_the_other_rows_and_names_its_pages(db, monkeypatch):
    _pages(monkeypatch, 8)
    provider = _PagesProvider(fail=lambda pages: RuntimeError(RAW) if "p5" in pages else None)
    _use(monkeypatch, provider)

    result = AIExtractService(db).extract(FORM, _pdf())

    assert _codes(result) == ["ZZT-p1", "ZZT-p2", "ZZT-p3", "ZZT-p4", "ZZT-p7", "ZZT-p8"]
    assert result.note == "Pages 5-6 could not be read, try them again."
    assert "zzt-raw" not in (result.note or "")


def test_a_slow_group_that_runs_out_keeps_the_other_rows(db, monkeypatch):
    """One page group times out (its own cap); the read does not wait for it past the cap."""
    _pages(monkeypatch, 8)
    provider = _PagesProvider(
        fail=lambda pages: httpx.ReadTimeout("zzt read timed out") if "p3" in pages else None
    )
    _use(monkeypatch, provider)

    result = AIExtractService(db).extract(FORM, _pdf())

    assert _codes(result) == ["ZZT-p1", "ZZT-p2", "ZZT-p5", "ZZT-p6", "ZZT-p7", "ZZT-p8"]
    assert result.note == "Pages 3-4 could not be read, try them again."


def test_two_failed_groups_are_named_together(db, monkeypatch):
    _pages(monkeypatch, 12)
    provider = _PagesProvider(
        fail=lambda pages: RuntimeError("zzt down") if pages[0] in ("p1", "p10") else None
    )
    _use(monkeypatch, provider)

    result = AIExtractService(db).extract(FORM, _pdf())

    assert _codes(result) == [f"ZZT-p{k}" for k in range(4, 10)]
    assert result.note == "Pages 1-3 and 10-12 could not be read, try them again."


def test_every_group_failing_is_the_503_path(db, monkeypatch):
    _pages(monkeypatch, 8)
    _use(monkeypatch, _PagesProvider(fail=lambda pages: RuntimeError(RAW)))

    with pytest.raises(AppException) as caught:
        AIExtractService(db).extract(FORM, _pdf())

    assert caught.value.status_code == 503
    assert caught.value.code == "ai_extract_provider_failed"
    assert caught.value.message == PLAIN_FAILED


def test_an_exact_duplicate_row_from_a_later_group_is_dropped(db, monkeypatch):
    """A row printed on two pages (or a repeated header line) is read twice: keep the first.
    A row that differs in any value is a different row and stays. A repeat inside ONE group
    stays too: that read saw both on its own pages, as a single call always did."""
    _pages(monkeypatch, 8)
    same = {"product_code": "ZZT-SAME", "unit_price": 10}
    per_group = {
        ("p1", "p2"): [dict(same), dict(same)],
        ("p7", "p8"): [dict(same), {**same, "unit_price": 12}],
    }
    provider = _PagesProvider(extra=lambda pages: per_group.get(tuple(pages), [dict(same)]))
    _use(monkeypatch, provider)

    result = AIExtractService(db).extract(FORM, _pdf())

    assert _codes(result) == [
        "ZZT-p1", "ZZT-p2", "ZZT-SAME", "ZZT-SAME",
        "ZZT-p3", "ZZT-p4", "ZZT-p5", "ZZT-p6", "ZZT-p7", "ZZT-p8", "ZZT-SAME",
    ]
    assert [p.unit_price for p in result.products if p.product_code == "ZZT-SAME"] == [10, 10, 12]


def test_fields_take_the_first_non_empty_value_and_lists_combine():
    """A single value (a name) takes the first page that has one; a list (DO numbers, codes)
    gathers every group's entries in page order, each once (review: keeping only the first
    group's list dropped DO-2)."""
    from app.services.ai_extract.extract_service import _merge_answers

    merged = _merge_answers(
        [
            {"customer_name": "", "delivery_order_number": ["DO-1"], "products": [{"product_code": "A"}]},
            {"customer_name": "ZZT Customer", "delivery_order_number": ["DO-2", "DO-1"],
             "products": [{"product_code": "B"}]},
            {"customer_name": "ZZT Other", "delivery_order_number": None},
        ]
    )

    assert merged["customer_name"] == "ZZT Customer"
    assert merged["delivery_order_number"] == ["DO-1", "DO-2"]
    assert merged["products"] == [{"product_code": "A"}, {"product_code": "B"}]


@pytest.mark.parametrize(
    "form_key, pages",
    [
        (FORM, 1),
        (FORM, 6),  # crew: 6 pages / 168 rows read in 34 s in one call
        ("portal.complaint", 2),  # review: two photos, two DO numbers, read together
    ],
)
def test_an_upload_of_up_to_6_pages_is_still_one_call(db, monkeypatch, form_key, pages):
    _pages(monkeypatch, pages)
    provider = _PagesProvider()
    _use(monkeypatch, provider)

    AIExtractService(db).extract(form_key, _pdf())

    assert provider.calls == [[f"p{k}" for k in range(1, pages + 1)]]


def test_an_8_photo_complaint_is_exactly_one_extract_call(db, monkeypatch):
    """Review, round 4 (crew ruling a17992588): a complaint lists a few affected products, so a
    split buys no speed, and read apart its photos gave near-duplicate rows and one group's
    defect description. Only price tag, purchase and sponsorship uploads are split."""
    _pages(monkeypatch, 8)
    provider = _PagesProvider()
    _use(monkeypatch, provider)

    AIExtractService(db).extract("portal.complaint", _pdf())

    assert provider.calls == [[f"p{k}" for k in range(1, 9)]]


@pytest.mark.parametrize(
    "form_key", ["portal.price_tag_request", "portal.purchase_request", "portal.sponsorship_form"]
)
def test_the_three_list_forms_split_past_6_pages(db, monkeypatch, form_key):
    _pages(monkeypatch, 8)
    provider = _PagesProvider()
    _use(monkeypatch, provider)

    AIExtractService(db).extract(form_key, _pdf())

    assert sorted(provider.calls) == [["p1", "p2"], ["p3", "p4"], ["p5", "p6"], ["p7", "p8"]]


@pytest.mark.parametrize("form_key", ["portal.stock_inquiry", "master.product_fields"])
def test_a_form_without_line_items_is_never_split(db, monkeypatch, form_key):
    """Its answer is one set of fields, not rows per page: read apart, fields would be lost."""
    _pages(monkeypatch, 12)
    provider = _PagesProvider()
    _use(monkeypatch, provider)

    AIExtractService(db).extract(form_key, _pdf())

    assert len(provider.calls) == 1


def test_pasted_text_is_read_once_with_the_first_group(db, monkeypatch):
    _pages(monkeypatch, 8)
    seen: dict[str, bool] = {}

    class _Records(_PagesProvider):
        def chat(self, **kwargs):
            first = kwargs["images"][0].data_b64
            seen[first] = "ZZT-PASTED-LINE" in str(kwargs["messages"])
            return super().chat(**kwargs)

    _use(monkeypatch, _Records())
    files = _pdf() + [ExtractFile(filename="paste.txt", mime="text/plain", data=b"ZZT-PASTED-LINE x 3")]

    AIExtractService(db).extract(FORM, files)

    assert seen == {"p1": True, "p3": False, "p5": False, "p7": False}


def test_a_video_is_not_split_its_frames_are_read_together(db, monkeypatch):
    """Frames of one clip show the same products; read apart they would come back as near-copies."""
    _pages(monkeypatch, 8)
    provider = _PagesProvider()
    _use(monkeypatch, provider)

    AIExtractService(db).extract(FORM, [ExtractFile(filename="zzt.mp4", mime="video/mp4", data=b"zzt")])

    assert provider.calls == [[f"p{k}" for k in range(1, 9)]]


def test_portal_route_returns_the_rows_and_the_note_never_the_raw_error(monkeypatch):
    _pages(monkeypatch, 8)
    res = _portal_post(
        monkeypatch, _PagesProvider(fail=lambda pages: RuntimeError(RAW) if "p3" in pages else None)
    )

    assert res.status_code == 200, res.text
    assert [p["product_code"] for p in res.json()["products"]] == [
        "ZZT-p1", "ZZT-p2", "ZZT-p5", "ZZT-p6", "ZZT-p7", "ZZT-p8"
    ]
    assert res.json()["note"] == "Pages 3-4 could not be read, try them again."
    assert "zzt-raw" not in res.text
