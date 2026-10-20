"""Publish the PARSER-TEMPLATE parser version: `head/parser_template.TEMPLATE`, verbatim.

The result is the NEXT `chatbot_semantic_parser` version, UNLABELLED: runs pin it with
`prompt_overrides`, and only the owner moves a label. Idempotent: a version already carrying
the exact template publishes nothing.

Usage, from `sorento_crm_backend/` with the backend env (`DATABASE_URL`) in place:

    venv/bin/python -m scripts.publish_parser_template

Prints `published chatbot_semantic_parser v<N>` or `already published as v<N>`.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

PROMPT_NAME = "chatbot_semantic_parser"


def _existing(session: Session):
    from app.models.ai_prompt import AIPromptVersion
    from app.services.chatbot.head.parser_template import TEMPLATE

    return (
        session.query(AIPromptVersion)
        .filter(AIPromptVersion.name == PROMPT_NAME, AIPromptVersion.template == TEMPLATE)
        .first()
    )


def publish(session: Session) -> int | None:
    """The new version number, or None when a version already carries the template."""
    from app.models.ai_prompt import AIPromptVersion
    from app.services.chatbot.head.parser_template import TEMPLATE

    if _existing(session) is not None:
        return None
    versions = session.query(AIPromptVersion.version).filter(AIPromptVersion.name == PROMPT_NAME).all()
    next_version = max((int(v[0]) for v in versions), default=0) + 1
    session.add(
        AIPromptVersion(
            name=PROMPT_NAME,
            version=next_version,
            type="text",
            template=TEMPLATE,
            variables=["current_date"],
            commit_message="PARSER-TEMPLATE: the consolidated parser template",
        )
    )
    session.commit()
    return next_version


def main() -> None:
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        new = publish(session)
        existing = _existing(session) if new is None else None
        if existing is not None:
            print(f"already published as v{existing.version}")
        else:
            print(f"published {PROMPT_NAME} v{new}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
