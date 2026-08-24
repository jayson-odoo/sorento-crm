"""SCM M5 Part B - market advisory schemas (signals viz + topic CRUD + run log).

Mirrors the FE contract in ``scm/market/types/market.types.ts``. No UUID surfaces
in a display field the FE renders: signals carry the topic's human ``topic_label``
(never ``topic_id``) and ``category_ref`` is a readable category code.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ── Signals (read-only viz) ────────────────────────────────────────────────────


class MarketSignal(BaseModel):
    id: str
    topic_label: str  # resolved from the topic - never a UUID
    category_ref: Optional[str] = None
    currency: Optional[str] = None
    value: Optional[float] = None
    trend: Optional[str] = None  # up | down | flat | null
    summary: str
    source_url: Optional[str] = None
    captured_at: str  # naive-UTC ISO string


class MarketSignalListResponse(BaseModel):
    data: list[MarketSignal]


# ── Topics (config CRUD) ───────────────────────────────────────────────────────


class MarketResearchTopic(BaseModel):
    id: str
    label: str
    category_ref: Optional[str] = None
    currency: Optional[str] = None
    search_prompt: str
    cadence: str  # daily | weekly | monthly | manual
    is_active: bool


class MarketResearchTopicWrite(BaseModel):
    label: str = Field(..., min_length=1)
    category_ref: Optional[str] = None
    currency: Optional[str] = None
    # required - the prompt drives the web search; a promptless topic is inert
    # (matches the FE modal, which requires it).
    search_prompt: str = Field(..., min_length=1)
    cadence: str = "manual"
    is_active: bool = True


class MarketTopicListResponse(BaseModel):
    data: list[MarketResearchTopic]


class MarketTopicResult(BaseModel):
    topic: MarketResearchTopic


# ── Run (observability) ────────────────────────────────────────────────────────


class MarketResearchRun(BaseModel):
    id: str
    status: str  # running | completed | failed
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    topic_count: int = 0
    signal_count: int = 0
    error: Optional[str] = None  # serialized from the model's error_text column


class MarketResearchRunResult(BaseModel):
    run: MarketResearchRun


# ── Ad-hoc search (fired from the planning flow, M6-B) ──────────────────────────


class AdhocSearchRequest(BaseModel):
    # free-text market question, e.g. "trending bathroom colours 2026"
    query: str = Field(..., min_length=1)
    category_ref: Optional[str] = None  # category id to key the signal to (optional)
    currency: Optional[str] = None


class AdhocSearchResult(BaseModel):
    signals: list[MarketSignal]
    run: MarketResearchRun


# ── Market signal -> proposed qty deltas (M8-E11, proposal ONLY, no writes) ─────


class MarketProposalRequest(BaseModel):
    # base the proposal on an existing cached signal, OR run a fresh ad-hoc search
    signal_id: Optional[str] = None
    query: Optional[str] = None
    category_ref: Optional[str] = None  # scope a fresh search to a category (optional)


class MarketProposalLine(BaseModel):
    rec_id: str  # target recommendation for the confirm-gated /adjust call
    sku: Optional[str] = None
    product_name: Optional[str] = None
    old_qty: float
    new_qty: float  # bounded uplift - a proposal, never written here
    unit_cost: Optional[float] = None
    cash_impact_delta: Optional[float] = None  # (new-old) * unit_cost; null if uncosted
    reason: str  # pre-filled from the signal for the override layer


class MarketSource(BaseModel):
    """One citation backing a market signal (M8-F): a url + optional page title."""

    url: str
    title: Optional[str] = None


class MarketProposalResult(BaseModel):
    signal_summary: Optional[str] = None
    source_url: Optional[str] = None  # kept for back-compat; prefer ``sources``
    # M8-F: the citation sources proving the signal is factual (several when available;
    # falls back to the single legacy source_url so older cached signals still show one).
    sources: list[MarketSource] = []
    lines: list[MarketProposalLine]
