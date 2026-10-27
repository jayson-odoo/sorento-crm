"""The status a form lands on when it is submitted, and what "waiting for the office" means.

A first submit lands on the form's own review stage (``submitted`` for most forms;
``pending_project_sales`` for a stock inquiry, ``pending`` for a project registration,
``pending_approval`` for a quotation or a dealer-kit edition). A submit that answers a
rejection lands on ``resubmitted`` instead (owner, 27 Oct 2026), on every form, so staff
and the contact can tell an appeal from a fresh form.

``resubmitted`` behaves exactly like the stage it stands in for. Any gate, filter,
button or counter that meant "sitting at that stage" reads ``is_awaiting_review`` /
``awaiting_review_statuses``, never the bare stage string.
Plan: documentation/plans/forms/PLAN-resubmitted-status-27oct.md.
"""
from __future__ import annotations

from typing import Optional

SUBMITTED = "submitted"
RESUBMITTED = "resubmitted"

AWAITING_REVIEW: tuple[str, ...] = (SUBMITTED, RESUBMITTED)


def status_on_submit(was_rejected: bool, stage: str = SUBMITTED) -> str:
    return RESUBMITTED if was_rejected else stage


def awaiting_review_statuses(stage: str = SUBMITTED) -> tuple[str, ...]:
    return (stage, RESUBMITTED)


def is_awaiting_review(status: Optional[str], stage: str = SUBMITTED) -> bool:
    return (status or "").strip().lower() in awaiting_review_statuses(stage)
