# UAC: PORTAL-P2-ONLY-THEIRS

Copied from the P2 brief (`PLAN-portal-unify-scout-27oct.md`, PR #1894). "Limited user" = holds a
module's `view_own` and not its `view`, and is not admin/superadmin.

1. Per module, a limited user's list holds only their rows (two salespeople, two contacts, rows
   for each, seeded in the test).
2. A foreign id returns 404 on the detail route and on EVERY child route. For projects the test
   enumerates `app.routes` under the project-sales router with a `{project_id}` path parameter and
   asserts 404 for a foreign project on each.
3. Writes (edit, delete, child creates) on foreign rows return 404.
4. Holders of `VIEW` (staff), admin and superadmin get identical results to before (regression
   assertions), and a user holding both `VIEW` and `VIEW_OWN` behaves as `VIEW`.
5. Conversations: list, page, search, comments, window, media limited to their agents' customers;
   foreign `contact_ref` 404; reply still needs `REPLY`.
6. Cross-cutting readers closed for a foreign id: form comments, activities, downloads/exports,
   AI assistant record context, global search; none of the P2 models is a generic list-query
   resource.
7. Linked contact null: the limited user sees only rows keyed on their user id.
8. One migration, single alembic head, no role grant, no FE change.
