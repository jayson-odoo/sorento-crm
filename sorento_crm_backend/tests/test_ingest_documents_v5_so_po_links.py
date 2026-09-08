"""Group V5 - AutoCount linkage widen: `from_so_line_ref` / `from_so_external`
/ `from_po_line_ref` / `from_po_number`, on both `purchase_orders.lines` and
`shipping_orders.lines` (brief: ingest-contract-2-2-so-links; no separate
PLAN file for this slice - the coder brief is the contract, frozen with the
foundryx ESB session).

  AC-V5-1  a PO/SPO line carrying all four new fields is ACCEPTED
  AC-V5-2  a v2.1-shaped payload (none of the four fields) still ingests
           unchanged
  AC-V5-3  `from_so_external` with no `db` fails validation, naming the field

More sections land here as the later commits of this slice add behaviour
(persisting `from_po_line_ref`/`from_po_number` on `spo_allocations`,
resolving `from_so_line_ref` to a precise claim, recording `from_so_external`
raw).

Substrate reused byte-for-byte from `test_ingest_documents.py` /
`test_ingest_shipping_orders.py`, same as every other V-group file in this
suite.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.api.v1.external.contract import FIELDS_ADDED
from app.models.order import SalesOrder, SalesOrderLine

from tests.test_ingest_documents import (
    INGEST_PO,
    MARKER,
    _po_line,
    _po_record,
    _ref,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)
from tests.test_ingest_shipping_orders import (
    INGEST_SPO,
    _spo_line,
    _spo_record,
)

__all__ = ["env"]

CONTRACT_URL = "/api/v1/external/contract"


def _seed_so_line(env, *, so_number: str, product_id: str, source_ref: str, qty=10):
    """A sales order + one line carrying a real `source_ref`, bypassing
    ingest entirely - `from_so_line_ref` resolution is a plain join against
    `sales_order_lines.source_ref`, independent of how that row got there.

    Committed, not just flushed, for the same reason
    `test_ingest_documents_v2_links._seed_plain_so` commits: a dry-run
    ingest call rolls its own transaction back, and an uncommitted seed
    sitting inside that same transaction would vanish with it.
    """
    so = SalesOrder(so_number=so_number, status="open", company_id=env.company_a)
    env.db.add(so)
    env.db.flush()
    line = SalesOrderLine(
        sales_order_id=so.id,
        product_id=product_id,
        qty_ordered=qty,
        source_ref=source_ref,
        company_id=env.company_a,
    )
    env.db.add(line)
    env.db.flush()
    env.db.commit()
    return so, line


def _claims_for(env, *, po_number: str) -> list[dict]:
    """Byte-for-byte copy of `test_ingest_documents_v2_links._claims_for` -
    see that file's own comment for why the table name is bare, not
    `scm.order_link_claim`."""
    rows = (
        env.db.execute(
            text(
                "SELECT so_number, po_number, item_code, source, po_line_id, "
                "spo_allocation_id, so_line_id, resolved_at FROM order_link_claim "
                "WHERE po_number = :po AND company_id = :c"
            ),
            {"po": po_number, "c": env.company_a},
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


def _spo_rows(env, spo_number: str):
    """Byte-for-byte copy of `test_ingest_shipping_orders._spo_rows`."""
    return (
        env.db.execute(
            text(
                "SELECT * FROM spo_allocations WHERE company_id = :c AND spo_number = :n "
                "ORDER BY spo_line_number"
            ),
            {"c": env.company_a, "n": spo_number},
        )
        .mappings()
        .all()
    )


# ============================================================== AC-V5-1/2/3
class TestSchemaAcceptance:
    def test_a_po_line_with_all_four_new_fields_is_accepted(self, env):
        line = _po_line(
            env,
            from_so_line_ref=f"{MARKER}:45700100:45700148",
            from_so_external={"db": "AED_OTHER", "doc_key": 1, "doc_no": "SO-1", "dtl_key": 2},
            from_po_line_ref=f"{MARKER}:44909094:45021331",
            from_po_number="202606-S0018",
        )
        record = _po_record(env, lines=[line])

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text

    def test_a_spo_line_with_all_four_new_fields_is_accepted(self, env):
        line = _spo_line(
            env,
            from_so_line_ref=f"{MARKER}:45700100:45700148",
            from_so_external={"db": "AED_OTHER", "doc_key": 1, "doc_no": None, "dtl_key": None},
            from_po_line_ref=f"{MARKER}:44909094:45021331",
            from_po_number="202606-S0018",
        )
        record = _spo_record(env, lines=[line], supplier_ref=env.supplier_ref)

        res = env.post(INGEST_SPO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text

    def test_a_v21_shaped_po_payload_still_ingests_unchanged(self, env):
        """No trace of any of the four fields - the plain v1/v2.1 shape
        every pre-existing test in this suite already sends."""
        record = _po_record(env)

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text

    def test_from_so_external_with_no_db_fails_and_names_the_field(self, env):
        line = _po_line(env, from_so_external={"doc_key": 1})
        record = _po_record(env, lines=[line])

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", res.text
        assert "lines.0.from_so_external.db" in entry["errors"], entry


# ==================================================================== V5 contract
class TestContractVersion22:
    def test_contract_reports_2_2_and_lists_the_four_fields(self, env):
        res = env.client.get(CONTRACT_URL)

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["version"] == "2.2"
        wanted = {
            "from_so_line_ref", "from_so_external", "from_po_line_ref", "from_po_number",
        }
        for entity in ("purchase_orders", "shipping_orders"):
            got = set(body["fields_added"].get(entity, []))
            assert wanted.issubset(got), (entity, wanted - got)

    def test_the_registry_constant_itself_carries_the_same_fields(self):
        """Pin at the source, not just at the HTTP surface - a future
        refactor of `get_contract()`'s response shape should not be able to
        silently drop these from `FIELDS_ADDED` unnoticed."""
        wanted = {
            "from_so_line_ref", "from_so_external", "from_po_line_ref", "from_po_number",
        }
        for entity in ("purchase_orders", "shipping_orders"):
            got = set(FIELDS_ADDED.get(entity, []))
            assert wanted.issubset(got), (entity, wanted - got)


# ================================================================== AC-V5-4
class TestSpoAllocationPurchaseLink:
    def test_from_po_fields_land_on_the_spo_allocation_row(self, env):
        line = _spo_line(
            env,
            from_po_line_ref=f"{MARKER}:44909094:45021331",
            from_po_number="202606-S0018",
        )
        record = _spo_record(env, lines=[line], supplier_ref=env.supplier_ref)

        res = env.post(INGEST_SPO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text
        row = _spo_rows(env, record["spo_number"])[0]
        assert row["from_po_line_ref"] == f"{MARKER}:44909094:45021331"
        assert row["from_po_number"] == "202606-S0018"

    def test_an_omitted_field_on_repush_never_clears_a_stored_value(self, env):
        line = _spo_line(
            env,
            from_po_line_ref=f"{MARKER}:44909094:45021331",
            from_po_number="202606-S0018",
        )
        record = _spo_record(env, lines=[line], supplier_ref=env.supplier_ref)
        first = env.post(INGEST_SPO, [record])
        assert first.json()["records"][0]["outcome"] == "created", first.text

        # Re-push the SAME line by source_ref, this time with neither key
        # sent at all - the ordinary shape of a routine re-push.
        repush_line = _spo_line(env, ref=line["source_ref"])
        repush = dict(record, lines=[repush_line])

        res = env.post(INGEST_SPO, [repush])

        assert res.json()["records"][0]["outcome"] == "updated", res.text
        row = _spo_rows(env, record["spo_number"])[0]
        assert row["from_po_line_ref"] == f"{MARKER}:44909094:45021331"
        assert row["from_po_number"] == "202606-S0018"


# ================================================================ AC-V5-5/6
class TestFromSoLineRefClaims:
    def test_a_resolvable_ref_writes_the_claim_already_paired_on_a_po_line(self, env):
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        so_ref = _ref("SOL")
        so, so_line = _seed_so_line(
            env,
            so_number=f"{MARKER}-SOA-{uuid.uuid4().hex[:8]}",
            product_id=product_id,
            source_ref=so_ref,
        )

        line = _po_line(env, from_so_line_ref=so_ref)
        record = _po_record(env, lines=[line])

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        claims = _claims_for(env, po_number=record["po_number"])
        assert len(claims) == 1, claims
        claim = claims[0]
        assert claim["so_number"] == so.so_number
        assert str(claim["so_line_id"]) == str(so_line.id)
        assert claim["source"] == "autocount"
        assert claim["resolved_at"] is not None

    def test_an_unresolvable_ref_falls_back_to_the_from_so_numbers_open_claim(self, env):
        """The SO has not been pushed yet - the normal case. There is no
        number inside a ref alone, so this proves the plain `from_so_numbers`
        companion field still opens a claim exactly as it did before this
        slice, unaffected by the ref failing to resolve."""
        so_a = f"{MARKER}-SOA-{uuid.uuid4().hex[:8]}"
        line = _po_line(
            env,
            from_so_numbers=[so_a],
            from_so_line_ref=f"{MARKER}:99999999:99999999",  # resolves to nothing
        )
        record = _po_record(env, lines=[line])

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        claims = _claims_for(env, po_number=record["po_number"])
        assert len(claims) == 1, claims
        assert claims[0]["so_number"] == so_a
        assert claims[0]["so_line_id"] is None
        assert claims[0]["resolved_at"] is None

    def test_a_resolvable_ref_writes_the_claim_already_paired_on_an_spo_line(self, env):
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        so_ref = _ref("SOL")
        so, so_line = _seed_so_line(
            env,
            so_number=f"{MARKER}-SOA-{uuid.uuid4().hex[:8]}",
            product_id=product_id,
            source_ref=so_ref,
        )

        line = _spo_line(env, from_so_line_ref=so_ref)
        record = _spo_record(env, lines=[line], supplier_ref=env.supplier_ref)

        res = env.post(INGEST_SPO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        claims = _claims_for(env, po_number=record["spo_number"])
        assert len(claims) == 1, claims
        claim = claims[0]
        assert claim["so_number"] == so.so_number
        assert str(claim["so_line_id"]) == str(so_line.id)
        assert claim["spo_allocation_id"] is not None
        assert claim["po_line_id"] is None
        assert claim["resolved_at"] is not None

    def test_repush_does_not_duplicate_the_ref_claim(self, env):
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        so_ref = _ref("SOL")
        _seed_so_line(
            env,
            so_number=f"{MARKER}-SOA-{uuid.uuid4().hex[:8]}",
            product_id=product_id,
            source_ref=so_ref,
        )
        line = _po_line(env, from_so_line_ref=so_ref)
        record = _po_record(env, lines=[line])

        first = env.post(INGEST_PO, [record])
        assert first.json()["records"][0]["outcome"] == "created", first.text
        second = env.post(INGEST_PO, [record])

        assert second.json()["records"][0]["outcome"] == "updated", second.text
        assert len(_claims_for(env, po_number=record["po_number"])) == 1


# ================================================================== AC-V5-7
class TestFromSoExternalRawStorage:
    def test_from_so_external_lands_raw_on_the_purchase_order_line(self, env):
        line = _po_line(
            env,
            from_so_external={
                "db": "AED_OTHER", "doc_key": 45700100, "doc_no": "SO-9", "dtl_key": 45700148,
            },
        )
        record = _po_record(env, lines=[line])

        res = env.post(INGEST_PO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text
        header = env.header("purchase_orders", record["source_ref"])
        po_line = env.po_lines(header["id"])[0]
        assert po_line["from_so_external"] == {
            "db": "AED_OTHER", "doc_key": 45700100, "doc_no": "SO-9", "dtl_key": 45700148,
        }
        # Never resolved into a claim - there is no so_number a cross-book
        # key can name, so no `order_link_claim` row exists for this
        # document at all.
        assert _claims_for(env, po_number=record["po_number"]) == []

    def test_from_so_external_lands_raw_on_the_spo_allocation_row(self, env):
        line = _spo_line(
            env,
            from_so_external={"db": "AED_OTHER", "doc_key": 1, "doc_no": None, "dtl_key": None},
        )
        record = _spo_record(env, lines=[line], supplier_ref=env.supplier_ref)

        res = env.post(INGEST_SPO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text
        row = _spo_rows(env, record["spo_number"])[0]
        assert row["from_so_external"] == {
            "db": "AED_OTHER", "doc_key": 1, "doc_no": None, "dtl_key": None,
        }


# ==================================================================== S1
class TestExplicitNullClears:
    """`test_an_omitted_field_on_repush_never_clears_a_stored_value` passes
    even under a truthiness check, since an OMITTED field yields `None` the
    same way an explicit `null` does. These tests are what actually pins
    `model_fields_set` (presence, not truthiness) and therefore the
    `absent_vs_null: true` the contract advertises: an explicit `null` DOES
    clear a stored value, on both `purchase_order_lines` and
    `spo_allocations`.
    """

    def test_an_explicit_null_clears_from_po_line_ref_on_a_purchase_order_line(self, env):
        line = _po_line(env, from_po_line_ref=f"{MARKER}:44909094:45021331")
        record = _po_record(env, lines=[line])
        first = env.post(INGEST_PO, [record])
        assert first.json()["records"][0]["outcome"] == "created", first.text

        repush_line = _po_line(env, ref=line["source_ref"], from_po_line_ref=None)
        repush = dict(record, lines=[repush_line])
        res = env.post(INGEST_PO, [repush])

        assert res.json()["records"][0]["outcome"] == "updated", res.text
        header = env.header("purchase_orders", record["source_ref"])
        po_line = env.po_lines(header["id"])[0]
        assert po_line["from_po_line_ref"] is None

    def test_an_explicit_null_clears_from_po_line_ref_on_an_spo_line(self, env):
        line = _spo_line(env, from_po_line_ref=f"{MARKER}:44909094:45021331")
        record = _spo_record(env, lines=[line], supplier_ref=env.supplier_ref)
        first = env.post(INGEST_SPO, [record])
        assert first.json()["records"][0]["outcome"] == "created", first.text

        repush_line = _spo_line(env, ref=line["source_ref"], from_po_line_ref=None)
        repush = dict(record, lines=[repush_line])
        res = env.post(INGEST_SPO, [repush])

        assert res.json()["records"][0]["outcome"] == "updated", res.text
        row = _spo_rows(env, record["spo_number"])[0]
        assert row["from_po_line_ref"] is None

    def test_an_explicit_null_clears_from_so_external_on_a_purchase_order_line(self, env):
        line = _po_line(env, from_so_external={"db": "AED_OTHER", "doc_key": 1})
        record = _po_record(env, lines=[line])
        first = env.post(INGEST_PO, [record])
        assert first.json()["records"][0]["outcome"] == "created", first.text

        repush_line = _po_line(env, ref=line["source_ref"], from_so_external=None)
        repush = dict(record, lines=[repush_line])
        res = env.post(INGEST_PO, [repush])

        assert res.json()["records"][0]["outcome"] == "updated", res.text
        header = env.header("purchase_orders", record["source_ref"])
        po_line = env.po_lines(header["id"])[0]
        assert po_line["from_so_external"] is None

    def test_an_explicit_null_clears_from_so_external_on_an_spo_line(self, env):
        line = _spo_line(env, from_so_external={"db": "AED_OTHER", "doc_key": 1})
        record = _spo_record(env, lines=[line], supplier_ref=env.supplier_ref)
        first = env.post(INGEST_SPO, [record])
        assert first.json()["records"][0]["outcome"] == "created", first.text

        repush_line = _spo_line(env, ref=line["source_ref"], from_so_external=None)
        repush = dict(record, lines=[repush_line])
        res = env.post(INGEST_SPO, [repush])

        assert res.json()["records"][0]["outcome"] == "updated", res.text
        row = _spo_rows(env, record["spo_number"])[0]
        assert row["from_so_external"] is None
