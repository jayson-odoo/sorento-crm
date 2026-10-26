"""Seed the span prompt and publish the span-pass parser version, dark (ENTITY-EXTRACT-MATCH S2,
documentation/plans/chatbot/PLAN-entity-extract-match-26oct.md "S2 design").

Two things, neither of which changes a live turn:
- `chatbot_span_extractor` v1 (the phase-1 B2 wording) with a `production` label. Nothing reads it unless a
  parser version carries the `== LOOKUP SPANS ==` line.
- one UNLABELLED `chatbot_semantic_parser` version: the PROMPT-RULES-DIET text (`chatbot_prompt_diet_edits.build`
  on the production text) with its `== LOOKUP LISTS ==` line swapped for `== LOOKUP SPANS ==`. The label never
  moves; the owner picks the version in the Chatbot Console to try the span pass.

Idempotent: a version already carrying this exact template (or this commit message, as a hand-applied copy of the
SQL does) publishes nothing, and an existing span prompt is kept.
Downgrade removes only the rows this migration made.

Revision ID: eem_0001_span_pass
Revises: diet_0001_parser_prompt_diet
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "eem_0001_span_pass"
down_revision = "diet_0001_parser_prompt_diet"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PARSER = "chatbot_semantic_parser"
SPAN_PROMPT = "chatbot_span_extractor"
PARSER_MESSAGE = (
    "ENTITY-EXTRACT-MATCH S2: the PROMPT-RULES-DIET parser text with the lookup lists swapped for the span pass "
    "(== LOOKUP SPANS ==). Unlabelled; pick it in the Chatbot Console to try it."
)
SPAN_MESSAGE = "ENTITY-EXTRACT-MATCH S2: the span extractor prompt (phase-1 B2 wording)."


def publish_on_production(session: Session) -> int | None:
    """The production-labelled text, edited, as a new UNLABELLED version with the span marker; its number, or None
    when there is no production label, the edits do not apply, or this text is already published."""
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
        logger.warning("eem_0001: no production-labelled parser version, nothing published")
        return None
    built = prompt_diet_edits.build(row[0])
    if built is None:
        logger.warning("eem_0001: the production parser text does not take the edits, nothing published")
        return None
    template = "\n".join(SPAN_MARKER if ln.strip() == MARKER else ln for ln in built.split("\n"))
    if session.query(AIPromptVersion.version).filter(
        AIPromptVersion.name == PARSER,
        (AIPromptVersion.template == template) | (AIPromptVersion.commit_message == PARSER_MESSAGE),
    ).first():
        logger.info("eem_0001: this text is already published")
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
            commit_message=PARSER_MESSAGE,
        )
    )
    session.flush()
    logger.info("eem_0001: published chatbot_semantic_parser v%s, label unmoved", next_version)
    return next_version


def seed_span_prompt(session: Session) -> None:
    """`chatbot_span_extractor` v1 from its code fallback, labelled production; an existing one is left alone."""
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from app.services.ai_prompt_registry import PROMPT_KEYS

    spec = PROMPT_KEYS[SPAN_PROMPT]
    version = session.query(AIPromptVersion).filter(AIPromptVersion.name == SPAN_PROMPT, AIPromptVersion.version == 1).first()
    if version is None:
        version = AIPromptVersion(
            name=SPAN_PROMPT, version=1, type="text", template=spec.fallback(), variables=list(spec.variables),
            commit_message=SPAN_MESSAGE,
        )
        session.add(version)
        session.flush()
    if session.query(AIPromptLabel).filter(AIPromptLabel.name == SPAN_PROMPT, AIPromptLabel.label == "production").first() is None:
        session.add(AIPromptLabel(name=SPAN_PROMPT, label="production", version_id=version.id))
        session.flush()


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        seed_span_prompt(session)
        publish_on_production(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Drop the rows this migration made: the span prompt it seeded and the unlabelled parser versions it published."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt_labels WHERE name = :n AND version_id IN "
            "(SELECT id FROM ai_prompt_versions WHERE name = :n AND commit_message = :m)"
        ),
        {"n": SPAN_PROMPT, "m": SPAN_MESSAGE},
    )
    bind.execute(
        sa.text("DELETE FROM ai_prompt_versions WHERE name = :n AND commit_message = :m"),
        {"n": SPAN_PROMPT, "m": SPAN_MESSAGE},
    )
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt_versions WHERE name = :n AND commit_message = :m "
            "AND id NOT IN (SELECT version_id FROM ai_prompt_labels)"
        ),
        {"n": PARSER, "m": PARSER_MESSAGE},
    )
