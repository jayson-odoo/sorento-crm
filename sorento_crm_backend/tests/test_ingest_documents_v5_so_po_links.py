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

from sqlalchemy import text

from app.api.v1.external.contract import FIELDS_ADDED

from tests.test_ingest_documents import (
    INGEST_PO,
    MARKER,
    _po_line,
    _po_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)
from tests.test_ingest_shipping_orders import (
    INGEST_SPO,
    _spo_line,
    _spo_record,
)

__all__ = ["env"]

CONTRACT_URL = "/api/v1/external/contract"


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
