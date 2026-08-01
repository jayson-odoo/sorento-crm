"""P6 delivery-schedule intake: extraction, reconciliation and phases (UAC group E).

Four rules carry the design, and every test below is one of them:

- **Reconciliation is per COLUMN, never per document** (AC-E3, measured 2026-08-02).
  29 of 37 columns reconciled on the first vision pass of the real R1 schedule. A
  document-level accept would have rejected it, and every other real schedule with it.
- **The checksum has two independent sources**: the schedule's own TOTAL QTY row,
  transcribed rather than computed, and the PO quantity for the same product.
- **It reconciles against the PO VERSION the schedule NAMES** (finding G1), not the
  current amended state. A schedule issued before a handwritten cancellation still
  reconciles, because the customer considers it correct.
- **Phase identity is `(area_group, sequence)`, never the label** (finding G6). The
  COMMON AREA rows carry no label at all, and matching by label collapsed three real
  phases into one.

The unit tests feed the persistence layer a canned page payload shaped exactly like the
extractor's output, so they never call the live model. One further test DOES call it,
against the client's own committed schedule, and is skipped without a key.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.order import Customer
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    CustomerItemCodeMap,
    DeliverySchedule,
    DeliveryScheduleCell,
    DeliveryScheduleVersion,
    ProjectDeliveryPhase,
    ProjectPOLine,
    ProjectPOVersion,
)
from app.models.projects import ProjectParty
from app.models.user import User
from app.services import project_seed_service
from app.services.error_handler import AppException
from app.services.project_schedule_service import ProjectScheduleService, parse_text_matrix

from ._pg_fixture import blank_session

MARKER = "zzt-schedule"

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "sorento_crm_frontend"
    / "e2e"
    / "fixtures"
    / "project-cs"
)


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _product(db, code: str, name: str) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Set")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=code,
        product_name=name,
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _customer(db, company_id: str) -> Customer:
    row = Customer(
        id=_uid(),
        company_id=company_id,
        customer_code=f"ZZT-{_uid()[:8]}",
        customer_name=f"{MARKER} Buimaco",
    )
    db.add(row)
    db.flush()
    return row


def _project(db, company_id: str, owner: str):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Tuju {_uid()[:6]}",
    )


def _po_with_version(db, project, owner: str, customer, lines):
    """A customer PO, its issuer bridged to a debtor, and one extracted document version.

    ``lines`` is ``[(product, qty)]``. The PO quantity a schedule column reconciles
    against comes from THESE rows: the version the schedule names, as printed.
    """
    from app.services import project_po_service as pos

    party = ProjectParty(
        id=_uid(),
        company_id=project.company_id,
        party_type="main_contractor",
        name=f"{MARKER} contractor {_uid()[:6]}",
        customer_id=customer.id,
    )
    db.add(party)
    db.flush()

    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "po_source": "contractor_direct",
            "issuing_party_id": party.id,
            "po_number": f"ZZT-PO-{_uid()[:6]}",
            "po_date": date(2026, 1, 16),
        },
    )
    version = ProjectPOVersion(
        id=_uid(), company_id=project.company_id, purchase_order_id=po.id, version_no=1,
        extraction_state="done",
    )
    db.add(version)
    db.flush()
    for index, (product, qty) in enumerate(lines, start=1):
        db.add(
            ProjectPOLine(
                id=_uid(),
                company_id=project.company_id,
                po_version_id=version.id,
                line_no=index,
                stock_code_raw=product.product_code,
                qty=Decimal(qty),
                resolved_product_id=product.id,
                resolution_source="code",
            )
        )
    db.flush()
    return po, version


def _schedule_version(db, project, po, po_version, *, version_no=1, label=None):
    schedule = (
        db.query(DeliverySchedule)
        .filter(DeliverySchedule.purchase_order_id == po.id)
        .first()
    )
    if schedule is None:
        schedule = DeliverySchedule(
            id=_uid(),
            company_id=project.company_id,
            project_id=project.id,
            purchase_order_id=po.id,
        )
        db.add(schedule)
        db.flush()
    version = DeliveryScheduleVersion(
        id=_uid(),
        company_id=project.company_id,
        delivery_schedule_id=schedule.id,
        version_no=version_no,
        revision_label=label,
        po_version_id=po_version.id,
        extraction_state="queued",
    )
    db.add(version)
    db.flush()
    return version


def _page(products, phases, cells, totals) -> dict:
    """One page of the extractor's answer, in its own JSON shape."""
    return {
        "header": {"po_ref": "HQ 26/01/121", "schedule_date": "2026-03-04"},
        "products": products,
        "phases": phases,
        "cells": cells,
        "reported_totals": totals,
    }


def _two_column_page(*, wc_cells, basin_cells, wc_total, basin_total):
    """The shape of every unit test below: two products, two TOWER rows, two
    UNLABELED COMMON AREA rows. The unlabeled pair is finding G6 in miniature."""
    return _page(
        products=[
            {"col": 1, "customer_code": "BUI-HB-SRTWC8613-RL", "code": "SRTWC8613-RL",
             "name": "One-Piece WC"},
            {"col": 2, "customer_code": "BUI-HB-SRTWB7055", "code": "SRTWB7055",
             "name": "Counter-Top Basin"},
        ],
        phases=[
            {"row": 1, "area_group": "TOWER", "label": "Level 2 & 7",
             "delivery_date": "2026-07-01"},
            {"row": 2, "area_group": "TOWER", "label": "Level 8 & 10",
             "delivery_date": "2026-08-03"},
            {"row": 3, "area_group": "COMMON AREA", "label": None,
             "delivery_date": "2026-07-01"},
            {"row": 4, "area_group": "COMMON AREA", "label": None,
             "delivery_date": "2027-06-01"},
        ],
        cells=(
            [{"row": row, "col": 1, "qty": qty} for row, qty in wc_cells]
            + [{"row": row, "col": 2, "qty": qty} for row, qty in basin_cells]
        ),
        totals=[{"col": 1, "qty": wc_total}, {"col": 2, "qty": basin_total}],
    )


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Yana")
        yield db, company_id, owner


@pytest.fixture()
def scenario(seeded):
    """A project, a PO version quoting 200 WC and 100 basins, and an empty schedule."""
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    customer = _customer(db, company_id)
    # The client's real codes: the whole point of the `BUI-HB-` prefix is that our code
    # is printed inside theirs, and a made-up code would not exercise that.
    wc = _product(db, "SRTWC8613-RL", "One-Piece WC")
    basin = _product(db, "SRTWB7055", "Counter-Top Basin")
    po, po_version = _po_with_version(
        db, project, owner, customer, [(wc, "200"), (basin, "100")]
    )
    version = _schedule_version(db, project, po, po_version)
    return {
        "db": db,
        "owner": owner,
        "project": project,
        "customer": customer,
        "wc": wc,
        "basin": basin,
        "po": po,
        "po_version": po_version,
        "version": version,
    }


def _columns(detail):
    return {c["customer_code_raw"]: c for c in detail["products"]}


def _phase(detail, area_group: str, sequence: int):
    """Phases are addressed by (area_group, sequence), never by sequence alone: every
    area group numbers its own rows from one."""
    return next(
        p
        for p in detail["phases"]
        if p["area_group"] == area_group and p["sequence"] == sequence
    )


# ------------------------------------------------------------------ reconciliation


def test_a_column_reconciles_against_the_reported_total_and_the_po(scenario):
    """AC-E3. Both checks agree, so the column is clean and nobody is asked anything."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _two_column_page(
        wc_cells=[(1, 120), (2, 80)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    detail = service.get_version_detail(scenario["version"].id)
    columns = _columns(detail)
    wc = columns["BUI-HB-SRTWC8613-RL"]

    assert wc["column_total"] == "200"
    assert wc["reported_total"] == "200"
    assert wc["po_qty"] == "200"
    assert wc["reconciled"] is True
    assert detail["reconciliation"] == {"reconciled_columns": 2, "total_columns": 2}


def test_a_failing_column_is_flagged_without_failing_the_others(scenario):
    """The measured reason the design is per column: 8 of 37 columns failed on the real
    R1 and a document-level reject would have thrown away the other 29."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _two_column_page(
        wc_cells=[(1, 120), (2, 75)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    columns = _columns(service.get_version_detail(scenario["version"].id))
    assert columns["BUI-HB-SRTWC8613-RL"]["reconciled"] is False
    assert columns["BUI-HB-SRTWC8613-RL"]["column_total"] == "195"
    assert columns["BUI-HB-SRTWB7055"]["reconciled"] is True

    version = db.get(DeliveryScheduleVersion, scenario["version"].id)
    assert version.reconciled_columns == 1
    assert version.total_columns == 2


def test_an_empty_cell_is_never_stored_as_a_zero(scenario):
    """A blank means this phase does not take this product. Writing zeroes would make
    every phase look like it was planned for every product."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _two_column_page(
        wc_cells=[(1, 120), (2, 80)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    cells = (
        db.query(DeliveryScheduleCell)
        .filter(DeliveryScheduleCell.version_id == scenario["version"].id)
        .all()
    )
    # Four filled cells out of eight possible: the other four were blank on the page.
    assert len(cells) == 4
    assert all(cell.qty != 0 for cell in cells)


def test_the_schedule_reconciles_against_the_po_version_it_names(scenario):
    """Finding G1. The named version still carries the 200 the schedule was drawn from;
    a later version cancelling half of it must not retrospectively reject this document."""
    db = scenario["db"]
    service = ProjectScheduleService(db)

    later = ProjectPOVersion(
        id=_uid(),
        company_id=scenario["project"].company_id,
        purchase_order_id=scenario["po"].id,
        version_no=2,
        extraction_state="done",
    )
    db.add(later)
    db.flush()
    db.add(
        ProjectPOLine(
            id=_uid(),
            company_id=scenario["project"].company_id,
            po_version_id=later.id,
            line_no=1,
            stock_code_raw=scenario["wc"].product_code,
            qty=Decimal("100"),
            resolved_product_id=scenario["wc"].id,
        )
    )
    db.flush()

    page = _two_column_page(
        wc_cells=[(1, 120), (2, 80)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    columns = _columns(service.get_version_detail(scenario["version"].id))
    assert columns["BUI-HB-SRTWC8613-RL"]["po_qty"] == "200"
    assert columns["BUI-HB-SRTWC8613-RL"]["reconciled"] is True


def test_a_quantity_cancelled_on_the_named_version_still_reconciles_and_is_reported(
    scenario,
):
    """AC-E3a. The cancelled quantity stays visible as a note rather than silently
    changing the number the schedule is measured against."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    line = (
        db.query(ProjectPOLine)
        .filter(
            ProjectPOLine.po_version_id == scenario["po_version"].id,
            ProjectPOLine.resolved_product_id == scenario["wc"].id,
        )
        .first()
    )
    line.is_cancelled = True
    db.flush()

    page = _two_column_page(
        wc_cells=[(1, 120), (2, 80)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    columns = _columns(service.get_version_detail(scenario["version"].id))
    wc = columns["BUI-HB-SRTWC8613-RL"]
    assert wc["reconciled"] is True
    assert wc["cancelled_qty"] == "200"
    assert "cancelled" in (wc["note"] or "").lower()


# ------------------------------------------------------------------------- phases


def test_two_unlabeled_common_area_rows_stay_two_phases(scenario):
    """Finding G6, measured: matching on the label collapsed three real COMMON AREA
    rows into one. Identity is (area_group, sequence)."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _two_column_page(
        wc_cells=[(1, 120), (2, 80)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    common = (
        db.query(ProjectDeliveryPhase)
        .filter(
            ProjectDeliveryPhase.project_id == scenario["project"].id,
            ProjectDeliveryPhase.area_group == "COMMON AREA",
        )
        .order_by(ProjectDeliveryPhase.sequence)
        .all()
    )
    assert [p.sequence for p in common] == [1, 2]
    assert [p.label for p in common] == [None, None]
    assert [p.delivery_date for p in common] == [date(2026, 7, 1), date(2027, 6, 1)]


def test_re_extracting_a_version_does_not_duplicate_its_phases(scenario):
    """Phases are upserted on their identity: a re-read after a prompt change must not
    leave the project with two of every row."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _two_column_page(
        wc_cells=[(1, 120), (2, 80)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    phases = (
        db.query(ProjectDeliveryPhase)
        .filter(ProjectDeliveryPhase.project_id == scenario["project"].id)
        .all()
    )
    assert len(phases) == 4
    cells = (
        db.query(DeliveryScheduleCell)
        .filter(DeliveryScheduleCell.version_id == scenario["version"].id)
        .count()
    )
    assert cells == 4


# ------------------------------------------------------------- customer code map


def test_a_remembered_customer_code_resolves_the_next_schedule_by_itself(scenario):
    """AC-E4. A human identifies `BUI-HB-*` once per customer; the next schedule from
    that customer resolves silently and says that is what happened."""
    db = scenario["db"]
    service = ProjectScheduleService(db)

    # A code our catalogue cannot recover on its own: nothing in it matches a product.
    page = _page(
        products=[{"col": 1, "customer_code": "BUI-HB-XX9931", "code": None,
                   "name": "Mystery item"}],
        phases=[{"row": 1, "area_group": "TOWER", "label": "Level 2 & 7",
                 "delivery_date": "2026-07-01"}],
        cells=[{"row": 1, "col": 1, "qty": 200}],
        totals=[{"col": 1, "qty": 200}],
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    columns = service.get_version_detail(scenario["version"].id)["products"]
    assert columns[0]["product_id"] is None
    assert columns[0]["resolution_source"] is None

    service.resolve_product_column(
        scenario["version"].id, 0, scenario["wc"].id, actor_user_id=scenario["owner"]
    )
    db.flush()

    mapped = (
        db.query(CustomerItemCodeMap)
        .filter(CustomerItemCodeMap.customer_code == "BUI-HB-XX9931")
        .first()
    )
    assert mapped is not None
    assert mapped.customer_id == scenario["customer"].id
    assert mapped.product_id == scenario["wc"].id

    # Second schedule from the same customer: nobody is asked again.
    second = _schedule_version(
        db, scenario["project"], scenario["po"], scenario["po_version"], version_no=2
    )
    service.persist_pages(second, [(1, page)])
    db.flush()

    columns = service.get_version_detail(second.id)["products"]
    assert columns[0]["product_id"] == scenario["wc"].id
    assert columns[0]["resolution_source"] == "map"
    assert columns[0]["product_code"] == scenario["wc"].product_code


def test_a_column_resolves_from_the_code_inside_the_customers_own(scenario):
    """`BUI-HB-SRTWC8613-RL` carries our code. Recovering it needs no map and no model."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _page(
        products=[{"col": 1, "customer_code": f"BUI-HB-{scenario['wc'].product_code}",
                   "code": None, "name": "One-Piece WC"}],
        phases=[{"row": 1, "area_group": "TOWER", "label": "Level 2 & 7",
                 "delivery_date": "2026-07-01"}],
        cells=[{"row": 1, "col": 1, "qty": 200}],
        totals=[{"col": 1, "qty": 200}],
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    column = service.get_version_detail(scenario["version"].id)["products"][0]
    assert column["product_id"] == scenario["wc"].id
    assert column["resolution_source"] == "code"


# --------------------------------------------------------------- addressing a column


def test_every_cell_says_which_column_it_belongs_to(scenario):
    """An unidentified column has no product id, so keying the grid on product alone
    leaves it rendering empty while still showing a total, which reads as a bug."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _page(
        products=[{"col": 1, "customer_code": "BUI-HB-XX9931", "code": None, "name": "Mystery"}],
        phases=[{"row": 1, "area_group": "TOWER", "label": "Level 2 & 7",
                 "delivery_date": "2026-07-01"}],
        cells=[{"row": 1, "col": 1, "qty": 200}],
        totals=[{"col": 1, "qty": 200}],
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    detail = service.get_version_detail(scenario["version"].id)
    assert detail["products"][0]["product_index"] == 0
    assert detail["products"][0]["product_id"] is None
    assert detail["cells"][0]["product_index"] == 0
    assert detail["cells"][0]["product_id"] is None


def test_an_unidentified_column_can_be_corrected_by_its_index(scenario):
    """The column nobody has named yet is exactly the column somebody is fixing."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _page(
        products=[{"col": 1, "customer_code": "BUI-HB-XX9931", "code": None, "name": "Mystery"}],
        phases=[{"row": 1, "area_group": "TOWER", "label": "Level 2 & 7",
                 "delivery_date": "2026-07-01"}],
        cells=[{"row": 1, "col": 1, "qty": 190}],
        totals=[{"col": 1, "qty": 200}],
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    detail = service.get_version_detail(scenario["version"].id)
    phase_one = _phase(detail, "TOWER", 1)
    service.update_cells(
        scenario["version"].id,
        [{"phase_id": phase_one["id"], "product_index": 0, "qty": "200"}],
    )
    db.flush()

    detail = service.get_version_detail(scenario["version"].id)
    assert detail["products"][0]["column_total"] == "200"
    assert [cell["qty"] for cell in detail["cells"]] == ["200"]


# ----------------------------------------------------------------------- listings


def test_a_project_lists_its_schedules_with_the_po_that_named_them(scenario):
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _two_column_page(
        wc_cells=[(1, 120), (2, 80)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    rows = service.list_schedules(scenario["project"].id)
    assert len(rows) == 1
    assert rows[0]["po_number"] == scenario["po"].po_number
    assert rows[0]["latest_version_no"] == 1
    assert rows[0]["version_count"] == 1
    assert (rows[0]["reconciled_columns"], rows[0]["total_columns"]) == (2, 2)

    second = _schedule_version(
        db, scenario["project"], scenario["po"], scenario["po_version"],
        version_no=2, label="REVISED 1",
    )
    db.flush()
    rows = service.list_schedules(scenario["project"].id)
    assert rows[0]["version_count"] == 2
    assert rows[0]["latest_version_id"] == second.id

    history = service.list_versions(rows[0]["id"])
    assert [row["version_no"] for row in history] == [2, 1]
    assert history[0]["revision_label"] == "REVISED 1"


# ----------------------------------------------------------------- cell correction


def test_correcting_a_cell_flips_the_column_to_reconciled(scenario):
    """The per-column correction path: CS fixes the cells the checksum named, and the
    column stops being a problem without anyone touching the other 36."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _two_column_page(
        wc_cells=[(1, 120), (2, 75)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    detail = service.get_version_detail(scenario["version"].id)
    assert _columns(detail)["BUI-HB-SRTWC8613-RL"]["reconciled"] is False
    phase_two = _phase(detail, "TOWER", 2)

    service.update_cells(
        scenario["version"].id,
        [{"phase_id": phase_two["id"], "product_id": scenario["wc"].id, "qty": "80"}],
    )
    db.flush()

    columns = _columns(service.get_version_detail(scenario["version"].id))
    assert columns["BUI-HB-SRTWC8613-RL"]["column_total"] == "200"
    assert columns["BUI-HB-SRTWC8613-RL"]["reconciled"] is True


def test_a_cell_set_to_zero_is_deleted_rather_than_stored(scenario):
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _two_column_page(
        wc_cells=[(1, 120), (2, 80)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    detail = service.get_version_detail(scenario["version"].id)
    phase_two = _phase(detail, "TOWER", 2)
    service.update_cells(
        scenario["version"].id,
        [{"phase_id": phase_two["id"], "product_id": scenario["wc"].id, "qty": "0"}],
    )
    db.flush()

    remaining = (
        db.query(DeliveryScheduleCell)
        .filter(
            DeliveryScheduleCell.version_id == scenario["version"].id,
            DeliveryScheduleCell.phase_id == phase_two["id"],
            DeliveryScheduleCell.product_id == scenario["wc"].id,
        )
        .count()
    )
    assert remaining == 0


# ------------------------------------------------------------------------ confirm


def test_confirm_is_refused_while_a_column_is_unreconciled(scenario):
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _two_column_page(
        wc_cells=[(1, 120), (2, 75)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    with pytest.raises(AppException) as excinfo:
        service.confirm(scenario["version"].id, actor_user_id=scenario["owner"])
    assert excinfo.value.status_code == 409
    assert "BUI-HB-SRTWC8613-RL" in str(excinfo.value.detail)


def test_confirm_proceeds_when_the_failure_is_acknowledged_with_a_reason(scenario):
    """A person may still be right about a column the arithmetic doubts, but their name
    and their reason go on the record."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _two_column_page(
        wc_cells=[(1, 120), (2, 75)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    service.confirm(
        scenario["version"].id,
        actor_user_id=scenario["owner"],
        acknowledge_unreconciled=True,
        reason="Customer confirmed 75 by email on 4 March",
    )
    db.flush()

    version = db.get(DeliveryScheduleVersion, scenario["version"].id)
    assert version.confirmed_at is not None
    assert version.confirmed_by == scenario["owner"]
    assert (
        version.reconciliation_json["acknowledgement"]["reason"]
        == "Customer confirmed 75 by email on 4 March"
    )


def test_acknowledging_without_a_reason_is_refused(scenario):
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _two_column_page(
        wc_cells=[(1, 120), (2, 75)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    db.flush()

    with pytest.raises(AppException) as excinfo:
        service.confirm(
            scenario["version"].id,
            actor_user_id=scenario["owner"],
            acknowledge_unreconciled=True,
            reason="   ",
        )
    assert excinfo.value.status_code == 422


def test_confirm_is_refused_while_part_of_the_document_is_unread(scenario):
    """A page that did not answer takes its whole columns with it, so nothing flags
    them. Binding that would commit a schedule with products silently missing."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    page = _two_column_page(
        wc_cells=[(1, 120), (2, 80)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, page)])
    scenario["version"].extraction_state = "partial"
    scenario["version"].extraction_error = "Pages 5, 6 could not be read."
    db.flush()

    with pytest.raises(AppException) as excinfo:
        service.confirm(scenario["version"].id, actor_user_id=scenario["owner"])
    assert excinfo.value.status_code == 409
    assert "Pages 5, 6" in str(excinfo.value.detail)

    service.confirm(
        scenario["version"].id,
        actor_user_id=scenario["owner"],
        acknowledge_unreconciled=True,
        reason="Pages 5 and 6 keyed in by hand from the fax",
    )
    db.flush()
    version = db.get(DeliveryScheduleVersion, scenario["version"].id)
    assert version.reconciliation_json["acknowledgement"]["partial_read"] is True


def test_confirm_promotes_the_dates_this_version_carries(scenario):
    """A revision moves dates. The phase row keeps the OLD date until somebody confirms
    the new document, so the delta engine still has both ends of the move."""
    db = scenario["db"]
    service = ProjectScheduleService(db)
    first = _two_column_page(
        wc_cells=[(1, 120), (2, 80)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    service.persist_pages(scenario["version"], [(1, first)])
    service.confirm(scenario["version"].id, actor_user_id=scenario["owner"])
    db.flush()

    revised = _two_column_page(
        wc_cells=[(1, 120), (2, 80)], basin_cells=[(3, 60), (4, 40)],
        wc_total=200, basin_total=100,
    )
    revised["phases"][0]["delivery_date"] = "2027-01-07"
    second = _schedule_version(
        db, scenario["project"], scenario["po"], scenario["po_version"],
        version_no=2, label="REVISED 1",
    )
    service.persist_pages(second, [(1, revised)])
    db.flush()

    phase = (
        db.query(ProjectDeliveryPhase)
        .filter(
            ProjectDeliveryPhase.project_id == scenario["project"].id,
            ProjectDeliveryPhase.area_group == "TOWER",
            ProjectDeliveryPhase.sequence == 1,
        )
        .first()
    )
    assert phase.delivery_date == date(2026, 7, 1)

    detail = service.get_version_detail(second.id)
    row = [p for p in detail["phases"] if p["sequence"] == 1 and p["area_group"] == "TOWER"][0]
    assert row["delivery_date"] == "2027-01-07"
    assert row["promoted_delivery_date"] == "2026-07-01"

    service.confirm(second.id, actor_user_id=scenario["owner"])
    db.flush()
    db.refresh(phase)
    assert phase.delivery_date == date(2027, 1, 7)


# --------------------------------------------------------------- the text layer


@pytest.mark.parametrize(
    "filename, expected_columns, floor",
    [
        # MEASURED 2026-08-02 on the client's own documents. Pure vision managed 29/37
        # on R1 and 35/38 on R2 (PLAN 5c); the text layer is why intake is hybrid.
        ("delivery-schedule-buimaco-r1.pdf", 38, 36),
        ("delivery-schedule-slg-r2.pdf", 39, 37),
    ],
)
def test_the_text_layer_reproduces_the_real_schedule_matrix(
    filename, expected_columns, floor
):
    """The schedules HAVE a text layer, so quantities are read from it geometrically and
    vision is left to do structure.

    The remainders are not misreads: they are columns whose total the customer wrote as
    prose rather than as a number, so there is nothing to compare against.
    """
    content = (FIXTURES / filename).read_bytes()
    pages = parse_text_matrix(content, "application/pdf")

    assert len(pages) == 7
    matched = 0
    columns = 0
    for page in pages.values():
        assert len(page.rows) == 15  # 12 TOWER + 3 COMMON AREA, on every page
        for index in range(page.column_count):
            columns += 1
            total = sum(
                (row.get(index, Decimal(0)) for row in page.rows), Decimal(0)
            )
            if page.totals.get(index) is not None and total == page.totals[index]:
                matched += 1
    assert columns == expected_columns
    assert matched >= floor


def test_a_page_whose_printed_totals_all_agree_is_trusted_for_its_whole_grid():
    """The corroboration rule: a page's grid is proven by the columns that carry a
    printed total. Where every one of them agrees, the columns with no printed total
    are transcribed from the same proven grid rather than left to vision."""
    content = (FIXTURES / "delivery-schedule-buimaco-r1.pdf").read_bytes()
    pages = parse_text_matrix(content, "application/pdf")

    # Page 6 carries a column whose total the customer wrote as prose; every other
    # column on it agrees, so the page is proven.
    assert pages[6].grid_proven is True
    # Page 5 carries a row the label column does not show, so one column comes up short
    # and the page is NOT trusted: those columns stay with vision and reach CS.
    assert pages[5].grid_proven is False


# ------------------------------------------------------- the real document, live


@pytest.mark.skipif(
    not __import__("app.config", fromlist=["settings"]).settings.gemini_api_key,
    reason="needs GEMINI_API_KEY: this one reads the real document with the real model",
)
def test_the_real_r1_schedule_extracts_and_reconciles(seeded):
    """The golden set as an acceptance test (PLAN 5a), end to end and unmocked.

    MEASURED 2026-08-02, `gemini-2.5-flash` plus the text-layer cross-check, over the
    client's own R1: 37 columns after the two identically-headed Grab Bar columns merge,
    35 of them equal to the schedule's own printed TOTAL QTY row, 15 phases, no failed
    pages. Vision alone managed 29 of 37 (PLAN 5c). The floors below ARE that
    measurement, not an aspiration; raise them only after re-measuring.

    Products are NOT seeded, so every column is unresolved and the PO half of the
    checksum cannot fire. What this pins is the transcription of the matrix, which is
    the part of the job this slice owns.
    """
    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    customer = _customer(db, company_id)
    po, po_version = _po_with_version(db, project, owner, customer, [])
    version = _schedule_version(db, project, po, po_version)
    content = (FIXTURES / "delivery-schedule-buimaco-r1.pdf").read_bytes()

    service = ProjectScheduleService(db)
    result = service.persist_pages(
        version,
        service.read_document(content, "application/pdf"),
        text_pages=parse_text_matrix(content, "application/pdf"),
    )
    db.flush()

    detail = service.get_version_detail(version.id)
    matching = [
        column
        for column in detail["products"]
        if column["reported_total"] is not None
        and column["column_total"] == column["reported_total"]
    ]
    print(
        f"\nreal R1: {len(detail['products'])} columns, {len(matching)} match the "
        f"printed TOTAL QTY row, {len(detail['phases'])} phases, "
        f"failed pages={result.get('failed_pages')}, "
        f"quantities from={detail['products'] and version.reconciliation_json['qty_source']}"
    )
    for column in detail["products"]:
        if column in matching:
            continue
        print(
            f"  unmatched: {column['customer_code_raw']} "
            f"page {column['qty_source']} sum={column['column_total']} "
            f"reported={column['reported_total']}"
        )
    assert len(detail["products"]) >= 37
    assert len(matching) >= 35
    assert len(detail["phases"]) == 15
