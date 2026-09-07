"""The ONE writer of what the conversation is about (AC-942 to AC-946, AC-950, AC-953).

Growth r1 slice B3. The plan measured the defect this closes: carry was decided by TWO
writers, the parser prompt's "always continue the previous turn" and ten deterministic
rules scattered through `head/output_exchange.py`, and the two disagreed. Prompt v3 gave
up the first (slice B2). This gives up the second: six named rules, applied in one place,
in one order, each with its own test and each writing one `focus` trace entry when it
fires.

**What moved here, verbatim in behaviour.** These blocks are DELETED from
`head/output_exchange.py`, not shadowed (AC-950), and their predicates are reproduced
here unchanged so the captured corpus still grades:

| deleted from `output_exchange`            | now                          |
|-------------------------------------------|------------------------------|
| the executor's `reuse` date carry          | `date_restated_only`         |
| the executor's `requested_attributes` carry| `reuse_alive` (attributes)   |
| the executor's `is_active` carry           | `reuse_alive` (is_active)    |
| `domain_reused_entityless`                 | `reuse_alive` (domain)       |
| owner ruling K rule 4 (`domain_inherited_compatible`, `bare_entity_retyped`) | `reuse_alive` (domain) |
| the `#6` switch-word override              | `domain_from_switch_word`    |
| owner ruling K rule 2 (`entities_dropped_on_topic_change`) | `reset_on_topic`  |
| `_query_brands_carried`                    | `reuse_alive` (brands)       |
| `_tier_carried`                            | `reuse_alive` (tier)         |
| the executor's axis-wise `kept_prior`      | `replace_same_axis`          |

**The diagnostics are kept, deliberately.** Every one of those blocks stamped a key on the
emission (`domain_inherited_compatible`, `_tier_carried`, ...) and 1,875 captured fixtures
grade those keys byte for byte. Moving a decision is not licence to change what the
decision RECORDS, so each rule stamps exactly what its old site stamped. The corpus is then
the proof that the move was behaviour-preserving, which is the only proof available for a
refactor this size.

**Where `focus` comes from on a session that has none.** Every live contact's stored
session, and every capture in the corpus, was written before this existed. `from_session`
therefore PROJECTS a focus out of the legacy keys - but ONLY on the one turn where the
`focus` key is entirely ABSENT, and dated to the turn that first saw it. Once the key
exists the projection never runs again, and `{}` counts as existing: `decay` writes the key
explicitly, so an empty focus means "everything aged out", and a projection that fell
through on one would rebuild the slot out of the legacy `entities` the tail is still
writing and put the TTL permanently out of reach. Measured on the first cut of this module:
the slot came back alive on the very turn it died.

**The order is the plan's**, and it is not arbitrary:

1. `replace_same_axis`  - this turn's own values win on their own axis, always.
2. `reset_on_topic`     - the customer said "something else": drop everything but the
                          tier and the brands, which are constraints on the PERSON rather
                          than on the question.
3. `reuse_alive`        - an axis this turn did not name takes the alive slot. A DEAD slot
                          never reuses, which is the whole point of slice B1.
4. `domain_from_switch_word` - a bare domain word switches the domain and keeps the
                          products, so "incoming?" after a stock answer is about the same
                          products (AC-942).
5. `date_restated_only` - the date window comes from the current message, with one
                          exception the executor has always made.
6. `anaphora_reuses`    - "it" / "that one" resolves to the alive product slot, and asks
                          when there is none.

`replace_same_axis` runs FIRST so `reuse_alive` can ask a simple question ("did this turn
name this axis?") instead of a compound one, and `reset_on_topic` runs before `reuse_alive`
so a reset cannot be undone by the very next rule.

Nothing here reads the customer's words, opens a session or calls a model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.services.chatbot import jsc, topic
from app.services.chatbot.contracts import FOCUS_SLOTS

# The entity hint that owns each single-value axis. `products` is handled apart because it
# is the one axis that legitimately holds several values at once.
_SLOT_BY_HINT: dict[str, str] = {
    "customer": "customer",
    "transporter": "transporter",
    "warehouse": "warehouse",
}

# What a topic reset does NOT clear. A tier and a brand are constraints the CUSTOMER put on
# the conversation ("I am a Cabana dealer"), not answers to the question being asked, so
# "show me another one" changes the subject and not who is asking (AC-943).
RESET_KEEPS: frozenset[str] = frozenset({"tier", "brands"})


@dataclass
class Turn:
    """Everything the six rules read, gathered once by the caller.

    A dataclass rather than nine parameters because every rule needs a different four of
    them and a positional signature would be re-ordered by the next person who adds a rule.
    `o` is the emission under post-processing and IS mutated: these rules exist to decide
    what the rest of the turn sees.
    """

    o: dict[str, Any]
    prev: dict[str, Any]
    turn_no: int
    # `explicit` and `switch_domain` are computed early in `_post_process`, off the model's
    # OWN emission, before any carry can rewrite `domain_hint`. Where they are computed is
    # load-bearing (that file says so at the point it computes them), so they are passed in
    # rather than recomputed here on a value the rules above have already moved.
    explicit: bool = False
    switch_domain: str | None = None
    # `output_exchange`'s B2' provenance test: is this entity one the previous turn's state
    # carried in, rather than one this message named? It needs four closures from that
    # function, so it arrives as a callable.
    is_carried: Callable[[Any], bool] = lambda _e: False
    # A "all dates" widen already nulled the window on purpose, so `date_restated_only`
    # must not put it back.
    date_widened: bool = False
    # `output_exchange.v3_signals`: `answers_open_question`, `anaphora`, `topic_reset`.
    # All false / empty under prompt v1 and v2, which is what makes this lane inert until
    # v3 is promoted.
    signals: dict[str, Any] = field(default_factory=dict)
    # The model's OWN emission, before any post-processing touched it. Owner ruling K rule
    # 4 tests it rather than the live object because `apply_dym_pick` re-stamps every prior
    # entity `current_message: true`, so the live object cannot say what this turn named.
    parser_raw: dict[str, Any] = field(default_factory=dict)
    latest_user_message: Any = None
    # An open question is alive this turn. `confident=false` may replace an alive slot only
    # through a picker (AC-953), and this is how a rule knows one exists.
    has_picker: bool = False
    # `reuse_domain_entityless` already ran, inside the entity executor. See that
    # function for why it cannot wait for `apply`.
    entityless_domain_reused: bool = False
    # This turn's entities came from ANSWERING an open question, so the slot they set is
    # sourced `pick`. An operator reading the trace can then tell "the customer typed it"
    # from "the customer chose it from rows we showed them", which is a different kind of
    # certainty and the reason `confident=false` is allowed through a picker (AC-953).
    answered_by_pick: bool = False


@dataclass
class Outputs:
    """The new focus, the trace entries the rules that fired wrote, and one deferral.

    `drop_carried_entities` is `reset_on_topic`'s decision about the EMISSION, held back
    rather than applied. The rule runs where all six run - before the domain blocklist,
    because the blocklist needs the final domain - but its drop has to LAND after the
    blocklist, where owner ruling K rule 2 always landed it. Applying it early is not
    neutral: the blocklist would then find the entity already gone and stamp
    `entities_filtered` / `broaden_dropped` differently, which moved 16 captured fixtures
    on those two diagnostics alone (measured, 7 Sep 2026). The decision is still taken in
    one place; only the write is deferred, and `_post_process` performs it at the exact
    line the deleted block occupied.
    """

    focus: dict[str, Any] = field(default_factory=dict)
    entries: list[dict[str, Any]] = field(default_factory=list)
    drop_carried_entities: bool = False
    # `reset_on_topic` fired on the customer's OWN "something else" this turn. The two
    # rules that would otherwise put a domain straight back read it: a reset that ends
    # with the domain it just cleared still alive has reset nothing a customer can see.
    topic_reset: bool = False


# --------------------------------------------------------------------------- #
# Reading and writing a slot
# --------------------------------------------------------------------------- #


def slot(value: Any, *, turn_no: int, source: str) -> dict[str, Any]:
    """One slot. No wall clock: see `contracts.FocusSlot` for why (D11 + AC-206)."""
    return {"value": value, "set_at_turn": int(turn_no), "source": source}


def value_of(focus: Any, name: str) -> Any:
    entry = (focus or {}).get(name)
    return entry.get("value") if isinstance(entry, dict) else None


def from_session(variables: Any, *, turn_no: int) -> dict[str, Any]:
    """The stored focus, or one PROJECTED from the legacy session keys.

    A projection rather than an empty focus, because an empty one would drop the scope of
    every conversation in flight at deploy time and of every capture in the corpus - which
    is not a migration, it is an outage the tests would have caught and the customers would
    have paid for.

    THE KEY'S PRESENCE IS THE WHOLE TEST, and `{}` is present. `decay` writes it
    explicitly, so an empty focus means "every slot aged out" - and rebuilding one from the
    legacy `entities` the tail is still writing would resurrect the slot on the turn it
    died and put the TTL permanently out of reach. Only an ABSENT key means "this session
    predates the slot", and that is the one case the legacy keys answer.

    Projected slots are dated to `turn_no`, the turn they were first SEEN. Nobody can know
    when they were really set, so they get one full TTL from first sight and age normally
    after it. Dating them earlier would be a guess; re-dating them every turn is the defect
    above. `source` is `reuse`, because that is what they are.
    """
    stored = variables if isinstance(variables, dict) else {}
    if "focus" in stored:
        existing = stored.get("focus")
        if not isinstance(existing, dict):
            return {}
        return {k: v for k, v in existing.items() if k in FOCUS_SLOTS and isinstance(v, dict)}

    projected: dict[str, Any] = {}
    at = max(0, int(turn_no))

    def put(name: str, value: Any) -> None:
        if value is None or value == [] or value == {} or value == "":
            return
        projected[name] = slot(value, turn_no=at, source="reuse")

    entities = [e for e in jsc.array(stored.get("entities")) if jsc.truthy(e)]
    put("products", [e for e in entities if jsc.lower_or_empty(jsc.get(e, "hint")) == "product"])
    for hint, name in _SLOT_BY_HINT.items():
        match = next(
            (e for e in entities if jsc.lower_or_empty(jsc.get(e, "hint")) == hint), None
        )
        put(name, match)
    put("domain", stored.get("domain_hint"))
    window = {
        "start": stored.get("date_filter_start"),
        "end": stored.get("date_filter_end"),
        "mode": stored.get("date_mode"),
    }
    put("date_window", window if (window["start"] or window["end"]) else None)
    put("attributes", [a for a in jsc.array(stored.get("requested_attributes")) if jsc.truthy(a)])
    put("tier", [t for t in jsc.array(stored.get("access_levels")) if jsc.truthy(t)])
    put("brands", [b for b in jsc.array(stored.get("query_brands")) if jsc.truthy(b)])
    return projected


# --------------------------------------------------------------------------- #
# The six rules, in the order `apply` runs them
# --------------------------------------------------------------------------- #


def replace_same_axis(focus: dict[str, Any], turn: Turn, out: Outputs) -> None:
    """A current-message entity replaces the slot of its own type, and only that slot.

    This is the executor's axis-wise `kept_prior` said as a rule: naming a product changes
    the product and leaves the customer alone. It is what makes "what about Y" after a DO
    result replace the product and keep everything else (AC-942, AC-946).

    **`confident=false` never replaces an alive slot on its own (AC-953).** The parser sets
    it when it had to cram more than one untyped concept into one `raw` because the
    customer gave nothing to split on, so acting on it silently narrows the question to
    something nobody asked. It replaces a slot that is EMPTY (there is nothing to lose) and
    it replaces one through a PICKER (the customer chose from rows we showed them); against
    an alive slot with no picker it is dropped and the alive value stands.
    """
    current = [
        e
        for e in jsc.array(turn.o.get("entities"))
        if jsc.truthy(e) and jsc.get(e, "current_message") is True
    ]
    if not current:
        return

    source = "pick" if turn.answered_by_pick else "current_message"
    products = _confident_enough(
        focus, "products", [e for e in current if _is_product(e)], turn
    )
    if products:
        _set(focus, "products", products, turn, out, rule="replace_same_axis", source=source)

    for hint, name in _SLOT_BY_HINT.items():
        named = next((e for e in current if jsc.lower_or_empty(jsc.get(e, "hint")) == hint), None)
        if named is not None and _confident_enough(focus, name, [named], turn):
            _set(focus, name, named, turn, out, rule="replace_same_axis", source=source)


def _confident_enough(
    focus: dict[str, Any], name: str, entities: list, turn: Turn
) -> list[Any]:
    """AC-953, PER ENTITY: the confident ones replace, the unconfident ones do not.

    The parser sets `confident=false` when it had to cram more than one untyped concept
    into one `raw` because the customer gave nothing to split on ("one siew srtkt72ss").
    Acting on that against a slot the customer is still talking about narrows the question
    to something nobody asked, and says nothing about having done so.

    **Per entity, not per turn**, which is the difference the review caught: "SRTWC8517 and
    one siew srtkt72ss" is one clean code and one unsplittable phrase, and dropping the
    whole replacement because of the second throws away the first as well - so the turn
    answers about the PREVIOUS product, which is worse than either reading of this one.

    Two things still let an unconfident entity through. An EMPTY slot: there is nothing to
    lose, and a guess beats having no scope at all. And an open PICKER: the value came from
    rows we showed the customer and they chose one, so there is nothing left to be unsure
    about.
    """
    if turn.has_picker or _is_empty(value_of(focus, name)):
        return list(entities)
    return [e for e in entities if jsc.get(e, "confident") is not False]


def reset_on_topic(focus: dict[str, Any], turn: Turn, out: Outputs) -> None:
    """The customer moved off the subject: drop every slot but the tier and the brands.

    TWO triggers, and they are the same event seen from two sides:

    * the parser's own `topic_reset` under prompt v3 ("another one", "别的", AC-943);
    * owner ruling K rule 2 (H66): an EXPLICIT new query, in a different domain, bringing
      its own scope, with an entity carried from the old subject still narrowing it. That
      rule's three conditions are reproduced exactly, because each one is load-bearing and
      the file it came from says why: a guessed domain reads as a change on the turns that
      are not one, a turn with no entity of its own has the carry as its only scope, and
      `topic.changed` is the shared definition of "changed the subject".

    The carried entities are dropped from the EMISSION too, with the same
    `entities_dropped_on_topic_change` diagnostic the deleted block stamped, so the corpus
    grades the move.
    """
    entities = turn.o.get("entities")
    if jsc.truthy(turn.o.get("is_menu_label")) or not jsc.is_array(entities):
        return

    this_turn = [e for e in entities if jsc.truthy(e) and not turn.is_carried(e)]
    ruling_k2 = bool(
        turn.explicit
        and len(this_turn) > 0
        and topic.changed(jsc.get(turn.prev, "domain_hint") or None, turn.o.get("domain_hint"))
    )
    said_so = turn.signals.get("topic_reset") is True
    if not (ruling_k2 or said_so):
        return

    # DEFERRED, not applied: see `Outputs.drop_carried_entities`.
    out.drop_carried_entities = True
    out.topic_reset = said_so
    if said_so and not jsc.truthy(jsc.get(turn.parser_raw, "domain_hint")):
        # THE DOMAIN GOES TOO, when the customer named none of their own. "别的" that ends
        # with `domain_hint: inventory` still alive has reset nothing anybody can see: the
        # next turn inherits it, the lane routes on it, and the reply answers about the
        # subject the customer just said they were finished with. Only under the customer's
        # OWN reset - owner ruling K rule 2 fires on an explicit NEW-domain query, where
        # the domain is the new one and must stand.
        turn.o["domain_hint"] = None
        turn.o["intent_hint"] = None
        turn.o["domain_cleared_on_topic_reset"] = True

    for name in list(focus):
        if name in RESET_KEEPS:
            continue
        # A slot this very message set is not stale: "别的, show me SRTWC8517" resets the
        # subject AND names the new one, and clearing what rule 1 just wrote would answer
        # nothing at all.
        if _set_this_turn(focus, name, turn):
            continue
        _clear(focus, name, turn, out, rule="reset_on_topic")


def drop_carried_entities_on_topic_change(o: dict[str, Any], *, is_carried: Callable[[Any], bool]) -> None:
    """`reset_on_topic`'s EMISSION half, performed where owner ruling K rule 2 performed it.

    Called by `_post_process` immediately after the domain blocklist, with the decision
    already taken by `reset_on_topic`. What is left for this pass is exactly what the
    blocklist cannot see: an entity whose hint is perfectly legal in the new domain and
    which nevertheless belongs to the old subject.
    """
    entities = o.get("entities")
    if not jsc.is_array(entities):
        return
    this_turn = [e for e in entities if jsc.truthy(e) and not is_carried(e)]
    dropped = [
        f"{jsc.get(e, 'hint')}:{jsc.get(e, 'raw')}"
        for e in entities
        if jsc.truthy(e) and is_carried(e)
    ]
    if dropped:
        o["entities"] = this_turn
        o["entities_dropped_on_topic_change"] = dropped


def reuse_domain_entityless(
    o: dict[str, Any],
    *,
    prev: Any,
    explicit: bool,
    switch_domain: Any,
    topic_reset: bool = False,
) -> bool:
    """"and the price?" inherits the domain. Called from INSIDE the entity executor.

    `reuse_alive`'s domain half, split out because it cannot wait for `apply`. The
    positional-pick block downstream (`domain_inherited_for_position`) fires only when
    `domain_hint` is still falsy, so a carry that runs after it takes the stamp off
    `domain_reused_entityless` and puts it on that block instead: measured, 5 captured
    fixtures moved on exactly those two diagnostic keys and on nothing else. The decision
    is the same one, the module is the same one, and the ordering the corpus records is
    kept.

    Reproduced predicate for predicate, INCLUDING that the diagnostic is stamped even when
    the previous state carried no domain at all: the old block set the key unconditionally
    once past its two gates, and 5 captures grade that.

    Returns whether it fired, so `apply` can write the `focus` trace entry for it.
    """
    if o.get("message_type") in ("casual", "request_for_help"):
        return False
    if explicit or switch_domain:  # a domain switch beats the carry
        return False
    if topic_reset:
        # The customer said "something else". This runs inside the entity executor, before
        # `reset_on_topic` is evaluated, so it takes the signal directly rather than
        # carrying a domain the rule two steps later is about to clear.
        return False
    prev_domain = jsc.get(prev, "domain_hint")
    prev_intent = jsc.get(prev, "intent_hint")
    o["domain_hint"] = (
        prev_domain
        if jsc.truthy(prev_domain)
        else (o.get("domain_hint") if jsc.truthy(o.get("domain_hint")) else None)
    )
    o["intent_hint"] = (
        prev_intent
        if jsc.truthy(prev_intent)
        else (o.get("intent_hint") if jsc.truthy(o.get("intent_hint")) else None)
    )
    o["domain_reused_entityless"] = True
    return True


def reuse_alive(focus: dict[str, Any], turn: Turn, out: Outputs) -> None:
    """An axis this turn did not name takes the ALIVE slot. A dead slot never reuses.

    Six axes, each with the predicate its deleted block used:

    * **domain** - two shapes of the same rule. With no entity of its own the turn is a
      continuation ("and the price?") and inherits the domain, which is
      `domain_reused_entityless`. WITH an entity but no domain of its own it is owner
      ruling K rule 4: the domain types the entity rather than the model's guess at the
      token's shape, which is what stopped a genuine product code being offered as
      "did you mean the customer?". Both are gated on the same two signals - the model
      named no decisive domain of its own, and no switch word fired.
    * **attributes** - the PERSPECTIVE of the question ("how many", "when") is an axis the
      pick turn did not name.
    * **is_active** - carried only when this turn said no status word at all.
    * **tier** and **brands** - a constraint on the asker, carried across a continuation of
      the same question. Same predicate for both, kept separate because the two axes can
      legitimately disagree (new brand, same tier).

    The date window is NOT here: it has its own rule, because "never carried" is its
    default and the continuation is the exception.
    """
    o = turn.o
    reusing = _reusing_scope(o)
    # THE SCOPE CONTINUATION, exactly as the executor drew it: the three carries below that
    # used to live inside its `reuse` arm are gated on that arm having run, and no wider.
    # `entity_op_applied` is what records it, and a menu label - which skips the executor
    # entirely - therefore carries nothing, which is also what happens today.
    continuation = o.get("entity_op_applied") == "reuse"

    if o.get("message_type") not in ("casual", "request_for_help") and not out.topic_reset:
        if not turn.explicit and not turn.switch_domain:
            _reuse_domain(focus, turn, out, continuation=continuation)

    if continuation and not _has_values(o.get("requested_attributes")):
        alive = value_of(focus, "attributes")
        if _has_values(alive):
            o["requested_attributes"] = list(alive)
            _touch(focus, "attributes", turn, out, rule="reuse_alive")

    if continuation:
        _reuse_is_active(turn)

    if not _has_values(o.get("query_brands")) and reusing:
        alive = value_of(focus, "brands")
        if _has_values(alive):
            o["query_brands"] = list(alive)
            o["_query_brands_carried"] = True
            _touch(focus, "brands", turn, out, rule="reuse_alive")

    if not _has_values(o.get("access_levels")) and reusing:
        alive = value_of(focus, "tier")
        if _has_values(alive):
            o["access_levels"] = list(alive)
            o["_tier_carried"] = True
            _touch(focus, "tier", turn, out, rule="reuse_alive")

    _drop_dead_carried_entities(focus, turn, out)


def _drop_dead_carried_entities(focus: dict[str, Any], turn: Turn, out: Outputs) -> None:
    """A DEAD slot does not reuse, and that has to reach the ENTITY LIST or it means nothing.

    This is what makes decay observable. The entity executor's `reuse` arm carries the
    previous turn's entities forward off `previous_conversation_state.entities`, which the
    tail keeps writing whatever the focus says - so a products slot that aged out at intake
    was still in scope at the lane, the reply still answered about it, and the TTL was a
    number in the trace with no effect on a single customer-visible byte. AC-940 asks for
    the reply to ASK which product; this is the line that makes it.

    Only CARRIED entities, and only where the slot is gone. An entity this message named is
    the turn's own scope; a slot that is alive is a slot the customer is still on. And the
    axes with no slot of their own (an order number, a category, a flyer) are left alone
    rather than swept up, because nothing here knows when they went stale.

    Inert on the whole captured corpus by construction: those sessions carry no `focus`
    key, so `from_session` projects one FROM these very entities and every slot is alive.
    """
    if out.drop_carried_entities:
        # `reset_on_topic` already owns this turn's carried entities, and it cleared every
        # slot two rules ago - so every carried entity now looks like one whose slot aged
        # out. Sweeping them here would label the customer's own "something else" as
        # DECAY (`entities_dropped_on_decay`, rule `reuse_alive`) and leave nothing for
        # `entities_dropped_on_topic_change` to stamp, so the trace would say the bot
        # forgot rather than that the customer moved on - and the two have different fixes
        # when an operator reads them.
        return
    entities = jsc.array(turn.o.get("entities"))
    if not entities:
        return
    kept: list[Any] = []
    dropped_by_slot: dict[str, list[Any]] = {}
    for entity in entities:
        name = _slot_of(entity)
        if (
            name is None
            or jsc.get(entity, "current_message") is True
            or value_of(focus, name) not in (None, [], {})
        ):
            kept.append(entity)
            continue
        dropped_by_slot.setdefault(name, []).append(entity)
    if not dropped_by_slot:
        return
    turn.o["entities"] = kept
    turn.o["entities_dropped_on_decay"] = [
        f"{jsc.get(e, 'hint')}:{jsc.get(e, 'raw')}"
        for group in dropped_by_slot.values()
        for e in group
    ]
    for name, group in dropped_by_slot.items():
        out.entries.append(
            {
                "slot": name,
                "before": [jsc.get(e, "canonical_code") or jsc.get(e, "raw") for e in group],
                "after": None,
                "rule": "reuse_alive",
                "source": "reuse",
            }
        )


def _slot_of(entity: Any) -> str | None:
    """Which focus slot owns this entity's axis, or None for an axis with no slot."""
    hint = jsc.lower_or_empty(jsc.get(entity, "hint"))
    if hint == "product":
        return "products"
    return _SLOT_BY_HINT.get(hint)


def domain_from_switch_word(focus: dict[str, Any], turn: Turn, out: Outputs) -> None:
    """A bare domain word switches the domain and KEEPS the product slots (AC-942).

    "incoming?" after a stock answer is a question about the same products from a different
    angle, so the domain moves and nothing else does. `output_exchange` computes which word
    fired (whole-word, case-insensitive, every remaining content token a switch word of the
    same domain, no current-message entity); this applies the answer.

    `intent_hint` is nulled exactly as the deleted block nulled it: downstream re-derives it
    from the new domain, and keeping the old one would route a shipment question through the
    stock intent.
    """
    if not turn.switch_domain:
        return
    turn.o["domain_hint"] = turn.switch_domain
    turn.o["domain_switched_by_keyword"] = turn.switch_domain
    turn.o["intent_hint"] = None
    _set(focus, "domain", turn.switch_domain, turn, out, rule="domain_from_switch_word")


def date_restated_only(focus: dict[str, Any], turn: Turn, out: Outputs) -> None:
    """The window comes from THIS message, with the one exception the executor made.

    A date is the axis customers restate most often and inherit least ("last month" then
    "for customer ABC" is still last month, but "DO for ABC" a week later is not), so the
    default is that a turn which names no date has no date. The exception is a SCOPE
    CONTINUATION - `entity_op: reuse`, the same question asked again - which is where the
    executor has always restored the previous window, and removing that would silently
    widen every "and the quantity?" follow-up to all time.

    Two things stop the exception: `broaden_axis = "date"`, where the customer asked for the
    window to be dropped and restoring it answers the opposite of the question, and a
    date-widen re-attach, which nulls the window on purpose a few lines earlier.
    """
    o = turn.o
    if jsc.lower_or_empty(o.get("broaden_axis")) == "date" or turn.date_widened:
        o["date_filter_start"] = None
        o["date_filter_end"] = None
        o["date_mode"] = None
        _clear(focus, "date_window", turn, out, rule="date_restated_only")
        return

    if jsc.truthy(o.get("date_filter_start")) or jsc.truthy(o.get("date_filter_end")):
        _set(
            focus,
            "date_window",
            {
                "start": o.get("date_filter_start"),
                "end": o.get("date_filter_end"),
                "mode": o.get("date_mode"),
            },
            turn,
            out,
            rule="date_restated_only",
        )
        return

    if o.get("entity_op") != "reuse" and o.get("entity_op_applied") != "reuse":
        return
    window = value_of(focus, "date_window")
    if not isinstance(window, dict):
        return
    if jsc.truthy(window.get("start")):
        o["date_filter_start"] = window["start"]
    if jsc.truthy(window.get("end")):
        o["date_filter_end"] = window["end"]
    if jsc.truthy(window.get("mode")):
        o["date_mode"] = window["mode"]
    _touch(focus, "date_window", turn, out, rule="date_restated_only")


def anaphora_reuses(focus: dict[str, Any], turn: Turn, out: Outputs) -> None:
    """"it" / "that one" / "那个" resolves to the alive product slot, or asks (AC-941).

    The parser sets `anaphora` and emits NO entity, because there is no value in the message
    to extract - which is the whole difference between this and a bare code. So the rule is:
    put the alive products back into the emission as this turn's scope, with
    `current_message: false`, because they are carried and every carried-entity rule
    downstream keys on exactly that flag.

    With the slot DEAD there is deliberately nothing to do. The turn then reaches the lanes
    with no product and asks which one, which is the correct answer to "how much is it?"
    three subjects later and is the behaviour AC-941 names.
    """
    if turn.signals.get("anaphora") is not True:
        return
    if any(
        jsc.truthy(e) and jsc.get(e, "current_message") is True
        for e in jsc.array(turn.o.get("entities"))
    ):
        return
    products = value_of(focus, "products")
    if not _has_values(products):
        turn.o["anaphora_unresolved"] = True
        return
    turn.o["entities"] = [{**e, "current_message": False} for e in products]
    turn.o["entity_op"] = "reuse"
    turn.o["anaphora_resolved"] = True
    _touch(focus, "products", turn, out, rule="anaphora_reuses")


# --------------------------------------------------------------------------- #
# The orchestrator
# --------------------------------------------------------------------------- #


def apply(prev_focus: dict[str, Any], turn: Turn) -> Outputs:
    """The six rules, in the plan's order. Returns the new focus and its trace entries."""
    out = Outputs(focus=dict(prev_focus or {}))
    replace_same_axis(out.focus, turn, out)
    reset_on_topic(out.focus, turn, out)
    reuse_alive(out.focus, turn, out)
    domain_from_switch_word(out.focus, turn, out)
    date_restated_only(out.focus, turn, out)
    anaphora_reuses(out.focus, turn, out)
    _record_domain(out.focus, turn, out)
    return out


def _record_domain(focus: dict[str, Any], turn: Turn, out: Outputs) -> None:
    """The domain slot takes whatever the turn CONCLUDED. Bookkeeping, not a seventh rule.

    Runs LAST on purpose. The domain is the one axis several rules can move - the model's
    own decisive term, `reuse_alive`, `domain_from_switch_word`, and the positional and
    broaden blocks in `output_exchange` that are not focus rules at all - so recording it
    at any earlier point would file the value one of them was about to overwrite. And it
    has to be recorded, because it is what the NEXT turn inherits: a slot only ever written
    by the reuse rule could never be set by the turn that first named the domain.

    A slot a rule already wrote THIS turn is left alone, so `domain_from_switch_word`'s own
    trace line stands rather than being followed by a second one saying the same thing.
    """
    domain = turn.o.get("domain_hint")
    if not jsc.truthy(domain):
        return
    if out.topic_reset and not jsc.truthy(jsc.get(turn.parser_raw, "domain_hint")):
        # `reset_on_topic` just cleared this axis and the customer named no domain of
        # their own, so anything left in `domain_hint` is a carry from the subject they
        # said they were finished with. Recording it would undo the reset one line later.
        return
    if _set_this_turn(focus, "domain", turn):
        return
    _set(
        focus,
        "domain",
        domain,
        turn,
        out,
        rule="record_domain",
        source="pick" if turn.answered_by_pick else "current_message",
    )


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _reuse_domain(focus: dict[str, Any], turn: Turn, out: Outputs, *, continuation: bool) -> None:  # noqa: ARG001
    """Owner ruling K rule 4 and `domain_reused_entityless`, as one rule over the slot.

    Reproduced predicate for predicate from the two deleted blocks, including the
    `bare_entity_turn` narrowing and the retype, because each condition there is named
    after the production turn that forced it.
    """
    from app.services.chatbot.head.output_exchange import (
        BARE_ENTITY_TYPE_BY_DOMAIN,
        DOMAIN_BLOCKED_HINTS,
        _message_is_only_these_entities,
    )

    o = turn.o
    prev_dom = value_of(focus, "domain") or None
    if not jsc.truthy(prev_dom):
        return

    current = [
        e
        for e in jsc.array(o.get("entities"))
        if jsc.truthy(e) and jsc.get(e, "current_message") is True
    ]
    if not current:
        # The entity-less continuation already ran, in the executor
        # (`reuse_domain_entityless`); all that is left here is the trace line, and only
        # when the slot it reused is alive.
        if turn.entityless_domain_reused:
            _touch(focus, "domain", turn, out, rule="reuse_alive")
        return

    raw_snapshot = turn.parser_raw or {}
    bare_type = BARE_ENTITY_TYPE_BY_DOMAIN.get(jsc.js_string(prev_dom))
    bare_entity_turn = (
        bare_type is not None
        and len(current) == 1
        # A PICK IS NEVER BARE: an entity carrying an `ordinal` was produced by a positional
        # reply against a numbered list, so the customer named a ROW, and the row already
        # knows its own type (capture parser-15129616).
        and not any(jsc.get(e, "ordinal") is not None for e in current)
        and not jsc.truthy(jsc.get(raw_snapshot, "domain_hint"))
        and not jsc.truthy(jsc.get(raw_snapshot, "intent_hint"))
        and _message_is_only_these_entities(turn.latest_user_message, current)
    )
    blocked_for_prev = set(DOMAIN_BLOCKED_HINTS.get(prev_dom, []))
    compatible = bare_entity_turn or all(
        jsc.lower_or_empty(jsc.get(e, "hint")) not in blocked_for_prev for e in current
    )
    if not compatible:
        o["domain_inherit_blocked"] = prev_dom  # topic switch, this turn's domain kept
        return

    o["domain_hint"] = prev_dom
    prev_intent = jsc.get(turn.prev, "intent_hint")
    o["intent_hint"] = (
        prev_intent
        if jsc.truthy(prev_intent)
        else (o.get("intent_hint") if jsc.truthy(o.get("intent_hint")) else None)
    )
    o["domain_inherited_compatible"] = True
    if bare_entity_turn:
        # RETYPE, in place: `current` holds the same dicts `o["entities"]` does, so the
        # blocklist, the axis map and the resolver all see the domain's own type rather
        # than the guessed one. Stamped only when the type actually MOVED.
        retyped = False
        for e in current:
            if jsc.lower_or_empty(jsc.get(e, "hint")) != bare_type:
                e["hint"] = bare_type
                retyped = True
        if retyped:
            o["bare_entity_retyped"] = bare_type
    _touch(focus, "domain", turn, out, rule="reuse_alive")


def _reuse_is_active(turn: Turn) -> None:
    """Carried only when this turn said no status word at all.

    `is_active` is NOT a focus slot, and that is a decision rather than an omission: the
    plan names nine axes and this is not one of them, because "discontinued" is a property
    of the RECORDS being asked about rather than of what the conversation is about. It
    therefore reads the previous state directly and ages with the conversation as a whole.
    The trigger for giving it a slot is a measured turn where it should have decayed on its
    own and did not.
    """
    o = turn.o
    if _norm(o.get("is_active")) is not None:
        return
    prev = turn.prev
    if jsc.has(prev, "is_active") and _norm(jsc.get(prev, "is_active")) is not None:
        o["is_active"] = jsc.get(prev, "is_active")


def _reusing_scope(o: dict[str, Any]) -> bool:
    """"this turn continues the previous scope" - the predicate the two carries shared."""
    entities = jsc.array(o.get("entities"))
    return o.get("entity_op") == "reuse" or (
        len(entities) > 0
        and not any(jsc.truthy(e) and jsc.get(e, "current_message") is True for e in entities)
    )


def _has_values(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _is_empty(value: Any) -> bool:
    """Nothing in the slot. `[]` and `{}` count, the same way `decay` counts them."""
    return value is None or value == [] or value == {} or value == ""


def _is_product(entity: Any) -> bool:
    return jsc.lower_or_empty(jsc.get(entity, "hint")) == "product"


def _norm(value: Any) -> Any:
    return jsc.norm(value)


def _set_this_turn(focus: dict[str, Any], name: str, turn: Turn) -> bool:
    entry = focus.get(name)
    return isinstance(entry, dict) and int(entry.get("set_at_turn") or -1) == int(turn.turn_no)


def _set(
    focus: dict[str, Any],
    name: str,
    value: Any,
    turn: Turn,
    out: Outputs,
    *,
    rule: str,
    source: str = "current_message",
) -> None:
    before = value_of(focus, name)
    if before == value and _set_this_turn(focus, name, turn):
        return
    focus[name] = slot(value, turn_no=turn.turn_no, source=source)
    out.entries.append(
        {"slot": name, "before": before, "after": value, "rule": rule, "source": source}
    )


def _touch(focus: dict[str, Any], name: str, turn: Turn, out: Outputs, *, rule: str) -> None:
    """Record a REUSE without moving the slot's age.

    Deliberate, and the difference matters: a slot the customer keeps silently benefiting
    from is not a slot they keep restating. Refreshing `set_at_turn` on every reuse would
    make the TTL unreachable and give back exactly the unbounded carry slice B1 removed.
    """
    entry = focus.get(name)
    if not isinstance(entry, dict):
        return
    entry["source"] = "reuse"
    out.entries.append(
        {
            "slot": name,
            "before": entry.get("value"),
            "after": entry.get("value"),
            "rule": rule,
            "source": "reuse",
        }
    )


def _clear(focus: dict[str, Any], name: str, turn: Turn, out: Outputs, *, rule: str) -> None:
    if name not in focus:
        return
    before = value_of(focus, name)
    focus.pop(name, None)
    out.entries.append(
        {"slot": name, "before": before, "after": None, "rule": rule, "source": "reuse"}
    )
