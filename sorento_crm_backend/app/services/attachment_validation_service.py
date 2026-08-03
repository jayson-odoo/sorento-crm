"""One validator for every uploaded file, in `resources`, beside the attachments it judges.

AC-M21 puts this HERE and nowhere else. `resources` is the module complaints, service
jobs, the forms platform and the portal already depend on, so a validator that lives in
it is inherited by all of them; a copy under any one of those modules is how two upload
types end up judged by two prompts nobody can compare. Three separate slices consume
this one (consumer intake evidence, technician proof, collection proof) and none of them
may grow its own scorer.

Five things decide the shape of this module, and each is a place where the obvious
implementation is wrong.

**"Unvalidated" is a state, not an absent score.** A hard timeout that lands as score 0,
or as a NULL the UI reads as failure, REFUSES A GOOD PHOTO because the network was slow -
a technician in a basement at 6pm loses the job he just closed. So the outcome carries an
explicit ``state`` (``scored`` / ``unvalidated`` / ``skipped``) and, when it could not
judge, a ``reason`` - which is the only thing separating "my timeout is too short" from
"my provider key is wrong". `passed` is None for both `skipped` and `unvalidated`, never
False: a caller that renders `passed is False` as Retake must not put a Retake button in
front of a photo nobody looked at.

**Nothing here ever raises.** Every caller is an upload path, and an upload path that has
to wrap this in its own try/except grows three copies of that try/except within a release,
the third of which forgets to roll the session back. A missing provider degrades rather
than 400s, because `ai_extract`'s 400 copied into an upload path turns every photo upload
on a fresh install, on a dev machine and on any tenant without an AI subscription into a
failure - for a feature that is advisory.

**Per-type behaviour is DATA (AC-M25).** Nothing in this file knows a single type's code.
Everything it decides comes from three columns - `validate_on_upload`, `validation_guidance`
and `min_score` - and the prompt itself is a registry key, versioned and editable without
a deploy. A branch per type would make adding the next photo type a deployment, which is
the exact cost the slice exists to remove.

**The scale is integer 0-100 on both sides of the comparison.** A model reply on the
0.0-1.0 scale is a scale MISMATCH and degrades; it is never rounded, because 0.82 rounds
to 1 and refuses a good photo. An out-of-range reply degrades rather than clamping,
because clamping 1000 to 100 passes a file on an answer nobody can explain. The threshold
is inclusive, `min_score = 0` passes everything and `min_score = NULL` is advisory.

**The timeout is enforced HERE, with a thread, not delegated to the provider SDK.** A
delegated timeout is precisely what fails on a stalled mobile connection, where no
response ever arrives and no SDK deadline fires. The worker thread is a daemon and is
abandoned on expiry: its result is discarded, and the process is never held open by it.

See documentation/plans/after-sales/after-sales-warranty-acceptance-criteria.md,
AC-M20 to AC-M27 plus the "S2a corrections" block.
"""
from __future__ import annotations

import base64
import json
import logging
import math
import threading
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import AttachmentType
from app.services import ai_prompt_registry
from app.services.error_handler import handle_not_found, handle_validation_error

# Imported as a NAME, so a test (and a future adapter) can substitute the provider
# on this module. The repo's other multimodal call site binds it the same way.
from app.services.llm_provider import ChatResult, ImagePart, LLMProvider, get_provider

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Contract                                                                      #
# --------------------------------------------------------------------------- #

# The registry key holding the prompt. Deliberately NOT `validator`, which is the
# assistant's own dormant answer-confidence gate.
PROMPT_KEY = "attachment_validator"
PROMPT_VARIABLE = "validation_guidance"

# One scale, declared once, used by the parser, the comparison, the write guard and
# the admin schema. Integer, because min_score is admin data entry beside
# max_file_size_mb and an admin who types 70 meaning 70% into a 0-1 column sets a
# threshold nothing can ever clear.
SCORE_MIN = 0
SCORE_MAX = 100

# `skipped` is never persisted: a row from a type that never opted in must be
# indistinguishable from every row written before this slice existed.
STATE_SCORED = "scored"
STATE_UNVALIDATED = "unvalidated"
STATE_SKIPPED = "skipped"

REASON_TIMEOUT = "timeout"
REASON_ERROR = "error"
REASON_NO_GUIDANCE = "no_guidance"
REASON_NO_PROVIDER = "no_provider"
REASON_UNSUPPORTED_MEDIA = "unsupported_media"

# Synchronous means somebody is holding a phone still. Past roughly twenty seconds
# they have already decided the app is broken. Read at CALL time, never bound as a
# default argument, so tuning it here actually changes behaviour.
VALIDATION_TIMEOUT_SECONDS = 12.0

# "." gets past a non-empty check and defeats the entire point of asking.
OVERRIDE_REASON_MIN_LENGTH = 10

# Matches entity_attachment_links.latitude / longitude, which match complaints'.
COORDINATE_SCALE = 7
_COORDINATE_QUANTUM = Decimal(1).scaleb(-COORDINATE_SCALE)
_LATITUDE_LIMIT = Decimal(90)
_LONGITUDE_LIMIT = Decimal(180)

# What a vision model will accept. The type's own allowed_extensions already decided
# whether the file may be UPLOADED; this list only decides whether we can look at it,
# and a file we cannot look at degrades rather than taking the upload down with it.
_VIEWABLE_MIMES = frozenset(
    {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
)
_VIEWABLE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
_DEFAULT_MIME = "image/png"

# The static half of the request. Every type sends exactly this; only the rendered
# system prompt differs, and it differs only by the type's guidance.
_USER_INSTRUCTION = (
    "Score the attached file against the requirement above. Reply with the JSON "
    "object only."
)

_MAX_REPLY_TOKENS = 300


@dataclass(frozen=True)
class ValidationOutcome:
    """What the validator is willing to claim about one file.

    ``passed`` is a three-valued answer on purpose. False means "judged, and it did
    not meet the threshold". None means "no claim" - either the type never asked for
    a verdict, or nothing could be judged - and the two are told apart by ``state``.
    """

    state: str
    score: Optional[int] = None
    suggestion: Optional[str] = None
    passed: Optional[bool] = None
    reason: Optional[str] = None


def _skipped() -> ValidationOutcome:
    return ValidationOutcome(state=STATE_SKIPPED)


def _unvalidated(reason: str) -> ValidationOutcome:
    return ValidationOutcome(state=STATE_UNVALIDATED, reason=reason)


class _Expired(Exception):
    """The worker thread outlived its budget. Private: it never leaves this module."""


# --------------------------------------------------------------------------- #
# The validator                                                                 #
# --------------------------------------------------------------------------- #


def validate_upload(
    db: Session,
    *,
    attachment_type: Optional[AttachmentType],
    data: bytes,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
    timeout: Optional[float] = None,
) -> ValidationOutcome:
    """Score one file's BYTES against its attachment type's guidance. Never raises.

    Bytes, never an id and never a URL (AC-M23c): uploads span two storage providers
    and R2 keys are not always public, so a validator built on a presigned URL behaves
    differently per provider and breaks for whichever one a tenant is mid-migration on.
    On upload the bytes are in hand anyway, before anything has been stored.

    The order of the gates is load-bearing. A type that did not opt in, and a type
    that opted in with nothing to judge against, must both return WITHOUT resolving a
    provider or calling a model: no latency and no new failure mode for the modules
    that never asked for any of this.
    """
    if attachment_type is None:
        # attachments.attachment_type_id is nullable and set to NULL on type delete.
        return _skipped()
    if not bool(getattr(attachment_type, "validate_on_upload", False)):
        return _skipped()

    guidance = (getattr(attachment_type, "validation_guidance", None) or "").strip()
    if not guidance:
        # The type asked to be validated and there is nothing to validate against.
        # NOT `skipped`: that misconfiguration has to stay visible rather than
        # looking like a type that opted out. Scoring against an empty instruction
        # returns a number that looks authoritative and means nothing.
        logger.warning(
            "Attachment type %s asks for validation with no guidance",
            getattr(attachment_type, "id", None),
        )
        return _unvalidated(REASON_NO_GUIDANCE)

    image = _as_image_part(data, filename, content_type)
    if image is None:
        return _unvalidated(REASON_UNSUPPORTED_MEDIA)

    provider, model_name = _resolve_provider(db)
    if provider is None:
        return _unvalidated(REASON_NO_PROVIDER)

    try:
        prompt = _render_prompt(db, guidance)
    except Exception:  # noqa: BLE001
        logger.warning("Attachment validation prompt render failed", exc_info=True)
        return _unvalidated(REASON_ERROR)

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": _USER_INSTRUCTION},
    ]
    budget = timeout if timeout is not None else VALIDATION_TIMEOUT_SECONDS

    def _ask() -> ChatResult:
        return provider.chat(
            messages=messages,
            images=[image],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=_MAX_REPLY_TOKENS,
            model=model_name,
        )

    try:
        result = _within_budget(_ask, budget)
    except _Expired:
        logger.warning("Attachment validation timed out after %ss", budget)
        return _unvalidated(REASON_TIMEOUT)
    except BaseException:  # noqa: BLE001 - a rate limit is not evidence about a photo
        logger.warning("Attachment validation provider call failed", exc_info=True)
        return _unvalidated(REASON_ERROR)

    parsed = _parse_reply(getattr(result, "content", None))
    if parsed is None:
        return _unvalidated(REASON_ERROR)

    score, suggestion = parsed
    return ValidationOutcome(
        state=STATE_SCORED,
        score=score,
        suggestion=suggestion,
        passed=_meets(score, getattr(attachment_type, "min_score", None)),
        reason=None,
    )


def _meets(score: int, threshold: Any) -> bool:
    """Inclusive, and permissive at both edges.

    NULL is advisory: no threshold means nothing to fail, and coercing it to 0 or to
    any other number invents a gate the admin did not set. 0 is a gate every score
    clears, because `score >= 0` is always true - reading it as "nothing passes"
    turns a plausible admin typo into a type nobody can upload to. `>=` and not `>`,
    because an admin who sets 60 means sixty is good enough.
    """
    if threshold is None:
        return True
    try:
        return int(score) >= int(threshold)
    except (TypeError, ValueError):
        return True


# --------------------------------------------------------------------------- #
# Persistence                                                                   #
# --------------------------------------------------------------------------- #


def apply_outcome(
    link: EntityAttachmentLink, outcome: Optional[ValidationOutcome]
) -> EntityAttachmentLink:
    """Write one outcome onto one link row. The ONLY mapping from verdict to columns.

    A `skipped` outcome writes NOTHING. That row must be indistinguishable from every
    row that predates this slice, or a reader has two spellings of "nothing to say
    here" and has to guess which one a NULL is.
    """
    if outcome is None or outcome.state == STATE_SKIPPED:
        return link
    link.ai_validation_state = outcome.state
    link.ai_validation_reason = outcome.reason
    link.ai_score = outcome.score
    link.ai_suggestion = outcome.suggestion
    return link


def record_override(
    db: Session,
    *,
    link_id: str,
    reason: str,
    user_id: Optional[str] = None,
) -> EntityAttachmentLink:
    """"Use anyway" - refused without a real reason, and refused when nothing failed.

    AC-M24 is written as a UI sentence, and a guard on the action routes is not a
    guard (ADR-0013 rule 7): the portal, the CRM panel and a technician app are three
    callers and they all pass through here.

    The second half matters as much as the first. There is nothing to override on an
    upload that passed, or on one nobody could judge, and a reason recorded against
    either pollutes the single metric this exists to produce - the override reason is
    what says the GUIDANCE is wrong rather than the uploader, and a timed-out upload
    counted as an override reports a network problem as a disagreement.

    ``user_id`` is accepted for the caller contract and LOGGED, not stored: no column
    for the overriding principal is specified, and inventing one here would put a
    second unreviewed home for attribution on a table every module writes to.
    """
    text = (reason or "").strip()
    if len(text) < OVERRIDE_REASON_MIN_LENGTH:
        raise handle_validation_error(
            f"A reason of at least {OVERRIDE_REASON_MIN_LENGTH} characters is "
            "required to use a file that did not meet its requirement."
        )

    link = (
        db.query(EntityAttachmentLink)
        .filter(EntityAttachmentLink.id == str(link_id or "").strip())
        .first()
    )
    if link is None:
        raise handle_not_found("Attachment link", link_id)

    if not _did_fail(db, link):
        raise handle_validation_error(
            "This file did not fail its check, so there is nothing to override."
        )

    link.override_reason = text
    db.flush()
    logger.info("Attachment validation overridden link=%s by=%s", link.id, user_id)
    return link


def _did_fail(db: Session, link: EntityAttachmentLink) -> bool:
    """True only for a link that was JUDGED and fell short of a real threshold."""
    if getattr(link, "ai_validation_state", None) != STATE_SCORED:
        return False
    score = getattr(link, "ai_score", None)
    if score is None:
        return False
    threshold = _threshold_for(db, link)
    if threshold is None:
        return False
    try:
        return int(score) < int(threshold)
    except (TypeError, ValueError):
        return False


def _threshold_for(db: Session, link: EntityAttachmentLink) -> Optional[int]:
    """The min_score of the type this link's file belongs to, or None."""
    attachment = getattr(link, "attachment", None)
    type_id = getattr(attachment, "attachment_type_id", None) if attachment else None
    if not type_id:
        return None
    row = (
        db.query(AttachmentType.min_score)
        .filter(AttachmentType.id == str(type_id))
        .first()
    )
    return row[0] if row else None


# --------------------------------------------------------------------------- #
# Capture pin                                                                   #
# --------------------------------------------------------------------------- #


def normalize_coordinates(latitude: Any, longitude: Any) -> tuple[Any, Any]:
    """Where the photo was taken, or (None, None). Never raises, never blocks.

    AC-M27 says geolocation never blocks an upload, so a browser that said no, a
    browser that handed back nonsense and a device that reported a failed fix are all
    the same answer: omitted.

    Half a fix is dropped whole. A lone latitude is not a place - stored alone it
    renders as a pin on the prime meridian off the coast of Ghana, presented as where
    the photo was taken. Exactly (0, 0) is dropped for the same reason: it is the
    classic no-fix sentinel, and Sorento operates in Malaysia, so the odds it is a
    real reading are nil. That last one is a DECISION with no AC behind it.
    """
    lat = _coordinate(latitude, _LATITUDE_LIMIT)
    lon = _coordinate(longitude, _LONGITUDE_LIMIT)
    if lat is None or lon is None:
        return None, None
    if lat == 0 and lon == 0:
        return None, None
    return lat, lon


def _coordinate(value: Any, limit: Decimal) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    if not parsed.is_finite():
        return None
    if parsed < -limit or parsed > limit:
        return None
    return parsed.quantize(_COORDINATE_QUANTUM, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# Internals                                                                     #
# --------------------------------------------------------------------------- #


def _render_prompt(db: Session, guidance: str) -> str:
    """The registry's live text with the type's guidance substituted in.

    The prompt is registry data (AC-M25), so it is versioned, labelled, editable in
    the prompt editor without a deploy, and covered by the hardcoded fallback when the
    database is unreachable. The guidance arrives as a DECLARED variable rather than
    by concatenation, which is what lets the save-time validator refuse a version that
    dropped the token - a prompt that judges every file against nothing.
    """
    text, _version = ai_prompt_registry.render(
        db, PROMPT_KEY, **{PROMPT_VARIABLE: guidance}
    )
    return text


def _resolve_provider(db: Session) -> tuple[Optional[LLMProvider], Optional[str]]:
    """The configured provider, or (None, None). NEVER an exception.

    Same source as every other AI call site, one difference that is the whole point:
    a missing key is not an error here. Raising would turn every photo upload on a
    fresh install into a failure for a feature that is advisory.
    """
    try:
        from app.models.ai_assistant import AIAssistantConfig

        cfg = (
            db.query(AIAssistantConfig)
            .order_by(AIAssistantConfig.created_at.asc())
            .first()
        )
    except Exception:  # noqa: BLE001
        logger.warning("Attachment validation provider lookup failed", exc_info=True)
        return None, None

    name = (getattr(cfg, "provider", None) or "openai") if cfg else "openai"
    model_name = ((getattr(cfg, "model", None) or "") if cfg else "") or ""
    api_key = ((getattr(cfg, "api_key_ciphertext", None) or "") if cfg else "") or (
        getattr(settings, "openai_api_key", "") or ""
    )
    if not api_key:
        return None, None
    if not model_name:
        model_name = "gpt-4o" if name == "openai" else "claude-sonnet-4-6"
    try:
        return get_provider(name, api_key, model=model_name), model_name
    except Exception:  # noqa: BLE001 - an unknown provider name is a misconfiguration
        logger.warning("Attachment validation provider %s is not usable", name)
        return None, None


def _as_image_part(
    data: Optional[bytes], filename: Optional[str], content_type: Optional[str]
) -> Optional[ImagePart]:
    """The uploaded bytes, ready to send, or None when nothing can look at them."""
    payload = data or b""
    if not payload:
        return None
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    name = (filename or "").strip().lower()
    if mime not in _VIEWABLE_MIMES and not name.endswith(_VIEWABLE_EXTENSIONS):
        logger.info("Attachment validation cannot read mime=%s name=%s", mime, name)
        return None
    if mime == "image/jpg":
        mime = "image/jpeg"
    return ImagePart(
        mime=mime or _DEFAULT_MIME,
        data_b64=base64.b64encode(payload).decode("ascii"),
    )


def _within_budget(work: Callable[[], Any], budget: Optional[float]) -> Any:
    """Run ``work`` on a daemon thread and give up after ``budget`` seconds.

    Enforced here rather than passed to the provider SDK. A delegated deadline is
    exactly what fails on a stalled mobile connection, where the socket never returns
    and no client-side timer is armed. On expiry the thread is abandoned: it is a
    daemon, so it holds nothing open, and its answer is discarded because by then
    somebody has already been told we could not judge the file.
    """
    if not budget or budget <= 0:
        return work()

    box: dict[str, Any] = {}

    def _run() -> None:
        try:
            box["value"] = work()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            box["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(budget)
    if thread.is_alive():
        raise _Expired()
    error = box.get("error")
    if error is not None:
        raise error
    return box.get("value")


def _parse_reply(content: Any) -> Optional[tuple[int, Optional[str]]]:
    """(score, suggestion) from the model's reply, or None if it cannot be trusted.

    None on ANY doubt. `int(...)` on a refusal raises, and a bare `except: score = 0`
    refuses a good file over a parsing accident.
    """
    payload = _load_json(content)
    if payload is None:
        return None
    score = _coerce_score(payload.get("score"))
    if score is None:
        logger.info("Attachment validation reply carried no usable score")
        return None
    raw_suggestion = payload.get("suggestion")
    suggestion = str(raw_suggestion).strip() if raw_suggestion is not None else ""
    return score, (suggestion or None)


def _load_json(content: Any) -> Optional[dict]:
    if not content or not isinstance(content, str):
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except (ValueError, TypeError):
            return None
    return parsed if isinstance(parsed, dict) else None


def _coerce_score(raw: Any) -> Optional[int]:
    """An integer on OUR scale, or None. Never rounded and never clamped.

    A value strictly between 0 and 1 is the 0.0-1.0 scale half the world uses. Rounded
    onto 0-100 it becomes 1 and a good file is refused, so it is refused as
    unparseable instead - silent rounding here is always wrong in the direction that
    rejects. An out-of-range value is refused for the mirror-image reason: clamping
    1000 to 100 passes a file on an answer nobody can explain, and clamping -5 to 0
    fails one.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return None
        try:
            raw = float(stripped)
        except ValueError:
            return None
    if isinstance(raw, float):
        if not math.isfinite(raw) or not raw.is_integer():
            return None
        raw = int(raw)
    if not isinstance(raw, int):
        return None
    if raw < SCORE_MIN or raw > SCORE_MAX:
        return None
    return raw
