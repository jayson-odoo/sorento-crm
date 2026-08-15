"""`MediaExtractService` - the composer for both extraction lanes (PLAN 4.2).

A sibling package to `ai_extract`, not an edit to it, so the live portal route is
untouched. What is reused is what genuinely transfers: `ExtractFile` and
`_render_files` (bytes to provider image parts, including the PDF and video
branches), provider resolution off `AIAssistantConfig`, and `_log_usage` - which
already writes `AIAssistantUsageLog` with `contact_id`, so token spend for this
feature lands on the existing usage dashboard with no new plumbing.

What is deliberately NOT reused:

* the `portal.complaint` prompt and schema. Measured against three real Sorento
  images it was flawless on a clean screenshot, produced three confident wrong
  answers on a photographed RMA form, and found only the model code on an angled
  carton photo. This package has its own prompt (`prompts.py`) and its own
  output contract (`schema.py`).
* `_canonical_product_code`. Product-code matching is not rebuilt here: the raw
  string plus `confident` goes out and `resolve-entity` adjudicates, because it
  already runs a far better ladder with typo tolerance this extraction cannot
  have.

**Which lane runs is decided by `job.modality` and nothing else** - `image` goes
to the vision call, `voice` to `transcribe.py`. The document-versus-label split
INSIDE the image lane is not a second dispatch: the model classifies and
extracts in the same pass (`image_kind`), because a second round trip doubles
both the cost and the latency, and the latency now sits inside n8n's
`lock:{contact}` budget.

Everything here runs in the RQ work-horse, on a worker thread, against its own
short-lived session. It must never touch the ORM row the task owns.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.media_extract import prompts, wording
from app.services.media_extract.schema import (
    MediaExtraction,
    MediaExtractionParseError,
    empty_result_body,
    parse_extraction,
    parse_provider_json,
)
from app.services.media_extract.transcribe import (
    TranscriptionError,
    transcribe,
)

logger = logging.getLogger(__name__)

# `form_key` values on the usage log. `feature` stays `ai_extract` because that
# is what `_log_usage` writes and what the dashboard's contact-scoped view
# defaults to; the form key is what separates a photo read from a portal form.
FORM_KEY_IMAGE = "chatbot.media.image"
FORM_KEY_VOICE = "chatbot.media.voice"

# Media download bounds. The Respond.io CDN url is short-lived, so a slow fetch
# is a failure rather than something to wait out.
MEDIA_FETCH_TIMEOUT_SECONDS = 20.0
MAX_MEDIA_BYTES = 25 * 1024 * 1024  # the transcription API's own ceiling

# Vision call bounds. `max_tokens` is generous for a JSON object of at most a
# dozen entities and stops a rambling model from spending the whole budget.
VISION_MAX_TOKENS = 2048

# The last-resort model per provider (used only when neither the media settings
# nor the `AIAssistantConfig` row names one) lives with the providers themselves
# as `llm_provider.DEFAULT_MODELS`, so this lane, `ai_extract` and the spec
# understander all agree on it. Each is that provider's cheap-but-capable model,
# matching what migration 358 seeded for OpenAI.


class MediaExtractionError(RuntimeError):
    """Extraction could not be produced. Becomes the job's `error` and the
    `failed` callback's reason - never an HTTP status, because this runs in the
    worker where there is no request to fail."""


@dataclass
class MediaJobInput:
    """A plain snapshot of the job row, taken before the extraction thread runs.

    The extraction happens on a worker thread with a bounded join, so it must
    never lazy-load off the session the task owns. Snapshotting into a dataclass
    makes that structural rather than a rule someone has to remember.
    """

    job_id: str
    modality: str
    tier: Optional[str]
    media_url: Optional[str]
    mime_type: Optional[str]
    caption: Optional[str]
    usage_id: Optional[str]

    @classmethod
    def from_job(cls, job: Any) -> "MediaJobInput":
        return cls(
            job_id=str(job.id),
            modality=str(job.modality),
            tier=job.tier,
            media_url=job.media_url,
            mime_type=job.mime_type,
            caption=job.caption,
            usage_id=str(job.usage_id) if job.usage_id else None,
        )


@dataclass
class MediaExtractionOutcome:
    """The result body plus what it cost, for the ledger and the dashboard."""

    result: dict[str, Any]
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


def fetch_media_bytes(url: str) -> tuple[bytes, Optional[str]]:
    """Download the media. A module-level seam so tests never hit the network."""
    import httpx

    if not url:
        raise MediaExtractionError("The message carried no media url.")
    try:
        with httpx.Client(
            timeout=MEDIA_FETCH_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.content
            content_type = response.headers.get("content-type")
    except Exception as exc:  # noqa: BLE001 - any download failure is a failed job
        raise MediaExtractionError(f"Could not download the media: {exc}") from exc
    if not data:
        raise MediaExtractionError("The media downloaded as zero bytes.")
    if len(data) > MAX_MEDIA_BYTES:
        raise MediaExtractionError(
            f"The media is {len(data) // (1024 * 1024)}MB, over the "
            f"{MAX_MEDIA_BYTES // (1024 * 1024)}MB limit."
        )
    return data, content_type


def build_image_result_body(
    extraction: MediaExtraction,
    *,
    caption: Optional[str],
    max_entities: int,
) -> dict[str, Any]:
    """The PLAN 3.5 result body for an image, including `rendered_text`.

    `rendered_text` is what the far end patches into the queue item upstream of
    `tf-message`, so it must read like something a customer typed - that is what
    the parser is tuned on. PLAN 4.5's table, implemented:

    | caption plus entities        | the caption with the raw strings appended |
    | no caption                   | null, with `needs_clarification: true`    |
    | unclear caption intent       | null, with `needs_clarification: true`    |
    | nothing extracted            | the caption alone - today's behaviour      |

    Only ENTITY raws are appended. Attributes have no hint, so `resolve-entity`
    cannot look them up and appending them would be noise in the parser's input;
    they still reach the customer through the confirmation message.
    """
    caption_text = (caption or "").strip() or None
    # Rule 16 of the prompt, enforced rather than trusted: no caption is always a
    # clarification, whether or not the model remembered to say so.
    needs_clarification = extraction.needs_clarification or caption_text is None

    body = empty_result_body(caption_text)
    body.update(
        {
            "entities": [entity.model_dump() for entity in extraction.entities],
            "attributes": [
                attribute.model_dump() for attribute in extraction.attributes
            ],
            "conflicts": [conflict.model_dump() for conflict in extraction.conflicts],
            "image_kind": extraction.image_kind,
            # Both are read by the model and both are carried through rather
            # than dropped at the parse: `caption_intent` is what makes rule 15
            # behave, and `notes` ("blurred lower half") is what a support
            # person needs when a dealer asks why their photo did not work.
            "caption_intent": extraction.caption_intent,
            "notes": extraction.notes,
            "needs_clarification": needs_clarification,
            "truncated": extraction.truncated,
        }
    )

    if needs_clarification:
        # Nothing is rendered for the parser: guessing the intent on top of an
        # imperfect reading stacks two silent failure modes, so the system asks.
        body["rendered_text"] = None
        body["clarification_message"] = wording.clarification(
            extraction.entities, extraction.attributes
        )
        return body

    if extraction.is_empty:
        # Identical to what the turn does today when nothing is read.
        body["rendered_text"] = caption_text
        body["confirmation_message"] = wording.nothing_read()
        return body

    raws = [entity.raw for entity in extraction.entities]
    body["rendered_text"] = (
        f"{caption_text}: {', '.join(raws)}" if raws else caption_text
    )
    confirmation = wording.confirmation(
        extraction.entities, extraction.attributes, extraction.conflicts
    )
    if extraction.truncated:
        confirmation = f"{confirmation} {wording.truncated_note(max_entities)}"
    body["confirmation_message"] = confirmation
    return body


def build_voice_result_body(
    *,
    transcript: str,
    languages_detected: Optional[list[str]],
) -> dict[str, Any]:
    """The PLAN 3.5 result body for a voice note.

    `rendered_text` is the transcript itself - the same trick `patch-transcript`
    already uses in the spine, so the turn continues as though it had been typed.
    """
    text = (transcript or "").strip()
    body = empty_result_body(None)
    body["transcript"] = text or None
    body["languages_detected"] = languages_detected

    if not text:
        body["needs_clarification"] = True
        body["clarification_message"] = wording.voice_unclear()
        return body

    body["rendered_text"] = text
    # An empty (but present) detected-language list is the model saying it is
    # unsure. That is an answer, so it changes the confirmation rather than
    # being swallowed.
    if languages_detected is not None and not languages_detected:
        body["confirmation_message"] = wording.voice_language_unsure(text)
    else:
        body["confirmation_message"] = wording.voice_confirmation(text)
    return body


class MediaExtractService:
    """Runs one extraction, on its own session, in the worker process."""

    def __init__(self, db: Session):
        self.db = db

    # ----- Entry point ------------------------------------------------------

    def extract(self, job: MediaJobInput) -> MediaExtractionOutcome:
        """The only dispatch: `modality` picks the lane."""
        from app.services.media_access_service import resolve_media_settings

        settings = resolve_media_settings(self.db)
        if job.modality == "voice":
            outcome = self._extract_voice(job, settings)
        elif job.modality == "image":
            outcome = self._extract_image(job, settings)
        else:
            raise MediaExtractionError(f"Unsupported media modality {job.modality!r}.")
        self._stamp_usage_cost(job, outcome)
        return outcome

    # ----- Image ------------------------------------------------------------

    def _extract_image(self, job: MediaJobInput, settings: Any) -> MediaExtractionOutcome:
        from app.services.ai_extract.extract_service import (
            AIExtractService,
            ExtractFile,
        )
        from app.services.llm_provider import ChatResult

        data, content_type = fetch_media_bytes(job.media_url or "")
        mime = (job.mime_type or content_type or "image/jpeg").split(";")[0].strip()

        helper = AIExtractService(self.db)
        parts = helper._render_files(
            [ExtractFile(filename=_filename_for(mime), mime=mime, data=data)]
        )
        if not parts:
            raise MediaExtractionError(
                f"Nothing readable in the media (mime {mime or 'unknown'})."
            )

        provider, provider_name, model_name = self._resolve_image_provider(
            job.tier, settings
        )
        messages = prompts.build_messages(
            max_entities=settings.max_entities, caption=job.caption
        )
        started = time.perf_counter()
        try:
            result: ChatResult = provider.chat(
                messages=messages,
                images=parts,
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=VISION_MAX_TOKENS,
                model=model_name,
            )
        except Exception as exc:  # noqa: BLE001 - a provider failure is a failed job
            raise MediaExtractionError(f"The vision model call failed: {exc}") from exc
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        try:
            payload = parse_provider_json(result.content)
        except MediaExtractionParseError as exc:
            raise MediaExtractionError(str(exc)) from exc
        extraction = parse_extraction(payload, max_entities=settings.max_entities)
        body = build_image_result_body(
            extraction, caption=job.caption, max_entities=settings.max_entities
        )

        self._log_usage(
            helper,
            job=job,
            provider_name=provider_name,
            model=model_name,
            result=result,
            elapsed_ms=elapsed_ms,
            form_key=FORM_KEY_IMAGE,
            answered=not extraction.is_empty,
        )
        return MediaExtractionOutcome(
            result=body,
            provider=provider_name,
            model=model_name,
            prompt_tokens=int(result.prompt_tokens or 0),
            completion_tokens=int(result.completion_tokens or 0),
        )

    def _resolve_image_provider(self, tier: Optional[str], settings: Any):
        """Provider and model for this call, degraded tier included.

        Reads `media_image_provider` / `media_image_model` first and falls back
        to the `AIAssistantConfig` row - the same source the chat assistant and
        `ai_extract` use, so one API key configuration serves all three. A
        `degraded` tier uses `media_image_degraded_model`. Migration 358 seeds
        the measured tiers (`openai`/`gpt-4o` standard, `gpt-4o-mini` degraded -
        PLAN section 14.1), but all three columns stay clearable: a NULL
        `media_image_degraded_model` means the quota is a hard refusal instead of
        a degrade, so a degraded tier only reaches here while a model is named.
        """
        from app.models.ai_assistant import AIAssistantConfig
        from app.services.llm_provider import default_model_for, get_provider

        cfg = (
            self.db.query(AIAssistantConfig)
            .order_by(AIAssistantConfig.created_at.asc())
            .first()
        )
        provider_name = (
            settings.image_provider or (cfg.provider if cfg else None) or "openai"
        )
        if tier == "degraded" and settings.image_degraded_model:
            model_name = settings.image_degraded_model
        else:
            model_name = settings.image_model or (cfg.model if cfg else "") or ""
        if not model_name:
            model_name = default_model_for(provider_name)

        api_key = self._api_key(cfg, provider_name)
        if not api_key:
            # Naming the provider is the whole message: the lane can run on a
            # different provider than the assistant, so "no key configured" on
            # its own sends an admin to look at a key that is already set.
            raise MediaExtractionError(
                f"No API key is configured for the '{provider_name}' image "
                "provider. Set it in System > AI Assistant."
            )
        try:
            provider = get_provider(provider_name, api_key, model=model_name)
        except ValueError as exc:
            raise MediaExtractionError(str(exc)) from exc
        return provider, provider_name, model_name

    @staticmethod
    def _api_key(cfg: Any, provider_name: str) -> str:
        """The key for this provider, preferring the provider-specific column."""
        from app.config import settings as app_settings

        if provider_name == "anthropic":
            return (
                (getattr(cfg, "anthropic_api_key_ciphertext", None) if cfg else "")
                or (getattr(cfg, "api_key_ciphertext", None) if cfg else "")
                or ""
            )
        if provider_name == "gemini":
            # The generic key column only counts when the assistant itself runs
            # on Gemini - otherwise it holds someone else's key and would be
            # sent to Google as a 400 that reads like a Gemini outage.
            generic = (
                (getattr(cfg, "api_key_ciphertext", None) if cfg else "")
                if (getattr(cfg, "provider", None) if cfg else None) == "gemini"
                else ""
            )
            return (
                (getattr(cfg, "gemini_api_key_ciphertext", None) if cfg else "")
                or generic
                or app_settings.gemini_api_key
                or ""
            )
        return (
            (getattr(cfg, "api_key_ciphertext", None) if cfg else "")
            or app_settings.openai_api_key
            or ""
        )

    # ----- Voice ------------------------------------------------------------

    @staticmethod
    def _resolve_voice_model(tier: Optional[str], settings: Any) -> str:
        """The transcription model for this call, degraded tier included.

        The mirror of `_resolve_image_provider`'s tier branch, and it was
        missing: `job.tier` was ignored here, so an over-quota voice note was
        transcribed on the standard model while the contact was told accuracy
        had dropped. A NULL `media_voice_degraded_model` means the quota refuses
        rather than degrades, so a `degraded` tier only reaches this branch while
        a model is actually named - the `or` is belt and braces, not a fallback
        anyone should rely on.
        """
        if tier == "degraded" and getattr(settings, "voice_degraded_model", None):
            return str(settings.voice_degraded_model)
        return str(settings.transcribe_model)

    def _extract_voice(self, job: MediaJobInput, settings: Any) -> MediaExtractionOutcome:
        from app.models.ai_assistant import AIAssistantConfig
        from app.services.ai_extract.extract_service import AIExtractService
        from app.services.llm_provider import ChatResult

        data, content_type = fetch_media_bytes(job.media_url or "")
        cfg = (
            self.db.query(AIAssistantConfig)
            .order_by(AIAssistantConfig.created_at.asc())
            .first()
        )
        model_name = self._resolve_voice_model(job.tier, settings)
        started = time.perf_counter()
        try:
            heard = transcribe(
                data,
                model=model_name,
                # Built from settings at call time (UAC S5-01/S5-02): pinned,
                # hints or auto, defaulting to pinned/`en`.
                strategy=settings.language_strategy(),
                api_key=self._api_key(cfg, "openai"),
                mime_type=job.mime_type or content_type,
                media_url=job.media_url,
                timeout=settings.extraction_timeout_seconds,
            )
        except TranscriptionError as exc:
            # The provider's own message, not a generic one.
            raise MediaExtractionError(str(exc)) from exc
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        body = build_voice_result_body(
            transcript=heard.text, languages_detected=heard.languages_detected
        )
        # Transcription is billed by audio duration, not tokens, so the usage row
        # carries zeros. It is still written: the dashboard's value here is the
        # per-contact call count and the model actually used.
        self._log_usage(
            AIExtractService(self.db),
            job=job,
            provider_name="openai",
            model=heard.model,
            result=ChatResult(
                content="", prompt_tokens=0, completion_tokens=0, total_tokens=0
            ),
            elapsed_ms=elapsed_ms,
            form_key=FORM_KEY_VOICE,
            answered=bool(heard.text),
        )
        return MediaExtractionOutcome(
            result=body, provider="openai", model=heard.model
        )

    # ----- Accounting -------------------------------------------------------

    def _contact_id(self, usage_id: Optional[str]) -> Optional[str]:
        if not usage_id:
            return None
        from app.models.media import ContactMediaUsage

        usage = (
            self.db.query(ContactMediaUsage)
            .filter(ContactMediaUsage.id == usage_id)
            .first()
        )
        return usage.contact_id if usage is not None else None

    def _log_usage(
        self,
        helper: Any,
        *,
        job: MediaJobInput,
        provider_name: str,
        model: str,
        result: Any,
        elapsed_ms: int,
        form_key: str,
        answered: bool,
    ) -> None:
        """Token spend onto the existing dashboard, tagged with `contact_id`.

        Reuses `AIExtractService._log_usage` verbatim (PLAN 4.1) rather than
        writing a second `AIAssistantUsageLog` insert: it is already best-effort
        and already the only writer that populates `contact_id`, which is what
        the dashboard's per-contact view scopes to.
        """
        helper._log_usage(
            provider_name=provider_name,
            model=model,
            result=result,
            elapsed_ms=elapsed_ms,
            user_id=None,
            contact_id=self._contact_id(job.usage_id),
            form_key=form_key,
            page_count=1,
            answered=answered,
        )

    def _is_orphaned(self, job: MediaJobInput) -> bool:
        """Did the task give up on this extraction while it was still running?

        `_run_bounded` joins the extraction thread with a timeout. On a timeout
        the task marks the job `failed` and moves on, but the thread is still
        alive and eventually finishes its provider call - and it used to stamp
        token counts onto a row already recorded as a failure, annotating it as
        a success it was not.

        Terminal here means exactly that case: on the normal path this runs
        before the task writes `completed`, so the status is still `running`. A
        missing job row is NOT treated as orphaned, since a caller running an
        extraction without a job row (a direct service call) still wants its
        spend recorded.
        """
        from app.models.media import MediaExtractionJob

        status = (
            self.db.query(MediaExtractionJob.status)
            .filter(MediaExtractionJob.id == job.job_id)
            .scalar()
        )
        return status in ("completed", "failed")

    def _stamp_usage_cost(
        self, job: MediaJobInput, outcome: MediaExtractionOutcome
    ) -> None:
        """Stamp model/provider/tokens onto the ledger row. Best-effort.

        The ledger is the metered fact and the decision it recorded is already
        committed; failing to annotate it must never turn a successful
        extraction into a failed job.

        An extraction the task already timed out on does not stamp - it logs
        instead. The spend happened either way and must not be invisible, but
        the row says `failed` and writing success-shaped token counts onto it
        would be a record of something that did not happen.
        """
        if not job.usage_id:
            return
        from app.models.media import ContactMediaUsage

        try:
            if self._is_orphaned(job):
                logger.warning(
                    "media extract: job %s finished AFTER the worker gave up on "
                    "it; spend not stamped on usage %s (provider=%s model=%s "
                    "prompt_tokens=%s completion_tokens=%s)",
                    job.job_id,
                    job.usage_id,
                    outcome.provider,
                    outcome.model,
                    outcome.prompt_tokens,
                    outcome.completion_tokens,
                )
                return
            usage = (
                self.db.query(ContactMediaUsage)
                .filter(ContactMediaUsage.id == job.usage_id)
                .first()
            )
            if usage is None:
                return
            usage.provider = outcome.provider
            usage.model = outcome.model
            usage.prompt_tokens = outcome.prompt_tokens
            usage.completion_tokens = outcome.completion_tokens
            self.db.commit()
        except Exception:  # noqa: BLE001
            logger.warning(
                "media extract: could not stamp cost on usage %s", job.usage_id,
                exc_info=True,
            )
            self.db.rollback()


def _filename_for(mime: str) -> str:
    """A filename with an extension, because `_render_files` sniffs both."""
    extension = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/webm": ".webm",
        "video/3gpp": ".3gp",
    }.get((mime or "").lower(), ".jpg")
    return f"media{extension}"


def run_extraction(job: Any, *, db: Optional[Session] = None) -> dict[str, Any]:
    """Convenience entry point: snapshot the ORM row, extract, return the body.

    Used by `app.tasks.media_tasks.run_media_extraction`. Opens its own session
    when none is supplied, because the caller runs on a worker thread and must
    not borrow the task's.
    """
    job_input = MediaJobInput.from_job(job)
    if db is not None:
        return MediaExtractService(db).extract(job_input).result

    from app.database import SessionLocal

    session = SessionLocal()
    try:
        return MediaExtractService(session).extract(job_input).result
    finally:
        session.close()


# Re-exported so a caller does not have to know which module holds the base
# shape when it wants an empty body (e.g. an unsupported mime that is not worth
# failing the turn over).
__all__ = [
    "FORM_KEY_IMAGE",
    "FORM_KEY_VOICE",
    "MediaExtractService",
    "MediaExtractionError",
    "MediaExtractionOutcome",
    "MediaJobInput",
    "build_image_result_body",
    "build_voice_result_body",
    "empty_result_body",
    "fetch_media_bytes",
    "run_extraction",
]
