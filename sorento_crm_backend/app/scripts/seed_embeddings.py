"""CLI utility to seed embedding events from existing DB data.

Usage examples:
  python -m app.scripts.seed_embeddings --source all --batch-size 300
  python -m app.scripts.seed_embeddings --source product --max-rows 1000 --dry-run
"""
from __future__ import annotations

import argparse
import json

from app.database import SessionLocal
from app.services.embedding_backfill_service import EmbeddingBackfillService


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed embedding queue from existing records")
    parser.add_argument(
        "--source",
        default="all",
        choices=[
            "all",
            "product",
            "promotion",
            "promotion_product",
            "inbound_shipment",
            "inbound_shipment_line",
            "spo_allocation",
            "picking_header",
            "picking_line",
            "product_attachment",
            "promotion_attachment",
            "attachment",
            "form",
            "schema_doc",
            "order",
            "order_status",
            "order_line",
            "mcp_tool",
        ],
        help="Source table to backfill",
    )
    parser.add_argument("--batch-size", type=int, default=500, help="Rows per fetch batch")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional hard cap per source")
    parser.add_argument("--dry-run", action="store_true", help="Scan only, do not enqueue events")
    parser.add_argument("--triggered-by", default="cli-backfill", help="Audit actor label")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = EmbeddingBackfillService(db).run(
            source=args.source,
            batch_size=max(1, args.batch_size),
            max_rows=args.max_rows if args.max_rows and args.max_rows > 0 else None,
            dry_run=args.dry_run,
            triggered_by=args.triggered_by,
        )
        print(json.dumps(result, default=str, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
