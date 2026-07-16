"""SCM M5 — bounded semantic explainer (NOT the agent/MCP flow).

Turns a reorder recommendation's FROZEN numbers into plain-language prose and
answers scoped follow-up questions. Hard boundary (AC-M5.3 / AC-M5.8): the LLM
receives already-computed numbers as input and emits prose only — there is NO
tool/agent loop and NO path from LLM output to a numeric field. The only column
this service ever writes is ``recommendation.explanation`` (Text, cached prose).

- ``explain_recommendation`` — lazy: return the cached sentence, else generate
  one from the frozen facts, cache it, return.
- ``answer_question`` — bounded Q&A over the same frozen facts; if a question
  needs a number not in the facts the model must reply with ``REFUSAL`` verbatim.

Reuses the shared ``llm_provider`` + ``ai_prompt_registry`` (prompt key
``scm_recommendation_explainer``, immutable versions + movable labels) + the
``AIAssistantConfig`` provider credentials, so it's governed like every other flow.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.models.ai_assistant import AIAssistantConfig
from app.models.scm import MarketSignal, ReorderRecommendation
from app.config import settings
from app.services.ai_prompt_registry import render
from app.services.error_handler import AppException
from app.services.llm_provider import get_provider
from app.services.scm import reorder_engine

# The exact refusal contract — mirrored by the FE (`explainerMockStore.REFUSAL`)
# and asserted byte-for-byte in tests. The prompt instructs the model to emit this
# verbatim when a question can't be answered from the frozen facts.
REFUSAL = "I can't compute that from this recommendation's data."

_PROMPT_KEY = "scm_recommendation_explainer"
_ADVISORY_PROMPT_KEY = "scm_market_advisory"
_MAX_TOKENS = 220


# ---------------------------------------------------------------------------
# facts (frozen numbers only — this is the LLM's entire world)
# ---------------------------------------------------------------------------

def _num(v: Any) -> Optional[float]:
    return float(v) if v is not None else None


def _rec_facts(rec: ReorderRecommendation) -> dict:
    """The frozen, already-computed numbers the model is allowed to speak. Pulled
    from the recommendation columns + its frozen ``inputs`` snapshot — never
    recomputed here."""
    inp = rec.inputs or {}
    supplier = inp.get("supplier") or {}
    facts = {
        "sku": inp.get("sku"),
        "product_name": inp.get("product_name"),
        "type": rec.rec_type,
        "order_quantity": _num(rec.rounded_qty),
        "reorder_point": _num(rec.reorder_point),
        "net_position": _num(rec.net_position),
        "days_of_cover": _num(rec.days_of_cover),
        "forecast_daily_demand": _num(rec.forecast_daily_demand),
        "safety_stock": _num(inp.get("safety_stock")),
        "lead_time_days": _num(inp.get("lead_time_days")),
        "unit_cost": _num(rec.unit_cost),
        "cash_impact": _num(rec.cash_impact),
        "currency": rec.currency,
        "policy_type": inp.get("policy_type"),
        "triggered_reason": rec.triggered_reason,
        "supplier_name": supplier.get("supplier_name"),
        "supplier_lead_time_days": _num(supplier.get("lead_time_days")),
        "confidence": rec.confidence_band,
    }
    # Drop keys with no value so the model can't mistake a null for a real number.
    return {k: v for k, v in facts.items() if v is not None and v != ""}


# ---------------------------------------------------------------------------
# provider
# ---------------------------------------------------------------------------

def _provider_and_model(db: Session):
    """(provider, model) from the shared assistant config, or (None, None) when
    no API key is configured — callers degrade gracefully, never raise."""
    config = (
        db.query(AIAssistantConfig)
        .order_by(AIAssistantConfig.created_at.asc())
        .first()
    )
    api_key = (config.api_key_ciphertext if config else None) or getattr(
        settings, "openai_api_key", None
    )
    # config is None (empty config table) still degrades gracefully even when a
    # global env key is set — never raise (the docstring contract).
    if not api_key or config is None:
        return None, None
    provider = get_provider(config.provider, api_key, config.model)
    return provider, config.model


def _get_rec(db: Session, rec_id: str) -> ReorderRecommendation:
    rec = (
        db.query(ReorderRecommendation)
        .filter(ReorderRecommendation.id == rec_id)
        .first()
    )
    if not rec:
        raise AppException(status_code=404, message="Recommendation not found.")
    return rec


def _chat(db: Session, provider, model: Optional[str], user_block: str) -> str:
    system = render(db, _PROMPT_KEY)[0]
    result = provider.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_block},
        ],
        temperature=0.0,
        model=model,
        max_tokens=_MAX_TOKENS,
    )
    return (result.content or "").strip()


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def explain_recommendation(db: Session, rec_id: str) -> str:
    """Lazy, cached one-sentence explanation of a recommendation (AC-M5.1)."""
    rec = _get_rec(db, rec_id)
    if rec.explanation:
        return rec.explanation

    provider, model = _provider_and_model(db)
    if provider is None:
        # No LLM configured — degrade to a deterministic sentence (never blocks the
        # UI, never fabricates: it only restates frozen facts). Not cached.
        return _deterministic_explanation(rec)

    facts = _rec_facts(rec)
    user_block = (
        "EXPLAIN mode. Recommendation facts (JSON — the ONLY numbers you may use):\n"
        f"{json.dumps(facts, ensure_ascii=False)}\n\n"
        "Write one plain sentence telling the planner what to do and why."
    )
    text = _chat(db, provider, model, user_block)
    if text:
        rec.explanation = text  # the ONLY write — prose, never a numeric field
        db.flush()
    return text or _deterministic_explanation(rec)


def answer_question(db: Session, rec_id: str, question: str) -> str:
    """Bounded Q&A over a recommendation's frozen facts (AC-M5.2). A question that
    needs a number not in the facts returns ``REFUSAL`` verbatim — never a figure."""
    if not (question or "").strip():
        raise AppException(status_code=422, message="A question is required.")
    rec = _get_rec(db, rec_id)

    provider, model = _provider_and_model(db)
    if provider is None:
        return REFUSAL

    facts = _rec_facts(rec)
    user_block = (
        "ASK mode. Recommendation facts (JSON — the ONLY numbers you may use):\n"
        f"{json.dumps(facts, ensure_ascii=False)}\n\n"
        f"Planner's question: {question.strip()}\n\n"
        f'If the answer needs anything not in the facts, reply EXACTLY: "{REFUSAL}"'
    )
    text = _chat(db, provider, model, user_block)
    return text or REFUSAL


def market_advisory(db: Session, rec_id: str) -> Optional[str]:
    """Market advisory for a recommendation (M5 Part B).

    Lazy + cached: return the cached advisory if present. Else find the most recent
    ``market_signal`` matching this rec by **product category + currency**; if one
    exists, condense it into ONE advisory sentence (LLM ADVISORY mode — never a new
    number), cache it to ``rec.market_advisory`` (the ONLY write), and return it. No
    matching signal → ``None``. Advisory is decision-support prose from a STORED
    signal — the LLM never searches and never touches a numeric column."""
    rec = _get_rec(db, rec_id)
    if rec.market_advisory:
        return rec.market_advisory

    signal = _match_market_signal(db, rec)
    if signal is None:
        return None

    provider, model = _provider_and_model(db)
    if provider is None:
        # No LLM configured — the stored signal's own summary IS advisory prose
        # (restates the captured signal, invents nothing). Not cached, so a later
        # LLM-enabled view can still generate the condensed sentence.
        return (signal.summary or None)

    text = _advisory_chat(db, provider, model, rec, signal)
    if text:
        rec.market_advisory = text  # the ONLY write — prose, never a numeric field
        db.flush()
    return text or (signal.summary or None)


def _rec_currency(rec: ReorderRecommendation) -> Optional[str]:
    """Currency to match signals on: the rec's own currency, else the frozen
    supplier/inputs currency."""
    if rec.currency:
        return rec.currency
    inp = rec.inputs or {}
    supplier = inp.get("supplier") or {}
    return supplier.get("currency") or inp.get("currency")


def _rec_category_refs(db: Session, rec: ReorderRecommendation) -> list[str]:
    """The category tokens a signal could be keyed by for this rec — BOTH the
    category **id** (what the topic picker stores as ``category_ref``) and the
    human ``category_code`` — so a signal matches regardless of which the config
    used. Value-space-agnostic on purpose (the FE stores the id)."""
    refs: list[str] = []
    cat_id = db.execute(
        text("SELECT category_id::text FROM products WHERE id = :p"),
        {"p": rec.product_id},
    ).scalar()
    if cat_id:
        refs.append(cat_id)
    code = reorder_engine.load_category_code(db, rec.product_id)
    if code:
        refs.append(code)
    return refs


def _match_market_signal(
    db: Session, rec: ReorderRecommendation
) -> Optional[MarketSignal]:
    """Most-recent cached signal matching the rec by product category (+ currency).

    Category is matched on the product's category id OR code (a topic configured
    through the UI stores the id; a legacy/code-keyed signal still matches).
    Currency: a currencied rec matches a signal of the same currency OR a
    currency-agnostic (null) signal; a rec with NO resolvable currency matches
    only currency-agnostic signals (never a wrong-currency one)."""
    refs = _rec_category_refs(db, rec)
    if not refs:
        return None
    q = db.query(MarketSignal).filter(MarketSignal.category_ref.in_(refs))
    currency = _rec_currency(rec)
    if currency:
        q = q.filter(
            or_(MarketSignal.currency == currency, MarketSignal.currency.is_(None))
        )
    else:
        q = q.filter(MarketSignal.currency.is_(None))
    return (
        q.order_by(
            MarketSignal.captured_at.desc().nullslast(),
            MarketSignal.created_at.desc(),
        ).first()
    )


def _advisory_chat(
    db: Session,
    provider,
    model: Optional[str],
    rec: ReorderRecommendation,
    signal: MarketSignal,
) -> str:
    """Render the ADVISORY prompt and condense the stored signal into one sentence."""
    system = render(db, _ADVISORY_PROMPT_KEY)[0]
    inp = rec.inputs or {}
    ctx = {
        "sku": inp.get("sku"),
        "product_name": inp.get("product_name"),
        "rec_type": rec.rec_type,
        "order_quantity": _num(rec.rounded_qty),
        "currency": rec.currency,
        "signal_summary": signal.summary,
        "signal_value": _num(signal.value),
        "signal_trend": signal.trend,
        "signal_currency": signal.currency,
        "signal_category": signal.category_ref,
        "signal_source": signal.source_url,
    }
    ctx = {k: v for k, v in ctx.items() if v is not None and v != ""}
    user_block = (
        "ADVISORY mode. Recommendation context + the cached market signal (JSON — the "
        "signal is the ONLY market data you may reference):\n"
        f"{json.dumps(ctx, ensure_ascii=False)}\n\n"
        "Write one advisory sentence on what this market signal means for this buy."
    )
    result = provider.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_block},
        ],
        temperature=0.0,
        model=model,
        max_tokens=_MAX_TOKENS,
    )
    return (result.content or "").strip()


# ---------------------------------------------------------------------------
# deterministic fallback (no LLM) — restates frozen facts, invents nothing
# ---------------------------------------------------------------------------

def _fmt(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def _deterministic_explanation(rec: ReorderRecommendation) -> str:
    f = _rec_facts(rec)
    sku = f.get("sku") or "this SKU"
    if rec.rec_type == "buy":
        return (
            f"Order {_fmt(f.get('order_quantity'))} units of {sku} — net position "
            f"({_fmt(f.get('net_position'))}) has reached the reorder point "
            f"({_fmt(f.get('reorder_point'))}), so it is time to replenish."
        )
    if rec.rec_type == "exception":
        return f"{sku} would reorder, but no supplier is linked to source it — link one to proceed."
    return f"{sku} is flagged for review based on its current cover."
