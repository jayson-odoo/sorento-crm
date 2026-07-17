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
import re
from typing import Any, Optional

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.models.ai_assistant import AIAssistantConfig
from app.models.scm import MarketSignal, ReorderRecommendation, ReorderRun
from app.config import settings
from app.services.ai_prompt_registry import render
from app.services.error_handler import AppException
from app.services.llm_provider import get_provider
from app.services.scm import cash_ranking, reorder_engine

# The exact refusal contract — mirrored by the FE (`explainerMockStore.REFUSAL`)
# and asserted byte-for-byte in tests. The prompt instructs the model to emit this
# verbatim when a question can't be answered from the frozen facts.
REFUSAL = "I can't compute that from this recommendation's data."

_PROMPT_KEY = "scm_recommendation_explainer"
_ADVISORY_PROMPT_KEY = "scm_market_advisory"
_MAX_TOKENS = 220
# Plan-chat answers are longer than a one-liner (a manager asks for a short list /
# comparison) but still bounded. The context can hold a few hundred compact recs.
_RUN_CHAT_MAX_TOKENS = 700
_RUN_CHAT_MAX_RECS = 250


# ---------------------------------------------------------------------------
# facts (frozen numbers only — this is the LLM's entire world)
# ---------------------------------------------------------------------------

def _num(v: Any) -> Optional[float]:
    return float(v) if v is not None else None


_SELECTION_WHY = {
    "primary": "it is the primary supplier",
    "best_score": "it has the best supplier performance score",
    "lowest_cost": "it is the lowest cost",
}


def _rec_facts(rec: ReorderRecommendation) -> dict:
    """The frozen, already-computed numbers the model is allowed to speak. Pulled
    from the recommendation columns + its frozen ``inputs`` snapshot — never
    recomputed here."""
    inp = rec.inputs or {}
    supplier = inp.get("supplier") or {}
    selection = inp.get("selection")  # frozen key is "selection" (primary|best_score|lowest_cost)
    # Ranked alternatives the engine considered (so "why THIS supplier" / "why not
    # another" is answerable from the frozen set, not refused).
    alternatives = [
        {
            "supplier_name": a.get("supplier_name"),
            "unit_cost": _num(a.get("unit_cost")),
            "lead_time_days": _num(a.get("lead_time_days")),
            "performance_score": _num(a.get("composite_score")),
        }
        for a in (inp.get("alternatives") or [])
        if a and a.get("supplier_name")
    ]
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
        "reason": inp.get("reason"),  # dead | overstock | reorder_point | ... (disposition rows)
        "disposition_action": inp.get("disposition_action"),  # discontinue | promo | hold
        # --- chosen supplier + WHY it was chosen + the alternatives ---
        "chosen_supplier": supplier.get("supplier_name"),
        "chosen_supplier_cost": _num(supplier.get("unit_cost")),
        "chosen_supplier_lead_time_days": _num(supplier.get("lead_time_days")),
        "chosen_supplier_performance_score": _num(supplier.get("composite_score")),
        "supplier_chosen_because": _SELECTION_WHY.get(selection) if selection else None,
        "alternative_suppliers": alternatives or None,
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
        "Write one plain sentence telling the planner what to do and why. "
        "Money is Malaysian Ringgit — write it as 'RM'."
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
        "Money is Malaysian Ringgit — write it as 'RM'. "
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


# ---------------------------------------------------------------------------
# run-level overview (M5) — aggregate the run's frozen numbers → one short brief
# ---------------------------------------------------------------------------

def _run_facts(db: Session, run_id: str) -> dict:
    """Aggregate a run's FROZEN recommendation numbers for the overview — counts,
    cash, the biggest buys and the most urgent SKUs. All read straight from the
    stored recs; nothing recomputed."""
    counts = dict(
        db.execute(
            text(
                "SELECT rec_type, count(*) FROM scm.reorder_recommendation "
                "WHERE run_id = :r GROUP BY rec_type"
            ),
            {"r": run_id},
        ).all()
    )
    total_cash = db.execute(
        text(
            "SELECT COALESCE(SUM(cash_impact),0) FROM scm.reorder_recommendation "
            "WHERE run_id = :r AND rec_type='buy' AND cash_impact IS NOT NULL"
        ),
        {"r": run_id},
    ).scalar()
    needs_cost = db.execute(
        text(
            "SELECT count(*) FROM scm.reorder_recommendation "
            "WHERE run_id = :r AND rec_type='buy' AND cash_impact IS NULL"
        ),
        {"r": run_id},
    ).scalar()
    top_buys = [
        {
            "sku": r["sku"],
            "order_quantity": _num(r["rounded_qty"]),
            "cash_impact": _num(r["cash_impact"]),
        }
        for r in db.execute(
            text(
                "SELECT inputs->>'sku' AS sku, rounded_qty, cash_impact "
                "FROM scm.reorder_recommendation "
                "WHERE run_id = :r AND rec_type='buy' AND cash_impact IS NOT NULL "
                "ORDER BY cash_impact DESC LIMIT 5"
            ),
            {"r": run_id},
        ).mappings().all()
    ]
    urgent = [
        {"sku": r["sku"], "days_of_cover": _num(r["days_of_cover"])}
        for r in db.execute(
            text(
                "SELECT inputs->>'sku' AS sku, days_of_cover "
                "FROM scm.reorder_recommendation "
                "WHERE run_id = :r AND rec_type='buy' AND days_of_cover IS NOT NULL "
                "ORDER BY days_of_cover ASC LIMIT 5"
            ),
            {"r": run_id},
        ).mappings().all()
    ]
    facts = {
        "buy_count": int(counts.get("buy", 0)),
        "disposition_count": int(counts.get("disposition", 0)),
        "exception_count": int(counts.get("exception", 0)),
        "total_cash_impact": _num(total_cash),
        "buys_missing_supplier_cost": int(needs_cost or 0),
        "biggest_buys": top_buys or None,
        "most_urgent_skus": urgent or None,
    }
    return {k: v for k, v in facts.items() if v is not None and v != ""}


def explain_run(db: Session, run_id: str) -> str:
    """Lazy, cached run-level AI overview — a short brief over the run's frozen
    aggregates (LLM speaks only the given numbers; no numeric write except the
    cached ``reorder_run.overview`` prose)."""
    run = db.query(ReorderRun).filter(ReorderRun.id == run_id).first()
    if not run:
        raise AppException(status_code=404, message="Run not found.")
    if run.overview:
        return run.overview

    facts = _run_facts(db, run_id)
    provider, model = _provider_and_model(db)
    if provider is None:
        return _deterministic_run_overview(facts)

    user_block = (
        "RUN OVERVIEW mode. Reorder-run aggregates (JSON — the ONLY numbers you may "
        "use):\n"
        f"{json.dumps(facts, ensure_ascii=False)}\n\n"
        "Write a short brief (2-3 sentences) for a planner: the scale of what this run "
        "recommends (buys, dispositions, total cash), then the few SKUs that most need "
        "attention (biggest cash and/or soonest to stock out), naming them. Plain prose, "
        "no lists, only the given numbers. Money is Malaysian Ringgit — write it as 'RM'."
    )
    text_out = _chat(db, provider, model, user_block)
    if text_out:
        run.overview = text_out  # the ONLY write — prose, never a numeric field
        db.flush()
    return text_out or _deterministic_run_overview(facts)


def _deterministic_run_overview(facts: dict) -> str:
    buys = facts.get("buy_count", 0)
    disp = facts.get("disposition_count", 0)
    cash = facts.get("total_cash_impact")
    parts = [
        f"This run recommends {buys} buy{'s' if buys != 1 else ''} "
        f"and {disp} disposition{'s' if disp != 1 else ''}"
        + (f", about {_fmt(cash)} in cash." if cash is not None else ".")
    ]
    missing = facts.get("buys_missing_supplier_cost")
    if missing:
        parts.append(f"{_fmt(missing)} buys still need a supplier cost to be cash-ranked.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# plan-chat — a grounded, multi-turn conversation over the WHOLE run (M6-A)
# ---------------------------------------------------------------------------

def _run_market_signals(db: Session, run_id: str, limit: int = 15) -> list[dict]:
    """Latest cached market signals whose category matches any product in the run —
    so a plan-chat question like 'given the colour trend, what should I stock?' has
    the signal text to reason over. Matched on the product's category **id** (what
    the topic picker + ad-hoc search store as ``category_ref``)."""
    refs = [
        r[0]
        for r in db.execute(
            text(
                "SELECT DISTINCT p.category_id::text FROM scm.reorder_recommendation r "
                "JOIN products p ON p.id = r.product_id "
                "WHERE r.run_id = :r AND p.category_id IS NOT NULL"
            ),
            {"r": run_id},
        ).all()
    ]
    if not refs:
        return []
    rows = (
        db.query(MarketSignal)
        .filter(MarketSignal.category_ref.in_(refs))
        .order_by(
            MarketSignal.captured_at.desc().nullslast(),
            MarketSignal.created_at.desc(),
        )
        .limit(limit)
        .all()
    )
    return [
        {
            "category_ref": s.category_ref,
            "summary": s.summary,
            "trend": s.trend,
            "value": _num(s.value),
            "currency": s.currency,
            "source_url": s.source_url,
        }
        for s in rows
    ]


def _run_chat_context(db: Session, run_id: str) -> dict:
    """The whole run, compact, as the plan-chat's entire world (AC-M6.2): run
    aggregates + a per-rec snapshot of EVERY rec (capped, urgent + biggest-cash
    first) + matched market signals. Frozen numbers only — nothing recomputed."""
    run = db.query(ReorderRun).filter(ReorderRun.id == run_id).first()
    if not run:
        raise AppException(status_code=404, message="Run not found.")
    total = (
        db.execute(
            text("SELECT count(*) FROM scm.reorder_recommendation WHERE run_id = :r"),
            {"r": run_id},
        ).scalar()
        or 0
    )
    rows = db.execute(
        text(
            "SELECT inputs->>'sku' AS sku, inputs->>'product_name' AS product_name, "
            "rec_type, rounded_qty, cash_impact, net_position, days_of_cover, "
            "reorder_point, rank, funding_status, "
            "inputs->>'disposition_action' AS disposition_action, "
            "inputs->>'reason' AS reason, "
            "inputs->'supplier'->>'supplier_name' AS supplier "
            "FROM scm.reorder_recommendation WHERE run_id = :r "
            # urgent (soonest to run dry) first, then biggest cash — the order a
            # manager cares about, and the right rows to keep if we must truncate.
            "ORDER BY (days_of_cover IS NULL), days_of_cover ASC, "
            "cash_impact DESC NULLS LAST LIMIT :lim"
        ),
        {"r": run_id, "lim": _RUN_CHAT_MAX_RECS},
    ).mappings().all()
    recs = [
        {
            k: v
            for k, v in {
                "sku": r["sku"],
                "product_name": r["product_name"],
                "type": r["rec_type"],
                "order_quantity": _num(r["rounded_qty"]),
                "cash_impact": _num(r["cash_impact"]),
                "net_position": _num(r["net_position"]),
                "days_of_cover": _num(r["days_of_cover"]),
                "reorder_point": _num(r["reorder_point"]),
                "rank": r["rank"],
                "funding_status": r["funding_status"],
                "disposition_action": r["disposition_action"],
                "reason": r["reason"],
                "supplier": r["supplier"],
            }.items()
            if v is not None and v != ""
        }
        for r in rows
    ]
    ctx: dict = {
        "aggregates": _run_facts(db, run_id),
        "recommendations_total": int(total),
        "recommendations_shown": len(recs),
        "recommendations": recs,
    }
    if len(recs) < int(total):
        ctx["truncation_note"] = (
            f"Showing the {len(recs)} most urgent / highest-cash of {total} "
            "recommendations; totals in 'aggregates' cover all of them."
        )
    signals = _run_market_signals(db, run_id)
    if signals:
        ctx["market_signals"] = signals
    return ctx


def _deterministic_run_chat_fallback(ctx: dict) -> str:
    """No LLM configured — restate the aggregates (never fabricate an answer)."""
    return _deterministic_run_overview(ctx.get("aggregates") or {}) + (
        " (AI chat is unavailable — configure a provider to ask follow-up questions.)"
    )


# A budget what-if ("what defers at RM 200k?") is a DECISION-CRITICAL number: the
# funding split must come from the deterministic greedy-by-rank allocator, NOT from
# the LLM doing arithmetic in prose. We parse the amount, run the real allocator, and
# hand the LLM the computed result to narrate (LLM-boundary preserved).
_BUDGET_INTENT_RE = re.compile(r"budget|fund|afford|defer|spend|\bcash\b|\brm\b|\bmyr\b", re.I)
_AMOUNT_RE = re.compile(r"(?:rm|myr|\$)?\s*(\d[\d,]*(?:\.\d+)?)\s*([km])?\b", re.I)
_BUDGET_SCENARIO_CAP = 50  # cap the funded/deferred lists so context stays bounded


def _parse_budget(question: str) -> Optional[float]:
    """Pull a budget figure out of a question when it's clearly a funding what-if.
    Requires a funding-intent word AND a plausible amount (has a k/m unit, an RM/$
    prefix, or is ≥ 1000) so counts like 'top 5 buys' are ignored. Returns the last
    plausible amount (the budget usually comes last: 'cut the budget to RM 200k')."""
    if not _BUDGET_INTENT_RE.search(question or ""):
        return None
    best: Optional[float] = None
    for m in _AMOUNT_RE.finditer(question):
        num = float(m.group(1).replace(",", ""))
        unit = (m.group(2) or "").lower()
        prefixed = question[max(0, m.start() - 4): m.start()].lower()
        has_currency = "rm" in prefixed or "myr" in prefixed or "$" in prefixed
        if unit == "k":
            num *= 1_000
        elif unit == "m":
            num *= 1_000_000
        if unit or has_currency or num >= 1000:
            best = num
    return best


def _budget_scenario(db: Session, run_id: str, budget: float) -> dict:
    """The ENGINE's funding split for ``budget`` — the same greedy-by-rank allocator
    the Cash-budget slider uses (view-time, no persistence). This is authoritative;
    the LLM only narrates it."""
    rows = db.execute(
        text(
            "SELECT id, inputs->>'sku' AS sku, rank, cash_impact "
            "FROM scm.reorder_recommendation WHERE run_id = :r AND rec_type = 'buy'"
        ),
        {"r": run_id},
    ).mappings().all()
    buys = [
        cash_ranking.Buy(
            id=str(x["id"]),
            rank=int(x["rank"]) if x["rank"] is not None else None,
            cash_impact=float(x["cash_impact"]) if x["cash_impact"] is not None else None,
        )
        for x in rows
    ]
    res = cash_ranking.allocate_funding(buys, budget)
    meta = {
        str(x["id"]): (x["sku"], x["rank"], _num(x["cash_impact"]))
        for x in rows
    }
    funded = sorted(
        (meta[i] for i, s in res.status_by_id.items() if s == "funded"),
        key=lambda t: (t[1] if t[1] is not None else 1 << 30),
    )
    deferred = sorted(
        (meta[i] for i, s in res.status_by_id.items() if s == "deferred"),
        key=lambda t: (t[1] if t[1] is not None else 1 << 30),
    )
    return {
        "budget": float(budget),
        "rule": (
            "greedy by rank: fund each COSTED buy (in rank order) whose full cash "
            "impact fits the remaining budget, else defer it and continue to the next "
            "that fits; uncosted buys can't be funded until a supplier cost is added"
        ),
        "funded_count": res.funded_count,
        "deferred_count": res.deferred_count,
        "needs_cost_count": res.needs_cost_count,
        "funded_cash": res.funded_cash,
        "deferred_cash": res.deferred_cash,
        "funded": [{"sku": s, "cash_impact": c} for s, _, c in funded[:_BUDGET_SCENARIO_CAP]],
        "deferred": [{"sku": s, "cash_impact": c} for s, _, c in deferred[:_BUDGET_SCENARIO_CAP]],
    }


# Plan-chat gets its OWN system prompt. It must NOT inherit the single-recommendation
# explainer's refusal contract (which tells the model to reply with the exact REFUSAL
# string whenever the answer isn't in "this recommendation's data") — a run-level
# question like "what defers under budget X" IS answerable by reasoning over all the
# recs in the context, and the explainer prompt would wrongly force a refusal.
_RUN_CHAT_SYSTEM = (
    "You are a supply-chain planning assistant helping a manager interrogate ONE "
    "reorder run. You are given the run as JSON: aggregate totals plus a list of "
    "recommendations, each with its SKU, type (buy/disposition/exception), order "
    "quantity, cash impact, net position, days of cover, reorder point, rank, funding "
    "status, and supplier — plus any matched market signals.\n\n"
    "You may freely COUNT, SUM, RANK, FILTER, GROUP and COMPARE the numbers you are "
    "given to answer questions — e.g. 'which buys are most urgent' (lowest days of "
    "cover), 'what would defer if the budget were RM 200k' (walk the buys by rank, add "
    "up cash impact until the budget is spent; the rest defer), 'which supplier costs "
    "the most in total'. This is reasoning over provided data, and it is exactly your "
    "job — do it, don't refuse.\n\n"
    "When the JSON includes a 'budget_scenario' object, it is the AUTHORITATIVE "
    "funding split for that budget, already computed by the deterministic engine "
    "(greedy by rank) — report its 'funded' / 'deferred' lists, counts and cash "
    "verbatim; do NOT re-derive or second-guess which buys are funded. Buys under "
    "'needs_cost_count' cannot be funded at any budget until a supplier cost is added; "
    "mention them so the number reconciles.\n\n"
    "Hard rule: use ONLY the figures present in the given JSON. Never invent, estimate, "
    "or pull in a number that isn't there. If a question genuinely needs data the run "
    "does not contain (e.g. a supplier's phone number, next month's forecast), say so "
    "plainly in your own words — do NOT fabricate. Answer concisely, name specific SKUs "
    "and figures, and write money in Malaysian Ringgit as 'RM'."
)


def answer_run_question(
    db: Session,
    run_id: str,
    question: str,
    history: Optional[list[dict]] = None,
) -> str:
    """Grounded, multi-turn plan-chat (AC-M6.1-6.6). The model may REASON over the
    run's frozen numbers (count, sum, rank, compare, "what defers under budget X")
    but must not invent a figure the context doesn't contain. Prose only, no tools,
    no numeric write."""
    if not (question or "").strip():
        raise AppException(status_code=422, message="A question is required.")
    ctx = _run_chat_context(db, run_id)

    # Budget what-if → compute the funding split deterministically (the LLM must not
    # do this arithmetic itself) and hand it over as the authoritative answer.
    budget = _parse_budget(question)
    if budget is not None:
        ctx["budget_scenario"] = _budget_scenario(db, run_id, budget)

    provider, model = _provider_and_model(db)
    if provider is None:
        return _deterministic_run_chat_fallback(ctx)

    messages: list[dict] = [
        {"role": "system", "content": _RUN_CHAT_SYSTEM},
        {
            "role": "user",
            "content": (
                "Here is the reorder run to answer questions about (JSON):\n"
                f"{json.dumps(ctx, ensure_ascii=False)}"
            ),
        },
        {"role": "assistant", "content": "Understood — ask me anything about this plan."},
    ]
    for turn in history or []:
        q = (turn.get("question") or "").strip()
        a = (turn.get("answer") or "").strip()
        if q:
            messages.append({"role": "user", "content": q})
        if a:
            messages.append({"role": "assistant", "content": a})
    messages.append({"role": "user", "content": question.strip()})

    result = provider.chat(
        messages,
        temperature=0.0,
        model=model,
        max_tokens=_RUN_CHAT_MAX_TOKENS,
    )
    return (result.content or "").strip() or _deterministic_run_chat_fallback(ctx)


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
