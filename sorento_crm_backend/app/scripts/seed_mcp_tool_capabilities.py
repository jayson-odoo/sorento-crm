"""Seed / rebuild Tool-RAG capabilities (implemented MCP tools + planned tools) into embedding queue.

Typical usage:

  # Seed (or refresh) embeddings for all implemented MCP tools from catalog.py
  python -m app.scripts.seed_mcp_tool_capabilities

  # Include planned/aspirational tool definitions as well
  python -m app.scripts.seed_mcp_tool_capabilities --include-planned

  # Seed only a specific tool (useful after tweaking its intent)
  python -m app.scripts.seed_mcp_tool_capabilities --only crm_master_products_list

  # Preview what would be seeded without queueing jobs
  python -m app.scripts.seed_mcp_tool_capabilities --dry-run

  # Full rebuild: mark existing mcp_tool chunks as non-current and re-embed everything
  python -m app.scripts.seed_mcp_tool_capabilities --rebuild
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

from sqlalchemy import text

from app.database import SessionLocal
from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
from app.services.embedding_service import EmbeddingEventService
from app.services.mcp_tool_capability_service import build_capability_documents, TOOL_INTENTS


def _sync_enabled_tools(db) -> list[tuple[str, int, int]]:
    """Ensure every catalogued tool (TOOL_INTENTS) is present in every
    ai_assistant_configs.enabled_tools whitelist.

    The RAG pipeline applies `enabled_tools` as a hard filter after reranking,
    so a tool missing from the whitelist is invisible to the LLM no matter how
    high its RAG score. Keep this in lockstep with the catalog to prevent
    silently-dropped tools after catalog additions.
    """
    catalog = sorted(TOOL_INTENTS.keys())
    rows = db.execute(text("SELECT id, enabled_tools FROM ai_assistant_configs")).all()
    report: list[tuple[str, int, int]] = []
    for r in rows:
        cur = set(r.enabled_tools or [])
        merged = sorted(cur | set(catalog))
        added = len(set(merged) - cur)
        if added:
            db.execute(
                text("UPDATE ai_assistant_configs SET enabled_tools = CAST(:t AS jsonb), updated_at = NOW() WHERE id = :i"),
                {"t": json.dumps(merged), "i": r.id},
            )
        report.append((str(r.id), len(cur), added))
    db.commit()
    return report


def _mark_existing_non_current(db) -> int:
    now = datetime.utcnow()
    touched = (
        db.query(EmbeddingChunk)
        .filter(EmbeddingChunk.source_type == "mcp_tool", EmbeddingChunk.is_current.is_(True))
        .update({EmbeddingChunk.is_current: False, EmbeddingChunk.superseded_at: now}, synchronize_session=False)
    )
    (
        db.query(EmbeddingDocument)
        .filter(EmbeddingDocument.source_type == "mcp_tool", EmbeddingDocument.is_active.is_(True))
        .update({EmbeddingDocument.is_active: False}, synchronize_session=False)
    )
    db.commit()
    return int(touched or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed / rebuild mcp_tool capability docs in embedding queue")
    parser.add_argument("--implemented-only", dest="implemented_only", action="store_true", help="Only seed implemented MCP tools")
    parser.add_argument("--include-planned", dest="implemented_only", action="store_false", help="Include planned/non-MCP tool definitions")
    parser.set_defaults(implemented_only=True)
    parser.add_argument("--definitions-file", default=None, help="Optional JSON file for tool RAG definitions")
    parser.add_argument("--only", default=None, help="Seed only tools whose source_key exactly matches this value")
    parser.add_argument("--rebuild", action="store_true", help="Mark existing mcp_tool chunks non-current before seeding so every tool is fully re-embedded")
    parser.add_argument("--dry-run", action="store_true", help="Print payload summary without enqueueing")
    parser.add_argument("--triggered-by", default="cli-mcp-tool-seed")
    args = parser.parse_args()

    include_planned = not args.implemented_only
    docs = build_capability_documents(include_planned=include_planned, definitions_file=args.definitions_file)
    if args.only:
        docs = [d for d in docs if d.source_key == args.only]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "count": len(docs),
                    "includes_planned": include_planned,
                    "rebuild": args.rebuild,
                    "sample": [
                        {
                            "source_id": d.source_id,
                            "tool_name": d.metadata.get("tool_name"),
                            "category": d.metadata.get("category"),
                            "questions": (d.metadata.get("typical_user_questions") or [])[:2],
                        }
                        for d in docs[:10]
                    ],
                },
                indent=2,
            )
        )
        return

    db = SessionLocal()
    try:
        invalidated = _mark_existing_non_current(db) if args.rebuild else 0
        svc = EmbeddingEventService(db)
        queued = 0
        failed = 0
        for doc in docs:
            try:
                svc.queue_event(
                    source_type="mcp_tool",
                    source_id=doc.source_id,
                    source_key=doc.source_key,
                    event_type="embedding.rebuild_requested",
                    changed_fields=["tool_capability_seed"],
                    payload={"capability": {"title": doc.title, "source_key": doc.source_key, "body_text": doc.body_text, "metadata": doc.metadata}},
                    triggered_by=args.triggered_by,
                )
                queued += 1
            except Exception:
                failed += 1
        sync_report = _sync_enabled_tools(db)
        print(
            json.dumps(
                {
                    "queued": queued,
                    "failed": failed,
                    "total": len(docs),
                    "invalidated_chunks": invalidated,
                    "enabled_tools_sync": [
                        {"config_id": cid, "before": before, "added": added}
                        for (cid, before, added) in sync_report
                    ],
                },
                indent=2,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
