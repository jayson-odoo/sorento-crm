"""Retry the indexes `gc_idx_0001_spo_from_po_key`, `bfd_idx_0001_billing_from_doc_no` and `lec_0002_embedding_indexes` could not build.

GOODSCHAIN-INDEX-QUERY, BILLING-FROM-DOC-INDEX, LOOKUP-EMBED-CENTRAL. Those revisions let a deploy succeed when an
index build times out (`app/utils/online_index.py`), so something has to try again: `start.sh`
runs this in the background on every backend start, after `alembic upgrade head`. With every
index VALID it is one catalog lookup per index. Two builders at once (blue and green starting together, or a
migration still running) are serialised by the advisory lock `ensure_indexes_online` takes;
the one that does not get it does nothing.

Never fails the container: every outcome, an import error included, exits 0 and is logged.
(After `start.sh` execs gunicorn, gunicorn reaps this process like a worker, so a non-zero
exit would read as a crashed worker.)

    python -m scripts.ensure_goods_chain_indexes
"""
from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("ensure_goods_chain_indexes")


def run(engine) -> bool:
    """True when every index is VALID afterwards."""
    from app.services import embedding_indexes
    from app.utils import online_index

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as bind:
        return online_index.ensure_indexes_online(
            bind,
            online_index.GOODS_CHAIN_KEY_INDEXES
            + online_index.BILLING_FROM_DOC_INDEXES
            + embedding_indexes.MIGRATION_INDEXES,
        )


def main() -> None:
    try:
        # Imports inside the try: a broken import must not exit non-zero either.
        import sqlalchemy as sa

        # The URL `alembic/env.py` migrates through, so this reaches the same database.
        from app.config import settings

        ok = run(sa.create_engine(settings.database_url, poolclass=sa.pool.NullPool))
        log.info("online indexes %s", "VALID" if ok else "not all built; next start retries")
    except Exception:  # noqa: BLE001 - a retry must never take the backend down
        log.warning("online index retry failed; next start retries", exc_info=True)


if __name__ == "__main__":
    main()
