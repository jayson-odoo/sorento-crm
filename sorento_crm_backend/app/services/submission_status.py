"""The status a form lands on when it is submitted.

A first submit is ``submitted``. A submit that answers a rejection is ``resubmitted``
(owner, 27 Oct 2026), so staff and the contact can tell an appeal from a fresh form.
Staff may do everything from ``resubmitted`` that they may from ``submitted``: any
check that meant "waiting for the office" reads ``AWAITING_REVIEW``, never the bare
``"submitted"`` string. Plan: documentation/plans/forms/PLAN-resubmitted-status-27oct.md.
"""
from __future__ import annotations

SUBMITTED = "submitted"
RESUBMITTED = "resubmitted"

AWAITING_REVIEW: tuple[str, ...] = (SUBMITTED, RESUBMITTED)


def status_on_submit(was_rejected: bool) -> str:
    return RESUBMITTED if was_rejected else SUBMITTED
