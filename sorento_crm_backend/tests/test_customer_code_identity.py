"""CUSTOMER-CODE-IDENTITY - within a company the debtor code identifies the
customer; names are labels (owner decision, 30 Sep 2026).

UAC: documentation/plans/master-data/customer-code-identity-acceptance-criteria.md

  AC-01  a document naming a known code with a different name lands on the
         existing row, creates nothing, keeps the master name, records an alias
  AC-02  a code nobody holds is back-created once; the next name lands on it
  AC-03  legacy duplicates: the row holding the integration ref wins, warning
         `customer_ambiguous`
  AC-04  legacy duplicates, no ref: the row with orders wins, same warning
  AC-05  `customer_ambiguous` is in the published vocabulary
  AC-06  `customer_back_create.get_or_create` matches by code alone
  AC-08  the masters push adopts by code alone, renames, keeps the old name
  AC-11  manual create refuses a held code whatever the name
  AC-12  the unique index is (company, lower(btrim(code)))
  plus the CUSTOMER-KEY-AUTOKEY fold-in: a code-adopted customer already
  holding a different-source AutoKey ref updates, keeps its stored ref, warns
  `ref_mismatch` and never links the AccNo ref (mirrors the products rule).

Every test seeds its own chain on the blank scratch schema (`tests._pg_fixture`).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.integration_reference import IntegrationReference
from app.models.order import Customer, SalesOrder
from app.schemas.order import CustomerCreate, CustomerResponse
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.error_handler import AppException
from app.services.integration_reference_service import IntegrationReferenceService
from app.services.master_ingest_service import MasterIngestService
from app.services.order_service import CustomerService
from app.services.rules import customer_rules
from app.services.scm import customer_back_create

from tests._pg_fixture import blank_session, unique_code
from tests.test_ingest_documents import (
    INGEST_SO,
    MARKER,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)

__all__ = ["env"]


def _customer(db, company_id: str, *, code: str, name: str) -> Customer:
    row = Customer(customer_code=code, customer_name=name, company_id=company_id)
    db.add(row)
    db.flush()
    return row


def _allow_legacy_duplicates(db) -> None:
    """The scratch schema is built from the model, so it already carries
    `uq_customers_company_code_lower`; a test about the rows that predate the
    merge migration has to take the index off first (DDL inside the rolled-back
    transaction, gone with the schema)."""
    db.execute(text("DROP INDEX IF EXISTS uq_customers_company_code_lower"))


def _rows_for_code(db, code: str, company_id: str) -> list:
    return (
        db.execute(
            text(
                "SELECT id, customer_name, name_aliases FROM customers "
                "WHERE upper(btrim(customer_code)) = upper(btrim(:c)) AND company_id = :cid "
                "ORDER BY created_at, id"
            ),
            {"c": code, "cid": company_id},
        )
        .mappings()
        .all()
    )


# ================================================== document ingest (AC-01..04)
class TestDocumentIngestResolvesByCode:
    def test_a_changed_debtor_name_lands_on_the_code_holder_and_stays_on_the_order(self, env):
        """AC-01: 300-1001 pushed as "MODERNMED SDN BHD" is still 300-1001. The
        name the SO was issued under is stored on the SO (`sales_orders.debtor_name`,
        owner decision); the master name is never written from a document."""
        code = unique_code(MARKER)
        stored = _customer(env.db, env.company_a, code=code, name="1 LIVING DEPOT SDN BHD")

        res = env.post(
            INGEST_SO, [_so_record(env, customer_code=code, customer_name="MODERNMED SDN BHD")]
        )

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert "customer_created" not in entry.get("warnings", []), entry
        header = env.header("sales_orders", entry["source_ref"])
        assert str(header["customer_id"]) == str(stored.id)
        assert header["debtor_name"] == "MODERNMED SDN BHD"

        rows = _rows_for_code(env.db, code, env.company_a)
        assert len(rows) == 1, rows
        assert rows[0]["customer_name"] == "1 LIVING DEPOT SDN BHD", "a document never renames"
        assert rows[0]["name_aliases"] == [], "a document name is not a master alias"

    def test_a_re_push_with_a_new_name_updates_the_order_name_only(self, env):
        code = unique_code(MARKER)
        _customer(env.db, env.company_a, code=code, name="ALPHA SDN BHD")
        ref = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"

        for name in ("Beta Sdn Bhd", "  Gamma Sdn Bhd "):
            res = env.post(
                INGEST_SO, [_so_record(env, ref=ref, customer_code=code, customer_name=name)]
            )
            assert res.status_code == 200, res.text

        header = env.header("sales_orders", ref)
        assert header["debtor_name"] == "Gamma Sdn Bhd"
        rows = _rows_for_code(env.db, code, env.company_a)
        assert len(rows) == 1
        assert rows[0]["customer_name"] == "ALPHA SDN BHD"
        assert rows[0]["name_aliases"] == []

    def test_a_push_without_a_name_leaves_the_stored_order_name_alone(self, env):
        code = unique_code(MARKER)
        _customer(env.db, env.company_a, code=code, name="ALPHA SDN BHD")
        ref = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
        env.post(INGEST_SO, [_so_record(env, ref=ref, customer_code=code, customer_name="Beta")])
        env.post(INGEST_SO, [_so_record(env, ref=ref, customer_code=code)])
        assert env.header("sales_orders", ref)["debtor_name"] == "Beta"

    def test_an_unknown_code_is_back_created_once_and_the_next_name_lands_on_it(self, env):
        """AC-02."""
        code = unique_code(MARKER)
        first = env.post(INGEST_SO, [_so_record(env, customer_code=code, customer_name="FIRST NAME")])
        assert first.status_code == 200, first.text
        assert "customer_created" in first.json()["records"][0].get("warnings", [])

        second = env.post(
            INGEST_SO, [_so_record(env, customer_code=code, customer_name="SECOND NAME")]
        )
        assert second.status_code == 200, second.text
        entry = second.json()["records"][0]
        assert "customer_created" not in entry.get("warnings", []), entry

        rows = _rows_for_code(env.db, code, env.company_a)
        assert len(rows) == 1, rows
        assert rows[0]["customer_name"] == "FIRST NAME"
        assert rows[0]["name_aliases"] == []
        first_header = env.header("sales_orders", first.json()["records"][0]["source_ref"])
        second_header = env.header("sales_orders", entry["source_ref"])
        assert str(first_header["customer_id"]) == str(second_header["customer_id"]) == str(rows[0]["id"])
        assert (first_header["debtor_name"], second_header["debtor_name"]) == ("FIRST NAME", "SECOND NAME")

    def test_legacy_duplicates_resolve_to_the_row_holding_the_ref_and_warn(self, env):
        """AC-03. Two rows share the code (seeded straight into the table, the way
        the pre-merge database holds them); the one the integration knows wins."""
        _allow_legacy_duplicates(env.db)
        code = unique_code(MARKER)
        alpha = _customer(env.db, env.company_a, code=code, name="ALPHA")
        beta = _customer(env.db, env.company_a, code=code, name="BETA")
        env.refs.link(entity_type="customers", entity_id=str(beta.id), source_ref=f"DEBTOR-{code}")

        res = env.post(INGEST_SO, [_so_record(env, customer_code=code)])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert "customer_ambiguous" in entry.get("warnings", []), entry
        assert "customer_created" not in entry.get("warnings", []), entry
        header = env.header("sales_orders", entry["source_ref"])
        assert str(header["customer_id"]) == str(beta.id)
        assert str(header["customer_id"]) != str(alpha.id)

    def test_legacy_duplicates_without_a_ref_resolve_to_the_row_with_orders_and_warn(self, env):
        """AC-04."""
        _allow_legacy_duplicates(env.db)
        code = unique_code(MARKER)
        alpha = _customer(env.db, env.company_a, code=code, name="ALPHA")
        beta = _customer(env.db, env.company_a, code=code, name="BETA")
        env.db.add(
            SalesOrder(
                so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
                status="open",
                customer_id=str(beta.id),
                company_id=env.company_a,
            )
        )
        env.db.flush()

        res = env.post(INGEST_SO, [_so_record(env, customer_code=code, customer_name="GAMMA")])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert "customer_ambiguous" in entry.get("warnings", []), entry
        header = env.header("sales_orders", entry["source_ref"])
        assert str(header["customer_id"]) == str(beta.id)
        assert str(header["customer_id"]) != str(alpha.id)
        # No third row was created for the new name.
        assert len(_rows_for_code(env.db, code, env.company_a)) == 2

    def test_the_vocabulary_publishes_customer_ambiguous(self, env):
        """AC-05."""
        from app.api.v1.external.contract import WARNINGS

        assert "customer_ambiguous" in WARNINGS
        res = env.client.get("/api/v1/external/contract")
        assert res.status_code == 200, res.text
        assert "customer_ambiguous" in res.json()["warnings"]


# ============================================== back-create + picker (AC-06)
@pytest.fixture()
def db():
    register_company_scope_listeners()
    with blank_session() as session:
        yield session


@pytest.fixture()
def company_b(db) -> str:
    company = Company(id=str(uuid.uuid4()), name=f"{MARKER} B", code=unique_code(MARKER)[:10])
    db.add(company)
    db.flush()
    return str(company.id)


class TestBackCreateByCode:
    def test_get_or_create_returns_the_code_holder_whatever_the_name(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = unique_code(MARKER)
        stored = _customer(db, DEFAULT_COMPANY_ID, code=code, name="ALPHA")

        found = customer_back_create.get_or_create(
            db, code=f"  {code.lower()} ", name="Beta", company_id=DEFAULT_COMPANY_ID
        )

        assert found is not None and str(found.id) == str(stored.id)
        assert db.query(Customer).filter(Customer.customer_code.ilike(code)).count() == 1
        assert found.customer_name == "ALPHA"
        assert found.name_aliases == [], "a document name never touches the master"

    def test_get_or_create_never_matches_another_company(self, db, company_b):
        set_company_scope(db, None)
        code = unique_code(MARKER)
        _customer(db, company_b, code=code, name="THEIRS")

        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        created = customer_back_create.get_or_create(
            db, code=code, name="OURS", company_id=DEFAULT_COMPANY_ID
        )

        assert created is not None
        assert str(created.company_id) == DEFAULT_COMPANY_ID
        assert created.customer_name == "OURS"
        assert created.name_aliases == []

    def test_picker_prefers_ref_then_orders_then_oldest(self, db):
        _allow_legacy_duplicates(db)
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = unique_code(MARKER)
        oldest = _customer(db, DEFAULT_COMPANY_ID, code=code, name="OLDEST")
        with_orders = _customer(db, DEFAULT_COMPANY_ID, code=code, name="ORDERS")
        with_ref = _customer(db, DEFAULT_COMPANY_ID, code=code, name="REF")
        db.execute(
            text(
                "UPDATE customers SET created_at = created_at - interval '1 day' WHERE id = :i"
            ),
            {"i": str(oldest.id)},
        )
        db.add(
            SalesOrder(
                so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
                status="open",
                customer_id=str(with_orders.id),
                company_id=DEFAULT_COMPANY_ID,
            )
        )
        db.flush()

        picked, ambiguous = customer_rules.pick_customer_by_code(db, code, DEFAULT_COMPANY_ID)
        assert (picked, ambiguous) == (str(with_orders.id), True)

        IntegrationReferenceService(db, company_id=DEFAULT_COMPANY_ID).link(
            entity_type="customers", entity_id=str(with_ref.id), source_ref=f"DEBTOR-{code}"
        )
        picked, ambiguous = customer_rules.pick_customer_by_code(db, code, DEFAULT_COMPANY_ID)
        assert (picked, ambiguous) == (str(with_ref.id), True)

        db.execute(
            text("DELETE FROM integration_references WHERE entity_id = :i"), {"i": str(with_ref.id)}
        )
        db.execute(text("DELETE FROM sales_orders WHERE customer_id = :i"), {"i": str(with_orders.id)})
        picked, ambiguous = customer_rules.pick_customer_by_code(db, code, DEFAULT_COMPANY_ID)
        assert (picked, ambiguous) == (str(oldest.id), True)

    def test_picker_is_unambiguous_for_a_single_row_and_none_for_no_row(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = unique_code(MARKER)
        assert customer_rules.pick_customer_by_code(db, code, DEFAULT_COMPANY_ID) == (None, False)
        only = _customer(db, DEFAULT_COMPANY_ID, code=code, name="ONLY")
        assert customer_rules.pick_customer_by_code(db, f" {code.lower()} ", DEFAULT_COMPANY_ID) == (
            str(only.id),
            False,
        )


# ======================================================= masters push (AC-08)
def _esb(db, company_id: str) -> MasterIngestService:
    return MasterIngestService(db, integration_id=None, company_id=company_id)


class TestMastersPushAdoptsByCode:
    def test_a_new_name_under_a_known_code_renames_and_keeps_the_old_name(self, db):
        """AC-08: the masters push IS AutoCount's debtor master, so it owns the name."""
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = unique_code(MARKER)[:30]
        alpha = _customer(db, DEFAULT_COMPANY_ID, code=code, name="ALPHA")
        ref = f"DK-{code}"

        result = _esb(db, DEFAULT_COMPANY_ID).ingest(
            "customers", [{"source_ref": ref, "code": code, "name": "BETA", "email": "b@new.com"}]
        )

        assert (result.created, result.updated) == (0, 1), result.records[0].errors
        rows = _rows_for_code(db, code, DEFAULT_COMPANY_ID)
        assert len(rows) == 1, rows
        assert str(rows[0]["id"]) == str(alpha.id)
        assert rows[0]["customer_name"] == "BETA"
        assert rows[0]["name_aliases"] == ["ALPHA"]
        linked = (
            db.query(IntegrationReference).filter_by(entity_type="customers", source_ref=ref).one()
        )
        assert str(linked.entity_id) == str(alpha.id)

    def test_a_ref_hit_that_renames_keeps_the_old_name_too(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = unique_code(MARKER)[:30]
        ref = f"DK-{code}"
        svc = _esb(db, DEFAULT_COMPANY_ID)
        svc.ingest("customers", [{"source_ref": ref, "code": code, "name": "V1"}])
        svc.ingest("customers", [{"source_ref": ref, "code": code, "name": "V2"}])
        svc.ingest("customers", [{"source_ref": ref, "code": code, "name": "V2"}])

        rows = _rows_for_code(db, code, DEFAULT_COMPANY_ID)
        assert len(rows) == 1
        assert rows[0]["customer_name"] == "V2"
        assert rows[0]["name_aliases"] == ["V1"]

    def test_code_adopted_customer_holding_an_autokey_ref_updates_keeps_it_and_warns(self, db):
        """CUSTOMER-KEY-AUTOKEY (a): the wrapper's /debtorbypage exposes no AutoKey,
        so the Customer entity keys on AccNo (`AED_SORENTO:300-1003`) while the
        SO/PO feeds already linked the row under `AED_SORENTO:2613`. Code wins:
        update, keep the stored ref, `ref_mismatch`, never link the AccNo ref."""
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = unique_code(MARKER)[:30]
        row = _customer(db, DEFAULT_COMPANY_ID, code=code, name="OLD NAME")
        stored_ref = f"AED_SORENTO:{uuid.uuid4().int % 10000}"
        IntegrationReferenceService(db, company_id=DEFAULT_COMPANY_ID).link(
            entity_type="customers", entity_id=str(row.id), source_ref=stored_ref
        )
        accno_ref = f"AED_SORENTO:{code}"

        result = _esb(db, DEFAULT_COMPANY_ID).ingest(
            "customers",
            [{"source_ref": accno_ref, "code": code, "name": "NEW NAME", "email": "n@x.com"}],
        )

        record = result.records[0]
        assert (result.created, result.updated) == (0, 1), record.errors
        assert str(record.entity_id) == str(row.id)
        assert "ref_mismatch" in record.warnings, record

        refs = (
            db.query(IntegrationReference.source_ref)
            .filter_by(entity_type="customers", entity_id=str(row.id))
            .all()
        )
        assert [r[0] for r in refs] == [stored_ref]
        assert (
            db.query(IntegrationReference).filter_by(entity_type="customers", source_ref=accno_ref).first()
            is None
        ), "the AccNo ref is never linked"
        rows = _rows_for_code(db, code, DEFAULT_COMPANY_ID)
        assert rows[0]["customer_name"] == "NEW NAME"
        assert rows[0]["name_aliases"] == ["OLD NAME"]

    def test_code_adopted_customer_held_by_another_source_system_still_conflicts(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = unique_code(MARKER)[:30]
        row = _customer(db, DEFAULT_COMPANY_ID, code=code, name="OLD NAME")
        IntegrationReferenceService(db, company_id=DEFAULT_COMPANY_ID).link(
            entity_type="customers",
            entity_id=str(row.id),
            source_ref=f"SAGE-{code}",
            source_system="sage",
        )

        result = _esb(db, DEFAULT_COMPANY_ID).ingest(
            "customers", [{"source_ref": f"AED_SORENTO:{code}", "code": code, "name": "NEW NAME"}]
        )

        assert (result.created, result.updated) == (0, 0)
        assert result.records[0].errors, result.records[0]
        assert _rows_for_code(db, code, DEFAULT_COMPANY_ID)[0]["customer_name"] == "OLD NAME"


# ================================================== manual create (AC-11)
class TestManualCreateByCode:
    def test_create_refuses_a_held_code_whatever_the_name(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = unique_code(MARKER)
        _customer(db, DEFAULT_COMPANY_ID, code=code, name="ALPHA")

        with pytest.raises(AppException) as exc:
            CustomerService(db).create_customer(
                CustomerCreate(customer_code=f" {code.lower()} ", customer_name="BETA")
            )
        assert exc.value.status_code == 409

    def test_a_manual_rename_keeps_the_old_name_as_an_alias(self, db):
        from app.schemas.order import CustomerUpdate

        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        row = _customer(db, DEFAULT_COMPANY_ID, code=unique_code(MARKER), name="OLD NAME")
        svc = CustomerService(db)
        svc.update_customer(str(row.id), CustomerUpdate(customer_name="NEW NAME"))
        svc.update_customer(str(row.id), CustomerUpdate(customer_name="new name "))
        svc.update_customer(str(row.id), CustomerUpdate(email="x@y.z"))
        db.refresh(row)
        assert row.customer_name == "new name "
        assert row.name_aliases == ["OLD NAME"]

    def test_create_accepts_the_same_code_in_another_company(self, db, company_b):
        set_company_scope(db, None)
        code = unique_code(MARKER)
        _customer(db, company_b, code=code, name="THEIRS")

        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        created = CustomerService(db).create_customer(
            CustomerCreate(customer_code=code, customer_name="OURS")
        )
        assert str(created.company_id) == DEFAULT_COMPANY_ID


# ============================================ SO screens (AC-19/20, D8 S1)
class TestSoScreensShowTheOrderName:
    """The order's own `debtor_name` first, the master name for an order that carries
    none, the debtor code for one nobody holds."""

    def _so(self, db, *, customer_id, debtor_name=None, debtor_code=None):
        so = SalesOrder(
            so_number=unique_code("SO"),
            status="open",
            customer_id=customer_id,
            debtor_name=debtor_name,
            debtor_code=debtor_code,
            company_id=DEFAULT_COMPANY_ID,
        )
        db.add(so)
        db.flush()
        return so

    def test_the_scm_serializer_prefers_the_order_name(self, db):
        from app.services.scm.sales_order_service import SalesOrderService

        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        master = _customer(db, DEFAULT_COMPANY_ID, code=unique_code(MARKER), name="MASTER NAME")
        with_own = self._so(db, customer_id=str(master.id), debtor_name="ORDER NAME")
        without = self._so(db, customer_id=str(master.id), debtor_name="  ")

        svc = SalesOrderService(db)
        assert svc.serialize(with_own)["customer_name"] == "ORDER NAME"
        assert svc.serialize(without)["customer_name"] == "MASTER NAME"

    def test_the_scm_list_search_matches_the_order_name(self, db):
        from app.services.scm.sales_order_service import SalesOrderService

        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        master = _customer(db, DEFAULT_COMPANY_ID, code=unique_code(MARKER), name="MASTER NAME")
        needle = f"ZZTNEEDLE{uuid.uuid4().hex[:6]}"
        so = self._so(db, customer_id=str(master.id), debtor_name=f"{needle} Sdn Bhd")

        result = SalesOrderService(db).list(
            page=1, limit=20, sort=None, direction="asc", query=needle, status=None, priority=None
        )
        assert result["pagination"]["total"] == 1
        assert result["data"][0]["id"] == so.id
        assert result["data"][0]["customer_name"] == f"{needle} Sdn Bhd"

    def test_the_shared_sql_label_prefers_the_order_name(self, db):
        from app.services.scm.customer_label import CUSTOMER_JOIN_ON, CUSTOMER_LABEL_SQL

        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        master = _customer(db, DEFAULT_COMPANY_ID, code=unique_code(MARKER), name="MASTER NAME")
        with_own = self._so(db, customer_id=str(master.id), debtor_name="ORDER NAME")
        without = self._so(db, customer_id=str(master.id))
        nobody = self._so(db, customer_id=None, debtor_code="300-ZZT9")

        def label(so_id: str) -> str:
            return db.execute(
                text(
                    f"SELECT {CUSTOMER_LABEL_SQL} FROM sales_orders so "
                    f"LEFT JOIN customers c ON {CUSTOMER_JOIN_ON} WHERE so.id = :id"
                ),
                {"id": so_id},
            ).scalar()

        assert label(with_own.id) == "ORDER NAME"
        assert label(without.id) == "MASTER NAME"
        assert label(nobody.id) == "Debtor 300-ZZT9"

    def test_so_outstanding_rows_prefer_the_order_name(self, db):
        from app.models.order import SalesOrderLine
        from app.services.order_service import so_outstanding_rows
        from tests._mc_lookup_seed import product

        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        master = _customer(db, DEFAULT_COMPANY_ID, code=unique_code(MARKER), name="MASTER NAME")
        prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("P")[:30])
        for name in ("ORDER NAME", None):
            so = self._so(db, customer_id=str(master.id), debtor_name=name)
            db.add(
                SalesOrderLine(
                    sales_order_id=so.id,
                    product_id=prod.id,
                    qty_ordered=5,
                    qty_delivered=1,
                    line_status="open",
                    company_id=DEFAULT_COMPANY_ID,
                )
            )
        db.flush()

        rows = so_outstanding_rows(db, customer_ids=[str(master.id)])
        assert sorted(r["customer"] for r in rows) == ["MASTER NAME", "ORDER NAME"]


# ============================================== schema + response (AC-12)
class TestSchema:
    def test_two_rows_with_one_code_in_one_company_are_refused(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = unique_code(MARKER)
        _customer(db, DEFAULT_COMPANY_ID, code=code, name="ALPHA")
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                _customer(db, DEFAULT_COMPANY_ID, code=f" {code.lower()} ", name="BETA")

    def test_the_same_code_may_exist_once_per_company(self, db, company_b):
        set_company_scope(db, None)
        code = unique_code(MARKER)
        _customer(db, DEFAULT_COMPANY_ID, code=code, name="OURS")
        _customer(db, company_b, code=code, name="THEIRS")
        assert db.query(Customer).filter(Customer.customer_code == code).count() == 2

    def test_the_live_index_is_on_company_and_code_alone(self, db):
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

    def test_the_response_carries_the_aliases(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        row = _customer(db, DEFAULT_COMPANY_ID, code=unique_code(MARKER), name="ALPHA")
        assert row.name_aliases == []
        customer_rules.record_name_alias(row, "Beta")
        db.flush()
        db.refresh(row)
        assert CustomerResponse.model_validate(row).name_aliases == ["Beta"]
