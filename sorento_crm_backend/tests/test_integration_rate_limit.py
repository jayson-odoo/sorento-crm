"""Slice 9 of AutoCount Group A — per-integration rate limiting (AC-AC-10).

**Given** an integration exceeding its configured rate
**When** it calls
**Then** 429 with Retry-After is returned
**And** the limit is per integration, not global
**And** when the limiter backend is unavailable the request is allowed
    (fail-open) and an alert is raised.

Fail-open is the deliberate choice (plan decision A7). Rate limiting here is
abuse control, not authorization: a dead limiter grants nobody access, because
authentication is DB-backed and still enforced. Fail-closed would turn a Redis
blip into a simultaneous ESB-sync and n8n outage.
"""
from unittest.mock import patch

import pytest

from app.services.integration_rate_limit import (
    DEFAULT_LIMIT_PER_MINUTE,
    RateLimitOutcome,
    check_integration_rate_limit,
    limit_for,
)


class _FakeIntegration:
    def __init__(self, id_="int-1", name="n8n", config_json=None):
        self.id = id_
        self.name = name
        self.config_json = config_json


class TestLimitResolution:
    def test_uses_the_documented_default_when_unconfigured(self):
        assert limit_for(_FakeIntegration()) == DEFAULT_LIMIT_PER_MINUTE

    def test_per_integration_override_from_config(self):
        # The ESB pushing 10k products needs a different ceiling from a
        # conversational webhook. One global number cannot serve both.
        assert limit_for(_FakeIntegration(config_json={"rate_limit_per_minute": 5000})) == 5000

    def test_zero_disables_the_limit(self):
        # Matches the existing limiter's convention: limit<=0 means unlimited.
        assert limit_for(_FakeIntegration(config_json={"rate_limit_per_minute": 0})) == 0

    def test_ignores_a_nonsense_override_rather_than_crashing_auth(self):
        # config_json is operator-editable. A bad value must not take down the
        # authentication path for that integration.
        assert limit_for(_FakeIntegration(config_json={"rate_limit_per_minute": "lots"})) == (
            DEFAULT_LIMIT_PER_MINUTE
        )

    def test_ignores_a_negative_override(self):
        assert limit_for(_FakeIntegration(config_json={"rate_limit_per_minute": -10})) == (
            DEFAULT_LIMIT_PER_MINUTE
        )


class TestEnforcement:
    def test_allows_when_under_the_limit(self):
        with patch("app.services.integration_rate_limit.rate_limit.hit") as hit:
            hit.return_value = type("R", (), {"allowed": True, "retry_after_seconds": None})()
            outcome = check_integration_rate_limit(_FakeIntegration())
        assert outcome.allowed is True

    def test_denies_with_retry_after_when_over(self):
        with patch("app.services.integration_rate_limit.rate_limit.hit") as hit:
            hit.return_value = type("R", (), {"allowed": False, "retry_after_seconds": 42})()
            outcome = check_integration_rate_limit(_FakeIntegration())
        assert outcome.allowed is False
        # Without Retry-After the caller can only guess, and a well-behaved
        # integration degrades into a hot retry loop.
        assert outcome.retry_after_seconds == 42

    def test_bucket_is_keyed_per_integration_not_globally(self):
        # AC-AC-10: one noisy integration must not throttle the others.
        with patch("app.services.integration_rate_limit.rate_limit.hit") as hit:
            hit.return_value = type("R", (), {"allowed": True, "retry_after_seconds": None})()
            check_integration_rate_limit(_FakeIntegration(id_="int-A"))
            check_integration_rate_limit(_FakeIntegration(id_="int-B"))

        idents = [call.args[1] for call in hit.call_args_list]
        assert idents == ["int-A", "int-B"]
        assert len(set(idents)) == 2

    def test_disabled_limit_skips_the_backend_entirely(self):
        with patch("app.services.integration_rate_limit.rate_limit.hit") as hit:
            outcome = check_integration_rate_limit(
                _FakeIntegration(config_json={"rate_limit_per_minute": 0})
            )
        assert outcome.allowed is True
        hit.assert_not_called()


class TestFailOpen:
    def test_allows_when_the_limiter_backend_is_unavailable(self):
        # A7. The worst case is an already-authenticated caller going
        # unthrottled during an outage -- far better than blocking every
        # integration because Redis blipped.
        with patch("app.services.integration_rate_limit.rate_limit.hit") as hit:
            hit.side_effect = RuntimeError("redis down")
            outcome = check_integration_rate_limit(_FakeIntegration())
        assert outcome.allowed is True
        assert outcome.degraded is True

    def test_degraded_state_is_alerted_not_silent(self):
        # A limiter that is quietly off is indistinguishable from one that is
        # working. The alert is what makes the fail-open honest.
        with patch("app.services.integration_rate_limit.rate_limit.hit") as hit, patch(
            "app.services.integration_rate_limit._alert_limiter_degraded"
        ) as alert:
            hit.side_effect = RuntimeError("redis down")
            check_integration_rate_limit(_FakeIntegration())
        alert.assert_called_once()

    def test_normal_operation_raises_no_alert(self):
        with patch("app.services.integration_rate_limit.rate_limit.hit") as hit, patch(
            "app.services.integration_rate_limit._alert_limiter_degraded"
        ) as alert:
            hit.return_value = type("R", (), {"allowed": True, "retry_after_seconds": None})()
            check_integration_rate_limit(_FakeIntegration())
        alert.assert_not_called()

    def test_a_failing_alert_never_breaks_the_request(self):
        # Observability must not become a new failure mode on the auth path.
        with patch("app.services.integration_rate_limit.rate_limit.hit") as hit, patch(
            "app.services.integration_rate_limit._alert_limiter_degraded"
        ) as alert:
            hit.side_effect = RuntimeError("redis down")
            alert.side_effect = RuntimeError("alerting is also down")
            outcome = check_integration_rate_limit(_FakeIntegration())
        assert outcome.allowed is True


class TestOutcomeShape:
    def test_outcome_reports_the_limit_it_applied(self):
        # An operator seeing a 429 needs to know which ceiling was hit before
        # they can decide whether to raise it.
        with patch("app.services.integration_rate_limit.rate_limit.hit") as hit:
            hit.return_value = type("R", (), {"allowed": False, "retry_after_seconds": 30})()
            outcome = check_integration_rate_limit(
                _FakeIntegration(config_json={"rate_limit_per_minute": 120})
            )
        assert outcome.limit == 120

    def test_outcome_is_a_rate_limit_outcome(self):
        with patch("app.services.integration_rate_limit.rate_limit.hit") as hit:
            hit.return_value = type("R", (), {"allowed": True, "retry_after_seconds": None})()
            assert isinstance(check_integration_rate_limit(_FakeIntegration()), RateLimitOutcome)
