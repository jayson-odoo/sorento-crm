"""Owner console pass 4, item 4 / issue #708 (7 Sep 2026): a numbered pick over a
`suggest_offer` roster (partial miss, `dym_last_result_set` null) drops the already-resolved
code from scope.

"SRTKS6091 and SRTKS8091 got stock": SRTKS6091 resolves, SRTKS8091 misses and gets a sibling
did-you-mean offer; the turn persists `selection_context: suggest_offer` with
`dym_last_result_set` null (the miss is claimed by `build-suggest-offer` before the tail runs,
so `_partial_dym_block` never writes the dym roster - the SAME premise
`tests/chatbot/_shared_turn_helpers.py::TestAPartialDidYouMeanPickReplacesOnlyTheMissingToken` measures
and explicitly declines to grade: "Without [`reference_target: 'dym'`] the STOCK positional arm
resolves the digit over `last_result_set` instead (measured: that arm came back
`replace_combine` with only the pick in scope and the resolved SRTKS6091 dropped - a separate
finding, reported, not graded here)." This file grades exactly that finding, reusing that
class's own seed/wiring by COMPOSITION (a bare instance, not a subclass - importing the class
itself would make pytest collect its test methods a second time under this file, where the
`seeded` fixture it depends on is not in scope).

Reviewer-measured (issue #708): over a `suggest_offer` roster, `reference_target` of `None`,
`"result"` and `"dym"` ALL come back `entity_op: replace_combine` with only the picked code in
scope - `apply_dym_pick` keys on `dym_last_result_set` being PRESENT, so the discriminator is
which roster happens to be in state, not the parser's own tag.

Expected (AC-818's own visible contract, extended to this roster shape): the resolved code
(SRTKS6091) plus the picked code both end up in scope, and the answer names both.
"""
from __future__ import annotations

from tests.chatbot.test_engine import _parser_output
from tests.chatbot._shared_turn_helpers import (
    TestAPartialDidYouMeanPickReplacesOnlyTheMissingToken as _PartialDymChain,
)
from tests.chatbot._shared_turn_helpers import _session_of
from tests.chatbot._shared_turn_helpers import seeded  # noqa: F401 - re-exported fixture

_base = _PartialDymChain()


class TestIssue708ANumberedPickOverASuggestOfferRosterKeepsTheResolvedCode:
    def test_a_bare_numbered_pick_keeps_the_resolved_code_and_the_pick(
        self, seeded, session_factory, monkeypatch
    ):
        _base._seed_scope_and_products(session_factory)
        _base._put_trgm_on_the_search_path(session_factory)
        _base._wire(session_factory, monkeypatch)

        head1 = _base._run(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="business_query",
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[
                    {
                        "raw": _base.RESOLVED,
                        "hint": "product",
                        "canonical_code": None,
                        "current_message": True,
                        "confident": True,
                    },
                    {
                        "raw": _base.MISSING,
                        "hint": "product",
                        "canonical_code": None,
                        "current_message": True,
                        "confident": True,
                    },
                ],
            ),
            text_body=f"{_base.RESOLVED} and {_base.MISSING} got stock",
            msg_id="ZZT-708-t1",
        )
        assert head1.status in ("done", "delegated"), head1.error

        # D8/AC-1013/AC-1033: no `selection_context` / `dym_last_result_set` / top-level
        # `entities` mirror - the offer is one `open_question` slot (`kind: "product_pick"`,
        # AC-1013's `suggest_offer` -> `product_pick` mapping), and the resolved siblings
        # ride `focus.products`, not a bare `variables.entities` list.
        stored = _session_of(session_factory)["variables"]
        open_question = stored.get("open_question") or {}
        assert open_question.get("kind") == "product_pick", open_question
        products = ((stored.get("focus") or {}).get("products") or {}).get("value") or []
        raws = {str(e.get("raw")).upper() for e in products}
        assert {_base.RESOLVED, _base.MISSING} <= raws, raws

        roster = open_question.get("options") or []
        assert roster, f"a numbered pick needs SOME roster to resolve '2' against: {stored!r}"
        position = 2 if len(roster) > 1 else 1
        picked_row = roster[position - 1]
        picked = picked_row.get("code") or picked_row.get("value") or picked_row.get("label")

        # -- turn 2: "2". NO `reference_target: "dym"` tag (the bare shape #708 measures),
        #    and no `dym_last_result_set` seeded - issue #708's exact premise. ISSUE #708:
        #    `open_question.py::_product_pick`'s `payload.keep` is what carries the
        #    already-resolved sibling forward - `dialogue/open_question.py` around line 340.
        head2 = _base._run(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="clarification",
                intent_hint=None,
                domain_hint=None,
                entities=[],
                reference_positions=[position],
                reference_target=None,
            ),
            text_body=str(position),
            msg_id="ZZT-708-t2",
        )
        stored2 = _session_of(session_factory)["variables"]
        products2 = ((stored2.get("focus") or {}).get("products") or {}).get("value") or []
        codes = sorted(str(e.get("canonical_code") or e.get("raw")).upper() for e in products2)
        assert codes == sorted([_base.RESOLVED, str(picked).upper()]), (
            f"the scope must be the already-resolved code PLUS the pick, never the pick "
            f"alone - `payload.keep` must not drop {_base.RESOLVED}: {products2!r}"
        )
        assert head2.branch_kind == "business_query", head2.branch_kind
