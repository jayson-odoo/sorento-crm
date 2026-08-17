"""Chatbot media: settings resolution, the gate, and the fast path.

See `documentation/plans/ideation/PLAN-chatbot-media-endpoint.md` sections 2 and 3.

Everything here is milliseconds of ordinary SQLAlchemy work. It decides, meters
and records **before any money is spent**, and it commits before the caller
starts waiting on the worker - so the ledger row and the decision are durable
even if the wait or the worker later dies.

Two directions of failure, deliberately opposite, and the PR must say so:

* the **gate fails closed** - no `contact_media_limit` row, or `is_allowed=false`,
  is a refusal. This is an entitlement, not an abuse ceiling.
* the **burst limiter fails open** - it runs on Redis via the existing
  `rate_limit.hit` primitive, and an infra outage must not stop a paying dealer
  sending a photo. Pacing is the only control here that is genuinely ephemeral.

Nothing in this module caches: a changed system default takes effect on the very
next call, which is what "without a deploy" has to mean.
"""
from __future__ import annotations

import calendar
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, cast
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.media import (
    MEDIA_MODALITIES,
    QUOTA_CONSUMING_OUTCOMES,
    ContactMediaLimit,
    ContactMediaUsage,
    MediaExtractionJob,
)
from app.models.user import SystemSetting
from app.services import rate_limit
from app.services.media_extract import wording

logger = logging.getLogger(__name__)

MALAYSIA_TZ = ZoneInfo("Asia/Kuala_Lumpur")

# Redis buckets. Namespaced so the media pacing counter can never collide with
# the signup/OTP limiters that share the primitive.
_BURST_BUCKET = "media_burst"
_BURST_NOTICE_BUCKET = "media_burst_notice"

# Operator-editable bounds (PLAN 2.4). Enforced here as well as in the settings
# validator, because a number only the UI refuses is not a constraint.
SYNC_WAIT_MIN_SECONDS = 5
SYNC_WAIT_MAX_SECONDS = 90
EXTRACTION_TIMEOUT_MIN_SECONDS = 5
EXTRACTION_TIMEOUT_MAX_SECONDS = 110

# Fallbacks used when `system_settings` has no row at all (a blank install) or a
# nullable column has never been written. Mirrors PLAN section 2.4.
_DEFAULTS: dict[str, Any] = {
    "image_monthly_limit": 50,
    "voice_monthly_limit": 100,
    "voice_max_seconds": 120,
    "burst_limit": 5,
    "burst_window_seconds": 60,
    "warn_threshold_percent": 80,
    "transcribe_model": "whisper-1",
    "language_mode": "pinned",
    "language_pinned": "en",
    "language_hints": "en,ms,zh",
    "sync_wait_seconds": 30,
    "extraction_timeout_seconds": 45,
    "max_entities": 10,
}


def _now_utc() -> datetime:
    """The single seam through which this module reads "now".

    A module-level callable rather than an inline `datetime.now()` so a test can
    pin the instant instead of sleeping until a real month boundary - the period
    is computed in Asia/Kuala_Lumpur, so the interesting cases are exactly the
    ones that only occur for eight hours a month.
    """
    return datetime.now(timezone.utc)


def _as_malaysia(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(MALAYSIA_TZ)


def period_key_for(moment: Optional[datetime] = None) -> str:
    """`YYYY-MM` in Asia/Kuala_Lumpur. n8n never does this arithmetic."""
    local = _as_malaysia(moment or _now_utc())
    return f"{local.year:04d}-{local.month:02d}"


def resets_on_label(moment: Optional[datetime] = None) -> str:
    """The reset date already rendered for a human: "1 September".

    Returned rendered, never as an ISO date, because every consumer of this - the
    operator card, the customer notice, n8n - would otherwise have to format it,
    and three formatters is three ways to disagree.
    """
    local = _as_malaysia(moment or _now_utc())
    # The year is not rendered: "1 January" is unambiguous next to a reset that is
    # always within a month, and a year would read as a due date rather than a
    # rollover.
    month = 1 if local.month == 12 else local.month + 1
    return f"1 {calendar.month_name[month]}"


@dataclass
class MediaSettings:
    """The resolved `media_*` settings, without the column prefix.

    This is the resolved object, not the row: `image_monthly_limit`, not
    `media_image_monthly_limit`. Callers should never read the ORM row directly,
    so the fallback-when-NULL rules live in exactly one place.
    """

    image_monthly_limit: int
    voice_monthly_limit: int
    voice_max_seconds: int
    burst_limit: int
    burst_window_seconds: int
    warn_threshold_percent: int
    image_provider: Optional[str]
    image_model: Optional[str]
    image_degraded_model: Optional[str]
    transcribe_model: str
    voice_degraded_model: Optional[str]
    language_mode: str
    language_pinned: str
    language_hints: list[str]
    sync_wait_seconds: float
    extraction_timeout_seconds: float
    max_entities: int

    def monthly_limit_for(self, modality: str) -> int:
        return (
            self.voice_monthly_limit if modality == "voice" else self.image_monthly_limit
        )

    def degraded_model_for(self, modality: str) -> Optional[str]:
        """The degraded model for THIS modality, or None if there is not one.

        Per modality, not shared: reading the image column for a voice note
        degraded a transcription that then ran on exactly the same model as
        always, so the voice quota was decorative and the contact was told their
        accuracy had dropped when nothing had changed. None means the quota is a
        hard refusal, which is what PLAN 3.2 specifies for an unconfigured
        degraded tier and is the honest answer while no cheaper transcription
        model has been measured.
        """
        return (
            self.voice_degraded_model
            if modality == "voice"
            else self.image_degraded_model
        )

    def language_strategy(self) -> dict:
        """The transcription request shape, built at call time from settings."""
        if self.language_mode == "hints":
            return {"mode": "hints", "languages": list(self.language_hints)}
        if self.language_mode == "auto":
            return {"mode": "auto"}
        return {"mode": "pinned", "language": self.language_pinned}


def _column(row: Optional[SystemSetting], name: str, key: str) -> Any:
    """Read a `media_*` column, falling back to the plan default when unwritten."""
    value = getattr(row, name, None) if row is not None else None
    return _DEFAULTS[key] if value is None else value


def resolve_media_settings(db: Session) -> MediaSettings:
    """Read the `system_settings` singleton's `media_*` columns, live.

    No cache by design (UAC S1-07 / S1-09): the operator changes a number on the
    settings page and the very next media call obeys it.
    """
    row = db.query(SystemSetting).first()
    hints_csv = str(_column(row, "media_language_hints", "language_hints") or "")
    sync_wait = _clamp(
        _column(row, "media_sync_wait_seconds", "sync_wait_seconds"),
        SYNC_WAIT_MIN_SECONDS,
        SYNC_WAIT_MAX_SECONDS,
    )
    extraction_timeout = _clamp(
        _column(row, "media_extraction_timeout_seconds", "extraction_timeout_seconds"),
        EXTRACTION_TIMEOUT_MIN_SECONDS,
        EXTRACTION_TIMEOUT_MAX_SECONDS,
    )
    # The inequality is the point of the pair (UAC S3-01d): a job that outlives
    # the wait must still be inside the worker's own ceiling, or it is killed
    # mid-flight instead of degrading to the callback.
    extraction_timeout = max(extraction_timeout, sync_wait)
    return MediaSettings(
        image_monthly_limit=int(_column(row, "media_image_monthly_limit", "image_monthly_limit")),
        voice_monthly_limit=int(_column(row, "media_voice_monthly_limit", "voice_monthly_limit")),
        voice_max_seconds=int(_column(row, "media_voice_max_seconds", "voice_max_seconds")),
        burst_limit=int(_column(row, "media_burst_limit", "burst_limit")),
        burst_window_seconds=int(_column(row, "media_burst_window_seconds", "burst_window_seconds")),
        warn_threshold_percent=int(
            _column(row, "media_warn_threshold_percent", "warn_threshold_percent")
        ),
        # NULL is meaningful for all four of these, so they are read raw: the two
        # provider columns inherit the AIAssistantConfig row, and a NULL degraded
        # model means degradation is impossible FOR THAT MODALITY. Image ships
        # seeded (migration 358, measured in PLAN 14.1); voice ships unseeded,
        # because no cheaper transcription model has been measured.
        image_provider=getattr(row, "media_image_provider", None) if row else None,
        image_model=getattr(row, "media_image_model", None) if row else None,
        image_degraded_model=getattr(row, "media_image_degraded_model", None) if row else None,
        transcribe_model=str(_column(row, "media_transcribe_model", "transcribe_model")),
        voice_degraded_model=getattr(row, "media_voice_degraded_model", None) if row else None,
        language_mode=str(_column(row, "media_language_mode", "language_mode")),
        language_pinned=str(_column(row, "media_language_pinned", "language_pinned")),
        language_hints=[part.strip() for part in hints_csv.split(",") if part.strip()],
        sync_wait_seconds=sync_wait,
        extraction_timeout_seconds=extraction_timeout,
        max_entities=int(_column(row, "media_max_entities", "max_entities")),
    )


def _clamp(value: Any, low: int, high: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(low)
    return max(low, min(high, number))


def get_limit_row(
    db: Session, contact_id: str, modality: str, *, for_update: bool = False
) -> Optional[ContactMediaLimit]:
    """The gate row, or None.

    `for_update` takes a row lock for the rest of the transaction. The fast path
    uses it so two requests for the same contact decide the quota one after the
    other rather than both reading `used = limit - 1` and both passing; the same
    lock serializes the once-per-period notice stamps on the row.
    """
    query = db.query(ContactMediaLimit).filter(
        ContactMediaLimit.contact_id == contact_id,
        ContactMediaLimit.modality == modality,
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def resolve_effective_limit(
    db: Session,
    contact_id: str,
    modality: str,
    *,
    settings: Optional[MediaSettings] = None,
) -> int:
    """The monthly limit actually in force for this contact and modality.

    Answers independently of whether the modality is currently *allowed*: a
    never-configured contact still has an effective limit, it just has no row
    granting access to spend against it. That is what lets the operator card show
    `has_row: false` alongside a real number instead of a blank.

    `settings` is an optimisation only - a caller that has already resolved them
    passes them in to save a query. Omitting it re-reads, which is what makes a
    changed default take effect on the very next call.
    """
    row = get_limit_row(db, contact_id, modality)
    if row is not None and row.monthly_limit is not None:
        return int(row.monthly_limit)
    return (settings or resolve_media_settings(db)).monthly_limit_for(modality)


def effective_clip_seconds(
    limit_row: Optional[ContactMediaLimit], settings: MediaSettings
) -> int:
    """The voice clip cap in force: the contact's override, else the default.

    Takes the row rather than the contact id so every caller that already has it
    (the operator card, the fast path) reuses the rule without a second query,
    and the worker - which measures the real clip length before transcribing -
    applies exactly the same number the fast path did.
    """
    if limit_row is not None and limit_row.max_clip_seconds is not None:
        return int(limit_row.max_clip_seconds)
    return int(settings.voice_max_seconds)


def count_usage(
    db: Session, respond_io_id: str, modality: str, period_key: str
) -> int:
    """Items consumed this period. Refusals never count (UAC S2-04)."""
    return (
        db.query(func.count(ContactMediaUsage.id))
        .filter(
            ContactMediaUsage.respond_io_id == respond_io_id,
            ContactMediaUsage.modality == modality,
            ContactMediaUsage.period_key == period_key,
            ContactMediaUsage.outcome.in_(QUOTA_CONSUMING_OUTCOMES),
        )
        .scalar()
        or 0
    )


def mark_usage_outcome(
    db: Session,
    usage_id: Optional[str],
    outcome: str,
    notices: Optional[list[dict]] = None,
) -> None:
    """Re-stamp an accepted ledger row once its fate is known.

    The only writer of `outcome` after the insert, so whether an item consumes
    the contact's allowance stays decided in one place: `failed` still consumes
    (the provider was called and the money was spent), while `not_queued`
    (nothing ran) and `refused_duration` (refused before the transcription call)
    do not. Only an `accepted` row is re-stamped - a refusal was already final
    and a second terminal write must not move it.

    `notices` is the customer-facing text that outcome produced, written onto
    the same row under the same guard because the callback and the polling
    endpoint read it from there. Omitting it leaves whatever the insert wrote
    alone, so an ordinary outcome flip never blanks an existing notice.
    """
    if usage_id is None:
        return
    usage = (
        db.query(ContactMediaUsage).filter(ContactMediaUsage.id == usage_id).first()
    )
    if usage is not None and usage.outcome == "accepted":
        usage.outcome = outcome
        if notices is not None:
            usage.notices = notices


# --------------------------------------------------------------------------- #
# The operator surface (PLAN 3.6)                                             #
# --------------------------------------------------------------------------- #


def _used_for_contact(
    db: Session, contact_id: str, modality: str, period_key: str
) -> int:
    """Consumption for the operator card.

    Keyed on `contact_id` rather than `respond_io_id` because this is the
    reporting question ("what has this contact used"), not the enforcement one.
    Refusals never count, so a contact refused fifty times still shows their full
    allowance - which is the number the operator turning access on needs to see.
    """
    return (
        db.query(func.count(ContactMediaUsage.id))
        .filter(
            ContactMediaUsage.contact_id == contact_id,
            ContactMediaUsage.modality == modality,
            ContactMediaUsage.period_key == period_key,
            ContactMediaUsage.outcome.in_(QUOTA_CONSUMING_OUTCOMES),
        )
        .scalar()
        or 0
    )


def _updated_by_name(db: Session, updated_by: Optional[str]) -> Optional[str]:
    """Resolve the stored id to a name. No UUID ever reaches the UI."""
    if not updated_by:
        return None
    from app.models.user import User

    user = db.query(User).filter(User.id == updated_by).first()
    return getattr(user, "name", None) or None


def build_access_item(
    db: Session,
    contact_id: str,
    modality: str,
    *,
    settings: Optional[MediaSettings] = None,
    period_key: Optional[str] = None,
) -> dict:
    """One modality's row for the contact Media Access card.

    `has_row` is deliberately separate from `is_allowed`: "never configured" and
    "somebody turned this off" are different support conversations and the
    operator has to be able to tell them apart.
    """
    settings = settings or resolve_media_settings(db)
    period_key = period_key or period_key_for()
    row = get_limit_row(db, contact_id, modality)

    effective_limit = (
        int(row.monthly_limit)
        if row is not None and row.monthly_limit is not None
        else settings.monthly_limit_for(modality)
    )
    effective_clip = (
        effective_clip_seconds(row, settings) if modality == "voice" else None
    )

    used = _used_for_contact(db, contact_id, modality, period_key)
    return {
        "modality": modality,
        "is_allowed": bool(row.is_allowed) if row is not None else False,
        "has_row": row is not None,
        "monthly_limit": row.monthly_limit if row is not None else None,
        "effective_monthly_limit": effective_limit,
        "max_clip_seconds": row.max_clip_seconds if row is not None else None,
        "effective_max_clip_seconds": effective_clip,
        "used": used,
        "remaining": max(0, effective_limit - used),
        "updated_at": row.updated_at.isoformat() if row is not None and row.updated_at else None,
        "updated_by_name": _updated_by_name(db, row.updated_by if row else None),
    }


def build_access_view(db: Session, contact_id: str) -> dict:
    """The whole card: the period, its rendered reset date, and BOTH modalities.

    Both are always present, in the order image then voice, whether or not a row
    exists - a detail page never hides a section on missing data.
    """
    settings = resolve_media_settings(db)
    now = _now_utc()
    period_key = period_key_for(now)
    return {
        "period_key": period_key,
        "resets_on": resets_on_label(now),
        "items": [
            build_access_item(
                db, contact_id, modality, settings=settings, period_key=period_key
            )
            for modality in MEDIA_MODALITIES
        ],
    }


def upsert_access(
    db: Session,
    contact_id: str,
    modality: str,
    *,
    is_allowed: bool,
    monthly_limit: Optional[int],
    max_clip_seconds: Optional[int],
    updated_by: Optional[str] = None,
) -> dict:
    """Create or update the gate row and return the recomputed item.

    A NULL `monthly_limit` clears the override and returns the contact to the
    system default - live, with no deploy. `max_clip_seconds` is voice-only and
    is ignored for image rather than silently stored where nothing reads it.
    """
    values = {
        "is_allowed": bool(is_allowed),
        "monthly_limit": monthly_limit,
        "max_clip_seconds": max_clip_seconds if modality == "voice" else None,
        "updated_by": updated_by,
        "updated_at": _now_utc().replace(tzinfo=None),
    }
    statement = pg_insert(ContactMediaLimit.__table__).values(
        id=str(uuid.uuid4()),
        contact_id=contact_id,
        modality=modality,
        **values,
    )
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_contact_media_limit_contact_modality", set_=values
        )
    )
    db.flush()
    db.expire_all()
    return build_access_item(db, contact_id, modality)


# --------------------------------------------------------------------------- #
# The fast path                                                               #
# --------------------------------------------------------------------------- #


@dataclass
class MediaRequest:
    """One inbound media item, as n8n describes it."""

    respond_io_id: str
    message_id: str
    modality: str
    media_ordinal: int = 0
    media_url: Optional[str] = None
    mime_type: Optional[str] = None
    caption: Optional[str] = None
    duration_ms: Optional[int] = None
    bytes: Optional[int] = None
    turn_id: Optional[str] = None
    callback_url: Optional[str] = None
    callback_headers: Optional[dict] = None
    context: Optional[dict] = None


@dataclass
class MediaDecision:
    """What the fast path decided, and what it wrote while deciding."""

    decision: str  # accepted | denied_gate | denied_burst | denied_quota | denied_duration
    tier: Optional[str] = None
    idempotent_replay: bool = False
    usage: Optional[ContactMediaUsage] = None
    job: Optional[MediaExtractionJob] = None
    quota: dict = field(default_factory=dict)
    notices: list[dict] = field(default_factory=list)
    language_strategy: Optional[dict] = None

    @property
    def accepted(self) -> bool:
        return self.decision == "accepted"


# Ledger outcome -> the decision the caller is told. `failed` maps back to
# `accepted` because the decision WAS accept; the extraction failed afterwards,
# which is a `status`, not a decision.
_OUTCOME_TO_DECISION = {
    "accepted": "accepted",
    "failed": "accepted",
    "not_queued": "accepted",
    "refused_gate": "denied_gate",
    "refused_burst": "denied_burst",
    "refused_quota": "denied_quota",
    "refused_duration": "denied_duration",
}


def _notice(kind: str, text: str) -> dict:
    """A ready-to-send customer notice.

    Every string comes from `media_extract/wording.py` (S6) so the far end sends
    a string and formats nothing. The shape - ready-to-send text, `append: true`,
    never a substitute for the answer - is the contract.
    """
    return {"kind": kind, "text": text, "append": True}


def decide_and_record(
    db: Session,
    request: MediaRequest,
    *,
    settings: Optional[MediaSettings] = None,
    now: Optional[datetime] = None,
) -> MediaDecision:
    """Steps 1-9 of PLAN section 3.3, in one transaction, before any spend.

    The caller commits. Nothing here performs, enqueues or waits on the
    extraction - it only decides, meters, records and (when accepted) creates the
    job row the caller will enqueue.
    """
    settings = settings or resolve_media_settings(db)
    now = now or _now_utc()
    period_key = period_key_for(now)
    resets_on = resets_on_label(now)

    # 1. Resolve the contact. An unknown contact is a gate refusal, not a 404:
    #    n8n branches on the decision, and "who?" and "not allowed" are the same
    #    answer to the dealer.
    contact = (
        db.query(RespondContact)
        .filter(RespondContact.respond_io_id == request.respond_io_id)
        .first()
    )

    # 2. Idempotency probe. This is what makes n8n's `retryOnFail` cheap rather
    #    than a second spend; nothing below runs on a replay.
    existing = _find_usage(db, request)
    if existing is not None:
        return _replay(db, existing, settings, resets_on)

    # 3. Gate row, locked for the rest of the transaction. Absence of a row is
    #    denial - fail closed, by construction. The lock is what makes the quota
    #    count below a serialized decision per contact and modality: without it
    #    two concurrent items both read `used = limit - 1`, both pass, and both
    #    stamp the once-per-period notices. The burst limiter normally bounds
    #    that overshoot, but it fails open on a Redis outage, so the bound has
    #    to live in the transaction that spends.
    limit_row = (
        get_limit_row(db, contact.id, request.modality, for_update=True)
        if contact is not None
        else None
    )
    limit = (
        resolve_effective_limit(db, contact.id, request.modality, settings=settings)
        if contact is not None
        else settings.monthly_limit_for(request.modality)
    )
    used = count_usage(db, request.respond_io_id, request.modality, period_key)

    def _quota(consumed: int) -> dict:
        return {
            "used": consumed,
            "limit": limit,
            "remaining": max(0, limit - consumed),
            "period_key": period_key,
            "resets_on": resets_on,
        }

    def _refuse(outcome: str, notices: list[dict]) -> MediaDecision:
        usage, inserted = _record(
            db, request, contact, period_key, outcome, tier=None, notices=notices
        )
        if not inserted:
            return _replay(db, usage, settings, resets_on)
        return MediaDecision(
            decision=_OUTCOME_TO_DECISION[outcome],
            tier=None,
            usage=usage,
            quota=_quota(used),
            notices=notices,
        )

    if limit_row is None or not limit_row.is_allowed:
        return _refuse(
            "refused_gate",
            [_notice("not_enabled", wording.not_enabled(request.modality))],
        )

    # 4. Duration cap (voice only), against the effective max clip length. The
    #    stated `duration_ms` is a HINT: it refuses early and cheaply when the
    #    caller is honest, but it is not the authority and its absence is not a
    #    pass. `MediaExtractService` measures the real length off the downloaded
    #    audio and applies this same cap before the transcription is paid for.
    if request.modality == "voice" and request.duration_ms is not None:
        max_seconds = effective_clip_seconds(limit_row, settings)
        if request.duration_ms > max_seconds * 1000:
            return _refuse(
                "refused_duration",
                [_notice("too_long", wording.clip_too_long(max_seconds))],
            )

    # 5. Burst. Redis is correct here and only here: the window is genuinely
    #    ephemeral and a reset is harmless. Fails open.
    burst = rate_limit.hit(
        _BURST_BUCKET,
        request.respond_io_id,
        limit=settings.burst_limit,
        window_seconds=settings.burst_window_seconds,
    )
    if not burst.allowed:
        # One pacing message per window, not one per image - otherwise the
        # message about sending too much becomes the thing sending too much.
        first_in_window = rate_limit.hit(
            _BURST_NOTICE_BUCKET,
            request.respond_io_id,
            limit=1,
            window_seconds=settings.burst_window_seconds,
        ).allowed
        logger.info(
            "media burst limit hit for %s (%s); notice=%s",
            request.respond_io_id,
            request.modality,
            first_in_window,
        )
        notices = (
            [_notice("burst", wording.burst())] if first_in_window else []
        )
        return _refuse("refused_burst", notices)

    # 6. Quota. Over the limit degrades when a degraded model is configured FOR
    #    THIS MODALITY; `denied_quota` is only ever returned when degradation is
    #    impossible. Reading one modality's degraded model for the other would
    #    run the same model at full price and still tell the contact their
    #    accuracy had dropped.
    tier = "standard"
    notices: list[dict] = []
    if used >= limit:
        if not settings.degraded_model_for(request.modality):
            return _refuse(
                "refused_quota",
                [
                    _notice(
                        "quota_exhausted",
                        wording.quota_exhausted(limit, resets_on, request.modality),
                    )
                ],
            )
        tier = "degraded"

    # 8. Notices, stamped in the same transaction so each can fire only once per
    #    period per modality even under a retry.
    #
    #    Computed BEFORE the ledger insert even though the plan numbers it after,
    #    because every input is already known (`used + 1`, and the two
    #    once-per-period stamps on the limit row) and the notices then travel in
    #    the insert itself. The ledger is the metered fact and is append-mostly:
    #    an INSERT followed by an UPDATE of the row just written would make it
    #    churn for no gain.
    used_after = used + 1
    threshold = _warn_threshold_count(limit, settings.warn_threshold_percent)
    if (
        tier == "standard"
        and threshold
        and used_after >= threshold
        and limit_row.warned_period != period_key
    ):
        limit_row.warned_period = period_key
        notices.append(
            _notice(
                "warn_80",
                wording.warn_threshold(
                    max(0, limit - used_after), limit, resets_on, request.modality
                ),
            )
        )
    if tier == "degraded" and limit_row.degraded_notified_period != period_key:
        limit_row.degraded_notified_period = period_key
        notices.append(
            _notice("degraded", wording.degraded(resets_on, request.modality))
        )

    # 7. Record, with the notices on it. Recording precedes spending, so
    #    "crashed after spending, before recording" cannot happen - and storing
    #    the notices on the metered fact is what lets a replay and the callback
    #    carry the same text this response does. The notices are part of what was
    #    decided, not a by-product of rendering it.
    usage, inserted = _record(
        db, request, contact, period_key, "accepted", tier=tier, notices=notices
    )
    if not inserted:
        return _replay(db, usage, settings, resets_on)

    # 9. The job row. The caller enqueues it after the commit, so the worker
    #    cannot pick up a row that is not there yet.
    job = MediaExtractionJob(
        usage_id=usage.id,
        status="queued",
        modality=request.modality,
        tier=tier,
        media_url=request.media_url,
        mime_type=request.mime_type,
        caption=request.caption,
        callback_url=request.callback_url,
        callback_headers=request.callback_headers,
        callback_status="pending" if request.callback_url else None,
        callback_attempts=0,
        context=request.context,
    )
    db.add(job)
    db.flush()

    return MediaDecision(
        decision="accepted",
        tier=tier,
        usage=usage,
        job=job,
        quota=_quota(used_after),
        notices=notices,
        language_strategy=(
            settings.language_strategy() if request.modality == "voice" else None
        ),
    )


# A `queued` job older than the synchronous wait plus this grace, or a `running`
# job older than the extraction ceiling plus this grace, is stranded: no worker
# is going to finish it. The grace absorbs an honest queue backlog.
STRANDED_GRACE_SECONDS = 120.0


def reclaim_stranded_job(
    db: Session,
    job: MediaExtractionJob,
    usage: ContactMediaUsage,
    settings: MediaSettings,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """On an idempotent replay, recover a job nothing else will ever recover.

    Returns True when the caller must enqueue the job again. Three strand paths,
    all closed on the replay itself rather than by a sweeper, because the replay
    IS the retry n8n already sends:

    * `queued` past the synchronous wait plus a grace: the enqueue never landed
      (crash between the usage commit and the enqueue, or Redis lost the RQ
      job). Enqueue again; the task is a no-op on a job that meanwhile finished.
    * `running` past the extraction ceiling plus a grace: the work-horse died
      mid-extraction. Marked failed and the allowance is kept as spent - the
      provider may well have been called - so the contact gets a terminal answer
      instead of `pending` forever.
    * `failed` with the allowance refunded (`not_queued`): nothing ran, so the
      job goes back to `queued`, the ledger back to `accepted`, and it is
      enqueued once more. A job that failed AFTER the provider was called keeps
      its `failed` outcome and is never re-run.
    """
    now = (now or _now_utc()).replace(tzinfo=None)

    def _age(since: Optional[datetime]) -> float:
        if since is None:
            return float("inf")
        return (now - since.replace(tzinfo=None)).total_seconds()

    if job.status == "queued":
        return _age(job.created_at) > settings.sync_wait_seconds + STRANDED_GRACE_SECONDS

    if job.status == "running":
        if _age(job.started_at or job.created_at) > (
            settings.extraction_timeout_seconds + STRANDED_GRACE_SECONDS
        ):
            job.status = "failed"
            job.result = None
            job.error = "Extraction did not finish; the worker running it stopped."
            job.completed_at = now
            mark_usage_outcome(db, usage.id, "failed")
            db.flush()
        return False

    if job.status == "failed" and usage.outcome == "not_queued":
        job.status = "queued"
        job.error = None
        job.result = None
        job.rq_job_id = None
        job.started_at = None
        job.completed_at = None
        usage.outcome = "accepted"
        db.flush()
        return True

    return False


def _warn_threshold_count(limit: int, percent: int) -> int:
    if limit <= 0 or percent <= 0:
        return 0
    return int(math.ceil(limit * percent / 100.0))


def _find_usage(db: Session, request: MediaRequest) -> Optional[ContactMediaUsage]:
    return (
        db.query(ContactMediaUsage)
        .filter(
            ContactMediaUsage.respond_io_id == request.respond_io_id,
            ContactMediaUsage.message_id == request.message_id,
            ContactMediaUsage.modality == request.modality,
            ContactMediaUsage.media_ordinal == request.media_ordinal,
        )
        .first()
    )


def _replay(
    db: Session,
    usage: ContactMediaUsage,
    settings: MediaSettings,
    resets_on: str,
) -> MediaDecision:
    """The stored decision, returned again, with nothing re-run and nothing spent.

    Including the notices it carried. A replay is the response n8n's
    `retryOnFail` actually delivers to the dealer, so returning an empty list
    meant a retried `denied_gate` reached them with no message at all - the one
    case where the customer needs the text most, because there is no extraction
    result to speak for itself.
    """
    job = (
        db.query(MediaExtractionJob)
        .filter(MediaExtractionJob.usage_id == usage.id)
        .first()
    )
    limit = (
        resolve_effective_limit(db, usage.contact_id, usage.modality, settings=settings)
        if usage.contact_id
        else settings.monthly_limit_for(usage.modality)
    )
    used = count_usage(db, usage.respond_io_id, usage.modality, usage.period_key)
    return MediaDecision(
        decision=_OUTCOME_TO_DECISION.get(usage.outcome, "denied_gate"),
        tier=usage.tier,
        idempotent_replay=True,
        usage=usage,
        job=job,
        quota={
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "period_key": usage.period_key,
            "resets_on": resets_on,
        },
        notices=[dict(notice) for notice in cast(list[dict], usage.notices or [])],
        language_strategy=(
            settings.language_strategy() if usage.modality == "voice" else None
        ),
    )


def _record(
    db: Session,
    request: MediaRequest,
    contact: Optional[RespondContact],
    period_key: str,
    outcome: str,
    *,
    tier: Optional[str],
    notices: Optional[list[dict]] = None,
) -> tuple[ContactMediaUsage, bool]:
    """`INSERT ... ON CONFLICT DO NOTHING`, then re-select.

    Returns `(usage, inserted)`. The conflict path (`inserted=False`) is the
    concurrent-duplicate case: two n8n retries racing each other, where the
    loser gets the WINNER's committed row back. The loser must then take the
    replay path rather than act on the row as its own - in particular it must
    not create a second job, which `uq_media_extraction_job_usage_id` would
    reject. `decide_and_record` branches on the flag for exactly that.

    `notices` travels in the insert rather than being written over the row
    afterwards: the ledger is append-mostly and must not churn, and on the
    conflict path the notices that count are the ones the FIRST caller recorded,
    which is exactly what "insert or leave alone" gives.
    """
    statement = (
        pg_insert(ContactMediaUsage.__table__)
        .values(
            respond_io_id=request.respond_io_id,
            contact_id=contact.id if contact is not None else None,
            modality=request.modality,
            message_id=request.message_id,
            media_ordinal=request.media_ordinal,
            period_key=period_key,
            outcome=outcome,
            tier=tier,
            turn_id=request.turn_id,
            bytes=request.bytes,
            duration_ms=request.duration_ms,
            notices=list(notices) if notices else None,
        )
        .on_conflict_do_nothing(constraint="uq_contact_media_usage_idempotency")
    )
    result = db.execute(statement)
    db.flush()
    usage = _find_usage(db, request)
    if usage is None:  # pragma: no cover - only reachable if the insert vanished
        raise RuntimeError("media usage row could not be recorded")
    return usage, result.rowcount == 1
