"""Publish the chatbot parser prompt with the LOW STOCK REPORT words as NEW versions,
label unmoved (console check, 14 Sep 2026).

Found on the lane stack's own console run, and invisible to pytest for the reason
migration 514 records: every parser test asserts against the Python constant, while
`ai_prompt_registry.render()` reads the PUBLISHED `chatbot_semantic_parser` row (the
`production` label) and falls back to the constant only when no DB row exists at all. So
`chatbot_parser_prompt.LOW_STOCK_ADDENDUM` (S7, #893) reached no live turn: "low stock
report" parsed as `check_stock` and "reorder report" as a form lookup, and the low stock
intent could never fire however it was phrased.

Both bodies are published for the measured reason 487, 490 and 514 give: prod's
`production` label sits on the FULL `SEMANTIC_PARSER_PROMPT`, while the local / dev label
sits on the SLIM one, so publishing one text reaches one deployment only.

Same immutable-versions-plus-movable-labels split as migration 475: each text lands as the
next `chatbot_semantic_parser` version with NO label, so promoting is one label move in
the admin UI and rolling back is the reverse move. **Nothing a customer sees changes until
the owner promotes the label** - that promote is a post-deploy step on this lane's PR.

Idempotent, and safe on a fresh database: ``seed_prompt_registry`` runs first so v1 and
the ``production`` label exist even on an install that never saw an earlier chatbot
migration, and each publish is skipped when a version already carries that template.

The insert logic lives in module-level ``publish(session)`` so it can be called outside
alembic (e.g. to publish against the shared dev database without an ``alembic upgrade``,
which is how the console check gets a version id to pass to ``--prompt-version``).

Revision ID: 517_chatbot_low_stock_vocab
Revises: 516_low_stock_report
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS

revision = "517_chatbot_low_stock_vocab"
down_revision = "516_low_stock_report"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"


def _full_text() -> str:
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT

    return SEMANTIC_PARSER_PROMPT


def _slim_text() -> str:
    # SEMANTIC_PARSER_PROMPT_SLIM retired from the live module (chatbot turn
    # re-architecture S0, AC-1506) - this migration keeps publishing the exact body it
    # always published, from the immutable copy alembic/_legacy_prompt_bodies.py holds.
    import sys
    from pathlib import Path

    _alembic_root = Path(__file__).resolve().parent.parent
    if str(_alembic_root) not in sys.path:
        sys.path.insert(0, str(_alembic_root))
    from _legacy_prompt_bodies import SEMANTIC_PARSER_PROMPT_SLIM_V1

    return SEMANTIC_PARSER_PROMPT_SLIM_V1


def _publish_one(session: Session, template: str, tag: str) -> int | None:
    """Publish ``template`` as the next `chatbot_semantic_parser` version, unless a
    version already carries it. Returns the new version number, or None when already
    published. ``tag`` is only for the log line (``"full"`` or ``"slim"``)."""
    spec = PROMPT_KEYS[PROMPT_NAME]
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
            "chatbot parser low-stock-vocabulary %s prompt already published as v%s; "
            "nothing to do",
            tag,
            existing.version,
        )
        return None
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
        "published chatbot parser low-stock-vocabulary %s prompt as v%s (%s chars); "
        "production label left on the previous version, promote by moving it",
        tag,
        next_version,
        len(template),
    )
    return next_version


def publish(session: Session) -> dict[str, int | None]:
    """Publish BOTH the FULL and SLIM texts as new versions, each idempotent on template
    equality. Returns ``{"full": v|None, "slim": v|None}``; a second call on an
    already-published database returns both None."""
    return {
        "full": _publish_one(session, _full_text(), "full"),
        "slim": _publish_one(session, _slim_text(), "slim"),
    }


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
    """Drop the unlabelled versions this migration published (FULL and SLIM).

    A version this migration published can stop being unlabelled: the owner may have
    since moved a label (e.g. `production`) onto it in the admin UI.
    `AIPromptLabel.version_id` is `ondelete="CASCADE"` (`app/models/ai_prompt.py`), so
    deleting a labelled version would silently delete the label row with it - a
    downgrade must never do that. Any version this migration published that now carries
    a label is therefore excluded from the delete; the label keeps pointing at it.
    """
    bind = op.get_bind()
    templates = [_full_text(), _slim_text()]
    session = Session(bind=bind)
    try:
        labelled_version_ids = {
            row[0]
            for row in (
                session.query(AIPromptLabel.version_id)
                .join(AIPromptVersion, AIPromptVersion.id == AIPromptLabel.version_id)
                .filter(AIPromptVersion.name == PROMPT_NAME)
                .all()
            )
        }
        query = session.query(AIPromptVersion).filter(
            AIPromptVersion.name == PROMPT_NAME,
            AIPromptVersion.template.in_(templates),
        )
        if labelled_version_ids:
            query = query.filter(AIPromptVersion.id.notin_(labelled_version_ids))
        query.delete(synchronize_session=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
