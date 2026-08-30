"""What the book this page uploaded wrote, read back off the job (AC-H13).

`PLAN-scm-oi-handshake.md` section 3, "Link now" and "Open purchase orders". The page has
neither fact at queue time - the write happens on the worker - so it asks the finished job
what it touched: the products to narrow the cascade to, the documents to filter the
purchase-order list by. Pinned here:

* the route reads the importer's OWN answer off `result.upload`, both channels' spelling;
* a job nobody has finished says so rather than pretending it wrote nothing;
* CS is refused it, like every other action on this page;
* the purchase-order list narrowed by those documents shows exactly them.

Reuses the handshake suite's harness (real database, rolled back). Every row seeded behind
the `ZZT` marker: CI's database has no data.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.job import ImportJob, JobStatus
from app.models.procurement import PurchaseOrder
from app.services.scm.purchase_order_service import PurchaseOrderService

from .test_order_inquiry_handshake import (
    LIST,
    MARKER,
    _as_purchasing,
    _supplier,
    _uid,
    api,
    world,
)

__all__ = ["api", "world"]  # re-exported fixtures; keeps linters from calling them unused


def _job(world, *, result=None, status=JobStatus.FINISHED.value, job_type="outstanding_po_import"):
    job = ImportJob(
        id=uuid.uuid4(),
        job_id=str(uuid.uuid4()),
        job_type=job_type,
        status=status,
        user_id=world.buyer,
        filename=f"{MARKER}-po-book.xlsx",
        company_id=uuid.UUID(str(world.company_id)),
        result=result,
    )
    world.db.add(job)
    world.db.commit()
    return job


def _url(job) -> str:
    return f"{LIST}/upload-jobs/{job.job_id}"


def test_the_route_states_the_products_and_documents_the_upload_wrote(api):
    _client, world = api
    job = _job(
        world,
        result={
            "message": "Outstanding purchase order import completed",
            "upload": {
                "ok": True,
                "product_ids": ["11111111-1111-1111-1111-111111111111"],
                "scope_documents": ["202607-S0070", "202607-S0039"],
            },
        },
    )

    with _as_purchasing(world) as buyer:
        response = buyer.get(_url(job))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["finished"] is True
    assert body["product_ids"] == ["11111111-1111-1111-1111-111111111111"]
    # Sorted, so the same upload always sends the same URL to the purchase-order list.
    assert body["documents"] == ["202607-S0039", "202607-S0070"]
    assert body["document_count"] == 2


def test_the_history_channel_spelling_is_read_too(api):
    """`po_history_service` states `documents`; the outstanding channel states
    `scope_documents`. One reader, both books."""
    _client, world = api
    job = _job(
        world,
        job_type="po_history_import",
        result={"upload": {"ok": True, "product_ids": ["p-1"], "documents": ["SPO-2026/08-0061"]}},
    )

    with _as_purchasing(world) as buyer:
        response = buyer.get(_url(job))

    assert response.status_code == 200, response.text
    assert response.json()["documents"] == ["SPO-2026/08-0061"]


def test_a_job_still_running_is_not_finished_and_names_nothing(api):
    """The page shows its two next steps on `finished`, so a running job must not claim
    to be one - and it has written no result to read either."""
    _client, world = api
    job = _job(world, status=JobStatus.STARTED.value, result=None)

    with _as_purchasing(world) as buyer:
        response = buyer.get(_url(job))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["finished"] is False
    assert body["product_ids"] == [] and body["documents"] == []


def test_a_failed_job_is_finished_and_says_it_wrote_nothing(api):
    """Nobody is waiting on it any more, which is what `finished` means - the alert says
    the book could not be read, and there is nothing to link or to go and look at."""
    _client, world = api
    job = _job(world, status=JobStatus.FAILED.value, result=None)

    with _as_purchasing(world) as buyer:
        response = buyer.get(_url(job))

    assert response.status_code == 200, response.text
    assert response.json()["finished"] is True
    assert response.json()["product_ids"] == []


def test_an_unknown_job_is_a_404(api):
    _client, world = api
    with _as_purchasing(world) as buyer:
        response = buyer.get(f"{LIST}/upload-jobs/{uuid.uuid4()}")
    assert response.status_code == 404, response.text


def test_a_cs_user_is_refused(api):
    """AC-H3: asking what an upload wrote is how the buyer decides what to link, and CS
    does neither."""
    cs_client, world = api
    job = _job(world, result={"upload": {"product_ids": []}})
    assert cs_client.get(_url(job)).status_code == 403


def test_the_purchase_order_list_narrows_to_the_documents_it_is_given(api):
    """The other half of "Open purchase orders": the list shows that upload's orders and
    not the other thirteen thousand."""
    _client, world = api
    supplier = _supplier(world)
    numbers = [f"ZZT-PO-{_uid()[:8]}" for _ in range(3)]
    for number in numbers:
        world.db.add(
            PurchaseOrder(
                id=_uid(),
                company_id=world.company_id,
                po_number=number,
                supplier_id=supplier.id,
                issue_date=date(2026, 6, 1),
                status="active",
            )
        )
    world.db.commit()

    service = PurchaseOrderService(world.db)
    narrowed = service.list(
        1, 50, None, "desc", None, None, None, documents=numbers[:2]
    )
    assert {row["po_number"] for row in narrowed["data"]} == set(numbers[:2])

    # A named set that resolved to nothing is an empty answer, never the whole book.
    empty = service.list(1, 50, None, "desc", None, None, None, documents=[])
    assert empty["data"] == []

    # And omitting it changes nothing about how this list has always read.
    unfiltered = service.list(1, 50, None, "desc", None, None, None)
    assert unfiltered["pagination"]["total"] >= 3


def test_the_documents_filter_composes_with_the_lists_other_filters(api):
    """It is a filter like any other, not a mode: a status the named orders do not have
    still empties the page."""
    _client, world = api
    supplier = _supplier(world)
    number = f"ZZT-PO-{_uid()[:8]}"
    world.db.add(
        PurchaseOrder(
            id=_uid(),
            company_id=world.company_id,
            po_number=number,
            supplier_id=supplier.id,
            issue_date=date(2026, 6, 1),
            status="active",
        )
    )
    world.db.commit()

    service = PurchaseOrderService(world.db)
    assert service.list(
        1, 50, None, "desc", None, "active", None, documents=[number]
    )["data"]
    assert (
        service.list(1, 50, None, "desc", None, "cancelled", None, documents=[number])[
            "data"
        ]
        == []
    )
