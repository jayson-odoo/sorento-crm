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

# The nodes a capture must carry before a world can be built from it. Each one is a value
# the turn cannot be replayed without: the message, the contact, the session it read, the
# parser's raw emission, the access answer, and the reply the turn actually sent.
REQUIRED_NODES = (
    "tf-message",
    "sorento-sub-respond-findcontact-respond",
    "get-session-vars",
    "Call 'sub-query-reformulator'",
    "check-access",
    "build-ctx",
    "crossdomain-compose",
)

# Which captures can supply a world. Every slug whose graph is a whole spine execution;
# a sub-workflow capture only has its own sub's nodes and cannot make one.
WORLD_SLUGS = ("live-spine-sorento-consume-main", "clone-spine-RS", "spine-rs-1a")

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


def _tail_input_item(ctx: dict) -> dict[str, Any]:
    """The item as it ENTERS the tail, recovered from whichever node the capture holds."""
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
    """
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

    An ANSWERED turn compresses `variables.response` to `Previous turn (<domain>): ...`,
    and that answer comes from `central-exchange` and nowhere else - so a capture without
    it cannot reproduce the reply no matter how faithful the port is. Every other lane
    needs one of the escalate / offer builders instead.
    """
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
    parse = _json(ctx["Call 'sub-query-reformulator'"]) or {}
    parser_raw = parse.get("_parser_raw")
    if not isinstance(parser_raw, dict):
        return None
    session = _json(ctx["get-session-vars"]) or {}
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
            "message": _json(ctx["tf-message"]) or {},
            "contact": _json(ctx["sorento-sub-respond-findcontact-respond"]) or {},
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
        access=_json(ctx["check-access"]) or {},
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
        return (
            "the exported parser post-processor disagrees with the body that produced this "
            f"capture on {', '.join(differing)} - the S1 routing-ladder difference already "
            "registered in `_corpus.STALE_FIXTURES`. Grading the tail against a different "
            "understanding of the turn would attribute an S1 body difference to S2"
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
    if world.expected_variables.get("picker_last_result_set") and not actual_variables.get(
        "picker_last_result_set"
    ):
        return (
            "captured before B56 (H29): the capture persisted the PREVIOUS turn's picker "
            "on a turn that built an offer of its own, which is the defect the shipping "
            "body fixes and `tests/chatbot/test_tail_units.py` pins"
        )
    return None
