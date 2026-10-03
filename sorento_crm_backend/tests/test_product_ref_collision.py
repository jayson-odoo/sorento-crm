"""RED tests for PRODUCT-REF-COLLISION (code-first, owner ruling 3 Oct), AC-1..AC-10.

UAC: documentation/plans/autocount/product-ref-collision-acceptance-criteria.md

Product identity is company + normalised product code, for the feed and for every
document line; `source_ref` is link/audit only. Billing documents are covered in
tests/test_product_ref_collision_billing.py (that suite has its own env).

Substrate: the `env` fixture of tests.test_ingest_documents (blank Postgres schema,
real routes). Every scenario seeds its own products.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.product import Product
from app.services.master_ref_resolver import WARN_REF_MISMATCH

from tests.test_ingest_documents import (
    INGEST_PO,
    INGEST_SO,
    MARKER,
    _po_line,
    _po_record,
    _so_line,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)
from tests.test_ingest_shipping_orders import INGEST_SPO, _spo_line, _spo_record, _spo_rows

__all__ = ["env"]

BOOK = "AED_V2_MOCHA"
FOREIGN_CODE = "MKT4524SS-DIY"
INGEST_PRODUCTS = "/api/v1/external/ingest/products"


# ------------------------------------------------------------------ helpers
def _product(env, code: str, *, list_price=Decimal("10.00")) -> str:
    row = Product(
        product_code=code,
        product_name=code,
        category_id=env._category.id,
        base_uom_id=env._uom.id,
        list_price=list_price,
        company_id=env.company_a,
    )
    env.db.add(row)
    env.db.flush()
    env.db.commit()
    return str(row.id)


def _link(env, product_id: str, ref: str) -> None:
    env.refs.link(entity_type="products", entity_id=product_id, source_ref=ref)
    env.db.commit()


def _row(env, product_id: str):
    env.db.expire_all()
    return env.db.execute(
        text("SELECT * FROM products WHERE id = :i"), {"i": product_id}
    ).mappings().first()


def _snapshot(env, product_id: str) -> dict:
    return dict(_row(env, product_id))


def _refs_of(env, product_id: str) -> list[str]:
    return list(
        env.db.execute(
            text(
                "SELECT source_ref FROM integration_references "
                "WHERE entity_type = 'products' AND entity_id = :i"
            ),
            {"i": product_id},
        ).scalars()
    )


def _owner_of(env, ref: str):
    v = env.db.execute(
        text(
            "SELECT entity_id FROM integration_references "
            "WHERE source_ref = :r AND entity_type = 'products'"
        ),
        {"r": ref},
    ).scalar()
    return str(v) if v else None


def _count_code(env, code: str) -> int:
    return env.db.execute(
        text("SELECT count(*) FROM products WHERE product_code = :c AND company_id = :co"),
        {"c": code, "co": env.company_a},
    ).scalar()


def _push(env, records, *, dry_run=False):
    res = env.post(INGEST_PRODUCTS, records, dry_run=dry_run)
    assert res.status_code == 200, res.text
    return res.json()["records"]


def _foreign_setup(env):
    """MKT4524SS-DIY holds ref BOOK:2001; product '2001' exists with no ref."""
    ref = f"{BOOK}:2001"
    foreign_id = _product(env, FOREIGN_CODE)
    _link(env, foreign_id, ref)
    target_id = _product(env, "2001")
    return ref, foreign_id, target_id


# ------------------------------------------------------------- product feed
class TestFeedPush:
    def test_ac1_foreign_ref_updates_the_code_owner_not_the_ref_holder(self, env):
        ref, foreign_id, target_id = _foreign_setup(env)
        before = _snapshot(env, foreign_id)

        (entry,) = _push(env, [{"source_ref": ref, "code": "2001", "name": "Renamed Two Thousand One"}])

        assert entry["outcome"] != "failed", entry
        assert entry["entity_id"] == target_id, entry
        assert WARN_REF_MISMATCH in entry.get("warnings", []), entry
        assert _row(env, target_id)["product_name"] == "Renamed Two Thousand One"
        assert _snapshot(env, foreign_id) == before
        assert _owner_of(env, ref) == foreign_id

    def test_ac1_dry_run_reports_no_failure(self, env):
        ref, foreign_id, target_id = _foreign_setup(env)
        before = _snapshot(env, foreign_id)

        (entry,) = _push(
            env, [{"source_ref": ref, "code": "2001", "name": "Renamed Two Thousand One"}], dry_run=True
        )

        assert entry["outcome"] != "failed", entry
        assert entry["entity_id"] == target_id, entry
        assert WARN_REF_MISMATCH in entry.get("warnings", []), entry
        assert _snapshot(env, foreign_id) == before

    def test_ac2_foreign_ref_with_no_code_owner_creates_and_does_not_link(self, env):
        ref = f"{BOOK}:2004"
        foreign_id = _product(env, "MKT4528ASS-DIY")
        _link(env, foreign_id, ref)
        before = _snapshot(env, foreign_id)
        assert _count_code(env, "2004") == 0

        (entry,) = _push(env, [{"source_ref": ref, "code": "2004", "name": "Two Thousand Four"}])

        assert entry["outcome"] == "created", entry
        assert WARN_REF_MISMATCH in entry.get("warnings", []), entry
        new_id = entry["entity_id"]
        assert new_id and new_id != foreign_id, entry
        assert _count_code(env, "2004") == 1
        assert _snapshot(env, foreign_id) == before
        assert _owner_of(env, ref) == foreign_id
        assert _refs_of(env, new_id) == []

    def test_ac3_agreeing_ref_updates_without_warning(self, env):
        ref = f"{BOOK}:2001"
        product_id = _product(env, "2001")
        _link(env, product_id, ref)

        (entry,) = _push(
            env, [{"source_ref": ref, "code": "2001", "name": "Agreed", "list_price": "42.00"}]
        )

        assert entry["outcome"] == "updated", entry
        assert entry["entity_id"] == product_id
        assert WARN_REF_MISMATCH not in entry.get("warnings", []), entry
        assert _row(env, product_id)["list_price"] == Decimal("42.00")

    def test_ac4a_code_owner_without_ref_is_linked_under_the_pushed_ref(self, env):
        ref = f"{BOOK}:2001"
        product_id = _product(env, "2001")
        assert _owner_of(env, ref) is None

        (entry,) = _push(env, [{"source_ref": ref, "code": "2001", "name": "Adopted"}])

        assert entry["outcome"] == "updated", entry
        assert entry["entity_id"] == product_id
        assert WARN_REF_MISMATCH not in entry.get("warnings", []), entry
        assert _owner_of(env, ref) == product_id

    def test_ac4b_code_owner_with_a_different_ref_keeps_its_stored_ref(self, env):
        stored = f"{BOOK}:99001"
        product_id = _product(env, "2001")
        _link(env, product_id, stored)
        pushed = f"{BOOK}:2001"

        (entry,) = _push(env, [{"source_ref": pushed, "code": "2001", "name": "Kept"}])

        assert entry["outcome"] == "updated", entry
        assert entry["entity_id"] == product_id
        assert _refs_of(env, product_id) == [stored]
        assert _owner_of(env, pushed) is None

    def test_ac9_feed_code_comparison_ignores_case_and_edge_whitespace(self, env):
        ref = f"{BOOK}:2001"
        product_id = _product(env, FOREIGN_CODE)
        _link(env, product_id, ref)

        (entry,) = _push(env, [{"source_ref": ref, "code": " mkt4524ss-diy ", "name": "Same"}])

        assert entry["outcome"] == "updated", entry
        assert entry["entity_id"] == product_id
        assert WARN_REF_MISMATCH not in entry.get("warnings", []), entry

    def test_ac10_two_records_in_one_batch_hit_foreign_refs(self, env):
        ref, foreign_id, target_id = _foreign_setup(env)
        ref2 = f"{BOOK}:2004"
        foreign2_id = _product(env, "MKT4528ASS-DIY")
        _link(env, foreign2_id, ref2)

        entries = _push(
            env,
            [
                {"source_ref": ref, "code": "2001", "name": "Batch One"},
                {"source_ref": ref2, "code": "2004", "name": "Batch Four"},
                {"source_ref": ref, "code": "2001", "name": "Batch One Again"},
            ],
        )

        assert all(e["outcome"] != "failed" for e in entries), entries
        assert entries[0]["entity_id"] == target_id, entries
        assert entries[2]["entity_id"] == target_id, entries
        assert entries[1]["entity_id"] not in (foreign_id, foreign2_id), entries
        for e in entries:
            assert WARN_REF_MISMATCH in e.get("warnings", []), e
        assert _row(env, foreign_id)["product_code"] == FOREIGN_CODE
        assert _row(env, foreign2_id)["product_code"] == "MKT4528ASS-DIY"
        assert _owner_of(env, ref) == foreign_id
        assert _owner_of(env, ref2) == foreign2_id


# --------------------------------------------------------- SO line (SO ref)
def _so_bound(env, record) -> str | None:
    header = env.header("sales_orders", record["source_ref"])
    if header is None:
        return None
    lines = env.so_lines(header["id"])
    return str(lines[0]["product_id"]) if lines else None


def _so_post(env, **line_extra):
    line = {"source_ref": f"{BOOK}:L1", "qty_ordered": 3, **line_extra}
    record = _so_record(env, lines=[line])
    res = env.post(INGEST_SO, [record])
    assert res.status_code == 200, res.text
    return res.json()["records"][0], record


class TestSalesOrderLine:
    def test_ac5_ref_and_code_agree_binds_without_warning(self, env):
        ref = f"{BOOK}:2001"
        pid = _product(env, FOREIGN_CODE)
        _link(env, pid, ref)

        entry, record = _so_post(env, product_ref=ref, product_code=FOREIGN_CODE)

        assert entry["outcome"] == "created", entry
        assert WARN_REF_MISMATCH not in entry.get("warnings", []), entry
        assert _so_bound(env, record) == pid

    def test_ac6_ref_hits_a_code_owned_by_b_binds_b(self, env):
        ref = f"{BOOK}:2001"
        a_id = _product(env, FOREIGN_CODE)
        _link(env, a_id, ref)
        b_id = _product(env, "2001")
        before_a = _snapshot(env, a_id)

        entry, record = _so_post(env, product_ref=ref, product_code="2001")

        assert entry["outcome"] == "created", entry
        assert WARN_REF_MISMATCH in entry.get("warnings", []), entry
        assert _so_bound(env, record) == b_id
        assert _snapshot(env, a_id) == before_a
        assert _owner_of(env, ref) == a_id

    def test_ac6_b_without_a_ref_is_bound_and_the_ref_is_not_moved(self, env):
        ref = f"{BOOK}:2001"
        a_id = _product(env, FOREIGN_CODE)
        _link(env, a_id, ref)
        b_id = _product(env, "2001")
        assert _refs_of(env, b_id) == []

        entry, record = _so_post(env, product_ref=ref, product_code="2001")

        assert entry["outcome"] == "created", entry
        assert _so_bound(env, record) == b_id
        assert _owner_of(env, ref) == a_id
        assert _refs_of(env, b_id) == []

    def test_ac7_code_owned_by_nobody_is_retryable_missing_product(self, env):
        ref = f"{BOOK}:2004"
        a_id = _product(env, "MKT4528ASS-DIY")
        _link(env, a_id, ref)
        assert _count_code(env, "2004") == 0

        entry, record = _so_post(env, product_ref=ref, product_code="2004")

        assert entry["outcome"] == "retryable", entry
        assert "product_code" in entry.get("errors", {}), entry
        assert env.header("sales_orders", record["source_ref"]) is None

    def test_ac8_no_product_code_resolves_by_ref_as_today(self, env):
        ref = f"{BOOK}:2001"
        pid = _product(env, FOREIGN_CODE)
        _link(env, pid, ref)

        entry, record = _so_post(env, product_ref=ref)

        assert entry["outcome"] == "created", entry
        assert WARN_REF_MISMATCH not in entry.get("warnings", []), entry
        assert _so_bound(env, record) == pid

    def test_ac9_line_code_comparison_ignores_case_and_whitespace(self, env):
        ref = f"{BOOK}:2001"
        pid = _product(env, FOREIGN_CODE)
        _link(env, pid, ref)

        entry, record = _so_post(env, product_ref=ref, product_code=" mkt4524ss-diy ")

        assert entry["outcome"] == "created", entry
        assert WARN_REF_MISMATCH not in entry.get("warnings", []), entry
        assert _so_bound(env, record) == pid


# -------------------------------------------------------------- PO line
def _po_post(env, **line_extra):
    line = {"source_ref": f"{BOOK}:PL1", "qty_ordered": 4, **line_extra}
    record = _po_record(env, lines=[line], supplier_ref=env.supplier_ref)
    res = env.post(INGEST_PO, [record])
    assert res.status_code == 200, res.text
    return res.json()["records"][0], record


def _po_bound(env, record) -> str | None:
    header = env.header("purchase_orders", record["source_ref"])
    if header is None:
        return None
    lines = env.po_lines(header["id"])
    return str(lines[0]["product_id"]) if lines else None


class TestPurchaseOrderLine:
    def test_ac6_ref_hits_a_code_owned_by_b_binds_b(self, env):
        ref = f"{BOOK}:2001"
        a_id = _product(env, FOREIGN_CODE)
        _link(env, a_id, ref)
        b_id = _product(env, "2001")

        entry, record = _po_post(env, product_ref=ref, product_code="2001")

        assert entry["outcome"] == "created", entry
        assert WARN_REF_MISMATCH in entry.get("warnings", []), entry
        assert _po_bound(env, record) == b_id
        assert _owner_of(env, ref) == a_id

    def test_ac7_code_owned_by_nobody_is_retryable_missing_product(self, env):
        ref = f"{BOOK}:2004"
        a_id = _product(env, "MKT4528ASS-DIY")
        _link(env, a_id, ref)

        entry, record = _po_post(env, product_ref=ref, product_code="2004")

        assert entry["outcome"] == "retryable", entry
        assert "product_code" in entry.get("errors", {}), entry
        assert env.header("purchase_orders", record["source_ref"]) is None

    def test_ac8_no_product_code_resolves_by_ref_as_today(self, env):
        ref = f"{BOOK}:2001"
        pid = _product(env, FOREIGN_CODE)
        _link(env, pid, ref)

        entry, record = _po_post(env, product_ref=ref)

        assert entry["outcome"] == "created", entry
        assert _po_bound(env, record) == pid


# -------------------------------------------------------------- SPO line
def _spo_post(env, **line_extra):
    line = {"source_ref": f"{BOOK}:SL1", "qty_ordered": 10, **line_extra}
    record = _spo_record(env, lines=[line], supplier_ref=env.supplier_ref)
    res = env.post(INGEST_SPO, [record])
    assert res.status_code == 200, res.text
    return res.json()["records"][0], record


class TestShippingOrderLine:
    def test_ac6_ref_hits_a_code_owned_by_b_binds_b(self, env):
        ref = f"{BOOK}:2001"
        a_id = _product(env, FOREIGN_CODE)
        _link(env, a_id, ref)
        b_id = _product(env, "2001")

        entry, record = _spo_post(env, product_ref=ref, product_code="2001")

        assert entry["outcome"] == "created", entry
        assert WARN_REF_MISMATCH in entry.get("warnings", []), entry
        rows = _spo_rows(env, record["spo_number"])
        assert [str(r["product_id"]) for r in rows] == [b_id]
        assert _owner_of(env, ref) == a_id

    def test_ac7_code_owned_by_nobody_is_retryable_missing_product(self, env):
        ref = f"{BOOK}:2004"
        a_id = _product(env, "MKT4528ASS-DIY")
        _link(env, a_id, ref)

        entry, record = _spo_post(env, product_ref=ref, product_code="2004")

        assert entry["outcome"] == "retryable", entry
        assert "product_code" in entry.get("errors", {}), entry
        assert _spo_rows(env, record["spo_number"]) == []

    def test_ac8_no_product_code_resolves_by_ref_as_today(self, env):
        ref = f"{BOOK}:2001"
        pid = _product(env, FOREIGN_CODE)
        _link(env, pid, ref)

        entry, record = _spo_post(env, product_ref=ref)

        assert entry["outcome"] == "created", entry
        rows = _spo_rows(env, record["spo_number"])
        assert [str(r["product_id"]) for r in rows] == [pid]
