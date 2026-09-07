"""World replay: a whole captured turn, end to end through `run_turn` + `complete_turn`.

AC-009. A "world" is not captured separately - it is DERIVED from a spine capture, because
a spine capture already carries every node output of its own execution in `ctx`. The n8n
repo has exactly ONE hand-built world and no tooling to make more, so building 100+ by
capturing them was a target against a capability that does not exist; deriving them from
the 200 `compile-current-state` captures the S1 corpus already holds costs nothing and
grades the SAME executions the node replay grades, only end to end.

**What is stubbed, and why each one.** Everything the CRM cannot reproduce offline is
replaced by the value that execution actually saw:

* the PARSER, at the provider seam - the world feeds `_parser_raw`, the model's own raw
  emission, so `output_exchange`'s 69 derived keys still run for real;
* the ACCESS check - `check-access`'s captured response, because the contact's grants are
  production data;
* the CS ROSTER read - `get-cs-members`'s captured items, for the same reason;
* the stock-denial flag - OFF, which is what production runs (R1).

Nothing else is faked. The session read and write, the turn row, the copy resolution, the
outcome hub, the state compiler and the compose all run against a real blank Postgres
schema, which is the point: node replay proves each function, a world proves the WIRING.

**Multi-turn worlds chain the CRM's OWN memory.** Turn 2 of a contact reads the session
turn 1 wrote, not the session n8n wrote, so a carry the port gets wrong changes the reply
and the world goes red. That is the only test in the suite that can catch it.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from tests.chatbot import _corpus

# TWO nodes, not seven. Every input a world needs is on the `build-ctx` HUB - the message,
# the contact, the session that was read, the parser's raw emission, the access answer and
# the media block are each a producer's output VERBATIM on it (that is what `build-ctx.js`
# is for) - so reading the hub covers a capture whose own graph does not contain those
# producers as nodes at all. `crossdomain-compose` is the reply the turn actually sent, and
# without it there is nothing to grade against.
REQUIRED_NODES = ("build-ctx", "crossdomain-compose")

# Which captures can supply a world.
#
# `sub-output-live` is the best of them and was added on 5 Sep: the tail's own workflow
# carries the whole hub on its `build-ctx` carrier AND the thirteen trigger fields
# verbatim, so a world derived from it is complete by construction and grades the body the
# port implements. The three spine slugs stay because they are what the head's own
# captures live under.
WORLD_SLUGS = (
    "sub-output-live",
    "live-spine-sorento-consume-main",
    "clone-spine-RS",
    "spine-rs-1a",
)

# The shapes gate 0 asks for by name (plan, cutover ladder 0): "at least 5 per branch_kind
# and per shape (picker, did-you-mean, tier ask, escalation, offer-hold, media)". Derived
# from the capture, never declared on it, so a re-capture reclassifies itself.
SHAPES = ("picker", "did_you_mean", "tier_ask", "escalation", "offer_hold", "media", "plain")


@dataclass(frozen=True)
class World:
    """One captured turn, with everything needed to replay and grade it."""

    world_id: str
    slug: str
    execution_id: str
    contact_id: str
    # Nodes the capture does not carry although its own state depends on them. Non-empty
    # means the world is derived but not gradeable in this corpus.
    missing_inputs: tuple[str, ...]
    # `route-turn`'s own decision, when the capture has that node. None means this world
    # cannot grade the router.
    branch_kind: str | None
    # The tag the LANE put on the item (`not_found`, `access_choice`, ...). A different
    # vocabulary from `branch_kind` and never asserted against it.
    lane_tag: str | None
    shape: str
    # inputs
    envelope: dict[str, Any]
    session_vars: dict[str, Any]
    parser_raw: dict[str, Any]
    access: dict[str, Any]
    fragments: dict[str, Any]
    roster_responses: list[Any]
    # what the execution actually produced
    expected_text: Any
    expected_quick_replies: Any
    expected_variables: dict[str, Any]
    # The parse block the capture's own execution produced. Compared against the port's
    # to tell an S1 body difference apart from an S2 defect.
    captured_parse_output: dict[str, Any]

    @property
    def is_delegated(self) -> bool:
        """S2 still delegates every lane, so every world runs `/turn` then `/complete`."""
        return True


@dataclass
class MultiTurnWorld:
    """3 to 5 consecutive turns of ONE contact, replayed on the CRM's own memory."""

    contact_id: str
    turns: list[World] = field(default_factory=list)


def _json(items: Any) -> Any:
    return (items[0] or {}).get("json") if items else None


def _all_json(items: Any) -> list[Any]:
    return [(i or {}).get("json") for i in (items or [])]


def _shape_of(hub: dict, ctx: dict, item: dict, variables: dict, text: Any) -> str:
    """The world's SHAPE, derived from what the turn actually did.

    Ordered, first match wins, most specific first: a tier ask that also renders a picker
    is a tier ask, because the tier roster is what the next turn resolves against.

    MEDIA is read off `ctx.media`, the RS-4 hub key, not off which media nodes happen to
    appear in the capture: `detect-media` runs on EVERY turn and only a non-null hub key
    means a photo or a voice note actually arrived.
    """
    if hub.get("media") is not None:
        return "media"
    if item.get("branch_kind") == "offer_hold" or ctx.get("offer-hold-reply"):
        return "offer_hold"
    if variables.get("tier_menu") or variables.get("selection_context") == "tier_offer":
        return "tier_ask"
    if variables.get("dym_last_result_set") or variables.get("dym_offer"):
        return "did_you_mean"
    if variables.get("picker_last_result_set") or variables.get("selection_context") == "disambiguation":
        return "picker"
    if variables.get("selection_context") in ("member_offer", "team_clarify", "company_clarify"):
        return "escalation"
    if isinstance(text, str) and re.search(r"would you like me to escalate", text, re.IGNORECASE):
        return "escalation"
    return "plain"


def _expected_reply(ctx: dict) -> tuple[Any, Any, dict[str, Any]]:
    """`crossdomain-compose`'s output, through either shape a capture can carry."""
    composed = _json(ctx.get("crossdomain-compose")) or {}
    if "reply" in composed:
        reply = composed.get("reply") or {}
        patch = reply.get("session_patch") or {}
        return reply.get("text"), reply.get("quick_replies"), patch.get("variables") or {}
    return (
        composed.get("user_response"),
        composed.get("quick_reply"),
        composed.get("variables") or {},
    )


# The four fields `escalate-catalog` STAMPS onto the item it received. Removing them
# recovers the item as it entered the tail, which is what `/complete` is given - feeding
# the stamped item back in would make the catalog re-derive its own output on top of
# itself, and on the CS lane would render the picker twice.
_CATALOG_STAMPS = ("response", "manualResponse", "includeResponse", "is_escalate_offer")

# Producers `sub-output`'s graph does NOT contain: the happy-path answer, the validator,
# the promotion picker and the miss builders all live in `sub-main-processing`. RS-6.1c is
# the mechanism for exactly this - a moved producer hands its slice back as
# `outcome_fragment` - so a world uses that contract rather than inventing a channel.
_FRAGMENT_PRODUCERS = (
    "build-ideate-reply",
    "central-exchange",
    "promo-picker",
    "validator",
    "crossdomain-zeroset",
    "build-miss-member-offer",
    "dym-annotate-partial",
    "dym-annotate",
)


# The eleven nullable producer fields `sub-output`'s trigger declares, beside `item` and
# `ctx`. ONE list, so the world harness and `engine.FRAGMENT_FIELDS` cannot drift.
_TRIGGER_FIELDS = (
    "result",
    "resolved",
    "gate",
    "offer_hold",
    "suggest_offer",
    "not_found",
    "incoming_picker",
    "access_choice",
    "crossdomain_render",
    "answer",
    "clarify",
)


def _tail_input_item(ctx: dict) -> dict[str, Any]:
    """The item as it ENTERS the tail, recovered from whichever node the capture holds."""
    restored = _json(ctx.get("item-restore"))
    if isinstance(restored, dict):
        # `item-restore` re-emits the trigger's `item` VERBATIM, which is exactly what the
        # tail receives - no recovery arithmetic needed.
        return restored
    catalog = _json(ctx.get("escalate-catalog"))
    if isinstance(catalog, dict):
        return {k: v for k, v in catalog.items() if k not in _CATALOG_STAMPS}
    hub = _json(ctx.get("build-outcome"))
    if isinstance(hub, dict):
        return {k: v for k, v in hub.items() if k != "outcome"}
    router = _json(ctx.get("route-turn"))
    return router if isinstance(router, dict) else {}


def _fragments_from(ctx: dict, item: dict) -> dict[str, Any]:
    """The `sub-output` trigger contract, rebuilt from the capture's own node outputs.

    Exactly the expressions `Call 'sub-output'` carries today
    (`$('x').isExecuted ? $('x').first().json : null`), which is what makes a world's
    `/complete` call the same call n8n makes.

    A `sub-output-live` capture has the trigger ITSELF, which is better than rebuilding:
    it is the body of the real call, with n8n's own null-dropping already applied. It is
    preferred whenever present and the reconstruction is the fallback for spine captures.
    """
    trigger = _json(ctx.get("When Executed by Another Workflow"))
    if isinstance(trigger, dict) and "item" in trigger:
        return {
            "item": item,
            **{name: trigger.get(name) for name in _TRIGGER_FIELDS},
        }
    fragment = {
        name: _json(ctx.get(name)) for name in _FRAGMENT_PRODUCERS if ctx.get(name)
    }
    return {
        "item": {**item, "outcome_fragment": fragment} if fragment else item,
        "result": _build_result(ctx),
        "resolved": _json(ctx.get("resolve-entity")),
        "gate": _json(ctx.get("disallowed-entity-gate")),
        "offer_hold": _json(ctx.get("offer-hold-reply")),
        "suggest_offer": _json(ctx.get("build-suggest-offer")),
        "not_found": _json(ctx.get("not-found-error-message")),
        "incoming_picker": _json(ctx.get("annotate-incoming-picker")),
        "access_choice": _json(ctx.get("access-level-choice-message")),
        "crossdomain_render": _json(ctx.get("crossdomain-render")),
        "answer": _json(ctx.get("Call 'sub-answer'")),
        "clarify": _json(ctx.get("clarify-company-reply")),
    }


# The producers that can make a reply. `central-exchange` is the happy path's; the rest
# are the escalate / offer arms. A capture that carries none of them cannot be replayed
# end to end, because the CRM has nothing to compose the answer FROM - that lane's
# producer lived inside a sub the spine capture never recorded.
_TEXT_PRODUCERS = (
    "central-exchange",
    "escalate-catalog",
    "build-suggest-offer",
    "build-cs-member-offer",
    "build-ideate-reply",
    "clarify-company-reply",
    "offer-hold-reply",
)


def _can_produce_the_reply(ctx: dict, variables: dict) -> bool:
    """Does this capture carry the producer its own reply came from?

    A `sub-output` capture always does, by construction: the tail's INPUT ITEM is the
    answer envelope on the happy path (`compile-current-state`'s `getResultObj` falls
    back to `$input`, because no node in that graph writes `outcome_fragment`), and the
    trigger carries it verbatim. So a capture with the trigger needs no producer test at
    all - it has exactly what the tail runs on.
    """
    trigger = _json(ctx.get("When Executed by Another Workflow"))
    if isinstance(trigger, dict) and "item" in trigger:
        return True
    # A SPINE capture is the other case: the tail ran inline or inside a sub, so the
    # answer came from a named producer. An ANSWERED turn compresses `variables.response`
    # to `Previous turn (<domain>): ...` and that comes from `central-exchange` and
    # nowhere else, so a capture without it cannot reproduce the reply no matter how
    # faithful the port is. Every other lane needs one of the escalate / offer builders.
    response = variables.get("response")
    if isinstance(response, str) and response.startswith("Previous turn ("):
        return bool(ctx.get("central-exchange"))
    return any(ctx.get(name) for name in _TEXT_PRODUCERS)


# Session keys that can only be derived from the resolver and the entity gate. When the
# capture's own variables carry one, a capture WITHOUT those two nodes cannot be replayed:
# the CRM would correctly compute nulls and be graded against values it was never given.
_GATE_DERIVED_KEYS = (
    "routing_companies",
    "routing_company",
    "routing_brand",
    "routing_brand_source",
    "routing_roster_plan",
    "picker_last_result_set",
    "picker_families",
)


def _missing_inputs(ctx: dict, variables: dict) -> tuple[str, ...]:
    """Nodes this world's own state needs that the capture does not carry.

    A `clone-spine-RS` capture records the SPINE only - the resolver and the entity gate
    run inside `sub-resolve-and-gate`, a different workflow, so its `ctx` has neither even
    though the execution certainly ran them. Replaying such a world would grade the CRM's
    correct nulls against values it was never given, which says nothing about the port.
    The world is still DERIVED (it is a real turn, and a fresh capture makes it gradeable);
    the replay skips it by name, the way a stale node capture is skipped.
    """
    if not any(variables.get(key) for key in _GATE_DERIVED_KEYS):
        return ()
    return tuple(
        node for node in ("disallowed-entity-gate", "resolve-entity") if not ctx.get(node)
    )


def _build_result(ctx: dict) -> Any:
    """`build-result`'s output, with the cross-domain block where the SHIPPING body reads it.

    The two bodies differ on ONE read: the live spine's `crossdomain-compose` takes the
    block off `crossdomain-render._xdBlock`, and the body the export ships takes it off
    `build-result.result.xd.block` (RS-6.1a moved it). On a live capture the second is
    null and the first is populated, so handing the port the live value through the shape
    it expects replays the SAME block rather than writing the capture off. Verified by
    `diff` of the two exported bodies: that read plus the RS-3 seal is the whole delta.
    """
    result = _json(ctx.get("build-result"))
    inner = result.get("result") if isinstance(result, dict) else None
    xd = inner.get("xd") if isinstance(inner, dict) else None
    if isinstance(xd, dict) and xd.get("block"):
        return result
    render = _json(ctx.get("crossdomain-render"))
    block = (render or {}).get("_xdBlock")
    if not block:
        return result
    # `build-result` is an RS-6.1a node and only 24 of the live captures predate it, so
    # on most of them the envelope has to be built around the block rather than patched
    # into one. `xd.block` is the ONLY thing `crossdomain-compose` reads off `result`.
    base = result if isinstance(result, dict) else {}
    return {
        **base,
        "result": {**(inner or {}), "xd": {**(xd or {}), "block": block}},
    }


def _world_from(fixture: _corpus.Fixture) -> World | None:
    ctx = fixture.ctx
    if any(not ctx.get(node) for node in REQUIRED_NODES):
        return None
    hub = (_json(ctx["build-ctx"]) or {}).get("ctx") or {}
    contact = hub.get("contact") or {}
    contact_id = str(contact.get("id") or "")
    if not contact_id:
        return None
    # Every one of these is read off the HUB rather than off the producer node, so a
    # capture whose graph does not contain that producer still makes a world.
    parse = hub.get("parse") or {}
    parser_raw = parse.get("_parser_raw")
    if not isinstance(parser_raw, dict):
        return None
    session = hub.get("session") or {}
    session_vars = session.get("session_vars") or {}
    if not isinstance(session_vars, dict):
        session_vars = {}

    item = _tail_input_item(ctx)
    # Only a capture with a real `route-turn` node can grade the ROUTER. On the live spine
    # the routing is still an If ladder, and the `branch_kind` on the tail's item is the
    # LANE's own tag (`not_found`, `access_choice`), which is a different vocabulary - so
    # a world derived from one grades the reply and the memory, not the lane.
    router = _json(ctx.get("route-turn"))
    routed_kind = (router or {}).get("branch_kind") if isinstance(router, dict) else None
    text, quick, variables = _expected_reply(ctx)
    if not _can_produce_the_reply(ctx, variables):
        return None

    execution_id = str((fixture.data.get("source") or {}).get("execution_id") or fixture.name)
    return World(
        world_id=f"{fixture.name}",
        slug=fixture.name.split("/")[0] if "/" in fixture.name else "vendored",
        execution_id=execution_id,
        contact_id=contact_id,
        missing_inputs=_missing_inputs(ctx, variables),
        branch_kind=routed_kind,
        lane_tag=(item or {}).get("branch_kind"),
        shape=_shape_of(hub, ctx, item or {}, variables, text),
        envelope={
            "message": hub.get("text") or {},
            "contact": contact,
            # `ctx.media` is the RS-4 hub key the media-confirmation block reads. It rides
            # on the envelope because that is where `run_turn` takes it from - n8n's
            # `sub-media-intake` patches it onto the queue item before the spine runs.
            "media": hub.get("media"),
            # D14: a world never sends and never writes a real session. The engine reads
            # this off the row it stores, so the whole replay is dry by construction
            # rather than by remembering to pass a flag at each call site.
            "is_test": True,
            "ingress": "console",
        },
        session_vars=session_vars,
        parser_raw=parser_raw,
        access=hub.get("access") or {},
        fragments=_fragments_from(ctx, item or {}),
        roster_responses=_all_json(ctx.get("get-cs-members")),
        expected_text=text,
        expected_quick_replies=quick,
        expected_variables=variables,
        captured_parse_output=parse.get("output") or {},
    )


def _candidate_fixtures() -> Iterable[_corpus.Fixture]:
    """Every capture that could carry a whole execution, from EVERY node directory.

    Not just the ten nodes the port has replayed: a world needs the execution's `ctx`,
    and `disallowed-entity-gate` or `build-suggest-offer` records the same turn as
    `compile-current-state` does. Restricting the scan to the ported nodes would have
    thrown away most of the corpus for no reason other than which directory the capture
    happens to live in.
    """
    import json as _json_mod

    root = _corpus.corpus_root()
    if root is not None:
        for slug in WORLD_SLUGS:
            slug_dir = root / "nodes" / slug
            if not slug_dir.is_dir():
                continue
            for node_dir in sorted(slug_dir.iterdir()):
                if not node_dir.is_dir():
                    continue
                for path in sorted(node_dir.glob("*.json")):
                    with path.open(encoding="utf-8") as handle:
                        yield _corpus.Fixture(
                            node=node_dir.name,
                            name=f"{slug}/{path.stem}",
                            path=path,
                            data=_json_mod.load(handle),
                        )
    # The vendored subset too, so a checkout with no sibling n8n repo still has worlds.
    for node in sorted(_corpus.NODE_SLUGS):
        yield from _corpus.vendored(node)


def derive_worlds() -> list[World]:
    """Every world the corpus can produce, deduped by execution, in a stable order.

    Deduped by `(slug, execution_id)` because the same execution is captured under
    several node directories - `compile-current-state`, `crossdomain-compose` and
    `escalate-catalog` all record the same turn - and replaying it three times would
    inflate the count without adding a single new path.
    """
    seen: dict[tuple[str, str], World] = {}
    for fixture in _candidate_fixtures():
        world = _world_from(fixture)
        if world is None:
            continue
        seen.setdefault((world.slug, world.execution_id), world)
    return [seen[key] for key in sorted(seen)]


def multi_turn_worlds(worlds: Iterable[World], *, minimum: int = 3, maximum: int = 5) -> list[MultiTurnWorld]:
    """Consecutive turns of ONE contact, in execution order, in runs of 3 to 5.

    Execution ids are monotonic per n8n instance, so sorting by them recovers the order
    the customer actually sent the messages in. A contact with more than `maximum` turns
    is cut into several runs rather than one long one: the memory paths this exists to
    exercise are all within a few turns, and a 30-turn chain would fail as one opaque
    unit instead of naming the turn that broke.
    """
    by_contact: dict[str, list[World]] = defaultdict(list)
    for world in worlds:
        by_contact[world.contact_id].append(world)
    out: list[MultiTurnWorld] = []
    for contact_id, turns in sorted(by_contact.items()):
        ordered = sorted(turns, key=lambda w: (len(w.execution_id), w.execution_id))
        for start in range(0, len(ordered), maximum):
            chunk = ordered[start : start + maximum]
            if len(chunk) >= minimum:
                out.append(MultiTurnWorld(contact_id=contact_id, turns=chunk))
    return out


def matrix(worlds: Iterable[World]) -> dict[str, dict[str, int]]:
    """`{"branch_kind": {...}, "shape": {...}}` - the counts COVERAGE.md renders."""
    by_branch: dict[str, int] = defaultdict(int)
    by_shape: dict[str, int] = defaultdict(int)
    for world in worlds:
        by_branch[str(world.branch_kind or "unknown")] += 1
        by_shape[world.shape] += 1
    return {"branch_kind": dict(sorted(by_branch.items())), "shape": dict(sorted(by_shape.items()))}


def seed_sql_params(world: World) -> dict[str, Any]:
    """The one row a world needs: the contact and the session it read."""
    return {
        "cid": world.contact_id,
        "phone": f"+60{abs(hash(world.contact_id)) % 10**9:09d}",
        "sv": json.dumps(world.session_vars),
    }


# --------------------------------------------------------------------------- #
# Body differences: a world is either GRADED or SKIPPED BY NAME, never partly
# excused. Each signature below is a difference between the body the export
# ships (which the port implements) and the body that produced the capture -
# the same distinction `_corpus.STALE_FIXTURES` draws for node replay, one level
# up. A world skipped here is a world a fresh capture makes gradeable.
# --------------------------------------------------------------------------- #

# The one PERMANENT world-level difference, and it is not a body difference at all: the
# dym offer stamps `$execution.id` as its identity, and in the CRM that identity is the
# turn id. The offer only has to be stable within the session, so the successor is
# correct - but the value can never equal a captured n8n execution id.
WORLD_DROP_PATHS: tuple[tuple[str, ...], ...] = (("dym_offer", "id"),)


def drop_paths(variables: dict[str, Any]) -> dict[str, Any]:
    """A copy of `variables` with `WORLD_DROP_PATHS` removed."""
    out = json.loads(json.dumps(variables, default=str))
    for path in WORLD_DROP_PATHS:
        node: Any = out
        for key in path[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, dict):
            node.pop(path[-1], None)
    return out


def body_difference(
    world: World,
    *,
    parse_output: dict[str, Any],
    actual_variables: dict[str, Any],
    captured_parse_output: dict[str, Any],
) -> str | None:
    """The named reason this world cannot be graded, or None.

    Order matters: the parse difference is checked first because everything downstream of
    the parser inherits it, so reporting a session-key difference on such a turn would
    name the symptom instead of the cause.
    """
    # The session keys the PORT writes and no capture can carry. Same list, same reason as
    # `divergences._PORT_ONLY_SESSION_KEYS`, which is the node-level half of this: `pending`
    # is the R3 marker and `focus` is growth r1 slice B3's dialogue state. Everything else
    # in the patch is still graded, `entities` and `domain_hint` included.
    if world.missing_inputs:
        return (
            "the capture does not carry "
            + ", ".join(f"`{n}`" for n in world.missing_inputs)
            + ", which its own persisted state was derived from (a spine-only capture: "
            "those nodes ran inside a sub this fixture never recorded)"
        )
    if parse_output != captured_parse_output:
        differing = sorted(
            key
            for key in set(parse_output) | set(captured_parse_output)
            if parse_output.get(key) != captured_parse_output.get(key)
        )
        # AC-821 / review of #713 blocker B2, NAMED rather than absorbed by the generic
        # arm below, whose "a capture older than that body" reason would be a lie here.
        # ONE world reaches this: `sub-output-live/out-15023025`, whose live parser emitted
        # `suggested_team: "purchasing_product"` - a team that is not one of the eight the
        # router can act on - and whose live spine persisted it verbatim. That is the
        # defect B2 fixes (the next turn assigns whatever is in `variables.routing`), so
        # the port deliberately narrows it back to the routing chain's own answer and this
        # world can no longer be graded against the capture.
        #
        # Deliberately unable to excuse anything else: `routing` must be the ONLY key that
        # moved, and the CAPTURE's own team must be the non-catalogue one. A capture whose
        # team is a real member, or one that also differs elsewhere, still falls through.
        from app.services.chatbot.contracts import SUGGESTED_TEAMS

        captured_team = (
            (captured_parse_output.get("routing") or {}).get("suggested_team")
            if isinstance(captured_parse_output.get("routing"), dict)
            else None
        )
        if differing == ["routing"] and isinstance(captured_team, str) and (
            captured_team.strip().lower() not in SUGGESTED_TEAMS
        ):
            return (
                f"the capture's own `routing.suggested_team` is {captured_team!r}, which is "
                "not one of the eight teams in `contracts.SUGGESTED_TEAMS`. AC-821 / review "
                "of #713 B2: a team word the router cannot act on must never reach the "
                "persisted routing, because the NEXT turn assigns whatever is there "
                "(measured: 'escalate to marketing' then 'I need a human' called "
                "next_assignee with team_code 'marketing' and commented 'Team: marketing'). "
                "The port narrows it back to the routing chain's own answer, so this "
                "capture records the defect and cannot be graded. Pinned by "
                "tests/chatbot/test_pass4_item1b_marketing_ambiguous_clarify.py::"
                "TestANonCatalogueTeamWordIsNeverPersistedOrAssigned"
            )
        return (
            "the parser post-processor disagrees with the body that produced this capture "
            f"on {', '.join(differing)}. S1 was re-ported onto the LIVE `output_exchange` "
            "body on 5 Sep, which retired most of this class; what is left is a capture "
            "older than that body. Grading the TAIL against a different understanding of "
            "the turn would attribute a head-side body difference to S2"
        )
    if "requested_attributes" not in world.expected_variables:
        return (
            "captured before QS-9 added `requested_attributes` to the persisted object "
            "(the shipping body array-guards it and always writes it)"
        )
    if actual_variables.get("tier_menu") and "tier_menu" not in world.expected_variables:
        return (
            "captured before the RS-9 Fix 6 tier-menu block, which is a `>`-only hunk in "
            "the body the export ships"
        )
    prev_variables = (world.session_vars or {}).get("variables") or {}
    if (
        actual_variables.get("selection_context")
        and not world.expected_variables.get("selection_context")
        and actual_variables.get("selection_context") == prev_variables.get("selection_context")
        and actual_variables.get("last_result_set") == prev_variables.get("last_result_set")
    ):
        return (
            "captured before OWNER RULING K rule 1 (6 Sep 2026): the offer roster on the "
            "customer's screen now survives a turn that builds no offer of its own, so "
            "'1', then '2', then '3' answer against the same list. This capture records "
            "the old lifetime - the roster cleared the moment the turn had no offer of "
            "its own - and the port re-seats exactly the LABEL AND THE LIST the session "
            "already held, which is what keys this skip: anything else the port persisted "
            "here would be a defect, not the ruling. "
            "The node-level half is registered in tests/chatbot/divergences.py and the "
            "rule is pinned by tests/chatbot/test_tail_units.py"
        )
    if world.expected_variables.get("picker_last_result_set") and not actual_variables.get(
        "picker_last_result_set"
    ):
        return (
            "captured before B56 (H29): the capture persisted the PREVIOUS turn's picker "
            "on a turn that built an offer of its own, which is the defect the shipping "
            "body fixes and `tests/chatbot/test_tail_units.py` pins"
        )
    return None


# --------------------------------------------------------------------------- #
# The OWNER worlds (growth r1 slice B5, AC-940 to AC-948)
# --------------------------------------------------------------------------- #
#
# Derived worlds grade the PORT: a real execution replayed, byte for byte. These grade the
# RULES, and they have to be authored rather than derived for one reason - every capture in
# the corpus predates the code they are about. There is no recorded turn where a focus slot
# aged out, because nothing aged before slice B1; none where the parser said `topic_reset`,
# because no promoted prompt emits it; none where a pick resolved against frozen options,
# because the options were not frozen.
#
# **Same chaining property as `MultiTurnWorld`, which is the whole point** (see this module's
# docstring): turn N+1 reads the session turn N wrote, through `run_turn` and
# `complete_turn`, so a lifecycle rule the code gets wrong changes the answer two turns
# later. The session read and write, the turn rows, the decay pass, the parse
# post-processing, the six focus rules, the open-question resolver and the state compiler
# all run for real against a blank Postgres schema.
#
# **What is stubbed, and why.** The PARSER (the emission is authored, exactly as a derived
# world feeds `_parser_raw`), the ACCESS check, and the LANE that renders a roster - `arm`
# writes what that lane would have persisted. The last one is the only addition to the
# derived worlds' stub list, and it is there because rendering a real picker needs a
# resolver, an MCP call and a product catalogue, none of which says anything about whether
# "2" resolves to the second row.
#
# **These worlds assert DIALOGUE FACTS, never reply prose.** Which product is in scope,
# which domain, whether the question was answered, what decayed. The words a customer reads
# are the owner console pass's job (AC-991), and asserting them here would pin copy that
# the console pass exists to change.


@dataclass(frozen=True)
class OwnerTurn:
    """One authored turn: what the customer said, what the parser made of it, what must
    then be true."""

    message: str
    # Overrides on `tests.chatbot.test_engine._parser_output()`. A v3 emission sets
    # `answers_open_question`, `anaphora` or `topic_reset`; a v1-shaped one leaves them out.
    emission: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)
    # The roster the PREVIOUS reply showed, as the lane would have persisted it. Written
    # into the session before this turn runs.
    arm: dict[str, Any] | None = None
    # A quoted reply: the rows the quoted message carried (AC-947).
    quoted_rows: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class OwnerWorld:
    world_id: str
    acs: tuple[str, ...]
    why: str
    turns: tuple[OwnerTurn, ...]
    # The focus TTL this world runs under. Named per world because the TTL is what two of
    # them are about.
    ttl_turns: int = 3
    # Which parser CONTRACT this conversation runs under. False is the PROMOTED one (v1):
    # 26 keys, no `Focus:` line, the three growth-r1 signals inert. A world about a pick,
    # an anaphora or a topic reset needs v3 and says so, which also documents which of
    # these cases only start working when the owner moves the label (AC-952).
    emits_v3: bool = False


def _product(code: str, **over: Any) -> dict[str, Any]:
    return {
        "raw": code,
        "hint": "product",
        "canonical_code": code,
        "current_message": True,
        "confident": True,
        **over,
    }


def _customer(name: str) -> dict[str, Any]:
    return {
        "raw": name,
        "hint": "customer",
        "canonical_code": name,
        "current_message": True,
        "confident": True,
    }


def _roster(*codes: str) -> list[dict[str, Any]]:
    return [
        {"idx": i, "label": code, "code": code, "uuid": f"uuid-{code}", "entity_type": "product"}
        for i, code in enumerate(codes, start=1)
    ]


def _answers(**kw: Any) -> dict[str, Any]:
    return {"resolved": False, "picks": [], "yes_no": None, "free_text": None, **kw}


# "and the price?" - a REUSE continuation, which is what the two TTL worlds need and what
# a casual turn is not. The executor carries the previous entity set forward on one of
# these, so the scope stays alive by the legacy path right up to the turn the slot dies,
# and the world grades what actually reaches the lane.
_CONTINUATION: dict[str, Any] = {
    "message_type": "business_query",
    "domain_hint": None,
    "intent_hint": None,
    "entities": [],
    "entity_op": "reuse",
}


OWNER_WORLDS: tuple[OwnerWorld, ...] = (
    OwnerWorld(
        world_id="owner-pick-then-next-pick",
        emits_v3=True,
        acs=("AC-944",),
        why=(
            "A picker of three products is offered. '2' resolves to the SECOND FROZEN "
            "option, and a second pick against the same list still resolves - the roster "
            "is on the customer's screen until it ages out, which is owner ruling K rule "
            "1 seen from the dialogue side."
        ),
        turns=(
            OwnerTurn(
                message="SRTKS8091 got stock?",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [_product("SRTKS8091")],
                },
                expect={"focus_products": ["SRTKS8091"], "focus_domain": "inventory"},
            ),
            OwnerTurn(
                message="2",
                arm={
                    "selection_context": "disambiguation",
                    "last_result_set": _roster("SRTKS8091-A", "SRTKS8091-B", "SRTKS8091-C"),
                },
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "answers_open_question": _answers(resolved=True, picks=[2]),
                },
                expect={
                    "answered": "product_pick",
                    "focus_products": ["SRTKS8091-B"],
                    "qf": {"entity_op": "replace"},
                },
            ),
            OwnerTurn(
                message="1",
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "answers_open_question": _answers(resolved=True, picks=[1]),
                },
                expect={"answered": "product_pick", "focus_products": ["SRTKS8091-A"]},
            ),
        ),
    ),
    OwnerWorld(
        world_id="owner-escalate-declined-after-a-result",
        emits_v3=True,
        acs=("AC-945",),
        why=(
            "An escalation offer, then 'no'. The declined copy is the lane's; what this "
            "grades is that the answer REACHES the escalation handler as a decline and "
            "never as a new query."
        ),
        turns=(
            OwnerTurn(
                message="SRTWC8517 stock?",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [_product("SRTWC8517")],
                },
                expect={"focus_products": ["SRTWC8517"]},
            ),
            OwnerTurn(
                message="no",
                arm={"pending": {"kind": "escalation_offer", "team": "warehouse"}},
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "entities": [],
                    "is_affirmative": False,
                    "answers_open_question": _answers(resolved=True, yes_no="no"),
                },
                expect={"answered": "escalate_yes_no", "qf": {"is_affirmative": False}},
            ),
        ),
    ),
    OwnerWorld(
        world_id="owner-escalate-offer-left-unanswered-then-decays",
        emits_v3=True,
        acs=("AC-945",),
        why=(
            "The offer is neither accepted nor declined: the customer asks a stock "
            "question instead. It is ANSWERED, the offer is left open, and the offer is "
            "cleared by its own TTL with a `decay` trace line rather than being answered "
            "silently by a later 'yes' about something else."
        ),
        turns=(
            OwnerTurn(
                message="do you have MSK11A-QT",
                arm={"pending": {"kind": "escalation_offer", "team": "warehouse"}},
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [_product("MSK11A-QT")],
                    "answers_open_question": _answers(resolved=False),
                },
                expect={"answered": None, "focus_products": ["MSK11A-QT"]},
            ),
            OwnerTurn(
                message="and SRTWC8517",
                emission={
                    "message_type": "business_query",
                    "domain_hint": None,
                    "entities": [_product("SRTWC8517")],
                },
                expect={"focus_products": ["SRTWC8517"]},
            ),
            OwnerTurn(
                message="and SRTKS6091",
                emission={
                    "message_type": "business_query",
                    "domain_hint": None,
                    "entities": [_product("SRTKS6091")],
                },
                expect={"focus_products": ["SRTKS6091"], "open_question_gone": True},
            ),
        ),
    ),
    OwnerWorld(
        world_id="owner-filter-change-after-a-do-result",
        acs=("AC-946",),
        why=(
            "'for customer ABC instead' replaces the customer slot and leaves the "
            "products; 'last month' then replaces ONLY the date window. One axis per "
            "turn, which is `replace_same_axis` and `date_restated_only` together."
        ),
        turns=(
            OwnerTurn(
                message="DO for SRTWC8517",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "order",
                    "intent_hint": "check_order",
                    "entities": [_product("SRTWC8517")],
                },
                expect={"focus_products": ["SRTWC8517"], "focus_domain": "order"},
            ),
            OwnerTurn(
                message="for customer ABC instead",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "order",
                    "intent_hint": "check_order",
                    "entities": [_customer("ABC")],
                },
                expect={
                    "focus_customer": "ABC",
                    "focus_products": ["SRTWC8517"],
                    "focus_domain": "order",
                },
            ),
            OwnerTurn(
                message="last month",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "order",
                    "intent_hint": "check_order",
                    "entities": [],
                    "entity_op": "reuse",
                    "date_filter_start": "2026-08-01",
                    "date_filter_end": "2026-08-31",
                },
                expect={
                    "focus_customer": "ABC",
                    "focus_date_window": {
                        "start": "2026-08-01",
                        "end": "2026-08-31",
                        "mode": None,
                    },
                    "qf": {"date_filter_start": "2026-08-01"},
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="owner-what-about-y-after-a-stock-answer",
        acs=("AC-942",),
        why=(
            "'incoming?' after a stock answer keeps the products and switches the domain; "
            "'what about Y' after that replaces the product and KEEPS incoming. The two "
            "halves are `domain_from_switch_word` and `replace_same_axis`, and the second "
            "is what proves the switch did not also become sticky."
        ),
        turns=(
            OwnerTurn(
                message="SRTWC8517 stock?",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [_product("SRTWC8517")],
                },
                expect={"focus_products": ["SRTWC8517"], "focus_domain": "inventory"},
            ),
            OwnerTurn(
                message="incoming?",
                emission={
                    "message_type": "business_query",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "entity_op": "reuse",
                },
                expect={
                    "focus_products": ["SRTWC8517"],
                    "focus_domain": "incoming",
                    "qf": {"domain_hint": "incoming", "domain_switched_by_keyword": "incoming"},
                },
            ),
            OwnerTurn(
                message="SRTKS6091",
                emission={
                    "message_type": "business_query",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [_product("SRTKS6091")],
                },
                expect={
                    "focus_products": ["SRTKS6091"],
                    "focus_domain": "incoming",
                    "qf": {"domain_hint": "incoming"},
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="owner-product-decays-under-continuation-turns",
        acs=("AC-940",),
        why=(
            "A product asked at turn 1 and never named again, with the turns in between "
            "being REUSE continuations of the same question rather than small talk - so "
            "the executor carries the entity forward on every one of them and the scope "
            "looks alive right up to the moment it is not. At N+2 the answer still has "
            "the product; at N+4 it has nothing and the reply has to ask which product. "
            "That last assertion is on the ENTITY LIST, because a TTL that only clears a "
            "focus slot changes no byte a customer reads."
        ),
        turns=(
            OwnerTurn(
                message="SRTWC8517 stock?",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [_product("SRTWC8517")],
                },
                expect={"focus_products": ["SRTWC8517"], "qf_entity_codes": ["SRTWC8517"]},
            ),
            OwnerTurn(
                message="and the price?",
                emission=_CONTINUATION,
                expect={"focus_products": ["SRTWC8517"], "qf_entity_codes": ["SRTWC8517"]},
            ),
            OwnerTurn(
                message="and the dimensions?",
                # Age 2 at this turn: inside the TTL, so the question is still answerable
                # and the product is still in scope.
                emission=_CONTINUATION,
                expect={
                    "focus_products": ["SRTWC8517"],
                    "qf_entity_codes": ["SRTWC8517"],
                    "decayed": (),
                },
            ),
            OwnerTurn(
                message="and the weight?",
                emission=_CONTINUATION,
                expect={"focus_products": ["SRTWC8517"], "qf_entity_codes": ["SRTWC8517"]},
            ),
            OwnerTurn(
                message="and the colour?",
                # Age 4: past the TTL. The slot is dropped at intake AND the carried
                # entity goes with it, so the turn reaches the lanes with nothing to
                # answer about and the reply asks which product.
                emission=_CONTINUATION,
                expect={
                    "focus_products": None,
                    "qf_entity_codes": [],
                    "decayed": ("products",),
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="owner-anaphora-past-the-ttl-asks-which-product",
        acs=("AC-941",),
        why=(
            "The same shape, answered with 'that one' instead of a bare continuation. "
            "Inside the TTL the reference resolves to the alive product; past it there is "
            "nothing to resolve against, the turn is marked unresolved and the bot has to "
            "ask. The `decay` trace line names the slot and its age in turns, which is "
            "AC-941's own evidence."
        ),
        emits_v3=True,
        turns=(
            OwnerTurn(
                message="SRTWC8517 stock?",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [_product("SRTWC8517")],
                },
                expect={"focus_products": ["SRTWC8517"]},
            ),
            OwnerTurn(
                message="and the price?",
                emission=_CONTINUATION,
                expect={"focus_products": ["SRTWC8517"]},
            ),
            OwnerTurn(
                message="what about that one",
                emission={**_CONTINUATION, "anaphora": True},
                expect={
                    "focus_products": ["SRTWC8517"],
                    "qf_entity_codes": ["SRTWC8517"],
                    "qf": {"anaphora_resolved": True},
                },
            ),
            OwnerTurn(
                message="and the weight?",
                emission=_CONTINUATION,
                expect={"focus_products": ["SRTWC8517"]},
            ),
            OwnerTurn(
                message="how much is that one",
                emission={**_CONTINUATION, "anaphora": True},
                expect={
                    "focus_products": None,
                    "qf_entity_codes": [],
                    "qf": {"anaphora_unresolved": True},
                    "decayed": ("products",),
                    "decay_reason_contains": "not restated for 4 turns",
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="owner-partial-miss-pick-resolves-the-dym-roster",
        acs=("AC-944", "AC-948"),
        emits_v3=True,
        why=(
            "The partial miss: one code resolved and the other got a did-you-mean, so TWO "
            "numbered lists are live at once. The rows the customer is LOOKING at are the "
            "suggestions (`dym_last_result_set`); `last_result_set` holds the stock lines "
            "for the code that resolved. '2' has to mean the second SUGGESTION, and the "
            "sibling that already resolved has to survive the pick (issue #708)."
        ),
        turns=(
            OwnerTurn(
                message="SRTKS6091 and SRTKS8091 got stock?",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [_product("SRTKS6091"), _product("SRTKS8091")],
                },
                expect={"focus_products": ["SRTKS6091", "SRTKS8091"]},
            ),
            OwnerTurn(
                message="2",
                arm={
                    "selection_context": "suggest_offer",
                    # The ANSWER's own rows for the code that resolved. Freezing these
                    # would make "2" a stock line.
                    "last_result_set": [
                        {"idx": 1, "label": "SRTKS6091 - 12 in KL", "entity_type": "product"}
                    ],
                    # The rows the reply actually numbered.
                    "dym_last_result_set": _roster("SRTKS8091-A", "SRTKS8091-B"),
                    "dym_offer": {
                        "candidates": [
                            {
                                "code": "SRTKS8091-A",
                                "for_raw": "SRTKS8091",
                                "for_canonical": "SRTKS8091",
                            },
                            {
                                "code": "SRTKS8091-B",
                                "for_raw": "SRTKS8091",
                                "for_canonical": "SRTKS8091",
                            },
                        ]
                    },
                },
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "entities": [],
                    "answers_open_question": _answers(resolved=True, picks=[2]),
                },
                expect={
                    "answered": "product_pick",
                    # The second SUGGESTION, and the sibling that already resolved.
                    "qf_entity_codes": ["SRTKS8091-B", "SRTKS6091"],
                    "focus_products": ["SRTKS8091-B", "SRTKS6091"],
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="owner-quoted-reply-pick",
        emits_v3=True,
        acs=("AC-947",),
        why=(
            "A quoted reply to an OLDER picker resolves against THAT message's frozen "
            "options, not against the roster the latest turn left open. The rows the "
            "customer is looking at are the ones they quoted."
        ),
        turns=(
            OwnerTurn(
                message="SRTKS8091 got stock?",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [_product("SRTKS8091")],
                },
                expect={"focus_products": ["SRTKS8091"]},
            ),
            OwnerTurn(
                message="2",
                arm={
                    "selection_context": "disambiguation",
                    "last_result_set": _roster("NEW-1", "NEW-2", "NEW-3"),
                },
                quoted_rows=_roster("OLD-1", "OLD-2", "OLD-3"),
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "entities": [],
                    "answers_open_question": _answers(resolved=True, picks=[2]),
                },
                expect={"answered": "product_pick", "focus_products": ["OLD-2"]},
            ),
        ),
    ),
)
