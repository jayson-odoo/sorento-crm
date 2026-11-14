"""Publish the chatbot parser prompt with the issue rule as a NEW version, label unmoved
(WA-COMPLAINT-INTAKE, documentation/plans/chatbot/PROMPT-wa-issue-ideate.md).

A user reporting a problem with the CRM system or the assistant itself is ideate (an issue to log), not
request_for_help or the domain of the screen it is about. Production runs the stored
`chatbot_semantic_parser` version, so the rule ships as the three anchored edits of
`app/services/chatbot/head/issue_rule.apply_issue_rule`, applied to the template of the version holding the
`production` label (its rendered policy blocks stay as they are), landing as the next version with NO label
move. Promoting is one label move on the Prompts page; rolling back is the reverse move.

Idempotent, and safe on a fresh database: `seed_prompt_registry` runs first, a version already carrying the
exact template is not published twice, and a production text that already carries the rule or lacks an
anchor is logged and publishes nothing.

Revision ID: wa_0002_parser_issue_ideate
Revises: wa_0001_idea_submit_perm
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion

revision = "wa_0002_parser_issue_ideate"
down_revision = "wa_0001_idea_submit_perm"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"

#: Stamped on the version this publishes, so `downgrade()` removes that row alone.
MARKER_KEY = "wa_0002_parser_issue_ideate"


def publish(session: Session) -> int | None:
    """Publish the production text plus the issue rule as the next `chatbot_semantic_parser` version,
    unlabelled. Returns the new version number, or None when nothing was published."""
    from app.services.chatbot.head.issue_rule import apply_issue_rule

    base = (
        session.query(AIPromptVersion)
        .join(AIPromptLabel, AIPromptLabel.version_id == AIPromptVersion.id)
        .filter(AIPromptLabel.name == PROMPT_NAME, AIPromptLabel.label == "production")
        .first()
    )
    if base is None:
        logger.warning("chatbot parser issue rule: no production version of %s; nothing published", PROMPT_NAME)
        return None
    try:
        template = apply_issue_rule(base.template or "")
    except ValueError as exc:
        logger.warning("chatbot parser issue rule not published: production v%s %s", base.version, exc)
        return None
    if template is None:
        logger.info("chatbot parser issue rule: production v%s already carries it; nothing to do", base.version)
        return None
    existing = (
        session.query(AIPromptVersion)
        .filter(AIPromptVersion.name == PROMPT_NAME, AIPromptVersion.template == template)
        .first()
    )
    if existing is not None:
        logger.info("chatbot parser issue rule already published as v%s; nothing to do", existing.version)
        return None
    versions = session.query(AIPromptVersion.version).filter(AIPromptVersion.name == PROMPT_NAME).all()
    next_version = max((int(v[0]) for v in versions), default=0) + 1
    session.add(
        AIPromptVersion(
            name=PROMPT_NAME,
            version=next_version,
            type=base.type or "text",
            template=template,
            variables=list(base.variables or []),
            config_json={**(base.config_json or {}), MARKER_KEY: True},
            commit_message=(
                "WA-COMPLAINT-INTAKE: a report of a CRM or assistant problem is ideate (issue). "
                "Unlabelled, promote from the Prompts page."
            ),
        )
    )
    session.commit()
    logger.info(
        "published chatbot parser issue rule prompt as v%s (from production v%s); production label left on "
        "the previous version, promote by moving it",
        next_version,
        base.version,
    )
    return next_version


def upgrade() -> None:
    from app.services.ai_prompt_seed import seed_prompt_registry

    bind = op.get_bind()
    # v1 from the fallback plus the production label, if absent.
    seed_prompt_registry(bind)

    session = Session(bind=bind)
    try:
        publish(session)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Drop the unlabelled version this published (by its marker), unless the owner has since moved a label
    onto it (a label row cascades with its version, and a downgrade must never delete a label)."""
    session = Session(bind=op.get_bind())
    try:
        labelled = {
            row.version_id
            for row in session.query(AIPromptLabel)
            .join(AIPromptVersion, AIPromptVersion.id == AIPromptLabel.version_id)
            .filter(AIPromptVersion.name == PROMPT_NAME)
        }
        for row in session.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME):
            if row.id not in labelled and (row.config_json or {}).get(MARKER_KEY):
                session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
