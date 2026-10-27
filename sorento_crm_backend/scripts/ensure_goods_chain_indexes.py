"""Retry the goods chain key indexes migration `gc_idx_0001_spo_from_po_key` could not build.

GOODSCHAIN-INDEX-QUERY. That revision lets a deploy succeed when an index build times out
(`app/utils/online_index.py`), so something has to try again: `start.sh` runs this in the
background on every backend start, after `alembic upgrade head`. With both indexes VALID it is
one catalog lookup per index. Two backends starting together (blue and green) take a
pg_try_advisory_lock first; the one that does not get it does nothing.

Never fails the container: every outcome exits 0 and is logged.

    python -m scripts.ensure_goods_chain_indexes
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.utils.online_index import (
    ADVISORY_LOCK_KEY,
    GOODS_CHAIN_KEY_INDEXES,
    ensure_indexes_online,
    index_valid,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("ensure_goods_chain_indexes")


def run(engine) -> bool:
    """True when every index is VALID afterwards."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as bind:
        if all(index_valid(bind, t, n) is True for t, n, _c in GOODS_CHAIN_KEY_INDEXES):
            return True
        if not bind.execute(sa.text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}).scalar():
            log.info("another backend is building the goods chain key indexes; leaving it to it")
            return False
        try:
            return ensure_indexes_online(bind, GOODS_CHAIN_KEY_INDEXES)
        finally:
            bind.execute(sa.text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})


def main() -> None:
    try:
        # The URL `alembic/env.py` migrates through, so this reaches the same database.
        from app.config import settings

        ok = run(sa.create_engine(settings.database_url, poolclass=sa.pool.NullPool))
        log.info("goods chain key indexes %s", "VALID" if ok else "not all built; next start retries")
    except Exception:  # noqa: BLE001 - a retry must never take the backend down
        log.warning("goods chain key index retry failed; next start retries", exc_info=True)


if __name__ == "__main__":
    main()
