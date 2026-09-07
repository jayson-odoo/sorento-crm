"""Publish the amended slim parser prompt as a NEW version, label unmoved (R-a / R-c).

Owner console pass 4, 7 Sep 2026. The slim body's ROUTING section now says that
`routing.suggested_team` carries the customer's OWN team word verbatim when that word
names several catalogue teams or none ("marketing", "sales"), and is null ONLY when the
customer named no team at all.

That distinction is the whole point: at the escalation lane, "escalate to marketing" and
"I want to talk to a human" both arrived with a null team under the previous contract, so
the one premise that could tell them apart did not exist and the lane's H64 inheritance
guard fired on both (production turns 1f0428cb / 9089ef88, n8n execs 15501799 / 15502378 -
a request naming no team was handed the eight-team menu). D11 forbids the lane reading the
two messages to tell them apart, so the discriminator is produced by the parser and this
migration is how it reaches the registry.

Same shape as `475_chatbot_parser_prompt_slim`, deliberately, and for the same reason: an
immutable version plus a movable label. Version 1 stays the LIVE 46,906-character body and
keeps the `production` label, so deploying this changes NOTHING about how a turn is parsed;
the amended slim text lands as the next version with NO label, and promoting is one label
move in the admin UI.

**So this migration alone does not change production behaviour**, and that is stated here
rather than left to be discovered: until the owner moves the label, production keeps
parsing "escalate to marketing" to a null team, and the lane assigns the routing table's
default for it. That is the pre-#706 behaviour, not the #706 regression this lane fixes -
the regression is the eight-team menu, and deleting the inheritance premise removes it
under either prompt.

Idempotent, and safe on a fresh database: `seed_prompt_registry` runs first, and the
publish is skipped when a version already carries the same template (which is what happens
on a fresh install, where 475 already published this exact amended text).

Revision ID: 480_chatbot_team_word
Revises: 486_scm_claim_qty_planner
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS
from app.services.ai_prompt_seed import seed_prompt_registry

revision = "480_chatbot_team_word"
down_revision = "486_scm_claim_qty_planner"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"


def _slim_text() -> str:
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT_SLIM

    return SEMANTIC_PARSER_PROMPT_SLIM


def upgrade() -> None:
    bind = op.get_bind()
    seed_prompt_registry(bind)

    template = _slim_text()
    spec = PROMPT_KEYS[PROMPT_NAME]
    session = Session(bind=bind)
    try:
        existing = (
            session.query(AIPromptVersion)
            .filter(
                AIPromptVersion.name == PROMPT_NAME,
                AIPromptVersion.template == template,
            )
            .first()
        )
        if existing is not None:
            logger.info(
                "chatbot parser team-word prompt already published as v%s; nothing to do",
                existing.version,
            )
            return
        versions = (
            session.query(AIPromptVersion.version)
            .filter(AIPromptVersion.name == PROMPT_NAME)
            .all()
        )
        next_version = max((int(v[0]) for v in versions), default=0) + 1
        session.add(
            AIPromptVersion(
                name=PROMPT_NAME,
                version=next_version,
                type="text",
                template=template,
                variables=list(spec.variables),
            )
        )
        session.commit()
        logger.info(
            "published the amended slim chatbot parser prompt as v%s (%s chars); the "
            "production label is left where it is, promote by moving it",
            next_version,
            len(template),
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Drop the unlabelled amended version. A labelled one is never touched."""
    bind = op.get_bind()
    template = _slim_text()
    session = Session(bind=bind)
    try:
        (
            session.query(AIPromptVersion)
            .filter(
                AIPromptVersion.name == PROMPT_NAME,
                AIPromptVersion.template == template,
            )
            .delete(synchronize_session=False)
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
