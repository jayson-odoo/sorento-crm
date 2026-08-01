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
from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.services.ai_prompt_registry import render
from app.services.llm_provider import ImagePart, get_provider

logger = logging.getLogger(__name__)

RASTER_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


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


@dataclass
class ExtractionResult:
    model: str
    page_count: int
    pages: list[PageResult] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0

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
    """
    api_key = settings.gemini_api_key
    if not api_key:
        raise ExtractionUnavailable(
            "No document extraction key configured (GEMINI_API_KEY). "
            "The document is stored and can be completed by hand."
        )

    chosen_model = model or settings.document_ai_model
    provider = get_provider(settings.document_ai_provider, api_key, chosen_model)
    images = render_pages(content, mime)
    result = ExtractionResult(model=f"{provider.name}/{chosen_model}", page_count=len(images))

    for index, image_b64 in enumerate(images, start=1):
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

        result.pages.append(page)
        result.prompt_tokens += page.prompt_tokens
        result.completion_tokens += page.completion_tokens
        if on_page is not None:
            try:
                on_page(page)
            except Exception:  # noqa: BLE001 - progress reporting is best effort
                logger.warning("on_page callback failed for page %s", index, exc_info=True)

    return result
