"""AC-1032: `output_exchange.py` no longer defines the carry rules, `tail/pending.py`
is gone.

Grep-style, source-scan assertions - the same class of guardrail
`test_import_boundary.py` and `test_focus_rules.py::TestTheRulesAreGoneFromOutputExchange`
already use, extended to the two rules and the one marker those files do not cover.

RED today: `_switch_word_domain` and `_team_clarify_pick` are still defined as functions
in `output_exchange.py` (superseded by `dialogue/focus.py::domains_from_asks` and
`dialogue/open_question.py::_team_pick` respectively, not yet deleted), the AXIS BROADEN
restore marker `broaden_axis_domain_restored` is still stamped there, and
`app/services/chatbot/tail/pending.py` still exists (superseded by
`dialogue/open_question.py::ask`, which persists the question directly). `_query_brands_
carried` / `_tier_carried` already moved to `dialogue/focus.py` at S1 and are not
re-asserted here beyond a source-scan of `output_exchange.py` for completeness.
"""
from __future__ import annotations

import re
from pathlib import Path

CHATBOT_DIR = Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"
OUTPUT_EXCHANGE = CHATBOT_DIR / "head" / "output_exchange.py"
PENDING_MODULE = CHATBOT_DIR / "tail" / "pending.py"


def test_output_exchange_no_longer_defines_the_deleted_rules() -> None:
    source = OUTPUT_EXCHANGE.read_text()

    for deleted in (
        "def _switch_word_domain",
        "def _team_clarify_pick",
    ):
        assert deleted not in source, (
            f"output_exchange.py still defines {deleted!r} - superseded by the dialogue "
            "module and not yet deleted"
        )

    # `_query_brands_carried` / `_tier_carried` moved to dialogue/focus.py at S1; only a
    # docstring/comment mention of either name should remain here, never a live stamp
    # (`o["_query_brands_carried"] = ...`).
    for stamp in ("_query_brands_carried", "_tier_carried"):
        assert not re.search(rf'o\[["\']{stamp}["\']\]\s*=', source), (
            f"output_exchange.py still stamps {stamp!r} directly - it must live only in "
            "dialogue/focus.py now"
        )

    assert "broaden_axis_domain_restored" not in source, (
        "the AXIS BROADEN restore marker is still stamped in output_exchange.py"
    )


def test_tail_pending_module_does_not_exist() -> None:
    assert not PENDING_MODULE.exists(), (
        f"{PENDING_MODULE} still exists - superseded by "
        "dialogue/open_question.py::ask, which persists the question directly"
    )
