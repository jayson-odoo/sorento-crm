"""Phase 2 RED tests - REPORT-ENGINE slice 1b: the parser learns `sales_ranking`.

`documentation/plans/chatbot/PLAN-report-engine.md` section 11, "Parser", "Contracts" and the
migration `report_engine_0001_prompt` (the `acct_ledger_0002_vocab` pattern).

Ambiguities flagged to the captain:
* `order_status` is a permissive `string_or_null` in the strict schema today (its values live in
  the prompt, not an enum), so "the order_status enum gains sales_ranking" cannot be asserted
  literally. Pinned: IF the schema ever constrains it with an enum it must hold `sales_ranking`,
  and the prompt names `sales_ranking` (below).
* section 11 says the addendum is appended AFTER `MEMORY_ADDENDUM`, while the ACCOUNT-LEDGER
  tests pin MEMORY as the prompt's tail. Only "REPORT_ASK_ADDENDUM is in the prompt" is pinned.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.chatbot.head.parser import PARSE_OUTPUT_JSON_SCHEMA
from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT

from tests._pg_fixture import blank_session

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
PROMPT_NAME = "chatbot_semantic_parser"


def test_order_status_schema_does_not_exclude_sales_ranking() -> None:
    prop = PARSE_OUTPUT_JSON_SCHEMA["properties"]["order_status"]
    if "enum" in prop:
        assert "sales_ranking" in prop["enum"], prop


def test_group_by_enum_gains_the_new_dimensions() -> None:
    enum = PARSE_OUTPUT_JSON_SCHEMA["properties"]["group_by"]["enum"]
    for word in ("sales_agent", "brand", "category", "channel"):
        assert word in enum, (word, enum)


def test_the_addendum_is_in_the_prompt() -> None:
    from app.services import chatbot_parser_prompt

    assert hasattr(chatbot_parser_prompt, "REPORT_ASK_ADDENDUM"), "REPORT_ASK_ADDENDUM is not defined"
    addendum = chatbot_parser_prompt.REPORT_ASK_ADDENDUM
    assert addendum in SEMANTIC_PARSER_PROMPT
    assert "sales_ranking" in addendum
    assert "top 3 salesman for Sorento brand last month" in addendum
    assert "sales_agent" in addendum


def test_the_addendum_keeps_top_selling_for_products_and_categories() -> None:
    from app.services import chatbot_parser_prompt

    addendum = getattr(chatbot_parser_prompt, "REPORT_ASK_ADDENDUM", "")
    assert "top_selling" in addendum, "ranking products stays top_selling"


def test_sales_figure_statuses_gain_sales_ranking() -> None:
    from app.services.chatbot import contracts

    assert "sales_ranking" in contracts.SALES_FIGURE_STATUSES, contracts.SALES_FIGURE_STATUSES


# ------------------------------------------------------------------ migration


def _load(filename: str, alias: str):
    path = VERSIONS / filename
    assert path.exists(), f"{filename} does not exist"
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_id_and_publish_callable() -> None:
    module = _load("report_engine_0001_prompt.py", "mig_report_engine_0001")
    assert module.revision == "report_engine_0001_prompt"
    assert len(module.revision) <= 32
    assert callable(module.publish)


def _production_label(session):
    return (
        session.query(AIPromptLabel)
        .filter(AIPromptLabel.name == PROMPT_NAME, AIPromptLabel.label == "production")
        .first()
    )


def test_migration_publishes_a_new_version_label_unmoved_and_idempotent() -> None:
    module = _load("report_engine_0001_prompt.py", "mig_report_engine_0001_publish")
    with blank_session() as session:
        from app.services.ai_prompt_registry import PROMPT_KEYS
        from app.services.ai_prompt_seed import seed_prompt_registry

        session.add(
            AIPromptVersion(
                name=PROMPT_NAME, version=1, type="text", template="STALE PROMPT TEXT (before sales ranking)",
                variables=list(PROMPT_KEYS[PROMPT_NAME].variables),
            )
        )
        session.commit()
        seed_prompt_registry(session.get_bind())
        before = _production_label(session)
        assert before is not None
        version_before = before.version_id

        first = module.publish(session)
        assert isinstance(first, int) and first >= 2, first
        assert module.publish(session) is None

        published = (
            session.query(AIPromptVersion)
            .filter(AIPromptVersion.name == PROMPT_NAME, AIPromptVersion.version == first)
            .one()
        )
        assert "sales_ranking" in published.template
        session.expire_all()
        after = _production_label(session)
        assert after is not None and after.version_id == version_before
