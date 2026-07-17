"""SCM M5 Part B — market advisory schemas (signals viz + topic CRUD + run log).

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
    topic_label: str  # resolved from the topic — never a UUID
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
    # required — the prompt drives the web search; a promptless topic is inert
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
