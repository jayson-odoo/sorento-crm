"""Migration `482_chatbot_warehouse_cue` publishes the warehouse-arrival-cue FULL and SLIM
prompts as NEW, unlabelled `chatbot_semantic_parser` versions each.

The filename starts with a digit, so it is imported via `importlib` from its file path (the
`_run_migration` idiom in `tests/test_prompt_registry_is_seeded_by_migrations.py`), not by
module path. Postgres blank schema, per PRINCIPLES - `seed_prompt_registry` needs the
`ai_prompt_versions` / `ai_prompt_labels` tables to already exist, which `blank_session` gives
via `create_all`, but has no rows until the migration seeds them.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.models.ai_prompt import AIPromptVersion
from tests._pg_fixture import blank_session

MIGRATION_FILE = "482_chatbot_warehouse_cue.py"


def _load_migration():
    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / MIGRATION_FILE
    spec = importlib.util.spec_from_file_location("migration_under_test_482", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publish_is_idempotent_one_new_version_each_then_none() -> None:
    """Models prod: v1 already carries the pre-fix FULL text, seeded long before this
    migration existed (`seed_prompt_registry` only inserts a v1 when missing, so it never
    updates a live row). publish() must create new FULL and SLIM versions above it - the
    FULL one is the version prod's admin actually promotes - and a second call is a no-op
    for both."""
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
                template="STALE FULL PROMPT TEXT (pre warehouse-cue fix)",
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


def test_upgrade_seeds_a_fresh_database_and_publishes() -> None:
    """`upgrade()` must work standalone on a database that never ran an earlier chatbot
    migration - it seeds v1 + the production label before publishing. On a genuinely blank
    database `seed_prompt_registry` seeds v1 from the CURRENT (already-fixed) FULL fallback,
    so only the SLIM text needs a new version; the important thing `upgrade()` must not do is
    error, and it must leave both the FULL and SLIM fixed templates present in the registry."""
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
            "upgrade() must seed v1 and publish at least the new SLIM warehouse-cue version"
        )
        templates = {row.template for row in rows}
        assert module._full_text() in templates
        assert module._slim_text() in templates
