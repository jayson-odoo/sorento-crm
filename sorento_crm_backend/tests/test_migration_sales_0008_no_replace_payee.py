"""Migration `sales_0008_no_replace_payee` (lane TARGET-PER-ACCOUNT-PAYOUT, owner card Q1 a, Q2 a, Q3).

Same harness as `test_migration_sales_0006_dealer_targets.py`: the sales revisions up to this one
run on a scratch copy of the `sales` schema inside one outer transaction that is rolled back.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import pytest
import sqlalchemy as sa

from app.database import engine

from .test_migration_sales_0003_targets import _check_constraints, _insert_target, _load, _run, _seed_company

_EARLIER = (
    "sales_0001_teams",
    "sales_0002_team_leader",
    "sales_0003_targets",
    "sales_0004_target_brands",
    "sales_0005_commission_tiers",
    "sales_0006_dealer_targets",
    "sales_0007_tier_additional",
)


def _seed_linked(raw, scratch):
    """Two dealer targets, the first replaced by the second and paid to a customer."""
    company = _seed_company(raw)
    top = _insert_target(raw, scratch, company_id=company, subject_kind="dealer")
    own = _insert_target(raw, scratch, company_id=company, subject_kind="dealer", replaced_by_target_id=top)
    return company, top, own


@contextmanager
def _upgraded(*, seed=None):
    mods = [_load(n) for n in _EARLIER]
    m8 = _load("sales_0008_no_replace_payee")
    scratch = f"zzs_mig_sales8_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    with engine.connect() as raw:
        outer = raw.begin()
        try:
            raw.exec_driver_sql(f'CREATE SCHEMA "{scratch}"')
            conn = raw.execution_options(schema_translate_map={"sales": scratch})
            for m in mods:
                _run(conn, m.upgrade)
            seeded = seed(raw, scratch) if seed else None
            _run(conn, m8.upgrade)
            yield raw, conn, scratch, m8, seeded
        finally:
            outer.rollback()


def _columns(raw, scratch, table):
    return {c["name"] for c in sa.inspect(raw).get_columns(table, schema=scratch)}


def test_revision_chains_and_fits():
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    m8 = _load("sales_0008_no_replace_payee")
    assert m8.revision == "sales_0008_no_replace_payee" and len(m8.revision) <= 32
    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert m8.down_revision in {r.revision for r in script.walk_revisions()}
    heads = list(script.get_heads())
    assert len(heads) == 1, heads
    assert m8.revision in {r.revision for r in script.walk_revisions(base="base", head=heads[0])}


def test_upgrade_drops_replaced_by_and_pays_to_keeping_the_targets():
    with _upgraded(seed=_seed_linked) as (raw, _conn, scratch, _m8, seeded):
        _company, top, own = seeded
        cols = _columns(raw, scratch, "targets")
        assert "replaced_by_target_id" not in cols and "payout_customer_id" not in cols
        checks = _check_constraints(raw, scratch, "targets")
        assert "ck_sales_targets_replaced_by_dealer" not in checks and "ck_sales_targets_payout_dealer" not in checks
        ids = {str(r[0]) for r in raw.execute(sa.text(f'SELECT id FROM "{scratch}".targets'))}
        assert {top, own} <= ids
        assert "bonus_amount" in _columns(raw, scratch, "target_tier_rates")


def test_a_negative_account_bonus_is_refused():
    with _upgraded() as (raw, _conn, scratch, _m8, _seeded):
        checks = _check_constraints(raw, scratch, "target_tier_rates")
        assert "bonus_amount" in checks["ck_sales_target_tier_rates_bonus_amount"]


def test_downgrade_round_trip():
    with _upgraded(seed=_seed_linked) as (raw, conn, scratch, m8, _seeded):
        _run(conn, m8.downgrade)
        cols = _columns(raw, scratch, "targets")
        assert {"replaced_by_target_id", "payout_customer_id"} <= cols
        assert "bonus_amount" not in _columns(raw, scratch, "target_tier_rates")
        _run(conn, m8.upgrade)
        assert "replaced_by_target_id" not in _columns(raw, scratch, "targets")


@pytest.fixture(autouse=True)
def _postgres_only():
    if engine.dialect.name != "postgresql":
        pytest.skip("Postgres only")
