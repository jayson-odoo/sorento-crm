"""C5 (PLAN-ideation-capture-02oct section 4a-bis): an intent-only message such as
"want to submit idea" has NO problem. The rule ships as the fallback text of
``ideate_extractor`` and one migration publishes it to the production registry row.
"""
from __future__ import annotations

import ast
import pathlib
import re

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services import ai_prompt_registry
from app.services.ai_prompt_seed import bump_prompt_to_fallback
from tests._pg_fixture import blank_session

VERSIONS_DIR = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
BUMP = 'bump_prompt_to_fallback(op.get_bind(), "ideate_extractor")'
SEED = "seed_prompt_registry(op.get_bind())"


def _fallback() -> str:
    return ai_prompt_registry.PROMPT_KEYS["ideate_extractor"].fallback()


def test_fallback_has_intent_only_rule():
    text = _fallback()
    assert "want to submit idea" in text
    assert "did not state" in text


def _bump_migrations() -> list[tuple[pathlib.Path, str]]:
    """Version files that bump ideate_extractor AND are the C5 one: the others
    (272, confirm, reply_fmt) predate it, so pick files that also seed and are
    newest by chaining onto merge_03oct_join5."""
    out = []
    for p in VERSIONS_DIR.glob("*.py"):
        src = p.read_text(encoding="utf-8")
        if BUMP in src and "merge_03oct_join5" in src and "down_revision" in src:
            out.append((p, src))
    return out


def _assign(src: str, name: str):
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    return None


def test_migration_bumps_extractor_and_seeds_registry():
    found = [(p, s) for p, s in _bump_migrations() if _assign(s, "down_revision") == "merge_03oct_join5"]
    assert len(found) == 1, "expected exactly one migration with down_revision merge_03oct_join5 that bumps ideate_extractor"
    path, src = found[0]
    assert SEED in src
    assert BUMP in src
    # both calls live in upgrade(), not a comment
    upgrade = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "upgrade")
    body = ast.get_source_segment(src, upgrade)
    assert BUMP in body and SEED in body
    revision = _assign(src, "revision")
    assert isinstance(revision, str) and 0 < len(revision) <= 32


def test_alembic_head_is_single_and_is_the_new_migration():
    revs: dict[str, object] = {}
    for p in VERSIONS_DIR.glob("*.py"):
        src = p.read_text(encoding="utf-8")
        rev = _assign(src, "revision")
        if rev is not None:
            revs[rev] = _assign(src, "down_revision")
    parents: set[str] = set()
    for down in revs.values():
        if isinstance(down, (tuple, list)):
            parents.update(down)
        elif down:
            parents.add(down)
    heads = [r for r in revs if r not in parents]
    assert len(heads) == 1, f"alembic heads: {heads}"
    assert heads[0] != "merge_03oct_join5", "a new migration must sit on top of merge_03oct_join5"
    assert revs[heads[0]] == "merge_03oct_join5"


def test_bump_publishes_new_rule_to_production_version():
    with blank_session() as db:
        bump_prompt_to_fallback(db.connection(), "ideate_extractor")
        label = (
            db.query(AIPromptLabel)
            .filter(AIPromptLabel.name == "ideate_extractor", AIPromptLabel.label == "production")
            .first()
        )
        assert label is not None
        row = db.query(AIPromptVersion).filter(AIPromptVersion.id == label.version_id).one()
        assert row.template == _fallback()
        assert "want to submit idea" in row.template
        assert "did not state" in row.template
