"""Republish the SUPPLIER-ASK prompt pair on a copy that already ran `sask_0002_span_supplier`.

The migration publishes once per exact text, so a copy migrated before fix round 3 (#2066) holds the parser version
without the "after <year>" sentence. This runs the migration's own `publish` again (no `alembic_version` change):
the span version it finds is reused, and the parser version with the new text is published UNLABELLED and paired
with it. Only the owner moves a label.

Usage, from `sorento_crm_backend/` with the backend env (`DATABASE_URL`) in place:

    venv/bin/python -m scripts.publish_supplier_ask_prompts

Prints `span v<N>, parser v<M>: after-year sentence published. Pin parser v<M>.`, or exits non-zero with FAILED
when the published parser version does not carry the date sentence.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "sask_0002_span_supplier.py"


def _migration():
    spec = importlib.util.spec_from_file_location("_sask_0002_span_supplier", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    from app.database import SessionLocal
    from app.models.ai_prompt import AIPromptVersion

    sask = _migration()
    db = SessionLocal()
    try:
        span_v, parser_v = sask.publish(db)
        db.commit()
        row = (
            db.query(AIPromptVersion)
            .filter(AIPromptVersion.name == sask.PARSER, AIPromptVersion.version == parser_v)
            .first()
            if parser_v is not None
            else None
        )
        took = bool(row is not None and sask.AFTER_YEAR_SENTENCE in (row.template or ""))
        if not took:
            raise SystemExit(
                f"FAILED: parser v{parser_v} does not carry the after-year sentence (span v{span_v}); nothing to pin"
            )
        print(f"span v{span_v}, parser v{parser_v}: after-year sentence published. Pin parser v{parser_v}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
