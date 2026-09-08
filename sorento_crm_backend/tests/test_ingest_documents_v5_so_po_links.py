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
