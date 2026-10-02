"""Lane CUSTOMER-GROUP, S1 red tests for the `cust_group_0001` seed (AC-2).

`seed(connection)` is a module-level function of ``alembic/versions/cust_group_0001.py``
(precedent: ``tests/test_migration_acct_ledger.py``, loaded by path). It runs on a blank
Postgres schema built from the models, so it also needs ``customer_groups`` and
``customers.customer_group_id`` to exist there. Every row is seeded here.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

from sqlalchemy import text

from app.models.order import Customer
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID

from ._mc_lookup_seed import MOCHA_ID, seed_mocha
from ._pg_fixture import blank_session

VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _load():
    path = VERSIONS / "cust_group_0001.py"
    assert path.exists(), "cust_group_0001.py does not exist"
    spec = importlib.util.spec_from_file_location("mig_cust_group_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cust(db, name, level=None, code=None, company_id=DEFAULT_COMPANY_ID) -> str:
    row = Customer(
        id=str(uuid.uuid4()),
        customer_code=code or f"ZZT-{uuid.uuid4().hex[:8]}",
        customer_name=name,
        company_id=company_id,
        account_level=level,
    )
    db.add(row)
    db.flush()
    return row.id


def _groups(db, company_id=DEFAULT_COMPANY_ID) -> dict[str, str]:
    rows = db.execute(
        text("SELECT id, name FROM customer_groups WHERE company_id = :c"), {"c": company_id}
    ).fetchall()
    return {name: str(gid) for gid, name in rows}


def _group_of(db, customer_id):
    value = db.execute(
        text("SELECT customer_group_id FROM customers WHERE id = :c"), {"c": customer_id}
    ).scalar_one()
    return str(value) if value is not None else None


def _run(db) -> None:
    _load().seed(db.connection())
    db.expire_all()


def test_revision_chain_and_additive():
    module = _load()
    assert module.revision == "cust_group_0001"
    assert module.down_revision == "grn_pull_0001_perm"
    source = (VERSIONS / "cust_group_0001.py").read_text(encoding="utf-8")
    assert "IF NOT EXISTS" in source


def test_numbered_family_becomes_one_group_with_every_member():
    with blank_session() as db:
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        a = _cust(db, "HANLIM TRADING SDN BHD [A/C I]", 1)
        b = _cust(db, "HANLIM TRADING SDN BHD [A/C II]", 2)
        c = _cust(db, "HANLIM TRADING SDN BHD")

        _run(db)

        groups = _groups(db)
        assert list(groups) == ["HANLIM TRADING SDN BHD"]
        assert {_group_of(db, i) for i in (a, b, c)} == {groups["HANLIM TRADING SDN BHD"]}


def test_unnumbered_and_single_row_families_get_no_group():
    with blank_session() as db:
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        cash1 = _cust(db, "CASH 1")
        cash2 = _cust(db, "CASH 2")
        solo = _cust(db, "SOLO TRADING SDN BHD [A/C I]", 1)

        _run(db)

        assert _groups(db) == {}
        assert [_group_of(db, i) for i in (cash1, cash2, solo)] == [None, None, None]


def test_a_row_already_in_a_group_is_not_moved_and_a_rerun_creates_nothing():
    with blank_session() as db:
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        mine = str(uuid.uuid4())
        db.execute(
            text(
                "INSERT INTO customer_groups (id, company_id, name, created_at, updated_at) "
                "VALUES (:i, :c, 'ZZT HAND MADE', now(), now())"
            ),
            {"i": mine, "c": DEFAULT_COMPANY_ID},
        )
        grouped = _cust(db, "PRE SET SDN BHD [A/C I]", 1)
        db.execute(text("UPDATE customers SET customer_group_id = :g WHERE id = :c"), {"g": mine, "c": grouped})
        _cust(db, "PRE SET SDN BHD [A/C II]", 2)

        _run(db)
        assert _group_of(db, grouped) == mine

        _cust(db, "OTHER FAMILY SDN BHD [A/C I]", 1)
        _cust(db, "OTHER FAMILY SDN BHD [A/C II]", 2)
        _run(db)
        before = db.execute(text("SELECT count(*) FROM customer_groups")).scalar_one()
        _run(db)
        after = db.execute(text("SELECT count(*) FROM customer_groups")).scalar_one()
        assert before == after
        assert _group_of(db, grouped) == mine


def test_name_is_the_label_of_the_lowest_level_member_ties_by_lowest_code():
    with blank_session() as db:
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        _cust(db, "Zed Sdn Bhd [A/C II]", 2, code="ZZT-A")
        _cust(db, "ZED SDN BHD [A/C I]", 1, code="ZZT-B")
        _cust(db, "Quo Sdn Bhd [A/C I]", 1, code="ZZT-D")
        _cust(db, "QUO SDN BHD [A/C I]", 1, code="ZZT-C")

        _run(db)

        assert sorted(_groups(db)) == ["QUO SDN BHD", "ZED SDN BHD"]


def test_the_same_family_in_two_companies_is_two_groups():
    with blank_session() as db:
        seed_mocha(db)
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
        for company in (DEFAULT_COMPANY_ID, MOCHA_ID):
            _cust(db, "TWIN SDN BHD [A/C I]", 1, company_id=company)
            _cust(db, "TWIN SDN BHD [A/C II]", 2, company_id=company)

        _run(db)

        assert list(_groups(db, DEFAULT_COMPANY_ID)) == ["TWIN SDN BHD"]
        assert list(_groups(db, MOCHA_ID)) == ["TWIN SDN BHD"]
        assert _groups(db, DEFAULT_COMPANY_ID)["TWIN SDN BHD"] != _groups(db, MOCHA_ID)["TWIN SDN BHD"]
