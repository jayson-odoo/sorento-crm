# PLAN: self-reference turns never refuse on carried foreign customers

Status: in progress, small fix track (no migration, no auth/RBAC change, no new ingest surface).
Lane: CHATBOT-SELFREF-SCOPE. Parent: `PLAN-chatbot-customer-scope-29sep.md` (PR #1365).

## Symptom (production, 30 Sep 2026)

A contact linked to six HANLIM TRADING customers asked "I want to check my sales today".
Parser verdict: `business_query`, `order_status="sales_report"`, `self_reference=true`,
`entities=[]`. The bot answered the scope refusal line and called no tool.

## Cause

The cold path is right: `engine._customer_scope_gate` hands a self-reference turn with no
typed customer word all the linked ids. The refusal came from CARRIED state instead:

- `engine._screen_resolver_for_scope` is fed carried entities
  (`turn_runtime.with_carried_entities`) and refuses when every match of a token is a
  customer outside the links, or when a dropped row sat on an offer payload.
- `fetch.entity_ids_transformer` raises `ScopeViolation` when the offer's carried
  `customer_ids` hold an id outside the links.
- The tier-probe seam in `lanes/business/__init__.py` re-raises the same refusal and writes
  no trace event.

Owner rulings (parent plan, Decisions Q5/Q6/Q7): self-reference substitutes the links, the
answer spans ALL linked customers, and the refusal text is for a TYPED foreign customer word
only.

## Change

R1 A self-reference turn with no customer word in the current message never refuses. Carried
   entities or carried `customer_ids` outside the links are dropped or clamped to the links,
   the linked customers become the subject, the tool runs. Applied at every seam.
R2 A typed foreign customer word still refuses exactly as today (AC-CS-10/11).
R3 One test per seam reproducing the production shape (a prior turn carrying a foreign
   customer, then the self-reference turn).
R4 Every scope decision writes a `customer_scope` trace record with the reason and the ids
   dropped, the tier-probe seam included.
R5 No parser or prompt change, no migration.
