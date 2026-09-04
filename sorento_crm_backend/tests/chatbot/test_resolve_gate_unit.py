"""S6a unit + contract tests: the parts no capture can grade (AC-601, AC-602, AC-603).

The 254-case replay in `test_replay.py` is the real parity gate. This file covers the four
things it cannot:

* **the two output keys the SHIPPING body added after every capture was taken** -
  `specific_options` and `tier_pick_domain` (see `_corpus.CAPTURE_BODY_ADDITIONS`). They
  are stripped before the replay compares, so without these tests they would be untested;
* **the `access_ask` exit**, which has ZERO captures in any slug;
* **H16** (AC-603): only the VALUES of `by_entity_type` are data;
* **H46**: `_isTimeline` CONTAINS the sentinel, it is not equality.

Nothing here touches a database, the network or an LLM.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.chatbot import contracts
from app.services.chatbot.lanes import business
from app.services.chatbot.lanes.business import pickers, resolve_gate
from app.services.chatbot.lanes.business.gate import run_gate
from app.services.chatbot.lanes.business.services import ResolveGateServices
from app.services.chatbot.lanes.business.tier_gate import tier_gate


def _match(uuid: str, code: str, *, company: str, tier: str = "exact") -> dict[str, Any]:
    return {
        "uuid": uuid,
        "entity_type": "product",
        "canonical_code": code,
        "match_tier": tier,
        "company_name": company,
    }


def _ambiguous_resolver(matches: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tokens": ["abc"],
        "resolutions": [{"token": "abc", "resolved": False, "matches": matches}],
        "unresolved_tokens": [],
    }


def _parser(domain: str) -> dict[str, Any]:
    return {
        "domain_hint": domain,
        "entities": [
            {"hint": "product", "raw": "abc", "current_message": True},
            {"hint": "attachment_type", "raw": "certificate", "canonical_code": "certificate"},
        ],
    }


class TestSpecificOptions:
    """RS-9 Fix 5: the picker's render order, exposed so line N maps to candidate N."""

    def test_it_is_always_emitted_even_when_nothing_is_ambiguous(self) -> None:
        out = run_gate({}, parser={"domain_hint": "forms", "entities": []}, resolver={})
        assert out["specific_options"] == [], (
            "the key is emitted on EVERY turn - a reader that has to tell absent from "
            "empty is a reader that will get it wrong"
        )

    def test_it_holds_the_candidates_in_the_order_the_lines_were_numbered(self) -> None:
        resolver = _ambiguous_resolver(
            [_match("u1", "ABC-1", company="Sorento"), _match("u2", "ABC-2", company="Mocha")]
        )
        out = run_gate(dict(resolver), parser=_parser("product_attachment"), resolver=resolver)
        assert out["require_specific"] is True
        labels = [c["label"] for o in out["specific_options"] for c in o["candidates"]]
        numbered = out["gate_clarification"].split("\n")[-len(labels) :]
        assert numbered == [f"{i + 1}. {label}" for i, label in enumerate(labels)]
        assert [c["company"] for o in out["specific_options"] for c in o["candidates"]] == [
            "Sorento",
            "Mocha",
        ]

    def test_f16_suffixes_only_the_duplicated_code_and_only_on_product_attachment(self) -> None:
        """A same-code cross-company twin is two lines identical apart from their number.

        F16 appends the company to ONLY those lines, and ONLY on `product_attachment`:
        `incoming`'s annotator re-joins the rendered lines to its probe BY EXACT CODE TEXT,
        so a suffixed line would miss that set and render a confident FALSE "- no incoming".
        """
        matches = [
            _match("u1", "ABC-1", company="Sorento"),
            _match("u2", "ABC-1", company="Mocha"),
            _match("u3", "ABC-2", company="Sorento"),
        ]
        attachment = run_gate(
            dict(_ambiguous_resolver(matches)),
            parser=_parser("product_attachment"),
            resolver=_ambiguous_resolver(matches),
        )
        labels = [c["label"] for o in attachment["specific_options"] for c in o["candidates"]]
        assert labels == ["ABC-1 (Sorento)", "ABC-1 (Mocha)", "ABC-2"]

        incoming_parser = {
            "domain_hint": "incoming",
            "entities": [{"hint": "product", "raw": "abc", "current_message": True}],
        }
        incoming = run_gate(
            dict(_ambiguous_resolver(matches)),
            parser=incoming_parser,
            resolver=_ambiguous_resolver(matches),
        )
        incoming_labels = [c["label"] for o in incoming["specific_options"] for c in o["candidates"]]
        assert incoming_labels == ["ABC-1", "ABC-1", "ABC-2"], (
            "the incoming picker's lines must stay byte-equal to the codes its probe "
            "matches on"
        )


class TestTierPickStamps:
    """RS-9 Fix 6 / Fix 8: the tier-menu re-pick, and the domain it forwards."""

    ENTITLED = {"name": ["Sorento Dealer", "Sorento Office", "End User"]}

    def test_a_valid_pick_overrides_whatever_the_parser_carried(self) -> None:
        out = tier_gate(
            dict(self.ENTITLED),
            parser={"domain_hint": "promotion", "access_levels": ["dealer"]},
            item={"tier_pick": "office", "tier_pick_domain": "promotion"},
        )
        assert out["tier_stated"] == ["office"]
        assert out["tier_ask"] is False
        assert out["tier_pick_domain"] == "promotion"

    def test_an_out_of_range_pick_forces_the_reprompt_on_any_domain(self) -> None:
        out = tier_gate(
            dict(self.ENTITLED),
            parser={"domain_hint": None, "access_levels": ["dealer"], "_pending_pick": True},
            item={"tier_pick_invalid": True},
        )
        assert out["tier_stated"] == []
        assert out["tier_ask"] is True, (
            "an out-of-range TIER pick must reach the reprompt even on a bare digit that "
            "states no domain and even when the parser resolved a PROMO-ROW pick"
        )

    def test_tier_pick_domain_is_null_when_nothing_stamped_it(self) -> None:
        out = tier_gate(dict(self.ENTITLED), parser={"domain_hint": "promotion"}, item=None)
        assert out["tier_pick_domain"] is None


class TestAccessAskExit:
    """The one exit arm with ZERO captures, in any slug."""

    def _services(self, names: list[str]) -> ResolveGateServices:
        def _resolve(_body: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("resolve-entity must not run when If4 takes its FALSE leg")

        return ResolveGateServices(
            access_types=lambda **_: [{"name": n} for n in names],
            resolve_entity=_resolve,
            probe=lambda **_: None,
        )

    def _ctx(self) -> dict[str, Any]:
        return {
            "contact": {"id": "c1"},
            "parse": {"output": {"domain_hint": "promotion", "entities": []}},
            "session": {},
        }

    def test_zero_entitlement_exits_access_ask_carrying_tier_gate(self) -> None:
        out = resolve_gate.run(
            self._ctx(), "access_check", {}, services=self._services([])
        )
        assert out["_exit_kind"] == "access_ask"
        assert out["tier_proceed"] is False
        assert out["aggregate"] == {"name": []}
        assert out["tier_gate"]["entitled_tiers"] == []
        # The three the gate never reached stay NULL, which is what n8n's presence gates read.
        assert out["resolved"] is None
        assert out["gate"] is None
        assert out["ctx_resolved"] is None
        assert out["annotate_incoming"] is None

    def test_an_entitled_contact_goes_on_to_resolve_entity(self) -> None:
        services = ResolveGateServices(
            access_types=lambda **_: [{"name": "Sorento Dealer"}],
            resolve_entity=lambda _body: {"tokens": [], "resolutions": [], "unresolved_tokens": []},
            probe=lambda **_: None,
        )
        out = resolve_gate.run(self._ctx(), "access_check", {}, services=services)
        assert out["_exit_kind"] != "access_ask"
        assert out["aggregate"] == {"name": ["Sorento Dealer"]}
        assert out["resolved"] is not None


class TestByEntityTypeKeysAreNeverData:
    """AC-603 / H16: only the VALUES of `by_entity_type` are rows."""

    def test_a_metadata_key_never_reaches_a_customer_facing_string(self) -> None:
        resolver = {
            "match_mode": "and",
            "tokens": ["abc"],
            "intersection": None,
            "by_entity_type": {
                "product": [_match("u1", "ABC-1", company="Sorento")],
                # A key that is METADATA, not an entity type. n8n renders `by_entity_type`
                # to customers elsewhere, and a reader that iterated KEYS would print it.
                "_result_total": 7,
            },
            "unresolved_tokens": [],
        }
        out = run_gate(dict(resolver), parser=_parser("incoming"), resolver=resolver)
        rendered = "\n".join(
            [
                str(out.get("gate_clarification") or ""),
                str(out.get("gate_reason") or ""),
                str(out.get("access_notice") or ""),
            ]
        )
        assert "_result_total" not in rendered
        assert all(e.get("entity_type") != "_result_total" for e in out["compatible_entities"])
        assert all(
            "_result_total" not in str(c.get("label"))
            for o in out["specific_options"]
            for c in o["candidates"]
        )

    def test_the_non_array_value_is_flattened_the_way_javascript_does(self) -> None:
        """`Object.values(x).flat()` passes a non-array value THROUGH, it does not drop it.

        Reproduced rather than tidied: dropping it would be a silent narrowing, and the
        row it lets through is discarded one line later for having no `uuid` anyway.
        """
        from app.services.chatbot.lanes.business.gate import _flatten_by_entity_type

        assert _flatten_by_entity_type({"product": [1, 2], "_meta": 7}) == [1, 2, 7]
        assert _flatten_by_entity_type(None) == []


class TestTimelineSentinel:
    """H46: `_isTimeline` is `.some(k === '__all__')` - CONTAINS, not equals."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (["__all__"], True),
            # The case an earlier mutation test could not falsify, and the reason the
            # guard reading it is load-bearing rather than belt-and-braces.
            (["__all__", "gatepass_date"], True),
            (["gatepass_date", "__all__"], True),
            ([" __all__ "], True),
            (["gatepass_date"], False),
            ([], False),
            ([None], False),
            (None, False),
            ("__all__", False),
        ],
    )
    def test_contains_the_sentinel(self, value: Any, expected: bool) -> None:
        assert contracts.is_timeline(value) is expected


class TestPickerProbeArms:
    """A probe that did not run must never read as a probe that found nothing."""

    GATE = {"gate_clarification": "Which customer do you mean? Please choose:\n1. ACME SDN BHD"}

    def test_an_unavailable_probe_renders_the_bare_picker(self) -> None:
        out = pickers.annotate_customer(dict(self.GATE), probe=None, parser={})
        assert out["escalate_message"] == self.GATE["gate_clarification"]
        assert out["customer_probe_hits"] is None
        assert out["customer_probe_skip_reason"] == "probe_unavailable"

    def test_a_saturated_page_renders_the_bare_picker(self) -> None:
        rows = [{"customer_name": "ACME SDN BHD"}] * pickers.PAGE_SATURATION
        out = pickers.annotate_customer(dict(self.GATE), probe={"answers": rows}, parser={})
        assert out["escalate_message"] == self.GATE["gate_clarification"]
        assert out["customer_probe_skip_reason"] == "page_saturated"

    def test_a_defaulted_window_bounds_the_miss_claim(self) -> None:
        out = pickers.annotate_customer(dict(self.GATE), probe={"answers": []}, parser={})
        assert out["customer_probe_window_days"] == 90
        assert out["escalate_message"].endswith("None of these have a recent delivery.")
        assert " - no recent delivery" in out["escalate_message"]

    def test_a_customer_dated_window_makes_the_plain_claim(self) -> None:
        out = pickers.annotate_customer(
            dict(self.GATE), probe={"answers": []}, parser={"date_filter_start": "2026-01-01"}
        )
        assert out["customer_probe_window_days"] is None
        assert out["escalate_message"].endswith("None of these have a matching delivery.")

    def test_the_incoming_picker_keeps_the_numbering_and_the_order(self) -> None:
        gate = {"gate_clarification": "Choose:\n1. AAA-1\n2. BBB-2"}
        out = pickers.annotate_incoming(gate, probe={"answers": [{"title": "aaa-1"}]})
        assert out["escalate_message"] == "Choose:\n1. AAA-1 - has incoming\n2. BBB-2 - no incoming"
        assert out["is_clarification"] is False


class TestDelegateSeam:
    """The three arms that reach the sub, and the one Set node on one of their edges."""

    def test_only_the_three_business_arms_enter_the_lane(self) -> None:
        assert set(business.ENTRY_BY_BRANCH_KIND) == {
            "check_promotion",
            "stock_denied",
            "business_query",
        }
        assert business.handles("business_query") is True
        assert business.handles("out_of_scope") is False
        assert business.handles(None) is False

    def test_check_promotion_enters_at_access_check_and_the_others_at_resolve(self) -> None:
        assert business.ENTRY_BY_BRANCH_KIND["check_promotion"] == "access_check"
        assert business.ENTRY_BY_BRANCH_KIND["stock_denied"] == "resolve"
        assert business.ENTRY_BY_BRANCH_KIND["business_query"] == "resolve"

    def test_the_stock_denied_edge_carries_edit_fields2s_one_field(self) -> None:
        seen: dict[str, Any] = {}

        def _resolve(_body: dict[str, Any]) -> dict[str, Any]:
            return {"tokens": [], "resolutions": [], "unresolved_tokens": []}

        services = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=_resolve, probe=lambda **_: None
        )
        ctx = {"contact": {"id": "c1"}, "parse": {"output": {"entities": []}}, "session": {}}
        original = {"branch_kind": "stock_denied"}
        fragment = business.run_until_exit(
            ctx, original, branch_kind="stock_denied", services=services
        )
        assert fragment["delegate"] == "business_query"
        assert fragment["payload"]["_exit_kind"] in contracts.EXIT_KINDS
        assert original == {"branch_kind": "stock_denied"}, "the router's item is not mutated"
        assert seen == {}

    def test_every_exit_carries_the_six_contract_fields_and_a_declared_kind(self) -> None:
        """`sub-main-processing`'s presence gates read these SIX keys by name.

        A missing key is not a missing field: it is a stand-in node that silently stops
        executing, and every by-name reader downstream of it throwing. So the arm must emit
        all six on every exit, `None` included, and `_exit_kind` must be one of the four
        `resolve-arm` tests for.
        """
        assert contracts.EXIT_KINDS == ("continue", "access_ask", "not_found", "offer")
        for kind in contracts.EXIT_KINDS:
            item = resolve_gate.exit_item({"carried": 1}, exit_kind=kind, fields={})
            assert item["_exit_kind"] == kind
            assert item["carried"] == 1
            for field in contracts.EXIT_CONTRACT_FIELDS:
                assert field in item and item[field] is None
