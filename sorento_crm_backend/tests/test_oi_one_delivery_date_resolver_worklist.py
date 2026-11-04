"""OI-ONE-DELIVERY-DATE: the resolver and the OI worklist (AC-A1..A3, A10..A12, B1, B2, C5).

Contract: `documentation/plans/scm/oi-one-delivery-date-acceptance-criteria.md`,
`PLAN-oi-one-delivery-date-03nov.md`. TEST-FIRST: no implementation exists. A red here is a
missing `app.services.oi_delivery_date` module or a worklist that still prints the row's
stored date.

Terms: SO line date = core `sales_order_lines.required_date`, else the mirror's
`delivery_date`, else the row's own stored date. Told date = the stored column. Was = the
told date when it differs from the SO line date, else `previous_delivery_date` when that
differs, else None. 2030-01-01 is printed as it is.

Every test seeds its own chain (`tests/_oi_one_date_seed.py`) and finds its rows by a unique
item code, so the shared database's other rows never matter.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models.base import company_scope
from app.models.project_so import OrderInquiryRow

from ._oi_one_date_seed import NO_CORE, Chain, digits
from ._pg_fixture import blank_session
from .test_order_inquiry_worklist import _restore, _sorento

LIST = "/api/v1/project-sales/order-inquiries"
SUMMARY = f"{LIST}/summary"

OLD = date(2026, 7, 1)  # the told date from OI-2609-0588
NEW = date(2027, 1, 7)  # the SO line date AutoCount shows
FAR = date(2030, 1, 1)


@pytest.fixture()
def world():
    from ._oi_one_date_seed import worklist_client

    with blank_session() as db:
        company_id = _sorento(db)
        client, originals = worklist_client(db, company_id)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id
        finally:
            _restore(originals)


def _by_item(client, token: str, **params):
    response = client.get(LIST, params={"query": token, "limit": 100, **params})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _tagged_chain(db, company_id):
    chain = Chain(db, company_id)
    chain.product.product_code = f"ZZT-OD-{digits(10)}"
    db.flush()
    return chain, chain.product.product_code


# --------------------------------------------------------------------------- was_of


def test_was_of_follows_the_uac_rule():
    """Terms: Was = told when it differs from the line date; else previous when it differs;
    else None."""
    from app.services.oi_delivery_date import was_of

    assert was_of(OLD, None, NEW) == OLD
    assert was_of(OLD, date(2026, 5, 1), NEW) == OLD, "told wins over previous"
    assert was_of(NEW, OLD, NEW) == OLD, "AC-B2: confirmed, told == line, Was = previous"
    assert was_of(NEW, None, NEW) is None
    assert was_of(NEW, NEW, NEW) is None, "previous equal to the line date is no Was"
    assert was_of(None, OLD, NEW) == OLD
    assert was_of(OLD, None, None) is None, "no line date at all: nothing to compare with"


# --------------------------------------------------------------------------- resolve


def test_resolve_core_first_then_mirror_then_told(world):
    """AC-A1, AC-A11, AC-A12: core wins over a lagging mirror; mirror when no core line is
    linked; the told date when there is no line, or the line has no date."""
    from app.services.oi_delivery_date import OiDate, resolve

    _client, db, company_id = world
    chain = Chain(db, company_id)
    _core, lag_mirror = chain.add_line(core_date=NEW, mirror_date=date(2026, 6, 1))
    _none, mirror_only = chain.add_line(core_date=NO_CORE, mirror_date=date(2027, 3, 3))
    _undated_core, undated = chain.add_line(core_date=None, mirror_date=None)

    core_row = chain.add_row(lag_mirror, told=OLD)
    mirror_row = chain.add_row(mirror_only, told=OLD)
    undated_row = chain.add_row(undated, told=OLD)
    no_line_row = chain.add_row(None, told=OLD)
    db.flush()

    out = resolve(db, [core_row, mirror_row, undated_row, no_line_row])

    assert isinstance(out[str(core_row.id)], OiDate)
    assert out[str(core_row.id)].date == NEW, "AC-A12: the core date wins over the mirror"
    assert out[str(core_row.id)].was == OLD
    assert out[str(mirror_row.id)].date == date(2027, 3, 3)
    assert out[str(mirror_row.id)].was == OLD
    assert out[str(undated_row.id)].date == OLD, "AC-A11: line has no date, told date prints"
    assert out[str(undated_row.id)].was is None
    assert out[str(no_line_row.id)].date == OLD, "AC-A11: no SO line, told date prints"
    assert out[str(no_line_row.id)].was is None


def test_resolve_prints_2030_as_it_is(world):
    """AC-A10: no TBA special case."""
    from app.services.oi_delivery_date import resolve

    _client, db, company_id = world
    chain = Chain(db, company_id)
    _core, line = chain.add_line(core_date=FAR, mirror_date=date(2026, 6, 1))
    row = chain.add_row(line, told=date(2026, 6, 1))
    assert resolve(db, [row])[str(row.id)].date == FAR


def test_resolve_after_confirm_keeps_the_old_date_as_was(world):
    """AC-B2: once CS confirmed (told == line date, previous = the old told date), Was is
    `previous_delivery_date`."""
    from app.services.oi_delivery_date import resolve

    _client, db, company_id = world
    chain = Chain(db, company_id)
    _core, line = chain.add_line(core_date=NEW, mirror_date=NEW)
    row = chain.add_row(line, told=NEW, previous=OLD)
    got = resolve(db, [row])[str(row.id)]
    assert (got.date, got.was) == (NEW, OLD)


# --------------------------------------------------------------------------- worklist


def test_worklist_row_prints_the_so_line_date_and_the_was(world):
    """AC-A1: OI-2609-0588 style: told 01/07/2026, SO line 07/01/2027."""
    client, db, company_id = world
    chain, token = _tagged_chain(db, company_id)
    _core, line = chain.add_line(core_date=NEW, mirror_date=NEW)
    row = chain.add_row(line, told=OLD)
    db.commit()

    rows = {r["id"]: r for r in _by_item(client, token)}

    assert rows[row.id]["delivery_date"] == NEW.isoformat()
    assert rows[row.id]["previous_delivery_date"] == OLD.isoformat()


def test_worklist_a_row_that_matches_has_no_was(world):
    """AC-A1/E3: told == line and no previous: no Was."""
    client, db, company_id = world
    chain, token = _tagged_chain(db, company_id)
    _core, line = chain.add_line(core_date=NEW, mirror_date=NEW)
    row = chain.add_row(line, told=NEW)
    db.commit()

    got = {r["id"]: r for r in _by_item(client, token)}[row.id]
    assert got["delivery_date"] == NEW.isoformat()
    assert got["previous_delivery_date"] is None


def test_worklist_2030_and_lagging_mirror_and_undated_line(world):
    """AC-A10, AC-A11, AC-A12 on the wire."""
    client, db, company_id = world
    chain, token = _tagged_chain(db, company_id)
    _c1, far = chain.add_line(core_date=FAR, mirror_date=date(2026, 6, 1))
    _c2, undated = chain.add_line(core_date=None, mirror_date=None)
    far_row = chain.add_row(far, told=date(2026, 6, 1))
    undated_row = chain.add_row(undated, told=date(2026, 8, 8))
    no_line_row = chain.add_row(None, told=date(2026, 9, 9))
    db.commit()

    rows = {r["id"]: r for r in _by_item(client, token)}

    assert rows[far_row.id]["delivery_date"] == "2030-01-01"
    assert rows[undated_row.id]["delivery_date"] == "2026-08-08"
    assert rows[no_line_row.id]["delivery_date"] == "2026-09-09"


def test_worklist_several_rows_on_one_line_each_print_the_line_date(world):
    """AC-C5: SO369829 L27, three rows at 01/02, 01/03, 01/04/2027, line 30/12/2027."""
    client, db, company_id = world
    chain, token = _tagged_chain(db, company_id)
    line_date = date(2027, 12, 30)
    _core, line = chain.add_line(core_date=line_date, mirror_date=line_date)
    told = [date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1)]
    rows = [chain.add_row(line, told=t, qty="5") for t in told]
    db.commit()

    got = {r["id"]: r for r in _by_item(client, token)}

    for row, was in zip(rows, told):
        assert got[row.id]["delivery_date"] == line_date.isoformat()
        assert got[row.id]["previous_delivery_date"] == was.isoformat()


def test_worklist_sorts_the_whole_result_by_the_so_line_date(world):
    """AC-A2: told dates run the opposite way to the line dates; the server sort follows
    the line dates in both directions."""
    client, db, company_id = world
    chain, token = _tagged_chain(db, company_id)
    plan = [  # (told, line date)
        (date(2026, 9, 1), date(2027, 3, 1)),
        (date(2026, 10, 1), date(2027, 2, 1)),
        (date(2026, 11, 1), date(2027, 1, 1)),
    ]
    ids = []
    for told, line_date in plan:
        _core, line = chain.add_line(core_date=line_date, mirror_date=line_date)
        ids.append(chain.add_row(line, told=told).id)
    db.commit()

    asc = client.get(LIST, params={"query": token, "sort": "delivery_date", "dir": "asc"})
    desc = client.get(LIST, params={"query": token, "sort": "delivery_date", "dir": "desc"})

    assert asc.status_code == 200, asc.text
    assert [r["id"] for r in asc.json()["data"]] == [ids[2], ids[1], ids[0]]
    assert [r["id"] for r in desc.json()["data"]] == [ids[0], ids[1], ids[2]]


def test_worklist_delivery_month_filter_uses_the_so_line_date(world):
    """AC-A3: a row whose line is 07/01/2027 sits under January 2027, not July 2026."""
    client, db, company_id = world
    chain, token = _tagged_chain(db, company_id)
    _core, line = chain.add_line(core_date=NEW, mirror_date=NEW)
    row = chain.add_row(line, told=OLD)
    db.commit()

    january = {r["id"] for r in _by_item(client, token, delivery_month="2027-01")}
    july = {r["id"] for r in _by_item(client, token, delivery_month="2026-07")}

    assert row.id in january
    assert row.id not in july


def test_worklist_delivery_from_to_filter_uses_the_so_line_date(world):
    """AC-A3: the from / to window reads the line date."""
    client, db, company_id = world
    chain, token = _tagged_chain(db, company_id)
    _core, line = chain.add_line(core_date=NEW, mirror_date=NEW)
    row = chain.add_row(line, told=OLD)
    db.commit()

    inside = {
        r["id"]
        for r in _by_item(client, token, delivery_from="2027-01-01", delivery_to="2027-01-31")
    }
    told_window = {
        r["id"]
        for r in _by_item(client, token, delivery_from="2026-07-01", delivery_to="2026-07-31")
    }

    assert row.id in inside
    assert row.id not in told_window


def test_summary_month_tabs_bucket_by_the_so_line_date(world):
    """AC-A3: the month tabs count the row under the SO line's month."""
    client, db, company_id = world
    chain, token = _tagged_chain(db, company_id)
    _core, line = chain.add_line(core_date=NEW, mirror_date=NEW)
    chain.add_row(line, told=OLD)
    db.commit()

    response = client.get(SUMMARY, params={"query": token})

    assert response.status_code == 200, response.text
    months = {m["month"]: m for m in response.json()["by_month"]}
    assert "2027-01" in months
    assert "2026-07" not in months


# --------------------------------------------------------------------------- pending change


def test_pending_autocount_move_shows_at_once_with_the_told_date_as_was(world):
    """AC-B1: AutoCount moves the line (core required_date and mirror delivery_date), CS has
    not confirmed anything: the OI reads the new date, Was = the told date, and the stored
    column is untouched (AC-B3: nothing here sends or settles)."""
    client, db, company_id = world
    chain, token = _tagged_chain(db, company_id)
    core, line = chain.add_line(core_date=OLD, mirror_date=OLD)
    row = chain.add_row(line, told=OLD)
    db.commit()
    before = {r["id"]: r for r in _by_item(client, token)}[row.id]
    assert before["delivery_date"] == OLD.isoformat()
    assert before["previous_delivery_date"] is None

    core.required_date = NEW
    line.delivery_date = NEW
    db.commit()

    after = {r["id"]: r for r in _by_item(client, token)}[row.id]
    assert after["delivery_date"] == NEW.isoformat()
    assert after["previous_delivery_date"] == OLD.isoformat()
    db.expire_all()
    stored = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert stored.delivery_date == OLD, "the stored column stays the told date"
    assert stored.previous_delivery_date is None
