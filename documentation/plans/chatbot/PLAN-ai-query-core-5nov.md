# PLAN: AI-QUERY-CORE (phase 1 of the AI tools standard)

Status: review done 5 Nov 2026 (two fix rounds; reviewer and security reviewer findings fixed), waiting on the owner's go
to merge. Track: full (multi-company reads, RBAC).
Lane AI-QUERY-CORE, PR #2188.

Parent plan: `PLAN-ai-tools-standard-5nov.md` section 4 "QUERY-CORE" (branch `claude/ai-tools-scout-mcp-vea9ka`,
PR #2185). UAC: `ai-tools-standard-acceptance-criteria.md` AC-1, AC-2, AC-3, AC-6, AC-9.

## Scope

- `app/services/assistant_registry/` (core, no import of `app/services/chatbot`): `FieldDef`, `EntityDef`, the query
  compiler and runner, pilot entities `order`, `product`, `purchase_order`, `complaint`.
- `crm_query` and `crm_describe` agent tools (`app/services/chatbot/agent/query_tools.py`), run in process under
  `run_as_user`; offered to staff principals on the panel and to linked-user WhatsApp turns, never to a contact
  principal.
- Caps: 50 rows, 200 groups, `SET LOCAL statement_timeout = 5000`.
- The 12 tests of the parent plan's QUERY-CORE section.

Out: actions, `tools_search`, CI gate. No change to who holds the agent slug; `chatbot_agent_enabled` default unchanged.

## Measured facts (read 5 Nov, base 8cc55cdb)

- In-process reads are `writes.UserRead` rows in `writes.USER_READS`; offered by `permitted_user_reads`
  (`app/services/chatbot/agent/writes.py:471`, empty for `ctx.principal == "contact"`) and run by `run_user_read`
  (`writes.py:481`). `run_as_user` (`writes.py:143`) stamps the user's company scope (`_scope_for_user`, one active
  company) and the audit actor; the brand scope already on the session stays.
- `do_orm_execute` filters every `CompanyScopedMixin` model (`app/models/base.py:113`). `Order`, `Product`,
  `PurchaseOrder` (procurement, `purchase_orders`), `Supplier`, `Customer`, `Brand`, `ProductCategory` are company
  scoped. `Complaint` is NOT (`app/models/complaints.py:14`); its list narrows only by brand
  (`complaint_in_scope_clauses`, `app/services/complaints_service.py:447`), so the registry repeats that clause.
- Screen slugs: orders `order_management.orders.view` (`api/v1/order_management/orders.py`, menu `:288`); products
  `master_data.products.view` (menu `:578`; the route itself takes any signed-in user); SCM purchase orders
  `scm.dashboard.view` (`api/v1/scm/purchase_orders.py:37`, menu `:502`); complaints
  `complaint_management.complaints.view` / `.view_own` (`own_scope.REQUEST_KINDS`, own = row's `contact_id` is the
  user's contact, `own_scope.request_clause`).
- Modules: order `order`, product `product`, purchase order `scm`, complaint `complaints` (`api/v1/__init__.py`).
- Orders list excludes `deleted_at` rows (`order_service.py:945`).
- Naive timestamps are stored UTC (`activity_service.py:480`), so a date bucket converts UTC to Asia/Kuala_Lumpur;
  `Date` columns are bucketed as is.

## Contract (what the tests are written against)

`app/services/assistant_registry/`:

- `types.py`: `FieldDef(label, permission=None, column=None)` (`column` defaults to the field key);
  `EntityDef(key, label, module, model, view_permission, own_permission, own_clause, fields, relations, screen_path,
  pages=(), routes=(), scope=None)`. `view_permission=None` marks a lookup entity reachable only through a relation
  (not listed, not queryable directly; its fields are read under the parent's slugs). `own_clause(me)` returns the
  "only theirs" SQL clause (`own_scope.Me`) and replaces the parent plan's `owner_column`, because the complaint's
  own rule is the contact, not a user-id column. `relations: {name: (entity_key, fk_column)}`. `scope(db)` returns
  extra always-on clauses (orders: not deleted; complaints: brand scope).
- `ENTITIES: dict[str, EntityDef]` collected from every module file in the package.
- `query.run_query(db, user_id, spec) -> dict` and `query.describe(db, user_id, entity=None) -> dict`, both
  raising `query.QueryRefused(code, message)` with `code` in `unknown_entity`, `unknown_field`, `restricted`,
  `no_access`, `own_only_unsupported`, `module_disabled`, `invalid`, `too_deep`, `timeout`.
- Spec: `entity`, `fields`, `filters [{field, op, value}]`, `group_by [field | {field, bucket}]`,
  `aggregates [{fn, field?}]`, `sort [{field, dir}]`, `limit`. Ops: eq, ne, in, not_in, lt, lte, gt, gte, between,
  contains, starts_with, is_null, is_not_null. Buckets: day, week, month, quarter, year. Fns: count,
  count_distinct, sum, avg, min, max (sum / avg on numeric fields only). Aggregate alias `<fn>_<field>` or `count`.
  Dotted paths through relations, at most 2 hops.
- Row result: `{"entity", "rows": [{"id", "link", <field>: value}], "total", "truncated", "restricted": [...]}`;
  a selected field whose slug the user lacks is dropped and named in `restricted`; the same field in a filter,
  group, aggregate or sort refuses the whole query (`restricted`). Group result:
  `{"entity", "groups": [{<group key>: value, <alias>: value}], "total_groups", "truncated"}`.
- Caps: `MAX_ROWS = 50`, `MAX_GROUPS = 200`, `STATEMENT_TIMEOUT_MS = 5000` (`SET LOCAL` inside a savepoint, so a
  timeout rolls back to it and the session stays usable).

`app/services/chatbot/agent/query_tools.py` registers `crm_query` and `crm_describe` as `UserRead`s in
`writes.USER_READS` (user slug `""`: the entity's own slug is checked inside, per entity), each run under
`run_as_user`; `QueryRefused` becomes `ToolResult("denied"|"invalid"|"timeout", message=...)`. Linked-only: not
offered when a console operator acts for someone else (an aggregate cannot be intersected across two people).

## Decisions made in review (5 Nov)

- **Relations join plain table aliases**, each carrying its own company predicate in the ON clause, and the root's
  company predicate is stated in the WHERE clause. The session's automatic criterion is not adapted to an ORM alias
  inside a join (Postgres refused `supplier.name`), and is not attached when only relation columns are selected.
- **Brand scope (WhatsApp linked user):** `order` repeats the screen's rule (only orders with a line of an in-scope
  product, `order_service.scope_product_filter`). The header money fields (`subtotal_amount`, `total_amount`) carry
  `FieldDef.whole_document`: refused while a brand scope is set, because the screen recomputes them from the
  in-scope lines and the header total counts the others. Complaints repeat `complaint_in_scope_clauses`.
- **Customer-scoped WhatsApp contact** (linked customers, no office access type): today every WhatsApp read of it is
  narrowed to those customers; these tools run as the linked user and cannot narrow by customer, so they are not
  offered off the panel (`UserRead.available`). Owner can relax this.
- **Offer rule:** the tools are offered to a user holding at least one registered entity's view or own slug
  (`query_tools.ANY_ENTITY`), and not when a console operator acts for someone else (`linked_only`).
- **Complaint product codes:** the header lists every line's code and the screen cuts it to the contact's brands,
  so `product_code` is `whole_document` too.
- **Lookup module:** a relation's target module is checked; a lookup carries the module of the screen showing it.
- `crm_query`'s schema is kept small for the token budget, but every array names its `items` and every object its
  `properties`: Gemini refuses anything less with a 400 and the whole turn fails (crew browser pass, 5 Nov).
  `tests/chatbot/agent/test_agent_tool_schemas_gemini.py` checks every agent tool's converted declaration.

## Token measurement (AC-6)

OpenAI `responses/input_tokens`, gpt-4.1 tokenizer, the same request with the in-process tool block (USER_READS,
WRITES, plan and answer schemas) before and after, measured again on the head merged with main of 5 Nov evening: 2145 before, 2474 after,
**+329 input tokens per model call** for a user offered the tools (+254 on the first head, +305 after the Gemini fix,
+329 after the naming and field-note guidance below). The MCP catalogue part of the request is unchanged. AC-6 ("no higher than before phase 1")
is not met by this lane alone; the parent plan's lever is the module waves replacing per-module tools with
registry entities.

## Crew browser pass on 826964f2 (5 Nov) and what changed

- Steps 1, 2, 4, 5 passed. Step 3 grouped "per agent" by `salesman`, while the Delivery Orders list's Agent column is
  `agent`; step 7's counts (list 101 / 87 / 11 vs bot 99 / 86 / 11) compared the list's agent with the bot's
  salesman. `test_R3_per_agent_counts_equal_the_delivery_orders_lists_own_filter` runs the list's own search
  (`ListQuerySearchService`, the Filters dialog's path) against `crm_query` grouped by `agent` over rows that differ
  on cancelled, deleted, order date vs created date and agent vs salesman: the counts are equal, so the gap was
  the field choice. It passed before the change (a regression proof, not a red test).
- `FieldDef.note`, shown by `crm_describe`: `agent` is the list's Agent column and the field for per agent
  questions, `salesman` is not, `order_date` is the date the list filters on, `created_at` is not.
- Step 6 listed products by code and price without the name although the query read it. `EntityDef.name_by`: every
  row carries the fields a record is named by (product code and name, order number and debtor, PO number,
  complaint number and customer), and the result's `name_rows_by` tells the model to name each row by them.
- Steps 3 and 6 are model choices; the change gives the model the facts and the instruction, and crew's re-pass
  is the check.
