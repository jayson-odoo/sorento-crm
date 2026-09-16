# The narrower: per (domain, entity kind) policy, proceed / ask roster / ask type /
# ask tier / filter optional (PLAN-chatbot-turn-rearch.md "The policy", AC-1526).
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.chatbot.turn.state import KIND_FIELD_MAP, Focus, Profile

# Which suffix an ask carries, by policy value.
_ROSTER_POLICIES = {"narrow_to_code", "must_narrow_one", "narrow_by_tier"}
_TYPE_POLICIES = {"narrow_by_type"}


def _candidates(focus: Focus, kind: str) -> list[dict[str, Any]]:
    if kind == "tier":
        return [{"raw": t, "canonical_code": t} for t in focus.tier]
    attr = KIND_FIELD_MAP.get(kind)
    if attr:
        value = getattr(focus, attr, [])
        return list(value) if isinstance(value, list) else []
    return list(focus.extra.get(kind, []))


def _choices(candidates: list[dict[str, Any]], grouping: str | None) -> int:
    """How many CHOICES these rows really are: one per family where the kind has a
    family rule, one per row otherwise."""
    if grouping != "ledger_family":
        return len(candidates)
    keys = {_family_of(c, grouping) or str(c.get("uuid") or id(c)) for c in candidates}
    return len(keys)


def _token_of(candidate: dict[str, Any]) -> str:
    """The word the customer typed for this row."""
    return str(candidate.get("raw") or candidate.get("canonical_code") or "").strip()


def _code_of(candidate: dict[str, Any]) -> str:
    """The code this row IS - the resolver's own, the token's only where it matched one."""
    return str(candidate.get("canonical_code") or candidate.get("raw") or "").strip()


def _distinct_codes(candidates: list[dict[str, Any]]) -> set[str]:
    """How many different things the carry actually names.

    A family (contract 103) is one code across several rows - `SRTWC286-SH-P` with two
    ledgers is one choice, not two - so the count that decides whether there is still a
    choice to make is the count of CODES, never of rows.
    """
    return {
        str(c.get("canonical_code") or c.get("raw") or "").strip().casefold()
        for c in candidates
        if (c.get("canonical_code") or c.get("raw"))
    }


#: Words that name a company's LEGAL FORM, not the business (`gate._LEGAL_FORM` on main,
#: spelled as words because this package may not use regular expressions).
_LEGAL_FORM_WORDS = frozenset({"SDN", "BHD"})


def _without_brackets(text: str) -> str:
    """`text` with every bracketed or parenthesised run removed.

    The ledger marker a customer row carries is always bracketed - `CHIN CHUN HARDWARE
    SDN BHD - [A/C I]`, `HANLIM TRADING (JB) SDN BHD (SRT)` - and it is the only part of
    the name that differs between the ledgers of one trading name.
    """
    out: list[str] = []
    depth = 0
    for ch in text:
        if ch in "[(":
            depth += 1
            continue
        if ch in "])":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out)


def ledger_family_key(text: str) -> str:
    """The TRADING NAME behind a customer row, as a comparison key.

    Main's `gate._cust_base`, rule for rule: upper-cased, bracketed parts dropped, the
    legal-form words dropped, everything non-alphanumeric collapsed to one space. Written
    with string operations rather than the three regexes it uses because the turn package
    may not call `re` (AC-1520).
    """
    stripped = _without_brackets(text.upper())
    cleaned = "".join(ch if ch.isalnum() else " " for ch in stripped)
    return " ".join(w for w in cleaned.split() if w not in _LEGAL_FORM_WORDS)


def _ledger_family_label(text: str) -> str:
    """What the family is CALLED: the row's own name without its ledger marker."""
    cleaned = " ".join(_without_brackets(text).split()).strip().strip("-").strip()
    return cleaned or text


def _family_of(candidate: dict[str, Any], grouping: str | None) -> str | None:
    """The key rows of one family share, or None when this kind has no family rule.

    `chatbot_entity_kinds.family_grouping` is the rule and it had no reader at all until
    now: the `customer` row has said `ledger_family` since the S0 seed, and the owner's
    hand pass 2 (item 1) read a six-line roster, one per ledger of ONE trading name, for
    "Delivery for hanlim". Ledgers of one name are one customer.
    """
    if grouping != "ledger_family":
        return None
    name = candidate.get("name") or candidate.get("label") or candidate.get("raw")
    if not name:
        return None
    key = ledger_family_key(str(name))
    return key or None


def _options(
    candidates: list[dict[str, Any]], kind: str, grouping: str | None = None
) -> list[dict[str, Any]]:
    """One numbered row per candidate.

    `uuid` is the identity the pick resolves to and `uuids` is the FAMILY that identity
    stands for (contract 103): one code with several ledgers or several rows is still one
    thing to the person reading the list, and picking it must yield every member. A
    resolver row carries both; a focus entity has only its own code, which is its own
    family of one.

    `stamp` is what the picker probe already measured about that row ("has incoming"),
    kept as its OWN field rather than folded into `label` - `label` is the resolver's
    own code (contract 28's roster lists what the resolver found, not a sentence about
    it), what a pick resolves back onto (`apply._answer_pending`'s `raw`); the renderer
    is what prints `"{label} - {stamp}"` for the customer to read.

    `code` rides beside `uuid` because they answer two different questions and a pick
    needs both (browser pass 2, turns 4 / 8 / 6): the uuid is what a tool that filters
    by id is given, the code is what a tool that filters by code is given and what the
    answer's own header names. Carrying only the uuid is what printed
    `*incoming stock* for 65514803-1609-4fe8-8b60-2e908c8f9bd4:` and asked the
    outstanding report for `product_code = <uuid>`. For a customer the code and the
    label differ (an account code nobody typed, against the name the roster printed),
    so both are kept.
    """
    built: list[dict[str, Any]] = []
    by_label: dict[str, dict[str, Any]] = {}
    for c in candidates:
        code = c.get("canonical_code") or c.get("raw")
        identity = c.get("uuid") or code
        family = c.get("uuids")
        # `name` is the resolver's human label, present only where the code is not what
        # a person would recognise (customers, `turn_runtime.candidates_by_kind`); the
        # pick still resolves through `uuid`, so the label is free to be the name.
        name = c.get("name")
        label = name or c.get("raw") or code
        stamp = c.get("stamp")
        uuids = list(family) if isinstance(family, list) and family else ([identity] if identity else [])
        # ONE LINE PER LABEL, and the line carries every row behind it (contract 103's
        # own rule, read one level up from the code): a family is one code across
        # several ledgers, and a customer is one NAME across several ledgers - browser
        # pass 3 turn 10 printed one trading name once per account and asked the customer
        # to choose between rows they cannot tell apart. The pick still yields every
        # member, because `uuids` is the union.
        family = _family_of(c, grouping)
        if family:
            # Item 1: one line per TRADING NAME. The ledgers of one customer are one
            # choice to the person reading the list ("CHIN CHUN HARDWARE SDN BHD -
            # [A/C I]" and "- [A/C II]" are the same shop), and the pick still reaches
            # every ledger because `uuids` is the union.
            key = family
            label = _ledger_family_label(str(name or label or ""))
        else:
            key = str(label).strip().casefold() if label else str(identity)
        merged = by_label.get(key)
        if merged is not None:
            for u in uuids:
                if u not in merged["uuids"]:
                    merged["uuids"].append(u)
            if stamp and not merged.get("stamp"):
                merged["stamp"] = stamp
            continue
        option: dict[str, Any] = {
            "position": len(built) + 1,
            "label": label,
            "code": code,
            "uuid": identity,
            "uuids": uuids,
            "entity_type": kind,
            "payload": {},
        }
        if name:
            option["name"] = name
        if stamp:
            option["stamp"] = stamp
        by_label[key] = option
        built.append(option)
    return built


@dataclass
class NarrowOutcome:
    ask_kind: str | None
    ask_options: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    filter_value: Any
    #: A short reason the caller traces instead of the plain `{domain}.{kind}:
    #: {policy_value}` line, when this outcome is not the policy's ordinary read
    #: (currently only "settled_carry" - see `must_narrow_one` below).
    note: str | None = None


def decide(
    *,
    kind: str,
    policy_value: str,
    focus: Focus,
    profile: Profile,
    attributes: tuple[str, ...] | list[str] = (),
    resolved_candidates: list[dict[str, Any]] | None = None,
    just_picked: bool = False,
    family_grouping: str | None = None,
) -> NarrowOutcome:
    """`attributes` is the verdict's `requested_attributes` - what the question asked ABOUT.

    A question that names its own attribute has already answered the narrower's question
    (contract 114 to 120): "which taps have a certificate" needs no "which kind of file?",
    and a count of what this contact may see needs no tier pick before it can be counted.
    So a named attribute satisfies `narrow_by_type` and silences `narrow_by_tier`, and
    changes nothing for any other policy value.
    """
    if policy_value == "not_applicable":
        return NarrowOutcome(None, [], [], None)

    candidates = _candidates(focus, kind)

    if just_picked and policy_value in ("narrow_to_code", "must_narrow_one"):
        # Owner hand pass 2, item 10: this kind was answered by a NUMBERED PICK on this
        # very turn. Both roster policies below ask about a CARRY - rows that arrived
        # from an earlier turn and might still be a choice - and neither is a rule about
        # an answer the customer has just given. Re-asking one printed the roster back
        # over its own answer (turn 0a181cfd, "All" over a ten-variant product roster).
        # `narrow_by_tier` is deliberately NOT here: its own branch already reads the
        # tier the pick just wrote and turns it into the FILTER the promotion fetch
        # needs, and short-circuiting it would send the tier through as an entity.
        return NarrowOutcome(None, [], candidates, None, note="just_picked")

    # What the RESOLVER matched for the tokens this turn named. It outranks the focus
    # rows for a narrowing decision, because a roster the customer is asked to choose
    # from has to list things that exist: "wc286" is one focus entity and ten real
    # products, and offering the customer their own typo back is not a choice.
    if resolved_candidates:
        # Owner hand pass 2, item 6, the other half (turn c45e2929, "Outstsnding DO for
        # 7445"): a token THIS message named that the resolver read as SEVERAL things is a
        # roster, whatever the domain does with it afterwards - "a product token on an order
        # ask resolves (roster when ambiguous) and filters the report; never dropped
        # silently". The measured verdict for that turn is `resolved: false, ambiguous:
        # true` over nine SRTWT7445 variants, and a filter takes ONE value, so the
        # `optional_filter` arm below quietly filtered the customer's report by whichever
        # variant the resolver happened to list first. The roster policies already ask this
        # exact question (same options, same builder); this says a FILTER has to know which
        # one it is filtering by too.
        #
        # Only for what this MESSAGE named, and only while it is unsettled: the subject a
        # conversation carries has already been answered for (contract 33 / 35, contract
        # 36's settled roster), and re-asking it on every follow-up turn is the loop the
        # sticky roster exists to avoid. `current_message` is honest for the first time here
        # (`state.focus_from_wire` down-flags what it reads back), which is what coder 12
        # measured as this rule's missing signal.
        #
        # A token that IS one of the codes it matched is not ambiguous at all (AC-1119,
        # console run 3: the owner typed `SRTWT7445`, which exists, and the report ran for
        # `SRTWT7445-LV-GM`). The typed code is the filter and the family siblings beside it
        # are noise, which is the rule the lane already applies downstream - asked here in
        # the same terms so the two cannot disagree about the same token.
        typed_now = {
            _token_of(c).casefold()
            for c in candidates
            if c.get("current_message") is True and not c.get("uuid")
        } - {""}
        typed_exactly = any(
            _code_of(row).casefold() in typed_now for row in resolved_candidates
        )
        if (
            policy_value == "optional_filter"
            and typed_now
            and not typed_exactly
            and _choices(resolved_candidates, family_grouping) > 1
        ):
            return NarrowOutcome(
                f"{kind}_pick",
                _options(resolved_candidates, kind, family_grouping),
                [],
                None,
                note="ambiguous_filter_asks",
            )
        if policy_value in _ROSTER_POLICIES and kind != "tier":
            if _choices(resolved_candidates, family_grouping) <= 1:
                # A code that resolves to exactly one thing IS narrowed to a code -
                # there is nothing left to ask. One FAMILY is one thing too (item 1):
                # six ledgers of one trading name are six rows and one customer, and a
                # picker over them asks the customer to choose between accounts they
                # cannot tell apart.
                return NarrowOutcome(None, [], list(resolved_candidates), None)
            return NarrowOutcome(
                f"{kind}_pick", _options(resolved_candidates, kind, family_grouping), [], None
            )
        candidates = list(resolved_candidates)

    if policy_value == "list_all":
        return NarrowOutcome(None, [], candidates, None)

    if policy_value in _ROSTER_POLICIES:
        if policy_value == "narrow_by_tier" and kind == "tier":
            if attributes and not candidates:
                return NarrowOutcome(None, [], [], profile.tier)
            if candidates:
                one = candidates[-1]
                value = one.get("canonical_code") or one.get("raw")
                return NarrowOutcome(None, [], [], value)
            if profile.tier:
                return NarrowOutcome(None, [], [], profile.tier)
            return NarrowOutcome("tier_pick", [], [], None)
        if policy_value == "must_narrow_one":
            # Ruling (16 Sep 2026, captain): the narrower must never re-ask for an
            # entity the conversation already settled. A focus-carried entity with a
            # `uuid` IS settled (the resolver matched it, or the customer picked it
            # off a roster) - never re-asked. SEVERAL distinct names in play at once
            # (three different customers named the same turn) is a real choice on the
            # table and still asks - unchanged from before. A SINGLE bare name with
            # nothing else to compare it against is handed to the RESOLVER this turn
            # instead of guessed at here: `resolved_candidates` above already covers
            # "the resolver found several for this one token" (asks) and "found
            # exactly one" (settles); reaching HERE with one un-uuid'd candidate means
            # there was no resolver answer for it at all this turn, so it passes
            # through, deferred, rather than an ask manufactured from a name alone.
            if candidates and all(c.get("uuid") for c in candidates):
                return NarrowOutcome(None, [], candidates, None, note="settled_carry")
            if _choices(candidates, family_grouping) > 1:
                return NarrowOutcome(
                    f"{kind}_pick", _options(candidates, kind, family_grouping), [], None
                )
            return NarrowOutcome(
                None, [], candidates, None, note="settled_carry" if candidates else None
            )
        # AC-1526's own wording: "product under incoming and purchase cost asks for
        # a code" - a NAMED candidate is asked about, not assumed. What settles it is
        # IDENTITY: a candidate carrying a `uuid` is one the resolver matched or the
        # customer picked off this very roster, and asking again for a code you
        # already hold re-prints the same question forever (contract 36's own sticky
        # roster is what feeds it back). `must_narrow_one` is handled above instead -
        # this branch is `narrow_to_code` only now.
        if candidates and not all(c.get("uuid") for c in candidates):
            return NarrowOutcome(f"{kind}_pick", _options(candidates, kind), [], None)
        if len(_distinct_codes(candidates)) > 1:
            # "narrow to a CODE" means one code. A settled carry of TEN codes (the ten
            # variants an inventory answer just listed) is still ten codes, and the
            # domain switch that keeps them - "incoming", with no product named - has to
            # offer the same roster the customer would have got for "incoming srtwc286"
            # (browser pass 2 turn 2, owner ruling 16 Sep 2026). One code carried by
            # several ledger rows is still ONE code and is never re-asked (contract 103).
            return NarrowOutcome(f"{kind}_pick", _options(candidates, kind), [], None)
        if candidates:
            # R6 (captain ruling, 16 Sep 2026): a SETTLED carry - every candidate holds
            # a uuid, the resolver matched it or the customer picked it - is the thing
            # to fetch, not nothing. Returning `[]` here left the incoming fetch with no
            # entity after the pick that narrowed it (contract 33 / 35: the follow-up
            # without repeating the product, the domain switch that keeps it).
            return NarrowOutcome(None, [], candidates, None, note="settled_carry")
        return NarrowOutcome(None, [], [], None)

    if policy_value in _TYPE_POLICIES:
        if not candidates:
            if attributes:
                return NarrowOutcome(None, [], [], attributes[0])
            return NarrowOutcome(f"{kind}_ask", [], [], None)
        return NarrowOutcome(None, [], candidates, None)

    # "optional_filter" and anything unrecognised: narrow when named, never asked.
    value = candidates[0].get("canonical_code") or candidates[0].get("raw") if candidates else None
    return NarrowOutcome(None, [], candidates, value)
