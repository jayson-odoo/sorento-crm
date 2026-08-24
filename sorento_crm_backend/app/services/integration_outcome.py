"""Classify an integration-log row into an outcome the dashboard can honestly show.

`integration_log.status` conflates three different things: whether the call worked,
whether it is still in flight, and whether a non-2xx response was actually a problem.
Counting raw `status == 'failed'` therefore over-reports: on the live DB every historical
`sla_management` failure is one benign idempotency race ("Conversation is already
responded."), and rows sitting in `pending` / `processing` were counted in the channel
total while appearing in neither bucket - which is why `n8n_crm_chat_outbound` rendered
as success 0 / failed 0 / total 13.

Four buckets, and they must sum to the channel total.

The signature table exists for **history**. Going forward the writers record an honest
status (see `sla_tracking`, which now writes `idempotent_already_active` rather than
`failed`), so the table should shrink over time rather than grow.
"""
from __future__ import annotations

from typing import Any

OUTCOME_SUCCESS = "success"
OUTCOME_FAILED = "failed"
OUTCOME_BENIGN = "benign"
OUTCOME_IN_FLIGHT = "in_flight"

# Statuses the app writes when a call demonstrably worked.
_SUCCESS_STATUSES = frozenset({"success", "sent", "delivered"})

# Statuses meaning "expected non-action" - nothing went wrong and nothing was owed.
_BENIGN_STATUSES = frozenset({"skipped", "idempotent_already_active", "noop"})

# Statuses meaning the call is still in progress.
_IN_FLIGHT_STATUSES = frozenset({"pending", "processing", "queued", "retrying"})

# Per-channel error signatures that are benign despite being logged as failures.
# Scoped by channel deliberately: the same words on a different integration are not
# assumed harmless. Matched case-insensitively against `error_message`.
_BENIGN_SIGNATURES: dict[str, tuple[str, ...]] = {
    "sla_management": ("conversation is already responded",),
}


def classify(row: Any) -> str:
    """Return one of the four OUTCOME_* constants for an integration-log row."""
    status = (getattr(row, "status", None) or "").strip().lower()

    if status in _SUCCESS_STATUSES:
        return OUTCOME_SUCCESS
    if status in _BENIGN_STATUSES:
        return OUTCOME_BENIGN

    if status == "failed":
        channel = (getattr(row, "integration_channel", None) or "").strip().lower()
        message = (getattr(row, "error_message", None) or "").lower()
        if message:
            for signature in _BENIGN_SIGNATURES.get(channel, ()):
                if signature in message:
                    return OUTCOME_BENIGN
        return OUTCOME_FAILED

    if status in _IN_FLIGHT_STATUSES:
        return OUTCOME_IN_FLIGHT

    # Unrecognised status: treat as in-flight rather than success. An unknown value
    # must never inflate the success count - that is how a regression hides.
    return OUTCOME_IN_FLIGHT
