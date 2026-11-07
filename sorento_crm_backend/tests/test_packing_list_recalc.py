"""PACKING-LIST-RECALC (6 Nov 2026): a packing list's stored line figures and header
status follow every change to their inputs, without anybody opening the page.

The owner's prod case (YMMU7738143): an SPO pushed from AutoCount with NO container,
its receipt already stated; later the ref is fixed in AutoCount and the next push
carries the container. The push links the allocations to the packing list, but the
stored line status and header status stayed stale until the packing list page was
opened, because its GET was the thing that recomputed (and wrote).

The listener (`app/services/scm/packing_list_recalc.py`) notes the containers whose
inputs a commit changed and dispatches one recompute per container. Tests capture
the dispatch (`session.info` hook) and then run exactly what the `scm_recalc` job
runs, `recalc_packing_list`, on the same test session.
"""
from __future__ import annotations

import random
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PickingHeader,
    PickingLine,
)
from app.services.scm import packing_list_recalc
from tests._pg_fixture import unique_code
from tests.test_ingest_documents import MARKER
from tests.test_ingest_shipping_orders import (
    INGEST_SPO,
    _spo_line,
    _spo_record,
    _spo_rows,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)

__all__ = ["env"]


@pytest.fixture
def dispatched(env):
    """Capture what the listener dispatches instead of queueing it on Redis."""
    packing_list_recalc.register_packing_list_recalc_listeners()
    calls: list[list[str]] = []

    def _capture(ids):
        # Review B1: a dispatch must only ever happen at the OUTERMOST commit, never on
        # a SAVEPOINT release (the AutoCount ingest wraps each record in one).
        assert not env.db.in_nested_transaction(), "dispatched on a savepoint release"
        calls.append(list(ids))

    env.db.info[packing_list_recalc._DISPATCH_KEY] = _capture
    yield calls
    env.db.info.pop(packing_list_recalc._DISPATCH_KEY, None)


def _run_dispatched(env, calls) -> set[str]:
    """What the worker would do with every queued job: one recompute per container."""
    ids = {sid for batch in calls for sid in batch}
    calls.clear()
    for sid in sorted(ids):
        assert packing_list_recalc.recalc_packing_list(env.db, sid)
    return ids


def _container() -> str:
    return f"ZZTU{random.randint(10**6, 10**7 - 1)}"


def _packing_list(env, *, container: str, qty: int = 10, status: str = "in_transit"):
    product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
    shipment = InboundShipment(
        id=str(uuid.uuid4()),
        company_id=env.company_a,
        shipment_number=unique_code(f"{MARKER}-PL"),
        shipping_container_number=container,
        shipment_date=date(2026, 10, 1),
        estimated_arrival_date=date(2026, 10, 20),
        shipment_status=status,
    )
    env.db.add(shipment)
    env.db.flush()
    line = InboundShipmentLine(
        id=str(uuid.uuid4()),
        company_id=env.company_a,
        shipment_id=shipment.id,
        product_id=product_id,
        quantity_shipped=qty,
        quantity_received=0,
        line_status="in_transit",
    )
    env.db.add(line)
    env.db.commit()
    return str(shipment.id), str(line.id), product_id


def _stored(env, shipment_id: str, line_id: str):
    header = env.db.execute(
        text("SELECT shipment_status FROM inbound_shipments WHERE id = :i"), {"i": shipment_id}
    ).scalar()
    row = env.db.execute(
        text(
            "SELECT line_status, quantity_received, spo_allocated_quantity "
            "FROM inbound_shipment_lines WHERE id = :i"
        ),
        {"i": line_id},
    ).mappings().one()
    return header, dict(row)


def _status_audits(env, shipment_id: str):
    return env.db.execute(
        text(
            "SELECT old_values, new_values, reason FROM audit_logs "
            "WHERE entity_id = :i AND event = 'packing_list.status_recalculated' "
            "ORDER BY changed_at"
        ),
        {"i": shipment_id},
    ).mappings().all()


# ------------------------------------------------------------------- prod case
def test_container_arriving_on_a_later_push_recomputes_the_packing_list(env, dispatched):
    """YMMU7738143: the container reaches the SPO on a later AutoCount push; the
    packing list's lines and header follow with no page open."""
    container = _container()
    shipment_id, line_id, _ = _packing_list(env, container=container, qty=10)

    line = _spo_line(env, qty_ordered=10, qty_received=10, line_number=1)
    record = _spo_record(env, supplier_ref=env.supplier_ref, lines=[line])
    res = env.post(INGEST_SPO, [record])
    assert res.status_code == 200, res.text
    rows = _spo_rows(env, record["spo_number"])
    assert [r["inbound_shipment_id"] for r in rows] == [None]
    _run_dispatched(env, dispatched)
    assert _stored(env, shipment_id, line_id)[0] == "in_transit"

    # The ref is fixed in AutoCount: the same document, now naming the container.
    res = env.post(INGEST_SPO, [dict(record, container_number=container)])
    assert res.status_code == 200, res.text
    rows = _spo_rows(env, record["spo_number"])
    assert [str(r["inbound_shipment_id"]) for r in rows] == [shipment_id]

    # One dispatch, at the route's own commit, not one per record savepoint.
    assert len(dispatched) == 1
    assert shipment_id in _run_dispatched(env, dispatched)
    header, stored = _stored(env, shipment_id, line_id)
    assert stored == {
        "line_status": "received",
        "quantity_received": 10,
        "spo_allocated_quantity": 10,
    }
    assert header == "fully_received"

    audits = _status_audits(env, shipment_id)
    assert len(audits) == 1
    assert audits[0]["old_values"] == {"shipment_status": "in_transit"}
    assert audits[0]["new_values"] == {"shipment_status": "fully_received"}
    assert audits[0]["reason"] == "input_change"


def test_container_moved_recomputes_both_packing_lists(env, dispatched):
    """A container corrected from A to B releases A's lines and links B's."""
    container_a, container_b = _container(), _container()
    a_id, a_line, _ = _packing_list(env, container=container_a, qty=10)
    b_id, b_line, _ = _packing_list(env, container=container_b, qty=10)

    line = _spo_line(env, qty_ordered=10, qty_received=10, line_number=1)
    record = _spo_record(env, supplier_ref=env.supplier_ref, lines=[line], container_number=container_a)
    assert env.post(INGEST_SPO, [record]).status_code == 200
    _run_dispatched(env, dispatched)
    assert _stored(env, a_id, a_line)[0] == "fully_received"

    assert env.post(INGEST_SPO, [dict(record, container_number=container_b)]).status_code == 200
    assert {a_id, b_id} <= _run_dispatched(env, dispatched)
    assert _stored(env, b_id, b_line)[0] == "fully_received"
    header_a, stored_a = _stored(env, a_id, a_line)
    assert stored_a["spo_allocated_quantity"] == 0
    assert stored_a["quantity_received"] == 0
    assert header_a == "in_transit"


def test_grn_approval_recomputes_the_packing_list(env, dispatched):
    """A GRN posted against an already-linked allocation: the pick's container."""
    container = _container()
    shipment_id, line_id, product_id = _packing_list(env, container=container, qty=10)
    line = _spo_line(env, qty_ordered=10, line_number=1)
    record = _spo_record(env, supplier_ref=env.supplier_ref, lines=[line], container_number=container)
    assert env.post(INGEST_SPO, [record]).status_code == 200
    _run_dispatched(env, dispatched)
    assert _stored(env, shipment_id, line_id)[0] == "in_transit"
    allocation_id = str(_spo_rows(env, record["spo_number"])[0]["id"])
    warehouse_id = env.refs.resolve(entity_type="warehouses", source_ref=env.warehouse_ref)

    header = PickingHeader(
        id=str(uuid.uuid4()),
        company_id=env.company_a,
        picking_number=unique_code(f"{MARKER}-GR"),
        picking_type="goods_received",
        picking_status="draft",
        spo_number=record["spo_number"],
    )
    env.db.add(header)
    env.db.flush()
    env.db.add(
        PickingLine(
            id=str(uuid.uuid4()),
            company_id=env.company_a,
            picking_header_id=header.id,
            spo_allocation_id=allocation_id,
            product_id=product_id,
            source_warehouse_id=warehouse_id,
            quantity_expected=10,
            quantity_picked=10,
        )
    )
    env.db.commit()
    _run_dispatched(env, dispatched)
    assert _stored(env, shipment_id, line_id)[0] == "in_transit"  # draft GRN counts nothing

    header.picking_status = "approved"
    env.db.commit()
    assert shipment_id in _run_dispatched(env, dispatched)
    assert _stored(env, shipment_id, line_id)[0] == "fully_received"


def test_unrelated_allocation_edit_dispatches_nothing(env, dispatched):
    """A column the recompute does not read (a note) queues nothing."""
    container = _container()
    _packing_list(env, container=container)
    record = _spo_record(
        env, supplier_ref=env.supplier_ref, lines=[_spo_line(env, line_number=1)],
        container_number=container,
    )
    assert env.post(INGEST_SPO, [record]).status_code == 200
    _run_dispatched(env, dispatched)
    from app.models.procurement import SPOAllocation

    row = env.db.query(SPOAllocation).filter(SPOAllocation.spo_number == record["spo_number"]).one()
    row.allocation_notes = "hand note"
    env.db.commit()
    assert dispatched == []


def test_rollback_dispatches_nothing(env, dispatched):
    container = _container()
    shipment_id, _, _ = _packing_list(env, container=container)
    record = _spo_record(
        env, supplier_ref=env.supplier_ref, lines=[_spo_line(env, line_number=1)],
    )
    assert env.post(INGEST_SPO, [record]).status_code == 200
    _run_dispatched(env, dispatched)
    from app.models.procurement import SPOAllocation

    row = env.db.query(SPOAllocation).filter(SPOAllocation.spo_number == record["spo_number"]).one()
    row.inbound_shipment_id = shipment_id
    env.db.flush()
    assert shipment_id in packing_list_recalc.pending_shipment_ids(env.db)
    env.db.rollback()
    assert packing_list_recalc.pending_shipment_ids(env.db) == set()
    assert dispatched == []


def test_savepoint_rollback_drops_only_its_own_notes(env, dispatched):
    container_a, container_b = _container(), _container()
    a_id, _, _ = _packing_list(env, container=container_a)
    b_id, _, _ = _packing_list(env, container=container_b)
    record = _spo_record(
        env, supplier_ref=env.supplier_ref,
        lines=[_spo_line(env, line_number=1), _spo_line(env, line_number=2)],
    )
    assert env.post(INGEST_SPO, [record]).status_code == 200
    _run_dispatched(env, dispatched)
    from app.models.procurement import SPOAllocation

    first, second = (
        env.db.query(SPOAllocation)
        .filter(SPOAllocation.spo_number == record["spo_number"])
        .order_by(SPOAllocation.spo_line_number)
        .all()
    )
    kept = env.db.begin_nested()
    first.inbound_shipment_id = a_id
    env.db.flush()
    kept.commit()
    assert dispatched == []  # a savepoint release dispatches nothing
    dropped = env.db.begin_nested()
    second.inbound_shipment_id = b_id
    env.db.flush()
    dropped.rollback()
    env.db.commit()
    assert dispatched == [[a_id]]


def test_expired_allocation_repointed_names_its_old_container(env, dispatched):
    """Review should-fix 3: an instance expired by an earlier commit carries no old
    value in its history; the old container is read before the UPDATE goes out."""
    container_a, container_b = _container(), _container()
    a_id, _, _ = _packing_list(env, container=container_a)
    b_id, _, _ = _packing_list(env, container=container_b)
    record = _spo_record(
        env, supplier_ref=env.supplier_ref, lines=[_spo_line(env, line_number=1)],
        container_number=container_a,
    )
    assert env.post(INGEST_SPO, [record]).status_code == 200
    _run_dispatched(env, dispatched)
    from app.models.procurement import SPOAllocation

    row = env.db.query(SPOAllocation).filter(SPOAllocation.spo_number == record["spo_number"]).one()
    env.db.commit()  # expires `row`
    row.inbound_shipment_id = b_id
    env.db.commit()
    assert {a_id, b_id} <= {sid for batch in dispatched for sid in batch}


# ------------------------------------------------------------------- the GET
def test_packing_list_get_reads_and_queues_instead_of_writing(env, dispatched, monkeypatch):
    """The page GET writes nothing; stale stored figures queue the recompute."""
    container = _container()
    shipment_id, line_id, _ = _packing_list(env, container=container, qty=10)
    record = _spo_record(
        env, supplier_ref=env.supplier_ref,
        lines=[_spo_line(env, qty_ordered=10, qty_received=10, line_number=1)],
        container_number=container,
    )
    assert env.post(INGEST_SPO, [record]).status_code == 200
    dispatched.clear()
    # Stale on purpose: a write that went around the ORM.
    env.db.execute(
        text("UPDATE inbound_shipment_lines SET line_status = 'in_transit', quantity_received = 0 WHERE id = :i"),
        {"i": line_id},
    )
    env.db.execute(
        text("UPDATE inbound_shipments SET shipment_status = 'in_transit' WHERE id = :i"),
        {"i": shipment_id},
    )
    env.db.commit()

    queued: list[list[str]] = []
    monkeypatch.setattr(
        "app.services.scm.packing_list_recalc.dispatch_recalc", lambda ids: queued.append(list(ids))
    )
    res = env.client.get(f"/api/v1/procurement/packing-lists/{shipment_id}")
    assert res.status_code == 200, res.text
    body = res.json()
    # The response is computed live, header included ...
    assert body["shipment_lines"][0]["line_status"] == "received"
    assert body["shipment_status"] == "fully_received"
    # ... the stored row is left alone, and the recompute is queued.
    assert _stored(env, shipment_id, line_id) == (
        "in_transit",
        {"line_status": "in_transit", "quantity_received": 0, "spo_allocated_quantity": 0},
    )
    assert queued == [[shipment_id]]

    # Current figures: nothing queued.
    packing_list_recalc.recalc_packing_list(env.db, shipment_id)
    queued.clear()
    assert env.client.get(f"/api/v1/procurement/packing-lists/{shipment_id}").status_code == 200
    assert queued == []


# ------------------------------------------------------------------- dispatch
def test_dispatch_skips_a_container_whose_job_is_still_waiting(monkeypatch):
    """Burst de-dupe: ten writes to one container while its job waits = one job. Once
    that job has started, a new write queues again (the run may predate the write)."""
    import rq
    import rq.job
    from rq.exceptions import NoSuchJobError

    jobs: dict[str, str] = {}

    class _Job:
        def __init__(self, status):
            self._status = status

        @classmethod
        def fetch(cls, job_id, connection=None):
            if job_id not in jobs:
                raise NoSuchJobError(job_id)
            return cls(jobs[job_id])

        def get_status(self, refresh=True):
            return self._status

    enqueued: list[str] = []

    class _Queue:
        def __init__(self, name, connection=None):
            assert name == "scm_recalc"

        def enqueue(self, func, *args, job_id=None, **kwargs):
            assert func == "app.tasks.packing_list_recalc_tasks.recalc_packing_list_job"
            jobs[job_id] = "queued"
            enqueued.append(job_id)

    monkeypatch.setattr(rq, "Queue", _Queue)
    monkeypatch.setattr(rq.job, "Job", _Job)
    sid = str(uuid.uuid4())
    for _ in range(10):
        packing_list_recalc.dispatch_recalc([sid])
    assert enqueued == [f"pl-recalc-{sid}"]

    # Review B2: while the job runs, a new write queues under a FRESH id (re-using the
    # running job's id would let the worker's cleanup delete the re-queued job).
    jobs[f"pl-recalc-{sid}"] = "started"
    for _ in range(5):
        packing_list_recalc.dispatch_recalc([sid])
    assert enqueued == [f"pl-recalc-{sid}", f"pl-recalc-{sid}-rerun"]

    # Both running: a one-off id rather than a lost write.
    jobs[f"pl-recalc-{sid}-rerun"] = "started"
    packing_list_recalc.dispatch_recalc([sid])
    assert len(enqueued) == 3 and enqueued[2].startswith(f"pl-recalc-{sid}-")

    # The first run finished: its own id is free again.
    jobs[f"pl-recalc-{sid}"] = "finished"
    packing_list_recalc.dispatch_recalc([sid])
    assert enqueued[3] == f"pl-recalc-{sid}"


def test_dispatch_falls_back_inline_when_redis_is_down(monkeypatch):
    import redis

    broken = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2)
    monkeypatch.setattr("app.services.queue_service.redis_conn", broken)
    ran: list[list[str]] = []
    monkeypatch.setattr(packing_list_recalc, "recalc_inline", lambda ids: ran.append(list(ids)))
    packing_list_recalc.dispatch_recalc(["x"])
    assert ran == [["x"]]
