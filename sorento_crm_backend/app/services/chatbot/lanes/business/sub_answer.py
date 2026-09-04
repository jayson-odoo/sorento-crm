"""Port of `sub-answer` (S6c, AC-607): the lane an ANSWERED turn takes.

Eight nodes: the item carrier, the LLM-envelope unwrapper, the miss-roster pair, the
member offer, the partial did-you-mean pair, and the exit. `If6` (in `answer.py`) is what
chooses this lane over `miss_suggest.py`.

Bodies are `sub-answer-live`'s, verified against the slug the captures came from
(`sub-answer-live`, 36 captures per node from the 5 Sep batch).

D11: nothing here matches raw customer text. The one text operation is
`central_exchange`'s fence-stripping, which is parsing an LLM's own output envelope, not
reading a customer's words - and it is marked at its line.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.chatbot import jsc

logger = logging.getLogger(__name__)


class AnswerInputError(ValueError):
    """`answer-input` refused the trigger payload, with the sub's own wording."""


def answer_input(trigger: dict[str, Any] | None) -> dict[str, Any]:
    """`answer-input`: the LAST link of the carrier chain, and that placement is the point.

    `central-exchange` reads its input POSITIONALLY (`$input.first().json`), so unlike
    every other mover on this lane it is NOT insulated by the name-preserving stubs: a
    carrier chain ending anywhere else hands it that carrier's narrow re-emission instead
    of the item the spine put on the edge. That shipped once - it received `{ctx}`, echoed
    it, and the customer got no reply at all on 3 of 3 real turns.
    """
    t = trigger if isinstance(trigger, dict) else {}
    item = t.get("item")
    if item is None or not isinstance(item, dict):
        raise AnswerInputError(
            "sub-answer: the trigger carried no `item` object - the contract is "
            "{ ctx, item, result, gate, resolved, aggregate, is_test }"
        )
    return item


# ```json ... ``` fences around an LLM answer. Parsing the model's OWN envelope, not the
# customer's words, which is why D11 does not reach it.
_FENCE_RE = re.compile(r"```[\s\S]*?```")
_FENCE_MARKER_RE = re.compile(r"```json?|```")


def central_exchange(item: dict[str, Any] | None) -> Any:
    """`central-exchange`: unwrap whatever shape the answer arrived in.

    Three shapes, in the JS's own order: an already-parsed `output` object; a string
    carrying JSON, possibly fenced; or the item itself. The odd middle branch where a
    fence-free string is returned AS the output and then has `quick_reply` assigned onto it
    is reproduced rather than corrected - in JS that assignment onto a primitive silently
    does nothing, and "fixing" it would change what the tail receives.
    """
    input_item = item if isinstance(item, dict) else {}
    if isinstance(input_item.get("output"), dict):
        return input_item["output"]

    raw = jsc.js_string(input_item.get("output") or input_item.get("text") or "")
    if not raw:
        return input_item

    # D11-reproduced: `central-exchange`'s own fence strip over the LLM's answer envelope.
    raw = _FENCE_RE.sub(lambda m: _FENCE_MARKER_RE.sub("", m.group(0)), raw)
    idx = raw.find("{")
    if idx == -1:
        # JS assigns `quick_reply` onto a STRING here, which is a no-op. Same shape out.
        return raw
    start_slice = raw[idx:]
    last = start_slice.rfind("}")
    clean_slice = start_slice[: last + 1] if last != -1 else start_slice
    return json.loads(clean_slice)


def answer_result(
    item: dict[str, Any] | None,
    *,
    central_exchange: Any = None,
    member_offer: Any = None,
    dym_annotate_partial: Any = None,
) -> dict[str, Any]:
    """`answer-result`: the sub's ONE exit, two mutually exclusive terminals.

    `outcome_fragment` carries whichever of the three `build-outcome` producers actually
    ran this turn, computed the way `build-outcome`'s own `_one()` would have. There is no
    unaware intermediate between here and its one consumer, which already reads and strips
    the key - so nothing needs to strip it on the way.
    """
    fragment = {
        "central-exchange": central_exchange if central_exchange is not None else None,
        "build-miss-member-offer": member_offer if member_offer is not None else None,
        "dym-annotate-partial": dym_annotate_partial if dym_annotate_partial is not None else None,
    }
    if dym_annotate_partial is not None:
        return {**dym_annotate_partial, "outcome_fragment": fragment}
    return {**(item if isinstance(item, dict) else {}), "outcome_fragment": fragment}


# --------------------------------------------------------------------------- #
# miss-roster-check / miss-roster-plan / build-miss-member-offer
# --------------------------------------------------------------------------- #

# tool -> the parser domain it must ride with, and the routing PAIR(S) it may carry, so
# the offer's phrasing and the human-intervention team stay in lockstep. `members` is FALSE
# on every row: the members half of the feature is not deployed.
#
# This table is the CRM's own `stamp_lookup_companies` set (11 of 11), so "all domains" is
# closed by construction rather than by enumeration luck, and it is MIRRORED BYTE-IDENTICAL
# in `miss_roster_check` and `miss_roster_plan` - which is why it is declared ONCE here.
#
# `crm_master_product_attachments_list` legitimately rides TWO pairs: the parser's routing
# splits `product_attachment` on whether the ask is about a certificate.
MISS_ROSTER_LANE: dict[str, dict[str, Any]] = {
    "crm_order_management_orders_list": {
        "domain": "order",
        "pairs": [("customer_service", "order_enquiries")],
        "members": False,
    },
    "crm_order_management_orders_by_product_list": {
        "domain": "order",
        "pairs": [("customer_service", "order_enquiries")],
        "members": False,
    },
    "crm_incoming_stock_list": {
        "domain": "incoming",
        "pairs": [("purchasing", "incoming_stock_enquiries")],
        "members": False,
    },
    "crm_incoming_stock_by_product": {
        "domain": "incoming",
        "pairs": [("purchasing", "incoming_stock_enquiries")],
        "members": False,
    },
    "crm_incoming_stock_shipments": {
        "domain": "incoming",
        "pairs": [("purchasing", "incoming_stock_enquiries")],
        "members": False,
    },
    "crm_inventory_stock_balance_list": {
        "domain": "inventory",
        "pairs": [("warehouse", "general_enquiries")],
        "members": False,
    },
    "crm_marketing_promotions_list": {
        "domain": "promotion",
        "pairs": [("marketing_promotion", "general_enquiries")],
        "members": False,
    },
    "crm_marketing_promotion_products_list": {
        "domain": "promotion",
        "pairs": [("marketing_promotion", "general_enquiries")],
        "members": False,
    },
    "crm_master_products_list": {
        "domain": "master_products",
        "pairs": [("purchasing", "general_enquiries")],
        "members": False,
    },
    "crm_master_product_attachments_list": {
        "domain": "product_attachment",
        "pairs": [
            ("marketing_product", "general_enquiries"),
            ("purchasing_certification", "general_enquiries"),
        ],
        "members": False,
    },
    "crm_certificates_list": {
        "domain": "product_attachment",
        "pairs": [("purchasing_certification", "general_enquiries")],
        "members": False,
    },
}

# `/would you like me to escalate/i` over the reply this turn already built. A parity
# reproduction of the ONE-offer-per-turn check, not a new read of the customer's words.
_ESCALATE_OFFER_RE = re.compile(r"would you like me to escalate", re.IGNORECASE)


def _miss_roster_offer(
    item: dict[str, Any], *, build_result: dict[str, Any], parser: dict[str, Any]
) -> bool:
    """`computeOffer`: FAIL-CLOSED - any missing signal is `False`.

    Fires only on an ANSWERED turn whose envelope shows EXACTLY ONE queried company with no
    answer. SINGLE MISS ONLY: two or more would persist a multi-entry roster plan, which
    the escalation lane turns into a null-company routing source and hands to a real
    round-robin assign on a pool the customer never picked.

    A qty-0 stock ROW is an answer - its `company_name` field marks that company answered.
    Only a company with ZERO rows is a miss.
    """
    try:
        j = item
        if j.get("has_result") is not True:
            return False
        tool = jsc.js_string((jsc.get(build_result, "tool") or {}).get("name") or "").strip()
        lane = MISS_ROSTER_LANE.get(tool) if tool else None
        if not lane:
            return False
        o = parser or {}
        if o.get("domain_hint") != lane["domain"]:
            return False
        r = o.get("routing") or {}
        if not any(
            p[0] == r.get("suggested_team") and p[1] == r.get("suggested_agent")
            for p in lane["pairs"]
        ):
            return False
        # ONE offer per turn: the cross-domain block and the promo picker are the two other
        # renderers that can put one on the reply.
        block = ((jsc.get(build_result, "xd") or {}).get("block")) or None
        if jsc.truthy(block) and jsc.get(block, "any") is True:
            return False
        # D11-reproduced: `miss-roster-check`'s own one-offer-per-turn check over the reply
        # this turn already built (never the customer's words).
        if _ESCALATE_OFFER_RE.search(jsc.js_string(j.get("response") or "")):
            return False
        p = jsc.get(build_result, "promo") or {}
        if (
            p.get("_brand_gate_closed") is True
            or jsc.truthy(p.get("_promo_notfound"))
            or jsc.truthy(p.get("_promo_unmatched"))
            or jsc.truthy(p.get("_promo_pick"))
            or jsc.truthy(p.get("_promo_picker_shape"))
        ):
            return False
        lc = j.get("lookup_companies") if isinstance(j.get("lookup_companies"), list) else []
        if not lc:
            return False
        ans = j.get("answers") if isinstance(j.get("answers"), list) else []
        if not ans:
            return False
        hit: list[str] = []
        for a in ans:
            f = (
                jsc.find(
                    jsc.get(a, "fields"),
                    lambda x: jsc.truthy(x)
                    and jsc.get(x, "key") == "company_name"
                    and jsc.truthy(jsc.get(x, "value")),
                )
                if jsc.truthy(a) and isinstance(jsc.get(a, "fields"), list)
                else None
            )
            if not jsc.truthy(f):
                return False
            hit.append(jsc.js_string(jsc.get(f, "value")).lower().strip())
        return (
            len(
                [
                    c
                    for c in lc
                    if jsc.truthy(c)
                    and jsc.truthy(jsc.get(c, "name"))
                    and jsc.js_string(jsc.get(c, "name")).lower().strip() not in hit
                ]
            )
            == 1
        )
    except Exception:  # noqa: BLE001 - the JS's own catch: any fault is "no offer"
        return False


def miss_roster_check(
    item: dict[str, Any] | None,
    *,
    build_result: dict[str, Any] | None,
    parser: dict[str, Any] | None,
) -> dict[str, Any]:
    """`miss-roster-check`: stamps `_offer`, and nothing else."""
    body = item if isinstance(item, dict) else {}
    return {
        **body,
        "_offer": _miss_roster_offer(
            body,
            build_result=build_result if isinstance(build_result, dict) else {},
            parser=parser if isinstance(parser, dict) else {},
        ),
    }
