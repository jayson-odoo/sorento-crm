"""Publish the span-pass parser version from a production text that already carries the diet (ENTITY-EXTRACT-MATCH
S2 fix). eem_0001 built the span version as production text -> diet edits -> swap, so on a production text that
already has the diet applied the edits found no anchor and nothing was published.

This takes the production-labelled text as it is: when it carries the `== LOOKUP LISTS ==` line (and no
`== LOOKUP SPANS ==` line) it publishes that text with the line swapped for `== LOOKUP SPANS ==` as the next
UNLABELLED `chatbot_semantic_parser` version. The label never moves. Idempotent: the same template, or a version
with this commit message, publishes nothing. Downgrade removes only the unlabelled version it made.

Revision ID: eem_0002_span_version_on_diet
Revises: eem_0001_span_pass
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "eem_0002_span_version_on_diet"
down_revision = "eem_0001_span_pass"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PARSER = "chatbot_semantic_parser"
MESSAGE = (
    "ENTITY-EXTRACT-MATCH S2 fix: the production parser text with the lookup lists swapped for the span pass "
    "(== LOOKUP SPANS ==). Unlabelled; pick it in the Chatbot Console to try it."
)


def publish_on_production(session: Session) -> int | None:
    """The production-labelled text with its lists line swapped for the span line, as a new UNLABELLED version;
    its number, or None when there is no production label, the text has no lists line (or already has the span
    line), or this text is already published."""
    from app.models.ai_prompt import AIPromptVersion
    from app.services import chatbot_prompt_diet_edits as prompt_diet_edits
    from app.services.chatbot_lookup_edits import MARKER, SPAN_MARKER

    row = session.execute(
        sa.text(
            "SELECT v.template, v.variables FROM ai_prompt_versions v JOIN ai_prompt_labels l "
            "ON l.version_id = v.id WHERE l.name = :n AND l.label = 'production'"
        ),
        {"n": PARSER},
    ).first()
    if row is None:
        logger.warning("eem_0002: no production-labelled parser version, nothing published")
        return None
    lines = (row[0] or "").split("\n")
    stripped = [ln.strip() for ln in lines]
    if SPAN_MARKER in stripped:
        logger.warning("eem_0002: the production parser text already carries the span line, nothing published")
        return None
    if MARKER not in stripped:
        logger.warning("eem_0002: the production parser text has no lookup lists line, nothing published")
        return None
    if prompt_diet_edits.build(row[0]) is not None:
        logger.warning("eem_0002: the production parser text is pre-diet, eem_0001's case, nothing published")
        return None
    template = "\n".join(SPAN_MARKER if ln.strip() == MARKER else ln for ln in lines)
    if session.query(AIPromptVersion.version).filter(
        AIPromptVersion.name == PARSER,
        (AIPromptVersion.template == template) | (AIPromptVersion.commit_message == MESSAGE),
    ).first():
        logger.info("eem_0002: this text is already published, nothing published")
        return None
    versions = session.query(AIPromptVersion.version).filter(AIPromptVersion.name == PARSER).all()
    next_version = max((int(v[0]) for v in versions), default=0) + 1
    session.add(
        AIPromptVersion(
            name=PARSER,
            version=next_version,
            type="text",
            template=template,
            variables=list(row[1] or ["current_date"]),
            config_json={"wording_edit": True},
            commit_message=MESSAGE,
        )
    )
    session.flush()
    logger.info("eem_0002: published chatbot_semantic_parser v%s, label unmoved", next_version)
    return next_version


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        publish_on_production(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "DELETE FROM ai_prompt_versions WHERE name = :n AND commit_message = :m "
            "AND id NOT IN (SELECT version_id FROM ai_prompt_labels)"
        ),
        {"n": PARSER, "m": MESSAGE},
    )
