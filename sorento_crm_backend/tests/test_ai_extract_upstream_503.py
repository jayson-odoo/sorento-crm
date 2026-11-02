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
