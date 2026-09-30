"""AC-13/14/15 - the duplicate-code merge, tested by running the migration on a
scratch schema built in the PRE-migration shape (pair index, no `name_aliases`).

Survivor per code per company: the row holding the integration reference, else
the one with the most orders (`orders` + `sales_orders`), else the oldest. Every
FK is repointed (discovered from `pg_constraint`, as migration 220 did), a child
row that would collide with one the survivor already holds is dropped, a loser's
`main` contact steps down to `stakeholder` when the survivor has a `main`, the
losers' names become the survivor's aliases, and the losers are deleted.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests._pg_fixture import blank_session, unique_code

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "cci_0001_customer_code_identity.py"
)


def _run_upgrade(db):
    spec = importlib.util.spec_from_file_location("m_cci_0001", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.upgrade()


def _pre_migration_shape(db) -> None:
    """Undo what ``Base.metadata.create_all`` already emitted from the model."""
    db.execute(text("DROP INDEX IF EXISTS uq_customers_company_code_lower"))
    db.execute(text("ALTER TABLE customers DROP COLUMN IF EXISTS name_aliases"))
    db.execute(
        text(
            "CREATE UNIQUE INDEX uq_customers_company_code_name_lower ON customers "
            "(company_id, lower(btrim(customer_code)), lower(btrim(customer_name)))"
        )
    )


def _company(db) -> str:
    cid = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO companies (id, name, code) VALUES (:i, :n, :c)"),
        {"i": cid, "n": f"ZZT {cid[:8]}", "c": unique_code("CO")[:20]},
    )
    return cid


def _customer(db, company_id: str, code: str, name: str, *, days_old: int) -> str:
    cid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO customers (id, company_id, customer_code, customer_name, is_active, "
            "customer_type, created_at) VALUES (:i, :cid, :code, :name, true, 'company', "
            "now() - make_interval(days => :d))"
        ),
        {"i": cid, "cid": company_id, "code": code, "name": name, "d": days_old},
    )
    return cid


def _ref(db, company_id: str, customer_id: str, source_ref: str) -> None:
    db.execute(
        text(
            "INSERT INTO integration_references (id, entity_type, entity_id, company_id, "
            "source_system, source_ref) VALUES (:i, 'customers', :e, :cid, 'autocount', :r)"
        ),
        {"i": str(uuid.uuid4()), "e": customer_id, "cid": company_id, "r": source_ref},
    )


def _order(db, company_id: str, customer_id: str) -> str:
    oid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO orders (id, company_id, order_number, customer_id, is_cancelled, "
            "kpi_warning, subtotal_amount, discount_amount, tax_amount, total_amount, "
            "synced_to_excel) VALUES (:i, :cid, :n, :c, false, false, 0, 0, 0, 0, false)"
        ),
        {"i": oid, "cid": company_id, "n": unique_code("DO"), "c": customer_id},
    )
    return oid


def _sales_order(db, company_id: str, customer_id: str) -> str:
    sid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO sales_orders (id, company_id, so_number, status, customer_id) "
            "VALUES (:i, :cid, :n, 'open', :c)"
        ),
        {"i": sid, "cid": company_id, "n": unique_code("SO"), "c": customer_id},
    )
    return sid


def _contact(db, company_id: str, customer_id: str, name: str, role: str) -> str:
    pid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO customer_contacts (id, company_id, customer_id, full_name, sync_source, "
            "contact_role, sort_order) VALUES (:i, :cid, :c, :n, 'manual', :r, 0)"
        ),
        {"i": pid, "cid": company_id, "c": customer_id, "n": name, "r": role},
    )
    return pid


def _respond_contact(db) -> str:
    rid = f"ZZT-{uuid.uuid4().hex[:10]}"
    db.execute(
        text("INSERT INTO respond_contacts (id, phone_number) VALUES (:i, :p)"),
        {"i": rid, "p": f"+60{uuid.uuid4().int % 10**9:09d}"},
    )
    return rid


def _link(db, company_id: str, contact_id: str, customer_id: str, *, primary: bool) -> str:
    lid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO respond_contact_customers (id, company_id, contact_id, customer_id, "
            "is_primary, source) VALUES (:i, :cid, :ct, :cu, :p, 'manual')"
        ),
        {"i": lid, "cid": company_id, "ct": contact_id, "cu": customer_id, "p": primary},
    )
    return lid


def _customer_row(db, customer_id: str):
    return (
        db.execute(
            text("SELECT customer_name, name_aliases FROM customers WHERE id = :i"),
            {"i": customer_id},
        )
        .mappings()
        .first()
    )


def _scalar(db, sql: str, **params):
    return db.execute(text(sql), params).scalar()


def test_duplicate_codes_merge_onto_one_survivor_per_company():
    with blank_session() as db:
        _pre_migration_shape(db)
        company = _company(db)
        other_company = _company(db)

        # Code 1: ref holder wins even though a sibling has more orders.
        code1 = unique_code("300")
        a = _customer(db, company, code1, "1 LIVING DEPOT SDN BHD", days_old=30)
        b = _customer(db, company, code1, "1 LIVING DEPOT SDN BHD [A/C I]", days_old=20)
        c = _customer(db, company, code1, "MODERNMED SDN BHD", days_old=10)
        _ref(db, company, a, "AED_SORENTO:2613")
        # A second ref on a loser (an AccNo one) goes with the loser.
        _ref(db, company, b, "AED_SORENTO:300-1001")
        # Fill-only: the survivor has no email; the oldest loser's wins, the
        # survivor's own phone stays.
        db.execute(
            text("UPDATE customers SET phone_number = '03-000' WHERE id = :a"), {"a": a}
        )
        db.execute(
            text("UPDATE customers SET email = 'b@x.my', phone_number = '03-111' WHERE id = :b"),
            {"b": b},
        )
        db.execute(text("UPDATE customers SET email = 'c@x.my' WHERE id = :c"), {"c": c})
        b_orders = {_order(db, company, b), _order(db, company, b)}
        c_so = _sales_order(db, company, c)
        alice = _contact(db, company, a, "Alice", "main")
        bob = _contact(db, company, b, "Bob", "main")
        cathy = _contact(db, company, c, "Cathy", "stakeholder")
        p1, p2 = _respond_contact(db), _respond_contact(db)
        _link(db, company, p2, a, primary=False)
        _link(db, company, p1, b, primary=True)
        b_p2 = _link(db, company, p2, b, primary=False)
        # The same code in ANOTHER company is a different customer and stays.
        theirs = _customer(db, other_company, code1, "THEIR 300", days_old=5)

        # Code 2: no ref; most orders (orders + sales_orders) wins over oldest.
        code2 = unique_code("300")
        d = _customer(db, company, code2, "D OLDEST", days_old=40)
        e = _customer(db, company, code2, "E BUSIEST", days_old=1)
        d_order = _order(db, company, d)
        _sales_order(db, company, e)
        _sales_order(db, company, e)

        # Code 3: nothing to choose on; the oldest survives. Case/space variant.
        # The survivor has no main contact and TWO losers do: the oldest loser's
        # main moves over as main, the other steps down.
        code3 = unique_code("300")
        f = _customer(db, company, code3, "F OLDEST", days_old=9)
        g = _customer(db, company, f"  {code3.lower()} ", "G NEWER", days_old=2)
        g2 = _customer(db, company, code3.upper(), "G2 NEWEST", days_old=1)
        gina = _contact(db, company, g, "Gina", "main")
        gus = _contact(db, company, g2, "Gus", "main")

        # Code 4: a single row is left alone.
        code4 = unique_code("300")
        h = _customer(db, company, code4, "H ALONE", days_old=3)
        # Search embeddings the ORM listener wrote for the losers must go with them.
        for loser in (g, g2):
            db.execute(
                text(
                    "INSERT INTO embedding_documents (id, source_type, source_id, body_text, "
                    "source_hash, is_active) VALUES (:i, 'customer', :s, 'x', :h, true)"
                ),
                {"i": str(uuid.uuid4()), "s": loser, "h": uuid.uuid4().hex},
            )
        db.flush()

        _run_upgrade(db)

        # --- code 1
        survivors = db.execute(
            text(
                "SELECT id FROM customers WHERE lower(btrim(customer_code)) = lower(btrim(:c)) "
                "AND company_id = :cid"
            ),
            {"c": code1, "cid": company},
        ).scalars().all()
        assert [str(s) for s in survivors] == [a]
        row = _customer_row(db, a)
        assert row["customer_name"] == "1 LIVING DEPOT SDN BHD"
        assert row["name_aliases"] == ["1 LIVING DEPOT SDN BHD [A/C I]", "MODERNMED SDN BHD"]
        filled = db.execute(
            text("SELECT email, phone_number FROM customers WHERE id = :a"), {"a": a}
        ).first()
        assert tuple(filled) == ("b@x.my", "03-000")
        assert _scalar(db, "SELECT count(*) FROM customers WHERE id IN (:b, :c)", b=b, c=c) == 0
        assert _scalar(db, "SELECT count(*) FROM customers WHERE id = :t", t=theirs) == 1

        repointed = set(
            str(x)
            for x in db.execute(
                text("SELECT id FROM orders WHERE customer_id = :a"), {"a": a}
            ).scalars()
        )
        assert repointed == b_orders
        assert str(_scalar(db, "SELECT customer_id FROM sales_orders WHERE id = :s", s=c_so)) == a

        contacts = db.execute(
            text(
                "SELECT id, contact_role FROM customer_contacts WHERE customer_id = :a "
                "ORDER BY full_name"
            ),
            {"a": a},
        ).all()
        assert [(str(i), r) for i, r in contacts] == [
            (alice, "main"),
            (bob, "stakeholder"),
            (cathy, "stakeholder"),
        ]

        links = db.execute(
            text(
                "SELECT contact_id, is_primary FROM respond_contact_customers "
                "WHERE customer_id = :a ORDER BY contact_id"
            ),
            {"a": a},
        ).all()
        assert sorted(links) == sorted([(p1, True), (p2, False)])
        assert _scalar(db, "SELECT count(*) FROM respond_contact_customers WHERE id = :l", l=b_p2) == 0
        assert _scalar(
            db, "SELECT count(*) FROM respond_contact_customers WHERE customer_id IN (:b, :c)", b=b, c=c
        ) == 0

        refs = db.execute(
            text(
                "SELECT entity_id, source_ref FROM integration_references "
                "WHERE entity_type = 'customers' AND company_id = :cid"
            ),
            {"cid": company},
        ).all()
        assert [(str(i), r) for i, r in refs] == [(a, "AED_SORENTO:2613")]

        # --- code 2
        assert _scalar(db, "SELECT count(*) FROM customers WHERE id = :d", d=d) == 0
        assert str(_scalar(db, "SELECT customer_id FROM orders WHERE id = :o", o=d_order)) == e
        assert _customer_row(db, e)["name_aliases"] == ["D OLDEST"]

        # --- code 3
        assert _scalar(db, "SELECT count(*) FROM customers WHERE id IN (:g, :g2)", g=g, g2=g2) == 0
        assert _customer_row(db, f)["name_aliases"] == ["G NEWER", "G2 NEWEST"]
        moved = db.execute(
            text(
                "SELECT id, contact_role FROM customer_contacts WHERE customer_id = :f "
                "ORDER BY full_name"
            ),
            {"f": f},
        ).all()
        assert [(str(i), r) for i, r in moved] == [(gina, "main"), (gus, "stakeholder")]
        assert _scalar(db, "SELECT count(*) FROM embedding_documents WHERE source_id IN (:g, :g2)", g=g, g2=g2) == 0

        # --- code 4
        assert _customer_row(db, h) == {"customer_name": "H ALONE", "name_aliases": []}

        # --- the index swap
        names = set(
            db.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'customers' AND schemaname = current_schema()"
                )
            ).scalars()
        )
        assert "uq_customers_company_code_lower" in names
        assert "uq_customers_company_code_name_lower" not in names


def test_upgrade_is_idempotent_on_a_clean_table():
    with blank_session() as db:
        _pre_migration_shape(db)
        company = _company(db)
        only = _customer(db, company, unique_code("300"), "ONLY", days_old=1)
        db.flush()
        _run_upgrade(db)
        _run_upgrade(db)
        assert _customer_row(db, only) == {"customer_name": "ONLY", "name_aliases": []}
