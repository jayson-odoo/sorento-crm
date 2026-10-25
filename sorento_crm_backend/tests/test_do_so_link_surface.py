"""DO-SO-LINK-SURFACE: each DO line on the DO detail read names the SO it delivers.

Plan: documentation/plans/scm/PLAN-do-so-link-surface-25oct.md (R1, R4). Explicit links only:
the stored `sales_order_line_id`, else the SO AutoCount names in `FromDocNo` inside the DO's own
company; never a product or qty match. Postgres only, every row seeded here. The session has NO
company scope, so "another company's SO is not resolved" proves the read filters on the DO's
company itself.
"""
from __future__ import annotations

from app.schemas.order import OrderResponse
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.order_service import OrderService
from tests._pg_fixture import unique_code
from tests.test_so_line_history import (  # noqa: F401
    OTHER_COMPANY,
    db,
    seed_do,
    seed_do_line,
    seed_product,
    seed_so,
    seed_so_line,
    seed_wh,
)


def _read(db, order):
    return OrderResponse.model_validate(OrderService(db).get_order(str(order.id))).model_dump()


def _line(out, seq):
    return next(line for line in out["lines"] if line["line_sequence"] == seq)


def test_stored_link_names_the_so_and_its_line_no(db):
    so = seed_so(db, DEFAULT_COMPANY_ID)
    p = seed_product(db, DEFAULT_COMPANY_ID)
    wh = seed_wh(db, DEFAULT_COMPANY_ID)
    sol = seed_so_line(db, so, p)
    sol.line_no = 3
    db.flush()
    d = seed_do(db, DEFAULT_COMPANY_ID)
    seed_do_line(db, d, p, wh, so_line=sol, from_doc_no=so.so_number)

    line = _line(_read(db, d), 1)

    assert line["from_doc_no"] == so.so_number
    assert line["sales_order"] == {"id": str(so.id), "so_number": so.so_number, "line_no": 3}


def test_no_stored_line_resolves_the_so_by_its_fromdocno_with_no_line(db):
    """The product sits on two SO lines: AutoCount named the SO, not the line (Q2 a)."""
    so = seed_so(db, DEFAULT_COMPANY_ID)
    p = seed_product(db, DEFAULT_COMPANY_ID)
    wh = seed_wh(db, DEFAULT_COMPANY_ID)
    seed_so_line(db, so, p)
    seed_so_line(db, so, p)
    d = seed_do(db, DEFAULT_COMPANY_ID)
    seed_do_line(db, d, p, wh, from_doc_no=so.so_number)

    line = _line(_read(db, d), 1)

    assert line["sales_order"] == {"id": str(so.id), "so_number": so.so_number, "line_no": None}


def test_so_not_in_the_crm_keeps_the_autocount_number_and_no_link(db):
    p = seed_product(db, DEFAULT_COMPANY_ID)
    wh = seed_wh(db, DEFAULT_COMPANY_ID)
    d = seed_do(db, DEFAULT_COMPANY_ID)
    missing = unique_code("SO")
    seed_do_line(db, d, p, wh, from_doc_no=missing)

    line = _line(_read(db, d), 1)

    assert line["from_doc_no"] == missing
    assert line["sales_order"] is None


def test_direct_do_line_has_no_so(db):
    p = seed_product(db, DEFAULT_COMPANY_ID)
    wh = seed_wh(db, DEFAULT_COMPANY_ID)
    d = seed_do(db, DEFAULT_COMPANY_ID)
    seed_do_line(db, d, p, wh, from_doc_no=None, from_doc_type=None)

    line = _line(_read(db, d), 1)

    assert line["from_doc_no"] is None
    assert line["sales_order"] is None


def test_another_companys_so_with_the_same_number_is_not_resolved(db):
    so = seed_so(db, OTHER_COMPANY)
    p = seed_product(db, DEFAULT_COMPANY_ID)
    wh = seed_wh(db, DEFAULT_COMPANY_ID)
    d = seed_do(db, DEFAULT_COMPANY_ID)
    seed_do_line(db, d, p, wh, from_doc_no=so.so_number)

    assert _line(_read(db, d), 1)["sales_order"] is None


def test_non_so_source_is_not_resolved_as_an_so(db):
    """A DO line transferred from a quotation (`QT`) whose number happens to match an SO."""
    so = seed_so(db, DEFAULT_COMPANY_ID)
    p = seed_product(db, DEFAULT_COMPANY_ID)
    wh = seed_wh(db, DEFAULT_COMPANY_ID)
    d = seed_do(db, DEFAULT_COMPANY_ID)
    seed_do_line(db, d, p, wh, from_doc_no=so.so_number, from_doc_type="QT")

    assert _line(_read(db, d), 1)["sales_order"] is None


def test_one_do_over_two_sos_names_each_on_its_own_line(db):
    so1 = seed_so(db, DEFAULT_COMPANY_ID)
    so2 = seed_so(db, DEFAULT_COMPANY_ID)
    p = seed_product(db, DEFAULT_COMPANY_ID)
    wh = seed_wh(db, DEFAULT_COMPANY_ID)
    l1 = seed_so_line(db, so1, p)
    d = seed_do(db, DEFAULT_COMPANY_ID)
    seed_do_line(db, d, p, wh, so_line=l1, from_doc_no=so1.so_number, seq=1)
    seed_do_line(db, d, p, wh, from_doc_no=so2.so_number, seq=2)

    out = _read(db, d)

    assert _line(out, 1)["sales_order"]["so_number"] == so1.so_number
    assert _line(out, 2)["sales_order"]["so_number"] == so2.so_number
