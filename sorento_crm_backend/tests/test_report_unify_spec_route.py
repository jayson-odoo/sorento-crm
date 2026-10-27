"""Phase 2 RED tests - the spec filter and `group_by=spec:<key>` on
`GET /api/v1/order-management/report-ask` (lane REPORT-UNIFY, slice 1, engine).

`documentation/plans/reports/PLAN-report-unify-27oct.md` sections 0 and 1 and
`report-unify-27oct-acceptance-criteria.md`: AC-RU-1 to AC-RU-7 and AC-RU-9. The two new
outstanding bases and the optional period are in `test_report_unify_outstanding_bases.py`.
Invoiced is not here: it lands with PR #1916 and joins the AC-RU-7 tally on the rebase.

Postgres only (`tests/_pg_fixture.py`), every row seeded here (CI's database has none).

Readings the tester PINNED where the contract is silent (flagged to the captain):
* the echo: `body["filters"]` is the route's list of `{key, label, values}`; a spec is one entry
  with `key == "spec"` whose `values` carry "<registry label>: <value label>" (AC-RU-9
  "Trap type: P-trap"). The entry's own `label` is not asserted.
* `not_applied` is a TOP-LEVEL list of `{filter, value, reason}` on the body; `value` is the
  raw `key:value` the caller sent. Only the unit case asserts `value` (the contract names it).
* `group_by=spec:<key>` row names: the registry's value label when it has one ("P-trap"),
  else the raw value. The tests compare names with case and punctuation ignored, so both
  "P-trap" and "p_trap" pass; "Not stated" is exact.
* a spec group is a ranking, so it needs `top_n` like every other group (422 `top_n_required`).
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import unique_code
from tests._report_ask_so_seed import seed_so_line
from tests._report_unify_seed import (
    bulk_products,
    delivered_status,
    hide_spec_keys,
    make_product,
    seed_registry,
)
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    _as_contact,
    _contact,
    client,
    db,
    line,
    money,
    seed_customer,
    seed_do,
    warehouse,
)
from tests.test_report_ask_route import _brand, _category
from tests.test_top_selling_report import _access

D = Decimal
ROUTE = "/api/v1/order-management/report-ask"
KEY = {"X-API-Key": "k"}
PERIOD = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
SEP = date(2026, 9, 10)
NOT_STATED = "Not stated"


# ------------------------------------------------------------------------- helpers


def _ask(client, contact, **params):
    q = {**PERIOD, **_as_contact(contact), **params}
    q = {k: v for k, v in q.items() if v is not None}
    return client.get(ROUTE, params=q, headers=KEY)


def _ok(client, contact, **params):
    resp = _ask(client, contact, **params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _staff(db):
    """A grant holder with an office access type (the audience a product ranking is for)."""
    contact = _contact(db)
    _access(db, contact, "Sorento Office")
    db.commit()
    return contact


def _tot(body):
    return body["total"]["qty"], money(body["total"]["amount"])


def _rows(body):
    return [(r["name"], r["qty"], money(r["amount"])) for r in body["rows"]]


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _by_name(body):
    return {_norm(r["name"]): (r["qty"], money(r["amount"])) for r in body["rows"]}


def _not_applied(body):
    return body.get("not_applied") or []


def _has_na(body, filter_, reason, value=None):
    return any(
        n.get("filter") == filter_ and n.get("reason") == reason and (value is None or n.get("value") == value)
        for n in _not_applied(body)
    )


def _spec_echo(body):
    return [f for f in body["filters"] if f["key"] == "spec"]


def _sale(db, w, prod, qty, total):
    return seed_so_line(db, cust=w.cust, prod=prod, qty=qty, total=total, wh=w.wh, order_date=SEP)


def _trap_world(db):
    """Six products, one fully delivered September line each (qty / total):

        p1 p_trap  length 250   cat X   1 /  100
        p2 p_trap  length 250   cat X   2 /  200
        p3 p_trap  length 200   cat Y   3 /  400
        p4 s_trap  length 250   cat X   4 /  800
        p5 no spec row          cat X   5 / 1600
        p6 spec row, length 300 only    cat X   6 / 3200   (no trap_type)

    p_trap 6 / 700 | s_trap 4 / 800 | length 250: 7 / 1100 | p_trap and length 250: 3 / 300
    not stated trap_type: 11 / 4800 | everything 21 / 6300
    """
    seed_registry(db)
    w = SimpleNamespace()
    w.cust = seed_customer(db, name=unique_code("Cust"))
    w.wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WH"))
    w.cat_x, w.cat_y = _category(db, "ZZT-CAT-X"), _category(db, "ZZT-CAT-Y")
    mm = "mm"
    w.p1 = make_product(db, unique_code("P1"), category=w.cat_x, specs={"trap_type": "p_trap", "length": (250, mm)})
    w.p2 = make_product(db, unique_code("P2"), category=w.cat_x, specs={"trap_type": "p_trap", "length": (250, mm)})
    w.p3 = make_product(db, unique_code("P3"), category=w.cat_y, specs={"trap_type": "p_trap", "length": (200, mm)})
    w.p4 = make_product(db, unique_code("P4"), category=w.cat_x, specs={"trap_type": "s_trap", "length": (250, mm)})
    w.p5 = make_product(db, unique_code("P5"), category=w.cat_x)
    w.p6 = make_product(db, unique_code("P6"), category=w.cat_x, specs={"length": (300, mm)})
    for prod, qty, total in ((w.p1, 1, "100.00"), (w.p2, 2, "200.00"), (w.p3, 3, "400.00"),
                             (w.p4, 4, "800.00"), (w.p5, 5, "1600.00"), (w.p6, 6, "3200.00")):
        _sale(db, w, prod, qty, total)
    db.commit()
    return w


# ================================================================ AC-RU-1: the spec filter


def test_ac_ru_1_spec_narrows_to_products_with_that_value_and_the_total_is_their_sum(client, db):
    """AC-RU-1: spec=trap_type:p_trap with a category returns only the p_trap products of it."""
    w = _trap_world(db)
    contact = _staff(db)
    body = _ok(client, contact, spec="trap_type:p_trap", category_ids=[w.cat_x.id])
    assert body["status"] == "ok", body
    assert _tot(body) == (3, D("300.00")), body["total"]  # p1 + p2; p3 is in category Y
    whole = _ok(client, contact, spec="trap_type:p_trap")
    assert _tot(whole) == (6, D("700.00")), whole["total"]  # p1 + p2 + p3


def test_ac_ru_1_spec_set_rows_sum_to_the_total(client, db):
    """AC-RU-1: the total equals the sum of those products' rows (group_by=product)."""
    w = _trap_world(db)
    body = _ok(client, _staff(db), spec="trap_type:p_trap", group_by="product", top_n=50)
    assert sorted(r["name"] for r in body["rows"]) == sorted(p.product_code for p in (w.p1, w.p2, w.p3)), body["rows"]
    assert sum(r["qty"] for r in body["rows"]) == 6 and sum(money(r["amount"]) for r in body["rows"]) == D("700.00")
    assert _tot(body) == (6, D("700.00")), body["total"]


def test_ac_ru_1_a_different_key_is_anded(client, db):
    """AC-RU-1: spec=trap_type:p_trap&spec=length:250 is p1 + p2 only (p3 is length 200)."""
    _trap_world(db)
    body = _ok(client, _staff(db), spec=["trap_type:p_trap", "length:250"])
    assert _tot(body) == (3, D("300.00")), body["total"]


def test_ac_ru_1_the_same_key_repeated_is_ored(client, db):
    """AC-RU-1: spec=trap_type:p_trap&spec=trap_type:s_trap is p1..p4."""
    _trap_world(db)
    body = _ok(client, _staff(db), spec=["trap_type:p_trap", "trap_type:s_trap"])
    assert _tot(body) == (10, D("1500.00")), body["total"]


def test_ac_ru_1_strings_match_case_insensitively(client, db):
    """AC-RU-1 (membership_clause): a string value matches whatever its case."""
    _trap_world(db)
    body = _ok(client, _staff(db), spec="trap_type:P_TRAP")
    assert _tot(body) == (6, D("700.00")), body["total"]


def test_ac_ru_1_a_list_value_matches_by_containment(client, db):
    """AC-RU-1 (membership_clause): a product holding two values matches either one."""
    seed_registry(db)
    w = SimpleNamespace(
        cust=seed_customer(db, name=unique_code("Cust")), wh=warehouse(db, company_id=DEFAULT_COMPANY_ID),
    )
    both = make_product(db, unique_code("BOTH"), specs={"trap_type": ["p_trap", "s_trap"]})
    other = make_product(db, unique_code("OTH"), specs={"trap_type": "wall"})
    _sale(db, w, both, 2, "20.00")
    _sale(db, w, other, 3, "30.00")
    db.commit()
    contact = _staff(db)
    assert _tot(_ok(client, contact, spec="trap_type:p_trap")) == (2, D("20.00"))
    assert _tot(_ok(client, contact, spec="trap_type:s_trap")) == (2, D("20.00"))


def test_ac_ru_1_spec_is_anded_with_product_code_and_product_ids(client, db):
    """AC-RU-1 / plan section 1: the spec set narrows with product_code / product_ids, never widens."""
    w = _trap_world(db)
    contact = _staff(db)
    by_code = _ok(client, contact, spec="trap_type:p_trap", product_code=w.p1.product_code)
    assert _tot(by_code) == (1, D("100.00")), by_code["total"]
    by_ids = _ok(client, contact, spec="trap_type:p_trap", product_ids=[w.p2.id, w.p4.id])
    assert _tot(by_ids) == (2, D("200.00")), by_ids["total"]  # p4 is s_trap


def test_ac_ru_1_a_spec_with_no_colon_is_422_invalid_spec(client, db):
    """AC-RU-1 (plan section 1, malformed input): spec=trap_type has no key:value shape."""
    _trap_world(db)
    resp = _ask(client, _staff(db), spec="trap_type")
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") == "invalid_spec", resp.text


def test_ac_ru_1_a_spec_set_with_an_empty_intersection_with_product_ids_is_ok_with_zero_rows(client, db):
    """AC-RU-4 (plan section 1): the spec matches products, but none of the named product_ids: status ok
    (the existing AND), zero rows, zero total. Only a spec matching NO product at all is no_products."""
    w = _trap_world(db)
    body = _ok(client, _staff(db), spec="trap_type:p_trap", product_ids=[w.p4.id], group_by="product", top_n=10)
    assert body["status"] == "ok", body
    assert body["rows"] == [] and body["total"]["qty"] == 0 and money(body["total"]["amount"]) == D("0.00"), body


def test_ac_ru_1_spec_on_the_chat_dataset_is_422_unknown_param(client, db):
    """AC-RU-1 (plan section 1): `spec` is not a chat key. (Passes today: a regression pin.)"""
    resp = _ask(client, _staff(db), dataset="chat", spec="trap_type:p_trap")
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") == "unknown_param", resp.text


# ================================================================ AC-RU-2: no 50 cap on a spec


def test_ac_ru_2_a_spec_set_larger_than_fifty_products_is_answered_whole(client, db):
    """AC-RU-2: 55 matching products, one line each (qty 1, 1.00): the spec answers 55 / 55.00."""
    seed_registry(db)
    w = SimpleNamespace(cust=seed_customer(db, name=unique_code("Cust")), wh=warehouse(db, company_id=DEFAULT_COMPANY_ID))
    big = bulk_products(db, 55, prefix=unique_code("BIG", alpha=True), specs={"trap_type": "p_trap"})
    for prod in big:
        _sale(db, w, prod, 1, "1.00")
    odd = make_product(db, unique_code("ODD"), specs={"trap_type": "s_trap"})
    _sale(db, w, odd, 7, "70.00")
    db.commit()
    body = _ok(client, _staff(db), spec="trap_type:p_trap")
    assert body["status"] == "ok", body
    assert _tot(body) == (55, D("55.00")), body["total"]


# ================================================================ AC-RU-3: numeric specs and units


def test_ac_ru_3_a_numeric_spec_matches_the_stored_number_exactly(client, db):
    """AC-RU-3: length:250 is p1, p2, p4; the 200 and the unstated lengths (p5, p6) are excluded."""
    _trap_world(db)
    body = _ok(client, _staff(db), spec="length:250")
    assert _tot(body) == (7, D("1100.00")), body["total"]
    assert not _not_applied(body), body


def test_ac_ru_3_a_value_in_the_registry_unit_is_the_same_as_the_bare_number(client, db):
    """AC-RU-3: length:250mm on an mm key equals length:250."""
    _trap_world(db)
    contact = _staff(db)
    with_unit = _ok(client, contact, spec="length:250mm")
    assert _tot(with_unit) == (7, D("1100.00")), with_unit["total"]
    assert not _not_applied(with_unit), with_unit


def test_ac_ru_3_a_value_in_another_unit_is_not_applied_and_the_figures_are_unfiltered(client, db):
    """AC-RU-3: length:25cm is echoed under not_applied (unit) and the spec does not narrow."""
    _trap_world(db)
    body = _ok(client, _staff(db), spec="length:25cm")
    assert _has_na(body, "spec", "unit", "length:25cm"), body.get("not_applied")
    assert _tot(body) == (21, D("6300.00")), body["total"]
    assert not _spec_echo(body), body["filters"]


def test_ac_ru_3_an_unknown_key_is_not_applied_and_the_figures_are_unfiltered(client, db):
    """AC-RU-3: a key not in product_spec_registry is echoed under not_applied (unknown_spec)."""
    _trap_world(db)
    body = _ok(client, _staff(db), spec="colour:red")
    assert _has_na(body, "spec", "unknown_spec", "colour:red"), body.get("not_applied")
    assert _tot(body) == (21, D("6300.00")), body["total"]


def test_ac_ru_3_an_unapplied_spec_beside_an_applied_one_leaves_only_the_applied_narrowing(client, db):
    """AC-RU-3: the applied key still narrows; only the bad one is dropped."""
    _trap_world(db)
    body = _ok(client, _staff(db), spec=["trap_type:p_trap", "length:25cm"])
    assert _has_na(body, "spec", "unit", "length:25cm"), body.get("not_applied")
    assert _tot(body) == (6, D("700.00")), body["total"]


# ================================================================ AC-RU-4: no match


def test_ac_ru_4_a_spec_matching_no_product_is_no_products_and_never_the_unfiltered_set(client, db):
    """AC-RU-4: trap_type:wall matches nothing: 200, status no_products, no rows, zero total."""
    _trap_world(db)
    body = _ok(client, _staff(db), spec="trap_type:wall")
    assert body["status"] == "no_products", body
    assert body["rows"] == [], body
    assert body["total"]["qty"] == 0 and money(body["total"]["amount"]) == D("0.00"), body["total"]


def test_ac_ru_4_a_numeric_spec_matching_no_product_is_no_products(client, db):
    """AC-RU-4: length:999 matches nothing."""
    _trap_world(db)
    body = _ok(client, _staff(db), spec="length:999", group_by="product", top_n=10)
    assert body["status"] == "no_products", body
    assert body["rows"] == [] and body["total"]["qty"] == 0, body


# ================================================================ AC-RU-5: hidden keys


def test_ac_ru_5_a_key_hidden_from_the_contact_is_not_applied(client, db):
    """AC-RU-5: the contact's policy hides trap_type: not narrowed, echoed under not_applied (hidden)."""
    _trap_world(db)
    contact = _staff(db)
    hide_spec_keys(db, contact, ["trap_type"])
    db.commit()
    body = _ok(client, contact, spec="trap_type:p_trap")
    assert _has_na(body, "spec", "hidden"), body.get("not_applied")
    assert _tot(body) == (21, D("6300.00")), body["total"]
    assert not _spec_echo(body), body["filters"]


def test_ac_ru_5_a_hidden_key_beside_a_visible_one_leaves_the_visible_narrowing(client, db):
    """AC-RU-5: only the hidden key is dropped; length:250 still narrows."""
    _trap_world(db)
    contact = _staff(db)
    hide_spec_keys(db, contact, ["trap_type"])
    db.commit()
    body = _ok(client, contact, spec=["trap_type:p_trap", "length:250"])
    assert _has_na(body, "spec", "hidden"), body.get("not_applied")
    assert _tot(body) == (7, D("1100.00")), body["total"]


def test_ac_ru_5_a_contact_the_policy_does_not_hide_it_from_is_narrowed(client, db):
    """AC-RU-5 control: another contact (no policy row) gets the same key applied."""
    _trap_world(db)
    hidden_from = _staff(db)
    hide_spec_keys(db, hidden_from, ["trap_type"])
    db.commit()
    other = _staff(db)
    body = _ok(client, other, spec="trap_type:p_trap")
    assert _tot(body) == (6, D("700.00")), body["total"]
    assert not _has_na(body, "spec", "hidden"), body.get("not_applied")


# ================================================================ AC-RU-9: the echo


def test_ac_ru_9_the_echo_names_the_spec_by_the_registry_labels(client, db):
    """AC-RU-9: filters carries a spec entry reading "Trap type: P-trap"."""
    _trap_world(db)
    body = _ok(client, _staff(db), spec="trap_type:p_trap")
    echo = _spec_echo(body)
    assert len(echo) == 1, body["filters"]
    assert "Trap type: P-trap" in echo[0]["values"], echo


def test_ac_ru_9_every_applied_spec_is_echoed(client, db):
    """AC-RU-9: two keys, two echoed terms with the registry labels ("Length: 250" carries the number)."""
    _trap_world(db)
    body = _ok(client, _staff(db), spec=["trap_type:p_trap", "length:250"])
    text = " | ".join(v for f in _spec_echo(body) for v in f["values"])
    assert "Trap type: P-trap" in text and "Length: 250" in text, body["filters"]


# ================================================================ AC-RU-6: group_by=spec:<key>


def test_ac_ru_6_group_by_spec_is_one_row_per_value_plus_not_stated_and_sums_to_the_total(client, db):
    """AC-RU-6: rows P-trap 700, S-trap 800, Not stated 4800 (p5 no row, p6 no trap_type)."""
    _trap_world(db)
    contact = _staff(db)
    body = _ok(client, contact, group_by="spec:trap_type", top_n=10)
    assert body["status"] == "ok", body
    assert body["group_by"] == "spec:trap_type", body
    got = _by_name(body)
    assert got == {
        _norm("P-trap"): (6, D("700.00")),
        _norm("S-trap"): (4, D("800.00")),
        _norm(NOT_STATED): (11, D("4800.00")),
    }, body["rows"]
    assert any(r["name"] == NOT_STATED for r in body["rows"]), body["rows"]
    assert sum(money(r["amount"]) for r in body["rows"]) == money(body["total"]["amount"]) == D("6300.00")
    ungrouped = _ok(client, contact)
    assert _tot(ungrouped) == _tot(body) == (21, D("6300.00"))


def test_ac_ru_6_the_rows_rank_by_the_measure(client, db):
    """AC-RU-6: ranked like other groups: by amount Not stated, S-trap, P-trap; by qty Not stated, P-trap, S-trap."""
    _trap_world(db)
    contact = _staff(db)
    by_amount = _ok(client, contact, group_by="spec:trap_type", top_n=10)
    assert [r["rank"] for r in by_amount["rows"]] == [1, 2, 3]
    assert [_norm(r["name"]) for r in by_amount["rows"]] == [_norm(NOT_STATED), _norm("S-trap"), _norm("P-trap")]
    by_qty = _ok(client, contact, group_by="spec:trap_type", top_n=10, measure="qty")
    assert [_norm(r["name"]) for r in by_qty["rows"]] == [_norm(NOT_STATED), _norm("P-trap"), _norm("S-trap")]
    asc = _ok(client, contact, group_by="spec:trap_type", top_n=10, sort="asc")
    assert [_norm(r["name"]) for r in asc["rows"]] == [_norm("P-trap"), _norm("S-trap"), _norm(NOT_STATED)]


def test_ac_ru_6_top_n_cuts_after_the_fold_and_the_total_stays_whole(client, db):
    """AC-RU-6: three p_trap products of 100 each (300) beat one s_trap product of 250, though the
    s_trap product outranks each single p_trap product; top_n=1 therefore reads P-trap 300 only
    if the cut came AFTER the fold. more / total_count count the folded rows."""
    seed_registry(db)
    w = SimpleNamespace(cust=seed_customer(db, name=unique_code("Cust")), wh=warehouse(db, company_id=DEFAULT_COMPANY_ID))
    for n in range(3):
        _sale(db, w, make_product(db, unique_code(f"PT{n}"), specs={"trap_type": "p_trap"}), 1, "100.00")
    _sale(db, w, make_product(db, unique_code("ST"), specs={"trap_type": "s_trap"}), 1, "250.00")
    _sale(db, w, make_product(db, unique_code("NS")), 1, "50.00")
    db.commit()
    body = _ok(client, _staff(db), group_by="spec:trap_type", top_n=1)
    assert [(_norm(r["name"]), money(r["amount"])) for r in body["rows"]] == [(_norm("P-trap"), D("300.00"))], body["rows"]
    assert body["more"] == 2 and body["total_count"] == 3, body
    assert _tot(body) == (5, D("600.00")), body["total"]


def test_ac_ru_6_group_by_a_key_missing_from_the_registry_is_422_unknown_group_by(client, db):
    """AC-RU-6: spec:nosuchkey names no registry key. (Passes today for the wrong reason too; the
    registered-key tests above are the red ones.)"""
    _trap_world(db)
    resp = _ask(client, _staff(db), group_by="spec:nosuchkey", top_n=5)
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") == "unknown_group_by", resp.text


def test_ac_ru_6_group_by_spec_honours_a_spec_filter(client, db):
    """AC-RU-6: the fold runs over the filtered set: p_trap only, so one P-trap row and no S-trap."""
    _trap_world(db)
    body = _ok(client, _staff(db), spec="trap_type:p_trap", group_by="spec:trap_type", top_n=10)
    assert _by_name(body) == {_norm("P-trap"): (6, D("700.00"))}, body["rows"]


# ================================================================ AC-RU-7: the tally (delivered, ordered, outstanding, pending_delivery)


def _tally_world(db):
    """One world for all four bases. Products (spec / SO line qty 10, 4 delivered / DO line):

        pA p_trap  SO total 1000  DO 2 / 100       pD no spec row     SO total 200  DO 2 / 20
        pB p_trap  SO total  500  DO 2 /  50       pE spec row, no trap_type  100  DO 2 / 10
        pC s_trap  SO total  300  DO 2 /  30

    delivered 20 / 840 | ordered 50 / 2100 | outstanding 30 / 1260 | pending_delivery 10 / 210.
    A delivered DO of pA (7 / 999) is in no basis but delivered's SO lines, so pending stays 10 / 210.
    """
    seed_registry(db)
    w = SimpleNamespace()
    w.c1, w.c2 = seed_customer(db, name=unique_code("C1")), seed_customer(db, name=unique_code("C2"))
    w.wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WH"))
    spec = {"A": {"trap_type": "p_trap"}, "B": {"trap_type": "p_trap"}, "C": {"trap_type": "s_trap"}, "D": None, "E": {"length": (1, "mm")}}
    w.p = {k: make_product(db, unique_code(f"T{k}"), specs=v) for k, v in spec.items()}
    for k, total in (("A", "1000.00"), ("B", "500.00"), ("C", "300.00"), ("D", "200.00"), ("E", "100.00")):
        seed_so_line(db, cust=w.c1, prod=w.p[k], qty=10, delivered=4, total=total, wh=w.wh, order_date=SEP)
    seed_do(db, customer_id=w.c1.id, order_date=SEP, source_book="db1", lines=[
        line(w.p["A"].id, w.wh.id, 2, total="100.00"), line(w.p["B"].id, w.wh.id, 2, total="50.00")])
    seed_do(db, customer_id=w.c2.id, order_date=SEP, source_book="db1", lines=[
        line(w.p["C"].id, w.wh.id, 2, total="30.00"), line(w.p["D"].id, w.wh.id, 2, total="20.00"),
        line(w.p["E"].id, w.wh.id, 2, total="10.00")])
    gone = seed_do(db, customer_id=w.c1.id, order_date=SEP, source_book="db1", lines=[
        line(w.p["A"].id, w.wh.id, 7, total="999.00")])
    gone.order_status_id = delivered_status(db).id
    gone.actual_delivery_date = SEP
    db.commit()
    return w


TALLY_EXPECTED = {
    "delivered": (20, D("840.00")),
    "ordered": (50, D("2100.00")),
    "outstanding": (30, D("1260.00")),
    "pending_delivery": (10, D("210.00")),
}


@pytest.mark.parametrize("basis", list(TALLY_EXPECTED))
def test_ac_ru_7_total_equals_sum_by_product_equals_sum_by_spec(client, db, basis):
    """AC-RU-7: no grouping == sum of group_by=product == sum of group_by=spec:trap_type (with Not stated)."""
    _tally_world(db)
    contact = _staff(db)
    total = _ok(client, contact, basis=basis)
    by_product = _ok(client, contact, basis=basis, group_by="product", top_n=1000)
    by_spec = _ok(client, contact, basis=basis, group_by="spec:trap_type", top_n=1000)
    assert _tot(total) == TALLY_EXPECTED[basis], total["total"]
    for grouped in (by_product, by_spec):
        assert sum(r["qty"] for r in grouped["rows"]) == total["total"]["qty"], grouped["rows"]
        assert sum(money(r["amount"]) for r in grouped["rows"]) == money(total["total"]["amount"]), grouped["rows"]
        assert _tot(grouped) == _tot(total), grouped["total"]
    assert any(r["name"] == NOT_STATED for r in by_spec["rows"]), by_spec["rows"]
