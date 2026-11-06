"""PACKING-LIST-RECALC follow-up (after #2215): the gaps crew's adversarial review named.

1. Hand-run maintenance scripts open `app.database.SessionLocal` without importing
   `app.main` or `worker.py`, so the recompute listener was never registered for them.
   It is now registered where `SessionLocal` is built.
2. The hourly sweep only visited containers with an unreceived line, so a change that
   should take a Fully Received container BACK (made around the listener, e.g. a bulk
   `query.update()` in a script) stayed stale. It now also visits containers whose
   inputs changed since the last sweep (an `updated_at` watermark).
3. The header's own `shipment_status` / `company_id` are watched too (an edit queues the
   recompute); the recompute's own status write does not queue itself.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.models.procurement import InboundShipment, SPOAllocation
from app.services.scm import packing_list_recalc
from tests.test_packing_list_recalc import (  # noqa: F401 - fixtures reused
    INGEST_SPO,
    _container,
    _packing_list,
    _run_dispatched,
    _spo_line,
    _spo_record,
    _stored,
    dispatched,
    env,
)

__all__ = ["env", "dispatched"]

BACKEND = Path(__file__).resolve().parents[1]


def test_a_script_session_has_the_recalc_listener():
    """A fresh interpreter that imports only `app.database` (what every maintenance
    script does) has the listener registered."""
    code = (
        "import app.database\n"
        "from sqlalchemy import event\n"
        "from sqlalchemy.orm import Session\n"
        "from app.services.scm import packing_list_recalc as m\n"
        "print(event.contains(Session, 'after_flush', m._collect),"
        " event.contains(Session, 'after_commit', m._after_commit))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=120
    )
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "True True"


def _now(env):
    return env.db.execute(select(func.localtimestamp())).scalar()


def test_sweep_takes_a_fully_received_container_back_after_a_change_the_listener_missed(env, dispatched):
    container = _container()
    shipment_id, line_id, _ = _packing_list(env, container=container, qty=10)
    record = _spo_record(
        env, supplier_ref=env.supplier_ref,
        lines=[_spo_line(env, qty_ordered=10, qty_received=10, line_number=1)],
        container_number=container,
    )
    assert env.post(INGEST_SPO, [record]).status_code == 200
    _run_dispatched(env, dispatched)
    assert _stored(env, shipment_id, line_id)[0] == "fully_received"

    since = _now(env)
    # A script retiring the line in bulk: no ORM instance, so no flush listener.
    env.db.query(SPOAllocation).filter(SPOAllocation.spo_number == record["spo_number"]).update(
        {"retired_at": datetime.now(timezone.utc).replace(tzinfo=None)},
        synchronize_session=False,
    )
    env.db.commit()
    assert dispatched == []

    from app.services.rules.shipping_order_rules import nightly_refresh_open_containers

    nightly_refresh_open_containers(env.db, since=since)
    assert _stored(env, shipment_id, line_id)[0] == "in_transit"


def test_header_status_or_company_edit_queues_the_recompute(env, dispatched):
    container = _container()
    shipment_id, _, _ = _packing_list(env, container=container)
    _run_dispatched(env, dispatched)

    shipment = env.db.get(InboundShipment, shipment_id)
    shipment.shipment_status = "fully_received"
    env.db.commit()
    assert dispatched == [[shipment_id]]


def test_the_recompute_does_not_queue_itself(env, dispatched):
    """Its own header write (in_transit to fully_received) must not queue another run."""
    container = _container()
    shipment_id, line_id, _ = _packing_list(env, container=container, qty=10)
    record = _spo_record(
        env, supplier_ref=env.supplier_ref,
        lines=[_spo_line(env, qty_ordered=10, qty_received=10, line_number=1)],
        container_number=container,
    )
    assert env.post(INGEST_SPO, [record]).status_code == 200
    assert shipment_id in _run_dispatched(env, dispatched)
    assert _stored(env, shipment_id, line_id)[0] == "fully_received"
    assert dispatched == []
