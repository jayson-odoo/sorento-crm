"""OI-UX-FILTER-SNAPSHOT (owner, 3 Nov 19:15/19:35): every Stock Debt line that names a sales
order also names its CUSTOMER and PROJECT, the way the SO list does: `customer_name` is the
debtor name the order was issued under (else the customer master's name), `project_label`
is `SalesOrder.project_label`. Live drill (`cell`) and snapshot drill (`lines`) alike; a
snapshot taken before these fields existed still answers them (read live off the order).

Postgres only; every test seeds its own chain with a `ZZTSD` marker.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.scm.supply_assignment import month_key
from tests.scm.conftest import requires_pg
from tests.scm.test_stock_debt_routes import BASE, _months_ahead
from tests.scm.test_stock_debt_snapshots import (
    _book,
    _client,
    _lines,
    _marker,
    _row_id,
    _taken,
)

pytestmark = requires_pg


def _label(db, lines, *, near=None, far=None):
    """`near` / `far` -> (debtor_name, project_label) on that line's order."""
    for name, value in (("near", near), ("far", far)):
        if value is None:
            continue
        order = lines[name][0]
        order.debtor_name, order.project_label = value
    db.flush()


def test_the_live_drill_names_customer_and_project(scm_app):
    app, db = _client(scm_app)
    marker = _marker()
    product, _bin, _pool, lines = _book(db, marker)
    _label(db, lines, near=("ZZT ACME SDN BHD (PROJECT)", "TAMAN ZZT"))

    with TestClient(app) as c:
        resp = c.get(f"{BASE}/{product.id}/cell", params={"month": month_key(_months_ahead(1))})
    assert resp.status_code == 200, resp.text
    (line,) = resp.json()["demand"]
    assert line["so_number"] == f"{marker}-SO-near"
    assert line["customer_name"] == "ZZT ACME SDN BHD (PROJECT)"
    assert line["project_label"] == "TAMAN ZZT"


def test_a_line_with_no_customer_or_project_answers_null_not_an_id(scm_app):
    app, db = _client(scm_app)
    marker = _marker()
    product, _bin, _pool, _lines_ = _book(db, marker)

    with TestClient(app) as c:
        resp = c.get(f"{BASE}/{product.id}/cell", params={"month": month_key(_months_ahead(3))})
    (line,) = resp.json()["demand"]
    assert line["customer_name"] is None
    assert line["project_label"] is None


def test_the_snapshot_drill_names_customer_and_project(scm_app):
    app, db = _client(scm_app)
    marker = _marker()
    product, _bin, _pool, lines = _book(db, marker)
    _label(
        db, lines,
        near=("ZZT ACME SDN BHD (PROJECT)", "TAMAN ZZT"),
        far=("ZZT BETA SDN BHD", None),
    )

    with TestClient(app) as c:
        header = _taken(c, marker)
        row_id = _row_id(c, header["id"], product.product_code)
        by_so = {l["so_number"]: l for l in _lines(c, header["id"], row_id)}

    near, far = by_so[f"{marker}-SO-near"], by_so[f"{marker}-SO-far"]
    assert (near["customer_name"], near["project_label"]) == ("ZZT ACME SDN BHD (PROJECT)", "TAMAN ZZT")
    assert (far["customer_name"], far["project_label"]) == ("ZZT BETA SDN BHD", None)


def test_a_snapshot_stored_without_the_fields_still_names_them(scm_app):
    """Snapshots saved before this change hold lines with no customer/project keys."""
    app, db = _client(scm_app)
    marker = _marker()
    product, _bin, _pool, lines = _book(db, marker)
    _label(db, lines, near=("ZZT ACME SDN BHD (PROJECT)", "TAMAN ZZT"))

    with TestClient(app) as c:
        header = _taken(c, marker)
        row_id = _row_id(c, header["id"], product.product_code)
        db.execute(
            text(
                "UPDATE projects.stock_debt_snapshot_rows SET lines = ("
                " SELECT jsonb_agg(l - 'customer_name' - 'project_label')"
                " FROM jsonb_array_elements(lines) l) WHERE id = :i"
            ),
            {"i": row_id},
        )
        db.expire_all()
        by_so = {l["so_number"]: l for l in _lines(c, header["id"], row_id)}

    near = by_so[f"{marker}-SO-near"]
    assert near["customer_name"] == "ZZT ACME SDN BHD (PROJECT)"
    assert near["project_label"] == "TAMAN ZZT"
