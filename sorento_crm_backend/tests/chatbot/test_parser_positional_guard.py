"""A bare positional reply must never re-domain a turn (migration 493, owner ruling
8 Sep 2026, production turn `3114fc64-a2ef-4653-9618-f88aec724b78`).

The parser's RAW output for the bare reply "2", shown a `master_products` previous turn
with 15 records, was `message_type` business_query / `intent_hint` check_order /
`domain_hint` order with `entities` []. The `GROWTH_R1_ADDENDUM` text that biases a product
entity toward `check_order` ("A DELIVERY WORD PLUS A NAME IS AN ORDER ASK") is what caused
it: a bare number, seen next to nothing but the previous turn's product list, was enough to
bias the parse. This file pins the guard sentence in place and that migration 493 publishes
it, the same shape as `tests/test_chatbot_warehouse_cue_migration.py` pins migration 487.

The sentence is scoped to a reply INTO the previous numbered list (review, 8 Sep 2026): the
carry it leans on (`output_exchange.py`) only fires when `reference_positions` is non-empty,
so an unconditional guard would null both hints on a shape like "that one" - which is not a
POSITIONAL REFERENCES shape at all - and hand the customer a clarifier with nothing to carry.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.chatbot_parser_prompt import (
    GROWTH_R1_ADDENDUM,
    SEMANTIC_PARSER_PROMPT,
    SEMANTIC_PARSER_PROMPT_SLIM,
)
from tests._pg_fixture import blank_session

GUARD_SENTENCE = (
    'A bare positional reply into the previous numbered list - a number ("2"), "the 2nd '
    'one", "1 and 3", "the last one" - names nothing of its own: it NEVER sets domain_hint '
    "or intent_hint. Leave both null, put the position in reference_positions as "
    "POSITIONAL REFERENCES says, and let the carry fill the domain from the previous turn, "
    "whatever that turn's domain was."
)

MIGRATION_FILE = "493_chatbot_parser_positional_guard.py"


def _load_migration():
    path = Path(__file__).resolve().parent.parent.parent / "alembic" / "versions" / MIGRATION_FILE
    spec = importlib.util.spec_from_file_location("migration_under_test_493", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestBothPublishedBodiesCarryTheGuard:
    def test_the_guard_sentence_is_in_both_bodies(self) -> None:
        for body in (SEMANTIC_PARSER_PROMPT, SEMANTIC_PARSER_PROMPT_SLIM):
            assert body.count(GUARD_SENTENCE) == 1

    def test_the_addendum_carries_the_guard_and_is_the_tail_of_both_bodies(self) -> None:
        """The guard lives INSIDE `GROWTH_R1_ADDENDUM`, so the addendum has to actually be
        the tail of both bodies (not woven in separately for FULL vs SLIM) or the guard
        could silently reach only one of them - exactly the failure mode this file exists
        to catch."""
        assert GUARD_SENTENCE in GROWTH_R1_ADDENDUM
        assert SEMANTIC_PARSER_PROMPT.endswith(GROWTH_R1_ADDENDUM)
        assert SEMANTIC_PARSER_PROMPT_SLIM.endswith(GROWTH_R1_ADDENDUM)


def test_publish_is_idempotent_one_new_version_each_then_none() -> None:
    """Models prod: v1 already carries the pre-guard FULL text, seeded long before this
    migration existed. `publish()` must create new FULL and SLIM versions above it, and a
    second call is a no-op for both, and the `production` label must not move."""
    module = _load_migration()
    with blank_session() as session:
        from app.services.ai_prompt_registry import PROMPT_KEYS
        from app.services.ai_prompt_seed import seed_prompt_registry

        spec = PROMPT_KEYS["chatbot_semantic_parser"]
        session.add(
            AIPromptVersion(
                name="chatbot_semantic_parser",
                version=1,
                type="text",
                template="STALE FULL PROMPT TEXT (pre positional-guard fix)",
                variables=list(spec.variables),
            )
        )
        session.commit()
        # v1 exists already, so this only adds the production label pointing at it.
        seed_prompt_registry(session.get_bind())

        first = module.publish(session)
        assert isinstance(first, dict) and set(first) == {"full", "slim"}
        assert isinstance(first["full"], int) and first["full"] >= 2, (
            "first publish() must create a new FULL version above the stale v1"
        )
        assert isinstance(first["slim"], int) and first["slim"] >= 2, (
            "first publish() must create a new SLIM version above the stale v1"
        )
        assert first["full"] != first["slim"], "FULL and SLIM texts differ, so must be distinct versions"

        second = module.publish(session)
        assert second == {"full": None, "slim": None}, (
            "second publish() must be a no-op for both: same templates already exist"
        )

        rows = (
            session.query(AIPromptVersion)
            .filter(AIPromptVersion.name == "chatbot_semantic_parser")
            .all()
        )
        versions = {row.version for row in rows}
        assert first["full"] in versions
        assert first["slim"] in versions
        assert len([v for v in versions if v == first["full"]]) == 1
        assert len([v for v in versions if v == first["slim"]]) == 1

        production_label = (
            session.query(AIPromptLabel)
            .filter(
                AIPromptLabel.name == "chatbot_semantic_parser",
                AIPromptLabel.label == "production",
            )
            .first()
        )
        v1 = (
            session.query(AIPromptVersion)
            .filter(
                AIPromptVersion.name == "chatbot_semantic_parser",
                AIPromptVersion.version == 1,
            )
            .first()
        )
        assert production_label is not None
        assert production_label.version_id == v1.id, (
            "the production label must stay on v1 after publish() - promoting is a "
            "deliberate, separate action in the admin UI, never a migration side effect"
        )


def test_downgrade_preserves_a_promoted_label_and_only_deletes_the_unlabelled_version() -> None:
    """`AIPromptLabel.version_id` is `ondelete=CASCADE`. If the owner promotes `production`
    onto the FULL version this migration published, a later `alembic downgrade` must not
    cascade-delete that label along with the version row - it must exclude any labelled
    version from the delete and leave the label pointing at it. The unlabelled SLIM version
    this migration also published carries no such protection and must still be dropped.
    """
    module = _load_migration()
    with blank_session() as session:
        from unittest.mock import patch

        from app.services.ai_prompt_registry import PROMPT_KEYS
        from app.services.ai_prompt_seed import seed_prompt_registry

        spec = PROMPT_KEYS["chatbot_semantic_parser"]
        session.add(
            AIPromptVersion(
                name="chatbot_semantic_parser",
                version=1,
                type="text",
                template="STALE FULL PROMPT TEXT (pre positional-guard fix)",
                variables=list(spec.variables),
            )
        )
        session.commit()
        seed_prompt_registry(session.get_bind())  # v1 already exists; only adds the label

        with patch("alembic.op.get_bind", return_value=session.get_bind()):
            module.upgrade()

        full_version = (
            session.query(AIPromptVersion)
            .filter(
                AIPromptVersion.name == "chatbot_semantic_parser",
                AIPromptVersion.template == module._full_text(),
            )
            .one()
        )
        slim_version_id = (
            session.query(AIPromptVersion.id)
            .filter(
                AIPromptVersion.name == "chatbot_semantic_parser",
                AIPromptVersion.template == module._slim_text(),
            )
            .scalar()
        )

        # The owner promotes `production` onto the new FULL version in the admin UI.
        production_label = (
            session.query(AIPromptLabel)
            .filter(
                AIPromptLabel.name == "chatbot_semantic_parser",
                AIPromptLabel.label == "production",
            )
            .one()
        )
        production_label.version_id = full_version.id
        session.commit()

        with patch("alembic.op.get_bind", return_value=session.get_bind()):
            module.downgrade()

        production_label = (
            session.query(AIPromptLabel)
            .filter(
                AIPromptLabel.name == "chatbot_semantic_parser",
                AIPromptLabel.label == "production",
            )
            .first()
        )
        assert production_label is not None, (
            "downgrade() must never cascade-delete a label - the FK is ondelete=CASCADE, "
            "so deleting the labelled version silently takes the label row with it"
        )
        assert production_label.version_id == full_version.id, (
            "the label must still point at the FULL version the owner promoted"
        )

        remaining_ids = {
            row[0]
            for row in session.query(AIPromptVersion.id)
            .filter(AIPromptVersion.name == "chatbot_semantic_parser")
            .all()
        }
        assert full_version.id in remaining_ids, "the labelled FULL version must survive downgrade()"
        assert slim_version_id not in remaining_ids, (
            "the unlabelled SLIM version carries no label and must still be deleted"
        )


def test_upgrade_seeds_a_fresh_database_and_publishes() -> None:
    """`upgrade()` must work standalone on a database that never ran an earlier chatbot
    migration - it seeds v1 + the production label before publishing. On a genuinely blank
    database `seed_prompt_registry` seeds v1 from the CURRENT (already-guarded) FULL
    fallback, so only the SLIM text needs a new version; the important thing `upgrade()`
    must not do is error, and it must leave both the FULL and SLIM guarded templates present
    in the registry."""
    module = _load_migration()
    with blank_session() as session:
        from unittest.mock import patch

        with patch("alembic.op.get_bind", return_value=session.get_bind()):
            module.upgrade()

        rows = (
            session.query(AIPromptVersion)
            .filter(AIPromptVersion.name == "chatbot_semantic_parser")
            .all()
        )
        assert len(rows) >= 2, (
            "upgrade() must seed v1 and publish at least the new SLIM positional-guard version"
        )
        templates = {row.template for row in rows}
        assert module._full_text() in templates
        assert module._slim_text() in templates
