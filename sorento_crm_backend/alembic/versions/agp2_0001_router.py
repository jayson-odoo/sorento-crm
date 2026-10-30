"""AGENTIC-P2-ROUTE: router settings, per-contact agent cap, Jev key, Jev price and the router prompt

Revision ID: agp2_0001_router
Revises: oihr_0011_item_code_wrap
Create Date: 2026-10-30 00:00:00.000000

Additive and idempotent. Two system settings (the router's confidence floor and the daily agent
cap), a nullable per-contact cap, the TypeSafe (Jev) key slot on the AI config, the `jev-1.14.0`
price row, and the `chatbot_router` prompt (v1 + production label on provider `typesafe`, model
`jev-1.14.0`) seeded when missing. Downgrade drops the columns and the seeded prompt; the price row
stays (an operator may have edited it).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from app.services.analytics_connector import prices

revision = "agp2_0001_router"
down_revision = "oihr_0011_item_code_wrap"
branch_labels = None
depends_on = None

PROMPT = "chatbot_router"
MESSAGE = "AGENTIC-P2-ROUTE: the console router's instructions and criteria for Jev."
MODEL = "jev-1.14.0"


def seed_router_prompt(session: Session) -> None:
    """`chatbot_router` v1 from its code fallback with a production label (provider typesafe, model
    jev-1.14.0); an existing label is left alone."""
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from app.services.ai_prompt_registry import PROMPT_KEYS

    if session.query(AIPromptLabel).filter(AIPromptLabel.name == PROMPT, AIPromptLabel.label == "production").first():
        return
    spec = PROMPT_KEYS[PROMPT]
    version = session.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT, AIPromptVersion.version == 1).first()
    if version is None:
        version = AIPromptVersion(
            name=PROMPT, version=1, type="text", template=spec.fallback(), variables=list(spec.variables),
            commit_message=MESSAGE,
        )
        session.add(version)
        session.flush()
    session.add(
        AIPromptLabel(name=PROMPT, label="production", version_id=version.id, provider="typesafe", model=MODEL)
    )
    session.flush()


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings "
        "ADD COLUMN IF NOT EXISTS chatbot_router_min_score DOUBLE PRECISION NOT NULL DEFAULT 0.7"
    )
    op.execute(
        "ALTER TABLE system_settings "
        "ADD COLUMN IF NOT EXISTS chatbot_agent_daily_turns INTEGER NOT NULL DEFAULT 50"
    )
    op.execute("ALTER TABLE respond_contacts ADD COLUMN IF NOT EXISTS chatbot_agent_daily_turns INTEGER")
    op.execute("ALTER TABLE ai_assistant_configs ADD COLUMN IF NOT EXISTS typesafe_api_key_ciphertext TEXT")
    prices.seed_prices(op.get_bind(), (MODEL,))
    session = Session(bind=op.get_bind())
    try:
        seed_router_prompt(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt_labels WHERE name = :n AND version_id IN "
            "(SELECT id FROM ai_prompt_versions WHERE name = :n AND commit_message = :m)"
        ),
        {"n": PROMPT, "m": MESSAGE},
    )
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt_versions WHERE name = :n AND commit_message = :m "
            "AND id NOT IN (SELECT version_id FROM ai_prompt_labels)"
        ),
        {"n": PROMPT, "m": MESSAGE},
    )
    op.execute("ALTER TABLE ai_assistant_configs DROP COLUMN IF EXISTS typesafe_api_key_ciphertext")
    op.execute("ALTER TABLE respond_contacts DROP COLUMN IF EXISTS chatbot_agent_daily_turns")
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_agent_daily_turns")
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_router_min_score")
