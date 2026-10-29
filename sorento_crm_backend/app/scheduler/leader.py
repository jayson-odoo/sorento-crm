"""Scheduler leader guard (HA-TIER1-N8N-BOX).

The APScheduler `BackgroundScheduler` is single-node: two processes running it would each fire
every cron tick. Until now only the convention "one container sets ENABLE_SCHEDULER" kept it
single. With a warm standby node (documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md) that
convention is one wrong env line away from double-processing, so `start_scheduler` takes
leadership first:

1. The database must be writable (`pg_is_in_recovery()` false). A scheduler started by mistake
   on the standby, against the hot-standby replica, refuses to run. Always on: it is one query
   and works through any pooler.
2. When `SCHEDULER_LEADER_DATABASE_URL` is set, it must also win a session-level Postgres
   advisory lock, held on a connection of its own for the life of the process, so a second
   scheduler against the same primary refuses to run. That URL must reach Postgres DIRECTLY
   (not a transaction-mode pgbouncer): through such a pooler the lock sits on a server
   connection that outlives the process holding it, so the next worker could never start, or
   lands on that same server connection, re-enters the lock and runs beside the first.
   Unset = no lock (today's behaviour), logged once.

The lock lives as long as its session. A Postgres restart or a terminated backend ends it, so
the scheduler heartbeat calls `exit_if_leadership_lost` every tick: if the held connection no
longer answers, the process exits and `restart: unless-stopped` brings it back to take the lock
again (or to refuse, if another scheduler took it meanwhile). RQ work-horses forked from the
worker inherit the socket but never touch it, and leave through `os._exit`, so they do not close
it.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

LEADER_URL_ENV = "SCHEDULER_LEADER_DATABASE_URL"
LEADER_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"sorento-scheduler-leader").digest()[:8], "big", signed=True
)

_held = None  # the connection that holds the lock, for the life of the process
_held_guard = threading.Lock()


class SchedulerNotLeader(RuntimeError):
    """Raised when this process must not run the scheduler."""


def _assert_writable(connection) -> None:
    if connection.execute(text("SELECT pg_is_in_recovery()")).scalar():
        raise SchedulerNotLeader(
            "database is a read-only standby (pg_is_in_recovery); the scheduler runs only "
            "against the primary, after promotion"
        )


def acquire_leadership() -> None:
    """Take scheduler leadership or raise `SchedulerNotLeader`. Idempotent within a process."""
    global _held
    with _held_guard:
        if _held is not None:
            return
        url = os.getenv(LEADER_URL_ENV, "").strip()
        if not url:
            from app.database import engine

            with engine.connect() as connection:
                _assert_writable(connection)
            logger.warning(
                "%s unset: scheduler leader lock off (standby check only)", LEADER_URL_ENV
            )
            return

        connection = create_engine(
            url, poolclass=NullPool, connect_args={"options": "-c timezone=utc"}
        ).connect()
        try:
            _assert_writable(connection)
            taken = connection.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": LEADER_LOCK_KEY}
            ).scalar()
            connection.commit()
            if not taken:
                raise SchedulerNotLeader(
                    "another process holds the scheduler leader lock; only one scheduler may run"
                )
        except Exception:
            connection.close()
            raise
        _held = connection
        logger.info("Scheduler leader lock taken")


def exit_if_leadership_lost() -> None:
    """Exit the process when the lock's session is gone. No-op without a lock."""
    connection = _held
    if connection is None:
        return
    try:
        with _held_guard:
            connection.execute(text("SELECT 1"))
            connection.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("Scheduler leader lock lost (%s); exiting so a restart re-takes it", type(e).__name__)
        os._exit(1)


def release_leadership() -> None:
    """Drop the lock (scheduler shutdown, tests). Closing the session frees it too."""
    global _held
    with _held_guard:
        connection, _held = _held, None
    if connection is None:
        return
    try:
        connection.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LEADER_LOCK_KEY})
        connection.commit()
    except Exception:  # noqa: BLE001
        logger.warning("scheduler leader lock release failed", exc_info=True)
    finally:
        connection.close()  # NullPool: the session ends, so the lock cannot linger
