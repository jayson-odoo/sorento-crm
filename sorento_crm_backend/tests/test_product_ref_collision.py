"""RED tests for PRODUCT-REF-COLLISION (AC-1..AC-7).

UAC: documentation/plans/autocount/product-ref-collision-acceptance-criteria.md

AutoCount document lines link products under `<BOOK>:<ItemAutoKey>` (numeric)
while the product feed sends `<BOOK>:<ItemCode>`. A feed ref that lands on a
foreign product (different code) must not rename/overwrite it, and a document
line whose ref disagrees with its sent code must prefer the code's owner.

Substrate: the `env` fixture of tests.test_ingest_products_code_wins (blank
Postgres schema, real routes). Every scenario seeds its own chain.
"""
from __future__ import annotations

from decimal import Decimal

from app.services.master_ref_resolver import WARN_REF_MISMATCH

from tests.test_ingest_products_code_wins import MARKER, env  # noqa: F401 - fixture reuse

__all__ = ["env"]

BOOK = "AED_V2_MOCHA"
FOREIGN_CODE = "MKT4524SS-DIY"
INGEST_SO = "/api/v1/external/ingest/sales_orders"


def _so_post(env, lines: list[dict]):
    import uuid

    record = {
        "source_ref": f"{BOOK}:SO:{uuid.uuid4().hex[:8]}",
        "so_number": f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
        "status": "open",
        "lines": lines,
    }
    res = env.client.post(INGEST_SO, json={"companyCode": env.company_a_code, "records": [record]})
    assert res.status_code == 200, res.text
    return res.json()["records"][0], record


def _line_product_id(env, entry_record: dict, line_idx: int = 0):
    from sqlalchemy import text

    header_id = _owner_of(env, "sales_orders", entry_record["source_ref"])
    rows = (
        env.db.execute(
            text("SELECT product_id FROM sales_order_lines WHERE sales_order_id = :i ORDER BY created_at, id"),
            {"i": header_id},
        )
        .scalars()
        .all()
    )
    return str(rows[line_idx]) if rows else None


def _owner_of(env, entity_type: str, ref: str):
    from sqlalchemy import text

    return env.db.execute(
        text("SELECT entity_id FROM integration_references WHERE source_ref = :r AND entity_type = :t"),
        {"r": ref, "t": entity_type},
    ).scalar()


def _count_products(env, code: str) -> int:
    from sqlalchemy import text

    return env.db.execute(
        text("SELECT count(*) FROM products WHERE product_code = :c AND company_id = :co"),
        {"c": code, "co": env.company_a},
    ).scalar()


def _snapshot(env, product_id: str) -> dict:
    return dict(env.row("products", product_id))


def _foreign_setup(env):
    """Product FOREIGN_CODE holds ref BOOK:2001; product '2001' exists unlinked."""
    ref = f"{BOOK}:2001"
    foreign_id, _ = env.product(code=FOREIGN_CODE, list_price=Decimal("10.00"))
    env.link("products", foreign_id, ref=ref)
    target_id, _ = env.product(code="2001", list_price=Decimal("10.00"))
    return ref, foreign_id, target_id


class TestFeedPush:
    def test_t1_foreign_ref_hit_updates_the_code_owner_not_the_ref_holder(self, env):
        ref, foreign_id, target_id = _foreign_setup(env)
        before = _snapshot(env, foreign_id)

        res = env.ingest("products", [{"source_ref": ref, "code": "2001", "name": "Renamed Two Thousand One"}])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] != "failed", entry
        assert entry["entity_id"] == target_id, entry
        assert WARN_REF_MISMATCH in entry.get("warnings", []), entry
        assert env.row("products", target_id)["product_name"] == "Renamed Two Thousand One"
        after = _snapshot(env, foreign_id)
        assert after["product_code"] == FOREIGN_CODE
        assert after["product_name"] == before["product_name"]
        assert str(_owner_of(env, "products", ref)) == foreign_id

    def test_t1_dry_run_reports_no_failure(self, env):
        ref, foreign_id, target_id = _foreign_setup(env)

        res = env.ingest(
            "products",
            [{"source_ref": ref, "code": "2001", "name": "Renamed Two Thousand One"}],
            dry_run=True,
        )

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] != "failed", entry
        assert entry["entity_id"] == target_id, entry
        assert WARN_REF_MISMATCH in entry.get("warnings", []), entry
        assert env.row("products", foreign_id)["product_code"] == FOREIGN_CODE

    def test_t2_foreign_ref_with_no_code_owner_creates_a_new_product(self, env):
        ref = f"{BOOK}:2004"
        foreign_id, foreign_code = env.product(code="MKT4528ASS-DIY")
        env.link("products", foreign_id, ref=ref)
        before = _snapshot(env, foreign_id)
        assert _count_products(env, "2004") == 0

        res = env.ingest("products", [{"source_ref": ref, "code": "2004", "name": "Two Thousand Four"}])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] != "failed", entry
        assert entry["outcome"] == "created", entry
        assert WARN_REF_MISMATCH in entry.get("warnings", []), entry
        assert entry["entity_id"] != foreign_id, entry
        assert _count_products(env, "2004") == 1
        after = _snapshot(env, foreign_id)
        assert after["product_code"] == foreign_code
        assert after["product_name"] == before["product_name"]
        assert str(_owner_of(env, "products", ref)) == foreign_id

    def test_t3_agreeing_ref_updates_as_today_without_warning(self, env):
        ref = f"{BOOK}:2001"
        product_id, code = env.product(code="2001")
        env.link("products", product_id, ref=ref)

        res = env.ingest("products", [{"source_ref": ref, "code": "2001", "name": "Agreed Name", "list_price": "42.00"}])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", entry
        assert entry["entity_id"] == product_id
        assert WARN_REF_MISMATCH not in entry.get("warnings", []), entry
        assert env.row("products", product_id)["list_price"] == Decimal("42.00")

    def test_t5_code_comparison_ignores_case_and_edge_whitespace(self, env):
        ref = f"{BOOK}:2001"
        product_id, _ = env.product(code=FOREIGN_CODE)
        env.link("products", product_id, ref=ref)

        res = env.ingest(
            "products", [{"source_ref": ref, "code": " mkt4524ss-diy ", "name": "Same Product"}]
        )

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", entry
        assert entry["entity_id"] == product_id
        assert WARN_REF_MISMATCH not in entry.get("warnings", []), entry

    def test_t5_two_records_in_one_batch_hit_the_same_foreign_ref(self, env):
        ref, foreign_id, target_id = _foreign_setup(env)
        ref2 = f"{BOOK}:2004"
        foreign2_id, _ = env.product(code="MKT4528ASS-DIY")
        env.link("products", foreign2_id, ref=ref2)

        res = env.ingest(
            "products",
            [
                {"source_ref": ref, "code": "2001", "name": "Batch Two Thousand One"},
                {"source_ref": ref2, "code": "2004", "name": "Batch Two Thousand Four"},
                {"source_ref": ref, "code": "2001", "name": "Batch Two Thousand One Again"},
            ],
        )

        assert res.status_code == 200, res.text
        entries = res.json()["records"]
        assert [e["outcome"] for e in entries] != [], entries
        assert all(e["outcome"] != "failed" for e in entries), entries
        assert entries[0]["entity_id"] == target_id, entries
        assert entries[2]["entity_id"] == target_id, entries
        assert entries[1]["entity_id"] not in (foreign_id, foreign2_id), entries
        for e in entries:
            assert WARN_REF_MISMATCH in e.get("warnings", []), e
        assert env.row("products", foreign_id)["product_code"] == FOREIGN_CODE
        assert env.row("products", foreign2_id)["product_code"] == "MKT4528ASS-DIY"
        assert str(_owner_of(env, "products", ref)) == foreign_id
        assert str(_owner_of(env, "products", ref2)) == foreign2_id


class TestSalesOrderLine:
    def test_t4a_ref_and_code_agree_binds_without_warning(self, env):
        ref = f"{BOOK}:2001"
        product_id, _ = env.product(code=FOREIGN_CODE)
        env.link("products", product_id, ref=ref)

        entry, record = _so_post(
            env,
            [{"source_ref": f"{BOOK}:L1", "product_ref": ref, "product_code": FOREIGN_CODE, "qty_ordered": 3}],
        )

        assert entry["outcome"] == "created", entry
        assert WARN_REF_MISMATCH not in entry.get("warnings", []), entry
        assert _line_product_id(env, record) == product_id

    def test_t4b_ref_hits_a_but_code_owned_by_b_binds_b(self, env):
        ref = f"{BOOK}:2001"
        a_id, _ = env.product(code=FOREIGN_CODE)
        env.link("products", a_id, ref=ref)
        b_id, _ = env.product(code="2001")

        entry, record = _so_post(
            env,
            [{"source_ref": f"{BOOK}:L1", "product_ref": ref, "product_code": "2001", "qty_ordered": 3}],
        )

        assert entry["outcome"] == "created", entry
        assert WARN_REF_MISMATCH in entry.get("warnings", []), entry
        assert _line_product_id(env, record) == b_id

    def test_t4c_ref_hits_a_and_code_owned_by_nobody_is_retryable_missing_product(self, env):
        # Owner decision pending (recommended option): flip this test if the
        # owner rules the line should bind A with ref_mismatch instead.
        ref = f"{BOOK}:2004"
        a_id, _ = env.product(code="MKT4528ASS-DIY")
        env.link("products", a_id, ref=ref)
        assert _count_products(env, "2004") == 0

        entry, record = _so_post(
            env,
            [{"source_ref": f"{BOOK}:L1", "product_ref": ref, "product_code": "2004", "qty_ordered": 3}],
        )

        assert entry["outcome"] == "retryable", entry
        assert "product_code" in entry.get("errors", {}), entry
        assert _owner_of(env, "sales_orders", record["source_ref"]) is None
        from sqlalchemy import text

        bound = env.db.execute(
            text("SELECT count(*) FROM sales_order_lines WHERE product_id = :p"), {"p": a_id}
        ).scalar()
        assert bound == 0

    def test_t5_line_code_comparison_ignores_case_and_whitespace(self, env):
        ref = f"{BOOK}:2001"
        product_id, _ = env.product(code=FOREIGN_CODE)
        env.link("products", product_id, ref=ref)

        entry, record = _so_post(
            env,
            [{"source_ref": f"{BOOK}:L1", "product_ref": ref, "product_code": " mkt4524ss-diy ", "qty_ordered": 3}],
        )

        assert entry["outcome"] == "created", entry
        assert WARN_REF_MISMATCH not in entry.get("warnings", []), entry
        assert _line_product_id(env, record) == product_id
