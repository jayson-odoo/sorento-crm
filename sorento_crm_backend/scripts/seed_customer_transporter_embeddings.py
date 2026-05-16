"""One-shot backfill for customer + transporter embedding sources.

Run after migration 200_transporters_table is applied and the embedding worker
is running. Enqueues rebuild events for:

  * Every Customer row (master table).
  * Every distinct orders.debtor_code with no matching Customer (synthetic
    source_id `debtor:<code>`).
  * Every Transporter row (seeded by the migration from distinct orders.transporter).

Usage:
    python -m scripts.seed_customer_transporter_embeddings
    python -m scripts.seed_customer_transporter_embeddings --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a top-level script from sorento_crm_backend/.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.services.embedding_backfill_service import EmbeddingBackfillService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=300)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--triggered-by", default="cli-seed-customer-transporter")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        svc = EmbeddingBackfillService(db)
        summary = {}
        for source in ("customer", "transporter"):
            result = svc.run(
                source=source,
                batch_size=max(1, args.batch_size),
                max_rows=args.max_rows if args.max_rows and args.max_rows > 0 else None,
                dry_run=args.dry_run,
                triggered_by=args.triggered_by,
            )
            summary[source] = result
        print(json.dumps(summary, default=str, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
