"""The live production parser prompt, with registry variables where they reproduce it
exactly (owner, #1405, 1 Oct 2026).

Loads the owner-supplied production text (`alembic/data/chatbot_semantic_parser.prod-20261001.txt`,
verbatim, sha256 fdbf2ea1...) and swaps each hard-coded registry list for its
`{{variable}}` ONLY where the registry renders exactly that text from the tables as they
stand at migration time (`chatbot_prompt_vars.identical_wording_layer`). A registry that
differs keeps the owner's list literal; the report of every list (replaced or kept, and
what differs) is stored on the version (`config_json.identical_report`) and logged.

The result is proven before insert: rendering it from the tables gives the file byte for
byte. If that proof ever fails the file is inserted verbatim instead (no variables), so
the owner never gets a version that renders differently from what he pasted.

Inserted as ONE new UNLABELLED version (version = max + 1 at run time). No label moves
and no existing version is touched; the owner publishes it himself. Idempotent: does
nothing when a version with the same template, or from the same snapshot, exists.
Downgrade deletes only its own row, and only while it is unlabelled.

Revision ID: pdyn_0003_prod_identical
Revises: pdyn_0002_wording_layer
Create Date: 2026-10-01
"""
from __future__ import annotations

import hashlib
import logging
import pathlib

from alembic import op
from sqlalchemy import text as sql
from sqlalchemy.orm import Session

revision = "pdyn_0003_prod_identical"
down_revision = "pdyn_0002_wording_layer"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"
SNAPSHOT = pathlib.Path(__file__).resolve().parents[1] / "data" / "chatbot_semantic_parser.prod-20261001.txt"
MESSAGE = (
    "Production text of 1 Oct 2026 (owner-supplied), registry variables wherever the "
    "registry reproduces it exactly. Renders identical to that text. Unlabelled: publish "
    "from the Prompts page."
)


def _sha() -> str:
    return hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()


def _renders_identical(template: str, source: str, session: Session) -> bool:
    from app.services import ai_prompt_registry, chatbot_prompt_vars

    names = ai_prompt_registry.extract_tokens(template) & set(chatbot_prompt_vars.VARIABLE_NAMES)
    values = {name: chatbot_prompt_vars.render_value(session, name) for name in names}
    return ai_prompt_registry._substitute(template, values) == source


def apply(bind) -> int | None:
    from app.models.ai_prompt import AIPromptVersion
    from app.services import chatbot_prompt_vars

    source = SNAPSHOT.read_text(encoding="utf-8")
    sha = _sha()
    session = Session(bind=bind)
    try:
        chatbot_prompt_vars.clear_cache()
        template, report = chatbot_prompt_vars.identical_wording_layer(source, session)
        identical = _renders_identical(template, source, session)
        if not identical:
            logger.warning("prod snapshot: swapped text did not render identical; inserting it verbatim")
            template, report = source, [{"variable": "*", "line": None, "action": "kept literal (proof failed)"}]
        exists = session.execute(
            sql(
                "SELECT version FROM ai_prompt_versions WHERE name = :n "
                "AND (template = :t OR config_json->>'prod_snapshot_sha256' = :s) LIMIT 1"
            ),
            {"n": PROMPT_NAME, "t": template, "s": sha},
        ).scalar()
        if exists is not None:
            logger.info("prod snapshot already published as v%s; nothing to do", exists)
            return None
        top = session.execute(
            sql("SELECT max(version) FROM ai_prompt_versions WHERE name = :n"), {"n": PROMPT_NAME}
        ).scalar()
        version = int(top or 0) + 1
        variables = session.execute(
            sql(
                "SELECT v.variables FROM ai_prompt_versions v JOIN ai_prompt_labels l ON l.version_id = v.id "
                "WHERE l.name = :n AND l.label = 'production'"
            ),
            {"n": PROMPT_NAME},
        ).scalar()
        session.add(
            AIPromptVersion(
                name=PROMPT_NAME,
                version=version,
                type="text",
                template=template,
                variables=list(variables or ["current_date"]),
                config_json={
                    "prod_snapshot": SNAPSHOT.name,
                    "prod_snapshot_sha256": sha,
                    "rendered_identical": identical,
                    "identical_report": report,
                },
                commit_message=MESSAGE,
            )
        )
        session.commit()
        for row in report:
            logger.info("prod snapshot v%s: {{%s}} line %s %s", version, row["variable"], row["line"], row["action"])
        return version
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def remove(bind) -> None:
    """Delete this migration's own row, and only while nobody has labelled it."""
    bind.execute(
        sql(
            "DELETE FROM ai_prompt_versions v WHERE v.name = :n "
            "AND v.config_json->>'prod_snapshot_sha256' = :s "
            "AND NOT EXISTS (SELECT 1 FROM ai_prompt_labels l WHERE l.version_id = v.id)"
        ),
        {"n": PROMPT_NAME, "s": _sha()},
    )


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    remove(op.get_bind())
