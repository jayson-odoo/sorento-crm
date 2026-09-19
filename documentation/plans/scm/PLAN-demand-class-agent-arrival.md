# PLAN - demand class follows the agent when the agent arrives late

**Status:** built, in review. **Track: small fix** (two seams in one domain, under 50 app lines,
no migration, no endpoint, no auth or scoping change). Branch `fix/scm-demand-class-agent-arrival`.

## The ruling this serves

Captain, 28 Aug 2026: the demand class ladder is `stored order type -> stated order type ->
selling agent's demand class -> customer market segment`. The agent outranks the customer
because the sales force is split by channel and one debtor buys through both. One copy of the
ladder: `app/services/scm/demand_class.py::classify_document`.

## Measured, prod copy `sorento_ai_automation_0918_1900`, 20 Sep 2026

- AutoCount pushes a new sales order BEFORE its agent is filled. SO421912 (MATRIX IZEN SDN BHD
  (PROJECT), debtor 300-M169): first push 17 Sep 08:19 UTC carried `agent_code: null`,
  `sales_agent_ref: null`; the second push 09:37 UTC carried BRENDON (agent class `project`).
- On the first push the ladder had no agent, fell to the customer rung, read
  `market_segment_code = 'retail'`, and stored `retail`. On the second push
  `_classify_sales_order` returned early on the stored class, so BRENDON's `project` never
  applied. Same story on SO421432 (OPTAD MARKETING SDN BHD (PROJECT), agent JEREMY) and
  SO421913 / SO421915 / SO421919. CS flipped them by hand.
- Orders that NEVER get an agent are rare: 24 of about 139,000 AutoCount orders created since
  1 Sep 2026. So the customer rung stays a useful first answer; it must not be a final one.
- `sales_agent_service._backfill_null_class_orders` fills an agent's NULL-class orders
  customer segment FIRST, agent second. That is the pre-28-Aug order and now disagrees with
  the ladder.

## The change

### Seam 1 - `document_ingest_service._classify_sales_order`

The "stored class is never overwritten" early return gains ONE exception: the agent is
arriving on this push. Precisely: the stored header has `demand_class` set AND the stored
header's `sales_agent_id` is empty AND this push resolved a `sales_agent_id` whose agent
carries a demand class. In that case run `classify_document` exactly as for a new document
(so a stored or stated order type still wins over the agent) and write the answer when it is
not None. It never blanks a class.

Every other case is unchanged: a stored class with a stored agent is settled; a stored class
where the arriving agent has no demand class is settled.

Rejected alternative: leave the class NULL while the agent is null. It strands the orders that
never get an agent as unclassified, and the plan page has no Unclassified column.

### Seam 1b - `document_ingest_service._header_values` (fix round 1)

Reviewers found the blocker: an agent-less push (`sales_agent_ref` and `agent_code` both
empty, so `_resolve_master` returns `None`) BLANKED a stored `sales_agent_id` - the
`header_refs` loop wrote `values["sales_agent_id"] = None` unconditionally, and the setattr
loop after `_header_values` applied it. That re-arms Seam 1's exception by accident: a
hand-set `project` class on an order with a stored agent survives an agent-less push (Seam 1's
own guard), but the agent-less push itself blanks the stored agent, so the NEXT push naming a
different agent finds no stored agent, reads as "the agent is arriving for the first time",
and re-decides the class. It also let an API caller pick the class by alternating agent codes.

Measured, same prod copy, `api_call_log` (2031 sales-order pushes): an agent followed by an
agent-less push happened 0 times; agent-less then an agent, 5 times; agent A changed to a
DIFFERENT agent B, 7 times. Nothing legitimate relies on an agent-less push blanking a stored
agent.

Fix: in `_header_values`'s `header_refs` loop, when the resolved value for `sales_agent_id` is
`None` AND the stored header already has an agent, the key is dropped from the header-values
dict instead of being set to `None`. Dropping the key (not writing `None` over it) keeps it off
the unconditional setattr loop AND off `_diff`'s dry-run report, so an agent-less re-push
neither blanks the column nor is reported as changing it. Scoped to `sales_agent_id` only
(the only column this spec resolves that has this problem); `customer_id` and the
purchase-orders spec are untouched - `sales_agent_id` is a sales-orders-only column, so the
guard cannot reach a PO. A push naming a DIFFERENT agent still overwrites it (A -> B unchanged)
and still does not re-decide the class, because `header.sales_agent_id` stays non-empty for
that push.

### Seam 2 - `sales_agent_service._backfill_null_class_orders`

Collapse the two UPDATEs into one: every order with `sales_agent_id = agent.id AND
demand_class IS NULL` takes the agent's class. A NULL-class row has already had its order type
found silent, and the agent outranks the customer, so the segment branch is dead weight that
contradicts the ladder. Rewrite the docstring to say so. `_PROJECT_SEGMENT_MATCH_SQL` goes if
nothing else uses it.

## Out of scope

- Data repair on prod (customers named "(PROJECT)" with a retail or blank segment; agent LCL's
  per-customer split). Owner-run SQL, drafted separately.
- Any per-customer override rung above the agent.

## Risks accepted

1. A class hand-set while the order had NO agent yet is re-decided, once, the first time an
   agent with a demand class of its own arrives (Seam 1's exception, unchanged by round 1). A
   project-to-retail flip on that re-decision removes the order from the fulfilment board, the
   reconciliation worklist, the order-inquiry import and any open line drafts built against it.
2. Pre-existing, out of scope: `_backfill_null_class_orders`'s UPDATE carries no company
   predicate, so a shared agent row (`company_id IS NULL`) reaches that agent's orders across
   every company - the same row set the UPDATE touched before this lane, single-UPDATE or two.
3. Pre-existing: `sales_orders` carries no audit tracking, so a demand-class change (by either
   seam, or by hand) leaves no audit row behind.
4. Migration `401_so_class_segment_rank.py` moved about 63 prod rows to the customer segment's
   class under the pre-28-Aug ranking. Those rows are non-NULL today, so neither seam touches
   them - Seam 1 never overwrites a stored class, and Seam 2 only fills `demand_class IS NULL`.

## Tests (Postgres only, shared dev DB, touched files only)

- `tests/test_ingest_documents_v2_demand.py` - extend.
- `tests/scm/test_sales_agent_demand_class_backfill.py` - extend / correct.

Fix round 1 additions: AC-11 (new test), AC-12 (folded into AC-3's own test - the assertion
that a later push naming a different agent still replaces the stored agent id), and AC-6
strengthened to a two-push regression (agent-less push, then a push naming a different agent)
that reproduces the blanking bug before Seam 1b.
