"""`tests/chatbot/COVERAGE.md` is the gate-0 evidence, so it must not be able to go stale.

Review B2: the file said `route-turn 5 / build-ctx 3` while the loader found 116 / 114,
and `--check` exited 1 with nobody running it. A coverage report that lags the corpus is
worse than none - it is a green light nobody re-earned.

The check is content equality against a fresh render, so the failure names the drift and
the fix is one command. It runs against the FULL corpus when the sibling n8n checkout is
present and skips when it is not: CI has the vendored subset only, and grading a
report about 700 fixtures against 134 would fail for the wrong reason.
"""
from __future__ import annotations

import pytest

from scripts import chatbot_fixture_coverage as coverage
from tests.chatbot import _corpus


@pytest.fixture()
def full_corpus() -> None:
    """Only the tests that COMPARE the file need the corpus.

    Deliberately not autouse: the gate-state logic below is pure and is exactly what CI
    (which has the vendored subset only) should still be grading. Skipping it there would
    leave the `exhausted` rule untested in the one place it decides whether a PR opens.
    """
    if _corpus.corpus_root() is None:
        pytest.skip(
            "COVERAGE.md describes the FULL corpus, which this checkout cannot see; "
            f"{_corpus.corpus_skip_reason()}"
        )


def test_coverage_md_is_not_stale(full_corpus) -> None:
    rendered = coverage.render(coverage.collect())
    current = coverage.OUTPUT.read_text(encoding="utf-8") if coverage.OUTPUT.exists() else ""
    assert current == rendered, (
        "tests/chatbot/COVERAGE.md no longer matches the corpus - run "
        "`python scripts/chatbot_fixture_coverage.py` and commit the result"
    )


def test_the_check_flag_agrees_with_the_file(full_corpus) -> None:
    """`--check` is what a human or a CI step would run; keep the two in step."""
    import sys

    argv = sys.argv
    sys.argv = ["chatbot_fixture_coverage.py", "--check"]
    try:
        assert coverage.main() == 0
    finally:
        sys.argv = argv


class TestGateStates:
    """The three non-`met` states each mean something different; none may collapse."""

    def test_a_short_cell_in_an_unscanned_pool_blocks(self) -> None:
        state, blocks = coverage._cell_state("a-node-nobody-captured", "some_branch", 1)
        assert state == "SHORT"
        assert blocks is True

    def test_a_short_cell_in_a_fully_scanned_pool_does_not_block(self) -> None:
        state, blocks = coverage._cell_state("route-turn", "not_supported", 1)
        assert state == "exhausted (1)"
        assert blocks is False

    def test_a_node_IN_the_report_but_UNDER_scanned_is_still_short(self, monkeypatch) -> None:
        """`exhausted` is earned by `scanned == version_pool`, never by appearing in the
        table. A partly-scanned pool means the missing captures might be there and nobody
        looked, which is precisely what gate 0 must keep blocking on - granting the state
        by membership would turn the report into a rubber stamp."""
        partly = dict(coverage.CAPTURE_REPORT["spine-rs-1a"])
        partly["scanned"] = 300  # of 567 on this version
        monkeypatch.setitem(coverage.CAPTURE_REPORT, "spine-rs-1a", partly)

        assert coverage._pool_is_exhausted(partly) is False
        state, blocks = coverage._cell_state("route-turn", "not_supported", 1)
        assert state == "SHORT"
        assert blocks is True

    def test_a_dead_by_vocabulary_cell_is_exempt_even_in_an_under_scanned_pool(
        self, monkeypatch
    ) -> None:
        partly = dict(coverage.CAPTURE_REPORT["spine-rs-1a"])
        partly["scanned"] = 0
        monkeypatch.setitem(coverage.CAPTURE_REPORT, "spine-rs-1a", partly)
        assert coverage._cell_state("route-turn", "demand_qty", 0) == (
            "dead by vocabulary",
            False,
        )

    def test_the_scans_on_record_today_are_complete(self) -> None:
        """If this ever goes red, the report was edited without a re-scan."""
        for slug, report in coverage.CAPTURE_REPORT.items():
            assert report["scanned"] == report["version_pool"], (
                f"{slug} is recorded as {report['scanned']} of {report['version_pool']} "
                "on its current version, so its branches are SHORT, not exhausted"
            )
            assert report["version_pool"] <= report["all_versions"]

    def test_a_dead_by_vocabulary_cell_never_blocks_at_any_count(self) -> None:
        """H1: live tests `stock_check` and the parser emits `check_stock`, so these two
        arms have never fired. 0 is the CORRECT number, not a gap."""
        for branch in ("demand_qty", "stock_denied"):
            state, blocks = coverage._cell_state("route-turn", branch, 0)
            assert state == "dead by vocabulary"
            assert blocks is False

    def test_a_met_cell_is_met_wherever_it_lives(self) -> None:
        assert coverage._cell_state("route-turn", "business_query", 87) == ("met", False)


# The cells gate 0 blocks on TODAY, pinned so the list can only shrink. Every entry is a
# tail node the S2 slice ports, and every one is short for the same reason: no capture
# agent has run against `sub-output` yet, so its pool is not in `CAPTURE_REPORT` and
# `exhausted` cannot be earned. The fix is a capture run before the S2 PR opens, per gate
# 0; the fix is NEVER an entry added here. A cell that leaves this list and a cell that
# joins it are both failures worth reading.
EXPECTED_BLOCKING: frozenset[str] = frozenset(
    {
        "build-cs-member-offer/all (4 of 5)",
        "build-outcome/access_choice (2 of 5)",
        "build-outcome/not_found (1 of 5)",
        "build-outcome/not_supported (3 of 5)",
        "build-outcome/out_of_scope (4 of 5)",
        "compile-current-state/goods_receive (2 of 5)",
        "compile-current-state/ideate (3 of 5)",
        "compile-current-state/product_attachment (2 of 5)",
        "compile-current-state/resource_attachment (0 of 5)",
        "compile-current-state/spo_allocation (4 of 5)",
        "crossdomain-compose/incoming (3 of 5)",
        "crossdomain-compose/inventory (4 of 5)",
        "crossdomain-compose/no_domain (1 of 5)",
        "crossdomain-compose/promotion (1 of 5)",
        "crossdomain-compose/spo_allocation (1 of 5)",
        "cs-roster-plan/all (4 of 5)",
        "escalate-catalog/access_choice (1 of 5)",
        "escalate-catalog/clarify_menu (3 of 5)",
        "escalate-catalog/not_supported (3 of 5)",
        "escalate-catalog/offer_hold (3 of 5)",
    }
)


class TestTheReportIsHonest:
    def test_the_cells_gate_zero_blocks_on_are_exactly_the_ones_on_record(
        self, full_corpus
    ) -> None:
        """Pinned, not "nothing blocks": S2's tail nodes are short until a capture run.

        Asserting the SET is what keeps the state honest in both directions - a new short
        cell fails here instead of hiding in a table, and a cell that has since been
        captured fails too, so the list shrinks rather than rotting.
        """
        blocking = set(coverage.blocking_cells(coverage.collect()))
        assert blocking == set(EXPECTED_BLOCKING), (
            "gate 0's blocking set moved.\nnewly blocking: "
            f"{sorted(blocking - EXPECTED_BLOCKING)}\nno longer blocking (retire them): "
            f"{sorted(EXPECTED_BLOCKING - blocking)}"
        )

    def test_the_world_corpus_is_reported_with_its_shapes(self, full_corpus) -> None:
        """AC-009's own numbers are in the report, so gate 0 can be read in one place."""
        rendered = coverage.render(coverage.collect())
        assert "## World replay (AC-009)" in rendered
        for shape in ("picker", "did_you_mean", "tier_ask", "escalation", "offer_hold", "media"):
            assert f"`{shape}`" in rendered

    def test_every_route_turn_branch_has_a_row_even_at_zero_captures(self, full_corpus) -> None:
        """A branch nobody captured must be a VISIBLE zero, not an absent row."""
        from app.services.chatbot.contracts import BRANCH_KINDS

        rows = coverage.collect()["rows"]["route-turn"]
        assert set(BRANCH_KINDS) <= set(rows)

    def test_the_capture_pools_are_recorded_with_their_version(self, full_corpus) -> None:
        rendered = coverage.render(coverage.collect())
        for report in coverage.CAPTURE_REPORT.values():
            assert report["version"] in rendered
            assert str(report["scanned"]) in rendered
            assert str(report["version_pool"]) in rendered
