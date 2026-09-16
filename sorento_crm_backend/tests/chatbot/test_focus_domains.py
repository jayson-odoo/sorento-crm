"""AC-1012: `dialogue/focus.py::domains_from_asks` - D7, "a domain word with no product
REPLACES `focus.domains`, never appends."

Lane 1 replaces the singular `domain_from_switch_word` rule (today's rule 4, keyed off
`domain_hint`) with `domains_from_asks`, keyed off the parser v3 `asks[]` list, per the
plan's rule order: `replace_same_axis, reset_on_topic, reuse_alive, domains_from_asks,
date_restated_only, anaphora_reuses, confident_guard`.

RED: `app.services.chatbot.dialogue.focus` has no `domains_from_asks` attribute yet (only
today's singular `domain_from_switch_word`). Same harness as
`tests/chatbot/test_focus_rules.py` (`fr.Turn`, `fr.Outputs`, `fr.slot`).
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot.dialogue import focus as fr


def _turn(o: dict[str, Any], **kw: Any):
    base = {"prev": {}, "turn_no": 5}
    base.update(kw)
    return fr.Turn(o=o, **base)  # type: ignore[arg-type]


class TestDomainsFromAsks:
    def test_domain_word_without_product_replaces_domains(self) -> None:
        assert hasattr(fr, "domains_from_asks"), (
            "dialogue/focus.py has no domains_from_asks rule yet - only the singular "
            "domain_from_switch_word"
        )

        # -- "PO?": a domain word, no product entity -> REPLACES the whole list ----- #
        turn = _turn({"asks": [{"domain": "purchase_order", "entities": []}]})
        out = fr.Outputs()
        out.focus["domains"] = fr.slot(["inventory", "incoming"], turn_no=3, source="reuse")

        fr.domains_from_asks(out.focus, turn, out)

        assert out.focus["domains"]["value"] == ["purchase_order"], (
            "a domain word with no product must REPLACE focus.domains, never append"
        )

        # -- no asks at all this turn -> the rule is a no-op, leaving whatever the ---- #
        # -- earlier reuse_alive carry already set on out.focus["domains"] ----------- #
        turn_no_ask = _turn({"asks": []})
        out_no_ask = fr.Outputs()
        carried = fr.slot(["incoming"], turn_no=2, source="reuse")
        out_no_ask.focus["domains"] = carried

        fr.domains_from_asks(out_no_ask.focus, turn_no_ask, out_no_ask)

        assert out_no_ask.focus["domains"] == carried, (
            "no asks this turn must reuse the already-set domains list, not clear it"
        )
