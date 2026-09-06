"""Group V2 - Demand classification on sales-order ingest (PLAN section 1 D4, 2.3).

  AC-V2-1   stored order_type already classifies -> demand_class from it; the
            payload's order_type never overwrites what is already stored (fill-only)
  AC-V2-2   no stored order_type, payload order_type classifies -> order_type is
            filled AND demand_class is derived from it
  AC-V2-3   neither order_type -> the linked agent's demand_class is written
  AC-V2-4   none of those -> the linked customer's market segment decides it
  AC-V2-5   nothing classifies -> record still lands, demand_class stays NULL,
            verdict warnings carries "unclassified_demand"
  AC-V2-6   a stored demand_class is never downgraded or blanked by a later push
            that cannot classify (even one that names a conflicting segment)
  AC-V2-7   `demand_class` is not an accepted payload key (extra="forbid")

Plus a direct parity test of `app.services.scm.demand_class.classify_document`,
the pure ladder function PLAN section 1 D4 extracts out of
`outstanding_import_service._classify_demand`.

Substrate reused verbatim from `tests.test_ingest_documents` per the tester brief:
the blank scratch schema, the `env` fixture (two companies + one linked master of
every kind), `_so_record` / `_so_line` / `_ref`, the `ZZTDOC` marker. `order_type`
is a NEW optional header field `CanonicalSalesOrder` does not declare yet, so
every test that sends it is expected to fail today on `extra="forbid"` - that is
the RED reason for this slice, not a fixture bug. `sales_agent_ref` and
`customer_ref` are v1 keys already accepted; using them here (rather than the
S1 code/name fallbacks) keeps this file's RED status independent of S1's
progress in the same worktree.
"""
from __future__ import annotations

import uuid

from app.models.access import MarketSegment
from app.models.order import Customer, SalesOrder
from app.models.sales_agent import SalesAgent

from tests._pg_fixture import unique_code
from tests.test_ingest_documents import (
    INGEST_SO,
    MARKER,
    _ref,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse per the tester brief
)

__all__ = ["env"]


# ------------------------------------------------------------------ seed helpers
def _seed_so_header(env, *, order_type=None, demand_class=None, ref=None, number=None):
    """A `sales_orders` header written DIRECTLY (not through the API), because
    `order_type` and `demand_class` are not payload fields - the only way a
    header carries them today is a prior import / CS edit."""
    row = SalesOrder(
        id=str(uuid.uuid4()),
        company_id=env.company_a,
        so_number=number or f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
        status="open",
        order_type=order_type,
        demand_class=demand_class,
        source_system="autocount",
    )
    env.db.add(row)
    env.db.flush()
    source_ref = ref or _ref("SO")
    env.refs.link(entity_type="sales_orders", entity_id=row.id, source_ref=source_ref)
    return row, source_ref


def _market_segment(env, *, stem: str) -> MarketSegment:
    row = MarketSegment(code=unique_code(stem), name=f"{MARKER} {stem} segment")
    env.db.add(row)
    env.db.flush()
    return row


def _customer_with_segment(env, *, segment_code: str) -> Customer:
    row = Customer(
        customer_code=unique_code(MARKER),
        customer_name=f"{MARKER} segment customer",
        company_id=env.company_a,
        market_segment_code=segment_code,
    )
    env.db.add(row)
    env.db.flush()
    return row


def _linked_customer_ref(env, *, segment_code: str) -> str:
    customer = _customer_with_segment(env, segment_code=segment_code)
    return env._link("customers", customer.id, "DEBTOR-SEG")


def _agent_with_class(env, *, demand_class: str) -> SalesAgent:
    row = SalesAgent(
        sales_agent=f"{MARKER}-{uuid.uuid4().hex[:6].upper()}", demand_class=demand_class
    )
    env.db.add(row)
    env.db.flush()
    return row


def _linked_agent_ref(env, *, demand_class: str) -> str:
    agent = _agent_with_class(env, demand_class=demand_class)
    return env._link("sales_agents", agent.id, "AGENT-DC")


# ================================================================== AC-V2-1
class TestStoredOrderTypeWinsOverPayload:
    def test_demand_class_comes_from_stored_order_type_and_it_is_not_overwritten(self, env):
        header, source_ref = _seed_so_header(env, order_type="Project Alpha")

        record = _so_record(env, ref=source_ref, number=header.so_number, order_type="Dealer")
        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", res.text
        stored = env.header("sales_orders", source_ref)
        assert stored["order_type"] == "Project Alpha", (
            "fill-only: the payload's order_type must never restate an already-"
            f"stored value, got {stored['order_type']!r}"
        )
        assert stored["demand_class"] == "project", stored


# ================================================================== AC-V2-2
class TestPayloadOrderTypeFillsAnAbsentHeader:
    def test_project_order_type_fills_the_header_and_classifies_project(self, env):
        record = _so_record(env, order_type="project")

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        assert header["order_type"] == "project"
        assert header["demand_class"] == "project"

    def test_dealer_order_type_fills_the_header_and_classifies_retail(self, env):
        record = _so_record(env, order_type="dealer")

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        assert header["order_type"] == "dealer"
        assert header["demand_class"] == "retail"


# ================================================================== AC-V2-3
class TestAgentDemandClassIsThirdRung:
    def test_linked_agent_demand_class_is_written_when_no_order_type_states_anything(self, env):
        agent_ref = _linked_agent_ref(env, demand_class="project")
        record = _so_record(env, sales_agent_ref=agent_ref)

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        assert header["demand_class"] == "project"


# ================================================================== AC-V2-4
class TestCustomerSegmentIsFourthRung:
    def test_project_shaped_segment_classifies_project(self, env):
        segment = _market_segment(env, stem="PROJECT")
        customer_ref = _linked_customer_ref(env, segment_code=segment.code)
        record = _so_record(env, customer_ref=customer_ref)

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        assert header["demand_class"] == "project"

    def test_retail_shaped_segment_classifies_retail(self, env):
        segment = _market_segment(env, stem="RETAIL")
        customer_ref = _linked_customer_ref(env, segment_code=segment.code)
        record = _so_record(env, customer_ref=customer_ref)

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        assert header["demand_class"] == "retail"


# ================================================================== AC-V2-5
class TestNothingClassifies:
    def test_record_still_lands_demand_class_null_and_warns_unclassified(self, env):
        record = _so_record(env)  # no order_type, no agent, no customer

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        assert "unclassified_demand" in entry.get("warnings", []), entry
        header = env.header("sales_orders", record["source_ref"])
        assert header["demand_class"] is None


# ================================================================== AC-V2-6
class TestStoredDemandClassNeverDowngraded:
    def test_a_later_unclassifiable_push_leaves_a_stored_class_untouched(self, env):
        header, source_ref = _seed_so_header(env, demand_class="project")
        # A conflicting signal that WOULD classify as "retail" if the ladder ran
        # from scratch - proving the guard is "stored wins outright", not merely
        # "no worse answer happened to be available".
        segment = _market_segment(env, stem="RETAIL")
        customer_ref = _linked_customer_ref(env, segment_code=segment.code)

        record = _so_record(env, ref=source_ref, number=header.so_number, customer_ref=customer_ref)
        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", res.text
        stored = env.header("sales_orders", source_ref)
        assert stored["demand_class"] == "project", (
            "a stored demand_class must never be downgraded or blanked by a "
            f"later push, got {stored['demand_class']!r}"
        )
        assert "unclassified_demand" not in entry.get("warnings", []), entry


# ================================================================== AC-V2-7
class TestDemandClassIsNeverAPayloadField:
    def test_demand_class_in_the_payload_is_rejected(self, env):
        record = _so_record(env, demand_class="project")

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", res.text
        assert "demand_class" in entry.get("errors", {}), entry


# ============================================================ parity: the ladder
class TestClassifyDocumentSignatureAndLadder:
    """`classify_document` per PLAN section 1 D4:

        classify_document(db, *, stored_order_type, stated_order_type,
                           agent_demand_class, debtor_code, company_id) -> Optional[str]

    Importing it is itself the RED signal today (the function does not exist
    yet - it is still inlined as `_classify_demand` /
    `_class_of` / `_segment_of` in `outstanding_import_service.py`). Imported
    inside each test body so a missing function fails one test at a time
    rather than the whole module at collection.
    """

    def test_stored_order_type_outranks_everything_else(self, env):
        from app.services.scm.demand_class import classify_document

        result = classify_document(
            env.db,
            stored_order_type="Project Alpha",
            stated_order_type="Dealer",
            agent_demand_class="retail",
            debtor_code="does-not-matter",
            company_id=env.company_a,
        )
        assert result == "project"

    def test_stated_order_type_is_the_second_rung(self, env):
        from app.services.scm.demand_class import classify_document

        project = classify_document(
            env.db,
            stored_order_type=None,
            stated_order_type="project",
            agent_demand_class=None,
            debtor_code=None,
            company_id=env.company_a,
        )
        assert project == "project"

        retail = classify_document(
            env.db,
            stored_order_type=None,
            stated_order_type="dealer",
            agent_demand_class=None,
            debtor_code=None,
            company_id=env.company_a,
        )
        assert retail == "retail"

    def test_agent_demand_class_is_the_third_rung(self, env):
        from app.services.scm.demand_class import classify_document

        result = classify_document(
            env.db,
            stored_order_type=None,
            stated_order_type=None,
            agent_demand_class="project",
            debtor_code=None,
            company_id=env.company_a,
        )
        assert result == "project"

    def test_customer_segment_is_the_fourth_and_last_rung(self, env):
        from app.services.scm.demand_class import classify_document

        segment = _market_segment(env, stem="PROJECT")
        customer = _customer_with_segment(env, segment_code=segment.code)

        result = classify_document(
            env.db,
            stored_order_type=None,
            stated_order_type=None,
            agent_demand_class=None,
            debtor_code=customer.customer_code,
            company_id=env.company_a,
        )
        assert result == "project"

    def test_nothing_classifies_returns_none(self, env):
        from app.services.scm.demand_class import classify_document

        result = classify_document(
            env.db,
            stored_order_type=None,
            stated_order_type=None,
            agent_demand_class=None,
            debtor_code=None,
            company_id=env.company_a,
        )
        assert result is None
