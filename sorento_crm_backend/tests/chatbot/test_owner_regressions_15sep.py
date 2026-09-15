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
(`TestTheOfferRidesOnABornDisambiguationRoster`, flipped in this same round). R-F (the
picked family's `family_uuids`, NOT `open_question.payload.families` - design revised
15 Sep 2026 per the 2026-08-24 "family outlives the roster" ruling) is tested here at its
two seats, `dialogue/open_question.py::_entity_of` and
`lanes/business/fetch.py::entity_ids_transformer`. R-B is a separate mechanism, tested in
`tests/chatbot/test_outstanding_lane.py`.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot.dialogue import open_question as oq
from app.services.chatbot.lanes.business import fetch as fetch_mod
from app.services.chatbot.lanes.business.gate import run_gate
from app.services.chatbot.head import output_exchange as ox


def _answer(**kw: Any) -> dict[str, Any]:
    return {**ox.NO_OPEN_QUESTION_ANSWER, **kw}


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
    """R-F (coder a1f1112d diagnosis, 15 Sep 2026, design revised same day - NO
    `open_question.payload.families`, per the 2026-08-24 ruling that a family outlives
    the roster): a customer roster row that spans two ledgers - "CHIN CHUN HARDWARE SDN
    BHD (MCH, SRT)" - must fetch BOTH ledgers' uuids when picked. The family travels ON
    the roster ROW and the PICKED ENTITY as `family_uuids` - a row field `gate.run_gate`
    composes (`lanes/business/gate.py:956-966`'s picker-row construction) and
    `dialogue/open_question.py::_entity_of` copies onto the entity it builds for
    `focus.customer`. Neither exists today: `_entity_of` (573-586) builds `{raw, hint,
    canonical_code, uuid, current_message, confident}` and nothing else, so a
    `family_uuids` key on the row is silently dropped at the pick. Two seats, two tests:
    the pick-time copy (`_entity_of`, `dialogue/open_question.py`), and the tool-call
    expansion (`entity_ids_transformer`, `lanes/business/fetch.py`) that has to turn
    `focus.customer.family_uuids` into every uuid the `customer_ids` argument carries -
    today it reads only `e.get("uuid")`, one value per entity."""

    # Real customer uuids (sorento_ai_automation_focus_full): CHIN CHUN HARDWARE SDN BHD
    # - [A/C I] (300-C043) and CHIN CHUN HOMEMART SDN BHD - [CERAMIC] (300-C125), the two
    # ledgers a "(MCH, SRT)"-style multi-company roster row spans. `entity_ids_transformer`
    # is uuid-format-only (`_UUID_RE`, fetch.py:329/504 - it SKIPS any entity whose `uuid`
    # does not match `^[0-9a-f]{8}-...\Z` before any family logic ever runs), so a synthetic
    # id like "uuid-mch" would make test 2 pass for the WRONG reason (both real tests below
    # need genuine uuid4 strings, not a synthetic label).
    ROW_UUID = "060f4eaf-88ca-486a-a203-b0b61eeb9cd8"
    FAMILY_UUID = "13eb525b-985c-44a5-abc4-4be5c7db6cd6"

    def test_a_picked_row_carries_its_family_uuids_onto_the_entity(self) -> None:
        outcome = oq.resolve(
            "customer_pick",
            _answer(resolved=True, picks=[1]),
            [
                {
                    "idx": 1,
                    "label": "CHIN CHUN HARDWARE SDN BHD (MCH, SRT)",
                    "code": "300-C043",
                    "uuid": self.ROW_UUID,
                    "entity_type": "customer",
                    # `gate.run_gate`'s own row field (956-966): every uuid this
                    # roster row's family spans, computed on the ARMING turn.
                    "family_uuids": [self.ROW_UUID, self.FAMILY_UUID],
                }
            ],
            {},
        )

        assert outcome.focus["customer"].get("family_uuids") == [
            self.ROW_UUID,
            self.FAMILY_UUID,
        ], (
            f"_entity_of must copy the row's family_uuids onto the picked entity so "
            f"the report fetches both ledgers, not just the row's own uuid: "
            f"{outcome.focus.get('customer')!r}"
        )

    def test_the_tool_call_expands_family_uuids_into_every_ledger(self) -> None:
        trigger = {
            "tool": "crm_order_management_orders_list",
            "entities": [
                {
                    "entity_type": "customer",
                    "uuid": self.ROW_UUID,
                    "code": "300-C043",
                    "family_uuids": [self.ROW_UUID, self.FAMILY_UUID],
                }
            ],
            "semantic_input": {},
        }

        args = fetch_mod.entity_ids_transformer(trigger)

        # Confirms the entity itself is NOT silently skipped by the uuid-format gate
        # before we ever get to grading the family expansion (the bug this whole round
        # is chasing hides behind a false green exactly this way).
        assert not (args.get("_diagnostics") or {}).get("skipped"), (
            f"the row uuid itself must pass entity_ids_transformer's uuid-format gate: "
            f"{args.get('_diagnostics')!r}"
        )
        assert sorted(args.get("customer_ids") or []) == sorted([self.ROW_UUID, self.FAMILY_UUID]), (
            f"the tool call must carry every ledger the picked row's family spans, "
            f"not only the row's own uuid: {args.get('customer_ids')!r}"
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
