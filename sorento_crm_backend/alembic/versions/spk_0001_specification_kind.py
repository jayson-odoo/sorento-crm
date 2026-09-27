"""The `specification` entity kind, and the parser prompt that teaches it, as a NEW
version with the production label unmoved (fix round 8 on PR #833).

Owner retest of round 7 (27 Sep 2026): "is it the parser is not bounded by what the
system has as a spec? like it doesn't know colour is colour one meh, why it become
document type one". The parser had no kind for a product property, so a descriptor it
could not place became an `attachment_type`. This adds:

  * the `chatbot_entity_kinds` row `specification` (resolver `product_spec_registry`, no
    did-you-mean, optional filter), the policy row the prompt's entity-kind lines and the
    turn engine read;
  * the next `chatbot_semantic_parser` version: `chatbot_rearch_s4`'s own body formula
    (the constant, now ending in `SPECIFICATION_ADDENDUM`, plus the policy blocks, which
    now close with one Specification line per registry key rendered from the
    specification registry). No label: promoting is one label move on the Prompts page,
    rolling back the reverse move, the same split as 475 and `sa2_r9_open_question`.

Idempotent, and safe on a fresh database: the kind row is inserted only when absent, and
the publish is skipped when a version already carries exactly this template.
`insert_kind(bind)` and `publish(bind)` are module-level so bootstrap can call them.

Revision ID: spk_0001_specification_kind
Revises: bcw_0001_brand_chatbot_weight
"""
from __future__ import annotations

import importlib.util
import logging
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "spk_0001_specification_kind"
down_revision = "bcw_0001_brand_chatbot_weight"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"
#: Stamped on the version this publishes, so `downgrade()` removes that row alone.
MARKER_KEY = "spk_0001_specification_kind"

#: Frozen here, not imported: a migration's data must not move when the seed module does.
KIND_ROW = {
    "kind": "specification",
    "label": "Specification",
    "resolver_source": "product_spec_registry",
    "did_you_mean": False,
    "default_narrowing": "optional_filter",
    "family_grouping": None,
}


def insert_kind(bind) -> bool:
    """Insert the `specification` kind row when absent. True when it inserted one."""
    present = bind.execute(
        sa.text("SELECT 1 FROM chatbot_entity_kinds WHERE kind = :kind"), {"kind": KIND_ROW["kind"]}
    ).first()
    if present is not None:
        return False
    next_order = bind.execute(sa.text("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM chatbot_entity_kinds")).scalar()
    bind.execute(
        sa.text(
            "INSERT INTO chatbot_entity_kinds "
            "(id, kind, label, resolver_source, did_you_mean, default_narrowing, family_grouping, "
            "base_property_words, sort_order) "
            "VALUES (:id, :kind, :label, :resolver_source, :did_you_mean, :default_narrowing, "
            ":family_grouping, CAST('{}' AS jsonb), :sort_order)"
        ),
        {**KIND_ROW, "id": str(uuid.uuid4()), "sort_order": int(next_order or 0)},
    )
    return True


def _load_s4():
    """`chatbot_rearch_s4`, for its body formula. Importing a revision file runs no DDL."""
    spec = importlib.util.spec_from_file_location(
        "_spk_0001_s4", Path(__file__).resolve().parent / "chatbot_rearch_s4.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def publish(bind) -> None:
    from app.models.ai_prompt import AIPromptVersion
    from app.services.ai_prompt_registry import PROMPT_KEYS
    from app.services.ai_prompt_seed import seed_prompt_registry

    seed_prompt_registry(bind)
    session = Session(bind=bind)
    try:
        template, blocks_hash = _load_s4()._body(session)
        # Only the NEWEST version counts as already published: an older version with the
        # same words (a migration ordered before this one may have published without the
        # specification kind since) must not stop the merged words becoming the next one.
        latest = (
            session.query(AIPromptVersion)
            .filter(AIPromptVersion.name == PROMPT_NAME)
            .order_by(AIPromptVersion.version.desc())
            .first()
        )
        if latest is not None and latest.template == template:
            logger.info("chatbot parser specification prompt already published as v%s", latest.version)
            return
        next_version = (int(latest.version) if latest is not None else 0) + 1
        session.add(
            AIPromptVersion(
                name=PROMPT_NAME,
                version=next_version,
                type="text",
                template=template,
                variables=list(PROMPT_KEYS[PROMPT_NAME].variables),
                config_json={"blocks_hash": blocks_hash, MARKER_KEY: True},
                commit_message=(
                    "PR #833 fix round 8: the specification entity kind, bounded by the "
                    "specification registry. Unlabelled, promote from the Prompts page."
                ),
            )
        )
        session.commit()
        logger.info(
            "published chatbot parser specification prompt as v%s (%s chars); production "
            "label left where it was",
            next_version,
            len(template),
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def upgrade() -> None:
    bind = op.get_bind()
    insert_kind(bind)
    publish(bind)


def downgrade() -> None:
    """Drop the unlabelled version this published and the kind row. A labelled version
    is never touched."""
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        labelled = {row.version_id for row in session.query(AIPromptLabel).filter(AIPromptLabel.name == PROMPT_NAME)}
        for row in session.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME):
            if row.id not in labelled and (row.config_json or {}).get(MARKER_KEY):
                session.delete(row)
        session.commit()
    finally:
        session.close()
    bind.execute(sa.text("DELETE FROM chatbot_entity_kinds WHERE kind = :kind"), {"kind": KIND_ROW["kind"]})
