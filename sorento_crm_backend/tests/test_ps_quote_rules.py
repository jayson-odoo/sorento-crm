"""PS-QUOTE-RULES (CARD-ps-quote-rules-02nov.md), written BEFORE the implementation.

B1. A line outside the project's series needs a manager's approval (the existing
    ``projects.quotations.approve`` grant, nobody hard-coded) before the quotation can be sent.
B2. Asking for approval of a discount (a line below its minimum price) puts the project in Final
    Negotiation: the critical flag is raised and the stage moves forward to the
    ``final_negotiation`` rung when the graph has one. Withdrawn or rejected, it stays there.

Postgres only, via ``blank_session``; every row carries the ``zzt-qrules`` marker.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.product import Product, ProductCategory
from app.models.projects import ProjectSeries
from app.models.status import Status
from app.services.error_handler import AppException

from ._pg_fixture import blank_session
from .test_project_quotation_approval import (
    ABOVE_FLOOR,
    BELOW_FLOOR,
    EVERYTHING,
    LIST_PRICE,
    _setup,
    _sign,
    _status,
    _user,
)

MARKER = "zzt-qrules"


def _uid() -> str:
    return str(uuid.uuid4())


def _series_around(db, company_id: str, scope, product: Product) -> None:
    """Nominate a series on the scope whose category holds ``product``."""
    from app.services import project_pricing_service as pricing

    series = ProjectSeries(id=_uid(), company_id=company_id, name=f"{MARKER} Premium")
    db.add(series)
    db.flush()
    pricing.set_series_categories(db, series=series, category_ids=[product.category_id])
    scope.series_id = series.id
    db.flush()


def _outsider(db, product: Product) -> Product:
    """A product in a category the series does not nominate."""
    category = ProductCategory(
        id=_uid(),
        category_code=f"ZZT-{_uid()[:8]}",
        category_name=f"{MARKER} Kitchen Sinks",
    )
    db.add(category)
    db.flush()
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} Sink",
        category_id=category.id,
        base_uom_id=product.base_uom_id,
        list_price=Decimal(LIST_PRICE),
    )
    db.add(row)
    db.flush()
    return row


def _line(db, scope, product, owner, unit_price: str):
    from app.services import project_quotation_service as quotes

    return quotes.upsert_line(
        db,
        version=quotes.current_version(db, scope.id),
        actor_user_id=owner,
        payload={"product_id": product.id, "unit_price": unit_price, "quantity": 2},
    )


def _ladder(db) -> dict:
    """Prod's ladder on top of the seeded one: final_negotiation and sponsorship_form after
    tendering, terminal rungs after them (prod made these in the admin editor)."""
    rows = {
        s.key: s
        for s in db.query(Status)
        .filter(Status.entity_type == "project", Status.scope_id.is_(None))
        .all()
    }
    for key, order in (("po_received", 7), ("lost", 8), ("dormant", 9)):
        rows[key].sort_order = order
    for key, label, order in (
        ("final_negotiation", "Final Negotiation", 5),
        ("sponsorship_form", "Sponsorship Form", 6),
    ):
        if key not in rows:
            rows[key] = Status(
                id=_uid(),
                entity_type="project",
                scope_id=None,
                key=key,
                label=label,
                sort_order=order,
            )
            db.add(rows[key])
    db.flush()
    return rows


def _ask(db, document, owner) -> None:
    from app.services import project_quotation_approval_service as approval

    approval.move(
        db,
        document=document,
        to_status_id=_status(db, "pending_approval").id,
        actor_user_id=owner,
    )


# ------------------------------------------------------------------------- B1


def test_an_off_series_line_at_default_price_blocks_issue_until_approved():
    from app.services import project_quotation_approval_service as approval
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        company_id, owner, product, _, document, scope = _setup(db)
        _series_around(db, company_id, scope, product)
        _line(db, scope, product, owner, ABOVE_FLOOR)
        line = _line(db, scope, _outsider(db, product), owner, LIST_PRICE)
        assert line.is_non_standard is True
        assert line.is_below_floor is False

        assert approval.off_series_line_count(db, document) == 1
        assert approval.below_floor_line_count(db, document) == 0
        assert approval.requires_approval(db, document) is True

        _sign(db, document, owner)
        with pytest.raises(AppException) as refused:
            qdocs.issue(db, document=document, actor_user_id=owner)
        assert refused.value.status_code == 422
        assert refused.value.detail["code"] == "quotation_off_series_pending_approval"
        assert "outside the project's series" in refused.value.message
        assert qdocs.current_issue(db, document) is None

        manager = _user(db, f"{MARKER} Manager")
        _ask(db, document, owner)
        approval.approve(db, document=document, actor_user_id=manager, permissions=EVERYTHING)
        assert qdocs.issue(db, document=document, actor_user_id=owner).issue_no == 1
        # Issuing spends the approval, exactly as for the minimum price.
        assert approval.current_key(db, document) == "issued"


def test_in_series_lines_and_a_project_without_series_are_not_gated():
    from app.services import project_quotation_approval_service as approval
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        company_id, owner, product, _, document, scope = _setup(db)
        # No series nominated: nothing is off-series, even a product from anywhere.
        _line(db, scope, _outsider(db, product), owner, ABOVE_FLOOR)
        assert approval.off_series_line_count(db, document) == 0
        assert approval.requires_approval(db, document) is False
        _sign(db, document, owner)
        assert qdocs.issue(db, document=document, actor_user_id=owner).issue_no == 1
        db.refresh(document)
        assert document.approval_status_id is None


def test_mixed_reasons_one_approval_and_the_message_names_both():
    from app.services import project_quotation_approval_service as approval
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        company_id, owner, product, _, document, scope = _setup(db)
        _series_around(db, company_id, scope, product)
        _line(db, scope, product, owner, BELOW_FLOOR)
        _line(db, scope, _outsider(db, product), owner, LIST_PRICE)
        _sign(db, document, owner)
        with pytest.raises(AppException) as refused:
            qdocs.issue(db, document=document, actor_user_id=owner)
        # The minimum-price code stays the code whenever a line is below it (the screen and
        # older clients already handle it); the message names both reasons.
        assert refused.value.detail["code"] == "quotation_below_floor_pending_approval"
        assert "outside the project's series" in refused.value.message
        assert "below the minimum price" in refused.value.message

        block = approval.serialize_approval(db, document)
        assert block["requires_approval"] is True
        assert block["below_floor_line_count"] == 1
        assert block["off_series_line_count"] == 1


def test_an_off_series_approval_request_is_recorded_with_its_counts():
    from app.models.activities import ActivityEvent
    from app.services import project_quotation_approval_service as approval

    with blank_session() as db:
        company_id, owner, product, project, document, scope = _setup(db)
        _series_around(db, company_id, scope, product)
        _line(db, scope, _outsider(db, product), owner, LIST_PRICE)
        _ask(db, document, owner)
        row = (
            db.query(ActivityEvent)
            .filter(
                ActivityEvent.entity_id == str(project.id),
                ActivityEvent.system_template == "quotation_approval_requested",
            )
            .one()
        )
        assert row.system_payload["off_series_line_count"] == 1
        assert row.system_payload["below_floor_line_count"] == 0
        assert "outside the project's series" in (row.body_text or "")
        assert approval.current_key(db, document) == "pending_approval"


# ------------------------------------------------------------------------- B2


def _project_key(db, project) -> str:
    db.refresh(project)
    return db.query(Status).filter(Status.id == project.status_id).one().key


def _put_on(db, project, rows, key) -> None:
    project.status_id = rows[key].id
    db.flush()


def test_a_discount_request_moves_the_project_to_final_negotiation_and_raises_the_flag():
    from app.models.activities import ActivityEvent

    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        rows = _ladder(db)
        _put_on(db, project, rows, "specified")
        _line(db, scope, product, owner, BELOW_FLOOR)
        assert project.is_critical is False

        _ask(db, document, owner)

        assert _project_key(db, project) == "final_negotiation"
        assert project.is_critical is True
        assert project.critical_at is not None
        moved = (
            db.query(ActivityEvent)
            .filter(
                ActivityEvent.entity_id == str(project.id),
                ActivityEvent.system_template == "stage_changed",
            )
            .one()
        )
        assert str(moved.actor_id) == owner
        assert moved.system_payload["to_status_id"] == str(rows["final_negotiation"].id)


def test_an_off_series_only_request_is_not_a_discount():
    with blank_session() as db:
        company_id, owner, product, project, document, scope = _setup(db)
        rows = _ladder(db)
        _put_on(db, project, rows, "specified")
        _series_around(db, company_id, scope, product)
        _line(db, scope, _outsider(db, product), owner, LIST_PRICE)

        _ask(db, document, owner)

        assert _project_key(db, project) == "specified"
        assert project.is_critical is False


@pytest.mark.parametrize("key", ["sponsorship_form", "po_received", "final_negotiation"])
def test_a_project_at_or_past_final_negotiation_keeps_its_stage(key):
    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        rows = _ladder(db)
        _put_on(db, project, rows, key)
        _line(db, scope, product, owner, BELOW_FLOOR)

        _ask(db, document, owner)

        assert _project_key(db, project) == key
        assert project.is_critical is True


def test_without_a_final_negotiation_rung_only_the_flag_is_raised():
    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        before = _project_key(db, project)
        _line(db, scope, product, owner, BELOW_FLOOR)

        _ask(db, document, owner)

        assert _project_key(db, project) == before
        assert project.is_critical is True


def test_the_flag_clock_is_not_reset_by_a_second_request():
    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        _line(db, scope, product, owner, BELOW_FLOOR)
        project.is_critical = True
        from datetime import datetime

        project.critical_at = datetime(2026, 10, 1, 9, 0)
        db.flush()

        _ask(db, document, owner)

        assert project.critical_at == datetime(2026, 10, 1, 9, 0)


@pytest.mark.parametrize("ending", ["reject", "withdraw"])
def test_a_rejected_or_withdrawn_discount_leaves_the_project_in_final_negotiation(ending):
    from app.services import project_quotation_approval_service as approval

    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        rows = _ladder(db)
        _put_on(db, project, rows, "quoted")
        _line(db, scope, product, owner, BELOW_FLOOR)
        _ask(db, document, owner)
        assert _project_key(db, project) == "final_negotiation"

        manager = _user(db, f"{MARKER} Manager")
        if ending == "reject":
            approval.reject(
                db,
                document=document,
                actor_user_id=manager,
                reason="Too deep, try 5% less",
                permissions=EVERYTHING,
            )
        else:
            approval.revise_approval(db, document, owner, "Customer agreed list price")

        assert _project_key(db, project) == "final_negotiation"
        assert project.is_critical is True


def test_a_resubmitted_discount_after_rejection_also_moves_a_project_that_was_moved_back():
    from app.services import project_quotation_approval_service as approval

    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        rows = _ladder(db)
        _put_on(db, project, rows, "quoted")
        _line(db, scope, product, owner, BELOW_FLOOR)
        _ask(db, document, owner)
        manager = _user(db, f"{MARKER} Manager")
        approval.reject(
            db, document=document, actor_user_id=manager, reason="No", permissions=EVERYTHING
        )
        # Somebody moved it back by hand meanwhile.
        _put_on(db, project, rows, "quoted")

        _ask(db, document, owner)  # resubmit

        assert approval.current_key(db, document) in {"resubmitted", "pending_approval"}
        assert _project_key(db, project) == "final_negotiation"
