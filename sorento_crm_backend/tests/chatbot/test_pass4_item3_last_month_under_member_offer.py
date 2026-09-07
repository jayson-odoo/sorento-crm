"""Owner console pass 4, item 3 (E residue, 7 Sep 2026): "last month" under a member_offer
still refuses with "I need at least one filter", though #706 item E's own fix landed.

Production turns 0eef1cc3-5a1b-4f3f-9916-d3ee25f7cfff ("delivery to hanlim, product srtwc286"
-> no order matched, creates the `member_offer`) then 48ee6081-eb53-43b3-b7ff-26a3964d0d39
("last month", ttl 3 -> 2, reply "That would search every delivery order we have - I need at
least one filter to narrow it down..."), `turns-lane3`.

MEASURED, and stated here rather than guessed at, per the brief: the OTHER two candidate
causes are BOTH fine on this capture -
  * the date window IS derived from "last month": `_parser_raw.date_filter_start /
    date_filter_end` are `2026-08-01` / `2026-08-31` and they SURVIVE into `output` unchanged.
  * `member_offer_filter_modification` IS set to `True` on this parser output, and
    `route.decide`'s `is_low_signal` arm already yields to it (`head/route.py` ~:166-169) -
    #706 item E's own fix, confirmed still in place.

The stage that DOES drop the filter: **the offer's own entities are never carried forward.**
`output_exchange.py`'s Tier 3 "FILTER MODIFICATION" arm (`elif has_filter_signal:`, ~:2506-
2521) restores `domain_hint`/`intent_hint` from the offer's carried state, and its own
comment says "the window and the ENTITY are kept" - but the code that follows the comment
only ever writes `o["domain_hint"]` / `o["intent_hint"]`; there is no line that restores
`o["entities"]` from `prev.entities` (`hanlim` + `srtwc286`, both still `current_message:
true` in the offer's own persisted state). So this turn's `output.entities` comes out `[]`,
and the narrowed query has nothing to be narrowed to run against, though the date window and
the restored domain both survive - which is exactly the shape the production reply's refusal
text names ("Give me an order number, transporter, customer, or date range").

Expected: the narrowed query runs with the offer's own customer + product scope (`hanlim`,
`srtwc286`) PLUS the last-month window, never the "need at least one filter" refusal.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output
from tests.chatbot.test_r3_pending_end_to_end import _stub_parser


@pytest.fixture()
def seeded(session_factory):
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000009", "sv": json.dumps({"variables": {}})},
    )
    db.commit()
    return db


ROSTER = [
    {"idx": i, "label": f"Member {i}", "uuid": f"u{i}", "respond_user_id": f"r{i}"}
    for i in range(1, 7)
]


def _seed_member_offer(session_factory) -> None:
    db = session_factory()
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE respond_io_id = :cid"),
        {
            "cid": CONTACT_ID,
            "sv": json.dumps(
                {
                    "variables": {
                        "message_type": "business_query",
                        "intent_hint": "check_order",
                        "domain_hint": "order",
                        "entities": [
                            {
                                "raw": "hanlim",
                                "hint": "customer",
                                "canonical_code": None,
                                "current_message": True,
                                "confident": True,
                            },
                            {
                                "raw": "srtwc286",
                                "hint": "product",
                                "canonical_code": None,
                                "current_message": True,
                                "confident": True,
                            },
                        ],
                        "routing": {
                            "suggested_team": "customer_service",
                            "suggested_agent": "order_enquiries",
                        },
                        "escalation": {"is_escalation_confirmation": False},
                        "response": (
                            "But no order matched these. Would you like me to escalate to "
                            "Sorento customer service team?"
                        ),
                        "selection_context": "member_offer",
                        "last_result_set": ROSTER,
                        "pending": {
                            "kind": "member_offer",
                            "team": "customer_service",
                            "domain": "order",
                            "ttl": 3,
                        },
                    }
                }
            ),
        },
    )
    db.commit()


class TestLastMonthUnderAMemberOfferKeepsTheOffersOwnScope:
    def test_last_month_narrows_with_hanlim_and_srtwc286_never_the_need_a_filter_refusal(
        self, seeded, session_factory, monkeypatch
    ):
        _seed_member_offer(session_factory)

        qf = _parser_output(
            message_type="casual",
            intent_hint=None,
            domain_hint=None,
            entities=[],
            date_mode=None,
            date_filter_start="2026-08-01",
            date_filter_end="2026-08-31",
            routing={"suggested_team": None, "suggested_agent": None},
        )
        _stub_parser(monkeypatch, qf)
        envelope = _envelope(is_test=True)
        envelope.message["message"]["messageId"] = "ZZT-item3-last-month"
        envelope.message["message"]["message"]["text"] = "last month"

        head = engine_mod.run_turn(envelope, session_factory=session_factory)

        output = head.ctx["parse"]["output"]
        # The two premises the brief asks to be checked, both measured fine on this capture -
        # stated as assertions so a future regression there is caught here too, not silently
        # re-attributed to this test.
        assert output.get("member_offer_filter_modification") is True, output
        assert output.get("date_filter_start") == "2026-08-01", output
        assert output.get("date_filter_end") == "2026-08-31", output
        assert output.get("domain_hint") == "order", (
            f"the carried domain must survive the filter-modification arm: {output!r}"
        )

        # The actual defect: the offer's own scope never reaches this turn's entities.
        raws = {str(e.get("raw")).lower() for e in (output.get("entities") or [])}
        assert {"hanlim", "srtwc286"} <= raws, (
            "a date-only narrowing of a still-open member offer must keep the offer's own "
            f"customer and product in scope, not drop them: entities={output.get('entities')!r}"
        )

        assert head.branch_kind != "low_signal", (
            f"the filter-modification fix must keep this off low_signal: {head.branch_kind!r}"
        )
