"""OI-ONE-DELIVERY-DATE: the readers that print or sort a date (AC-A3 per-project, A4, A5,
A7, A10 to A12, D1).

TEST-FIRST. A red is a reader still printing the row's stored (told) date, never a fixture
bug. Every chain is seeded here (`tests/_oi_one_date_seed.py`).

Not covered here, named so nobody thinks it is: the handover Excel attachment and the
worklist / per-project Excel and PDF exports (AC-A5/A9) read the same fields the tests below
pin (OI-EXPORT-SHARED, #2146, owns those files). The undo email and confirm preview (AC-A6),
the matrix (AC-A3), the link window and demand legs (AC-A8) and the sheet re-upload (AC-C1)
are pinned in `tests/test_oi_one_delivery_date_legs.py`.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models.project_so import OrderInquiryRow

from ._oi_one_date_seed import Chain, MARKER, NO_CORE, digits
from ._pg_fixture import blank_session, unique_code
from .test_oi_handover_resend import (  # noqa: F401  (fixture + helpers)
    PREVIEW,
    _automation,
    _oi,
    _ok,
    rs,
)
from .test_order_inquiry_reserve import (  # noqa: F401  (fixture + helpers)
    REQUEST_URL,
    _captured_dispatches,
    _register,
    _requested_calls,
    api,
)

__all__ = ["rs", "api"]

OLD = date(2026, 7, 1)
NEW = date(2027, 1, 7)
FAR = date(2030, 1, 1)


def _fmt(value: date) -> str:
    return value.strftime("%d/%m/%Y")


# --------------------------------------------------------------------------- per project


def test_per_project_list_prints_and_sorts_by_the_so_line_date():
    """AC-A1, AC-A2 for the per-project list: `ProjectOrderInquiryService.list_rows` (default
    sort "delivery_date") and `serialize_rows`."""
    from app.models.base import company_scope
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService
    from app.models.projects import Project, ProjectLead

    from .test_order_inquiry_worklist import _sorento

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            lead = ProjectLead(
                lead_code=unique_code("lead"),
                title=f"{MARKER} lead",
                normalised_title=unique_code("zzt lead"),
            )
            db.add(lead)
            db.flush()
            project = Project(
                project_code=unique_code("proj"),
                title=f"{MARKER} project",
                normalised_title=unique_code("zzt project"),
                lead_id=lead.id,
            )
            db.add(project)
            db.flush()
            chain = Chain(db, company_id)
            chain.pso.project_id = project.id
            db.flush()
            plan = [  # (told, line date): told order is the reverse of the line order
                (date(2026, 9, 1), date(2027, 3, 1)),
                (date(2026, 10, 1), date(2027, 2, 1)),
                (date(2026, 11, 1), FAR),
            ]
            ids = []
            for told, line_date in plan:
                _core, line = chain.add_line(core_date=line_date, mirror_date=line_date)
                ids.append(chain.add_row(line, told=told).id)
            db.commit()

            service = ProjectOrderInquiryService(db)
            rows, total = service.list_rows(project.id, sort="delivery_date", direction="asc")
            assert total == 3
            assert [r["id"] for r in rows] == [ids[1], ids[0], ids[2]]
            by_id = {r["id"]: r for r in rows}
            assert by_id[ids[0]]["delivery_date"] == date(2027, 3, 1)
            assert by_id[ids[2]]["delivery_date"] == FAR, "AC-A10: 2030-01-01 as it is"
            assert by_id[ids[0]]["previous_delivery_date"] == date(2026, 9, 1)

            desc, _ = service.list_rows(project.id, sort="delivery_date", direction="desc")
            assert [r["id"] for r in desc] == [ids[2], ids[0], ids[1]]


# --------------------------------------------------------------------------- reserve


def test_reserve_request_context_prints_and_sorts_by_the_so_line_date(api, monkeypatch):
    """AC-A4: `reserve.rows[]` and the merged `reserve.lines` carry the SO line date, and the
    merged table sorts by it. Same item code on both rows, so the date decides the order."""
    from app.services.order_inquiry_reserve_service import merged_context

    client, world = api
    _register()
    calls = _captured_dispatches(monkeypatch)
    chain = Chain(world.db, world.company_id)
    _c1, late_line = chain.add_line(core_date=NEW, mirror_date=NEW)
    _c2, early_line = chain.add_line(core_date=date(2026, 12, 1), mirror_date=date(2026, 12, 1))
    # Told dates are reversed against the line dates.
    late = chain.add_row(
        late_line, told=date(2026, 7, 1), inquiry=world.inquiry,
        item_code="ZZT-OD-RESERVE", stock_location=world.site.warehouse_code,
    )
    early = chain.add_row(
        early_line, told=date(2026, 8, 1), inquiry=world.inquiry,
        item_code="ZZT-OD-RESERVE", stock_location=world.site.warehouse_code,
    )
    world.db.commit()

    response = client.post(
        REQUEST_URL(world.inquiry.id),
        json={
            "rows": [
                {"row_id": r.id, "qty_requested": "10", "warehouse_id": world.site.id}
                for r in (late, early)
            ],
            "note": None,
        },
    )
    assert response.status_code == 201, response.text
    world.db.commit()

    matches = _requested_calls(calls)
    assert len(matches) == 1
    context = matches[0]["context"]
    printed = sorted(r["delivery_date"] for r in context["reserve"]["rows"])
    assert printed == sorted([_fmt(NEW), _fmt(date(2026, 12, 1))])
    iso = {r["delivery_iso"] for r in context["reserve"]["rows"]}
    assert iso == {NEW.isoformat(), "2026-12-01"}

    lines = merged_context([context])["reserve"]["lines"]
    assert [l["delivery_date"] for l in lines] == [_fmt(date(2026, 12, 1)), _fmt(NEW)], (
        "sorted by the SO line date, not the told date"
    )


# --------------------------------------------------------------------------- handover


def test_handover_item_line_prints_the_so_line_date():
    """AC-A5 (email = preview = attachment all read `handover_item`), AC-A10, AC-A12."""
    from app.models.base import company_scope
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    from .test_order_inquiry_worklist import _sorento

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            chain = Chain(db, company_id)
            _c, moved = chain.add_line(core_date=NEW, mirror_date=NEW)
            _c, lagging = chain.add_line(core_date=FAR, mirror_date=date(2026, 6, 1))
            _c, no_core = chain.add_line(core_date=NO_CORE, mirror_date=date(2027, 3, 3))
            moved_row = chain.add_row(moved, told=OLD)
            lag_row = chain.add_row(lagging, told=date(2026, 6, 1))
            mirror_row = chain.add_row(no_core, told=OLD)
            db.commit()
            service = ProjectOrderInquiryService(db)

            assert service.handover_item(moved_row, kind="raised")["line"]["delivery_date"] == _fmt(NEW)
            assert service.handover_item(lag_row, kind="raised")["line"]["delivery_date"] == "01/01/2030"
            assert service.handover_item(mirror_row, kind="raised")["line"]["delivery_date"] == "03/03/2027"


def test_handover_settled_line_prints_the_so_date_and_keeps_the_old_one_as_was():
    """AC-A5: a line whose SO date moved prints the old date as WAS (DELIVERY DATE) and the
    SO line date as the new one (DELIVERY DATE CHANGE TO), as today."""
    from app.models.base import company_scope
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    from .test_order_inquiry_worklist import _sorento

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            chain = Chain(db, company_id)
            _c, line = chain.add_line(core_date=NEW, mirror_date=NEW)
            row = chain.add_row(line, told=NEW, previous=OLD)
            db.commit()

            item = ProjectOrderInquiryService(db).handover_item(
                row, kind="settled", was={"delivery_date": OLD}
            )

            assert item["line"]["delivery_date"] == _fmt(NEW)
            assert item["line"]["was"]["delivery_date"] == _fmt(OLD)


def test_resend_preview_prints_the_so_line_date_in_email_and_ticks(rs):
    """AC-A5: the send / resend preview's email body and its row ticks print the SO line
    date, not the told date."""
    client, world = rs
    _automation(world)
    inquiry = _oi(world)
    chain = Chain(world.db, world.company_id)
    _c, line = chain.add_line(core_date=NEW, mirror_date=NEW)
    row = chain.add_row(
        line, told=OLD, inquiry=inquiry, item_code="ZZT-OD-RESEND",
        stock_location="BRW-BB",
    )
    world.db.commit()

    body = _ok(client.post(PREVIEW, json={"inquiry_ids": [inquiry.id]}))

    email = body["emails"][0]
    assert _fmt(NEW) in email["body_html"]
    assert _fmt(OLD) not in email["body_html"]
    tick = next(l for l in email["lines"] if l["row_id"] == row.id)
    assert str(tick["delivery_date"]) == NEW.isoformat()


# --------------------------------------------------------------------------- stock debt snapshot


def test_stock_debt_snapshot_freezes_the_so_line_date_on_its_oi_rows():
    """AC-A7. `_frozen_oi(oi_row, inquiry)` is a staticmethod with no session today, so the
    coder either resolves through the row's own session or makes it an instance method;
    this calls it whichever way it is left. (Guessed seam: the public `create` needs a whole
    Stock Debt board seeded, which is far beyond this slice.)"""
    import inspect

    from app.models.base import company_scope
    from app.services.scm.stock_debt_snapshot_service import StockDebtSnapshotService

    from .test_order_inquiry_worklist import _sorento

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            chain = Chain(db, company_id)
            core, line = chain.add_line(core_date=NEW, mirror_date=NEW)
            row = chain.add_row(line, told=OLD)
            db.commit()
            service = StockDebtSnapshotService(db)
            linked = service._linked_oi_rows([str(core.id)])
            (oi_row, inquiry), = linked[str(core.id)]
            assert str(oi_row.id) == str(row.id)

            frozen_oi = StockDebtSnapshotService._frozen_oi
            params = inspect.signature(frozen_oi).parameters
            # Either the coder keeps the (oi_row, inquiry) shape and resolves inside, or
            # makes it an instance method; both are called the same way from here.
            frozen = (
                frozen_oi(service, oi_row, inquiry)
                if "self" in params
                else frozen_oi(oi_row, inquiry)
            )

            assert frozen["delivery_date"] == NEW.isoformat()
            assert frozen["row_id"] == str(row.id)
