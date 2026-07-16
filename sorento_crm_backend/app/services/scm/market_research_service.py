"""SCM M5 Part B — market research service (advisory-only web-search signals).

Two halves, with a hard line between them:

- **Fully real + verifiable (no external key needed):** topic CRUD, signal reads
  (joined to their topic for the human label), and the ``market_research_run``
  observability row. These persist and serialize deterministically.
- **Key-gated (Anthropic web search):** ``_web_search_topic`` is the ONLY part
  that reaches the network. Without ``ANTHROPIC_API_KEY`` it returns ``[]`` and
  ``run_research`` records a ``status='failed'`` run with a clear error — never a
  crash. Tests monkeypatch ``_web_search_topic`` to inject synthetic signals and
  exercise the whole persistence path with no network.

LLM boundary (AC-M5.8): this service writes ONLY the ``scm.market_signal`` table
(+ its run log). It NEVER writes a numeric field on ``reorder_recommendation`` —
signals are their own advisory-only table; the deterministic engine never reads
them.

TODO (M5 fast-follow): a ``scheduled_task`` (``scm_market_research``) should call
``run_research`` on each topic's cadence. Kept synchronous + manual for now.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.scm import MarketResearchRun, MarketResearchTopic, MarketSignal
from app.schemas.scm_market import MarketResearchTopicWrite
from app.services.error_handler import AppException
from app.services.scm import explainer_service

logger = logging.getLogger(__name__)

# The honest degrade message surfaced on the run row when no web-search key is set.
NO_KEY_ERROR = "Anthropic web-search not configured (set ANTHROPIC_API_KEY)"

# ⚠ CONFIRM AGAINST CURRENT ANTHROPIC DOCS BEFORE ENABLING IN PROD. The web-search
# server-tool type string and the model id below are pinned to what was current at
# authoring time; Anthropic revises both. Read the `claude-api` skill first.
_ANTHROPIC_MODEL = "claude-3-5-sonnet-latest"
_WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
_SEARCH_MAX_TOKENS = 1024
_EXTRACT_MAX_TOKENS = 400
_VALID_TRENDS = {"up", "down", "flat"}


# ---------------------------------------------------------------------------
# key access (single choke-point so tests + the endpoint agree)
# ---------------------------------------------------------------------------

def _anthropic_api_key() -> Optional[str]:
    return getattr(settings, "anthropic_api_key", None) or None


# ---------------------------------------------------------------------------
# serializers (no UUID in any display field — topic_label, not topic_id)
# ---------------------------------------------------------------------------

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _topic_out(t: MarketResearchTopic) -> dict:
    return {
        "id": t.id,
        "label": t.label,
        "category_ref": t.category_ref,
        "currency": t.currency,
        "search_prompt": t.search_prompt or "",
        "cadence": t.cadence or "manual",
        "is_active": bool(t.is_active),
    }


def _signal_out(s: MarketSignal, topic_label: str) -> dict:
    return {
        "id": s.id,
        "topic_label": topic_label,
        "category_ref": s.category_ref,
        "currency": s.currency,
        "value": float(s.value) if s.value is not None else None,
        "trend": s.trend,
        "summary": s.summary or "",
        "source_url": s.source_url,
        "captured_at": _iso(s.captured_at) or _iso(s.created_at) or "",
    }


def _run_out(r: MarketResearchRun) -> dict:
    return {
        "id": r.id,
        "status": r.status,
        "started_at": _iso(r.started_at),
        "finished_at": _iso(r.finished_at),
        "topic_count": int(r.topic_count or 0),
        "signal_count": int(r.signal_count or 0),
        "error": r.error_text,
    }


# ---------------------------------------------------------------------------
# topic CRUD (fully real)
# ---------------------------------------------------------------------------

def list_topics(db: Session) -> list[dict]:
    rows = (
        db.query(MarketResearchTopic)
        .order_by(MarketResearchTopic.created_at.desc())
        .all()
    )
    return [_topic_out(t) for t in rows]


def _get_topic(db: Session, topic_id: str) -> MarketResearchTopic:
    t = (
        db.query(MarketResearchTopic)
        .filter(MarketResearchTopic.id == topic_id)
        .first()
    )
    if not t:
        raise AppException(status_code=404, message="Research topic not found.")
    return t


def create_topic(db: Session, body: MarketResearchTopicWrite) -> dict:
    t = MarketResearchTopic(
        label=body.label,
        category_ref=body.category_ref,
        currency=body.currency,
        search_prompt=body.search_prompt or "",
        cadence=body.cadence or "manual",
        is_active=body.is_active,
        source_system="manual",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _topic_out(t)


def update_topic(db: Session, topic_id: str, body: MarketResearchTopicWrite) -> dict:
    t = _get_topic(db, topic_id)
    t.label = body.label
    t.category_ref = body.category_ref
    t.currency = body.currency
    t.search_prompt = body.search_prompt or ""
    t.cadence = body.cadence or "manual"
    t.is_active = body.is_active
    db.commit()
    db.refresh(t)
    return _topic_out(t)


def delete_topic(db: Session, topic_id: str) -> None:
    t = _get_topic(db, topic_id)
    db.delete(t)  # hard delete; signals cascade via FK ON DELETE CASCADE
    db.commit()


# ---------------------------------------------------------------------------
# signal reads (fully real)
# ---------------------------------------------------------------------------

def list_signals(db: Session) -> list[dict]:
    """All cached signals, newest-captured first, each carrying its topic's human
    label (LEFT JOIN so a signal outlives nothing but degrades to a placeholder
    label if the topic FK is somehow null)."""
    rows = (
        db.query(MarketSignal, MarketResearchTopic.label)
        .outerjoin(
            MarketResearchTopic, MarketResearchTopic.id == MarketSignal.topic_id
        )
        .order_by(
            MarketSignal.captured_at.desc().nullslast(),
            MarketSignal.created_at.desc(),
        )
        .all()
    )
    return [_signal_out(s, label or "—") for s, label in rows]


def get_run(db: Session, run_id: str) -> dict:
    r = db.query(MarketResearchRun).filter(MarketResearchRun.id == run_id).first()
    if not r:
        raise AppException(status_code=404, message="Research run not found.")
    return _run_out(r)


# ---------------------------------------------------------------------------
# research run (persistence real; web search key-gated)
# ---------------------------------------------------------------------------

def run_research(db: Session, actor: Optional[str] = None) -> dict:
    """Create a run, search each ACTIVE topic, persist extracted signals, and log
    the run. No Anthropic key → a valid ``status='failed'`` run row (0 signals) for
    observability, never a crash. Per-topic failures are trapped so one bad topic
    doesn't sink the whole run (they're appended to the run's error text)."""
    started = datetime.utcnow()
    run = MarketResearchRun(status="running", started_at=started, source_system="manual")
    db.add(run)
    db.flush()  # assign run.id

    topics = (
        db.query(MarketResearchTopic)
        .filter(MarketResearchTopic.is_active.is_(True))
        .all()
    )
    run.topic_count = len(topics)

    if not _anthropic_api_key():
        run.status = "failed"
        run.error_text = NO_KEY_ERROR
        run.signal_count = 0
        run.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(run)
        return _run_out(run)

    signal_count = 0
    errors: list[str] = []
    for topic in topics:
        try:
            extracted = _web_search_topic(db, topic)
        except Exception as exc:  # one bad topic must not sink the run
            logger.exception("market research: topic %s failed", topic.id)
            errors.append(f"{topic.label}: {exc}")
            continue
        for item in extracted or []:
            summary = (item.get("summary") or "").strip()
            if not summary:
                continue  # a signal with no readable summary is not worth caching
            trend = item.get("trend")
            if trend not in _VALID_TRENDS:
                trend = None
            db.add(
                MarketSignal(
                    topic_id=topic.id,
                    category_ref=topic.category_ref,
                    currency=topic.currency,
                    value=_coerce_num(item.get("value")),
                    trend=trend,
                    summary=summary,
                    source_url=item.get("source_url"),
                    captured_at=datetime.utcnow(),
                    source_system="web_search",
                )
            )
            signal_count += 1

    run.signal_count = signal_count
    # failed = every topic errored and nothing landed; otherwise completed (any
    # per-topic errors are still logged on the run's error_text for observability).
    run.status = "failed" if (errors and signal_count == 0) else "completed"
    run.finished_at = datetime.utcnow()
    if errors:
        run.error_text = "; ".join(errors)[:2000]
    db.commit()
    db.refresh(run)
    return _run_out(run)


def _coerce_num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# KEY-GATED: Anthropic web search + schema-forced extraction (isolated so tests
# monkeypatch this one function)
# ---------------------------------------------------------------------------

def _web_search_topic(db: Session, topic: MarketResearchTopic) -> list[dict]:
    """Search one topic and return 0+ extracted signal dicts
    ``{value, trend, summary, source_url}``.

    KEY-GATED: returns ``[]`` when no Anthropic key is configured. Tests monkeypatch
    this whole function; the rest of ``run_research`` is exercised without network.
    """
    key = _anthropic_api_key()
    if not key:
        return []
    search_text = _anthropic_web_search(topic.search_prompt or topic.label, key)
    if not search_text:
        return []
    return _extract_signals(db, topic, search_text)


def _anthropic_web_search(prompt: str, api_key: str) -> str:
    """Raw Anthropic SDK call with the web-search SERVER tool. Returns the model's
    concatenated text output (which cites the figures/URLs it found).

    ⚠ The tool version string + model id are pinned to authoring-time values and MUST
    be re-confirmed against current Anthropic docs before enabling in prod.
    """
    import anthropic  # local import: optional dep, only needed on the key-gated path

    client = anthropic.Anthropic(api_key=api_key)
    instruction = (
        "\n\nUsing web search, report the single most relevant current figure for the "
        "above (a price, index level, %, or rate), whether it is trending up, down or "
        "flat, a one-line plain-language summary a supply-chain planner can act on, and "
        "the source URL you took the figure from. Be concise."
    )
    resp = client.messages.create(
        model=_ANTHROPIC_MODEL,
        max_tokens=_SEARCH_MAX_TOKENS,
        tools=[_WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": f"{prompt}{instruction}"}],
    )
    parts: list[str] = []
    for block in getattr(resp, "content", None) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts).strip()


_EXTRACT_SYSTEM = (
    "You extract STRUCTURED market signals from web-search result text for a supply-"
    "chain tool. Return ONLY JSON of the form "
    '{"signals": [{"value": <number|null>, "trend": "up"|"down"|"flat"|null, '
    '"summary": <one-line string>, "source_url": <url|null>}]}. '
    "Use only figures that appear in the given text — never invent or compute a number. "
    "If the text has no usable figure, still emit a signal with value=null and a "
    "qualitative summary. Output at most 2 signals."
)


def _extract_signals(db: Session, topic: MarketResearchTopic, search_text: str) -> list[dict]:
    """Second pass: schema-forced JSON extraction from the web-search prose. Uses the
    shared assistant provider (OpenAI is fine for extraction). Never fabricates a
    number — it only lifts figures already present in ``search_text``."""
    provider, model = explainer_service._provider_and_model(db)
    if provider is None:
        return []
    user_block = (
        "Web-search result text to extract from:\n"
        f"{search_text}\n\n"
        "Emit the signals JSON now."
    )
    result = provider.chat(
        [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user", "content": user_block},
        ],
        temperature=0.0,
        model=model,
        max_tokens=_EXTRACT_MAX_TOKENS,
        response_format={"type": "json_object"},
    )
    raw = (result.content or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    signals = parsed.get("signals") if isinstance(parsed, dict) else None
    if not isinstance(signals, list):
        # Tolerate a bare object as a single signal.
        signals = [parsed] if isinstance(parsed, dict) else []
    return [s for s in signals if isinstance(s, dict)]
