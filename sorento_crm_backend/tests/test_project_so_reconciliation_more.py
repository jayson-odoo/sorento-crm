"""Stage 1B reconciliation gap coverage (STAGE1B-scm-front-planning-reconciliation.md,
UAC-scm-front-planning.md AC-A01..AC-A04). Fills what
``test_project_so_reconciliation.py`` / ``test_project_so_reconciliation_routes.py`` do
not already exercise:

- `list_fulfilment_planning` / `GET /project-sales/fulfilment-planning`: ``query``
  matches provisional ref, AutoCount doc no and area group; ``project_id`` filter;
  pagination total is the FILTERED count when ``review_state`` is given; draft/blocked
  SOs are excluded (only published/amended); company scoping.
- ``review_state`` / ``exception_count`` propagate through the build and regroup
  responses, and a draft SO's detail reads ``awaiting_reconciliation`` without crashing.
- Ingest of a DIVERGENT document still links lines, because reconcile runs before the
  comparison (`ProjectSOIngestService.ingest`).

Postgres, blank scratch schema via ``tests/_pg_fixture.py::blank_session``, rolled back
at teardown. Every FK target is seeded here; nothing is borrowed from an existing row.
Seeding helpers are reused from the sibling files rather than copied, per the repo's own
established idiom (``test_project_so_worksheet.py`` imports from ``test_project_so_draft``).
"""
from __future__ import annotations

from decimal import Decimal

from app.models.base import company_scope
from app.models.company import Company
from app.models.order import SalesOrder, SalesOrderLine
from app.models.project_so import (
    SO_STATUS_AMENDED,
    SO_STATUS_BLOCKED,
    SO_STATUS_DRAFT,
    SO_STATUS_PUBLISHED,
    ProjectSalesOrderLine,
)
from app.services import project_seed_service
from app.services.project_so_draft_service import ProjectSODraftService

from ._pg_fixture import blank_session
from .test_project_so_divergence import MAR, OUTCOME_DIVERGENT, ProjectSOIngestService
from .test_project_so_divergence import _customer as _div_customer
from .test_project_so_divergence import _document as _div_document
from .test_project_so_divergence import _line as _div_line
from .test_project_so_divergence import _order as _div_order
from .test_project_so_divergence import _po as _div_po
from .test_project_so_divergence import _product as _div_product
from .test_project_so_divergence import _project as _div_project
from .test_project_so_divergence import _their as _div_their
from .test_project_so_draft import _minimal as _draft_minimal
from .test_project_so_reconciliation import (
    D1,
    _core_line,
    _core_order,
    _product,
    _project,
    _project_line,
    _project_order,
    _sorento,
    _uid,
    _user,
)
from .test_project_so_reconciliation_routes import (
    BASE,
    EDIT,
    VIEW,
    _client,
    _restore,
)

MARKER = "zzt-so-recon-more"


# --------------------------------------------------------------------------- #
# GET /fulfilment-planning: query matching                                    #
# --------------------------------------------------------------------------- #


def test_query_matches_the_provisional_ref():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        project = _project(db, company_id, owner)
        product = _product(db)
        target = _project_order(db, project, area_group="TOWER")
        _project_line(db, target, product, line_no=1, delivery_date=D1)
        other = _project_order(db, project, area_group="PODIUM")
        _project_line(db, other, product, line_no=1, delivery_date=D1)
        db.commit()

        client, originals = _client(db, owner, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BASE}/fulfilment-planning",
                    params={"query": target.provisional_ref},
                )
                assert response.status_code == 200, response.text
                ids = {row["id"] for row in response.json()["data"]}
                assert ids == {target.id}
        finally:
            _restore(originals)


def test_query_matches_the_autocount_doc_no():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        project = _project(db, company_id, owner)
        product = _product(db)
        doc_no = f"ZZT-DOCNO-{_uid()[:8]}"
        target = _project_order(db, project, autocount_doc_no=doc_no)
        _project_line(db, target, product, line_no=1, delivery_date=D1)
        other = _project_order(db, project, autocount_doc_no=None)
        _project_line(db, other, product, line_no=1, delivery_date=D1)
        db.commit()

        client, originals = _client(db, owner, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BASE}/fulfilment-planning", params={"query": doc_no}
                )
                assert response.status_code == 200, response.text
                ids = {row["id"] for row in response.json()["data"]}
                assert ids == {target.id}
        finally:
            _restore(originals)


def test_query_matches_the_area_group():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        project = _project(db, company_id, owner)
        product = _product(db)
        area = f"ZZT-AREA-{_uid()[:8]}"
        target = _project_order(db, project, area_group=area)
        _project_line(db, target, product, line_no=1, delivery_date=D1)
        other = _project_order(db, project, area_group="PODIUM")
        _project_line(db, other, product, line_no=1, delivery_date=D1)
        db.commit()

        client, originals = _client(db, owner, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BASE}/fulfilment-planning", params={"query": area}
                )
                assert response.status_code == 200, response.text
                ids = {row["id"] for row in response.json()["data"]}
                assert ids == {target.id}
        finally:
            _restore(originals)


# --------------------------------------------------------------------------- #
# GET /fulfilment-planning: project_id filter                                 #
# --------------------------------------------------------------------------- #


def test_project_id_filters_the_list_to_that_project_only():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        product = _product(db)
        project_a = _project(db, company_id, owner)
        order_a = _project_order(db, project_a, area_group="TOWER")
        _project_line(db, order_a, product, line_no=1, delivery_date=D1)
        project_b = _project(db, company_id, owner)
        order_b = _project_order(db, project_b, area_group="TOWER")
        _project_line(db, order_b, product, line_no=1, delivery_date=D1)
        db.commit()

        client, originals = _client(db, owner, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BASE}/fulfilment-planning", params={"project_id": project_a.id}
                )
                assert response.status_code == 200, response.text
                ids = {row["id"] for row in response.json()["data"]}
                assert ids == {order_a.id}
        finally:
            _restore(originals)


# --------------------------------------------------------------------------- #
# GET /fulfilment-planning: pagination total is the FILTERED count            #
# --------------------------------------------------------------------------- #


def test_pagination_total_is_the_filtered_count_when_review_state_is_given():
    """3 needs_cs_review orders, 2 awaiting: filtering to needs_cs_review with a page
    size of 1 must report ``total: 3`` (the filtered count), not 5 (unfiltered) and
    not 1 (the page size)."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        project = _project(db, company_id, owner)
        product = _product(db)

        for _ in range(3):
            core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
            _core_line(db, core_order, product, required_date=D1)
            complete = _project_order(
                db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
            )
            _project_line(db, complete, product, line_no=1, delivery_date=D1)

        for _ in range(2):
            awaiting = _project_order(db, project, autocount_doc_no=None, so_id=None)
            _project_line(db, awaiting, product, line_no=1, delivery_date=D1)

        db.commit()

        client, originals = _client(db, owner, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BASE}/fulfilment-planning",
                    params={"review_state": "needs_cs_review", "page": 1, "limit": 1},
                )
                assert response.status_code == 200, response.text
                body = response.json()
                assert len(body["data"]) == 1
                assert body["pagination"]["total"] == 3
        finally:
            _restore(originals)


def test_pagination_without_a_review_state_filter_pages_the_orders_themselves():
    """No ``review_state`` filter means the ORM query is paginated before anything is
    derived, so a page is a page of the whole set: three published orders at a page
    size of two are two rows then one, a reported total of three, and no order on both
    pages (the ``id`` tiebreak makes the split stable)."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        project = _project(db, company_id, owner)
        product = _product(db)

        seeded = []
        for _ in range(3):
            order = _project_order(db, project, autocount_doc_no=None, so_id=None)
            _project_line(db, order, product, line_no=1, delivery_date=D1)
            seeded.append(order.id)
        db.commit()

        client, originals = _client(db, owner, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                first = client.get(
                    f"{BASE}/fulfilment-planning", params={"page": 1, "limit": 2}
                )
                second = client.get(
                    f"{BASE}/fulfilment-planning", params={"page": 2, "limit": 2}
                )
                assert first.status_code == 200, first.text
                assert second.status_code == 200, second.text
                page_one = [row["id"] for row in first.json()["data"]]
                page_two = [row["id"] for row in second.json()["data"]]
                assert len(page_one) == 2
                assert len(page_two) == 1
                assert first.json()["pagination"]["total"] == 3
                assert set(page_one) | set(page_two) == set(seeded)
        finally:
            _restore(originals)


# --------------------------------------------------------------------------- #
# GET /fulfilment-planning: draft/blocked SOs are excluded                    #
# --------------------------------------------------------------------------- #


def test_draft_and_blocked_sos_are_excluded_only_published_and_amended_show():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        project = _project(db, company_id, owner)
        product = _product(db)

        draft = _project_order(db, project, status=SO_STATUS_DRAFT)
        _project_line(db, draft, product, line_no=1, delivery_date=D1)
        blocked = _project_order(db, project, status=SO_STATUS_BLOCKED)
        _project_line(db, blocked, product, line_no=1, delivery_date=D1)
        published = _project_order(db, project, status=SO_STATUS_PUBLISHED)
        _project_line(db, published, product, line_no=1, delivery_date=D1)
        amended = _project_order(db, project, status=SO_STATUS_AMENDED)
        _project_line(db, amended, product, line_no=1, delivery_date=D1)
        db.commit()

        client, originals = _client(db, owner, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(f"{BASE}/fulfilment-planning")
                assert response.status_code == 200, response.text
                ids = {row["id"] for row in response.json()["data"]}
                assert ids == {published.id, amended.id}
                assert draft.id not in ids
                assert blocked.id not in ids
        finally:
            _restore(originals)


# --------------------------------------------------------------------------- #
# GET /fulfilment-planning: company scoping                                   #
# --------------------------------------------------------------------------- #


def test_an_so_of_another_company_never_appears_in_the_list():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        project = _project(db, company_id, owner)
        product = _product(db)

        ours = _project_order(db, project, area_group="TOWER")
        _project_line(db, ours, product, line_no=1, delivery_date=D1)

        other_company_id = _uid()
        db.add(
            Company(
                id=other_company_id,
                name=f"{MARKER} other co",
                code=f"ZZT{_uid()[:6]}",
            )
        )
        db.flush()
        foreign = _project_order(db, project, area_group="TOWER")
        foreign.company_id = other_company_id
        _project_line(db, foreign, product, line_no=1, delivery_date=D1)
        db.commit()

        client, originals = _client(db, owner, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(f"{BASE}/fulfilment-planning")
                assert response.status_code == 200, response.text
                ids = {row["id"] for row in response.json()["data"]}
                assert ours.id in ids
                assert foreign.id not in ids
        finally:
            _restore(originals)


# --------------------------------------------------------------------------- #
# review_state / exception_count propagate through build + regroup            #
# --------------------------------------------------------------------------- #


def test_the_build_route_response_rows_carry_no_review_state_while_they_are_drafts():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        _project_unused, _product_unused, po, schedule = _draft_minimal(
            db, company_id, owner
        )
        db.commit()

        client, originals = _client(db, owner, [VIEW, EDIT])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.post(
                    f"{BASE}/purchase-orders/{po.id}/build-sales-orders",
                    json={"schedule_version_id": schedule.id},
                )
                assert response.status_code == 201, response.text
                body = response.json()
                assert body["data"], "expected at least one drafted sales order"
                for row in body["data"]:
                    # A draft has not left the building, so there is no AutoCount
                    # document for it to disagree with and no state to read (AC-A03).
                    assert row["review_state"] is None
                    assert row["exception_count"] == 0
        finally:
            _restore(originals)


def test_the_regroup_route_response_rows_carry_no_review_state_while_they_are_drafts():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        _project_unused, _product_unused, po, schedule = _draft_minimal(
            db, company_id, owner
        )
        built = ProjectSODraftService(db).build(po.id, schedule.id)
        order_id = built["data"][0]["id"]
        lines = (
            db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == order_id)
            .all()
        )
        db.commit()

        client, originals = _client(db, owner, [VIEW, EDIT])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.post(
                    f"{BASE}/sales-orders/{order_id}/regroup",
                    json={
                        "groups": [
                            {
                                "line_ids": [line.id for line in lines],
                                "area_group": "TOWER",
                            }
                        ]
                    },
                )
                assert response.status_code == 200, response.text
                body = response.json()
                assert body, "expected at least one regrouped sales order"
                for row in body:
                    assert row["review_state"] is None
                    assert row["exception_count"] == 0
        finally:
            _restore(originals)


def test_a_draft_so_detail_carries_no_review_state_at_all():
    """AC-A02/AC-A03. A draft is not reconciled against anything: it has no AutoCount
    document, it is excluded from the fulfilment worklist, and its detail must carry NO
    review state rather than an "awaiting reconciliation" it has not earned. The screen
    renders no pill without one."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        project = _project(db, company_id, owner)
        product = _product(db)
        order = _project_order(db, project, status=SO_STATUS_DRAFT)
        _project_line(db, order, product, line_no=1, delivery_date=D1)
        db.commit()

        client, originals = _client(db, owner, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(f"{BASE}/sales-orders/{order.id}")
                assert response.status_code == 200, response.text
                body = response.json()
                assert body["review_state"] is None
                assert body["exception_count"] == 0
        finally:
            _restore(originals)


# --------------------------------------------------------------------------- #
# AC-A01: ingest of a DIVERGENT document still links lines                    #
# --------------------------------------------------------------------------- #


def test_ingest_of_a_divergent_document_still_links_the_project_lines():
    """`ProjectSOIngestService.ingest` calls `reconcile_core_order` (adopts `so_id`)
    and then `ProjectSOReconciliationService.reconcile` BEFORE `compare()` runs, so a
    document whose quantity disagrees with ours (OUTCOME_DIVERGENT) still gets the
    Project line linked to the real core sales order line. Seeded the same shape
    ``test_project_so_divergence.py``'s own ``scenario`` fixture uses: one published
    sales order, one line, 600 units at 12.50."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        actor = _user(db)
        project = _div_project(db, company_id, actor)
        customer = _div_customer(db, f"ZZTC{_uid()[:6]}")
        po = _div_po(db, project, customer, po_number=f"PO-778-{_uid()[:6]}")
        order = _div_order(db, project, po)
        product = _div_product(db, f"CB{_uid()[:6]}")
        project_line = _div_line(db, order, product, "600", "12.50")
        order.total_amount = Decimal("7500.00")
        db.flush()

        doc_no = f"ZZT-SO-{_uid()[:8]}"
        core_order = SalesOrder(id=_uid(), so_number=doc_no, status="open")
        if order.company_id is not None:
            core_order.company_id = order.company_id
        db.add(core_order)
        db.flush()
        core_line = SalesOrderLine(
            id=_uid(),
            sales_order_id=core_order.id,
            product_id=product.id,
            qty_ordered=Decimal("600"),
            qty_delivered=Decimal("0"),
            required_date=MAR,
        )
        if core_order.company_id is not None:
            core_line.company_id = core_order.company_id
        db.add(core_line)
        db.flush()

        document = _div_document(
            doc_no=doc_no,
            customer_code=customer.customer_code,
            po_number=po.po_number,
            lines=[_div_their(product.product_code, "550", "12.50")],
        )
        result = ProjectSOIngestService(db).ingest(document, actor_user_id=actor)

        assert result.outcome == OUTCOME_DIVERGENT

        db.refresh(order)
        assert order.so_id == core_order.id

        db.refresh(project_line)
        assert project_line.core_sales_order_line_id == core_line.id
