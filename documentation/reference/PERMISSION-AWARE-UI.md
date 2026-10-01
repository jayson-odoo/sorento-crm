# Permission-aware UI standard

Status: binding for new frontend work from 1 Oct 2026 (lane PERM-UI-AUDIT). Audit of the
current gaps: `documentation/reports/AUDIT-permission-ui-2026-10-01.md`.

Why this exists: PR #1413 (PL-TABS-ACCESS) found packing-list detail tabs reading SCM
endpoints that require `scm.dashboard.view`. The UI never checked that slug, so the tabs
showed for everyone; the tab bodies branched only on `isLoading`, so the 403 rendered as
"No proforma invoice"; and the user also got a retry delay plus the global permission toast
(`providers/query-provider.tsx:83-101`). Every helper needed to avoid that already existed.
This page says how to use them so it does not happen again.

The backend is the enforcement. The frontend's job is to never *show* something the backend
will refuse, and to say "no access" honestly when it does refuse.

## Facts the rules rely on

- Backend gates: `require_permission(slug)` / `require_any_permission([...])` and their
  `_with_api_key` twins, `sorento_crm_backend/app/dependencies.py:384-560`, plus a module guard
  per router in `app/api/v1/__init__.py`. Their 403 `detail` strings are exactly
  `Permission required: <slug>`, `One of these permissions required: ...` and
  `Module not enabled: <module>` (`dependencies.py:396,456,462`, `modules/runtime/guards.py`).
- Superadmin and admin pass every backend gate (`user_service.py:1501`), and
  `GET /user-management/users/me/permissions` returns them every slug **that exists as a row in
  the permissions table** (`user_service.py:1468-1470`). A slug used in `require_permission`
  but never seeded therefore lets an admin through the backend while the UI hides the screen.
- FE errors are plain `Error(message)` built by `extractApiError` (`lib/api-client.ts`); the
  HTTP status is not carried. Today the only way to recognise a 403 is the message prefix.
- Helpers: `usePermissions` / `useHasPermission` / `useHasAnyPermission`
  (`hooks/usePermissions.ts:9-35`), `RequireAccess` + `AccessDenied`
  (`app/components/common/RequireAccess.tsx:28`, `AccessDenied.tsx`), menu gating via
  `permission` / `permissionsAny` (`config/types.ts:17-20`, `config/menu.config.tsx`), and the
  per-query toast opt-out `meta: { silent: true }` (`providers/query-provider.tsx:54`).

## Rule 1. One permission constant per route group, shared by FE and BE

Backend: a router declares its read and write gates once, as module-level constants, and
every route uses them. No inline slug strings on individual routes.

```python
# app/api/v1/scm/proforma_invoices.py
SCM_READ = "scm.dashboard.view"
SCM_EDIT = "scm.dashboard.edit"
_READ = require_permission(SCM_READ)
_EDIT = require_permission(SCM_EDIT)

@router.get("/proforma-invoices/{pi_id}")
def get_pi(pi_id: str, _u: dict = Depends(_READ), db: Session = Depends(get_db)): ...
```

Frontend: the feature service that owns the URL also owns the slug. It exports one `*_PERMS`
object; menu entries, tabs, buttons and `RequireAccess` import it. A literal slug string in a
component is a review defect.

```ts
// app/(protected)/scm/services/proformaInvoiceService.ts
/** Mirrors SCM_READ / SCM_EDIT in app/api/v1/scm/proforma_invoices.py. */
export const PROFORMA_PERMS = {
  read: 'scm.dashboard.view',
  edit: 'scm.dashboard.edit',
} as const;

export async function getProformaInvoice(id: string) {
  const res = await apiFetch(`/api/v1/scm/proforma-invoices/${id}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load proforma invoice'));
  return res.json();
}
```

The `// Mirrors ...` comment names the backend constant. That comment is what the manifest
test in the audit report keys on, so keep it exact.

## Rule 2. Tabs, menu items and buttons are gated by the slug the backend route requires

The gate is the slug of the endpoint the surface *reads* (for a tab or page) or *writes* (for
a button). Not a neighbouring slug that "usually comes with it".

```tsx
const canSeePi = useHasPermission(PROFORMA_PERMS.read);
const canSeeGrn = useHasPermission(GRN_PERMS.read);

const tabs = [
  { value: 'lines', label: 'Lines' },                              // reads this record's own route
  canSeePi && { value: 'proforma', label: 'Proforma invoice' },    // cross-module read, Rule 6
  canSeeGrn && { value: 'grn', label: 'GRN' },
].filter(Boolean) as TabDef[];
```

- A hidden tab is removed from the tab list, not rendered disabled.
- A tab's query is only enabled when the tab is allowed: `enabled: canSeePi && !!id`.
- Buttons: hide when the user lacks the write slug. Do not show a button that always 403s.
- Menu: the leaf's `permission` is the slug of the list endpoint the page loads first.

## Rule 3. Every data hook's consumer renders four states

Loading, error, empty, data. Branching on `isLoading` alone is a defect: when the query
errors, `data` is undefined and the empty state renders a lie.

```tsx
const { data, isLoading, error } = useProformaInvoice(id, { enabled: canSeePi });

if (isLoading) return <TabSkeleton />;
if (error) {
  return isAccessDenied(error)
    ? <AccessDenied variant="inline" />                 // Rule 4
    : <InlineError message={error.message} onRetry={refetch} />;
}
if (!data) return <EmptyState title="No proforma invoice" />;
return <ProformaInvoiceView pi={data} />;
```

`isAccessDenied` is the one place that recognises a refusal. It does not exist yet; the
follow-up lane adds it to `lib/api-client.ts` next to `extractApiError`:

```ts
const ACCESS_DENIED_PREFIXES = [
  'Permission required:',
  'One of these permissions required',
  'Module not enabled:',
];
export function isAccessDenied(error: unknown): boolean {
  const msg = error instanceof Error ? error.message : '';
  return ACCESS_DENIED_PREFIXES.some((p) => msg.startsWith(p));
}
```

If a status-carrying error is ever added, only this function changes; call sites stay.
`providers/query-provider.tsx:83-85` must use this helper too. It currently matches
`One of these permissions required:` with the colon, so it misses both the strict-mode variant
`One of these permissions required (module may be disabled): ...` (`dependencies.py:456`) and
`Module not enabled: ...`; both of those toast the raw backend string instead of the friendly
permission toast.

## Rule 4. A 403 renders `AccessDenied` in place: no toast, no retry

- In place: a page renders the full-page `AccessDenied`; a tab or panel renders the same
  component in its inline variant (an `inline` prop is part of the follow-up lane: smaller
  padding, no "Back to dashboard" button, same copy). Never a raw red error card with the
  backend string.
- No toast: a component that renders all four states sets `meta: { silent: true }` on its
  query. The global toast stays as the fallback for components that have not been fixed yet,
  so it is not removed until the audit rows are closed.
- No retry: a 403 will not become a 200 on retry, and retrying adds a visible delay before
  the denied state. The shared default becomes:

```ts
retry: (failureCount, error) => !isAccessDenied(error) && failureCount < 1,
```

## Rule 5. Every deep-linkable page is wrapped in `RequireAccess`

The sidebar hides a link; it does not stop a pasted URL, a bookmark or a notification link.
Each `page.tsx` (or the segment's `layout.tsx`, when every child needs the same slug) wraps
its body in `RequireAccess` with the slug of the page's primary read:

```tsx
// app/(protected)/scm/packing-lists/[id]/page.tsx
export default function Page() {
  return (
    <RequireAccess permission={PACKING_LIST_PERMS.read}>
      <PackingListDetail />
    </RequireAccess>
  );
}
```

`RequireAccess` shows a loader while permissions resolve and `AccessDenied` (not a redirect)
when denied, so it never flashes the wrong state.

## Rule 6. Cross-module reads are declared, not discovered

A screen in module A that reads an endpoint of module B (a procurement page reading SCM, an
order detail reading inventory, a project page reading procurement) must:

1. Import module B's `*_PERMS` constant. Never re-type B's slug, never assume A's slug implies it.
2. Gate the surface on B's slug (Rule 2) and enable B's query only when allowed.
3. Render B's 403 as an inline `AccessDenied` (Rules 3-4). The rest of A's page stays usable.
4. Remember B's **module guard**: if module B is disabled for the tenant, B's routes 403 with
   `Module not enabled:` even for a user holding the slug. `isAccessDenied` covers it.

The import line is the declaration. A reviewer can see from a component's imports which other
modules it depends on, and the manifest test can list them.

## Review checklist (add to PR-CHECKLIST.md)

- [ ] Every new endpoint call goes through a service that exports a `*_PERMS` constant naming
      the backend constant it mirrors.
- [ ] Every tab / menu leaf / button is gated with that constant; no slug string literals.
- [ ] Every query consumer handles loading / error (403 vs other) / empty / data.
- [ ] 403 renders `AccessDenied` in place; the query is `meta: { silent: true }`.
- [ ] Every new `page.tsx` is under a `RequireAccess`.
- [ ] Cross-module reads import the other module's `*_PERMS` and gate on it.
- [ ] A new backend slug is seeded as a permissions row (otherwise admins are hidden from it).
