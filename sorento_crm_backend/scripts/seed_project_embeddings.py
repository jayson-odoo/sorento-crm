"""One-shot backfill for the `project` embedding source (PROJECT-REG-PORTAL D9).

The registration queue's "meaning" duplicate signal reads project embeddings. New and edited
projects are queued by the change listener; this enqueues rebuild events for the projects that
already exist. Run it once with the embedding worker running.

Usage:
    python -m scripts.seed_project_embeddings
    python -m scripts.seed_project_embeddings --dry-run
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
from app.models.base import set_company_scope  # noqa: E402
from app.services.embedding_backfill_service import EmbeddingBackfillService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=300)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--triggered-by", default="cli-seed-project")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        set_company_scope(db, None)  # every company's projects
        result = EmbeddingBackfillService(db).run(
            source="project",
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
