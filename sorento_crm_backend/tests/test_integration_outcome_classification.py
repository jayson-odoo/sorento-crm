"""Integration-log outcome classification.

Covers UAC OBS-S1-01 .. OBS-S1-08.

The health card counted raw `status == 'failed'`, so benign outcomes were reported as
failures. On the live DB **every** historical `sla_management` failure is the same
thing: a 400 carrying "Conversation is already responded." - an idempotency race, not a
fault. Meanwhile rows in `pending` / `processing` / `sent` were counted in the channel
total but rendered in neither bucket, so `n8n_crm_chat_outbound` displayed
success 0 / failed 0 / total 13.

Classification is therefore four buckets that must sum to the total:
success, failed, benign, in_flight.
"""
import pytest

from app.services.integration_outcome import (
    OUTCOME_BENIGN,
    OUTCOME_FAILED,
    OUTCOME_IN_FLIGHT,
    OUTCOME_SUCCESS,
    classify,
)


class Row:
    """Minimal stand-in for an IntegrationLog row."""

    def __init__(self, channel="n8n", status="success", status_code=None, error_message=None):
        self.integration_channel = channel
        self.status = status
        self.status_code = status_code
        self.error_message = error_message


# --------------------------------------------------------------------------- #
# Plain statuses                                                              #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status", ["success", "sent"])
def test_success_statuses(status):
    assert classify(Row(status=status)) == OUTCOME_SUCCESS


@pytest.mark.parametrize("status", ["pending", "processing"])
def test_in_flight_statuses(status):
    """Counted in the channel total before, but rendered nowhere."""
    assert classify(Row(status=status)) == OUTCOME_IN_FLIGHT


def test_genuine_failure_stays_failed():
    assert classify(Row(status="failed", status_code=500, error_message="boom")) == OUTCOME_FAILED


def test_unknown_status_is_not_silently_a_success():
    """An unrecognised status must not inflate the success count."""
    assert classify(Row(status="weird-new-status")) == OUTCOME_IN_FLIGHT


# --------------------------------------------------------------------------- #
# Explicit benign statuses written by the app                                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status", ["skipped", "idempotent_already_active"])
def test_explicit_benign_statuses(status):
    assert classify(Row(status=status)) == OUTCOME_BENIGN


# --------------------------------------------------------------------------- #
# Historical rows reclassified by signature                                   #
# --------------------------------------------------------------------------- #
def test_sla_already_responded_is_benign():
    """The 46 historical sla_management 'failures' are all this one race."""
    row = Row(
        channel="sla_management",
        status="failed",
        error_message="400: {'message': 'Conversation is already responded.', 'code': 'VALIDATION'}",
    )
    assert classify(row) == OUTCOME_BENIGN


def test_signature_match_is_case_insensitive():
    row = Row(
        channel="sla_management",
        status="failed",
        error_message="400: conversation is ALREADY RESPONDED.",
    )
    assert classify(row) == OUTCOME_BENIGN


def test_signature_is_scoped_to_its_channel():
    """The same text on another channel is not assumed benign."""
    row = Row(
        channel="respond_io",
        status="failed",
        error_message="Conversation is already responded.",
    )
    assert classify(row) == OUTCOME_FAILED


def test_other_sla_failures_remain_failures():
    """Reclassification must not swallow real faults on the same channel."""
    row = Row(
        channel="sla_management",
        status="failed",
        status_code=500,
        error_message="Internal Server Error",
    )
    assert classify(row) == OUTCOME_FAILED


def test_null_error_message_on_failed_stays_failed():
    assert classify(Row(channel="sla_management", status="failed")) == OUTCOME_FAILED


# --------------------------------------------------------------------------- #
# Auth failures are real - they were the bulk of respond_io                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("code", [401, 403])
def test_auth_failures_are_real_failures(code):
    row = Row(channel="respond_io", status="failed", status_code=code, error_message="Forbidden")
    assert classify(row) == OUTCOME_FAILED
