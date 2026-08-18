"""Read an uploaded document page by page with a vision model.

Shared by customer PO intake and delivery-schedule intake, which are the same
mechanical job on different paper: rasterise, ask per page, parse JSON, keep the
raw answer.

Three decisions worth knowing before you use it:

**Per page, never whole document.** A ten page scan asked as one request gives one
answer that is wrong in an unlocatable way, and the failure mode of a vision model on
a long document is quiet omission. Per page, a bad page is a bad page, the others
stand, and the retry is cheap.

**The raw answer is kept.** ``PageResult.data`` goes into ``extracted_json`` verbatim.
Every number is checked downstream by arithmetic that does not consult the model, and
when a check fails the only way to tell a misread from a bad rule is to still have what
the model actually said.

**A page that fails does not fail the document.** ``PageResult.error`` is set and the
page carries no data. Nine good pages out of ten is a document a person can finish; an
exception is a document they cannot start.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.services.ai_prompt_registry import render
from app.services.llm_provider import ImagePart, get_provider, resolve_api_key

logger = logging.getLogger(__name__)

RASTER_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}

# The environment leg of ``resolve_api_key``, named per provider so an operator
# with no key on the settings page is told which variable to set rather than
# being sent to look at the wrong one. Anything outside these two falls back to
# the OpenAI key in the resolver, so it is named the same way here.
_ENV_KEY_NAME = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


class ExtractionUnavailable(RuntimeError):
    """No key configured. Distinct from a failed read: nothing was attempted."""


@dataclass
class PageResult:
    page_no: int  # 1-based, matching what the person sees in the viewer
    data: Optional[dict] = None
    error: Optional[str] = None
    raw_text: Optional[str] = None  # kept only when parsing failed, for diagnosis
    prompt_tokens: int = 0
    completion_tokens: int = 0
    elapsed_ms: int = 0


@dataclass
class ExtractionResult:
    model: str
    page_count: int
    pages: list[PageResult] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # How long the model actually took. Reading ten scanned pages is minutes of
    # waiting, and a person who is told "2m 14s" once stops wondering whether it hung.
    elapsed_ms: int = 0

    @property
    def ok_pages(self) -> list[PageResult]:
        return [p for p in self.pages if p.data is not None]

    @property
    def failed_pages(self) -> list[int]:
        return [p.page_no for p in self.pages if p.data is None]


def render_pages(content: bytes, mime: str, *, dpi: Optional[int] = None,
                 page_limit: Optional[int] = None) -> list[str]:
    """Rasterise a PDF (or pass through an image) as base64 PNG, one per page.

    A photographed PO arrives as a JPEG and needs no rasterising, which is why the
    image case is not an error.
    """
    mime = (mime or "").lower()
    if mime in RASTER_MIMES:
        return [base64.b64encode(content).decode()]

    import fitz  # PyMuPDF; imported here so the module stays cheap to import

    dpi = dpi or settings.document_ai_render_dpi
    limit = page_limit or settings.document_ai_page_limit
    document = fitz.open(stream=content, filetype="pdf")
    try:
        pages = []
        for index in range(min(len(document), limit)):
            pixmap = document[index].get_pixmap(dpi=dpi)
            pages.append(base64.b64encode(pixmap.tobytes("png")).decode())
        if len(document) > limit:
            logger.warning(
                "document has %s pages, extracting the first %s (document_ai_page_limit)",
                len(document), limit,
            )
        return pages
    finally:
        document.close()


def page_count(content: bytes, mime: str) -> int:
    if (mime or "").lower() in RASTER_MIMES:
        return 1
    import fitz

    document = fitz.open(stream=content, filetype="pdf")
    try:
        return len(document)
    finally:
        document.close()


def _parse_json(text: str) -> dict:
    """Tolerate a fenced answer. Structured output makes this rare, not impossible."""
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("```")[1]
        if body.startswith("json"):
            body = body[4:]
    return json.loads(body)


def _assistant_config(db: Session):
    """The AI assistant config row, or ``None`` when the install has never saved one.

    Read exactly the way ``ai_extract`` and the media lane read it: oldest row
    first, no write. ``AIAssistantConfigService._ensure_singleton`` would create
    and commit a row, which extraction must not do - it runs on the worker
    inside somebody else's transaction and has no principal to attribute a new
    row to. ``resolve_api_key`` treats ``None`` as "no columns set" and falls
    through to the environment key, so an install with no row configured keeps
    working exactly as it did before.
    """
    from app.models.ai_assistant import AIAssistantConfig

    return (
        db.query(AIAssistantConfig)
        .order_by(AIAssistantConfig.created_at.asc())
        .first()
    )


def extract_document(
    db: Session,
    content: bytes,
    mime: str,
    *,
    prompt_key: str,
    model: Optional[str] = None,
    on_page: Optional[Callable[[PageResult], None]] = None,
) -> ExtractionResult:
    """Run ``prompt_key`` over every page of the document.

    ``prompt_key`` is a name in the AI prompt registry, so the prompt is versioned and
    can be rolled back without a deploy. It must declare ``page_no`` and
    ``page_count``: telling the model where it is in the document is what stops it
    inventing a header on page 7.

    ``on_page`` is called after each page so a caller can persist progress; a long scan
    should not look frozen for two minutes.

    The key is resolved through the shared ``resolve_api_key`` ladder against the
    AI assistant config row, for the provider ``document_ai_provider`` names: the
    provider-specific column an operator saved in the UI first, then the generic
    column when the assistant itself runs on that provider, then the environment
    key. Reading the environment alone meant a key saved on the settings page was
    silently ignored and the feature reported itself unavailable.

    The usage row this writes carries no principal. Extraction runs on the worker with
    no request behind it, and neither version row records who uploaded it, so there is
    nothing truthful to attribute it to yet. Recording a guess would be worse than the
    blank.
    """
    provider_name = (settings.document_ai_provider or "").strip().lower()
    api_key = resolve_api_key(_assistant_config(db), provider_name)
    if not api_key:
        env_var = _ENV_KEY_NAME.get(provider_name, "OPENAI_API_KEY")
        raise ExtractionUnavailable(
            f"No document extraction key configured for the '{provider_name}' provider. "
            "Set one on the AI assistant settings page (System > AI Assistant), or as "
            f"the {env_var} environment variable. "
            "The document is stored and can be completed by hand."
        )

    chosen_model = model or settings.document_ai_model
    provider = get_provider(provider_name, api_key, chosen_model)
    images = render_pages(content, mime)
    result = ExtractionResult(model=f"{provider.name}/{chosen_model}", page_count=len(images))

    started = time.perf_counter()
    for index, image_b64 in enumerate(images, start=1):
        page_started = time.perf_counter()
        prompt, _version = render(
            db, prompt_key, page_no=index, page_count=len(images)
        )
        page = PageResult(page_no=index)
        try:
            answer = provider.chat(
                [{"role": "user", "content": prompt}],
                images=[ImagePart(mime="image/png", data_b64=image_b64)],
                temperature=0,
                response_format={"type": "json_object"},
            )
            page.prompt_tokens = answer.prompt_tokens
            page.completion_tokens = answer.completion_tokens
            page.data = _parse_json(answer.content)
        except json.JSONDecodeError:
            page.error = "the model's answer was not valid JSON"
            page.raw_text = (answer.content or "")[:2000]
        except Exception as exc:  # noqa: BLE001 - one bad page must not lose the rest
            page.error = str(exc)[:300]
            logger.warning("extraction failed on page %s: %s", index, page.error)

        page.elapsed_ms = int((time.perf_counter() - page_started) * 1000)
        result.pages.append(page)
        result.prompt_tokens += page.prompt_tokens
        result.completion_tokens += page.completion_tokens
        if on_page is not None:
            try:
                on_page(page)
            except Exception:  # noqa: BLE001 - progress reporting is best effort
                logger.warning("on_page callback failed for page %s", index, exc_info=True)

    result.elapsed_ms = int((time.perf_counter() - started) * 1000)
    _log_usage(db, result, prompt_key=prompt_key, provider=provider.name)
    return result


def _log_usage(db: Session, result: "ExtractionResult", *, prompt_key: str, provider: str) -> None:
    """Record what this document cost, next to every other model call in the product.

    Extraction is by far the most expensive thing the system asks a model to do, and it
    was the only thing not showing up in the usage figures. Best effort on purpose: a
    telemetry write must never be the reason a document that WAS read is reported as
    failed.
    """
    try:
        from app.models.ai_assistant import AIAssistantUsageLog

        db.add(
            AIAssistantUsageLog(
                model=result.model,
                provider=provider,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.prompt_tokens + result.completion_tokens,
                # One call per page, so the page count IS the number of model calls.
                tool_calls_count=result.page_count,
                response_time_ms=result.elapsed_ms,
                was_answered=bool(result.ok_pages),
                feature="ai_document_extract",
                form_key=prompt_key,
            )
        )
        db.flush()
    except Exception:  # noqa: BLE001
        logger.warning("could not record extraction usage", exc_info=True)
