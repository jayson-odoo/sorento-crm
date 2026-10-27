"""Sales report grant (`sales_orders.sales_report`) - security pins, captain's brief
20 Sep 2026, from the security review of `c9967c34b..484c79d92`.

The gate itself lives at `lanes/business/__init__.py:1209-1219`
(`order_status == "sales_report"` -> `_sales_report_not_enabled()`), reached two ways:
`turn_runtime.lane_parse_output` (the `order_status` a REPLY was composed for can come
from `focus.status`, carried across turns - `turn/apply.py::_answer_outstanding` sets
`focus.status = "sales_report"` the moment a `sales_report_detail` pending is answered)
and the EARLIER `run_until_exit` bypass in the same module (R-S3, `lanes/business/
__init__.py` around line 576) that skips resolve+gate entirely for an ungranted
`sales_report` ask BEFORE it ever asks a customer picker.

Postgres only (`session_factory`, blank schema via `tests.chatbot.conftest`). Every
chain seeded fresh through `test_outstanding_lane._seed_contact`, reusing its shared
`_run_turn` harness (the real `engine.run_turn`, business lane on) and `test_
sales_report_lane`'s own `SALES_REPORT_HIT`/`SALES_REPORT_DENIAL` fixtures - no new
harness invented for three tests. No em or en dashes.

Engine code is NOT touched by this file's author (tester brief, `PRINCIPLES.md` Phase 2
discipline) - SF-1 is measured RED here and left red for the coder.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_outstanding_lane import (
    PRODUCT_CODE,
    PRODUCT_UUID,
    _ambiguous_hanlim_resolve_services,
    _qf,
    _run_turn,
    _seed_contact,
    _session_of,
)
from tests.chatbot.test_sales_report_lane import SALES_REPORT_DENIAL, SALES_REPORT_HIT


# --------------------------------------------------------------------------- #
# SF-2 - a grant present on the turn that ARMS a sales_report_detail offer (or its
# carried focus), then revoked before the offer is answered / the focus continues.
# Both are already-shipped invariants (`run_fetch`'s `_SALES_REPORT_GRANT` re-check on
# EVERY turn it reaches, never cached from an earlier turn) - measured GREEN before
# writing, not assumed.
# --------------------------------------------------------------------------- #


def _arm_sales_report_detail(session_factory, monkeypatch) -> None:
    """Turn 1, WITH the grant: a real hit, which arms a `sales_report_detail` pending
    (`turn/pending.py`'s kind) the plan's own S4 point 7 describes. Measured directly
    (`open_question.kind == "sales_report_detail"`) before this helper was written."""
    _seed_contact(session_factory, variables={})
    _run_turn(
        session_factory,
        monkeypatch,
        qf=_qf(order_status="sales_report"),
        text_body="sales report for SRTWT7445",
        msg_id="ZZT-sf2-arm-1",
        attributes=["sales_orders.sales_report"],
        matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
        mcp_response=SALES_REPORT_HIT,
    )


# --------------------------------------------------------------------------- #
# SF-1 - a FRESH, ungranted sales-report ask whose customer token resolves to SEVERAL
# customers (order domain: `customer: must_narrow_one`, `turn/policy_rows.py:143`).
# Expected RED today: `engine.py`'s own `plan.ask` short-circuits straight to
# `compose_question` (building and returning the customer roster) before `run_fetch`
# - and so before its `_SALES_REPORT_GRANT` check - is ever reached. `run_until_exit`'s
# OWN earlier R-S3 bypass (`lanes/business/__init__.py`, skips resolve+gate for an
# ungranted sales-report ask) never fires either, because the new turn engine's ask
# path does not call into `lanes/business` at all until AFTER a pick narrows the
# customer to one - the roster itself is the leak.
#
# Pinning the BEHAVIOUR (denial, no roster, no pending, no customer label reaches the
# reply), not the seam - a coder is free to close this gap at narrow/plan/decide,
# wherever `plan.ask` gets built, rather than only inside `lanes/business`.
# --------------------------------------------------------------------------- #


def _no_probe(**_kwargs: Any) -> dict[str, Any]:
    return {"items": [], "has_result": False}


class TestSF1RosterMustNotPrecedeTheGrantRefusal:
    @pytest.mark.parametrize(
        "text_body,extra_qf",
        [
            pytest.param("sales report for hanlim", {}, id="fresh-ask"),
            pytest.param(
                "dealer sales report for hanlim", {"sales_channel": "dealer"}, id="channel-worded-ask"
            ),
        ],
    )
    def test_an_ungranted_ambiguous_customer_ask_is_denied_before_any_roster(
        self, session_factory, monkeypatch, text_body: str, extra_qf: dict[str, Any]
    ) -> None:
        _seed_contact(session_factory, variables={})
        result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(
                order_status="sales_report",
                entities=[
                    {
                        "raw": "hanlim", "hint": "customer", "canonical_code": None,
                        "current_message": True, "confident": True,
                    }
                ],
                **extra_qf,
            ),
            text_body=text_body,
            msg_id=f"ZZT-sf1-{text_body[:10]}-1",
            attributes=[],  # no grant at all
            resolve_services=_ambiguous_hanlim_resolve_services(_no_probe),
        )
        reply = (result.reply or {}).get("text") or ""
        assert captured == [], (
            f"no tool may run for an ungranted sales-report ask, ambiguous customer or "
            f"not: {captured}"
        )
        assert reply.strip() == SALES_REPORT_DENIAL, (
            "an ungranted contact must be refused directly, never shown a customer "
            f"roster first: {reply!r}"
        )
        open_question = (_session_of(session_factory).get("open_question") or {})
        assert not open_question, (
            f"no roster/pick may be armed for a turn that was refused outright: "
            f"{open_question}"
        )
        for name in ("HANLIM TRADING SDN BHD", "HANLIM HARDWARE SDN BHD", "300-H070", "300-H071"):
            assert name not in reply, (
                f"a real customer match must never reach an ungranted contact's reply: "
                f"{reply!r}"
            )
