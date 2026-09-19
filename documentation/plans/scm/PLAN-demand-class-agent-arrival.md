# PLAN - demand class follows the agent when the agent arrives late

**Status:** building. **Track: small fix** (two seams in one domain, under 50 app lines, no
migration, no endpoint, no auth or scoping change). Branch `fix/scm-demand-class-agent-arrival`.

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

## Tests (Postgres only, shared dev DB, touched files only)

- `tests/test_ingest_documents_v2_demand.py` - extend.
- `tests/scm/test_sales_agent_demand_class_backfill.py` - extend / correct.
