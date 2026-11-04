"""Seed the PO-LINK-HISTORY "first seen" event for PO lines linked before history began.

POLH-BACKFILL-ASYNC. This was the `polh_0001_seen_backfill` migration's data step until the
5 Nov release, where it kept blue unhealthy past blue/green's 240 s wait and the whole release
rolled back. `start.sh` now runs this in the background on every backend start, after
`alembic upgrade head`; the work is `app.services.scm.po_link_history.backfill_seen` (one commit
per batch, resumable, idempotent). Once every linked line is seeded a run is one anti-join scan
(0.55 s on the prod clone) and inserts nothing.

Two backends starting together (blue and green) are serialised by a session advisory lock; the
one that does not get it does nothing.

Never fails the container: every outcome, an import error included, exits 0 and is logged.
(After `start.sh` execs gunicorn, gunicorn reaps this process like a worker, so a non-zero
exit would read as a crashed worker.)

    python -m scripts.backfill_po_link_seen
"""
from __future__ import annotations

import logging
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("backfill_po_link_seen")

#: pg advisory lock key, distinct from `app.utils.online_index.ADVISORY_LOCK_KEY`.
ADVISORY_LOCK_KEY = 0x504F4C48  # "POLH"


def run(engine) -> Optional[int]:
    """Rows seeded, or None when another backend holds the lock."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from app.services.scm import po_link_history

    key = {"k": ADVISORY_LOCK_KEY}
    # One dedicated connection: the session-level lock lives on it across the per-batch commits.
    with engine.connect() as conn:
        got = conn.execute(sa.text("SELECT pg_try_advisory_lock(:k)"), key).scalar()
        conn.commit()
        if not got:
            log.info("po link seen backfill: another backend is running it; skipped")
            return None
        try:
            with Session(bind=conn) as db:
                return po_link_history.backfill_seen(db)
        finally:
            conn.rollback()
            conn.execute(sa.text("SELECT pg_advisory_unlock(:k)"), key)
            conn.commit()


def main() -> None:
    try:
        # Imports inside the try: a broken import must not exit non-zero either.
        import sqlalchemy as sa

        # The URL `alembic/env.py` migrates through, so this reaches the same database.
        from app.config import settings

        seeded = run(sa.create_engine(settings.database_url, poolclass=sa.pool.NullPool))
        if seeded is not None:
            log.info("po link seen backfill: done, %d rows seeded", seeded)
    except Exception:  # noqa: BLE001 - a backfill must never take the backend down
        log.warning("po link seen backfill failed; next start resumes it", exc_info=True)


if __name__ == "__main__":
    main()
