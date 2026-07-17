"""SCM M8-E11 — market signal -> proposed qty deltas (proposal ONLY, no writes).

A market signal reaches the plan through the chat, never the engine. This service
takes a signal (an existing cached ``scm.market_signal`` by id, OR a fresh ad-hoc
web search), matches it to the run's BUY recs by product **category id OR code**
(the same both-ways match the advisory + market factor use), and returns a concrete
per-line proposal: old qty -> a bounded uplifted qty, the recomputed cash impact
delta, and a reason pre-filled from the signal.

HARD GUARDRAIL (umbrella §0 / M8-E7): this NEVER writes a numeric field on
``reorder_recommendation`` and NEVER re-runs the engine. It returns a proposal; the
human confirms per line via the existing ``POST /recommendations/{id}/adjust`` which
lands the number in the override layer. The only table an ad-hoc search touches is
``scm.market_signal`` (its own advisory-only table) — never a recommendation column.

Ambiguous matches are LISTED, not collapsed (M8-E6): every matching buy rec becomes
its own candidate line for the user to choose from.
"""
from __future__ import annotations

import math
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.scm import MarketSignal, ReorderRun
from app.services.error_handler import AppException
from app.services.scm import market_research_service, reorder_engine

# The suggested uplift on a market up-trend: +12%, the mid-point of the 10-15% band
# the plan calls for. Deterministic + documented; the human still confirms the number.
UPLIFT_PCT = 0.12


def _num(v) -> Optional[float]:
    return float(v) if v is not None else None


def _proposed_qty(
    old_qty: float,
    *,
    moq: Optional[float],
    order_multiple: Optional[float],
    max_qty: Optional[float],
) -> float:
    """Bounded suggested new qty: uplift ``old_qty`` by ``UPLIFT_PCT``, floor at moq +
    round UP to the order multiple (the engine's own rounding), ceil to a whole unit,
    and clamp to any ``max_qty`` cap on the rec. Never drops below the original."""
    target = old_qty * (1.0 + UPLIFT_PCT)
    new_qty = reorder_engine.round_order_qty(target, moq, order_multiple)
    # ceil to whole units, but round off float noise first (100*1.12 = 112.0000…1)
    new_qty = float(math.ceil(round(new_qty, 6)))
    if new_qty <= old_qty:
        # rounding collapsed the uplift — nudge by one order step so it is a real delta
        step = float(order_multiple) if order_multiple and float(order_multiple) > 0 else 1.0
        new_qty = old_qty + step
    if max_qty is not None and new_qty > float(max_qty):
        new_qty = float(max_qty)
    return new_qty


def _resolve_signal(
    db: Session,
    *,
    signal_id: Optional[str],
    query: Optional[str],
    category_ref: Optional[str],
    actor: Optional[str],
) -> Optional[MarketSignal]:
    """Resolve the signal to base the proposal on: an existing cached signal by id, or
    the newest signal from a fresh ad-hoc web search. ``None`` when a search found
    nothing (graceful empty proposal, no crash)."""
    if signal_id:
        sig = db.query(MarketSignal).filter(MarketSignal.id == signal_id).first()
        if sig is None:
            raise AppException(status_code=404, message="Market signal not found.")
        return sig
    if (query or "").strip():
        out = market_research_service.search_adhoc(db, query or "", category_ref, actor=actor)
        signals = out.get("signals") or []
        if not signals:
            return None  # no key / nothing found — degrade to an empty proposal
        return (
            db.query(MarketSignal)
            .filter(MarketSignal.id == signals[0]["id"])
            .first()
        )
    raise AppException(status_code=422, message="A signal_id or query is required.")


def _matching_buy_recs(db: Session, run_id: str, category_ref: Optional[str]) -> list[dict]:
    """The run's BUY recs whose product category (id OR code) matches the signal's
    ``category_ref``. Empty when the signal has no category (advisory-only, un-mappable)."""
    if not category_ref:
        return []
    rows = db.execute(
        text(
            "SELECT r.id::text AS rec_id, r.rounded_qty AS rounded_qty, "
            "r.unit_cost AS unit_cost, r.currency AS currency, r.inputs AS inputs, "
            "r.inputs->>'sku' AS sku, r.inputs->>'product_name' AS product_name "
            "FROM scm.reorder_recommendation r "
            "JOIN products p ON p.id = r.product_id "
            "LEFT JOIN product_categories pc ON pc.id = p.category_id "
            "WHERE r.run_id = :run AND r.rec_type = 'buy' "
            "AND (p.category_id::text = :ref OR pc.category_code = :ref) "
            "ORDER BY r.rank NULLS LAST, r.inputs->>'sku'"
        ),
        {"run": run_id, "ref": category_ref},
    ).mappings().all()
    return [dict(r) for r in rows]


def _line_reason(signal: MarketSignal) -> str:
    """Pre-filled override reason built from the signal (not the model). Hyphen only."""
    trend = f" (trend {signal.trend})" if signal.trend else ""
    summary = (signal.summary or "market signal").strip()
    return f"Market signal{trend}: {summary} - suggested +{int(UPLIFT_PCT * 100)}% cover."


def build_market_proposal(
    db: Session,
    run_id: str,
    *,
    signal_id: Optional[str] = None,
    query: Optional[str] = None,
    category_ref: Optional[str] = None,
    actor: Optional[str] = None,
) -> dict:
    """Map a market signal to a per-line qty-uplift proposal on the run's matching BUY
    recs (M8-E5/E6). Read-only: returns a proposal, writes NOTHING to any
    recommendation column and never re-runs the engine (M8-E7)."""
    run = db.query(ReorderRun).filter(ReorderRun.id == run_id).first()
    if not run:
        raise AppException(status_code=404, message="Run not found.")

    signal = _resolve_signal(
        db, signal_id=signal_id, query=query, category_ref=category_ref, actor=actor
    )
    if signal is None:
        return {"signal_summary": None, "source_url": None, "sources": [], "lines": []}

    recs = _matching_buy_recs(db, run_id, signal.category_ref)
    reason = _line_reason(signal)
    lines: list[dict] = []
    for r in recs:
        old_qty = _num(r["rounded_qty"]) or 0.0
        inp = r["inputs"] or {}
        new_qty = _proposed_qty(
            old_qty,
            moq=_num(inp.get("moq")),
            order_multiple=_num(inp.get("order_multiple")),
            max_qty=_num(inp.get("max_qty")),
        )
        unit_cost = _num(r["unit_cost"])
        cash_impact_delta = (
            round((new_qty - old_qty) * unit_cost, 2) if unit_cost is not None else None
        )
        lines.append(
            {
                "rec_id": r["rec_id"],
                "sku": r["sku"],
                "product_name": r["product_name"],
                "old_qty": old_qty,
                "new_qty": new_qty,
                "unit_cost": unit_cost,
                "cash_impact_delta": cash_impact_delta,
                "reason": reason,
            }
        )
    return {
        "signal_summary": signal.summary,
        "source_url": signal.source_url,
        "sources": _signal_sources(signal),
        "lines": lines,
    }


def _signal_sources(signal: MarketSignal) -> list[dict]:
    """Citation sources for a signal (M8-F): the harvested ``sources`` list when present,
    else a single-item fallback built from the legacy ``source_url`` so older cached
    signals still surface one clickable link. Deduped, url-only entries dropped."""
    out: list[dict] = []
    seen: set[str] = set()
    for s in signal.sources or []:
        url = (s.get("url") if isinstance(s, dict) else None) or ""
        url = url.strip()
        if url and url not in seen:
            seen.add(url)
            out.append({"url": url, "title": (s.get("title") if isinstance(s, dict) else None)})
    if not out and (signal.source_url or "").strip():
        out.append({"url": signal.source_url.strip(), "title": None})
    return out
