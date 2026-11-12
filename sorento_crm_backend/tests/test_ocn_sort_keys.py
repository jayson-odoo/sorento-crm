"""OCN-ORDER-CHANGE-NOTICE red tests: every OCN list column sorts on the server (UAC F2, G2).

Column ids (the FE list's column ids, which the list sends as `sort`): ocn_number, ocn_date,
customer_name, customer_po_no, change_type_name, risk_level, project_title,
sales_in_charge_name, status. Pattern: tests/test_portal_p4_npa_sort_keys.py.

Rows are created i = 0, 1, 2 with created_at ASCENDING in i, and each column's value sorts
DESCENDING in i, so an ignored key (the created_at fallback) cannot pass: asc == desc when the
fallback ignores `dir`, and asc == creation order when it does not; neither is the value order.
Risk and status may sort by label or by their natural order, so each is seeded with values
whose every acceptable order differs from both fallbacks.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from ._forms_chain_support import SORENTO, user, world  # noqa: F401
from ._ocn_support import OCN, change_type, ocn, project, rows_of, uid  # noqa: F401

STRICT = ("ocn_number", "ocn_date", "customer_name", "customer_po_no", "change_type_name",
          "project_title", "sales_in_charge_name")


def _seed(o, column):
    from app.models.project_so import OrderChangeNotice

    letters = "CBA"  # value i sorts descending in i
    ids = []
    base = datetime(2026, 11, 1, 9, 0, 0)
    for i in range(3):
        cols = dict(
            id=uid(),
            company_id=SORENTO,
            ocn_number=f"OCN26-{9100 + i}",
            status="draft",
            source="crm",
            created_by=o.raiser,
            customer_name="Customer M",
            customer_po_no="XT04/3800 (R1)",
            ocn_date=date(2026, 11, 1),
            created_at=base + timedelta(minutes=i),
        )
        if column == "ocn_number":
            cols["ocn_number"] = f"OCN26-{9200 - i}"
        elif column == "ocn_date":
            cols["ocn_date"] = date(2026, 12, 20 - i)
        elif column == "customer_name":
            cols["customer_name"] = f"Customer {letters[i]}"
        elif column == "customer_po_no":
            cols["customer_po_no"] = f"XT04/{3873 - i} (R1)"
        elif column == "change_type_name":
            cols["change_type_id"] = change_type(o.db, f"ZZT Type {letters[i]}", "Low").id
        elif column == "project_title":
            # Titles share no word (the project clash check blocks lookalikes); they sort descending in i.
            cols["project_id"] = project(o.db, o.raiser, ("Quillmoss Court", "Juniper Wharf", "Bexley Gardens")[i]).id
        elif column == "sales_in_charge_name":
            cols["sales_in_charge_user_id"] = user(o.db, f"Sales {letters[i]}")
        elif column == "risk_level":
            cols["change_type_id"] = change_type(o.db, f"ZZT Risk {i}", ("High", "Low", "Highest")[i]).id
        elif column == "status":
            cols["status"] = ("submitted", "approved", "draft")[i]
        row = OrderChangeNotice(**cols)
        o.db.add(row)
        o.db.flush()
        ids.append(row.id)
    o.db.commit()
    return ids


def _order(o, column, direction):
    res = o.as_(o.viewer).get(OCN, params={"sort": column, "dir": direction, "limit": 100})
    assert res.status_code == 200, res.text
    return [r["id"] for r in rows_of(res.json())]


@pytest.mark.parametrize("column", STRICT)
def test_f2_ocn_list_sorts_on_every_column(ocn, column):
    ids = _seed(ocn, column)
    asc, desc = _order(ocn, column, "asc"), _order(ocn, column, "desc")
    assert set(asc) == set(desc) == set(ids)
    assert asc != desc, f"sort={column}: asc and desc gave the same order, the key is ignored"
    assert asc == list(reversed(desc))
    assert asc == list(reversed(ids)), f"sort={column} asc mis-ordered"


#: Acceptable ascending orders (as indices of the creation order) per non-strict column.
LOOSE = {
    # values (High, Low, Highest): by label High < Highest < Low; by severity Low < High < Highest
    "risk_level": ([0, 2, 1], [1, 0, 2]),
    # values (submitted, approved, draft): by label approved < draft < submitted; by lifecycle
    # draft < submitted < approved
    "status": ([1, 2, 0], [2, 0, 1]),
}


@pytest.mark.parametrize("column", list(LOOSE))
def test_f2_ocn_list_sorts_risk_and_status(ocn, column):
    ids = _seed(ocn, column)
    asc, desc = _order(ocn, column, "asc"), _order(ocn, column, "desc")
    assert set(asc) == set(desc) == set(ids)
    assert asc != desc, f"sort={column}: asc and desc gave the same order, the key is ignored"
    assert asc == list(reversed(desc))
    assert asc in [[ids[i] for i in order] for order in LOOSE[column]], f"sort={column} asc mis-ordered"
