"""SPO-CASCADE: deleting a packing list must not delete AutoCount-synced SPO lines.

Incident (production, 28 Sep 2026): SPO-2026/09-0104 (AutoCount DocKey
`AED_SORENTO:45897229`, 18 lines, container DFSU7408507) was pushed by
`POST /api/v1/external/ingest/shipping_orders` and linked to inbound shipment
PL-2609-059 by container. A user then deleted that packing list. The ORM relationship
`InboundShipment.spo_allocations` cascaded `delete-orphan` and the FK was
`ON DELETE CASCADE`, so all 18 lines were hard-deleted with no audit row
(`spo_allocations` was on the audit skip list). The AutoCount sync never re-pushes a
document it has already pushed, so the SPO was gone for good.

Owner ruling: "we shouldn't delete on cascade". A shipping order is a document in its own
right (`SPOAllocation` docstring: since migration 420 this table holds the SPO document
itself; `inbound_shipment_id` NULL means "promised, not yet on a named shipment"). Deleting
the shipment it was booked on UNLINKS its lines; it never deletes them.

Four contracts, each red before the fix:

  (a) deleting a packing list keeps its SPO lines, with `inbound_shipment_id` NULL, on the
      service path, the bulk path and a raw `DELETE FROM inbound_shipments` (the FK itself);
  (b) a new packing list with the same container relinks the unlinked lines to itself;
  (c) the single-row SPO line delete refuses a caller without
      `procurement.spo_allocations.delete` (the bulk route already does);
  (d) an SPO line delete by staff writes an audit row naming who deleted it.

Postgres via `tests/_pg_fixture.py::blank_session`, never sqlite. The TestClient / company
plumbing is `tests/test_external_company_anchor_scope.py`'s `env` fixture, imported not
copied.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import AuditActor, clear_actor, stamp_actor
from app.models.audit import AuditLog
from app.models.procurement import InboundShipment, SPOAllocation
from app.schemas.procurement import InboundShipmentCreate, InboundShipmentLineCreate
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from app.services.procurement_service import InboundShipmentService, SPOAllocationService
from app.services.user_service import UserPermissionService
from tests.test_external_company_anchor_scope import env  # noqa: F401 - pytest fixture

__all__ = ["env"]

MARKER = "ZZTSPOCAS"
SPO_ALLOCATIONS = "/api/v1/procurement/spo-allocations"
DELETE_PERMISSION = "procurement.spo_allocations.delete"
AUTOCOUNT_DOC_KEY = "AED_SORENTO:45897229"


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    register_audit_listeners()
    yield
    clear_actor()


def _container() -> str:
    """A real ISO 6346 shape (four letters, seven digits), unique per test."""
    return f"ZZTU{uuid.uuid4().int % 10_000_000:07d}"


def _shipment(env, container: str) -> InboundShipment:
    row = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=f"{MARKER}-PL-{uuid.uuid4().hex[:6]}",
        shipping_container_number=container,
        shipment_date=date(2026, 9, 1),
        shipment_status="pending",
        company_id=env.company_a,
    )
    env.db.add(row)
    env.db.flush()
    return row


def _autocount_lines(env, shipment: InboundShipment, container: str, *, count: int = 2):
    """`count` lines of one AutoCount-pushed shipping order, booked on `shipment`.

    Shaped like the ingest writes them (`shipping_order_ingest_service._apply_line`):
    `source_doc_ref` = the DocKey, `container_number` = the cleaned container, and
    `inbound_shipment_id` resolved by container.
    """
    product = env.product(f"{MARKER}-P-{uuid.uuid4().hex[:6]}", env.company_a)
    warehouse = env.warehouse(f"{MARKER}WH{uuid.uuid4().hex[:6]}", env.company_a)
    spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
    # `uq_spo_allocations_company_source_ref`: the DtlKey is unique per company, so each
    # seeded document gets its own, while the DocKey stays the incident's.
    dtl_key = uuid.uuid4().hex[:8]
    rows = []
    for line_no in range(1, count + 1):
        row = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=env.company_a,
            spo_number=spo_number,
            spo_line_number=line_no,
            product_id=product.id,
            warehouse_id=warehouse.id,
            allocated_quantity=10 * line_no,
            quantity_received=0,
            line_status="open",
            receipt_status="pending",
            source_system="autocount",
            source_ref=f"{AUTOCOUNT_DOC_KEY}:{dtl_key}:{line_no}",
            source_doc_ref=AUTOCOUNT_DOC_KEY,
            container_number=container,
            inbound_shipment_id=shipment.id,
        )
        env.db.add(row)
        rows.append(row)
    env.db.flush()
    env.db.commit()
    return rows


def _surviving(env, ids: list[str]) -> list[SPOAllocation]:
    env.db.expire_all()
    return (
        env.db.query(SPOAllocation)
        .filter(SPOAllocation.id.in_(ids))
        .order_by(SPOAllocation.spo_line_number)
        .all()
    )


# --------------------------------------------------------------------------- #
# (a) deleting a packing list keeps the SPO lines, unlinked                    #
# --------------------------------------------------------------------------- #
def test_deleting_a_packing_list_keeps_autocount_spo_lines_and_unlinks_them(env):
    """The incident, replayed: the shipment goes, every line of the pushed document
    stays, with `inbound_shipment_id` NULL and everything else untouched."""
    container = _container()
    shipment = _shipment(env, container)
    lines = _autocount_lines(env, shipment, container, count=3)
    ids = [row.id for row in lines]

    InboundShipmentService(env.db).delete_shipment(shipment.id)

    assert env.db.get(InboundShipment, shipment.id) is None
    survivors = _surviving(env, ids)
    assert [row.id for row in survivors] == ids, "SPO lines were deleted with the packing list"
    assert all(row.inbound_shipment_id is None for row in survivors)
    assert all(row.source_doc_ref == AUTOCOUNT_DOC_KEY for row in survivors)
    # The raw fact a later shipment relinks on is kept (D6).
    assert all(row.container_number == container for row in survivors)
    assert [row.allocated_quantity for row in survivors] == [10, 20, 30]


def test_bulk_deleting_packing_lists_keeps_autocount_spo_lines_and_unlinks_them(env):
    """Same contract on the bulk route's service path."""
    container_1, container_2 = _container(), _container()
    shipment_1 = _shipment(env, container_1)
    shipment_2 = _shipment(env, container_2)
    ids = [row.id for row in _autocount_lines(env, shipment_1, container_1)]
    ids += [row.id for row in _autocount_lines(env, shipment_2, container_2)]

    result = InboundShipmentService(env.db).bulk_delete_shipments([shipment_1.id, shipment_2.id])

    assert result["deleted_count"] == 2
    survivors = _surviving(env, ids)
    assert {row.id for row in survivors} == set(ids)
    assert all(row.inbound_shipment_id is None for row in survivors)


def test_the_foreign_key_itself_sets_null_rather_than_cascading(env):
    """The database-level contract, independent of the ORM: a raw
    `DELETE FROM inbound_shipments` (a migration, a psql session, a bulk statement
    that bypasses the unit of work) must leave the lines behind with the FK nulled,
    because `ON DELETE CASCADE` is exactly what deleted the 18 lines in production."""
    container = _container()
    shipment = _shipment(env, container)
    ids = [row.id for row in _autocount_lines(env, shipment, container)]

    env.db.execute(text("DELETE FROM inbound_shipments WHERE id = :id"), {"id": shipment.id})
    env.db.commit()

    survivors = _surviving(env, ids)
    assert [row.id for row in survivors] == ids, "the FK still cascades the delete"
    assert all(row.inbound_shipment_id is None for row in survivors)


# --------------------------------------------------------------------------- #
# (b) a new packing list with the same container relinks the unlinked lines   #
# --------------------------------------------------------------------------- #
def test_a_new_packing_list_with_the_same_container_relinks_the_unlinked_lines(env):
    """PL-2609-033 deleted at 03:00, PL-2609-059 uploaded at 03:00:55: the re-upload of
    the same container is routine, and the document's lines must land on the new
    shipment without waiting for the nightly sweep."""
    container = _container()
    old_shipment = _shipment(env, container)
    lines = _autocount_lines(env, old_shipment, container)
    ids = [row.id for row in lines]
    product_id = lines[0].product_id

    service = InboundShipmentService(env.db)
    service.delete_shipment(old_shipment.id)
    assert all(row.inbound_shipment_id is None for row in _surviving(env, ids))

    new_shipment = service.create_shipment(
        InboundShipmentCreate(
            shipping_container_number=container,
            shipment_date=date(2026, 9, 2),
            shipment_lines=[
                InboundShipmentLineCreate(product_id=product_id, quantity_shipped=5)
            ],
        )
    )

    survivors = _surviving(env, ids)
    assert [row.id for row in survivors] == ids
    assert {row.inbound_shipment_id for row in survivors} == {str(new_shipment.id)}


# --------------------------------------------------------------------------- #
# (c) the single-row SPO line delete is permission-gated                       #
# --------------------------------------------------------------------------- #
def test_single_spo_line_delete_refuses_a_caller_without_the_delete_permission(
    env, monkeypatch
):
    """`DELETE /spo-allocations/{id}` checked only `get_current_user`; the bulk route
    next to it requires `procurement.spo_allocations.delete`. Same write, same gate."""
    container = _container()
    shipment = _shipment(env, container)
    (line,) = _autocount_lines(env, shipment, container, count=1)

    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: False
    )

    bulk = env.client.request("DELETE", f"{SPO_ALLOCATIONS}/bulk", json={"ids": [line.id]})
    assert bulk.status_code == 403, bulk.text  # the gate the single route must match

    single = env.client.delete(f"{SPO_ALLOCATIONS}/{line.id}")
    assert single.status_code == 403, single.text
    assert DELETE_PERMISSION in single.json()["detail"]
    assert _surviving(env, [line.id]) != [], "the refused delete still removed the line"


def test_single_spo_line_delete_with_the_permission_still_works(env, monkeypatch):
    container = _container()
    shipment = _shipment(env, container)
    (line,) = _autocount_lines(env, shipment, container, count=1)

    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug == DELETE_PERMISSION,
    )

    response = env.client.delete(f"{SPO_ALLOCATIONS}/{line.id}")
    assert response.status_code == 200, response.text
    assert _surviving(env, [line.id]) == []


# --------------------------------------------------------------------------- #
# (d) an SPO line delete is traceable                                          #
# --------------------------------------------------------------------------- #
def _audit_rows(env, entity_id: str, action: str) -> list[AuditLog]:
    return (
        env.db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "spo_allocations",
            AuditLog.entity_id == str(entity_id),
            AuditLog.action == action,
        )
        .all()
    )


def test_deleting_an_spo_line_as_staff_writes_an_audit_row_naming_who(env):
    """A future disappearance has to be traceable: who, when, which document. The table
    is on the audit skip list (measured for the SYNC's churn, and the plan's 10x ceiling
    cannot credit the sync-writer exclusion), so a staff delete left nothing behind; the
    service now writes the row itself (`procurement_service._audit_spo_line`)."""
    container = _container()
    shipment = _shipment(env, container)
    (line,) = _autocount_lines(env, shipment, container, count=1)
    user_id = str(uuid.uuid4())
    stamp_actor(
        AuditActor(actor_type="user", user_id=user_id, real_user_id=user_id, auth_method="password"),
        db=env.db,
    )

    SPOAllocationService(env.db).delete_allocation(line.id)

    rows = _audit_rows(env, line.id, "DELETE")
    assert len(rows) == 1, "no audit row for the SPO line delete"
    (row,) = rows
    assert row.user_id == user_id
    assert row.actor_type == "user"
    assert (row.old_values or {}).get("spo_number") == line.spo_number
    assert (row.old_values or {}).get("source_doc_ref") == AUTOCOUNT_DOC_KEY


def test_bulk_deleting_spo_lines_as_staff_writes_an_audit_row_per_line(env):
    """The bulk route deletes with a query-level `delete()`, outside the unit of work;
    the `do_orm_execute` listener has to itemise those too."""
    container = _container()
    shipment = _shipment(env, container)
    lines = _autocount_lines(env, shipment, container, count=2)
    user_id = str(uuid.uuid4())
    stamp_actor(
        AuditActor(actor_type="user", user_id=user_id, real_user_id=user_id, auth_method="password"),
        db=env.db,
    )

    # Read before the delete: the instances are gone afterwards and refresh would raise.
    expected = [(row.id, row.spo_line_number) for row in lines]

    SPOAllocationService(env.db).bulk_delete_allocations([line_id for line_id, _ in expected])

    for line_id, line_no in expected:
        rows = _audit_rows(env, line_id, "DELETE")
        assert len(rows) == 1, f"no audit row for bulk-deleted line {line_no}"
        assert rows[0].user_id == user_id


def test_deleting_an_spo_document_as_staff_writes_an_audit_row_per_line(env):
    """`spo_document.delete`, the deferred action the UI's "Delete selected" parks
    (`record_actions._delete_spo_document` -> `delete_document`): the path an operator
    actually takes, so the one that most needs a trail."""
    container = _container()
    shipment = _shipment(env, container)
    lines = _autocount_lines(env, shipment, container, count=2)
    expected = [(row.id, row.spo_line_number) for row in lines]
    spo_number = lines[0].spo_number
    user_id = str(uuid.uuid4())
    stamp_actor(
        AuditActor(actor_type="user", user_id=user_id, real_user_id=user_id, auth_method="password"),
        db=env.db,
    )

    result = SPOAllocationService(env.db).delete_document(spo_number)

    assert result["deleted_count"] == 2
    for line_id, line_no in expected:
        rows = _audit_rows(env, line_id, "DELETE")
        assert len(rows) == 1, f"no audit row for document-deleted line {line_no}"
        assert rows[0].user_id == user_id
        assert (rows[0].old_values or {}).get("spo_number") == spo_number


def test_deleting_a_packing_list_records_the_unlink_on_each_spo_line(env):
    """The unlink is itself a change to the SPO line, and it is the one a support
    engineer looks for first when a document is no longer on its container."""
    container = _container()
    shipment = _shipment(env, container)
    lines = _autocount_lines(env, shipment, container, count=2)
    user_id = str(uuid.uuid4())
    stamp_actor(
        AuditActor(actor_type="user", user_id=user_id, real_user_id=user_id, auth_method="password"),
        db=env.db,
    )

    InboundShipmentService(env.db).delete_shipment(shipment.id)

    for line in lines:
        assert _audit_rows(env, line.id, "DELETE") == [], "the line was deleted, not unlinked"
        rows = _audit_rows(env, line.id, "UPDATE")
        assert len(rows) == 1, f"no audit row for the unlink of line {line.spo_line_number}"
        assert rows[0].user_id == user_id
        assert (rows[0].old_values or {}).get("inbound_shipment_id") == shipment.id
        assert (rows[0].new_values or {}).get("inbound_shipment_id") is None
