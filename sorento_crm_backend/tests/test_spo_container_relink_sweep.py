"""S5 (review re-check, 2026-09-06): the nightly sweep
`relink_allocations_for_container`'s own docstring promised - an allocation
written before its shipment existed, or a shipment created AFTER its
allocations were pushed, otherwise never gets linked again.

Two things, kept in one small file rather than folded into an existing
review-guard file: the RULE (`nightly_relink_all_containers` relinks per
(company, container) pair, never crossing companies) and the WIRING (the
scheduler actually registers a tick that calls it) - the second read off
`task_scheduler.py`'s own source, the same technique
`test_scheduler_company_scope.py` already uses for a bare-SessionLocal guard,
rather than starting a real `BackgroundScheduler` in a test process.
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.procurement import InboundShipment, SPOAllocation
from app.services.rules.shipping_order_rules import nightly_relink_all_containers

from tests.test_ingest_documents import env  # noqa: F401 - pytest fixture, imported for reuse

__all__ = ["env"]

MARKER = "ZZTSPORELINK"

SCHEDULER_SRC = Path(__file__).resolve().parents[1] / "app" / "scheduler" / "task_scheduler.py"


def _company(db) -> str:
    row = Company(id=str(uuid.uuid4()), name=f"{MARKER} B", code=f"ZZS{uuid.uuid4().hex[:6]}")
    db.add(row)
    db.flush()
    return str(row.id)


def _unlinked_allocation(db, *, company_id: str, container: str, product_id: str) -> SPOAllocation:
    alloc = SPOAllocation(
        id=str(uuid.uuid4()),
        spo_number=f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}",
        spo_line_number=1,
        product_id=product_id,
        container_number=container,
        allocated_quantity=10,
        quantity_received=0,
        line_status="open",
        company_id=company_id,
    )
    db.add(alloc)
    return alloc


def _shipment(db, *, company_id: str, container: str) -> InboundShipment:
    shipment = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=f"{MARKER}-SH-{uuid.uuid4().hex[:8]}",
        shipping_container_number=container,
        shipment_date=date(2026, 1, 1),
        shipment_status="pending",
        company_id=company_id,
    )
    db.add(shipment)
    return shipment


class TestNightlyRelinkAllContainers:
    """`shipping_order_rules.nightly_relink_all_containers`: relinks every
    unlinked (company, container) pair it finds, one company's allocations
    never touched by another's shipment."""

    def test_relinks_one_unlinked_pair_per_company(self, env):
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        company_b = _company(env.db)

        container_a = f"{MARKER}-CONTA-{uuid.uuid4().hex[:8]}".upper()
        container_b = f"{MARKER}-CONTB-{uuid.uuid4().hex[:8]}".upper()
        alloc_a = _unlinked_allocation(
            env.db, company_id=env.company_a, container=container_a, product_id=product_id
        )
        alloc_b = _unlinked_allocation(
            env.db, company_id=company_b, container=container_b, product_id=product_id
        )
        shipment_a = _shipment(env.db, company_id=env.company_a, container=container_a)
        shipment_b = _shipment(env.db, company_id=company_b, container=container_b)
        env.db.flush()
        env.db.commit()

        # Emulates `scheduler_session()`'s own ambient-scope override: a
        # nightly sweep sees every company, unlike `env.db`'s request-time
        # scope (pinned to `company_a` by the fixture's own earlier
        # ORM writes) - the real tick sets this via `scheduler_session()`,
        # never relying on whatever the caller's ambient scope happened to be.
        set_company_scope(env.db, None)
        relinked = nightly_relink_all_containers(env.db)

        assert relinked == 2, "one pair per company must relink"
        env.db.refresh(alloc_a)
        env.db.refresh(alloc_b)
        assert alloc_a.inbound_shipment_id == shipment_a.id
        assert alloc_b.inbound_shipment_id == shipment_b.id

    def test_never_links_a_container_across_companies(self, env):
        """The same container number, two different companies, two different
        shipments - each allocation must land on its OWN company's shipment,
        never the other one's."""
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        company_b = _company(env.db)

        shared_container = f"{MARKER}-SHARED-{uuid.uuid4().hex[:8]}".upper()
        alloc_a = _unlinked_allocation(
            env.db, company_id=env.company_a, container=shared_container, product_id=product_id
        )
        alloc_b = _unlinked_allocation(
            env.db, company_id=company_b, container=shared_container, product_id=product_id
        )
        shipment_a = _shipment(env.db, company_id=env.company_a, container=shared_container)
        shipment_b = _shipment(env.db, company_id=company_b, container=shared_container)
        env.db.flush()
        env.db.commit()

        set_company_scope(env.db, None)  # nightly sweep sees every company
        nightly_relink_all_containers(env.db)

        env.db.refresh(alloc_a)
        env.db.refresh(alloc_b)
        assert alloc_a.inbound_shipment_id == shipment_a.id
        assert alloc_b.inbound_shipment_id == shipment_b.id
        assert alloc_a.inbound_shipment_id != shipment_b.id
        assert alloc_b.inbound_shipment_id != shipment_a.id

    def test_a_container_with_no_shipment_yet_relinks_nothing(self, env):
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        container = f"{MARKER}-NOSHIP-{uuid.uuid4().hex[:8]}".upper()
        alloc = _unlinked_allocation(
            env.db, company_id=env.company_a, container=container, product_id=product_id
        )
        env.db.flush()
        env.db.commit()

        relinked = nightly_relink_all_containers(env.db)

        assert relinked == 0
        env.db.refresh(alloc)
        assert alloc.inbound_shipment_id is None


def test_scheduler_registers_the_nightly_relink_sweep_job():
    """WIRING, not the rule - `start_scheduler` must actually `add_job` a
    tick that calls `nightly_relink_all_containers`, next to the other daily
    jobs, gated the same way every other tick is (`ENABLE_SCHEDULER`, checked
    once in `app.main.startup_event` before `start_scheduler()` is ever
    called - nothing extra needed inside this function itself)."""
    source = SCHEDULER_SRC.read_text()
    assert 'id="spo_container_relink_sweep"' in source, (
        "no add_job registers the nightly relink sweep"
    )
    assert "nightly_relink_all_containers" in source, (
        "the registered tick must call the shared relink-all function"
    )
    assert 'IntervalTrigger(hours=24)' in source.split('id="spo_container_relink_sweep"')[0].rsplit(
        "scheduler.add_job", 1
    )[-1], "the relink sweep must run daily, next to the other daily jobs"
