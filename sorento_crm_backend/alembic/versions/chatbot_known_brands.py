"""Publish the chatbot parser prompt with BOTH the per-entity `quantity` key
(slice 5, F4) and the `Known brands:` line (slice 9, F1a) as ONE new version,
label unmoved (issue #1262, Samantha case).

Merged from two migrations (review round, 26 Sep 2026): `chatbot_quantity_vocab`
and `chatbot_known_brands` each published the SAME live `SEMANTIC_PARSER_PROMPT`
constant - by the time the second one ran, the Python module already carried
BOTH addenda (they are stacked string concatenation, not two separate texts), so
`_publish_one`'s own idempotent-on-template-equality check made the second
migration's own `publish()` call a no-op every time: two revisions publishing one
version, and downgrading the second alone would have deleted the FIRST
migration's own row (the one both slices actually depend on) since `downgrade()`
matches by template content, not by which migration wrote it. Neither slice was
pushed to prod, so folding them into one revision - this one - is safe; nothing
downstream references the retired `chatbot_quantity_vocab` id (grepped).

Same reason `521_sales_report_month_fix` publishes: `ai_prompt_registry.render()`
reads the PUBLISHED row, not the Python constant (the fallback is used only when
no DB row exists at all), so a session must have a published version carrying
both addenda before either can reach a live turn.

Slice 5 (owner ruling 1, issue comment 26 Sep ~06:40Z, binding): "i don't want
hard code, the parser supposed to be able to identify the quantity right?" - the
schema gains a per-entity `quantity` (`app/services/chatbot/head/parser.py`, code
change, not this migration's business) and `QUANTITY_ADDENDUM` teaches the model
the shape a quantity actually takes beside a product code ("xN", "N pcs", "N
units") and that a caption-only quantity line applies to the photo's own
products - never a rule for the CODE to strip a quantity back out of text it
already read correctly.

Slice 9 (F1a) carries TWO changes of its own, not one addendum stacked on an
unchanged body:

1. An IN-PLACE edit to the ENTITY OPERATIONS list's own `brand -> Sorento, Mocha,
   or Cabana` bullet (`app/services/chatbot_parser_prompt.py`, code change, not
   this migration's business) - AC-S9-2's own test asserts the hard-coded phrase
   is GONE from the published template, which an addendum stacked outside the
   body cannot make true (the phrase would still be present, merely superseded in
   meaning). The bullet now points at the `Known brands:` line instead.
2. `KNOWN_BRANDS_ADDENDUM` (the same named-addendum pattern `QUANTITY_ADDENDUM`
   ships), stacked on top of the quantity addendum - teaches the model to read
   that line, fresh every turn, from the live `Brand` table for the contact's own
   companies (`turn_runtime`, code change) - a brand entity's `canonical_code` is
   the brand NAME as that line lists it, never the code in parentheses and never
   a name the model remembers from training.

Only the FULL body is published (fix lane round 2, N2). The earlier draft also
"republished" the SLIM body, as 487 / 490 / 514 / 517 / 519 / 520 / 521 do, but the
SLIM body retired from the live module (AC-1506) and the copy this revision could
reach was the frozen legacy `SLIM_V1`, which carries NEITHER addendum. A local or dev
label sitting on SLIM therefore gets neither the quantity key nor the Known brands
line from this revision; point that label at the FULL version this revision publishes
to test either slice there. Publishing SLIM_V1 was a no-op on every database (an
earlier migration already holds that text), and matching it on downgrade deleted the
earlier migration's own unlabelled row.

Same immutable-versions-plus-movable-labels split as migration 475: the text
lands as the next `chatbot_semantic_parser` version with NO label, so promoting
is one label move in the admin UI and rolling back is the reverse move. Nothing a
customer sees changes until the owner promotes.

Idempotent, and safe on a fresh database: ``seed_prompt_registry`` runs first so
v1 and the ``production`` label exist even on an install that never saw an
earlier chatbot migration, and each publish is skipped when a version already
carries that template.

The insert logic lives in module-level ``publish(session)`` so it can be called
outside alembic (e.g. to publish against the shared dev database without an
``alembic upgrade``, which is how the console check gets a version id to pass to
``--prompt-version``).

Revision ID: chatbot_known_brands
Revises: sales_0002_team_leader
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS

revision = "chatbot_known_brands"
down_revision = "sales_0002_team_leader"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"


def _full_text() -> str:
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT

    return SEMANTIC_PARSER_PROMPT


def _publish_one(session: Session, template: str, tag: str) -> int | None:
    """Publish ``template`` as the next `chatbot_semantic_parser` version, unless a
    version already carries it. Returns the new version number, or None when already
    published. ``tag`` is only for the log line."""
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
            "chatbot parser quantity+known-brands %s prompt already published as v%s; "
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
        "published chatbot parser quantity+known-brands %s prompt as v%s (%s chars); "
        "production label left on the previous version, promote by moving it",
        tag,
        next_version,
        len(template),
    )
    return next_version


def publish(session: Session) -> dict[str, int | None]:
    """Publish the FULL text as a new version, idempotent on template equality. Returns
    ``{"full": v|None}``; a second call on an already-published database returns None."""
    return {"full": _publish_one(session, _full_text(), "full")}


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
    """Drop the unlabelled version this migration published. Its FULL text carries both
    addenda, so no other migration's row matches it (a later identical publish is
    skipped by `_publish_one`), which is what makes a template match safe here.

    A version this migration published can stop being unlabelled: the owner may have
    since moved a label (e.g. `production`) onto it in the admin UI.
    `AIPromptLabel.version_id` is `ondelete="CASCADE"` (`app/models/ai_prompt.py`), so
    deleting a labelled version would silently delete the label row with it - a
    downgrade must never do that. Any version this migration published that now carries
    a label is therefore excluded from the delete; the label keeps pointing at it.
    """
    bind = op.get_bind()
    templates = [_full_text()]
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
