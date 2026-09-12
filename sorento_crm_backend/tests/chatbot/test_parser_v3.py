"""Parser prompt v3: extract only, three new keys, published unpromoted (AC-949, AC-952).

Growth r1 slice B2. What this file holds the change to:

* the v3 TEXT no longer contains any instruction to continue the previous domain or to
  re-emit previous entities, and every other section of the SLIM prompt survives;
* the three new keys are on the WIRE for every version, and `output_exchange` tolerates
  their absence so all 1,875 captured emissions still replay;
* `v3_signals` normalises operator-facing nonsense rather than passing it to a handler;
* the migration publishes v3 with NO label. Promotion is the owner's step (AC-952).

Offline apart from the migration test, which needs the prompt registry on Postgres.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.head import output_exchange as ox
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot_parser_prompt import (
    SEMANTIC_PARSER_PROMPT,
    SEMANTIC_PARSER_PROMPT_SLIM,
    SEMANTIC_PARSER_PROMPT_V3,
)


class TestV3StopsTellingTheModelToCarry:
    """AC-949's cause: the prompt was one of the two writers of carry."""

    @pytest.mark.parametrize(
        "instruction",
        [
            "== BARE ENTITY CONTINUATION ==",
            "if the previous turn's domain still fits",
            "domain_hint and intent_hint = the\n    previous turn's",
            "the previous turn's\n    domain_hint and intent_hint carried",
            "A product carried from the previous turn stays as the scoping entity",
            "previous_conversation_state",
        ],
    )
    def test_the_carry_instruction_is_gone(self, instruction: str) -> None:
        assert instruction in SEMANTIC_PARSER_PROMPT_SLIM, (
            "this test is only meaningful while the SLIM prompt still carries the "
            "instruction v3 removes; if it no longer does, retire the case"
        )
        assert instruction not in SEMANTIC_PARSER_PROMPT_V3

    def test_the_extract_only_rule_replaces_it(self) -> None:
        assert "== EXTRACT ONLY ==" in SEMANTIC_PARSER_PROMPT_V3
        assert "NEVER re-emit a value the current message does not name" in SEMANTIC_PARSER_PROMPT_V3

    def test_current_message_is_documented_as_always_true(self) -> None:
        """AC-949 is asserted across the corpus replay; this is the instruction behind it."""
        assert (
            '"current_message": true - ALWAYS, because you only ever emit what this '
            "message names" in SEMANTIC_PARSER_PROMPT_V3
        )

    @pytest.mark.parametrize(
        "section",
        [
            "== ANSWERING AN OPEN QUESTION ==",
            "== ANAPHORA ==",
            "== TOPIC RESET ==",
        ],
    )
    def test_the_three_new_rules_are_declared(self, section: str) -> None:
        assert section in SEMANTIC_PARSER_PROMPT_V3

    @pytest.mark.parametrize("cue", ["那个", "别的", "yang lain", "itu", "换一个"])
    def test_the_multilingual_cues_the_plan_names_are_in_the_text(self, cue: str) -> None:
        """AC-941 / AC-943 are about Chinese and Malay phrasing, not only English."""
        assert cue in SEMANTIC_PARSER_PROMPT_V3

    @pytest.mark.parametrize(
        "kept",
        [
            "== DECISIVE DOMAIN TERMS ==",
            "== REQUESTED ATTRIBUTES ==",
            "== BROADEN AXIS ==",
            "== DATE FILTER (per-message, never carried over) ==",
            "== ORDER_STATUS FILTER ==",
            "== IS_ACTIVE FILTER ==",
            "== POSITIONAL REFERENCES AND REFERENCE TARGET ==",
            "== PERSON-NAME MENTION ==",
            "== ROUTING ==",
        ],
    )
    def test_every_other_section_survives(self, kept: str) -> None:
        """v3 removes INSTRUCTIONS, never keys: `output_exchange` derives ~69 keys from
        this emission and a section quietly dropped is a lane that stops working."""
        assert kept in SEMANTIC_PARSER_PROMPT_V3

    def test_it_uses_no_dash_characters(self) -> None:
        """The house rule, applied to prompt text like any other writing.

        The two characters are built from their code points rather than typed, because the
        repository's own pre-push guard rejects an added line that CONTAINS one - a literal
        here would fail the gate this test exists to enforce.
        """
        for dash in (chr(0x2014), chr(0x2013)):
            assert dash not in SEMANTIC_PARSER_PROMPT_V3


class TestTheWireCarriesTheThreeKeysUNDERV3ONLY:
    """The gate, and it is the difference between shipping this and breaking production.

    Strict structured output makes every declared property REQUIRED, so a schema shared
    between the versions forces the promoted v1 prompt to emit three keys no instruction
    in it mentions - and the model invents all three.
    """

    def test_the_v3_schema_declares_and_requires_them(self) -> None:
        schema = parser_mod.PARSE_OUTPUT_JSON_SCHEMA_V3
        for key in parser_mod.V3_EMISSION_KEYS:
            assert key in schema["properties"]
            assert key in schema["required"]

    def test_the_v1_schema_declares_none_of_them(self) -> None:
        schema = parser_mod.PARSE_OUTPUT_JSON_SCHEMA
        for key in parser_mod.V3_EMISSION_KEYS:
            assert key not in schema["properties"]
            assert key not in schema["required"]
        assert len(schema["required"]) == 26

    def test_the_two_schemas_differ_by_exactly_those_three(self) -> None:
        assert parser_mod.DECLARED_KEYS_V3 - parser_mod.DECLARED_KEYS == set(
            parser_mod.V3_EMISSION_KEYS
        )
        assert parser_mod.DECLARED_KEYS - parser_mod.DECLARED_KEYS_V3 == set()

    def test_the_answer_object_is_strict_too(self) -> None:
        answer = parser_mod.PARSE_OUTPUT_JSON_SCHEMA_V3["properties"]["answers_open_question"]
        assert answer["additionalProperties"] is False
        assert set(answer["required"]) == {"resolved", "picks", "yes_no", "free_text"}

    def test_the_version_is_read_off_the_resolved_prompt_text(self) -> None:
        """One string decides both what the model is asked for and what it is held to, so
        the two cannot drift."""
        assert parser_mod.emits_v3(SEMANTIC_PARSER_PROMPT) is False
        assert parser_mod.emits_v3(SEMANTIC_PARSER_PROMPT_SLIM) is False
        assert parser_mod.emits_v3(SEMANTIC_PARSER_PROMPT_V3) is True
        assert parser_mod.emits_v3(None) is False

    def test_schema_for_picks_the_pair_that_belong_together(self) -> None:
        schema, required = parser_mod.schema_for(v3=False)
        assert schema is parser_mod.PARSE_OUTPUT_JSON_SCHEMA
        assert required is parser_mod.DECLARED_KEYS
        schema, required = parser_mod.schema_for(v3=True)
        assert schema is parser_mod.PARSE_OUTPUT_JSON_SCHEMA_V3
        assert required is parser_mod.DECLARED_KEYS_V3

    def test_a_v1_emission_needs_no_exemption_to_post_process(self) -> None:
        """The 1,875 captured emissions predate v3 and always will. They are COMPLETE
        under the v1 contract now, rather than complete-with-three-exemptions."""
        assert ox._required_emission_keys() == parser_mod.DECLARED_KEYS - {"broaden_axis"}
        for key in parser_mod.V3_EMISSION_KEYS:
            assert key not in ox._required_emission_keys()

    def test_the_signals_are_inert_for_a_parse_made_under_v1(self) -> None:
        """A v1 model asked to fill a v3 schema invents all three; reading one would let a
        promoted v1 deployment clear a customer's scope."""
        invented = {
            "answers_open_question": {"resolved": True, "picks": [2], "yes_no": "yes"},
            "anaphora": True,
            "topic_reset": True,
        }

        assert ox.v3_signals(invented, emits_v3=False) == {
            "answers_open_question": ox.NO_OPEN_QUESTION_ANSWER,
            "anaphora": False,
            "topic_reset": False,
        }
        assert ox.v3_signals(invented, emits_v3=True)["topic_reset"] is True


class TestV3SignalsNormalises:
    def test_an_emission_without_the_keys_reads_as_nothing_happened(self) -> None:
        assert ox.v3_signals({}) == {
            "answers_open_question": ox.NO_OPEN_QUESTION_ANSWER,
            "anaphora": False,
            "topic_reset": False,
        }

    def test_a_truthy_string_is_not_a_boolean(self) -> None:
        """`"false"` is truthy in Python and `"true"` is a string, so neither may be read
        as the model's answer. The check is identity with `True`, not truthiness."""
        assert ox.v3_signals({"anaphora": "false"})["anaphora"] is False
        assert ox.v3_signals({"anaphora": "true"})["anaphora"] is False
        assert ox.v3_signals({"anaphora": True})["anaphora"] is True

    def test_picks_are_positive_one_based_integers_and_nothing_else(self) -> None:
        signals = ox.v3_signals(
            {"answers_open_question": {"resolved": True, "picks": [2, "3", 0, -1, "x", 1.5]}}
        )

        assert signals["answers_open_question"]["picks"] == [2, 3]

    def test_a_conversational_yes_is_not_a_yes_no_value(self) -> None:
        """The handler switches on exactly `"yes"` or `"no"`; anything else is None, so a
        model that answered in prose cannot accidentally confirm an escalation."""
        assert ox.v3_signals({"answers_open_question": {"yes_no": "Yes"}})[
            "answers_open_question"
        ]["yes_no"] == "yes"
        assert (
            ox.v3_signals({"answers_open_question": {"yes_no": "yes please"}})[
                "answers_open_question"
            ]["yes_no"]
            is None
        )

    def test_a_real_v3_emission_passes_through(self) -> None:
        signals = ox.v3_signals(
            {
                "answers_open_question": {
                    "resolved": True,
                    "picks": [1, 3],
                    "yes_no": None,
                    "free_text": None,
                },
                "anaphora": False,
                "topic_reset": True,
            }
        )

        assert signals["answers_open_question"]["picks"] == [1, 3]
        assert signals["topic_reset"] is True


def _load_migration():
    """The revision module by PATH: its filename starts with a digit, so it has no module
    path. Same idiom as `tests/test_chatbot_warehouse_cue_migration.py`."""
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "513_chatbot_parser_v3.py"
    )
    spec = importlib.util.spec_from_file_location("migration_under_test_489", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheMigrationPublishesWithoutPromoting:
    """AC-952: a new registry VERSION, no label. Promotion is one label move, by the owner."""

    def test_it_publishes_v3_once_and_moves_no_label(self) -> None:
        from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
        from app.services.ai_prompt_seed import seed_prompt_registry
        from tests._pg_fixture import blank_session

        module = _load_migration()
        with blank_session() as session:
            seed_prompt_registry(session.get_bind())
            labels_before = {
                (row.name, row.version_id) for row in session.query(AIPromptLabel).all()
            }

            version = module.publish(session)
            assert version is not None

            published = (
                session.query(AIPromptVersion)
                .filter(
                    AIPromptVersion.name == "chatbot_semantic_parser",
                    AIPromptVersion.version == version,
                )
                .one()
            )
            assert published.template == SEMANTIC_PARSER_PROMPT_V3
            assert (
                session.query(AIPromptLabel)
                .filter(AIPromptLabel.version_id == published.id)
                .count()
                == 0
            ), "v3 must ship UNLABELLED; promoting it is the owner's step (AC-952)"
            assert {
                (row.name, row.version_id) for row in session.query(AIPromptLabel).all()
            } == labels_before

            assert module.publish(session) is None, "publishing twice must be a no-op"
