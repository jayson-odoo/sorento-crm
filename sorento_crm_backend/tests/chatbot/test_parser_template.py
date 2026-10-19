"""PARSER-TEMPLATE F1-A (plan PLAN-parser-template-20oct.md): the one consolidated parser prompt.

Red tests: the lint, the template's size and gate markers, the `template` flag on ParserConfig,
the stock-ask regex standing down under the template, and the unlabelled idempotent publisher.
"""
from __future__ import annotations

import re
import types
import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services import ai_prompt_registry
from app.services.chatbot.head import parser as parser_mod
from tests._pg_fixture import blank_session

KEY = parser_mod.PROMPT_KEY
MARKER = "== PARSER TEMPLATE =="


def _pt():
    from app.services.chatbot.head import parser_template

    return parser_template


@pytest.fixture(autouse=True)
def _fresh_cache():
    ai_prompt_registry.bust_cache()
    yield
    ai_prompt_registry.bust_cache()


# --- lint on small fixture texts -----------------------------------------------------------------

CLEAN = f"""{MARKER}
R-P1-01 Relation to the state
Read state_changes first. Say what the message does to the held list.

R-P2-01 Entities in this message
Pick the product the message names from the candidate block, or none.

R-P3-02 Domain
The `domain_hint` follows the thing asked about.
"""


def test_lint_clean_text_passes():
    assert _pt().lint(CLEAN) == []


def test_lint_missing_rule_id_fails():
    text = CLEAN + "\nEntities without an id\nPick the product the message names.\n"
    assert _pt().lint(text) != []


def test_lint_duplicate_ids_fail():
    text = CLEAN + "\nR-P1-01 Relation again\nSecond block with a used id.\n"
    problems = _pt().lint(text)
    assert problems and any("R-P1-01" in p for p in problems)


ABSOLUTE_PAIR = f"""{MARKER}
R-P3-01 Domain of a count
The `domain_hint` is ALWAYS stock when a count sits beside a code.

R-P3-02 Domain of a lone item
The `domain_hint` is NEVER stock when only another item is named.
"""


def test_lint_two_absolute_rules_over_one_field_fail_without_a_see_link():
    problems = _pt().lint(ABSOLUTE_PAIR)
    assert problems and any("domain_hint" in p for p in problems)


def test_lint_two_absolute_rules_pass_once_one_names_the_other():
    linked = ABSOLUTE_PAIR.replace(
        "The `domain_hint` is NEVER stock when only another item is named.",
        "The `domain_hint` is NEVER stock when only another item is named (see R-P3-01).",
    )
    assert _pt().lint(linked) == []


@pytest.mark.parametrize("word", ["overrides", "override", "alias"])
def test_lint_override_or_alias_wording_fails(word):
    text = CLEAN + f"\nR-X-01 Extra\nThis rule {word} the earlier ones.\n"
    assert _pt().lint(text) != []


def _word_list(n: int) -> str:
    items = ", ".join(f'"word{i}"' for i in range(n))
    return CLEAN + f"\nR-X-02 Triggers\nAsking for stock is any of {items}.\n"


def test_lint_nine_item_quoted_word_list_fails():
    assert _pt().lint(_word_list(9)) != []


def test_lint_eight_item_quoted_word_list_passes():
    assert _pt().lint(_word_list(8)) == []


# --- the template itself -------------------------------------------------------------------------


def test_template_lints_clean():
    assert _pt().lint(_pt().TEMPLATE) == []


def test_template_keeps_gate_markers():
    lines = [ln.strip() for ln in _pt().TEMPLATE.splitlines()]
    for marker in ("== CLOSED LISTS ==", "== CODE LOOKUP ==", MARKER):
        assert marker in lines


def test_template_size_at_most_90k():
    assert len(_pt().TEMPLATE) <= 90_000


def test_template_has_marker():
    assert _pt().MARKER == MARKER
    assert MARKER in [ln.strip() for ln in _pt().TEMPLATE.splitlines()]


# --- ParserConfig.template -----------------------------------------------------------------------


def _version(db, template: str, *, label: str | None = None) -> AIPromptVersion:
    versions = [v for (v,) in db.query(AIPromptVersion.version).filter(AIPromptVersion.name == KEY)]
    row = AIPromptVersion(
        id=str(uuid.uuid4()), name=KEY, version=max(versions, default=0) + 1, type="text", template=template,
        variables=["current_date"],
    )
    db.add(row)
    db.flush()
    if label:
        db.add(AIPromptLabel(id=str(uuid.uuid4()), name=KEY, label=label, version_id=row.id))
        db.flush()
    return row


def _stub_resolve(monkeypatch):
    from app.services import ai_assistant_service, chatbot_prompt_vars, llm_provider

    monkeypatch.setattr(parser_mod, "render", lambda db, key, current_date, override_version_id=None: ("sys", 1))
    monkeypatch.setattr(parser_mod, "agent_model", lambda db, key: (None, None))
    monkeypatch.setattr(
        ai_assistant_service.AIAssistantConfigService, "get",
        lambda self: types.SimpleNamespace(provider="openai", model="m"),
    )
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda config, provider: "k")
    monkeypatch.setattr(chatbot_prompt_vars, "closed_list_enum", lambda db: [])


def test_config_template_flag_follows_marker(monkeypatch):
    _stub_resolve(monkeypatch)
    with blank_session() as db:
        with_marker = _version(db, f"parser\n{MARKER}\nbody")
        without = _version(db, "parser body", label="production")

        def cfg(row):
            return parser_mod.resolve_config(db, current_date="2026-10-20", override_version_id=row.id)

        assert cfg(with_marker).template is True
        assert cfg(without).template is False
    default = parser_mod.ParserConfig(system_prompt="x", prompt_version=1, provider="openai", model="m", api_key="k")
    assert default.template is False


# --- the stock-ask regex stands down -------------------------------------------------------------


def _incoming_verdict() -> dict:
    return {
        "intent_hint": "check_incoming",
        "domain_hint": "incoming",
        "requested_attributes": [],
        "entities": [{"raw": "CWCX611", "hint": "product", "canonical_code": "CWCX611", "quantity": 300}],
        "asks": [],
    }


def test_stock_ask_regex_stands_down_under_the_template():
    from app.services.chatbot import engine

    # Off: put back to inventory, exactly as today.
    off = engine._as_a_stock_ask_by_its_own_words(_incoming_verdict(), "CWCX611 x 300")
    assert off["domain_hint"] == "inventory" and off["intent_hint"] == "check_stock"
    # master_products reading is put back too when off.
    mp = {**_incoming_verdict(), "intent_hint": "check_product", "domain_hint": "master_products"}
    assert engine._as_a_stock_ask_by_its_own_words(mp, "CWCX611 x 300")["domain_hint"] == "inventory"
    # On: the parser's verdict stands (R-DOM-QTY in the prompt decides).
    on = engine._as_a_stock_ask_by_its_own_words(_incoming_verdict(), "CWCX611 x 300", template=True)
    assert on["domain_hint"] == "incoming" and on["intent_hint"] == "check_incoming"
    on_mp = engine._as_a_stock_ask_by_its_own_words(mp, "CWCX611 x 300", template=True)
    assert on_mp["domain_hint"] == "master_products"


# --- the publisher -------------------------------------------------------------------------------


def _publisher():
    from scripts import publish_parser_template

    return publish_parser_template


def test_publisher_publishes_unlabelled_and_is_idempotent():
    with blank_session() as db:
        _version(db, "older parser", label="production")
        first = _publisher().publish(db)
        again = _publisher().publish(db)

        row = db.query(AIPromptVersion).filter(AIPromptVersion.name == KEY, AIPromptVersion.version == first).one()
        assert first == 2
        assert row.template == _pt().TEMPLATE
        assert again is None
        assert db.query(AIPromptVersion).filter(AIPromptVersion.name == KEY).count() == 2
        labels = db.query(AIPromptLabel).filter(AIPromptLabel.name == KEY).all()
        assert [lb.version_id for lb in labels] == [db.query(AIPromptVersion).filter_by(name=KEY, version=1).one().id]


# --- contract gaps from the rule map (B7, B2, B4) ------------------------------------------------


def test_template_turns_on_the_state_block(monkeypatch):
    """B7: the CHAT-STATE heading is a gate marker the code reads off the raw template
    (`chat_state_prompt.HEADING`, present on this branch), so a version published from TEMPLATE
    must turn every gate on."""
    from app.services.chatbot.head.chat_state_prompt import HEADING

    template = _pt().TEMPLATE
    assert HEADING in [ln.strip() for ln in template.splitlines()]
    _stub_resolve(monkeypatch)
    with blank_session() as db:
        row = _version(db, template)
        cfg = parser_mod.resolve_config(db, current_date="2026-10-20", override_version_id=row.id)
        assert cfg.state_block is True
        assert cfg.closed_lists is True
        assert cfg.code_lookup is True
        assert cfg.template is True


def test_template_keeps_the_names_find_rule_cites():
    """B2: FIND_RULE is rendered into production through {{find_filters}} and names a section
    of the parser prompt; the template must still carry that name."""
    import re

    from app.services.product_find import FIND_RULE

    cited = set(re.findall(r"[A-Z]{3,}(?: [A-Z]{3,}){2,}", FIND_RULE))
    assert "BARE ENTITY CONTINUATION" in cited
    for name in cited:
        assert name in _pt().TEMPLATE, name


def test_template_uses_the_registry_variables():
    """B4: no literal registry list (the drift test's own check) and the placeholders in place."""
    from app.services import chatbot_prompt_vars as pv

    template = _pt().TEMPLATE
    assert pv.literal_lists(template) == []
    for name in pv.LITERAL_LIST_PATTERNS:
        assert name in pv.VARIABLE_NAMES
        assert "{{" + name + "}}" in template, name


# --- F1-C: prompt-layer risks found by the read-only check of TEMPLATE ---------------------------


def _rule_blocks(text: str) -> list[str]:
    import re

    blocks: list[str] = []
    for line in text.splitlines():
        if re.match(r"R-(?:P[123]|X)-\d\d\b", line):
            blocks.append(line)
        elif blocks:
            blocks[-1] += "\n" + line
    return blocks


def _sentences(text: str) -> list[str]:
    import re

    return [s for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]


def test_template_explains_ranking_drill():
    """report_ask.py reads a null ranking_drill as unsure and asks again; twice -> SCOPE_GIVE_UP.
    The reply to 'above, or across all?' is read ONLY from ranking_drill, so the prompt must set it."""
    template = _pt().TEMPLATE
    explained = [
        b for b in _rule_blocks(template)
        if "`ranking_drill`" in b and "scoped" in b and "global" in b and "unsure" in b
        and "sales ranking" in b and "group_by" in b
    ]
    assert explained, "no rule explains ranking_drill (scoped / global / unsure) on a sales ranking with its own group_by"
    for sentence in _sentences(template):
        if "`ranking_drill`" in sentence and "null" in sentence and "scoped" not in sentence:
            pytest.fail("ranking_drill is listed among the keys stated null: " + sentence[:160])


def test_template_value_only_narrowing_leaves_domain_null():
    """turn/decide.py R24 `_keeps_subject` treats a domain_hint as the message's own ask, which drops
    the stored scope; a reply that only narrows by a value must leave domain_hint null (v178)."""
    import re

    found = [
        s for s in _sentences(_pt().TEMPLATE)
        if re.search(r"narrow", s, re.I) and "`domain_hint`" in s and re.search(r"\bnull\b", s)
        and re.search(r"purpose|ask of its own|own ask|new ask", s, re.I)
    ]
    assert found, "no sentence says a value-only narrowing with no new purpose leaves `domain_hint` null"


def test_template_does_not_ask_for_unconfident_hints_when_guessing():
    """_unsure_capture_as_codes drops the non-code words of `hint_confident` false entities for
    dealers, so the prompt must not tell the model to flag a guessed kind that way."""
    import re

    for sentence in _sentences(_pt().TEMPLATE):
        if re.search(r"guess|unsure of its kind", sentence, re.I) and "`hint_confident`" in sentence \
                and re.search(r"false", sentence):
            pytest.fail("guessing is tied to hint_confident false: " + sentence[:160])


# --- F1-D: gate run 1 fixes (precedence and priming) ---------------------------------------------


def _block(rule_id: str) -> str:
    found = [b for b in _rule_blocks(_pt().TEMPLATE) if b.startswith(rule_id)]
    assert found, f"no rule block {rule_id}"
    return found[0]


def test_template_file_word_defers_to_file_rule():
    """D1: R-P2-02's closed-list sentence must not make file types a word-less closed list over
    R-P2-06; one rule decides the file word, and videos are handled as photos are."""
    cand = _block("R-P2-02")
    assert "see R-P2-06" in cand, "R-P2-02 does not defer file types to R-P2-06"
    for sentence in _sentences(cand):
        if "no word of its own" in sentence:
            assert not re.search(r"file type", sentence, re.I), (
                "closed-list sentence still names file types: " + sentence[:160]
            )
    file_rule = _block("R-P2-06")
    assert re.search(r"video", file_rule, re.I), "R-P2-06 has no meaning rule for videos"


def test_template_listed_scheme_alone_is_the_whole_certificate_ask():
    """S1 (#1755 F3-b B-5): a listed scheme named is ONE attachment_type entity (listed_item the
    scheme, no separate kind entity beside it; code adds the parent kind); a certificate ask with
    no listed scheme is the kind entity."""
    block = _block("R-P2-06")
    assert not re.search(r"\balways\b[^.\n]{0,80}kind", block, re.I), (
        "R-P2-06 still says a certificate ask always carries the kind entity"
    )
    assert re.search(r"(one|a single|the only|the whole) (attachment_type )?(entity|certificate ask)", block, re.I), (
        "R-P2-06 does not say a listed scheme is one entity"
    )
    assert re.search(r"no (separate )?kind entity|without (a |the )?(separate )?kind entity|kind entity (beside|next to)|not (also )?(a |the )?(separate )?kind", block, re.I), (
        "R-P2-06 does not say no separate kind entity stands beside a listed scheme"
    )
    assert re.search(r"no (listed )?scheme|not (a )?listed scheme|scheme (is|are) not listed", block, re.I) and "Certificate kind" in block, (
        "R-P2-06 does not say a certificate ask with no listed scheme is the kind entity"
    )


def test_template_quantity_only_message_defers_to_stock_rule():
    """S6: R-X-03's quantity sentence must not claim the held domain repeats; after a
    master_products / attachment / promotion answer R-P1-03 makes it a stock ask."""
    block = _block("R-X-03")
    found = [s for s in _sentences(block) if "quantity" in s]
    assert found, "R-X-03 has no quantity sentence"
    for sentence in found:
        assert re.search(r"see (R-P1-0\d, )*R-P1-03", sentence), "quantity sentence does not defer: " + sentence[:200]
        assert not re.search(r"repeat", sentence, re.I), "quantity sentence still says the held fields repeat: " + sentence[:200]


def test_template_attribute_phrase_unprimed_and_still_sold_is_discontinued():
    """D3: no 'list price' example priming an added word; the phrase is the user's own words;
    'still sold' maps to discontinued."""
    block = _block("R-P3-05")
    assert "list price" not in block, "R-P3-05 still primes with the example 'list price'"
    assert re.search(r"own words|no word added|never add|not add|without adding", block, re.I), (
        "R-P3-05 does not say the phrase is the user's own words with no word added"
    )
    assert "still sold" in block and "discontinued" in block, (
        "R-P3-05 does not tie 'still sold' to discontinued"
    )


# --- F1-D round 2 --------------------------------------------------------------------------------


def test_template_procedure_line_defers_file_types_to_file_rule():
    """D4: the R-X-01 P2 line must not say every entity is picked from the candidates block;
    file types and certificates are never in it, so R-P2-06 decides them."""
    block = _block("R-X-01")
    lines = [ln for ln in block.splitlines() if ln.lstrip().startswith("P2.")]
    assert lines, "R-X-01 has no P2 line"
    assert "R-P2-06" in lines[0], "R-X-01 P2 line has no carve-out for R-P2-06: " + lines[0][:200]


def test_template_bare_spec_has_worked_example_with_reason():
    """D3b: 'SRTKT73SS spec' is a request for the whole spec list, not a property called spec."""
    block = _block("R-P3-05")
    assert re.search(r'"[A-Za-z0-9]+ spec"[^\n]{0,40}?(->|is|:)\s*\[\]', block), (
        "R-P3-05 has no worked example of a product code followed by spec mapped to []"
    )
    assert "whole" in block and re.search(r"spec list|all of[^.\n]{0,30}spec", block, re.I), (
        "R-P3-05 does not give the reason (whole spec list)"
    )


def test_template_stated_quantity_is_a_stock_ask_after_any_answer():
    """F1-F (owner ruling 20 Oct): a stated quantity with no ask word of its own is a stock ask
    (inventory / check_stock) whatever the last answer's domain."""
    block = _block("R-P1-03")
    assert not re.search(r"continues the last answer", block, re.I), (
        "R-P1-03 still says a quantity continues the last answer's domain"
    )
    assert not re.search(r"takes no quantity|domain that takes a quantity|when that domain takes", block, re.I), (
        "R-P1-03 still limits the rule to domains that take a quantity"
    )
    first = block.split("\n- ", 1)[0]
    assert "inventory" in first and "check_stock" in first and re.search(r"whatever|any answer|every answer|regardless", first, re.I), (
        "R-P1-03 does not say a stated quantity is a stock ask whatever the last answer"
    )
