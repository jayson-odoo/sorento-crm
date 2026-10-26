"""PROMPT-DIET-V66 red tests: the real diet EDITS on the ENTITY CONFIDENCE block in its prod v65 and v66 shapes.

Prod v66 (the production parser text since 26 Oct) is v65 with `one ` dropped before `<customer name>` in three lines of
this block (owner edit, 12 chars); every other diet anchor is the same in both (measured on the exact texts,
documentation/plans/chatbot/PLAN-prompt-diet-v66-26oct.md). Pure, no database.
"""
from __future__ import annotations

import pytest

from app.services import chatbot_prompt_diet_edits as diet

MARKER = "== LOOKUP LISTS =="
FILLER = "Filler rule one for {{current_date}}.\nFiller rule two stays."
OWNER_TOKEN = "one <customer name>"

# The block as prod v65 carries it, and as #1867 measured it after the diet edits.
CONFIDENCE_V65 = 'Each entity also carries a "confident" boolean \u2014 your certainty that entity.raw is ONE\ncleanly-typed referent, and NOT a mash of several concepts forced together.\n  - confident: true  → entity.raw is a single clean referent: a single word, a multi-word\n    phrase that names ONE thing ("water closet", "<customer name>"), or a part\n    the USER explicitly labeled. This is the DEFAULT \u2014 when unsure, prefer true.\n  - confident: false → you had to cram MORE THAN ONE concept/type into a single\n    entity.raw because the user gave NO separation or label, so you cannot split it\n    without guessing. Example: "one <customer name> srtkt72ss" = quantity + a customer-ish name +\n    a product code mashed together with no labels → ONE order entity, confident:false.\n  A lone code or single token is ONE clean referent → confident:true EVEN IF you doubt it\n  exists in the system \u2014 existence is the resolver\'s job, not yours. Set confident:false\n  ONLY when you had to cram MORE THAN ONE untyped concept into a single raw because the\n  user gave no separation or label.\n  When the user DOES label the parts, SPLIT into separate entities, each confident:true:\n    "customer one <customer name>, product srtkt72ss"\n      → { "raw":"one <customer name>",  "hint":"customer", "confident":true }\n      → { "raw":"srtkt72ss", "hint":"product",  "confident":true }\n  Vagueness is SEMANTIC, not word-count: a multi-word phrase that is ONE referent is\n  confident:true; a single untyped mash of several distinct values is confident:false.\n\nAlso emit ONE entity_op describing how this turn relates to the previous entities:\n  - "clear"          → the user broadened the ENTITY scope to everything with NO narrowing value ("show all promotions", "list everything"). entities = [].\n                       Widening ONE axis is NOT "clear" \u2014 see BROADEN AXIS. Clearing entities there throws away the question the user is still asking.\n  - "replace_combine"→ the user named one or more NEW scoping values. The new values REPLACE the previous scope. Put the new values in entities. (Use this when the user gives a new product, promotion, category, brand, customer, etc. \u2014 even if it looks related to the old one.)\n  - "replace"        → "only X" / "just X" (in any language) sets entity_op "replace" whenever X is NOT the whole subject already on its own - "only TCNU3167091" over a subject that also carries a product, "just the SO" over one that also carries a customer. THIS MESSAGE\'s own entities become the WHOLE scope: every OTHER carried value is dropped too, not just replaced on its own axis. Different from "replace_combine": a plain new value there REPLACES the axis it names and KEEPS every other carried axis (a new product still keeps the carried customer); "only"/"just" replaces the WHOLE scope with this message\'s own entities alone, carrying nothing else forward.\n  - "modify"         → same subject as before, only an attribute changes ("the same product but its price instead"). entities = the unchanged subject; the attribute change shows in domain/intent.\n  - "reuse"          → the current message adds no new scoping value and refers to the SAME thing as before. Downstream re-applies the previous entities unchanged.\n\nPick exactly one. When unsure between replace_combine and reuse: if the message names\na concrete new value → replace_combine; if it names none → reuse.'
CONFIDENCE_V65_DIET = 'Each entity also carries a "confident" boolean:\n  - confident: true → a single clean referent: one word, a multi-word phrase naming ONE thing ("water closet", "<customer name>"), a part the USER labeled, or a lone code / single token EVEN IF you doubt it exists in the system. DEFAULT: when unsure, true.\n  - confident: false → ONLY when you had to cram MORE THAN ONE concept/type into one entity.raw because the user gave NO separation or label, so you cannot split it without guessing: "one <customer name> srtkt72ss" = quantity + a customer-ish name + a product code with no labels → ONE order entity, confident:false.\n  When the user DOES label the parts, SPLIT into separate entities, each confident:true:\n    "customer one <customer name>, product srtkt72ss"\n      → { "raw":"one <customer name>",  "hint":"customer", "confident":true }\n      → { "raw":"srtkt72ss", "hint":"product",  "confident":true }\n\nAlso emit ONE entity_op, how this turn relates to the previous entities:\n  - "clear" → the user broadened the ENTITY scope to everything with NO narrowing value ("show all promotions", "list everything"); entities = []. Widening ONE axis is NOT "clear" (see BROADEN AXIS).\n  - "replace_combine" → the user named one or more NEW scoping values (a new product, promotion, category, brand, customer, etc., even if it looks related to the old one): they REPLACE the previous scope; put them in entities.\n  - "replace" → "only X" / "just X" (in any language) when X is NOT the whole subject already on its own ("only TCNU3167091" over a subject that also carries a product, "just the SO" over one that also carries a customer): THIS MESSAGE\'s own entities become the WHOLE scope, every OTHER carried value dropped too. Unlike "replace_combine", where a plain new value REPLACES the axis it names and KEEPS every other carried axis (a new product still keeps the carried customer).\n  - "modify" → same subject as before, only an attribute changes ("the same product but its price instead"); entities = the unchanged subject, the change shows in domain/intent.\n  - "reuse" → no new scoping value, the SAME thing as before; downstream re-applies the previous entities unchanged.\n\nUnsure between replace_combine and reuse: a concrete new value → replace_combine, none → reuse.'
CONFIDENCE_V66 = CONFIDENCE_V65.replace(OWNER_TOKEN, "<customer name>")
CONFIDENCE_V66_DIET = CONFIDENCE_V65_DIET.replace(OWNER_TOKEN, "<customer name>")


def block_edits():
    """The real text edits that land in this block (their anchor sits inside its v65 shape)."""
    return tuple(e for e in diet.EDITS if e.op != "replace_line" and e.anchor in CONFIDENCE_V65)


def text(block: str) -> str:
    return f"{FILLER}\n\n{block}\n\nTail rule.\n{MARKER}\n"


@pytest.fixture(autouse=True)
def _block_edits_only(monkeypatch):
    monkeypatch.setattr(diet, "EDITS", block_edits())


def test_the_two_shapes_differ_by_the_owner_edit_only():
    assert CONFIDENCE_V65.count(OWNER_TOKEN) == 3
    assert len(CONFIDENCE_V65) - len(CONFIDENCE_V66) == 12
    assert block_edits()


def test_v66_block_takes_the_edits_and_keeps_the_owner_edit():
    out = diet.apply(text(CONFIDENCE_V66))
    assert out == text(CONFIDENCE_V66_DIET)
    assert OWNER_TOKEN not in out


def test_v65_block_output_is_unchanged():
    assert diet.apply(text(CONFIDENCE_V65)) == text(CONFIDENCE_V65_DIET)
