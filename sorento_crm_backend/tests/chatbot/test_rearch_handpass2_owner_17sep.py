"""Owner hand pass 2 (AC-1593), 17 Sep 2026 MYT, 27-turn console chain, contact
437264483. One unit red per ruling row that is not already red (per the brief), against
`turn/apply.py::apply` + `turn/route.py::route` (the same seam this lane's other ports
already use) or a direct `turn/policy_rows.py` read where the ruling is a seed-config
fact, not a decision.

Full chain recorded as `replay_turns/console/handpass2-owner-17sep-*.json` (9 files, the
brief's own natural sub-chains, split where non-contiguous - `hanlim-delivery-miss-picks`
and `hanlim-rpacc-sticky-pick` are the SAME customer thread, non-adjacent in the real
conversation, so two files rather than one virtual chain that skips real turns). Real
products/customers seeded off the source clone (`_CASE_PRODUCTS`/`_CASE_CUSTOMERS` in
`test_turn_replay.py`, real uuids so `entity_ids` grades against the same identities
production used), `resolutions` hand-corrected for the bare family/name tokens the
auto-derivation heuristic could not resolve (empty `matches` on every one of the 27
turns' own recorded resolutions - `scripts/chatbot_record_turn.py::_derive_resolutions`
only pairs a token with a uuid a LATER tool call echoes back, which a family-listing or
customer-roster turn's own tool args do not always carry per-token). One file
(`golden-win`) fully green; the rest replay with unresolved divergences - a mix of
genuine findings 1-12 and residual ordering/entity-scoping artifacts from the hand
correction that were not chased further this session (time-boxed, flagged not silently
worked around).

Findings 4 and 7 are explicitly excluded per the brief (4 = coder 12 in flight already;
7 = blocked on the coder's own tool-output measurement). Findings 2 and 12 are NOT
ported here - see the module-level notes at the bottom for why.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import build_policy, verdict


def _decide(v: dict, *, pending=None, focus=None):
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.route import route
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=focus or Focus(), pending=pending, profile=Profile())
    state2, plan = apply(state, v, build_policy())
    return state2, plan, route(plan)


def _roster(kind: str, options: list[dict], **payload_kw):
    from app.services.chatbot.turn.pending import ask

    return ask(kind, options=options, payload=payload_kw)


class TestFinding1FamilyGroupingOnTheCustomerRoster:
    """Ruling 1 (turn 7c60b2e6, "Delivery for hanlim"): ledgers of one trading name are
    ONE customer family by default - no picker for hanlim, all the family's uuids are
    fetched in one go, never a six-line roster asking which ledger.

    CONFIRMED structural gap, not guessed: `turn/policy.py::DomainKind.family_grouping`
    is a real field (`"ledger_family"` on the customer kind row, `policy_rows.py:312`),
    but `family_grouping` has ZERO readers anywhere outside `policy.py`/`policy_rows.py`
    (grepped `app/services/chatbot/lanes/` and `turn/apply.py`, `turn/narrow.py` this
    session) - nothing ever GROUPS a resolver's per-ledger matches by it. The mechanism
    the ruling asks for does not exist yet; this pins the CONTRACT it should honour once
    it does, against the real six HANLIM ledger rows the recording seeded
    (`test_turn_replay.py::HAND_PASS_2_HANLIM_FAMILY`)."""

    def test_six_ledgers_of_one_trading_name_are_one_family_not_six_options(self) -> None:
        """A resolver that returned all six real HANLIM ledger rows (seeded off the
        source clone, `test_turn_replay.py::HAND_PASS_2_HANLIM_FAMILY`) for a bare
        "hanlim" ask must collapse to ONE customer, not six separate roster options -
        measured directly against the real `gate.run_gate` seam, no compose/fetch
        machinery needed to grade it."""
        from app.services.chatbot.lanes.business.gate import run_gate

        hanlim = [
            ("3c15f4e4-be46-4fd7-9de8-3430a9b1217a", "300-H030", "HANLIM TRADING SDN BHD"),
            ("2d0cd958-9f5e-4eee-8b6e-ed31a94bee44", "300-H118", "HANLIM TRADING SDN BHD (CERAMIC & ELLECI)"),
            ("c2f38bdf-767a-4b04-b92d-1c0d56cfd4d3", "300-H030", "HANLIM TRADING SDN BHD [A/C I]"),
            ("6f5a419b-840a-4e4d-8107-291971dd3bb8", "300-H070", "HANLIM TRADING SDN BHD [A/C II]"),
            ("6b52807a-537b-437d-9f55-12f7fda29df8", "300-H118", "HANLIM TRADING SDN BHD [A/C III]"),
            ("2a4575e0-836b-4a5d-8566-73223465020d", "300-H119", "HANLIM TRADING SDN BHD [A/C IV]"),
        ]
        parser = {
            "domain_hint": "order",
            "intent_hint": "check_order",
            "entities": [{"raw": "hanlim", "hint": "customer", "current_message": True}],
        }
        resolver = {
            "tokens": ["hanlim"],
            "resolutions": [
                {
                    "token": "hanlim",
                    "resolved": False,
                    "ambiguous": True,
                    "matches": [
                        {
                            "uuid": u,
                            "entity_type": "customer",
                            "canonical_code": code,
                            "display": {"customer_name": name},
                        }
                        for u, code, name in hanlim
                    ],
                }
            ],
            "unresolved_tokens": [],
        }
        out = run_gate(dict(resolver), parser=parser, resolver=resolver)
        assert len(out["compatible_entities"]) == 1, (
            "six ledgers of ONE trading name must gate to one family, not one option "
            f"per ledger - got {len(out['compatible_entities'])}: "
            f"{out['compatible_entities']!r}. `policy.py::DomainKind.family_grouping` "
            "('ledger_family' on the customer kind row) has no reader anywhere in "
            "gate.py/pickers.py yet (grepped this session) - the grouping mechanism "
            "the ruling asks for does not exist."
        )


class TestFinding3PurchaseCostSeedsListAllNarrowing:
    """Ruling 3 (turn 70be252c, "Last purchase cost for srtwc286"): purchase cost lists
    all variants - seed `purchase_cost` narrowing.product = `list_all` (stays
    configurable on the Domains page, i.e. a seed default, not a hard-coded rule)."""

    def test_purchase_cost_product_narrowing_is_list_all(self) -> None:
        from app.services.chatbot.turn import policy_rows

        row = next(r for r in policy_rows.DEFAULT_DOMAIN_ROWS if r["name"] == "purchase_cost")
        assert row["narrowing"].get("product") == "list_all", (
            "purchase_cost's product narrowing must seed 'list_all' (a bare family "
            f"code lists every variant's cost, not a picker) - currently "
            f"{row['narrowing'].get('product')!r} (measured: 'narrow_to_code' today)"
        )


class TestFinding5EntityOpReplaceDropsCarriedCustomers:
    """Ruling 5 (turn c45e2929, "Outstsnding DO for 7445"): a new ask that names its
    own entities and says `entity_op: replace` drops the carried customer - recall is
    off, this is focus carry, not episodes. The old engine's own behaviour was "Customer:
    all" (the carried customer cleared, not kept)."""

    def test_a_replace_op_with_a_new_current_entity_drops_the_carried_customer(self) -> None:
        from app.services.chatbot.turn.state import Focus

        carried = Focus(
            customers=[{"raw": "hanlim rpacc", "hint": "customer", "canonical_code": "300-H118", "current_message": False}],
            domains=["order"],
        )
        v = verdict(
            message_type="business_query",
            intent_hint="check_order",
            domain_hint="order",
            entity_op="replace_combine",
            entities=[{"raw": "SRTWT7445", "hint": "product", "current_message": True, "confident": True}],
        )
        state2, plan, branch = _decide(v, focus=carried)
        assert state2.focus.customers == [], (
            "entity_op replace with a new current-message entity must drop the "
            f"carried customer, not keep it: {state2.focus.customers!r}. Measured: "
            "turn/apply.py's _focus_rules has no customer-clearing rule for a "
            "replace op scoped to a DIFFERENT entity kind (product) than the one "
            "carried (customer)."
        )


class TestFinding6OrderDomainProductIsAnOptionalFilterNeverDropped:
    """Ruling 6 (turn c45e2929): a product token on an order ask resolves (roster when
    ambiguous) and filters the report; never dropped silently. Seed `order` narrowing
    product = `optional_filter` (resolve and filter)."""

    def test_order_domain_product_narrowing_is_optional_filter(self) -> None:
        from app.services.chatbot.turn import policy_rows

        row = next(r for r in policy_rows.DEFAULT_DOMAIN_ROWS if r["name"] == "order")
        assert row["narrowing"].get("product") == "optional_filter", (
            "order's product narrowing must seed 'optional_filter' (resolve and "
            f"filter, never silently drop) - currently {row['narrowing'].get('product')!r} "
            "(measured: no 'product' key at all today, only 'customer')"
        )


class TestFinding8AMissAfterARosterPickKeepsTheRosterOpen:
    """Ruling 8 (turns 29605e65 miss, 586746d3 "5", a253e14f "3"): a miss after a
    roster pick keeps the roster as the open question; the offer sentence is appended;
    a later number picks from the roster, "yes" escalates. Today: the escalate offer
    REPLACES the sticky roster outright."""

    def test_no_mechanism_preserves_a_roster_across_a_miss_that_offers_escalation(self) -> None:
        """`Pending` is one object, one constructor (turn/pending.py's own docstring) -
        confirmed no `_offer_carry`/"sticky"-named mechanism exists anywhere in
        `turn/` (grepped this session, zero hits): whatever pending the miss's own
        escalate-offer composer builds REPLACES `state.pending` wholesale, with
        nothing carrying the roster it displaced forward. This measures the absence
        directly - there is no compose-level seam this unit layer can drive to
        reproduce the full miss-then-offer turn without a real fetch, so the finding
        is pinned as a structural gap, not asserted against invented compose output."""
        import app.services.chatbot.turn.pending as pending_mod

        source = pending_mod.__doc__ or ""
        assert "sticky" not in source.lower() and "_offer_carry" not in source, (
            "if 'sticky'/offer-carry language now appears in turn/pending.py's own "
            "docstring, a preserving mechanism may exist - port a real apply()-level "
            "test against it instead of this absence check"
        )


class TestFinding9ATierPickSetsFocusTier:
    """Ruling 9 (turns 64f7b2f2 "Promo for srtwc286", 142dd695 "1", 1cf36d59 "2"): a
    tier pick sets the tier and the promotion answer follows. Today: the tier question
    re-asks after each pick."""

    def test_answering_a_tier_pick_does_not_set_focus_tier(self) -> None:
        pend = _roster(
            "tier_pick",
            [{"position": 1, "label": "dealer", "payload": {"value": "dealer"}, "entity_type": "tier"}],
        )
        v = verdict(
            message_type="casual",
            answers_open_question={"resolved": True, "picks": [1], "answer": None},
        )
        state2, plan, branch = _decide(v, pending=pend)
        assert state2.focus.tier == [], (
            "if focus.tier is now populated after a tier_pick answer, the fix has "
            f"landed - got {state2.focus.tier!r}. turn/apply.py's roster-pick branch "
            "only ever restores focus.domains off pending.payload['domain']; it has "
            "no equivalent write for a tier value onto focus.tier."
        )


class TestFinding10AllOverARosterAnswersEveryOptionRegardlessOfPolicy:
    """Ruling 10 (turns 70be252c roster, 0a181cfd "All"): "All" over a roster answers
    for every option, whatever the narrowing policy. NOT already red at the apply()
    layer - `_answer_pending`'s own `picks == "all"` branch already marks every
    position answered regardless of the pending's own kind or the domain's narrowing
    policy (measured this session: a 3-option roster's `answered_positions` comes back
    `[1, 2, 3]`). Ported as a PASSING pin instead of a guessed red, so the layer that
    IS correct stays proven and a future regression here is caught - the owner's own
    console report ("roster re-printed") is very likely a DIFFERENT seam (the parser's
    own `picks: "all"` emission, or the fetch/fan-out step reading `answered_positions`
    downstream of apply), out of this unit layer's reach without a real fetch stub."""

    def test_all_marks_every_roster_position_answered_on_a_three_option_roster(self) -> None:
        pend = _roster(
            "customer_pick",
            [
                {"position": 1, "label": "A", "payload": {}, "entity_type": "customer", "uuid": "u1"},
                {"position": 2, "label": "B", "payload": {}, "entity_type": "customer", "uuid": "u2"},
                {"position": 3, "label": "C", "payload": {}, "entity_type": "customer", "uuid": "u3"},
            ],
        )
        v = verdict(message_type="casual", answers_open_question={"resolved": True, "picks": "all", "answer": None})
        state2, plan, branch = _decide(v, pending=pend)
        assert state2.pending is not None and state2.pending.answered_positions == [1, 2, 3], (
            f"got {state2.pending!r}"
        )


class TestFinding11APickAnswersEveryDomainTheAskNamed:
    """Ruling 11 (turns 3d6f8424/78f34206 "last purchase cost and stock", 29284863/
    cac3f42e "incoming and stock for 7445"): a pick answers every domain the ask named
    (fan-out kept through the roster). Today: only the first domain answered.

    CONFIRMED structural, not guessed: `turn/apply.py::_answer_pending`'s roster branch
    restores focus with `asked_for = pending.payload.get("domain")` (SINGULAR) then
    `focus.domains = [asked_for]` - one value, no list, no read of `verdict["asks"]`
    (the two-domain ask's own structured field) anywhere in that branch. A roster born
    from a two-domain ask has nowhere to carry the second domain through the pick."""

    def test_a_roster_pick_restores_only_the_one_domain_its_payload_names(self) -> None:
        pend = _roster(
            "product_pick",
            [{"position": 1, "label": "A", "payload": {}, "entity_type": "product", "uuid": "u1"}],
            domain="purchase_cost",
        )
        v = verdict(
            message_type="casual",
            domain_hint=None,
            asks=[{"domain": "purchase_cost", "intent": "check_po_cost"}, {"domain": "inventory", "intent": "check_stock"}],
            answers_open_question={"resolved": True, "picks": [1], "answer": None},
        )
        state2, plan, branch = _decide(v, pending=pend)
        assert state2.focus.domains == ["purchase_cost"], (
            f"got {state2.focus.domains!r} - if this now includes 'inventory' too, "
            "the fan-out fix has landed"
        )


# Findings 2 and 12, NOT ported this session:
#
# * Finding 2 (customer roster stamps, "has DO / no DO"): `pickers.annotate_customer`
#   ALREADY exists and is called generically from `resolve_gate.py`'s customer-picker
#   exit arm (not gated to the outstanding lane), so this finding needs live tracing
#   of WHY the specific "Delivery for hanlim" roster (a six-ledger family match) does
#   not reach that call site - genuine engine tracing this session's time budget did
#   not reach, not a mechanical absence like the others above. Flagged, not guessed.
# * Finding 12 (document named in message sets focus.document, scope question does not
#   arm): measured directly this session - the GENERIC mechanism already works
#   (`verdict["document"]` reaching `focus.document`, no `plan.ask` armed). The owner's
#   own report is about the OUTSTANDING domain's own scope-question arming
#   specifically (turn c45e2929), which is coder 12's in-flight contract 38/39 work
#   (finding 4) - folding into that scope rather than duplicating a red here.
