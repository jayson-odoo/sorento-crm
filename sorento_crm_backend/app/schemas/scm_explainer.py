"""SCM M5 - semantic explainer request/response schemas (bounded LLM flow)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.scm_market import MarketProposalResult


class ExplanationResult(BaseModel):
    explanation: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)


class AskResult(BaseModel):
    answer: str


class AdvisoryResult(BaseModel):
    advisory: Optional[str] = None


class RunOverviewResult(BaseModel):
    overview: str


class RunChatTurn(BaseModel):
    """One prior exchange in the plan-chat transcript (client-held, forwarded so
    follow-ups resolve)."""

    question: str
    answer: str


class RunChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    history: list[RunChatTurn] = Field(default_factory=list)


class ActionProposalLine(BaseModel):
    """One confirm-gated per-line decision the assistant proposes from a natural-language
    plan instruction (M8-F16). ``rec_id`` is a REAL recommendation the FE routes through
    the existing /accept · /reject · /adjust endpoints on Apply - the LLM proposes the
    line + the decision, the human confirms, no numeric field is ever written by the LLM."""

    rec_id: str
    sku: Optional[str] = None
    product_name: Optional[str] = None
    action: str  # accept | reject | adjust
    current_qty: Optional[float] = None
    new_qty: Optional[float] = None  # adjust only - the proposed qty (still confirmed via /adjust)
    reason: str


class ActionProposal(BaseModel):
    """The structured action card (M8-F16): a plain-language summary + resolved per-line
    decisions. Unresolvable references are left OUT of ``lines`` and named in ``summary``."""

    summary: str
    lines: list[ActionProposalLine]


class PlanComparisonRow(BaseModel):
    """One product's THIS-run vs PRIOR-run figures (M8-F: deterministic compare). Every
    number is a frozen engine value; the LLM never computes or compares them."""

    sku: Optional[str] = None
    product_name: Optional[str] = None
    # current run
    current_qty: Optional[float] = None
    current_funding: Optional[str] = None  # funded | deferred
    current_days_cover: Optional[float] = None
    current_net: Optional[float] = None
    # most-recent prior run (null when this product was never planned before)
    previous_run_date: Optional[str] = None
    previous_qty: Optional[float] = None
    previous_decision: Optional[str] = None  # proposed | accepted | adjusted | dismissed
    previous_days_cover: Optional[float] = None
    previous_net: Optional[float] = None
    # deterministic deltas
    qty_delta: Optional[float] = None  # current_qty - previous_qty (null when no prior)
    direction: str  # new | up | down | same
    reason: str  # deterministic qualitative why, built in Python from the deltas


class PlanComparison(BaseModel):
    """Deterministic product-by-product comparison of this plan against each product's
    most recent prior plan (M8-F: 'how does this plan compare to the previous plans')."""

    rows: list[PlanComparisonRow]
    compared_count: int  # rows that HAD a prior plan to compare against


class RunChatResult(BaseModel):
    answer: str
    # M8-F6: attached only when a live market scan mapped a signal onto plan lines  - 
    # the same confirm-gated proposal card the standalone market-proposal returned.
    proposal: Optional[MarketProposalResult] = None
    # M8-F16: attached when the question is a natural-language plan INSTRUCTION the
    # assistant resolved into per-line accept/reject/adjust decisions to Apply.
    action_proposal: Optional[ActionProposal] = None
    # M8-F: attached when the question asks how this plan compares to previous plans  - 
    # a DETERMINISTIC per-product diff (numbers computed in Python, never the LLM).
    comparison: Optional[PlanComparison] = None


# ── Cross-run history (M8-E3) ──────────────────────────────────────────────


class PastPlanLine(BaseModel):
    """One prior-run recommendation line for the same SKU / a category sibling /
    a variant neighbour. All human-readable (product_code, not a UUID)."""

    run_date: Optional[str] = None  # naive-UTC ISO string of the past run
    product_code: Optional[str] = None
    rounded_qty: Optional[float] = None
    funding_status: Optional[str] = None  # funded | deferred | null
    decision_status: Optional[str] = None  # proposed | accepted | adjusted | dismissed
    override_reason: Optional[str] = None
    days_of_cover: Optional[float] = None


class PastPlansResult(BaseModel):
    data: list[PastPlanLine]
