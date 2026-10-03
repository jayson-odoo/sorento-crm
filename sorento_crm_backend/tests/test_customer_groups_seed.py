"""`cust_group_0001` is DDL only (lane CUST-GROUP-SEED-REVIEW).

Owner ruling 3 Oct 2026: no automatic name-matching joins, explicit links only. The upgrade
creates `customer_groups` and `customers.customer_group_id` and assigns NO customer to any
group, however alike their names are. ``upgrade()`` runs here under a real alembic
``Operations`` context on the blank Postgres schema, with the table and column dropped first
so it has something to create.

`plan_groups` is still the pure name-rule helper behind ``scripts/customer_groups_seed_sql.py``
(a proposal printer); its naming tests stay below.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.order import Customer
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID

from ._pg_fixture import blank_session

VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _load():
    path = VERSIONS / "cust_group_0001.py"
    assert path.exists(), "cust_group_0001.py does not exist"
    spec = importlib.util.spec_from_file_location("mig_cust_group_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain_and_additive():
    module = _load()
    assert module.revision == "cust_group_0001"
    # Survives a re-parent and later migrations: one head, and this revision is on its path.
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(VERSIONS.parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(VERSIONS.parent))
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_heads())
    assert len(heads) == 1
    assert module.revision in {r.revision for r in script.walk_revisions(base="base", head=heads[0])}
    assert script.get_revision(module.down_revision) is not None
    source = (VERSIONS / "cust_group_0001.py").read_text(encoding="utf-8")
    assert "IF NOT EXISTS" in source


def test_upgrade_does_not_name_match_or_seed():
    module = _load()
    assert not hasattr(module, "seed")
    source = (VERSIONS / "cust_group_0001.py").read_text(encoding="utf-8")
    upgrade_body = source[source.index("def upgrade()") : source.index("def downgrade()")]
    assert "plan_groups" not in upgrade_body
    assert "UPDATE customers" not in upgrade_body
    assert "INSERT INTO customer_groups" not in upgrade_body


def _cust(db, name, level=None) -> str:
    row = Customer(
        id=str(uuid.uuid4()),
        customer_code=f"ZZT-{uuid.uuid4().hex[:8]}",
        customer_name=name,
        company_id=DEFAULT_COMPANY_ID,
        account_level=level,
    )
    db.add(row)
    db.flush()
    return row.id


def test_upgrade_creates_the_table_and_column_and_groups_no_customer():
    with blank_session() as db:
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        # A numbered family the old seed would have joined into one group.
        ids = [
            _cust(db, "HANLIM TRADING SDN BHD [A/C I]", 1),
            _cust(db, "HANLIM TRADING SDN BHD [A/C II]", 2),
            _cust(db, "HANLIM TRADING SDN BHD"),
        ]
        conn = db.connection()
        conn.execute(text("ALTER TABLE customers DROP COLUMN customer_group_id CASCADE"))
        conn.execute(text("DROP TABLE customer_groups CASCADE"))

        with Operations.context(MigrationContext.configure(conn)):
            _load().upgrade()

        schema = conn.execute(text("SELECT current_schema()")).scalar_one()
        assert conn.execute(
            text("SELECT to_regclass(:t)"), {"t": f'"{schema}".customer_groups'}
        ).scalar_one() is not None
        assert conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns WHERE table_schema = :s "
                "AND table_name = 'customers' AND column_name = 'customer_group_id'"
            ),
            {"s": schema},
        ).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM customer_groups")).scalar_one() == 0
        assert conn.execute(
            text(
                "SELECT count(*) FROM customers "
                "WHERE id = ANY(CAST(:ids AS uuid[])) AND customer_group_id IS NOT NULL"
            ),
            {"ids": ids},
        ).scalar_one() == 0
        assert conn.execute(
            text("SELECT count(*) FROM customers WHERE customer_group_id IS NOT NULL")
        ).scalar_one() == 0


# ============================================================ seed naming: shared bracketed runs


def _plan(names_levels, company=DEFAULT_COMPANY_ID):
    """`plan_groups` rows are (id, company_id, code, name, level, group_id); pure, no DB."""
    rows = [
        (str(uuid.uuid4()), company, f"ZZT-{i:02d}", name, level, None)
        for i, (name, level) in enumerate(names_levels)
    ]
    return [group_name for _c, group_name, _ids in _load().plan_groups(rows)]


def test_group_name_keeps_a_bracketed_run_every_member_shares():
    assert _plan([("SCR MARKETING (M) SDN BHD [A/C IV]", 4), ("SCR MARKETING (M) SDN BHD [A/C I]", 1)]) == [
        "SCR MARKETING (M) SDN BHD"
    ]
    assert _plan(
        [("CHENG HUAT HARDWARE (SENTUL) SDN BHD [A/C I]", 1), ("CHENG HUAT HARDWARE (SENTUL) SDN BHD [A/C II]", 2)]
    ) == ["CHENG HUAT HARDWARE (SENTUL) SDN BHD"]


def test_group_name_drops_a_bracketed_run_only_some_members_carry():
    hanlim = [
        ("HANLIM TRADING SDN BHD [A/C I]", 1),
        ("HANLIM TRADING SDN BHD [A/C II]", 2),
        ("HANLIM TRADING SDN BHD [A/C III]", 3),
        ("HANLIM TRADING SDN BHD [A/C IV]", 4),
        ("HANLIM TRADING SDN BHD", None),
        ("HANLIM TRADING SDN BHD (CERAMIC & ELLECI)", None),
    ]
    assert _plan(hanlim) == ["HANLIM TRADING SDN BHD"]
    jubin = [
        ("JUBIN BMS (NS) SDN BHD [A/C I]", 1),
        ("JUBIN BMS (KLANG) SDN BHD [A/C I]", 1),
        ("JUBIN BMS (1990) SDN BHD [A/C III]", 3),
        ("JUBIN BMS SDN BHD", None),
    ]
    assert _plan(jubin) == ["JUBIN BMS SDN BHD"]
