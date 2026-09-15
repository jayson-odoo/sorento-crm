"""Publish parser v3 (asks) and clarifier v2 as NEW versions, labels unmoved (L1-S2).

AC-1021 / AC-1024 / D10. Two prompts, one migration, because they are one change: the parser
stops emitting `domain_hint` + a flat `entities` list and emits `asks` instead, and the
clarifier stops being handed the session bag and is handed the alive focus. Publishing one
without the other would leave a version pair that was never meant to answer together.

**Published, NOT promoted**, exactly as 475, 480, 487 and 513 published theirs: each text
lands as the next version of its key with NO label, so this migration reaching production
changes no customer's turn. Promotion is one label move in the admin UI and it is the
OWNER's step, after the shadow window (AC-1027 to AC-1031) and the console pass. Rolling
back is the reverse label move.

513 published an EARLIER v3 body - the one derived from the 7 Sep prompt, before the merge
with main and before `asks`. It is deliberately left where it is rather than rewritten: a
published version is immutable history, an owner may have pinned it in the console, and
this migration simply publishes the next one.

Idempotent, and safe on a fresh database: `seed_prompt_registry` runs first so v1 and the
`production` label exist even on an install that never saw an earlier chatbot migration, and
each publish is skipped when a version already carries that exact template.

Revision ID: 516_chatbot_parser_v3_asks
Revises: 515_chatbot_parser_shadow
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS
from app.services.ai_prompt_seed import seed_prompt_registry

revision = "516_chatbot_parser_v3_asks"
down_revision = "515_chatbot_parser_shadow"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PARSER_NAME = "chatbot_semantic_parser"
CLARIFIER_NAME = "chatbot_clarifier"


def _texts() -> dict[str, str]:
    """The two templates, imported at call time so the constants stay the one source."""
    from app.services.chatbot_clarifier_prompt import CLARIFIER_PROMPT_V2
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT_V3

    return {PARSER_NAME: SEMANTIC_PARSER_PROMPT_V3, CLARIFIER_NAME: CLARIFIER_PROMPT_V2}


def publish(session: Session, name: str, template: str, *, what: str) -> int | None:
    """Publish `template` as the next version of `name`, unless one already carries it.

    Returns the new version number, or None when it was already published. The same shape
    513 uses, lifted rather than imported: a migration that imported another migration's
    helper would break the moment that file was squashed.
    """
    spec = PROMPT_KEYS[name]
    existing = (
        session.query(AIPromptVersion)
        .filter(AIPromptVersion.name == name, AIPromptVersion.template == template)
        .first()
    )
    if existing is not None:
        logger.info("%s already published as v%s; nothing to do", what, existing.version)
        return None
    versions = session.query(AIPromptVersion.version).filter(AIPromptVersion.name == name).all()
    next_version = max((int(v[0]) for v in versions), default=0) + 1
    session.add(
        AIPromptVersion(
            name=name,
            version=next_version,
            type="text",
            template=template,
            variables=list(spec.variables),
        )
    )
    session.commit()
    logger.info(
        "published %s as v%s (%s chars); every label left where it was, promote by moving one",
        what,
        next_version,
        len(template),
    )
    return next_version


def upgrade() -> None:
    bind = op.get_bind()
    seed_prompt_registry(bind)

    session = Session(bind=bind)
    try:
        texts = _texts()
        publish(session, PARSER_NAME, texts[PARSER_NAME], what="chatbot parser v3 (asks)")
        publish(session, CLARIFIER_NAME, texts[CLARIFIER_NAME], what="chatbot clarifier v2 (focus hints)")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Drop the two unlabelled versions this migration published.

    A version published here can stop being unlabelled: the owner may have since moved a
    label onto it. `AIPromptLabel.version_id` is `ondelete="CASCADE"`
    (`app/models/ai_prompt.py`), so deleting a labelled version would silently delete the
    label row with it, and a downgrade must never do that. Any version carrying a label is
    left alone, which is the rule 487 and 513 apply.
    """
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        texts = _texts()
        for name, template in texts.items():
            labelled = {
                row[0]
                for row in (
                    session.query(AIPromptLabel.version_id)
                    .join(AIPromptVersion, AIPromptVersion.id == AIPromptLabel.version_id)
                    .filter(AIPromptVersion.name == name)
                    .all()
                )
            }
            query = session.query(AIPromptVersion).filter(
                AIPromptVersion.name == name,
                AIPromptVersion.template == template,
            )
            if labelled:
                query = query.filter(AIPromptVersion.id.notin_(labelled))
            query.delete(synchronize_session=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
