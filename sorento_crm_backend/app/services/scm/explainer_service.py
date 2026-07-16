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

from sqlalchemy.orm import Session

from app.models.ai_assistant import AIAssistantConfig
from app.models.scm import ReorderRecommendation
from app.config import settings
from app.services.ai_prompt_registry import render
from app.services.error_handler import AppException
from app.services.llm_provider import get_provider

# The exact refusal contract — mirrored by the FE (`explainerMockStore.REFUSAL`)
# and asserted byte-for-byte in tests. The prompt instructs the model to emit this
# verbatim when a question can't be answered from the frozen facts.
REFUSAL = "I can't compute that from this recommendation's data."

_PROMPT_KEY = "scm_recommendation_explainer"
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
    """Market advisory for a recommendation — filled by M5 Part B (market signals).
    Until signals exist this returns the cached advisory or None (no matching signal)."""
    rec = _get_rec(db, rec_id)
    return rec.market_advisory or None


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
