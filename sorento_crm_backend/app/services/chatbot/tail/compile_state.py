"""Port of `compile-current-state.js` (1,948 lines): the reply and the memory (AC-202).

This is the node that decides what the customer reads and what the bot remembers. Every
session key on the turn path is written here, in one object, and every carry lifecycle
(the did-you-mean offer, the disambiguation picker, the tier menu, the routing axes) is a
first-match-wins ladder inside it.

Three properties of the JS are load-bearing and are reproduced deliberately:

* **The output object is built from SCRATCH, never spread from the input.** The upstream
  `dym-transform-partial` appends fourteen harness control keys to the item, and
  `save-session-vars` used to PUT the WHOLE item, so a spread would persist harness keys
  into real customer sessions. `SessionVars(extra="forbid")` is the CRM's structural
  version of the same guarantee (H15, AC-203) and it is enforced on the write path.
* **`undefined` is an ABSENT KEY, not a null.** `variables.query_scope` is simply missing
  on a turn where the parser emitted no scope, and the captured fixtures record that. The
  port carries `jsc.UNDEFINED` through and `strip_undefined` drops it at the boundary,
  which is exactly what `JSON.stringify` does.
* **First match wins, in the written order.** The eight dym-offer rules (AC-204) and the
  five-way roster ladder are ordered ladders, not independent predicates; re-ordering them
  changes which list a bare "2" resolves against next turn.

**No new text sniffing.** D11 forbids matching the customer's words or a previous reply
outside the parser. The two places the JS did are the ones R3 replaces: this node's own
`offeredEscalation` regex over `userResponse` (which reads THIS turn's freshly composed
text, not a remembered one, so it is a local predicate rather than a state read) and
`crossdomain-compose`'s `isAnswered`. Both keep their reproduced form for parity, and
`pending.py` writes the marker beside them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.services.chatbot import jsc
from app.services.chatbot.tail import pending as pending_marker

UNDEFINED = jsc.UNDEFINED

# U+2014, written as an escape rather than as the character itself. The repo's own hard
# rule forbids the byte in source (and the pre-push guard enforces it), but this node both
# EMITS one on the merge arm and FOLDS every one it finds - the JS does, so the port must,
# or the two disagree on a customer-visible string.
EM_DASH = "\u2014"


@dataclass
class CompiledState:
    """The node's output plus the two facts the next stage needs as VALUES, not as text.

    `item` is what n8n's `compile-current-state` emits, byte for byte, and it is what the
    replay corpus grades. The other two exist so `crossdomain-compose` never has to read
    a reply back with a regex (D11, R3):

    * `answered_domain` is the domain the business-summary arm stamped, or None. The JS
      asked "does the state start with `Previous turn (`" of the state it had just
      written; this is the same question answered from the branch that wrote it.
    * `offer_open` is whether this turn's reply leaves an escalation offer open. It is
      what `pending.derive` keys on, and compose re-derives the marker when IT appends
      the phrase.
    """

    item: dict[str, Any]
    answered_domain: str | None = None
    offer_open: bool = False
    _notes: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# JSON-boundary helpers
# --------------------------------------------------------------------------- #


def strip_undefined(value: Any) -> Any:
    """What `JSON.stringify` does to `undefined`: drop the key, null the array slot."""
    if isinstance(value, dict):
        return {k: strip_undefined(v) for k, v in value.items() if v is not UNDEFINED}
    if isinstance(value, list):
        return [None if v is UNDEFINED else strip_undefined(v) for v in value]
    return value


def _u(obj: Any, key: str) -> Any:
    """`obj.key` keeping `undefined` distinct from `null` (a JSON trip loses the key)."""
    if not jsc.has(obj, key):
        return UNDEFINED
    return obj.get(key)


def _concat(text: Any, suffix: str) -> str:
    """JS `+=` on a possibly-undefined string. `undefined + "x"` is `"undefinedx"`."""
    return jsc.js_string(text) + suffix


def sanitize_em_dash(value: Any) -> Any:
    """Deep-walk and fold every U+2014 to a hyphen (captain hard rule, 2026-08-22).

    Dynamic text (LLM, CRM, RAG sourced) must never carry an em-dash to a customer. The
    walk is over the FINAL payload, so it covers `user_response`, `quick_reply` and every
    persisted `variables.*` string no matter which arm produced it.
    """
    if isinstance(value, dict):
        for key, inner in value.items():
            if isinstance(inner, str):
                value[key] = inner.replace(EM_DASH, "-")
            elif isinstance(inner, (dict, list)):
                sanitize_em_dash(inner)
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            if isinstance(inner, str):
                value[index] = inner.replace(EM_DASH, "-")
            elif isinstance(inner, (dict, list)):
                sanitize_em_dash(inner)
    return value


def seal(patch: Mapping[str, Any]) -> dict[str, Any]:
    """RS-3 half H2: the `reply` contract, derived from ONE object.

    `session_patch` is the item VERBATIM, which is load-bearing: `save-session-vars` PUTs
    the whole thing, so a `variables`-only patch would change a production request body.
    `text` / `quick_replies` are SEALED FROM that same object at this single point, so
    the two views can never drift; every later writer edits the patch and re-seals.
    """
    return {
        "text": _u(patch, "user_response"),
        "quick_replies": _u(patch, "quick_reply"),
        "session_patch": patch,
    }


# --------------------------------------------------------------------------- #
# Small pure helpers lifted out of the node body
# --------------------------------------------------------------------------- #

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _is_uuid(value: Any) -> bool:
    return bool(_UUID_RE.match(jsc.js_string(value if jsc.truthy(value) else "")))


def _tok_key(value: Any) -> str:
    """`_tokKey`: separators stripped, lower-cased. The join key for token -> entity."""
    return re.sub(r"[-\s]+", "", jsc.nullish_str(value, "")).lower()


def _norm(value: Any) -> str:
    return jsc.nullish_str(value, "").strip().lower()


def _and_list(parts: list[str]) -> str:
    """`_and`: "a", "a and b", "a, b and c"."""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _pretty_key(key: Any) -> str:
    return jsc.js_string(key).replace("_", " ").strip()


def _pretty_team(team: Any) -> str:
    """DISPLAY ONLY: underscores to spaces at the interpolation, never at the source."""
    return jsc.js_string("" if team is None else team).replace("_", " ").strip()


def _prettify_type(value: Any) -> str:
    """A snake_case / kebab entity type as a display word; a plain lowercase word passes."""
    s = jsc.nullish_str(value, "").strip()
    if not s:
        return ""
    if not re.search(r"[_-]", s) and s == s.lower():
        return s
    return re.sub(r"[_-]+", " ", s).strip().lower()


def _prev_variables(ctx: Mapping[str, Any]) -> dict[str, Any]:
    """`(s && s.session_vars && s.session_vars.variables) || (s && s.variables) || {}`."""
    session = jsc.get(ctx, "session")
    nested = jsc.get(jsc.get(session, "session_vars"), "variables")
    if jsc.truthy(nested):
        return nested
    flat = jsc.get(session, "variables")
    if jsc.truthy(flat):
        return flat
    return {}


def _field_value(item: Any, label_wanted: str) -> Any:
    field = jsc.find(
        jsc.get(item, "fields"),
        lambda x: jsc.lower_or_empty(jsc.get(x, "label")) == label_wanted.lower(),
    )
    return jsc.get(field, "value") if field is not None else None


def reconcile_entities(parser_entities: Any, resolver_json: Any) -> Any:
    """The resolver checked against real data, so its `entity_type` wins over the hint.

    Two narrowing rules are safety properties rather than tidiness. A token that named
    ONE thing may be pinned to it; a token that named several is still a FAMILY, and
    taking `matches[0]` is what silently narrowed a whole-family search to one variant
    the customer never chose (exec 13733614 into 13733666). And when several matches
    disagree about `entity_type`, guessing which the resolver meant is the same mistake
    one field over, so the parser's own hint is left alone.
    """
    if not jsc.is_array(parser_entities):
        return parser_entities if jsc.truthy(parser_entities) else []

    resolutions = jsc.array(jsc.get(resolver_json, "resolutions"))
    intersection = jsc.array(jsc.get(resolver_json, "intersection"))

    out = []
    for pe in parser_entities:
        raw = _norm(jsc.get(pe, "raw"))
        match = None
        family_count = 0

        res = jsc.find(
            resolutions,
            lambda r, raw=raw: _norm(jsc.get(r, "token") or jsc.get(r, "query")) == raw,
        )
        res_matches = jsc.array(jsc.get(res, "matches"))
        if res is not None and len(res_matches) > 0:
            family_count = len(res_matches)
            match = res_matches[0] if family_count == 1 else None

        if match is None and not family_count and len(intersection) > 0:
            match = jsc.find(
                intersection,
                lambda m, raw=raw: _norm(jsc.get(m, "canonical_code")) == raw
                or _norm(jsc.get(jsc.get(m, "display"), "product_name")) == raw,
            )

        if match is not None and jsc.truthy(jsc.get(match, "entity_type")):
            out.append(
                {
                    **pe,
                    "hint": jsc.get(match, "entity_type"),
                    "canonical_code": jsc.get(match, "canonical_code"),
                }
            )
            continue
        if family_count > 1:
            types = {
                jsc.get(m, "entity_type") for m in res_matches if jsc.truthy(jsc.get(m, "entity_type"))
            }
            hint = next(iter(types)) if len(types) == 1 else jsc.get(pe, "hint")
            # `pe.canonical_code ?? null`, never a bare null: the parser authors codes of
            # its own (`attachment_type: "gambar"` -> `"photo"`) and `output_exchange`
            # rewrites `e.raw` from them before the resolver sees the token.
            code = jsc.get(pe, "canonical_code")
            out.append({**pe, "hint": hint, "canonical_code": code if code is not None else None})
            continue
        out.append(pe)
    return out


# --------------------------------------------------------------------------- #
# The node
# --------------------------------------------------------------------------- #


def compile_current_state(  # noqa: PLR0912, PLR0915 - a line-by-line port; splitting it would hide the ladder
    item: Mapping[str, Any],
    ctx: Mapping[str, Any],
    *,
    resolved: Any = None,
    gate: Any = None,
    execution_id: str = "",
) -> dict[str, Any]:
    """`compile-current-state.js`. Returns `{reply: {text, quick_replies, session_patch}}`.

    `resolved` and `gate` are `sub-output`'s `resolve-entity` / `disallowed-entity-gate`
    carriers, i.e. the trigger's own nullable fields. `execution_id` stands in for
    `$execution.id`, which the dym offer stamps as its identity - the CRM's turn id.
    """
    qf = jsc.get(jsc.get(ctx, "parse"), "output") or {}
    outcome = jsc.get(item, "outcome") or {}
    gate_ran = gate is not None
    gate_json = gate if isinstance(gate, dict) else {}
    resolver_json = resolved if isinstance(resolved, dict) else {}
    prev = _prev_variables(ctx)

    # ---- the reply ladder ------------------------------------------------- #
    response: Any = UNDEFINED
    include_response = True
    is_escalate_branch = True
    quick_reply: Any = UNDEFINED
    manual_response = False

    cat = outcome.get("escalate-catalog")
    mem = outcome.get("build-cs-member-offer")
    suggest_raw = outcome.get("build-suggest-offer")
    sug = suggest_raw if (jsc.truthy(suggest_raw) and jsc.get(suggest_raw, "suggest_offer") is True) else None
    ideate = outcome.get("build-ideate-reply")
    # Delta 4: a date-suggest AND a CS member roster both present means show BOTH.
    merge = bool(jsc.truthy(sug) and jsc.truthy(mem))

    if jsc.truthy(ideate):
        response = _u(ideate, "response")
        manual_response = True
        include_response = True
        is_escalate_branch = True
    elif merge:
        rows = jsc.array(jsc.get(mem, "cs_last_result_set"))
        mem_companies: set[Any] = set()
        for m in rows:
            ids = jsc.get(m, "company_ids")
            ids = ids if (jsc.is_array(ids) and len(ids) > 0) else [jsc.get(m, "company_id") or None]
            for i in ids:
                mem_companies.add(i or None)
        routing_companies = jsc.get(mem, "routing_companies")
        multi_co = jsc.is_array(routing_companies) and len(routing_companies) > 1
        # EVERY ROW PRINTS, UNCONDITIONALLY: one line per roster row, in roster order,
        # with the company named inline when the turn spans more than one. The
        # grouped-by-header form this replaced dropped rows, so a customer was invited to
        # pick a number they were never shown.
        lines = []
        for m in rows:
            companies = jsc.get(m, "companies")
            label = (
                companies
                if (jsc.is_array(companies) and len(companies) > 0)
                else ([jsc.get(m, "company_name")] if jsc.truthy(jsc.get(m, "company_name")) else [])
            )
            idx = jsc.get(m, "idx")
            text = jsc.get(m, "label")
            lines.append(
                f"{jsc.js_string(idx)}. {jsc.js_string(text)} ({' / '.join(jsc.js_string(x) for x in label)})"
                if (multi_co and label)
                else f"{jsc.js_string(idx)}. {jsc.js_string(text)}"
            )
        if multi_co:
            for p in jsc.array(routing_companies):
                if jsc.truthy(p) and jsc.truthy(jsc.get(p, "company_name")) and (
                    jsc.get(p, "company_id") or None
                ) not in mem_companies:
                    lines.append(
                        f"[ {jsc.js_string(jsc.get(p, 'company_name'))}: no customer-service "
                        f"members are configured {EM_DASH} omitted. ]"
                    )
        picker = "\n".join(lines)
        multi_close = jsc.get(mem, "cs_multi_close")
        close = (
            multi_close
            if (multi_co and isinstance(multi_close, str) and multi_close)
            else "Or just reply 'yes' and we'll assign automatically."
        )
        offer_company = jsc.get(mem, "cs_offer_company")
        suggest_response = jsc.get(sug, "suggest_response")
        if isinstance(offer_company, str) and offer_company and isinstance(suggest_response, str):
            sug_text: Any = re.sub(
                r"(would you like me to escalate to )((?:[a-z0-9-]+ )*[a-z0-9-]+ team\?)",
                lambda m: f"{m.group(1)}*{offer_company}* {m.group(2)}",
                suggest_response,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            sug_text = suggest_response
        response = (
            f"{jsc.js_string(sug_text)}\n\nTo escalate, choose who to route to. "
            f"Reply the number or name:\n{picker}\n\n{jsc.js_string(close)}"
        )
        manual_response = True
        include_response = True
        is_escalate_branch = True
    elif jsc.truthy(sug):
        response = _u(sug, "suggest_response")
        manual_response = True
        include_response = True
        is_escalate_branch = True
    elif jsc.truthy(mem):
        response = _u(mem, "response")
        manual_response = jsc.get(mem, "manualResponse")
        include_response = jsc.get(mem, "includeResponse")
        is_escalate_branch = True
    elif jsc.truthy(cat):
        response = _u(cat, "response")
        manual_response = jsc.get(cat, "manualResponse")
        include_response = jsc.get(cat, "includeResponse")
        is_escalate_branch = True
    elif jsc.truthy(outcome.get("central-exchange")):
        response = _u(outcome.get("central-exchange"), "response")
        is_escalate_branch = False

    access_choice = outcome.get("access-level-choice-message")
    if jsc.truthy(access_choice):
        offered = jsc.get(access_choice, "quick_reply")
        quick_reply = offered if len(offered or []) > 0 else None
    if jsc.truthy(sug):
        quick_reply = jsc.get(sug, "suggest_quick_reply")

    def get_result_obj() -> Any:
        if jsc.truthy(outcome.get("central-exchange")):
            return outcome.get("central-exchange")
        if jsc.truthy(outcome.get("validator")):
            return outcome.get("validator")
        if gate_ran:
            return gate_json
        # RS-3 leak-stop: `build-outcome` FORWARDS this item and adds one key, so
        # `outcome` is stripped back off here and the returned bytes are what they were
        # before the hub existed.
        if not jsc.truthy(item):
            return {}
        return {k: v for k, v in item.items() if k != "outcome"}

    user_response: Any = response if include_response else UNDEFINED
    last_result_set: Any = []

    # ---- the business summary (the parser-facing compressed `response`) ---- #
    result_obj = get_result_obj()
    items_list = (
        jsc.get(result_obj, "items")
        if jsc.is_array(jsc.get(result_obj, "items"))
        else jsc.get(result_obj, "answers")
        if jsc.is_array(jsc.get(result_obj, "answers"))
        else jsc.get(result_obj, "compatible_entities")
        if jsc.is_array(jsc.get(result_obj, "compatible_entities"))
        else []
    )
    domain = jsc.get(qf, "domain_hint") or "result"
    if jsc.get(result_obj, "require_specific") is True and jsc.is_array(
        jsc.get(result_obj, "compatible_entities")
    ):
        # The picker roster mirrors what the gate rendered. It was product-only because
        # the gate's choose-list was; the customer-ambiguity picker renders CUSTOMER rows
        # too, and filtering them out left the roster empty so the positional reply had
        # nothing to resolve.
        items_list = [
            e for e in items_list if jsc.js_string(jsc.get(e, "entity_type")).lower() in ("product", "customer")
        ]
    answered_domain: str | None = None
    if jsc.get(qf, "message_type") == "business_query" and not jsc.truthy(manual_response):
        # The one arm that writes `Previous turn (<domain>): ...`. Recording the domain
        # HERE is what lets `crossdomain-compose` skip re-reading the reply.
        answered_domain = jsc.js_string(domain)
        if len(items_list) == 0:
            response = f"Previous turn ({jsc.js_string(domain)}): no results."
        else:
            indexed = []
            for i, it in enumerate(items_list):
                fields = jsc.array(jsc.get(it, "fields"))
                first_field = fields[0] if fields else None
                # label priority covers BOTH shapes: envelope item (title / fields) and
                # compatible_entity (code / canonical_code / product_name)
                label = (
                    jsc.get(it, "title")
                    or jsc.get(it, "code")
                    or jsc.get(it, "canonical_code")
                    or jsc.get(jsc.get(it, "display"), "product_name")
                    or _field_value(it, "Form Name")
                    or _field_value(it, "Promotion Name")
                    or _field_value(it, "Product")
                    or (jsc.get(first_field, "value") if first_field is not None else None)
                    or f"item {i + 1}"
                )
                indexed.append(
                    {
                        "idx": i + 1,
                        "uuid": jsc.get(it, "uuid") or jsc.get(it, "id") or None,
                        "label": jsc.js_string(label).replace("*", "").strip(),
                        "entity_type": jsc.get(it, "entity_type") or None,
                        "product": _field_value(it, "Product") or jsc.get(it, "product") or jsc.get(it, "code") or None,
                        "attachment_type": jsc.get(it, "attachmentType") or jsc.get(it, "attachment_type") or None,
                        "filename": jsc.get(it, "filename") or None,
                    }
                )
            what = indexed[0]["attachment_type"] or "records"
            response = (
                f"Previous turn ({jsc.js_string(domain)}): returned {len(items_list)} {jsc.js_string(what)}"
            )
            last_result_set = indexed

    reconciled_entities = reconcile_entities(jsc.get(qf, "entities"), resolver_json)

    # ---- the roster ladder: which offer owns `last_result_set` ------------- #
    if merge:
        last_result_set = jsc.array(jsc.get(mem, "cs_last_result_set"))
    elif jsc.truthy(sug):
        last_result_set = jsc.array(jsc.get(sug, "suggest_last_result_set"))
    elif jsc.truthy(mem):
        last_result_set = jsc.array(jsc.get(mem, "cs_last_result_set"))
    r_obj = get_result_obj()
    is_disambig = bool(
        jsc.truthy(r_obj)
        and jsc.get(r_obj, "require_specific") is True
        and jsc.is_array(jsc.get(r_obj, "compatible_entities"))
        and len(jsc.get(r_obj, "compatible_entities")) > 0
    )
    # promo-picker builds its own roster and the parser's ALL handler is gated on
    # `selection_context === 'suggest_offer'`. LOWEST precedence on purpose: member,
    # suggest and cs rosters must still win a stray "2".
    promo_raw = outcome.get("promo-picker")
    promo = (
        promo_raw
        if (
            jsc.truthy(promo_raw)
            and jsc.is_array(jsc.get(promo_raw, "suggest_last_result_set"))
            and len(jsc.get(promo_raw, "suggest_last_result_set")) > 0
        )
        else None
    )
    if not merge and not jsc.truthy(sug) and not jsc.truthy(mem) and promo is not None:
        last_result_set = jsc.get(promo, "suggest_last_result_set")
    # The tier ask persists the TIER roster so the parser resolves "2" / "all" to tier
    # tokens next turn. D4: the tier itself is NEVER persisted, only the offer roster,
    # and only for this one round trip.
    tier_raw = outcome.get("access-level-choice-message")
    tier = (
        tier_raw
        if (
            jsc.truthy(tier_raw)
            and jsc.get(tier_raw, "tier_offer") is True
            and jsc.is_array(jsc.get(tier_raw, "tier_last_result_set"))
            and len(jsc.get(tier_raw, "tier_last_result_set")) > 0
        )
        else None
    )
    if not merge and not jsc.truthy(sug) and not jsc.truthy(mem) and promo is None and tier is not None:
        last_result_set = jsc.get(tier, "tier_last_result_set")
    selection_context = (
        "member_offer"
        if merge
        else "suggest_offer"
        if jsc.truthy(sug)
        else (jsc.get(mem, "selection_context") or None)
        if jsc.truthy(mem)
        else "suggest_offer"
        if promo is not None
        else "tier_offer"
        if tier is not None
        else "disambiguation"
        if is_disambig
        else None
    )

    # ---- N-1a: say WHAT matched, on spec answers only --------------------- #
    user_response = _matched_on_line(
        user_response,
        qf=qf,
        resolver_json=resolver_json,
        gate_ran=gate_ran,
        gate_json=gate_json,
        is_escalate_branch=is_escalate_branch,
        include_response=include_response,
        manual_response=manual_response,
        last_result_set=last_result_set,
    )

    # ---- N-2: name the qualifier we could not filter by ------------------- #
    user_response = _unmet_spec_line(
        user_response,
        qf=qf,
        ctx=ctx,
        resolver_json=resolver_json,
        is_escalate_branch=is_escalate_branch,
        include_response=include_response,
        manual_response=manual_response,
        last_result_set=last_result_set,
    )

    # ---- friendly domain disclaimers -------------------------------------- #
    answered_plain = (
        not is_escalate_branch
        and jsc.truthy(include_response)
        and isinstance(user_response, str)
        and user_response.strip() != ""
        and jsc.is_array(last_result_set)
        and len(last_result_set) > 0
    )
    if answered_plain:
        domain_hint = jsc.get(qf, "domain_hint")
        if domain_hint == "master_products":
            user_response += (
                "\n\nP/S: if the spec you're after isn't shown above, just ask me for the "
                "*product catalogue* and I'll pull it up for you \U0001f60a"
            )
        elif domain_hint == "resource_attachment":
            ents = reconciled_entities if jsc.is_array(reconciled_entities) else jsc.array(jsc.get(qf, "entities"))
            wants_catalogue = any(
                re.search(r"catalog|katalog", jsc.js_string(jsc.get(e, "raw") if jsc.truthy(jsc.get(e, "raw")) else ""), re.IGNORECASE)
                for e in ents
            )
            if wants_catalogue:
                user_response += (
                    "\n\nTip: looking for a specific detail like material or finish? Search "
                    "the *product code* inside the catalogue and you'll find all its "
                    "attributes there \U0001f44d"
                )

    # ---- #3 zerostock itemize --------------------------------------------- #
    domain_hint = jsc.get(qf, "domain_hint")
    if (
        domain_hint in ("inventory", "incoming")
        and jsc.get(qf, "message_type") == "business_query"
        and not jsc.truthy(manual_response)
        and not is_escalate_branch
        and jsc.is_array(last_result_set)
        and len(last_result_set) > 0
        and isinstance(user_response, str)
        and user_response.strip() != ""
    ):
        zs_json = outcome.get("crossdomain-zeroset")
        if jsc.truthy(zs_json):
            zs = jsc.get(zs_json, "_xd") or {}
            returned_codes = jsc.array(jsc.get(zs, "returned_codes"))
            if len(returned_codes) > 0:
                missing = [
                    jsc.get(m, "code") for m in jsc.array(jsc.get(zs, "missing")) if jsc.truthy(jsc.get(m, "code"))
                ]
                if len(missing) > 0:
                    shown = missing[:10]
                    # DOMAIN-AWARE NOUN: this line fires on inventory AND incoming turns
                    # and used to say "stock records" on an ETA turn, one line above a
                    # block reporting real on-hand stock.
                    noun = "incoming" if domain_hint == "incoming" else "stock"
                    user_response += (
                        f"\n\nNo {noun} records found for: "
                        f"{', '.join(jsc.js_string(c) for c in shown)}."
                    )

    # ---- the customer's spelling: ONE token -> entity map ------------------ #
    # `resolutions[].token` is NOT what the customer typed: the resolver is sent
    # `canonical_code ?? raw`, strips separators for products, and the CRM rewrites what
    # it echoes. Every renderer that quotes a token back maps it through here, or the
    # reply hands the customer a code they never wrote.
    ent_by_tok: dict[str, Any] = {}
    for ent in jsc.array(jsc.get(qf, "entities")):
        ent_key = _tok_key(jsc.get(ent, "raw"))
        if ent_key and ent_key not in ent_by_tok:
            ent_by_tok[ent_key] = ent
        code_key = _tok_key(jsc.get(ent, "canonical_code"))
        if code_key and code_key not in ent_by_tok:
            ent_by_tok[code_key] = ent

    def ent_of_tok(token: Any) -> Any:
        return ent_by_tok.get(_tok_key(token))

    def raw_of_tok(token: Any) -> Any:
        e = ent_of_tok(token)
        raw = jsc.get(e, "raw") if e is not None else None
        return raw if jsc.truthy(raw) else token

    # ---- the partial-miss did-you-mean block ------------------------------ #
    dym_last_result_set: Any = None
    partial_offer: Any = None
    user_response, response, dym_last_result_set, partial_offer = _partial_dym_block(
        user_response,
        response,
        qf=qf,
        outcome=outcome,
        resolver_json=resolver_json,
        gate_ran=gate_ran,
        gate_json=gate_json,
        get_result_obj=get_result_obj,
        is_escalate_branch=is_escalate_branch,
        include_response=include_response,
        manual_response=manual_response,
        last_result_set=last_result_set,
        ent_of_tok=ent_of_tok,
        raw_of_tok=raw_of_tok,
        execution_id=execution_id,
    )

    # ---- the did-you-mean offer lifecycle (AC-204: eight rules, in order) -- #
    sug_offer = jsc.get(sug, "dym_offer") if jsc.truthy(sug) else None
    new_offer = (
        sug_offer
        if (
            jsc.truthy(sug_offer)
            and jsc.is_array(jsc.get(sug_offer, "candidates"))
            and len(jsc.get(sug_offer, "candidates")) > 0
        )
        else (partial_offer or None)
    )
    prev_offer_raw = jsc.get(prev, "dym_offer")
    prev_offer = prev_offer_raw if isinstance(prev_offer_raw, dict) else None
    pick_applied = jsc.get(qf, "dym_pick_applied") is True
    escalation = jsc.get(qf, "escalation")
    # A human owns the thread once escalation is confirmed OR a specific member resolved.
    escalated = bool(
        jsc.truthy(escalation)
        and (
            jsc.get(escalation, "is_escalation_confirmation") is True
            or jsc.truthy(jsc.get(escalation, "preferred_assignee_id"))
        )
    )
    answered = jsc.is_array(last_result_set) and len(last_result_set) > 0
    if new_offer:  # 1. fresh offer -> REPLACE
        dym_offer: Any = {**new_offer, "ttl": 3, "picked": []}
    elif not prev_offer:  # nothing to carry
        dym_offer = None
    elif (
        jsc.truthy(jsc.get(qf, "domain_hint"))
        and jsc.truthy(jsc.get(prev_offer, "domain"))
        and jsc.get(qf, "domain_hint") != jsc.get(prev_offer, "domain")
    ):
        dym_offer = None  # 2. domain switch (null never kills: a bare-code pick emits null)
    elif escalated:
        dym_offer = None  # 3. escalation committed -> DIE
    elif pick_applied:  # 4. pick applied -> RETAIN
        picked = list(jsc.array(jsc.get(prev_offer, "picked")))
        pick_code = jsc.get(qf, "dym_offer_pick_code")
        if jsc.truthy(pick_code) and pick_code not in picked:
            picked.append(pick_code)
        dym_offer = {**prev_offer, "ttl": 3, "picked": picked}
    elif answered:
        dym_offer = None  # 5. answered, no pick -> DIE
    elif not (jsc.js_number(jsc.get(prev_offer, "ttl")) > 1):
        dym_offer = None  # 6. TTL exhausted
    else:
        dym_offer = {**prev_offer, "ttl": jsc.js_number(jsc.get(prev_offer, "ttl")) - 1}  # 7. decrement

    # ---- the output object, built FROM SCRATCH ---------------------------- #
    requested_attributes = jsc.get(qf, "requested_attributes")
    variables: dict[str, Any] = {
        "message_type": _u(qf, "message_type"),
        "intent_hint": _u(qf, "intent_hint"),
        "domain_hint": _u(qf, "domain_hint"),
        "user_goal": _u(qf, "user_goal"),
        "query_scope": _u(qf, "query_scope"),
        # The TIER is a per-turn choice that goes stale (D4); the BRAND is a constraint
        # the customer put on the question and must survive a continuation, or the brand
        # half of the scope vanishes and re-opens a gate that already denied the turn.
        "query_brands": _u(qf, "query_brands"),
        "access_levels": _u(qf, "access_levels"),
        "entities": reconciled_entities,
        "routing": _u(qf, "routing"),
        "escalation": _u(qf, "escalation"),
        "response": response,  # the COMPRESSED view (parser-facing)
        "last_result_set": last_result_set,
        "selection_context": selection_context,
        "date_filter_start": _u(qf, "date_filter_start"),
        # QS-9: the PERSPECTIVE of the question (quantity vs delivery-order) is an axis
        # of the query exactly like the date window beside it. Array-guarded because the
        # parser carry reads it as an array.
        "requested_attributes": requested_attributes if jsc.is_array(requested_attributes) else [],
        "date_filter_end": _u(qf, "date_filter_end"),
        "date_mode": _u(qf, "date_mode"),
        "match_mode": _u(qf, "match_mode"),
        "contains_flyer": _u(qf, "contains_flyer"),
        "dym_offer": dym_offer,
        # A READ-ONLY LEGACY MIRROR of the offer's candidates, kept only for the
        # spine-to-parser promotion window so an OLD parser can still pick.
        "dym_candidates": jsc.get(dym_offer, "candidates")
        if (jsc.truthy(dym_offer) and jsc.is_array(jsc.get(dym_offer, "candidates")))
        else [],
        # On an ideate turn persist the endpoint's returned pointer; on any other turn
        # carry the prior one forward so a CRM question mid-collection does not wipe an
        # open draft (IU3).
        "ideation": jsc.get(ideate, "ideation") if jsc.truthy(ideate) else (jsc.get(prev, "ideation") or None),
    }
    output: dict[str, Any] = {
        "variables": variables,
        "user_response": user_response,
        "quick_reply": quick_reply,
    }
    # Emitted ONLY when a dym set exists this turn (absent on every no-dym turn).
    if dym_last_result_set:
        variables["dym_last_result_set"] = dym_last_result_set

    # ---- TIER MENU PERSISTENCE (RS-9 Fix 6) ------------------------------- #
    # `route-turn`'s pre-check needs the OFFERED tier list, in order, to resolve a bare
    # digit on ANY later turn of the promotion thread - not just the one round trip the
    # `_tier` carry above covers. A SEPARATE key from `picker_last_result_set`, which
    # dies the moment a fresh entity is typed, because a promo browse routinely types
    # fresh product codes while the tier menu must stay live underneath it.
    tm_prev = jsc.get(prev, "tier_menu")
    tm_prev = tm_prev if jsc.is_array(tm_prev) else None
    tm_born = (
        jsc.get(tier, "tier_last_result_set")
        if (
            tier is not None
            and jsc.is_array(jsc.get(tier, "tier_last_result_set"))
            and len(jsc.get(tier, "tier_last_result_set")) > 0
        )
        else None
    )
    tm_domain_ok = jsc.get(qf, "domain_hint") is None or jsc.get(qf, "domain_hint") == "promotion"
    tier_menu = tm_born or (tm_prev if tm_domain_ok else None)
    if tier_menu:
        variables["tier_menu"] = tier_menu

    # ---- an open offer survives the answer (the picker carry) ------------- #
    _picker_carry(
        variables,
        qf=qf,
        ctx=ctx,
        prev=prev,
        gate_ran=gate_ran,
        gate_json=gate_json,
        is_disambig=is_disambig,
        selection_context=selection_context,
        last_result_set=last_result_set,
        mem=mem,
        promo=promo,
        tier=tier,
    )

    # ---- brand-company routing axes for the escalation turn --------------- #
    same_team = bool(
        jsc.truthy(prev)
        and jsc.truthy(jsc.get(prev, "routing"))
        and jsc.truthy(jsc.get(qf, "routing"))
        and jsc.get(jsc.get(prev, "routing"), "suggested_team")
        == jsc.get(jsc.get(qf, "routing"), "suggested_team")
    )
    fresh = bool(
        gate_ran
        and jsc.is_array(jsc.get(gate_json, "routing_companies"))
        and len(jsc.get(gate_json, "routing_companies")) > 0
    )
    # The roster plan ACTUALLY used by get-cs-members this turn. Only the plan items that
    # CONTRIBUTED a member are kept: a company whose roster came back empty was named in
    # the reply but has nobody to assign, so it must not turn a de-facto single pool into
    # "both axes null" on the bare-"yes" turn. A plan must never outlive its roster.
    plan_items = outcome.get("cs-roster-plan")
    plan_items = plan_items if plan_items is not None else None
    shown_rows = (
        jsc.get(mem, "cs_last_result_set")
        if (not jsc.truthy(ideate) and jsc.truthy(mem) and jsc.is_array(jsc.get(mem, "cs_last_result_set")))
        else []
    )
    shown_cos: set[Any] = set()
    for row in shown_rows:
        ids = jsc.get(row, "company_ids")
        ids = ids if (jsc.is_array(ids) and len(ids) > 0) else [jsc.get(row, "company_id") or None]
        for i in ids:
            shown_cos.add(i or None)
    used_plan = [p for p in jsc.array(plan_items) if (jsc.get(p, "company_id") or None) in shown_cos]
    if used_plan:
        variables["routing_roster_plan"] = [
            {
                "plan_idx": jsc.get(p, "plan_idx") if jsc.get(p, "plan_idx") is not None else i,
                "company_id": jsc.get(p, "company_id") or None,
                "company_name": jsc.get(p, "company_name") or None,
                "brand_code": jsc.get(p, "brand_code") or None,
            }
            for i, p in enumerate(used_plan)
        ]
    else:
        variables["routing_roster_plan"] = (
            jsc.get(prev, "routing_roster_plan")
            if (
                plan_items is None
                and not fresh
                and same_team
                and jsc.is_array(jsc.get(prev, "routing_roster_plan"))
            )
            else None
        )
    variables["routing_brand"] = (
        jsc.get(gate_json, "routing_brand") if fresh else (jsc.get(prev, "routing_brand") if same_team else None)
    )
    variables["routing_brand_source"] = (
        jsc.get(gate_json, "routing_brand_source")
        if fresh
        else (jsc.get(prev, "routing_brand_source") if same_team else None)
    )
    variables["routing_company"] = (
        jsc.get(gate_json, "routing_company") if fresh else (jsc.get(prev, "routing_company") if same_team else None)
    )
    variables["routing_companies"] = (
        jsc.get(gate_json, "routing_companies")
        if fresh
        else (jsc.get(prev, "routing_companies") if (same_team and jsc.is_array(jsc.get(prev, "routing_companies"))) else None)
    )

    # ---- miss-company routing: result-aware escalation scoping ------------ #
    turn_state: dict[str, Any] = {"answered_domain": answered_domain, "offer_open": False}
    _miss_company_routing(
        output,
        qf=qf,
        prev=prev,
        outcome=outcome,
        ideate=ideate,
        sug=sug,
        mem=mem,
        dym_last_result_set=dym_last_result_set,
        turn_state=turn_state,
    )

    # ---- search-scope disclosure (delivery orders only) ------------------- #
    _search_scope_header(
        output,
        qf=qf,
        gate_ran=gate_ran,
        gate_json=gate_json,
        resolver_json=resolver_json,
        resolved_ran=resolved is not None,
        is_escalate_branch=is_escalate_branch,
        last_result_set=last_result_set,
        raw_of_tok=raw_of_tok,
    )

    # ---- MI-D: the media confirmation, merged into the answer ------------- #
    _media_confirm_prefix(output, qf=qf, ctx=ctx, resolver_json=resolver_json, resolved_ran=resolved is not None)

    # R3: the persisted marker that replaces the frozen-string read (H13, D11). An
    # escalation offer is open when the catalog said so - which covers the not_found, the
    # escalate_offer and the member-offer arms, since the member offer SPREADS the
    # catalog - or when a miss arm appended the frozen phrase itself.
    offer_open = bool(jsc.get(cat, "is_escalate_offer") is True or turn_state["offer_open"])
    variables["pending"] = pending_marker.derive(offer_open=offer_open, qf=qf, gate=gate)

    sanitize_em_dash(output)
    # The node's output IS a serialised n8n item, so `undefined` becomes an absent key
    # right here - and every downstream reader (crossdomain-compose, save-session-vars,
    # the sender) sees the stripped shape, never the sentinel.
    return CompiledState(
        item=strip_undefined({"reply": seal(output)}),
        answered_domain=turn_state["answered_domain"],
        offer_open=offer_open,
    )


# --------------------------------------------------------------------------- #
# N-1a: say WHAT matched, on spec answers only (spec-raw-text-migration)
# --------------------------------------------------------------------------- #

# class verbatim, brand verbatim, everything else underscores-to-spaces + titlecase.
# Both keys are exempt from the lower_snake pin because brand values carry real spaces
# and case ("NO LOGO", "American Standard"); re-casing them rewrites the catalogue's own
# spelling at the customer.
_VERBATIM_KEYS = ("class", "brand")


def _title(value: str) -> str:
    """TITLECASE PROPER - lower first, THEN capitalise.

    An uppercase-only pass would leave "SORENTO" and "NO LOGO" untouched by itself, which
    would make the class/brand exemption unfalsifiable. It is exempt because it is
    exempt, and the exemption has its own test.
    """
    lowered = value.replace("_", " ").lower()
    return re.sub(r"\b[a-z]", lambda m: m.group(0).upper(), lowered).strip()


def _human_val(key: Any, value: Any) -> str | None:
    """A spec value rendered honestly, or None. Boolean / object / missing are DROPPED."""
    if isinstance(value, bool):
        return None  # a boolean is not a value anyone can read back as their own words
    if isinstance(value, (int, float)) and not jsc.is_nan(value):
        return jsc.js_string(value)
    if isinstance(value, list):
        parts = [p for p in (_human_val(key, x) for x in value) if isinstance(p, str) and p]
        return ", ".join(parts) if parts else None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped if jsc.js_string(key).lower() in _VERBATIM_KEYS else _title(stripped)


def _matched_on_line(
    user_response: Any,
    *,
    qf: Mapping[str, Any],
    resolver_json: Any,
    gate_ran: bool,
    gate_json: Mapping[str, Any],
    is_escalate_branch: bool,
    include_response: Any,
    manual_response: Any,
    last_result_set: Any,
) -> Any:
    """`matched_specs INTERSECT (spec_asked-keys UNION {class})`, rendered as VALUES.

    The customer described a product in their own words and got five codes back with no
    indication of WHICH part of their description did the work, so a wrong assumption on
    our side and a right answer looked identical to them.

    Two filters carry the honesty. `spec_asked` is what the CUSTOMER asked for, so
    intersecting with it keeps a HOUSE PREFERENCE out of a line that reads as "your words
    matched this". And the sentence is WHOLE-ANSWER scoped, so it is emitted only when
    EVERY row shown is a spec row: a partial attribution is not a weaker claim, it is a
    false one.
    """
    answered = (
        not is_escalate_branch
        and jsc.truthy(include_response)
        and not jsc.truthy(manual_response)
        and jsc.get(qf, "message_type") == "business_query"
        and isinstance(user_response, str)
        and user_response.strip() != ""
        and jsc.is_array(last_result_set)
        and len(last_result_set) > 0
    )
    if not answered:
        return user_response
    spec_res = resolver_json if isinstance(resolver_json, dict) else {}
    # The rows the customer was actually shown. `compatible_entities` carries no
    # `match_tier`, so the tier is read off the resolver rows and joined back by
    # uuid/code. A gate that did not run means no answer set, so no line.
    if not gate_ran:
        return user_response
    shown_ents = list(jsc.array(jsc.get(gate_json, "compatible_entities")))
    shown_set: set[str] = set()
    for e in shown_ents:
        for v in (jsc.get(e, "uuid"), jsc.get(e, "code")):
            key = jsc.nullish_str(v, "").strip().lower()
            if key:
                shown_set.add(key)
    if not shown_set:
        return user_response

    all_matches: list[Any] = []
    for res in jsc.array(jsc.get(spec_res, "resolutions")):
        all_matches.extend(jsc.array(jsc.get(res, "matches")))
    all_matches.extend(jsc.array(jsc.get(spec_res, "intersection")))

    def _in_answer(m: Any) -> bool:
        for v in (jsc.get(m, "uuid"), jsc.get(m, "canonical_code")):
            key = jsc.nullish_str(v, "").strip().lower()
            if key and key in shown_set:
                return True
        return False

    spec_rows = [
        m
        for m in all_matches
        if jsc.nullish_str(jsc.get(m, "match_tier"), "").lower() == "spec_search" and _in_answer(m)
    ]
    spec_keys: set[str] = set()
    for m in spec_rows:
        for v in (jsc.get(m, "uuid"), jsc.get(m, "canonical_code")):
            key = jsc.nullish_str(v, "").strip().lower()
            if key:
                spec_keys.add(key)
    all_shown_are_spec = len(shown_ents) > 0 and all(
        any(
            (jsc.nullish_str(v, "").strip().lower() in spec_keys)
            for v in (jsc.get(e, "uuid"), jsc.get(e, "code"))
            if jsc.nullish_str(v, "").strip().lower()
        )
        for e in shown_ents
    )
    if not all_shown_are_spec:
        return user_response

    keys: list[str] = []
    for m in spec_rows:
        matched_specs = jsc.get(jsc.get(m, "display"), "matched_specs")
        for k in jsc.array(matched_specs):
            # STRINGS ONLY, never `String(k)`: the wire is a list of key names, and
            # coercing junk renders "[object Object]" inside a customer-facing sentence.
            key = k.strip() if isinstance(k, str) else ""
            if key and key not in keys:
                keys.append(key)
    if not keys:
        return user_response

    asked: set[str] = set()
    for a in jsc.array(jsc.get(spec_res, "spec_asked")):
        raw_key = (
            a.get("key")
            if (isinstance(a, dict) and isinstance(a.get("key"), str))
            else (a if isinstance(a, str) else "")
        )
        normalised = jsc.js_string(raw_key).strip().lower()
        if normalised:
            asked.add(normalised)
    # If `spec_asked` is ABSENT the endpoint predates CRM #142: nothing is asked-for, so
    # only `class` survives and the line degrades to the description form. That
    # degradation IS the deployment tell, and it is asserted rather than papered over.
    selected = [k for k in keys if k.lower() == "class" or k.lower() in asked]
    # Class leads: it is the noun the customer typed and the qualifiers modify it.
    ordered = [k for k in selected if k.lower() == "class"] + [k for k in selected if k.lower() != "class"]

    def _value_for(key: str) -> Any:
        for m in spec_rows:
            specs = jsc.get(jsc.get(m, "display"), "specifications")
            if isinstance(specs, dict) and key in specs:
                return specs[key]
        return UNDEFINED

    parts: list[str] = []
    for k in ordered:
        value = _value_for(k)
        rendered = None if value is UNDEFINED else _human_val(k, value)
        if not isinstance(rendered, str) or not rendered:
            continue
        parts.append(rendered if k.lower() == "class" else f"{_pretty_key(k)}: {rendered}")
    return user_response + (
        f"\n\n_Matched on: {_and_list(parts)}._" if parts else "\n\n_Matched on your description._"
    )


# --------------------------------------------------------------------------- #
# N-2: name the qualifier we could not filter by (spec-answer-honesty)
# --------------------------------------------------------------------------- #

# Units the catalogue's spec keys actually carry. A WHITELIST on purpose: matching "any
# letters after the number" would echo "2 sinks" as if it were a measurement.
_UNITS = frozenset(
    {
        "mm", "cm", "m", "mtr", "meter", "meters", "metre", "metres",
        "in", "inch", "inches", "ft", "l", "ltr", "litre", "litres", "liter", "liters",
        "kg", "g", "w", "kw", "v", "bar", "mpa", '"', "'",
    }
)
_QUANTITY_BINDING_WINDOW = 20
_TOK_CHAR_RE = re.compile(r"[0-9A-Za-z._/-]")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_UNIT_RE = re.compile(r"^ ?([A-Za-z]{1,7}|\"|')")


def _raw_message(ctx: Mapping[str, Any]) -> str:
    """`ctx.text.message.message.text || ...attachment.description` - what they typed."""
    text = jsc.get(ctx, "text")
    inner = jsc.get(jsc.get(text, "message"), "message")
    body = jsc.get(inner, "text") or jsc.get(jsc.get(inner, "attachment"), "description")
    return jsc.js_string(body if jsc.truthy(body) else "")


def _unmet_spec_line(  # noqa: PLR0915 - one ported block, kept whole
    user_response: Any,
    *,
    qf: Mapping[str, Any],
    ctx: Mapping[str, Any],
    resolver_json: Any,
    is_escalate_branch: bool,
    include_response: Any,
    manual_response: Any,
    last_result_set: Any,
) -> Any:
    """"thickness isn't recorded for these products, so I couldn't narrow by 1.2mm."

    Silence must never pass as success: "...thickness 1.2mm" and "...thickness 1.0mm"
    returned a BYTE-IDENTICAL reply, so the customer had no way to know the spec was
    never filtered on. `spec_unmet` is emitted only by the CRM's spec-search fallback and
    is `[]` when everything asked for was met, so this is inert on every turn that works.

    **The value is echoed from the customer's OWN MESSAGE or not at all.** The wire
    carries `1.0` as the number 1 and the CRM normalises to millimetres, so THE UNIT IS
    NOT ON THE WIRE: rendering it bare told a customer who typed "1.0mm" that we could
    not narrow by "1". Which span is chosen follows the CRM's own binding rule - the
    number nearest the key's own word, within 20 characters - and a genuine tie is
    AMBIGUOUS and drops to "by it", because guessing is what produced the defect.
    """
    answered = (
        not is_escalate_branch
        and jsc.truthy(include_response)
        and not jsc.truthy(manual_response)
        and jsc.get(qf, "message_type") == "business_query"
        and isinstance(user_response, str)
        and user_response.strip() != ""
        and jsc.is_array(last_result_set)
        and len(last_result_set) > 0
    )
    if not answered:
        return user_response
    re_json = resolver_json if isinstance(resolver_json, dict) else {}
    unmet = jsc.get(re_json, "spec_unmet")
    unmet = unmet if jsc.is_array(unmet) else []
    if len(unmet) == 0:
        return user_response

    named: list[dict[str, Any]] = []
    for u in unmet:
        if u is None:
            continue
        if isinstance(u, str):
            # `u.split('=')` then `[k, v]`: a bare "thickness" leaves `v` undefined, and
            # "a=b=c" binds `v` to "b" - a partition would bind it to "b=c".
            parts = u.split("=")
            value = parts[1] if len(parts) > 1 else None
            named.append(
                {"key": _pretty_key(parts[0]), "value": None if value is None else jsc.js_string(value).strip()}
            )
        elif isinstance(u, dict) and u.get("key") is not None:
            value = u.get("value")
            named.append(
                {"key": _pretty_key(u.get("key")), "value": None if value is None else jsc.js_string(value).strip()}
            )
    if not named:
        return user_response

    shown = named[:3]  # cap, same spirit as the miss-token cap of 5
    key_list = _and_list([x["key"] for x in shown])
    is_are = "isn't" if len(shown) == 1 else "aren't"
    raw_msg = _raw_message(ctx)

    def _is_tok_char(c: str) -> bool:
        return bool(c) and bool(_TOK_CHAR_RE.match(c))

    def _crosses_code(start: int, end: int) -> bool:
        """A hyphen, underscore or slash does NOT end a token: "ABC-1.2MM" is one part
        number, and quoting it back as a spec is the defect this exists to stop."""
        ts, te = start, end
        while ts > 0 and _is_tok_char(raw_msg[ts - 1]):
            ts -= 1
        while te < len(raw_msg) and _is_tok_char(raw_msg[te]):
            te += 1
        return bool(re.search(r"[A-Za-z]", raw_msg[ts:start] + raw_msg[end:te]))

    def _key_anchors(key: Any) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        normalised = re.sub(r"[^a-z0-9]+", " ", jsc.js_string("" if key is None else key).lower()).strip()
        if not normalised or not raw_msg:
            return out
        forms: list[str] = []
        if len(normalised) >= 3:
            forms.append(normalised)
        for word in normalised.split(" "):
            if len(word) >= 3 and word not in forms:
                forms.append(word)
        hay = raw_msg.lower()
        for form in forms:
            for m in re.finditer(r"\b" + form + r"(?:s)?\b", hay):
                out.append((m.start(), m.end()))
        return out

    def _num_candidates(number: float) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in _NUMBER_RE.finditer(raw_msg):
            start = m.start()
            prev_char = raw_msg[start - 1] if start > 0 else ""
            if prev_char and re.match(r"[0-9A-Za-z.]", prev_char):
                continue  # inside a code or a longer number
            if abs(float(m.group(0)) - number) >= 1e-9:
                continue  # a different quantity
            end = start + len(m.group(0))
            rest = raw_msg[end:]
            unit_match = _UNIT_RE.match(rest)
            has_unit = bool(
                unit_match
                and unit_match.group(1).lower() in _UNITS
                and not re.match(r"[A-Za-z]", rest[len(unit_match.group(0)) : len(unit_match.group(0)) + 1] or "")
            )
            if has_unit:
                end += len(unit_match.group(0))
            if end < len(raw_msg) and re.match(r"[0-9A-Za-z]", raw_msg[end]):
                continue  # "1.2xyz" - never echo a partial token
            if _crosses_code(start, end):
                continue  # "ABC-1.2MM" is a part number
            out.append({"start": start, "end": end, "text": raw_msg[start:end], "unit": has_unit})
        return out

    def _pick_span(candidates: list[dict[str, Any]], key: Any) -> str | None:
        if not candidates:
            return None
        pool = candidates
        anchors = _key_anchors(key)
        if anchors:
            scored: list[tuple[dict[str, Any], int]] = []
            for c in candidates:
                best = None
                for a_start, a_end in anchors:
                    distance = c["start"] - a_end if c["start"] >= a_end else a_start - c["end"]
                    if distance >= 0 and (best is None or distance < best):
                        best = distance
                if best is not None and best <= _QUANTITY_BINDING_WINDOW:
                    scored.append((c, best))
            if not scored:
                return None  # nothing sits near the key
            minimum = min(d for _, d in scored)
            pool = [c for c, d in scored if d == minimum]
        else:
            with_unit = [c for c in pool if c["unit"]]
            if with_unit:
                pool = with_unit
        texts: list[str] = []
        for c in pool:
            if c["text"] not in texts:
                texts.append(c["text"])
        return texts[0] if len(texts) == 1 else None  # a genuine tie is AMBIGUOUS

    def _span_for(value: Any, key: Any) -> str | None:
        v = "" if value is None else jsc.js_string(value).strip()
        # A boolean is not a quantity anyone typed, and must not be echoed just because
        # the WORD appears in the message.
        if not v or not raw_msg or v in ("true", "false"):
            return None
        if re.fullmatch(r"\d+(?:\.\d+)?", v):
            return _pick_span(_num_candidates(float(v)), key)
        # Non-numeric (a material, a finish): echo it only if the customer actually wrote
        # it, in THEIR casing. A CRM-normalised spelling they never typed falls back.
        index = raw_msg.lower().find(v.lower())
        if index < 0:
            return None
        before = raw_msg[index - 1] if index > 0 else ""
        after = raw_msg[index + len(v)] if index + len(v) < len(raw_msg) else ""
        if (before and re.match(r"[0-9A-Za-z]", before)) or (after and re.match(r"[0-9A-Za-z]", after)):
            return None
        if _crosses_code(index, index + len(v)):
            return None
        return raw_msg[index : index + len(v)]

    # ALL-OR-NOTHING, so the key list and the value list can never desync and half a list
    # can never attribute a number the customer did not write. Deduped: two keys that
    # failed on the same span read "thickness and depth ... by 1.2mm".
    spans = [_span_for(x["value"], x["key"]) for x in shown]
    quotable = all(isinstance(s, str) and s for s in spans)
    if quotable:
        unique: list[str] = []
        for s in spans:
            if s not in unique:
                unique.append(s)  # type: ignore[arg-type]
        tail = f"so I couldn't narrow by {_and_list(unique)}."
    else:
        tail = "so I couldn't narrow by it." if len(shown) == 1 else "so I couldn't narrow by them."
    return user_response + f"\n\n{key_list} {is_are} recorded for these products, {tail}"


# --------------------------------------------------------------------------- #
# dym-partial-disambiguation: genuine misses on the ANSWERED happy path
# --------------------------------------------------------------------------- #

# A token is CODE-SHAPED when it has a digit and starts with two letters. A code-shaped
# unresolved token is never cleared by a spec answer, so an unknown code still surfaces
# its own miss and a mixed hit-plus-miss turn renders both. The dash class is wide on
# purpose: WhatsApp keyboards emit several of them.
_CODE_SHAPE_RE = re.compile(r"^[A-Za-z][A-Za-z][A-Za-z0-9._/\-‐-―−﹘﹣－]*$")
_HAS_DIGIT_RE = re.compile(r"[0-9]")
# `attachment_type` is how the parser narrows WHICH documents to return ("gambar" ->
# "photo"). It is a FILTER, not a thing the customer asked us to FIND, and reporting it
# as a miss printed "technicaldrawing (attachment_type): not found." underneath the very
# files it claims we could not find.
_FILTER_HINTS = frozenset({"attachment_type"})


def _not_code_shaped(entities: Any) -> list[str]:
    raws = [jsc.js_string(jsc.get(x, "raw") if jsc.truthy(jsc.get(x, "raw")) else "").strip() for x in jsc.array(entities)]
    kept = [
        v for v in raws if len(v) > 0 and not (_HAS_DIGIT_RE.search(v) and _CODE_SHAPE_RE.match(v))
    ]
    out: list[str] = []
    for v in kept:
        if v not in out:
            out.append(v)
    return out


def _partial_dym_block(  # noqa: PLR0912, PLR0915 - one ported block, kept whole
    user_response: Any,
    response: Any,
    *,
    qf: Mapping[str, Any],
    outcome: Mapping[str, Any],
    resolver_json: Any,
    gate_ran: bool,
    gate_json: Mapping[str, Any],
    get_result_obj,
    is_escalate_branch: bool,
    include_response: Any,
    manual_response: Any,
    last_result_set: Any,
    ent_of_tok,
    raw_of_tok,
    execution_id: str,
) -> tuple[Any, Any, Any, Any]:
    """Surface genuine-miss tokens on the ANSWERED happy path.

    When SOME tokens resolved (stock answered) and OTHERS are genuine misses, the misses
    used to vanish - `build-suggest-offer` is downstream of not-found and never runs on
    the proceed path. This appends a numbered "did you mean" block, persists a SEPARATE
    `dym_last_result_set` WITHOUT touching `last_result_set` or `selection_context` (so
    the stock positional-pick affordance survives), feeds an offer into the lifecycle so
    it survives the answered-turn kill, and appends the single parser-visible marker to
    the compressed `response`.

    **Six suppressions, each keyed on an OUTCOME rather than a mechanism.** A token whose
    own candidates became the answer, a token the gate resolved by document-class
    narrowing, a token spec search answered, a token the promo picker already reported, a
    filter token, and a token with an exact match. Every one of them was a measured turn
    where the customer read "not found" underneath the very rows their words produced.
    Anything unlinkable FAILS OPEN and is still reported: a genuine miss must never be
    silenced.
    """
    answered = (
        not is_escalate_branch
        and jsc.truthy(include_response)
        and isinstance(user_response, str)
        and user_response.strip() != ""
        and jsc.is_array(last_result_set)
        and len(last_result_set) > 0
        and jsc.get(qf, "message_type") == "business_query"
        and not jsc.truthy(manual_response)
    )
    if not answered:
        return user_response, response, None, None

    r = resolver_json if isinstance(resolver_json, dict) else {}
    gate = gate_json if gate_ran else {}

    # Guard exactly as build-suggest-offer (defensive parity: both false on a true answer)
    result_obj = get_result_obj()
    is_clar = jsc.get(result_obj, "is_clarification") is True
    if is_clar or jsc.get(gate, "require_specific") is True:
        return user_response, response, None, None

    def _is_exact(m: Any) -> bool:
        return jsc.nullish_str(jsc.get(m, "match_tier"), "").lower() == "exact"

    def _human_label(m: Any) -> Any:
        code = jsc.get(m, "canonical_code")
        if jsc.truthy(code) and not _is_uuid(code):
            return jsc.js_string(code)
        display = jsc.get(m, "display") or {}
        return jsc.get(display, "description") or jsc.get(display, "product_name") or jsc.get(display, "name") or None

    allowed_lookup = jsc.get(jsc.get(gate, "gate_debug"), "allowed_lookup")
    allowed_types = allowed_lookup if jsc.is_array(allowed_lookup) else None

    def _token_candidates(res: Any) -> list[Any]:
        acc = list(jsc.array(jsc.get(res, "matches"))) + list(jsc.array(jsc.get(res, "alternatives")))
        seen: set[Any] = set()
        keep: list[Any] = []
        for m in acc:
            code = jsc.get(m, "canonical_code")
            if not jsc.truthy(code):
                continue
            if _is_exact(m):
                continue  # exact would have resolved
            if allowed_types is not None and jsc.truthy(jsc.get(m, "entity_type")) and jsc.get(m, "entity_type") not in allowed_types:
                continue
            if code in seen:
                continue
            seen.add(code)
            keep.append(m)
        return keep

    unresolved = jsc.array(jsc.get(r, "unresolved_tokens"))

    # `r` is the RAW resolver node, so a token the GATE resolved still looks unresolved.
    # Narrow by construction: only tokens the gate stamped.
    gate_resolved_tokens = {
        jsc.nullish_str(jsc.get(x, "token"), "").strip().lower()
        for x in jsc.array(jsc.get(gate, "resolutions"))
        if jsc.truthy(x)
        and jsc.get(x, "resolved") is True
        and jsc.get(x, "resolved_by") in ("document-class-narrowing", "same-code-collapse")
    }
    gate_resolved_tokens.discard("")

    answer_codes: set[str] = set()
    for e in jsc.array(jsc.get(gate, "compatible_entities")):
        for v in (jsc.get(e, "uuid"), jsc.get(e, "code")):
            key = jsc.nullish_str(v, "").strip().lower()
            if key:
                answer_codes.add(key)

    def _token_was_answered(res: Any) -> bool:
        """`intersection` is the THIRD place an answer set hides: the legacy envelope has
        no `resolutions` at all, and reading only matches/alternatives left it
        unprotected, so a token that "failed" and a token that produced the answer looked
        the same."""
        if not answer_codes:
            return False
        cands = (
            list(jsc.array(jsc.get(res, "matches")))
            + list(jsc.array(jsc.get(res, "alternatives")))
            + list(jsc.array(jsc.get(res, "intersection")))
        )
        for m in cands:
            for v in (jsc.get(m, "uuid"), jsc.get(m, "canonical_code")):
                key = jsc.nullish_str(v, "").strip().lower()
                if key and key in answer_codes:
                    return True
        return False

    def _is_spec_row(m: Any) -> bool:
        return jsc.nullish_str(jsc.get(m, "match_tier"), "").lower() == "spec_search"

    spec_rows: list[Any] = []
    for res in jsc.array(jsc.get(r, "resolutions")):
        spec_rows.extend(jsc.array(jsc.get(res, "matches")))
    spec_rows.extend(jsc.array(jsc.get(r, "intersection")))
    spec_search_answered = bool(answer_codes) and any(
        _is_spec_row(m)
        and any(
            jsc.nullish_str(v, "").strip().lower() in answer_codes
            for v in (jsc.get(m, "uuid"), jsc.get(m, "canonical_code"))
            if jsc.nullish_str(v, "").strip().lower()
        )
        for m in spec_rows
    )

    def _token_reached_spec_search(res: Any) -> bool:
        # (a) the CRM's QUERY-KEYED resolution is not a customer token: since the
        # spec-raw-text migration `query` IS the customer's whole sentence, so a renderer
        # that groups misses BY TOKEN printed their own question back as a failed search
        # term. Identified POSITIVELY, by the spec_search tier its own matches carry, and
        # FAIL-OPEN: a resolution with no matches identifies nothing, so it is REPORTED.
        matches = jsc.array(jsc.get(res, "matches"))
        if matches and all(_is_spec_row(m) for m in matches):
            return True
        # (b) the customer's OWN descriptive words, answered BY spec search. Judged on
        # the CUSTOMER'S RAW, never the resolver's echo: the resolver squashes a
        # product-hint phrase to one token whose digits sit behind two letters, so the
        # code-shape test read it as a CODE and this arm never fired for the tokens it
        # was written for.
        return spec_search_answered and len(_not_code_shaped([{"raw": raw_of_tok(jsc.get(res, "token"))}])) > 0

    # ONE MISS, ONE VOICE: promo-picker renders its own miss for promotion turns, and
    # without this the same token was reported twice in one reply.
    picker_reported: set[str] = set()
    promo_out = outcome.get("promo-picker") or {}
    for t in jsc.array(jsc.get(jsc.get(promo_out, "_promo_notfound"), "tokens")):
        picker_reported.add(jsc.nullish_str(t, "").strip().lower())
    for t in jsc.array(jsc.get(promo_out, "_promo_unmatched")):
        picker_reported.add(jsc.nullish_str(t, "").strip().lower())

    def _is_filter_token(token: Any) -> bool:
        """Keyed on the ORIGINATING PARSER ENTITY's `hint`, never the resolver's echoed
        `entity_type` - the echo is exactly what these findings show cannot be trusted,
        and on a filter token there are no matches to echo one from anyway."""
        e = ent_of_tok(token)
        return bool(e is not None and jsc.nullish_str(jsc.get(e, "hint"), "").strip().lower() in _FILTER_HINTS)

    miss_resolutions: list[Any] = []
    resolutions = jsc.get(r, "resolutions")
    if jsc.is_array(resolutions):
        miss_resolutions = [
            res
            for res in resolutions
            if jsc.truthy(res)
            and jsc.get(res, "resolved") is not True
            and not any(_is_exact(m) for m in jsc.array(jsc.get(res, "matches")))
            and jsc.nullish_str(jsc.get(res, "token"), "").strip().lower() not in gate_resolved_tokens
            and not _token_reached_spec_search(res)
            and jsc.nullish_str(jsc.get(res, "token"), "").strip().lower() not in picker_reported
            and not _is_filter_token(jsc.get(res, "token"))
            and not _token_was_answered(res)
        ]
    elif (
        len(unresolved) > 0
        and not _token_was_answered(r)
        and not all(jsc.nullish_str(t, "").strip().lower() in picker_reported for t in unresolved)
    ):
        miss_resolutions = [r]  # legacy single-resolution shape

    surfaced = miss_resolutions[:5]  # cap missed tokens shown at 5
    if not surfaced:
        return user_response, response, None, None  # no genuine miss -> pure no-op

    # dym-probe-before-offer: the has-it annotation. Not probed means NO suffix, never a
    # misleading "no".
    dym_ann = None
    for name in ("dym-annotate-partial", "dym-annotate"):
        if jsc.truthy(outcome.get(name)):
            dym_ann = outcome.get(name)
            break
    dym_meta = jsc.get(dym_ann, "dym_probe_meta")
    dym_ok = bool(jsc.truthy(dym_ann) and jsc.truthy(dym_meta) and jsc.get(dym_meta, "ok") is True)
    dym_has = {_norm(c) for c in jsc.array(jsc.get(dym_ann, "dym_available_codes"))} if dym_ok else set()
    dym_probed = {_norm(c) for c in jsc.array(jsc.get(dym_meta, "probed"))} if dym_ok else set()
    entities = jsc.array(jsc.get(qf, "entities"))

    def _dym_att_noun() -> Any:
        if jsc.get(qf, "domain_hint") != "product_attachment":
            return None
        at = jsc.find(entities, lambda e: jsc.lower_or_empty(jsc.get(e, "hint")) == "attachment_type")
        raw = jsc.get(at, "raw") if at is not None else None
        return raw if jsc.truthy(raw) else "document"

    def _dym_noun_of(noun: Any) -> str:
        s = jsc.nullish_str(noun, "").strip()
        return "certificate" if re.match(r"^cert", s, re.IGNORECASE) else (s or "document")

    dym_noun = _dym_noun_of(jsc.get(dym_meta, "noun") or _dym_att_noun()) if dym_ok else None

    def _dym_suffix(code: Any) -> str:
        if not dym_ok:
            return ""
        key = _norm(code)
        if key not in dym_probed:
            return ""  # never a misleading "no" for an unprobed code
        return f" - has {dym_noun}" if key in dym_has else f" - no {dym_noun}"

    # NO SORT HERE. The idx is GLOBAL and CONTIGUOUS across tokens, and the numbered rows
    # carry the pick linkage the parser's numbered-DYM handler resolves against, so
    # reordering would renumber across token blocks and break the round trip.
    idx = 0
    lines: list[str] = []
    numbered: list[dict[str, Any]] = []
    dym_cands: list[dict[str, Any]] = []
    for res in surfaced:
        token = (
            jsc.get(res, "token")
            or (unresolved[0] if unresolved else None)
            or (jsc.get(entities[0], "raw") if entities else None)
            or "that item"
        )
        picks = [
            {"m": m, "label": _human_label(m)}
            for m in _token_candidates(res)[:3]
        ]
        picks = [p for p in picks if jsc.truthy(p["label"])]
        # The type label: resolver PRIMARY (this token's own first match), parser hint
        # FALLBACK, bare when neither is known. Both sources prettified - the hint
        # fallback used to print raw, so one vocabulary came out in two spellings in the
        # same reply.
        type_src_ent = ent_of_tok(token)
        raw_type = None
        res_matches = jsc.array(jsc.get(res, "matches"))
        if res_matches and jsc.truthy(jsc.get(res_matches[0], "entity_type")):
            raw_type = jsc.get(res_matches[0], "entity_type")
        type_label = _prettify_type(raw_type) or _prettify_type(
            jsc.get(type_src_ent, "hint") if type_src_ent is not None else None
        ) or ""
        type_suffix = f" ({type_label})" if type_label else ""
        if picks:
            src_ent = jsc.find(
                entities,
                lambda e, token=token: jsc.js_string(jsc.get(e, "raw") if jsc.truthy(jsc.get(e, "raw")) else "").lower().strip()
                == jsc.js_string(token if jsc.truthy(token) else "").lower().strip(),
            )
            # QUOTE THE CUSTOMER'S SPELLING, not the resolver's echo. `for_raw` stays the
            # RESOLVER token deliberately: it is pick-linkage data, not copy.
            lines.append(f'"{jsc.js_string(raw_of_tok(token))}"{type_suffix}, did you mean:')
            for p in picks:
                idx += 1
                m = p["m"]
                is_u = _is_uuid(jsc.get(m, "canonical_code"))
                for_hint = jsc.get(m, "entity_type") or (jsc.get(src_ent, "hint") if src_ent is not None else None) or None
                for_canon = (jsc.get(src_ent, "canonical_code") if src_ent is not None else None) or None
                lines.append(f"  {idx}. {jsc.js_string(p['label'])}{_dym_suffix(jsc.get(m, 'canonical_code'))}")
                numbered.append(
                    {
                        "idx": idx,
                        "label": p["label"],
                        "value": p["label"] if is_u else jsc.get(m, "canonical_code"),
                        "product": jsc.get(m, "canonical_code"),
                        "uuid": jsc.get(m, "uuid") or None,
                        "entity_type": jsc.get(m, "entity_type") or None,
                        "for_raw": token,
                        "for_hint": for_hint,
                        "for_canonical": for_canon,
                    }
                )
                dym_cands.append(
                    {
                        "code": jsc.get(m, "canonical_code"),
                        "uuid": jsc.get(m, "uuid") or None,
                        "entity_type": jsc.get(m, "entity_type") or None,
                        "for_raw": token,
                        "for_hint": for_hint,
                        "for_canonical": for_canon,
                    }
                )
        else:
            lines.append(f'"{jsc.js_string(raw_of_tok(token))}"{type_suffix}: not found.')

    total = len(numbered)
    footer = "Reply a number to check it, or ask again." if total >= 1 else "Ask again with the correct code."
    user_response = user_response + "\n\nCouldn't find these:\n" + "\n".join(lines) + "\n\n" + footer

    dym_last_result_set = None
    partial_offer = None
    if total >= 1:
        dym_last_result_set = numbered
        partial_offer = {
            "id": jsc.js_string(execution_id),
            "domain": (jsc.get(qf, "domain_hint") or None) if jsc.truthy(qf) else None,
            "ttl": 3,
            "candidates": dym_cands,
            "picked": [],
        }
        # The SINGLE parser-visible marker on the compressed view, so the parser learns a
        # dym offer is active next turn.
        response = _concat(response, f" [{total} did-you-mean suggestions active]")
    return user_response, response, dym_last_result_set, partial_offer


# --------------------------------------------------------------------------- #
# An open offer survives the answer (the disambiguation-picker carry)
# --------------------------------------------------------------------------- #


def _picker_carry(  # noqa: PLR0912 - one ported block, kept whole
    variables: dict[str, Any],
    *,
    qf: Mapping[str, Any],
    ctx: Mapping[str, Any],
    prev: Mapping[str, Any],
    gate_ran: bool,
    gate_json: Mapping[str, Any],
    is_disambig: bool,
    selection_context: Any,
    last_result_set: Any,
    mem: Any,
    promo: Any,
    tier: Any,
) -> None:
    """"I choose 4 5 6 7 8, then I want to choose 4 - cannot." (captain, 2026-08-20)

    The picker turn persists its roster correctly and the pick works, but the ANSWER then
    overwrites `last_result_set` with its own rows, so the next "4" resolves to order #4
    instead of customer #4. The roster is kept in its OWN field and, while it is alive,
    re-seated as `last_result_set` so the existing positional machinery keeps resolving
    picks against it.

    **H29, AC-205: an offer born THIS TURN outranks a carried picker.** The ladder above
    reassigns `last_result_set` and the label whenever this turn built an offer of its
    own; carrying here anyway wrote both back to the PREVIOUS turn's picker, so the
    customer read one list while the session was armed against a different, invisible
    one, and a real CS escalation was silently dropped. `_sug` is deliberately NOT in the
    born-this-turn list: it has its own TTL lifecycle, and adding it moves a live turn.

    **The member and tier offers are never CARRIED, and that is a safety property.**
    `member_offer` is not a roster label, it is the arming pin on the CS-assign path: a
    carry re-seats it invisibly and the next bare "yes" assigns a human to somebody who
    already declined. `tier_offer` is one round trip by decision D4.
    """
    born_now = (
        is_disambig
        and selection_context == "disambiguation"
        and jsc.is_array(last_result_set)
        and len(last_result_set) > 0
    )
    # A numbered FORMS answer list is a picker in the customer's eyes (#75): 18 rows,
    # pick 8, the answer overwrote the list, and the next "3" was out of range. A
    # MULTI-position pick answers with more than one row and must never re-birth, or the
    # carried 18 shrinks to the picked subset.
    form_pick_turn = jsc.is_array(jsc.get(qf, "reference_positions")) and len(jsc.get(qf, "reference_positions")) > 0
    form_born_now = (
        not born_now
        and not is_disambig
        and not form_pick_turn
        and selection_context is None
        and not (jsc.truthy(mem) or promo is not None or tier is not None)
        and jsc.js_string(jsc.get(qf, "domain_hint") or "").lower() == "forms"
        and jsc.is_array(last_result_set)
        and len(last_result_set) > 1
    )
    gate = gate_json if gate_ran else None
    if born_now:
        born: dict[str, Any] | None = {
            "set": last_result_set,
            "kind": "disambiguation",
            "fam": (jsc.get(gate, "picker_families") if gate is not None else None) or None,
        }
    elif form_born_now:
        born = {"set": last_result_set, "kind": "disambiguation", "fam": None}
    else:
        born = None

    # Freshness is judged on what the CUSTOMER typed - the LLM's OWN entity list - not
    # the post-processed one: `output_exchange` re-attaches the prior scope on a pick as
    # `current_message` with no ordinal, and reading that as a new enquiry dropped the
    # very roster this block exists to keep.
    raw_entities = jsc.get(jsc.get(ctx, "parse"), "_parser_raw")
    raw_entities = jsc.get(raw_entities, "entities")
    if jsc.is_array(raw_entities):
        fresh_typed = any(jsc.truthy(e) and jsc.get(e, "current_message") is True for e in raw_entities)
    else:
        fresh_typed = any(
            jsc.truthy(e)
            and jsc.get(e, "current_message") is True
            and jsc.get(e, "ordinal") is None
            and jsc.get(e, "dym_slot") is None
            for e in jsc.array(jsc.get(qf, "entities"))
        )

    offer_born_this_turn = bool(jsc.truthy(mem) or promo is not None or tier is not None)
    prev_picker = jsc.get(prev, "picker_last_result_set")
    carried = (
        prev_picker
        if (
            born is None
            and not offer_born_this_turn
            and jsc.is_array(prev_picker)
            and len(prev_picker) > 0
            and not fresh_typed
        )
        else None
    )
    picker_set = born["set"] if born is not None else carried
    if jsc.truthy(picker_set):
        variables["picker_last_result_set"] = picker_set
        # The candidate-to-account-family map the gate built for this picker, so the PICK
        # turn covers exactly the accounts the picker's probe counted.
        fam = born["fam"] if born is not None else (jsc.get(prev, "picker_families") or None)
        if jsc.truthy(fam) and len(fam) > 0:
            variables["picker_families"] = fam
        variables["picker_domain"] = (
            (jsc.get(qf, "domain_hint") if jsc.get(qf, "domain_hint") is not None else None)
            if born is not None
            else _u(prev, "picker_domain")
        )
        # The kind rides WITH the roster: a session written before 2026-08-24 carries a
        # roster and no kind, and every one of those is a require_specific picker.
        kind = born["kind"] if born is not None else (jsc.get(prev, "picker_selection_context") or "disambiguation")
        variables["picker_selection_context"] = kind
        # re-seat: the next positional reply resolves against the OFFER, not the answer
        variables["last_result_set"] = picker_set
        variables["selection_context"] = kind

    # THE FAMILY OUTLIVES THE ROSTER (captain, 2026-08-24). `picker_families` maps a
    # picked candidate to the ACCOUNTS it stands for, and the PIN is not bound to the
    # roster's lifetime: an entity keeps its uuid for as long as the customer keeps
    # talking about it. The roster expired, the family went with it, and the pick covered
    # 1 account instead of the 12 the picker had measured.
    if not jsc.truthy(variables.get("picker_families")):
        fam_pinned = any(
            jsc.truthy(e) and jsc.lower_or_empty(jsc.get(e, "hint")) == "customer" and jsc.truthy(jsc.get(e, "uuid"))
            for e in jsc.array(jsc.get(qf, "entities"))
        )
        fam_keep = jsc.get(prev, "picker_families") if jsc.truthy(prev) else None
        if fam_pinned and jsc.truthy(fam_keep) and len(fam_keep) > 0:
            variables["picker_families"] = fam_keep
            variables["picker_families_carried"] = True  # diagnostic


# --------------------------------------------------------------------------- #
# miss-company-routing: result-aware escalation scoping
# --------------------------------------------------------------------------- #

_FROZEN_ESCALATE_PREFIX = "Would you like me to escalate to"


def _miss_company_routing(  # noqa: PLR0912, PLR0915 - one ported block, kept whole
    output: dict[str, Any],
    *,
    qf: Mapping[str, Any],
    prev: Mapping[str, Any],
    outcome: Mapping[str, Any],
    ideate: Any,
    sug: Any,
    mem: Any,
    dym_last_result_set: Any,
    turn_state: dict[str, Any],
) -> None:
    """Two arms, placed LAST so both have the final word on what is sent and persisted.

    **Case B (clarify)** fires when the escalation lane diverted on
    `multi_company_unpicked` (no assignment happened) or when an unresolved reply landed
    on an open MULTI-company offer: replace the confirmation text with the clarify ask
    and RE-PERSIST the prior offer state so the next reply still resolves. Every
    unresolved path out of an open multi-company offer therefore keeps
    `selection_context`, `last_result_set`, the roster plan and the frozen phrase; only
    an explicit decline or a brand-new business query clears them.

    **Case A (miss offer)** appends the FROZEN escalation phrase plus the picker, extends
    `last_result_set` with the member rows, arms the pick context, and persists the MISS
    pool identity. **Case A-plain** is the same for the incoming / stock lanes, which
    showed no picker: the phrase ONLY, `selection_context` untouched, because opening the
    member arm there would let a bare "yes" resolve a roster the customer never saw.

    Both arms fail closed: any missing signal leaves the turn byte-identical, and the two
    cannot co-occur (the miss lane rides the happy path, the clarify rides the divert).
    """
    variables = output["variables"]
    clar = None
    for name in ("clarify-company-reply", "offer-hold-reply"):
        j = outcome.get(name)
        if jsc.truthy(j) and isinstance(jsc.get(j, "clarify_text"), str) and jsc.get(j, "clarify_text").strip():
            clar = j
            break
    mc_mem = outcome.get("build-miss-member-offer")
    mc_rows = (
        jsc.get(mc_mem, "miss_member_rows")
        if (
            jsc.truthy(mc_mem)
            and jsc.get(mc_mem, "miss_member_offer") is True
            and jsc.is_array(jsc.get(mc_mem, "miss_member_rows"))
        )
        else []
    )
    plain_plan = (
        [
            {
                "plan_idx": jsc.get(p, "plan_idx") if jsc.get(p, "plan_idx") is not None else i,
                "company_id": jsc.get(p, "company_id") or None,
                "company_name": jsc.get(p, "company_name") or None,
                "brand_code": jsc.get(p, "brand_code") or None,
            }
            for i, p in enumerate(jsc.get(mc_mem, "miss_roster_plan"))
        ]
        if (
            jsc.truthy(mc_mem)
            and jsc.get(mc_mem, "miss_plain_offer") is True
            and jsc.is_array(jsc.get(mc_mem, "miss_roster_plan"))
        )
        else []
    )

    if clar is not None:
        output["user_response"] = jsc.get(clar, "clarify_text")
        # The clarify ask REPLACES the reply, so this turn no longer answered anything -
        # which is exactly what the "starts with Previous turn (" test used to detect
        # once the response had been overwritten.
        turn_state["answered_domain"] = None
        # B-HB-2: the escalation sub's OWN THIS-TURN gate ask. CHECKED FIRST, ahead of
        # "an offer was already open": persistence must track what was ACTUALLY SENT, or
        # the next turn resolves a company-name reply against the WRONG (persisted) pool
        # while the customer is looking at the right one. The stale axes are NULLED, not
        # merely left un-rewritten, because an earlier block in this same node may have
        # left a value in them.
        fresh_gate = jsc.is_array(jsc.get(clar, "routing_companies")) and len(jsc.get(clar, "routing_companies")) > 0
        if fresh_gate:
            variables["response"] = jsc.get(clar, "clarify_text")
            variables["routing_companies"] = jsc.get(clar, "routing_companies")
            variables["routing_roster_plan"] = None
            variables["routing_company"] = None
            variables["routing_brand"] = None
        elif jsc.get(clar, "clarify_team") is True:
            # Without this the team-clarify arm fell through to the STALE previous
            # response; if that was an escalate offer, `offeredEscalation` read TRUE
            # against an offer the customer can no longer see, and a negatively phrased
            # clarify answer read as declining it.
            variables["response"] = jsc.get(clar, "clarify_text")
        elif isinstance(jsc.get(prev, "response"), str) and jsc.get(prev, "response"):
            variables["response"] = jsc.get(prev, "response")
        if fresh_gate:
            # The customer was shown company NAMES on this ask, nothing numbered, so a
            # stale numbered roster would let a numeric reply resolve an invisible prior
            # member instead of the company pick the ask promised.
            variables["last_result_set"] = []
        elif jsc.is_array(jsc.get(prev, "last_result_set")):
            variables["last_result_set"] = jsc.get(prev, "last_result_set")
        if jsc.get(clar, "clarify_team") is True:
            # SINGLE-USE: only a turn where clarify-team-reply itself ran stamps this;
            # every other turn falls through to the ladder above, so clearing is
            # automatic rather than a second line to remember.
            variables["selection_context"] = "team_clarify"
        elif fresh_gate:
            variables["selection_context"] = None
        elif jsc.truthy(jsc.get(prev, "selection_context")):
            variables["selection_context"] = jsc.get(prev, "selection_context")
        if not fresh_gate and jsc.is_array(jsc.get(prev, "routing_roster_plan")):
            variables["routing_roster_plan"] = jsc.get(prev, "routing_roster_plan")
        if not fresh_gate and jsc.has(prev, "routing_company"):
            variables["routing_company"] = jsc.get(prev, "routing_company")
        if not fresh_gate and jsc.has(prev, "routing_brand"):
            variables["routing_brand"] = jsc.get(prev, "routing_brand")
        if not fresh_gate and jsc.is_array(jsc.get(prev, "routing_companies")):
            variables["routing_companies"] = jsc.get(prev, "routing_companies")
        return

    if (
        len(mc_rows) > 0
        and not jsc.truthy(ideate)
        and not jsc.truthy(sug)
        and not jsc.truthy(mem)
        and not dym_last_result_set
        and isinstance(output.get("user_response"), str)
        and output["user_response"].strip()
        and isinstance(jsc.get(mc_mem, "miss_offer_text"), str)
        and jsc.get(mc_mem, "miss_offer_text").strip()
    ):
        team = jsc.get(jsc.get(qf, "routing"), "suggested_team") or "customer_service"
        plan = [
            {
                "plan_idx": jsc.get(p, "plan_idx") if jsc.get(p, "plan_idx") is not None else i,
                "company_id": jsc.get(p, "company_id") or None,
                "company_name": jsc.get(p, "company_name") or None,
                "brand_code": jsc.get(p, "brand_code") or None,
            }
            for i, p in enumerate(jsc.array(jsc.get(mc_mem, "miss_roster_plan")))
        ]
        # ONE miss company means the phrase names it, bold, after "to". The parser
        # contract is the PREFIX, so the prefix wording stays byte-exact and the same
        # string goes to BOTH the visible reply and the persisted `variables.response`.
        company = f"*{jsc.js_string(plan[0]['company_name'])}* " if (len(plan) == 1 and plan[0]["company_name"]) else ""
        phrase = f"{_FROZEN_ESCALATE_PREFIX} {company}{_pretty_team(team)} team?"
        turn_state["offer_open"] = True  # R3: the frozen phrase is appended right here
        output["user_response"] += f"\n\n{phrase}\n\n{jsc.get(mc_mem, 'miss_offer_text')}"
        previous = variables.get("response")
        variables["response"] = f"{previous if isinstance(previous, str) else ''}\n\n{phrase}".strip()
        base = variables.get("last_result_set")
        variables["last_result_set"] = (base if jsc.is_array(base) else []) + list(mc_rows)
        variables["selection_context"] = "member_offer"
        if plan:
            variables["routing_roster_plan"] = plan  # MISS pool identity overrides the axes block
            variables["routing_company"] = plan[0]["company_id"] if len(plan) == 1 else None
            variables["routing_brand"] = plan[0]["brand_code"] if len(plan) == 1 else None
        return

    if (
        len(plain_plan) > 0
        and not jsc.truthy(ideate)
        and not jsc.truthy(sug)
        and not jsc.truthy(mem)
        and not dym_last_result_set
        and isinstance(output.get("user_response"), str)
        and output["user_response"].strip()
    ):
        # PLAIN arm (incoming / stock miss): the FROZEN phrase ONLY. NO picker text, no
        # `last_result_set` extension, no `selection_context` change - the member arm must
        # NOT open, because a later "yes" rides the confirmation arm off the persisted
        # phrase and a company-name reply rides the parser's open-offer company_pick arm.
        roster_plan = jsc.array(jsc.get(mc_mem, "miss_roster_plan"))
        first_team = jsc.get(roster_plan[0], "team") if roster_plan else None
        team = (
            first_team.strip()
            if (isinstance(first_team, str) and first_team.strip())
            else (jsc.get(jsc.get(qf, "routing"), "suggested_team") or "customer_service")
        )
        company = (
            f"*{jsc.js_string(plain_plan[0]['company_name'])}* "
            if (len(plain_plan) == 1 and plain_plan[0]["company_name"])
            else ""
        )
        phrase = f"{_FROZEN_ESCALATE_PREFIX} {company}{_pretty_team(team)} team?"
        turn_state["offer_open"] = True  # R3: the frozen phrase is appended right here
        output["user_response"] += f"\n\n{phrase}"
        previous = variables.get("response")
        variables["response"] = f"{previous if isinstance(previous, str) else ''}\n\n{phrase}".strip()
        variables["routing_roster_plan"] = plain_plan
        variables["routing_company"] = plain_plan[0]["company_id"] if len(plain_plan) == 1 else None
        variables["routing_brand"] = plain_plan[0]["brand_code"] if len(plain_plan) == 1 else None


# --------------------------------------------------------------------------- #
# Search-scope disclosure: say WHICH dates the answer covers
# --------------------------------------------------------------------------- #

# NARROWED (captain, 2026-08-24): this header describes a DELIVERY ORDER search
# specifically. It used to gate on "domains the CRM date-filters", which let it render
# "Customer: all customers" on an inbound shipment answer - meaningless, a container has
# no customer - alongside "Dates: all dates".
_DATE_SCOPE_DOMAINS = frozenset({"order"})

# DELIBERATE DUPLICATE, kept in lockstep with `not-found-error-message.js`'s own header:
# a MISS opens with the same three lines, because a search that scanned every customer
# said so nowhere. Same axis list, same label priority, same date formatting.
_AXES: tuple[dict[str, Any], ...] = (
    {"label": "Customer", "types": ("customer",), "hints": ("customer",), "always": True, "all_text": "all customers"},
    {"label": "Product", "types": ("product",), "hints": ("product",), "always": True, "all_text": "all products"},
    {
        "label": "Order",
        "types": ("customer_order", "order", "order_number"),
        "hints": ("order", "customer_order", "order_number"),
        "always": False,
    },
    {"label": "Transporter", "types": ("transporter",), "hints": ("transporter",), "always": False},
    {
        "label": "Container",
        "types": ("inbound_shipment",),
        "hints": ("inbound_shipment", "container"),
        "always": False,
    },
    {"label": "Warehouse", "types": ("warehouse",), "hints": ("warehouse",), "always": False},
)
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _format_date(value: Any) -> str:
    """ISO to DD/MM/YYYY, matching the row fields the CRM already renders."""
    m = _ISO_DATE_RE.match(jsc.nullish_str(value, ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else jsc.nullish_str(value, "")


def _search_scope_header(
    output: dict[str, Any],
    *,
    qf: Mapping[str, Any],
    gate_ran: bool,
    gate_json: Mapping[str, Any],
    resolver_json: Any,
    resolved_ran: bool,
    is_escalate_branch: bool,
    last_result_set: Any,
    raw_of_tok,
) -> None:
    """"Customer: ... / Product: ... / Dates: ..." above a delivery-order answer.

    An answer that does not state its date window is ambiguous: "1 order" reads equally
    as "1 order ever" and "1 order this month", and the customer cannot tell which.

    **Rendered from the GATE's `compatible_entities`, never from the parser's hints** -
    the axes actually put in scope, not what the model guessed the words meant. Two
    measured turns are why: a pick off a numbered list scoped the search to ONE order
    while the header read "all customers / all products", and a bare code the parser
    hinted as an order resolved to 10 products, which the header still called "all
    products" - a straight lie about what the customer just got.

    A disclosure bug must never block the answer, so the whole block is best-effort.
    """
    try:
        if is_escalate_branch:
            return  # escalate / clarify copy, not a data answer
        if not jsc.is_array(last_result_set) or len(last_result_set) == 0:
            return
        if not isinstance(output.get("user_response"), str) or not output["user_response"].strip():
            return
        if jsc.js_string(jsc.get(qf, "domain_hint") or "").lower() not in _DATE_SCOPE_DOMAINS:
            return
        start = jsc.get(qf, "date_filter_start") or None
        end = jsc.get(qf, "date_filter_end") or None
        if not start and not end:
            dates = "all dates"
        elif start and end and start == end:
            dates = _format_date(start)
        else:
            dates = f"{_format_date(start) if start else 'earliest'} to {_format_date(end) if end else 'today'}"

        entities = jsc.array(jsc.get(qf, "entities"))
        gate_entities = (
            jsc.get(gate_json, "compatible_entities")
            if (gate_ran and jsc.is_array(jsc.get(gate_json, "compatible_entities")))
            else []
        )
        resolutions = (
            jsc.get(resolver_json, "resolutions")
            if (resolved_ran and jsc.is_array(jsc.get(resolver_json, "resolutions")))
            else []
        )

        def _axis_words(axis: Mapping[str, Any]) -> str | None:
            type_set = set(axis["types"])
            rows = [e for e in gate_entities if jsc.truthy(e) and _norm(jsc.get(e, "entity_type")) in type_set]
            if not rows:
                return None  # axis never put in scope
            words: list[Any] = []

            def _add(value: Any) -> None:
                if value not in words:
                    words.append(value)

            for res in resolutions:  # 1. the customer's own typed token
                hits = any(
                    jsc.truthy(m) and _norm(jsc.get(m, "entity_type")) in type_set
                    for m in jsc.array(jsc.get(res, "matches"))
                )
                token = jsc.nullish_str(jsc.get(res, "token"), "").strip()
                if hits and token:
                    _add(raw_of_tok(token))
            if not words:  # 2. the parser's own hinted raw
                for e in entities:
                    if not jsc.truthy(e) or _norm(jsc.get(e, "hint")) not in axis["hints"]:
                        continue
                    value = jsc.nullish_str(jsc.get(e, "raw"), "").strip()
                    if value:
                        _add(value)
            if not words:  # 3. last resort: the gate's own label
                for row in rows:
                    value = jsc.nullish_str(jsc.get(row, "title") or jsc.get(row, "code"), "").strip()
                    if value:
                        _add(value)
            return ", ".join(jsc.js_string(w) for w in words)

        lines: list[str] = []
        for axis in _AXES:
            words = _axis_words(axis)
            if axis["always"]:
                lines.append(f"{axis['label']}: {words or axis['all_text']}")
            elif words:
                lines.append(f"{axis['label']}: {words}")
        lines.append(f"Dates: {dates}")
        output["user_response"] = "\n".join(lines) + "\n\n" + output["user_response"]
    except Exception:  # noqa: BLE001 - a disclosure bug must never block the answer
        return


# --------------------------------------------------------------------------- #
# MI-D: the media confirmation, merged into the answer
# --------------------------------------------------------------------------- #

# On a media-derived turn only these entity kinds are meaningful; OCR noise the extractor
# reads off the image (sizes, dates, loose furniture words hinted as category) must not
# become lookup entities and must not appear in this prefix.
_MEDIA_ALLOW_HINTS = frozenset({"product", "customer", "order", "promotion"})
# Attribute-kind clauses are self-describing and never become entities. All except
# `document number` are dropped as noise; document number is the one attribute kind the
# captain named meaningful.
_MEDIA_DROP_ATTR_LABELS = (
    "size", "quantity", "batch number", "barcode", "box dimension", "document date",
)
_MEDIA_SHAPE_RE = re.compile(r"^(I read )(.+?)( from that photo\.)([\s\S]*)$")
_MEDIA_TAIL_RE = re.compile(r"\s*[^.!?]*\?\s*$")


def _media_confirm_prefix(  # noqa: PLR0912 - one ported block, kept whole
    output: dict[str, Any],
    *,
    qf: Mapping[str, Any],
    ctx: Mapping[str, Any],
    resolver_json: Any,
    resolved_ran: bool,
) -> None:
    """Prepend the CRM's photo / voice confirmation to whatever this node ends up sending.

    Option D (captain, 2026-08-22): the media confirmation is MERGED into the answer, not
    sent as a separate message. Placed as the LAST statement before the seal so it applies
    exactly once regardless of which branch produced `user_response`.

    A VOICE turn quotes the transcript verbatim and has no item list, so the shape regex
    simply does not match and the sentence passes through UNLABELED - the removed splice
    risked landing mid-word ("SRT (product)WC286SH") and putting labels inside a quoted
    transcript.
    """
    try:
        # RS-4: `patch-transcript` moved into `sub-media-intake`, so this reads the
        # nullable `ctx.media` hub key. Same three states, one less by-name producer.
        media_ctx = jsc.get(ctx, "media")
        if media_ctx is None:
            return  # text turn - no media, no-op
        media = jsc.get(jsc.get(media_ctx, "message"), "_media") or {}
        raw_full = jsc.get(media, "confirmation_text")
        if not isinstance(raw_full, str) or not raw_full.strip():
            return  # media turn but nothing to confirm
        if not isinstance(output.get("user_response"), str) or not output["user_response"].strip():
            return

        # NOTICE SPLIT: media-route appends degraded-tier notices AFTER the confirmation
        # sentence, joined with a blank line. Only the confirmation segment gets the
        # interrogative-tail strip; notices are carried through verbatim.
        blank = raw_full.find("\n\n")
        raw = raw_full if blank == -1 else raw_full[:blank]
        notices_tail = "" if blank == -1 else raw_full[blank + 2 :]

        def _join_notices(text: str) -> str:
            return f"{text}\n\n{notices_tail}" if notices_tail else text

        # 1. strip the trailing confirmation question ("Is that right?").
        stripped = _MEDIA_TAIL_RE.sub("", raw).strip()
        statement = stripped or re.sub(r"\?+\s*$", "", raw).strip()

        # 2. label source per token: the resolver's `entity_type` PRIMARY (open
        # vocabulary), the parser `hint` FALLBACK, bare when neither classifies.
        q_entities = jsc.array(jsc.get(qf, "entities"))
        resolutions = (
            jsc.get(resolver_json, "resolutions")
            if (resolved_ran and jsc.is_array(jsc.get(resolver_json, "resolutions")))
            else []
        )
        # The resolver's `token` is space-stripped before it ever reaches the resolver
        # (dashes kept); the parser's `raw` is the UNSTRIPPED spelling and is what
        # actually appears in `confirmation_text`. Join on the normalised key so the
        # search is for the text as it READS, while the type comes from the resolver.
        q_by_norm: dict[str, Any] = {}
        for e in q_entities:
            if jsc.truthy(e) and jsc.truthy(jsc.get(e, "raw")):
                q_by_norm.setdefault(_tok_key(jsc.get(e, "raw")), e)

        label_for: dict[str, dict[str, Any]] = {}
        for res in resolutions:
            token = jsc.get(res, "token")
            if not jsc.truthy(token):
                continue
            matches = jsc.array(jsc.get(res, "matches"))
            m = matches[0] if matches else None
            if m is None or not jsc.truthy(jsc.get(m, "entity_type")):
                continue
            key = _tok_key(token)
            qe = q_by_norm.get(key)
            # `attachment_type` is the request's FILTER (the caption "check product
            # photo"), never something read FROM the image: skipped by hint, not value.
            if qe is not None and jsc.lower_or_empty(jsc.get(qe, "hint")) == "attachment_type":
                continue
            hint = jsc.lower_or_empty(jsc.get(qe, "hint")) if qe is not None else None
            allowed = (
                hint in _MEDIA_ALLOW_HINTS
                if hint
                else jsc.lower_or_empty(jsc.get(m, "entity_type")) in _MEDIA_ALLOW_HINTS
            )
            label_for[key] = {"type": jsc.js_string(jsc.get(m, "entity_type")), "allowed": allowed}
        for e in q_entities:
            if not jsc.truthy(e) or not jsc.truthy(jsc.get(e, "raw")) or not jsc.truthy(jsc.get(e, "hint")):
                continue
            key = _tok_key(jsc.get(e, "raw"))
            if jsc.js_string(jsc.get(e, "hint")).lower() == "attachment_type":
                continue
            if key in label_for:
                continue  # the resolver already classified it
            label_for[key] = {
                "type": jsc.get(e, "hint"),
                "allowed": jsc.js_string(jsc.get(e, "hint")).lower() in _MEDIA_ALLOW_HINTS,
            }

        # 3. `wording.py` builds the sentence as a fixed "I read <items> from that photo."
        # shape, joined ", " with " and " before the last.
        shape = _MEDIA_SHAPE_RE.match(statement)
        if shape:
            lead, items_blob, tail, rest = shape.group(1), shape.group(2), shape.group(3), shape.group(4)
            comma_parts = items_blob.split(", ")
            if len(comma_parts) > 1:
                last = comma_parts.pop()
                last_parts = last.split(" and ")
                items = comma_parts + (last_parts if len(last_parts) == 2 else [last])
            else:
                two_parts = items_blob.split(" and ")
                items = two_parts if len(two_parts) == 2 else [items_blob]

            kept: list[str] = []
            for raw_item in items:
                item = raw_item.strip()
                if not item:
                    continue
                if any(item.lower().startswith(label + " ") for label in _MEDIA_DROP_ATTR_LABELS):
                    continue  # drop: a recognised noise attribute kind
                found = label_for.get(_tok_key(item))
                if found is not None:
                    if not found["allowed"]:
                        continue  # drop: a disallowed hint (e.g. category)
                    label = _prettify_type(found["type"])
                    kept.append(f"{item} ({label})" if label else item)
                else:
                    kept.append(item)  # unrecognised clause: keep bare, never guessed

            if kept:
                joined = kept[0] if len(kept) == 1 else ", ".join(kept[:-1]) + " and " + kept[-1]
                statement = f"{lead}{joined}{tail}{rest}"
                output["user_response"] = f"{_join_notices(statement)}\n\n{output['user_response']}"
            elif notices_tail:
                # Nothing survived the allow-set, so the entity confirmation is skipped
                # (never invent CRM-unsourced wording) - but a notice still carries real
                # information, e.g. a degraded tier, and must still reach the customer.
                output["user_response"] = f"{notices_tail}\n\n{output['user_response']}"
            return

        output["user_response"] = f"{_join_notices(statement)}\n\n{output['user_response']}"
    except Exception:  # noqa: BLE001 - never block the answer on a labelling bug
        return
