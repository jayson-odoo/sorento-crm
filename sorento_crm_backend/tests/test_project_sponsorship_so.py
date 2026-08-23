"""P12 Group K: an approved sponsorship form becomes a sales order (AC-K1, AC-K2, AC-K3).

Group J (pre-order) is withdrawn - the client does not want pre-orders as sales orders
(D26) - so this file is the whole of P12's build.

Three claims worth pinning, all of them things a commercial draft does differently:

* **Price is zero and stays zero.** A sponsorship is a giveaway. The quotation price and
  quantity checks are skipped because there is no quotation to check against, but product
  resolution still runs: a code nobody stocks is a hard stop whether or not money changes
  hands (AC-K2).
* **It starts in `awaiting_costing` and cannot publish from there** (AC-K3, D28). Accounts
  has to attend to it before it reaches AutoCount.
* **A month becomes the LAST DAY of that month** (D29), never the first: netting is FIFO by
  delivery date, so the last day cannot claim covering stock ahead of a dated commercial
  line in the same month.

Postgres, blank scratch schema, rolled back at teardown. Every FK target is seeded here.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.procurement import PurchaseRequestHeader, PurchaseRequestLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    SO_STATUS_AWAITING_COSTING,
    SO_STATUS_DRAFT,
    SO_STATUS_READY,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SODraftFinding,
)
from app.models.user import User
from app.services import project_seed_service
from app.services.error_handler import AppException
from app.services.project_so_draft_service import ProjectSODraftService, month_end

from ._pg_fixture import blank_session

MARKER = "zzt-spon"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = db.execute(text("select id from companies where code='SRT'")).scalar()
        project_seed_service.run(db, company_id=company_id)
        user_id = _uid()
        db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} Accounts"))
        db.flush()
        yield db, company_id, user_id


def _product(db, code: str, *, active: bool = True) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=code,
        product_name=f"{MARKER} {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
        is_active=active,
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
        title=f"{MARKER} Tuju Residences {_uid()[:12]}",
    )


def _form(
    db,
    project,
    *,
    approval_status: str | None = "approved",
    delivery: date | None = date(2027, 5, 20),
    lines: list[tuple[str, str]] | None = None,
) -> PurchaseRequestHeader:
    form = PurchaseRequestHeader(
        id=_uid(),
        request_type="sponsorship_form",
        request_number=f"PSSF{_uid()[:6]}",
        request_date=date(2026, 8, 1),
        project_id=project.id if project else None,
        project_title=project.title if project else f"{MARKER} unlinked",
        customer_name=f"{MARKER} SLG",
        sponsor_subject="showroom",
        status="submitted",
        approval_status=approval_status,
        expected_delivery_date=delivery,
    )
    db.add(form)
    db.flush()
    for index, (code, qty) in enumerate(lines or [], start=1):
        db.add(
            PurchaseRequestLine(
                id=_uid(),
                purchase_request_id=form.id,
                item_code=code,
                quantity=Decimal(qty),
                sort_order=index,
            )
        )
    db.flush()
    return form


def _lines_of(db, order) -> list[ProjectSalesOrderLine]:
    return (
        db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == order.id)
        .order_by(ProjectSalesOrderLine.line_no)
        .all()
    )


def _findings(db, order) -> list[SODraftFinding]:
    return (
        db.query(SODraftFinding)
        .filter(SODraftFinding.project_sales_order_id == order.id)
        .all()
    )


# --------------------------------------------------------------------------- #
# D29 - a month becomes a date                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "year,month,expected",
    [
        (2027, 1, date(2027, 1, 31)),
        (2027, 4, date(2027, 4, 30)),
        (2027, 2, date(2027, 2, 28)),
        (2028, 2, date(2028, 2, 29)),  # leap year, or the date does not exist
        (2027, 12, date(2027, 12, 31)),
    ],
)
def test_a_month_resolves_to_its_last_day(year, month, expected):
    assert month_end(year, month) == expected


# --------------------------------------------------------------------------- #
# AC-K1                                                                        #
# --------------------------------------------------------------------------- #


def test_an_approved_form_produces_a_draft_at_price_zero(seeded):
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    grating = _product(db, "CB6633")
    form = _form(db, project, lines=[("CB6633", "20")])

    order = ProjectSODraftService(db).build_from_sponsorship_form(
        form.id, actor_user_id=user_id
    )

    assert order.is_sponsorship is True
    assert order.sponsorship_form_id == form.id
    assert order.project_id == project.id
    lines = _lines_of(db, order)
    assert [(line.product_id, line.qty) for line in lines] == [
        (grating.id, Decimal("20.0000"))
    ]
    assert lines[0].unit_price == Decimal("0")
    assert lines[0].amount == Decimal("0")
    assert order.total_amount == Decimal("0.00")


def test_the_form_number_is_carried_so_accounts_can_find_the_document(seeded):
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, lines=[("CB6633", "5")])

    order = ProjectSODraftService(db).build_from_sponsorship_form(
        form.id, actor_user_id=user_id
    )

    assert form.request_number in (order.provisional_ref or "")


def test_a_line_price_on_the_form_is_ignored(seeded):
    """A sponsorship form may carry an indicative value. The SO is still a giveaway."""
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, lines=[("CB6633", "20")])
    line = db.query(PurchaseRequestLine).filter_by(purchase_request_id=form.id).one()
    line.unit_price = Decimal("12.50")
    line.total = Decimal("250.00")
    db.flush()

    order = ProjectSODraftService(db).build_from_sponsorship_form(
        form.id, actor_user_id=user_id
    )

    assert _lines_of(db, order)[0].unit_price == Decimal("0")


def test_the_delivery_date_comes_from_the_form(seeded):
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, delivery=date(2027, 5, 20), lines=[("CB6633", "5")])

    order = ProjectSODraftService(db).build_from_sponsorship_form(
        form.id, actor_user_id=user_id
    )

    assert _lines_of(db, order)[0].delivery_date == date(2027, 5, 20)


def test_a_form_with_no_delivery_date_leaves_the_line_undated(seeded):
    """Undated demand is served LAST by the netting engine, which is the honest
    position: an undated giveaway cannot claim stock ahead of a dated delivery."""
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, delivery=None, lines=[("CB6633", "5")])

    order = ProjectSODraftService(db).build_from_sponsorship_form(
        form.id, actor_user_id=user_id
    )

    assert _lines_of(db, order)[0].delivery_date is None


def test_rebuilding_replaces_the_draft_rather_than_adding_a_second(seeded):
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, lines=[("CB6633", "20")])
    service = ProjectSODraftService(db)

    first = service.build_from_sponsorship_form(form.id, actor_user_id=user_id)
    second = service.build_from_sponsorship_form(form.id, actor_user_id=user_id)

    assert first.id == second.id
    orders = (
        db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.sponsorship_form_id == form.id)
        .all()
    )
    assert len(orders) == 1
    assert len(_lines_of(db, second)) == 1


def test_a_form_that_is_not_approved_is_refused(seeded):
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, approval_status="pending", lines=[("CB6633", "20")])

    with pytest.raises(AppException) as exc:
        ProjectSODraftService(db).build_from_sponsorship_form(
            form.id, actor_user_id=user_id
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "sponsorship_not_approved"


def test_a_form_with_no_project_is_refused(seeded):
    """The project is the anchor (D18). Without one there is nothing to hang it on."""
    db, company_id, user_id = seeded
    _product(db, "CB6633")
    form = _form(db, None, lines=[("CB6633", "20")])

    with pytest.raises(AppException) as exc:
        ProjectSODraftService(db).build_from_sponsorship_form(
            form.id, actor_user_id=user_id
        )

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "sponsorship_no_project"


def test_a_form_with_no_lines_is_refused(seeded):
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    form = _form(db, project, lines=[])

    with pytest.raises(AppException) as exc:
        ProjectSODraftService(db).build_from_sponsorship_form(
            form.id, actor_user_id=user_id
        )

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "sponsorship_has_no_lines"


def test_a_purchase_request_is_not_a_sponsorship_form(seeded):
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, lines=[("CB6633", "20")])
    form.request_type = "purchase_request"
    db.flush()

    with pytest.raises(AppException) as exc:
        ProjectSODraftService(db).build_from_sponsorship_form(
            form.id, actor_user_id=user_id
        )

    assert exc.value.status_code == 422


# --------------------------------------------------------------------------- #
# AC-K2                                                                        #
# --------------------------------------------------------------------------- #


def test_an_unstocked_code_is_still_a_hard_stop(seeded):
    """Product resolution survives (AC-K2): a code nobody stocks cannot be shipped,
    whether or not money changes hands."""
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    form = _form(db, project, lines=[("NOT-A-PRODUCT", "20")])

    order = ProjectSODraftService(db).build_from_sponsorship_form(
        form.id, actor_user_id=user_id
    )

    codes = {finding.code for finding in _findings(db, order)}
    assert "unresolved_product" in codes
    assert _lines_of(db, order)[0].product_id is None


def test_a_discontinued_product_is_reported(seeded):
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "OLD-CODE", active=False)
    form = _form(db, project, lines=[("OLD-CODE", "20")])

    order = ProjectSODraftService(db).build_from_sponsorship_form(
        form.id, actor_user_id=user_id
    )

    codes = {finding.code for finding in _findings(db, order)}
    assert "product_discontinued" in codes


def test_no_quotation_finding_is_raised(seeded):
    """AC-K2: price and quantity checks are skipped. There is no quotation to check."""
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, lines=[("CB6633", "20")])

    order = ProjectSODraftService(db).build_from_sponsorship_form(
        form.id, actor_user_id=user_id
    )

    codes = {finding.code for finding in _findings(db, order)}
    assert codes.isdisjoint({"price_vs_quotation", "code_vs_quotation", "total_mismatch"})


def test_a_price_of_zero_does_not_read_as_an_arithmetic_error(seeded):
    """`line_arithmetic` compares qty x price against the amount. Both are zero here, and
    a giveaway must not be blocked by the check that protects commercial lines."""
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, lines=[("CB6633", "20")])

    order = ProjectSODraftService(db).build_from_sponsorship_form(
        form.id, actor_user_id=user_id
    )

    codes = {finding.code for finding in _findings(db, order)}
    assert "line_arithmetic" not in codes


# --------------------------------------------------------------------------- #
# AC-K3 and D28                                                                #
# --------------------------------------------------------------------------- #


def test_a_sponsorship_draft_starts_awaiting_costing(seeded):
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, lines=[("CB6633", "20")])

    order = ProjectSODraftService(db).build_from_sponsorship_form(
        form.id, actor_user_id=user_id
    )

    assert order.status == SO_STATUS_AWAITING_COSTING


def test_it_cannot_publish_while_awaiting_costing(seeded):
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, lines=[("CB6633", "20")])
    service = ProjectSODraftService(db)
    order = service.build_from_sponsorship_form(form.id, actor_user_id=user_id)

    with pytest.raises(AppException) as exc:
        service.publish(order, actor_user_id=user_id)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "so_awaiting_costing"


def test_confirming_the_costing_releases_it_to_the_normal_gate(seeded):
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, lines=[("CB6633", "20")])
    service = ProjectSODraftService(db)
    order = service.build_from_sponsorship_form(form.id, actor_user_id=user_id)

    service.confirm_costing(order, actor_user_id=user_id)

    # Nothing outstanding on this draft, so the normal gate lands it on ready.
    assert order.status == SO_STATUS_READY
    published = service.publish(order, actor_user_id=user_id)
    assert published["status"] == "published"


def test_confirming_the_costing_still_respects_a_hard_stop(seeded):
    """Releasing it for costing is not a way around the arithmetic gate."""
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    form = _form(db, project, lines=[("NOT-A-PRODUCT", "20")])
    service = ProjectSODraftService(db)
    order = service.build_from_sponsorship_form(form.id, actor_user_id=user_id)

    service.confirm_costing(order, actor_user_id=user_id)

    assert order.status != SO_STATUS_READY
    with pytest.raises(AppException) as exc:
        service.publish(order, actor_user_id=user_id)
    assert exc.value.detail["code"] == "so_publish_blocked"


def test_confirming_the_costing_twice_is_refused(seeded):
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    _product(db, "CB6633")
    form = _form(db, project, lines=[("CB6633", "20")])
    service = ProjectSODraftService(db)
    order = service.build_from_sponsorship_form(form.id, actor_user_id=user_id)
    service.confirm_costing(order, actor_user_id=user_id)

    with pytest.raises(AppException) as exc:
        service.confirm_costing(order, actor_user_id=user_id)

    assert exc.value.status_code == 409


def test_a_commercial_order_is_never_awaiting_costing(seeded):
    """The status belongs to the sponsorship path only. A commercial draft that landed
    in it could never publish, and nobody would know why."""
    db, company_id, user_id = seeded
    project = _project(db, company_id, user_id)
    order = ProjectSalesOrder(
        id=_uid(),
        company_id=company_id,
        project_id=project.id,
        provisional_ref=f"ZZT-{_uid()[:8]}",
        status=SO_STATUS_DRAFT,
        grouping_origin="area",
    )
    db.add(order)
    db.flush()

    with pytest.raises(AppException) as exc:
        ProjectSODraftService(db).confirm_costing(order, actor_user_id=user_id)

    assert exc.value.status_code == 409
