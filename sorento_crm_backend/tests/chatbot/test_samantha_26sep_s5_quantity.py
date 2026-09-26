"""Phase 2 RED tests - issue #1262 (Samantha case), group B, slice 5, finding F4.

Turns T5 and T7 to T10 of the diagnosed conversation. Source:
`documentation/plans/chatbot/PLAN-chatbot-samantha-slices-26sep.md` slice 5 and
`chatbot-samantha-slices-26sep-acceptance-criteria.md` AC-S5-1 to AC-S5-4.

Owner ruling 1 (binding, issue comment 26 Sep ~06:40Z): "i don't want hard code, the
parser supposed to be able to identify the quantity right?" - NO regex strip of "xN" /
"N pcs" anywhere in code. The parser schema gets a per-entity `quantity`, the prompt
tells it a leading/trailing "xN"/"N pcs" IS that quantity and is never part of the raw,
and `media_extract/service.py` keeps a photo's caption and its codes apart (instead of
gluing them into one string) so the parser can read them as separate things. Code only
ever reads what the parser already decided; nothing here folds, strips or pattern-matches
a quantity out of a code string.

Today: `head/parser.py`'s entity schema has no `quantity` key at all (only the
message-level `demand_qty`); `media_extract/service.py::build_image_result_body` builds
`rendered_text = f"{caption}: {', '.join(raws)}"`, gluing a caption ("X5") straight onto
the product code ("M210-GM") as `"X5: M210-GM"` (T10) and dropping every per-line
quantity attribute the vision step already read (T5); nothing downstream names a
product's quantity beside its code in a reply.
"""
from __future__ import annotations

from app.services.chatbot.head.parser import _build_json_schema
from app.services.chatbot.turn.state import fold_token
from app.services.chatbot.lanes.business.resolve_gate import _token_of


# --------------------------------------------------------------------------- #
# AC-S5-1: the parser schema carries a per-entity quantity, and the prompt says
# a leading/trailing "xN" / "N pcs" IS that quantity.
# --------------------------------------------------------------------------- #


def test_parser_schema_carries_a_per_entity_quantity() -> None:
    schema = _build_json_schema()
    entity_props = schema["properties"]["entities"]["items"]["properties"]

    assert "quantity" in entity_props, (
        f"the entity item schema must carry its own 'quantity' key: {entity_props.keys()}"
    )
    assert entity_props["quantity"]["type"] == ["number", "null"], (
        f"'quantity' must be an optional number: {entity_props['quantity']}"
    )


def test_quantity_is_required_in_the_strict_entity_schema() -> None:
    """Phase 3 fix-round ask (coordinator, 26 Sep): the entity item's own `required`
    list must carry "quantity" alongside its siblings - strict-mode structured output
    (AC-105's own note, `llm_provider.py`'s `strict: True`) rejects a `properties` key
    absent from `required`, so a `quantity` key with no matching `required` entry
    would 422 every parser call, not merely fail to populate.
    """
    schema = _build_json_schema()
    entity_item = schema["properties"]["entities"]["items"]
    assert "quantity" in entity_item["required"], (
        f"'quantity' must be in the entity item's own required list: {entity_item['required']!r}"
    )


def test_prompt_says_xn_is_a_quantity_not_part_of_the_raw() -> None:
    """Read the raw prompt SOURCE TEXT (`app/services/chatbot_parser_prompt.py`) rather
    than any one named constant - the new rule ships as a new unlabelled version
    (PLAN ruling 10), and this file adds it as an addendum constant, a rewrite of the
    live body, or both; the coder's own naming is not this test's business. What must
    be true regardless of the constant's name: SOME text the parser is fed says a
    leading or trailing "xN" / "N pcs" names the entity's quantity, and is not part of
    its raw/code."""
    import pathlib

    prompt_file = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "chatbot_parser_prompt.py"
    )
    text = prompt_file.read_text(encoding="utf-8", errors="ignore").lower()

    names_quantity_rule = "quantity" in text and (
        "xn" in text.replace(" ", "") or "n pcs" in text or "pcs" in text
    )
    names_not_part_of_raw = "not part of" in text or "never part of" in text

    assert names_quantity_rule and names_not_part_of_raw, (
        "the parser prompt source must say a leading/trailing 'xN'/'N pcs' is the "
        "entity's quantity and is never part of its raw/code - found no such rule"
    )


# --------------------------------------------------------------------------- #
# AC-S5-2 (T10): caption "X5", code "M210-GM" - kept apart, not glued.
# --------------------------------------------------------------------------- #


def test_t10_photo_caption_and_code_are_not_glued() -> None:
    from app.services.media_extract.schema import MediaEntity, MediaExtraction
    from app.services.media_extract.service import build_image_result_body

    extraction = MediaExtraction(entities=[MediaEntity(raw="M210-GM", hint="product")])
    body = build_image_result_body(extraction, caption="X5", max_entities=10)
    rendered = body["rendered_text"] or ""

    assert "X5: M210-GM" not in rendered, (
        f"the caption must not be glued onto the code with ': ': {rendered!r}"
    )
    assert "X5" in rendered and "M210-GM" in rendered, (
        f"both the caption and the code must still reach the parser's text: {rendered!r}"
    )


# --------------------------------------------------------------------------- #
# AC-S5-3 (T5): per-line quantities (x3, x4) travel with their own codes.
# --------------------------------------------------------------------------- #


def test_t5_rendered_text_keeps_line_quantities() -> None:
    from app.services.media_extract.schema import MediaAttribute, MediaEntity, MediaExtraction
    from app.services.media_extract.service import build_image_result_body

    extraction = MediaExtraction(
        entities=[
            MediaEntity(raw="SRTBF 11502", hint="product"),
            MediaEntity(raw="SRTBF 11503", hint="product"),
        ],
        attributes=[
            MediaAttribute(kind="quantity", raw="3", entity_raw="SRTBF 11502"),
            MediaAttribute(kind="quantity", raw="4", entity_raw="SRTBF 11503"),
        ],
    )
    body = build_image_result_body(extraction, caption=None, max_entities=10)
    rendered = body["rendered_text"] or ""

    lines = [ln for ln in rendered.split("\n") if ln.strip()]
    line_11502 = next((ln for ln in lines if "SRTBF 11502" in ln), "")
    line_11503 = next((ln for ln in lines if "SRTBF 11503" in ln), "")

    assert "3" in line_11502, (
        f"SRTBF 11502's own quantity (3) must travel beside its own code: {rendered!r}"
    )
    assert "4" in line_11503, (
        f"SRTBF 11503's own quantity (4) must travel beside its own code: {rendered!r}"
    )
    assert line_11502 != line_11503, (
        f"the two products' quantities must not collapse onto one shared line: {rendered!r}"
    )


# --------------------------------------------------------------------------- #
# AC-S5-4: the reply names the product with the parser's own quantity.
# --------------------------------------------------------------------------- #


def test_t10_reply_names_the_parser_quantity_beside_the_code() -> None:
    """Seam: `turn/state.py::focus_row_label` - the ONE shared "how does a row name
    itself" function `turn/compose.py::_subject_line` and `tail/scope_block.py::
    _focus_words` both already read (tester's own choice, module docstring: "one
    place, one place to update"). A focus row carrying the parser's own `quantity`
    must print it beside the code, "M210-GM (x5)" - never a second regex reading a
    quantity back out of the raw text (owner ruling 1)."""
    from app.services.chatbot.turn.state import focus_row_label

    row = {"raw": "M210-GM", "canonical_code": "M210-GM", "quantity": 5}
    label = focus_row_label(row)

    assert label == "M210-GM (x5)", (
        f"a focus row's own parser-emitted quantity must print beside its code: {label!r}"
    )


def test_focus_row_label_unchanged_with_no_quantity() -> None:
    """Guard: a row with no quantity at all (every row before this slice) prints
    exactly as it always did."""
    from app.services.chatbot.turn.state import focus_row_label

    row = {"raw": "M210-GM", "canonical_code": "M210-GM"}
    assert focus_row_label(row) == "M210-GM"


# --------------------------------------------------------------------------- #
# Guard named by the captain's test list: no quantity regex in the token fold.
# --------------------------------------------------------------------------- #


def test_no_quantity_regex_in_the_token_fold() -> None:
    """`fold_token` (`turn/state.py`) and `_token_of` (`resolve_gate.py`) must never
    strip a leading "xN" out of a code - owner ruling 1 is that the PARSER identifies
    the quantity as its own field, not that any downstream fold learns to peel one
    off a string. Both stay exactly what they are today."""
    assert fold_token("M210-GM") == "M210GM", (
        "fold_token must keep stripping only separators, never a quantity prefix"
    )
    assert _token_of({"canonical_code": None, "raw": "X5: M210-GM"}) == "X5: M210-GM", (
        "_token_of must never regex-strip a glued 'X5: ' prefix off a raw string - "
        "the fix is the parser never emitting that glued string in the first place"
    )
