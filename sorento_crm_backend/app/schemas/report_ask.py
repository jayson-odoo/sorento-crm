"""`GET /api/v1/order-management/report-ask` (lane REPORT-ENGINE, PLAN-report-engine.md
section 10).

Every field is declared on purpose: `response_model` silently drops any field the schema does
not name (LESSONS-LEARNT.md).
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class ReportAskFilter(BaseModel):
    key: str
    label: str
    values: List[str]


class ReportAskNotApplied(BaseModel):
    # REPORT-UNIFY: a filter the caller named that did not narrow the figures, and why
    # (unknown_spec | hidden | unit | invalid_value | per_document).
    filter: str
    value: str
    reason: str


class ReportAskRow(BaseModel):
    rank: int
    name: str
    qty: int
    amount: float
    # REPORT-DRILLDOWN: the ids the row's name stands for (a location's code; "none" for the
    # "(no agent)" row), so a follow-up can rank within exactly the rows printed. Empty for a
    # channel or month row (not a drill source).
    keys: List[str] = []
    # REPORT-SMART-L R3a: a category row's code (the top selling reply printed a category by its code).
    code: Optional[str] = None
    # REPORT-SMART-1021: a count measure's distinct count (customers, orders, products).
    count: Optional[int] = None
    # REPORT-SMART-1021 `compare_to`: the earlier window's figures and the change in percent
    # on the sort measure (None when the earlier figure is zero).
    prev: Optional["ReportAskFigures"] = None
    change_pct: Optional[float] = None


class ReportAskFigures(BaseModel):
    qty: int
    amount: float
    count: Optional[int] = None


class ReportAskTotal(BaseModel):
    qty: int
    amount: float
    count: Optional[int] = None
    prev: Optional[ReportAskFigures] = None
    change_pct: Optional[float] = None


class ReportAskSummaryRow(BaseModel):
    name: str
    qty: int
    amount: float
    # Undelivered orders only: the whole quantity of the lines still owing some.
    ordered_qty: Optional[int] = None


class ReportAskSummary(BaseModel):
    """REPORT-OUTSTANDING-SUMMARY: the pre-#1922 outstanding summary (`reports.ask.outstanding_summary`)."""

    documents: int
    qty: int
    amount: float
    ordered_qty: Optional[int] = None
    date_first: Optional[str] = None
    date_last: Optional[str] = None
    by_location: List[ReportAskSummaryRow] = []
    second: Optional[str] = None  # customer | product | None (both named)
    by_second: List[ReportAskSummaryRow] = []


class ReportAskResponse(BaseModel):
    status: str  # ok | refused | busy | no_products
    message: Optional[str] = None
    basis: str
    basis_label: str
    measure: str
    sort: str = "desc"
    group_by: Optional[str] = None
    group_label: Optional[str] = None
    # None = every date (an outstanding basis asked with no period).
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    filters: List[ReportAskFilter] = []
    not_applied: List[ReportAskNotApplied] = []
    rows: List[ReportAskRow] = []
    more: int = 0
    total_count: int = 0
    total: ReportAskTotal
    compare_to: Optional[str] = None
    compare_from: Optional[str] = None
    compare_until: Optional[str] = None
    # REPORT-SMART-L R3b: an item / category ranking with an agent filter carries the share of the window's
    # sales orders that carry any agent (the old top selling note); absent otherwise.
    sales_agent_fill_rate: Optional[float] = None
    # REPORT-OUTSTANDING-SUMMARY: an outstanding kind naming a product or a customer; absent otherwise.
    summary: Optional[ReportAskSummary] = None


class ReportAskChatRow(BaseModel):
    rank: int
    name: str
    value: float
    # Failure rate only: failed turns and the non-noise turns they are a share of.
    numerator: Optional[int] = None
    denominator: Optional[int] = None
    # A customer ranking only: the customer card's agent (None = no agent).
    agent: Optional[str] = None


class ReportAskChatTotal(BaseModel):
    value: float
    numerator: Optional[int] = None
    denominator: Optional[int] = None


class ReportAskChatCoverage(BaseModel):
    percent: int
    taxonomy_version: Optional[int] = None
    line: str


class ReportAskChatResponse(BaseModel):
    """`dataset=chat` (CA-3). Declared in full: `response_model` drops what is not named."""

    status: str  # ok | busy
    message: Optional[str] = None
    dataset: str = "chat"
    basis: str
    measure: str
    unit: str  # asks | turns | contacts | %
    sort: str = "desc"
    group_by: Optional[str] = None
    group_label: Optional[str] = None
    date_from: str
    date_to: str
    filters: List[ReportAskFilter] = []
    rows: List[ReportAskChatRow] = []
    more: int = 0
    total_count: int = 0
    total: ReportAskChatTotal
    coverage: Optional[ReportAskChatCoverage] = None
    # Distinct unclassified contacts, only when the reply splits or filters by asker.
    unclassified_askers: Optional[int] = None
    # Distinct unclassified contacts the default asker filter left out; null when they are in or the
    # message chose its own askers.
    unclassified_left_out: Optional[int] = None
