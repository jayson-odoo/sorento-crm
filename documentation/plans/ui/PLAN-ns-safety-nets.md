# PLAN: never-stuck safety nets (levers L6, L8, L9)

Status: in progress (small fix track: FE only, no migration, no RBAC change; the permission
gate's *failure* path changes, not who is allowed). Lane NS-SAFETY-NETS.

Standard: `documentation/reference/NEVER-STUCK-UI.md` (S3, S5). Audit:
`documentation/reports/AUDIT-never-stuck-2026-10-01.md` (PR #1416). Owner rule, 1 Oct 2026:
nothing may hang; every failure ends in a clear, honest state.

Out of scope: session / sign-out (L1, lane SESSION-NEVER-STUCK), shared-lookup permissions
(L10, owner call pending), DataGrid error state (L2), pickers (L5), polling (L7).

## Shared fixes

### L8: boundaries (rows 33, 40)

- `components/common/RouteErrorScreen.tsx`: one fixed-copy error screen (never
  `error.message`; `digest` shown as a reference). Detects a chunk-load failure (deploy skew:
  the browser holds an old build whose chunks are gone) and offers **Reload** (full
  `window.location.reload()`, the only thing that fetches the new build) instead of `reset()`.
- `app/global-error.tsx` + `components/common/GlobalErrorView.tsx`: own `<html>`/`<body>`,
  plain markup and inline styles, no UI-primitive imports (the root layout's providers, CSS or a
  shared chunk may be what failed), Reload button. Catches a failed `ssr:false` chunk load of
  `DynamicClientProviders`.
- `error.tsx` in `app/(auth)`, `app/(public)`, `app/unsubscribe`, all rendering
  `RouteErrorScreen`, none with a staff link: `(auth)` also holds customer pages (portal,
  quotation-sign, view, approval, forms). `(protected)/error.tsx` keeps its copy and gains the chunk-load Reload.

### L6: permission-load failure is not "no access" (row 34)

- `usePermissions()` exposes `isError` = the permissions query failed and holds no data
  (a failed background refetch over a good cached set is still "data").
- `RequireAccess` (permission mode): `isError` renders `PermissionsLoadError` ("Could not
  check your access" + Retry calling `refetch`), never `AccessDenied`.
- `useHasPermission` / `useHasAnyPermission` consumers (452 call sites) cannot each render an
  error, so the protected layout shows one banner with Retry while the permissions query is
  failed. Buttons stay hidden (fail closed) but the user is told why and can retry.

### L9: detail layouts branch on error before drawing tabs (rows 11, 12, 15)

- `components/common/LoadErrorState.tsx`: "Could not load X" + message + Retry, and
  `QueryErrorState` (403 -> `AccessDenied`, else `LoadErrorState`). `lib/api-client.ts` gains
  `apiError` (status-carrying), `isAccessDenied`, `isNotFound` (S3 snippet) and
  `retryUnlessRefused` (one retry for a fault, none for a 403 / 404). The three layout queries
  and the permissions query set `meta: { silent: true }` (S4.3): the failure is shown in place,
  not toasted on top. `query-provider.tsx` uses `isAccessDenied` for its permission toast.
- A failed background refetch over data already shown keeps the data in all three layouts.
- `user-management/users/[id]/layout.tsx` (row 11): error -> AccessDenied / not-found /
  LoadErrorState before the tabs render; the 404 redirect moves out of `queryFn` into an
  effect on the settled error, using `router.replace` (S6.4).
- `user-management/settings/layout.tsx` (row 12): a failed settings read renders
  LoadErrorState instead of the tab bodies, so no tab can draw (and Save) blank defaults.
- `user-management/contacts/[id]/layout.tsx` (row 15): same, no endless skeleton, no "not
  found" for a refused or failed read. `page.tsx` needs no change: the layout no longer renders
  `children` until the record is there.

## Tests (red first, vitest)

1. L8: `RouteErrorScreen` shows fixed copy (not the message), the digest, Retry calls
   `reset`; a ChunkLoadError shows Reload. `global-error` renders html/body + Reload.
   Each route group has an `error.tsx` (file presence test).
2. L6: `RequireAccess` with a failed permissions query shows "Could not check your access" and
   Retry refetches; denied still shows AccessDenied; banner shows on failure only.
3. L9: each of the three layouts with a 500 renders the error + Retry and no tab body; a 403
   renders AccessDenied; settings layout with a failed read renders no Save button.

Kill test: revert each fix, the matching test goes red.
