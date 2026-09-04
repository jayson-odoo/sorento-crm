"""The eight branch kinds the CRM finishes itself (S3, AC-301).

n8n answers these with a `tag-*` Set, `escalate-catalog` and the shared compile/send path.
The CRM already has all three - `route.decide` stamps the tag, `tail/outcome.escalate_catalog`
is the catalog, and the S2 tail is the compile path - so this module is small on purpose:
it builds the `sub-output` FRAGMENTS each lane would have handed the tail, and the tail
runs unchanged. No second pipeline, no second copy of the reply ladder.

Two of the eight are not catalog arms and are handled here:

* **`access_denied`** never reaches `compile-current-state` at all. n8n's
  `tag-access-denied` goes straight to `sorento-sub-respond-sendmsg-respond5`, whose
  `message` expression IS the whole reply - so the CRM composes that one string and skips
  the tail. That is not an optimisation: a contact who is not allowed the agent must not
  have the turn written into their memory, and running the tail would write it.
* **`offer_hold`** has no canned text. `offer-hold-reply.js` COMPOSES the clarify ask from
  the persisted pool, and `escalate-catalog` then reads `clarify_text` off it by reference.
  `offer_hold_clarify_text` is that composer, and it is deliberately a standalone function
  because the same body is deployed to `clarify-company-reply` too (its own header says
  so), which S5 will need.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.chatbot import jsc
from app.services.chatbot.tail.compile_state import EM_DASH
from app.services.chatbot.contracts import CRM_COMPLETED_BRANCH_KINDS
from app.services.chatbot.copy import CannedCopy

# The eight `branch_kind`s S3 answers, PROJECTED off the one declaration rather than
# repeated: `contracts.CRM_COMPLETED_BRANCH_KINDS` is what the code can finish across every
# slice, and `delegate_for` reads it together with `system_settings.chatbot_completed_lanes`
# to decide a turn. This subset only says which of them THIS module knows how to compose;
# `low_signal` is S4's and is answered by `lanes/casual.py`.
COMPLETED_BRANCH_KINDS: frozenset[str] = CRM_COMPLETED_BRANCH_KINDS - {"low_signal"}

# The one lane that answers WITHOUT the tail, and therefore without a session write.
NO_SESSION_WRITE_BRANCH_KINDS: frozenset[str] = frozenset({"access_denied"})


def access_denied_text(ctx: Mapping[str, Any], copy: CannedCopy) -> str:
    """`sorento-sub-respond-sendmsg-respond5`'s `message` expression, verbatim.

    `Sorry, you are not allowed to access {agent}`, where the agent is the parser's
    `suggested_agent` with **em-dashes folded to hyphens**. That fold is n8n's own
    (`.replace(/\\u2014/g, '-')`) and it is on the AGENT, not on the sentence: an agent
    name that arrives with an em-dash in it is a parser emission, and the customer must
    not read a character the repo forbids anywhere else.
    """
    routing = jsc.get(jsc.get(jsc.get(ctx, "parse"), "output") or {}, "routing") or {}
    agent = jsc.get(routing, "suggested_agent")
    folded = jsc.js_string(agent if jsc.truthy(agent) else "").replace(EM_DASH, "-")
    return copy.render("access_denied", team=folded)


def offer_hold_clarify_text(
    *,
    routing_roster_plan: Any,
    routing_companies: Any,
    copy: CannedCopy | None = None,
) -> str:
    """`offer-hold-reply.js` - the clarify ask, composed from the PERSISTED pool.

    ONE body, deployed to both `offer-hold-reply` and `clarify-company-reply` (that node's
    own header says so), which is why this is a function and not an arm of a switch.

    The pool is `routing_roster_plan` when it has rows, else `routing_companies`. Names are
    DEDUPED - two pool rows sharing a company collapse to one printed name, and the
    single-name parenthetical still resolves because the parser keys the pick per name.

    Three shapes, and the third is the reason the copy is split in two:

    * two or more names: "Both *A* and *B* teams are listed" / "*A*, *B* and *C* teams ...";
    * one name: "*A* teams are listed" (the JS's own wording, plural verb and all);
    * NO names at all (a degraded pool): the company affordance is DROPPED, because the
      parser's company-pick arm refuses every pick against an empty pool and inviting a
      reply that cannot resolve is worse than asking for one that can.
    """
    from app.services.chatbot.copy import fallback_copy

    canned = copy if copy is not None else fallback_copy()
    plan = routing_roster_plan if jsc.is_array(routing_roster_plan) else []
    pools = plan if len(plan) > 0 else (routing_companies if jsc.is_array(routing_companies) else [])

    names: list[str] = []
    for row in pools:
        name = jsc.get(row, "company_name")
        if jsc.truthy(name) and name not in names:
            names.append(name)
    bold = [f"*{jsc.js_string(n)}*" for n in names]
    joined = (
        f"{', '.join(bold[:-1])} and {bold[-1]}" if len(bold) > 1 else (bold[0] if bold else "")
    )
    if len(names) == 2:
        lead = f"Both {joined} teams are listed"
    elif joined:
        lead = f"{joined} teams are listed"
    else:
        lead = "More than one team is listed"

    if names:
        return lead + canned.render("offer_hold", companies=" / ".join(bold))
    return lead + canned.render("offer_hold_no_companies")


def fragments_for(
    branch_kind: str,
    item: Mapping[str, Any],
    ctx: Mapping[str, Any],
    prev_variables: Mapping[str, Any],
    copy: CannedCopy,
) -> dict[str, Any]:
    """The `sub-output` trigger fields this lane would have handed the tail.

    Everything the tail needs and nothing it does not: `item` is what `route-turn`
    stamped, and `offer_hold` is the one producer output a canned lane supplies (the
    catalog reads `clarify_text` off it by reference). The other eleven trigger fields are
    null on every canned lane, because none of them runs a resolver, a gate or a fetch.
    """
    fragments: dict[str, Any] = {"item": dict(item)}
    if branch_kind == "offer_hold":
        fragments["offer_hold"] = {
            "clarify_company": True,
            "clarify_text": offer_hold_clarify_text(
                routing_roster_plan=prev_variables.get("routing_roster_plan"),
                routing_companies=prev_variables.get("routing_companies"),
                copy=copy,
            ),
        }
    return fragments
