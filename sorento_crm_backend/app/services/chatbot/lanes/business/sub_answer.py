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
