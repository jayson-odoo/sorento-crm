"""Owner-found regressions on the merged head (feat/chatbot-focus, d4ae8203b), 15 Sep 2026.

Coder a1f1112d's diagnosis, from a live capture pair
(nodes/clone-spine-RS/compile-current-state/b56-pick-turn.json,
nodes/sub-miss-suggest-live/miss-suggest-result/ms-14993042.json) plus the console-check
evidence in `documentation/plans/chatbot/evidence/focus-l1/console-check-merged-d4ae8203b.md`.

R-C/R-D/R-E are one defect (the pick seam), tested here at the two seats it actually lives
in: the ARMING side (`gate.run_gate`'s `require_specific` narrowing, `opt_uuids` at
`lanes/business/gate.py:753-754`, which the pick's own KEEP mechanism depends on -
`_keep_beside`'s own docstring in `tail/compile_state.py` already documents this as the
reason `keep` comes back empty on every `require_specific` turn today) and the CUSTOMER-PICK
side (`dialogue/open_question.py::_customer_pick` ignoring `payload.keep` and
`_entity_of`'s `raw`/`canonical_code` swap - see `tests/chatbot/test_open_question.py`,
flipped in this same round). R-A is tested in `tests/chatbot/test_sticky_roster_tail.py`
(`TestTheOfferRidesOnABornDisambiguationRoster`, flipped in this same round). R-B and R-F
are separate mechanisms, tested here and in `tests/chatbot/test_outstanding_lane.py`.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot.lanes.business.gate import run_gate
from tests.chatbot.test_tail_units import _compile, _ctx


def _ambiguous_product_matches(*codes: str) -> list[dict[str, Any]]:
    return [
        {
            "uuid": f"uuid-{code}",
            "entity_type": "product",
            "canonical_code": code,
            "match_tier": "trgm",
            "company_name": "Sorento",
        }
        for code in codes
    ]


class TestRCTheArmingSideFreezesCoResolvedSiblings:
    """`_keep_beside` (`tail/compile_state.py:439-466`) subtracts the picker's own
    candidates from `gate.compatible_entities` - the rule is right, but `gate.run_gate`'s
    OWN `require_specific` narrowing (`opt_uuids`, lines 753-754) has already thrown away
    everything that is not one of the picker's own candidates by the time `_keep_beside`
    runs, so "already resolved" and "on offer" read as the same set and the subtraction
    leaves nothing - exactly what the docstring says happens "today", stated as a fact
    about the current code rather than a fixed one. These two tests exercise `run_gate`
    directly and prove the co-resolved sibling is gone from `compatible_entities` before
    `_keep_beside` (or `miss_suggest._attach_question`'s identical construction) ever sees
    it - the seat coder a1f1112d's fix has to close.
    """

    def test_a_co_resolved_product_survives_the_customers_own_picker(self) -> None:
        """"delivery for chin chun product wc286": "chin chun" is ambiguous (several
        real customer accounts), "wc286" resolves to exactly one product. The customer
        picker's narrowing must not drop the product a `customer_pick` roster is
        entitled to `keep` beside it."""
        resolver = {
            "tokens": ["chin chun", "wc286"],
            "resolutions": [
                {
                    "token": "chin chun",
                    "resolved": False,
                    "matches": [
                        {
                            "uuid": "cust-1",
                            "entity_type": "customer",
                            "canonical_code": "300-C043",
                            "match_tier": "trgm",
                            "company_name": "Sorento",
                        },
                        {
                            "uuid": "cust-2",
                            "entity_type": "customer",
                            "canonical_code": "300-C044",
                            "match_tier": "trgm",
                            "company_name": "Sorento",
                        },
                    ],
                },
                {
                    "token": "wc286",
                    "resolved": True,
                    "matches": [
                        {
                            "uuid": "prod-wc286",
                            "entity_type": "product",
                            "canonical_code": "WC286",
                            "match_tier": "exact",
                            "company_name": "Sorento",
                        }
                    ],
                },
            ],
            "unresolved_tokens": [],
        }
        parser = {
            "domain_hint": "order",
            "entities": [
                {"hint": "customer", "raw": "chin chun", "current_message": True},
                {"hint": "product", "raw": "wc286", "current_message": True},
            ],
        }

        out = run_gate(dict(resolver), parser=parser, resolver=resolver)

        assert out["require_specific"] is True
        compat_types = {e["entity_type"] for e in out["compatible_entities"]}
        assert "product" in compat_types, (
            f"gate.py:753-754 narrows compatible_entities to the picker's own "
            f"candidate uuids (the ambiguous customer's), dropping the co-resolved "
            f"product the pick's payload.keep is meant to freeze: "
            f"{out['compatible_entities']!r}"
        )

    def test_a_co_resolved_attachment_type_survives_the_products_own_picker(self) -> None:
        """"photo for srtwc286": "srtwc286" is a real family (several real SKUs),
        "photo" resolves to exactly one attachment type. Picking a product off the
        10-row picker must not drop the attachment type the SAME message named - the
        live defect: picking "4" (SRTWC286-SH) re-asked "Please provide the attachment
        type" instead of answering with the photo."""
        resolver = {
            "tokens": ["srtwc286", "photo"],
            "resolutions": [
                {
                    "token": "srtwc286",
                    "resolved": False,
                    "matches": _ambiguous_product_matches(
                        "SRTWC286-SH", "SRTWC286-SH-P", "SRTWC286-SH-200"
                    ),
                },
                {
                    "token": "photo",
                    "resolved": True,
                    "matches": [
                        {
                            "uuid": "attach-photo",
                            "entity_type": "attachment_type",
                            "canonical_code": "Product Photos",
                            "match_tier": "exact",
                            "company_name": None,
                        }
                    ],
                },
            ],
            "unresolved_tokens": [],
        }
        parser = {
            "domain_hint": "product_attachment",
            "entities": [
                {"hint": "product", "raw": "srtwc286", "current_message": True},
                {"hint": "attachment_type", "raw": "photo", "current_message": True},
            ],
        }

        out = run_gate(dict(resolver), parser=parser, resolver=resolver)

        assert out["require_specific"] is True
        compat_types = {e["entity_type"] for e in out["compatible_entities"]}
        assert "attachment_type" in compat_types, (
            f"gate.py:753-754 narrows compatible_entities to the picker's own "
            f"candidate uuids (the ambiguous product's), dropping the co-resolved "
            f"attachment type - there is no focus axis for it, so `payload.keep` is "
            f"the only channel that carries it forward to the pick turn: "
            f"{out['compatible_entities']!r}"
        )


class TestRFAPickedMultiLedgerRowKeepsEveryLedger:
    """R-F (coder a1f1112d diagnosis, same round): a customer roster row that spans two
    ledgers - "CHIN CHUN HARDWARE SDN BHD (MCH, SRT)" - must fetch BOTH ledgers' uuids
    when picked. `gate.run_gate` already computes the per-row family map
    (`out["picker_families"]`, `cust_families` in `lanes/business/gate.py`) on the
    ARMING turn, but `tail/compile_state.py:1593`'s five-key projection
    (`output["variables"] = {key: variables.get(key) for key in SESSION_VAR_KEYS}`) drops
    ANY key that is not one of the five, and `picker_families` is not one of them - so by
    the pick turn, `variables.picker_families` is always empty and the family-widening
    block in `gate.py` (~line 1011, `if all_present: ... fam_mem = variables.get(
    "picker_families")`) never has anything to read. The fix moves the family map onto
    `open_question.payload.families` (a key `open_question`, one of the five, already
    carries) instead. This test proves the projection drops it today, at the seat that
    actually drops it - `compile_current_state`'s own five-key wall - rather than
    guessing at gate.py's read-back side, which a fix would rewire onto a different key
    entirely."""

    def test_the_family_map_a_picker_turn_computes_does_not_survive_the_five_key_wall(
        self,
    ) -> None:
        codes = ["CHIN CHUN HARDWARE SDN BHD (MCH, SRT)"]
        ctx = _ctx(
            message_type="business_query",
            domain_hint="order",
            intent_hint="check_order",
        )
        ctx["parse"]["_turn_no"] = 1
        item = {
            "outcome": {
                "central-exchange": {
                    "require_specific": True,
                    "compatible_entities": [
                        {"uuid": "uuid-mch-srt", "entity_type": "customer", "code": codes[0]}
                    ],
                    # `gate.run_gate`'s own output key, computed on this arming turn -
                    # the per-row family map the pick turn needs to widen to both
                    # ledgers.
                    "picker_families": {
                        "chin chun hardware": ["uuid-mch", "uuid-srt"],
                    },
                }
            }
        }

        result = _compile(item, ctx)

        variables = result["variables"]
        assert "picker_families" not in variables, (
            "AC-1001's five-key wall: no key outside SESSION_VAR_KEYS should even be "
            "attempted here - if this now fails because picker_families started "
            "surviving as a TOP-LEVEL key, that is still the wrong seat (see the fix "
            "direction in this test's own docstring)"
        )
        open_question = variables.get("open_question") or {}
        payload = open_question.get("payload") or {}
        assert payload.get("families"), (
            f"the family map must ride open_question.payload.families - one of the "
            f"five keys that survives the wall - so the pick turn can widen "
            f"'CHIN CHUN HARDWARE SDN BHD (MCH, SRT)' to both uuid-mch and uuid-srt "
            f"instead of the one row it was pinned to: open_question={open_question!r}"
        )


def test_every_class_in_this_file_names_the_coder_diagnosis() -> None:
    """A cheap guard against this file's own bit-rot: every class here traces to the
    15 Sep coder a1f1112d diagnosis by name, so a reader can find the source of truth."""
    import inspect
    import sys

    module = sys.modules[__name__]
    classes = [
        obj
        for name, obj in vars(module).items()
        if inspect.isclass(obj) and name.startswith("Test")
    ]
    assert classes, "this file defines no test classes"
    for cls in classes:
        assert cls.__doc__ and "a1f1112d" in cls.__doc__, (
            f"{cls.__name__} does not cite the coder diagnosis it comes from"
        )
