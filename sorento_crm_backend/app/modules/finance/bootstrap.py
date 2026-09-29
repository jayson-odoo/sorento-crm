"""Finance module bootstrap (plan 3.5, #1309).

`MODULE_KEY` is what `require_module_enabled_with_api_key` will gate `/api/v1/finance/*` on
(S2) and what the invoiced basis in the sales reports checks (S1). The module owns the Postgres
schema `finance` (created by `fin_0001_billing_documents`, which holds `billing_documents` and
`billing_document_lines`). S0 adds no router: the only door is the existing
`/external/ingest/billing_documents`.
"""

MODULE_KEY = "finance"
