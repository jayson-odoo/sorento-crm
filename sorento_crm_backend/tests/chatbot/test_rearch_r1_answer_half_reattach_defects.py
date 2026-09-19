"""R1 - the two pure defects named in `PLAN-chatbot-answer-half-reattach.md` ("The
three live bugs, root causes" table, slice R1) and their UACs
(`chatbot-answer-half-reattach-acceptance-criteria.md` AC-1688, AC-1691, AC-1692).

Written test-FIRST, with no R1 implementation to read - only the plan's own measured
facts and this session's own direct measurement against the CURRENT (unfixed) code at
`turn/narrow.py`, `turn_runtime.py` and `turn/fetch.py`. Every test below is RED today
for the reason its own docstring/assertion message names (measured, not assumed - see
this session's handoff for the exact command and output).

AC-1692: a hyphenated or spaced code the resolver could not place is never offered back
as a roster option - `narrow._token_of` must fold the way `turn_runtime._token_key`
does (the same fold class B1 already fixed at `_entity_token_key`, commit
b32b0a500).

AC-1691: no roster is ever asked with fewer than two options, across every roster
narrowing policy (`narrow._ROSTER_POLICIES`) and both the product and customer entity
kinds. Measured today (see class docstring below): red for BOTH `narrow_to_code` and
`narrow_by_tier` whenever the kind is not `"tier"` - not "`narrow_to_code` only" as the
plan's own table guesses (that guess is explicitly flagged there as unverified). The
shared fallthrough arm at `narrow.py`'s "AC-1526's own wording ... narrow_to_code only
now" comment (around line 437) is reached by ANY roster policy value that is neither
`must_narrow_one` nor `narrow_by_tier` guarded to `kind == "tier"`, which is why
`narrow_by_tier` on a non-tier kind (never seeded that way in production, but the same
code path) shows the identical one-option roster.

AC-1688: a tool never runs unfiltered because its subject did not resolve.
(a) `turn_runtime._answered_unfiltered` must treat a non-empty `unplaced` with an EMPTY
    entity list as "answered unfiltered" (today it returns False for exactly that case -
    see the function's own guard clause `if not entities or not unplaced: return False`).
(b) `turn/fetch.py::_climb` must never run a cross-domain rung when the primary
    `FetchSpec.entities` is empty - today it reuses the SAME (empty) spec for every
    rung via `replace(spec, domain=rung)`, so an unresolved subject's miss climbs the
    ladder and calls the rung's tool with no product filter at all. Parametrized over
    every domain `policy_rows.DEFAULT_DOMAIN_ROWS` actually gives a non-empty `ladder`
    (measured: `inventory` -> `["incoming", "purchase_order"]`, `incoming` ->
    `["inventory", "purchase_order"]` - read off the seed data, not hard-coded).

`case-071`/`case-058` (the outstanding-report exception `_answered_unfiltered`'s own
docstring names) and `test_s6c_answer_lane.py` / `test_replay.py` are NOT touched by
this file.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.chatbot.trace import TurnTrace
from app.services.chatbot.turn import policy_rows
from app.services.chatbot.turn.fetch import run_fetch
from app.services.chatbot.turn.narrow import _ROSTER_POLICIES, _token_of, decide
from app.services.chatbot.turn.plan import FetchSpec, Plan, Trace
from app.services.chatbot.turn.policy import Policy
from app.services.chatbot.turn.state import Focus, KIND_FIELD_MAP, Profile
from app.services.chatbot.turn_runtime import _answered_unfiltered, _token_key

# --------------------------------------------------------------------------- #
# AC-1692: the join fold agrees between narrow.py and turn_runtime.py
# --------------------------------------------------------------------------- #

#: Cases named in the UAC (AC-1692), plus the spaced variant the captain's brief also
#: names ("plus a spaced variant").
_HYPHENATED_OR_SPACED_TOKENS: tuple[str, ...] = (
    "SRTWT165-FT",
    "srtwt7202-new",
    "sttwc286-SH",
    "SRTWT165 FT",
)


class TestTokenFoldAgreesWithTheResolversOwnFold:
    """`narrow.py:386`'s `unplaced` membership test computes `_token_of(c).casefold()`;
    `turn_runtime.unplaced_tokens`/`unplaced` is keyed by `_token_key`, which additionally
    strips `[-\\s]+` (the resolver's OWN `_PRODUCT_FOLD`, B1). The two sides of that join
    must agree for every code that has a hyphen or a space in it - most Sorento codes do."""

    @pytest.mark.parametrize("token", _HYPHENATED_OR_SPACED_TOKENS)
    def test_narrow_token_of_folds_like_turn_runtime_token_key(self, token: str) -> None:
        candidate = {"raw": token, "canonical_code": token}
        narrow_join_key = _token_of(candidate).casefold()
        resolver_key = _token_key(token)
        assert narrow_join_key == resolver_key, (
            f"narrow._token_of({candidate!r}).casefold() == {narrow_join_key!r} but "
            f"turn_runtime._token_key({token!r}) == {resolver_key!r} - narrow.py:386's "
            "unplaced-membership join keys one side WITH the separator and the other "
            "WITHOUT, so it can never match for a hyphenated or spaced code (the same "
            "fold-mismatch class B1 already fixed at _entity_token_key for a different "
            "call site, commit b32b0a500)"
        )


class TestUnplacedHyphenatedOrSpacedCodeNeverOfferedBack:
    """AC-1692's own behavioural half: a candidate the resolver reported unplaced (keyed
    the resolver's OWN way) must never come back out of `narrow.decide` as a roster
    option - the `unplaced_never_offered` guard at narrow.py:381-395 must actually fire.

    Measured today (this session, direct `decide()` call): every one of these four
    tokens comes back as a `product_pick` with ONE option whose label is the customer's
    own typed token verbatim - exactly the F8 "one-option roster echoing the typed
    token" bug (hand pass 8, `SRTWT165-FT CERT` / `Incoming srtwt7202-new` /
    `Technical drawings sttwc286-SH`).
    """

    @pytest.mark.parametrize("token", _HYPHENATED_OR_SPACED_TOKENS)
    def test_unplaced_code_is_never_rostered_back(self, token: str) -> None:
        candidates = [{"raw": token, "canonical_code": token, "hint": "product"}]
        focus = Focus(products=candidates)
        # Keyed the RESOLVER's own way (`turn_runtime._token_key`, folded) - the shape
        # `unplaced_tokens()` actually produces and `apply()` actually passes through as
        # a frozenset of keys (`engine.py`: `unplaced=frozenset(unplaced_tokens)`).
        unplaced = frozenset({_token_key(token)})

        outcome = decide(
            kind="product",
            policy_value="narrow_to_code",
            focus=focus,
            profile=Profile(),
            resolved_candidates=None,
            unplaced=unplaced,
        )

        assert outcome.ask_kind is None, (
            f"decide() rostered the unplaced token {token!r} back as a "
            f"{outcome.ask_kind!r} with options {outcome.ask_options!r} - the "
            f"unplaced_never_offered guard did not fire (note={outcome.note!r}); "
            "expected note='unplaced_never_offered' and no ask at all"
        )
        offered_labels = [str(o.get("label")) for o in outcome.ask_options]
        assert token not in offered_labels, (
            f"the customer's own unresolved token {token!r} was offered back as a "
            f"roster option: {outcome.ask_options!r}"
        )


# --------------------------------------------------------------------------- #
# AC-1691: no roster with fewer than two options, over every roster policy and both
# entity kinds the UAC names.
# --------------------------------------------------------------------------- #


def _focus_with_one_ambiguous_candidate(kind: str) -> Focus:
    """A focus carrying exactly ONE un-uuid'd candidate of `kind` - the resolver named
    it this turn but it settles nothing (no `uuid`), which is the shape every roster
    policy's ambiguity branch reads."""
    focus = Focus()
    candidate = {"raw": "AMBIG-1", "canonical_code": "AMBIG-1", "hint": kind}
    attr = KIND_FIELD_MAP.get(kind)
    if attr:
        setattr(focus, attr, [candidate])
    else:
        focus.extra[kind] = [candidate]
    return focus


class TestNoRosterIsEverAskedWithFewerThanTwoOptions:
    """AC-1691, "parametrized over every narrowing policy ... and over product and
    customer kinds": every value in `narrow._ROSTER_POLICIES` (read off the module, not
    hard-coded here) crossed with `["product", "customer"]`.

    Measured today (this session, direct `decide()` calls over all six cells): a
    `_pick` with exactly ONE option comes back for FOUR of the six -
    `narrow_to_code`/product, `narrow_to_code`/customer, `narrow_by_tier`/product,
    `narrow_by_tier`/customer - all falling into the SAME shared, unconditional
    "narrow_to_code only now" roster arm (narrow.py, "if candidates and not all(c.get
    ('uuid') for c in candidates): return NarrowOutcome(f'{kind}_pick', ...)"), because
    `narrow_by_tier`'s tier-specific branch only special-cases `kind == "tier"` and
    falls through to that same arm for any other kind. `must_narrow_one`/product and
    `must_narrow_one`/customer are already correct (a single ambiguous candidate is one
    choice, not a roster - `_choices(...) > 1` correctly gates it) - this is NOT
    "`narrow_to_code` only", contra the plan table's own (there, explicitly flagged as
    unverified) guess.

    `narrow_by_tier`'s REAL production pairing is `kind == "tier"` only
    (`policy_rows.DEFAULT_DOMAIN_ROWS`'s `promotion` row) and is out of this test's
    scope (the UAC names product/customer only) - its own zero-option placeholder for
    that kind is filled in by `turn/apply.py` from `policy.tier_order` before it ever
    reaches a customer, verified separately in this session (3 options via `apply()`,
    not a violation).
    """

    @pytest.mark.parametrize("kind", ["product", "customer"])
    @pytest.mark.parametrize("policy_value", sorted(_ROSTER_POLICIES))
    def test_roster_pick_never_has_fewer_than_two_options(
        self, policy_value: str, kind: str
    ) -> None:
        focus = _focus_with_one_ambiguous_candidate(kind)

        outcome = decide(
            kind=kind,
            policy_value=policy_value,
            focus=focus,
            profile=Profile(),
            resolved_candidates=None,
            unplaced=None,
        )

        if outcome.ask_kind is None:
            return
        assert len(outcome.ask_options) >= 2, (
            f"policy_value={policy_value!r} kind={kind!r} rostered a "
            f"{outcome.ask_kind!r} with only {len(outcome.ask_options)} option(s) "
            f"({outcome.ask_options!r}) from a single ambiguous candidate - a roster "
            "must never offer fewer than two choices (AC-1691); one candidate is a "
            "settled thing to fetch, not a question"
        )


# --------------------------------------------------------------------------- #
# AC-1688(a): `_answered_unfiltered` treats an empty entity list with a non-empty
# `unplaced` as unfiltered.
# --------------------------------------------------------------------------- #


class TestAnsweredUnfilteredTreatsEmptyEntitiesAsUnfiltered:
    """`turn_runtime._answered_unfiltered`'s own docstring: "unfiltered" means the tool
    had nothing to narrow BY. Its current guard clause (`if not entities or not
    unplaced: return False`) returns False the moment `entities` is empty, which is
    backwards: an EMPTY entity list is the MOST unfiltered a fetch can be. Measured
    today: `_answered_unfiltered({"fetch": {"tool": {"name": ...}}}, [], {"...": "..."})
    == False`; the non-empty-entities sibling case already returns True (unchanged,
    kept green here as a control).
    """

    def test_empty_entities_with_unplaced_is_unfiltered(self) -> None:
        fragment = {"fetch": {"tool": {"name": "crm_inventory_stock_balance_list"}}}
        unplaced = {"srtwt165nl": "SRTWT165-NL"}

        result = _answered_unfiltered(fragment, [], unplaced)

        assert result is True, (
            "_answered_unfiltered(fragment, [], unplaced) returned False for an EMPTY "
            "entity list with a non-empty unplaced - a tool that ran with nothing to "
            "narrow by is the definition of 'answered unfiltered', and this is exactly "
            "the case that let crm_inventory_stock_balance_list answer about the whole "
            "catalogue for a token the resolver never placed (security review N-1)"
        )

    def test_control_non_empty_entities_all_unplaced_still_unfiltered(self) -> None:
        """Unchanged control: this branch already worked before R1 and must keep
        working - a real regression here would be a DIFFERENT, worse bug."""
        fragment = {"fetch": {"tool": {"name": "crm_inventory_stock_balance_list"}}}
        unplaced = {"srtwt165nl": "SRTWT165-NL"}
        entities = [{"raw": "SRTWT165-NL", "canonical_code": "SRTWT165-NL"}]

        assert _answered_unfiltered(fragment, entities, unplaced) is True

    def test_outstanding_report_exception_stays_filtered(self) -> None:
        """The one named exception (`case-071`/`case-058`): an outstanding report
        fetch filters by the CODE itself, not an id, so it is never "unfiltered" even
        when every entity it has is unplaced."""
        fragment = {
            "fetch": {
                "outstanding_report": True,
                "tool": {"name": "crm_outstanding_report"},
            }
        }
        unplaced = {"srtwt7445": "SRTWT7445"}
        entities = [{"raw": "SRTWT7445", "canonical_code": "SRTWT7445"}]

        assert _answered_unfiltered(fragment, entities, unplaced) is False
        # And the empty-entities shape must ALSO respect the same exception once fixed.
        assert _answered_unfiltered(fragment, [], unplaced) is False


# --------------------------------------------------------------------------- #
# AC-1688(b): a cross-domain rung never runs when the primary spec has no entities,
# parametrized over every domain policy_rows.DEFAULT_DOMAIN_ROWS actually ladders.
# --------------------------------------------------------------------------- #


def _ladder_domains() -> list[str]:
    """Every domain the SEED DATA actually gives a non-empty `ladder` - read off
    `policy_rows.DEFAULT_DOMAIN_ROWS`, never hard-coded (measured today: `inventory`
    and `incoming`)."""
    return [
        str(row["name"])
        for row in policy_rows.DEFAULT_DOMAIN_ROWS
        if row.get("ladder")
    ]


def _real_policy() -> Policy:
    return Policy.from_rows(
        domains=policy_rows.DEFAULT_DOMAIN_ROWS,
        kinds=policy_rows.DEFAULT_KIND_ROWS,
        tier_order=[],
    )


def _spying_ctx(*, granted_reveals: list[str]) -> tuple[SimpleNamespace, list[tuple[str, list[Any]]]]:
    calls: list[tuple[str, list[Any]]] = []

    def runner(domain: str, spec: FetchSpec) -> dict[str, Any]:
        calls.append((domain, list(spec.entities)))
        # Always a miss: no figures/denied/error/tool_has_result, so `envelope_missed`
        # is True and `_climb` is given every chance to (wrongly) keep climbing.
        return {}

    ctx = SimpleNamespace(
        policy=_real_policy(),
        tool_runner=runner,
        trace=TurnTrace(),
        # Both real rung grants held, so a missing grant can never explain a rung NOT
        # running - the only thing left to explain it is the fix this test wants.
        granted_reveals=granted_reveals,
    )
    return ctx, calls


class TestCrossDomainRungNeverRunsWithNoEntities:
    """`turn/fetch.py::_climb` reuses the PRIMARY spec unchanged for every rung
    (`replace(spec, domain=rung)`), so a domain whose subject never resolved (empty
    `FetchSpec.entities`) climbs its ladder and calls the rung's tool with the SAME
    empty entity list - unfiltered. Measured today, both ladder domains: `run_fetch`
    with `FetchSpec(domain=X, entities=[], ...)` and an always-miss tool_runner calls
    the primary AND every rung, all with `entities == []`
    (`[('inventory', []), ('incoming', []), ('purchase_order', [])]` for `inventory`;
    `[('incoming', []), ('inventory', []), ('purchase_order', [])]` for `incoming`).
    """

    @pytest.mark.parametrize("domain", _ladder_domains())
    def test_rung_does_not_run_when_primary_spec_has_no_entities(self, domain: str) -> None:
        ctx, calls = _spying_ctx(granted_reveals=["purchase_orders.placed"])
        spec = FetchSpec(domain=domain, entities=[], filters={}, date_window=None)
        plan = Plan(domains=[domain], fetch=[spec], ask=None, denied=[], trace=Trace())

        run_fetch(plan, ctx)

        assert calls == [(domain, [])], (
            f"run_fetch climbed the {domain!r} ladder with an EMPTY entity list and "
            f"called {calls[1:]!r} beyond the primary fetch - a cross-domain rung must "
            "never run for a subject that did not resolve, whatever the ladder names"
        )

    def test_ladder_domains_are_not_hard_coded_and_are_non_empty(self) -> None:
        """A guard on the parametrize source itself: if the seed data ever drops every
        ladder, this test file's own parametrization would silently cover nothing."""
        assert _ladder_domains(), "expected at least one domain with a non-empty ladder"


# --------------------------------------------------------------------------- #
# AC-1688 gap found while re-pinning `handbuilt-rp-004` (fixture round, 20 Sep 2026,
# captain-confirmed real): `_climb`'s `if not spec.entities: return` guard only
# catches a LITERALLY EMPTY list. `narrow.decide`'s own `unplaced_never_offered`
# outcome (`NarrowOutcome(None, [], candidates, None, note="unplaced_never_offered")`)
# hands the fetch a NON-EMPTY entities list whose members carry no `uuid` at all - the
# exact SAME "did this resolve" signal `lanes/business/fetch.py::entity_ids_
# transformer` reads to decide `missing_or_bad_uuid` (measured there: `uuid` falsy OR
# not shaped like `_UUID_RE`, `^[0-9a-f]{8}-...`). Pinned on that same signal, not a
# new one: a rung must never run when NO entity in the spec carries a resolved uuid.
# --------------------------------------------------------------------------- #


def _unresolved_entity(code: str) -> dict[str, Any]:
    """The shape `narrow.decide`'s `unplaced_never_offered` outcome actually leaves an
    entity in - present (raw/canonical_code), no `uuid` at all. This is exactly the
    entity `fetch.py::entity_ids_transformer` reports `missing_or_bad_uuid` for."""
    return {"raw": code, "canonical_code": code, "entity_type": "product"}


def _resolved_entity(code: str, uuid: str) -> dict[str, Any]:
    """A real, resolved candidate - a valid `_UUID_RE`-shaped uuid, the signal
    `entity_ids_transformer` reads as "this one is real, pass its id through"."""
    return {"raw": code, "canonical_code": code, "entity_type": "product", "uuid": uuid}


class TestCrossDomainRungNeverRunsWhenNoEntityIsResolved:
    """Measured today (both ladder domains, via `run_fetch` directly - the same seam
    `TestCrossDomainRungNeverRunsWithNoEntities` uses): a spec whose ONLY entity has no
    resolved uuid still climbs the WHOLE ladder exactly as a spec with a real,
    resolved-but-still-missing product would - `[('inventory', [...]), ('incoming',
    [...]), ('purchase_order', [...])]` for `inventory`, `[('incoming', [...]),
    ('inventory', [...]), ('purchase_order', [...])]` for `incoming` - because
    `_climb`'s own guard only asks "is this list empty", never "does anything in it
    have a real id". This is the live path `handbuilt-rp-004`'s own re-pin measured
    this session: "stock and eta for SRTWT2634" (SRTWT2634 never resolves) climbs to
    `purchase_order` and fires a real `crm_procurement_po_placed_list` call whose args
    carry zero real uuids (`skipped: [{"code": "SRTWT2634", "reason":
    "missing_or_bad_uuid"}]`) - the rows are discarded later by `_answered_unfiltered`,
    but the unfiltered MCP round trip itself still happens.
    """

    @pytest.mark.parametrize("domain", _ladder_domains())
    def test_rung_does_not_run_when_no_entity_in_the_spec_is_resolved(
        self, domain: str
    ) -> None:
        ctx, calls = _spying_ctx(granted_reveals=["purchase_orders.placed"])
        unresolved = [_unresolved_entity("SRTWT2634")]
        spec = FetchSpec(domain=domain, entities=unresolved, filters={}, date_window=None)
        plan = Plan(domains=[domain], fetch=[spec], ask=None, denied=[], trace=Trace())

        run_fetch(plan, ctx)

        assert calls == [(domain, unresolved)], (
            f"run_fetch climbed the {domain!r} ladder for a spec whose ONLY entity has "
            f"no resolved uuid (the exact missing_or_bad_uuid signal) and called "
            f"{calls[1:]!r} beyond the primary fetch - a rung must never run when "
            "nothing in the spec actually resolved, whatever the ladder names"
        )

    @pytest.mark.parametrize("domain", _ladder_domains())
    def test_rung_still_runs_when_one_of_two_entities_is_resolved(
        self, domain: str
    ) -> None:
        """The permissive half: a spec that has AT LEAST ONE real, resolved entity
        beside an unresolved one is not "nothing to narrow by" - today's code already
        lets the rung run in this shape (it does not distinguish resolved from
        unresolved at all yet), and that is correct, so this is a green control, not a
        new pin. If a future fix over-corrects to "any unresolved entity blocks the
        rung", this is the test that would catch it."""
        ctx, calls = _spying_ctx(granted_reveals=["purchase_orders.placed"])
        mixed = [
            _resolved_entity("SRTWC286", "11111111-1111-1111-1111-111111111111"),
            _unresolved_entity("SRTWT2634"),
        ]
        spec = FetchSpec(domain=domain, entities=mixed, filters={}, date_window=None)
        plan = Plan(domains=[domain], fetch=[spec], ask=None, denied=[], trace=Trace())

        run_fetch(plan, ctx)

        rung_domains = [c[0] for c in calls[1:]]
        assert rung_domains, (
            f"expected the {domain!r} ladder to still climb when one of two entities "
            f"is genuinely resolved, but no rung ran at all: {calls!r}"
        )


class TestThePrimaryFetchIsAlreadyProtectedByADifferentMechanism:
    """What the captain asked this session to check before pinning anything further:
    does the PRIMARY fetch (not a rung) also run unfiltered for an all-unresolved,
    non-empty entities list? Measured: NO - `turn_runtime._answered_unfiltered` (a
    DIFFERENT mechanism than `_climb`'s spec.entities guard, living in `make_tool_
    runner`'s own closure, not in `turn/fetch.py` at all) already treats this exact
    shape as unfiltered and overrides the tool's own answer with a clean miss. This is
    R1's OWN already-shipped fix (this file's `TestAnsweredUnfilteredTreatsEmpty
    EntitiesAsUnfiltered.test_control_non_empty_entities_all_unplaced_still_
    unfiltered`, already green before this class existed) - restated here, beside the
    rung gap, so a reader comparing the two seams side by side sees why only one of
    them needed a new pin this round.
    """

    def test_primary_fetch_protection_is_answered_unfiltered_not_climbs_own_guard(
        self,
    ) -> None:
        fragment = {"fetch": {"tool": {"name": "crm_inventory_stock_balance_list"}}}
        unplaced = {_token_key("SRTWT2634"): "SRTWT2634"}
        entities = [_unresolved_entity("SRTWT2634")]

        result = _answered_unfiltered(fragment, entities, unplaced)

        assert result is True, (
            "the primary fetch's own protection (_answered_unfiltered) no longer "
            "treats a non-empty, all-unresolved entities list as unfiltered - if this "
            "ever goes red, the PRIMARY fetch (not just the rung) is at risk, and the "
            "fix belongs in turn_runtime.py, not turn/fetch.py::_climb"
        )
