# PLAN: chatbot "SPO" routes to SPO allocations; warehouse filter on PO and SPO asks

Status: PLANNING (small fix track, no UI change). Lane PO-SPO-WAREHOUSE, 29 Sep 2026.
UAC: `po-spo-warehouse-29sep-acceptance-criteria.md`.

## Owner rulings (29 Sep 2026, verbatim intent)

- "SPO should be SPO allocations answer, not considered incoming." The word SPO routes to
  the `spo_allocation` domain, never `incoming`.
- Warehouse/location filtering on PO (`purchase_order`) and SPO (`spo_allocation`) asks.
- "incoming stays as it is": the incoming domain and its tools are untouched.

## Measured (filled in as the lane progresses)

To be re-verified against the code on this branch before implementation starts.
