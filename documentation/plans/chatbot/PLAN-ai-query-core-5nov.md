# PLAN: AI-QUERY-CORE (phase 1 of the AI tools standard)

Status: in progress 5 Nov 2026 (Build). Track: full (multi-company reads, RBAC). Lane AI-QUERY-CORE.

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
