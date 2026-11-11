"""NON-CANCELLABLE-ITEMS: the setting, the stored line flag, the REMARK column, the CRM gate
and the AutoCount alert.

Plan: documentation/plans/project-sales/PLAN-non-cancellable-items-11nov.md. Owner answers
(11 Nov 2026): set on the project series plus a company default (series wins; model beats
category), "Non-cancellable" in the REMARK column (no terms sentence), override needs
``projects.non_cancellable.override`` and a reason, AutoCount cuts alert the override role.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.audit import AuditLog
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.projects import NonCancellableRule, ProjectSeries
from app.models.user import User
from app.services import non_cancellable_service as nc
from app.services import project_seed_service
from app.services import quotation_columns
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-noncancel"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} Ali"))
    db.flush()
    return user_id


def _uom(db) -> str:
    row = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{uuid.uuid4().hex}", uom_name="Unit")
    db.add(row)
    db.flush()
    return row.id


def _category(db, company_id, name: str, parent_id=None) -> ProductCategory:
    row = ProductCategory(
        id=_uid(),
        company_id=company_id,
        category_code=f"ZZT-{_uid()[:8]}",
        category_name=f"{MARKER} {name}",
        parent_category_id=parent_id,
    )
    db.add(row)
    db.flush()
    return row


def _product(db, company_id, category_id, uom_id: str, name="Bathtub") -> Product:
    row = Product(
        id=_uid(),
        company_id=company_id,
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} {name}",
        description=f"Free standing {name.lower()}",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=Decimal("1950.00"),
    )
    db.add(row)
    db.flush()
    return row


def _series(db, company_id, category_ids, marked_ids=()) -> ProjectSeries:
    from app.services import project_pricing_service as pricing

    series = ProjectSeries(id=_uid(), company_id=company_id, name=f"{MARKER} {_uid()[:8]}")
    db.add(series)
    db.flush()
    pricing.set_series_categories(db, series=series, category_ids=list(category_ids))
    nc.set_series_categories(db, series=series, category_ids=list(marked_ids))
    return series


def _scope(db, company_id: str, owner: str, series_id=None):
    from app.services import project_quotation_service as quotes
    from app.services.project_service import register_project

    project = register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Mutiara Heights {_uid()[:12]}",
    )
    quotation = quotes.create_quotation(
        db,
        project=project,
        actor_user_id=owner,
        payload={"scope_label": "House Units", "series_id": series_id},
    )
    return quotation, quotes.current_version(db, quotation.id)


def _line(db, version, owner, product, qty=53):
    from app.services import project_quotation_service as quotes

    return quotes.upsert_line(
        db,
        version=version,
        actor_user_id=owner,
        payload={"product_id": product.id, "unit_price": "1950.00", "quantity": qty},
    )


@pytest.fixture
def world():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db)
        uom = _uom(db)
        bath = _category(db, company_id, "Bathtubs")
        freestanding = _category(db, company_id, "Freestanding", parent_id=bath.id)
        taps = _category(db, company_id, "Taps")
        yield {
            "db": db,
            "company_id": company_id,
            "owner": owner,
            "uom": uom,
            "bath": bath,
            "freestanding": freestanding,
            "taps": taps,
        }


# ------------------------------------------------------------------ the setting


def test_series_category_marks_lines_under_it_and_its_children(world):
    db, cid, owner = world["db"], world["company_id"], world["owner"]
    tub = _product(db, cid, world["freestanding"].id, world["uom"])
    tap = _product(db, cid, world["taps"].id, world["uom"], name="Bathtub Mixer Tap")
    series = _series(
        db, cid, [world["bath"].id, world["taps"].id], marked_ids=[world["bath"].id]
    )
    _q, version = _scope(db, cid, owner, series_id=series.id)

    tub_line = _line(db, version, owner, tub)
    tap_line = _line(db, version, owner, tap)

    # The parent category covers its child; the tap with "Bathtub" in its name does not.
    assert tub_line.is_non_cancellable is True
    assert tap_line.is_non_cancellable is False


def test_model_row_beats_the_category_both_ways(world):
    db, cid, owner = world["db"], world["company_id"], world["owner"]
    fast_mover = _product(db, cid, world["bath"].id, world["uom"])
    special_tap = _product(db, cid, world["taps"].id, world["uom"], name="Tap")
    series = _series(
        db, cid, [world["bath"].id, world["taps"].id], marked_ids=[world["bath"].id]
    )
    nc.set_series_product(db, series=series, product_id=fast_mover.id, non_cancellable=False)
    nc.set_series_product(db, series=series, product_id=special_tap.id, non_cancellable=True)
    _q, version = _scope(db, cid, owner, series_id=series.id)

    assert _line(db, version, owner, fast_mover).is_non_cancellable is False
    assert _line(db, version, owner, special_tap).is_non_cancellable is True


def test_marking_a_category_outside_the_series_is_refused(world):
    db, cid = world["db"], world["company_id"]
    series = _series(db, cid, [world["taps"].id])
    with pytest.raises(AppException) as err:
        nc.set_series_categories(db, series=series, category_ids=[world["bath"].id])
    assert err.value.status_code == 422


def test_company_default_covers_a_scope_with_no_series(world):
    db, cid, owner = world["db"], world["company_id"], world["owner"]
    tub = _product(db, cid, world["freestanding"].id, world["uom"])
    other = _product(db, cid, world["taps"].id, world["uom"], name="Tap")
    nc.create_rule(
        db, company_id=cid, payload={"category_id": world["bath"].id}, actor_user_id=owner
    )
    _q, version = _scope(db, cid, owner)

    assert _line(db, version, owner, tub).is_non_cancellable is True
    assert _line(db, version, owner, other).is_non_cancellable is False


def test_series_answer_wins_over_company_default(world):
    db, cid, owner = world["db"], world["company_id"], world["owner"]
    tub = _product(db, cid, world["bath"].id, world["uom"])
    nc.create_rule(db, company_id=cid, payload={"product_id": tub.id}, actor_user_id=owner)
    series = _series(db, cid, [world["bath"].id])
    nc.set_series_product(db, series=series, product_id=tub.id, non_cancellable=False)
    _q, version = _scope(db, cid, owner, series_id=series.id)

    assert _line(db, version, owner, tub).is_non_cancellable is False


def test_company_product_rule_exempts_one_model_from_its_category(world):
    db, cid, owner = world["db"], world["company_id"], world["owner"]
    tub = _product(db, cid, world["bath"].id, world["uom"])
    nc.create_rule(db, company_id=cid, payload={"category_id": world["bath"].id}, actor_user_id=owner)
    nc.create_rule(
        db,
        company_id=cid,
        payload={"product_id": tub.id, "non_cancellable": False},
        actor_user_id=owner,
    )
    _q, version = _scope(db, cid, owner)
    assert _line(db, version, owner, tub).is_non_cancellable is False


def test_a_second_rule_for_the_same_target_is_refused(world):
    db, cid, owner = world["db"], world["company_id"], world["owner"]
    nc.create_rule(db, company_id=cid, payload={"category_id": world["bath"].id}, actor_user_id=owner)
    with pytest.raises(AppException) as err:
        nc.create_rule(
            db, company_id=cid, payload={"category_id": world["bath"].id}, actor_user_id=owner
        )
    assert err.value.status_code == 409
    with pytest.raises(AppException) as both:
        nc.create_rule(
            db,
            company_id=cid,
            payload={"category_id": world["bath"].id, "product_id": _uid()},
            actor_user_id=owner,
        )
    assert both.value.status_code == 422
    assert db.query(NonCancellableRule).filter_by(company_id=cid).count() == 1


def test_a_set_holding_a_non_cancellable_part_is_non_cancellable(world):
    db, cid = world["db"], world["company_id"]
    tub = _product(db, cid, world["bath"].id, world["uom"])
    tap = _product(db, cid, world["taps"].id, world["uom"], name="Tap")
    setting = nc.series_setting(db, None, cid)
    assert setting.empty
    nc.create_rule(db, company_id=cid, payload={"category_id": world["bath"].id}, actor_user_id=None)
    setting = nc.series_setting(db, None, cid)
    parts = [{"product_id": tub.id}, {"product_id": tap.id}]
    assert nc.set_is_non_cancellable(db, product_set_id=_uid(), parts_snapshot=parts, setting=setting)
    assert not nc.set_is_non_cancellable(
        db, product_set_id=_uid(), parts_snapshot=[{"product_id": tap.id}], setting=setting
    )


def test_recompute_picks_up_a_setting_changed_after_pricing(world):
    from app.services import project_quotation_service as quotes

    db, cid, owner = world["db"], world["company_id"], world["owner"]
    tub = _product(db, cid, world["bath"].id, world["uom"])
    series = _series(db, cid, [world["bath"].id])
    _q, version = _scope(db, cid, owner, series_id=series.id)
    line = _line(db, version, owner, tub)
    assert line.is_non_cancellable is False

    nc.set_series_categories(db, series=series, category_ids=[world["bath"].id])
    report = quotes.recompute_version(db, version=version)

    assert line.is_non_cancellable is True
    assert report["changed_count"] == 1


# --------------------------------------------------------------- REMARK column


def test_remark_column_only_on_a_scope_with_a_non_cancellable_line(world):
    db, cid, owner = world["db"], world["company_id"], world["owner"]
    tub = _product(db, cid, world["bath"].id, world["uom"])
    tap = _product(db, cid, world["taps"].id, world["uom"], name="Tap")
    series = _series(db, cid, [world["bath"].id, world["taps"].id], [world["bath"].id])
    _q, version = _scope(db, cid, owner, series_id=series.id)
    tub_line = _line(db, version, owner, tub)
    tap_line = _line(db, version, owner, tap)

    keys = [k for k, _l in quotation_columns.for_lines([tub_line, tap_line])]
    assert quotation_columns.REMARK in keys
    # Before GRAND TOTAL, so the money stays the last column every total row relies on.
    assert keys[-1] == "amount" and keys[-2] == quotation_columns.REMARK
    assert quotation_columns.remark(tub_line) == "Non-cancellable"
    assert quotation_columns.remark(tap_line) == ""
    assert quotation_columns.REMARK not in [
        k for k, _l in quotation_columns.for_lines([tap_line])
    ]


def test_pdf_scope_prints_the_remark_cell(world):
    from app.services import project_quotation_pdf_service as pdf

    db, cid, owner = world["db"], world["company_id"], world["owner"]
    tub = _product(db, cid, world["bath"].id, world["uom"])
    series = _series(db, cid, [world["bath"].id], [world["bath"].id])
    _q, version = _scope(db, cid, owner, series_id=series.id)
    line = _line(db, version, owner, tub)

    html = pdf._scope_html(db, {"lines": [line], "label": "House Units", "total": Decimal("1")}, {})
    assert "<th>REMARK</th>" in html
    assert '<td class="remark">Non-cancellable</td>' in html


# ------------------------------------------------------------------ the gate


def _confirmed(db, quotation, line):
    """A published project SO whose line consumes ``line`` (the order is confirmed)."""
    from datetime import datetime

    from app.models.project_so import ProjectSalesOrder, ProjectSalesOrderLine

    order = ProjectSalesOrder(
        id=_uid(),
        company_id=quotation.company_id,
        project_id=quotation.project_id,
        provisional_ref=f"ZZT-{_uid()[:8]}",
        status="published",
        published_at=datetime.utcnow(),
    )
    db.add(order)
    db.flush()
    db.add(
        ProjectSalesOrderLine(
            id=_uid(),
            company_id=quotation.company_id,
            project_sales_order_id=order.id,
            line_no=1,
            qty=line.quantity,
            quotation_line_id=line.id,
        )
    )
    db.flush()
    return order


def test_removing_a_line_before_the_so_is_confirmed_is_free(world):
    from app.services import project_quotation_service as quotes

    db, cid, owner = world["db"], world["company_id"], world["owner"]
    tub = _product(db, cid, world["bath"].id, world["uom"])
    series = _series(db, cid, [world["bath"].id], [world["bath"].id])
    _q, version = _scope(db, cid, owner, series_id=series.id)
    line = _line(db, version, owner, tub)
    quotes.delete_line(db, version=version, line=line, user_id=owner)


def test_removing_a_confirmed_non_cancellable_line_needs_an_override(world, monkeypatch):
    from app.services import project_quotation_service as quotes

    db, cid, owner = world["db"], world["company_id"], world["owner"]
    tub = _product(db, cid, world["bath"].id, world["uom"])
    series = _series(db, cid, [world["bath"].id], [world["bath"].id])
    quotation, version = _scope(db, cid, owner, series_id=series.id)
    line = _line(db, version, owner, tub)
    _confirmed(db, quotation, line)

    monkeypatch.setattr(nc, "can_override", lambda _db, _uid: False)
    with pytest.raises(AppException) as refused:
        quotes.delete_line(db, version=version, line=line, user_id=owner)
    assert refused.value.status_code == 409
    assert refused.value.code == "non_cancellable_line"

    with pytest.raises(AppException) as forbidden:
        quotes.delete_line(
            db, version=version, line=line, user_id=owner, non_cancellable_override_reason="x"
        )
    assert forbidden.value.status_code == 403

    monkeypatch.setattr(nc, "can_override", lambda _db, _uid: True)
    with pytest.raises(AppException) as no_reason:
        quotes.delete_line(db, version=version, line=line, user_id=owner)
    assert no_reason.value.status_code == 409

    line_id = str(line.id)
    quotes.delete_line(
        db,
        version=version,
        line=line,
        user_id=owner,
        non_cancellable_override_reason="Customer pays the restocking charge",
    )
    logged = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == line_id, AuditLog.event == nc.AUDIT_EVENT)
        .all()
    )
    assert len(logged) == 1
    assert logged[0].reason == "Customer pays the restocking charge"


def test_bulk_save_cannot_drop_or_cut_a_confirmed_non_cancellable_line(world, monkeypatch):
    from app.services import project_quotation_service as quotes

    db, cid, owner = world["db"], world["company_id"], world["owner"]
    tub = _product(db, cid, world["bath"].id, world["uom"])
    series = _series(db, cid, [world["bath"].id], [world["bath"].id])
    quotation, version = _scope(db, cid, owner, series_id=series.id)
    line = _line(db, version, owner, tub, qty=53)
    _confirmed(db, quotation, line)
    monkeypatch.setattr(nc, "can_override", lambda _db, _uid: False)

    for lines in (
        [],  # dropped
        [{"id": line.id, "product_id": tub.id, "unit_price": "1950.00", "quantity": 40}],
        [{"id": line.id, "is_section": True, "band_label": "OPTION"}],
    ):
        with pytest.raises(AppException) as refused:
            quotes.replace_lines(db, version=version, actor_user_id=owner, lines=lines)
        assert refused.value.code == "non_cancellable_line"

    # Raising the quantity, or a single-line edit that keeps it, is free.
    quotes.replace_lines(
        db,
        version=version,
        actor_user_id=owner,
        lines=[{"id": line.id, "product_id": tub.id, "unit_price": "1950.00", "quantity": 60}],
    )
    with pytest.raises(AppException):
        quotes.upsert_line(
            db, version=version, actor_user_id=owner, line=line, payload={"quantity": 10}
        )


def test_assert_may_reduce_passes_when_nothing_is_non_cancellable(world):
    nc.assert_may_reduce(
        world["db"], reductions=[], user_id=None, override_reason=None, action="x"
    )


def test_so_lines_share_their_quotation_line_flag(world):
    from types import SimpleNamespace

    db, cid, owner = world["db"], world["company_id"], world["owner"]
    tub = _product(db, cid, world["bath"].id, world["uom"])
    tap = _product(db, cid, world["taps"].id, world["uom"], name="Tap")
    series = _series(db, cid, [world["bath"].id, world["taps"].id], [world["bath"].id])
    _q, version = _scope(db, cid, owner, series_id=series.id)
    tub_line = _line(db, version, owner, tub)
    tap_line = _line(db, version, owner, tap)
    so_lines = [
        SimpleNamespace(id="a", quotation_line_id=tub_line.id),
        SimpleNamespace(id="b", quotation_line_id=tub_line.id),
        SimpleNamespace(id="c", quotation_line_id=tap_line.id),
        SimpleNamespace(id="d", quotation_line_id=None),
    ]
    assert nc.so_lines_non_cancellable(db, so_lines) == {"a", "b"}


# ---------------------------------------------------------- the amendment path


def test_amendment_cut_rows_are_only_qty_reductions(world):
    from types import SimpleNamespace

    from app.services.project_so_delta_service import ProjectSODeltaService

    service = ProjectSODeltaService(world["db"])
    line = SimpleNamespace(id="l1", qty=Decimal("53"), line_no=1)
    service._line_or_none = lambda _id: line  # type: ignore[method-assign]
    rows = [
        {"verb": "CANCEL BALANCE", "so_line_id": "l1", "to_value": "40"},
        {"verb": "ORDER", "so_line_id": "l1", "to_value": "60"},
        {"verb": "DELAY", "so_line_id": "l1", "to_value": "2026-12-01"},
        {"verb": "RESERVE & ORDER", "so_line_id": "l1", "to_value": "53"},
    ]
    cuts = service._cut_lines(rows)
    assert [row["to_value"] for row, _l in cuts] == ["40"]


# -------------------------------------------------------------- AutoCount alert


def test_autocount_alert_goes_only_to_cuts_of_flagged_lines(world, monkeypatch):
    from types import SimpleNamespace

    db = world["db"]
    sent = []
    monkeypatch.setattr(nc, "_notify", lambda _db, **kw: sent.append(kw) or 1)
    monkeypatch.setattr(
        "app.services.project_notify_service.approver_user_ids",
        lambda *_a, **_k: ["mgr"],
    )

    mirror = SimpleNamespace(
        id="m1",
        core_sales_order_line_id="core1",
        project_sales_order_id="pso1",
        product_id=None,
        line_no=3,
        description="Free standing bathtub",
    )
    order = SimpleNamespace(
        id="pso1", company_id=world["company_id"], autocount_doc_no="SO400123", provisional_ref="P1"
    )

    class _Q:
        def __init__(self, result):
            self.result = result

        def filter(self, *_a, **_k):
            return self

        def all(self):
            return self.result

        def first(self):
            return self.result[0] if self.result else None

    real_query = db.query

    def fake_query(model, *rest):
        name = getattr(model, "__name__", "")
        if name == "ProjectSalesOrderLine":
            return _Q([mirror])
        if name == "ProjectSalesOrder":
            return _Q([order])
        return real_query(model, *rest)

    monkeypatch.setattr(db, "query", fake_query)
    monkeypatch.setattr(nc, "so_lines_non_cancellable", lambda _db, lines: {"m1"})

    # An increase and an unchanged line raise nothing.
    assert nc.alert_autocount_reductions(db, [("core1", 53, 60), ("core1", 53, 53)], source="t") == 0
    assert sent == []

    assert nc.alert_autocount_reductions(db, [("core1", 53, 40)], source="SO book") == 1
    assert sent[0]["user_ids"] == ["mgr"]
    assert "SO400123" in sent[0]["title"]
    assert "53 to 40" in sent[0]["body"]
    assert sent[0]["dedup_key"] == "m1:non_cancellable:40"

    monkeypatch.setattr(nc, "so_lines_non_cancellable", lambda _db, lines: set())
    sent.clear()
    assert nc.alert_autocount_reductions(db, [("core1", 53, 0)], source="Cancel SO") == 0
    assert sent == []
