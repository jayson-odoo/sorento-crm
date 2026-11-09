"""SORENTO-TOWN follow-up: the tick falls back to the primary when the read replica is down.

PLAN-sorento-town-08nov.md (Phase 0 contract, the tick): "build on a session from the read replica
when `TOWN_REPLICA_DATABASE_URL` is set (else primary)". A configured but unreachable replica used to
fail every company's build (each logged, nothing stored); now the tick checks the replica once, logs
one warning, and builds every company on the primary.

Kill test: drop the reachability check in `run_town_snapshot_tick` (always use the replica when the
URL is set) and `test_a_down_replica_falls_back_to_the_primary_with_one_warning` goes red.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID
from tests.town._town_seed import DAY, fake_full, myt
from tests.town.test_town_snapshot_tick import _KeepOpen, _keys_for, _tick, env  # noqa: F401  (fixture)

# Nothing listens on port 1, so a connection is refused at once (no timeout to wait out).
DOWN_REPLICA = "postgresql+psycopg2://town:town@127.0.0.1:1/town_replica"


def test_a_down_replica_falls_back_to_the_primary_with_one_warning(env, caplog):
    env.patch.setattr(settings, "town_replica_database_url", DOWN_REPLICA)
    with caplog.at_level(logging.WARNING, logger=env.town.logger.name):
        _tick(env, myt(DAY, 10, 0))

    assert sorted(env.calls) == sorted([DEFAULT_COMPANY_ID, MOCHA_ID])
    for company in (DEFAULT_COMPANY_ID, MOCHA_ID):
        keys = {k.decode() for k in _keys_for(company)}
        assert f"town:{company}:{DAY.isoformat()}:full" in keys
    replica_warnings = [r for r in caplog.records if "replica" in r.getMessage().lower()]
    assert len(replica_warnings) == 1, [r.getMessage() for r in caplog.records]
    assert replica_warnings[0].levelno == logging.WARNING
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_a_reachable_replica_is_still_where_the_builds_run(env):
    replica = _KeepOpen(env.db)
    replica.on_replica = True
    env.patch.setattr(settings, "town_replica_database_url", DOWN_REPLICA)
    env.patch.setattr(env.town, "_replica_session", lambda: replica)

    seen = []

    def probe(session, company_id, day, *, now):
        seen.append(getattr(session, "on_replica", False))
        return fake_full(day, company_id)

    env.patch.setattr(env.town, "build_snapshot", probe)
    _tick(env, myt(DAY, 10, 0))
    assert seen and all(seen)
