"""Group V1 - code and name fallbacks, back-create (PLAN section 2.2, D1/D2/D9/D10).

  AC-V1-1   customer_ref wins over customer_code; debtor_code is still written
  AC-V1-2   no ref, customer_code matches an existing row in the anchor company only
  AC-V1-3   code+name match nothing -> a customer is back-created and linked
  AC-V1-4   code only, no name, no match -> lands unlinked, "customer_unresolved"
  AC-V1-5   purchase order supplier ladder: code, cleaned name, back-create
  AC-V1-6   sales-order agent_code ladder: sales_agents.sales_agent, back-create
  AC-V1-7   line product_code ladder; a miss on a SENT code stays retryable
  AC-V1-7b  a sent-but-unresolved warehouse lands NULL with a warning (v2 deviation)
  AC-V1-8   a ref into another company still fails, new fields present or not
  AC-V1-9   PO currency defaults to CNY on header and line when unstated
  AC-V1-10  dry_run creates no master; the verdict still reports what would happen

Every test seeds its own chain on the blank scratch schema (`tests._pg_fixture`),
reusing the `env` fixture and record builders from `test_ingest_documents` per the
tester brief - no new substrate. None of `customer_code`, `customer_name`,
`agent_code`, `supplier_code`, `supplier_name`, `product_code`, `warehouse_code`
exist on the canonical schemas yet, so most records here are rejected by
`extra="forbid"` today: that ValidationError, surfacing as
`outcome == "failed"` with an `errors` entry naming the field, is the expected
RED reason. A few ACs (currency default, the warehouse-unresolved deviation) need
no new schema field and fail on behaviour instead.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.models.order import Customer
from app.models.procurement import Supplier
from app.models.sales_agent import SalesAgent
from app.services.scm.customer_label import normalize_debtor_code

from tests._pg_fixture import unique_code
from tests.test_ingest_documents import (
    INGEST_PO,
    INGEST_SO,
    MARKER,
    _po_line,
    _po_record,
    _ref,
    _so_line,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse per the tester brief
)

__all__ = ["env"]


def _plain_customer(env, company_id: str, *, code: str, name: str | None = None) -> Customer:
    """A customer row NOT registered under any integration_reference.

    Distinct from `env.link_customer`: AC-V1-2 is specifically about matching a
    row the ESB never pushed (the xlsx era, or a customer created by hand) - one
    that can only be found by code, never by ref.
    """
    row = Customer(
        customer_code=code,
        customer_name=name or f"{MARKER} plain customer",
        company_id=company_id,
    )
    env.db.add(row)
    env.db.flush()
    return row


def _plain_supplier(env, company_id: str, *, code: str, name: str | None = None) -> Supplier:
    row = Supplier(
        supplier_code=code,
        supplier_name=name or f"{MARKER} plain supplier",
        company_id=company_id,
    )
    env.db.add(row)
    env.db.flush()
    return row


def _plain_agent(*, code: str) -> SalesAgent:
    return SalesAgent(sales_agent=code)


# ================================================================== AC-V1-1
class TestCustomerRefWinsOverCode:
    def test_customer_ref_resolves_and_code_is_still_written_to_debtor_code(self, env):
        code = f"  {unique_code(MARKER)}  "
        record = _so_record(env, customer_ref=env.customer_ref, customer_code=code)

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        expected_customer_id = env.refs.resolve(
            entity_type="customers", source_ref=env.customer_ref
        )
        assert str(header["customer_id"]) == str(expected_customer_id)
        assert header["debtor_code"] == normalize_debtor_code(code)


# ================================================================== AC-V1-2
class TestCustomerCodeFallback:
    def test_customer_code_matches_an_existing_row_in_the_anchor_company(self, env):
        """Case/whitespace-insensitive: the payload spells the code differently
        from how the row stores it, and the two must still be the same debtor."""
        stored = _plain_customer(env, env.company_a, code=unique_code(MARKER))

        record = _so_record(env, customer_code=f"  {stored.customer_code.lower()}  ")
        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        assert str(header["customer_id"]) == str(stored.id)
        assert header["debtor_code"] == normalize_debtor_code(stored.customer_code)

    def test_the_same_code_in_the_other_company_is_not_matched(self, env):
        """A code that only exists in company B must not silently attach this
        company-A order to somebody else's debtor."""
        code = unique_code(MARKER)
        _plain_customer(env, env.company_b, code=code)

        record = _so_record(env, customer_code=code)
        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        assert header["customer_id"] is None
        assert header["debtor_code"] == normalize_debtor_code(code)
        assert "customer_unresolved" in entry.get("warnings", [])


# ================================================================== AC-V1-3
class TestCustomerBackCreate:
    def test_code_and_name_matching_nothing_creates_and_links_a_customer(self, env):
        code = unique_code(MARKER)
        name = f"{MARKER} Brand New Sdn Bhd"
        record = _so_record(env, customer_code=code, customer_name=name)

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        assert "customer_created" in entry.get("warnings", [])

        header = env.header("sales_orders", record["source_ref"])
        assert header["customer_id"] is not None
        created = (
            env.db.execute(
                text("SELECT * FROM customers WHERE id = :id"),
                {"id": header["customer_id"]},
            )
            .mappings()
            .first()
        )
        assert created["customer_code"] == code
        assert created["customer_name"] == name
        assert created["customer_type"] == "company"
        assert created["is_active"] is True
        assert created["market_segment_code"] is None
        assert str(created["company_id"]) == str(env.company_a)

    def test_a_customer_ref_sent_alongside_resolves_the_new_row_next_time(self, env):
        """The created row is registered under the ref that was sent, so a
        re-push with only `customer_ref` finds it (step 1 of the ladder)."""
        code = unique_code(MARKER)
        name = f"{MARKER} Another New Co"
        new_ref = _ref("DEBTOR-NEW")
        record = _so_record(
            env, customer_ref=new_ref, customer_code=code, customer_name=name
        )

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        resolved = env.refs.resolve(entity_type="customers", source_ref=new_ref)
        assert resolved is not None
        assert str(resolved) == str(header["customer_id"])


# ================================================================== AC-V1-4
class TestCustomerCodeOnlyUnresolved:
    def test_code_only_no_name_no_match_lands_unlinked_and_warns(self, env):
        code = unique_code(MARKER)
        record = _so_record(env, customer_code=code)

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        assert "customer_unresolved" in entry.get("warnings", [])
        header = env.header("sales_orders", record["source_ref"])
        assert header["customer_id"] is None
        assert header["debtor_code"] == normalize_debtor_code(code)
        # No row minted for a code-only miss (D2): the unique pair index is on
        # (code, name), and a code-only row would collide with a later named one.
        assert (
            env.db.execute(
                text(
                    "SELECT count(*) FROM customers WHERE company_id = :c "
                    "AND upper(btrim(customer_code)) = upper(btrim(:code))"
                ),
                {"c": env.company_a, "code": code},
            ).scalar()
            == 0
        )


# ================================================================== AC-V1-5
class TestSupplierLadder:
    def test_supplier_code_match(self, env):
        stored = _plain_supplier(env, env.company_a, code=unique_code(MARKER))
        record = _po_record(env, supplier_code=f" {stored.supplier_code.lower()} ")

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("purchase_orders", record["source_ref"])
        assert str(header["supplier_id"]) == str(stored.id)

    def test_supplier_name_matches_after_stripping_the_rmb_suffix(self, env):
        stored = _plain_supplier(
            env, env.company_a, code=unique_code(MARKER), name="Xiamen Taiyang Co"
        )
        record = _po_record(env, supplier_name="Xiamen Taiyang Co (RMB)")

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("purchase_orders", record["source_ref"])
        assert str(header["supplier_id"]) == str(stored.id)

    def test_neither_matches_back_creates_and_registers_the_ref(self, env):
        code = unique_code(MARKER)
        name = f"{MARKER} New Creditor Co"
        new_ref = _ref("CREDITOR-NEW")
        record = _po_record(
            env, supplier_ref=new_ref, supplier_code=code, supplier_name=name
        )

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        assert "supplier_created" in entry.get("warnings", [])
        header = env.header("purchase_orders", record["source_ref"])
        created = (
            env.db.execute(
                text("SELECT * FROM suppliers WHERE id = :id"),
                {"id": header["supplier_id"]},
            )
            .mappings()
            .first()
        )
        assert created is not None
        assert created["supplier_code"] == code
        assert created["supplier_name"] == name
        resolved = env.refs.resolve(entity_type="suppliers", source_ref=new_ref)
        assert str(resolved) == str(header["supplier_id"])

    def test_back_create_slugs_the_name_when_only_a_name_is_sent(self, env):
        name = f"{MARKER} Nameless Supplier Co"
        record = _po_record(env, supplier_name=name)

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("purchase_orders", record["source_ref"])
        created = (
            env.db.execute(
                text("SELECT * FROM suppliers WHERE id = :id"),
                {"id": header["supplier_id"]},
            )
            .mappings()
            .first()
        )
        assert created is not None
        assert created["supplier_code"]


# ================================================================== AC-V1-6
class TestAgentCodeLadder:
    def test_agent_code_resolves_an_existing_row(self, env):
        agent = _plain_agent(code=f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
        env.db.add(agent)
        env.db.flush()

        record = _so_record(env, agent_code=f"  {agent.sales_agent.lower()}  ")
        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        assert str(header["sales_agent_id"]) == str(agent.id)

    def test_agent_code_creates_a_shared_row_and_registers_the_ref(self, env):
        code = f"{MARKER}-{uuid.uuid4().hex[:6].upper()}"
        new_ref = _ref("AGENT-NEW")
        record = _so_record(env, sales_agent_ref=new_ref, agent_code=code)

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        assert "agent_created" in entry.get("warnings", [])
        header = env.header("sales_orders", record["source_ref"])
        created = (
            env.db.execute(
                text("SELECT * FROM sales_agents WHERE id = :id"),
                {"id": header["sales_agent_id"]},
            )
            .mappings()
            .first()
        )
        assert created is not None
        assert created["sales_agent"] == code
        assert created["source"] == "import"
        resolved = env.refs.resolve(entity_type="sales_agents", source_ref=new_ref)
        assert str(resolved) == str(header["sales_agent_id"])


# ================================================================== AC-V1-7
class TestLineProductCodeLadder:
    def test_line_product_code_resolves_within_the_anchor_company(self, env):
        from app.models.product import Product

        product = Product(
            product_code=unique_code(MARKER),
            product_name=f"{MARKER} product by code",
            category_id=env._category.id,
            base_uom_id=env._uom.id,
            list_price=1,
            company_id=env.company_a,
        )
        env.db.add(product)
        env.db.flush()

        line = {
            "source_ref": _ref("SOL"),
            "product_code": product.product_code,
            "qty_ordered": 5,
        }
        record = _so_record(env, lines=[line])

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        lines = env.so_lines(header["id"])
        assert str(lines[0]["product_id"]) == str(product.id)

    def test_a_miss_on_a_sent_product_code_is_retryable_and_writes_nothing(self, env):
        before = env.counts()
        line = {
            "source_ref": _ref("SOL"),
            "product_code": f"{MARKER}-NOT-SYNCED-YET",
            "qty_ordered": 5,
        }
        record = _so_record(env, lines=[line])

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "retryable", res.text
        assert "not found" in entry["errors"].get("lines.0.product_code", ""), entry
        assert env.header("sales_orders", record["source_ref"]) is None
        assert env.counts() == before


# ================================================================= AC-V1-7b
class TestWarehouseUnresolvedIsAWarningNotARetry:
    def test_an_unresolved_sent_warehouse_ref_lands_null_with_a_warning(self, env):
        """v2 deviation from D10: today this is `retryable` (pinned in
        `test_ingest_documents.TestUnresolvedReferences`); v2 lets it through."""
        record = _so_record(
            env, lines=[_so_line(env, warehouse_ref=f"{MARKER}:LOC-NOT-SYNCED-YET")]
        )

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        assert "warehouse_unresolved" in entry.get("warnings", [])
        header = env.header("sales_orders", record["source_ref"])
        lines = env.so_lines(header["id"])
        assert lines[0]["warehouse_id"] is None

    def test_an_unresolved_sent_warehouse_code_lands_null_with_a_warning(self, env):
        line = {
            "source_ref": _ref("SOL"),
            "product_ref": env.product_ref,
            "qty_ordered": 5,
            "warehouse_code": f"{MARKER}-NOT-SYNCED-YET",
        }
        record = _so_record(env, lines=[line])

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        assert "warehouse_unresolved" in entry.get("warnings", [])
        header = env.header("sales_orders", record["source_ref"])
        lines = env.so_lines(header["id"])
        assert lines[0]["warehouse_id"] is None


# ================================================================== AC-V1-8
class TestCrossCompanyRefStillFails:
    def test_a_customer_ref_into_another_company_still_fails_with_the_new_fields_present(
        self, env
    ):
        foreign_customer = env.link_customer(env.company_b)
        record = _so_record(
            env, customer_ref=foreign_customer, customer_code=unique_code(MARKER)
        )

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", res.text
        assert "another company" in entry["errors"].get("customer_ref", "")
        assert env.header("sales_orders", record["source_ref"]) is None

    def test_a_supplier_ref_into_another_company_still_fails_with_the_new_fields_present(
        self, env
    ):
        foreign_supplier = env.link_supplier(env.company_b)
        record = _po_record(
            env, supplier_ref=foreign_supplier, supplier_code=unique_code(MARKER)
        )

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", res.text
        assert "another company" in entry["errors"].get("supplier_ref", "")
        assert env.header("purchase_orders", record["source_ref"]) is None


# ================================================================== AC-V1-9
class TestPurchaseOrderCurrencyDefault:
    def test_header_and_line_default_to_cny_when_unstated(self, env):
        record = _po_record(env)  # no currency anywhere
        assert "currency" not in record

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("purchase_orders", record["source_ref"])
        assert header["currency"] == "CNY"
        lines = env.po_lines(header["id"])
        assert lines[0]["currency"] == "CNY"

    def test_a_stated_currency_is_stored_as_sent(self, env):
        line = _po_line(env, currency="MYR")
        record = _po_record(env, lines=[line], currency="USD")

        res = env.post(INGEST_PO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text
        header = env.header("purchase_orders", record["source_ref"])
        assert header["currency"] == "USD"
        lines = env.po_lines(header["id"])
        assert lines[0]["currency"] == "MYR"


# ================================================================= AC-V1-10
class TestDryRunBackCreate:
    def test_dry_run_creates_no_supplier_but_reports_what_would_happen(self, env):
        code = unique_code(MARKER)
        name = f"{MARKER} Dry Run Co"
        record = _po_record(env, supplier_code=code, supplier_name=name)

        res = env.post(INGEST_PO, [record], dry_run=True)

        body = res.json()
        assert body["dry_run"] is True
        entry = body["records"][0]
        assert entry["outcome"] == "created", res.text
        assert "supplier_created" in entry.get("warnings", [])
        assert (
            env.db.execute(
                text(
                    "SELECT count(*) FROM suppliers WHERE company_id = :c "
                    "AND upper(btrim(supplier_code)) = upper(btrim(:code))"
                ),
                {"c": env.company_a, "code": code},
            ).scalar()
            == 0
        )
        assert env.header("purchase_orders", record["source_ref"]) is None

    def test_dry_run_creates_no_customer_but_reports_what_would_happen(self, env):
        code = unique_code(MARKER)
        name = f"{MARKER} Dry Run Customer"
        record = _so_record(env, customer_code=code, customer_name=name)

        res = env.post(INGEST_SO, [record], dry_run=True)

        body = res.json()
        assert body["dry_run"] is True
        entry = body["records"][0]
        assert entry["outcome"] == "created", res.text
        assert "customer_created" in entry.get("warnings", [])
        assert (
            env.db.execute(
                text(
                    "SELECT count(*) FROM customers WHERE company_id = :c "
                    "AND upper(btrim(customer_code)) = upper(btrim(:code))"
                ),
                {"c": env.company_a, "code": code},
            ).scalar()
            == 0
        )


# ============================================================== schema pin
class TestSchemaStillForbidsUnknownKeys:
    def test_a_v1_payload_with_no_new_keys_still_validates(self, env):
        """Byte-for-byte parity: nothing added here should make a plain v1
        record start failing (AC-V0-2 lives in its own file; this is the same
        guarantee from the resolution side)."""
        record = _so_record(env, customer_ref=env.customer_ref)

        res = env.post(INGEST_SO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text

    def test_an_unknown_key_is_still_rejected_and_names_it(self, env):
        record = _so_record(env, customer_nick="Bob")

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", res.text
        assert "customer_nick" in entry["errors"]
