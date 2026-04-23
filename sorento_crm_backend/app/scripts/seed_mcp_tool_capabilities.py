"""Seed Tool-RAG capabilities (implemented MCP tools + planned tools) into embedding queue."""
from __future__ import annotations

import argparse
import json

from app.database import SessionLocal
from app.services.embedding_service import EmbeddingEventService
from app.services.mcp_tool_capability_service import build_capability_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed mcp_tool capability docs into embedding queue")
    parser.add_argument("--implemented-only", dest="implemented_only", action="store_true", help="Only seed implemented MCP tools")
    parser.add_argument("--include-planned", dest="implemented_only", action="store_false", help="Include planned/non-MCP tool definitions")
    parser.set_defaults(implemented_only=True)
    parser.add_argument("--definitions-file", default=None, help="Optional JSON file for tool RAG definitions")
    parser.add_argument("--dry-run", action="store_true", help="Print payload summary without enqueueing")
    parser.add_argument("--triggered-by", default="cli-mcp-tool-seed")
    args = parser.parse_args()

    include_planned = not args.implemented_only
    docs = build_capability_documents(include_planned=include_planned, definitions_file=args.definitions_file)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "count": len(docs),
                    "sample": [d.source_id for d in docs[:5]],
                    "includes_planned": include_planned,
                },
                indent=2,
            )
        )
        return

    db = SessionLocal()
    try:
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
        print(json.dumps({"queued": queued, "failed": failed, "total": len(docs)}, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
