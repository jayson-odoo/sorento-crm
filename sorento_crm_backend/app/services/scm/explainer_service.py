"""SCM M5 - bounded semantic explainer (NOT the agent/MCP flow).

Turns a reorder recommendation's FROZEN numbers into plain-language prose and
answers scoped follow-up questions. Hard boundary (AC-M5.3 / AC-M5.8): the LLM
receives already-computed numbers as input and emits prose only - there is NO
tool/agent loop and NO path from LLM output to a numeric field. The only column
this service ever writes is ``recommendation.explanation`` (Text, cached prose).

- ``explain_recommendation`` - lazy: return the cached sentence, else generate
  one from the frozen facts, cache it, return.
- ``answer_question`` - bounded Q&A over the same frozen facts; if a question
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
from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.llm_provider import get_provider
from app.services.scm import cash_ranking, reorder_engine

# The exact refusal contract - mirrored by the FE (`explainerMockStore.REFUSAL`)
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
# Cross-run history (M8-E3) is prefetched into the chat context; bounded so a
# category with a long tail of past runs can't blow the token budget.
_PAST_PLANS_LIMIT = 40
_PAST_PLANS_CHAT_SKUS = 3  # at most N mentioned SKUs expanded per turn

# M8-F6: the chat auto-decides whether a question needs a LIVE market web search.
# Trend/market language (not a plan-internal number question) routes to a live
# ad-hoc scan whose signal is folded into the answer + mapped to a confirm-gated
# proposal. Kept narrow so a plain "which buy eats the most cash" never fires it.
_MARKET_INTENT_RE = re.compile(
    r"(market|trend|trending|seasonal|popular|competitor|industry\s+news|"
    r"in\s+vogue|fashion|colou?r\s+trend|demand\s+surge|surge\s+in\s+demand|"
    r"outlook|forecast|price\s+trend|prices?\s+(?:are\s+)?(?:rising|climbing|"
    r"going\s+up|surging|falling|dropping)|latest\s+news|what'?s\s+hot|"
    r"selling\s+well|going\s+viral)",
    re.I,
)

# M8-F7: "previous / similar plan(s)" language triggers past-plans injection EVEN
# when the user names no SKU (we fall back to this plan's own top cash-impact buys).
_PAST_PLANS_INTENT_RE = re.compile(
    r"(previous|prior|\bpast\b|earlier|before|history|historical|"
    r"last\s+(?:time|run|plan|week|month)|similar\s+plans?|recurring|"
    r"how\s+did\s+we|used\s+to)",
    re.I,
)

# M8-F16: a natural-language INSTRUCTION to change plan decisions (accept / reject /
# defer / keep-only / adjust of specific lines) routes to a schema-forced structured
# action-parse whose per-line refs are resolved to REAL rec ids. There is deliberately
# NO keyword gate here: a verb allowlist silently dropped natural instructions ("mr loo
# just wants to buy C-FH24"). The structured parser is the sole, semantic gate - it
# returns empty lines for a plain question, which resolves to NO action_proposal.


# ---------------------------------------------------------------------------
# facts (frozen numbers only - this is the LLM's entire world)
# ---------------------------------------------------------------------------

def _num(v: Any) -> Optional[float]:
    return float(v) if v is not None else None


def _iso(dt: Any) -> Optional[str]:
    """Naive-UTC ISO string (or None) - matches the market service's date serializer."""
    return dt.isoformat() if dt else None


_SELECTION_WHY = {
    "primary": "it is the primary supplier",
    "best_score": "it has the best supplier performance score",
    "lowest_cost": "it is the lowest cost",
}


def _rec_facts(rec: ReorderRecommendation) -> dict:
    """The frozen, already-computed numbers the model is allowed to speak. Pulled
    from the recommendation columns + its frozen ``inputs`` snapshot - never
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
    no API key is configured - callers degrade gracefully, never raise."""
    config = (
        db.query(AIAssistantConfig)
        .order_by(AIAssistantConfig.created_at.asc())
        .first()
    )
    api_key = (config.api_key_ciphertext if config else None) or getattr(
        settings, "openai_api_key", None
    )
    # config is None (empty config table) still degrades gracefully even when a
    # global env key is set - never raise (the docstring contract).
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
        # No LLM configured - degrade to a deterministic sentence (never blocks the
        # UI, never fabricates: it only restates frozen facts). Not cached.
        return _deterministic_explanation(rec)

    facts = _rec_facts(rec)
    user_block = (
        "EXPLAIN mode. Recommendation facts (JSON - the ONLY numbers you may use):\n"
        f"{json.dumps(facts, ensure_ascii=False)}\n\n"
        "Write one plain sentence telling the planner what to do and why. "
        "Money is Malaysian Ringgit - write it as 'RM'."
    )
    text = _chat(db, provider, model, user_block)
    if text:
        rec.explanation = text  # the ONLY write - prose, never a numeric field
        db.flush()
    return text or _deterministic_explanation(rec)


def answer_question(db: Session, rec_id: str, question: str) -> str:
    """Bounded Q&A over a recommendation's frozen facts (AC-M5.2). A question that
    needs a number not in the facts returns ``REFUSAL`` verbatim - never a figure."""
    if not (question or "").strip():
        raise AppException(status_code=422, message="A question is required.")
    rec = _get_rec(db, rec_id)

    provider, model = _provider_and_model(db)
    if provider is None:
        return REFUSAL

    facts = _rec_facts(rec)
    user_block = (
        "ASK mode. Recommendation facts (JSON - the ONLY numbers you may use):\n"
        f"{json.dumps(facts, ensure_ascii=False)}\n\n"
        f"Planner's question: {question.strip()}\n\n"
        "Money is Malaysian Ringgit - write it as 'RM'. "
        f'If the answer needs anything not in the facts, reply EXACTLY: "{REFUSAL}"'
    )
    text = _chat(db, provider, model, user_block)
    return text or REFUSAL


def market_advisory(db: Session, rec_id: str) -> Optional[str]:
    """Market advisory for a recommendation (M5 Part B).

    Lazy + cached: return the cached advisory if present. Else find the most recent
    ``market_signal`` matching this rec by **product category + currency**; if one
    exists, condense it into ONE advisory sentence (LLM ADVISORY mode - never a new
    number), cache it to ``rec.market_advisory`` (the ONLY write), and return it. No
    matching signal → ``None``. Advisory is decision-support prose from a STORED
    signal - the LLM never searches and never touches a numeric column."""
    rec = _get_rec(db, rec_id)
    if rec.market_advisory:
        return rec.market_advisory

    signal = _match_market_signal(db, rec)
    if signal is None:
        return None

    provider, model = _provider_and_model(db)
    if provider is None:
        # No LLM configured - the stored signal's own summary IS advisory prose
        # (restates the captured signal, invents nothing). Not cached, so a later
        # LLM-enabled view can still generate the condensed sentence.
        return (signal.summary or None)

    text = _advisory_chat(db, provider, model, rec, signal)
    if text:
        rec.market_advisory = text  # the ONLY write - prose, never a numeric field
        db.flush()
    return text or (signal.summary or None)


# ---------------------------------------------------------------------------
# run-level overview (M5) - aggregate the run's frozen numbers → one short brief
# ---------------------------------------------------------------------------

def _run_facts(db: Session, run_id: str) -> dict:
    """Aggregate a run's FROZEN recommendation numbers for the overview - counts,
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
    """Lazy, cached run-level AI overview - a short brief over the run's frozen
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
        "RUN OVERVIEW mode. Reorder-run aggregates (JSON - the ONLY numbers you may "
        "use):\n"
        f"{json.dumps(facts, ensure_ascii=False)}\n\n"
        "Write a short brief (2-3 sentences) for a planner: the scale of what this run "
        "recommends (buys, dispositions, total cash), then the few SKUs that most need "
        "attention (biggest cash and/or soonest to stock out), naming them. Plain prose, "
        "no lists, only the given numbers. Money is Malaysian Ringgit - write it as 'RM'."
    )
    text_out = _chat(db, provider, model, user_block)
    if text_out:
        run.overview = text_out  # the ONLY write - prose, never a numeric field
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
# plan-chat - a grounded, multi-turn conversation over the WHOLE run (M6-A)
# ---------------------------------------------------------------------------

def _run_market_signals(db: Session, run_id: str, limit: int = 15) -> list[dict]:
    """Latest cached market signals whose category matches any product in the run  - 
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
    first) + matched market signals. Frozen numbers only - nothing recomputed."""
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
            # urgent (soonest to run dry) first, then biggest cash - the order a
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
    """No LLM configured - restate the aggregates (never fabricate an answer)."""
    return _deterministic_run_overview(ctx.get("aggregates") or {}) + (
        " (AI chat is unavailable - configure a provider to ask follow-up questions.)"
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
    """The ENGINE's funding split for ``budget`` - the same greedy-by-rank allocator
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


# ---------------------------------------------------------------------------
# cross-run history (M8-E3) - prior COMPLETED-run lines for the same SKU, its
# category siblings, and its variant_of_id neighbours. Read-only; writes nothing.
# ---------------------------------------------------------------------------

def _similar_product_ids(
    db: Session,
    *,
    product_code: Optional[str] = None,
    category_ref: Optional[str] = None,
) -> list[str]:
    """The product ids that count as 'the same or similar' for cross-run history:
    the exact SKU, its category siblings (matched on the category **id OR code**),
    and its ``variant_of_id`` neighbours (parent, children, same-parent siblings).

    Value-space-agnostic on the category token (id or code) - the same both-ways
    match the advisory + market factor use, so a caller can pass either."""
    ids: set[str] = set()

    if category_ref:
        rows = db.execute(
            text(
                "SELECT p.id::text FROM products p "
                "LEFT JOIN product_categories pc ON pc.id = p.category_id "
                "WHERE p.category_id::text = :ref OR pc.category_code = :ref"
            ),
            {"ref": category_ref},
        ).all()
        ids.update(r[0] for r in rows)

    if product_code:
        target = db.execute(
            text(
                "SELECT id::text AS id, category_id::text AS category_id, "
                "variant_of_id::text AS variant_of_id "
                "FROM products WHERE product_code = :c"
            ),
            {"c": product_code},
        ).mappings().first()
        if target:
            ids.add(target["id"])
            # category siblings (same category as the mentioned SKU)
            if target["category_id"]:
                rows = db.execute(
                    text("SELECT id::text FROM products WHERE category_id::text = :cat"),
                    {"cat": target["category_id"]},
                ).all()
                ids.update(r[0] for r in rows)
            # variant neighbours: children, the parent, and same-parent siblings
            rows = db.execute(
                text(
                    "SELECT id::text FROM products WHERE "
                    "variant_of_id::text = :pid "                                  # children
                    "OR id::text = :parent "                                       # parent
                    "OR (:sibof IS NOT NULL AND variant_of_id::text = :sibof)"     # siblings
                ),
                {"pid": target["id"], "parent": target["variant_of_id"],
                 "sibof": target["variant_of_id"]},
            ).all()
            ids.update(r[0] for r in rows)

    return list(ids)


def query_past_plans(
    db: Session,
    *,
    product_code: Optional[str] = None,
    category_ref: Optional[str] = None,
    exclude_run_id: Optional[str] = None,
    limit: int = _PAST_PLANS_LIMIT,
) -> list[dict]:
    """Prior COMPLETED-run recommendation lines for the same SKU + its category
    siblings + variant neighbours (M8-E3). Newest run first, bounded. Each line is a
    read-only snapshot: run_date, product_code, order qty, funding, decision status,
    override reason, days-of-cover. Writes nothing (guardrail: history is a read)."""
    product_ids = _similar_product_ids(
        db, product_code=product_code, category_ref=category_ref
    )
    if not product_ids:
        return []
    # Cross-run by design, so the entry gate on the CURRENT run does not cover it: this
    # scans every completed run and would otherwise surface another company's past plans.
    co, co_params = company_sql_predicate(db, "run.company_id", param_prefix="cpp")
    rows = db.execute(
        text(
            "SELECT run.created_at AS run_date, p.product_code AS product_code, "
            "r.rounded_qty AS rounded_qty, r.funding_status AS funding_status, "
            "r.status AS decision_status, r.days_of_cover AS days_of_cover, "
            "ov.reason_text AS override_reason "
            "FROM scm.reorder_recommendation r "
            "JOIN scm.reorder_run run ON run.id = r.run_id "
            "JOIN products p ON p.id = r.product_id "
            "LEFT JOIN LATERAL ("
            "  SELECT reason_text FROM scm.recommendation_override o "
            "  WHERE o.recommendation_id = r.id "
            "  ORDER BY o.created_at DESC LIMIT 1"
            ") ov ON true "
            "WHERE run.status = 'completed' "
            "AND r.product_id::text = ANY(:ids) "
            "AND (:exclude IS NULL OR run.id::text <> :exclude) "
            f"AND {co or 'true'} "
            "ORDER BY run.created_at DESC, p.product_code "
            "LIMIT :lim"
        ),
        {"ids": product_ids, "exclude": exclude_run_id, "lim": int(limit), **co_params},
    ).mappings().all()
    return [
        {
            "run_date": _iso(r["run_date"]),
            "product_code": r["product_code"],
            "rounded_qty": _num(r["rounded_qty"]),
            "funding_status": r["funding_status"],
            "decision_status": r["decision_status"],
            "override_reason": r["override_reason"],
            "days_of_cover": _num(r["days_of_cover"]),
        }
        for r in rows
    ]


# M8-F: "how does this plan compare to the previous plan(s)" routes to a DETERMINISTIC
# product-by-product diff. Routing only - the comparison maths is pure Python; the LLM
# never computes or compares a number (guardrail: LLMs are bad at arithmetic).
_COMPARE_INTENT_RE = re.compile(
    r"(compare|comparison|compared|versus|\bvs\.?\b|difference\s+(?:between|from|with)|"
    r"how\s+(?:does|do|is)\s+.*(?:compare|differ)|against\s+(?:the\s+)?(?:previous|prior|last)|"
    r"(?:previous|prior|last)\s+plan.*(?:vs|versus|compare))",
    re.I,
)

_COMPARE_MAX_ROWS = 8


def _compare_direction(cur_qty: Optional[float], prev_qty: Optional[float]) -> str:
    """new (no prior) | up | down | same - from the two frozen quantities only."""
    if prev_qty is None:
        return "new"
    if cur_qty is None:
        return "same"
    if cur_qty > prev_qty + 1e-9:
        return "up"
    if cur_qty < prev_qty - 1e-9:
        return "down"
    return "same"


def _compare_reason(cur: dict, prev: Optional[dict]) -> str:
    """A short QUALITATIVE why for a comparison row, assembled in Python from the frozen
    deltas (never the LLM). Speaks to what actually moved: demand, stock position, cover."""
    if prev is None:
        return "New in this plan; it was not planned in the most recent prior run."
    parts: list[str] = []
    dem_c, dem_p = cur.get("dem"), prev.get("dem")
    if dem_c is not None and dem_p is not None:
        if dem_c > dem_p * 1.05:
            parts.append("demand is running higher")
        elif dem_c < dem_p * 0.95:
            parts.append("demand is running lower")
    net_c, net_p = cur.get("net"), prev.get("net")
    if net_c is not None and net_p is not None:
        if net_c < net_p:
            parts.append("the stock position is tighter")
        elif net_c > net_p:
            parts.append("the stock position is healthier")
    doc_c, doc_p = cur.get("doc"), prev.get("doc")
    if doc_c is not None and doc_p is not None:
        if doc_c < doc_p:
            parts.append("runway has fallen")
        elif doc_c > doc_p:
            parts.append("runway has risen")
    if not parts:
        return "The inputs are broadly unchanged since the last plan."
    return "Because " + ", and ".join(parts) + "."


def build_plan_comparison(
    db: Session, run_id: str, limit: int = _COMPARE_MAX_ROWS
) -> Optional[dict]:
    """DETERMINISTIC product-by-product comparison of THIS run against each product's
    most recent PRIOR completed run (M8-F). For the run's top buys by priority, look up
    the same product's newest earlier buy rec and diff the FROZEN figures (qty, funding,
    net, days-of-cover) in Python. Returns ``{rows, compared_count}`` or ``None`` when the
    run has no buys. No LLM touches any number - the assistant only narrates around it."""
    cur_rows = db.execute(
        text(
            "SELECT r.product_id::text AS pid, p.product_code AS sku, p.product_name AS name, "
            "r.rounded_qty AS qty, r.funding_status AS fs, r.days_of_cover AS doc, "
            "r.net_position AS net, r.forecast_daily_demand AS dem "
            "FROM scm.reorder_recommendation r JOIN products p ON p.id = r.product_id "
            # Only the ORDERABLE plan (costed buys) - skipped needs-cost SKUs aren't part
            # of the plan, so they must not appear in a plan-vs-previous comparison.
            "WHERE r.run_id = :rid AND r.rec_type = 'buy' AND r.unit_cost IS NOT NULL "
            "ORDER BY r.rank NULLS LAST, p.product_code LIMIT :lim"
        ),
        {"rid": run_id, "lim": int(limit)},
    ).mappings().all()
    if not cur_rows:
        return None

    rows: list[dict] = []
    compared = 0
    # Reaches BACK past the gated run, so it carries its own predicate (see past-plans).
    prev_co, prev_co_params = company_sql_predicate(db, "run.company_id", param_prefix="cpv")
    for c in cur_rows:
        prev = db.execute(
            text(
                "SELECT run.created_at AS rd, pr.rounded_qty AS qty, pr.status AS st, "
                "pr.funding_status AS fs, pr.days_of_cover AS doc, pr.net_position AS net, "
                "pr.forecast_daily_demand AS dem "
                "FROM scm.reorder_recommendation pr "
                "JOIN scm.reorder_run run ON run.id = pr.run_id "
                "WHERE pr.product_id::text = :pid AND pr.rec_type = 'buy' "
                "AND run.status = 'completed' AND run.id::text <> :rid "
                f"AND {prev_co or 'true'} "
                "ORDER BY run.created_at DESC LIMIT 1"
            ),
            {"pid": c["pid"], "rid": run_id, **prev_co_params},
        ).mappings().first()
        c_dict = {"dem": _num(c["dem"]), "net": _num(c["net"]), "doc": _num(c["doc"])}
        p_dict = (
            {"dem": _num(prev["dem"]), "net": _num(prev["net"]), "doc": _num(prev["doc"])}
            if prev
            else None
        )
        # Quantities are whole units on the card (a fractional order qty is meaningless).
        cur_qty = round(_num(c["qty"])) if c["qty"] is not None else None
        prev_qty = round(_num(prev["qty"])) if (prev and prev["qty"] is not None) else None
        if prev:
            compared += 1
        rows.append(
            {
                "sku": c["sku"],
                "product_name": c["name"],
                "current_qty": cur_qty,
                "current_funding": c["fs"],
                "current_days_cover": _num(c["doc"]),
                "current_net": _num(c["net"]),
                "previous_run_date": _iso(prev["rd"]) if prev else None,
                "previous_qty": prev_qty,
                "previous_decision": prev["st"] if prev else None,
                "previous_days_cover": _num(prev["doc"]) if prev else None,
                "previous_net": _num(prev["net"]) if prev else None,
                "qty_delta": (cur_qty - prev_qty) if (cur_qty is not None and prev_qty is not None) else None,
                "direction": _compare_direction(cur_qty, prev_qty),
                "reason": _compare_reason(c_dict, p_dict),
            }
        )
    return {"rows": rows, "compared_count": compared}


def _skus_mentioned(question: str, ctx: dict) -> list[str]:
    """SKUs from THIS run's recommendations that the question names (case-insensitive
    substring) - the trigger for prefetching cross-run history into the chat context.
    Bounded to the run's own SKUs so the match set is small + deterministic."""
    q = (question or "").lower()
    seen: list[str] = []
    for rec in ctx.get("recommendations") or []:
        sku = rec.get("sku")
        if sku and sku.lower() in q and sku not in seen:
            seen.append(sku)
    return seen


def _top_cash_skus(ctx: dict, limit: int = _PAST_PLANS_CHAT_SKUS) -> list[str]:
    """This plan's own highest cash-impact buy SKUs - the fallback drivers for a
    'previous / similar plans' question that names no SKU (M8-F7). Ordered by cash
    impact desc so the history we surface is for the buys that matter most today."""
    buys = [
        r
        for r in (ctx.get("recommendations") or [])
        if r.get("type") == "buy" and r.get("sku")
    ]
    buys.sort(key=lambda r: (r.get("cash_impact") or 0.0), reverse=True)
    out: list[str] = []
    for r in buys:
        if r["sku"] not in out:
            out.append(r["sku"])
        if len(out) >= limit:
            break
    return out


def _inject_past_plans(db: Session, ctx: dict, question: str, run_id: str) -> None:
    """Prefetch prior-run history into the chat context so the LLM can answer 'how
    did we handle X before' (M8-E3). When the question names a SKU in this run, we
    expand that SKU (+ its category siblings / variant neighbours). When the question
    is about previous / similar plans but names NO SKU (M8-F7), we fall back to this
    plan's own top cash-impact buys so 'tell me about similar previous plans' still
    returns real history. Single-call design: a context prefetch, not an agent loop."""
    mentioned = _skus_mentioned(question, ctx)
    if not mentioned:
        if not _PAST_PLANS_INTENT_RE.search(question or ""):
            return
        mentioned = _top_cash_skus(ctx)
        if not mentioned:
            return
    past: list[dict] = []
    for code in mentioned[:_PAST_PLANS_CHAT_SKUS]:
        past.extend(
            query_past_plans(
                db,
                product_code=code,
                exclude_run_id=run_id,
                limit=_PAST_PLANS_LIMIT,
            )
        )
    if past:
        ctx["past_plans"] = past[:_PAST_PLANS_LIMIT]


# Plan-chat gets its OWN system prompt. It must NOT inherit the single-recommendation
# explainer's refusal contract (which tells the model to reply with the exact REFUSAL
# string whenever the answer isn't in "this recommendation's data") - a run-level
# question like "what defers under budget X" IS answerable by reasoning over all the
# recs in the context, and the explainer prompt would wrongly force a refusal.
_RUN_CHAT_SYSTEM = (
    "You are a supply-chain planning assistant helping a manager review ONE reorder "
    "plan. You are given this plan's figures: aggregate totals plus a list of "
    "recommendations, each with its SKU, type (buy / stock allocation / exception), "
    "order quantity, cash impact, net position, runway (days of cover), reorder point, rank, "
    "funding status and supplier - plus, when relevant, prior-plan history, a computed "
    "budget split, and a live market reading.\n\n"
    "You may freely COUNT, SUM, RANK, FILTER, GROUP and COMPARE the figures you are "
    "given - e.g. 'which buys are most urgent' (lowest runway), 'what would "
    "defer if the budget were RM 200k' (walk the buys by rank, adding cash impact until "
    "the budget is spent; the rest defer), 'which supplier costs the most in total'. "
    "This is exactly your job - do it, do not refuse.\n\n"
    "When a budget split is provided, it is the AUTHORITATIVE funding result already "
    "computed for that budget (greedy by rank) - report its funded / deferred lists, "
    "counts and cash as given; do not re-derive or second-guess them. Buys that still "
    "need a supplier cost cannot be funded at any budget until a cost is added; mention "
    "them so the numbers reconcile.\n\n"
    "When prior-plan history is provided, use it to answer 'how did we handle this "
    "before' - cite the past run dates and figures, and do not invent history. When the "
    "manager asks about previous or similar plans and NO prior history is available, "
    "reply in plain business language, for example: 'I don't have prior plans for "
    "similar products yet.'\n\n"
    "A live market reading, when one was pulled, is provided ONLY as ``live_market_scan``. "
    "If ``live_market_scan`` has a ``summary``, THAT is your live reading for THIS question: "
    "state its figures in plain language and, if it maps to plan lines, tell the manager a "
    "confirm-gated quantity proposal is shown below to review. In that case you MUST NOT say "
    "you could not get a reading. Use ONLY the figures in ``live_market_scan.summary`` for the "
    "market trend - never a number from an earlier turn, a cached advisory, or elsewhere; if "
    "they differ, the live scan wins. Only when ``live_market_scan.status`` is 'unavailable' "
    "(no summary) may you say plainly that you could not get a live market reading right now, "
    "then answer from the plan. Never invent a market figure.\n\n"
    "When a proposed plan-action set is provided, the manager has asked you to change the "
    "plan (buy only certain lines, reject the rest, adjust a quantity). Briefly restate "
    "what you are proposing - which lines to accept, reject or adjust and why - and tell "
    "the manager to review it and click Apply to update the plan. NEVER say the plan is "
    "already changed; nothing changes until they click Apply.\n\n"
    "If NO proposed plan-action set and NO live market signal mapped to plan lines is "
    "provided, you MUST NOT tell the manager to click Apply, and you MUST NOT claim any "
    "proposal, card or button exists - there is none. Just answer the question plainly.\n\n"
    "When the manager asks how this plan compares to a previous / prior plan, a "
    "DETERMINISTIC product-by-product comparison table is rendered below your answer with "
    "the exact quantities and figures. Do NOT restate, recompute or compare any numbers "
    "yourself - you are bad at arithmetic and the table already has them. Your ENTIRE reply "
    "must be a single short orientation sentence, for example exactly: 'Here is how each "
    "product compares to its last plan; the table below shows what changed and why.' Do NOT "
    "write a table, a markdown table, a bulleted or numbered list of products, or any per-"
    "product line - the card below is the table. One sentence only.\n\n"
    "Hard rules: use ONLY the figures you are given - never invent, estimate or pull in "
    "a number that is not there; if a question genuinely needs data the plan does not "
    "carry (a supplier's phone number, next month's forecast), say so plainly. NEVER "
    "mention how this data reaches you or your own internals - do NOT use words like "
    "'JSON', 'array', 'object', 'field', 'context', 'the provided data', or refer to any "
    "data structure. Speak only in business terms, the way a colleague would. Answer "
    "concisely, name specific SKUs and figures, and write money in Malaysian Ringgit as "
    "'RM'."
)


def _build_run_chat_context(db: Session, run_id: str, question: str) -> dict:
    """The plan-chat's grounded world: the run snapshot + (when the question asks
    for it) a deterministic budget split and prior-plan history. Frozen numbers only,
    nothing recomputed by the LLM."""
    ctx = _run_chat_context(db, run_id)

    # Budget what-if → compute the funding split deterministically (the LLM must not
    # do this arithmetic itself) and hand it over as the authoritative answer.
    budget = _parse_budget(question)
    if budget is not None:
        ctx["budget_scenario"] = _budget_scenario(db, run_id, budget)

    # Cross-run history (M8-E3 + M8-F7): prefetch prior-run lines for a named SKU, or
    # (for a no-SKU "previous / similar plans" question) this plan's top-cash buys.
    _inject_past_plans(db, ctx, question, run_id)
    return ctx


def _run_chat_answer(
    db: Session,
    ctx: dict,
    question: str,
    history: Optional[list[dict]] = None,
) -> str:
    """Run the grounded plan-chat LLM turn over ``ctx`` and return prose. Prose only,
    no tools, no numeric write. Degrades to a deterministic aggregate sentence when no
    provider is configured."""
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
        {"role": "assistant", "content": "Understood - ask me anything about this plan."},
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
    ctx = _build_run_chat_context(db, run_id, question)
    return _run_chat_answer(db, ctx, question, history)


def _dominant_category_ref(db: Session, run_id: str) -> Optional[str]:
    """The category (code) of the run's highest cash-impact buy - the category a live
    market scan is keyed to so its signal can map back onto plan lines (M8-F6)."""
    pid = db.execute(
        text(
            "SELECT product_id FROM scm.reorder_recommendation "
            "WHERE run_id = :r AND rec_type = 'buy' AND cash_impact IS NOT NULL "
            "ORDER BY cash_impact DESC NULLS LAST LIMIT 1"
        ),
        {"r": run_id},
    ).scalar()
    if not pid:
        return None
    return reorder_engine.load_category_code(db, str(pid))


def _market_augment(
    db: Session, ctx: dict, run_id: str, question: str, actor: Optional[str]
) -> Optional[dict]:
    """M8-F6: run a LIVE ad-hoc market scan for a trend question, fold the reading into
    the chat context (so the answer speaks the trend), and return a confirm-gated
    proposal when the signal maps to plan lines (else ``None`` - the answer just
    mentions the trend). Key-gated + graceful: no key / no signal → an 'unavailable'
    note in the context and no proposal, never a crash. Writes NOTHING to any
    recommendation column (M8-E7) - the proposal is confirmed per line via /adjust."""
    # local import: market_proposal_service → market_research_service → this module,
    # so keep the edge out of module import time.
    from app.services.scm import market_proposal_service

    category_ref = _dominant_category_ref(db, run_id)
    result = market_proposal_service.build_market_proposal(
        db, run_id, query=question, category_ref=category_ref, actor=actor
    )
    lines = result.get("lines") or []
    if result.get("signal_summary"):
        ctx["live_market_scan"] = {
            "summary": result["signal_summary"],
            "source_url": result.get("source_url"),
            "matched_line_count": len(lines),
        }
    else:
        # no reading (no key / nothing found) - let the LLM say so in business terms
        ctx["live_market_scan"] = {"status": "unavailable"}
    return result if lines else None


# ---------------------------------------------------------------------------
# plan-action proposal (M8-F16) - a natural-language instruction ("buy FT-B only,
# reject the rest", "bump FT-03 to 684") becomes a STRUCTURED per-line proposal the
# human Applies. The LLM proposes which lines + which decision (schema-forced, so it
# emits data not prose); we resolve its SKU/name refs to REAL rec ids. Writes NOTHING.
# ---------------------------------------------------------------------------

_ACTION_PARSE_MAX_TOKENS = 700
_ACTION_PARSE_SCHEMA_NAME = "scm_plan_action_proposal"

# Schema-forced structured output: the model returns per-line decisions keyed by the
# plan line's SKU (never a rec id - no UUIDs cross the LLM boundary). ``rest`` applies
# one action to every OTHER buy line, so "reject the rest" needs no enumeration.
_ACTION_PARSE_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {
            "type": "string",
            "description": "One plain sentence for the manager describing the proposed changes.",
        },
        "lines": {
            "type": "array",
            "description": "One entry per line the instruction explicitly names.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "The exact SKU of a plan line the instruction refers to.",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["accept", "reject", "adjust"],
                        "description": "accept=buy/keep it; reject=do not buy/skip/defer it; "
                        "adjust=change the order quantity (set new_qty).",
                    },
                    "new_qty": {
                        "type": ["number", "null"],
                        "description": "Target order quantity for an adjust; null otherwise.",
                    },
                    "reason": {"type": "string", "description": "Short business reason for the decision."},
                },
                "required": ["ref", "action", "new_qty", "reason"],
            },
        },
        "rest": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "description": "Set only when the instruction covers all OTHER lines "
            "('the rest', 'the others', 'nothing else'); applies one action to every buy "
            "line not named in 'lines'.",
            "properties": {
                "action": {"type": "string", "enum": ["accept", "reject"]},
                "reason": {"type": "string"},
            },
            "required": ["action", "reason"],
        },
        "unresolved": {
            "type": "array",
            "description": "Raw phrases the instruction referenced but you could not tie to a plan line.",
            "items": {"type": "string"},
        },
    },
    "required": ["summary", "lines", "rest", "unresolved"],
}

_ACTION_PARSE_SYSTEM = (
    "You convert a planner's natural-language instruction about a reorder plan into a "
    "STRUCTURED set of per-line decisions. You are given the plan's buy lines, each with "
    "its SKU, product name and order quantity. For each line the instruction refers to, "
    "choose ONE action: 'accept' (buy it / keep it in the plan), 'reject' (do not buy, "
    "skip or defer it), or 'adjust' (change the order quantity - then set new_qty to the "
    "requested number). Reference each line by its exact SKU in 'ref'. "
    "For a 'buy X only' or 'keep only X' instruction, accept the named lines and, when "
    "the planner says the rest / the others / nothing else should be dropped, set 'rest' "
    "to that action so it applies to every OTHER buy line. For 'the top N by urgency or "
    "cash', name the specific SKUs you select in 'lines'. Give each line a short business "
    "reason. "
    "If the message is a QUESTION and not an instruction to change decisions, return an "
    "empty 'lines' list and null 'rest'. NEVER invent a SKU that is not in the plan; if "
    "you cannot tie a reference to a plan line, add its raw phrase to 'unresolved' and do "
    "not guess. Do not compute budgets or funding; only propose the decisions."
)


def _buy_lines_for_actions(db: Session, run_id: str) -> list[dict]:
    """The run's BUY recs as {rec_id, sku, product_name, current_qty} - the resolution
    table that maps an LLM's SKU/name reference back to a real recommendation id. Read
    only; the rec id never crosses the LLM boundary (it's filled in AFTER the parse)."""
    rows = db.execute(
        text(
            "SELECT id::text AS rec_id, inputs->>'sku' AS sku, "
            "inputs->>'product_name' AS product_name, rounded_qty "
            "FROM scm.reorder_recommendation WHERE run_id = :r AND rec_type = 'buy' "
            # Only ORDERABLE buys are part of the plan - uncosted (needs-cost) SKUs are
            # skipped, so an instruction like "reject the rest" must never enumerate them.
            "AND unit_cost IS NOT NULL"
        ),
        {"r": run_id},
    ).mappings().all()
    return [
        {
            "rec_id": r["rec_id"],
            "sku": r["sku"],
            "product_name": r["product_name"],
            "current_qty": _num(r["rounded_qty"]),
        }
        for r in rows
    ]


_ACTION_DEFAULT_REASON = {
    "accept": "Requested for purchase.",
    "reject": "Not wanted for this plan.",
    "adjust": "Quantity adjusted on request.",
}


def _match_buy_ref(ref: Optional[str], buys: list[dict]) -> tuple[Optional[dict], bool]:
    """Resolve an LLM reference to a single buy line. Exact SKU, then exact product
    name, then a unique substring on either. Returns (line, ambiguous): a unique hit →
    (line, False); no hit → (None, False); more than one candidate → (None, True) so the
    caller lists it rather than guessing (M8-F16 ambiguous refs are not auto-applied)."""
    key = (ref or "").strip().lower()
    if not key:
        return None, False
    exact_sku = [b for b in buys if (b.get("sku") or "").strip().lower() == key]
    if len(exact_sku) == 1:
        return exact_sku[0], False
    if len(exact_sku) > 1:
        return None, True
    exact_name = [b for b in buys if (b.get("product_name") or "").strip().lower() == key]
    if len(exact_name) == 1:
        return exact_name[0], False
    if len(exact_name) > 1:
        return None, True
    subs = {
        b["rec_id"]: b
        for b in buys
        if key in (b.get("sku") or "").strip().lower()
        or key in (b.get("product_name") or "").strip().lower()
    }
    if len(subs) == 1:
        return next(iter(subs.values())), False
    if len(subs) > 1:
        return None, True
    return None, False


def _resolve_action_proposal(parsed: dict, buys: list[dict], ctx: dict) -> Optional[dict]:
    """Map the schema-forced parse onto REAL rec ids. Named refs resolve to one line
    each (ambiguous/unknown → left out + noted in the summary); ``rest`` applies its
    action to every un-named buy line. Returns ``{summary, lines}`` or ``None`` when
    nothing resolved. Also stashes a compact note in ``ctx`` so the answer prose can
    restate the proposal. Writes NOTHING (guardrail)."""
    raw_lines = parsed.get("lines") or []
    rest = parsed.get("rest") or None
    unresolved: list[str] = [u for u in (parsed.get("unresolved") or []) if u]
    summary = (parsed.get("summary") or "").strip()

    resolved: list[dict] = []
    named_ids: set[str] = set()

    for ln in raw_lines:
        if not isinstance(ln, dict):
            continue
        action = ln.get("action")
        if action not in ("accept", "reject", "adjust"):
            continue
        line, ambiguous = _match_buy_ref(ln.get("ref"), buys)
        if line is None:
            if ln.get("ref"):
                unresolved.append(ln["ref"])
            continue
        if line["rec_id"] in named_ids:
            continue
        new_qty: Optional[float] = None
        if action == "adjust":
            nq = ln.get("new_qty")
            if nq is None:
                # an adjust with no target qty can't be Applied - list it, don't guess.
                if ln.get("ref"):
                    unresolved.append(ln["ref"])
                continue
            new_qty = float(nq)
        named_ids.add(line["rec_id"])
        resolved.append(
            {
                "rec_id": line["rec_id"],
                "sku": line.get("sku"),
                "product_name": line.get("product_name"),
                "action": action,
                "current_qty": line.get("current_qty"),
                "new_qty": new_qty,
                "reason": (ln.get("reason") or "").strip() or _ACTION_DEFAULT_REASON[action],
            }
        )

    if isinstance(rest, dict) and rest.get("action") in ("accept", "reject"):
        rest_action = rest["action"]
        rest_reason = (rest.get("reason") or "").strip() or _ACTION_DEFAULT_REASON[rest_action]
        for b in buys:
            if b["rec_id"] in named_ids:
                continue
            named_ids.add(b["rec_id"])
            resolved.append(
                {
                    "rec_id": b["rec_id"],
                    "sku": b.get("sku"),
                    "product_name": b.get("product_name"),
                    "action": rest_action,
                    "current_qty": b.get("current_qty"),
                    "new_qty": None,
                    "reason": rest_reason,
                }
            )

    if not resolved:
        return None

    if unresolved:
        deduped: list[str] = []
        for u in unresolved:
            if u not in deduped:
                deduped.append(u)
        note = "I could not match: " + ", ".join(deduped) + "."
        summary = f"{summary} {note}".strip() if summary else note

    if not summary:
        summary = _default_action_summary(resolved)

    ctx["proposed_plan_actions"] = {
        "summary": summary,
        "lines": [
            {
                "sku": r["sku"],
                "action": r["action"],
                **({"new_qty": r["new_qty"]} if r["action"] == "adjust" else {}),
            }
            for r in resolved
        ],
    }
    return {"summary": summary, "lines": resolved}


def _default_action_summary(resolved: list[dict]) -> str:
    accepts = [r["sku"] or "a line" for r in resolved if r["action"] == "accept"]
    rejects = [r["sku"] or "a line" for r in resolved if r["action"] == "reject"]
    adjusts = [r["sku"] or "a line" for r in resolved if r["action"] == "adjust"]
    parts: list[str] = []
    if accepts:
        parts.append(f"accept {', '.join(accepts)}")
    if rejects:
        parts.append(f"reject {', '.join(rejects)}")
    if adjusts:
        parts.append(f"adjust {', '.join(adjusts)}")
    return "Proposed: " + "; ".join(parts) + "." if parts else "Proposed plan changes."


def _build_action_proposal(
    db: Session, ctx: dict, run_id: str, question: str
) -> Optional[dict]:
    """Turn a plan instruction into a resolved per-line proposal (M8-F16). Schema-forced
    LLM call → resolve refs to real rec ids → confirm-gated card. Degrades to ``None``
    when no provider is configured or the parse yields nothing resolvable. Writes NOTHING
    to any recommendation column (the LLM only proposes; Apply routes through /accept,
    /reject and the human-confirmed /adjust)."""
    provider, model = _provider_and_model(db)
    if provider is None:
        return None
    buys = _buy_lines_for_actions(db, run_id)
    if not buys:
        return None
    # Only SKU / name / qty reach the LLM - never a rec id (no UUIDs cross the boundary).
    plan_lines = [
        {"sku": b["sku"], "product_name": b["product_name"], "order_quantity": b["current_qty"]}
        for b in buys
        if b.get("sku")
    ]
    user_block = (
        "PLAN ACTION mode. The plan's buy lines (JSON):\n"
        f"{json.dumps(plan_lines, ensure_ascii=False)}\n\n"
        f"Planner's instruction: {question.strip()}\n\n"
        "Return the structured per-line decisions."
    )
    try:
        result = provider.chat(
            [
                {"role": "system", "content": _ACTION_PARSE_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            temperature=0.0,
            model=model,
            max_tokens=_ACTION_PARSE_MAX_TOKENS,
            json_schema=_ACTION_PARSE_JSON_SCHEMA,
            json_schema_name=_ACTION_PARSE_SCHEMA_NAME,
        )
        parsed = json.loads((result.content or "").strip() or "{}")
    except Exception:  # noqa: BLE001 - a malformed parse degrades to no proposal
        return None
    if not isinstance(parsed, dict):
        return None
    return _resolve_action_proposal(parsed, buys, ctx)


def answer_run_chat(
    db: Session,
    run_id: str,
    question: str,
    history: Optional[list[dict]] = None,
    actor: Optional[str] = None,
) -> dict:
    """The unified plan assistant turn (M8-F6 + M8-F16). One Ask input: answer grounded
    on the plan + past plans, and, depending on the question:

      * a market-trend ask auto-runs a LIVE market scan, folds the reading into the
        answer, and attaches a confirm-gated qty ``proposal`` when a signal maps to lines;
      * a plan INSTRUCTION ("buy X only, reject the rest", "bump Y to 684") is resolved
        into a structured ``action_proposal`` of per-line accept/reject/adjust decisions
        the human Applies.

    Returns ``{answer, proposal, action_proposal}`` - both proposals ``None`` unless their
    trigger fired. No numeric write anywhere (M8-E7 / M8-F16 guardrail)."""
    if not (question or "").strip():
        raise AppException(status_code=422, message="A question is required.")
    ctx = _build_run_chat_context(db, run_id, question)

    proposal: Optional[dict] = None
    if _MARKET_INTENT_RE.search(question):
        proposal = _market_augment(db, ctx, run_id, question, actor)

    # M8-F16 (fix): the plan-action proposal is gated by the SCHEMA-FORCED parse itself,
    # NOT by a keyword regex. A verb allowlist ("accept|reject|only|the rest…") silently
    # dropped natural instructions like "mr loo just wants to buy C-FH24" (no listed
    # verb) - the answer prose then promised "click Apply" with no card behind it. The
    # structured parser classifies intent semantically and returns None for a plain
    # question, so we always run it and let an empty resolution be the real gate.
    action_proposal = _build_action_proposal(db, ctx, run_id, question)

    # M8-F: a compare-with-previous-plan ask gets a DETERMINISTIC per-product diff. The
    # numbers are computed here in Python; the answer prose is told NOT to restate any
    # figure (a table is rendered) so the LLM never does the comparison arithmetic.
    comparison: Optional[dict] = None
    if _COMPARE_INTENT_RE.search(question):
        comparison = build_plan_comparison(db, run_id)
        if comparison:
            ctx["deterministic_comparison_shown"] = True

    answer = _run_chat_answer(db, ctx, question, history)
    return {
        "answer": answer,
        "proposal": proposal,
        "action_proposal": action_proposal,
        "comparison": comparison,
    }


def _rec_currency(rec: ReorderRecommendation) -> Optional[str]:
    """Currency to match signals on: the rec's own currency, else the frozen
    supplier/inputs currency."""
    if rec.currency:
        return rec.currency
    inp = rec.inputs or {}
    supplier = inp.get("supplier") or {}
    return supplier.get("currency") or inp.get("currency")


def _rec_category_refs(db: Session, rec: ReorderRecommendation) -> list[str]:
    """The category tokens a signal could be keyed by for this rec - BOTH the
    category **id** (what the topic picker stores as ``category_ref``) and the
    human ``category_code`` - so a signal matches regardless of which the config
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
        "ADVISORY mode. Recommendation context + the cached market signal (JSON - the "
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
# deterministic fallback (no LLM) - restates frozen facts, invents nothing
# ---------------------------------------------------------------------------

def _fmt(v: Optional[float]) -> str:
    if v is None:
        return "-"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def _deterministic_explanation(rec: ReorderRecommendation) -> str:
    f = _rec_facts(rec)
    sku = f.get("sku") or "this SKU"
    if rec.rec_type == "buy":
        return (
            f"Order {_fmt(f.get('order_quantity'))} units of {sku} - net position "
            f"({_fmt(f.get('net_position'))}) has reached the reorder point "
            f"({_fmt(f.get('reorder_point'))}), so it is time to replenish."
        )
    if rec.rec_type == "exception":
        return f"{sku} would reorder, but no supplier is linked to source it - link one to proceed."
    return f"{sku} is flagged for review based on its current cover."
