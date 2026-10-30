"""FULFIL-SO-REMARK email content (AC-10..AC-13, AC-15), read off the handover context the
board's confirm-all dispatches (same capture as tests/test_oi_saved_line_email.py)."""
from __future__ import annotations

from datetime import date

import pytest
import sqlalchemy as sa

from .test_oi_saved_line_email import emails  # noqa: F401 - fixture
from .test_planning_change_apply_on_board import (  # noqa: F401 - fixtures reused
    BASE,
    api,
    world,
)
from .test_planning_changes import _core_line, _core_so, _line_payload, _project_line, _project_so

D = date(2026, 11, 2)


def _seed_order(world, *, ship_info=None, note=None, flags):
    """One core SO whose lines carry `line_remark` MOCK per `flags`; returns the project SO and
    its project lines. Raw UPDATEs: the failure before the columns exist is a DB error."""
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_lines = [
        _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5", required_date=D)
        for _ in flags
    ]
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    lines = [
        _project_line(db, order, line_no=10 * (i + 1), product=world.product, core_line=cl)
        for i, cl in enumerate(core_lines)
    ]
    if ship_info is not None:
        db.execute(
            sa.text("UPDATE sales_orders SET ship_info = :v WHERE id = :id"),
            {"v": ship_info, "id": core_so.id},
        )
    if note is not None:
        db.execute(
            sa.text("UPDATE sales_orders SET internal_note = :v WHERE id = :id"),
            {"v": note, "id": core_so.id},
        )
    for cl, flag in zip(core_lines, flags):
        if flag:
            db.execute(
                sa.text("UPDATE sales_order_lines SET line_remark = :v WHERE id = :id"),
                {"v": "***FOR STH(100)-2 UNITS MOCK UP", "id": cl.id},
            )
    db.commit()
    return order, lines


def _confirm_all(api, order, lines, so_remark="__absent__"):
    client, world = api
    entry = {"pso_id": order.id, "lines": [_line_payload(l.id, buy_qty="5") for l in lines]}
    if so_remark != "__absent__":
        entry["so_remark"] = so_remark
    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json={"orders": [entry]})
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["ok"] is True, response.text
    world.db.commit()


def _line_remarks(email):
    return [l["remark"] for l in email["lines"]]


def test_ac11_absent_so_remark_uses_the_default_for_the_lines_in_the_email(api, emails):
    _client, world = api
    order, lines = _seed_order(world, flags=[True, False])

    _confirm_all(api, order, lines)

    assert emails[0]["orders"][0]["remark"] == "Mockup"


def test_ac11_an_edited_so_remark_prints_as_sent(api, emails):
    _client, world = api
    order, lines = _seed_order(world, ship_info="SPONSORSHIP", flags=[False])

    _confirm_all(api, order, lines, so_remark="Sample for client")

    assert emails[0]["orders"][0]["remark"] == "Sample for client"


def test_ac11_a_cleared_so_remark_prints_blank_not_the_default(api, emails):
    _client, world = api
    order, lines = _seed_order(world, ship_info="SPONSORSHIP", flags=[True, False])

    _confirm_all(api, order, lines, so_remark="")

    assert emails[0]["orders"][0]["remark"] == ""


def test_ac5_sponsorship_default_when_absent(api, emails):
    _client, world = api
    order, lines = _seed_order(world, ship_info="SPONSORSHIP", note="***SPONSORSHIP (MOCKUP)***",
                               flags=[False])

    _confirm_all(api, order, lines)

    assert emails[0]["orders"][0]["remark"] == "Sponsorship"


def test_ac12_mixed_lines_label_each_mockup_line_ahead_of_its_text(api, emails):
    _client, world = api
    order, lines = _seed_order(world, flags=[True, False, True])

    _confirm_all(api, order, lines)

    assert sorted(_line_remarks(emails[0])) == sorted(["Mockup, ORDER", "ORDER", "Mockup, ORDER"])


def test_ac12_all_mockup_lines_get_no_label(api, emails):
    _client, world = api
    order, lines = _seed_order(world, flags=[True, True])

    _confirm_all(api, order, lines)

    assert _line_remarks(emails[0]) == ["ORDER", "ORDER"]
    assert emails[0]["orders"][0]["remark"] == "Mockup"


def test_ac12_no_mockup_lines_get_no_label_and_a_blank_so_remark(api, emails):
    _client, world = api
    order, lines = _seed_order(world, flags=[False, False])

    _confirm_all(api, order, lines)

    assert _line_remarks(emails[0]) == ["ORDER", "ORDER"]
    assert emails[0]["orders"][0]["remark"] == ""


def test_ac12_labels_follow_the_lines_in_this_email_only(api, emails):
    """SO419417 shape: only the non-mockup lines chosen this time -> blank, no labels."""
    _client, world = api
    order, lines = _seed_order(world, flags=[True, False, False])

    _confirm_all(api, order, lines[1:])

    assert emails[0]["orders"][0]["remark"] == ""
    assert _line_remarks(emails[0]) == ["ORDER", "ORDER"]


def test_ac12_note_mock_marks_every_line_so_no_labels(api, emails):
    _client, world = api
    order, lines = _seed_order(world, note="***FOR MOCKUP", flags=[False, False])

    _confirm_all(api, order, lines)

    assert emails[0]["orders"][0]["remark"] == "Mockup"
    assert _line_remarks(emails[0]) == ["ORDER", "ORDER"]


def test_ac10_so_remark_over_100_characters_is_a_422(api):
    client, world = api
    order, lines = _seed_order(world, flags=[False])

    response = client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={"orders": [{
            "pso_id": order.id, "so_remark": "x" * 101,
            "lines": [_line_payload(l.id, buy_qty="5") for l in lines],
        }]},
    )

    assert response.status_code == 422, response.text


def test_ac10_the_confirm_body_declares_so_remark():
    from app.schemas.project_supply import ConfirmManyOrderBody

    assert ConfirmManyOrderBody(pso_id="x").so_remark is None
    assert ConfirmManyOrderBody(pso_id="x", so_remark="").so_remark == ""
