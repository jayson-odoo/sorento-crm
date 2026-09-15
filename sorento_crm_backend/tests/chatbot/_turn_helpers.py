"""Shared builders for the S2 `app/services/chatbot/turn/` red tests (AC-1520 to
AC-1528, PLAN-chatbot-turn-rearch.md).

Not itself a test file (no `test_` prefix - pytest never collects it).

`verdict(**overrides)` is a PLAIN DICT, not a pydantic class: neither the PLAN nor the
UAC asserts `Verdict` is a pydantic model, and every existing reader in this package
(`jsc.get`, the lane modules) already consumes the parser's output as a dict - so the
tests build the same shape `apply()` is expected to accept. Every key defaults to the
parser schema's own "said nothing" value. `document`/`status`/`anaphora.
backward_reference`/`answers_open_question`/`escalation.escalation_declined` are NEW
keys the S0/S4 schema does not carry today (`head/parser.py::_build_json_schema` has no
`document`, `status`, `anaphora` or `answers_open_question` key yet, and `escalation`
carries only `is_escalation_confirmation`/`company_pick`) - included here because S2's
contract needs them; this is itself one of the ambiguities in the tester's report (the
exact shape of `answers_open_question`/`escalation.escalation_declined` is inferred from
the captain's brief, not read off an existing schema).

`PENDING_KINDS` (the "eight existing" pending kinds AC-1521 names) has no home today as
a single named constant - `contracts.OPEN_QUESTION_KINDS` does not exist. Derived here by
grepping every literal `"kind": "..."` a `pending`-shaped dict is built with across
`app/services/chatbot/` (`tail/pending.py`, `lanes/business/__init__.py`,
`lanes/escalation.py`, `tail/compile_state.py`): `escalation_offer`, `member_offer`,
`team_clarify`, `outstanding_scope`, `outstanding_detail`, `tier_ask`, `company_clarify`,
`disambiguation` - eight, matching the UAC's own count. Flagged as derived-not-literal.
"""
from __future__ import annotations

from typing import Any

PENDING_KINDS: tuple[str, ...] = (
    "escalation_offer",
    "member_offer",
    "team_clarify",
    "outstanding_scope",
    "outstanding_detail",
    "tier_ask",
    "company_clarify",
    "disambiguation",
)

# `reset_on_topic`'s survivors (PLAN AC-1525 / the ported `test_focus_rules.py` on
# `feat/chatbot-focus`, `TestResetOnTopic.test_topic_reset_clears_the_question_and_
# keeps_the_asker`): a topic reset clears every focus axis EXCEPT these two.
RESET_KEEPS: frozenset[str] = frozenset({"tier", "brands"})


def entity(
    raw: str,
    hint: str | None = "product",
    *,
    canonical_code: str | None = None,
    current_message: bool = True,
    confident: bool = True,
    hint_confident: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "raw": raw,
        "hint": hint,
        "canonical_code": canonical_code if canonical_code is not None else raw,
        "current_message": current_message,
        "confident": confident,
        "hint_confident": hint_confident,
        **extra,
    }


def verdict(**overrides: Any) -> dict[str, Any]:
    """The parser's parsed output, every key defaulted to its "said nothing" value."""
    base: dict[str, Any] = {
        "message_type": "business_query",
        "intent_hint": None,
        "domain_hint": None,
        "scope_intent": None,
        "is_affirmative": None,
        "user_goal": None,
        "access_levels": [],
        "broaden_axis": None,
        "date_mode": None,
        "date_filter_start": None,
        "date_filter_end": None,
        "match_mode": None,
        "demand_qty": None,
        "entities": [],
        "entity_op": None,
        "scope_exclusive": None,
        "requested_attributes": [],
        "contains_flyer": None,
        "reference_positions": [],
        "reference_target": None,
        "person_mention": None,
        "is_active": None,
        "document": [],
        "status": None,
        "group_by": None,
        "top_n": None,
        "correction": None,
        "routing": {"suggested_team": None, "suggested_agent": None},
        "escalation": {
            "is_escalation_confirmation": None,
            "escalation_declined": None,
            "company_pick": None,
        },
        "anaphora": {"backward_reference": False},
        "answers_open_question": {"resolved": False, "picks": [], "answer": None},
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Policy fixture (AC-1526): the six (domain, kind) triples the UAC names by name,
# not a DB read - "Policy built from rows: tests seed rows, never patch constants"
# (PLAN "Testing seams"), and the rows here are the in-memory stand-in.
# --------------------------------------------------------------------------- #

TIER_ORDER_FIXTURE: list[str] = ["dealer", "office", "end_user"]


def _domain_row(
    name: str,
    *,
    narrowing: dict[str, str],
    tools: tuple[str, ...] = (),
    reveal_key: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "label": name,
        "intents": [],
        "tools": list(tools),
        "primary_tool": tools[0] if tools else None,
        "escalation_team_code": None,
        "switch_words": [],
        "takes_date_filter": False,
        "reveal_key": reveal_key,
        "supported": True,
        "narrowing": narrowing,
        "ladder": [],
        "sort_order": 0,
    }


POLICY_DOMAIN_ROWS: list[dict[str, Any]] = [
    _domain_row("inventory", narrowing={"product": "list_all"}),
    _domain_row("incoming", narrowing={"product": "narrow_to_code"}),
    _domain_row("purchase_cost", narrowing={"product": "narrow_to_code"}),
    _domain_row("order", narrowing={"customer": "must_narrow_one"}),
    _domain_row("product_attachment", narrowing={"attachment_type": "narrow_by_type"}),
    _domain_row("promotion", narrowing={"tier": "narrow_by_tier"}),
]


def _kind_row(kind: str, *, default_narrowing: str, family_grouping: str | None = None) -> dict[str, Any]:
    row = {
        "kind": kind,
        "resolver_source": kind,
        "did_you_mean": True,
        "default_narrowing": default_narrowing,
        "family_grouping": family_grouping,
        "base_property_words": {} if kind != "product" else {"price": "list_price"},
    }
    return row


POLICY_KIND_ROWS: list[dict[str, Any]] = [
    _kind_row("product", default_narrowing="list_all", family_grouping="base_code"),
    _kind_row("customer", default_narrowing="must_narrow_one", family_grouping="ledger_family"),
    _kind_row("attachment_type", default_narrowing="narrow_by_type"),
    _kind_row("promotion", default_narrowing="optional_filter"),
]


def build_policy():
    """`Policy.from_rows(...)` over the fixture rows above. Imports lazily so importing
    this helper module never itself raises `ModuleNotFoundError` before a test gets to
    assert on it."""
    from app.services.chatbot.turn.policy import Policy

    return Policy.from_rows(
        domains=POLICY_DOMAIN_ROWS, kinds=POLICY_KIND_ROWS, tier_order=TIER_ORDER_FIXTURE
    )
